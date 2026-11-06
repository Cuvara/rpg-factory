#!/usr/bin/env python3
"""Factory context engine (called by scripts/factory-context.sh). Read-only; persists nothing.

Collects live git state per repo (worktree-aware), resolves it through scripts/lib/resolve.jq
(the routing engine: modules, dependents, contracts, lead/legs/follow-ups, checks, gates) and
renders a compact markdown snapshot or full JSON.

Usage (via factory-context.sh):
  [--repo <key>|all] [--repo-path <dir>] [--paths <p>...] [--base <ref>] [--json] [--lead <skill>] [--domain <id>] [--kind <artifact-kind>] [--graph] [--explain]
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
import workspace  # noqa: E402
from workspace import native_abs  # noqa: E402,F401  (public: run-checks.py imports it from here)
from pluginroot import plugin_root
from snapshot_render import (  # noqa: E402,F401 (public context helpers remain importable)
    MODES, die, domain_result, explain, handoff_graph, intent_domain, print_domain, render,
)
PLUGIN_ROOT = plugin_root()
REGISTRY = os.environ.get("RPG_FACTORY_REGISTRY") or os.path.join(PLUGIN_ROOT, "registry.json")
RESOLVE = os.path.join(PLUGIN_ROOT, "scripts", "lib", "resolve.jq")


def git(cwd, *args, timeout=60):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def parse_args(argv):
    a = {"repo": None, "repo_path": None, "paths": [], "base": None, "json": False, "lead": None, "domain": None, "kind": None, "graph": False, "explain": False,
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
        flag = {"--json": "json", "--graph": "graph", "--explain": "explain", "--full": "full", "--toolchain": "toolchain",
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
    return workspace.find_workspace(os.getcwd(), reg, env_first=True, use_default=True)


def main_checkout(top):
    return workspace.main_checkout(top, timeout=60)


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


def main():
    t0 = time.perf_counter()
    args = parse_args(sys.argv[1:])
    if not os.path.exists(REGISTRY):
        die(f"registry not found at {REGISTRY}", 3)
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    ws = find_workspace(reg)
    if args["graph"]:
        if not args["domain"] or args["paths"] or args["kind"] or args["repo"] or args["repo_path"]:
            die("--graph requires --domain <id> and cannot be combined with --repo, --repo-path, --paths, or --kind", 3)
        order, cycle = handoff_graph(reg, args["domain"])
        if cycle:
            line = "CYCLE: " + " -> ".join(cycle)
            print(json.dumps({"cycle": cycle}) if args["json"] else line)
            sys.exit(3)
        if args["json"]:
            print(json.dumps({"graph": order}))
        else:
            print("Dependency graph: " + " -> ".join(order))
        return
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
    if args["paths"] and not args["lead"]:
        claims = {}
        for state in repos:
            if state.get("error"):
                continue
            selected = state.get("suggested_skills", [])
            for item in selected:
                if item.get("role") not in ("lead", "co-lead"):
                    continue
                skill = reg.get("skills", {}).get(item["skill"], {})
                domain_id = skill.get("domain", "engineering")
                claims.setdefault(domain_id, {})[item["skill"]] = item.get("reasons", [])
        if len(claims) > 1:
            print("AMBIGUOUS: paths resolve to leads in multiple domains")
            for did in sorted(claims):
                for skill, reasons in sorted(claims[did].items()):
                    print(f"{did}: {skill}: {'; '.join(reasons)}")
            sys.exit(3)

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
