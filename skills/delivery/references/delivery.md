# Delivery policy: lead, workers, worktrees, Orca

The single copy of the generic policy for splitting a task across agents, in any repository or workspace. Other
files point here; none restates it. It adds no gate and no prompt: what is missing is reported and other work
continues. The delivery pipeline (section 10) runs it end to end; pipeline settings are the registry `pipeline`
block in a registered workspace, otherwise `skills/delivery/pipeline-defaults.json`. A workspace with its own rules
(the RPG workspace: factory-core `references/parallel-work.md`) keeps only those additions and points here.

<!-- policy:speed-rule -->
Prefer many short, focused parallel sessions over one long session; every spec stays short: objective, owned paths, checks, report format.

## 1. Roles

**Lead/Integrator (run lead)** - the main session, always. It:
1. owns the run scope and splits it into plan tasks with disjoint file ownership;
2. records each task's base commit and integration target;
3. writes the task spec for every task (section 3);
4. gives each task one worktree and starts ONE task-lead session in it (section 4, section 10 step 3);
5. answers the task leads' questions and follows their progress (`factory-pipeline.py status`);
6. assigns shared exclusive resources, one task at a time;
7. reads every task's result and verify report (section 6);
8. decides when a contribution is ready and integrates it (section 7), then runs integration QA (section 6);
9. writes the final report with the parallel-work ledger and cleans up (section 8).
It does not start a task's sub-sessions or edit task files (policy below).

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
4. with every subtask committed, starts ONE fresh verify session on that HEAD in the same worktree (section 6; tier S
   or prose-only: section 10 "QA tiers"); a FAIL goes to a fresh fix session, then one fresh re-verify session;
5. releases every session as soon as it reports (section 8, "Session lifecycle");
6. reports to the run lead (section 3) and records the verify verdict (`verdict --phase verify`).
It never pushes, merges, tags or removes its worktree.

<!-- policy:task-lead-claude -->
The task lead is a Claude session (registry pipeline.lead_agent), whatever the task's implementer, and Codex only when Claude is unavailable; implementation, review and QA sessions keep the cross-model pairing.

**Implementation sub-session** - edits only its subtask's paths in the task worktree, runs no test suites (only a
syntax check of the files it edited), and reports to the task lead. Commits: the policy below; a sub-session in a
child worktree (section 4) commits its paths on its own child branch and nothing else.

<!-- policy:only-task-lead-commits -->
Sub-sessions in the shared task worktree never commit, stage or stash; only the task lead commits there, with explicit paths.

**Verify worker** - one read-only session per task candidate (section 6): reviews the diff (architecture, scope,
safety rules, conventions, acceptance, test coverage, edge and failure cases), then runs the task tier command once.
**QA worker** and **Review worker** - the same checks as two read-only sessions, when only one is needed
(integration QA, a review without tests); a reviewer runs no suites, only a repro test when a finding needs one.

Task leads and their sessions never redefine the plan's scope, never merge, and never declare the overall run
done. A session that finds out-of-scope work reports it to its task lead, and the task lead to the run lead.

## 2. Before delegating

- Take the project snapshot (registered workspace: `factory-context.sh`) and `git worktree list` in each touched repo.
- With Orca, `orca worktree ps` and `orca orchestration run-list` show other coordinators' runs and worktrees: never
  bind to them, message their workers or edit their trees.
- Tasks and subtasks writing the same file, generated path or contract end overlap and run in sequence.
- Record per task: base branch and SHA, integration target, dependencies.

## 3. Task spec (every dispatch)

Objective; in-scope paths; exclusions (paths, repos, actions); base branch and SHA; dependencies; required checks
(fast tier, plus extended or external when named); acceptance criteria; report format. A task lead's spec adds the
task-lead rules; a sub-session's narrows it to its paths. No step lists.

A sub-session reports changed paths; each check with exact counts and log path (or NOT_RUN with command and reason);
limitations; out-of-scope findings. The task lead's report adds outcome, worktree path, branch, base and HEAD SHA,
each subtask with its commit, and the verify verdict (state, SHA, model).

## 4. Worktrees

