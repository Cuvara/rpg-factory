# Delivery pipeline CLI

Command forms and flag rules of `scripts/factory-pipeline.py`. The policy they implement is
`skills/delivery/references/delivery.md` (section 10); this file holds only the CLI details that policy points to.
Run the script as `python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py <verb>`; `--registry none` (before or
after the verb) reads `skills/delivery/pipeline-defaults.json` instead of the registry `pipeline` block.

## tier and planner

- `tier -- --repo <key> --paths <files>` prints XS, S, M or L and the flow. An S task is still a one-task `plan.json`
  with its own task lead (the task worktree, or the main checkout of a no-worktree repo).
- XS applies only when every path is prose (`pipeline_route.prose_path`, see "dispatch" below), no path is a contract
  or generated path, and the change stays within `pipeline.tiers.XS` (`max_files`, `max_changed_lines`). All forms
  measure changed lines against the same `max_changed_lines`: the plain `tier -- <factory-context.sh args>` and
  `--context-json` forms, with a checkout, count `git diff --numstat` over the snapshot's files plus the lines of
  untracked ones, against the merge-base with `HEAD` of the repo's `branch_diff_base` (the branch scan), else of the
  `--base` of the args (`--paths` leaves `branch_diff_base` null, so `tier -- --repo <key> --paths <files> --base <b>`
  counts the committed lines since `<b>` too), else against `HEAD`; `tier --plan` counts the changed lines of the
  checkout, and the gate those of the committed diff. The output names what was measured:
  `changed lines: <n> (<basis>)`, or `changed lines: not measured (no checkout)`; `--json` carries `lines_basis`, and
  `changed_lines` only when something was measured.
  An XS task has no task lead, task worktree or implement session: the run lead itself edits and
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
  integration QA"), and when a task owns code or test paths (not only prose) but its `checks` name no test suite
  ("checks name no test suite; name the suites that test the changed behaviour (task QA runs only them with
  `--within`)"). A scoped `tests/run-all.sh --affected ... --within <suites>` check counts as naming them.
- `subplan validate subplan.json` (format: `docs/schemas/pipeline-subplan.schema.json`) prints OK when every
  subtask path is repo-relative (no absolute or `..` path),
  inside the task's owned paths and outside its exclusions, overlapping subtasks are ordered by deps, there is no
  unknown dep or cycle, each subtask names an `implementer` or a `kind`, each implementer is a pipeline agent and each
  reviewer is of the other model. It prints the waves (one subtask per wave in a no-worktree repo) and refuses
  `placement: child` in a no-worktree repo. It warns like `validate` on a missing `reason` or one model for 3 or more
  subtasks.
- When the plan has no error, `validate` prints a `NOTE` line (`notes` in `--json`; never an error, the exit code is
  unchanged) for each recorded review or QA verdict of a task (or `integration:<repo>` QA) whose fingerprint no longer
  matches the plan: `recorded <phase> verdict of <id> is stale: the task's objective, paths, acceptance, checks or
  agents changed since it was recorded; re-run review/QA (status shows it)`. It only reads the verdict records.
- `validate` accepts tier XS (plan or task `tier`) only for a one-task plan whose owned paths are all prose, within
  `max_files` and, where the XS rule sets `contracts: false` / `generated: false`, no contract end or generated path;
  a non-prose path, a second task, a threshold exceeded, a contract or a generated path is an error.
- Both reject an unknown grade or one the model policy cannot resolve, and print the resolved model and effort per
  task or subtask.

## plan-edit

`plan-edit <plan.json> --from <edited copy> [--commit [--message <text>]]` is the atomic plan edit of delivery.md
section 8: edit a copy, never the plan, then let the verb check it and replace the plan.

- It validates the copy with the `validate` code path (same registry or `--registry none`, same checks and warnings),
  with the copy read as if it sat at the plan's path, so relative `repos.*.path` entries resolve exactly as they do
  for the plan.
- Only when validation has no error does it replace the plan, atomically: it writes a temp file in the plan's
  directory, then `os.replace`s the plan with it. Warnings never block the replace.
- On any validation error it prints the errors, leaves the plan file and the git index untouched (also with
  `--commit`: no commit is made) and exits 1.
- It exits 2, changing nothing, when the copy is missing or unreadable, when the copy's `id` differs from the plan's,
  or when `--commit` is given and the plan is not inside a git checkout.
