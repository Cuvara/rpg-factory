#!/usr/bin/env python3
"""Delivery pipeline for one Factory task: tier, plan validation, dispatch commands, review/QA verdicts, PR gate.

Policy: skills/delivery/references/delivery.md (generic), skills/factory-core/references/parallel-work.md (RPG specifics). Settings: registry.json `pipeline` (tiers, agents,
cross-model review pairing, exclusive resources) and `repos.<key>.worktrees`. Settings fall back to
skills/delivery/pipeline-defaults.json with `--registry none`, RPG_FACTORY_PIPELINE_REGISTRY=none or a missing registry
file (the installed plugin always ships registry.json, so there the flag or the variable selects them); every command the
script prints for a next session then carries `--registry none`. A plan may set `no_worktree_markers`
and `known_failing` ([{check, reason}]: checks that already fail at the base; specs name them, QA reports FAIL_AT_BASE). Plan format: docs/schemas/pipeline-plan.schema.json.

  tier [--json] [--context-json FILE] [-- <factory-context.sh args>]
        XS | S | M | L from the routing snapshot (repos, modules, files, contracts, generated paths). XS (registry
        pipeline.tiers.XS): every file prose (*.md, changelog.d/, skills/ directories), within max_files and
        max_changed_lines; `above XS:` names why not.
  tier --plan <plan.json> --repo KEY --paths FILE... [--json]
        the same for a plan repo key; a plan.repos entry the registry does not know (the plugin repo) is tiered
        from the paths alone: modules are skills/<name>, scripts/lib or the top-level directory, no contracts. With a
        checkout, the changed lines are `git diff --numstat HEAD` of the paths plus the lines of untracked ones.
  agents <plan.json> [--down AGENT [--reason TEXT] | --up AGENT] [--json]
        per-run MODEL_UNAVAILABLE marks in <state dir>/pipeline/<plan id>/agents.json, then the availability table.
  validate <plan.json> [--json]
        disjoint path ownership, dependency cycles, waves, the no-worktree rule (Unity projects: tasks one
        after another in the main checkout, never two in one wave), cross-model review pairing, and shared
        exclusive resources (one Unity test run at a time). Exit 1 on an error. WARN (no error) when a task's
        checks hold a full tests/run-all.sh or its acceptance requires one: full runs belong to integration QA.
        Model policy (registry
        pipeline.models, lib/model_policy.py; references/delivery.md section 10 "Model choice"): a task `grade` other
        than light|standard|heavy, a broken policy or override file and a role it cannot resolve are errors; prints the
        model and effort of the task lead and, per task, its grade (the plan's, else derived from the tier of its owned
        paths alone: XS and S light, M standard, L or a contract or generated path heavy) and its implement, review (heavy
        work: the heavy profile) and QA sessions. Tier XS (plan or task tier): exactly one task, every owned path prose,
        at most max_files paths, else an error naming the reason; its implementer is the run lead (pipeline.lead_agent).
  subplan validate <subplan.json> [--plan PATH] [--json]
        a task lead's split of ONE plan task (docs/schemas/pipeline-subplan.schema.json; `plan` is the plan file,
        relative to the subplan, or --plan; `task` the task id): an unknown task, a subtask path outside the task's owned
        paths or inside its exclusions, overlapping paths of subtasks not ordered by deps, unknown deps or a cycle, an
        implementer that is no pipeline agent, a reviewer of the implementer's model (registry
        pipeline.review_pairing), a `placement` other than shared|child, child without a `reason` and child in a
        no-worktree repo are errors; so are absolute or `..` paths and malformed subtasks (not an object, a
        non-string id, paths or deps that are not lists of strings). Prints the waves: one subtask per wave in a
        no-worktree repo (Unity project). A subtask `grade` other than light|standard|heavy and a grade the policy cannot
        resolve for its model are errors; prints each subtask's grade (its own, else the task's) and the model and effort
        of its implement and review sessions. Exit 0 OK, 1 errors, 2 usage.
  planner --request TEXT [--runner orca|agent|print] [--orca-unavailable REASON] [--agent ID]
          [--grade light|standard|heavy] [--model ID] [--effort LEVEL]
        the planner dispatch: read-only, in the lead's checkout (no worktree), writes plan.json.
        Every Orca dispatch stores the full spec under <state dir>/pipeline/<plan id>/specs/ (planner: _planner, a reserved plan id)
        and passes a one-line prompt pointing to that absolute file, so cmd.exe cannot truncate the spec; the
        planner's prompt also ends with "Request: TEXT", every whitespace run (newlines too) collapsed to one space.
  dispatch ... [--grade light|standard|heavy] [--model ID] [--effort LEVEL]   (every phase, and planner)
        every session runs with the model and effort of its role in the model policy: planner, lead, implement (the
        subtask's grade, else the task's), review (heavy work: heavy, else review) and qa. Orca commands (worker-start,
        agent launch) end with `--model ID --effort LEVEL --json`; the print runner's header names them;
        the Agent-tool runner passes the model alias (agent_tool_alias) and says on stderr and in one prompt line that
        the Agent tool cannot set an effort. --grade runs the session with that grade's profile; --model / --effort
        replace the profile's; outside the scope (registry plus the personal override file $RPG_FACTORY_MODEL_POLICY or
        <persistent state dir>/model-policy.json) they are a usage error (exit 2) and nothing is dispatched. A broken
        policy exits 1.
  dispatch <plan.json> --task ID --phase lead [--report-to RUN_ID|run:RUN_ID] [--runner orca|agent|print]
          [--orca-unavailable REASON] [--agent ID]
        the run lead starts ONE task-lead session per task, always a registry pipeline.lead_agent (Claude) session
        whatever the task's implementer (--agent another model: warning, ignored). In a worktree repo it gets the task worktree: created here
        from the base on the task branch <topic>-<id> (a task with deps: from <topic> when that integration branch
        exists, it carries the earlier waves; status still compares against the base), or resumed when that branch is
        already checked out; in a no-worktree repo the main checkout, never a worktree. The prompt is the task spec plus the task-lead rules: its
        own Orca Run, split into subtasks with disjoint paths (`subplan validate`), one fresh session per subtask in the
        same worktree, sub-sessions do not commit, the task lead commits per subtask, cross-model review and QA sessions
        there, release each session, report a `status` message (to Orca run RUN_ID: worker_done needs a dispatch,
        which the task lead has not) with branch and HEAD; never push, merge or remove the worktree. Orca forbids
        nested workers, so --runner orca prints a handoff, not a worker-start:
        `git worktree add --no-track -b <branch> <path> <base>` for a new task worktree, followed by
        `orca worktree set` with its parent, then `orca agent launch --worktree path:<dir> --prompt ...`;
        existing worktrees use only the launch command.
        A tier XS task starts no task lead: it prints the run lead's own steps (edit on plan.topic, commit with explicit
        paths, `dispatch --phase review --sha <sha>`, the task tier command, the `tier XS: lead ran task suites` QA
        verdict, gate); `--phase implement` on it is a usage error. Its review and QA read the topic checkout.
  dispatch <plan.json> --task ID --phase lead --placement shared|child ...
        Both placements create a task worktree beside the integration checkout (or the repo checkout if absent).
  dispatch <plan.json> --task ID --phase implement [--paths P...] [--runner ...] [--agent ID]
  dispatch <plan.json> --task ID --phase review|qa --sha SHA [--runner ...] [--agent ID]
        implement records the model it started per task/subtask (<task>[@<subtask>]__implementer.model.json); review
        and QA pair against it (else the planned routing), never current availability. review records its reviewer
        and any SAME_MODEL fallback per candidate SHA: the only source `verdict` stamps a fallback from.
        --runner print is a preview that writes no implementer or reviewer record. A print dispatch (the default
        outside Orca) leaves verdict nothing to pair against or stamp a SAME_MODEL fallback from: dispatch
        with --runner orca or --runner agent for a recorded session.
  ... [--subplan FILE --subtask ID] [--placement shared|child]
        --subplan/--subtask (a valid subplan of the task) default --paths to the subtask's paths, --agent to its
        implementer (implement) or reviewer (review), and --placement to its placement. --placement child runs the
        session in an Orca child of the task worktree (`worker-start --worktree new-child --name <task branch>--<subtask
        or phase> --base-branch <task branch | --sha>`, run from the task worktree): a child implement session commits
        on its child branch, the task lead merges it into the task branch and removes the child at once. Every child
        command (stderr) and spec says: never create or remove a child while a full tests/run-all.sh runs. Child in a
        no-worktree repo is a usage error (nothing printed).
        a session started by the task lead. In a worktree repo it joins the task's EXISTING worktree (found by the task
        branch in `git worktree list`, `--worktree path:<it>`), never a new one: no such worktree is an error (exit 1;
        run `--phase lead` first). implement: a sub-session that edits only the owned paths, or the subtask's --paths
        (inside them; it may then name its model with --agent), and does not commit. review/qa need --sha, the frozen
        candidate the task lead keeps at HEAD, and are read-only; the reviewer is the implementer's pair (another
        model) unless --agent overrides it; a reviewer runs no suites. Per-task qa runs in the task worktree (a
        no-worktree repo: main checkout); its spec names ONE tier command (registry pipeline.qa_tiers), never a full
        run: `tests/run-all.sh --affected --base <review base> [--only-suites <the checks' suites>] -j 2`. A check
        is folded into it only when it is one standalone suite or run-all command and its suite is one
        `tests/run-all.sh --list-suites` prints in the task checkout (no such flag: none is; a release-only suite
        never is); other checks, compound commands included, are extra commands, each suite once. Re-QA after a QA
        FAIL that recorded --failed-suites: --base <that FAIL's candidate> plus those suites. A tier-S task (plan or
        task tier S, or only *.md, changelog.d/ and skills/ directory paths) needs no QA session: the task lead may
        run the command after the review PASS.
        A no-worktree repo: implement is always a sub-session in the main checkout that does not commit (with or
        without --paths); only the task lead commits. --paths overlapping the task's exclusions is a usage error.
  dispatch <plan.json> --task integration:<repo> --phase qa --sha SHA [--runner ...] [--agent ID]
        QA of the integrated tree, in the existing checkout of the integration branch (plan.topic, found in `git
        worktree list`); none is an error (exit 1, no worktree created). A no-worktree repo: the main checkout.
        --placement child: an Orca child of that checkout (`worker-start --worktree new-child --base-branch <SHA>`).
        --runner agent is the Claude Code Agent-tool fallback (Claude only): a session planned for codex starts a
        fresh Claude session whose prompt and report say SAME_MODEL. Orca first (references/delivery.md
        section 5): inside an Orca session (ORCA_WORKTREE_ID or ORCA_AGENT_HOOK_ENDPOINT set) whose runtime is
        reachable (`orca status --json`), the default runner is orca (elsewhere print) and planner/dispatch --runner
        agent exit 2 unless --orca-unavailable REASON is given; the reason opens the session's prompt so its report
        names it. --orca-unavailable goes with --runner agent only. The integration QA spec names
        `tests/run-all.sh --workspace-only`; after the PR opens, CI green is the full-suite gate.
  verdict <plan.json> --task ID --phase review|qa --sha SHA --by AGENT --state PASS|FAIL|NOT_RUN|BLOCKED [--report FILE] [--note TEXT] [--implementer AGENT]
          [--subtask ID [--subplan FILE]] [--fallback 'AGENT unavailable' --note TEXT] [--failed-suites LIST]
        records a review or QA verdict (<state dir>/pipeline/<plan id>/, lib/fstate.py). A per-task
        --model ID / --effort LEVEL record the session model and effort as run.
        qa verdict of a worktree repo is the task lead's record; the gate still needs QA on the integration HEAD.
        --subtask records to the subtask's own file, never the task review the gate reads. Every verdict is also kept
        per candidate (<task>__<phase>__<sha12>__<by>.json). A task review by a model other than the task's paired
        reviewer never replaces the pair's record for the same SHA (stderr note). A subtask review pairs against the
        subtask's recorded implementer, else the one its review dispatch named, else the subtask's routing (--subplan).
        --fallback 'AGENT unavailable' (review only) records a retrospective SAME_MODEL fallback with a required
        --note explaining the outage. AGENT is the paired reviewer that was unavailable, never the replacement that
        reviewed: --fallback 'codex unavailable' --by claude when codex (the paired reviewer) was down and claude
        reviewed instead. Legacy --fallback AGENT (no "unavailable") also requires that agent to be unavailable now.
        --failed-suites (qa FAIL only): comma-separated suites (names run-all --list-suites prints, or (tests|testlab|
        scripts)/ .sh or .py paths; never tests/run-all.sh), the next QA dispatch reruns them.
        Tier S lead QA: `--phase qa --state PASS --by <lead model> --note 'tier S: lead ran task suites'`.
  gate <plan.json> [--allow-same-model] [--no-run-checks] [--json]
        READY_FOR_PR when every task is integrated, reviewed PASS by its paired model on a commit whose task
        paths did not change since (a path with the same content as at the reviewed commit, and the side commits of
        a merge of the default branch, never make a review STALE), QA is PASS on each integration HEAD, the
        integration trees are clean, fast checks are PASS and not STALE, every change sits in some task's owned
        paths (the plan file and its report.md belong to the run lead and are never stray), verdicts match the
        current plan (fingerprint), and no worktree of a no-worktree repo was created for the plan. A subtask
        whose recorded implementer is not the one the task review paired against (or is the task reviewer's own
        model) needs its own PASS review by its pair or a dispatch-recorded SAME_MODEL fallback review. A per-task
        QA PASS with a note starting 'tier S' (the lead's own run, no QA session) counts only for a tier-S task, one
        starting 'tier XS' only for a tier-XS task. A tier XS task: its lead QA on plan.topic stands in for the
        integration QA, and a committed diff (start...reviewed SHA) above pipeline.tiers.XS is a blocker. With
        --no-run-checks the state is UNVERIFIED (no delivery commands).
        Then prints the push, `gh pr create`, and `gh pr checks <pr> --watch` commands (run them only when the user authorized
        `deliver: pr` in this task; merging stays with the user). Exit 0 READY, 1 not ready.

  report <plan.json> --task ID --sha SHA (--body TEXT | --body-file FILE)
        the task lead's durable report: <state dir>/pipeline/<plan id>/<task>__lead-report.json (at, sha, summary = the
        first line capped at 200 characters, the full body). The lead runs it before its Orca `status` message, so the
        run lead's `status` shows completion even when the message never arrives. Exit 2 on an unknown task, a bad
        --sha or an empty body.
  status <plan.json> [--orca-run RUN_ID]... [--json]
        how far each task got (pending, implementing, candidate, reviewed, integrated, qa), derived from git and
        the recorded verdicts, with the next command per task and the ready wave: how a new lead session resumes a
        run. Schema docs/schemas/pipeline-status.schema.json. Exit 1 when the plan is invalid. Each task row lists
        its leftover Orca child worktrees (`children`: branch or directory `<task branch>--*`) with a note: merge, then
        `orca worktree rm --worktree path:<child>`.
        A tier XS task, as the gate sees it: its branch is plan.topic (the run lead's edits and commit), a candidate
        names `--phase review`, after the review PASS the run lead's task tier command and QA record at the topic
        HEAD, and that QA PASS stands in for the integration QA.
        With a task lead's Orca Run (task `orca_run` in the plan, or --orca-run, repeatable) it also lists the Run's
        settled workers that are not released (`orca orchestration worker-list --run <id> --json`, read-only) and puts
        their `orca orchestration worker-release --dispatch <id>` first in `next`; a running worker is no finding;
        no orca or a failing call is a NOT_AVAILABLE line, never an error. With --json the "Workers:" lines go to
        stderr (stdout stays the status schema). The worker-list call asks for --full rows (the concise row lacks the
        resource); a worker counts as released by terminalState, resource.releaseState or ownershipState `released`, a
        releaseCompletedAt, or the projection's resource state.
        Per task (notes, so the schema is unchanged): `lead report: <at> @<sha10> <summary>` from the `report` record
        (plus `(stale: task HEAD is <sha10>)` when the task HEAD moved on), and once the task has commits
        `READY_FOR_PR: yes` (lead report, PASS review and PASS QA at the task HEAD) or `READY_FOR_PR: no (<first
        missing thing>)`. With an Orca Run (read-only `orca orchestration check --run R --all --json`, never marks a
        message read; any failure is no opinion) a `task done: <id>` message is shown as a note when no durable record
        exists. Test slots held by a run in one of the plan's checkouts (`<state dir>/locks/run-all-slots/<n>/`, written
        by tests/run-all.sh) print as `Slots: slot <n> held by PID <pid> in <checkout> since <start>` with whether the
        PID is alive (stderr with --json); status never stops the process and prints no command that would.

  cleanup <plan.json> [--after-merge] [--orca-run RUN_ID]... [--json]
        CLEAN when the run left no worktree or task branch (<topic>-*) and no settled worker of a named Orca Run
        (as in status) is unreleased; with --after-merge, also lists removal of its integration worktree and
        lists local and origin branch deletion for plan branches contained in main. Otherwise prints removal commands and
        `orca orchestration worker-release --dispatch <id>` per unreleased worker, names each leftover child worktree
        as "child of <task>" (`orca worktree rm` once merged), names the rest, and reminds to
        release every worker session. Orca unavailable: NOT_AVAILABLE, the state is unchanged. Exit 0 CLEAN, 1 LEFTOVER.
        A task worktree git lists as prunable (its directory is gone), a leftover task directory (empty or not, named
        <topic>-<id> with / as -, no longer a git worktree) and an Orca record of such a removed worktree are
        LEFTOVER, never CLEAN: `git -C <repo> worktree prune`, then `orca worktree rm --worktree path:<dir>` once the
        directory is free (a process holds a directory Windows reports busy: the user decides, cleanup names no PID it
        cannot see and never stops a process). Before a task worktree is removed it names the Orca terminals bound to it
        (read-only `orca terminal list`) and tells the task lead to confirm each released worker's CLI exited.
        For such a leftover directory it lists `BUSY?` candidates from a read-only process listing (Windows: PowerShell
        Get-CimInstance Win32_Process, 20 s timeout; elsewhere `ps`): processes whose command line names the directory and
        an orphaned `wsl.exe ... sleep infinity` (its parent is gone), with PID, command and start time; the user decides,
        no kill command is ever printed, and a failing probe names nothing. It also prints `SLOT` lines for held test
        slots in the plan's checkouts, as status does (`slots` in --json).

Read-only against the repos (never fetches, pushes, commits or creates worktrees: the printed commands do). Exit 2 =
usage error.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.append(os.path.join(HERE, "lib"))
import fstate  # noqa: E402
import pipeline_route as pr  # noqa: E402
import model_policy  # noqa: E402
import subagent_policy  # noqa: E402
import orca_cmd  # noqa: E402
import plan_paths  # noqa: E402
from shells import find_bash  # noqa: E402

SCHEMA = "rpg-factory.pipeline-plan/1"
# task and subtask ids: the schemas' pattern (pipeline-plan, pipeline-subplan); validate, subplan validate, dispatch and
# verdict share it, and verdict file names use the id as is
ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9_.-]*$"
ID_RULE = "letters, digits, - _ ., starting with a letter or digit"


def id_ok(x):
    return isinstance(x, str) and re.fullmatch(ID_PATTERN[1:-1], x) is not None


def die(msg, code=2):
    print(f"factory-pipeline: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_registry(path):
    defaults = path == "none" or not os.path.isfile(path)
    if defaults:
        if path != "none":
            print(f"factory-pipeline: registry {path} not found: using skills/delivery/pipeline-defaults.json",
                  file=sys.stderr)
        path = os.path.join(ROOT, "skills", "delivery", "pipeline-defaults.json")
    with open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    if defaults:
        reg["_defaults"] = True  # private mark: pipeline_argv adds `--registry none` to the commands printed for a next session
    return reg


def pipeline_argv(reg):
    """The command prefix printed for a next session: python3 -B <this script>, plus `--registry none` when the defaults are
    in effect (the next session would otherwise load the RPG registry); with a registry nothing is added."""
    argv = ["python3", "-B", os.path.abspath(__file__)]
    return argv + ["--registry", "none"] if reg.get("_defaults") else argv


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

def tier_of(ctx, pipe, lines=None):
    """lines: the changed-line count of the change when known (tier --plan with a checkout), else None (counts as 0)."""
    repos = [r for r in ctx.get("repos", []) if r.get("touched") or any(f.get("source") == "given" for f in r.get("files", []))]
    modules = sorted({m for r in repos for m in r.get("touched", [])})
    files = sum(1 for r in repos for f in r.get("files", []) if f.get("source") in ("given", "branch"))
    # XS judges every file of the change, uncommitted ones included: one path that is not prose is above XS
    paths = sorted({f.get("path", "") for r in repos for f in r.get("files", [])})
    contracts = sorted({c["id"] for r in repos for c in r.get("contracts", [])})
    generated = sorted({h if isinstance(h, str) else h.get("path", "?") for r in repos for h in r.get("generated_hits", [])})
    facts = {"repos": [r["repo"] for r in repos], "modules": modules, "files": files, "contracts": contracts, "generated": generated}
    if lines is not None:
        facts["changed_lines"] = lines

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
    if "XS" in pipe["tiers"]:  # XS first: prose only, within its file and changed-line thresholds
        why = fits("XS") + ([] if paths else ["no changed files"])
        reasons["XS"] = why + [w for w in pr.above_xs(pipe["tiers"]["XS"], paths, lines or 0) if w not in why]
        if not reasons["XS"]:
            return {"tier": "XS", "facts": facts, "above": reasons, "flow": pipe["tiers"]["XS"].get("flow", "")}
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
    lines = None  # the changed-line count, known only for tier --plan with a checkout
    if a.plan:
        if not a.repo or not a.paths:
            die("tier --plan needs --repo <plan repo key> and --paths <files>")
        plan = read_plan(a.plan, reg)
        plan["_path"] = a.plan
        info = repo_info(plan, reg, a.repo)
        lines = changed_lines(info["path"], a.paths)
        if not info["registry"]:
            if not info["path"]:
                die(f"repo `{a.repo}` is neither a registry repo nor in plan.repos with a path")
            out = tier_of(plain_context(a.repo, a.paths), pipe, lines)
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
    return print_tier(a, tier_of(ctx, pipe, lines))


def numstat_lines(out):
    """Added plus removed lines of `git diff --numstat` output (a binary file counts 0)."""
    n = 0
    for line in (out or "").splitlines():
        added, removed = (line.split("\t") + ["", ""])[:2]
        n += int(added) + int(removed) if added.isdigit() and removed.isdigit() else 0
    return n


def changed_lines(repo_path, paths):
    """Changed lines of a working change in `paths` (tier --plan): `git diff --numstat HEAD` plus the lines of the
    untracked given files. 0 when unknown (no checkout, git fails)."""
    if not repo_path or not paths or not os.path.isdir(repo_path):
        return 0
    out, rc = git(repo_path, "diff", "--numstat", "--no-renames", "HEAD", "--", *paths)
    n = numstat_lines(out) if rc == 0 else 0
    untracked, rc = git(repo_path, "ls-files", "--others", "--exclude-standard", "--", *paths)
    for f in (untracked or "").splitlines() if rc == 0 else []:
        try:
            with open(os.path.join(repo_path, f), encoding="utf-8", errors="replace") as fh:
                n += sum(1 for _ in fh)
        except OSError:
            pass
    return n


def print_tier(a, out):
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        f = out["facts"]
        print(f"Tier: {out['tier']}  ({len(f['repos'])} repo(s), {len(f['modules'])} module(s), {f['files']} file(s), "
              + (f"{f['changed_lines']} changed line(s), " if "changed_lines" in f else "")
              + f"contracts: {', '.join(f['contracts']) or 'none'}, generated: {', '.join(f['generated']) or 'none'})")
        if out.get("basis"):
            print(f"  basis: {out['basis']}; modules: {', '.join(f['modules'])}")
        for t, why in out["above"].items():
            if why:
                print(f"  above {t}: " + "; ".join(why))
        print("Flow: " + out["flow"])
    return 0


# ---------------------------------------------------------------- model grades

TIER_GRADE = {"XS": "light", "S": "light", "M": "standard", "L": "heavy"}
TIERS = tuple(TIER_GRADE)
ICASE = os.name == "nt"  # the file system folds case: owned paths compare case-insensitively (tests force it on Linux)


def route_path(p):
    """A path as the routing engine sees it: forward slashes, no empty or `.` segments (a trailing slash stays, it marks
    a directory), so ./a//b and a/b grade alike. The repo root (`.`, `./`) is the empty path."""
    s = str(p).replace("\\", "/")
    segs = [x for x in s.split("/") if x not in ("", ".")]
    return ("/" if s.startswith("/") else "") + "/".join(segs) + ("/" if segs and s.endswith("/") else "")


def registry_spellings(reg, key):
    """Every path the registry names in repo `key` (module paths, plain generated paths, contract ends), globs left out."""
    out = set()
    for m in reg.get("modules") or []:
        if m.get("repo") == key:
            out.update(x for x in (m.get("paths") or []) + (m.get("generated") or []) if not x.startswith("**/"))
    for c in reg.get("contracts") or []:
        out.update(e["path"] for e in [c.get("source") or {}] + (c.get("copies") or [])
                   if e.get("repo") == key and e.get("path") and not e["path"].startswith("**/"))
    return out


def registry_case(reg, key, p):
    """`p` with its leading segments in the registry's spelling where the file system folds case (ICASE), so the
    case-sensitive routing engine sees BACKEND/SHARED/PROTO/WIRE.PROTO as backend/shared/proto/wire.proto. The longest
    registry path that `p` lies in, or that lies in `p`, supplies the spelling; the rest of `p` keeps its own case."""
    if not ICASE or not p:
        return p
    segs = p.rstrip("/").split("/")
    low = [x.lower() for x in segs]
    best = []
    for e in registry_spellings(reg, key):
        es = e.rstrip("/").split("/")
        k = 0
        while k < min(len(es), len(segs)) and es[k].lower() == low[k]:
            k += 1
        if (k == len(es) or k == len(segs)) and k > len(best):
            best = es[:k]
    return "/".join(best + segs[len(best):]) + ("/" if p.endswith("/") else "")


