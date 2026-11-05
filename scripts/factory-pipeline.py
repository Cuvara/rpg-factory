#!/usr/bin/env python3
"""Delivery pipeline for one Factory task: tier, plan validation, dispatch commands, review/QA verdicts, PR gate.

Policy: skills/factory-core/references/parallel-work.md. Settings: registry.json `pipeline` (tiers, agents,
cross-model review pairing, exclusive resources) and `repos.<key>.worktrees`. Plan format:
docs/schemas/pipeline-plan.schema.json.

  tier [--json] [--context-json FILE] [-- <factory-context.sh args>]
        S | M | L from the routing snapshot (repos, modules, files, contracts, generated paths).
  tier --plan <plan.json> --repo KEY --paths FILE... [--json]
        the same for a plan repo key; a plan.repos entry the registry does not know (the plugin repo) is tiered
        from the paths alone: modules are skills/<name>, scripts/lib or the top-level directory, no contracts.
  validate <plan.json> [--json]
        disjoint path ownership, dependency cycles, waves, the no-worktree rule (Unity projects: tasks one
        after another in the main checkout, never two in one wave), cross-model review pairing, and shared
        exclusive resources (one Unity test run at a time). Exit 1 on an error.
  subplan validate <subplan.json> [--plan PATH] [--json]
        a task lead's split of ONE plan task (docs/schemas/pipeline-subplan.schema.json; `plan` is the plan file,
        relative to the subplan, or --plan; `task` the task id): an unknown task, a subtask path outside the task's owned
        paths or inside its exclusions, overlapping paths of subtasks not ordered by deps, unknown deps or a cycle, an
        implementer that is no pipeline agent and a reviewer of the implementer's model (registry
        pipeline.review_pairing) are errors. Prints the waves. Exit 0 OK, 1 errors, 2 usage.
  planner --request TEXT [--runner orca|agent|print] [--agent ID]
        the planner dispatch: read-only, in the lead's checkout (no worktree), writes plan.json.
  dispatch <plan.json> --task ID --phase lead [--report-to RUN_ID] [--runner orca|agent|print] [--agent ID]
        the run lead starts ONE task-lead session per task. In a worktree repo it gets the task worktree: created here
        from the base on the task branch <topic>-<id> (or resumed when that branch is already checked out); in a
        no-worktree repo the main checkout, never a worktree. The prompt is the task spec plus the task-lead rules: its
        own Orca Run, split into subtasks with disjoint paths (`subplan validate`), one fresh session per subtask in the
        same worktree, sub-sessions do not commit, the task lead commits per subtask, cross-model review and QA sessions
        there, release each session, report a `status` message (to Orca run RUN_ID: worker_done needs a dispatch,
        which the task lead has not) with branch and HEAD; never push, merge or remove the worktree. Orca forbids
        nested workers, so --runner orca prints a handoff, not a worker-start:
        `orca worktree create --branch <task branch> --no-parent --agent ... --prompt ...` for a new task worktree,
        `orca agent launch --worktree path:<dir> --prompt ...` for an existing one or a no-worktree repo.
  dispatch <plan.json> --task ID --phase implement [--paths P...] [--runner ...] [--agent ID]
  dispatch <plan.json> --task ID --phase review|qa --sha SHA [--runner ...] [--agent ID]
        a session started by the task lead. In a worktree repo it joins the task's EXISTING worktree (found by the task
        branch in `git worktree list`, `--worktree path:<it>`), never a new one: no such worktree is an error (exit 1;
        run `--phase lead` first). implement: a sub-session that edits only the owned paths, or the subtask's --paths
        (inside them; it may then name its model with --agent), and does not commit. review/qa need --sha, the frozen
        candidate the task lead keeps at HEAD, and are read-only; the reviewer is the implementer's pair (another
        model) unless --agent overrides it. Per-task qa runs in the task worktree (a no-worktree repo: main checkout).
        No-worktree repo without --paths: an implement worker that commits on the task branch in the main checkout.
  dispatch <plan.json> --task integration:<repo> --phase qa --sha SHA [--runner ...] [--agent ID]
        QA of the integrated tree: a new worktree at SHA (a no-worktree repo: the main checkout).
  verdict <plan.json> --task ID --phase review|qa --sha SHA --by AGENT --state PASS|FAIL|NOT_RUN|BLOCKED [--report FILE]
        records a review or QA verdict (the only write: <state dir>/pipeline/<plan id>/, lib/fstate.py). A per-task
        qa verdict of a worktree repo is the task lead's record; the gate still needs QA on the integration HEAD.
  gate <plan.json> [--allow-same-model] [--no-run-checks] [--json]
        READY_FOR_PR when every task is integrated, reviewed PASS by its paired model on a commit whose task
        paths did not change since, QA is PASS on each integration HEAD, the integration trees are clean,
        fast checks are PASS and not STALE, every change sits in some task's owned paths, verdicts match the
        current plan (fingerprint), and no worktree of a no-worktree repo was created for the plan. With
        --no-run-checks the state is UNVERIFIED (no delivery commands).
        Then prints the push and `gh pr create` commands (run them only when the user authorized
        `deliver: pr` in this task; merging stays with the user). Exit 0 READY, 1 not ready.

  status <plan.json> [--json]
        how far each task got (pending, implementing, candidate, reviewed, integrated, qa), derived from git and
        the recorded verdicts, with the next command per task and the ready wave: how a new lead session resumes a
        run. Schema docs/schemas/pipeline-status.schema.json. Exit 1 when the plan is invalid.

  cleanup <plan.json> [--json]
        CLEAN when the run left no worktree or task branch (<topic>-*); otherwise prints `git worktree remove`
        and `git branch -d` for integrated ones, names the rest, and reminds to release every worker session.
        Exit 0 CLEAN, 1 LEFTOVER.

Read-only against the repos (never fetches, pushes, commits or creates worktrees: the printed commands do). Exit 2 =
usage error.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.append(os.path.join(HERE, "lib"))
import fstate  # noqa: E402
import orca_cmd  # noqa: E402
from shells import find_bash  # noqa: E402

SCHEMA = "rpg-factory.pipeline-plan/1"


def die(msg, code=2):
    print(f"factory-pipeline: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_registry(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def settings(reg):
    p = reg.get("pipeline")
    if not p:
        die("registry has no `pipeline` block")
    return p


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None, 1
    return r.stdout.strip(), r.returncode


# ---------------------------------------------------------------- tier

def tier_of(ctx, pipe):
    repos = [r for r in ctx.get("repos", []) if r.get("touched") or any(f.get("source") == "given" for f in r.get("files", []))]
    modules = sorted({m for r in repos for m in r.get("touched", [])})
    files = sum(1 for r in repos for f in r.get("files", []) if f.get("source") in ("given", "branch"))
    contracts = sorted({c["id"] for r in repos for c in r.get("contracts", [])})
    generated = sorted({h if isinstance(h, str) else h.get("path", "?") for r in repos for h in r.get("generated_hits", [])})
    facts = {"repos": [r["repo"] for r in repos], "modules": modules, "files": files, "contracts": contracts, "generated": generated}

    def fits(t):
        rule = pipe["tiers"][t]
        why = []
        if "max_repos" in rule and len(repos) > rule["max_repos"]:
            why.append(f"{len(repos)} repos > {rule['max_repos']}")
        if "max_modules" in rule and len(modules) > rule["max_modules"]:
            why.append(f"{len(modules)} modules > {rule['max_modules']}")
        if "max_files" in rule and files > rule["max_files"]:
            why.append(f"{files} files > {rule['max_files']}")
        if rule.get("contracts") is False and contracts:
            why.append("contract " + ", ".join(contracts))
        if rule.get("generated") is False and generated:
            why.append("generated path " + ", ".join(generated))
        return why

    reasons = {}
    for t in ("S", "M"):
        reasons[t] = fits(t)
        if not reasons[t]:
            return {"tier": t, "facts": facts, "above": reasons, "flow": pipe["tiers"][t].get("flow", "")}
    return {"tier": "L", "facts": facts, "above": reasons, "flow": pipe["tiers"]["L"].get("flow", "")}


PLAIN_MODULE_DIRS = ("scripts/lib", "scripts", "tests", "registry", "docs", "hooks", "commands")


def plain_module(p):
    """Module of a path in a repo the registry does not map (the plugin repo): skills/<name>, one of PLAIN_MODULE_DIRS,
    or `other` for anything else (root files, .claude, evals, changelog.d, ...)."""
    path = "/".join(x for x in str(p).replace("\\", "/").split("/") if x not in ("", "."))
    parts = path.split("/")
    if parts[0] == "skills" and len(parts) > 2:
        return "skills/" + parts[1]
    for d in PLAIN_MODULE_DIRS:
        if path.startswith(d + "/"):
            return d
    return "other"


def plain_context(key, paths):
    """A routing snapshot built from the paths alone: one repo, no contracts, no generated paths."""
    files = sorted(set(paths))
    return {"repos": [{"repo": key, "touched": sorted({plain_module(p) for p in files}),
                       "files": [{"path": p, "source": "given"} for p in files], "contracts": [], "generated_hits": []}]}


def cmd_tier(a, reg):
    pipe = settings(reg)
    if a.plan:
        if not a.repo or not a.paths:
            die("tier --plan needs --repo <plan repo key> and --paths <files>")
        plan = read_plan(a.plan)
        plan["_path"] = a.plan
        info = repo_info(plan, reg, a.repo)
        if not info["registry"]:
            if not info["path"]:
                die(f"repo `{a.repo}` is neither a registry repo nor in plan.repos with a path")
            out = tier_of(plain_context(a.repo, a.paths), pipe)
            out["basis"] = "paths (repo not in the registry)"
            return print_tier(a, out)
        a.rest = ["--repo", info["registry"], "--paths", *a.paths, *a.rest]
    elif a.repo or a.paths:
        die("--repo/--paths go with --plan; for a registry repo pass them after `--` to factory-context.sh")
    if a.context_json:
        with open(a.context_json, encoding="utf-8") as fh:
            ctx = json.load(fh)
    else:
        argv = [find_bash() or "bash", os.path.join(HERE, "factory-context.sh"), *a.rest, "--json"]
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            die("factory-context.sh failed: " + (r.stderr or r.stdout).strip()[:400], 1)
        ctx = json.loads(r.stdout)
    return print_tier(a, tier_of(ctx, pipe))


def print_tier(a, out):
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        f = out["facts"]
        print(f"Tier: {out['tier']}  ({len(f['repos'])} repo(s), {len(f['modules'])} module(s), {f['files']} file(s), "
              f"contracts: {', '.join(f['contracts']) or 'none'}, generated: {', '.join(f['generated']) or 'none'})")
        if out.get("basis"):
            print(f"  basis: {out['basis']}; modules: {', '.join(f['modules'])}")
        for t, why in out["above"].items():
            if why:
                print(f"  above {t}: " + "; ".join(why))
        print("Flow: " + out["flow"])
    return 0


# ---------------------------------------------------------------- plan

def read_plan(path):
    try:
        with open(path, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, ValueError) as e:
        die(f"cannot read plan {path}: {e}")
    if not isinstance(plan, dict):
        die("plan must be a JSON object")
    return plan


def repo_info(plan, reg, key):
    """{key, path, base, registry} for a task repo: a registry key, or an entry of plan.repos (unregistered)."""
    own = (plan.get("repos") or {}).get(key) or {}
    rreg = reg.get("repos", {}).get(own.get("registry", key))
    path = own.get("path") or (orca_cmd.repo_checkout(reg, own.get("registry", key)) if rreg else None)
    if path and not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(plan["_path"])), path))
    base = own.get("base") or (rreg or {}).get("default_branch")
    allowed, reason = orca_cmd.allows_worktree(reg, own.get("registry", key) if rreg else None, path)
    ident = os.path.normcase(os.path.realpath(path)) if path else f"?{key}"
    return {"key": key, "registry": own.get("registry", key) if rreg else None, "path": path, "base": base,
            "base_sha": own.get("base_sha"), "worktrees": allowed, "reason": reason, "identity": ident}


def same_repo(plan, reg, x, y):
    """Two plan repo keys name one checkout (a registry key and a plan.repos alias of the same path)."""
    return x == y or repo_info(plan, reg, x)["identity"] == repo_info(plan, reg, y)["identity"]


def norm_path(p):
    """Repo-relative owned path in one spelling: forward slashes, no leading ./, case-folded where the file system is."""
    p = str(p).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lower() if os.name == "nt" else p  # not normcase: it turns / into \ on Windows


def task_fingerprint(task, pipe):
    """What a verdict vouches for: a changed objective, owned paths, acceptance, checks or agents invalidate it."""
    keys = {k: task.get(k) for k in ("repo", "objective", "paths", "exclusions", "acceptance", "checks", "reviewer")}
    keys["implementer"] = task.get("implementer") or pipe["default_implementer"]
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()[:16]


def overlaps(p, q):
    a, b = norm_path(p).rstrip("/"), norm_path(q).rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/") or a in ("", ".") or b in ("", ".")


def waves_of(tasks):
    ids = [t["id"] for t in tasks]
    deps = {t["id"]: [d for d in t.get("deps", []) if d in ids] for t in tasks}
    done, waves = set(), []
    while len(done) < len(ids):
        ready = [i for i in ids if i not in done and all(d in done for d in deps[i])]
        if not ready:
            return waves, [i for i in ids if i not in done]
        waves.append(ready)
        done.update(ready)
    return waves, []


def depends(by_id, x, y):
    """x depends on y, directly or transitively (by_id: id -> item with `deps`)."""
    seen, todo = set(), [x]
    while todo:
        for d in by_id.get(todo.pop(), {}).get("deps", []):
            if d == y:
                return True
            if d not in seen:
                seen.add(d)
                todo.append(d)
    return False


def ordered(by_id, x, y):
    """One of x, y depends on the other: they never run at once, so they may touch the same files."""
    return depends(by_id, x, y) or depends(by_id, y, x)


def serialize(waves, tasks, reg, plan):
    """Split waves so a no-worktree repo never has two tasks in one wave (they run one after another)."""
    by_id = {t["id"]: t for t in tasks}
    out = []
    for wave in waves:
        rest = list(wave)
        while rest:
            taken, used, nxt = [], set(), []
            for tid in rest:
                info = repo_info(plan, reg, by_id[tid]["repo"])
                if not info["worktrees"] and info["identity"] in used:
                    nxt.append(tid)
                    continue
                if not info["worktrees"]:
                    used.add(info["identity"])
                taken.append(tid)
            out.append(taken)
            rest = nxt
    return out


def validate(plan, reg):
    pipe = settings(reg)
    errors, warnings = [], []
    if plan.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    for k in ("id", "title", "topic", "tasks"):
        if not plan.get(k):
            errors.append(f"missing `{k}`")
    if plan.get("tier") and plan["tier"] not in ("S", "M", "L"):
        errors.append("tier must be S, M or L")
    if plan.get("deliver", "none") not in ("pr", "none"):
        errors.append("deliver must be pr or none")
    tasks = plan.get("tasks") or []
    ids = [t.get("id") for t in tasks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate task id {dup}")
    if "integration" in ids or any(str(i).startswith("integration:") for i in ids):
        errors.append("task id `integration` is reserved for QA on the integration branch")
    agents = pipe["agents"]
    for t in tasks:
        tid = t.get("id", "?")
        for k in ("id", "repo", "objective", "paths", "acceptance"):
            if not t.get(k):
                errors.append(f"task {tid}: missing `{k}`")
        info = repo_info(plan, reg, t.get("repo"))
        if not info["path"]:
            errors.append(f"task {tid}: repo `{t.get('repo')}` is neither a registry repo nor in plan.repos with a path")
        impl = t.get("implementer") or pipe["default_implementer"]
        if impl not in agents:
            errors.append(f"task {tid}: implementer `{impl}` is not a pipeline agent ({', '.join(agents)})")
        reviewer = t.get("reviewer") or pipe["review_pairing"].get(impl)
        if reviewer == impl:
            errors.append(f"task {tid}: reviewer `{reviewer}` is the implementer's model; cross-model review needs the pair "
                          f"({pipe['review_pairing'].get(impl)})")
        if not info["worktrees"] and t.get("worktree") is True:
            errors.append(f"task {tid}: repo `{t.get('repo')}` takes no worktree ({info['reason']}); drop `worktree: true`")
        for d in t.get("deps", []):
            if d not in ids:
                errors.append(f"task {tid}: unknown dependency {d}")
    by_id = {t["id"]: t for t in tasks if t.get("id")}
    for i, t in enumerate(tasks):
        for u in tasks[i + 1:]:
            if not (t.get("repo") and u.get("repo") and same_repo(plan, reg, t["repo"], u["repo"])) or ordered(by_id, t.get("id"), u.get("id")):
                continue  # tasks ordered by a dependency may touch the same files: they never run at once
            hit = [f"{p} ~ {q}" for p in t.get("paths", []) for q in u.get("paths", []) if overlaps(p, q)]
            if hit:
                errors.append(f"tasks {t.get('id')} and {u.get('id')} own overlapping paths ({'; '.join(hit)}): merge them or "
                              f"make one depend on the other")
    waves, cycle = waves_of(list(by_id.values()))
    if cycle:
        errors.append("dependency cycle among " + ", ".join(cycle))
    order = {tid: n for n, w in enumerate(waves) for tid in w}
    planned = serialize(waves, list(by_id.values()), reg, plan) if not cycle else waves
    for n, w in enumerate(planned):
        for res in pipe.get("exclusive_resources", []):
            users = [tid for tid in w for t in tasks if t.get("id") == tid and
                     (res["id"] in t.get("resources", []) or t.get("repo") in res["repos"] or
                      (plan.get("repos") or {}).get(t.get("repo"), {}).get("registry") in res["repos"])]
            if len(users) > 1:
                warnings.append(f"wave {n + 1}: {', '.join(users)} share `{res['id']}` - {res['rule']}")
    no_wt = sorted({t["repo"] for t in tasks if t.get("repo") and not repo_info(plan, reg, t["repo"])["worktrees"]})
    return {"errors": errors, "warnings": warnings, "waves": planned, "order": order,
            "no_worktree_repos": no_wt}


def cmd_validate(a, reg):
    plan = read_plan(a.plan)
    plan["_path"] = a.plan
    out = validate(plan, reg)
    out.pop("order")
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for e in out["errors"]:
            print("ERROR " + e)
        for w in out["warnings"]:
            print("WARN  " + w)
        for n, w in enumerate(out["waves"], 1):
            print(f"Wave {n}: {', '.join(w)}")
        if out["no_worktree_repos"]:
            print("No worktree (main checkout, one task at a time): " + ", ".join(out["no_worktree_repos"]))
        print("OK" if not out["errors"] else f"INVALID ({len(out['errors'])} error(s))")
    return 1 if out["errors"] else 0


# ---------------------------------------------------------------- subplan

SUBPLAN_SCHEMA = "rpg-factory.pipeline-subplan/1"


def validate_subplan(sub, plan, reg):
    """A task lead's split of one plan task into subtasks: same task, disjoint paths inside its owned paths (unless
    ordered by deps), known acyclic deps, waves, a pipeline agent per subtask and a reviewer of the other model."""
    pipe = settings(reg)
    agents, pairing = pipe["agents"], pipe["review_pairing"]
    errors = []
    if sub.get("schema") != SUBPLAN_SCHEMA:
        errors.append(f"schema must be {SUBPLAN_SCHEMA}")
    tid = sub.get("task")
    task = next((t for t in plan.get("tasks", []) if t.get("id") == tid), None) if tid else None
    if not tid:
        errors.append("missing `task`")
    elif task is None:
        errors.append(f"unknown task {tid}: plan {plan.get('id', '?')} has "
                      f"{', '.join(str(t.get('id')) for t in plan.get('tasks', [])) or 'no task'}")
    owned = (task or {}).get("paths") or []
    excluded = (task or {}).get("exclusions") or []
    subs = sub.get("subtasks")
    if not isinstance(subs, list) or not subs:
        errors.append("missing `subtasks`")
        subs = []
    subs = [s for s in subs if isinstance(s, dict)]
    ids = [s.get("id") for s in subs]
    for dup in sorted({str(i) for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate subtask id {dup}")
    for s in subs:
        sid = s.get("id", "?")
        for k in ("id", "objective", "paths", "implementer"):
            if not s.get(k):
                errors.append(f"subtask {sid}: missing `{k}`")
        if s.get("task") not in (None, tid):
            errors.append(f"subtask {sid}: belongs to task {s['task']}, not {tid}: one subplan splits one task")
        if task is not None:
            for p in s.get("paths") or []:
                if not inside_owned(p, owned):
                    errors.append(f"subtask {sid}: path {p} is outside the owned paths of task {tid} ({', '.join(owned)})")
                elif any(inside_owned(p, [x]) or inside_owned(x, [p]) for x in excluded):
                    errors.append(f"subtask {sid}: path {p} overlaps an exclusion of task {tid}")
        impl = s.get("implementer")
        if impl and impl not in agents:
            errors.append(f"subtask {sid}: implementer `{impl}` is not a pipeline agent ({', '.join(agents)})")
        reviewer = s.get("reviewer") or pairing.get(impl)
        if impl in agents and reviewer == impl:
            errors.append(f"subtask {sid}: reviewer `{reviewer}` is the implementer's model; cross-model review needs the "
                          f"pair ({pairing.get(impl)})")
        elif impl in agents and reviewer not in agents:
            errors.append(f"subtask {sid}: reviewer `{reviewer}` is not a pipeline agent ({', '.join(agents)})")
        for d in s.get("deps", []):
            if d not in ids:
                errors.append(f"subtask {sid}: unknown dependency {d}")
    by_id = {s["id"]: s for s in subs if s.get("id")}
    for i, s in enumerate(subs):
        for u in subs[i + 1:]:
            if ordered(by_id, s.get("id"), u.get("id")):
                continue
            hit = [f"{p} ~ {q}" for p in s.get("paths") or [] for q in u.get("paths") or [] if overlaps(p, q)]
            if hit:
                errors.append(f"subtasks {s.get('id')} and {u.get('id')} own overlapping paths ({'; '.join(hit)}): merge "
                              "them or make one depend on the other")
    waves, cycle = waves_of(list(by_id.values()))
    if cycle:
        errors.append("dependency cycle among " + ", ".join(cycle))
    return {"plan": plan.get("_path"), "task": tid, "errors": errors, "waves": waves}


def cmd_subplan(a, reg):
    try:
        with open(a.subplan, encoding="utf-8") as fh:
            sub = json.load(fh)
    except (OSError, ValueError) as e:
        die(f"cannot read subplan {a.subplan}: {e}")
    if not isinstance(sub, dict):
        die("subplan must be a JSON object")
    path = a.plan or sub.get("plan")
    if not path:
        die("the subplan names no `plan` and no --plan was given")
    if not a.plan and not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(a.subplan)), path))
    plan = read_plan(path)
    plan["_path"] = path
    out = validate_subplan(sub, plan, reg)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for e in out["errors"]:
            print("ERROR " + e)
        for n, w in enumerate(out["waves"], 1):
            print(f"Wave {n}: {', '.join(w)}")
        print("OK" if not out["errors"] else f"INVALID ({len(out['errors'])} error(s))")
    return 1 if out["errors"] else 0


# ---------------------------------------------------------------- dispatch

def find_task(plan, tid):
    for t in plan.get("tasks", []):
        if t.get("id") == tid:
            return t
    die(f"unknown task {tid}")


def task_branch(plan, info, task):
    return plan["topic"] if not info["worktrees"] else f"{plan['topic']}-{task['id']}"


def emit(a, reg, agent, prompt, place, title):
    pipe = settings(reg)
    if a.runner == "orca":
        argv = orca_cmd.worker_start(prompt, pipe["agents"][agent]["orca_agent"], place, title=title)
        print(orca_cmd.quote(argv))
    elif a.runner == "agent":
        print(json.dumps(orca_cmd.agent_task(reg, agent, prompt, place, title), indent=2))
    else:
        print(f"# agent: {agent}   worktree: {place['worktree']}" + (f"   base: {place.get('base')}" if place.get("base") else "")
              + (f"   ({place['reason']})" if place.get("reason") else ""))
        print(prompt)
    if not shutil.which(pipe["agents"][agent]["bin"]):
        print(f"factory-pipeline: `{pipe['agents'][agent]['bin']}` is not on PATH here: the {agent} worker may be "
              f"unavailable (fallback: references/parallel-work.md, report the review as SAME_MODEL)", file=sys.stderr)


def cmd_planner(a, reg):
    pipe = settings(reg)
    agent = a.agent or pipe["default_implementer"]
    prompt = ("You are the planner of a Factory delivery pipeline. Read-only: change no file except the plan file.\n"
              f"Request: {a.request}\n"
              "1. Run the Factory route for the files the request will write and read the routed lead skill.\n"
              "2. Break the work into small tasks with disjoint owned paths; order dependent tasks with `deps`.\n"
              "   A repo with `worktrees: false` (Unity project) runs its tasks one after another: give each the full\n"
              "   implement -> review -> QA cycle before the next.\n"
              f"3. Write plan.json ({SCHEMA}, docs/schemas/pipeline-plan.schema.json) and run\n"
              "   `python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py validate plan.json` until it prints OK.\n"
              "4. Report the plan path, waves and any open question. Do not implement.")
    place = {"worktree": "current", "new": False, "reason": "planning is read-only: no worktree"}
    emit(a, reg, agent, prompt, place, "pipeline planner")
    return 0


def serial_predecessor(plan, reg, task):
    """The task that runs before `task` in the same no-worktree repo (wave order), or None."""
    by_id = {t["id"]: t for t in plan["tasks"]}
    seq = [tid for w in validate(plan, reg)["waves"] for tid in w if by_id[tid]["repo"] == task["repo"]]
    i = seq.index(task["id"]) if task["id"] in seq else 0
    return seq[i - 1] if i > 0 else None


def task_worktree(plan, info, task, branch):
    """The existing worktree that has the task branch checked out. Implement, review and per-task QA sessions of a
    worktree repo join the task lead's worktree; they never create one, so a missing one is an error."""
    home = worktree_for(info["path"], branch)[0] if info["path"] else None
    if not home:
        die(f"task {task['id']}: no worktree of {info['path']} has the task branch {branch} checked out. Start the task "
            f"lead first: `dispatch {plan['_path']} --task {task['id']} --phase lead` creates the task worktree. "
            "No worktree was created.", 1)
    return home