- One worktree per plan task, for its whole life, on the task branch `<topic>-<task id>` from the recorded base
  (the plan `topic` is the `<type>/<area>/<topic>` integration branch). All the task's sessions run in it, except
  one placed in a child ("Child worktrees" below).
- Only the dispatching tool creates worktrees: the run lead's handoff ("Orca visibility" below), an Orca child, or a
  Claude Code agent with `isolation: "worktree"`; never a second clone or nested repository. Without a task
  worktree a task lead's dispatch is an error.
- Never edit another task's worktree. One mutating command per worktree at a time: parallel sub-sessions edit
  disjoint files and run no git write.
- **No-worktree repos** (section 10; a root file in `no_worktree_markers`, of the pipeline settings or the plan's own,
  also marks one): the task lead runs on the plan `topic` branch; subtasks and verify run there one at a time,
  tasks in turn after each verify verdict.
- **Shared exclusive resources** (pipeline settings `exclusive_resources`: an editor or test runner, a container
  stack, a test lab, fixed ports) go to one task at a time; a task without one reports the check `NOT_RUN` with the
  exact command and reason.
- **Full test runs are a shared resource too.** One full run per machine: CI or integration QA runs a full suite,
  never every session (section 10 "QA tiers"). Never create a worktree or branch while a full run is in flight when
  the runner checks the shared `.git/config`.
