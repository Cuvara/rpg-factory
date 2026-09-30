#!/usr/bin/env python3
"""Factory check runner: executes the registry checks for a change and records evidence.

The agent does not grade its own checks. This runner resolves the checks for the given paths
through the routing engine, runs the local ones, parses their output and assigns a state:

  PASS           ran; exit 0; the parser found positive evidence (e.g. tests executed > 0)
  FAIL           ran and failed, or ran without evidence (0 tests executed), or left files behind
  SKIPPED        not run by explicit choice (--only filter / --tier excludes it)
  BLOCKED        not run: a check it needs failed, or the repo is not a git work tree
  NOT_AVAILABLE  not run: a required tool is missing on this machine
  HUMAN_REQUIRED not run: extended check without --approve, or an external check (CI, Unity
                 Editor, cluster, Docker stack) that a person must run or authorise
  NOT_RUN        (--status) declared for this change, but no evidence was ever recorded
  STALE          (--status) evidence exists but the tree changed since (HEAD, working-tree diff in
                 the check's directory, untracked files there, or the check definition)

Every executed check is stored with the identity of the tree it ran on (lib/evidence.py) and its
full log; the table shows a summary only. `--status` grades the declared checks against the
current tree WITHOUT running anything - a PASS from before an edit shows as STALE.

Usage: run-checks.py --repo <key> [--paths <p>...] [--tier fast|extended|external|all]
                     [--approve <check-id>...] [--only <module/check-id>...] [--timeout SEC]
                     [--dry-run] [--json] [--status]
  --paths      the files the task changed (default: the repo's working tree + branch diff)
  --tier       default "fast"; extended/external are listed as HUMAN_REQUIRED unless approved
Evidence: <state root>/evidence/<workspace>/<repo>/ (lib/fstate.py; never inside a repo).
Exit: 0 all executed checks PASS; 1 any FAIL/BLOCKED/NOT_AVAILABLE among required checks; 2 usage.
      --status: 0 only when every fast check is PASS on the current tree.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
REG = json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
sys.path.append(os.path.join(HERE, "lib"))  # appended: stdlib lookups must not stat /mnt/c first
import evidence  # noqa: E402
import fstate  # noqa: E402


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
        print(f"run-checks: --repo <{'|'.join(REG['repos'])}> required", file=sys.stderr)
        sys.exit(2)
    a["timeout"] = int(a["timeout"])
    return a


def git(d, *args):
    try:
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def worktree_state(d):
    """Paths that are changed/untracked (submodule internals excluded) - to detect check pollution."""
    return set(l[3:] for l in git(d, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=all").splitlines())


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
            st, detail = evidence.assess(rec, rdir, {**m, **c})
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
        print("| Tier | Module | Check | State | Detail |")
        print("|---|---|---|---|---|")
        for x in rows:
            print(f"| {x['tier']} | {x['module']} | {x['check']} | **{x['state']}** | {x['detail']} |")
        tally = {}
        for x in rows:
            tally[x["state"]] = tally.get(x["state"], 0) + 1
        print("Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    return 0 if all(x["state"] == "PASS" for x in rows if x["tier"] == "fast") else 1


def main():
    a = parse_args(sys.argv[1:])
    ws = REG["workspace"]["root_default"]
    env_ws = os.environ.get(REG["workspace"]["root_env"])
    ws = env_ws if env_ws and os.path.isdir(env_ws) else ws
    ctx_cmd = ["bash", os.path.join(PLUGIN_ROOT, "scripts", "factory-context.sh"), "--repo", a["repo"], "--json"]
    if a["paths"]:
        ctx_cmd += ["--paths", *a["paths"]]
    r = subprocess.run(ctx_cmd, capture_output=True, text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": PLUGIN_ROOT})
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(2)
    snap = json.loads(r.stdout)
    repo = snap["repos"][0]
    if repo.get("error"):
        print(f"run-checks: {repo['error']}", file=sys.stderr)
        sys.exit(2)
    rdir = repo["path"]
    meta = {(m["id"], c["id"]): c for m in REG["modules"] for t in ("fast", "extended", "external") for c in m["checks"][t]}
    commit = git(rdir, "rev-parse", "HEAD").strip()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    if a["status"]:
        return status(a, ws, repo, rdir, meta, commit)
    results, failed_ids = [], set()
    seen = {}
    before = None
    for c in repo["checks"]:
        key = (c["module"], c["id"])
        dedup = (c["cwd"], c["run"])
        m = meta.get(key, {})
        res = {"module": c["module"], "check": c["id"], "tier": c["tier"], "command": c["run"], "cwd": c["cwd"],
               "repo": a["repo"], "branch": repo["branch"], "commit": commit, "state": None, "exit": None,
               "duration_s": None, "counts": {}, "reason": None, "output_tail": None, "evidence_expected": c["evidence"]}
        full_id = f"{c['module']}/{c['id']}"
        if dedup in seen:
            res.update(state="SKIPPED", reason="same command already ran for another module in this run")
            first = seen[dedup]
            if first.get("identity"):  # same command + cwd = same evidence: record it for this module too
                evidence.store(ws, a["repo"], dict(first, module=c["module"], check=c["id"]), open(first["log"], encoding="utf-8", errors="replace").read())
        elif a["only"] and full_id not in a["only"] and c["id"] not in a["only"]:
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
        elif any(n in failed_ids for n in m.get("needs", [])):
            res.update(state="BLOCKED", reason="a check it needs did not pass: " + ", ".join(n for n in m.get("needs", []) if n in failed_ids))
        elif a["dry"]:
            res.update(state="SKIPPED", reason="--dry-run")
        else:
            seen[dedup] = res
            cwd = os.path.normpath(os.path.join(rdir, c["cwd"]))
            if not os.path.isdir(cwd):
                res.update(state="BLOCKED", reason=f"working directory {c['cwd']} does not exist in {rdir}")
                failed_ids.add(c["id"])
                results.append(res)
                continue
            if before is None:
                before = worktree_state(rdir)
            scopes = evidence.scopes_for(REG, c["module"], c["cwd"])
            ident = evidence.identity(rdir, scopes, {**m, **c})
            t0 = time.perf_counter()
            try:
                p = subprocess.run(["bash", "-c", c["run"]], cwd=cwd, capture_output=True, text=True, timeout=a["timeout"], errors="replace",
                                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
            except OSError as e:
                code, out = 127, f"could not start: {e}"
            except subprocess.TimeoutExpired as e:
                code, out = 124, f"TIMEOUT after {a['timeout']} s\n" + ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
            res["duration_s"] = round(time.perf_counter() - t0, 1)
            res["exit"] = code
            state, counts, reason = grade(parser_for({**m, **c}), code, out)
            after = worktree_state(rdir)
            leftovers = sorted(after - before)
            if leftovers:
                state = "FAIL"
                reason = (reason + "; " if reason else "") + f"check left {len(leftovers)} untracked/changed path(s) in the repo: {', '.join(leftovers[:5])}"
            res.update(state=state, counts=counts, reason=reason, output_tail="\n".join(out.strip().splitlines()[-15:]),
                       identity=ident, timestamp=stamp, scopes=scopes,
                       definition={k: {**m, **c}.get(k) for k in ("run", "cwd", "parser", "evidence")})
            res["log"] = evidence.store(ws, a["repo"], res, out)
        if res["state"] in ("FAIL", "BLOCKED", "NOT_AVAILABLE"):
            failed_ids.add(c["id"])
        results.append(res)

    outdir = os.path.join(fstate.persistent(), "evidence", fstate.workspace_key(ws), "runs")
    os.makedirs(outdir, exist_ok=True)
    record = {"repo": a["repo"], "path": rdir, "branch": repo["branch"], "commit": commit, "timestamp": stamp,
              "paths": a["paths"] or [f["path"] for f in repo["files"]], "routing": repo["routing"], "results": results}
    rf = os.path.join(outdir, f"{a['repo']}-{stamp}.json")
    json.dump(record, open(rf, "w", encoding="utf-8"), indent=2)
    if a["json"]:
        print(json.dumps(record, indent=2))
    else:
        print(f"Checks for {a['repo']} @ {repo['branch']} {commit[:7]} (evidence: {rf})")
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
    sys.exit(main())
