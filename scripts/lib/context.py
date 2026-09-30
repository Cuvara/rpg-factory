#!/usr/bin/env python3
"""Factory context engine (called by scripts/factory-context.sh). Read-only; persists nothing.

Collects live git state per repo (worktree-aware), resolves it through scripts/lib/resolve.jq
(the routing engine: modules, dependents, contracts, lead/legs/follow-ups, checks, gates) and
renders a compact markdown snapshot or full JSON.

Usage (via factory-context.sh):
  [--repo <key>|all] [--paths <p>...] [--base <ref>] [--json] [--lead <skill>] [--explain]
  [--full] [--toolchain] [--submodules]
  --repo      default: the repo (or worktree) containing the cwd, else all registered repos
  --paths     resolve only these repo-relative paths (requires a single repo); everything after
              --paths is a path. Use it when the tree holds pre-existing user changes.
  --lead      override the lead skill; must be one of the candidates (else exit 2)
  --explain   why every registered skill was or was not selected
  --full      include all rules, all human gates, all known issues, full toolchain versions
  --toolchain probe tool versions (slow on WSL: dotnet.exe ~5 s)
  --submodules scan uncommitted work inside submodules (the client's com.gdk.* cost ~9 s)
"""
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(HERE))
REGISTRY = os.path.join(PLUGIN_ROOT, "registry.json")
RESOLVE = os.path.join(PLUGIN_ROOT, "scripts", "lib", "resolve.jq")


MODES = {  # the Factory execution-mode contract (enforced by the hooks once declared)
    "analyze":   "read-only. Explain what exists and what a change would touch. Invoke the lead skill for its domain rules; change nothing.",
    "plan":      "read-only. Invoke the lead skill, then produce the plan from its workflow: files, legs, obligations, checks (tier + command), gates. Change nothing.",
    "implement": "full workflow: branch, implement, obligations, validate with run-checks.py, verify, report.",
    "validate":  "run and grade checks only (run-checks.py; --status first). No file changes.",
    "review":    "read-only review of existing changes against the lead skill's review checklist and registry rules.",
    "resume":    "factory-status.py first, then continue the interrupted task at its first incomplete step (implement rules).",
}


def die(msg, code=2):
    print(f"factory-context: {msg}", file=sys.stderr)
    sys.exit(code)


def git(cwd, *args, timeout=60):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def parse_args(argv):
    a = {"repo": None, "paths": [], "base": None, "json": False, "lead": None, "explain": False,
         "full": False, "toolchain": False, "submodules": False, "mode": None}
    i = 0
    while i < len(argv):
        x = argv[i]
        if x == "--paths":
            known = {"--repo", "--base", "--lead", "--json", "--explain", "--full", "--toolchain", "--submodules", "--mode"}
            j = i + 1
            while j < len(argv) and argv[j] not in known:
                a["paths"] += [p for p in argv[j].split(",") if p.strip()]
                j += 1
            i = j
            continue
        if x.startswith("--mode="):
            x, argv = "--mode", argv[:i] + ["--mode", x.split("=", 1)[1]] + argv[i + 1:]
        if x in ("--repo", "--base", "--lead", "--mode"):
            if i + 1 >= len(argv):
                die(f"{x} needs a value")
            a[x[2:]] = argv[i + 1]
            i += 2
            continue
        flag = {"--json": "json", "--explain": "explain", "--full": "full", "--toolchain": "toolchain",
                "--submodules": "submodules"}.get(x)
        if flag:
            a[flag] = True
        elif x in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            die(f"unknown argument '{x}'")
        i += 1
    return a


def find_workspace(reg):
    markers = reg["workspace"]["root_markers"]
    ok = lambda d: d and all(os.path.exists(os.path.join(d, m)) for m in markers)
    env = os.environ.get(reg["workspace"]["root_env"])
    if ok(env):
        return os.path.abspath(env)
    d = os.getcwd()
    while True:
        if ok(d):
            return d
        if os.path.dirname(d) == d:
            break
        d = os.path.dirname(d)
    return reg["workspace"]["root_default"] if ok(reg["workspace"]["root_default"]) else None


