# Delivery pipeline CLI

Command forms and flag rules of `scripts/factory-pipeline.py`. The policy they implement is
`skills/delivery/references/delivery.md` (section 10); this file holds only the CLI details that policy points to.
Run the script as `python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py <verb>`; `--registry none` (before or
after the verb) reads `skills/delivery/pipeline-defaults.json` instead of the registry `pipeline` block.

## tier and planner

- `tier -- --repo <key> --paths <files>` prints XS, S, M or L and the flow. An S task is still a one-task `plan.json`
  with its own task lead (the task worktree, or the main checkout of a no-worktree repo).
- XS applies only when every path is prose (`pipeline_route.prose_path`, see "dispatch" below), no path is a contract
  or generated path, and the change stays within `pipeline.tiers.XS` (`max_files`, `max_changed_lines`). This plain
  form counts files, not changed lines: `tier --plan` counts the changed lines of the checkout, and the gate those of
  the committed diff. An XS task has no task lead, task worktree or implement session: the run lead itself edits and
  commits it on the plan `topic` branch, dispatches one cross-model review and runs the task tier command (delivery.md
  section 10 step 1).
- `tier --plan plan.json --repo <key> --paths <files>` is the form for `--registry none` and for repos the plan names
  by path: the repo is read from the plan's `repos` entry, not from the registry.
- `planner --request <text> --runner orca` starts the L-tier planner worker. Planning is read-only and runs in the
  run lead's checkout, never in a new worktree.

## validate and subplan validate

- `validate plan.json` prints OK when the owned paths of the tasks are disjoint (or the tasks depend on each other),
  there is no cycle, the waves resolve, a no-worktree repo has no worktree and never two tasks in one wave, and every
  reviewer is of another model than its implementer. It warns (never errors) when one wave shares an exclusive
  resource (queue those runs), when an explicit `implementer` against the "Which model" table has no `reason`, when 3
  or more tasks all use one model, when a task's `checks` or acceptance require a full run ("full runs belong to
  integration QA"), and when its `checks` contain test suites ("implementers run syntax checks only, verify runs
  suites").
- `subplan validate subplan.json` (format: `docs/schemas/pipeline-subplan.schema.json`) prints OK when every
  subtask path is repo-relative (no absolute or `..` path),
  inside the task's owned paths and outside its exclusions, overlapping subtasks are ordered by deps, there is no
  unknown dep or cycle, each subtask names an `implementer` or a `kind`, each implementer is a pipeline agent and each
  reviewer is of the other model. It prints the waves (one subtask per wave in a no-worktree repo) and refuses
  `placement: child` in a no-worktree repo. It warns like `validate` on a missing `reason` or one model for 3 or more
  subtasks.
- `validate` accepts tier XS (plan or task `tier`) only for a one-task plan whose owned paths are all prose, within
  `max_files` and, where the XS rule sets `contracts: false` / `generated: false`, no contract end or generated path;
  a non-prose path, a second task, a threshold exceeded, a contract or a generated path is an error.
- Both reject an unknown grade or one the model policy cannot resolve, and print the resolved model and effort per
  task or subtask.

## dispatch

- `--note TEXT` is repeatable; `RPG_FACTORY_SESSION_NOTE` supplies one additional note. Dispatch appends each as a
  `Session note: <text>` line to every spec kind, collapsing whitespace and dropping duplicates. The lead's
  `<dispatch>` carries them on to its sessions. On win32, when `python3` resolves into WindowsApps or the Store alias
  `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe` exists (also behind a `python3` shim first on PATH), the spec
  also explains how to use the dispatch interpreter or a `python3` shim instead of the Microsoft Store alias.
