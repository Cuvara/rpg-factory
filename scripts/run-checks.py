#!/usr/bin/env python3
"""Factory check runner: executes the registry checks for a change and records evidence.

The agent does not grade its own checks. This runner resolves the checks for the given paths
through the routing engine, runs the local ones, parses their output and assigns a state:

  PASS           ran; exit 0; the parser found positive evidence (e.g. tests executed > 0)
  FAIL           ran and failed, or ran without evidence (0 tests executed), or left files behind
  SKIPPED        not run by explicit choice (--only filter / --tier excludes it)
  BLOCKED        not run: a check it needs did not PASS in this run (failed, skipped, or listed after it),
                 its working directory does not exist, or the workspace cannot be translated for bash
  NOT_AVAILABLE  not run: a required tool is missing on this machine
  HUMAN_REQUIRED not run: extended check without --approve, or an external check (CI, Unity
                 Editor, cluster, Docker stack) that a person must run or authorise
  NOT_RUN        (--status) declared for this change, but no evidence was ever recorded
  STALE          (--status) evidence exists but the tree changed since (HEAD, working-tree diff or
                 untracked files in the check's scope: its directory, its module's paths and those of
                 the modules it depends on), or the check definition or scope changed in the registry

Every executed check is stored with the identity of the tree it ran on (lib/evidence.py) and its
full log; the table shows a summary only. `--status` grades the declared checks against the
current tree WITHOUT running anything - a PASS from before an edit shows as STALE.

Usage: run-checks.py --repo <key> [--paths <p>...] [--tier fast|extended|external|all]
                     [--approve <check-id>...] [--only <module/check-id>...] [--timeout SEC]
                     [--dry-run] [--json] [--status]
  --paths      the files the task changed (default: the repo's working tree + branch diff); a path
               outside the repo checkout and its linked worktrees is a usage error
  --tier       default "fast"; extended/external are listed as HUMAN_REQUIRED unless approved
  --only       names must match a check declared for these paths (usage error otherwise)
Evidence: <state root>/evidence/<workspace>/<repo>/ (lib/fstate.py; never inside a repo).
Exit: 0 all executed checks PASS; 1 any FAIL/BLOCKED/NOT_AVAILABLE among required checks; 2 usage
      (unknown --repo/--tier/--only name, bad --timeout, path outside the repo).
      --status: 0 only when every fast check is PASS on the current tree.
"""
import json
import hashlib
import os
import posixpath
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
REG = json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
sys.path.append(os.path.join(HERE, "lib"))  # appended: stdlib lookups must not stat /mnt/c first
import evidence  # noqa: E402
import fstate  # noqa: E402
from context import native_abs  # noqa: E402