def is_dir_path(p, repo_path):
    """An owned path names a directory: the repo root, a trailing slash, a directory on disk in the checkout (read only),
    or, absent from disk, a last segment without an extension. So Editor/Codegen/Generated and
    Editor/Codegen/Generated/ grade alike."""
    if p == "" or p.endswith("/"):
        return True
    if repo_path:
        full = os.path.join(repo_path, p)
        if os.path.isdir(full):
            return True
        if os.path.exists(full):
            return False
    return "." not in p.rsplit("/", 1)[-1].lstrip(".")


def grade_paths(reg, key, paths, repo_path):
    """Owned paths in the one spelling grading compares: route_path, the registry's case where the file system folds
    case, and a trailing slash on every directory. The root stays the empty path."""
    out = []
    for p in paths:
        q = registry_case(reg, key, route_path(p)) if key else route_path(p)
        out.append(q + "/" if q and not q.endswith("/") and is_dir_path(q, repo_path) else q)
    return out


def static_resolve(reg, key, paths):
    """resolve.jq over the given paths alone (no git state, so the result never drifts with the branch), or None with
    the reason when jq is missing or fails."""
    files = [{"path": p, "status": "M", "source": "given"} for p in paths]
    try:
        r = subprocess.run(["jq", "-c", "--arg", "repo", key, "--argjson", "files", json.dumps(files), "--argjson", "subst",
                            "{}", "--argjson", "tools", "{}", "-f", os.path.join(HERE, "lib", "resolve.jq")],
                           input=json.dumps(reg), capture_output=True, text=True, timeout=60, encoding="utf-8",
                           errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"jq unavailable ({e.__class__.__name__})"
    if r.returncode != 0:
        return None, "routing engine failed: " + (r.stderr or "").strip()[:200]
    try:
        return json.loads(r.stdout), None
    except ValueError:
        return None, "routing engine printed no JSON"


def fold(p):
    return p.lower() if ICASE else p


def covers(a, b):
    """Path `a` (a file, or a directory with or without its trailing slash; the empty path is the repo root) is `b` or
    contains it: resolve.jq's path_matches, used both ways for owned paths. Case-insensitive where the file system is."""
    a, b = fold(a).rstrip("/"), fold(b).rstrip("/")
    return a == "" or b == a or b.startswith(a + "/")


def overlaps_entry(entry, p, roots=()):
    """A registry contract end or generated path `entry` and an owned path `p` (grade_paths: a directory ends with `/`,
    the root is empty) overlap when either contains the other. A `**/*<suffix>` glob matches a file with that suffix,
    and any owned directory that contains a root (`roots`: the paths of the module the glob belongs to) or lies inside
    one; with no roots (a contract glob) any owned directory may hold a match."""
    if entry.startswith("**/*"):
        if fold(p).endswith(fold(entry[4:])):
            return True
        if not (p == "" or p.endswith("/")):
            return False
        return not roots or any(covers(p, r) or covers(r, p) for r in roots)
    return covers(entry, p) or covers(p, entry)


def owned_overlap(reg, key, owned):
    """Contracts and generated paths of registry repo `key` an owned path (grade_paths spelling) overlaps either way.
    resolve.jq maps a file to what contains it; an owned directory must also count what it contains
    (backend/shared/proto/ holds wire.proto). A handoff contract counts only with its source end, as in resolve.jq."""
    contracts = []
    for c in reg.get("contracts") or []:
        ends = [(e, e is c.get("source")) for e in [c.get("source") or {}] + (c.get("copies") or [])
                if e.get("repo") == key and e.get("path")]
        hits = [src for e, src in ends if any(overlaps_entry(e["path"], p) for p in owned)]
        if hits and (c.get("kind") != "handoff" or any(hits)):
            contracts.append(c["id"])
    generated = []
    for m in reg.get("modules") or []:
        if m.get("repo") != key:
            continue
        for g in m.get("generated") or []:
            generated += [{"path": p or ".", "generated_by": g} for p in owned if overlaps_entry(g, p, m.get("paths") or [])]
    return contracts, generated


def task_context(plan, reg, task):
    """(routing snapshot of the task's owned paths alone, or None, reason). Each task resolves on its own: a batch
    would let one task's paths change another's result (a handoff copy counts only next to its source). A repo the
    registry does not know is resolved from the paths (plain_context)."""
    info = repo_info(plan, reg, task["repo"])
    if not info["registry"]:
        return plain_context(task["repo"], task["paths"]), None
    key = info["registry"]
    owned = sorted(set(grade_paths(reg, key, task["paths"], info["path"])))
    res, why = static_resolve(reg, key, owned)
    if res is None:
        return None, why
    contracts, generated = owned_overlap(reg, key, owned)
    contracts = sorted({c["id"] for c in res.get("contracts", [])} | set(contracts))
    files = res.get("files", [])
    return {"repos": [{
        "repo": key, "touched": sorted({f["module"] for f in files if f.get("module")}),
        "files": [{"path": f["path"], "source": "given"} for f in files],
        "contracts": [{"id": c} for c in contracts],
        "generated_hits": res.get("generated_hits", []) + generated}]}, None


def task_grades(plan, reg, policy, tasks):
    """task id -> {grade, source}: the plan's `grade`, else derived from the tier of the task's owned paths (S light, M
    standard, L or a contract or generated path heavy), else the policy's default_grade."""
    out, todo = {}, []
    for t in tasks:
        if t.get("grade") in model_policy.GRADES:
            out[t["id"]] = {"grade": t["grade"], "source": "plan"}
        else:
            todo.append(t)
    for t in todo:
        ctx, why = task_context(plan, reg, t)
        if ctx is None:
            out[t["id"]] = {"grade": policy["default_grade"], "source": f"default_grade (tier unknown: {why})"}
            continue
        tier = tier_of(ctx, settings(reg))
        heavy = tier["facts"]["contracts"] or tier["facts"]["generated"]
        grade = "heavy" if heavy else TIER_GRADE[tier["tier"]]
        out[t["id"]] = {"grade": grade, "source": f"tier {tier['tier']} of the owned paths"
                        + (", contract or generated path" if heavy else "")}
    return out


def load_policy(reg):
    """The model policy (registry pipeline.models plus the personal override file); a broken one exits 1."""
    try:
        return model_policy.load(reg)
    except model_policy.PolicyError as e:
        die(str(e), 1)


def review_role(grade):
    """A heavy task's (or subtask's) review runs with the heavy profile, so a hard diff gets a strong reviewer."""
    return "heavy" if grade == "heavy" else "review"


def session_agent(a, agent):
    """The agent that actually runs a session: --runner agent starts Claude only (AGENT_FALLBACK), else the planned one."""
    return AGENT_FALLBACK if a.runner == "agent" else agent


def subagent_rule(a, reg, role, agent):
    """The one-sentence subagent rule (registry pipeline.subagents) of `role` for the agent that runs the session;
    a missing or malformed policy exits 1 with nothing dispatched."""
    try:
        return subagent_policy.rule(reg, role, session_agent(a, agent))
    except subagent_policy.SubagentPolicyError as e:
        die(f"subagent policy: {e}. Nothing was dispatched.", 1)


def session_model(a, agent, role):
    """{model, effort, role} of one dispatched session: the policy's profile for the role (or --grade's), with --model /
    --effort as explicit overrides that must stay inside the scope (else usage error, exit 2: nothing dispatched)."""
    policy = a.policy
    role = getattr(a, "grade", None) or role
    try:
        prof = model_policy.resolve(policy, agent, role)
    except model_policy.PolicyError as e:
        die(f"model policy: {e}", 1)
    model, effort = getattr(a, "model", None) or prof["model"], getattr(a, "effort", None) or prof["effort"]
    if not model_policy.in_scope(policy, agent, model, effort):
        allowed = "; ".join(f"{m}: {', '.join(e)}" for m, e in (policy["scope"].get(agent) or {}).items()) or "none"
        die(f"--model/--effort: {agent} {model} / {effort} is outside the model scope (registry pipeline.models.scope "
            f"plus override; {agent}: {allowed}). Nothing was dispatched.")
    return {"model": model, "effort": effort, "role": role}


# ---------------------------------------------------------------- plan

def read_json_file(path, what):
    """A JSON object from a file; utf-8-sig, since PowerShell's `Out-File`/`Set-Content` write a UTF-8 BOM."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        die(f"cannot read {what} {path}: {e}")
    if not isinstance(doc, dict):
        die(f"{what} must be a JSON object")
    return doc


def read_plan(path, reg):
    plan = read_json_file(path, "plan")
    markers = plan.get("no_worktree_markers")
    if isinstance(markers, list) and all(isinstance(m, str) for m in markers):
        reg["pipeline"] = {**reg["pipeline"], "no_worktree_markers": list(markers)}
    return plan


def repo_info(plan, reg, key):
    """{key, path, base, registry} for a task repo: a registry key, or an entry of plan.repos (unregistered)."""
    own = (plan.get("repos") or {}).get(key) or {}
    rreg = reg.get("repos", {}).get(own.get("registry", key))
    path = own.get("path") or (orca_cmd.repo_checkout(reg, own.get("registry", key)) if rreg else None)
    path, path_reason = plan_paths.resolve_repo_path(path, plan.get("_path", os.path.join(os.getcwd(), "plan.json")), reg)
    if path_reason:
        die(path_reason)
    base = own.get("base") or (rreg or {}).get("default_branch")
    allowed, reason = orca_cmd.allows_worktree(reg, own.get("registry", key) if rreg else None, path)
    reason = reason.rstrip(". ") if reason else reason  # printed as "No worktree: <reason>." (no double period)
    ident = os.path.normcase(os.path.realpath(path)) if path else f"?{key}"
    return {"key": key, "registry": own.get("registry", key) if rreg else None, "path": path, "base": base,
            "base_sha": own.get("base_sha"), "worktrees": allowed, "reason": reason, "identity": ident}


def same_repo(plan, reg, x, y):
    """Two plan repo keys name one checkout (a registry key and a plan.repos alias of the same path)."""
    return x == y or repo_info(plan, reg, x)["identity"] == repo_info(plan, reg, y)["identity"]


def serial_key(plan, reg, key):
    """What tasks that run one after another share: a no-worktree checkout's identity (every plan alias of it, as in
    serialize()), else the repo key."""
    info = repo_info(plan, reg, key)
    return key if info["worktrees"] else info["identity"]


def serial_count(plan, reg, key):
    """How many tasks of the plan run in the serial group of repo `key` (per-task QA when a no-worktree group has >1)."""
    me = serial_key(plan, reg, key)
    return sum(1 for t in plan.get("tasks", []) if t.get("repo") and serial_key(plan, reg, t["repo"]) == me)


def norm_path(p):
    """Repo-relative owned path in one spelling: forward slashes, no `.` or empty segments (a trailing / is kept),
    case-folded where the file system is. `..` is not resolved here: path_problem() rejects it before any comparison."""
    s = str(p).replace("\\", "/")
    p = "/".join(x for x in s.split("/") if x not in ("", "."))
    if p and s.endswith("/"):
        p += "/"
    return p.lower() if ICASE else p  # not normcase: it turns / into \ on Windows


def specs(paths):
    """Git pathspecs for owned paths, matched the way norm_path() compares them: case-insensitive where the file system
    is (Windows), so a plan path in another case finds the same changes the owned-path check accepts."""
    return [f":(icase){p}" for p in paths] if ICASE else list(paths)


def path_problem(p):
    """Why an owned path cannot be compared by prefix (absolute, or a `..` segment that leaves its directory), or None.
    Containment, exclusion and overlap checks compare spellings, so `Assets/../../x` must never reach them."""
    if not isinstance(p, str) or not p.strip():
        return "is not a non-empty string"
    s = p.replace("\\", "/")
    if s.startswith("/") or (len(s) > 1 and s[1] == ":") or s.startswith("~"):
        return "is absolute; owned paths are repo-relative"
    if ".." in s.split("/"):
        return "has a `..` segment; owned paths are repo-relative without `..`"
    return None


def task_fingerprint(task, pipe):
    """What a verdict vouches for: a changed objective, owned paths, acceptance, checks or agents invalidate it."""
    keys = {k: task.get(k) for k in ("repo", "objective", "paths", "exclusions", "acceptance", "checks", "reviewer")}
    keys["implementer"] = pr.route(pipe, task, {a: {"available": True} for a in pipe["agents"]})[0]
    if "kind" in task:
        keys["kind"] = task["kind"]
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


def task_qa_warnings(task):
    """pr.qa_warnings without the verify tier command: a scoped run-all check is what the verify session runs, not a
    suite an implementer would run; a suite named next to it still warns."""
    def tier_only(c):
        rest = re.sub(r"(?:\./)?tests/run-all\.sh", "", c)
        rest = re.sub(r"--only-suites(?:=|\s+)\S+", "", rest)  # the suites a scoped run-all names are its scope
        return pr.mentions_runall(c) and not pr.full_run(c) and not pr.SUITE_CHECK.search(rest)
    return pr.qa_warnings(dict(task, checks=[c for c in task.get("checks", []) if not tier_only(c)]))


def xs_implementer(pipe):
    """Who implements a tier XS task: the run lead itself (registry pipeline.lead_agent); its review is the pair."""
    return pipe.get("lead_agent") or "claude"


def xs_heavy(plan, reg, rule, repo, paths):
    """Why `paths` of plan repo `repo` are above tier XS by registry pipeline.tiers.XS `contracts: false` /
    `generated: false`: the contracts and generated paths their routing snapshot names, as tier_of reports them.
    Empty when they fit or the snapshot is unknown (jq missing)."""
    if not paths or (rule.get("contracts") is not False and rule.get("generated") is not False):
        return []
    ctx, _ = task_context(plan, reg, {"repo": repo, "paths": list(paths)})
    if ctx is None:
        return []
    repos = ctx.get("repos", [])
    contracts = sorted({c["id"] for r in repos for c in r.get("contracts", [])})
    generated = sorted({h if isinstance(h, str) else h.get("path", "?") for r in repos for h in r.get("generated_hits", [])})
    why = []
    if rule.get("contracts") is False and contracts:
        why.append("contract " + ", ".join(contracts))
    if rule.get("generated") is False and generated:
        why.append("generated path " + ", ".join(generated))
    return why


def xs_plan_errors(plan, reg, pipe, tasks):
    """Why a plan or task marked tier XS is not one: XS is a one-task plan whose owned paths are all prose, at most
    pipeline.tiers.XS max_files and touch no contract or generated path when the rule forbids them (its changed lines
    are judged on the committed diff by the gate)."""
    xs = [t for t in tasks if pr.xs_plan(plan, t)]
    if not xs:
        return []
    rule = pipe["tiers"].get("XS")
    if not rule:
        return ["tier XS: the registry has no pipeline.tiers.XS rule"]
    errors = []
    if len(tasks) != 1:
        errors.append(f"tier XS: a tier XS plan has exactly one task, this one has {len(tasks)} (use tier S or M)")
    for t in xs:
        why = pr.above_xs(rule, t.get("paths") or [])
        if t.get("repo"):
            why += xs_heavy(plan, reg, rule, t["repo"], t.get("paths") or [])
        if why:
            errors.append(f"task {t.get('id', '?')}: tier XS, but its owned paths are above XS: " + "; ".join(why))
    return errors


def validate(plan, reg):
    pipe = settings(reg)
    errors, warnings = [], pr.warnings(pipe, plan.get("tasks") or [])
    if plan.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    for k in ("id", "title", "topic", "tasks"):
        if not plan.get(k):
            errors.append(f"missing `{k}`")
    if plan.get("id") and plan_dir_name(plan["id"]) == PLANNER_DIR:
        errors.append(f"plan id `{plan['id']}` is reserved: its state directory `{PLANNER_DIR}` holds the planner's specs")
    if plan.get("tier") and plan["tier"] not in TIERS:
        errors.append("tier must be XS, S, M or L")
    if plan.get("deliver", "none") not in ("pr", "none"):
        errors.append("deliver must be pr or none")
    if "no_worktree_markers" in plan and (not isinstance(plan["no_worktree_markers"], list) or
            not all(isinstance(m, str) for m in plan["no_worktree_markers"])):
        errors.append("no_worktree_markers must be an array of strings")
    if "known_failing" in plan:
        kf = plan["known_failing"]
        if not isinstance(kf, list):
            errors.append("known_failing must be an array of {check, reason} objects")
        else:
            for i, e in enumerate(kf):
                if not (isinstance(e, dict) and all(isinstance(e.get(k), str) and e[k].strip() for k in ("check", "reason"))):
                    errors.append(f"known_failing[{i}]: needs non-empty string check and reason")
                    continue
                for k in sorted(set(e) - {"check", "reason"}):
                    errors.append(f"known_failing[{i}]: unknown key {k}")
                warnings.append(f"known failing at base: {e['check']} - {e['reason']}")
    tasks = plan.get("tasks") or []
    ids = [t.get("id") for t in tasks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate task id {dup}")
    if "integration" in ids or any(str(i).startswith("integration:") for i in ids):
        errors.append("task id `integration` is reserved for QA on the integration branch")
    for i in ids:
        if i and not str(i).startswith("integration:") and not id_ok(i):
            errors.append(f"task id {json.dumps(i)} is not an id ({ID_RULE})")
    # integration:<repo> verdicts are stored as integration_<repo>: a task with that name would share their file
    clash = sorted({i for i in ids if isinstance(i, str)} & {safe_name(f"integration:{t.get('repo')}") for t in tasks})
    for i in clash:
        errors.append(f"task id `{i}` is reserved: the integration QA of repo {i[len('integration_'):]} keeps its "
                      "verdicts under that name")
    agents = pipe["agents"]
    for t in tasks:
        tid = t.get("id", "?")
        warnings.extend(task_qa_warnings(t))
        if t.get("kind") is not None and t["kind"] not in pr.KINDS:
            errors.append(f"task {tid}: unknown kind {t['kind']}")
        if t.get("implementer") and t["implementer"] not in agents:
            errors.append(f"task {tid}: unknown implementer {t['implementer']}")
        for k in ("id", "repo", "objective", "paths", "acceptance"):
            if not t.get(k):
                errors.append(f"task {tid}: missing `{k}`")
        info = repo_info(plan, reg, t.get("repo"))
        if not info["path"]:
            errors.append(f"task {tid}: repo `{t.get('repo')}` is neither a registry repo nor in plan.repos with a path")
        if "tier" in t and t["tier"] not in TIERS:
            errors.append(f"task {tid}: tier must be XS, S, M or L")
        impl = (xs_implementer(pipe) if pr.xs_plan(plan, t) else
                pr.route(pipe, t, {a: {"available": True} for a in agents})[0])
        if impl not in agents:
            errors.append(f"task {tid}: implementer `{impl}` is not a pipeline agent ({', '.join(agents)})")
        reviewer = t.get("reviewer") or pipe["review_pairing"].get(impl)
        if reviewer == impl:
            errors.append(f"task {tid}: reviewer `{reviewer}` is the implementer's model; cross-model review needs the pair "
                          f"({pipe['review_pairing'].get(impl)})")
        if not info["worktrees"] and t.get("worktree") is True:
            errors.append(f"task {tid}: repo `{t.get('repo')}` takes no worktree ({info['reason']}); drop `worktree: true`")
        if "orca_run" in t and not (isinstance(t["orca_run"], str) and t["orca_run"].strip()):
            errors.append(f"task {tid}: `orca_run` must be the task lead's Orca Run id (a non-empty string)")
        if "grade" in t and t["grade"] not in model_policy.GRADES:
            errors.append(f"task {tid}: grade {json.dumps(t['grade'])} is not one of {', '.join(model_policy.GRADES)}")
        if "grade_reason" in t and not isinstance(t["grade_reason"], str):
            errors.append(f"task {tid}: `grade_reason` must be a string")
        for d in t.get("deps", []):
            if d not in ids:
                errors.append(f"task {tid}: unknown dependency {d}")
        for k in ("paths", "exclusions"):
            for p in t.get(k) or []:
                why = path_problem(p)
                if why:
                    errors.append(f"task {tid}: {k[:-1]} {p} {why}")
    errors += xs_plan_errors(plan, reg, pipe, tasks)
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


def gradable(task):
    """A task the model preview can grade: validation's errors already name anything else (paths that are not
    non-empty repo-relative strings, an unknown grade), so the preview skips it instead of crashing."""
    return (isinstance(task, dict) and isinstance(task.get("repo"), str) and task["repo"]
            and isinstance(task.get("paths"), list) and task["paths"]
            and all(path_problem(p) is None for p in task["paths"])
            and (task.get("grade") is None or task.get("grade") in model_policy.GRADES))


def plan_models(plan, reg, errors):
    """What every session of the plan runs with (lead, and per task its grade, implement, review and QA), so the run
    lead sees the cost before any dispatch. A broken policy or a role it cannot resolve is an error."""
    pipe = settings(reg)
    try:
        policy = model_policy.load(reg)
    except model_policy.PolicyError as e:
        errors.append(str(e))
        return None
    out = {"lead": None, "tasks": {}}

    def pick(agent, role, who):
        try:
            return dict(model_policy.resolve(policy, agent, role), agent=agent, role=role)
        except model_policy.PolicyError as e:
            errors.append(f"{who}: model policy: {e}")
            return None
    avail = pr.available(pipe, plan)
    out["lead"] = pick(pr.choose(pipe.get("lead_agent") or "claude", "lead_agent", avail)[0], "lead", "task lead")
    tasks = [t for t in plan.get("tasks") or [] if gradable(t) and id_ok(t.get("id"))
             and repo_info(plan, reg, t["repo"])["path"]]
    grades = task_grades(plan, reg, policy, tasks)
    for t in tasks:
        if any(t.get(k) is not None and (not isinstance(t[k], str) or t[k] not in pipe["agents"])
               for k in ("implementer", "reviewer")):
            continue  # validation already reports malformed agent fields
        xs_impl = pr.choose(xs_implementer(pipe), "tier XS: the run lead implements", avail) if pr.xs_plan(plan, t) else None
        roles = pr.roles(pipe, t, avail, xs_impl)
        impl, reviewer = roles["implement"][0], roles["review"][0]
        if not isinstance(impl, str) or not isinstance(reviewer, str) or impl not in pipe["agents"]                 or reviewer not in pipe["agents"]:
            continue
        g = grades[t["id"]]
        who = f"task {t['id']} ({g['grade']})"
        out["tasks"][t["id"]] = dict(g, implement=pick(impl, g["grade"], who),
                                     review=pick(reviewer, review_role(g["grade"]), who), qa=pick(roles["qa"][0], "qa", who))
    return out


def model_text(m):
    return f"{m['agent']} {m['model']} {m['effort']}" if m else "unresolved"


def cmd_validate(a, reg):
    plan = read_plan(a.plan, reg)
    plan["_path"] = a.plan
    out = validate(plan, reg)
    out.pop("order")
    out["models"] = plan_models(plan, reg, out["errors"])
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for e in out["errors"]:
            print("ERROR " + e)
        for w in out.get("warnings", []):
            print("WARN  " + w)
        for n, w in enumerate(out["waves"], 1):
            print(f"Wave {n}: {', '.join(w)}")
        if out["no_worktree_repos"]:
            print("No worktree (main checkout, one task at a time): " + ", ".join(out["no_worktree_repos"]))
        if out["models"]:
            print(f"Model: task lead {model_text(out['models']['lead'])}")
            for tid, m in out["models"]["tasks"].items():
                print(f"Model: task {tid} grade {m['grade']} ({m['source']}): implement {model_text(m['implement'])}, "
                      f"review {model_text(m['review'])}, qa {model_text(m['qa'])}")
        print("OK" if not out["errors"] else f"INVALID ({len(out['errors'])} error(s))")
    return 1 if out["errors"] else 0


# ---------------------------------------------------------------- subplan

SUBPLAN_SCHEMA = "rpg-factory.pipeline-subplan/1"
PLACEMENTS = ("shared", "child")  # a subtask's session: the shared task worktree (default) or an Orca child of it
SUBPLAN_KEYS = ("schema", "plan", "task", "subtasks")  # the schema's additionalProperties: false, here and per subtask
SUBTASK_KEYS = ("id", "task", "objective", "paths", "deps", "implementer", "reviewer", "placement", "reason", "checks",
                "acceptance", "kind", "grade", "grade_reason")


def validate_subplan(sub, plan, reg):
    """A task lead's split of one plan task into subtasks: same task, disjoint paths inside its owned paths (unless
    ordered by deps), known acyclic deps, waves, a pipeline agent per subtask and a reviewer of the other model."""
    pipe = settings(reg)
    agents, pairing = pipe["agents"], pipe["review_pairing"]
    errors = []
    if sub.get("schema") != SUBPLAN_SCHEMA:
        errors.append(f"schema must be {SUBPLAN_SCHEMA}")
    for k in sorted(set(sub) - set(SUBPLAN_KEYS)):
        errors.append(f"unknown key `{k}` (a subplan has {', '.join(SUBPLAN_KEYS)})")
    tid = sub.get("task")
    if tid is not None and not isinstance(tid, str):
        errors.append(f"`task` must be a string, got {json.dumps(tid)}")
        tid = None
    task = next((t for t in plan.get("tasks", []) if t.get("id") == tid), None) if tid else None
    if not tid:
        errors.append("missing `task`")
    elif task is None:
        errors.append(f"unknown task {tid}: plan {plan.get('id', '?')} has "
                      f"{', '.join(str(t.get('id')) for t in plan.get('tasks', [])) or 'no task'}")
    owned = (task or {}).get("paths") or []
    excluded = (task or {}).get("exclusions") or []
    raw = sub.get("subtasks")
    if not isinstance(raw, list) or not raw:
        errors.append("missing `subtasks`" if raw is None else "`subtasks` must be a non-empty list of objects")
        raw = []
    subs = []
    for n, s in enumerate(raw, 1):  # a malformed item is an error, never silently dropped
        if not isinstance(s, dict):
            errors.append(f"subtask #{n}: must be an object, got {json.dumps(s)}")
            continue
        sid = s.get("id") if isinstance(s.get("id"), str) and s.get("id") else f"#{n}"
        clean = dict(s)
        for k in sorted(set(s) - set(SUBTASK_KEYS)):
            errors.append(f"subtask {sid}: unknown key `{k}` (a subtask has {', '.join(SUBTASK_KEYS)})")
        if isinstance(s.get("id"), str) and s["id"] and not id_ok(s["id"]):
            errors.append(f"subtask {json.dumps(s['id'])}: id is not an id ({ID_RULE})")
        for k in ("id", "task", "objective", "implementer", "reviewer", "placement", "reason", "grade", "grade_reason"):
            if k in s and not isinstance(s[k], str):
                errors.append(f"subtask {sid}: `{k}` must be a string, got {json.dumps(s[k])}")
                clean.pop(k)
        for k in ("paths", "deps", "checks", "acceptance"):
            if k in s and not (isinstance(s[k], list) and all(isinstance(x, str) for x in s[k])):
                errors.append(f"subtask {sid}: `{k}` must be a list of strings, got {json.dumps(s[k])}")
                clean[k] = []
        subs.append(clean)
    ids = [s.get("id") for s in subs]
    for dup in sorted({str(i) for i in ids if i is not None and ids.count(i) > 1}):
        errors.append(f"duplicate subtask id {dup}")
    info = repo_info(plan, reg, task["repo"]) if task is not None and task.get("repo") else None
    for s in subs:
        sid = s.get("id", "?")
        place = s.get("placement", "shared")
        if place not in PLACEMENTS:
            errors.append(f"subtask {sid}: placement `{place}` is not one of {', '.join(PLACEMENTS)}")
        elif place == "child":
            if not (s.get("reason") or "").strip():
                errors.append(f"subtask {sid}: placement child needs a `reason` (why isolation is faster or safer)")
            if info is not None and not info["worktrees"]:
                errors.append(f"subtask {sid}: placement child in repo `{task['repo']}`, which takes no worktree "
                              f"({info['reason']}): use shared")
        for k in ("id", "objective", "paths"):
            if not s.get(k):
                errors.append(f"subtask {sid}: missing `{k}`")
        if s.get("task") not in (None, tid):
            errors.append(f"subtask {sid}: belongs to task {s['task']}, not {tid}: one subplan splits one task")
        if "grade" in s and s["grade"] not in model_policy.GRADES:
            errors.append(f"subtask {sid}: grade {s['grade']} is not one of {', '.join(model_policy.GRADES)}")
        bad = [p for p in s.get("paths") or [] if path_problem(p)]
        for p in bad:
            errors.append(f"subtask {sid}: path {p} {path_problem(p)}")
        s["paths"] = [p for p in s.get("paths") or [] if p not in bad]  # overlap and waves see only safe paths
        if task is not None:
            for p in s["paths"]:
                if not inside_owned(p, owned):
                    errors.append(f"subtask {sid}: path {p} is outside the owned paths of task {tid} ({', '.join(owned)})")
                elif excluded_by(p, excluded):
                    errors.append(f"subtask {sid}: path {p} overlaps an exclusion of task {tid}")
        if s.get("kind") is not None and s["kind"] not in pr.KINDS:
            errors.append(f"subtask {sid}: unknown kind {s['kind']}")
        if not s.get("implementer") and not s.get("kind"):
            errors.append(f"subtask {sid}: missing implementer (or kind)")
        if s.get("implementer") and s["implementer"] not in agents:
            errors.append(f"subtask {sid}: implementer `{s['implementer']}` is not a pipeline agent ({', '.join(agents)})")
        impl = pr.route(pipe, s, {a: {"available": True} for a in agents})[0]
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
    serial = None
    if info is not None:
        if not info["worktrees"]:  # Unity project: never two sub-sessions editing or importing it at once
            serial = info["reason"]
            waves = [[sid] for w in waves for sid in w]
    return {"plan": plan.get("_path"), "task": tid, "errors": errors, "warnings": pr.warnings(pipe, subs), "waves": waves, "serial": serial}


def subplan_plan_path(sub, sub_path, override=None):
    """The plan a subplan splits: --plan, or its `plan` (relative to the subplan file)."""
    path = override or sub.get("plan")
    if not path:
        die("the subplan names no `plan` and no --plan was given")
    if not override and not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(sub_path)), path))
    return path


def cmd_subplan(a, reg):
    sub = read_json_file(a.subplan, "subplan")
    path = subplan_plan_path(sub, a.subplan, a.plan)
    plan = read_plan(path, reg)
    plan["_path"] = path
    out = validate_subplan(sub, plan, reg)
    out["models"] = subplan_models(sub, plan, reg, out["errors"])
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for e in out["errors"]:
            print("ERROR " + e)
        for w in out.get("warnings", []):
            print("WARN  " + w)
        for n, w in enumerate(out["waves"], 1):
            print(f"Wave {n}: {', '.join(w)}")
        if out["serial"]:
            print(f"One subtask at a time (no worktree: {out['serial']})")
        if out["models"]:
            for sid, m in out["models"]["subtasks"].items():
                print(f"Model: subtask {sid} grade {m['grade']} ({m['source']}): implement {model_text(m['implement'])}, "
                      f"review {model_text(m['review'])}")
        print("OK" if not out["errors"] else f"INVALID ({len(out['errors'])} error(s))")
    return 1 if out["errors"] else 0


def subplan_models(sub, plan, reg, errors):
    """Per subtask: its grade (its own, else the task's) and the model and effort of its implement and review sessions.
    A broken policy or a grade it cannot resolve for the subtask's model is an error. None when the task is unknown."""
    pipe = settings(reg)
    task = next((t for t in plan.get("tasks") or [] if isinstance(t, dict) and t.get("id") == sub.get("task")), None)
    if task is None or not isinstance(task.get("repo"), str) or not isinstance(task.get("paths"), list)             or not task["paths"] or any(path_problem(p) for p in task["paths"]):
        return None  # validation names what is wrong with the parent task
    try:
        policy = model_policy.load(reg)
    except model_policy.PolicyError as e:
        errors.append(str(e))
        return None
    if task.get("grade", "standard") not in model_policy.GRADES:  # the subtasks' inherited grade would be a guess
        errors.append(f"task {task['id']}: grade {json.dumps(task['grade'])} is not one of {', '.join(model_policy.GRADES)}")
        return None
    tg = task_grades(plan, reg, policy, [task])[task["id"]]
    out = {"task": tg, "subtasks": {}}
    raw = sub.get("subtasks")  # validate_subplan already rejected anything but a list of objects
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, dict) or not id_ok(s.get("id")):
            continue
        if any(s.get(k) is not None and (not isinstance(s[k], str) or s[k] not in pipe["agents"])
               for k in ("implementer", "reviewer")):
            continue  # validation already reports malformed agent fields
        roles = pr.roles(pipe, s, pr.available(pipe, plan))
        impl, reviewer = roles["implement"][0], roles["review"][0]
        own = s.get("grade") in model_policy.GRADES
        if "grade" in s and not own:
            continue  # validate_subplan already named the bad grade
        grade = s["grade"] if own else tg["grade"]
        row = {"grade": grade, "source": "subplan" if own else f"task grade: {tg['source']}"}
        for phase, agent, role in (("implement", impl, grade), ("review", reviewer, review_role(grade))):
            if not isinstance(agent, str) or agent not in pipe["agents"]:
                row[phase] = None  # validate_subplan already named the unknown reviewer
                continue
            try:
                row[phase] = dict(model_policy.resolve(policy, agent, role), agent=agent, role=role)
            except model_policy.PolicyError as e:
                errors.append(f"subtask {s['id']} ({grade}): model policy: {e}")
                row[phase] = None
        out["subtasks"][s["id"]] = row
    return out