def inside_owned(path, owned):
    p = norm_path(path).rstrip("/")
    return any(o in ("", ".") or p == o or p.startswith(o + "/") for o in (norm_path(x).rstrip("/") for x in owned))


def emit_lead_handoff(reg, agent, prompt, place, branch):
    """`orca agent launch` in an existing checkout, or `orca worktree create --agent` for the new task worktree: the task
    lead is not an Orca worker of the run lead (Orca forbids nested workers, max depth 1)."""
    entry = settings(reg)["agents"][agent]
    if place.get("new"):
        argv = ["orca", "worktree", "create", "--name", branch]
        for flag, key in (("--repo", "repo"), ("--base-branch", "base")):
            if place.get(key):
                argv += [flag, place[key]]
        argv += ["--branch", branch, "--no-parent", "--agent", entry["orca_agent"], "--prompt", prompt, "--json"]
    else:
        argv = ["orca", "agent", "launch", "--agent", entry["orca_agent"], "--worktree", place["worktree"], "--prompt", prompt,
                "--json"]
    print(orca_cmd.quote(argv))
    if not shutil.which(entry["bin"]):
        print(f"factory-pipeline: `{entry['bin']}` is not on PATH here: the {agent} task lead may be unavailable",
              file=sys.stderr)


def lead_prompt(plan, task, spec, info, impl, reviewer, where, report_to=None):
    """The task-lead spec: the task spec plus the rules of the second level (references/parallel-work.md)."""
    me = orca_cmd.quote(["python3", "-B", os.path.abspath(__file__)])
    d = f"{me} dispatch {orca_cmd.quote([os.path.abspath(plan['_path'])])} --task {task['id']}"
    rules = [
        "0. Orca: you are not a worker of the run lead (Orca allows no nested workers). Create your OWN Run "
        f"(`orca orchestration run-create --objective \"task {task['id']}\"`); your sub-sessions, review and QA are workers of "
        "that Run (the dispatch commands below print `orca orchestration worker-start`). Without Orca: --runner agent.",
        "1. Plan the task and split it into subtasks with disjoint paths inside owned_paths. Subtasks with disjoint paths "
        "run in parallel; the others run in order (deps). Each subtask names its implementer (claude or codex).",
        f"2. Write subplan.json and validate it: `{me} subplan validate <subplan.json>` must print OK before "
        "any dispatch (format: docs/schemas/pipeline-subplan.schema.json; "
        f"`plan` is {os.path.abspath(plan['_path'])}, `task` is {task['id']}).",
        f"3. Per subtask start ONE fresh Claude or Codex session in {where}: `{d} --phase implement --paths <subtask paths> "
        "[--agent claude|codex] --runner orca`. Never reuse a session for another subtask. Sub-sessions edit only their "
        "subtask paths and do NOT commit (one shared index).",
        "4. When a sub-session reports, review its diff (only its subtask paths changed, its checks ran with counts), "
        "then commit that subtask yourself with explicit paths (`git add -- <paths>`, Conventional Commits; never "
        "`git add -A`).",
        "5. With every subtask committed, HEAD is the candidate. Start a fresh cross-model review session "
        f"`{d} --phase review --sha <HEAD> --runner orca` (Codex reviews Claude's work, Claude reviews Codex's: registry "
        f"pipeline.review_pairing, here {reviewer} for {impl}; subtasks written by the other model get their own review "
        "with `--agent <its pair>`; the same model only as the SAME_MODEL fallback when the pair is unavailable, named in "
        f"the report) and a QA session `{d} --phase qa --sha <HEAD> --runner orca`, both in {where}. Keep HEAD at the "
        "candidate while they run.",
        "6. A FAIL goes to a fresh fix session (`--phase implement --paths <paths of the finding>`); commit the fix, then "
        "run review and QA again on the new HEAD.",
        "7. Release every session as soon as it reports (`orca orchestration worker-release --dispatch <id>`; stop "
        "background Agent workers).",
        f"8. Report to the run lead: branch {spec['branch']}, HEAD SHA, each subtask with its commit, the "
        "review and QA verdicts (state, SHA, model), each check with exact counts (or NOT_RUN with command and reason), "
        "limitations and out-of-scope findings. With Orca: `orca orchestration send --to "
        f"run:{report_to or '<run lead run id>'} --type status --subject \"task done: {task['id']}\" --body <that report>`; "
        "record the review and QA verdicts with `factory-pipeline.py verdict` (the run lead follows `status`).",
        "9. Never push, merge, tag or remove the worktree: the run lead integrates and removes the worktree after review "
        "PASS and integration.",
    ]
    return (f"Task lead for task {task['id']} of plan {plan['id']} ({plan['title']}), references/parallel-work.md. You own "
            f"this task and {where}; the run lead owns the plan, integration and cleanup.\n"
            + json.dumps(spec, indent=2) + "\nRules:\n" + "\n".join(rules)
            + (f"\nNo worktree: {info['reason']}. Work in {info['path']} on branch {spec['branch']}; never create a "
               "worktree. The previous task of this repo must have its QA verdict before you start. Subtasks run one after "
               "another (never two sessions editing or importing the project at once); review and QA also run in this "
               "checkout; a Unity test run is an exclusive resource (one at a time)."
               if not info["worktrees"] else ""))