- **Lesson.** Create a task worktree without touching `.git/config`: "Orca visibility" below.
- **Orca visibility: a plain git worktree has no Orca lineage.** Create a task worktree with
  `git worktree add --no-track -b <branch> <path> <base>`, never `orca worktree create` (it writes
  `branch.<name>.base` into the shared `.git/config`, breaking checks that hash it). Unregistered, it lands in
  Orca's hidden section (maintainer rule, 2026-11-09: never), so before `orca agent launch --worktree path:<path>`
  its creator runs exactly
  `orca worktree set --worktree path:<dir> --parent-worktree path:<parent> --display-name <topic>-<task> --workspace-status in-progress`
  (`<parent>`: the integration checkout, else - and for the integration checkout itself - the main checkout; a task
  lead's child: the task worktree). Every
  printed worktree creation prints this line.

### Child worktrees

Either level may place a session in an Orca child worktree when that is faster or safer (a task worktree itself is
not a child):

<!-- policy:placement-table -->
| Placement | When | How |
|---|---|---|
| shared (default) | small subtasks with disjoint files and narrow tests; review or QA while nothing else edits | the task worktree (run lead: the integration checkout); `placement: "shared"` |
| child | parallel subtasks that both run full suites or write generated or build output; risky or experimental work; QA that needs a clean frozen checkout while others still edit | `orca orchestration worker-start --worktree new-child` (a session) or `orca worktree create --parent-worktree <selector>` (a worktree); `placement: "child"` + `reason` |

- **Run lead.** `dispatch --phase lead` creates, registers and launches the task worktree as in "Orca visibility".
  Integration QA (`--placement child`) or a quick fix may run in a child of the integration checkout.
- **Task lead.** Each subplan subtask records `placement` (`shared` or `child` + `reason`); `dispatch --subtask`
  prints the matching `--worktree` (`${CLAUDE_PLUGIN_ROOT}/docs/pipeline-cli.md`, "dispatch"; later mentions mean this file).
- A child session commits on its own child branch (`<task branch>--<subtask or phase>`) with explicit paths. Review
  and QA children are named `<parent>--[<subtask>--]<phase>-<sha7>`, so they never collide.

<!-- policy:child-merge-remove -->
The owner merges a child's branch into its parent branch and removes the child at once (`orca worktree rm --worktree path:<child>`).

<!-- policy:child-no-run-all -->
Never create or remove a child worktree while a full tests/run-all.sh runs (the runner of a repo that has one): every checkout shares one .git/config.

- `orca worktree rm` also deletes the checked-out local branch when Orca can prove it is merged: remove a child
  only after its branch is merged. A no-worktree repo never gets a child.

## 5. Orca (preferred coordinator when available)

- Detect: `orca status --json`; usable when `result.runtime.reachable` is `true`. Before the first dispatch load
  the version-matched contract with `orca skills get orchestration` and follow it.
- **No nested workers.** Orca allows one worker level (`nested_worker_depth_exceeded`); never route around it. The
  task lead is a handoff (section 4 "Orca visibility", then
  `orca agent launch --agent <id> --worktree path:<path> --prompt <spec>`). It creates its own Run
  (`orca orchestration run-create`), starts its sessions as workers, and reports with
  `orca orchestration send --to run:<run lead run id> --type status`.
- Commands this policy relies on: `orca orchestration run-create`, `orca orchestration task-create`,
  `orca orchestration worker-start`, `orca orchestration check`, `orca orchestration reply`,
  `orca orchestration send`, `orca orchestration worker-show`, `orca orchestration worker-read`,
  `orca orchestration worker-list`, `orca orchestration worker-release`, `orca agent launch`,
  `orca worktree list`, `orca worktree create`, `orca worktree rm`.
- **Orca message traps:**
  - Only a dispatched Orca worker can send `--type escalation` or `worker_done` (else "No active Dispatch belongs to
    this message sender"); a task lead is not a worker of the run lead, so it reports with `--type status` (asks with
    `--type question`).
  - `orca orchestration check --wait --types <types>` still returns heartbeats: a wait loop acks each batch and keeps
    waiting for the wanted type. The run lead's single waiter is `${CLAUDE_PLUGIN_ROOT}/scripts/orca-wait.sh --run <id>`
    (one per Run, by a lock file in the state dir).
  - A multi-line `--prompt` through `cmd.exe` (Windows) is cut at the first newline: write the spec to a file and send
    a one-line prompt that names it (`dispatch` does this).
  - After a worker start or launch with `--agent codex`, read its terminal (`orca orchestration worker-read`) until it
    shows the prompt being worked on; `input_accepted` alone is no proof (a Codex CLI once sat idle at an empty prompt).
- **Codex, else Claude.** A Codex session that cannot start or never picks up its prompt is marked down
  (`agents --down codex`, section 10 "Which model") and its role dispatched again on Claude; the report names it.
- Never use `orca orchestration gate-create` for routine work.
- **Orca first inside Orca.** In an Orca session (`ORCA_WORKTREE_ID` or `ORCA_AGENT_HOOK_ENDPOINT` set) with the
  runtime reachable, `factory-pipeline.py planner` and `dispatch` default to `--runner orca` and refuse
  `--runner agent` (exit 2, naming `--runner orca`) unless `--orca-unavailable <reason>` is given; the reason goes
  into the session prompt so its report names it (Agent-tool task leads with plain git worktrees
  are invisible in Orca).
- **Fallback:** outside Orca, or when it cannot do an operation, use Claude Code background agents (`--runner agent`)
  and name the limitation. They are Claude only: a session planned for Codex counts as SAME_MODEL (section 10 step 4).
  Orca's absence never blocks progress.

## 6. Verify (review + QA, one session)

- Verify a **stable candidate commit** (its SHA recorded): the task lead's HEAD with every subtask committed, kept
  there while the session runs; never a tree that is still changing.
- One verify session per candidate, never a review and a QA session in parallel. It reviews the diff first; a
  blocking finding is a FAIL and no test runs. Else it runs the task tier command once (section 10 "QA tiers") and
  reports counts and log paths. After a FAIL and a fix, a fresh re-verify reviews only the fix delta and runs the
  failed suites plus what the fix touched.
- The task lead starts the verify worker, fresh and read-only, in the task's own worktree
  (`orca orchestration worker-start --worktree path:<task worktree>`), or in a child at that SHA when the placement
  table (section 4) says child; never in any other new worktree. It first checks that `git rev-parse HEAD` is that
  SHA; a result from a changing tree, or with HEAD on another commit, is reported as not independent.
- Integration QA is the run lead's: in the existing checkout of the integration branch, or a child of it at the
  integration HEAD (section 4), never in a task worktree; with no such checkout the dispatch is an error and no
  worktree is created. A no-worktree repo (section 4) verifies in the main checkout while no other task of it runs.
- When the candidate moves (a fix lands), list which findings and results refer to the old SHA; redo only those.
- Verdicts are PASS, FAIL, NOT_RUN or BLOCKED. NOT_RUN is never a pass.
- The leads read the verify report (counts, log paths, verdict) and do not re-run its checks.
  The run lead keeps only the integration QA on the integrated tree, with the suite the spec names (a registered
  workspace: also `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py --repo <key> --paths <files> --status`).

## 7. Integration checklist (the run lead, per contribution)

- [ ] The task lead reported (section 3) and the task's review PASS is recorded on its HEAD.
- [ ] Diff contains only the task's scope; base and target are the recorded ones.
- [ ] Diff reviewed by the lead; required checks and QA passed; no open blocking finding.
- [ ] No baseline or user files touched; shared-package impact named; file ownership clear.
- [ ] Integrate in dependency order with `git merge --no-ff` (section 10 step 5), then run the checks on the result.
- [ ] On a conflict or regression: stop that contribution, diagnose it and dispatch a scoped fix. Never discard
      work or resolve a conflict by blindly taking one side.

Merging task branches into the integration branch is the run lead's decision. Merging into a protected or shared branch
(develop, main, staging, release-*) and pushing stay on the user's request.

## 8. Cleanup (mandatory when a task is done)

A task is done when integrated with its review and QA recorded; the run, when the PR is open (without
`deliver: pr`: at READY_FOR_PR). Then, every time:

1. **Worktrees.** The run lead removes each task worktree its run created once the task is integrated and its tree
   clean: `git worktree remove <path>` (never `--force`; or `orca worktree rm`, then
   `git worktree prune`, else `git branch -d` fails). Unintegrated work is reported, not removed. Never remove the main
   checkout, the integration checkout before its PR is open, or another coordinator's worktree, nor one a session or
   process still uses ("Session lifecycle" below).
2. **Task branches.** A task branch whose commits are in the integration branch goes with its worktree
   (`git branch -d`, never `-D`); the integration branch stays until its PR is merged.
3. **Agent sessions.** Every session is released ("Session lifecycle" below); the run lead ends each task-lead
   session once it reported.
4. **Check.** `cleanup plan.json` must report CLEAN before the final report (`docs/pipeline-cli.md`, "status and
   cleanup"); the report's Cleanup column names what was removed and what was kept, and why.
5. **After the integration PR is merged into main**, the run lead removes the integration checkout, deletes the
   plan's branches that main contains locally and on origin (`git push origin --delete <branch>`), reports any other,
   releases every worker and starts the next plan from the updated main (`cleanup --after-merge`: CLEAN).

### Run report and plan edits

- **Run report in the repo.** At integration the run lead commits `docs/plans/<plan>/report.md`: sessions per task
  (role, model, Orca Run), verdicts (phase, SHA, model, result), checks with exact counts, limitations. Verdicts and specs stay per machine; a
  new machine re-runs review and QA.
- **Plan edits are atomic.** Edit a copy, `validate` it, replace the plan.

### Session lifecycle

- **One task, one task lead; one subtask, one fresh session.** Every dispatch starts a new session, never reused for
  another task, subtask, phase, wave or candidate SHA: a fix is a new implementation session, a resumed task lead a
  fresh `--phase lead` session. Verify, review and QA never run in an implementation or lead session.
- **Release each session as soon as it reports**, in every repo: in the turn it reports (`worker_done`, final report
  or verdict) it is released (`orca orchestration worker-release`, or the agent stopped); the worktree stays. A
  settled session never waits for a later wave; one whose candidate is superseded is released at once.
- **Releasing a session does not stop its test processes.** On Windows a suite runner a released worker started
  keeps running: a worker stops its own test process tree first, and the lead stops leftovers whose cwd is the task
  worktree. A leftover `codex` CLI keeps the directory busy, so `orca worktree rm` fails ("Delete failed"). Before a
  task worktree is removed, its Run has no unreleased worker, no Orca terminal bound to it, and each released
  worker's CLI exited. Never kill a process the run did not start: name it (PID, command) to the user.
- **Few sessions:** memory pressure kills background shells and test runs.
- **Each lead keeps only its state** (plan or subplan, branch, SHAs, verdicts), no transcript.
- **Handoff.** After a wave, or when its context grows long, the run lead ends its session with the wave settled; the
  next resumes from `factory-pipeline.py status plan.json`.

### In-session subagents

<!-- policy:subagents-read-only -->
In-session subagents are read-only scouts; parallel writes are subtasks dispatched with --phase implement.

An in-session subagent (the Agent tool, Codex `multi_agent`) is not recorded: its edits get no paired
review and race the task lead's commits. Registry `pipeline.subagents` holds this table's values.

| Role | Access | When | Max parallel | Limits |
|---|---|---|---|---|
| run lead | read | scout the repository before the plan | 3 | no dispatch, no verdict |
| planner | read | map paths and dependencies for the plan | 3 | no dispatch, no verdict |
| task lead | read | scout before the subplan | 2 | never implements, never commits through a subagent |
| implement | read | find call sites and examples | 2 | owned paths only, no edits by the subagent |
| review | read | read files for the reviewer | 3 | the reviewer's own model only |
| QA | none | - | 0 | QA reads and runs the checks itself |

Default model: `claude-sonnet-5-5` via the `rpg-factory:factory-explorer` agent (Codex: the `pipeline.subagents`
codex model), inside `pipeline.models.scope`. Use one only when the answer needs many files or an open search, with a
brief of at most 200 words (objective, paths, return `path:line`). It never edits, writes to git, uses Orca,
dispatches, records a verdict or starts a subagent; its result is never a verdict. A reviewer never uses one of the
other model (for example `codex:codex-rescue` in a Claude review). The session report names the subagents used.

## 9. Not authorized by this policy

- Tags and releases: only with explicit release authorization from the user in the current task.
- Production deploys.
- Consequential workflow dispatch, secrets, shared infrastructure and production data: a workspace's human gates
  keep their rules.
- Repositories outside the task.
- Bypassing branch protection or required CI.

## 10. Delivery pipeline

`${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py` turns sections 1-8 into commands; it only prints commands and
grades state. Plan format: `docs/schemas/pipeline-plan.schema.json`; command forms and flags: `docs/pipeline-cli.md`.

<!-- policy:no-worktree-repo -->
A no-worktree repo (registry `worktrees: false` or a configured no-worktree marker, for example a Unity project) never gets a worktree; its task lead and all its sessions run in its main checkout.

**Which model.** Implementer (a plan task carries a `kind`; a subtask an `implementer` or a `kind`): the explicit
`implementer`, else `agent_routing[kind]`, else `agent_routing.default`, else `default_implementer`, then availability:

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
  to Codex when Claude implemented. QA runs on the implementer's model only as the one-model fallback, in a fresh
  QA session. An explicit `implementer` against the table needs a `reason` (`validate` warns).
- **Availability never stops a task.** Agents are detected on PATH and Orca's account list; `RPG_FACTORY_AGENTS`
  overrides. A runtime MODEL_UNAVAILABLE holds for the run (`agents --down <agent>`). Every role falls back to the
  available model, which then implements, reviews, runs QA and, for Codex, leads; no command fails because a model is
  missing (the fallback review: step 4).
- **Recorded implementer.** `dispatch --phase implement` records the model it started, per task and subtask; review,
  QA, `verdict` and the gate pair against it, never current availability; no subtask needs a review of its own.

<!-- policy:single-verify -->
One verify session reviews the whole task diff: a prose subtask written by the verifier's model is covered, and a code subtask written by the verifier's model is listed by the gate as `SAME_MODEL (single verify)`, never blocking.

1. **Tier.** `factory-pipeline.py tier -- --repo <key> --paths <files>` prints S, M or L.
   S: the run lead writes a one-task `plan.json` and dispatches its task lead (step 3); steps 4-8 follow.
   M: the run lead writes `plan.json`. L: a read-only planner worker writes it (`planner --request <text>`).
2. **Plan.** `validate plan.json` must print OK.
3. **Task lead.** Per ready task the run lead runs
   `dispatch plan.json --task <id> --phase lead --report-to <run lead run id> --runner orca` (the section 5
   handoff). The task lead writes `subplan.json` until `subplan validate` prints OK, records each subtask's
   `placement` (section 4, "Child worktrees"), dispatches each with `--phase implement --subtask <sid>`, reviews each
   diff and commits it with explicit paths, or merges and removes a child.
4. **Verify (cross-model review, then QA, one session).** Each model's code is reviewed by the other
   (`review_pairing`): on the stable candidate the task lead runs `dispatch ... --phase verify --sha <sha>` once
   (section 6) and records `verdict --phase verify`; a FAIL gets a scoped fix in a fresh session and one fresh
   `--phase verify` on the new candidate. `--phase review` and `--phase qa` serve a lead that needs only one of them
   (integration QA, step 6).
   `--phase implement` in the shared placement starts a sub-session that does not commit, in every repo; with
   `--placement child` (or a `child` subtask) the session commits on its own child branch only, and the task lead
   merges and removes the child. Without the paired model a fresh same-model session verifies, carrying
   `SAME_MODEL (fallback: <model> unavailable)`, which the dispatch records for the SHA and the gate accepts (other
   forms: `docs/pipeline-cli.md`, "Fallback reviews"). Then the report (section 3).
5. **Integrate** (section 7) in wave order into the `topic` branch with `git merge --no-ff <task branch>`; a
   fast-forward or squash leaves earlier reviews STALE (`docs/pipeline-cli.md`, "gate").
6. **QA.** Once per repo on the integration HEAD, in its checkout
   (`dispatch ... --task integration:<repo> --phase qa --sha <head>`, "QA tiers" below); a no-worktree repo also per
   task. The worker fills `${CLAUDE_PLUGIN_ROOT}/templates/pipeline/qa-report.md`; the lead records the verdict.
7. **READY_FOR_PR.** `gate plan.json` is a read-only report (`docs/pipeline-cli.md`, "gate"); fix each blocker and
   re-run only the affected verify, review or QA.
8. **PR.** With `deliver: pr` (plan `deliver: "pr"`) and READY_FOR_PR, the run lead pushes the integration branch
   and opens the PR with the gate's commands, body = the final report (the delivery exception to "push only on
   request"). CI green (`gh pr checks <pr> --watch`) is the merge gate. Merging stays with the user; without
   `deliver: pr` the task ends at READY_FOR_PR.
9. **Cleanup.** Section 8, until `cleanup plan.json` reports CLEAN.

**QA tiers.** No identical tree is tested twice and a task never runs the whole suite: each role runs one command,
which `dispatch --phase verify` (or `--phase qa`) prints. Settings `qa_tiers` name only each tier's level (task
`affected`, integration `ci+workspace`), no commands. A repo with `tests/run-all.sh` (this plugin) gets the commands
of the table below; one without it gets its task checks (a registry repo: plus the run-checks fast tier). The shape:
implementers run no suites, one verify session per task runs only the suites its changes reach, integration runs
what CI cannot, CI is the full gate, a release runs everything.

<!-- policy:qa-tiers -->
| When | Runs | Who | Typical time |
|---|---|---|---|
| Implementer | no test suites; only a syntax check of the files it edited (`bash -n`, `python -m py_compile`, a JSON parse) | the implementation session | seconds |
| Verify, once per candidate | the diff review first (a blocking finding is a FAIL and no test runs); then `tests/run-all.sh --affected --base <review base> [--only-suites <check suites>] -j 2`: the suites the task's checks name (only those `tests/run-all.sh --list-suites` lists) plus the suites `tests/affected.py` maps to its changed files, each suite once. Explicit suites run all cases; affected-only suites with a case map run only affected cases. Other checks are extra commands; never a full run | one fresh verify session in the task worktree, started by the task lead | 2-5 min for a narrow change (one-file schema change 119 s, one-file skill change 288 s); a change to a global input of `tests/affected.py` selects every suite and takes about an hour with a slot wait |
| Re-verify after a FAIL | review of the fix delta only; then only the failed suites recorded with `verdict --phase verify --state FAIL --failed-at qa --failed-suites`, plus `--affected --base <previous FAIL candidate>`; a review-only FAIL (`--failed-at review`) ran no test, so the original base and checks stay | one fresh verify session on the fix candidate | as verify |
| Tier S or prose-only task (every owned path a .md file, under changelog.d/ or a skills/ directory) | the task tier command, after the review PASS; no QA session | the task lead: `verdict --phase qa --state PASS --by <lead> --note 'tier S: lead ran task suites'`; a lead-run QA verdict counts for tier S only | as verify, no session of its own |
| Integration QA, once per batch before the PR | `tests/run-all.sh --workspace-only` (only what CI cannot run: the live-workspace suites and checks, with the suite reuse), before the PR; after the PR opens, `gh pr checks <pr> --watch`: CI green is the full gate (pipeline settings `qa_tiers` integration `ci+workspace`) | the run lead's integration QA session | once per batch; CI runs the full suite in the background while the next task starts |
| Release | `tests/run-all.sh --release` and `tests/dogfood.sh --installed` (unchanged) | the release session | the slowest tier, release only |

- **Test-run slots.** A targeted run (`--affected` or `--only-suites`) takes one of a few machine-wide test slots
  and, when all are busy, waits instead of slowing every suite 2-4x (`--no-wait` exits 3); a dead
  holder's slot is taken over. A full run keeps its own lock (section 4). The slot belongs to the run, not the
  session: stop a QA worker's test run before abandoning it.
- **Implementers run no suites** (table above); `dispatch --phase implement` says so in its spec. `dispatch --phase
  verify` (and `--phase qa`) prints the case list for the tier command (`ALL` for explicit suites); a slow suite with
  cases runs only the cases the change touches. Frozen copies of a suite go under a temp dir, never into its folder.
- **CI is the full gate.** No full local run before a PR: CI runs the full suite, and the integration QA command
  covers what CI cannot, before the PR. After the PR opens, CI green (`gh pr checks <pr> --watch`) is the merge
  gate; while CI runs, start the next task, then come back and fix a red check before merging. Only a release runs
  the full local suite.
- **Tier S.** `dispatch --phase verify` (and `--phase qa`) marks a task tier S when the plan or the task says so or
  every owned path is prose (`docs/pipeline-cli.md`, "dispatch"). The gate accepts a QA verdict the task lead ran
  itself (note starting `tier S`) only for such a task, and a fresh QA session's PASS for every tier (the other
  model, or the implementer's as the Token rule's one-model fallback).