# ---------------------------------------------------------------- dispatch

def find_task(plan, tid):
    for t in plan.get("tasks", []):
        if t.get("id") == tid:
            return t
    die(f"unknown task {tid}")


def task_branch(plan, info, task):
    return plan["topic"] if not info["worktrees"] else f"{plan['topic']}-{task['id']}"


def start_base(plan, info, task):
    """Where a task branch starts: a later-wave task (deps) of a worktree repo starts from the integration branch
    plan.topic when it exists (it carries the earlier waves); otherwise the base. repos.<key>.base stays the
    comparison base of `status` and the gate."""
    base = info["base_sha"] or info["base"]
    if task.get("deps") and info["worktrees"] and info["path"]:
        if git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{plan['topic']}")[0]:
            return plan["topic"]
    return base


AGENT_FALLBACK = "claude"  # the Claude Code Agent tool starts Claude sessions only


def orca_prompt(a, prompt, plan=None, note=None):
    """Keep cmd.exe arguments on one line; the full, immutable spec lives in persistent state.
    `note` is appended after the pointer with every whitespace run collapsed to one space."""
    root = os.path.join(fstate.persistent(), "pipeline", PLANNER_DIR) if plan is None else verdict_dir(plan)
    task = fstate.session_key(getattr(a, "task", None) or "planner")
    phase = getattr(a, "phase", None) or "plan"
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    path = os.path.abspath(os.path.join(root, "specs", f"{task}-{phase}-{digest}.md"))
    fstate.write_text(path, prompt)
    return f"Read your task spec at {path} and follow it." + (f" {' '.join(note.split())}" if note else "")


def resolve_runner(a):
    """Orca first (references/delivery.md section 5): settle a.runner before any output. Orca is here when the
    session runs inside Orca and its runtime is reachable; the default runner is then orca (elsewhere print), and
    --runner agent there needs --orca-unavailable REASON."""
    reason = " ".join((a.orca_unavailable or "").split())
    if a.orca_unavailable is not None and a.runner != "agent":
        die("--orca-unavailable REASON goes with --runner agent only")
    if a.orca_unavailable is not None and not reason:
        die("--orca-unavailable needs a REASON")
    a.orca_unavailable = reason or None
    if a.runner not in (None, "agent"):
        return
    env = orca_cmd.in_orca_session()
    here = bool(env) and orca_cmd.orca_reachable()
    if a.runner is None:
        a.runner = "orca" if here else "print"
    elif here and not a.orca_unavailable:
        die(f"this session runs inside Orca ({env} is set) and the Orca runtime is reachable: use --runner orca "
            "(references/delivery.md section 5, Orca first). --runner agent here needs --orca-unavailable REASON, "
            "naming why Orca cannot run this session")


def emit(a, reg, agent, prompt, place, title, plan=None, note=None, role=None):
    """Print the session's dispatch: Orca worker-start, Agent-tool call or the plain prompt. `role` (planner, lead,
    review, qa or a grade) picks the model and effort (session_model) before anything is printed or written."""
    pipe = settings(reg)
    m = session_model(a, session_agent(a, agent), role)
    if a.runner == "orca":
        argv = orca_cmd.worker_start(orca_prompt(a, prompt, plan, note), pipe["agents"][agent]["orca_agent"], place,
                                     title=title, model=m["model"], effort=m["effort"])
        if place.get("new"):  # worker-start creates the worktree: a hidden repo would list it under "Hidden worktrees"
            show = place_show_line(place)
            if show:
                print(show)
        print(orca_cmd.quote(argv))
    elif a.runner == "agent":
        alias = model_policy.alias(a.policy, m["model"])
        if not alias:
            die(f"--runner agent: {m['model']} has no Agent-tool model alias (registry pipeline.models.agent_tool_alias: "
                "opus, sonnet or haiku); the Agent tool would run its default model, possibly outside the model scope. "
                "Nothing was dispatched. Use --runner orca or print, or add the alias.")
        prompt = (f"Model: {m['model']} ({m['role']} profile), planned effort {m['effort']}. The Claude Code Agent tool "
                  f"takes the model alias {alias} but cannot set an effort: this session runs at its default effort.\n" + prompt)
        print(f"factory-pipeline: --runner agent: model {alias or 'not settable'} ({m['model']}); effort {m['effort']} "
              "cannot be set through the Agent tool (the session runs at its default effort)", file=sys.stderr)
        # the Agent-tool fallback (no Orca) is Claude only: a fresh Claude session, whatever model the plan names;
        # a session planned for another model says so, and its review counts as SAME_MODEL
        if agent != AGENT_FALLBACK:
            prompt = (f"SAME_MODEL: this session was planned for {agent}; the Agent-tool fallback runs Claude only. Name "
                      f"SAME_MODEL in your report (a review verdict is recorded with --by {AGENT_FALLBACK} and counts as "
                      "SAME_MODEL).\n" + prompt)
            print(f"factory-pipeline: --runner agent starts a fresh Claude session for this {agent} session: SAME_MODEL",
                  file=sys.stderr)
            agent = AGENT_FALLBACK
        if a.orca_unavailable:
            prompt = (f"Orca unavailable: {a.orca_unavailable}. This session runs through the Claude Code Agent-tool "
                      "fallback (references/delivery.md section 5): name this reason in your report, and pass "
                      "--orca-unavailable with it to every factory-pipeline.py planner or dispatch you run with "
                      "--runner agent.\n" + prompt)
            print(f"factory-pipeline: --runner agent with Orca unavailable ({a.orca_unavailable}): the prompt names the "
                  "reason", file=sys.stderr)
        print(json.dumps(orca_cmd.agent_task(reg, agent, prompt, place, title, model=alias), indent=2))
    else:
        print(f"# agent: {agent}   model: {m['model']}   effort: {m['effort']}   worktree: {place['worktree']}"
              + (f"   base: {place.get('base')}" if place.get("base") else "")
              + (f"   ({place['reason']})" if place.get("reason") else ""))
        print(prompt)
    if not shutil.which(pipe["agents"][agent]["bin"]):
        print(f"factory-pipeline: `{pipe['agents'][agent]['bin']}` is not on PATH here: the {agent} worker may be "
              f"unavailable (fallback: references/delivery.md, report the review as SAME_MODEL)", file=sys.stderr)
    return agent


def implementer_of(pipe, plan, task, subtask=None, item=None):
    """(agent, why) a review or QA pairs against: the model `dispatch --phase implement` recorded for this task or
    subtask, else the planned routing with every agent available; never the current availability."""
    rec = pr.recorded(plan, task["id"], subtask, "implementer")
    if rec:
        return rec["agent"], "recorded implementer" + (f": {rec['why']}" if rec.get("why") else "")
    if not subtask:
        models = set(subtask_implementers(plan, task["id"]).values())
        if len(models) == 1:
            return models.pop(), "subtask implementers"
        if pr.xs_plan(plan, task):
            return xs_implementer(pipe), "tier XS: the run lead implements"
    agent, why = pr.planned(pipe, item or task)
    return agent, "planned implementer: " + why


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rubric_lines(policy, indent):
    """The registry rubric, one `- grade: sentence` line per grade."""
    return "".join(f"\n{indent}- {g}: {t}" for g, t in model_policy.rubric(policy).items())


def cmd_planner(a, reg):
    resolve_runner(a)
    pipe = settings(reg)
    a.policy = load_policy(reg)
    agent, why = pr.route(pipe, {"kind": "plan", "implementer": a.agent}, pr.available(pipe, None))
    print(f"model: plan -> {agent} ({why})", file=sys.stderr)
    prompt = ("You are the planner of a Factory delivery pipeline. Read-only: change no file except the plan file.\n"
              f"{subagent_rule(a, reg, 'planner', agent)}\n"
              f"Request: {a.request}\n"
              "1. Run the Factory route for the files the request will write and read the routed lead skill.\n"
              "2. Break the work into small tasks with disjoint owned paths; order dependent tasks with `deps`.\n"
              "   A repo with `worktrees: false` (Unity project) runs its tasks one after another: give each the full\n"
              "   implement -> review -> QA cycle before the next.\n"
              "   Grade each task light|standard|heavy with the rubric (registry pipeline.models.rubric) and write `grade`\n"
              "   and `grade_reason` (one line) per task; the grade picks the model and effort of its sessions:"
              + rubric_lines(a.policy, "   ") + "\n"
              f"3. Write plan.json ({SCHEMA}, docs/schemas/pipeline-plan.schema.json) and run\n"
              f"   `python3 -B ${{CLAUDE_PLUGIN_ROOT}}/scripts/factory-pipeline.py{' --registry none' if reg.get('_defaults') else ''} validate plan.json` until it prints OK.\n"
              "4. Report the plan path, waves, the models validate prints and any open question. Do not implement.")
    place = {"worktree": "current", "new": False, "reason": "planning is read-only: no worktree"}
    emit(a, reg, agent, prompt, place, "pipeline planner", note=f"Request: {a.request}", role="planner")
    return 0


def serial_predecessor(plan, reg, task):
    """The task that runs before `task` in the same no-worktree checkout (wave order, every plan alias of it), or None."""
    by_id = {t["id"]: t for t in plan["tasks"]}
    me = serial_key(plan, reg, task["repo"])
    seq = [tid for w in validate(plan, reg)["waves"] for tid in w if serial_key(plan, reg, by_id[tid]["repo"]) == me]
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


def excluded_by(path, exclusions):
    """A path overlaps an exclusion when either contains the other (subplan validate and dispatch --paths)."""
    return any(inside_owned(path, [x]) or inside_owned(x, [path]) for x in exclusions)


def orca_repo_visibility_hidden(repo):
    """True only when the read-only `orca repo list --json` shows externalWorktreeVisibility `hide` for the repo whose
    path is `repo`. Orca hides the worktrees it did not create (a `git worktree add`) from its sidebar in that case, even
    with lineage set. Show, inherit, absent, an unlisted repo or any orca failure: False (no opinion, never an error)."""
    exe = shutil.which("orca")
    if not exe or not repo:
        return False
    try:
        r = subprocess.run([exe, "repo", "list", "--json"], capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        rows = json.loads(r.stdout or "")["result"]["repos"] if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return False
    return isinstance(rows, list) and any(
        isinstance(x, dict) and norm_wt(x.get("path")) == norm_wt(repo) and x.get("externalWorktreeVisibility") == "hide"
        for x in rows)


def orca_repo_show_line(repo):
    """The `orca repo set ... --external-worktree-visibility show` line to print before a worktree add, or None."""
    if not orca_repo_visibility_hidden(repo):
        return None
    return orca_cmd.quote(["orca", "repo", "set", "--repo", f"path:{repo}", "--external-worktree-visibility", "show"])


def main_checkout(path):
    """The main checkout of the repo that holds `path` (first `git worktree list` record), else `path`."""
    trees, rc = git(path, "worktree", "list", "--porcelain")
    return trees.splitlines()[0][len("worktree "):] if not rc and trees and trees.startswith("worktree ") else path


def place_show_line(place):
    """The visibility line for a placement that creates a worktree (worker-start): the repo is `place['repo']` or the
    parent of a child placement. `orca repo list` holds the main checkout, so a repo path that is a linked worktree maps
    to its main checkout (as emit_lead_handoff does); an unknown repo gives None."""
    repo = str(place.get("repo") or "").removeprefix("path:")
    parent = str(place.get("child_of") or "").removeprefix("path:")
    return orca_repo_show_line(main_checkout(repo or parent) if (repo or parent) else None)


def emit_lead_handoff(reg, agent, prompt, place, branch, m):
    """Launch in an existing checkout or print a no-track git worktree creation first: the task
    lead is not an Orca worker of the run lead (Orca forbids nested workers, max depth 1). `m`: its model and effort."""
    entry = settings(reg)["agents"][agent]
    flags = orca_cmd.model_flags(m["model"], m["effort"])
    if place.get("new"):
        checkout = place["repo"][len("path:"):]
        path = os.path.join(os.path.dirname(place.get("parent") or checkout), branch.replace("/", "-"))
        main = main_checkout(checkout)
        show = orca_repo_show_line(main)
        if show:  # Orca hides a worktree it did not create when the repo's external worktree visibility is hide
            print(show)
        print(orca_cmd.quote(["git", "-C", checkout, "worktree", "add", "--no-track", "-b", branch, path, place["base"]]))
        print(orca_cmd.quote(["orca", "worktree", "set", "--worktree", f"path:{path}", "--parent-worktree",
                              f"path:{place.get('parent') or main}", "--display-name", branch.replace("/", "-"),
                              "--workspace-status", "in-progress"]))
        place = {"worktree": f"path:{path}"}
    argv = ["orca", "agent", "launch", "--agent", entry["orca_agent"], "--worktree", place["worktree"], "--prompt", prompt,
            *flags, "--json"]
    print(orca_cmd.quote(argv))
    if not shutil.which(entry["bin"]):
        print(f"factory-pipeline: `{entry['bin']}` is not on PATH here: the {agent} task lead may be unavailable",
              file=sys.stderr)


def spec_json(spec):
    """The task spec as JSON with one key per line (short specs: a list stays on its key's line)."""
    return "{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in spec.items()) + "\n}"


def known_failing_text(plan):
    """The plan's `known_failing` block for a lead or QA prompt; '' when the plan lists none."""
    kf = [e for e in plan.get("known_failing") or [] if isinstance(e, dict)]
    if not kf:
        return ""
    return ("Known failing at base (plan known_failing):\n"
            + "\n".join(f"- {e.get('check')}: {e.get('reason')}" for e in kf)
            + "\nA failure of a listed check that also fails at the task base is FAIL_AT_BASE: name it on the QA report's "
              "'Failing at base' line, not as a task FAIL. A listed check that now passes is reported as fixed.")


def base_health_hint(info, spec):
    """The lead dispatch's one-line base health hint (stderr), or None: only for a repo with a GitHub remote (local
    git, never a network command) and a base branch name (a SHA base falls back to the repo's base branch)."""
    if not info.get("path"):
        return None
    out, rc = git(info["path"], "remote", "-v")
    if rc or "github.com" not in (out or ""):
        return None
    sha = re.compile(r"^[0-9a-fA-F]{7,40}$")
    branch = next((b for b in (spec.get("base"), info.get("base")) if b and not sha.match(b)), None)
    if not branch:
        return None
    return f"factory-pipeline: base health: run `gh run list --branch {branch} --limit 1` before starting"


def lead_prompt(plan, task, spec, info, impl, reviewer, where, report_to=None, policy=None, reg=None, subagents=None):
    """The task-lead spec: the task spec plus the short rules of the second level (references/delivery.md)."""
    me = orca_cmd.quote(pipeline_argv(reg or {}))
    pf = orca_cmd.quote([os.path.abspath(plan["_path"])])
    d = "<dispatch>"  # spelled out once, in the rules' first line
    run_id = report_to[len("run:"):] if report_to and report_to.startswith("run:") else report_to  # X or run:X
    child = ("placement child (an Orca child worktree): it commits on its child branch; merge that branch into "
             f"{spec['branch']} and remove the child at once (`orca worktree rm --worktree path:<child>`); "
             f"{orca_cmd.CHILD_RULE.split(';')[0]}." if info["worktrees"] else
             "placement is always shared here (no worktree).")
    rules = [
        f"<pipeline> = `{me}`; <plan> = `{pf}`; <dispatch> = `<pipeline> dispatch <plan> --task {task['id']}`.",
        f"1. Orca: create your OWN Run (`orca orchestration run-create --objective \"task {task['id']}\"`); every session "
        "below is its worker (Orca allows no nested workers). Outside an Orca session: --runner agent; inside Orca with "
        "the runtime unreachable: --runner agent --orca-unavailable REASON.",
        "2. Split into short subtasks with disjoint paths inside owned_paths (many short parallel sessions beat one long "
        f"one); write subplan.json (docs/schemas/pipeline-subplan.schema.json; `plan` is {os.path.abspath(plan['_path'])}, "
        f"`task` is {task['id']}) and run `<pipeline> subplan validate <subplan.json>` until it prints OK. Grade each "
        "subtask light|standard|heavy with the rubric below (registry pipeline.models.rubric) and write `grade` + "
        f"`grade_reason` per subtask (none: the task's grade, {spec.get('grade', 'standard')}); validate prints the model and "
        "effort each session runs with. Dispatch picks --model/--effort from the policy; never pass one outside its "
        "scope (exit 2).",
        f"3. Per subtask ONE fresh session in {where}: `{d} --phase implement --subplan <subplan.json> --subtask <id> "
        "--runner orca`. placement shared (default): it edits only its paths and does NOT commit (one shared index); "
        f"you commit it with explicit paths (`git add -- <paths>`, Conventional Commits). {child}",
        f"4. Candidate = HEAD with every subtask committed. Start one verify session `{d} --phase verify --sha <HEAD> "
        f"--runner orca` ({reviewer} for {impl}). Keep HEAD at the candidate. Record both results with "
        "`verdict --phase verify` (a FAIL names `--failed-at review`: no test ran, the next verify keeps the original "
        "tests; or `--failed-at qa [--failed-suites ...]`). On FAIL start a fresh fix session, then a fresh verify on the new HEAD. "
        "For tier S and docs-only tasks, the lead runs the tier command after the review and records QA.",
        "5. Release each session the moment it reports, its candidate is superseded or it stops - not at task end: "
        "`orca orchestration worker-release --dispatch <id>`; `<pipeline> status <plan> --orca-run <your run id>` lists the "
        "unreleased ones.",
        f"6. Record verdicts with `<pipeline> verdict <plan> ...`. Write your report to a file and record it with "
        f"`<pipeline> report <plan> --task {task['id']} --sha <HEAD> --body-file <file>` (the run lead's `status` shows it "
        "and READY_FOR_PR; a message alone can be lost), then report to the run lead (`orca orchestration send --to "
        f"run:{run_id or '<run lead run id>'} --type status --subject \"task done: {task['id']}\" --body <report>`): branch "
        f"{spec['branch']}, HEAD SHA, your Orca Run id, subtasks with commits, review and QA verdicts (state, SHA, model), "
        "checks with exact counts (or NOT_RUN with reason), limitations, out-of-scope findings.",
        f"7. {subagents}" if subagents else None,
        ("8. Never push, tag, merge into the integration branch or remove the task worktree: the run lead integrates "
         "and cleans up." if info["worktrees"] else
         "8. Never push, merge or tag: the run lead integrates; the main checkout is never removed."),
    ]
    return (f"Task lead for task {task['id']} of plan {plan['id']} ({plan['title']}), references/delivery.md. You own "
            f"this task and {where}; the run lead owns the plan, integration and cleanup.\n"
            + spec_json(spec) + "\nRules:\n" + "\n".join(r for r in rules if r)
            + ("\n" + known_failing_text(plan) if known_failing_text(plan) else "")
            + ("\nGrade rubric:" + rubric_lines(policy, "") if policy else "")
            + (f"\nNo worktree: {info['reason']}. Work in {info['path']} on branch {spec['branch']}; never create a "
               "worktree. Start after the previous task of this repo has its QA verdict. Subtasks, review and QA run "
               "one after another in this checkout; a Unity test run is an exclusive resource."
               if not info["worktrees"] else ""))