def qa_body(sha, tasks, at_head=None):
    return ((at_head or f"Candidate SHA: {sha}. First check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT.")
            + "\nRead-only unless a check writes its own build output. Check every acceptance criterion below against the\n"
            "tree, run the tasks' checks (run-checks.py fast tier for registry repos), regressions, edge and failure\n"
            "cases. A Unity test run waits for the `unity-test` resource from the lead; never start a second Editor.\n"
            "Fill templates/pipeline/qa-report.md and end with `VERDICT: PASS|FAIL|NOT_RUN|BLOCKED`.\n"
            + "\n".join(f"- [{t['id']}] {c}" for t in tasks for c in t.get("acceptance", []))
            + "\nChecks:\n" + "\n".join(f"- [{t['id']}] {c}" for t in tasks for c in t.get("checks", [])))


def cmd_dispatch(a, reg):
    pipe = settings(reg)
    plan = read_plan(a.plan)
    plan["_path"] = a.plan
    v = validate(plan, reg)
    if v["errors"]:
        die("plan is invalid; run `validate` first: " + v["errors"][0], 1)
    if a.paths and a.phase != "implement":
        die("--paths (the subtask's paths) goes with --phase implement")
    if a.report_to and a.phase != "lead":
        die("--report-to (the run lead's Orca run id) goes with --phase lead")
    if a.phase == "qa" and a.task.startswith("integration:"):
        key = a.task.split(":", 1)[1]
        tasks = [t for t in plan["tasks"] if t["repo"] == key]
        if not tasks:
            die(f"no task of the plan is in repo {key}")
        info = repo_info(plan, reg, key)
        if not a.sha:
            die("qa needs --sha <candidate commit>")
        impls = {t.get("implementer") or pipe["default_implementer"] for t in tasks}
        agent = a.agent or (pipe["review_pairing"].get(next(iter(impls))) if len(impls) == 1 else pipe["default_implementer"])
        place = orca_cmd.placement(reg, info["registry"], info["path"], a.sha, f"{plan['topic']}-qa")
        prompt = (f"QA worker for plan {plan['id']} ({plan['title']}), repo {key}, branch {plan['topic']}, integrated tree.\n"
                  + qa_body(a.sha, tasks)
                  + (f"\nNo worktree: {info['reason']}. Work in {info['path']} on {plan['topic']}." if not info["worktrees"] else ""))
        emit(a, reg, agent, prompt, place, f"qa {plan['id']} {key}")
        return 0
    task = find_task(plan, a.task)
    info = repo_info(plan, reg, task["repo"])
    impl = task.get("implementer") or pipe["default_implementer"]
    branch = task_branch(plan, info, task)
    spec = {"plan": plan["id"], "task": task["id"], "repo": task["repo"], "objective": task["objective"],
            "owned_paths": task["paths"], "exclusions": task.get("exclusions", []), "deps": task.get("deps", []),
            "checks": task.get("checks", []), "acceptance": task["acceptance"], "branch": branch,
            "base": info["base_sha"] or info["base"]}
    if a.phase in ("lead", "implement") and not info["worktrees"]:
        prev = serial_predecessor(plan, reg, task)
        if prev and (fstate.read_json(verdict_file(plan, prev, "qa")) or {}).get("state") != "PASS":
            print(f"factory-pipeline: {task['repo']} takes one task at a time: task {prev} has no QA PASS yet; "
                  f"start {task['id']} after it", file=sys.stderr)
    if a.phase == "lead":
        reviewer = task.get("reviewer") or pipe["review_pairing"].get(impl)
        if not info["worktrees"]:
            place = orca_cmd.placement(reg, info["registry"], info["path"], spec["base"], branch)
            where = f"the main checkout {info['path']}"
        else:
            # the task worktree is created here, from the base on the task branch; a later lead resumes in it
            home = worktree_for(info["path"], branch)[0]
            place = ({"worktree": f"path:{home}", "new": False, "reason": "task worktree exists: resume in it"} if home
                     else orca_cmd.placement(reg, info["registry"], info["path"], spec["base"], branch))
            where = "this task worktree"
        prompt = lead_prompt(plan, task, spec, info, impl, reviewer, where, a.report_to)
        if a.runner == "orca":  # Orca has no nested workers: the task lead is a handoff with its own Run, not a worker
            emit_lead_handoff(reg, a.agent or impl, prompt, place, branch)
        else:
            emit(a, reg, a.agent or impl, prompt, place, f"lead {plan['id']}/{task['id']}")
        return 0
    if a.phase != "implement" and not a.sha:
        die(f"{a.phase} needs --sha <candidate commit>")
    if a.paths:
        outside = [p for p in a.paths if not inside_owned(p, task["paths"])]
        if outside:
            die(f"--paths {', '.join(outside)} outside the owned paths of task {task['id']}: {', '.join(task['paths'])}")
        spec["subtask_paths"] = a.paths
    elif a.phase == "implement" and a.agent and a.agent != impl:
        die(f"task {task['id']} is planned for {impl}; set `implementer: {a.agent}` in the plan (the reviewer pairing "
            "follows it) instead of --agent (a subtask session with --paths may name its own model)")
    # implement, review and per-task QA join the task lead's worktree (a no-worktree repo: its main checkout)
    home = task_worktree(plan, info, task, branch) if info["worktrees"] else None
    joined = {"worktree": f"path:{home}", "new": False, "reason": "the task lead's worktree"} if home else None
    if a.phase == "implement":
        agent = a.agent or impl
        place = joined or orca_cmd.placement(reg, info["registry"], info["path"], spec["base"], branch)
        if home or a.paths:
            prompt = (f"Implementation sub-session started by the task lead of task {task['id']} (references/parallel-work.md). "
                      f"Work in {home or info['path']} on branch {branch}: never switch branches or create a worktree. Edit "
                      f"only {'the subtask_paths' if a.paths else 'the owned paths'}. Do NOT commit, stage or stash: the "
                      "worktree has one shared index and the task lead commits. Run the checks; report to the task lead: "
                      "changed paths, each check with exact counts (or NOT_RUN with the command and reason), limitations and "
                      "out-of-scope findings. Never merge or push.\n"
                      + json.dumps(spec, indent=2)
                      + (f"\nNo worktree: {info['reason']}." if not info["worktrees"] else ""))
        else:
            prompt = ("Implementation worker (references/parallel-work.md section 3). Write only the owned paths; commit explicit "
                      "paths on the task branch; run the checks; report outcome, worktree, branch, base and HEAD SHA, changed "
                      "paths, each check with counts, limitations, and out-of-scope findings. Never merge or push.\n"
                      + json.dumps(spec, indent=2)
                      + f"\nNo worktree: {info['reason']}. Work in {info['path']} on branch {branch}; the previous task of this "
                        "repo must have its QA verdict before you start.")
        emit(a, reg, agent, prompt, place, f"implement {plan['id']}/{task['id']}")
        return 0
    at_head = (f"Candidate SHA: {a.sha}. You share the task worktree {home} with the task lead, who keeps HEAD at the "
               "candidate: first check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT and stop. Never check "
               "out, stage, commit or stash." if home else None)
    agent = a.agent or task.get("reviewer") or pipe["review_pairing"].get(impl)
    place = joined or {"worktree": f"path:{info['path']}", "new": False, "reason": info["reason"]}
    if a.phase == "qa":  # per-task QA: in the task worktree, or in the main checkout of a no-worktree repo
        prompt = (f"QA worker for plan {plan['id']} ({plan['title']}), repo {task['repo']}, branch {branch}, task {task['id']}.\n"
                  + qa_body(a.sha, [task], at_head)
                  + (f"\nNo worktree: {info['reason']}. Work in {info['path']} on {branch}." if not info["worktrees"] else ""))
        emit(a, reg, agent, prompt, place, f"qa {plan['id']}/{task['id']}")
        return 0
    if agent == impl:
        print(f"factory-pipeline: reviewer {agent} is the implementer's model: the verdict counts as SAME_MODEL", file=sys.stderr)
    base = info["base_sha"] or info["base"]
    prompt = (f"Review worker ({agent}) for code written by {impl}. Read-only: edit nothing, commit nothing.\n"
              + (at_head + "\n" if at_head else f"Candidate SHA: {a.sha}. ")
              + f"Review the whole diff `git diff {base}...{a.sha}` (not only the owned paths)"
              " against the spec: scope isolation (any change outside the owned paths is a finding), correctness, safety rules, the routed"
              " lead skill's review checklist, tests for each behaviour change, conventions.\n"
              + json.dumps(spec, indent=2)
              + "\nReport findings as `path:line severity problem fix`, then `VERDICT: PASS|FAIL`."
              + (f"\nNo worktree: {info['reason']}. Read the commits from {info['path']}; do not check out anything." if not info["worktrees"] else ""))
    emit(a, reg, agent, prompt, place, f"review {plan['id']}/{task['id']}")
    return 0