def parse_args(argv):
    a = {"repo": None, "paths": [], "tier": "fast", "approve": [], "only": [], "timeout": 1800, "dry": False, "json": False,
         "status": False}
    i, cur = 0, None
    flags = {"--repo", "--paths", "--tier", "--approve", "--only", "--timeout", "--dry-run", "--json", "--status"}
    while i < len(argv):
        x = argv[i]
        if x in ("--paths", "--approve", "--only"):
            cur = x[2:]
        elif x in ("--repo", "--tier", "--timeout"):
            a[x[2:]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 1
            cur = None
        elif x == "--dry-run":
            a["dry"], cur = True, None
        elif x == "--json":
            a["json"], cur = True, None
        elif x == "--status":
            a["status"], cur = True, None
        elif cur and x not in flags:
            a[cur].append(x)
        else:
            print(__doc__)
            sys.exit(2)
        i += 1
    if not a["repo"] or a["repo"] not in REG["repos"]:
        usage_error(f"--repo <{'|'.join(REG['repos'])}> required")
    if a["tier"] not in TIERS:
        usage_error(f"unknown --tier '{a['tier']}'; tiers: {', '.join(TIERS)}")
    try:
        a["timeout"] = int(a["timeout"])
    except (TypeError, ValueError):
        a["timeout"] = 0
    if a["timeout"] <= 0:
        usage_error("--timeout needs a positive number of seconds")
    return a


TIERS = ("fast", "extended", "external", "all")


def usage_error(msg):
    print(f"run-checks: {msg}", file=sys.stderr)
    sys.exit(2)


def git(d, *args):
    try:
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def worktree_state(d):
    """Fingerprint changed/untracked paths, including edits to already-dirty files."""
    entries = git(d, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=all").split("\0")
    paths = set()
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) >= 4:
            status, path = entry[:2], entry[3:]
            paths.add(path)
            if "R" in status or "C" in status:
                if i < len(entries) and entries[i]:
                    paths.add(entries[i])  # the source path follows the destination in porcelain -z output
                i += 1
    state = {}
    for path in paths:
        full = os.path.join(d, path)
        try:
            if os.path.islink(full):
                state[path] = "symlink:" + os.readlink(full)
            elif os.path.isfile(full):
                h = hashlib.sha256()
                with open(full, "rb") as f:
                    for block in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(block)
                state[path] = f"{h.hexdigest()}:{os.stat(full).st_mode}"
            elif os.path.isdir(full):
                state[path] = "directory"
            else:
                state[path] = "missing"
        except OSError as e:
            state[path] = f"unreadable:{e}"
    return state


def bash_env_path(path, bash):
    """Convert native workspace paths to the selected bash's path syntax; fail closed."""
    if os.name != "nt":
        return os.path.realpath(path)
    exe = os.path.normcase(os.path.realpath(bash))
    if "\\windows\\system32\\bash.exe" in exe:
        conv = subprocess.run([bash, "-c", "wslpath -u \"$1\"", "runner", path], capture_output=True, text=True, timeout=10)
        return conv.stdout.strip() if conv.returncode == 0 and conv.stdout.strip().startswith("/") else None
    cygpath = shutil.which("cygpath")
    if not cygpath:
        return None
    conv = subprocess.run([cygpath, "-u", path], capture_output=True, text=True, timeout=10)
    return conv.stdout.strip() if conv.returncode == 0 else None


def run_check(command, cwd, env, timeout):
    """Run bash in an isolated process group and clean up its entire child tree on timeout."""
    bash = shutil.which("bash")
    if not bash:
        return 127, "could not start: bash not found", False, "not started"
    kwargs = dict(cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                  encoding="utf-8", errors="replace", env=env)
    if os.name == "nt":
        p = subprocess.Popen([bash, "-c", command], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, **kwargs)
    else:
        p = subprocess.Popen([bash, "-c", command], start_new_session=True, **kwargs)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or "", False, "not needed"
    except subprocess.TimeoutExpired:
        pids = [p.pid]
        cleanup = "success"
        try:
            if os.name == "nt":
                killer = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, text=True, timeout=5)
                cleanup = "success" if killer.returncode == 0 else f"failed (taskkill exit {killer.returncode}: {killer.stderr.strip() or killer.stdout.strip()})"
            else:
                listing = subprocess.run(["ps", "-eo", "pid=,pgid="], capture_output=True, text=True, timeout=3)
                if listing.returncode == 0:
                    pids = sorted({int(pid) for pid, pgid in (line.split() for line in listing.stdout.splitlines()) if int(pgid) == p.pid})
                os.killpg(p.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError) as e:
            cleanup = f"failed ({e})"
        try:
            out, _ = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            out = ""
            cleanup += "; pipes/process did not close within 3 s"
        return 124, f"TIMEOUT after {timeout} s; pids={pids}; cleanup={cleanup}\n{out or ''}", True, cleanup


def parser_for(check):
    p = check.get("parser")
    if p:
        return p
    run = check["run"]
    if re.search(r"\bgo test\b", run):
        return "go-test"
    if re.search(r"\bdotnet(\.exe)? test\b|\{dotnet\} test", run) and "Regenerate" not in run:
        return "dotnet-test"
    if "netcode-headless.sh" in run:
        return r"regex:executed=[1-9]\d* passed=\d+ failed=0"
    return "exit"