def runall_suites(path):
    """The suites `tests/run-all.sh --list-suites` prints in the checkout; None when run-all lacks that flag (an
    older run-all ignores unknown flags and would start a full run, so the flag must appear in the script first) or
    fails; False when the checkout has no tests/run-all.sh at all (a product repo: QA keeps its own checks)."""
    script = os.path.join(path or ".", "tests", "run-all.sh")
    if not os.path.isfile(script):
        return False
    try:
        with open(script, encoding="utf-8", errors="replace") as f:
            if "--list-suites" not in f.read():
                return None
        # Git Bash, never the System32 WSL launcher a bare "bash" resolves to on Windows
        r = subprocess.run([find_bash() or "bash", "tests/run-all.sh", "--list-suites"], cwd=path or ".",
                           capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


QA_TIERS = {"task": "affected", "integration": "ci+workspace"}  # fallback when the registry has no pipeline.qa_tiers


def affected_case_lines(path, base, sha, suites, explicit):
    """Report the checkout's own case selection; failure is advisory, never a dispatch failure."""
    script = os.path.join(path, "tests", "affected.py")
    if not os.path.isfile(script):
        return "Affected cases: not computed (tests/affected.py missing)"
    changed, rc = git(path, "diff", "--name-only", f"{base}...{sha}")
    if rc:
        return "Affected cases: not computed (git diff failed)"
    if suites is None or suites is False:
        return "Affected cases: not computed (suite list unavailable)"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            names = os.path.join(tmp, "changed.txt")
            with open(names, "w", encoding="utf-8", newline="\n") as f:
                f.write(changed + "\n" if changed else "")
            r = subprocess.run([sys.executable, "-B", script, "cases", names, *sorted(suites)], cwd=path,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode:
            return "Affected cases: not computed (tests/affected.py cases failed)"
        selected = {}
        for line in r.stdout.splitlines():
            suite, cases = line.split("\t", 1)
            selected[suite] = cases
        # run-all selects explicit suites even when unaffected, and never passes --case to them.
        selected.update({suite: "ALL" for suite in explicit})
        lines = [f"{suite} {'ALL' if cases == 'ALL' else '--case ' + cases}"
                 for suite, cases in sorted(selected.items())]
        return "Affected cases (tests/affected.py cases):\n" + "\n".join(lines)
    except (OSError, subprocess.SubprocessError, ValueError):
        return "Affected cases: not computed (tests/affected.py cases failed)"


def tier_command(level, base, suites, task=False):
    """The run-all command of a registry pipeline.qa_tiers level.
    Task QA never gets a full run, whatever the level: without a base it runs only the check suites."""
    only = " --only-suites " + shlex.quote(','.join(suites)) if suites else ""
    if task or level == "affected":
        if base:
            return "tests/run-all.sh --affected --base " + shlex.quote(base) + only + " -j 2"
        return ("tests/run-all.sh" + only + " -j 2" if suites else
                "NONE: the review base is missing; the task lead must give one "
                "(tests/run-all.sh --affected --base <base> -j 2). Never a full run.")
    if level == "ci+workspace":
        return "tests/run-all.sh --workspace-only"
    return "tests/run-all.sh --reuse -j 4"


def qa_body(sha, tasks, at_head=None, base=None, integration=False, failed_suites=None, small=False, runall=None,
            tiers=None, subagents=None):
    head = ((at_head or f"Candidate SHA: {sha}. First check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT.")
            + "\nRead-only unless a check writes its own build output. Check each acceptance criterion against the tree, ")
    tail = ("regressions, edge and failure cases. A Unity test run waits for the `unity-test` resource; never a second "
            "Editor.\nReport: templates/pipeline/qa-report.md, ending `VERDICT: PASS|FAIL|NOT_RUN|BLOCKED`.\nAcceptance:\n"
            + "\n".join(f"- [{t['id']}] {c}" for t in tasks for c in t.get("acceptance", [])))
    if runall is False:  # no tests/run-all.sh (a product repo): the task checks and the registry fast tier
        return (head + "run the checks (run-checks.py fast tier for registry repos), " + tail
                + "\nChecks:\n" + "\n".join(f"- [{t['id']}] {c}" for t in tasks for c in t.get("checks", []))
                + ("\nPreviously failed suites:\n" + "\n".join(f"- {s}" for s in failed_suites) if failed_suites else "")
                + (f"\n{subagents}" if subagents else ""))
    suites, extra, dropped = pr.qa_checks(tasks, runall, failed_suites)
    key = "integration" if integration else "task"
    command = tier_command((tiers or {}).get(key) or QA_TIERS[key], None if integration else base, suites,
                           task=not integration)
    policy = ("Integration QA: run the workspace checks before the PR; CI green is the full-suite gate after the PR opens."
              if integration and ((tiers or {}).get(key) or QA_TIERS[key]) == "ci+workspace" else
              "Integration QA: one full run per batch under the run-all lock; reuse a PASS record of the same clean tree."
              if integration else
              "Task QA: never a full tests/run-all.sh run; CI is the full-suite gate. "
              "Run each selected suite once: affected suites and explicit check suites are deduplicated.")
    if small:
        policy += (" Tier S: no separate QA session is needed. The task lead may run this command after review PASS "
                   "and record verdict --phase qa --state PASS --by <lead model> --note 'tier S: lead ran task suites'.")
    if dropped and not integration:
        policy += " A full run-all check was dropped and folded into the tier command."
    return (head + "run the tier command and extra commands below, " + tail
            + "\n" + policy + "\nQA tier command:\n" + command
            + ("\nExtra commands:\n" + "\n".join(extra) if extra else "")
            + (f"\n{subagents}" if subagents else ""))


def child_at_head(sha, parent):
    return (f"Candidate SHA: {sha}. You run in an Orca child worktree of {parent} created at it: first check `git rev-parse "
            "HEAD` equals it; otherwise report NOT_INDEPENDENT and stop. Commit nothing; the owner removes the child "
            f"({orca_cmd.CHILD_RULE.split(';')[0]}).")


def load_subtask(a, plan, reg, task):
    """The subtask --subtask of the subplan --subplan (a valid subplan of this task), or None without them."""
    if not (a.subplan or a.subtask):
        return None
    if not (a.subplan and a.subtask):
        die("--subplan and --subtask go together")
    if a.phase == "lead" or a.task.startswith("integration:"):
        die("--subplan/--subtask go with --phase implement|review|qa of a plan task")
    sub = read_json_file(a.subplan, "subplan")
    path = subplan_plan_path(sub, a.subplan)
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.realpath(plan["_path"])):
        die(f"subplan {a.subplan} splits plan {path}, not {plan['_path']}")
    out = validate_subplan(sub, plan, reg)
    if out["task"] != task["id"]:
        die(f"subplan {a.subplan} splits task {out['task']}, not {task['id']}")
    if out["errors"]:
        die(f"subplan is invalid; run `subplan validate {a.subplan}`: {out['errors'][0]}", 1)
    s = next((x for x in sub["subtasks"] if x.get("id") == a.subtask), None)
    if s is None:
        die(f"unknown subtask {a.subtask}: subplan has {', '.join(x['id'] for x in sub['subtasks'])}")
    return s


def xs_task_tier(pipe, plan, task, info, base):
    """(checkout, task tier command, runs run-all) of a tier XS task: the run lead runs it in its plan.topic checkout
    (else the repo checkout); a product repo without tests/run-all.sh gets its task checks and the fast tier instead."""
    path = info["path"] or "<repo checkout>"
    where = (worktree_for(info["path"], plan["topic"])[0] if info["path"] else None) or path
    suites = runall_suites(where) if os.path.isdir(where) else None
    if suites is False:  # a product repo: its task checks and the fast tier
        return where, ("the task checks (run-checks.py fast tier for registry repos): "
                       + ("; ".join(task.get("checks") or []) or "none listed")), False
    return where, tier_command((pipe.get("qa_tiers") or {}).get("task") or QA_TIERS["task"], base,
                               pr.qa_checks([task], suites)[0], task=True), True


def xs_qa_record(cmd, pf, task, lead, sha):
    """The run lead's QA record of a tier XS task (the gate takes it as the integration QA at plan.topic's HEAD)."""
    return (f"{cmd} verdict {pf} --task {task['id']} --phase qa --sha {sha} --state PASS --by {lead} "
            "--note \"tier XS: lead ran task suites\"")


def xs_lead_steps(a, reg, pipe, plan, task, info, base):
    """What `dispatch --phase lead` prints for a tier XS task instead of starting a task lead: the run lead's own steps."""
    lead = xs_implementer(pipe)
    cmd = orca_cmd.quote(pipeline_argv(reg))
    pf, tid, topic = shlex.quote(a.plan), task["id"], plan["topic"]
    where, tier, _ = xs_task_tier(pipe, plan, task, info, base)
    paths = " ".join(shlex.quote(p) for p in task["paths"])
    return "\n".join([
        f"Tier XS: task {tid} starts no task lead, task worktree or implement session; the run lead ({lead}) edits it.",
        f"1. In {where} on the plan topic branch {topic} (new: `git switch --no-track -c {topic} {base}`), edit only "
        f"the owned paths: {', '.join(task['paths'])}.",
        f"2. Commit with explicit paths: `git add -- {paths}`, then `git commit -m '<type>(<scope>): ...'`; that "
        "commit is <sha>.",
        f"3. One cross-model review (implementer: {lead}): {cmd} dispatch {pf} --task {tid} --phase review --sha <sha>",
        f"4. After the review PASS, run the task tier command in {where}: {tier}",
        f"5. Record the QA: {xs_qa_record(cmd, pf, task, lead, '<sha>')}",
        f"6. {cmd} gate {pf}",
    ])


SPEC_COMPLETE = ("Your spec is complete: read skills/delivery/references/delivery.md only when blocked by something "
                 "the spec does not cover.")


def cmd_dispatch(a, reg):
    resolve_runner(a)
    plan = read_plan(a.plan, reg)
    pipe = settings(reg)
    a.policy = load_policy(reg)
    plan["_path"] = a.plan
    v = validate(plan, reg)
    if v["errors"]:
        die("plan is invalid; run `validate` first: " + v["errors"][0], 1)
    if a.paths and a.phase != "implement":
        die("--paths (the subtask's paths) goes with --phase implement")
    if a.report_to and a.phase != "lead":
        die("--report-to (the run lead's Orca run id) goes with --phase lead")
    if a.phase == "qa" and a.task.startswith("integration:"):
        if a.subplan or a.subtask:
            die("--subplan/--subtask go with --phase implement|review|qa of a plan task")
        key = a.task.split(":", 1)[1]
        tasks = [t for t in plan["tasks"] if t["repo"] == key]
        if not tasks:
            die(f"no task of the plan is in repo {key}")
        info = repo_info(plan, reg, key)
        if a.placement == "child" and not info["worktrees"]:
            die(f"--placement child: repo {key} takes no worktree ({info['reason']}); nothing was printed")
        if not a.sha:
            die("qa needs --sha <candidate commit>")
        impls = {implementer_of(pipe, plan, t) for t in tasks}
        avail = pr.available(pipe, plan)
        agent, why = (pr.choose(a.agent, "explicit --agent", avail) if a.agent else
                      pr.roles(pipe, {}, avail, next(iter(impls)))["qa"] if len({i[0] for i in impls}) == 1 else
                      pr.choose(pipe.get("qa_prefer", "codex"), "integration qa_prefer", avail))
        print(f"model: qa -> {agent} ({why})", file=sys.stderr)
        at_head, home = None, None
        if info["worktrees"]:
            # the integrated tree is the checkout of plan.topic (where the run lead merges): QA joins it or a child of it
            home = worktree_for(info["path"], plan["topic"])[0] if info["path"] else None
            if not home:
                die(f"integration QA: no worktree of {info['path']} has the integration branch {plan['topic']} checked out. "
                    "Check it out where the run lead integrates, then dispatch the QA again. No worktree was created.", 1)
            if a.placement == "child":
                place = orca_cmd.child_placement(child_branch(plan["topic"], None, "qa", a.sha), a.sha, home)
                at_head = child_at_head(a.sha, home)
            else:
                place = {"worktree": f"path:{home}", "new": False, "reason": "the integration checkout"}
                at_head = (f"Candidate SHA: {a.sha}. You share the integration checkout {home} with the run lead: first "
                           "check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT and stop. Never check "
                           "out, stage, commit or stash.")
        else:
            place = orca_cmd.placement(reg, info["registry"], info["path"], a.sha, f"{plan['topic']}-qa")
            # one checkout, every plan alias of it: integration QA waits for each task's own QA (as status does)
            me = serial_key(plan, reg, key)
            group = [t["id"] for t in plan["tasks"] if serial_key(plan, reg, t["repo"]) == me]
            open_ = [tid for tid in group if len(group) > 1
                     and (verdict_of(plan, reg, tid, "qa")[0] or {}).get("state") != "PASS"]
            if open_:
                print(f"factory-pipeline: {key} takes one task at a time: task {', '.join(open_)} has no QA PASS yet; "
                      "start the integration QA after it", file=sys.stderr)
        prompt = (f"QA worker for plan {plan['id']} ({plan['title']}), repo {key}, branch {plan['topic']}, integrated tree.\n"
                  + SPEC_COMPLETE + "\n"
                  + qa_body(a.sha, tasks, at_head, integration=True, runall=runall_suites(home or info["path"]),
                            tiers=pipe.get("qa_tiers"), subagents=subagent_rule(a, reg, "qa", agent))
                  + (f"\nNo worktree: {info['reason']}. Work in {info['path']} on {plan['topic']}." if not info["worktrees"] else "")
                  + ("\n" + known_failing_text(plan) if known_failing_text(plan) else ""))
        emit(a, reg, agent, prompt, place, f"qa {plan['id']} {key}", plan, role="qa")
        child_note(place)
        return 0
    task = find_task(plan, a.task)
    info = repo_info(plan, reg, task["repo"])
    impl = pr.route(pipe, task, pr.available(pipe, plan))[0]
    sub = load_subtask(a, plan, reg, task)
    sid = sub["id"] if sub else None
    xs = pr.xs_plan(plan, task)  # tier XS: the run lead edits on plan.topic; no task lead, task worktree or implement
    # review and QA pair against the recorded (else planned) implementer; implement and lead forecast from availability
    # (tier XS: the run lead is the implementer in every phase)
    model_roles = pr.roles(pipe, sub or task, pr.available(pipe, plan),
                           implementer_of(pipe, plan, task, sid, sub) if a.phase in ("review", "qa", "verify") or xs
                           else None)
    for role, (model, why) in model_roles.items():
        print(f"model: {role} -> {model} ({why})", file=sys.stderr)
    placement = a.placement or (sub or {}).get("placement") or "shared"
    if placement == "child" and not info["worktrees"]:
        die(f"--placement child: repo {task['repo']} takes no worktree ({info['reason']}); nothing was printed")
    branch = plan["topic"] if xs else task_branch(plan, info, task)
    spec = {"plan": plan["id"], "task": task["id"], "repo": task["repo"], "objective": task["objective"],
            "owned_paths": task["paths"], "exclusions": task.get("exclusions", []), "deps": task.get("deps", []),
            "checks": task.get("checks", []), "acceptance": task["acceptance"], "branch": branch,
            "base": start_base(plan, info, task)}
    # the task's grade (plan, else derived from its tier) and the grade of this session's work (a subtask's own grade
    # wins): implement runs with that grade's profile, review with heavy for heavy work, else review
    grade = None
    if a.phase in ("lead", "implement", "review", "verify"):
        grade = task_grades(plan, reg, a.policy, [task])[task["id"]]["grade"]
        if a.phase != "lead" and (sub or {}).get("grade"):
            grade = sub["grade"]
        spec["grade"] = grade
        if a.phase == "lead" and task.get("grade_reason"):
            spec["grade_reason"] = task["grade_reason"]
    if a.phase in ("lead", "implement") and not info["worktrees"]:
        prev = serial_predecessor(plan, reg, task)
        if prev and (verdict_of(plan, reg, prev, "qa")[0] or {}).get("state") != "PASS":
            print(f"factory-pipeline: {task['repo']} takes one task at a time: task {prev} has no QA PASS yet; "
                  f"start {task['id']} after it", file=sys.stderr)
    if a.phase == "lead" and xs:
        print(xs_lead_steps(a, reg, pipe, plan, task, info, spec["base"]))
        return 0
    if a.phase == "implement" and xs:
        die(f"task {task['id']} is tier XS: no implement session; the run lead edits the owned paths itself on "
            f"{plan['topic']} (`dispatch --phase lead` prints the steps)")
    if a.phase == "lead":
        hint = base_health_hint(info, spec)
        if hint:
            print(hint, file=sys.stderr)
        reviewer = task.get("reviewer") or pipe["review_pairing"].get(impl)
        if not info["worktrees"]:
            place = orca_cmd.placement(reg, info["registry"], info["path"], spec["base"], branch)
            where = f"the main checkout {info['path']}"
        else:
            # the task worktree is created here on the task branch, from the base (a later wave: from plan.topic, which
            # carries the earlier waves); a later lead resumes in it
            home = worktree_for(info["path"], branch)[0]
            place = ({"worktree": f"path:{home}", "new": False, "reason": "task worktree exists: resume in it"} if home
                     else orca_cmd.placement(reg, info["registry"], info["path"], spec["base"], branch))
            if not home:
                # Place the new checkout beside the integration checkout, when present.
                parent = worktree_for(info["path"], plan["topic"])[0]
                if parent:
                    place["parent"] = parent
                    place["reason"] = f"beside the integration checkout {parent}"
            where = "this task worktree"
        lead = model_roles["lead"][0]
        prompt = lead_prompt(plan, task, spec, info, impl, reviewer, where, a.report_to, a.policy, reg,
                             subagent_rule(a, reg, "lead", lead))
        if a.agent and a.agent != lead:
            print(f"factory-pipeline: the task lead is {lead} ({model_roles['lead'][1]}); --agent {a.agent} "
                  f"is ignored for --phase lead (implement, review and QA keep their pairing)", file=sys.stderr)
        if a.runner == "orca":  # Orca has no nested workers: the task lead is a handoff with its own Run, not a worker
            # resolved before orca_prompt writes the spec: outside the scope, nothing is written
            m = session_model(a, lead, "lead")
            emit_lead_handoff(reg, lead, orca_prompt(a, prompt, plan), place, branch, m)
        else:
            emit(a, reg, lead, prompt, place, f"lead {plan['id']}/{task['id']}", role="lead")
        child_note(place)
        return 0
    if a.phase != "implement" and not a.sha:
        die(f"{a.phase} needs --sha <candidate commit>")
    paths = a.paths or ((sub or {}).get("paths") if sub else None)
    if paths:
        bad = [f"{p} {path_problem(p)}" for p in paths if path_problem(p)]
        if bad:
            die("--paths " + "; ".join(bad))
        outside = [p for p in paths if not inside_owned(p, task["paths"])]
        if outside:
            die(f"--paths {', '.join(outside)} outside the owned paths of task {task['id']}: {', '.join(task['paths'])}")
        excluded = [p for p in paths if excluded_by(p, task.get("exclusions") or [])]
        if excluded:
            die(f"--paths {', '.join(excluded)} overlap the exclusions of task {task['id']}: "
                f"{', '.join(task.get('exclusions') or [])}")
        spec["subtask_paths"] = paths
    elif a.phase == "implement" and a.agent and pr.choose(a.agent, "explicit", pr.available(pipe, plan))[0] != impl:
        die(f"task {task['id']} is planned for {impl}; set `implementer: {a.agent}` in the plan (the reviewer pairing "
            "follows it) instead of --agent (a subtask session with --paths may name its own model)")
    if sub:
        spec["subtask"] = sub["id"]
        spec["subtask_objective"] = sub.get("objective")
        for k in ("checks", "acceptance"):
            if sub.get(k):
                spec[f"subtask_{k}"] = sub[k]
        if placement == "child":
            spec["placement_reason"] = sub.get("reason")
    # implement, review and per-task QA join the task lead's worktree or an Orca child of it (a no-worktree repo: its
    # main checkout)
    home_reason = "the task lead's worktree"
    if xs:  # review and QA read the run lead's topic checkout (else the repo checkout): there is no task worktree
        topic_home = worktree_for(info["path"], plan["topic"])[0] if info["path"] else None
        home = topic_home or info["path"]
        home_reason = (f"tier XS: the run lead's checkout of {plan['topic']}" if topic_home
                       else "tier XS: the repo checkout (no task worktree)")
    else:
        home = task_worktree(plan, info, task, branch) if info["worktrees"] else None
    child_name = child_branch(branch, sub["id"] if sub else None, a.phase, a.sha)
    if placement == "child":
        joined = orca_cmd.child_placement(child_name, branch if a.phase == "implement" else a.sha, home)
    else:
        joined = {"worktree": f"path:{home}", "new": False, "reason": home_reason} if home else None
    if a.phase == "implement":
        spec.pop("checks", None)
        spec.pop("subtask_checks", None)
        sub_impl = (sub or {}).get("implementer") if sub else None
        agent = pr.choose(a.agent, "explicit --agent", pr.available(pipe, plan))[0] if a.agent else model_roles["implement"][0]
        place = joined or orca_cmd.placement(reg, info["registry"], info["path"], spec["base"], branch)
        edit = "the subtask_paths" if paths else "the owned paths"
        report = ("Report to the task lead: changed paths, each check with exact counts (or NOT_RUN with command and "
                  "reason), limitations, out-of-scope findings. Never merge or push.")
        checks = ("Run no test suites; only a syntax check of the files you edited (bash -n, python3 -m py_compile, "
                  "JSON parse). The task's verify session runs the tests once.\n")
        if placement == "child":
            # a child has its own index: the sub-session commits there and the task lead merges the child branch
            prompt = (f"Implementation sub-session of task {task['id']} in an Orca child "
                      f"worktree of {home}, on its own branch {child_name} from {branch}. Edit only {edit}. Commit on "
                      "your child branch with explicit paths (`git add -- <paths>`, Conventional Commits); the task lead "
                      f"merges it into {branch} and removes the child at once. {orca_cmd.CHILD_RULE.split(';')[0]}.\n"
                      f"{report} Name your child branch and HEAD SHA.\n{subagent_rule(a, reg, 'implement', agent)}\n"
                      + spec_json(spec))
        else:
            # a non-committing sub-session of the task lead, also in a no-worktree repo without --paths: only the task
            # lead commits (one shared index); there is no committing implementation worker in a shared checkout
            prompt = (f"Implementation sub-session of task {task['id']}. Work in "
                      f"{home or info['path']} on branch {branch}: never switch branches or create a worktree. Edit only "
                      f"{edit}. Do NOT commit, stage or stash: one shared index; the task lead commits.\n{report}\n"
                      f"{subagent_rule(a, reg, 'implement', agent)}\n" + spec_json(spec)
                      + (f"\nNo worktree: {info['reason']}. Never two sessions editing or importing the project at once."
                         if not info["worktrees"] else ""))
        prompt += "\n" + SPEC_COMPLETE + "\n" + checks
        why = "explicit --agent" if a.agent else model_roles["implement"][1]
        start = git(home or info["path"], "rev-parse", "--verify", "HEAD")[0]
        started = emit(a, reg, agent, prompt, place, f"implement {plan['id']}/{task['id']}" + (f"/{sub['id']}" if sub else ""), plan, role=grade)
        # an ad hoc --paths session of its own model (no subtask id) is a slice: the task's record keeps its implementer
        if a.runner != "print" and (sub or not (a.paths and a.agent)):
            pr.record(plan, task["id"], sid, "implementer",
                      {"agent": started, "why": why if started == agent else f"--runner agent runs {started}",
                       "paths": paths or task["paths"],
                       "start": start,
                       "timestamp": now_utc()})
        child_note(place)
        return 0
    if placement == "child":
        at_head = child_at_head(a.sha, home)
    elif xs:
        at_head = (f"Candidate SHA: {a.sha}. Tier XS: the run lead committed it on {plan['topic']}; you read its checkout "
                   f"{home}: first check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT and stop. Never "
                   "check out, stage, commit or stash." if topic_home else None)
    else:
        at_head = (f"Candidate SHA: {a.sha}. You share the task worktree {home} with the task lead, who keeps HEAD at "
                   "the candidate: first check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT and stop. "
                   "Never check out, stage, commit or stash." if home else None)
    sub_impl = model_roles["implement"][0]
    agent = pr.choose(a.agent, "explicit --agent", pr.available(pipe, plan))[0] if a.agent else model_roles["review" if a.phase == "verify" else a.phase][0]
    place = joined or {"worktree": f"path:{info['path']}", "new": False, "reason": info["reason"]}
    title = f"{a.phase} {plan['id']}/{task['id']}" + (f"/{sub['id']}" if sub else "")
    if a.phase == "qa":  # per-task QA: in the task worktree (or a child of it), or the main checkout of a no-worktree repo
        base, _ = review_base(info, plan["topic"], spec["base"], a.sha)
        previous = fstate.read_json(verdict_file(plan, task["id"], "qa", sid))
        stale = previous and previous.get("fingerprint") != scope_fingerprint(plan, reg, task["id"])
        failed = []
        if (previous and not stale and previous.get("state") == "FAIL" and previous.get("failed_suites")
                and previous.get("sha") != git(info["path"], "rev-parse", a.sha)[0]):
            base, failed = previous["sha"], previous["failed_suites"]
        suites = runall_suites(home or info["path"])
        explicit, _, _ = pr.qa_checks([task], suites, failed)
        cases = affected_case_lines(home or info["path"], base, a.sha, suites, explicit)
        prompt = (f"QA worker for plan {plan['id']} ({plan['title']}), repo {task['repo']}, branch {branch}, task {task['id']}"
                  + (f", subtask {sub['id']}" if sub else "") + ".\n" + SPEC_COMPLETE + "\n"
                  + qa_body(a.sha, [task], at_head, base=base, failed_suites=failed, small=pr.small_task(plan, task),
                            runall=suites, tiers=pipe.get("qa_tiers"), subagents=subagent_rule(a, reg, "qa", agent))
                  + "\n" + cases + ("\nThe tier command already passes these cases: run-all gives affected-only suites with a case map --case."
                                      if cases.startswith("Affected cases (tests/affected.py cases):") else "")
                  + ("\nSubtask: " + spec_json({k: v for k, v in spec.items() if k.startswith("subtask")}) if sub else "")
                  + (f"\nNo worktree: {info['reason']}. Work in {info['path']} on {branch}." if not info["worktrees"] else "")
                  + ("\n" + known_failing_text(plan) if known_failing_text(plan) else ""))
        emit(a, reg, agent, prompt, place, title, plan, role="qa")
        child_note(place)
        return 0
    if agent == sub_impl:
        print(f"factory-pipeline: reviewer {agent} is the implementer's model: the verdict counts as SAME_MODEL", file=sys.stderr)
    base, base_note = review_base(info, plan["topic"], spec["base"], a.sha)
    plugin_repo = task["repo"] == "plugin" or (info["path"] and os.path.isfile(
        os.path.join(info["path"], ".claude-plugin", "plugin.json")))
    checklist = ("skills/factory-core/references/plugin-review.md" if plugin_repo
                 else "the routed lead skill's review checklist")
    failed, retry = [], False
    if a.phase == "verify":
        previous = fstate.read_json(verdict_file(plan, task["id"], "qa", sid))
        if (previous and previous.get("fingerprint") == scope_fingerprint(plan, reg, task["id"])
                and previous.get("state") == "FAIL"
                and previous.get("sha") != git(info["path"], "rev-parse", a.sha)[0]):
            base, failed, retry, base_note = previous["sha"], previous.get("failed_suites", []), True, "fix delta since previous candidate"
    prompt = (f"Review worker ({agent}) for code written by {sub_impl}"
              + (f" (subtask {sub['id']}; record with `verdict --subtask {sub['id']}`)" if sub else "")
              + (". Read-only: edit nothing, commit nothing. Review before running tests.\n" if a.phase == "verify"
                 else ". Read-only: edit nothing, commit nothing. Run no suites; only a minimal repro when needed.\n")
              + SPEC_COMPLETE + "\n" + subagent_rule(a, reg, "review", agent) + "\n"
              + (at_head + "\n" if at_head else f"Candidate SHA: {a.sha}. ")
              + f"Review the whole diff `git diff {base}...{a.sha}` (not only the owned paths)"
              + (f" ({base_note})" if base_note else "")
              + " against the spec: scope (a change outside the owned paths is a finding), correctness, safety rules, "
              + checklist + ", tests per behaviour change, conventions.\n"
              + spec_json(spec)
              + "\nReport: `path:line severity problem fix` per finding, then `VERDICT: PASS|FAIL`."
              + (f"\nNo worktree: {info['reason']}. Read the commits from {info['path']}; do not check out anything." if not info["worktrees"] else ""))
    if a.phase == "verify":
        suites = runall_suites(home or info["path"])
        selected_task = dict(task, checks=retry_checks(task, suites)) if retry else task
        explicit, _, _ = pr.qa_checks([selected_task], suites, failed)
        cases = affected_case_lines(home or info["path"], base, a.sha, suites, explicit)
        prompt += ("\nReview first. If any blocking finding exists, report FAIL and run no tests. "
                   "Otherwise run the following QA once.\n"
                   + qa_body(a.sha, [selected_task], at_head, base=base,
                             failed_suites=failed, small=pr.small_task(plan, task), runall=suites,
                             tiers=pipe.get("qa_tiers")) + "\n" + cases
                   + ("\n" + known_failing_text(plan) if known_failing_text(plan) else ""))
    fallback = "SAME_MODEL" in model_roles["review"][1] and agent == model_roles["review"][0]
    if fallback:
        prompt = model_roles["review"][1] + "\n" + prompt
    started = emit(a, reg, agent, prompt, place, title, plan, role=review_role(grade))
    full, rc = git(info["path"] or ".", "rev-parse", "--verify", "--quiet", a.sha + "^{commit}")
    sha = full if rc == 0 and full else a.sha
    # what verdict reads: a fallback is stamped only for this reviewer on this candidate, never from availability later
    if a.runner != "print":
        pr.record(plan, task["id"], sid, "reviewer",
                  {"agent": started, "sha": sha, "implementer": sub_impl,
                   "paths": paths or task["paths"],
                   "fallback": pr.paired(pipe, sub or task, sub_impl) if fallback and started == agent else None,
                   "timestamp": now_utc()}, sha)
    child_note(place)
    return 0


def retry_checks(task, runall=None):
    """The task checks a re-verify keeps. A repo with tests/run-all.sh: the run-all commands and the suites are
    dropped, the failed suites plus `--affected --base <previous candidate>` replace them; any other command
    (`python3 -B scripts/build-registry.py --check`) stays. A repo without it (a product repo): its check commands
    (`dotnet test ...`) all stay, because a failed_suites list cannot name them."""
    return [c for c in task.get("checks", [])
            if not pr.mentions_runall(c) and not (runall and pr.SUITE_CHECK.search(c))]


def child_branch(parent, sid, phase, sha=None):
    """An Orca child's name (and branch) under `parent`: `<parent>--<subtask>` for an implement session (the task lead
    merges that branch), `<parent>--[<subtask>--]<phase>-<sha7>` for review and QA, so the review and the QA of one
    candidate, or of a subtask whose implement child still exists, never collide in Orca."""
    if phase == "implement":
        return f"{parent}--{sid or phase}"
    return f"{parent}--" + (f"{sid}--" if sid else "") + f"{phase}-{str(sha)[:7]}"


def child_note(place):
    """A child worktree command also says the rule on stderr (stdout carries only the commands to run: the repo visibility line when Orca hides it, then the one launch command)."""
    if place.get("worktree") == "new-child":
        where = (f"run the command from {place['child_of']} (Orca makes the child of the worktree it runs in); "
                 if place.get("child_of") else "")
        print(f"factory-pipeline: child worktree ({place.get('reason')}): {where}{orca_cmd.CHILD_RULE} "
              "(`orca worktree rm --worktree path:<child>`)", file=sys.stderr)


# ---------------------------------------------------------------- verdicts

PLANNER_DIR = "_planner"  # the planner's specs: reserved, `validate` rejects a plan id that maps to it


def plan_dir_name(plan_id):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(plan_id))