- It prints what changed at task level: tasks added, tasks removed, and tasks whose owned paths, acceptance or deps
  changed. For changed paths or acceptance it also prints the staleness note: the recorded verdicts of those tasks
  go stale, so re-run `status` after the plan edit.
- `--commit` stages only the plan file (never `git add -A`, so other dirty files stay unstaged) and commits it in the
  plan's checkout. The default message is `docs(plans): edit plan <id>`; `--message <text>` replaces it. The verb
  never pushes.

## dispatch

- `--note TEXT` is repeatable; `RPG_FACTORY_SESSION_NOTE` supplies one additional note. Dispatch appends each as a
  `Session note: <text>` line to every spec kind, collapsing whitespace and dropping duplicates. The lead's
  `<dispatch>` carries them on to its sessions. On win32, when `python3` resolves into WindowsApps or the Store alias
  `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe` exists (also behind a `python3` shim first on PATH), the spec
  also explains how to use the dispatch interpreter or a `python3` shim instead of the Microsoft Store alias.
- `--note-file FILE` is repeatable and adds the file's text to every spec kind verbatim, as its own
  `Session note file <path>:` section. Nothing is collapsed, so parentheses, quotes, `&`, `|` and newlines survive.
  Files are deduplicated by absolute path. A missing, unreadable or blank file exits 2 before anything is written or
  printed. The lead spec forwards each one to the sessions it dispatches as `--note-file=<path>`. The Orca prompt is
  only the spec pointer `Read your task spec at <path> and follow it.`, so notes never go on `--prompt` (a note with
  quotes appended to `--prompt` once broke a lead launch with `unknown option '-FilePath'`).
- `dispatch plan.json --task <id> --phase lead --report-to <run lead run id> --runner orca` prints the task-lead
  handoff. A new task worktree: `git worktree add --no-track -b <branch> <path> <base>` (beside the checkout that has
  the plan `topic` checked out, else beside the repo checkout), then
  `<pipeline> orca-wait --worktree <path> && orca worktree set ...` (the lineage line of delivery.md section 4
  "Orca visibility", run only once Orca lists the new worktree: see "orca-wait"), then
  `orca agent launch --worktree path:<path>`. An existing task worktree, or the main
  checkout of a no-worktree repo, gets only the launch (never a worktree create or a new top-level worker there);
  `--placement shared|child` gives the same result. Orca allows one worker level (maximum depth 1), so the task lead
  then creates its own Run (`orca orchestration run-create --objective <text>`), starts its sessions as workers of that
  Run (`orca orchestration worker-start --worktree path:<task worktree>`, depth 1) and reports to the run lead with
  `orca orchestration send --to run:<run lead run id> --type status --subject <text> --body <report>`.
  A first-wave task branches from `repos.<key>.base`; a later-wave task (one with deps) from the plan's `topic`
  integration branch when it exists, because that branch carries the earlier waves. `repos.<key>.base` stays the
  comparison base of `status` and the gate: never point it at the topic (then `base..head` counts nothing and
  integrated tasks show as pending).
