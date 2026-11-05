# Parallel work: lead, workers, worktrees, Orca

The single policy for splitting a Factory task across agents. Other files point here; none restates it.
It adds no gate and no prompt: when something is missing, the task reports it and other work continues.
The delivery pipeline (section 10, `scripts/factory-pipeline.py`) is how the lead runs this policy end to end:
tier, plan, workers, cross-model review, QA, READY_FOR_PR, PR.

## 1. Roles

**Lead/Integrator** - the main Claude Code session, always. It:
1. owns the task scope and splits it into tasks with disjoint file ownership;
2. records each task's base commit and integration target;
3. writes the task spec for every dispatch (section 3);
4. creates or requests one worktree per task (section 4);
5. dispatches and supervises workers, and answers their questions;
6. assigns shared exclusive resources, one task at a time;
7. reviews every diff and re-verifies the key checks itself;
8. decides when a contribution is ready and integrates it (section 7);
9. writes the final report with the parallel-work ledger (`report.md`) and cleans up (section 8).

**Implementation worker** - works only in its task's worktree and branch, runs the targeted checks from its
spec, commits explicit paths, and sends a completion report.
**QA worker** - checks acceptance criteria, test coverage, regressions, edge and failure cases on a recorded
candidate SHA. Read-only unless its spec says otherwise.
**Review worker** - checks architecture, scope isolation, safety rules and conventions. Read-only.

Workers never redefine scope, never merge, and never declare the overall task done. A worker that finds
out-of-scope work reports it to the lead.

## 2. Before delegating

- Take the snapshot (`factory-context.sh`) and run `git worktree list` in every touched repo.
- With Orca: `orca worktree ps` and `orca orchestration run-list` show other coordinators' runs and
  worktrees. They belong to those coordinators: never bind to them, message their workers or edit their trees.
- Check file ownership: two tasks that write the same file, the same generated path or the same contract end
  overlap. Overlapping tasks run one after the other, not in parallel.
