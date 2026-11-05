#!/usr/bin/env python3
"""Entry point behind the rpg-factory slash commands. Validates arguments, then runs the real script.

  status [--remote] [--json]              factory-status.py: pending cross-repo work, evidence, freshness
  route (--domain ID | --kind KIND) | <repo> <path>... [--lead SKILL] [--json]
                                          factory-context.sh: domain or file routing, contracts, checks
                                          and gates for those files, and why
  check <repo> [<path>...] [--status] [--json]
                                          run-checks.py (fast tier) - or --status: grade stored evidence
                                          against the current tree without running anything
  doctor [--json]                         install state, registry, state paths, tools,
                                          dev tools (MCP servers, plugins, binaries) per skill
  domain [<id>] [--json]                  registry domains: lead, repos, artifact kinds, gates, handoffs,
                                          authoring artifact counts, stale/FAIL/HUMAN_REQUIRED, next steps
  workflow plan|status|dispatch|report     dependency-aware artifact workflow entry point
  pipeline tier|validate|planner|dispatch|verdict|gate|cleanup|status [args]
                                          factory-pipeline.py: task tier, plan validation, worker dispatch
                                          commands, review/QA verdicts, the READY_FOR_PR gate and run status
  ui [--json] [--project DIR] [--uitoolkit-ref REF] <request...>
                                          scripts/ui/ui_plan.py: UI plan - intent, ONLY the UI skills
                                          needed, lead route, missing context, components (exit 3 =
                                          NEEDS_CONTEXT)
  ui-figma | ui-components | ui-screen | ui-review  [same options] <request...>
                                          the same plan with the intent family forced (Figma import,
                                          component selection, screen implementation, review)
  help [--json]                           every command with its arguments, an example, the Claude form
                                          (/rpg-factory:<verb>) and the Codex form (python3 -B ...)

Read-only except `check` without --status, which runs the fast checks (builds/tests) exactly like
run-checks.py (`workflow dispatch` only prints a contract). Exit code = the underlying script's; 2 = usage error.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
sys.path.append(os.path.join(HERE, "lib"))  # appended: stdlib lookups must not stat /mnt/c first
from shells import find_bash  # noqa: E402

BASH = find_bash() or "bash"  # never the System32 WSL launcher on Windows
CODEX = "python3 -B " + os.path.join(ROOT, "scripts", "factory-cmd.py").replace(os.sep, "/")  # the shell form of a verb


def usage(msg=None):
    if msg:
        print(f"factory-cmd: {msg}\n", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


def registry():
    return json.load(open(os.path.join(ROOT, "registry.json"), encoding="utf-8"))


def run(argv):
    sys.stdout.flush()
    return subprocess.run(argv, env={**os.environ, "CLAUDE_PLUGIN_ROOT": ROOT}).returncode


def split_args(args):
    """Accept `a b`, `a,b` and a single quoted "a b" argument (slash commands pass one string)."""
    out = []
    for a in args:
        for part in a.replace(",", " ").split():
            out.append(part)
    return out


def repo_and_paths(args, verb):
    reg = registry()
    if not args:
        raise ValueError(f"{verb} needs a repo: {' | '.join(reg['repos'])}")
    if args[0] not in reg["repos"]:
        raise ValueError(f"unknown repo '{args[0]}'; repos: {' | '.join(reg['repos'])}")
    return args[0], args[1:]


def cmd_status(args):
    extra = [a for a in args if a in ("--remote", "--json")]
    if [a for a in args if a not in ("--remote", "--json")]:
        raise ValueError("status takes only --remote and --json")
    return run([sys.executable, "-B", os.path.join(ROOT, "scripts", "factory-status.py"), *extra])


def cmd_route(args):
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if args and args[0] in ("--domain", "--kind"):
        # selector form: --domain <id> | --kind <kind>, optionally with --domain/--lead to resolve an AMBIGUOUS kind
        if len(args) % 2:
            raise ValueError(f"route {args[0]}: every flag needs exactly one value")
        for flag, value in zip(args[::2], args[1::2]):
            if flag not in ("--domain", "--kind", "--lead") or value.startswith("--"):
                raise ValueError(f"route {args[0]} accepts only --domain, --kind and --lead with one value each")
        return run([BASH, os.path.join(ROOT, "scripts", "factory-context.sh"), *args] + (["--json"] if as_json else []))
    lead = None
    if "--lead" in args:
        i = args.index("--lead")
        if i + 1 >= len(args):
            raise ValueError("--lead needs a skill name")
        lead, args = args[i + 1], args[:i] + args[i + 2:]
    repo, paths = repo_and_paths(args, "route")
    if not paths:
        raise ValueError("route needs at least one repo-relative path (the files the task will write)")
    argv = [BASH, os.path.join(ROOT, "scripts", "factory-context.sh"), "--repo", repo, "--explain"]
    if as_json:
        argv.append("--json")
    if lead:
        argv += ["--lead", lead]
    return run(argv + ["--paths", *paths])


def cmd_check(args):
    flags = [a for a in ("--status", "--json") if a in args]
    args = [a for a in args if a not in ("--status", "--json")]
    repo, paths = repo_and_paths(args, "check")
    argv = [sys.executable, "-B", os.path.join(ROOT, "scripts", "run-checks.py"), "--repo", repo, *flags]
    if paths:
        argv += ["--paths", *paths]
    return run(argv)


def capture(argv):
    p = subprocess.run(argv, env={**os.environ, "CLAUDE_PLUGIN_ROOT": ROOT}, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout


def workspace(reg):
    return os.environ.get(reg["workspace"]["root_env"]) or reg["workspace"]["root_default"]


def cmd_doctor(args):
    as_json = args == ["--json"]
    if args and not as_json:
        raise ValueError("doctor takes only --json")
    import fstate
    reg = registry()
    rc = 0
    install = [sys.executable, "-B", os.path.join(ROOT, "scripts", "install-status.py")]
    check_reg = [BASH, os.path.join(ROOT, "scripts", "check-registry.sh"), "--structure-only"]
    if as_json:
        irc, iout = capture(install + ["--json"])
        try:
            install_state = json.loads(iout)
        except ValueError:
            install_state = {"state": "UNKNOWN", "output": iout.strip()}
        rrc, rout = capture(check_reg)
        rc |= irc | rrc
        registry_state = {"ok": rrc == 0, "output": rout.strip().splitlines()}
    else:
        print("## Install")
        rc |= run(install)
        print("\n## Registry")
        rc |= run(check_reg)
    ws = workspace(reg)
    ok_ws = all(os.path.exists(os.path.join(ws, m)) for m in reg["workspace"]["root_markers"])
    repos = {k: {"path": os.path.join(ws, r["path"]), "optional": bool(r.get("optional")),
                 "present": os.path.isdir(os.path.join(ws, r["path"], ".git"))} for k, r in reg["repos"].items()}
    missing = [t for t in ("git", "jq", "python3", "bash") if not shutil.which(t)]
    import hookspeed
    alias = hookspeed.python_alias()  # detection only: doctor never changes PATH
    py3 = {"path": alias or shutil.which("python3"), "windows_store_alias": bool(alias), "advice": hookspeed.alias_advice()}
    hooks = json.load(open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8"))["hooks"]
    hooks = {e: [h.get("matcher") or "*" for h in v] for e, v in hooks.items()}
    import devtools
    prober = devtools.Prober(ws, reg)
    tools, gaps = [], {}
    for t in reg.get("dev_tools", []):
        res = prober.tool(t)
        tools.append({"id": t["id"], "kind": t["kind"], "required": bool(t.get("required")), "state": res["state"],
                      "ok": res["ok"], "detail": res["detail"], "fallback": t.get("fallback"), "used_by": t.get("used_by", [])})
        if res["state"] == "MISSING" and t.get("required"):
            for s in t.get("used_by", []):
                gaps.setdefault(s, []).append(t["id"])
    if missing or not ok_ws:
        rc |= 1
    if as_json:
        print(json.dumps({"schema": "rpg-factory.doctor/1", "install": install_state, "registry": registry_state,
                          "workspace": {"path": ws, "markers_ok": ok_ws, "scratch_state": fstate.scratch(),
                                        "persistent_state": fstate.persistent(), "tmpdir": os.environ.get("TMPDIR")},
                          "repos": repos, "tools": {"required": ["git", "jq", "python3", "bash"], "missing": missing, "python3": py3},
                          "hooks": hooks, "dev_tools": tools, "skill_gaps": gaps, "exit": rc}, indent=2))
        return rc
    print("\n## Workspace and state")
    print(f"- workspace {ws}: {'OK' if ok_ws else 'MARKERS MISSING'}")
    for k, r in repos.items():
        print(f"- repo {k}: {'present' if r['present'] else 'absent'} ({r['path']})")
    print(f"- scratch state: {fstate.scratch()}  (TMPDIR={os.environ.get('TMPDIR', '<unset>')!r})")
    print(f"- persistent state: {fstate.persistent()}")
    print(f"- tools: {'all present' if not missing else 'MISSING ' + ', '.join(missing)}")
    if py3["advice"]:
        print(f"- python3: {py3['advice']}")
    print("- hooks: " + "; ".join(f"{e} [{', '.join(m)}]" for e, m in hooks.items()))
    print("\n## Dev tools (registry dev_tools; names only are read from MCP/plugin config)")
    for t in tools:
        need = "required" if t["required"] else "optional"
        print(f"- {t['id']} ({t['kind']}, {need}): **{t['state']}** - {'; '.join(t['detail'])}"
              + (f" - fallback: {t['fallback']}" if not t["ok"] and t["fallback"] else ""))
    for s, ids in sorted(gaps.items()):
        print(f"- skill {s} lacks required tool(s): {', '.join(ids)}")
    return rc


def cmd_workflow(args):
    if not args or args[0] not in ("plan", "status", "dispatch", "report"):
        raise ValueError("workflow needs plan|status|dispatch|report followed by a spec")
    return run([sys.executable, "-B", os.path.join(ROOT, "scripts", "factory-workflow.py"), *args])


PIPELINE_VERBS = ("tier", "validate", "planner", "dispatch", "verdict", "gate", "cleanup", "status")


def cmd_pipeline(raw):
    """Arguments keep their text (a planner request has blanks and commas); one quoted string is split shell-style."""
    args = shlex.split(raw[0]) if len(raw) == 1 else list(raw)
    if not args or args[0] not in PIPELINE_VERBS:
        raise ValueError("pipeline needs " + "|".join(PIPELINE_VERBS))
    return run([sys.executable, "-B", os.path.join(ROOT, "scripts", "factory-pipeline.py"), *args])


UI_VERBS = ("ui", "ui-figma", "ui-components", "ui-screen", "ui-review")


def cmd_ui(verb, raw):
    """UI verbs keep the request text intact (no comma splitting); one quoted string is split on blanks."""
    tokens = raw[0].split() if len(raw) == 1 else list(raw)
    opts, words, i = [], [], 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--json":
            opts.append(t)
        elif t in ("--project", "--uitoolkit-ref"):
            if i + 1 >= len(tokens) or tokens[i + 1].startswith("--"):
                raise ValueError(f"{verb} {t} needs a value")
            opts += [t, tokens[i + 1]]
            i += 1
        elif t:
            words.append(t)
        i += 1
    text = " ".join(words).strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()  # "$ARGUMENTS" quoted once more by the caller
    if not text:
        raise ValueError(f"{verb} needs a request, e.g. {verb} Create an inventory screen")
    return run([sys.executable, "-B", os.path.join(ROOT, "scripts", "ui", "ui_plan.py"), "--verb", verb, *opts, text])


def cmd_domain(args):
    as_json = "--json" in args
    ids = [a for a in args if a != "--json"]
    if len(ids) > 1 or any(i.startswith("-") for i in ids):
        raise ValueError("domain takes at most one domain id and --json")
    import context
    import fstate
    from artifacts import domain_summary, scan
    reg = registry()
    domains = reg.get("domains", {})
    if ids and ids[0] not in domains:
        raise ValueError(f"unknown domain '{ids[0]}'; domains: {' | '.join(domains)}")
    ws = fstate.workspace(reg)
    auth = reg.get("repos", {}).get("authoring")
    auth_dir = os.path.normpath(os.path.join(ws, auth["path"])) if auth else None
    auth_present = bool(auth_dir and os.path.isdir(auth_dir))

    def base(did):
        r = context.domain_result(reg, did, ws)
        r["repos"] = [{"id": k, "path": os.path.normpath(os.path.join(ws, reg["repos"][k]["path"])),
                       "present": os.path.isdir(os.path.join(ws, reg["repos"][k]["path"])),
                       "optional": bool(reg["repos"][k].get("optional"))} for k in domains[did].get("repos", [])]
        r["uses_authoring"] = "authoring" in domains[did].get("repos", [])
        return r

    if not ids:
        arts = scan(auth_dir) if auth_present else {}
        rows = []
        for did in domains:
            r = base(did)
            counts = {}
            for art in arts.values():
                if art.get("domain") == did:
                    counts[art["status"]] = counts.get(art["status"], 0) + 1
            rows.append({"id": did, "lead": r["lead"], "status": r["status"],
                         "repos": {x["id"]: x["present"] for x in r["repos"]},
                         "artifacts": counts if r["uses_authoring"] and auth_present else None})
        if as_json:
            print(json.dumps({"schema": "rpg-factory.domain/1", "workspace": ws, "authoring_present": auth_present,
                              "domains": rows}, indent=2))
            return 0
        print(f"# Domains (registry; workspace {ws})\n")
        for row in rows:
            repos = ", ".join(f"{k} {'present' if v else 'absent'}" for k, v in row["repos"].items()) or "none"
            if row["artifacts"] is not None:
                arts_txt = ", ".join(f"{k} {v}" for k, v in sorted(row["artifacts"].items())) or "no artifacts yet"
            elif row["lead"] is None:
                arts_txt = "none (routes by module ownership)"
            else:
                arts_txt = "authoring repo absent"
            print(f"- {row['id']} [{row['lead'] or 'module ownership'}]: repos {repos}; artifacts: {arts_txt}")
        print(f"\nDetail: /rpg-factory:domain <id>  (Codex: {CODEX} domain <id>)")
        return 0

    did = ids[0]
    r = base(did)
    contracts = {c["id"]: c for c in reg.get("contracts", [])}
    r["handoffs"] = [{"id": h, "summary": c.get("summary"), "driver": c.get("driver"), "gate": c.get("gate"),
                      "from": c.get("source", {}).get("path"), "to": [x.get("path") for x in c.get("copies", [])]}
                     for h in r["handoffs"] for c in [contracts.get(h, {})]]
    order, cycle = context.handoff_graph(reg, did)
    r["handoff_order"], r["handoff_cycle"] = order, cycle
    summary = None
    if r["uses_authoring"] and auth_present:
        summary = domain_summary(reg, os.path.join(ROOT, "registry.json"), auth_dir, did)
    r["authoring"] = {"path": auth_dir, "present": auth_present} if r["uses_authoring"] else None
    for key in ("artifacts", "stale", "quality", "human_required", "failing"):
        r[key] = summary[key] if summary else None
    cmd = CODEX
    nxt = []
    if r["lead"]:
        nxt.append(f"invoke rpg-factory:factory-core, then the lead rpg-factory:{r['lead']}")
        nxt.append(f"route: /rpg-factory:route --domain {did}  (Codex: {cmd} route --domain {did})")
    else:
        nxt.append(f"route a change by its files: /rpg-factory:route <repo> <path>...  (Codex: {cmd} route <repo> <path>...)")
    if r["uses_authoring"] and not auth_present:
        nxt.append(f"the optional authoring repo is absent ({auth_dir}); {did} artifacts need it")
    elif r["artifact_kinds"]:
        nxt.append(f"plan artifacts: {cmd} workflow plan <spec.json> --json  (kinds: {', '.join(r['artifact_kinds'])})")
    if summary and (summary["stale"] or summary["failing"]):
        nxt.append(f"fix stale or failing artifacts with the lead, then recheck: /rpg-factory:status  (Codex: {cmd} status)")
    if summary and summary["human_required"]:
        nxt.append(f"HUMAN_REQUIRED: a person approves {', '.join(summary['human_required'])}; never self-approve")
    r["next"] = nxt
    if as_json:
        print(json.dumps({"schema": "rpg-factory.domain/1", "domain": r}, indent=2))
        return 0
    print(f"# Domain {did} ({r['status'] or 'unknown'})\n")
    if r["summary"]:
        print(r["summary"] + "\n")
    print(f"- lead: {('rpg-factory:' + r['lead']) if r['lead'] else 'none - routes by --repo/--paths (module ownership)'}")
    print("- repos: " + (", ".join(f"{x['id']} {'present' if x['present'] else 'absent'}{' (optional)' if x['optional'] else ''}"
                                   for x in r["repos"]) or "none"))
    for key in ("artifact_kinds", "quality_gates", "human_gates"):
        print(f"- {key.replace('_', ' ')}: {', '.join(r[key]) or 'none'}")
    print("- handoffs: " + ("none" if not r["handoffs"] else ""))
    for h in r["handoffs"]:
        print(f"  - {h['id']}: {h['from']} -> {', '.join(h['to'])}" + (f" (gate {h['gate']})" if h["gate"] else ""))
    print("- handoff order (all domains): " + (" -> ".join(order) if order else "CYCLE " + " -> ".join(cycle or [])))
    if r["uses_authoring"]:
        print("\n## Artifacts")
        if summary is None:
            print(f"- authoring repo absent ({auth_dir})")
        else:
            print("- by status: " + (", ".join(f"{k} {v}" for k, v in sorted(summary["artifacts"].items())) or "no artifacts yet"))
            print("- stale upstream: " + (", ".join(summary["stale"]) or "none"))
            print(f"- FAIL/BLOCKED: {', '.join(summary['failing']) or 'none'}; "
                  f"HUMAN_REQUIRED: {', '.join(summary['human_required']) or 'none'}")
    print("\n## Next")
    for line in nxt:
        print(f"- {line}")
    return 0


VERBS = [  # help: one entry per verb; read_only is False only where the verb runs builds/tests
    {"verb": "status", "args": "[--remote] [--json]", "read_only": True, "example": "status --json",
     "summary": "pending cross-repo work, authoring domains, validation evidence, fetch freshness"},
    {"verb": "route", "args": "(--domain <id> | --kind <kind>) | <repo> <path>... [--lead <skill>] [--json]", "read_only": True,
     "example": "route server backend/shared/proto/wire.proto", "summary": "lead, legs, contracts, checks and gates for a change, and why"},
    {"verb": "check", "args": "<repo> [<path>...] [--status] [--json]", "read_only": False, "example": "check server --status",
     "summary": "run the fast checks and store evidence; --status only grades stored evidence (read-only)"},
    {"verb": "doctor", "args": "[--json]", "read_only": True, "example": "doctor --json",
     "summary": "install state, registry, workspace, repos, tools, hooks, dev tools"},
    {"verb": "domain", "args": "[<id>] [--json]", "read_only": True, "example": "domain design",
     "summary": "registry domains: lead, repos, kinds, gates, handoffs, artifact counts, stale/FAIL/HUMAN_REQUIRED, next steps"},
    {"verb": "workflow", "args": "plan|status|dispatch|report <spec> [--json]", "read_only": True,
     "example": "workflow plan spec.json --json", "summary": "dependency-aware artifact workflow (dispatch only prints a contract)"},
    {"verb": "pipeline", "args": "tier|validate|planner|dispatch|verdict|gate|cleanup|status [args]", "read_only": False,
     "example": "pipeline tier -- --repo server --paths backend/shared/proto/wire.proto",
     "summary": "delivery pipeline: task tier, plan validation, worker dispatch, review/QA verdicts, READY_FOR_PR gate, cleanup, run status"},
    {"verb": "ui", "args": "[--json] [--project <dir>] [--uitoolkit-ref <ref>] <request>", "read_only": True,
     "example": "ui Create an inventory screen", "summary": "UI plan: intent, ONLY the UI skills needed, lead route, missing context"},
    {"verb": "ui-figma", "args": "[ui options] <request>", "read_only": True, "example": "ui-figma Import the shop frame",
     "summary": "UI plan forced to Figma import"},
    {"verb": "ui-components", "args": "[ui options] <request>", "read_only": True,
     "example": "ui-components Find components for a shop", "summary": "UI plan forced to component selection"},
    {"verb": "ui-screen", "args": "[ui options] <request>", "read_only": True, "example": "ui-screen Build a settings screen",
     "summary": "UI plan forced to screen implementation"},
    {"verb": "ui-review", "args": "[ui options] <request>", "read_only": True, "example": "ui-review Review the HUD",
     "summary": "UI plan forced to review"},
    {"verb": "help", "args": "[--json]", "read_only": True, "example": "help --json",
     "summary": "this list; no slash command - agents and Codex discover the commands here"},
]


def cmd_help(args):
    if args not in ([], ["--json"]):
        raise ValueError("help takes only --json")
    cmd = CODEX
    rows = []
    for v in VERBS:
        has_md = os.path.isfile(os.path.join(ROOT, "commands", v["verb"] + ".md"))
        rows.append({**v, "claude": f"/rpg-factory:{v['verb']}" if has_md else None, "codex": f"{cmd} {v['verb']}"})
    if args:
        print(json.dumps({"schema": "rpg-factory.commands/1", "plugin_root": ROOT,
                          "exit_codes": {"0": "ok", "2": "usage error", "other": "the underlying script's"},
                          "commands": rows}, indent=2))
        return 0
    print("# rpg-factory commands\n")
    print(f"Claude: /rpg-factory:<verb> <args>.  Codex or any shell: {cmd} <verb> <args>.\n")
    for r in rows:
        rest = r["example"][len(r["verb"]):]
        print(f"- {r['verb']} {r['args']}  [{'read-only' if r['read_only'] else 'runs checks'}] - {r['summary']}")
        print(f"  e.g. " + (f"{r['claude']}{rest}  |  " if r["claude"] else "") + f"{r['codex']}{rest}")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        return usage()
    if argv[0] == "pipeline":
        try:
            return cmd_pipeline(argv[1:])
        except ValueError as e:
            return usage(str(e))
    if argv[0] in UI_VERBS:
        try:
            return cmd_ui(argv[0], argv[1:])
        except ValueError as e:
            return usage(str(e))
    verb, args = argv[0], split_args(argv[1:])
    fn = {"status": cmd_status, "route": cmd_route, "check": cmd_check, "doctor": cmd_doctor, "workflow": cmd_workflow,
          "domain": cmd_domain, "help": cmd_help}.get(verb)
    if not fn:
        return usage(f"unknown command '{verb}'")
    try:
        return fn(args)
    except ValueError as e:
        return usage(str(e))


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
