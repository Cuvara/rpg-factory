# Parallel work: lead, workers, worktrees, Orca

The single policy for splitting a Factory task across agents. Other files point here; none restates it.
It adds no gate and no prompt: when something is missing, the task reports it and other work continues.
The delivery pipeline (section 10, `scripts/factory-pipeline.py`) is how the lead runs this policy end to end:
tier, plan, task leads, cross-model review, QA, READY_FOR_PR, PR.

Work runs on two levels. The **run lead** splits the request into plan tasks and gives each task one worktree
and one **task lead** session. The task lead splits its task into subtasks and runs everything for that task -
implementation, cross-model review, QA, fixes - as fresh sessions in that one worktree, then reports to the run
lead, which integrates and cleans up.

## 1. Roles

**Lead/Integrator (run lead)** - the main Claude Code session, always. It:
1. owns the run scope and splits it into plan tasks with disjoint file ownership;
2. records each task's base commit and integration target;
3. writes the task spec for every task (section 3);
4. gives each task one worktree and starts ONE task-lead session in it (section 4, section 10 step 3);
5. answers the task leads' questions and follows their progress (`factory-pipeline.py status`);
6. assigns shared exclusive resources, one task at a time;
7. reviews every task's result and re-verifies the key checks itself;
8. decides when a contribution is ready and integrates it (section 7), then runs integration QA (section 6);
9. writes the final report with the parallel-work ledger (`report.md`) and cleans up (section 8).
It does not start a task's sub-sessions: that is the task lead's job.

**Task lead** - one fresh session per plan task, in that task's worktree (a no-worktree repo: its main checkout,
section 4). It is not an Orca worker of the run lead (section 5): it creates its own Orca Run. It:
1. plans its task and splits it into subtasks with disjoint paths inside the task's owned paths; subtasks with
   disjoint paths run in parallel, the others in order (`factory-pipeline.py subplan validate`, section 10 step 3);
2. starts one fresh Claude or Codex session per subtask in the same worktree, never reused for another subtask;
3. reviews each sub-session's diff and commits that subtask itself with explicit paths;
4. with every subtask committed, starts a fresh cross-model review session and a QA session on that HEAD in the
   same worktree; a FAIL goes to a fresh fix session;
5. releases every session as soon as it reports (section 8, "Session lifecycle");
6. reports to the run lead (section 3) and records the review and QA verdicts.
It never pushes, merges, tags or removes its worktree.

**Implementation sub-session** - edits only its subtask's paths in the task worktree, runs the targeted checks
from its spec, and reports to the task lead. It does not commit, stage or stash: the worktree has one shared
index and the task lead commits.
**QA worker** - checks acceptance criteria, test coverage, regressions, edge and failure cases on a recorded
candidate SHA. Read-only unless its spec says otherwise.
**Review worker** - checks architecture, scope isolation, safety rules and conventions. Read-only.

Task leads and their sessions never redefine the plan's scope, never merge, and never declare the overall run
done. A session that finds out-of-scope work reports it to its task lead, and the task lead to the run lead.

## 2. Before delegating

- Take the snapshot (`factory-context.sh`) and run `git worktree list` in every touched repo.
- With Orca: `orca worktree ps` and `orca orchestration run-list` show other coordinators' runs and
  worktrees. They belong to those coordinators: never bind to them, message their workers or edit their trees.
- Check file ownership: two tasks that write the same file, the same generated path or the same contract end
  overlap. Overlapping tasks run one after the other, not in parallel. The same holds for the subtasks of one task.
- Record per task: base branch and SHA, integration target (the task's own integration branch), dependencies.

## 3. Task spec (every dispatch)

Objective; in-scope paths; exclusions (paths, repos, actions); base branch and SHA; dependencies on other
tasks; required checks (`run-checks.py` tiers: fast, plus extended or external when named); acceptance
criteria; report format. The run lead's spec for a task lead adds the task-lead rules (section 1); the task
lead's spec for a sub-session is the same task spec narrowed to the subtask's paths.

A sub-session's report contains: changed paths; each check with exact counts and log path (or NOT_RUN with the
command and reason); known limitations; anything out of scope it noticed.