# ---------------------------------------------------------------- verdicts

def verdict_dir(plan):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in plan["id"])
    return os.path.join(fstate.persistent(), "pipeline", safe)


def verdict_file(plan, task, phase):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in task)
    return os.path.join(verdict_dir(plan), f"{safe}__{phase}.json")


def scope_fingerprint(plan, reg, task_id):
    """A task's fingerprint, or for integration:<repo> the fingerprints of every task of that repo."""
    pipe = settings(reg)
    if task_id.startswith("integration:"):
        key = task_id.split(":", 1)[1]
        parts = sorted(task_fingerprint(t, pipe) for t in plan.get("tasks", []) if t.get("repo") == key)
        return hashlib.sha256("".join(parts).encode()).hexdigest()[:16]
    return task_fingerprint(find_task(plan, task_id), pipe)


def read_verdict(plan, reg, task_id, phase, blockers):
    """The recorded verdict, or None with a blocker when it is missing or was recorded for another version of the plan."""
    rec = fstate.read_json(verdict_file(plan, task_id, phase))
    if not isinstance(rec, dict) or not rec.get("sha"):
        blockers.append(f"{task_id}: no {phase} verdict")
        return None
    if rec.get("fingerprint") != scope_fingerprint(plan, reg, task_id):
        blockers.append(f"{task_id}: {phase} verdict is STALE - the plan's objective, paths, acceptance, checks or agents changed since")
        return None
    return rec