def verdict_dir(plan):
    return os.path.join(fstate.persistent(), "pipeline", plan_dir_name(plan["id"]))


def safe_name(x):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(x))


SUB_SEP = "@"  # <task>@<subtask>: no task id contains it (ID_RULE), so no task's file name collides with a subtask's
LEGACY_SUB = "__sub-"  # older records: <task>__sub-<subtask>, which task id "<task>__sub-<subtask>" also produced


def verdict_file(plan, task, phase, subtask=None):
    """The current verdict of a task phase: <task>__<phase>.json; a subtask's own review or QA (--subtask) lives apart
    from the task's: <task>@<subtask>__<phase>.json."""
    sub = f"{SUB_SEP}{safe_name(subtask)}" if subtask else ""
    return os.path.join(verdict_dir(plan), f"{safe_name(task)}{sub}__{phase}.json")


def candidate_file(plan, task, phase, sha, by, subtask=None):
    """Every verdict is also kept per candidate: <task>__<phase>__<sha12>__<by>.json (a subtask: <task>@<id>__...)."""
    sub = f"{SUB_SEP}{safe_name(subtask)}" if subtask else ""
    return os.path.join(verdict_dir(plan), f"{safe_name(task)}{sub}__{phase}__{sha[:12]}__{safe_name(by)}.json")


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


def subtask_failures(plan, reg, task_id, target):
    """The subtask review/QA verdicts of a task that are not PASS on the target (the commit being graded: the
    integration HEAD in the gate, the task candidate in status): each blocks the gate and status. Every record of this
    version of the plan counts (the current file and the per-candidate archives; STALE records are ignored), but only
    when its commit is the target or an ancestor of it: a PASS on a fix left on an unmerged child branch never resolves
    a FAIL. Per subtask and phase, a candidate's own verdict is its current record (else its latest archive, a tie keeps
    the non-PASS) and only applicable candidates that no other applicable one contains decide: a PASS on a newer commit
    resolves an older FAIL, a late PASS on an older candidate never resolves a newer FAIL. New-style records supersede
    legacy records for the same subtask and phase."""
    vdir = verdict_dir(plan)
    # legacy <task>__sub-<id> records count only when their own task and subtask fields name this task's subtask: task
    # "<task>__sub-<id>" wrote the same names
    pres = (f"{safe_name(task_id)}{SUB_SEP}", f"{safe_name(task_id)}{LEGACY_SUB}")
    names = sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []
    fp, groups = None, {}
    for n in names:
        pre = next((x for x in pres if n.startswith(x)), None)
        if not pre or not n.endswith(".json"):
            continue
        rec = fstate.read_json(os.path.join(vdir, n))
        if (not isinstance(rec, dict) or rec.get("task") != task_id or not rec.get("subtask")
                or rec.get("phase") not in ("review", "qa") or not rec.get("sha")
                or not n.startswith(f"{pre}{safe_name(rec['subtask'])}__")):
            continue
        modern = f"{pres[0]}{safe_name(rec['subtask'])}__{rec['phase']}"
        fp = fp or scope_fingerprint(plan, reg, task_id)
        if pre == pres[1]:
            archive = re.compile(re.escape(modern) + r"__[0-9a-f]{12}__[^/]+\.json$")
            superseded = False
            for name in names:
                if name != modern + ".json" and not archive.fullmatch(name):
                    continue
                newer = fstate.read_json(os.path.join(vdir, name))
                if (isinstance(newer, dict) and newer.get("fingerprint") == fp
                        and newer.get("task") == task_id and newer.get("subtask") == rec["subtask"]
                        and newer.get("phase") == rec["phase"]):
                    superseded = True
                    break
            if superseded:
                continue
        if rec.get("fingerprint") != fp:
            continue
        current = n == f"{pre}{safe_name(rec['subtask'])}__{rec['phase']}.json"
        groups.setdefault((rec["subtask"], rec["phase"]), []).append((current, rec))
    if not groups:
        return []
    path = repo_info(plan, reg, find_task(plan, task_id)["repo"])["path"] or "."
    out = []
    for (sid, phase), recs in sorted(groups.items()):
        by_sha = {}
        for current, rec in recs:
            by_sha.setdefault(rec["sha"], []).append((current, rec))
        eff = {}
        for sha, rs in by_sha.items():
            if target and sha != target and not is_ancestor(path, sha, target):
                continue
            cur = [r for c, r in rs if c]
            eff[sha] = cur[0] if cur else max((r for _, r in rs),
                                              key=lambda r: (str(r.get("timestamp", "")), r.get("state") != "PASS"))
        tips = [sha for sha in eff if not any(o != sha and is_ancestor(path, sha, o) for o in eff)]
        for sha in sorted(tips):
            rec = eff[sha]
            if rec.get("state") != "PASS":
                out.append(f"subtask {sid} {phase} {rec.get('state')} at {sha[:10]} by {rec.get('by')} (fix it, then "
                           f"record `verdict --subtask {sid}` PASS on a commit that contains {sha[:10]})")
    return out


IMPL_TAIL = "__implementer.model.json"


def subtask_implementers(plan, task_id):
    """{subtask id: recorded implementer agent} from `dispatch --phase implement --subtask` records of a task."""
    vdir = verdict_dir(plan)
    pre = f"{safe_name(task_id)}{SUB_SEP}"
    out = {}
    for n in sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []:
        if n.startswith(pre) and n.endswith(IMPL_TAIL) and len(n) > len(pre) + len(IMPL_TAIL):
            rec = fstate.read_json(os.path.join(vdir, n))
            if isinstance(rec, dict) and rec.get("agent"):
                out[n[len(pre):-len(IMPL_TAIL)]] = rec["agent"]
    return out


def subtask_reviews(plan, reg, task_id, sid, target, stale=None, cache=None, checking=(), after=None):
    """PASS reviews on the target or an ancestor whose reviewed paths are unchanged."""
    vdir = verdict_dir(plan)
    pre = f"{safe_name(task_id)}{SUB_SEP}{safe_name(sid)}__review"
    path = repo_info(plan, reg, find_task(plan, task_id)["repo"])["path"] or "."
    fp, out = scope_fingerprint(plan, reg, task_id), []
    for n in sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []:
        if not (n == pre + ".json" or (n.startswith(pre + "__") and n.endswith(".json") and not n.endswith(".model.json"))):
            continue
        rec = fstate.read_json(os.path.join(vdir, n))
        if (isinstance(rec, dict) and rec.get("task") == task_id and rec.get("subtask") == sid
                and rec.get("phase") == "review" and rec.get("state") == "PASS" and rec.get("fingerprint") == fp
                and rec.get("sha") and (rec["sha"] == target or is_ancestor(path, rec["sha"], target))):
            if after and (rec["sha"] == after or not is_ancestor(path, after, rec["sha"])):
                continue
            paths = rec.get("paths") or recorded_subtask_paths(plan, task_id, sid) or find_task(plan, task_id)["paths"]
            scope = dict(find_task(plan, task_id), paths=paths, _subtasks=tuple(sorted((*checking, sid))))
            changed = uncovered_changes(plan, reg, scope, rec["sha"], target, cache=cache)
            if changed:
                if stale is not None:
                    stale.update(changed)
                continue
            out.append(rec)
    return out


def recorded_subtask_paths(plan, task_id, sid):
    """Recover legacy review scope from dispatch provenance or durable task subplans.

    Multiple definitions are unioned conservatively, never narrowed by choosing one.
    Unknown legacy scope retains the whole-task fallback in the caller.
    """
    provenance = pr.recorded(plan, task_id, sid, "implementer") or {}
    if provenance.get("paths"):
        return provenance["paths"]
    folder = os.path.join(verdict_dir(plan), safe_name(task_id))
    paths = set()
    task = find_task(plan, task_id)
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not (name.startswith("subplan") and name.endswith(".json")):
            continue
        doc = fstate.read_json(os.path.join(folder, name), {})
        if not isinstance(doc, dict) or doc.get("task") != task_id:
            continue
        for sub in doc.get("subtasks", []):
            if not isinstance(sub, dict) or sub.get("id") != sid:
                continue
            scope = sub.get("paths")
            if (isinstance(scope, list) and scope and all(isinstance(p, str) and not path_problem(p)
                    and inside_owned(p, task["paths"]) and not excluded_by(p, task.get("exclusions", [])) for p in scope)):
                paths.update(scope)
    return sorted(paths)


def review_implementer(pipe, plan, task, subtask=None, item=None, disp=None):
    """Resolve actual execution provenance before falling back to planned routing."""
    rec = pr.recorded(plan, task["id"], subtask, "implementer")
    if rec:
        return rec["agent"], "task dispatch" if not subtask else "subtask dispatch"
    models = set(subtask_implementers(plan, task["id"]).values()) if not subtask else set()
    if len(models) == 1:
        return models.pop(), "subtask implementers"
    if disp and disp.get("implementer") in pipe["agents"]:
        return disp["implementer"], "review dispatch"
    if not subtask and pr.xs_plan(plan, task):
        return xs_implementer(pipe), "tier XS: the run lead implements"
    return pr.planned(pipe, item or task)[0], "planned routing"


def uncovered_changes(plan, reg, task, sha, target, checking=(), cache=None):
    """Memoize attribution only within this evaluation; verdicts may change before the next gate."""
    cache = {} if cache is None else cache
    # Only checked descendants can exclude a later covering task. Earlier ancestors
    # cannot affect this result; retaining them would repeat every path through a DAG.
    by_id = {t["id"]: t for t in plan["tasks"]}
    blocked = tuple(sorted(tid for tid in checking if depends(by_id, tid, task["id"])))
    key = (task["id"], task["repo"], tuple(task["paths"]), sha, target, blocked, task.get("_subtasks", ()))
    if key not in cache:
        cache[key] = _uncovered_changes(plan, reg, task, sha, target, checking, cache)
    return list(cache[key])


def _uncovered_changes(plan, reg, task, sha, target, checking, cache):
    """Owned files changed since sha without current later-task review/QA coverage.

    A first-parent topic merge attributes only its introduced side commits. Direct
    topic edits and conflict resolutions changed against every parent have no owner.
    Recursion checks the covering review itself, so a post-review edit cannot hide
    behind an earlier task's review. Serial checkouts use their QA-delimited starts.
    A path whose content at target equals its content at sha is never changed, and the
    side commits of a merge of the repo's default branch (origin/<b>, else <b>, for b the
    plan base unless it is a SHA, the registry default_branch, then main) are nobody's
    task work: only that merge's own conflict resolutions count. A commit counts as
    default-branch work only when such a merge brought it in (a side commit not already
    in the merge's first parent); a first-parent topic commit made after the review stays
    task work even when it reached the default branch later through another PR (so a
    fast-forward of the topic to the default branch is STALE: fails safe).
    A task branch can sync the topic into itself (a merge whose non-first parents are all on
    the target's first-parent chain). What such a sync merge brings in is topic work the
    first-parent walk attributes on its own (direct topic commits and task merges), so
    counting it again on the task branch double-attributes it: only the sync merge's own
    conflict resolutions count, and a later task that owns them and depends on the task covers them.
    """
    info = repo_info(plan, reg, task["repo"])
    path = info["path"]
    if not is_ancestor(path, sha, target):
        return list(task["paths"])
    if sha == target:
        return []
    by_id = {t["id"]: t for t in plan["tasks"]}
    def files(a, b):
        out, rc = git(path, "diff", "--name-only", a, b, "--", *specs(task["paths"]))
        return set(out.splitlines()) if rc == 0 else set(task["paths"])
    def owns(t, f):
        return any(norm_path(p).rstrip("/") in ("", ".") or norm_path(f) == norm_path(p).rstrip("/")
                   or norm_path(f).startswith(norm_path(p).rstrip("/") + "/") for p in t["paths"])
    later = []
    for t in plan["tasks"]:
        if t["id"] in checking or not depends(by_id, t["id"], task["id"]) or not same_repo(plan, reg, t["repo"], task["repo"]):
            continue
        rv = verdict_of(plan, reg, t["id"], "review")[0]
        if not rv or rv.get("state") != "PASS" or not is_ancestor(path, rv["sha"], target):
            continue
        if uncovered_changes(plan, reg, t, rv["sha"], target, checking + (task["id"],), cache):
            continue
        qa = None
        if not info["worktrees"] and serial_count(plan, reg, task["repo"]) > 1:
            qa = verdict_of(plan, reg, t["id"], "qa")[0]
            if not qa or qa.get("state") != "PASS" or not is_ancestor(path, rv["sha"], qa["sha"]) or not is_ancestor(path, qa["sha"], target):
                continue
            if uncovered_changes(plan, reg, t, qa["sha"], target, checking + (task["id"],), cache):
                continue
        later.append((t, rv, own_start(plan, reg, info, t, rv["sha"])))
    # A sibling can supersede an earlier slice without a task merge. Require its
    # own current paired PASS, and credit only commits contained in that review.
    siblings = []
    if task.get("_subtasks"):
        pipe = settings(reg)
        for sid, impl in subtask_implementers(plan, task["id"]).items():
            if sid in task["_subtasks"]:
                continue
            start = (pr.recorded(plan, task["id"], sid, "implementer") or {}).get("start")
            if not start or not is_ancestor(path, start, target):
                continue
            want = pr.paired(pipe, find_task(plan, task["id"]), impl)
            for rec in subtask_reviews(plan, reg, task["id"], sid, target, cache=cache,
                                       checking=task["_subtasks"], after=sha):
                if rec.get("by") == want or (rec.get("by") == impl and fallback_matches(rec, want)):
                    paths = rec.get("paths") or recorded_subtask_paths(plan, task["id"], sid)
                    if paths:
                        siblings.append((dict(paths=paths), rec, start))
    bad = set()
    net_out, net_rc = git(path, "diff", "--name-only", sha, target, "--", *specs(task["paths"]))
    if net_rc == 0 and not (net_out or "").strip():
        return []
    net = set(net_out.splitlines()) if net_rc == 0 else None
    branches = [b for b in (info["base"], ((reg.get("repos") or {}).get(info["registry"] or task["repo"]) or {}).get("default_branch"), "main")
                if b and not re.fullmatch(r"[0-9a-f]{7,40}", b)]
    default_tip = next((t for b in dict.fromkeys(branches) for r in ("remotes/origin", "heads")
                        for t in [git(path, "rev-parse", "--verify", "--quiet", f"refs/{r}/{b}")[0]] if t), None)
    def merges_default(c):
        """c is a merge and all its parents but the first are on the default branch."""
        ps = (git(path, "show", "-s", "--format=%P", c)[0] or "").split()
        return len(ps) > 1 and all(is_ancestor(path, q, default_tip) for q in ps[1:])
    default_side = set()
    if default_tip:
        for m in (git(path, "rev-list", "--merges", f"{sha}..{target}")[0] or "").splitlines():
            ps = (git(path, "show", "-s", "--format=%P", m)[0] or "").split()
            if len(ps) > 1 and merges_default(m) and not is_ancestor(path, m, default_tip):  # not a PR merge on the default branch
                default_side.update((git(path, "rev-list", *ps[1:], "--not", ps[0])[0] or "").splitlines())
    def from_default(c):
        """c came in from the default branch: it is a commit a merge of the default branch brought in, or such a merge itself.
        A first-parent topic commit is task work even when it reached the default branch later through another PR."""
        return bool(default_tip) and (c in default_side or merges_default(c))
    chain, rc = git(path, "rev-list", "--first-parent", f"{sha}..{target}")
    if rc != 0:
        return list(task["paths"])
    topic_text, topic_rc = git(path, "rev-list", "--first-parent", target)
    if topic_rc != 0:
        return list(task["paths"])
    topic_chain = set((topic_text or "").splitlines())
    for merge in (chain or "").splitlines():
        if is_ancestor(path, merge, sha):
            continue
        parent_text, rc = git(path, "show", "-s", "--format=%P", merge)
        parents = (parent_text or "").split()
        if rc != 0 or not parents:
            return list(task["paths"])
        if len(parents) > 1:
            evil = git(path, "diff-tree", "--cc", "--name-only", "--no-commit-id", "-r", merge, "--", *specs(task["paths"]))
            if evil[1] != 0:
                return list(task["paths"])
            bad.update((evil[0] or "").splitlines())
            introduced, rc = git(path, "rev-list", *parents[1:], "--not", parents[0])
            if rc != 0:
                return list(task["paths"])
            commits = [] if from_default(merge) else (introduced or "").splitlines()
        else:
            commits = [merge]
        for commit in commits:
            if is_ancestor(path, commit, sha):
                continue
            parent_text, rc = git(path, "show", "-s", "--format=%P", commit)
            if rc != 0:
                return list(task["paths"])
            ps = (parent_text or "").split()
            if from_default(commit):
                if is_ancestor(path, commit, default_tip):
                    continue
                cc, rc = git(path, "diff-tree", "--cc", "--name-only", "--no-commit-id", "-r", commit, "--", *specs(task["paths"]))
                touched = set(cc.splitlines()) if rc == 0 else set(task["paths"])
            elif len(ps) > 1 and all(q in topic_chain for q in ps[1:]):
                cc, rc = git(path, "diff-tree", "--cc", "--name-only", "--no-commit-id", "-r", commit, "--", *specs(task["paths"]))
                touched = set(cc.splitlines()) if rc == 0 else set(task["paths"])
            else:
                touched = files(ps[0], commit) if ps else set(task["paths"])
            for f in touched:
                covered = any(owns(s, f) and is_ancestor(path, start, commit)
                              and not is_ancestor(path, commit, start)
                              and is_ancestor(path, commit, r["sha"]) for s, r, start in siblings)
                if covered:
                    continue
                for t, rv, start in later:
                    if not start or not owns(t, f) or not is_ancestor(path, commit, rv["sha"]) or is_ancestor(path, commit, start):
                        continue
                    if len(parents) > 1:
                        branch = task_branch(plan, info, t)
                        tip = git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0]
                        if not any(p in (tip, rv["sha"]) or is_ancestor(path, p, rv["sha"]) for p in parents[1:]):
                            continue
                    elif info["worktrees"]:
                        continue
                    covered = True
                    break
                if not covered:
                    bad.add(f)
    return sorted(bad if net is None else {f for f in bad if f in net})