The task lead's completion report to the run lead contains: outcome; worktree path; branch; base SHA; HEAD SHA;
each subtask with its commit; the review and QA verdicts (state, SHA, model); changed paths; each check with
exact counts and log path (or NOT_RUN with the command and reason); known limitations; anything out of scope it
noticed.

## 4. Worktrees

- One worktree per plan task, for its whole life, on the task branch `<topic>-<task id>` from the recorded base
  (the plan `topic` is the `<type>/<area>/<topic>` integration branch). It is created for the task lead; the task
  lead's implementation sub-sessions, review, QA and fix sessions all run in it (section 8, "Session lifecycle").
  Subtasks never get a worktree of their own.
- Only the dispatching tool creates worktrees: Orca (`orca worktree create`, the run lead's task-lead handoff)
  or a Claude Code agent with `isolation: "worktree"`. Never a second clone, never a nested repository.
  A session the task lead starts joins the existing task worktree; when there is none, dispatch is an error and
  no worktree is created.
- Never edit another task's worktree. Read-only inspection of it is fine.
- One mutating command per worktree at a time (`git-safety.md` rule 14) still applies: parallel sub-sessions
  edit disjoint files and run no git write; only the task lead stages and commits.
- **No worktree in a Unity project.** A repo with registry `worktrees: false` (the client) or a
  `ProjectSettings/ProjectVersion.txt` at its root (registry `pipeline.no_worktree_markers`) never gets a
  worktree, for any role: each one needs its own multi-GB `Library/` import. Its task lead runs in the main
  checkout on the task branch (the handoff is `orca agent launch --worktree path:<main checkout>`, never a
  worktree create or a new top-level worker); its subtasks run one after another, never two sessions editing or
  importing the project at once; its review and QA sessions run in that checkout too, read the commits there and
  change nothing. Its tasks run one after another: the next task starts after the previous task's QA verdict.
  Package, server, tool and plugin repos use worktrees and parallelise well.
- **Shared exclusive resources** (Unity Editor and Unity test runs - one at a time across the client and every
  package test project, registry `pipeline.exclusive_resources` -, a local or scratch Docker stack, the test lab, fixed ports):
  the lead assigns each to one task at a time. A task without the resource reports the dependent check as
  `NOT_RUN` with the exact command and reason; other work continues. There is no prompt.

## 5. Orca (preferred coordinator when available)

- Detect: `orca status --json`. Orca is usable when `result.runtime.reachable` is `true`.
- Load the version-matched coordinator and worker contract with `orca skills get orchestration` before
  the first dispatch, and follow it. This file does not restate it.
- **No nested workers.** Orca allows one level of workers (`nested_worker_depth_exceeded`, maximum depth 1); never
  route around it. So the task lead is not a worker of the run lead: the run lead starts it as a handoff,
  `orca worktree create --name <task branch> --branch <task branch> --no-parent --agent <id> --prompt <spec>` for a
  new task worktree or `orca agent launch --agent <id> --worktree path:<dir> --prompt <spec>` for an existing one
  (or a no-worktree repo). The task lead creates its own Run (`orca orchestration run-create --objective <text>`),
  starts its sessions as workers of that Run (`orca orchestration worker-start --worktree path:<task worktree>`,
  depth 1), and reports to the run lead with
  `orca orchestration send --to run:<run lead run id> --type status --subject <text> --body <report>`.
- Commands this policy relies on: `orca orchestration run-create`, `orca orchestration task-create`,
  `orca orchestration worker-start`, `orca orchestration check`, `orca orchestration reply`,
  `orca orchestration send`, `orca orchestration worker-show`, `orca orchestration worker-read`,
  `orca orchestration worker-list`, `orca orchestration worker-release`, `orca agent launch`,
  `orca worktree list`, `orca worktree create`, `orca worktree rm`.
- Never use `orca orchestration gate-create` for routine work: a decision gate blocks a task, and this
  plugin adds no blocking step.
- Runs you did not create belong to other coordinators (section 2).
- **Fallback:** when Orca is unavailable or cannot do an operation, use Claude Code background agents
  (`--runner agent`; `isolation: "worktree"` only where section 4 creates a worktree) and name the limitation in
  the report. The Agent tool starts Claude sessions only: a session planned for Codex runs as Claude and its
  review counts as SAME_MODEL (section 10 step 4). The absence of Orca never blocks progress.

## 6. Parallel QA and review

- Start QA and review on a **stable candidate commit**: record its SHA and give it to both workers. Never
  point them at a tree that is still changing. A task's candidate is the task lead's HEAD with every subtask
  committed; the task lead keeps HEAD there while review and QA run.
- A task's review and QA workers are fresh, read-only sessions the task lead starts in the task's own worktree,
  which holds the candidate commit (`orca orchestration worker-start --worktree path:<task worktree>`); never in a
  new worktree. The worker first checks that `git rev-parse HEAD` is that SHA; a result from a changing tree, or
  with HEAD on another commit, is reported as not independent.
- Integration QA is the run lead's: it runs in the existing checkout of the integration branch, never in a task
  worktree (which may already be removed); with no such checkout the dispatch is an error and no worktree is created.
- Exception: in a no-worktree repo (section 4) review and QA run in the main checkout, one at a time, while no
  other task of that repo runs.
- When the candidate moves (a fix lands), list which findings and results refer to the old SHA and must be
  redone; re-run only those.
- Verdicts are PASS, FAIL, NOT_RUN or BLOCKED. NOT_RUN is never a pass.
- Neither lead relies on self-reports: the task lead re-runs the key checks on its candidate, and the run lead on
  the task's result and the integrated tree, for example
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py --repo <key> --paths <files> --status` and the
  suite the spec names.

## 7. Integration checklist (the run lead, per contribution)

- [ ] The task lead reported (section 3) and the task's review PASS is recorded on its HEAD.
- [ ] Diff contains only the task's scope; base and target are the recorded ones.
- [ ] Diff reviewed by the lead; required checks and QA passed; no open blocking finding.
- [ ] No baseline or user files touched; shared-package impact named; file ownership clear.
- [ ] Integrate in dependency order into the task's integration branch, then run the post-integration checks
      on the combined tree.
- [ ] On a conflict or regression: stop that contribution, diagnose it, and dispatch a scoped fix. Never
      discard work and never resolve a conflict by blindly taking one side.

Merging task branches into the task's integration branch is the run lead's decision. Merging into a protected
or shared branch (develop, main, staging, release-*) and pushing stay on the user's request (`git-safety.md`
rule 5).

## 8. Cleanup (mandatory when a task is done)

A task is done when its contribution is integrated and its review and QA are recorded; the whole run is done
when the PR is open (or, without `deliver: pr`, when the gate reports READY_FOR_PR). Then, every time:

1. **Worktrees.** The run lead removes every task worktree its own run created once the task's review PASS is
   recorded and the task is integrated, and the tree is clean (no-worktree repo: nothing to remove):
   `git worktree remove <path>` without `--force`. A worktree with uncommitted or unintegrated work is not
   removed: report it instead. Never remove the main checkout, the integration branch's checkout before its PR is
   open, or a worktree another coordinator owns (section 2).
2. **Task branches.** The user asked for full cleanup, so a task branch whose commits are in the integration
   branch is deleted with its worktree (`git branch -d`, never `-D`). The integration branch stays: it carries
   the PR. `orca worktree rm` also deletes the checked-out local branch when Orca can prove it is merged (see
   its `--help`), and keeps branches it cannot prove merged - use it for Orca-created worktrees.
3. **Agent sessions.** End every Claude and Codex session the run started: each task lead releases its own
   workers (`orca orchestration worker-release` for each settled Orca worker: it closes only that worker's
   terminal and keeps its output readable), the run lead ends each task-lead session once its report is in, and
   any background Agent-tool session still running is stopped. No idle session outlives its task.
4. **Check.** `factory-pipeline.py cleanup plan.json` lists what is left (worktrees and task branches of the
   plan) and prints the commands; it must report CLEAN before the final report. The report's Cleanup column
   names what was removed and what was kept and why.

### Session lifecycle

- **One task, one task lead; one subtask, one fresh session.** Every dispatch starts a new session (Orca worker,
  Orca agent launch or Agent-tool session) for exactly one task or subtask. A session is never reused for another
  task, subtask, phase or a later wave. A scoped fix after a FAIL is a new implementation session in the same task
  worktree. A task lead that has to continue later is a fresh `--phase lead` session that resumes in the existing
  task worktree.
- **One worktree per task, for its whole life.** The task lead, its implementation sub-sessions, reviewer, QA
  worker and any fix run as separate fresh sessions in that one worktree; review and QA never get a new worktree.
  Reviewer and QA sessions are read-only and first check that `git rev-parse HEAD` is the candidate SHA (section 6).
- **Sub-sessions do not commit.** They share the worktree's index; the task lead reviews each diff and commits per
  subtask with explicit paths.
- **Release each session as soon as it reports**, in every repo. In the turn a session reports (`worker_done`,
  the agent's final report, or a review or QA verdict), it is released (`orca orchestration worker-release`, or
  the agent is stopped); the task worktree stays. The next role runs as a fresh session in that worktree: review
  on the candidate SHA, a fix after a FAIL, QA. The task is integrated (section 7) when its review PASS is
  recorded, in wave order (section 10 step 5); only then is its worktree removed (step 1 above). In a no-worktree
  repo only the task work is serialized - the next task starts after the previous task's QA verdict - while its
  sessions are released one by one as they report, like everywhere else. A settled session never waits for a
  later turn or wave.
- **Review and QA run in their own fresh sessions** (section 6, section 10 steps 4 and 6): never in an
  implementation session, never in a lead's session, and never reused across tasks or candidate SHAs.
- **Each lead keeps only its state:** the run lead `plan.json`, the integration branch, the recorded SHAs and the
  verdicts in the pipeline state dir; the task lead its subplan, its commits and verdicts. Neither carries
  session transcripts forward.
- **Handoff.** After each wave, or earlier when its context grows long, the run lead hands off: it ends its
  session with every session of the wave settled, and the next run lead session resumes from
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py status plan.json`, which re-derives where the plan
  stands (a pending task's next command is its `--phase lead` dispatch). Nothing else carries over. A handoff
  adds no gate and no confirmation step.

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
`docs/schemas/pipeline-plan.schema.json`. The pipeline only prints commands and grades state; the leads run them.

1. **Tier.** `factory-pipeline.py tier -- --repo <key> --paths <files>` prints S, M or L and the flow.
   S: the run lead implements in its own session, then the review, QA and gate steps below with one plan task.
   M: the run lead writes `plan.json`. L: a planner worker writes it (`factory-pipeline.py planner --request <text>
   --runner orca`); planning is read-only and runs in the run lead's checkout, never in a new worktree.
2. **Plan.** `factory-pipeline.py validate plan.json` must print OK: disjoint owned paths (or a dependency between the
   tasks), no cycle, waves, no worktree for a no-worktree repo and never two of its tasks in one wave, a reviewer of
   another model, and a warning when one wave shares an exclusive resource (queue those runs).
3. **Task lead.** Per ready task the run lead runs
   `factory-pipeline.py dispatch plan.json --task <id> --phase lead --report-to <run lead run id> --runner orca`.
   It prints the handoff of section 5: a new task worktree from the base on the task branch, or `orca agent launch`
   in the existing task worktree or the main checkout of a no-worktree repo (never a worktree there). The prompt is
   the task spec plus the task-lead rules (section 1). The task lead:
   - writes `subplan.json` (`docs/schemas/pipeline-subplan.schema.json`) and runs
     `factory-pipeline.py subplan validate subplan.json` until it prints OK: every subtask path inside the task's owned
     paths and outside its exclusions, repo-relative (no absolute or `..` path), overlapping subtasks ordered by
     deps, no unknown dep or cycle, each implementer a pipeline agent and each reviewer of the other model; it
     prints the waves (one subtask per wave in a no-worktree repo);
   - per subtask, `dispatch plan.json --task <id> --phase implement --paths <subtask paths> [--agent claude|codex]
     --runner orca` starts a fresh sub-session in the task worktree; the paths must lie inside the task's owned
     paths, and without a task worktree the dispatch fails (run `--phase lead` first);
   - reviews each diff and commits the subtask with explicit paths.
4. **Cross-model review.** Code written by Claude is reviewed by Codex and code written by Codex by Claude
   (registry `pipeline.review_pairing`); a subtask written by the other model gets its own review with
   `--agent <its pair>`. On the task's stable candidate commit the task lead runs
   `dispatch ... --phase review --sha <sha>`, which starts the review in the task worktree (section 6). Record the
   result: `factory-pipeline.py verdict plan.json --task <id> --phase review --sha <sha> --by <agent>
   --state PASS|FAIL --report <file>`. A FAIL goes back to the task as a scoped fix in a fresh implementation
   session in the task worktree (section 8, "Session lifecycle"), committed by the task lead as a new candidate
   SHA. When the paired model is unavailable, a fresh session of the same model reviews, the report names it
   SAME_MODEL, and the gate accepts it only with `--allow-same-model`; `--runner agent` (Claude only) marks a
   session planned for Codex SAME_MODEL in its prompt. The task lead also runs the per-task QA
   (`dispatch ... --phase qa --sha <sha>`, in the task worktree), then reports to the run lead (section 3).
5. **Integrate** (section 7), in wave order, into the integration branch named by the plan's `topic`. The run lead
   follows the tasks with `factory-pipeline.py status plan.json`.
6. **QA.** Once per repo on the integration HEAD, in the integration branch's existing checkout (section 6):
   `dispatch ... --task integration:<repo> --phase qa --sha <head>`; in a no-worktree repo also per task, before the
   next task starts (`--task <id>`). The QA worker fills `templates/pipeline/qa-report.md`; the lead records
   `verdict ... --phase qa`.
7. **READY_FOR_PR.** `factory-pipeline.py gate plan.json` is a read-only report: every task integrated, reviewed PASS
   by its paired model on a commit whose owned paths have not changed since, QA PASS on each integration HEAD,
   clean integration trees, fast checks PASS and not STALE (`run-checks.py --status`), and no pipeline worktree in
   a no-worktree repo. Anything else is a listed blocker: fix it and re-run the affected review or QA only.
8. **PR.** When the user put `deliver: pr` in the task (plan `deliver: "pr"`) and the gate prints READY_FOR_PR, the
   run lead pushes the integration branch and opens the PR with the commands the gate prints, body = the final
   report (`report.md`). This is the delivery exception of `git-safety.md` rule 5. Merging stays with the user;
   without `deliver: pr` the task ends at READY_FOR_PR in the report.
9. **Cleanup.** Section 8, every time: remove the run's worktrees and merged task branches, end every Claude
   and Codex session (each was released when it reported), and run `factory-pipeline.py cleanup plan.json` until it
   reports CLEAN.

This policy introduces no tripwire, no latch and no new confirmation step.
