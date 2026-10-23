# Parallel work: lead, workers, worktrees, Orca

The single policy for splitting a Factory task across agents. Other files point here; none restates it.
It adds no gate and no prompt: when something is missing, the task reports it and other work continues.

## 1. Roles

**Lead/Integrator** - the main Claude Code session, always. It:
1. owns the task scope and splits it into tasks with disjoint file ownership;
2. records each task's base commit and integration target;
3. writes the task spec for every dispatch (section 3);
4. creates or requests one worktree per implementation task (section 4);
5. dispatches and supervises workers, and answers their questions;
6. assigns shared exclusive resources, one task at a time;
7. reviews every diff and re-verifies the key checks itself;
8. decides when a contribution is ready and integrates it (section 7);
9. writes the final report with the parallel-work ledger (`report.md`) and cleans up (section 8).

**Implementation worker** - works only in its own worktree and branch, runs the targeted checks from its
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

- One worktree per implementation task, on a new `<type>/<area>/<topic>` branch from the recorded base.
- Only the dispatching tool creates worktrees: Orca (`orca orchestration worker-start --worktree <selector>`,
  or `orca worktree create`) or a Claude Code agent with `isolation: "worktree"`. Never a second clone,
  never a nested repository.
- Never edit another task's worktree. Read-only inspection of it is fine.
- One mutating command per worktree at a time (`git-safety.md` rule 14) still applies.
- **Unity:** at most one Unity writer worktree per client project. Each extra client worktree needs its own
  multi-GB `Library/` import, so client tasks usually run in sequence; server and package tasks parallelise well.
- **Shared exclusive resources** (Unity Editor, a local or scratch Docker stack, the test lab, fixed ports):
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
- Each QA and review worker runs in its own worktree checked out at that SHA
  (`orca orchestration worker-start --worktree new-top-level --base-branch <sha>`, or `isolation: "worktree"`,
  which starts from the lead's current HEAD). The worker first checks that `git rev-parse HEAD` is that SHA;
  a result from a shared or changing tree is reported as not independent.
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

## 8. Cleanup

Remove only worktrees that the lead's own tasks created, after they are integrated and clean, with
`git worktree remove <path>` without `--force`. Keep the task branches unless the user asks to delete them.
`orca worktree rm` also deletes the checked-out local branch when Orca can prove it is merged (see its
`--help`), so use it only for a worktree whose branch is disposable (an Orca-created QA or review branch
with no commits) or whose branch the user asked to delete. Release settled Orca workers with
`orca orchestration worker-release`.

## 9. Not authorized by this policy

- Tags and releases: only with explicit release authorization from the user in the current task
  (`git-safety.md` rule 5 and the release flow).
- Production deploys.
- Consequential workflow dispatch, secrets, shared infrastructure and production data: these are registry
  `human_gates` and keep their rules.
- Repositories outside the task.
- Bypassing branch protection or required CI.

This policy introduces no tripwire, no latch and no new confirmation step.