def fallback_matches(rec, agent):
    """Accept dispatch/legacy agent IDs and explicit retrospective outage reasons."""
    return rec.get("fallback") in (agent, f"{agent} unavailable")


def fallback_note(rec, agent):
    return f"SAME_MODEL (fallback: {agent} unavailable)" + (f"; note: {rec['note']}" if rec.get("note") else "")


def subtask_coverage(plan, reg, pipe, t, rv, impl, target, allow_same_model, cache=None):
    """Note code subtasks written by the verifier; one task review covers every subtask."""
    blockers, notes = [], []
    implementers = dict(rv.get("implementers", {}))
    implementers.update(subtask_implementers(plan, t["id"]))
    for sid, x in sorted(implementers.items()):
        if x == rv.get("by"):
            recorded = pr.recorded(plan, t["id"], sid, "implementer") or {}
            paths = recorded.get("paths") or t.get("paths", [])
            if not paths or not all(pr.prose_path(p) for p in paths):
                notes.append(f"{t['id']}: subtask {sid} SAME_MODEL (single verify)")
    return blockers, notes


def cmd_verdict(a, reg):
    if a.phase == "verify":
        if a.task.startswith("integration:"):
            die("verify verdicts are per task: --task <id>")
        from argparse import Namespace
        if a.failed_at and a.state != "FAIL":
            die("--failed-at goes with --phase verify --state FAIL")
        if a.state == "FAIL" and not a.failed_at:
            a.failed_at = "qa" if a.failed_suites is not None else None
            if not a.failed_at:
                die("verify --state FAIL needs --failed-at review (the review blocked, no test ran) or qa "
                    "(a test failed; add --failed-suites for suites)")
        if a.failed_at == "review" and a.failed_suites is not None:
            die("--failed-at review ran no tests: --failed-suites goes with a QA failure")
        if a.failed_suites is not None and a.state != "FAIL":
            die("--failed-suites goes with --phase qa --state FAIL")
        qa = Namespace(**vars(a))
        qa.phase, qa.implementer, qa.fallback = "qa", None, None
        review = Namespace(**vars(a))
        review.phase, review.failed_suites = "review", None
        if a.failed_at == "qa":
            review.state = "PASS"  # QA only ran after the review passed
        # review first: its arguments (--implementer, --fallback) are the ones that can still die
        result = cmd_verdict(review, reg)
        if result or a.failed_at == "review":
            # a review that blocked the candidate ran no tests: write no QA record, so the previous QA FAIL (its failed
            # suites and base) or the original base and checks still decide what the next verify runs
            if a.failed_at == "review" and not result:
                print("factory-pipeline: review FAIL ran no tests: QA stays NOT_RUN (no QA record written); the next "
                      "verify keeps the previous QA base and the task checks", file=sys.stderr)
            return result
        return cmd_verdict(qa, reg)
    plan = read_plan(a.plan, reg)
    pipe = settings(reg)
    if a.report and not os.path.isfile(a.report):
        die("--report must name an existing file; use --note TEXT for free text")
    if a.implementer and (a.phase != "review" or a.implementer not in pipe["agents"]):
        die("--implementer must name a pipeline agent and goes with --phase review")
    if a.state not in pipe["verdict_states"]:
        die(f"--state must be one of {', '.join(pipe['verdict_states'])}")
    if a.by not in pipe["agents"]:
        die(f"--by must be one of {', '.join(pipe['agents'])}")
    plan["_path"] = a.plan
    task = None
    if a.subtask and (a.task.startswith("integration:") or not id_ok(a.subtask)):
        die(f"--subtask is the id of a subtask of a plan task ({ID_RULE})")
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
           "timestamp": now_utc()}
    if a.note is not None:
        rec["note"] = a.note
    if a.failed_suites is not None:
        if a.phase != "qa" or a.state != "FAIL":
            die("--failed-suites goes with --phase qa --state FAIL")
        failed = sorted({s.strip() for s in a.failed_suites.split(',') if s.strip()})
        listed = None  # run-all's --list-suites, read only when a name is outside the (tests|testlab|scripts)/ form
        if any(pr.mentions_runall(s) for s in failed):
            die("--failed-suites never names tests/run-all.sh: a re-QA reruns failed suites, never a full run")

        def suite_ok(s):
            nonlocal listed
            if pr.failed_suite_ok(s):
                return True
            if listed is None:
                listed = runall_suites(repo_info(plan, reg, key)["path"]) or set()
            return s in listed
        if not failed or not all(suite_ok(s) for s in failed):
            die("--failed-suites needs comma-separated suites: names `tests/run-all.sh --list-suites` prints, "
                "or (tests|testlab|scripts)/ paths ending .sh or .py")
        rec["failed_suites"] = failed
    if a.subtask:
        rec["subtask"] = a.subtask
    if a.fallback is not None:
        if a.phase != "review":
            die("--fallback (the unavailable paired reviewer) goes with --phase review")
        unavailable = a.fallback.removesuffix(" unavailable")
        retrospective = a.fallback == f"{unavailable} unavailable"
        if unavailable not in pipe["agents"]:
            die(f"--fallback must be one of {', '.join(pipe['agents'])}")
        if retrospective and not a.subtask:
            die("retrospective --fallback requires --subtask; task reviews use dispatch-recorded fallback or current availability")
        if not retrospective and pr.available(pipe, plan).get(unavailable, {}).get("available"):
            others = [x for x in pipe["agents"] if x != unavailable]
            die(f"--fallback names the paired reviewer that is unavailable, but {unavailable} is available now, so it "
                "cannot be claimed as unavailable"
                + (f" (did you mean the other agent: --fallback '{others[0]} unavailable'?)" if len(others) == 1 else "")
                + f". Example: --fallback 'codex unavailable' --by claude --note TEXT when codex, the paired reviewer, was "
                "down and claude reviewed instead")
        if not (a.note and a.note.strip()):
            die("--fallback requires --note explaining the fallback")
        rec["fallback"] = f"{unavailable} unavailable"
    sub_item = load_subtask(a, plan, reg, task) if a.subplan else None
    if a.subtask:
        provenance = pr.recorded(plan, a.task, a.subtask, "implementer") or {}
        dispatched = pr.recorded(plan, a.task, a.subtask, "reviewer", full) or {}
        previous = fstate.read_json(verdict_file(plan, a.task, a.phase, a.subtask), {})
        if not isinstance(previous, dict) or previous.get("fingerprint") != rec["fingerprint"]:
            previous = {}
        rec["paths"] = ((sub_item or {}).get("paths") or dispatched.get("paths") or provenance.get("paths")
                        or previous.get("paths") or task["paths"])
    if task is not None and a.phase == "review":
        # a fallback only when this candidate's review dispatch was one and started this reviewer
        disp = pr.recorded(plan, a.task, a.subtask, "reviewer", full)
        # the implementer: the recorded one, else what this candidate's review dispatch paired against (routed over
        # the subtask), else the planned routing of the subtask (--subplan) or the task
        impl, source = review_implementer(pipe, plan, task, a.subtask, sub_item, disp)
        if a.implementer:
            recorded = pr.recorded(plan, a.task, a.subtask, "implementer")
            if recorded and recorded.get("agent") != a.implementer:
                die(f"--implementer {a.implementer} conflicts with recorded implementer {recorded.get('agent')} "
                    f"for {a.task}" + (f" subtask {a.subtask}" if a.subtask else ""))
            if not recorded and not a.subtask:
                # no task-level record: review_implementer takes the subtask records when they are unanimous
                models = set(subtask_implementers(plan, a.task).values())
                if len(models) == 1 and a.implementer not in models:
                    die(f"--implementer {a.implementer} conflicts with the recorded subtask implementer {next(iter(models))} "
                        f"for {a.task}: a task review pairs against it (record a task-level implement dispatch for "
                        f"{a.implementer}, or drop --implementer)")
            impl, source = a.implementer, "explicit"
        rec["implementer"] = impl
        rec["implementer_source"] = source
        rec["implementers"] = subtask_implementers(plan, a.task)
        if a.fallback is not None:
            # Gate subtask coverage pairs against the task too, including when
            # the supplied subplan declares its own reviewer.
            want = pr.paired(pipe, task, impl)
            if a.by != impl or not fallback_matches(rec, want):
                die(f"--fallback requires a SAME_MODEL review by implementer {impl} with fallback '{want} unavailable'")
        if (a.fallback is None and disp and disp.get("fallback") and disp["agent"] == a.by == impl
                and full.startswith(str(disp.get("sha")))):
            rec["fallback"] = disp["fallback"]
    for k in ("model", "effort"):  # what the session ran with (optional), so reports show it
        if getattr(a, k, None):
            rec[k] = getattr(a, k)
    kept = candidate_file(plan, a.task, a.phase, full, a.by, a.subtask)
    fstate.write_json(kept, rec, indent=2)
    path = verdict_file(plan, a.task, a.phase, a.subtask)
    if task is not None and a.phase == "review" and not a.subtask:
        # the task review the gate reads: a review by another model (a paired review of a Codex subtask recorded
        # without --subtask) never replaces the paired reviewer's record for the same candidate
        old = fstate.read_json(path)
        old_impl = (old.get("implementer") or review_implementer(pipe, plan, task)[0]) if isinstance(old, dict) else impl
        want = pr.paired(pipe, task, a.implementer or old_impl)
        new_pair = pr.paired(pipe, task, rec["implementer"])
        new_paired = a.by == new_pair or (a.by == rec["implementer"] and fallback_matches(rec, new_pair))
        if (not new_paired and isinstance(old, dict) and old.get("by") == want and old.get("sha") == full
                and old.get("fingerprint") == rec["fingerprint"]):
            print(f"factory-pipeline: kept the {want} review of {a.task} at {a.sha[:10]} (the task's paired reviewer); "
                  f"this {a.by} review is kept per candidate only: {kept}. A subtask review takes --subtask <id>.",
                  file=sys.stderr)
            return 0
    fstate.write_json(path, rec, indent=2)
    print(f"recorded {a.phase} {a.state} for {a.task}" + (f" subtask {a.subtask}" if a.subtask else "")
          + f" at {a.sha[:10]} by {a.by}" + "".join(f" {rec[k]}" for k in ("model", "effort") if k in rec) + f": {path}")
    return 0


# ---------------------------------------------------------------- gate

def worktree_records(path):
    """Every `git worktree list --porcelain` record of the repo (main checkout first): path, branch, prunable (the
    directory is gone but git still keeps the record)."""
    out, rc = git(path, "worktree", "list", "--porcelain")
    if rc != 0 or out is None:
        return []
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
        elif line == "prunable" or line.startswith("prunable "):
            cur["prunable"] = True
    return trees


def worktree_for(path, branch):
    trees = worktree_records(path)
    if not trees:
        return None, []
    home = next((t["path"] for t in trees if t.get("branch") == branch), None)
    return home, trees[1:]


def run_lead_files(plan, repo_path):
    """Repo-relative files the run lead owns on the integration branch: the plan file and its report (its own path when
    it sits inside the repo, else docs/plans/<id>.json); never task work and never stray."""
    names = {f"docs/plans/{plan.get('id')}.json"} if plan.get("id") else set()
    own = plan.get("_path")
    if own and repo_path:
        try:
            rel = os.path.relpath(os.path.realpath(own), os.path.realpath(repo_path)).replace("\\", "/")
        except ValueError:  # another drive
            rel = ".."
        if not rel.startswith("../") and rel != ".." and not os.path.isabs(rel):
            names.add(rel)
    names |= {os.path.splitext(n)[0] + "/report.md" for n in names}
    return {norm_path(n) for n in names}


def xs_diff_above(plan, reg, pipe, task, info, sha):
    """Why the committed diff of a tier XS task (`git diff <start>...<sha>`, the run lead's plan files left out) is above
    registry pipeline.tiers.XS: a path that is not prose, too many files or changed lines, a contract or generated path.
    Empty when it fits."""
    base, _ = review_base(info, plan["topic"], start_base(plan, info, task), sha)
    out, rc = git(info["path"], "diff", "--numstat", "--no-renames", f"{base}...{sha}")
    if rc != 0 or out is None:
        return [f"`git diff {base}...{sha[:10]}` failed"]
    lead_files = run_lead_files(plan, info["path"])
    rows = [r for r in out.splitlines() if r.count("\t") >= 2 and norm_path(r.split("\t", 2)[2]) not in lead_files]
    rule = pipe["tiers"].get("XS") or {}
    paths = [r.split("\t", 2)[2] for r in rows]
    return pr.above_xs(rule, paths, numstat_lines("\n".join(rows))) + xs_heavy(plan, reg, rule, task["repo"], paths)


def gate(plan, reg, allow_same_model=False, run_checks=True):
    coverage_cache = {}
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
            # every plan alias of this checkout shares the integration branch: their tasks' changes are not stray
            owned = [norm_path(p).rstrip("/") for t in plan["tasks"] if same_repo(plan, reg, t["repo"], key) for p in t["paths"]]
            lead_files = run_lead_files(plan, info["path"])
            stray = [f for f in (changed or "").splitlines() if norm_path(f) not in lead_files
                     and not any(o in ("", ".") or norm_path(f) == o or norm_path(f).startswith(o + "/") for o in owned)]
            if rc != 0 or stray:
                blockers.append(f"{key}: changes outside every task's owned paths: {', '.join(stray[:5]) or 'git diff failed'}")
        xs_task = next((t for t in plan["tasks"] if t.get("repo") == key and pr.xs_plan(plan, t)), None)
        if xs_task and not (fstate.read_json(verdict_file(plan, f"integration:{key}", "qa")) or {}).get("sha"):
            # tier XS: the run lead's own task QA on plan.topic is the QA of the integrated tree
            qa = read_verdict(plan, reg, xs_task["id"], "qa", blockers)
        else:
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
        blockers += [f"{t['id']}: {f}" for f in subtask_failures(plan, reg, t["id"], heads[key])]
        rv = read_verdict(plan, reg, t["id"], "review", blockers)
        if not rv:
            continue
        impl = rv.get("implementer") or review_implementer(pipe, plan, t, disp=pr.recorded(plan, t["id"], None, "reviewer", rv["sha"]))[0]
        want = pr.paired(pipe, t, impl)
        if rv.get("state") != "PASS":
            blockers.append(f"{t['id']}: review {rv.get('state')} at {rv.get('sha', '')[:10]}")
            continue
        if rv.get("by") != want:
            if rv.get("by") == impl and fallback_matches(rv, want):
                notes.append(f"{t['id']}: {fallback_note(rv, want)}")
            elif rv.get("by") == impl and allow_same_model:
                notes.append(f"{t['id']}: review SAME_MODEL ({impl}) accepted by --allow-same-model")
            else:
                blockers.append(f"{t['id']}: reviewed by {rv.get('by')}, cross-model review needs {want}"
                                + (" (or --allow-same-model when it is unavailable)" if rv.get("by") == impl else ""))
                continue
        if pr.xs_plan(plan, t):
            above = xs_diff_above(plan, reg, pipe, t, info, rv["sha"])
            if above:
                blockers.append(f"{t['id']}: tier XS, but the committed diff is above XS: " + "; ".join(above)
                                + " (plan it as tier S or M)")
        sub_blockers, sub_notes = subtask_coverage(plan, reg, pipe, t, rv, impl, heads[key], allow_same_model, coverage_cache)
        blockers += sub_blockers
        notes += sub_notes
        tq, tq_stale = verdict_of(plan, reg, t["id"], "qa")
        # QA eligibility is unchanged; only a tier S lead QA (no QA session) is limited to tier S tasks
        if tq and not tq_stale and tq.get("state") == "PASS" and (tq.get("note") or "").startswith("tier XS"):
            if pr.xs_plan(plan, t):
                notes.append(f"{t['id']}: tier XS lead ran task suites")
            else:
                blockers.append(f"{t['id']}: QA recorded as tier XS lead QA, but the task is not tier XS; "
                                "an S/M/L task gets its QA from its task lead or a QA session")
        if tq and not tq_stale and tq.get("state") == "PASS" and (tq.get("note") or "").startswith("tier S"):
            if pr.small_task(plan, t):
                notes.append(f"{t['id']}: tier S lead ran task suites")
            else:
                blockers.append(f"{t['id']}: QA recorded as tier S lead QA, but the task is not tier S; "
                                "an M/L task needs a QA session (dispatch --phase qa)")
        if not info["worktrees"] and serial_count(plan, reg, key) > 1:
            tq = read_verdict(plan, reg, t["id"], "qa", blockers)  # missing: "<id>: no qa verdict"
            if tq and tq.get("state") != "PASS":
                blockers.append(f"{t['id']}: QA {tq.get('state')} at {tq['sha'][:10]}")
            elif tq:
                _, rc = git(info["path"], "merge-base", "--is-ancestor", rv["sha"], tq["sha"])
                moved = uncovered_changes(plan, reg, t, tq["sha"], heads[key], cache=coverage_cache)
                if rc != 0:
                    blockers.append(f"{t['id']}: QA ran on {tq['sha'][:10]}, which does not contain the reviewed commit {rv['sha'][:10]}")
                elif moved:
                    blockers.append(f"{t['id']}: QA is STALE - owned paths changed after {tq['sha'][:10]}")
        _, rc = git(info["path"], "merge-base", "--is-ancestor", rv["sha"], heads[key])
        if rc != 0:
            blockers.append(f"{t['id']}: reviewed commit {rv['sha'][:10]} is not integrated into {plan['topic']}")
            continue
        changed = uncovered_changes(plan, reg, t, rv["sha"], heads[key], cache=coverage_cache)
        if changed:
            blockers.append(f"{t['id']}: review is STALE - owned paths changed after {rv['sha'][:10]}: "
                            + ", ".join(changed[:5]))
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
            commands.append("gh pr checks <pr> --watch   # CI green before merge; while CI runs, start the next task")
    state = "READY_FOR_PR" if ready else ("UNVERIFIED" if not blockers else "NOT_READY")
    return {"state": state, "deliver": plan.get("deliver", "none"),
            "blockers": blockers, "notes": notes, "heads": heads, "commands": commands}


def cmd_gate(a, reg):
    plan = read_plan(a.plan, reg)
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


# Orca worker accounting (`orca orchestration worker-list --json`): a worker whose dispatch settled still owns its
# terminal until it is released; terminal state `released` is done, any other state of a settled worker is a finding.
SETTLED_STATES = {"succeeded", "failed", "completed", "cancelled", "canceled", "stopped", "superseded", "abandoned",
                  "timed_out", "expired", "exited", "crashed"}


def orca_runs(plan, extra=None):
    """The task leads' Orca Run ids: each task's `orca_run` plus --orca-run, in order, without duplicates."""
    runs = [t.get("orca_run") for t in plan.get("tasks", []) if isinstance(t, dict)] + list(extra or [])
    runs = [r.strip()[len("run:"):] if r.strip().startswith("run:") else r.strip() for r in runs if isinstance(r, str)]
    return list(dict.fromkeys(r for r in runs if r))


def orca_workers(run):
    """(workers, None) from `orca orchestration worker-list --run RUN --full --json` (every page), or (None, why).
    --full: the concise row has only state/liveness/terminal/terminalState; the full row adds the resource (release
    state, ownership, release time), the projection and workerState/dispatchStatus."""
    exe = shutil.which("orca")
    if not exe:
        return None, "orca is not on PATH"
    workers, cursor = [], None
    for _ in range(50):
        argv = [exe, "orchestration", "worker-list", "--run", run, "--limit", "100", "--full", "--json"]
        if cursor:
            argv += ["--cursor", cursor]
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as e:
            return None, f"orca worker-list failed: {e}"
        try:
            doc = json.loads(r.stdout or "")
        except ValueError:
            doc = None
        if r.returncode != 0 or not isinstance(doc, dict) or doc.get("ok") is False or not isinstance(doc.get("result"), dict):
            why = " ".join(((r.stderr or "") + " " + (r.stdout or "")).split())[:200]
            return None, f"orca worker-list exited {r.returncode}" + (f": {why}" if why else "")
        res = doc["result"]
        workers += [w for w in res.get("workers") or [] if isinstance(w, dict)]
        page = res.get("page") if isinstance(res.get("page"), dict) else {}
        cursor = page.get("nextCursor") if page.get("hasMore") else None
        if not cursor:
            return workers, None
    return workers, None


def worker_settled(w):
    """The worker's dispatch settled. Full rows: projection.stage.detail, workerState, dispatchStatus; a concise row
    (no --full) carries only `state`."""
    stage = ((w.get("projection") or {}).get("stage") or {}) if isinstance(w.get("projection"), dict) else {}
    return (stage.get("detail") == "settled" or str(w.get("workerState", "")).lower() in SETTLED_STATES
            or str(w.get("dispatchStatus", "")).lower() in SETTLED_STATES
            or str(w.get("state", "")).lower() in SETTLED_STATES)


def worker_released(w):
    """The worker's terminal was released: the concise terminalState, the full resource (releaseState or ownershipState
    `released`, a releaseCompletedAt), or the projection's resource state."""
    res = w.get("resource") if isinstance(w.get("resource"), dict) else {}
    proj = (w.get("projection") or {}).get("resource") if isinstance(w.get("projection"), dict) else None
    return (w.get("terminalState") == "released" or res.get("releaseState") == "released"
            or res.get("ownershipState") == "released" or bool(res.get("releaseCompletedAt"))
            or (isinstance(proj, dict) and proj.get("state") == "released"))


def worker_no_terminal(w):
    """The worker owns no terminal: the full row's projection.resource.state is `absent` (reason not_materialized, or a
    failed terminal_create; resource, terminalState and the terminal handle are null). There is nothing to release."""
    proj = (w.get("projection") or {}).get("resource") if isinstance(w.get("projection"), dict) else None
    return isinstance(proj, dict) and proj.get("state") == "absent"


def orca_sessions(runs):
    """Per Run: settled workers that are not released, with the release command; NOT_AVAILABLE when orca cannot say.
    Read-only: worker-list only; a running worker is no finding, and an orca failure is never a failure here."""
    out = []
    for run in runs:
        workers, why = orca_workers(run)
        if workers is None:
            out.append({"run": run, "state": "NOT_AVAILABLE", "reason": why, "unreleased": [], "released": 0, "running": 0})
            continue
        unreleased, released, running = [], 0, 0
        for w in workers:
            res = w.get("resource") if isinstance(w.get("resource"), dict) else {}
            term = w.get("terminalState") or res.get("releaseState") or "unknown"
            if worker_released(w):
                released += 1
            elif not worker_settled(w):
                running += 1
            elif worker_no_terminal(w):
                continue    # settled without ever owning a terminal (terminal_create failed or never materialized): nothing to release
            else:
                did = str(w.get("dispatchId") or "?")
                note = res.get("retainedReason") or (f"release requested at {res['releaseRequestedAt']}"
                                                     if res.get("releaseRequestedAt") else None)
                unreleased.append({"dispatch": did, "worker": w.get("workerState") or w.get("state"), "terminal": term, "note": note,
                                   "command": orca_cmd.quote(["orca", "orchestration", "worker-release", "--dispatch", did])})
        out.append({"run": run, "state": "UNRELEASED" if unreleased else "OK", "reason": None, "unreleased": unreleased,
                    "released": released, "running": running})
    return out


def session_lines(sessions):
    """Text lines for cleanup and status: one per Run, one per unreleased worker."""
    lines = []
    for s in sessions:
        if s["state"] == "NOT_AVAILABLE":
            lines.append(f"NOT_AVAILABLE  run {s['run']}: {s['reason']} (worker release not checked)")
            continue
        lines.append(f"{s['state']}  run {s['run']}: {len(s['unreleased'])} settled worker(s) not released, "
                     f"{s['released']} released, {s['running']} running")
        for u in s["unreleased"]:
            lines.append(f"  UNRELEASED {u['dispatch']} ({u['worker']}, terminal {u['terminal']}"
                         + (f", {u['note']}" if u["note"] else "") + f"): {u['command']}")
    return lines


def orca_worktree_paths():
    """Normalised paths of every record in the read-only `orca worktree list --json`; None when orca cannot say
    (not on PATH, failing: no opinion, never an error)."""
    exe = shutil.which("orca")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "worktree", "list", "--limit", "10000", "--json"], capture_output=True, text=True,
                           timeout=60, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        rows = json.loads(r.stdout or "")["result"]["worktrees"] if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(rows, list):
        return None
    return {norm_wt(w["path"]) for w in rows if isinstance(w, dict) and w.get("path")}


def orca_terminals(path):
    """(handle, title) of the live Orca terminals bound to the worktree at `path` (read-only `orca terminal list`);
    [] when orca cannot say (no opinion)."""
    exe = shutil.which("orca")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "terminal", "list", "--worktree", f"path:{path}", "--limit", "100", "--json"],
                           capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL)
        rows = json.loads(r.stdout or "")["result"]["terminals"] if r.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    return [(str(t.get("handle") or "?"), str(t.get("title") or "")) for t in rows if isinstance(t, dict)]


# Processes and test slots: read-only. The run names what it sees (PID, command, start) and the user decides; nothing
# here stops a process or prints a command that would.
PS_LIST = ("Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{ pid = [int]$_.ProcessId; "
           "ppid = [int]$_.ParentProcessId; name = $_.Name; command = $_.CommandLine; "
           "started = $(if ($_.CreationDate) { $_.CreationDate.ToString('s') } else { '' }) } } | ConvertTo-Json -Compress")
PS_LINE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\w{3} \w{3}\s+\d+ [\d:]{8} \d{4})\s+(.*)$")


