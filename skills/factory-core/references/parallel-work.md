# Parallel work: lead, workers, worktrees, Orca

The single policy for splitting a Factory task across agents. Other files point here; none restates it.
It adds no gate and no prompt: when something is missing, the task reports it and other work continues.
The delivery pipeline (section 10, `scripts/factory-pipeline.py`) is how the lead runs this policy end to end:
tier, plan, task leads, cross-model review, QA, READY_FOR_PR, PR.

Work runs on two levels. The **run lead** splits the request into plan tasks and gives each task one worktree
and one **task lead** session. The task lead splits its task into subtasks and runs everything for that task -
implementation, cross-model review, QA, fixes - as fresh sessions in that one worktree (or, where section 4
"Child worktrees" says so, in an Orca child of it), then reports to the run lead, which integrates and cleans up.

<!-- policy:speed-rule -->
Prefer many short, focused parallel sessions over one long session; every spec stays short: objective, owned paths, checks, report format.

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
It does not start a task's sub-sessions and never edits a task's files itself: that is the task lead's job, for
every tier. A small (S tier) change is a plan with one task and still gets one task lead.

<!-- policy:run-lead-never-implements -->
The run lead never edits task files; an S-tier task is a one-task plan with its own task lead.

**Task lead** - one fresh session per plan task, in that task's worktree (a no-worktree repo: its main checkout,
section 4). It is not an Orca worker of the run lead (section 5): it creates its own Orca Run. It:
1. plans its task and splits it into subtasks with disjoint paths inside the task's owned paths; subtasks with
   disjoint paths run in parallel, the others in order (`factory-pipeline.py subplan validate`, section 10 step 3);
2. starts one fresh Claude or Codex session per subtask in the same worktree (or its child, section 4), never
   reused for another subtask;
3. reviews each sub-session's diff and commits that subtask itself with explicit paths (a child subtask: merges
   the child branch into the task branch and removes the child, section 4);
4. with every subtask committed, starts a fresh cross-model review session and a QA session on that HEAD in the
   same worktree (a tier S or prose-only task: no QA session, the task lead runs the task QA command itself after the
   review PASS, section 10 "QA tiers"); a FAIL goes to a fresh fix session;
5. releases every session as soon as it reports (section 8, "Session lifecycle");
6. reports to the run lead (section 3) and records the review and QA verdicts.
It never pushes, merges, tags or removes its worktree.

<!-- policy:task-lead-claude -->
The task lead is a Claude session (registry pipeline.lead_agent), whatever the task's implementer, and Codex only when Claude is unavailable; implementation, review and QA sessions keep the cross-model pairing.

**Implementation sub-session** - edits only its subtask's paths in the task worktree, runs the targeted checks
from its spec, and reports to the task lead. It does not commit, stage or stash: the worktree has one shared
index and the task lead commits. A sub-session in a child worktree (section 4) commits its paths on its own child
branch and nothing else.

<!-- policy:only-task-lead-commits -->
Sub-sessions in the shared task worktree never commit, stage or stash; only the task lead commits there, with explicit paths.

**QA worker** - checks acceptance criteria, test coverage, regressions, edge and failure cases on a recorded
candidate SHA. Read-only unless its spec says otherwise.
**Review worker** - checks architecture, scope isolation, safety rules and conventions. Read-only; it runs no
suites, only a repro test when a finding needs one (section 10 "QA tiers").

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
lead's spec for a sub-session is the same task spec narrowed to the subtask's paths. Specs stay short (section 1,
speed rule): no step lists; the session reads this policy for the how.

A sub-session's report contains: changed paths; each check with exact counts and log path (or NOT_RUN with the
command and reason); known limitations; anything out of scope it noticed.

The task lead's completion report to the run lead contains: outcome; worktree path; branch; base SHA; HEAD SHA;
each subtask with its commit; the review and QA verdicts (state, SHA, model); changed paths; each check with
exact counts and log path (or NOT_RUN with the command and reason); known limitations; anything out of scope it
noticed.

## 4. Worktrees

- One worktree per plan task, for its whole life, on the task branch `<topic>-<task id>` from the recorded base
  (the plan `topic` is the `<type>/<area>/<topic>` integration branch; a no-worktree repo has no per-task branch,
  below). It is created for the task lead; the task
  lead's implementation sub-sessions, review, QA and fix sessions run in it (section 8, "Session lifecycle"),
  except a session placed in an Orca child worktree ("Child worktrees" below).
- Only the dispatching tool creates worktrees: Orca (`orca worktree create`, the run lead's task-lead handoff, or
  an Orca child worktree) or a Claude Code agent with `isolation: "worktree"`. Never a second clone, never a
  nested repository. A session the task lead starts joins the existing task worktree or a child of it; when there
  is no task worktree, dispatch is an error and no worktree is created.
- Never edit another task's worktree. Read-only inspection of it is fine.
- One mutating command per worktree at a time (`git-safety.md` rule 14) still applies: parallel sub-sessions
  edit disjoint files and run no git write; only the task lead stages and commits.