def cmd_verdict(a, reg):
    pipe = settings(reg)
    plan = read_plan(a.plan)
    if a.state not in pipe["verdict_states"]:
        die(f"--state must be one of {', '.join(pipe['verdict_states'])}")
    if a.by not in pipe["agents"]:
        die(f"--by must be one of {', '.join(pipe['agents'])}")
    plan["_path"] = a.plan
    if not a.task.startswith("integration:"):
        task = find_task(plan, a.task)
        key = task["repo"]
    elif a.phase == "review":
        die("review verdicts are per task: --task <id>")
    else:
        key = a.task.split(":", 1)[1]
        if not any(t.get("repo") == key for t in plan.get("tasks", [])):
            die(f"no task of the plan is in repo {key}")
    if len(a.sha) < 7 or any(c not in "0123456789abcdef" for c in a.sha.lower()):
        die("--sha must be a commit id")
    full, rc = git(repo_info(plan, reg, key)["path"] or ".", "rev-parse", "--verify", "--quiet", a.sha + "^{commit}")
    if rc != 0 or not full:
        die(f"--sha {a.sha} is not a commit of repo {key}")
    rec = {"plan": plan.get("id"), "task": a.task, "phase": a.phase, "sha": full, "by": a.by, "state": a.state,
           "fingerprint": scope_fingerprint(plan, reg, a.task),
           "report": os.path.abspath(a.report) if a.report else None,
           "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    path = verdict_file(plan, a.task, a.phase)
    fstate.write_json(path, rec, indent=2)
    print(f"recorded {a.phase} {a.state} for {a.task} at {a.sha[:10]} by {a.by}: {path}")
    return 0


# ---------------------------------------------------------------- gate

def worktree_for(path, branch):
    out, rc = git(path, "worktree", "list", "--porcelain")
    if rc != 0 or out is None:
        return None, []
    trees, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                trees.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[9:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "", 1)
    home = next((t["path"] for t in trees if t.get("branch") == branch), None)
    return home, trees[1:]


def gate(plan, reg, allow_same_model=False, run_checks=True):
    pipe = settings(reg)
    v = validate(plan, reg)
    blockers, notes, commands, unverified = list(v["errors"]), [], [], []
    repos = sorted({t["repo"] for t in plan.get("tasks", []) if t.get("repo")})
    heads = {}
    for key in repos:
        info = repo_info(plan, reg, key)
        if not info["path"] or not os.path.isdir(info["path"]):
            blockers.append(f"{key}: checkout {info['path']} missing")
            continue
        head, rc = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{plan['topic']}")
        if rc != 0 or not head:
            blockers.append(f"{key}: integration branch {plan['topic']} does not exist")
            continue
        heads[key] = head
        home, extra = worktree_for(info["path"], plan["topic"])
        if not info["worktrees"]:
            mine = [t["path"] for t in extra if str(t.get("branch", "")).startswith(plan["topic"])]
            if mine:
                blockers.append(f"{key}: no-worktree repo has pipeline worktrees {', '.join(mine)} ({info['reason']})")
        if not home:
            blockers.append(f"{key}: {plan['topic']} is not checked out in any worktree; the integrated tree cannot be checked")
        else:
            dirty, rc = git(home, "status", "--porcelain", "--untracked-files=normal")
            if rc != 0 or dirty is None:
                blockers.append(f"{key}: `git status` failed in {home}")
            elif dirty:
                blockers.append(f"{key}: integration tree {home} has uncommitted changes")
            if not run_checks and info["registry"]:
                unverified.append(key)
            if run_checks and info["registry"]:
                paths = [p for t in plan["tasks"] if t["repo"] == key for p in t["paths"]]
                r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "run-checks.py"), "--repo", info["registry"],
                                    "--repo-path", home, "--status", "--json", "--paths", *paths],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
                try:
                    rows = json.loads(r.stdout).get("checks", [])
                except ValueError:
                    rows = None
                if rows is None:
                    blockers.append(f"{key}: run-checks --status failed: {(r.stderr or r.stdout).strip()[:200]}")
                else:
                    bad = [f"{x['check']} {x['state']}" for x in rows if x["tier"] == "fast" and x["state"] != "PASS"]
                    if bad:
                        blockers.append(f"{key}: fast checks not PASS on the integrated tree: {', '.join(bad)}")
                    open_ = [f"{x['check']} {x['state']}" for x in rows if x["tier"] != "fast" and x["state"] != "PASS"]
                    if open_:
                        notes.append(f"{key}: open (report them): {', '.join(open_)}")
        base = info["base_sha"] or info["base"]
        mb, rc = git(info["path"], "merge-base", base, head) if base else (None, 1)
        if rc != 0 or not mb:
            blockers.append(f"{key}: base {base} not found; cannot prove every change belongs to a task")
        else:
            changed, rc = git(info["path"], "diff", "--name-only", mb, head)
            owned = [norm_path(p).rstrip("/") for t in plan["tasks"] if t["repo"] == key for p in t["paths"]]
            stray = [f for f in (changed or "").splitlines()
                     if not any(o in ("", ".") or norm_path(f) == o or norm_path(f).startswith(o + "/") for o in owned)]
            if rc != 0 or stray:
                blockers.append(f"{key}: changes outside every task's owned paths: {', '.join(stray[:5]) or 'git diff failed'}")
        qa = read_verdict(plan, reg, f"integration:{key}", "qa", blockers)
        if not qa:
            pass
        elif qa.get("state") != "PASS":
            blockers.append(f"{key}: QA {qa.get('state')} at {qa.get('sha', '')[:10]}")
        elif head != qa.get("sha"):
            blockers.append(f"{key}: QA is STALE (ran on {qa.get('sha', '')[:10]}, integration HEAD is {head[:10]})")
    for t in plan.get("tasks", []):
        key = t.get("repo")
        if key not in heads:
            continue
        info = repo_info(plan, reg, key)
        impl = t.get("implementer") or pipe["default_implementer"]
        want = t.get("reviewer") or pipe["review_pairing"].get(impl)
        rv = read_verdict(plan, reg, t["id"], "review", blockers)
        if not rv:
            continue
        if rv.get("state") != "PASS":
            blockers.append(f"{t['id']}: review {rv.get('state')} at {rv.get('sha', '')[:10]}")
            continue
        if rv.get("by") != want:
            if rv.get("by") == impl and allow_same_model:
                notes.append(f"{t['id']}: review SAME_MODEL ({impl}) accepted by --allow-same-model")
            else:
                blockers.append(f"{t['id']}: reviewed by {rv.get('by')}, cross-model review needs {want}"
                                + (" (or --allow-same-model when it is unavailable)" if rv.get("by") == impl else ""))
                continue
        if not info["worktrees"] and sum(1 for u in plan["tasks"] if u["repo"] == key) > 1:
            tq = read_verdict(plan, reg, t["id"], "qa", blockers)  # missing: "<id>: no qa verdict"
            if tq and tq.get("state") != "PASS":
                blockers.append(f"{t['id']}: QA {tq.get('state')} at {tq['sha'][:10]}")
            elif tq:
                _, rc = git(info["path"], "merge-base", "--is-ancestor", rv["sha"], tq["sha"])
                moved, rc2 = git(info["path"], "diff", "--name-only", tq["sha"], heads[key], "--", *t["paths"])
                if rc != 0:
                    blockers.append(f"{t['id']}: QA ran on {tq['sha'][:10]}, which does not contain the reviewed commit {rv['sha'][:10]}")
                elif rc2 != 0 or moved:
                    blockers.append(f"{t['id']}: QA is STALE - owned paths changed after {tq['sha'][:10]}")
        _, rc = git(info["path"], "merge-base", "--is-ancestor", rv["sha"], heads[key])
        if rc != 0:
            blockers.append(f"{t['id']}: reviewed commit {rv['sha'][:10]} is not integrated into {plan['topic']}")
            continue
        changed, rc = git(info["path"], "diff", "--name-only", rv["sha"], heads[key], "--", *t["paths"])
        if rc != 0 or changed:
            blockers.append(f"{t['id']}: review is STALE - owned paths changed after {rv['sha'][:10]}: "
                            + ", ".join((changed or "?").splitlines()[:5]))
    if unverified and not blockers:
        notes.append("fast checks were not graded (--no-run-checks) for " + ", ".join(unverified) + ": no delivery")
    ready = not blockers and not unverified
    if ready and plan.get("deliver") == "pr":
        for key in repos:
            info = repo_info(plan, reg, key)
            commands.append(orca_cmd.quote(["git", "-C", info["path"], "push", "-u", "origin", plan["topic"]]))
            commands.append(orca_cmd.quote(["gh", "pr", "create", "--base", info["base"] or "main", "--head", plan["topic"],
                                            "--title", plan["title"], "--body-file", "<final report.md>"])
                            + f"   # run in {info['path']}")
    state = "READY_FOR_PR" if ready else ("UNVERIFIED" if not blockers else "NOT_READY")
    return {"state": state, "deliver": plan.get("deliver", "none"),
            "blockers": blockers, "notes": notes, "heads": heads, "commands": commands}