def process_table():
    """[{pid, ppid, name, command, started}] of the machine's processes, or None when it cannot be read (no opinion).
    RPG_FACTORY_PROCESS_TABLE=<json file> replaces the probe (tests): a list of such rows; `none` = cannot be read.
    Windows: PowerShell Get-CimInstance Win32_Process (20 s timeout); elsewhere `ps`."""
    fixture = os.environ.get("RPG_FACTORY_PROCESS_TABLE")
    if fixture:
        doc = fstate.read_json(fixture) if fixture != "none" else None
        return [r for r in doc if isinstance(r, dict)] if isinstance(doc, list) else None
    try:
        if os.name == "nt":
            exe = shutil.which("powershell") or shutil.which("pwsh")
            if not exe:
                return None
            r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", PS_LIST], capture_output=True,
                               text=True, timeout=20, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
            doc = json.loads(r.stdout or "") if r.returncode == 0 else None
            rows = [doc] if isinstance(doc, dict) else doc
            return [{"pid": d.get("pid"), "ppid": d.get("ppid"), "name": d.get("name") or "",
                     "command": d.get("command") or "", "started": d.get("started") or ""}
                    for d in rows if isinstance(d, dict)] if isinstance(rows, list) else None
        r = subprocess.run(["ps", "-eo", "pid=,ppid=,lstart=,args="], capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return None
        out = []
        for line in r.stdout.splitlines():
            m = PS_LINE.match(line)
            if m:
                cmd = m.group(4)
                out.append({"pid": int(m.group(1)), "ppid": int(m.group(2)),
                            "name": cmd.split(" ", 1)[0].rsplit("/", 1)[-1], "command": cmd, "started": m.group(3)})
        return out
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return None


def _canon(p):
    """A path in one spelling for matching: forward slashes, case-folded, and an MSYS (/c/x) or WSL (/mnt/c/x) drive
    path as c:/x (a run-all lock records the checkout as its shell sees it)."""
    p = str(p or "").replace("\\", "/").rstrip("/")
    m = re.match(r"^(?:/mnt)?/([A-Za-z])(/.*)?$", p)
    if m:
        p = f"{m.group(1)}:{m.group(2) or ''}"
    return p.casefold()


def plan_checkouts(plan, reg):
    """The checkouts of the plan's worktrees (task worktrees, integration checkout, children: branch <topic> or
    <topic>-*), plus the main checkout of a no-worktree repo. {canonical path: path}."""
    out, topic = {}, plan["topic"]
    for key in sorted({t["repo"] for t in plan.get("tasks", []) if t.get("repo")}):
        info = repo_info(plan, reg, key)
        if not info["path"] or not os.path.isdir(info["path"]):
            continue
        if not info["worktrees"]:
            out[_canon(info["path"])] = info["path"]
        for wt in worktree_records(info["path"]):
            br = str(wt.get("branch", ""))
            if br == topic or br.startswith(topic + "-"):
                out[_canon(wt["path"])] = wt["path"]
    return out


def read_slots():
    """[{slot, pid, winpid, checkout, started}] of the held test slots `tests/run-all.sh` publishes under
    <persistent state>/locks/run-all-slots/<n>/{pid,checkout,started,winpid}; [] when none."""
    root = os.path.join(fstate.persistent(), "locks", "run-all-slots")
    try:
        names = sorted(os.listdir(root), key=lambda n: (not n.isdigit(), int(n) if n.isdigit() else 0, n))
    except OSError:
        return []

    def get(d, f):
        try:
            with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                return fh.read().strip()
        except OSError:
            return ""
    out = []
    for n in names:
        d = os.path.join(root, n)
        if os.path.isdir(d) and get(d, "pid"):
            out.append({"slot": n, "pid": get(d, "pid"), "winpid": get(d, "winpid"), "checkout": get(d, "checkout"),
                        "started": get(d, "started")})
    return out


def slot_holders(plan, reg):
    """Test slots held by a run in one of the plan's checkouts: {slot, pid, checkout, started, alive} with alive True,
    False or None (cannot say). On Windows the slot's shell PID is an MSYS PID: the liveness check uses its winpid and
    is None without one. Read-only, never stops anything."""
    mine = plan_checkouts(plan, reg)
    held = [h for h in read_slots() if any(_canon(h["checkout"]) == c or _canon(h["checkout"]).startswith(c + "/")
                                           for c in mine)]
    if not held:
        return []
    table = process_table()
    for h in held:
        pid = h["winpid"] or (h["pid"] if os.name != "nt" else "")
        h["alive"] = None if table is None or not pid.isdigit() else any(str(r.get("pid")) == pid for r in table)
    return held


def slot_lines(holders):
    return [f"slot {h['slot']} held by PID {h['pid']}"
            + (f" (Windows PID {h['winpid']})" if h["winpid"] and h["winpid"] != h["pid"] else "")
            + f" in {h['checkout']} since {h['started'] or '?'}"
            + {True: " (alive)", False: " (not running)", None: " (liveness unknown)"}[h["alive"]]
            + ": the user decides, the run never stops it" for h in holders]


def _names_dir(cmd, form):
    """`form` (a canonical directory spelling) occurs in `cmd` followed by a path boundary, so x-gw does not name x-gw2."""
    text = cmd.replace("\\", "/").casefold()
    at = text.find(form)
    while at >= 0:
        end = at + len(form)
        if end >= len(text) or not (text[end].isalnum() or text[end] in "-_.+@~"):
            return True
        at = text.find(form, at + 1)
    return False


def busy_processes(directory):
    """Processes that may keep `directory` busy: their command line mentions it, and an orphaned `wsl.exe ... sleep
    infinity` (its parent process is gone). [{pid, name, command, started, why}]; [] when none or when the process
    table cannot be read (no opinion). Never stops anything."""
    table = process_table()
    if not table:
        return []
    want, pids, found = _canon(directory), {str(r.get("pid")) for r in table}, []
    forms = {want} | ({f"/mnt/{want[0]}{want[2:]}", f"/{want[0]}{want[2:]}"} if want[1:3] == ":/" else set())
    for r in table:
        cmd = str(r.get("command") or "")
        if str(r.get("pid")) == str(os.getpid()):
            continue
        if want and any(_names_dir(cmd, f) for f in forms):
            why = "its command line names the directory"
        elif (str(r.get("name") or "").casefold().startswith("wsl") and "sleep infinity" in cmd.casefold()
              and str(r.get("ppid")) not in pids):
            why = "orphaned wsl.exe sleep infinity (its parent process is gone)"
        else:
            continue
        found.append({"pid": r.get("pid"), "name": r.get("name") or "", "command": cmd[:300],
                      "started": r.get("started") or "", "why": why})
    return found


def busy_lines(directory, procs):
    return [f"process {p['pid']} ({p['name'] or '?'}) started {p['started'] or '?'}: {p['command'] or '?'} - {p['why']}; "
            f"it may keep {directory} busy: the user decides, the run never stops it" for p in procs]


BEFORE_REMOVAL = ("before a task worktree is removed no session may still use it: the task lead confirms that each "
                  "released worker's CLI exited (a released Codex worker: its codex process is gone); a process the "
                  "run did not start is named to the user (PID, command) and left to the user's decision, never "
                  "stopped by the run")
BUSY_NOTE = ("if `orca worktree rm` reports the directory busy (Windows: 'being used by another process'), a process "
             "holds it: name its PID and command to the user and leave the decision to them (cleanup lists the "
             "candidates it sees as BUSY? lines: PID, command, start time)")


def cleanup(plan, reg, orca_run=None, after_merge=False):
    """Worktrees and task branches the run left (names <topic>-*), with the commands that remove them, and settled
    Orca workers of the task leads' Runs that are not released."""
    left, commands, kept, leftovers, users = [], [], [], [], []
    orca_paths = []  # the Orca records, read once and only when a task worktree path is no git worktree any more
    for key in sorted({t["repo"] for t in plan.get("tasks", []) if t.get("repo")}):
        info = repo_info(plan, reg, key)
        if not info["path"] or not os.path.isdir(info["path"]):
            left.append(info["path"] or key)
            kept.append(f"{key}: repo path {info['path']} is missing - point repos.{key}.path at the main checkout")
            continue
        topic = plan["topic"]
        integrated = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{topic}")[0]
        remote_topic = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{topic}")[0]
        main = (git(info["path"], "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main")[0]
                or git(info["path"], "rev-parse", "--verify", "--quiet", "refs/heads/main")[0])
        topic_head = integrated or remote_topic
        merged = bool(after_merge and main and topic_head and is_ancestor(info["path"], topic_head, main))
        _, trees = worktree_for(info["path"], topic)
        tree_list, _ = git(info["path"], "worktree", "list", "--porcelain")
        first = (tree_list or "").splitlines()
        command_repo = first[0][9:] if first and first[0].startswith("worktree ") else info["path"]
        # an Orca child of a task worktree (or of the integration checkout): named after its parent branch, or
        # Orca's lineage names that worktree as its parent; only children of this run's worktrees
        parents = [(t["id"], task_branch(plan, info, t)) for t in plan["tasks"] if t.get("repo") == key]
        parents.append((f"integration:{key}", topic))
        parents = [(tid, pb, worktree_for(info["path"], pb)[0]) for tid, pb in parents]
        lineage = Lineage(pb for _, pb, _ in parents)
        prune = orca_cmd.quote(["git", "-C", command_repo, "worktree", "prune"])
        for wt in trees:
            if wt.get("prunable") and str(wt.get("branch", "")).startswith(topic + "-"):
                # the directory is gone but git keeps the record: `git branch -d` of its branch fails ('used by worktree')
                left.append(wt["path"])
                leftovers.append({"kind": "prunable", "path": wt["path"], "commands": [prune]})
                kept.append(f"{key}: LEFTOVER worktree record {wt['path']} ({wt['branch']}) is prunable (its directory "
                            "is gone): prune it before deleting the branch")
                if prune not in commands:
                    commands.append(prune)
                continue
            owner = next(((tid, pb, pp) for tid, pb, pp in parents
                          if info["worktrees"] and norm_wt(wt["path"]) != norm_wt(pp) and is_child(wt, pb, pp, lineage)), None)
            if owner:
                c = children_of(info["path"], [wt], owner[1], owner[2], lineage)[0]
                left.append(wt["path"])
                dirty, rc = git(wt["path"], "status", "--porcelain")
                if rc != 0 or dirty is None:
                    kept.append(f"{key}: child of {owner[0]}: `git status` failed in {wt['path']} - not removed, report it")
                elif dirty:
                    kept.append(f"{key}: child of {owner[0]}: {wt['path']} has uncommitted changes - not removed, report it")
                else:
                    kept.append(f"{key}: child of {owner[0]}: {child_note_text(c, owner[1])}")
                    if c["merged"]:
                        commands.append(orca_cmd.quote(["orca", "worktree", "rm", "--worktree", f"path:{wt['path']}"]))
                continue
            branch = str(wt.get("branch", ""))
            if not branch.startswith(topic + "-") and not (merged and branch == topic):
                continue
            dirty, rc = git(wt["path"], "status", "--porcelain")
            if rc != 0 or dirty:
                kept.append(f"{key}: worktree {wt['path']} has uncommitted changes - not removed, report it")
                left.append(wt["path"])
                continue
            left.append(wt["path"])
            commands.append(orca_cmd.quote(["git", "-C", command_repo, "worktree", "remove", wt["path"]]))
            for handle, title in orca_terminals(wt["path"]):
                users.append({"path": wt["path"], "terminal": handle, "title": title})
                kept.append(f"{key}: worktree {wt['path']} is still bound to Orca terminal {handle}"
                            + (f" ({title})" if title else "") + ": release or close it before the removal")
            if f"{key}: {BEFORE_REMOVAL}" not in kept:
                kept.append(f"{key}: {BEFORE_REMOVAL}")
        if info["worktrees"]:
            # a task worktree directory (<topic>-<id>, beside the integration or repo checkout) that is no git worktree
            # any more, and an Orca record of it: git prunes it, Orca removes it once no process holds the directory
            registered = {norm_wt(t["path"]) for t in worktree_records(info["path"])}
            parent = worktree_for(info["path"], topic)[0]
            beside = list(dict.fromkeys(os.path.dirname(p.rstrip("/\\")) for p in (parent, info["path"], command_repo) if p))
            for t in (t for t in plan["tasks"] if t.get("repo") == key):
                name = task_branch(plan, info, t).replace("/", "-")
                for d in dict.fromkeys(os.path.join(b, name) for b in beside):
                    if norm_wt(d) in registered:
                        continue
                    if not orca_paths:
                        orca_paths.append(orca_worktree_paths() or set())
                    on_disk, record = os.path.exists(d), norm_wt(d) in orca_paths[0]
                    if not on_disk and not record:
                        continue
                    left.append(d)
                    rm = orca_cmd.quote(["orca", "worktree", "rm", "--worktree", f"path:{d}"])
                    leftovers.append({"kind": "directory" if on_disk else "orca_record", "path": d,
                                      "orca_record": record, "commands": [prune, rm]})
                    what = (f"directory {d} (no git worktree any more" + (", with an Orca record" if record else "") + ")"
                            if on_disk else f"Orca record of the removed task worktree {d}")
                    kept.append(f"{key}: LEFTOVER {what}: `git worktree prune`, then `orca worktree rm` once the "
                                f"directory is free (check it is the old task worktree first); {BUSY_NOTE}")
                    commands.extend(c for c in (prune, rm) if c not in commands)
                    # a directory the removal may fail on: name the processes that may hold it (read-only; the user decides)
                    procs = busy_processes(d)
                    leftovers[-1]["processes"] = procs
                    kept.extend(f"{key}: BUSY? {line}" for line in busy_lines(d, procs))
        refs, _ = git(info["path"], "for-each-ref", "--format=%(refname:short)", f"refs/heads/{topic}-*")
        if after_merge and integrated:
            refs = (refs or "") + "\n" + topic
        for br in (refs or "").splitlines():
            target = main if after_merge else integrated
            _, rc = git(info["path"], "merge-base", "--is-ancestor", br, target) if target else (None, 1)
            if rc == 0:
                left.append(br)
                home, _ = worktree_for(info["path"], br)
                if home and all(norm_wt(home) != norm_wt(t["path"]) for t in trees):
                    kept.append(f"{key}: branch {br} is checked out in the main checkout {home} - not deleted")
                else:
                    commands.append(orca_cmd.quote(["git", "-C", command_repo, "branch", "-d", br]))
            else:
                left.append(br)
                kept.append(f"{key}: branch {br} is not in {'main' if after_merge else topic} - not deleted (integrate it or name it in the report)")
        if after_merge:
            remote_refs, _ = git(info["path"], "for-each-ref", "--format=%(refname)",
                                 f"refs/remotes/origin/{topic}", f"refs/remotes/origin/{topic}-*")
            for ref in sorted((remote_refs or "").splitlines(), key=lambda r: r == f"refs/remotes/origin/{topic}"):
                br = ref.removeprefix("refs/remotes/origin/")
                if br != topic and not br.startswith(topic + "-"):
                    continue
                left.append(ref)
                if main and is_ancestor(info["path"], ref, main):
                    commands.append(orca_cmd.quote(["git", "-C", command_repo, "push", "origin", "--delete", br]))
                else:
                    kept.append(f"{key}: remote branch {br} is not in main - not deleted")
        elif not topic_head:
            remote_refs, _ = git(info["path"], "for-each-ref", "--format=%(refname)",
                                 f"refs/remotes/origin/{topic}-*")
            for ref in (remote_refs or "").splitlines():
                left.append(ref)
                kept.append(f"{key}: {ref} remains but the integration branch is absent - verify the merge before deletion")
    specs_dir = os.path.join(verdict_dir(plan), "specs")
    n_specs = len([f for f in os.listdir(specs_dir) if f.endswith(".md")]) if os.path.isdir(specs_dir) else 0
    specs_kept = [f"{n_specs} spec file(s) in {specs_dir} (dispatch specs, kept as the run's record; delete by hand)"] if n_specs else []
    workers = orca_sessions(orca_runs(plan, orca_run))
    for s in workers:
        for u in s["unreleased"]:
            left.append(f"orca:{u['dispatch']}")
            commands.append(u["command"])
    return {"state": "CLEAN" if not left else "LEFTOVER", "left": left, "commands": commands, "kept": kept, "state_kept": specs_kept,
            "leftovers": leftovers, "terminals": users, "workers": workers, "slots": slot_holders(plan, reg),
            "sessions": "release every settled worker: `orca orchestration worker-list` then "
                        "`orca orchestration worker-release --dispatch <id>`; stop background Agent workers"
                        + ("" if workers else "; name the task leads' Runs (task `orca_run` or --orca-run) to check them")}


def cmd_cleanup(a, reg):
    plan = read_plan(a.plan, reg)
    plan["_path"] = a.plan
    out = cleanup(plan, reg, a.orca_run, a.after_merge)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Cleanup: {out['state']}")
        for c in out["commands"]:
            print("  " + c)
        for k in out["kept"]:
            print("  KEPT  " + k)
        for k in out["state_kept"]:
            print("  STATE " + k)
        for line in session_lines(out["workers"]):
            print("  WORKERS " + line)
        for line in slot_lines(out["slots"]):
            print("  SLOT " + line)
        print("Sessions: " + out["sessions"])
        if out["state"] == "CLEAN":
            print("Next: start the next plan from main")
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


def review_base(info, topic, start, sha):
    """Base of a review diff `git diff <base>...<sha>`: the task's own fork point, the same before and after integration.

    `start` is where the task branch was cut (plan.topic for a later wave, else repos.<key>.base). While `sha` is not on
    the topic, `start` is that fork point. Once the topic merged it, topic...sha is empty and repos.<key>.base would add
    the earlier waves' files, so the base is merge-base(M^1, sha) for the oldest first-parent topic commit M containing
    sha. Returns (base, note); the note says when no such merge is found and the diff may include earlier waves."""
    path = info["path"]
    if start != topic or not is_ancestor(path, sha, topic):
        return start, None
    chain = (git(path, "rev-list", "--first-parent", topic)[0] or "").split()  # newest first
    lo, hi, found = 0, len(chain) - 1, None  # containment is monotonic along the chain: binary search the oldest
    while lo <= hi:
        mid = (lo + hi) // 2
        if is_ancestor(path, sha, chain[mid]):
            found, lo = chain[mid], mid + 1
        else:
            hi = mid - 1
    full = git(path, "rev-parse", "--verify", "-q", f"{sha}^{{commit}}")[0]
    if found and found != full:  # found == sha: a fast-forward, no merge commit marks the task's start
        fork, rc = git(path, "merge-base", f"{found}^1", sha)
        if rc == 0 and fork:
            return fork, None
    base = info["base_sha"] or info["base"]
    return base, (f"{sha} is on {topic} without a merge commit that brought it in: this diff against {base} "
                  "may include earlier waves' changes; judge scope by the task's own commits")


def norm_wt(p):
    p = str(p or "").replace("\\", "/").rstrip("/")
    return p.casefold() if os.name == "nt" or p[1:3] == ":/" else p


class Lineage:
    """Orca's parent of each worktree (child path -> parent path), from the read-only `orca worktree list --json`,
    read once and only when a worktree is not already a child by name. Orca unavailable or failing: empty (the
    naming rule alone), never an error."""

    def __init__(self, own_branches=()):
        self._map, self._own = None, set(own_branches)

    def parent(self, wt):
        if wt.get("branch") in self._own:  # a task worktree or the integration checkout is no child: no orca call
            return None
        if self._map is None:
            self._map = self._read()
        return self._map.get(norm_wt(wt.get("path")))

    @staticmethod
    def _read():
        exe = shutil.which("orca")
        if not exe:
            return {}
        try:
            r = subprocess.run([exe, "worktree", "list", "--limit", "10000", "--json"], capture_output=True, text=True,
                               timeout=60, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
            rows = json.loads(r.stdout or "")["result"]["worktrees"] if r.returncode == 0 else []
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            return {}
        rows = [w for w in rows if isinstance(w, dict)] if isinstance(rows, list) else []
        path_of = {w.get("id"): w.get("path") for w in rows if w.get("id") and w.get("path")}
        out = {}
        for w in rows:
            lin = w.get("lineage") if isinstance(w.get("lineage"), dict) else {}
            pid = w.get("parentWorktreeId") or lin.get("parentWorktreeId")
            if pid in path_of and w.get("path"):
                out[norm_wt(w["path"])] = norm_wt(path_of[pid])
        for w in rows:  # a parent's childWorktreeIds also name its children
            kids = w.get("childWorktreeIds") if isinstance(w.get("childWorktreeIds"), list) else []
            for cid in kids:
                if cid in path_of and w.get("path"):
                    out.setdefault(norm_wt(path_of[cid]), norm_wt(w["path"]))
        return out


def is_child(wt, parent_branch, parent_path=None, lineage=None):
    """An Orca child of the worktree on `parent_branch`: its branch (Orca may add a prefix) or directory name starts
    with `<parent branch>--` (dispatch names children `<task branch>--...`, child_branch()), or Orca's lineage names
    the worktree at `parent_path` as its parent (`orca worktree create --parent-worktree` with any name)."""
    mark = parent_branch + "--"
    br = str(wt.get("branch") or "")
    base = os.path.basename(str(wt.get("path") or "").replace("\\", "/").rstrip("/"))
    if br.startswith(mark) or ("/" + mark) in br or base.startswith(mark.replace("/", "-")):
        return True
    return bool(parent_path and lineage and lineage.parent(wt) == norm_wt(parent_path))


def children_of(repo, trees, parent_branch, parent_path=None, lineage=None):
    """[{path, branch, merged}] of the child worktrees of `parent_branch` (merged: its HEAD is in the parent branch)."""
    out = []
    for wt in trees:
        if norm_wt(wt.get("path")) != norm_wt(parent_path) and is_child(wt, parent_branch, parent_path, lineage):
            br = wt.get("branch")
            out.append({"path": wt["path"], "branch": br,
                        "merged": bool(br) and is_ancestor(repo, f"refs/heads/{br}", f"refs/heads/{parent_branch}")})
    return out


def child_note_text(c, parent_branch):
    return (f"leftover child worktree {c['path']} ({c['branch'] or 'detached'}): "
            + ("merged" if c["merged"] else f"merge it into {parent_branch}") + ", then remove it at once: "
            + orca_cmd.quote(["orca", "worktree", "rm", "--worktree", f"path:{c['path']}"]))


def changed_since(path, sha, head, paths):
    out, rc = git(path, "diff", "--name-only", sha, head, "--", *specs(paths))
    return rc != 0 or bool(out)


def own_start(plan, reg, info, task, head):
    """Where the task's own commits start on `head`, or None when it has none yet. Dependent tasks may own the same
    paths, so the repo base is not enough: a branch cut from plan.topic starts at its fork point (none while it is still
    on the topic's first-parent chain: cut there, nothing of its own), and a no-worktree task, which shares the topic,
    starts only after its serial predecessor's current QA PASS on an ancestor of head (otherwise it has not started,
    and the predecessor's commits are not its own)."""
    base = info["base_sha"] or info["base"]
    if not info["worktrees"]:
        prev = serial_predecessor(plan, reg, task)
        if not prev:
            return base
        rec = verdict_of(plan, reg, prev, "qa")[0]
        return rec["sha"] if rec and rec.get("state") == "PASS" and is_ancestor(info["path"], rec["sha"], head) else None
    start = start_base(plan, info, task)
    if start != plan["topic"]:
        return base
    fork, note = review_base(info, plan["topic"], start, head)
    return None if note else fork


def task_status(plan, reg, task, n_in_repo, lineage=None):
    """Phase a task reached, derived from git and the recorded verdicts (no context of the session that ran it)."""
    info = repo_info(plan, reg, task["repo"])
    path, topic, paths = info["path"], plan["topic"], task["paths"]
    xs = pr.xs_plan(plan, task)  # tier XS: the run lead commits on plan.topic itself, there is no task branch
    branch = topic if xs else task_branch(plan, info, task)
    base = info["base_sha"] or info["base"]
    row = {"id": task["id"], "repo": task["repo"], "branch": branch, "worktree": None, "sha": None,
           "phase": "pending", "review": None, "qa": None, "children": [], "notes": []}
    if not path or not os.path.isdir(path):
        row["notes"].append(f"checkout {path} missing")
        return row, info
    head = git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] or None
    topic_head = git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{topic}")[0] or None
    row["worktree"], trees = worktree_for(path, branch)
    if info["worktrees"] and not xs:  # the topic checkout's children are the integration children
        row["children"] = children_of(path, trees, branch, row["worktree"], lineage)
        row["notes"] += [child_note_text(c, branch) for c in row["children"]]
    rv, rv_stale = verdict_of(plan, reg, task["id"], "review")
    per_task_qa = not info["worktrees"] and n_in_repo > 1
    qa, qa_stale = verdict_of(plan, reg, task["id"], "qa")
    integration_qa, integration_stale = verdict_of(plan, reg, f"integration:{task['repo']}", "qa")
    if integration_stale:
        row["notes"].append(f"integration QA for {task['repo']} is STALE: the plan changed since it was recorded")
    if not qa and not qa_stale and not per_task_qa:
        qa = integration_qa
    for kind, rec, stale in (("review", rv, rv_stale), ("qa", qa, qa_stale)):
        if rec:
            row[kind] = {"state": rec.get("state"), "sha": rec["sha"], "by": rec.get("by"), "task": rec.get("task")}
        elif stale:
            row["notes"].append(f"{kind} verdict is STALE: the plan's task changed since it was recorded")
    if head:
        row["sha"] = head
        # only the task's own commits that touch its own paths: a task branch cut from the integration branch, and
        # the shared integration branch of a no-worktree repo, also carry other tasks' commits (dependent tasks may
        # own the same paths)
        start = own_start(plan, reg, info, task, head) if base else None
        ahead = None
        if base:
            ahead = "0" if start is None else git(path, "rev-list", "--count", f"{start}..{head}", "--", *specs(paths))[0]
        if ahead is None or not str(ahead).isdigit():
            row["notes"].append(f"base {base} not found")
            ahead = "0"
        if int(ahead) > 0:
            row["phase"] = "candidate"
        elif (info["worktrees"] and not xs) or ((start is not None or not base) and row["worktree"]
                                   and git(row["worktree"], "status", "--porcelain", "--", *specs(paths))[0]):
            # a no-worktree task before its serial predecessor's QA PASS has not started: uncommitted work in the
            # paths they share is the predecessor's; a tier XS task has started when the run lead edits its paths
            row["phase"] = "implementing"
    elif (rv or rv_stale) and topic_head and base and git(path, "rev-list", "--count", f"{base}..{topic_head}", "--", *specs(paths))[0] not in (None, "", "0"):
        # A prior review identifies a task whose branch was removed after integration. Without it, commits on
        # the integration branch may belong to earlier tasks with the same owned paths: this task is pending.
        ok = rv and rv.get("state") == "PASS" and is_ancestor(path, rv["sha"], topic_head)
        row["sha"] = rv["sha"] if ok else topic_head
        row["phase"] = "candidate"
    elif not rv and not rv_stale and topic_head and base and git(path, "rev-list", "--count", f"{base}..{topic_head}", "--", *specs(paths))[0] not in (None, "", "0"):
        row["notes"].append(f"commits in owned paths on {topic} but no review record: integrated earlier? check before "
                            "dispatching again")
    if row["phase"] != "candidate" or not rv:
        return row, info
    review_target = topic_head if is_ancestor(path, rv["sha"], topic_head) else row["sha"]
    changed = uncovered_changes(plan, reg, task, rv["sha"], review_target)
    if row["sha"] != review_target and not is_ancestor(path, row["sha"], rv["sha"]):
        changed = sorted(set(changed) | set(uncovered_changes(plan, reg, task, rv["sha"], row["sha"])))
    if changed:
        row["notes"].append(f"review at {rv['sha'][:10]} is STALE: owned paths changed since: " + ", ".join(changed[:5]))
        return row, info
    row["phase"] = "reviewed"
    if rv.get("state") != "PASS" or not is_ancestor(path, rv["sha"], topic_head):
        return row, info
    row["phase"] = "integrated"
    # Keep the lead's QA visible above, but current integration QA also proves
    # completion in repos where the gate does not require per-task QA.
    if (not per_task_qa and integration_qa and integration_qa.get("state") == "PASS"
            and integration_qa["sha"] == topic_head):
        qa = integration_qa
    if qa and qa.get("state") == "PASS" and is_ancestor(path, rv["sha"], qa["sha"]):
        row["phase"] = "qa"
        if topic_head != qa["sha"] and uncovered_changes(plan, reg, task, qa["sha"], topic_head):
            row["phase"] = "integrated"
            row["notes"].append(f"QA at {qa['sha'][:10]} is STALE: owned paths changed on {topic} since")
    return row, info


def xs_qa_next(reg, plan, task, info, row, topic_head, me, pf):
    """A tier XS task's next step after its review PASS: the run lead runs the task tier command in its topic checkout
    and records its QA at plan.topic's HEAD, which the gate takes as the integration QA (no QA session)."""
    pipe = settings(reg)
    where, tier, runall = xs_task_tier(pipe, plan, task, info, start_base(plan, info, task))
    record = xs_qa_record(me, pf, task, xs_implementer(pipe), topic_head)
    row["notes"].append(f"tier XS: the run lead runs the task tier command in {where}"
                        + ("" if runall else f" ({tier})") + f", then records its QA at {(topic_head or '?')[:10]}")
    row["next"] = (orca_cmd.quote(["cd", where]) + f" && {tier} && {record}") if runall else record


def _integration_qa_row(plan, reg, tasks, rows, infos, key, first, me, pf):
    """Mark repo `key`'s tasks integrated with the integration QA as next command when that QA is not PASS at the
    integration HEAD. `first` is the alias of the same no-worktree checkout whose integration QA was offered already:
    this one waits for it. Returns the alias offered (or still `first`). A tier XS task's lead QA stands in for the
    integration QA, as in the gate, while no integration QA is recorded."""
    mine = [t["id"] for t in tasks if t["repo"] == key]
    info = infos[mine[0]]
    topic_head = git(info["path"], "rev-parse", "--verify", "--quiet", f"refs/heads/{plan['topic']}")[0]
    xs_task = next((t for t in tasks if t["repo"] == key and pr.xs_plan(plan, t)), None)
    if xs_task and not (fstate.read_json(verdict_file(plan, f"integration:{key}", "qa")) or {}).get("sha"):
        xq, _ = verdict_of(plan, reg, xs_task["id"], "qa")
        if xq and xq.get("state") == "PASS" and xq["sha"] == topic_head:
            return first
        row = rows[xs_task["id"]]
        row["phase"] = "integrated"
        row["notes"].append(f"tier XS lead QA at {(xq or {}).get('sha', '?')[:10]} is not at the integration HEAD "
                            f"{(topic_head or '?')[:10]}: the gate needs it there")
        xs_qa_next(reg, plan, xs_task, info, row, topic_head, me, pf)
        return first
    iq, iq_stale = verdict_of(plan, reg, f"integration:{key}", "qa")
    if iq and iq.get("state") == "PASS" and iq["sha"] == topic_head:
        return first
    if iq and iq.get("state") != "PASS":
        why = f"integration QA {iq.get('state')} at {iq['sha'][:10]}"
    elif iq:
        why = f"integration QA at {iq['sha'][:10]} is STALE: the integration HEAD is {(topic_head or '?')[:10]}"
    else:
        why = "no integration QA" + (" (its verdict is STALE: the plan changed)" if iq_stale else "")
    for tid in mine:
        rows[tid]["phase"] = "integrated"
        if not iq_stale:  # task_status already notes a plan-stale integration verdict on every row
            rows[tid]["notes"].append(why + f" for {key}: the gate needs it at the integration HEAD")
        if first:
            rows[tid]["notes"].append(f"integration QA of {first} runs first in this checkout: wait for its verdict")
            rows[tid]["next"] = None
        else:
            rows[tid]["next"] = (f"{me} dispatch {pf} --task integration:{key} --phase qa --sha {topic_head} "
                                 "--runner orca")
    return first or key


LEAD_REPORT_SUMMARY = 200
READY_PHASES = ("candidate", "reviewed", "integrated", "qa")


def lead_report_file(plan, task):
    """The task lead's durable report: <task>__lead-report.json beside the verdicts (`report` writes it, status reads it)."""
    return os.path.join(verdict_dir(plan), f"{safe_name(task)}__lead-report.json")


def lead_report_summary(body):
    first = next((ln.strip() for ln in str(body).splitlines() if ln.strip()), "")
    return first if len(first) <= LEAD_REPORT_SUMMARY else first[:LEAD_REPORT_SUMMARY - 3].rstrip() + "..."


def lead_report_notes(plan, row, task, orca_done, path=None, no_worktree=False):
    """The `lead report:` and `READY_FOR_PR:` notes of a task row (read-only). `orca_done`: task ids whose 'task done: <id>'
    message the run's Orca inbox shows; only used when no durable record exists (an older lead that sent a message only).
    `path`: the task's repo checkout. In a no-worktree repo the task HEAD is plan.topic and moves when the next task
    commits, so in the integrated and qa phases a report at an ancestor of the HEAD still counts (as review and QA do).
    `no_worktree`: the repo has no task worktrees; only there does a QA PASS at an ancestor of the HEAD count in the
    integrated phase (every task of the repo is marked integrated while the integration QA is still due)."""
    rec = fstate.read_json(lead_report_file(plan, task["id"]))
    rec = rec if isinstance(rec, dict) and rec.get("sha") else None
    head, notes = row["sha"], []
    report_current = bool(rec) and (rec["sha"] == head or (
        no_worktree and row["phase"] in ("integrated", "qa") and bool(path) and is_ancestor(path, rec["sha"], head)))
    if rec:
        stale = f" (stale: task HEAD is {head[:10]})" if head and not report_current else ""
        notes.append(f"lead report: {rec.get('at', '?')} @{rec['sha'][:10]} {rec.get('summary', '')}{stale}")
    elif task["id"] in orca_done:
        notes.append(f"lead report: task done: {task['id']} (an Orca message only: no durable record, ask the lead to run "
                     "`report`)")
    if row["phase"] not in READY_PHASES or pr.xs_plan(plan, task):
        return notes
    rv, qa, phase = row["review"], row["qa"], row["phase"]
    missing = None
    if not rec:
        missing = "no lead report"
    elif not report_current:
        missing = f"lead report is for {rec['sha'][:10]}, task HEAD is {head[:10]}"
    elif not rv:
        missing = "no review"
    elif rv["state"] != "PASS":
        missing = f"review {rv['state']}"
    elif rv["sha"] != head and phase not in ("integrated", "qa"):
        missing = f"review is at {rv['sha'][:10]}, task HEAD is {head[:10]}"
    elif not qa:
        missing = "no QA"
    elif qa["state"] != "PASS":
        missing = f"QA {qa['state']}"
    elif qa["sha"] != head and phase != "qa" and not (
            no_worktree and phase == "integrated" and bool(path) and is_ancestor(path, qa["sha"], head)):
        missing = f"QA is at {qa['sha'][:10]}, task HEAD is {head[:10]}"
    notes.append("READY_FOR_PR: yes" if missing is None else f"READY_FOR_PR: no ({missing})")
    return notes


def orca_done_tasks(runs):
    """Task ids named by a 'task done: <id>' message in the Runs' Orca inbox (`orca orchestration check --run R --all
    --json`: read-only, never marks a message read). Any orca failure (not on PATH, a caller not bound to the Run:
    consumer_fenced, bad JSON) is no opinion: nothing is shown."""
    exe = shutil.which("orca")
    done = set()
    for run in runs if exe else []:
        try:
            r = subprocess.run([exe, "orchestration", "check", "--run", run, "--all", "--json"], capture_output=True,
                               text=True, timeout=30, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
            doc = json.loads(r.stdout or "") if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        res = doc.get("result") if isinstance(doc, dict) and doc.get("ok") is not False else None
        msgs = res.get("messages") if isinstance(res, dict) else res
        for m in msgs if isinstance(msgs, list) else []:
            subject = str(m.get("subject") or "") if isinstance(m, dict) else ""
            if subject.lower().startswith("task done:"):
                done.add(subject.split(":", 1)[1].strip())
    return done


def status(plan, reg, orca_run=None):
    v = validate(plan, reg)
    me = orca_cmd.quote(pipeline_argv(reg))
    pf = orca_cmd.quote([os.path.abspath(plan["_path"])])
    tasks = plan.get("tasks", [])
    if v["errors"]:
        return {"schema": STATUS_SCHEMA, "plan": plan.get("id"), "topic": plan.get("topic"), "valid": False,
                "errors": v["errors"], "waves": v["waves"], "tasks": [], "integration_children": [], "ready_wave": None,
                "ready": [], "next": [f"{me} validate {pf}"]}
    keys = sorted({t["repo"] for t in tasks})
    count = {k: serial_count(plan, reg, k) for k in keys}  # a no-worktree checkout counts every plan alias of it
    rows, infos = {}, {}
    own = [task_branch(plan, repo_info(plan, reg, t["repo"]), t) for t in tasks] + [plan["topic"]]
    lineage = Lineage(own)  # one read-only `orca worktree list` for every task, only when needed
    for t in tasks:
        rows[t["id"]], infos[t["id"]] = task_status(plan, reg, t, count[t["repo"]], lineage)
    # children of the integration checkout (integration QA or a helper in `<topic>--*`, or any name by Orca's
    # lineage), once per repo
    int_children = []
    for key in keys:
        info = repo_info(plan, reg, key)
        if not info["worktrees"] or not info["path"] or not os.path.isdir(info["path"]):
            continue
        home, trees = worktree_for(info["path"], plan["topic"])
        for c in children_of(info["path"], trees, plan["topic"], home, lineage):
            int_children.append({"repo": key, **c, "note": child_note_text(c, plan["topic"])})
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
            if prev and rows[prev]["phase"] != "qa" and prev not in waiting:
                waiting.append(prev)
            if waiting:
                row["notes"].append("waits for " + ", ".join(waiting))
            else:
                ready.append(tid)  # a worktree repo starts the task lead, which creates the task worktree
                # every task starts its task lead: a worktree repo gets the task worktree, a no-worktree repo the
                # main checkout; the lead runs the subplan, review and QA in either case
                row["next"] = f"{dispatch} --phase lead --runner orca"
        elif row["phase"] == "implementing" and pr.xs_plan(plan, t):
            row["notes"].append(f"tier XS: the run lead edits the owned paths on {row['branch']}"
                                + (f" in {row['worktree']}" if row["worktree"] else "")
                                + ": commit them with explicit paths, then dispatch the review of that commit")
        elif row["phase"] == "implementing":
            row["notes"].append(f"implementation worker on {row['branch']}"
                                + (f" in {row['worktree']}" if row["worktree"] else "") + ": wait for its report")
        elif row["phase"] == "candidate" and pr.xs_plan(plan, t):
            # tier XS: no task lead verifies it; the run lead dispatches the one cross-model review itself
            row["next"] = f"{dispatch} --phase review --sha {row['sha']} --runner orca"
        elif row["phase"] == "candidate":
            row["next"] = f"{dispatch} --phase verify --sha {row['sha']} --runner orca"
        elif row["phase"] == "reviewed" and row["review"]["state"] != "PASS":
            row["notes"].append(f"review {row['review']['state']} at {row['review']['sha'][:10]}: fix the findings on "
                                f"{row['branch']}, then review the new HEAD")
            # only the task lead commits: it resumes (task worktree, or the main checkout of a no-worktree repo) and
            # starts a fresh fix session, then review and QA on the new HEAD
            row["next"] = f"{dispatch} --phase lead --runner orca"
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
            if pr.xs_plan(plan, t):
                xs_qa_next(reg, plan, t, info, row, topic_head, me, pf)
            elif not info["worktrees"] and count[t["repo"]] > 1:
                row["next"] = f"{dispatch} --phase qa --sha {topic_head} --runner orca"
            else:
                others = [u["id"] for u in tasks if u["repo"] == t["repo"] and rows[u["id"]]["phase"] not in done]
                if others:
                    row["notes"].append("QA runs once all tasks of the repo are integrated: waits for " + ", ".join(others))
                else:
                    row["next"] = f"{me} dispatch {pf} --task integration:{t['repo']} --phase qa --sha {topic_head} --runner orca"
    # the gate needs the repo's integration QA PASS at the integration HEAD (also after per-task QA of a no-worktree
    # repo): until then the repo's tasks stay integrated and the next command is that QA. A no-worktree checkout is
    # one serial group across every plan alias of it: its integration QA waits until every task of the checkout
    # passed per-task QA (a task lead may still edit it), and the aliases' integration QAs run one at a time
    groups = {}
    for key in keys:
        groups.setdefault(serial_key(plan, reg, key), []).append(key)
    for gkeys in groups.values():
        if not all(rows[t["id"]]["phase"] == "qa" for t in tasks if t["repo"] in gkeys):
            continue
        first = None
        for key in gkeys:
            first = _integration_qa_row(plan, reg, tasks, rows, infos, key, first, me, pf)
    # a current subtask review/QA FAIL blocks the task like a task review FAIL: the task lead fixes it (no gate)
    blocked = False
    for t in tasks:
        fails = subtask_failures(plan, reg, t["id"], rows[t["id"]]["sha"]) if rows[t["id"]]["phase"] in ("reviewed", "integrated", "qa") else []
        if fails:
            blocked = True
            rows[t["id"]]["notes"] += fails
            rows[t["id"]]["next"] = f"{me} dispatch {pf} --task {t['id']} --phase lead --runner orca"
    open_waves =[n for n, w in enumerate(v["waves"], 1) if any(rows[tid]["phase"] not in done for tid in w)]
    nxt = [f"{me} gate {pf}"] if tasks and not blocked and all(r["phase"] == "qa" for r in rows.values()) else []
    # settled Orca workers of the task leads' Runs that still own a terminal: release them now, not at task end
    workers = orca_sessions(orca_runs(plan, orca_run))
    nxt = [u["command"] for s in workers for u in s["unreleased"]] + nxt
    # what each task lead reported (a durable `report` record), and whether the work is ready for the PR gate: a run lead
    # polling status sees completion without messages; --orca-run adds the 'task done' messages of older leads
    runs = orca_runs(plan, orca_run)
    orca_done = orca_done_tasks(runs) if runs else set()
    for t in tasks:
        rinfo = repo_info(plan, reg, t["repo"])
        rows[t["id"]]["notes"] += lead_report_notes(plan, rows[t["id"]], t, orca_done, rinfo["path"],
                                                    no_worktree=not rinfo["worktrees"])
    out_rows = []
    for t in tasks:
        r = rows[t["id"]]
        out_rows.append({k: r[k] for k in ("id", "repo", "wave", "phase", "branch", "worktree", "sha", "review", "qa",
                                           "children", "next", "notes")})
    return {"schema": STATUS_SCHEMA, "plan": plan.get("id"), "topic": plan.get("topic"), "valid": True, "errors": [],
            "waves": v["waves"], "tasks": out_rows, "integration_children": int_children, "ready_wave": open_waves[0] if open_waves else None,
            "ready": ready, "next": nxt, "_workers": workers, "_slots": slot_holders(plan, reg)}


def cmd_status(a, reg):
    plan = read_plan(a.plan, reg)
    plan["_path"] = a.plan
    pipe = settings(reg)
    tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    # a task without an id (an INVALID plan) is still shown: status reports the error, never a traceback
    models = {str(task.get("id", "?")): {role: {"agent": agent, "why": why} for role, (agent, why) in pr.roles(
              pipe, task, pr.available(pipe, plan),
              implementer_of(pipe, plan, task) if isinstance(task.get("id"), str)
              and pr.recorded(plan, task["id"], None, "implementer") else None).items()}
              for task in tasks if isinstance(task, dict)}
    if not a.json:
        for tid, roles in models.items():
            for role, model in roles.items():
                print(f"model: {tid} {role} -> {model['agent']} ({model['why']})")
    out = status(plan, reg, a.orca_run)
    if a.json:
        out["models"] = models
    workers = out.pop("_workers", [])
    slots = out.pop("_slots", [])
    if a.json:
        print(json.dumps(out, indent=2))
        # the status schema has no workers or slots field: those lines (NOT_AVAILABLE, UNRELEASED, held slots) go to stderr
        for line in session_lines(workers):
            print("Workers: " + line, file=sys.stderr)
        for line in slot_lines(slots):
            print("Slots: " + line, file=sys.stderr)
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
    for c in out["integration_children"]:
        print(f"  [integration:{c['repo']}] child: {c['note']}")
    if out["ready_wave"]:
        print(f"Ready wave: {out['ready_wave']}" + (f"  (dispatch: {', '.join(out['ready'])})" if out["ready"] else ""))
    elif out["valid"] and out["tasks"]:
        print("Every wave is integrated.")
    for line in session_lines(workers):
        print("Workers: " + line)
    for line in slot_lines(slots):
        print("Slots: " + line)
    for c in out["next"]:
        print("Next: " + c)
    return 0 if out["valid"] else 1


def cmd_report(a, reg):
    """The task lead's durable report: <state dir>/pipeline/<plan id>/<task>__lead-report.json (at, sha, summary, body).
    Written before the Orca message, so the run lead's `status` shows completion even when the message is lost."""
    plan = read_plan(a.plan, reg)
    plan["_path"] = a.plan
    if a.task.startswith("integration:"):
        die("report is per plan task: --task <id>")
    task = find_task(plan, a.task)
    if a.body is not None:
        body = a.body
    else:
        try:
            with open(a.body_file, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError as e:
            die(f"--body-file {a.body_file}: {e.strerror or e}")
    if not body.strip():
        die("the report body is empty")
    if len(a.sha) < 7 or any(c not in "0123456789abcdef" for c in a.sha.lower()):
        die("--sha must be a commit id")
    full, rc = git(repo_info(plan, reg, task["repo"])["path"] or ".", "rev-parse", "--verify", "--quiet", a.sha + "^{commit}")
    if rc != 0 or not full:
        die(f"--sha {a.sha} is not a commit of repo {task['repo']}")
    rec = {"plan": plan.get("id"), "task": a.task, "sha": full, "at": now_utc(), "summary": lead_report_summary(body),
           "body": body}
    path = lead_report_file(plan, a.task)
    fstate.write_json(path, rec, indent=2)
    print(f"recorded lead report for {a.task} at {full[:10]}: {path}")
    return 0


def cmd_agents(a, reg):
    plan = read_plan(a.plan, reg)
    pipe = settings(reg)
    agent = a.down or a.up
    if agent and agent not in pipe["agents"]:
        die("unknown agent " + agent)
    if agent:
        pr.mark(plan, agent, a.reason if a.down else None)
    out = pr.available(pipe, plan)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for agent, state in out.items():
            print(f"{agent}: {'available' if state['available'] else 'unavailable'} ({state['why']})")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="factory-pipeline.py", description=__doc__.split("\n")[0])
    ap.add_argument("--registry", default=os.environ.get("RPG_FACTORY_PIPELINE_REGISTRY", os.path.join(ROOT, "registry.json")))
    # the same option after the verb; SUPPRESS keeps the top-level value unless it is given there (and then it wins)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--registry", default=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tier", parents=[common])
    t.add_argument("--json", action="store_true")
    t.add_argument("--context-json")
    t.add_argument("--plan")
    t.add_argument("--repo")
    t.add_argument("--paths", nargs="+")
    t.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("validate", parents=[common])
    p.add_argument("plan")
    p.add_argument("--json", action="store_true")
    sp = sub.add_parser("subplan", parents=[common])
    sp.add_argument("action", choices=("validate",))
    sp.add_argument("subplan")
    sp.add_argument("--plan")
    sp.add_argument("--json", action="store_true")
    for name in ("planner", "dispatch"):
        d = sub.add_parser(name, parents=[common])
        if name == "dispatch":
            d.add_argument("plan")
            d.add_argument("--task", required=True)
            d.add_argument("--phase", required=True, choices=("lead", "implement", "review", "qa", "verify"))
            d.add_argument("--sha")
            d.add_argument("--paths", nargs="+")
            d.add_argument("--report-to")
            d.add_argument("--placement", choices=PLACEMENTS)
            d.add_argument("--subplan")
            d.add_argument("--subtask")
        else:
            d.add_argument("--request", required=True)
        d.add_argument("--runner", choices=("orca", "agent", "print"), default=None)
        d.add_argument("--orca-unavailable", metavar="REASON")
        d.add_argument("--agent")
        d.add_argument("--grade", choices=model_policy.GRADES)
        d.add_argument("--model", metavar="ID")
        d.add_argument("--effort", metavar="LEVEL")
    v = sub.add_parser("verdict", parents=[common])
    v.add_argument("plan")
    v.add_argument("--task", required=True)
    v.add_argument("--phase", required=True, choices=("review", "qa", "verify"))
    v.add_argument("--sha", required=True)
    v.add_argument("--by", required=True)
    v.add_argument("--state", required=True)
    v.add_argument("--report")
    v.add_argument("--note")
    v.add_argument("--failed-suites")
    v.add_argument("--failed-at", choices=("review", "qa"),
                   help="--phase verify --state FAIL: `review` = the review blocked and no test ran (no QA record)")
    v.add_argument("--implementer")
    v.add_argument("--subtask")
    v.add_argument("--subplan")
    v.add_argument("--fallback", metavar="'AGENT unavailable'",
                   help="review only: the paired reviewer that was unavailable (not the replacement that reviewed), e.g. "
                        "--fallback 'codex unavailable' --by claude --note TEXT when codex was down and claude reviewed")
    ag = sub.add_parser("agents", parents=[common])
    ag.add_argument("plan")
    change = ag.add_mutually_exclusive_group()
    change.add_argument("--down")
    change.add_argument("--up")
    ag.add_argument("--reason", default="")
    ag.add_argument("--json", action="store_true")
    v.add_argument("--model", metavar="ID")
    v.add_argument("--effort", metavar="LEVEL")
    rp = sub.add_parser("report", parents=[common])
    rp.add_argument("plan")
    rp.add_argument("--task", required=True)
    rp.add_argument("--sha", required=True)
    body = rp.add_mutually_exclusive_group(required=True)
    body.add_argument("--body")
    body.add_argument("--body-file")
    st = sub.add_parser("status", parents=[common])
    st.add_argument("plan")
    st.add_argument("--json", action="store_true")
    st.add_argument("--orca-run", action="append", default=[], metavar="RUN_ID")
    c = sub.add_parser("cleanup", parents=[common])
    c.add_argument("plan")
    c.add_argument("--json", action="store_true")
    c.add_argument("--after-merge", action="store_true")
    c.add_argument("--orca-run", action="append", default=[], metavar="RUN_ID")
    g = sub.add_parser("gate", parents=[common])
    g.add_argument("plan")
    g.add_argument("--allow-same-model", action="store_true")
    g.add_argument("--no-run-checks", action="store_true")
    g.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "tier" and a.rest[:1] == ["--"]:
        a.rest = a.rest[1:]
    elif a.cmd == "tier" and a.rest and not a.rest[0].startswith("-"):
        # `tier <plan.json>` once reached factory-context.sh as an unknown argument; tier takes no positional
        die(f"tier takes no positional argument ({a.rest[0]}). Forms: `tier --plan <plan.json> --repo <key> --paths <files>` "
            "(a plan repo key) or `tier -- --repo <key> --paths <files>` (the routing snapshot of a registry repo)")
    reg = load_registry(a.registry)
    if getattr(a, "agent", None) and a.agent not in settings(reg)["agents"]:
        die(f"--agent must be one of {', '.join(settings(reg)['agents'])}")
    return {"agents": cmd_agents, "tier": cmd_tier, "validate": cmd_validate, "planner": cmd_planner, "dispatch": cmd_dispatch,
            "subplan": cmd_subplan, "verdict": cmd_verdict, "gate": cmd_gate, "cleanup": cmd_cleanup, "status": cmd_status,
            "report": cmd_report}[a.cmd](a, reg)


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