- Base health (advisory, print only): for a repo with a GitHub remote (read from the local `git remote -v`, never a
  network command) and a base branch name (a SHA base falls back to the repo's base branch), `--phase lead` prints
  ``factory-pipeline: base health: run `gh run list --branch <branch> --limit 1` before starting`` on stderr, and the
  lead spec carries the same advice on a `Base health:` line, so the task lead sees it too, not only the run lead.
  Dispatch never runs `gh` itself.
- Stacked task (the rule: delivery.md section 4 "Stacked dependents"): a task stacks when its one in-flight
  dependency in the same repo is a candidate or reviewed and every other dependency is integrated; two in-flight
  dependencies, or a pending or implementing one, never stack. When `status` notes `stackable on <dep>@<sha>`,
  `--phase lead` prints `git worktree add --no-track -b <topic>-<id> <path> <dependency tip SHA>` for a sibling beside
  the integration checkout (never a child of the dependency's worktree), the `orca-wait`-chained `orca worktree set`
  with the integration checkout (else the main checkout) as parent, then the launch; the lead prompt says to
  implement now and to run no verify, review or QA dispatch before `status` clears it. It records the dependency SHA
  as the base (a SHA, never a branch name) in `<task>__stack.json`, outside the task fingerprint, so recorded
  verdicts stay valid. A fresh dispatch (no task branch yet) first removes a leftover `<task>__stack.json` and
  `<task>__sync.json`. Tier XS and no-worktree tasks keep the unchanged handoff.
- Topic start base (no stack): a dependency whose task branch tip is already on the topic counts as settled even when
  its recorded phase is still candidate or reviewed (its verdicts may be STALE after the plan changed), so a task
  whose dependencies are all merged into the topic is not stackable. `--phase lead` then prints `git worktree add
  --no-track -b <topic>-<id> <path> <topic>`, never a dependency's old branch tip, and removes any leftover
  `<task>__stack.json`; no stack record exists afterwards. A task branch that exists and was cut from (or merged
  into) the topic ahead of `repos.<key>.base` starts at the topic, with or without deps: its review base and own
  start are the newest topic commit in its HEAD, so the tier command (`--affected`) and the review select only its
  own delta instead of every suite. A stack record whose dependency was integrated into the topic before the task
  branch was cut is ignored by `status` (no `stacked on` note), verify, review and QA dispatch and the gate (no
  `integrated before its dependency` blocker). Stacking on one in-flight dependency is unchanged.
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
  list for its base and suite selection (`ALL` for a check suite the change does not reach), with the affected suites
  outside the task checks named as left to CI. `--task integration:<repo>` targets the
  integration HEAD (a child of the integration checkout with `--placement child`); in a no-worktree repo `--task <id>`
  also runs per task, before the next task starts.
- A stacked task's `--phase verify|review|qa` exits 2 (no prompt, record or launch) until its dependency's
  review PASS SHA is in `--sha`; the reason names the merge (`git merge <dependency branch or PASS SHA>, never
  rebase`). Its review and QA `--affected --base` is the newest dependency SHA in HEAD (once the recorded dependency
  SHA is on the `topic`, the later-wave base), so they see only the task's own delta.
- Task QA tier command (`--phase verify|qa`, tier XS lead step): `tests/run-all.sh --affected --base <review base>
  --within <the checks' suites> -j 1`. Only the suites the task checks name run, each with its affected cases
  (`--case`; all cases when the change does not reach it); the other affected suites are left to CI and run-all names
  them on one `left to CI:` line. A check is folded in only when it is one standalone suite or plain run-all command
  and the suite is one `tests/run-all.sh --list-suites` prints; other checks stay extra commands. A task whose checks
  name no suite keeps the safe form `tests/run-all.sh --affected --base <review base> -j 1` (the whole affected
  closure; the spec says to name the suites in the task checks to scope it). Without a review base only the check
  suites run (`tests/run-all.sh --only-suites <suites> -j 1`), else the command is `NONE`; never a full run.
  Re-QA after a QA FAIL with `--failed-suites` (`--phase verify` and `--phase qa` alike): the same form with
  `--base <that FAIL's candidate>`, `--within` only the failed suites plus the task check suites the fix delta reaches
  (tests/affected.py: the delta since the failed candidate touches the suite or a path it tests); the other task check
  suites are not rerun, because their PASS stands on the failed candidate. The task's other check commands stay extra
  commands. When the affected selection cannot be computed (tests/affected.py missing or failing, `git diff`
  failing) the re-QA keeps every task check suite, the safe side, plus the failed suites. The repo-wide guard scripts
  `--within` also runs (`WITHIN_GUARDS` in tests/run-all.sh: `scripts/checks/english-only.py`,
  `scripts/checks/portable-paths.py`) are never listed as left to CI.
  Integration QA (`--task integration:<repo> --phase qa`): `tests/run-all.sh --workspace-only --base
  <plan base>` (the plan's comparison base: `repos.<key>.base_sha`, else `base`), only the workspace checks the
  change reaches; without a known base `tests/run-all.sh --workspace-only`. Exit 6 (nothing the change reaches) is
  NOT_RUN, never a pass: integration QA then runs `tests/run-all.sh --workspace-only` without a base and grades
  that run.
- Pre-flight (advisory): `--phase verify|qa` prints on stderr `factory-pipeline: selected N of M suites
  (tests/affected.py; K affected suites left to CI)` (N: the suites the tier command runs, the check suites under
  `--within`, else the whole affected closure; K: the affected suites outside the checks, the clause is omitted
  without check suites; M: `tests/run-all.sh --list-suites`), or
  `factory-pipeline: selected suites: not computed (<reason>)`, and a warning to narrow the task paths or its checks
  when N (the scoped count) is above `--suite-warn N` (default 40; below 1 is a usage error, exit 2). The prompt and exit code do not
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
  `--affected --base <that FAIL's candidate>` with only those suites in `--within`, plus the task check suites the
  fix delta reaches, never all the task's own check suites; a repo without `tests/run-all.sh` keeps its task check commands.
- `--model` and `--effort` are optional and stored with the verdict.
- A stacked task: a review or QA PASS (task, `--subtask`, or `--phase verify`) on a SHA without the dependency's
  current review PASS is refused (exit 2, nothing written); FAIL and the other states are recorded.

## report

```
factory-pipeline.py report plan.json --task <id> --sha <sha> (--body TEXT | --body-file FILE)
```

- The task lead's durable report. It writes `<state dir>/pipeline/<plan id>/<task>__lead-report.json` beside the
  verdicts: `plan`, `task`, `sha` (the full commit id `--sha` resolves to in the task's repo), `at` (UTC time),
  `summary` (the first non-blank line of the body, capped at 200 characters) and the full `body`. A new report
  replaces the previous one.
- The task lead runs it after the verify verdict and before its Orca `status` message to the run lead (delivery.md
  section 1 "Roles" and section 8 "Session lifecycle"), so the run lead's `status` shows completion even when the
  message never arrives.
- `status` shows the record as the `lead report:` note of the task row and uses it for `READY_FOR_PR` (see "status and
  cleanup"); `nudge` counts a new report as progress.
- Exit 0 recorded, 2 usage: an unknown task or `--task integration:<repo>`, a `--sha` that is no commit of the task's
  repo, an unreadable `--body-file` or an empty body.

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

## nudge

```
factory-pipeline.py nudge plan.json [--task <id>] [--idle SECONDS] [--stall SECONDS] [--orca-run RUN_ID]... [--send]
```

- Finds a start prompt that stayed unsubmitted in a task session's terminal (an Orca session whose prompt was typed
  but never submitted idles for hours). Per task with a task worktree it lists that worktree's Orca terminals
  (`orca terminal list`) and reads each screen (`orca terminal read`). Both are read-only.
- A terminal is `STUCK` only when all three hold: its screen still shows the spec pointer of a spec file of this plan
  (`Read your task spec at <path>`, a wrapped pointer is joined), its last output is older than `--idle` (default 120
  seconds), and the task made no progress since the spec file was written. Progress is a new commit on the task
  branch, a new lead report, or a new review or QA verdict file; model records do not count.
- One row per terminal: task, handle, idle seconds, `ok` or `STUCK`, the reason, and for a `STUCK` one the exact send
  command.
- `--send` sends one carriage return per `STUCK` terminal (`orca terminal send --terminal <handle> --text ...`) and
  records `<task>__nudge.json` (handle, time, spec path). Without `--send` nothing is written.
- One send per spec: a spec that was already nudged prints `nudged, still stuck: relaunch the session` and is never
  sent again.
- An `orca` that resolves to a `.cmd` or `.bat` shim is not sent to (the CR argument is dropped) and counts as a
  failed send; the row prints the command to run by hand.
- Orca missing or unreachable prints a note and exits 0. Exit 1 when a send failed, 2 on usage (an `integration:`
  task, a negative `--idle` or `--stall`, an unknown task).
- STALLED workers (read-only): `nudge` then checks the running workers of the task leads' Orca Runs: each listed
  task's `orca_run` plus `--orca-run RUN_ID` (repeatable). With no Run named it prints
  `nudge: no Orca Run named (task orca_run or --orca-run): stalled workers not checked`. Per Run it calls
  `orca orchestration worker-list --full` and skips settled or released workers; per running worker
  `orca orchestration worker-show --dispatch <id> --full --json` and the last output of its agent terminal
  (`agentTerminalHandle` in `orca terminal list` of its worktree).
- One row per running worker, `<run>  <dispatch>  idle <n>s  ...`: `ok  waiting on a human` when
  `observation.agentWait` is set; `ok  active (<n>s < <stall>s)` when the terminal was silent for less than `--stall`
  seconds (default 900); `ok ... (no opinion)` when a call fails or data is missing (worker-show, terminal list, no
  agent terminal or worktree, no `lastOutputAt`). Otherwise `STALLED  no turn start` (its last dispatch input ended
  `turn_unobserved`, or it has no dispatch input record and `lastError` says the turn start was not observed) or
  `STALLED  turn ended without worker_done`, followed by a `re-dispatch:` line: read the terminal
  (`orca terminal read --terminal <handle>`), `orca orchestration worker-stop --dispatch <id>`, dispatch a fresh
  session with the same phase, and release the old one with `orca orchestration worker-release --dispatch <id>`.
- `--send` never sends anything for a `STALLED` row and nothing is written for it; a `STALLED` row does not change the
  exit code.

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
  well: one that contains a dependency PASS merged strictly earlier clears both checks. A review SHA that is itself a
  commit of the integration head's first-parent chain (an integration commit, for example a delta review at the
  integration HEAD or later) never stands for the task's own merge point: such a candidate is skipped, and without an
  earlier PASS on the task branch merged after the dependency the order blocker stays. A dependent integrated before
  its dependency stays blocked, because its merge brings the dependency PASS in at the same first-parent position,
  even when it is reviewed again at a later integration HEAD. Any git error keeps the blocker (fail safe).
- A task review recorded at a later SHA of an already reviewed task (a delta review) keeps the fallback that dispatch
  recorded for its earlier review, so a recorded SAME_MODEL fallback stays an accepted note and a task never reviewed
  before still blocks (see "Fallback reviews").
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

## orca-wait

`orca-wait --worktree PATH [--gone] [--timeout SECONDS] [--interval SECONDS]` (PATH may carry a `path:` prefix) is
read-only: it polls `orca worktree list --json` every `--interval` seconds (default 2) until Orca lists PATH, or with
`--gone` no longer lists it, and writes nothing. It is not `scripts/orca-wait.sh` (the run lead's Orca message waiter,
`orca-wait.sh --run <id>`, below).

- Exit 0 once the condition holds: `orca-wait: <path> is listed by Orca` (`is no longer listed` with `--gone`).
- Exit 1 after `--timeout` seconds (default 60). Without `--gone`: the worktree stays hidden in Orca (an
  `orca worktree set` now changes nothing); retry, or run `orca worktree set` by hand once `orca worktree list` shows
  the path. With `--gone`: its branch is still in use by the worktree (`git branch -d` would fail with 'used by
  worktree'); retry, or delete the branch by hand once `orca worktree list` no longer shows the path.
- Exit 1 when `orca` is not on PATH or `orca worktree list --json` fails or prints no worktree list: it cannot tell,
  so run the next command by hand once the list shows (or no longer shows) the path.
- Exit 2 on a negative `--timeout` or `--interval`.
- Callers: the `dispatch --phase lead` handoff chains it before `orca worktree set` (Orca lists a worktree it did not
  create only after a while); `cleanup` prints `orca-wait --gone` per path it removes through `orca worktree rm`
  before a repo's first `git branch -d` (`orca worktree rm` removes asynchronously).

## Orca commands

The Orca commands delivery.md relies on: `orca orchestration run-create`, `orca orchestration task-create`,
`orca orchestration worker-start`, `orca orchestration check`, `orca orchestration reply`, `orca orchestration send`,
`orca orchestration worker-show`, `orca orchestration worker-read`, `orca orchestration worker-list`,
`orca orchestration worker-release`, `orca agent launch`, `orca worktree list`, `orca worktree create`,
`orca worktree rm`, `orca terminal list`, `orca terminal read`, `orca terminal send` (the last three: `nudge`).
`scripts/orca-wait.sh` allows one waiter per Run through a lock file in the state dir (it waits for messages; the
verb `orca-wait` above waits for a worktree record).

`scripts/orca-wait.sh --run <id> [--timeout-ms N] [--types T] [--stall-poll-ms N] [--stall-ms N]` exits:

- 0: a real delivery, printed on stdout.
- 2: usage, NOT_AVAILABLE (no `orca` on PATH), an invalid receipt or state.
- 3: the lock is held by another waiter (an orphaned holder is named and exits at its next poll) or the acquisition
  stays busy.
- 4: `orca orchestration check` failed.
- 5: a stalled worker (`STALL` lines; a provider error also prints the `agents --down` command as a `NEXT` line).
- 6: its parent process is gone (an orphaned waiter). It releases the lock. A real delivery it had already received
  is saved to `<lock>.orphan.<pid>.json` and the file is named on stderr; otherwise read it with
  `orca orchestration inbox` (Orca marks a returned batch as handled).
- 130 and 143: interrupted (INT, TERM).

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
  each leftover child ("child of <task>") with its merge state. A lineage-only child must have a branch belonging
  to the plan topic or start with `<topic>-` (also after an Orca prefix); foreign and detached worktrees are
  excluded. Named child branches still match the `<parent branch>--` rule.
- `stuck?: session <handle> still shows its start prompt after a nudge at <time>: relaunch the session` on a task row:
  the latest `nudge` record still shows the unsubmitted prompt and the task made no progress since (`nudge`).
- `lead report: <at> @<sha10> <summary>` on a task row comes from the task's `report` record, with
  `(stale: task HEAD is <sha10>)` when the task HEAD moved on. Without a record, a `task done: <id>` message of the
  task lead's Orca Run (read-only `orca orchestration check --run <id> --all --json`, never marks a message read; any
  failure is no opinion) shows as `lead report: task done: <id> (an Orca message only ...)`.
- `READY_FOR_PR: yes` or `READY_FOR_PR: no (<first missing reason>)` on each task row once the task has a candidate
  (phase candidate, reviewed, integrated or qa; never for a tier XS task). `yes` needs all of: a lead report at the
  task HEAD, a current review PASS and a current QA PASS at the task HEAD (an integrated task may have them at an
  ancestor, as the phase rules allow), and no blocker such as a subtask review or QA FAIL. The reason names the first
  of these that fails, for example `no lead report`, `review is at <sha10>, task HEAD is <sha10>` or `no QA`.
- `status --json` (`docs/schemas/pipeline-status.schema.json`) carries the same facts as typed fields; the text
  output is unchanged:
  - per task `lead_report`: `{at, sha, summary, current}` (`current` is true when the report counts for the task HEAD),
    or null without a durable record;
  - per task `ready_for_pr`: `{ready, missing}` (`missing` is the first missing reason, null when ready), or null
    where the text output prints no `READY_FOR_PR` note;
  - top-level `model_scope_widen`: the plan's valid model scope widenings (`agent`, `model`, `efforts`, `basis`,
    `reason`, plus the `text` the stderr line prints), `[]` when none. The `model scope widening: ...` lines still
    go to stderr.
- Test slots held by a run in one of the plan's checkouts print as `Slots: slot <n> held by PID <pid> in <checkout>
  since <start>` with the holder's liveness and its last progress (check, result, counts, age of the update); with
  `--json` these lines go to stderr and the `slots` field carries the same holders (slot, pid, winpid, alive,
  checkout, started, and `progress` with check, result, passed, failed, updated, age_seconds, or null before the
  first one), the entries `cleanup --json` has. Status never stops a holder: the user decides.
- A slot left by a verify dispatch: a slot whose holder is alive (or cannot be checked) in a task worktree of the plan
  (the task branch's worktree or one of its children) where, at or after the slot's start, that task's verify
  reported (a `qa` verdict, or a `review` FAIL, of the task or a subtask) or a worker of the task's Orca Run in that
  checkout was released (`releaseCompletedAt`, else the `releaseRequestedAt` of a released row; a release with
  neither time flags nothing). Status prints `Slots: LEFT BY VERIFY slot <n> held by PID <pid>
  [(Windows PID <winpid>)] in <checkout> since <start> [(alive)|(liveness unknown)]: task <id>: <what reported or
  was released, when> after the run started; stop that PID only: <command> (status never runs it)`. The command is
  `kill <pid>`, or `taskkill //PID <winpid> //T //F` when the slot has a Windows PID. The task row gets a note
  (`test slot <n> (PID <pid>) in <checkout> left by the verify session (...)`) and the command comes first in `next`.
  Status stays read-only and reuses its one `worker-list` call. With `--json` the line goes to stderr only: the
  schema's slot entries take no extra field.
- Worker listing requests `--full` and retries without it when Orca reports that flag as unknown, keeping the concise
  form for later pages. Concise rows use `terminalState` for release and `state` for settledness (a row whose
  `terminalState` is `released` counts as released even without a `state`); the Run line names missing fields and
  the checks they prevent. Other Orca failures remain NOT_AVAILABLE.
- Stacked notes on a task row: `stackable on <dep>@<sha>` (a pending task, ready: next is its `--phase lead`),
  `stacked on <dep>@<sha>`, `<dep> now at <sha> not in HEAD: merge it (never rebase), then continue` (next: the
  `git merge`), `sync: <dep> moved to <sha> (<at>)` (from the `sync` record, only for the current dependency, until
  HEAD contains the SHA), `verify waits: <reason>` (a candidate; next: the merge, or none while the dependency has no
  PASS), `integrate <dep> first (dependency first), then merge <branch> with git merge --no-ff` and, while one of
  them is not integrated, `stacked siblings <ids> on <dep>: sibling worktrees, not children of <dep>'s worktree;
  merge order <dep branch>, then <dependent branch> into <topic> (dependency first, git merge --no-ff); git branch -d
  a branch only after its merge`.
- `cleanup plan.json` lists what is left: the plan's worktrees and task branches (the same ownership as `status`: the
  topic or `<topic>--...` (the integration QA child), a task branch or `<task branch>-...`, each with an optional
  Orca prefix; a `<topic>-...` branch of another
  plan or a longer topic is not the plan's), leftover children, and settled Orca
  workers not released in each task lead's Run (task `orca_run` or `--orca-run <id>`, read-only `worker-list`; no
  orca is NOT_AVAILABLE), with the commands to remove them (`orca orchestration worker-release` closes only that
  worker's terminal and keeps its output readable). A leftover task directory (empty or not) or an Orca
  record of a removed worktree is LEFTOVER, never CLEAN, with `git worktree prune`, then
  `orca worktree rm --worktree path:<dir>` once the directory is free. `orca worktree rm` removes asynchronously, so
  before a repo's first `git branch -d` the commands carry one `<pipeline> orca-wait --gone --worktree <path>` per
  path removed through `orca worktree rm` (merged children, leftover directories and records): a branch is deleted
  only once its worktree record is gone ("orca-wait").
- For such a leftover directory `cleanup` lists `BUSY?` candidates from a read-only process listing (Windows:
  PowerShell `Get-CimInstance Win32_Process`, 20 s timeout; elsewhere `ps`): processes whose command line names the
  directory and an orphaned `wsl.exe ... sleep infinity` whose parent is gone, each with PID, command and start time.
  The user decides: no kill command is printed, and a failing probe names nothing. Before a task worktree is removed
  it names the Orca terminals bound to it (read-only `orca terminal list`). It also prints `SLOT` lines for held test
  slots in the plan's checkouts, as `status` prints its `Slots:` lines (`slots` in `--json`).
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
  and an out-of-scope profile is an error. It is not committed; it lets one person limit their own spend. It can
  never widen the scope.
- **Plan scope widening.** An optional plan field `model_scope_widen` (`docs/schemas/pipeline-plan.schema.json`) lets
  one plan use a model outside `models.scope`. It is a list of entries
  `{agent, model, efforts, basis, reason}`: `agent` is a pipeline agent, `efforts` a non-empty list, `basis` is
  `owner-approved` (`reason` holds the owner's word and its date) or `necessary` (`reason` says why no in-scope model
  can do the work), and `reason` is never empty. The policy order is the registry, then the personal override (narrow
  only), then the plan's widening; the widening applies to that plan alone and never to another plan.
  - A widened model is used only when passed explicitly (`dispatch --model` and `--effort`); `profiles` do not
    change. `subplan` validation uses the widened scope too. Without an entry a model outside the scope still exits 2.
  - `validate` fails on a malformed entry, an unknown agent, an unknown basis or an empty reason, and prints a NOTE for
    an entry whose model and efforts are already in scope. It prints `Model scope widening: ...` per entry, `status`
    prints `model scope widening: ...` per entry (stderr with `--json`, where the `model_scope_widen` field carries
    the entries), and `gate` prints a note per widening
    and the lead report lists them, so the final report shows them.
  - Every command that accepts a widened model prints one line, for example
    `model scope widened by plan <id>: <agent> <model> [<efforts>] (basis <basis>: <reason>)`.
