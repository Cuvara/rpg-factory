#!/usr/bin/env python3
"""Routing properties over REAL history (read-only): every recent commit of every workspace repo
is replayed through scripts/lib/resolve.jq and must satisfy:

  P1 deterministic lead: at most one lead; when any lead candidate exists, routing.lead is set
  P2 not ambiguous: routing.ambiguous is false (skill orders are unique)
  P3 order-invariant: shuffling the file list does not change lead/co-leads/legs/follow-ups
  P4 no role conflict: a skill is never both lead/co-lead and a follow-up
  P5 nothing unmapped: every path maps to a module (repo-level files go to <repo>.root)
  P6 coverage floor: >= 95% of commits get a lead unless all their touched modules are
     deliberately skill-less (docs / repo-level / user-owned submodules)

Usage: tests/routing-properties.test.py [--commits N]   (default 120 per repo; client since 2026-09-07)
Skips a repo that is not present. Exit 1 on any violation.
"""
import json
import os
import random
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.environ.get("RPG_FACTORY_WORKSPACE", "/mnt/c/Workspaces/UnityIndie")
REG = json.load(open(os.path.join(ROOT, "registry.json"), encoding="utf-8"))
N = int(sys.argv[sys.argv.index("--commits") + 1]) if "--commits" in sys.argv else 120


def git(d, *a):
    return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True).stdout


def resolve(repo, files):
    fj = json.dumps([{"path": p, "status": "--", "source": "given"} for p in files])
    r = subprocess.run(["jq", "-c", "--arg", "repo", repo, "--argjson", "files", fj, "--argjson", "subst", "{}",
                        "--argjson", "tools", "{}", "-f", os.path.join(ROOT, "scripts/lib/resolve.jq"),
                        os.path.join(ROOT, "registry.json")], capture_output=True, text=True)
    return json.loads(r.stdout)


def key(rt):
    return (rt["lead"], tuple(rt["co_leads"]), tuple(sorted(rt["legs"])), tuple(sorted(rt["follow_ups"])))


skillless = {m["id"] for m in REG["modules"] if not m.get("skills")}
viol, stats = [], {}
rng = random.Random(7)
for rk, rep in REG["repos"].items():
    d = os.path.join(WS, rep["path"])
    if not os.path.isdir(os.path.join(d, ".git")):
        print(f"SKIP  {rk}: not present")
        continue
    extra = ["--since=2026-09-07"] if rk == "client" else []
    shas = git(d, "log", "--no-merges", f"-{N}", "--format=%h", *extra).split()
    n = lead_n = exempt = 0
    for s in shas:
        files = [f for f in git(d, "show", "--name-only", "--format=", s).splitlines() if f]
        if not files:
            continue
        n += 1
        r = resolve(rk, files)
        rt = r["routing"]
        leads = [x["skill"] for x in r["suggested_skills"] if x["role"] == "lead"]
        if leads and not rt["lead"]:
            viol.append(f"P1 {rk}@{s}: lead candidates {leads} but no routing.lead")
        if rt["ambiguous"]:
            viol.append(f"P2 {rk}@{s}: ambiguous between {leads[:2]}")
        shuffled = files[:]
        rng.shuffle(shuffled)
        if key(resolve(rk, shuffled)["routing"]) != key(rt):
            viol.append(f"P3 {rk}@{s}: routing depends on file order")
        both = ({rt["lead"]} | set(rt["co_leads"])) & set(rt["follow_ups"])
        if both - {None}:
            viol.append(f"P4 {rk}@{s}: {sorted(both)} both lead and follow-up")
        if r["unmapped"]:
            viol.append(f"P5 {rk}@{s}: unmapped {r['unmapped'][:3]}")
        if rt["lead"]:
            lead_n += 1
        elif set(r["touched"]) <= skillless:
            exempt += 1
    cov = (lead_n + exempt) / n if n else 1.0
    stats[rk] = f"{n} commits, {lead_n} with a lead, {exempt} deliberately skill-less, coverage {cov:.0%}"
    if n and cov < 0.95:
        viol.append(f"P6 {rk}: coverage {cov:.0%} < 95%")
    print(f"INFO  {rk}: {stats[rk]}")
for v in viol:
    print("FAIL  " + v)
print(f"routing properties: {len(stats)} repos, {len(viol)} violation(s)")
sys.exit(1 if viol or not stats else 0)