def grade(parser, code, out):
    """(state, counts, reason)"""
    counts = {}
    if parser == "go-test":
        counts = {"passed": len(re.findall(r"^\s*--- PASS", out, re.M)), "failed": len(re.findall(r"^\s*--- FAIL", out, re.M)),
                  "skipped": len(re.findall(r"^\s*--- SKIP", out, re.M)),
                  "packages_ok": len(re.findall(r"^ok\s", out, re.M)), "packages_failed": len(re.findall(r"^FAIL\s", out, re.M)),
                  "no_test_files": len(re.findall(r"\[no test files\]", out))}
        counts["discovered"] = counts["passed"] + counts["failed"] + counts["skipped"]
        if code != 0 or counts["failed"]:
            return "FAIL", counts, f"exit {code}, {counts['failed']} failed"
        if counts["passed"] == 0:
            return "FAIL", counts, "exit 0 but no test PASSED - nothing was verified"
        return "PASS", counts, None
    if parser == "dotnet-test":
        tot = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        for m in re.finditer(r"(?:Passed|Failed)!\s+-\s+Failed:\s+(\d+),\s+Passed:\s+(\d+),\s+Skipped:\s+(\d+),\s+Total:\s+(\d+)", out):
            f, p, s, t = map(int, m.groups())
            tot["failed"] += f; tot["passed"] += p; tot["skipped"] += s; tot["total"] += t
        counts = {**tot, "discovered": tot["total"]}
        if code != 0 or tot["failed"]:
            return "FAIL", counts, f"exit {code}, {tot['failed']} failed"
        if tot["passed"] == 0:
            return "FAIL", counts, "no test passed (0 executed or all skipped) - dotnet test exits 0 on that"
        return "PASS", counts, None
    if parser.startswith("regex:"):
        pat = parser[6:]
        if code != 0:
            return "FAIL", counts, f"exit {code}"
        m = re.search(pat, out, re.M)
        if not m:
            return "FAIL", counts, f"exit 0 but expected evidence /{pat}/ not found"
        line = out[out.rfind("\n", 0, m.start()) + 1: out.find("\n", m.end()) if out.find("\n", m.end()) >= 0 else len(out)]
        counts = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
        counts["evidence"] = line.strip()[:120]
        return "PASS", counts, None
    return ("PASS", counts, None) if code == 0 else ("FAIL", counts, f"exit {code}")


def status(a, ws, repo, rdir, meta, commit):
    """Grade the declared checks against the current tree from stored evidence; runs nothing."""
    rows = []
    for c in repo["checks"]:
        m = meta.get((c["module"], c["id"]), {})
        if c["tier"] == "external":
            st, detail = "HUMAN_REQUIRED", "external: " + c["run"]
        else:
            rec = evidence.latest(ws, a["repo"], c["module"], c["id"])
            st, detail = evidence.assess(rec, rdir, {**m, **c}, evidence.scopes_for(REG, c["module"], c["cwd"]))
            if st == "NOT_RUN" and c["tier"] == "extended":
                detail += " (extended: ask the user, then --approve " + c["id"] + ")"
            if rec and st != "NOT_RUN":
                detail += f"; log {rec.get('log')}"
        rows.append({"tier": c["tier"], "module": c["module"], "check": c["id"], "state": st, "detail": detail})
    out = {"repo": a["repo"], "branch": repo["branch"], "commit": commit, "mode": "status", "checks": rows}
    if a["json"]:
        print(json.dumps(out, indent=2))
    else:
        print(f"Evidence for {a['repo']} @ {repo['branch']} {commit[:7]} against the CURRENT tree (nothing was run)")
        if not rows:
            print(NONE_REGISTERED)
        print("| Tier | Module | Check | State | Detail |")
        print("|---|---|---|---|---|")
        for x in rows:
            print(f"| {x['tier']} | {x['module']} | {x['check']} | **{x['state']}** | {x['detail']} |")
        tally = {}
        for x in rows:
            tally[x["state"]] = tally.get(x["state"], 0) + 1
        print("Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    return 0 if all(x["state"] == "PASS" for x in rows if x["tier"] == "fast") else 1


NONE_REGISTERED = "Checks: none registered for these paths - nothing to verify."


def within(p, d):
    p, d = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(d))
    return p == d or p.startswith(d.rstrip("\\/") + os.sep)