- **No worktree in a Unity project.** A repo with registry `worktrees: false` (the client) or a
  `ProjectSettings/ProjectVersion.txt` at its root (registry `pipeline.no_worktree_markers`) never gets a
  worktree, for any role: each one needs its own multi-GB `Library/` import. Its task lead runs in the main
  checkout on the plan `topic` branch, which is its task branch: every task of that repo commits there in turn (the handoff is `orca agent launch --worktree path:<main checkout>`, never a
  worktree create or a new top-level worker); its subtasks run one after another, never two sessions editing or
  importing the project at once; its review and QA sessions run in that checkout too, read the commits there and
  change nothing. Its tasks run one after another: the next task starts after the previous task's QA verdict.
  Package, server, tool and plugin repos use worktrees and parallelise well.
- **Shared exclusive resources** (Unity Editor and Unity test runs - one at a time across the client and every
  package test project, registry `pipeline.exclusive_resources` -, a local or scratch Docker stack, the test lab, fixed ports):
  the lead assigns each to one task at a time. A task without the resource reports the dependent check as
  `NOT_RUN` with the exact command and reason; other work continues. There is no prompt.
- **Full test runs are a shared resource too.** One full run per machine (the run-all lock): a full
  `tests/run-all.sh` takes a per-machine lock, and a second one waits. CI is the full-suite gate: no session runs the
  full suite before a PR (only a release does). Integration QA runs `tests/run-all.sh --workspace-only` and every
  other session runs its tier command (section 10 "QA tiers"). Four parallel full runs made every suite 2-4x
  slower and timed some out. Never create a worktree or branch while a full run is in flight: the shared
  `.git/config` check fails (`.claude/CLAUDE.md` "Operating lessons").
- **Lesson: `orca worktree create` writes `branch.<name>.base` into the shared `.git/config`**, which breaks the
  shared-config check of other sessions' full runs. `git worktree add --no-track -b <branch> <path> <base>` writes
  nothing to `.git/config` (verified: the config hash is unchanged). So `dispatch --phase lead` prefers it for a new
  task worktree and then starts the lead with `orca agent launch --worktree path:<path>`; `orca worktree create` stays
  the fallback when git cannot create the worktree.

### Child worktrees

Both levels may place a session in an Orca child worktree when that is faster or safer than sharing. The shared
worktree is the default for every session a task lead starts (implement, review, QA) and for the run lead's helper
sessions; only `dispatch --phase lead` defaults to `child` (a new task worktree under the integration checkout,
"Run lead" below). Choose per session:

<!-- policy:placement-table -->
| Placement | When | How |
|---|---|---|
| shared (default) | small subtasks with disjoint files and narrow tests; review or QA while nothing else edits | the task worktree (run lead: the integration checkout); `placement: "shared"` |
| child | parallel subtasks that both run full suites or write generated or build output; risky or experimental work; QA that needs a clean frozen checkout while others still edit | `orca orchestration worker-start --worktree new-child` (a session) or `orca worktree create --parent-worktree <selector>` (a worktree); `placement: "child"` + `reason` |

- **Run lead.** `dispatch --phase lead` creates a new task worktree as an Orca child of the checkout that has the
  plan `topic` checked out (`--parent-worktree path:<checkout>`); only when no checkout has it, `--no-parent` (a
  stderr note says so). `--placement shared` forces `--no-parent`; `--placement child` is the default. Orca lineage
  only: the git layout is the same. Helper sessions -
  integration QA (`--task integration:<repo> --phase qa --placement child`) or a quick fix - may run in a child
  of the integration checkout instead of sharing it.
- **Task lead.** Each subplan subtask records `placement` (`shared` or `child`) and, for `child`, a `reason`.
  `dispatch plan.json --task <id> --phase implement|review|qa --subplan subplan.json --subtask <sid>` takes the
  subtask's paths, agent and placement and prints the matching `--worktree` (`path:<task worktree>` or
  `new-child`, run from the task worktree).
- A child session commits on its own child branch (`<task branch>--<subtask or phase>`), with explicit paths. Review
  and QA children are named `<parent>--[<subtask>--]<phase>-<sha7>`, so the review and QA of one candidate never collide.

<!-- policy:child-merge-remove -->
The owner merges a child's branch into its parent branch and removes the child at once (`orca worktree rm --worktree path:<child>`).

<!-- policy:child-no-run-all -->
Never create or remove a child worktree while a full tests/run-all.sh runs: every checkout shares one .git/config.

- `factory-pipeline.py status` and `cleanup` list each leftover child ("child of <task>") with its merge state.
- A no-worktree (Unity) repo never gets a child: `subplan validate` and `dispatch` refuse `placement: child` there.

## 5. Orca (preferred coordinator when available)

- Detect: `orca status --json`. Orca is usable when `result.runtime.reachable` is `true`.
- Load the version-matched coordinator and worker contract with `orca skills get orchestration` before
  the first dispatch, and follow it. This file does not restate it.