def cmd_gate(a, reg):
    plan = read_plan(a.plan)
    plan["_path"] = a.plan
    out = gate(plan, reg, a.allow_same_model, not a.no_run_checks)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Gate: {out['state']}  (deliver: {out['deliver']})")
        for b in out["blockers"]:
            print("  BLOCKER " + b)
        for n in out["notes"]:
            print("  NOTE    " + n)
        if out["commands"]:
            print("Delivery (only with the user's `deliver: pr` authorization in this task; merging stays with the user):")
            for c in out["commands"]:
                print("  " + c)
        elif out["state"] == "READY_FOR_PR" and out["deliver"] != "pr":
            print("deliver is not `pr`: stop here and report; push and PR only when the user asks.")
    return 0 if out["state"] == "READY_FOR_PR" else 1


def cleanup(plan, reg):
    """Worktrees and task branches the run left (names <topic>-*), with the commands that remove them."""
    left, commands, kept = [], [], []
    for key in sorted({t["repo"] for t in plan.get("tasks", []) if t.get("repo")}):
        info = repo_info(plan, reg, key)
        if not info["path"] or not os.path.isdir(info["path"]):
            continue
        topic = plan["topic"]
        integrated = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{topic}")[0]
        _, trees = worktree_for(info["path"], topic)
        for wt in trees:
            if not str(wt.get("branch", "")).startswith(topic + "-"):
                continue
            dirty, rc = git(wt["path"], "status", "--porcelain")
            if rc != 0 or dirty:
                kept.append(f"{key}: worktree {wt['path']} has uncommitted changes - not removed, report it")
                left.append(wt["path"])
                continue
            left.append(wt["path"])
            commands.append(orca_cmd.quote(["git", "-C", info["path"], "worktree", "remove", wt["path"]]))
        refs, _ = git(info["path"], "for-each-ref", "--format=%(refname:short)", f"refs/heads/{topic}-*")
        for br in (refs or "").splitlines():
            _, rc = git(info["path"], "merge-base", "--is-ancestor", br, integrated) if integrated else (None, 1)
            if rc == 0:
                left.append(br)
                commands.append(orca_cmd.quote(["git", "-C", info["path"], "branch", "-d", br]))
            else:
                left.append(br)
                kept.append(f"{key}: branch {br} is not in {topic} - not deleted (integrate it or name it in the report)")
    return {"state": "CLEAN" if not left else "LEFTOVER", "left": left, "commands": commands, "kept": kept,
            "sessions": "release every settled worker: `orca orchestration worker-list` then "
                        "`orca orchestration worker-release --dispatch <id>`; stop background Agent workers"}