- `dispatch plan.json --task <id> --phase lead --report-to <run lead run id> --runner orca` prints the task-lead
  handoff. A new task worktree: `git worktree add --no-track -b <branch> <path> <base>` (beside the checkout that has
  the plan `topic` checked out, else beside the repo checkout), the `orca worktree set` lineage line of delivery.md
  section 4 "Orca visibility", then `orca agent launch --worktree path:<path>`. An existing task worktree, or the main
  checkout of a no-worktree repo, gets only the launch (never a worktree create or a new top-level worker there);
  `--placement shared|child` gives the same result. Orca allows one worker level (maximum depth 1), so the task lead
  then creates its own Run (`orca orchestration run-create --objective <text>`), starts its sessions as workers of that
  Run (`orca orchestration worker-start --worktree path:<task worktree>`, depth 1) and reports to the run lead with
  `orca orchestration send --to run:<run lead run id> --type status --subject <text> --body <report>`.
  A first-wave task branches from `repos.<key>.base`; a later-wave task (one with deps) from the plan's `topic`
  integration branch when it exists, because that branch carries the earlier waves. `repos.<key>.base` stays the
  comparison base of `status` and the gate: never point it at the topic (then `base..head` counts nothing and
  integrated tasks show as pending).
- Stacked task (the rule: delivery.md section 4 "Stacked dependents"): a task stacks when its one in-flight
  dependency in the same repo is a candidate or reviewed and every other dependency is integrated; two in-flight
  dependencies, or a pending or implementing one, never stack. When `status` notes `stackable on <dep>@<sha>`,
  `--phase lead` prints `git worktree add --no-track -b <topic>-<id> <path> <dependency tip SHA>` for a sibling beside
  the integration checkout (never a child of the dependency's worktree), `orca worktree set` with the integration
  checkout (else the main checkout) as parent, then the launch; the lead prompt says to implement now and to run no
  verify, review or QA dispatch before `status` clears it. It records the dependency SHA as the base (a SHA, never a
  branch name) in `<task>__stack.json`, outside the task fingerprint, so recorded verdicts stay valid. A fresh
  dispatch (no task branch yet) first removes a leftover `<task>__stack.json` and `<task>__sync.json`. Tier XS and
  no-worktree tasks keep the unchanged handoff.
- `dispatch plan.json --task <id> --phase implement --subplan subplan.json --subtask <sid> --runner orca` takes the
  subtask's paths, agent and placement; the ad hoc form is `--paths <subtask paths> [--agent claude|codex]
  [--placement shared|child]`. Paths outside the task's owned paths, or inside its exclusions, are refused; without
  a task worktree the dispatch fails (run `--phase lead` first). It records the model it started, per task and per
  subtask, and prints `--worktree path:<task worktree>` or `new-child` (run from the task worktree).
  `dispatch` refuses `placement: child` in a no-worktree repo.
- `dispatch ... --phase verify --sha <sha>` starts ONE read-only session of the reviewing model on the candidate in
  the task worktree: its prompt holds the review checklist first and the task tier command second (a blocking review
  finding is a FAIL and no test runs). When the paired model is unavailable it records the same-model fallback for
  that SHA. `status` names `--phase verify` after the last subtask; after a FAIL it names `--phase lead`, which
  resumes the task lead in its worktree (or the main checkout of a no-worktree repo) for the fix.
- XS task: `--phase lead` starts no session; it says the run lead edits the task on the `topic` branch and prints the
  run lead's steps: commit with explicit paths, the review command, the task tier command, the QA `verdict` record
  (note `tier XS: lead ran task suites`) and the gate. `--phase implement` exits 2. `--phase review --sha <sha>` then
  needs no task worktree: the reviewer reads the topic checkout, and the implementer is recorded as the run lead's
  model, so the review goes to the other model.
- `dispatch ... --phase review --sha <sha>` and `--phase qa --sha <sha>` start one of the two alone, for a lead that
  needs only one of them. `--phase qa` (like `--phase verify`) prints the tier command (never a full run) and the case
  list for its base and suite selection (`ALL` for explicit suites). `--task integration:<repo>` targets the
  integration HEAD (a child of the integration checkout with `--placement child`); in a no-worktree repo `--task <id>`
  also runs per task, before the next task starts.
- A stacked task's `--phase verify|review|qa` exits 2 (no prompt, record or launch) until its dependency's
  review PASS SHA is in `--sha`; the reason names the merge (`git merge <dependency branch or PASS SHA>, never
  rebase`). Its review and QA `--affected --base` is the newest dependency SHA in HEAD (once the recorded dependency
  SHA is on the `topic`, the later-wave base), so they see only the task's own delta.
- Pre-flight (advisory): `--phase verify|qa` prints on stderr `factory-pipeline: selected N of M suites
  (tests/affected.py)` (N: the Affected cases suites, M: `tests/run-all.sh --list-suites`), or
  `factory-pipeline: selected suites: not computed (<reason>)`, and a warning to narrow the task paths or its checks
  when N is above `--suite-warn N` (default 40; below 1 is a usage error, exit 2). The prompt and exit code do not
  change. `tests/run-all.sh --affected` exits 2 when python3 cannot run instead of
  widening to every suite. run-all records each suite's wall seconds, exit status and cases in the state dir's
  `run-all/timings.json` (JSON Lines).
- Tier S: `--phase verify` and `--phase qa` mark a task tier S when the plan or the task has tier S or every owned
  path is prose (`pipeline_route.prose_path`): a `.md` file anywhere, a path under `changelog.d/`, or a `skills/`
  directory path (no dot in its last segment). A non-`.md` file under `skills/`, `docs/*.json` and `docs/schemas/`
  are machine inputs, not prose: `docs/` alone does not make a task tier S.
- `dispatch` prints each role's model and why as `model: <role> -> <agent> (<why>)`; `status` prints
  `model: <task> <role> -> <agent> (<why>)`.
- `--runner orca|agent|print` picks the runner; inside Orca `--runner agent` needs `--orca-unavailable <reason>`
  (delivery.md section 5, "Orca first inside Orca"). `--runner agent` (Claude only) marks a session planned for
  Codex SAME_MODEL in its prompt and uses `isolation: "worktree"` only where delivery.md section 4 creates a
  worktree.

## verdict

```
factory-pipeline.py verdict plan.json --task <id> [--subtask <sid>] --phase verify|review|qa --sha <sha> --by <agent>
  --state PASS|FAIL --report <file> [--note TEXT] [--implementer AGENT] [--fallback '<model> unavailable']
  [--failed-at review|qa] [--failed-suites <tests/a.sh,...>] [--model ID] [--effort LEVEL]
```

- `--phase verify` (per task, never `integration:<repo>`) records the review and the QA verdict of one SHA in one
  call. A FAIL names where it failed: `--failed-at review` (the review blocked the candidate, no test ran) writes the
  review FAIL and no QA record, so the next verify keeps the original base and the task's checks;
  `--failed-at qa [--failed-suites <tests/a.sh,...>]` records review PASS and QA FAIL (`--failed-suites` alone implies
  `qa`). A QA-only FAIL is recorded the same way with `--phase qa`.

- `--report` names an existing file; `--note` takes free text.
- `--subtask <sid>` records a subtask's own review apart from the task review; the gate needs none (single verify).
- `--implementer` declares the true implementer and is refused when it conflicts with the one the dispatch recorded.
- `--failed-suites` goes with a QA FAIL. The next `dispatch --phase verify` (or `--phase qa`) on a new candidate prints
  `--affected --base <that FAIL's candidate>` with only those suites in `--only-suites`, not the task's own check
  suites; a repo without `tests/run-all.sh` keeps its task check commands.
- `--model` and `--effort` are optional and stored with the verdict.
- A stacked task: a review or QA PASS (task, `--subtask`, or `--phase verify`) on a SHA without the dependency's
  current review PASS is refused (exit 2, nothing written); FAIL and the other states are recorded.

## sync

```
factory-pipeline.py sync plan.json --task <id> [--send]
```

- The dependency's task lead runs it after each new candidate (a fix included); without stacked dependents it is a
  no-op. It compares the task's latest SHA (its task branch tip, else its review PASS) with the HEAD of each stacked
  dependent, prints `<dependent>: <id> moved to <sha>, not in HEAD <sha>: git -C <worktree> merge <ref>` (never a
  rebase) and records `<dependent>__sync.json`, the durable signal `status` shows until that HEAD contains the SHA.
  An up-to-date dependent prints `up to date` and its record is removed.
- `--send` also runs `orca orchestration send --type status` to the dependent's lead: `run:<task orca_run>`, else
  `@worktree:<its Orca worktree id>`. Without Orca (no address, or no Orca executable on PATH) it prints the command
  for the lead and exits 0. The message is only a nudge: the durable signal is the `sync` record in `status`.
- The dependent's task lead, at each subtask boundary, on a `sync:` or `<dep> now at <sha> not in HEAD` note, runs
  `git merge <dependency branch>` (never a rebase), resolving conflicts only inside its owned paths.
- Exit 0, 1 when a send failed, 2 usage (`--task integration:<repo>` included).

## Fallback reviews

- `verdict` stamps `SAME_MODEL (fallback: <model> unavailable)` only when that SHA's verify or review dispatch was a
  recorded fallback and `--by` is its reviewer, never from availability at verdict time. A subtask's fallback review
  is noted `SAME_MODEL (fallback: <pair> unavailable)`.
- Delta review: a task review recorded with `verdict --phase review` at a later SHA of a task already reviewed, by the
  implementer's model and with no review dispatch at that SHA, keeps the fallback that dispatch recorded for an earlier
  review of the same task by the same model whose SHA is an ancestor (the record notes `fallback_from`), so it stays an
  accepted `SAME_MODEL` note. A task never reviewed before still needs the dispatch record, and a git error keeps the
  blocker.
- Retrospective form: a same-model review made before dispatch recorded fallbacks (for example during an outage of
  the paired model) is recorded after the fact for a subtask review only, with
  `verdict --subtask <sid> --fallback '<model> unavailable' --note <why>`: `--subtask` and `--note` are required and
  `--by` must be the implementer's model. The bare form `--fallback <model>` is refused while that model is available.
- The task level refuses the retrospective form: a task review keeps a dispatch-recorded fallback or
  `gate --allow-same-model`.
- `gate` prints an accepted fallback with its reason and note, never silently; it needs `--allow-same-model` only for
  an unrecorded SAME_MODEL review.

## gate

- `gate plan.json` is a read-only report. READY_FOR_PR needs every task integrated, reviewed PASS by its paired model
  on a commit whose owned paths have not changed since (the verify verdict records review and QA of a task), QA PASS
  on each integration HEAD, clean integration trees, fast checks PASS and not STALE (`run-checks.py --status` in a
  registered workspace), and no pipeline worktree in a no-worktree repo. Anything else is a listed blocker. With
  `deliver: pr` it prints the push, PR and `gh pr checks <pr> --watch` commands.
- The gate credits a later wave's changes under an earlier task's or subtask's paths only through the merge commits
  on the topic's first-parent chain, each later task with its own current PASS review (and QA where required). A
  fast-forward or squash leaves those changes unattributed and the earlier review STALE.
- Stacked task: a blocker when its review PASS lacks the dependency's review PASS SHA (merge the dependency branch,
  then verify again), or when it was integrated before or together with its dependency (integrate the dependency
  first with `git merge --no-ff`, then the task). A clean merge of the dependency into the dependent is a sync merge
  and never makes the dependency's review STALE; its conflict resolutions do.
  The dependency's review PASS the gate uses is the newest PASS record of the dependency (its current verdict or a
  kept per-candidate record `<task>__review__<sha>__<agent>.json`) whose SHA is an ancestor of the dependent's
  reviewed commit; it is used when it is the dependency's current PASS or when the current PASS contains the
  dependent's reviewed commit (a delta review of the dependency at the integration HEAD). The integration order
  compares the merge point of that SHA, so a later delta review of the dependency no longer reports "integrated
  before its dependency". When the dependent's own current review is a delta review too (its reviewed commit is the
  integration HEAD), its earlier review PASS records contained in it (same plan version, newest first) are tried as
  well: one that contains a dependency PASS merged strictly earlier clears both checks. A dependent integrated before
  its dependency stays blocked, because its merge brings the dependency PASS in at the same first-parent position.
  Any git error keeps the blocker (fail safe).
- A recorded verdict holds for its task's fingerprint (objective, owned paths, exclusions, acceptance, checks,
  agents): a plan edit that only changes deps keeps it; changing a task's paths or acceptance makes it stale. Re-run
  `status` after any plan edit.
- Review, QA, `verdict` and the gate pair against the implementer `dispatch --phase implement` recorded (the
  planned routing when none is recorded), never against current availability: a model that comes back after a
  fallback does not change who reviews. No subtask needs a review of its own: the task's verify review covers every
  subtask, and the gate lists a code subtask written by the reviewer's model as an accepted
  `SAME_MODEL (single verify)` note (delivery.md section 10, `policy:single-verify`).
- An XS task needs its review PASS on the run lead's commit and the lead-run QA verdict (note starting `tier XS`) at
  the `topic` HEAD, which stands in for the integration QA while none is recorded; the gate blocks it when the
  committed diff exceeds the XS rule (a non-prose path, files, changed lines, a contract or generated path).
- The integration QA (or the tier XS lead QA) stays current after a later commit when its SHA is an ancestor of the
  integration HEAD and every file changed between them is a run lead file (the plan file, its `report.md` and the
  `backlog.md` beside it); the gate then prints a NOTE instead of rerunning the workspace QA. Any other changed file,
  a QA SHA that is not an ancestor or a failing git command keeps the `QA is STALE` blocker (fail safe).
- The gate checks the run lead files present on the integration branch with the machine-path rule of
  `scripts/lib/plan_paths.py` (the same rule as the portable-plans case of `tests/parallel-policy.test.sh`) and lists
  a blocker naming each file that holds machine-specific path text, so it is caught before the PR, not by CI.
- The gate also applies the English-only rule of `scripts/lib/english.py` to each of those files as read from the
  integration HEAD, honouring `tests/fixtures/english-allow.txt` read from the same HEAD (`path:line` and `path:*`
  entries, as `scripts/checks/english-only.py` does; no file means an empty allowlist). It lists one blocker per file
  naming the file, the first offending line number and the rule (`run lead file <path> line <n> is not English`), and a
  blocker when the allowlist itself is malformed. `status` shows the same blockers as `gate blocker:` notes on the
  first task of the repo.
- `status` follows the same XS flow: the task's branch is the `topic`; uncommitted edits in its paths are the run
  lead's; a commit names `--phase review --sha <sha>`; after the review PASS the next step is the task tier command and
  the lead QA record at the `topic` HEAD (never an integration QA session); with that QA PASS it names the gate.

## Orca commands

The Orca commands delivery.md relies on: `orca orchestration run-create`, `orca orchestration task-create`,
`orca orchestration worker-start`, `orca orchestration check`, `orca orchestration reply`, `orca orchestration send`,
`orca orchestration worker-show`, `orca orchestration worker-read`, `orca orchestration worker-list`,
`orca orchestration worker-release`, `orca agent launch`, `orca worktree list`, `orca worktree create`,
`orca worktree rm`. `scripts/orca-wait.sh` allows one waiter per Run through a lock file in the state dir.

## agents

An agent is available when its `agents.<a>.bin` of the pipeline settings is on PATH. Codex additionally needs one
auth source, checked in this order:

- `orca account`: Orca's account list (when Orca runs) has auth for it;
- `OPENAI_API_KEY set`: the variable is set;
- `api provider <name>`: the active `model_provider` of the Codex config (`$CODEX_HOME/config.toml`, else
  `~/.codex/config.toml`; top level or the default profile) carries authentication: an `http_headers` Authorization
  entry, an `env_key` whose variable is set, or a provider other than `openai` with a `base_url`;
- `codex login`: `codex login status` exits 0 (this also covers `requires_openai_auth`).

The `orca` and `codex login status` calls time out after 5 s. `agents` prints the source that made Codex available,
or every reason it is not (e.g. `no Orca account, codex login missing, no authenticated api provider`); it never
prints, logs or records a header, key or token value, only the source name. `RPG_FACTORY_AGENTS` (comma list)
overrides the detection, and a runtime MODEL_UNAVAILABLE still wins over any auth source. `agents plan.json --down
<agent> --reason <text>` records a runtime MODEL_UNAVAILABLE (revoked token, 401) for the run; `--up <agent>` clears
it. Mark Codex down when its session cannot start or never picks up its prompt (a trust prompt for hooks, CLI error,
quota, idle terminal, a 401), then dispatch the role again.

## status and cleanup

- `status plan.json` re-derives where the plan stands (a pending task's next command is its `--phase lead`
  dispatch); `--orca-run <run id>` lists the Run's settled workers that are not released. `status` and `cleanup` list
  each leftover child ("child of <task>") with its merge state.
- Stacked notes on a task row: `stackable on <dep>@<sha>` (a pending task, ready: next is its `--phase lead`),
  `stacked on <dep>@<sha>`, `<dep> now at <sha> not in HEAD: merge it (never rebase), then continue` (next: the
  `git merge`), `sync: <dep> moved to <sha> (<at>)` (from the `sync` record, only for the current dependency, until
  HEAD contains the SHA), `verify waits: <reason>` (a candidate; next: the merge, or none while the dependency has no
  PASS), `integrate <dep> first (dependency first), then merge <branch> with git merge --no-ff` and, while one of
  them is not integrated, `stacked siblings <ids> on <dep>: sibling worktrees, not children of <dep>'s worktree;
  merge order <dep branch>, then <dependent branch> into <topic> (dependency first, git merge --no-ff); git branch -d
  a branch only after its merge`.
- `cleanup plan.json` lists what is left: the plan's worktrees and task branches, leftover children, and settled Orca
  workers not released in each task lead's Run (task `orca_run` or `--orca-run <id>`, read-only `worker-list`; no
  orca is NOT_AVAILABLE), with the commands to remove them (`orca orchestration worker-release` closes only that
  worker's terminal and keeps its output readable). A leftover task directory (empty or not) or an Orca
  record of a removed worktree is LEFTOVER, never CLEAN, with `git worktree prune`, then
  `orca worktree rm --worktree path:<dir>` once the directory is free.
- `cleanup` prints the stacked siblings as `STACK <repo>: stacked siblings ... merge order ...` (`stacked` in
  `--json`: repo, dep, dependents, order, states `merged|not merged|gone`, text); they never change the state. A
  stacked dependent's worktree is a task worktree, never "child of <dependency>".
- `cleanup plan.json --after-merge`, once the integration PR is merged, lists the integration checkout, the local and
  origin branches of the plan that main contains (`git merge-base --is-ancestor <branch> origin/main` or
  `git branch --merged origin/main`; never `git branch -D`), and unreleased workers, and reports CLEAN only when none
  is left.
  The plan's `repos` path must point at the main checkout; a missing path is LEFTOVER.

## Model flags and runners

The model policy is delivery.md section 10 "Model choice"; these are its flags and runners.

- **Codex models.** Codex runs `gpt-6.1-sol` for planner, lead, review and `heavy`, and `gpt-6.1-terra` for
  `light`, `standard` and `qa` (all at effort `high`), the counterpart of `claude-sonnet-5-5` at `high` on Claude.
  `models.scope` and `docs/registry.schema.json` enforce that every profile lies inside the scope.
- **Grades.** A task or subtask carries an optional `grade` and `grade_reason`
  (`docs/schemas/pipeline-plan.schema.json`, `docs/schemas/pipeline-subplan.schema.json`). Without a grade the
  pipeline derives one from the task tier: S is `light`, M is `standard`, L, contract paths and generated paths are
  `heavy`. A subtask without a grade inherits its task's grade. `lead` is the task lead's role (`--phase lead`).
- **Flags.** `planner` and `dispatch` accept `--grade light|standard|heavy`, `--model ID` and `--effort LEVEL` as
  explicit overrides. A model or effort outside the scope is a usage error (exit 2); the pipeline never dispatches
  it. `verdict` accepts optional `--model` and `--effort` and stores them with the verdict.
- **Runners.** The `orca` runner adds `--model` and `--effort` to `orca orchestration worker-start`,
  `orca worktree create` and `orca agent launch`. The Agent-tool runner passes only a model alias
  (`models.agent_tool_alias`): the Agent tool cannot set an effort, so the output and the prompt say so. The `print`
  runner shows model and effort in its header.
- **Personal override.** An optional JSON file with the same keys, at `$RPG_FACTORY_MODEL_POLICY` or
  `<persistent state dir>/model-policy.json`, may narrow `scope` and replace `profiles`. The result is checked again
  and an out-of-scope profile is an error. It is not committed; it lets one person limit their own spend.