- **No nested workers.** Orca allows one level of workers (`nested_worker_depth_exceeded`, maximum depth 1); never
  route around it. So the task lead is not a worker of the run lead: the run lead starts it as a handoff,
  `orca worktree create --name <task branch> --branch <task branch> --parent-worktree path:<integration checkout>
  --agent <id> --prompt <spec>` for a new task worktree (`--no-parent` only when no checkout has the topic, section
  4) or `orca agent launch --agent <id> --worktree path:<dir> --prompt <spec>` for an existing one
  (or a no-worktree repo). The task lead creates its own Run (`orca orchestration run-create --objective <text>`),
  starts its sessions as workers of that Run (`orca orchestration worker-start --worktree path:<task worktree>`,
  depth 1), and reports to the run lead with
  `orca orchestration send --to run:<run lead run id> --type status --subject <text> --body <report>`.
- Commands this policy relies on: `orca orchestration run-create`, `orca orchestration task-create`,
  `orca orchestration worker-start`, `orca orchestration check`, `orca orchestration reply`,
  `orca orchestration send`, `orca orchestration worker-show`, `orca orchestration worker-read`,
  `orca orchestration worker-list`, `orca orchestration worker-release`, `orca agent launch`,
  `orca worktree list`, `orca worktree create`, `orca worktree rm`.
- **Orca message traps** (seen in this plugin's runs):
  - Only a dispatched Orca worker can send `--type escalation` or `worker_done`; from any other session Orca
    refuses with "No active Dispatch belongs to this message sender". A task lead is not a worker of the run lead,
    so it reports with `--type status` (or asks with `--type question`).
  - `orca orchestration check --wait --types <types>` still returns heartbeats: a wait loop acks each batch and
    keeps waiting until a message of the wanted type arrives, instead of treating the heartbeat as the answer.
    The run lead's single waiter is `scripts/orca-wait.sh --run <id>` (one instance per Run, by a lock file in the state dir).
  - A multi-line `--prompt` passed through `cmd.exe` (Windows) is cut at the first newline. Write the spec to a file
    and send a one-line prompt that names it (`factory-pipeline.py dispatch` does this).
  - After every worker start or launch with `--agent codex`, read the session's terminal
    (`orca orchestration worker-read` for a worker) until it shows the prompt being worked on. `input_accepted` alone is no proof:
    a Codex CLI (v0.166) once sat idle at an empty prompt.
- **Codex, else Claude.** Codex runs the rpg-factory hooks only after the user has trusted them once in Codex (a
  one-time step outside the run; `AGENTS.md`). When a Codex session cannot start or never picks up its prompt
  (trust prompt, CLI error, quota, idle terminal, a 401), the lead marks it down for the run
  (`factory-pipeline.py agents plan.json --down codex --reason <text>`) and dispatches the role again: it routes to
  Claude, a review by it carries the recorded fallback (section 10 "Which model", step 4), and the report names the
  substitution. Codex never blocks the run; the same holds the other way round when Claude is down.
- Never use `orca orchestration gate-create` for routine work: a decision gate blocks a task, and this
  plugin adds no blocking step.
- Runs you did not create belong to other coordinators (section 2).
- **Orca first inside Orca.** In an Orca session (`ORCA_WORKTREE_ID` or `ORCA_AGENT_HOOK_ENDPOINT` set) with the
  runtime reachable, `factory-pipeline.py planner` and `dispatch` default to `--runner orca` and refuse
  `--runner agent` (exit 2, naming `--runner orca`) unless `--orca-unavailable <reason>` is given; the reason goes
  into the session prompt so its report names it. Reason (user feedback 2026-11-07): the user works in Orca, and
  Agent-tool task leads with plain git worktrees are invisible in Orca.
- **Fallback:** outside Orca, or when Orca is unavailable or cannot do an operation (inside Orca: with
  `--orca-unavailable <reason>`), use Claude Code background agents (`--runner agent`; `isolation: "worktree"`
  only where section 4 creates a worktree) and name the limitation in the report. The Agent tool starts Claude
  sessions only: a session planned for Codex runs as Claude and its review counts as SAME_MODEL (section 10
  step 4). The absence of Orca never blocks progress.

## 6. Parallel QA and review

- Start QA and review on a **stable candidate commit**: record its SHA and give it to both workers. Never
  point them at a tree that is still changing. A task's candidate is the task lead's HEAD with every subtask
  committed; the task lead keeps HEAD there while review and QA run.
- A task's review and QA workers are fresh, read-only sessions the task lead starts in the task's own worktree,
  which holds the candidate commit (`orca orchestration worker-start --worktree path:<task worktree>`), or in a
  child at that SHA when the placement table (section 4) says child; never in any other new worktree. The worker first checks that `git rev-parse HEAD` is that SHA; a result from a changing tree, or
  with HEAD on another commit, is reported as not independent.
- Integration QA is the run lead's: it runs in the existing checkout of the integration branch, or in a child of
  that checkout at the integration HEAD (section 4), never in a task worktree (which may already be removed); with
  no such checkout the dispatch is an error and no worktree is created.
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
- [ ] Integrate in dependency order into the task's integration branch with `git merge --no-ff` (section 10
      step 5), then run the post-integration checks on the combined tree.
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
   `git worktree remove <path>` without `--force` (an Orca-created one: `orca worktree rm`, item 2). A leftover
   child (section 4) is merged into its parent branch, then removed with `orca worktree rm --worktree path:<child>`. A worktree with uncommitted or unintegrated work is not
   removed: report it instead. Never remove the main checkout, the integration branch's checkout before its PR is
   open, or a worktree another coordinator owns (section 2).