def outside_paths(a, repo):
    """--paths this run cannot verify. context.py drops (and lists in rejected_paths) absolute paths outside
    every checkout of the repo, and maps a path in another linked worktree of the repo to its repo-relative form -
    but checks run in the checkout run-checks runs in (repo["path"]), so evidence for that path would come from
    the wrong tree. Relative ../ paths escape the repo. Returns (outside, elsewhere)."""
    rdir = repo["path"]
    outside = [x["path"] for x in repo.get("rejected_paths", [])]
    outside += [f["path"] for f in repo["files"] if posixpath.normpath(f["path"]) == ".." or posixpath.normpath(f["path"]).startswith("../")]
    given = [native_abs(p.strip().strip('"').strip("'").replace("\\", "/")) for x in a["paths"] for p in x.split(",") if p.strip()]
    elsewhere = [p for p in given if os.path.isabs(p) and not within(p, rdir) and p not in outside]
    return outside, elsewhere


def context(a, paths):
    ctx_cmd = ["bash", os.path.join(PLUGIN_ROOT, "scripts", "factory-context.sh"), "--repo", a["repo"], "--json"]
    if paths:
        ctx_cmd += ["--paths", *paths]
    r = subprocess.run(ctx_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "CLAUDE_PLUGIN_ROOT": PLUGIN_ROOT})
    if r.returncode != 0:
        if "no path left to route" in r.stderr:  # every --paths entry is outside the repo and its worktrees
            usage_error(f"path(s) outside the {a['repo']} checkout and its worktrees: {r.stderr.strip()}")
        print(r.stderr, file=sys.stderr)
        sys.exit(2)
    repo = json.loads(r.stdout)["repos"][0]
    if repo.get("error"):
        usage_error(repo["error"])
    return repo


