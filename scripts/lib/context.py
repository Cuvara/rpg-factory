#!/usr/bin/env python3
"""Factory context engine (called by scripts/factory-context.sh). Read-only; persists nothing.

Collects live git state per repo (worktree-aware), resolves it through scripts/lib/resolve.jq
(the routing engine: modules, dependents, contracts, lead/legs/follow-ups, checks, gates) and
renders a compact markdown snapshot or full JSON.

Usage (via factory-context.sh):
  [--repo <key>|all] [--repo-path <dir>] [--paths <p>...] [--base <ref>] [--json] [--lead <skill>] [--domain <id>] [--kind <artifact-kind>] [--explain]
  [--full] [--toolchain] [--submodules] [--mode analyze|plan|implement|validate|review|resume]
  --repo      default: the repo (or worktree) containing the cwd, else all registered repos
  --repo-path explicit checkout or linked worktree to target (must belong to the registered repo). Without it the
              target is the git toplevel of the cwd when the cwd lies inside a checkout or linked worktree of the
              repo; only a cwd outside every worktree of that repo falls back to the registry canonical path, and
              the output says so (JSON: repos[].resolution)
  --paths     resolve only these paths (requires a single repo); the list ends at the next --flag.
              Repo-relative, repo-prefixed, absolute (C:\\, C:/, /c/, /mnt/c/; also inside a linked
              worktree of the repo) and glob forms are accepted. An absolute path outside the repo and
              its worktrees is reported and not routed (exit 2 when no path is left).
              Without --paths, uncommitted changes are the user's baseline: listed with their modules,
              never routed; only commits on a feature branch (vs --base) are routed.
  --mode      declare the Factory execution mode (also --mode=<m>; --repo, --base, --lead likewise); the
              hooks then add advisories for state changes in read-only modes - advisory only, they never block
  --lead      override the lead skill; must be one of the candidates (else exit 2)
  --domain    show domain entry points; may accompany routing to warn when ownership differs
  --kind      route an artifact kind to its claiming domain (ambiguous kinds require --domain or --lead)
  --explain   why every registered skill was or was not selected
  --full      include all rules, all human gates, all known issues, full toolchain versions
  --toolchain probe tool versions (slow on WSL: dotnet.exe ~5 s)
  --submodules scan uncommitted work inside submodules (the client's com.gdk.* cost ~9 s)
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)  # appended: stdlib lookups must not stat /mnt/c first
import devtools  # noqa: E402
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(HERE))
REGISTRY = os.environ.get("RPG_FACTORY_REGISTRY") or os.path.join(PLUGIN_ROOT, "registry.json")
RESOLVE = os.path.join(PLUGIN_ROOT, "scripts", "lib", "resolve.jq")


MODES = {  # the Factory execution-mode contract (the hooks add advisories once declared; they never block)
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
    a = {"repo": None, "repo_path": None, "paths": [], "base": None, "json": False, "lead": None, "domain": None, "kind": None, "explain": False,
         "full": False, "toolchain": False, "submodules": False, "mode": None}
    i = 0
    while i < len(argv):
        x = argv[i]
        if x == "--paths":
            j = i + 1
            while j < len(argv) and not argv[j].startswith("--"):  # any --flag or --flag=value ends the list
                a["paths"] += [p for p in argv[j].split(",") if p.strip()]
                j += 1
            i = j
            continue
        if x.split("=", 1)[0] in ("--repo", "--repo-path", "--base", "--lead", "--mode", "--domain", "--kind") and "=" in x:
            x, val = x.split("=", 1)
            argv = argv[:i] + [x, val] + argv[i + 1:]
        if x in ("--repo", "--repo-path", "--base", "--lead", "--mode", "--domain", "--kind"):
            if i + 1 >= len(argv):
                die(f"{x} needs a value")
            a[x[2:].replace("-", "_")] = argv[i + 1]
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


def domain_result(reg, domain_id, ws, lead_override=None):
    domains = reg.get("domains", {})
    if domain_id not in domains:
        die(f"unknown domain {domain_id}; known: {', '.join(domains) or 'none'}")
    d = dict(domains[domain_id])
    lead = d.get("lead")
    if lead_override:
        if lead_override not in reg.get("skills", {}):
            die(f"unknown lead {lead_override}; known: {', '.join(reg.get('skills', {}))}")
        if reg["skills"][lead_override].get("domain", "engineering") != domain_id:
            die(f"lead {lead_override} does not belong to domain {domain_id}")
        lead = lead_override
    repos = []
    for key in d.get("repos", []):
        rep = reg["repos"][key]
        path = os.path.join(ws, rep["path"]) if ws else rep["path"]
        present = os.path.isdir(path)
        if not present and not rep.get("optional", False):
            present = True
        repos.append({"id": key, "path": path, "status": "present" if present else "absent"})
    return {"id": domain_id, "status": d.get("status"), "summary": d.get("summary"), "lead": lead,
            "repos": repos, "artifact_kinds": d.get("artifact_kinds", []), "quality_gates": d.get("quality_gates", []),
            "human_gates": d.get("human_gates", []), "handoffs": d.get("handoffs", [])}


def intent_domain(reg, args, ws):
    domains = reg.get("domains", {})
    if args["domain"]:
        result = domain_result(reg, args["domain"], ws, args["lead"])
        if args["kind"] and args["kind"] not in result["artifact_kinds"]:
            die(f"kind {args['kind']} is not claimed by domain {args['domain']}")
        return result
    if not args["kind"]:
        return None
    kinds = {}
    for did, d in domains.items():
        for kind in d.get("artifact_kinds", []):
            kinds.setdefault(kind, []).append(did)
    candidates = kinds.get(args["kind"], [])
    if not candidates:
        die("unknown artifact kind; known: " + (", ".join(sorted(kinds)) if kinds else "no artifact kinds registered"))
    if args["lead"]:
        skill = reg.get("skills", {}).get(args["lead"])
        if not skill:
            die(f"unknown lead {args['lead']}; known: {', '.join(reg.get('skills', {}))}")
        did = skill.get("domain", "engineering")
        if did not in candidates:
            die(f"lead {args['lead']} does not belong to a domain claiming kind {args['kind']}")
        return domain_result(reg, did, ws, args["lead"])
    if len(candidates) > 1:
        if args["json"]:
            print(json.dumps({"ambiguous": True, "domains": candidates}))
        else:
            print(f"AMBIGUOUS: kind {args['kind']} is claimed by domains {', '.join(candidates)}")
        sys.exit(3)
    return domain_result(reg, candidates[0], ws)


def print_domain(result, as_json):
    if as_json:
        print(json.dumps({"domain": result}))
        return
    print("Domain")
    for key in ("id", "status", "summary"):
        print(f"{key}: {result.get(key) or ''}")
    print("lead: " + (result["lead"] if result["lead"] else "routes by --repo/--paths (module ownership)"))
    for key in ("repos", "artifact_kinds", "quality_gates", "human_gates", "handoffs"):
        values = result[key]
        if key == "repos":
            values = [f"{r['id']} ({r['status']}: {r['path']})" for r in values]
        print(f"{key}: {', '.join(values) if values else 'none'}")


def main_checkout(top):
    common = (git(top, "rev-parse", "--path-format=absolute", "--git-common-dir") or "").strip().rstrip("/")
    return os.path.dirname(common) if os.path.basename(common) == ".git" else top


def same_path(a, b):
    """True when a and b name the same directory (case, slash style and symlinks on Windows/WSL do not matter)."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def cwd_repo(reg, ws, start=None):
    """(key, directory) of the repo or worktree containing `start` (default: the cwd), if it is a registered repo.
    The directory is the git toplevel of `start`, so a linked worktree resolves to itself, not to its main checkout."""
    top = (git(start or os.getcwd(), "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return None, None
    main = os.path.abspath(main_checkout(top))
    for key, r in reg["repos"].items():
        canon = os.path.join(ws, r["path"])
        if same_path(canon, top) or same_path(canon, main):
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


def _exe_names(name):
    """The file names `name` may have on PATH: on Windows also name + each PATHEXT extension (python3.exe)."""
    if os.name != "nt" or os.path.splitext(name)[1]:
        return [name]
    exts = [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e]
    return [name] + [name + e.lower() for e in exts]


def which(cands):
    for c in cands:
        for d in os.environ.get("PATH", "").split(os.pathsep):
            for n in _exe_names(c):
                p = os.path.join(d, n)
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    return p
    return None


def tool_version(path, args, timeout=15):
    try:
        r = subprocess.run([path, *args.split()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
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


def native_abs(p):
    """Map a forward-slash path written in another shell's drive form to this platform's form: on Windows
    the git-bash `/c/...` and WSL `/mnt/c/...` forms become `C:/...`; elsewhere `C:/...` becomes
    `/mnt/c/...`. Anything else is returned unchanged."""
    if os.name == "nt":
        m = re.match(r"^/(?:mnt/)?([A-Za-z])(/.*)?$", p)
        if m:
            return f"{m.group(1).upper()}:{m.group(2) or '/'}"
        # git-bash rewrites an argument /mnt/c/x into <Git install>/mnt/c/x (MSYS path conversion)
        m = re.match(r"^[A-Za-z]:/.*?/mnt/([A-Za-z])(/.*)?$", p)
        if m and not os.path.exists(p):
            return f"{m.group(1).upper()}:{m.group(2) or '/'}"
    else:
        m = re.match(r"^([A-Za-z]):(/.*)?$", p)
        if m:
            return f"/mnt/{m.group(1).lower()}{m.group(2) or '/'}"
    return p


def rel_to(p, d):
    """Forward-slash path of absolute p relative to d, or None when p is outside d (or on another drive)."""
    try:
        rel = os.path.relpath(p, d).replace(os.sep, "/")
    except ValueError:  # Windows: p and d are on different drives
        return None
    return None if rel == ".." or rel.startswith("../") else rel


def worktrees(d):
    """Every checkout of the repo at d: its main checkout and all linked worktrees (git worktree list)."""
    out = git(main_checkout(d), "worktree", "list", "--porcelain") or ""
    return [native_abs(l[9:].strip()) for l in out.splitlines() if l.startswith("worktree ")] or [d]


def rel_in_checkouts(p, dirs):
    """p relative to the first of dirs containing it (the longest, so a worktree nested in a checkout wins)."""
    for w in sorted(dirs, key=len, reverse=True):
        rel = rel_to(p, w)
        if rel is not None:
            return rel
    return None


def foreign_repo(p, key, reg, ws):
    """The other registry repo whose checkout (or linked worktree) holds absolute path p, if any."""
    for k, r in reg["repos"].items():
        main = os.path.join(ws, r["path"])
        if k != key and os.path.isdir(main) and rel_in_checkouts(p, [main] + worktrees(main)) is not None:
            return k
    return None


def norm_paths(paths, d, rep, key=None, reg=None, ws=None):
    """Make --paths repo-relative: strip ./, a leading repo directory (`rpg-mmo-server/backend/..`),
    absolute paths inside the repo or one of its linked worktrees (C:\\ and C:/, git-bash /c/ and WSL
    /mnt/c/ forms); expand globs that match. Models pass all of these. Results always use forward
    slashes. An absolute path outside every checkout of the repo is not routed: it is returned in
    `rejected` with the reason, never as a repo-level file."""
    out, rejected, checkouts = [], [], None
    prefix = rep["path"].strip("/") + "/"
    for p in paths:
        p = native_abs(p.strip().strip('"').strip("'").replace("\\", "/"))
        if os.path.isabs(p):
            checkouts = checkouts if checkouts is not None else [d] + worktrees(d)
            rel = rel_in_checkouts(p, checkouts)
            if rel is None:
                other = foreign_repo(p, key, reg, ws) if reg and ws else None
                rejected.append({"path": p, "repo": other, "reason": f"in repo {other}: use --repo {other}" if other
                                 else "outside every checkout and worktree of this repo"})
                continue
            p = rel
        while p.startswith("./"):
            p = p[2:]
        if p.startswith(prefix) and not os.path.exists(os.path.join(d, p)):
            p = p[len(prefix):]
        if any(c in p for c in "*?["):
            hits = sorted(r for r in (rel_to(h, d) for h in glob.glob(os.path.join(d, p), recursive=True)) if r is not None)
            if hits:
                out += hits[:50]
                continue
        out.append(p)
    return list(dict.fromkeys(out)), rejected


def repo_state(key, d, rep, args, reg, ws=None):
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
    rejected, committed = [], []
    if args["paths"]:
        given, rejected = norm_paths(args["paths"], d, rep, key, reg, ws)
        files = [{"path": p, "status": "--", "source": "given"} for p in given]
        base_ok = False
    else:
        files = status_files(d, args["submodules"])
        base_ok = branch != default and git(d, "rev-parse", "--verify", "-q", base) is not None
        if base_ok:
            seen = {f["path"] for f in files}
            committed = [p for p in (git(d, "diff", "-z", "--name-only", f"{base}...HEAD") or "").split("\0") if p]
            for p in committed:
                if p not in seen:
                    files.append({"path": p, "status": "C ", "source": "branch"})
    gitlinks = [l.split("\t", 1)[1] for l in (git(d, "ls-files", "-s") or "").splitlines() if l.startswith("160000 ")]
    return {"repo": key, "path": d, "worktree": is_wt, "submodules": gitlinks, "main_checkout": main if is_wt else None, "branch": branch,
            "default_branch": default, "protected": prot, "head": head,
            "upstream": {"ref": up, "ahead": ahead, "behind": behind} if up else None,
            "branch_diff_base": base if base_ok else None, "files": files, "rejected_paths": rejected,
            "committed_paths": committed, "submodules_scanned": args["submodules"]}


def resolve(reg, key, files, subst, tools):
    r = subprocess.run(["jq", "-c", "--arg", "repo", key, "--argjson", "files", json.dumps(files),
                        "--argjson", "subst", json.dumps(subst), "--argjson", "tools", json.dumps(tools),
                        "-f", RESOLVE, REGISTRY], capture_output=True, text=True, encoding="utf-8", errors="replace")
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
        elif sk.get("kind") == "tech":
            users = [u for u in sk.get("used_by", []) if u in sel and sel[u]["role"] != "follow-up"]
            rows.append({"skill": name, "selected": "tech (supporting)" if name in state["routing"].get("tech", []) else "not selected",
                         "why": [f"tech skill: never lead/leg/follow-up; listed when a working skill uses it ({', '.join(users)})" if users
                                 else f"tech skill: none of its users ({', '.join(sk.get('used_by', []))}) works on this change"]})
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
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        d = json.loads(r.stdout)
        rt = d.get("runtime") or {}
        return {"state": d.get("state"), "runtime_version": rt.get("version"), "runtime_kind": rt.get("kind"),
                "installed_version": (d.get("installed") or {}).get("version"), "source_version": d["source"]["version"],
                "reasons": d.get("reasons", [])}
    except Exception:
        return {"state": "UNKNOWN"}


def render(snap, reg, args, views):
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
        add(f"**Mode: {snap['mode']}** - {MODES[snap['mode']]} (advisory: the hooks warn on state-changing commands and file writes in read-only modes, they do not block - keep to the mode; switch with `--mode implement` only when the user asked)")
    cl = snap.get("cwd_clone")
    if cl:
        add(f"**The current directory is an embedded clone** `{cl['in']}/{cl['path']}` (of `{cl['of']}`): gitignored user state inside "
            f"the {cl['in']} repo, NOT the canonical {cl['of']} checkout `{cl['canonical']}`. Factory snapshots, routes and validates "
            f"the canonical repos below. Do not edit, commit, reset or clean the clone unless the user explicitly asks.")
    add("")
    add("**Rules:** " + "; ".join(f"**{g['id']}** {g['rule']}" if args["full"] else f"**{g['id']}**" for g in reg["global_rules"])
        + ("" if args["full"] else " (full text: `--full` or registry `global_rules`)"))
    add("**Human gates:** " + ", ".join(g["id"] + (" (high)" if g.get("decision") == "deny" else "") for g in reg["human_gates"])
        + " - no tag or release without explicit release authorization in this task; otherwise stop at READY_TO_TAG.")
    if snap.get("services"):
        add("**Services:** " + ", ".join(f"`{sid}` {'reachable' if s['reachable'] else 'not reachable'} ({s['probe']})"
                                         for sid, s in snap["services"].items()))
    for r in snap["repos"]:
        add("")
        if r.get("error"):
            add(f"## {r['repo']}: ERROR {r['error']}")
            continue
        wt = f" worktree of {code(r['main_checkout'])}" if r.get("worktree") else ""
        if (r.get("resolution") or {}).get("note"):
            add(f"> **{r['repo']}: canonical checkout used.** {r['resolution']['note']}")
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
        for x in r.get("rejected_paths", []):
            add(f"**Warning: not routed** {code(x['path'])} - {x['reason']} (not a {r['repo']} file; never treated as repo-level)")
        route_cmd = f"`factory-context.sh --repo {r['repo']} --paths <files the task will write>`"
        v = views.get(r["repo"])
        if v is None:  # uncommitted changes only: the user's baseline, not the task
            add(f"**Baseline only - not routed:** the paths above are the user's pre-existing changes, not the task: no lead, "
                f"checks or gates are derived from them. Route the task with {route_cmd}.")
            issues = [k for k in reg.get("known_issues", []) if r["repo"] in k["scope"].split(",") or k["scope"] == "workspace"]
            if issues:
                add("Known issues here: " + "; ".join(f"**{k['id']}**" + (f" {k['summary']}" if args["full"] else "") for k in issues))
            continue
        if v is not r and any(f["source"] == "worktree" for f in r["files"]):
            add(f"Routing below covers only the {len(v['files'])} path(s) committed on this branch; the uncommitted paths are the "
                f"user's baseline. Route the task with {route_cmd}.")
        r = v
        rt = r["routing"]
        if not (rt["lead"] or rt["legs"] or rt["follow_ups"]):
            mods = {m["id"]: m for m in reg["modules"]}
            docs = list(dict.fromkeys(f"{reg['repos'][r['repo']]['path']}/{mods[t]['claude_md']}" for t in r["touched"]
                                      if t in mods and mods[t].get("claude_md")))
            add(f"**Routing** no specialised lead - factory-core only; follow "
                + (", ".join(map(code, docs)) if docs else code(reg["repos"][r["repo"]]["path"] + "/CLAUDE.md")))
        else:
            add("**Routing** " + (f"lead {code('rpg-factory:' + rt['lead'])}" if rt["lead"] else "no specialised lead (factory-core only)")
                + (f" · co-leads {', '.join(rt['co_leads'])}" if rt["co_leads"] else "")
                + (f" · legs {', '.join(rt['legs'])}" if rt["legs"] else "")
                + (f" · follow-ups {', '.join(rt['follow_ups'])}" if rt["follow_ups"] else "")
                + (f" · tech {', '.join(rt['tech'])}" if rt.get("tech") else "")
                + (" · **AMBIGUOUS** (same precedence class and order) - ask the user or pass --lead" if rt["ambiguous"] else "")
                + (" · (override)" if rt.get("override") else ""))
            if rt["lead"] and not rt["ambiguous"]:
                add(f"  **Next:** invoke the Skill tool with {code('rpg-factory:' + rt['lead'])} now - also for plan-only or "
                    "read-only requests; it owns this change's workflow, validation and gates"
                    + (f", then {', '.join(code('rpg-factory:' + c) for c in rt['co_leads'])}" if rt["co_leads"] else "") + "."
                    + (f" Then invoke the tech skill(s) {', '.join(code('rpg-factory:' + t) for t in rt['tech'])} (supporting context, "
                       "not a follow-up) before implementing, debugging, reviewing, or answering how the code works or how to "
                       "run a test - in every mode." if rt.get("tech") else ""))
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
        if r.get("dev_tools"):
            add("Tools for this change: " + "; ".join(
                f"{t['id']} {t['state']}" + (f" (fallback: {t['fallback']})" if not t["ok"] and t.get("fallback") else "")
                for t in r["dev_tools"]))
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
    route_requested = bool(args["repo"] or args["repo_path"] or args["paths"])
    if (args["domain"] or args["kind"]) and not route_requested:
        if args["repo_path"]:
            die("intent routing cannot use --repo-path")
        result = intent_domain(reg, args, ws)
        if result:
            print_domain(result, args["json"])
            return
    if not ws:
        die("not inside the RPG MMO workspace (markers not found; set RPG_FACTORY_WORKSPACE)", 4)
    requested_domain = None
    if args["domain"]:
        requested_domain = domain_result(reg, args["domain"], ws)
    here_key, here_dir = cwd_repo(reg, ws)
    explicit = False
    if args["repo_path"]:
        if not os.path.isdir(args["repo_path"]):
            die(f"--repo-path {args['repo_path']} is not a directory")
        here_key, here_dir = cwd_repo(reg, ws, args["repo_path"])
        explicit = True
        if not here_key:
            die(f"--repo-path {args['repo_path']} is not inside a checkout or linked worktree of a registered repo")
        if args["repo"] not in (None, "auto", here_key):
            die(f"--repo-path {args['repo_path']} belongs to repo '{here_key}', not '{args['repo']}'")
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
    subst = {"{dotnet}": os.path.basename(tools.get("dotnet") or "") or "<dotnet-not-found>", "{plugin_root}": PLUGIN_ROOT.replace("\\", "/")}  # check commands run through bash, which eats backslashes
    services = devtools.probe_services(reg)
    prober = devtools.Prober(ws, reg, services)
    repos, views, optional_absent = [], {}, []
    needed = set()
    for key in keys:
        rep = reg["repos"][key]
        canonical = os.path.join(ws, rep["path"])
        if not os.path.isdir(canonical) and rep.get("optional"):
            if args["repo"] == key:
                die(f"optional repo {key} is not present at {canonical}")
            optional_absent.append(key)
            continue
        if not os.path.isdir(canonical) and args["repo"] == key:
            die(f"repo {key} is not present at {canonical}")
        d = here_dir if key == here_key and here_dir else canonical
        if d is canonical:
            resolution = {"source": "canonical-fallback", "canonical": canonical, "note":
                          f"cwd {os.getcwd()} is outside every checkout and worktree of {key}: using the registry canonical checkout "
                          f"{canonical}; run from inside a worktree of {key} or pass --repo-path <worktree> to target it"}
        else:
            resolution = {"source": "repo-path" if explicit else ("cwd-checkout" if same_path(d, canonical) else "cwd-worktree"),
                          "canonical": canonical, "note": None}
        st = repo_state(key, d, rep, args, reg, ws)
        st["resolution"] = resolution
        if not st.get("error"):
            if args["paths"] and not st["files"]:
                die("no path left to route: " + "; ".join(f"{x['path']} ({x['reason']})" for x in st["rejected_paths"]))
            # JSON keeps the full resolution of every listed path (run-checks.py without --paths grades them all)
            st.update(resolve(reg, key, st["files"], subst, tools))
            if args["lead"]:
                apply_override(st, args["lead"])
            if args["explain"]:
                st["explain"] = explain(st, reg)
            rt = st["routing"]
            routed = ([rt["lead"]] if rt["lead"] else []) + rt["co_leads"] + rt["legs"] + rt.get("tech", [])
            st["dev_tools"] = prober.for_skills(routed) if routed else []
            # the task scope the snapshot routes: --paths, else only commits on the branch; uncommitted
            # status paths are the user's baseline and are never routed
            view = st
            if not args["paths"]:
                task = [{"path": p, "status": "C ", "source": "branch"} for p in st["committed_paths"]]
                view = dict(st, **resolve(reg, key, task, subst, tools)) if task else None
                if view is not None:
                    if args["lead"] and args["lead"] in [s["skill"] for s in view["suggested_skills"]]:
                        apply_override(view, args["lead"])
                    view["explain"] = explain(view, reg) if args["explain"] else None
                    vt = view["routing"]
                    routed = ([vt["lead"]] if vt["lead"] else []) + vt["co_leads"] + vt["legs"] + vt.get("tech", [])
                    view["dev_tools"] = prober.for_skills(routed) if routed else []
            st["task_scope"] = {"scope": "paths" if args["paths"] else ("branch" if view is not None else "baseline"),
                                "lead": view["routing"]["lead"] if view is not None else None,
                                "baseline_paths": [] if args["paths"] else [f["path"] for f in st["files"] if f["source"] == "worktree"]}
            views[key] = view
            for c in (view or {}).get("checks", []):
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
            "install": install_line(), "repos": repos, "toolchain": tc, "services": services, "cwd_clone": clone, "mode": args["mode"],
            "global_rules": reg["global_rules"], "human_gates": reg["human_gates"],
            "known_issues": reg.get("known_issues", [])}
    if requested_domain:
        mismatches = [r["routing"]["domain"] for r in repos if not r.get("error") and r.get("routing", {}).get("domain") != args["domain"]]
        if mismatches:
            snap["warnings"] = [f"requested domain {args['domain']} differs from routed domain {mismatches[0]}"]
    snap["optional_repos_absent"] = optional_absent
    snap["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
    if args["json"]:
        print(json.dumps(snap, indent=None))
    else:
        print(render(snap, reg, args, views))
        for key in optional_absent:
            print(f"optional repo {key} absent")
        for warning in snap.get("warnings", []):
            print(f"Warning: {warning}")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