2. **Task branches.** The user asked for full cleanup, so a task branch whose commits are in the integration
   branch is deleted with its worktree (`git branch -d`, never `-D`). The integration branch stays until its PR is
   merged: it carries the PR (item 5). `orca worktree rm` also deletes the checked-out local branch when Orca can prove it is merged (see
   its `--help`), and keeps branches it cannot prove merged - use it for Orca-created worktrees.
3. **Agent sessions.** End every Claude and Codex session the run started: each task lead releases its own
   workers (`orca orchestration worker-release` for each settled Orca worker: it closes only that worker's
   terminal and keeps its output readable), the run lead ends each task-lead session once its report is in, and
   any background Agent-tool session still running is stopped. No idle session outlives its task.
4. **Check.** `factory-pipeline.py cleanup plan.json` lists what is left (worktrees and task branches of the
   plan, leftover children, and settled Orca workers not released in each task lead's Run: task `orca_run` or `--orca-run <id>`,
   read-only `worker-list`; no orca is NOT_AVAILABLE) and prints the commands; it must report CLEAN before the
   final report. The report's Cleanup column
   names what was removed and what was kept and why.
5. **After the integration PR is merged into main** (user 2026-11-09). The run lead finishes the run's cleanup:
   - removes the integration checkout or worktree (`git worktree remove <path>`, or `orca worktree rm`), never the
     main checkout;
   - deletes every merged task branch and the integration branch locally (`git branch -d`, never `-D`) and on
     origin (`git push origin --delete <branch>`), only branches of this plan that main contains (check with
     `git merge-base --is-ancestor <branch> origin/main` or `git branch --merged origin/main`); a branch main does
     not contain stays and is reported;
   - releases every worker of the run (item 3);
   - starts the next plan from main: a new integration branch from the updated main, never from the deleted one.

   `factory-pipeline.py cleanup plan.json` lists these commands (worktrees, local and origin branches, unreleased
   workers) and reports CLEAN only when none is left.

### Run report and plan edits

- **Run report in the repo.** At integration the run lead writes `docs/plans/<plan>/report.md` and commits it with
  the integration: sessions per task (role, model, Orca Run), verdicts (phase, SHA, model, result), checks with exact
  counts, and limitations. Verdicts and specs stay in the per-machine state dir; a new machine re-runs review and
  QA instead of reusing them (`docs/plans/README.md`).
- **Plan edits are atomic.** Write the edit to a copy, `factory-pipeline.py validate` the copy, then replace the
  plan with it. Reason: on 2026-11-06 a run-lead edit left `plan.json` invalid for about a minute, and a task lead
  read the invalid plan mid-dispatch.

### Session lifecycle

- **One task, one task lead; one subtask, one fresh session.** Every dispatch starts a new session (Orca worker,
  Orca agent launch or Agent-tool session) for exactly one task or subtask. A session is never reused for another
  task, subtask, phase or a later wave. A scoped fix after a FAIL is a new implementation session in the same task
  worktree. A task lead that has to continue later is a fresh `--phase lead` session that resumes in the existing
  task worktree.
- **One worktree per task, for its whole life.** The task lead, its implementation sub-sessions, reviewer, QA
  worker and any fix run as separate fresh sessions in that one worktree, or in a short-lived child of it (section 4).
  Reviewer and QA sessions are read-only and first check that `git rev-parse HEAD` is the candidate SHA (section 6).
- **Sub-sessions do not commit.** They share the worktree's index; the task lead reviews each diff and commits per
  subtask with explicit paths. A child session commits only on its child branch (section 4).
- **Release each session as soon as it reports**, in every repo. In the turn a session reports (`worker_done`,
  the agent's final report, or a review or QA verdict), it is released (`orca orchestration worker-release`, or
  the agent is stopped); the task worktree stays. The next role runs as a fresh session in that worktree: review
  on the candidate SHA, a fix after a FAIL, QA. The task is integrated (section 7) when its review PASS is
  recorded, in wave order (section 10 step 5); only then is its worktree removed (step 1 above). In a no-worktree
  repo only the task work is serialized - the next task starts after the previous task's QA verdict - while its
  sessions are released one by one as they report, like everywhere else. A settled session never waits for a
  later turn or wave. A review or QA session whose candidate is superseded (a new HEAD) is released at once,
  not at task end; `factory-pipeline.py status plan.json --orca-run <run id>` lists the Run's settled workers that
  are not released.