def main_checkout(top):
    common = (git(top, "rev-parse", "--path-format=absolute", "--git-common-dir") or "").strip().rstrip("/")
    return os.path.dirname(common) if os.path.basename(common) == ".git" else top


def cwd_repo(reg, ws):
    """(key, directory) of the repo or worktree containing the cwd, if it is a registered repo."""
    top = (git(os.getcwd(), "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return None, None
    main = os.path.abspath(main_checkout(top))
    for key, r in reg["repos"].items():
        if os.path.abspath(os.path.join(ws, r["path"])) in (os.path.abspath(top), main):
            return key, os.path.abspath(top)
    return None, None


def cwd_clone(reg, ws):
    """The embedded package clone (gitignored nested repo, user state) containing the cwd, if any."""
    top = (git(os.getcwd(), "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return None
    for key, r in reg["repos"].items():
        for c in r.get("embedded_clones", []):
            if os.path.abspath(os.path.join(ws, r["path"], c["path"])) == os.path.abspath(top):
                return {"in": key, "path": c["path"], "of": c["of"], "dir": os.path.abspath(top),
                        "canonical": os.path.abspath(os.path.join(ws, reg["repos"][c["of"]]["path"]))}
    return None


def which(cands):
    for c in cands:
        for d in os.environ.get("PATH", "").split(os.pathsep):
            p = os.path.join(d, c)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def tool_version(path, args, timeout=15):
    try:
        r = subprocess.run([path, *args.split()], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return ((r.stdout or r.stderr).splitlines() or [""])[0].strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


def status_files(d, submodules):
    """Changed paths (NUL-safe) with status; submodule internals only when asked."""
    ign = "--ignore-submodules=untracked" if submodules else "--ignore-submodules=dirty"
    out = git(d, "status", "--porcelain=v1", "-z", "--untracked-files=normal", ign) or ""
    files, parts, i = [], out.split("\0"), 0
    while i < len(parts):
        e = parts[i]
        if not e:
            i += 1
            continue
        st, path = e[:2], e[3:]
        files.append({"path": path, "status": st, "source": "worktree"})
        i += 2 if st[0] in "RC" else 1
    return files


def norm_paths(paths, d, rep):
    """Make --paths repo-relative: strip ./, a leading repo directory (`rpg-mmo-server/backend/..`),
    absolute paths inside the repo; expand globs that match. Models pass all of these."""
    out = []
    prefix = rep["path"].strip("/") + "/"
    for p in paths:
        p = p.strip().strip('"').strip("'").replace("\\", "/")
        if os.path.isabs(p):
            rel = os.path.relpath(p, d)
            p = rel if not rel.startswith("..") else p
        while p.startswith("./"):
            p = p[2:]
        if p.startswith(prefix) and not os.path.exists(os.path.join(d, p)):
            p = p[len(prefix):]
        if any(c in p for c in "*?["):
            hits = sorted(os.path.relpath(h, d) for h in glob.glob(os.path.join(d, p), recursive=True))
            if hits:
                out += hits[:50]
                continue
        out.append(p)
    return list(dict.fromkeys(out))


def repo_state(key, d, rep, args, reg):
    if git(d, "rev-parse", "--is-inside-work-tree") is None:
        return {"repo": key, "path": d, "error": "not a git work tree"}
    default = rep["default_branch"]
    branch = (git(d, "branch", "--show-current") or "").strip() or "(detached)"
    head = (git(d, "rev-parse", "--short", "HEAD") or "").strip()
    main = main_checkout(d)
    is_wt = os.path.abspath(main) != os.path.abspath(d)
    prot = any(branch == p or (p.endswith("*") and branch.startswith(p[:-1])) for p in rep["protected_branches"])
    up = (git(d, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "").strip()
    ahead = behind = None
    if up:
        c = (git(d, "rev-list", "--left-right", "--count", f"{up}...HEAD") or "").split()
        if len(c) == 2:
            behind, ahead = c
    base = args["base"] or (f"origin/{default}" if git(d, "rev-parse", "--verify", "-q", f"origin/{default}") else default)
    if args["paths"]:
        files = [{"path": p, "status": "--", "source": "given"} for p in norm_paths(args["paths"], d, rep)]
        base_ok = False
    else:
        files = status_files(d, args["submodules"])
        base_ok = branch != default and git(d, "rev-parse", "--verify", "-q", base) is not None
        if base_ok:
            seen = {f["path"] for f in files}
            for p in (git(d, "diff", "-z", "--name-only", f"{base}...HEAD") or "").split("\0"):
                if p and p not in seen:
                    files.append({"path": p, "status": "C ", "source": "branch"})
    gitlinks = [l.split("\t", 1)[1] for l in (git(d, "ls-files", "-s") or "").splitlines() if l.startswith("160000 ")]
    return {"repo": key, "path": d, "worktree": is_wt, "submodules": gitlinks, "main_checkout": main if is_wt else None, "branch": branch,
            "default_branch": default, "protected": prot, "head": head,
            "upstream": {"ref": up, "ahead": ahead, "behind": behind} if up else None,
            "branch_diff_base": base if base_ok else None, "files": files,
            "submodules_scanned": args["submodules"]}


def resolve(reg, key, files, subst, tools):
    r = subprocess.run(["jq", "-c", "--arg", "repo", key, "--argjson", "files", json.dumps(files),
                        "--argjson", "subst", json.dumps(subst), "--argjson", "tools", json.dumps(tools),
                        "-f", RESOLVE, REGISTRY], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"routing engine failed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def apply_override(state, lead):
    cands = [s["skill"] for s in state["suggested_skills"]]
    if lead not in cands:
        die(f"--lead {lead} is not a candidate for these paths in repo {state['repo']}; candidates: "
            f"{', '.join(cands) or 'none'} (see --explain)")
    r = state["routing"]
    leads = [r["lead"]] + r["co_leads"] if r["lead"] else []
    r["co_leads"] = [s for s in leads if s and s != lead]
    r["legs"] = [s for s in r["legs"] if s != lead]
    r["follow_ups"] = [s for s in r["follow_ups"] if s != lead]
    r["lead"], r["override"], r["ambiguous"] = lead, True, False


def explain(state, reg):
    sel = {s["skill"]: s for s in state["suggested_skills"]}
    rows = []
    for name, sk in sorted(reg["skills"].items(), key=lambda kv: kv[1].get("order", 999)):
        if name == "factory-core":
            continue
        if name in sel:
            s = sel[name]
            role = "lead" if state["routing"]["lead"] == name else ("co-lead" if name in state["routing"]["co_leads"] else s["role"])
            rows.append({"skill": name, "selected": role, "class": s.get("class"), "order": s.get("order"), "why": s["reasons"]})
        else:
            owns = [m["id"] for m in reg["modules"] if name in (m.get("skills") or [])]
            drives = [c["id"] for c in reg["contracts"] if c.get("driver") == name]
            rows.append({"skill": name, "selected": "not selected",
                         "why": [f"no touched path maps to its modules ({', '.join(owns[:4])}{'...' if len(owns) > 4 else ''})"
                                 + (f" and no touched end of its contracts ({', '.join(drives)})" if drives else "")]})
    return rows


def install_line():
    try:
        r = subprocess.run([sys.executable, "-B", os.path.join(PLUGIN_ROOT, "scripts", "install-status.py"), "--json"],
                           capture_output=True, text=True, timeout=20)
        d = json.loads(r.stdout)
        rt = d.get("runtime") or {}
        return {"state": d.get("state"), "runtime_version": rt.get("version"), "runtime_kind": rt.get("kind"),
                "installed_version": (d.get("installed") or {}).get("version"), "source_version": d["source"]["version"],
                "reasons": d.get("reasons", [])}
    except Exception:
        return {"state": "UNKNOWN"}


def render(snap, reg, args):
    out = []
    add = out.append
    code = lambda s: f"`{s}`"
    inst = snap["install"]
    add(f"# Factory context ({snap['generated_at']}, {snap['elapsed_ms']} ms)")
    add(f"rpg-factory runtime {inst.get('runtime_version') or '-'} ({inst.get('runtime_kind') or 'not in a session'}), "
        f"installed {inst.get('installed_version')}, source {inst.get('source_version')} - install state **{inst.get('state')}**")
    if inst.get("state") not in ("CURRENT", None):
        for r in inst.get("reasons", [])[:3]:
            add(f"- {r}")
    add(f"Workspace `{snap['workspace']}`. Live snapshot: recompute per task; changed paths listed at task start are the user's baseline.")
    if snap.get("mode"):
        add(f"**Mode: {snap['mode']}** - {MODES[snap['mode']]} (the hooks enforce read-only modes; switch with `--mode implement` only when the user asked)")
    cl = snap.get("cwd_clone")
    if cl:
        add(f"**The current directory is an embedded clone** `{cl['in']}/{cl['path']}` (of `{cl['of']}`): gitignored user state inside "
            f"the {cl['in']} repo, NOT the canonical {cl['of']} checkout `{cl['canonical']}`. Factory snapshots, routes and validates "
            f"the canonical repos below. Do not edit, commit, reset or clean the clone unless the user explicitly asks.")
    add("")
    add("**Rules:** " + "; ".join(f"**{g['id']}** {g['rule']}" if args["full"] else f"**{g['id']}**" for g in reg["global_rules"])
        + ("" if args["full"] else " (full text: `--full` or registry `global_rules`)"))
    add("**Human gates:** " + ", ".join(g["id"] + (" (deny)" if g.get("decision") == "deny" else "") for g in reg["human_gates"])
        + " - agents never tag; stop at READY_TO_TAG.")
    for r in snap["repos"]:
        add("")
        if r.get("error"):
            add(f"## {r['repo']}: ERROR {r['error']}")
            continue
        wt = f" worktree of {code(r['main_checkout'])}" if r.get("worktree") else ""
        up = r.get("upstream")
        upt = f", {up['ref']} +{up['ahead']}/-{up['behind']} (last fetch)" if up else ""
        prot = " **PROTECTED** (branch before committing)" if r["protected"] else ""
        if not r["files"]:
            add(f"## {r['repo']}: {r['branch']}{prot} @{r['head']}{upt}{wt} - clean"
                + (f" (submodules {', '.join(r['submodules'])} not scanned)" if r.get("submodules") and not r.get("submodules_scanned") else ""))
            continue
        add(f"## {r['repo']}: {r['branch']}{prot} @{r['head']}{upt}{wt}  `{r['path']}`")
        given = any(f["source"] == "given" for f in r["files"])
        add(f"Changed paths ({len(r['files'])}" + (", from --paths" if given else ", pre-existing at task start = user baseline: never stage/clean/reset them") + "):")
        for f in r["files"][:25]:
            add(f"- {code(f['status'])} {code(f['path'])} -> {f['module'] or '**unmapped**'}" + (" (committed on branch)" if f["source"] == "branch" else ""))
        if len(r["files"]) > 25:
            add(f"- ... {len(r['files']) - 25} more (use --json)")
        if not r.get("submodules_scanned") and r.get("submodules"):
            add(f"- submodules {', '.join(map(code, r['submodules']))}: pointer moves shown above; uncommitted work inside them "
                "is NOT scanned (`--submodules`, ~9 s) - treat their contents as user state")
        rt = r["routing"]
        if rt["lead"] or rt["legs"] or rt["follow_ups"]:
            add("**Routing** " + (f"lead {code('rpg-factory:' + rt['lead'])}" if rt["lead"] else "no specialised lead (factory-core only)")
                + (f" · co-leads {', '.join(rt['co_leads'])}" if rt["co_leads"] else "")
                + (f" · legs {', '.join(rt['legs'])}" if rt["legs"] else "")
                + (f" · follow-ups {', '.join(rt['follow_ups'])}" if rt["follow_ups"] else "")
                + (" · **AMBIGUOUS** (same precedence class and order) - ask the user or pass --lead" if rt["ambiguous"] else "")
                + (" · (override)" if rt.get("override") else ""))
            if rt["lead"] and not rt["ambiguous"]:
                add(f"  **Next:** invoke the Skill tool with {code('rpg-factory:' + rt['lead'])} now - also for plan-only or "
                    "read-only requests; it owns this change's workflow, validation and gates"
                    + (f", then {', '.join(code('rpg-factory:' + c) for c in rt['co_leads'])}" if rt["co_leads"] else "") + ".")
            regc = {c["id"]: c for c in reg.get("contracts", [])}
            for c in r["contracts"]:
                src_repo = (regc.get(c["id"], {}).get("source") or {}).get("repo")
                if (src_repo and src_repo != r["repo"] and c["driver"] != rt["lead"]
                        and all(h["role"] != "source" for h in c["hits"])):
                    add(f"  **Cross-repo:** this repo is a downstream end of contract {code(c['id'])} (source in `{src_repo}`, "
                        f"driver {code('rpg-factory:' + c['driver'])}). If the task also changes the `{src_repo}` side, the task's "
                        f"lead is {code('rpg-factory:' + c['driver'])} - invoke it first; {code('rpg-factory:' + rt['lead'])} "
                        "is its follow-up here.")
            if rt.get("lead_basis"):
                add(f"  lead because: {'; '.join(rt['lead_basis']['reasons'][:3])} (class {rt['lead_basis']['class']}, order {rt['lead_basis']['order']})")
        add(f"Modules: {', '.join(r['touched']) or 'none'}" + (f"; dependents {', '.join(r['dependents'])}" if r["dependents"] else "")
            + (f"; cross-repo (advisory) {', '.join(x['id'] for x in r['cross_repo_dependents'])}" if r["cross_repo_dependents"] else ""))
        if r.get("repo_level"):
            add(f"Repo-level files (no module; review with the repo owner): {', '.join(map(code, r['repo_level']))}")
        if r["unmapped"]:
            add(f"**Unmapped**: {', '.join(map(code, r['unmapped']))}")
        if r["generated_hits"]:
            add("Generated paths touched (change only via their generator): " + ", ".join(f"{code(g['path'])} ({g['generated_by']})" for g in r["generated_hits"]))
        for c in r["contracts"]:
            add(f"Contract {code(c['id'])} ({'/'.join(sorted({h['role'] for h in c['hits']}))} touched, driver {c['driver']}): "
                + "; ".join(f"{e['repo']}:{e['path']}" for e in c["other_ends"][:6]))
        if r["gates"]:
            add("Gates for this change: " + ", ".join(f"**{g['gate']}**" for g in r["gates"]))
        if r["checks"]:
            add("Validation (run with `scripts/run-checks.py --repo " + r["repo"] + " --paths ...`):")
            for tier in ("fast", "extended", "external"):
                cs = [c for c in r["checks"] if c["tier"] == tier]
                if cs:
                    add(f"- {tier}: " + "; ".join(f"{c['module']}/{c['id']}" + (" MISSING " + ",".join(c["missing_tools"]) if c["missing_tools"] else "") for c in cs))
        for o in r["obligations"]:
            if o.get("changelog") or o.get("docs"):
                add(f"Obligations {o['module']}: CHANGELOG {o.get('changelog') or '-'}" + (f"; docs {', '.join(o['docs'][:3])}" if o.get("docs") else ""))
        issues = [k for k in reg.get("known_issues", []) if r["repo"] in k["scope"].split(",") or k["scope"] == "workspace"]
        if issues:
            add("Known issues here: " + "; ".join(f"**{k['id']}**" + (f" {k['summary']}" if args["full"] else "") for k in issues))
        if r.get("explain"):
            add("Explain:")
            for e in r["explain"]:
                add(f"- {e['skill']}: {e['selected']} - {'; '.join(e['why'][:2])}")
    tc = snap["toolchain"]
    if tc:
        add("")
        add("**Toolchain:** " + ", ".join(f"{t['tool']} " + ((t.get("version") or os.path.basename(t["resolved"])) if t["resolved"] else "**MISSING**")
                                          + (f" (CI pins {t['expected']})" if t.get("expected") and t.get("version") and t["expected"] not in t["version"] else "")
                                          for t in tc))
    return "\n".join(out)


def main():
    t0 = time.perf_counter()
    args = parse_args(sys.argv[1:])
    if not os.path.exists(REGISTRY):
        die(f"registry not found at {REGISTRY}", 3)
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    ws = find_workspace(reg)
    if not ws:
        die("not inside the RPG MMO workspace (markers not found; set RPG_FACTORY_WORKSPACE)", 4)
    here_key, here_dir = cwd_repo(reg, ws)
    clone = cwd_clone(reg, ws) if not here_key else None
    if args["repo"] and args["repo"] not in ("all", "auto") and args["repo"] not in reg["repos"]:
        die(f"unknown repo '{args['repo']}'; known: {', '.join(reg['repos'])}")
    if args["paths"] and (not args["repo"] or args["repo"] == "all") and not here_key:
        die(f"--paths requires --repo <{'|'.join(reg['repos'])}> (or run inside that repo)")
    if args["repo"] in (None, "auto"):
        keys = [here_key] if here_key else list(reg["repos"])
    elif args["repo"] == "all":
        keys = list(reg["repos"])
    else:
        keys = [args["repo"]]
    if args["paths"] and len(keys) != 1:
        die("--paths requires a single repo")
    if args["lead"] and len(keys) != 1:
        die("--lead requires a single repo")
    if args["mode"] and args["mode"] not in MODES:
        die(f"unknown mode '{args['mode']}'; modes: {', '.join(MODES)}")

    tools = {}
    for name, t in reg["tools"].items():
        tools[name] = which(t["candidates"])
    subst = {"{dotnet}": os.path.basename(tools.get("dotnet") or "") or "<dotnet-not-found>", "{plugin_root}": PLUGIN_ROOT}
    repos = []
    needed = set()
    for key in keys:
        rep = reg["repos"][key]
        d = here_dir if key == here_key and here_dir else os.path.join(ws, rep["path"])
        st = repo_state(key, d, rep, args, reg)
        if not st.get("error"):
            st.update(resolve(reg, key, st["files"], subst, tools))
            if args["lead"]:
                apply_override(st, args["lead"])
            if args["explain"]:
                st["explain"] = explain(st, reg)
            for c in st["checks"]:
                if c["tier"] != "external":
                    for m in reg["modules"]:
                        if m["id"] == c["module"]:
                            needed |= set(m.get("tools", []))
        repos.append(st)
    tc = []
    show = set(reg["tools"]) if (args["full"] or args["toolchain"]) else needed
    for name in sorted(show):
        t = reg["tools"][name]
        ver = tool_version(tools[name], t["version_args"]) if tools.get(name) and (args["toolchain"] or args["full"]) else None
        tc.append({"tool": name, "resolved": tools.get(name), "version": ver, "expected": t.get("expected")})
    snap = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "workspace": ws, "plugin_root": PLUGIN_ROOT,
            "install": install_line(), "repos": repos, "toolchain": tc, "cwd_clone": clone, "mode": args["mode"],
            "global_rules": reg["global_rules"], "human_gates": reg["human_gates"],
            "known_issues": reg.get("known_issues", [])}
    snap["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
    if args["json"]:
        print(json.dumps(snap, indent=None))
    else:
        print(render(snap, reg, args))


if __name__ == "__main__":
    main()