def cmd_cleanup(a, reg):
    plan = read_plan(a.plan)
    plan["_path"] = a.plan
    out = cleanup(plan, reg)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Cleanup: {out['state']}")
        for c in out["commands"]:
            print("  " + c)
        for k in out["kept"]:
            print("  KEPT  " + k)
        print("Sessions: " + out["sessions"])
    return 0 if out["state"] == "CLEAN" else 1


# ---------------------------------------------------------------- status

STATUS_SCHEMA = "rpg-factory.pipeline-status/1"
PHASES = ("pending", "implementing", "candidate", "reviewed", "integrated", "qa")


def verdict_of(plan, reg, task_id, phase):
    """(record, stale): the recorded verdict for this version of the plan, or None; stale when it vouches for another."""
    rec = fstate.read_json(verdict_file(plan, task_id, phase))
    if not isinstance(rec, dict) or not rec.get("sha"):
        return None, False
    if rec.get("fingerprint") != scope_fingerprint(plan, reg, task_id):
        return None, True
    return rec, False


def is_ancestor(path, a, b):
    return bool(a and b) and git(path, "merge-base", "--is-ancestor", a, b)[1] == 0


def changed_since(path, sha, head, paths):
    out, rc = git(path, "diff", "--name-only", sha, head, "--", *paths)
    return rc != 0 or bool(out)


def task_status(plan, reg, task, n_in_repo):
    """Phase a task reached, derived from git and the recorded verdicts (no context of the session that ran it)."""
    info = repo_info(plan, reg, task["repo"])
    path, topic, paths = info["path"], plan["topic"], task["paths"]
    branch = task_branch(plan, info, task)
    base = info["base_sha"] or info["base"]
    row = {"id": task["id"], "repo": task["repo"], "branch": branch, "worktree": None, "sha": None,
           "phase": "pending", "review": None, "qa": None, "notes": []}
    if not path or not os.path.isdir(path):
        row["notes"].append(f"checkout {path} missing")
        return row, info
    head = git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] or None
    topic_head = git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{topic}")[0] or None
    row["worktree"] = worktree_for(path, branch)[0]
    rv, rv_stale = verdict_of(plan, reg, task["id"], "review")
    per_task_qa = not info["worktrees"] and n_in_repo > 1
    qa_id = task["id"] if per_task_qa else f"integration:{task['repo']}"
    qa, qa_stale = verdict_of(plan, reg, qa_id, "qa")
    for kind, rec, stale in (("review", rv, rv_stale), ("qa", qa, qa_stale)):
        if rec:
            row[kind] = {"state": rec.get("state"), "sha": rec["sha"], "by": rec.get("by"), "task": rec.get("task")}
        elif stale:
            row["notes"].append(f"{kind} verdict is STALE: the plan's task changed since it was recorded")
    if head:
        row["sha"] = head
        # only commits that touch the task's own paths: a task branch cut from the integration branch, and the
        # shared integration branch of a no-worktree repo, also carry other tasks' commits
        ahead = git(path, "rev-list", "--count", f"{base}..{head}", "--", *paths)[0] if base else None
        if ahead is None or not str(ahead).isdigit():
            row["notes"].append(f"base {base} not found")
            ahead = "0"
        if int(ahead) > 0:
            row["phase"] = "candidate"
        elif info["worktrees"] or (row["worktree"] and git(row["worktree"], "status", "--porcelain", "--", *paths)[0]):
            row["phase"] = "implementing"
    elif topic_head and base and git(path, "rev-list", "--count", f"{base}..{topic_head}", "--", *paths)[0] not in (None, "", "0"):
        # task branch removed after integration: the reviewed commit, or the integration HEAD to review
        ok = rv and rv.get("state") == "PASS" and is_ancestor(path, rv["sha"], topic_head)
        row["sha"] = rv["sha"] if ok else topic_head
        row["phase"] = "candidate"
    if row["phase"] != "candidate" or not rv:
        return row, info
    if row["sha"] != rv["sha"] and (not is_ancestor(path, rv["sha"], row["sha"]) or changed_since(path, rv["sha"], row["sha"], paths)):
        row["notes"].append(f"review at {rv['sha'][:10]} is STALE: owned paths changed since")
        return row, info
    row["phase"] = "reviewed"
    if rv.get("state") != "PASS" or not is_ancestor(path, rv["sha"], topic_head):
        return row, info
    row["phase"] = "integrated"
    if qa and qa.get("state") == "PASS" and is_ancestor(path, rv["sha"], qa["sha"]):
        row["phase"] = "qa"
        if topic_head != qa["sha"] and changed_since(path, qa["sha"], topic_head, paths):
            row["phase"] = "integrated"
            row["notes"].append(f"QA at {qa['sha'][:10]} is STALE: owned paths changed on {topic} since")
    return row, info