- Record per task: base branch and SHA, integration target (the task's own integration branch), dependencies.

## 3. Task spec (every dispatch)

Objective; in-scope paths; exclusions (paths, repos, actions); base branch and SHA; dependencies on other
tasks; required checks (`run-checks.py` tiers: fast, plus extended or external when named); acceptance
criteria; report format.

The completion report contains: outcome; worktree path; branch; base SHA; HEAD SHA; changed paths; each check
with exact counts and log path (or NOT_RUN with the command and reason); known limitations; anything out of
scope it noticed.

## 4. Worktrees

- One worktree per task, on a new `<type>/<area>/<topic>` branch from the recorded base. The task's implementer,
  review, QA and fix sessions all run in it (section 8, "Session lifecycle").
- Only the dispatching tool creates worktrees: Orca (`orca orchestration worker-start --worktree <selector>`,
  or `orca worktree create`) or a Claude Code agent with `isolation: "worktree"`. Never a second clone,
  never a nested repository.
- Never edit another task's worktree. Read-only inspection of it is fine.
- One mutating command per worktree at a time (`git-safety.md` rule 14) still applies.
- **No worktree in a Unity project.** A repo with registry `worktrees: false` (the client) or a
  `ProjectSettings/ProjectVersion.txt` at its root never gets a worktree, for any role: each one needs its own
  multi-GB `Library/` import. Its tasks run one after another in the main checkout on the task branch, each with
  implement, cross-model review and QA before the next starts; its reviewers read the commits there and change
  nothing. Package, server, tool and plugin repos use worktrees and parallelise well.
- **Shared exclusive resources** (Unity Editor and Unity test runs - one at a time across the client and every
  package test project, registry `pipeline.exclusive_resources` -, a local or scratch Docker stack, the test lab, fixed ports):
  the lead assigns each to one task at a time. A task without the resource reports the dependent check as
  `NOT_RUN` with the exact command and reason; other work continues. There is no prompt.

## 5. Orca (preferred coordinator when available)

- Detect: `orca status --json`. Orca is usable when `result.runtime.reachable` is `true`.
- Load the version-matched coordinator and worker contract with `orca skills get orchestration` before
  the first dispatch, and follow it. This file does not restate it.
- Commands this policy relies on: `orca orchestration run-create`, `orca orchestration task-create`,
  `orca orchestration worker-start`, `orca orchestration check`, `orca orchestration reply`,
  `orca orchestration worker-show`, `orca orchestration worker-read`, `orca orchestration worker-list`,
  `orca orchestration worker-release`, `orca worktree list`, `orca worktree create`, `orca worktree rm`.
- Never use `orca orchestration gate-create` for routine work: a decision gate blocks a task, and this
  plugin adds no blocking step.
- Runs you did not create belong to other coordinators (section 2).
- **Fallback:** when Orca is unavailable or cannot do an operation, use Claude Code background agents with
  `isolation: "worktree"` and name the limitation in the report. The absence of Orca never blocks progress.

## 6. Parallel QA and review

- Start QA and review on a **stable candidate commit**: record its SHA and give it to both workers. Never
  point them at a tree that is still changing.
- A task's review and QA workers run as fresh, read-only sessions in the task's own worktree, which holds the
  candidate commit (`orca orchestration worker-start --worktree path:<task worktree>`); never in a new worktree.
  Integration QA runs in the integration branch's checkout. The worker first checks that `git rev-parse HEAD` is
  that SHA; a result from a changing tree, or with HEAD on another commit, is reported as not independent.
  Exception: in a no-worktree repo (section 4) review and QA run in the main checkout, one at a time, while no
  other task of that repo runs.
- When the candidate moves (a fix lands), list which findings and results refer to the old SHA and must be
  redone; re-run only those.
- Verdicts are PASS, FAIL, NOT_RUN or BLOCKED. NOT_RUN is never a pass.
- The lead does not rely on self-reports: it re-runs the key checks on the candidate tree, for example
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py --repo <key> --paths <files> --status` and the
  suite the spec names.

## 7. Integration checklist (the lead, per contribution)

- [ ] Diff contains only the task's scope; base and target are the recorded ones.
- [ ] Diff reviewed by the lead; required checks and QA passed; no open blocking finding.
- [ ] No baseline or user files touched; shared-package impact named; file ownership clear.
- [ ] Integrate in dependency order into the task's integration branch, then run the post-integration checks
      on the combined tree.
- [ ] On a conflict or regression: stop that contribution, diagnose it, and dispatch a scoped fix. Never
      discard work and never resolve a conflict by blindly taking one side.

Merging worker branches into the task's integration branch is the lead's decision. Merging into a protected
or shared branch (develop, main, staging, release-*) and pushing stay on the user's request (`git-safety.md`
rule 5).

## 8. Cleanup (mandatory when a task is done)

A task is done when its contribution is integrated and its review and QA are recorded; the whole run is done
when the PR is open (or, without `deliver: pr`, when the gate reports READY_FOR_PR). Then, every time:

1. **Worktrees.** Remove every task worktree the lead's own run created once the task's review PASS is recorded
   and the task is integrated, and the tree is clean (no-worktree repo: nothing to remove; its sessions settle
   after its QA): `git worktree remove <path>` without `--force`. A worktree with uncommitted or
   unintegrated work is not removed: report it instead. Never remove the main checkout, the integration branch's
   checkout before its PR is open, or a worktree another coordinator owns (section 2).
2. **Task branches.** The user asked for full cleanup, so a task branch whose commits are in the integration
   branch is deleted with its worktree (`git branch -d`, never `-D`). The integration branch stays: it carries
   the PR. `orca worktree rm` also deletes the checked-out local branch when Orca can prove it is merged (see
   its `--help`), and keeps branches it cannot prove merged - use it for Orca-created worktrees.
3. **Agent sessions.** End every Claude and Codex session the run started: `orca orchestration worker-release`
   for each settled Orca worker (it closes only that worker's terminal and keeps its output readable), and stop
   any background Agent-tool worker that is still running. No idle worker session outlives its task.
4. **Check.** `factory-pipeline.py cleanup plan.json` lists what is left (worktrees and task branches of the
   plan) and prints the commands; it must report CLEAN before the final report. The report's Cleanup column
   names what was removed and what was kept and why.

### Session lifecycle

- **One task, one fresh worker session.** Every dispatch starts a new worker session (Orca worker or Agent-tool
  worker) for exactly one task. A worker session is never reused for another task, another phase or a later wave.
  A scoped fix after a FAIL is a new dispatch in a new implementer session, in the same task worktree.
- **One worktree per task, for its whole life.** The task's implementer, reviewer, QA worker and any fix run as
  separate fresh sessions in that one worktree; review and QA never get a new worktree. Reviewer and QA sessions
  are read-only and first check that `git rev-parse HEAD` is the candidate SHA (section 6).
- **Release each session as soon as it reports.** In the turn a session reports (`worker_done`, the agent's final
  report, or a review or QA verdict), it is released (`orca orchestration worker-release`, or the agent is
  stopped); the task worktree stays. The next role runs as a fresh session in that worktree: review on the
  candidate SHA, a fix after a FAIL, QA where the repo needs it. The task is integrated (section 7) when its review
  PASS is recorded, in wave order (section 10 step 5); only then is its worktree removed (step 1 above). In a
  no-worktree repo the task's sessions settle after its QA. A settled worker never waits for a later turn or wave.
- **Review and QA run in their own fresh sessions** (section 6, section 10 steps 4 and 6): never in the
  implementer's session, never in the lead's session, and never reused across tasks or candidate SHAs.
- **The lead keeps only the plan and the integration state:** `plan.json`, the integration branch, the recorded
  SHAs and the verdicts in the pipeline state dir. It does not carry worker transcripts forward.
- **Handoff.** After each wave, or earlier when its context grows long, the lead hands off: it ends its session
  with every worker of the wave settled, and the next lead session resumes from
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py status plan.json`, which re-derives where the plan
  stands. Nothing else carries over. A handoff adds no gate and no confirmation step.

## 9. Not authorized by this policy

- Tags and releases: only with explicit release authorization from the user in the current task
  (`git-safety.md` rule 5 and the release flow).
- Production deploys.
- Consequential workflow dispatch, secrets, shared infrastructure and production data: these are registry
  `human_gates` and keep their rules.
- Repositories outside the task.
- Bypassing branch protection or required CI.

## 10. Delivery pipeline

`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py` turns sections 1-8 into commands. Tier thresholds, agents,
review pairing and exclusive resources live in registry `pipeline`; the plan format is
`docs/schemas/pipeline-plan.schema.json`. The pipeline only prints commands and grades state; the lead runs them.

1. **Tier.** `factory-pipeline.py tier -- --repo <key> --paths <files>` prints S, M or L and the flow.
   S: the lead implements in its own session, then the review, QA and gate steps below with one plan task.
   M: the lead writes `plan.json`. L: a planner worker writes it (`factory-pipeline.py planner --request <text>
   --runner orca`); planning is read-only and runs in the lead's checkout, never in a new worktree.
2. **Plan.** `factory-pipeline.py validate plan.json` must print OK: disjoint owned paths (or a dependency between the
   tasks), no cycle, waves, no worktree for a no-worktree repo and never two of its tasks in one wave, a reviewer of
   another model, and a warning when one wave shares an exclusive resource (queue those runs).
3. **Implement.** Per ready task, `factory-pipeline.py dispatch plan.json --task <id> --phase implement --runner orca`
   prints the worker start (section 5; `--runner agent` is the fallback). Section 3 is the task spec.
4. **Cross-model review.** Code written by Claude is reviewed by Codex and code written by Codex by Claude
   (registry `pipeline.review_pairing`). On the task's stable candidate commit:
   `dispatch ... --phase review --sha <sha>`. The review session runs in the task worktree (section 6);
   `dispatch --phase review|qa` still prints a start in a new worktree, so start the worker with
   `--worktree path:<task worktree>` instead. Record the result: `factory-pipeline.py verdict plan.json --task <id>
   --phase review --sha <sha> --by <agent> --state PASS|FAIL --report <file>`. A FAIL goes back to the task as a
   scoped fix in a fresh implementer session in the task worktree (section 8, "Session lifecycle") and a new
   candidate SHA. When the paired model is unavailable, a fresh session of the same model reviews, the report
   names it SAME_MODEL, and the gate accepts it only with `--allow-same-model`.
5. **Integrate** (section 7), in wave order, into the integration branch named by the plan's `topic`.
6. **QA.** Once per repo on the integration HEAD: `dispatch ... --task integration:<repo> --phase qa --sha <head>`;
   in a no-worktree repo also per task, before the next task starts (`--task <id>`). The QA worker fills
   `templates/pipeline/qa-report.md`; the lead records `verdict ... --phase qa`.
7. **READY_FOR_PR.** `factory-pipeline.py gate plan.json` is a read-only report: every task integrated, reviewed PASS
   by its paired model on a commit whose owned paths have not changed since, QA PASS on each integration HEAD,
   clean integration trees, fast checks PASS and not STALE (`run-checks.py --status`), and no pipeline worktree in
   a no-worktree repo. Anything else is a listed blocker: fix it and re-run the affected review or QA only.
8. **PR.** When the user put `deliver: pr` in the task (plan `deliver: "pr"`) and the gate prints READY_FOR_PR, the
   lead pushes the integration branch and opens the PR with the commands the gate prints, body = the final report
   (`report.md`). This is the delivery exception of `git-safety.md` rule 5. Merging stays with the user;
   without `deliver: pr` the task ends at READY_FOR_PR in the report.
9. **Cleanup.** Section 8, every time: remove the run's worktrees and merged task branches, release every Claude
   and Codex worker session, and run `factory-pipeline.py cleanup plan.json` until it reports CLEAN. In a no-worktree
   repo, release each task's sessions as soon as its QA verdict is recorded, before the next task starts.

This policy introduces no tripwire, no latch and no new confirmation step.