- **Re-verify.** The table row above; flags (`--failed-at review|qa`, `--failed-suites`): `docs/pipeline-cli.md`,
  "verdict". A repo without `tests/run-all.sh` keeps its task check commands (a failed-suites list cannot name them).
- **Plans.** A task's `checks` name its own suites or the affected-suites command, never a full run, and
  its acceptance never requires a full run: `validate` warns on either ("full runs belong to integration QA").
  `checks` run in the verify session: `validate` warns when a check would make an implementer run a suite.
- The run-all lock, suite reuse and selection rules of this plugin repo's runner are in `tests/README.md`.

This policy introduces no tripwire, no latch and no new confirmation step.

### Model choice

Every pipeline session starts with an explicit model and effort, never the CLI default. The only copy of the
policy; data: settings `models`; code: `scripts/lib/model_policy.py`; flags: `docs/pipeline-cli.md`.

- **Scope.** `models.scope` lists per agent the models and efforts that may run; nothing outside it is dispatched.
- **Agent first.** Resolve the agent by "Which model" (fallbacks included), then its profile within its scope.
- **Roles and profiles.** `models.profiles.<agent>` maps `planner`, `lead`, `implement` (by grade), `review` and
  `qa` to a model and effort; a `heavy` task's review uses the `heavy` profile.
- **Grades.** `light`, `standard` or `heavy` on a task or subtask, else derived from the tier; the task lead grades
  subtasks by `models.rubric` and records the reason.