def main():
    a = parse_args(sys.argv[1:])
    requested_ws = os.environ.get(REG["workspace"]["root_env"])
    ws = fstate.workspace(REG)
    repo = context(a, a["paths"])
    rdir = repo["path"]
    if a["paths"]:
        outside, elsewhere = outside_paths(a, repo)
        if outside:
            usage_error(f"path(s) outside the {a['repo']} checkout {rdir} and its worktrees: {', '.join(outside)}")
        if elsewhere:  # checks run in rdir: evidence for another worktree's file would describe the wrong tree
            usage_error(f"path(s) in another checkout of {a['repo']}: {', '.join(elsewhere)}; run run-checks from that "
                        f"checkout (checks run in, and evidence describes, the checkout run-checks runs in: {rdir})")
    unknown = [o for o in a["only"] if not any(o in (c["id"], f"{c['module']}/{c['id']}") for c in repo["checks"])]
    if unknown:
        usage_error(f"--only {' '.join(unknown)}: no such check for these paths; declared: "
                    + (", ".join(f"{c['module']}/{c['id']}" for c in repo["checks"]) or "none"))
    meta = {(m["id"], c["id"]): c for m in REG["modules"] for t in ("fast", "extended", "external") for c in m["checks"][t]}
    commit = git(rdir, "rev-parse", "HEAD").strip()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    if a["status"]:
        return status(a, ws, repo, rdir, meta, commit)
    results, state_of = [], {}  # (module, check id) -> state in THIS run

    def need_state(module, n):
        """State of prerequisite `n` in this run: the same module's check, else that id in any module (a
        non-PASS anywhere wins); None when it has not been graded before the check that needs it."""
        if (module, n) in state_of:
            return state_of[(module, n)]
        sts = [s for (_, i), s in state_of.items() if i == n]
        return next((s for s in sts if s != "PASS"), sts[0] if sts else None)

    seen = {}
    for c in repo["checks"]:
        key = (c["module"], c["id"])
        dedup = (c["cwd"], c["run"])
        m = meta.get(key, {})
        res = {"module": c["module"], "check": c["id"], "tier": c["tier"], "command": c["run"], "cwd": c["cwd"],
               "repo": a["repo"], "branch": repo["branch"], "commit": commit, "state": None, "exit": None,
               "duration_s": None, "counts": {}, "reason": None, "output_tail": None, "evidence_expected": c["evidence"]}
        full_id = f"{c['module']}/{c['id']}"
        unmet = [(n, need_state(c["module"], n)) for n in m.get("needs", []) if need_state(c["module"], n) != "PASS"]
        if a["only"] and full_id not in a["only"] and c["id"] not in a["only"]:
            res.update(state="SKIPPED", reason="not in --only")
        elif c["tier"] == "external":
            res.update(state="HUMAN_REQUIRED", reason="external: " + c["run"])
        elif c["tier"] == "extended" and c["id"] not in a["approve"] and full_id not in a["approve"]:
            res.update(state="HUMAN_REQUIRED", reason="extended check - ask the user"
                       + (f" (trigger: {c['trigger']})" if c.get("trigger") else "") + f", then rerun with --approve {c['id']}")
        elif a["tier"] not in ("all", c["tier"]) and not (c["tier"] == "extended" and (c["id"] in a["approve"] or full_id in a["approve"])):
            res.update(state="SKIPPED", reason=f"tier {c['tier']} not requested (--tier {a['tier']})")
        elif c["missing_tools"]:
            res.update(state="NOT_AVAILABLE", reason="missing tool(s): " + ", ".join(c["missing_tools"]))
        elif a["dry"]:
            res.update(state="SKIPPED", reason="--dry-run")
        elif unmet:  # a prerequisite that did not PASS in this run (failed, skipped, not run yet) proves nothing
            res.update(state="BLOCKED", reason="needs a check that did not pass in this run: "
                       + ", ".join(f"{n} ({s or 'not run before it'})" for n, s in unmet))
        elif dedup in seen:
            # same command + cwd already ran for another module: grade that output against THIS check's
            # definition and record it with this module's own scopes and identity
            first, out = seen[dedup]
            scopes = evidence.scopes_for(REG, c["module"], c["cwd"])
            state, counts, reason = grade(parser_for({**m, **c}), first["exit"], out)
            res.update(state=state, exit=first["exit"], duration_s=0.0, counts=counts,
                       reason=(reason + "; " if reason else "") + f"same command already ran for {first['module']}/{first['check']}; output shared",
                       output_tail=first["output_tail"], identity=evidence.identity(rdir, scopes, {**m, **c}), timestamp=stamp, scopes=scopes,
                       definition={k: {**m, **c}.get(k) for k in ("run", "cwd", "parser", "evidence")})
            res["log"] = evidence.store(ws, a["repo"], res, out)
        else:
            cwd = os.path.normpath(os.path.join(rdir, c["cwd"]))
            if not os.path.isdir(cwd):
                res.update(state="BLOCKED", reason=f"working directory {c['cwd']} does not exist in {rdir}")
                state_of[key] = res["state"]
                results.append(res)
                continue
            before = worktree_state(rdir)
            scopes = evidence.scopes_for(REG, c["module"], c["cwd"])
            ident = evidence.identity(rdir, scopes, {**m, **c})
            t0 = time.perf_counter()
            bash = shutil.which("bash")
            ws_path = bash_env_path(ws, bash) if bash else None
            repo_path = bash_env_path(os.path.realpath(rdir), bash) if bash else None
            head = git(rdir, "rev-parse", "HEAD").strip()
            if not os.path.isdir(ws) or (requested_ws and not os.path.isdir(requested_ws)) or not ws_path or not repo_path or not head:
                res.update(state="BLOCKED", reason="workspace or checkout path cannot be resolved for the selected bash environment")
                state_of[key] = res["state"]
                results.append(res)
                continue
            try:
                code, out, timed_out, cleanup = run_check(c["run"], cwd, {
                    **os.environ, "PYTHONDONTWRITEBYTECODE": "1", "RPG_FACTORY_WORKSPACE": ws_path,
                    "RPG_FACTORY_REPO_DIR": repo_path, "RPG_FACTORY_REPO_KEY": a["repo"], "RPG_FACTORY_HEAD": head,
                }, a["timeout"])
            except OSError as e:
                code, out, timed_out, cleanup = 127, f"could not start: {e}", False, "not started"
            res["duration_s"] = round(time.perf_counter() - t0, 1)
            res["exit"] = code
            state, counts, reason = grade(parser_for({**m, **c}), code, out)
            after = worktree_state(rdir)
            leftovers = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
            if leftovers:
                state = "FAIL"
                reason = (reason + "; " if reason else "") + f"check left {len(leftovers)} untracked/changed path(s) in the repo: {', '.join(leftovers[:5])}"
            if timed_out:
                state = "FAIL"
                diag = out.splitlines()[0] if out.startswith("TIMEOUT") else f"TIMEOUT after {a['timeout']} s"
                reason = f"{diag}; cleanup={cleanup}"
            res.update(state=state, counts=counts, reason=reason, output_tail="\n".join(out.strip().splitlines()[-15:]),
                       identity=ident, timestamp=stamp, scopes=scopes,
                       definition={k: {**m, **c}.get(k) for k in ("run", "cwd", "parser", "evidence")})
            res["log"] = evidence.store(ws, a["repo"], res, out)
            seen[dedup] = (res, out)
        state_of[key] = res["state"]
        results.append(res)

    record = {"repo": a["repo"], "path": rdir, "branch": repo["branch"], "commit": commit, "timestamp": stamp,
              "paths": a["paths"] or [f["path"] for f in repo["files"]], "routing": repo["routing"], "results": results}
    if a["dry"]:
        rf = None  # --dry-run records nothing: no run record, no evidence
    else:
        outdir = os.path.join(fstate.persistent(), "evidence", fstate.workspace_key(ws), "runs")
        rf = os.path.join(outdir, f"{a['repo']}-{stamp}-{fstate.unique_suffix()}.json")  # unique: parallel runs never collide
        fstate.write_json(rf, record, indent=2)
    if a["json"]:
        print(json.dumps(record, indent=2))
    else:
        print(f"Checks for {a['repo']} @ {repo['branch']} {commit[:7]} (evidence: {rf or 'none, --dry-run'})")
        if not results:
            print(NONE_REGISTERED)
        print("| Tier | Module | Check | State | Evidence / reason | Time |")
        print("|---|---|---|---|---|---|")
        for x in results:
            ev = ", ".join(f"{k}={v}" for k, v in x["counts"].items() if k in ("discovered", "executed", "passed", "failed", "skipped", "total")) \
                 or ("exit " + str(x["exit"]) if x["exit"] is not None else "")
            why = x["reason"] or ""
            print(f"| {x['tier']} | {x['module']} | {x['check']} | **{x['state']}** | {'; '.join(s for s in (ev, why) if s)} | "
                  f"{x['duration_s'] if x['duration_s'] is not None else '-'} |")
        tally = {}
        for x in results:
            tally[x["state"]] = tally.get(x["state"], 0) + 1
        print("Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    required_bad = [x for x in results if x["tier"] == "fast" and x["state"] in ("FAIL", "BLOCKED", "NOT_AVAILABLE")]
    ran_bad = [x for x in results if x["state"] == "FAIL"]
    return 1 if required_bad or ran_bad else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