def status(plan, reg):
    v = validate(plan, reg)
    me = orca_cmd.quote(["python3", "-B", os.path.abspath(__file__)])
    pf = orca_cmd.quote([os.path.abspath(plan["_path"])])
    tasks = plan.get("tasks", [])
    if v["errors"]:
        return {"schema": STATUS_SCHEMA, "plan": plan.get("id"), "topic": plan.get("topic"), "valid": False,
                "errors": v["errors"], "waves": v["waves"], "tasks": [], "ready_wave": None, "ready": [],
                "next": [f"{me} validate {pf}"]}
    count = {}
    for t in tasks:
        count[t["repo"]] = count.get(t["repo"], 0) + 1
    rows, infos = {}, {}
    for t in tasks:
        rows[t["id"]], infos[t["id"]] = task_status(plan, reg, t, count[t["repo"]])
    wave_of = {tid: n for n, w in enumerate(v["waves"], 1) for tid in w}
    done = ("integrated", "qa")
    ready = []
    for t in tasks:
        row, info, tid = rows[t["id"]], infos[t["id"]], t["id"]
        row["wave"] = wave_of.get(tid)
        row["next"] = None
        dispatch = f"{me} dispatch {pf} --task {tid}"
        if row["phase"] == "pending":
            waiting = [d for d in t.get("deps", []) if rows.get(d, {}).get("phase") not in done]
            prev = serial_predecessor(plan, reg, t) if not info["worktrees"] else None
            if prev and rows[prev]["phase"] != "qa":
                waiting.append(prev)
            if waiting:
                row["notes"].append("waits for " + ", ".join(waiting))
            else:
                ready.append(tid)  # a worktree repo starts the task lead, which creates the task worktree
                row["next"] = f"{dispatch} --phase {'lead' if info['worktrees'] else 'implement'} --runner orca"
        elif row["phase"] == "implementing":
            row["notes"].append(f"implementation worker on {row['branch']}"
                                + (f" in {row['worktree']}" if row["worktree"] else "") + ": wait for its report")
        elif row["phase"] == "candidate":
            row["next"] = f"{dispatch} --phase review --sha {row['sha']} --runner orca"
        elif row["phase"] == "reviewed" and row["review"]["state"] != "PASS":
            row["notes"].append(f"review {row['review']['state']} at {row['review']['sha'][:10]}: fix the findings on "
                                f"{row['branch']}, then review the new HEAD")
            fix = "lead" if info["worktrees"] and not row["worktree"] else "implement"
            row["next"] = f"{dispatch} --phase {fix} --runner orca"
        elif row["phase"] == "reviewed":
            home = worktree_for(info["path"], plan["topic"])[0]
            if home:
                row["next"] = orca_cmd.quote(["git", "-C", home, "merge", "--no-ff", row["branch"]])
            elif git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{plan['topic']}")[0]:
                row["notes"].append(f"integration branch {plan['topic']} exists but is not checked out: check it out "
                                    f"where the lead integrates, then merge {row['branch']}")
            else:
                row["notes"].append(f"integration branch {plan['topic']} is not checked out: create it from the base, "
                                    f"check it out where the lead integrates, then merge {row['branch']}")
                row["next"] = orca_cmd.quote(["git", "-C", info["path"], "branch", plan["topic"],
                                              info["base_sha"] or info["base"] or "main"])
        elif row["phase"] == "integrated":
            topic_head = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{plan['topic']}")[0]
            if not info["worktrees"] and count[t["repo"]] > 1:
                row["next"] = f"{dispatch} --phase qa --sha {topic_head} --runner orca"
            else:
                others = [u["id"] for u in tasks if u["repo"] == t["repo"] and rows[u["id"]]["phase"] not in done]
                if others:
                    row["notes"].append("QA runs once all tasks of the repo are integrated: waits for " + ", ".join(others))
                else:
                    row["next"] = f"{me} dispatch {pf} --task integration:{t['repo']} --phase qa --sha {topic_head} --runner orca"
    # the gate needs the repo's integration QA PASS at the integration HEAD (also after per-task QA of a no-worktree
    # repo): until then the repo's tasks stay integrated and the next command is that QA
    for key in sorted(count):
        mine = [t["id"] for t in tasks if t["repo"] == key]
        if not all(rows[tid]["phase"] == "qa" for tid in mine):
            continue
        info = infos[mine[0]]
        topic_head = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{plan['topic']}")[0]
        iq, iq_stale = verdict_of(plan, reg, f"integration:{key}", "qa")
        if iq and iq.get("state") == "PASS" and iq["sha"] == topic_head:
            continue
        if iq and iq.get("state") != "PASS":
            why = f"integration QA {iq.get('state')} at {iq['sha'][:10]}"
        elif iq:
            why = f"integration QA at {iq['sha'][:10]} is STALE: the integration HEAD is {(topic_head or '?')[:10]}"
        else:
            why = "no integration QA" + (" (its verdict is STALE: the plan changed)" if iq_stale else "")
        for tid in mine:
            rows[tid]["phase"] = "integrated"
            rows[tid]["notes"].append(why + f" for {key}: the gate needs it at the integration HEAD")
            rows[tid]["next"] = (f"{me} dispatch {pf} --task integration:{key} --phase qa --sha {topic_head} "
                                 "--runner orca")
    open_waves = [n for n, w in enumerate(v["waves"], 1) if any(rows[tid]["phase"] not in done for tid in w)]
    nxt = [f"{me} gate {pf}"] if tasks and all(r["phase"] == "qa" for r in rows.values()) else []
    out_rows = []
    for t in tasks:
        r = rows[t["id"]]
        out_rows.append({k: r[k] for k in ("id", "repo", "wave", "phase", "branch", "worktree", "sha", "review", "qa",
                                           "next", "notes")})
    return {"schema": STATUS_SCHEMA, "plan": plan.get("id"), "topic": plan.get("topic"), "valid": True, "errors": [],
            "waves": v["waves"], "tasks": out_rows, "ready_wave": open_waves[0] if open_waves else None,
            "ready": ready, "next": nxt}


def cmd_status(a, reg):
    plan = read_plan(a.plan)
    plan["_path"] = a.plan
    out = status(plan, reg)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0 if out["valid"] else 1
    print(f"Pipeline {out['plan']} on {out['topic']}" + ("" if out["valid"] else "  INVALID"))
    for e in out["errors"]:
        print("  ERROR " + e)
    for r in out["tasks"]:
        verdict = "".join(f"  {k} {r[k]['state']}@{r[k]['sha'][:10]}" for k in ("review", "qa") if r[k])
        print(f"  [{r['id']}] wave {r['wave']}  {r['phase']}" + (f"  {r['sha'][:10]}" if r["sha"] else "") + verdict)
        for n in r["notes"]:
            print("      note: " + n)
        if r["next"]:
            print("      next: " + r["next"])
    if out["ready_wave"]:
        print(f"Ready wave: {out['ready_wave']}" + (f"  (dispatch: {', '.join(out['ready'])})" if out["ready"] else ""))
    elif out["valid"] and out["tasks"]:
        print("Every wave is integrated.")
    for c in out["next"]:
        print("Next: " + c)
    return 0 if out["valid"] else 1


def main():
    ap = argparse.ArgumentParser(prog="factory-pipeline.py", description=__doc__.split("\n")[0])
    ap.add_argument("--registry", default=os.path.join(ROOT, "registry.json"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tier")
    t.add_argument("--json", action="store_true")
    t.add_argument("--context-json")
    t.add_argument("--plan")
    t.add_argument("--repo")
    t.add_argument("--paths", nargs="+")
    t.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("validate")
    p.add_argument("plan")
    p.add_argument("--json", action="store_true")
    sp = sub.add_parser("subplan")
    sp.add_argument("action", choices=("validate",))
    sp.add_argument("subplan")
    sp.add_argument("--plan")
    sp.add_argument("--json", action="store_true")
    for name in ("planner", "dispatch"):
        d = sub.add_parser(name)
        if name == "dispatch":
            d.add_argument("plan")
            d.add_argument("--task", required=True)
            d.add_argument("--phase", required=True, choices=("lead", "implement", "review", "qa"))
            d.add_argument("--sha")
            d.add_argument("--paths", nargs="+")
            d.add_argument("--report-to")
        else:
            d.add_argument("--request", required=True)
        d.add_argument("--runner", choices=("orca", "agent", "print"), default="print")
        d.add_argument("--agent")
    v = sub.add_parser("verdict")
    v.add_argument("plan")
    v.add_argument("--task", required=True)
    v.add_argument("--phase", required=True, choices=("review", "qa"))
    v.add_argument("--sha", required=True)
    v.add_argument("--by", required=True)
    v.add_argument("--state", required=True)
    v.add_argument("--report")
    st = sub.add_parser("status")
    st.add_argument("plan")
    st.add_argument("--json", action="store_true")
    c = sub.add_parser("cleanup")
    c.add_argument("plan")
    c.add_argument("--json", action="store_true")
    g = sub.add_parser("gate")
    g.add_argument("plan")
    g.add_argument("--allow-same-model", action="store_true")
    g.add_argument("--no-run-checks", action="store_true")
    g.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "tier" and a.rest[:1] == ["--"]:
        a.rest = a.rest[1:]
    reg = load_registry(a.registry)
    if getattr(a, "agent", None) and a.agent not in settings(reg)["agents"]:
        die(f"--agent must be one of {', '.join(settings(reg)['agents'])}")
    return {"tier": cmd_tier, "validate": cmd_validate, "planner": cmd_planner, "dispatch": cmd_dispatch,
            "subplan": cmd_subplan, "verdict": cmd_verdict, "gate": cmd_gate, "cleanup": cmd_cleanup, "status": cmd_status}[a.cmd](a, reg)


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