- **Releasing a session does not stop its test processes.** On Windows `orca orchestration worker-stop` and
  `worker-release` close the worker's terminal, but test processes it started (`run-all.sh`, `parallel-policy.test.sh`
  and their children) keep running, reparented, and load the machine (seen with a stopped QA `run-all.sh` and a
  reviewer's suites). Before a worker that runs tests is released, it stops its own test process tree; the lead then
  checks for leftover test processes whose cwd is the task worktree and stops only those.
- **Review and QA run in their own fresh sessions** (section 6, section 10 steps 4 and 6): never in an
  implementation session, never in a lead's session, and never reused across tasks or candidate SHAs.
- **Few sessions at once.** Under memory pressure Claude Code reaps background shells, which kills long test runs
  and waits mid-way. Keep open sessions few, run only the tier command of each role (section 10 "QA tiers"; one
  full run per machine, section 4), and release each one as soon as it reports.
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

<!-- policy:no-worktree-repo -->
A no-worktree (Unity) repo never gets a worktree; its task lead and all its sessions run in its main checkout.

**Which model.** Each plan task may carry a `kind`, and each subtask names an `implementer` or a `kind` (`subplan
validate` errors on neither); the implementer is the explicit `implementer`, else registry
`pipeline.agent_routing[kind]`, else `agent_routing.default`, else `default_implementer`, then mapped through availability:

<!-- policy:which-model -->
| Role or kind | Model | Registry |
|---|---|---|
| lead, plan, orchestration | claude | `lead_agent`, `agent_routing` |
| docs, policy (skill and reference prose) | claude | `agent_routing` |
| design (cross-file design, domain content) | claude | `agent_routing` |
| code, test, fix, refactor, generated | codex | `agent_routing` |
| review | the other model | `review_pairing` |
| QA | the model that did not implement (`qa_prefer` codex when codex did not implement) | `qa_prefer` |

- **Token rule.** The Claude task lead plans and delegates code to Codex and does not implement; QA runs go
  to Codex when Claude implemented (QA never runs on the implementer's model, except as a fallback: with one model
  available, that model runs QA in a fresh QA session, which the gate accepts for every tier). Only a QA verdict the
  task lead records itself (no QA session, note starting `tier S`) is limited to tier S tasks ("QA tiers" in section
  10). An explicit `implementer` against
  the table needs a `reason`: `validate` and `subplan validate` warn without one, and warn when 3 or more tasks or
  subtasks all use one model (warnings, never errors).
- **Availability never stops a task.** Available agents are detected: each `pipeline.agents.<a>.bin` on PATH,
  refined by the Orca account list when Orca runs; `RPG_FACTORY_AGENTS` (comma list) overrides the detection. A
  runtime MODEL_UNAVAILABLE (revoked token, 401) is recorded with
  `factory-pipeline.py agents plan.json --down <agent> --reason <text>` (`--up <agent>` clears it) and holds for
  the run. Every role falls back to the available model: with only Claude, Claude implements, reviews and runs QA;
  with only Codex, Codex does all of it and also leads. A fallback review carries
  `SAME_MODEL (fallback: <model> unavailable)` and the gate accepts it (step 4). `dispatch` and `status` print
  each role's model and why (`dispatch`: `model: <role> -> <agent> (<why>)`; `status`: `model: <task> <role> -> <agent>
  (<why>)`); no command fails because a model is missing.
- **Recorded implementer.** `dispatch --phase implement` records the model it started, per task and per
  subtask. Review, QA, `verdict` and the gate pair against that recorded implementer (the planned routing when
  none is recorded), never against current availability: a model that comes back after a fallback does not change
  who reviews. A subtask whose recorded implementer differs from the task implementer (or that is the task
  reviewer's own model) needs its own review: PASS by its pair, or a dispatch-recorded fallback review noted
  `SAME_MODEL (fallback: <pair> unavailable)`. Without it the gate blocks, naming the subtask, its recorded
  implementer and the reviewer it needs; the task review never covers it.

1. **Tier.** `factory-pipeline.py tier -- --repo <key> --paths <files>` prints S, M or L and the flow.
   S: the run lead writes a `plan.json` with one task and dispatches its task lead (step 3; the task worktree, or
   the main checkout of a no-worktree repo); the run lead never implements it in its own session. Steps 4-8 follow
   with that one task. M: the run lead writes `plan.json`. L: a planner worker writes it (`factory-pipeline.py planner --request <text>
   --runner orca`); planning is read-only and runs in the run lead's checkout, never in a new worktree.
2. **Plan.** `factory-pipeline.py validate plan.json` must print OK: disjoint owned paths (or a dependency between the
   tasks), no cycle, waves, no worktree for a no-worktree repo and never two of its tasks in one wave, a reviewer of
   another model, and a warning when one wave shares an exclusive resource (queue those runs).
3. **Task lead.** Per ready task the run lead runs
   `factory-pipeline.py dispatch plan.json --task <id> --phase lead --report-to <run lead run id> --runner orca`.
   It prints the handoff of section 5: a new task worktree on the task branch, or `orca agent launch`
   in the existing task worktree or the main checkout of a no-worktree repo (never a worktree there). A first-wave
   task branches from `repos.<key>.base`; a later-wave task (one with deps) branches from the plan's `topic`
   integration branch when it exists, because that branch carries the earlier waves. `repos.<key>.base` stays the
   comparison base of `status` and the gate: never point it at the topic (then `base..head` counts nothing and
   integrated tasks show as pending). The prompt is the task spec plus the task-lead rules (section 1). The task lead:
   - writes `subplan.json` (`docs/schemas/pipeline-subplan.schema.json`) and runs
     `factory-pipeline.py subplan validate subplan.json` until it prints OK: every subtask path inside the task's owned
     paths and outside its exclusions, repo-relative (no absolute or `..` path), overlapping subtasks ordered by
     deps, no unknown dep or cycle, each implementer a pipeline agent and each reviewer of the other model; it
     prints the waves (one subtask per wave in a no-worktree repo);
   - records per subtask `placement` (`shared` or `child` + `reason`; section 4, "Child worktrees");
   - per subtask, `dispatch plan.json --task <id> --phase implement --subplan subplan.json --subtask <sid> --runner orca`
     (or `--paths <subtask paths> [--agent claude|codex] [--placement shared|child]`) starts a fresh sub-session in
     the task worktree or a child of it; the paths must lie inside the task's owned paths, and without a task
     worktree the dispatch fails (run `--phase lead` first);
   - reviews each diff and commits the subtask with explicit paths, or merges a child's branch and removes the child.
4. **Cross-model review.** Code written by Claude is reviewed by Codex and code written by Codex by Claude
   (registry `pipeline.review_pairing`); a subtask written by the other model gets its own review with
   `--agent <its pair>`, recorded with `verdict ... --subtask <sid>`, which keeps it apart from the task review.
   On the task's stable candidate commit the task lead runs
   `dispatch ... --phase review --sha <sha>`, which starts the review in the task worktree (section 6). Record the
   result: `factory-pipeline.py verdict plan.json --task <id> [--subtask <sid>] --phase review --sha <sha> --by <agent>
   --state PASS|FAIL --report <file> [--note TEXT] [--implementer AGENT] [--fallback '<model> unavailable']`
   (`--report` names an existing file, `--note` takes free text; `--implementer` declares the true implementer and is
   refused when it conflicts with the one the dispatch recorded; the retrospective `--fallback '<model> unavailable'`
   needs `--subtask <sid>`). A FAIL goes back to the task lead (`status` names `--phase lead`, which
   resumes it in the task worktree or the main checkout of a no-worktree repo): it starts a scoped fix in a fresh
   implementation session there (section 8, "Session lifecycle") and commits it as a new candidate SHA.
   `--phase implement` in the shared placement starts a sub-session that does not commit, in every repo; with
   `--placement child` (or a `child` subtask) the session commits on its own child branch only, and the task lead
   merges that branch and removes the child (section 4); `--paths` inside the
   task's exclusions is refused. When the paired model is unavailable ("Which model" above), a fresh session of
   the same model reviews, its prompt and report carry `SAME_MODEL (fallback: <model> unavailable)`, and
   `dispatch --phase review` records that fallback for the candidate SHA. `verdict` stamps the fallback only when
   that SHA's review dispatch was a recorded fallback and `--by` is its reviewer, not from availability at verdict
   time. A same-model review made before dispatch recorded fallbacks (for example during an outage of the paired
   model) is recorded after the fact for a subtask review only, with `verdict --subtask <sid> --fallback '<model>
   unavailable' --note <why>`: `--subtask` and `--note` are required and `--by` must be the implementer's model (the
   bare form `--fallback <model>` is still refused while that model is available). The task level refuses the
   retrospective form: a task review keeps a dispatch-recorded fallback or `gate --allow-same-model`. The gate
   accepts a recorded fallback and prints it as an accepted
   fallback with its reason and note, never silently; it needs `--allow-same-model` only for an unrecorded
   SAME_MODEL review. `--runner agent` (Claude only) marks a session planned for Codex SAME_MODEL in its prompt.
   The task lead also runs the per-task QA
   (`dispatch ... --phase qa --sha <sha>`, in the task worktree; its spec names the task tier command and forbids a
   full run; a tier S task: the lead runs that command itself, "QA tiers" below), then reports to the run lead
   (section 3).
5. **Integrate** (section 7), in wave order, into the integration branch named by the plan's `topic`. The run lead
   follows the tasks with `factory-pipeline.py status plan.json`. Every task, and every later wave, is integrated
   with `git merge --no-ff <task branch>`: the gate credits a later wave's changes under an earlier task's or
   subtask's paths only through the merge commits on the topic's first-parent chain (each later task with its own
   current PASS review, and QA where required). A fast-forward or a squash leaves those changes unattributed and
   the earlier review STALE. A recorded verdict holds for its task's
   fingerprint (objective, owned paths, exclusions, acceptance, checks, agents): a plan edit that only changes deps
   keeps it, while changing a task's paths or acceptance makes it stale. Re-run `status` after any plan edit.
6. **QA.** Once per repo on the integration HEAD, in the integration branch's existing checkout (section 6):
   `dispatch ... --task integration:<repo> --phase qa --sha <head>`, whose spec names what CI cannot run
   (`tests/run-all.sh --workspace-only`) and the CI watch (`gh pr checks <pr> --watch`; CI green is the full gate,
   "QA tiers" below); in a no-worktree repo also per task, before the next task starts (`--task <id>`). The QA worker fills `templates/pipeline/qa-report.md`; the lead records
   `verdict ... --phase qa` (a FAIL with `--failed-suites`, which the re-QA spec reruns).
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

**QA tiers.** No identical tree is tested twice and a task never runs the whole suite: each role runs one command,
which `dispatch --phase qa` prints (registry `pipeline.qa_tiers`).

<!-- policy:qa-tiers -->
| When | Runs | Who |
|---|---|---|
| Task QA, each candidate | `tests/run-all.sh --affected --base <review base> [--only-suites <check suites>] -j 2`: the suites the task's checks name (only those `tests/run-all.sh --list-suites` lists) plus the suites `tests/affected.py` maps to its changed files, each suite once; other checks are extra commands; never a full run | a fresh QA session in the task worktree |
| Re-QA after a FAIL | the failed suites recorded with `verdict --failed-suites`, with the task check suites, plus `--affected --base <previous FAIL candidate>` | a fresh QA session on the fix candidate |
| Tier S or prose-only task (every owned path a .md file, under changelog.d/ or a skills/ directory) | the task QA command, after the review PASS; no QA session | the task lead: `verdict --phase qa --state PASS --by <lead> --note 'tier S: lead ran task suites'`; a lead-run QA verdict counts for tier S only |
| Reviewer | no suites; only a repro test when a finding needs one | the review session |
| Integration QA, once per batch before the PR | `tests/run-all.sh --workspace-only` (only what CI cannot run: the live-workspace suites and checks, with the suite reuse) plus `gh pr checks <pr> --watch`: CI green is the full gate (registry `pipeline.qa_tiers` integration `ci+workspace`) | the run lead's integration QA session |
| Release | `tests/run-all.sh --release` and `tests/dogfood.sh --installed` (unchanged) | the release session (`.claude/CLAUDE.md` "Releases") |

- **CI is the full gate.** No full local run before a PR: CI (`.github/workflows/tests.yml`, `--no-workspace
  --no-claude`) runs the full suite, and `--workspace-only` covers the rest. While CI runs, start the next task; come
  back for `gh pr checks <pr> --watch` and fix a red check before merging. Only a release runs
  `tests/run-all.sh --release` and `tests/dogfood.sh --installed`.
- **Tier S.** `dispatch --phase qa` marks a task tier S when the plan or the task has tier S or every owned path is
  prose (`pipeline_route.prose_path`): a `.md` file anywhere, a path under `changelog.d/`, or a `skills/` directory
  path (no dot in its last segment). A non-`.md` file under `skills/`, `docs/*.json` and `docs/schemas/` are machine
  inputs, not prose: `docs/` alone does not make a task tier S. The gate accepts a QA verdict the task lead ran
  itself (no QA session, note starting `tier S`) only for such a task. A QA PASS from a fresh QA session is accepted
  as before for every tier: by the other model, or by the implementer's model as the one-model fallback of the Token
  rule.
- **Re-QA.** A QA FAIL is recorded with `verdict --phase qa --state FAIL --failed-suites <tests/a.sh,...>`. The next
  `dispatch --phase qa` on a new candidate prints `--affected --base <that FAIL's candidate>` with those suites
  and the task check suites in `--only-suites`.
- **The lock.** A full run (no `--affected` or `--only-suites`, or any `--release` run) takes a per-machine lock in
  the persistent state dir; a second full run waits (`waiting for full run <pid> in <checkout>`), `--no-wait` exits 3
  instead, and a lock whose holder is dead is taken over (`run-all: taking over stale full-run lock (<pid>)`).
- **Reuse.** A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS
  record of the same clean tree with at least the same coverage (`reused full run at <HEAD> (tree <tree>, <date>)`;
  a `--no-workspace` or `--no-claude` record does not satisfy a run without that flag). Each suite's PASS is also
  recorded under a hash of its inputs (`tests/affected.py hashes`, the conservative rule: the suite file, the paths
  it names, every file in the tree of each code file the suite reaches, helpers with a caller edge included, the
  global inputs and the tool versions, and the imports of every included code file in turn until nothing new is
  added). Three exceptions: a `scripts/lib` module that is imported stays narrowed to its importers, suites
  directly in `tests/` are not tree data, and the index docs `scripts/README.md` and `tests/README.md` count only
  where a suite names them. A later run skips that suite (`PASS  <check> (reused <suite> inputs <hash>)`). Suites
  graded by a postprocessor and checks that read the live workspace are never reused, and no record is published when the inputs
  changed during the run. `--no-reuse` runs every suite, `--release` never reuses, and an input mapping that is
  unsure runs the suite.
- **Selection.** `--affected` follows the narrow static graph of `tests/affected.py` (Python imports and the shell
  and jq helpers a script loads or runs by name): a library module or a helper selects only the suites of the
  scripts that reach it, and anything unsure runs. A miss there is caught by integration QA, whose suite reuse uses
  the conservative rule above. `--only-suites` is unioned with `--affected`. In either mode the live-workspace blocks and the
  checks that run a script outside a suite line (skill citations, `factory-context.sh`, pin status, pin plan,
  package ready, Netcode headless) are selected like suites by that script path, else they count as not affected;
  `--only-suites` may name such a script (`tests/run-all.sh` usage header). `--only-suites` exits 2 on a name
  run-all does not run; `tests/run-all.sh --list-suites` (read-only) prints the names it accepts, and
  `dispatch --phase qa` folds into `--only-suites` only the checks that list names (other checks stay extra
  commands). A check that mentions `tests/run-all.sh` is folded only when it is one plain standalone scoped
  invocation (an optional `env -u TMPDIR` and `bash` prefix, plain flag tokens, `--affected` or `--only-suites`
  among them); every other check that mentions run-all, a plain full run included, is printed `DO NOT RUN` and the
  QA session reports it NOT_RUN. No check is dropped.
- **Plans.** A task's `checks` name its own suites or the `--affected` command, never a full `tests/run-all.sh`, and
  its acceptance never requires a full run: `validate` warns on either ("full runs belong to integration QA").

This policy introduces no tripwire, no latch and no new confirmation step.

### Model choice

Every pipeline session (planner, task lead, implementer, review, QA) starts with an explicit model and effort, not the
CLI default. This subsection is the only copy of the policy; the data lives in registry `pipeline.models`, the code in
`scripts/lib/model_policy.py`.

- **Scope.** `pipeline.models.scope` lists, per agent (`claude`, `codex`), the models and efforts that may run at all.
  Every profile must lie inside the scope (`scripts/check-registry.sh` and `docs/registry.schema.json` enforce it).
  Codex runs `gpt-6.1-sol` for planner, lead, review and `heavy`, and `gpt-6.1-terra` for `light`, `standard` and `qa`
  (all at effort `high`), the counterpart of `claude-sonnet-5-5` at `high` on Claude.
- **Agent first.** Apply the agent routing and availability rules in "Which model" above first, then resolve the
  selected agent's profile within its model scope, including fallback sessions.
- **Roles and profiles.** `pipeline.models.profiles.<agent>` maps a role to a model and effort. The roles are
  `planner`, `lead` (the task lead, `--phase lead`), `implement` (takes the profile of the subtask or task grade),
  `review` and `qa`. The review of a `heavy` task uses the `heavy` profile, so a hard diff gets a strong reviewer.
- **Grades.** A grade is `light`, `standard` or `heavy`. A task or subtask carries an optional `grade` and
  `grade_reason` (`docs/schemas/pipeline-plan.schema.json`, `docs/schemas/pipeline-subplan.schema.json`). Without a
  grade the pipeline derives one from the task tier: S is `light`, M is `standard`, L, contract paths and generated
  paths are `heavy`. A subtask without a grade inherits its task's grade. The rubric that tells a lead which grade to
  write is `pipeline.models.rubric`; the task lead grades each subtask with it and records the reason.
- **Checks.** `validate` and `subplan validate` reject an unknown grade and a grade the policy cannot resolve, and print
  the resolved model and effort per task or subtask, so the lead sees the cost before it dispatches.
- **Flags.** `planner` and `dispatch` accept `--grade light|standard|heavy`, `--model ID` and `--effort LEVEL` as
  explicit overrides. A model or effort outside the scope is a usage error (exit 2); the pipeline never dispatches it.
  `verdict` accepts optional `--model` and `--effort` and stores them with the verdict.
- **Runners.** The `orca` runner adds `--model` and `--effort` to `orca orchestration worker-start`, `orca worktree create`
  and `orca agent launch`. The Agent-tool runner passes only a model alias (`pipeline.models.agent_tool_alias`): the
  Agent tool cannot set an effort, so the output and the prompt say so. The `print` runner shows model and effort in its
  header.
- **Personal override.** An optional JSON file with the same keys, at `$RPG_FACTORY_MODEL_POLICY` or
  `<persistent state dir>/model-policy.json`, may narrow `scope` and replace `profiles`. The result is checked again
  and an out-of-scope profile is an error. It is not committed; it lets one person limit their own spend.
