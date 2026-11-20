# Backlog

Topics for the next plugin plans (base `main`). A topic leaves this file when a plan task covers it; the list
below says where each earlier topic went. Conventions: `docs/plans/README.md`.

When a topic becomes a plan task, its `checks` name the task's own suites or
`tests/run-all.sh --affected --base <task base> -j 2`, never a full `tests/run-all.sh`, and its acceptance never
requires a full run: the one full run of a batch is integration QA (`skills/delivery/references/delivery.md` section 10, "QA tiers").

## In plan

None.

## Open

### test-flakes-followups

From plan test-flakes (`docs/plans/test-flakes/report.md`):

- Task verify does not run the portable-paths enforce line (the tier command's inline checks lack it), so new test
  fixtures with placeholder user paths are caught only after the merge. Add it to the task QA inline checks.
- `doctor` text prints the older python3 hook-speed advice next to the new setup-fault line (near-duplicate).
- `scripts/README.md` says `root_default` reads are allowed in `scripts/lib/`; the guard allows only
  `lib/workspace.py` and `lib/fstate.py`.
- The netcode prune case in `tests/run-all-parallel.test.sh` is not mapped to `scripts/checks/netcode-headless.sh` in
  `tests/affected.py`.
- A `file:` URL with a host part before the home directory is not flagged by `MACHINE_PATH`; `cd x && git -C ../y` resolves against the hook cwd.
- The test_lab idle-host CPU assertion branch has not run on this host (busy during QA).

### test-speed-followups

From plan test-speed (`docs/plans/test-speed/report.md`):

- `factory-pipeline.py` costs 2.5-4 s per start on Windows (imports, many git subprocesses in `status` and `gate`);
  it dominates `tests/pipeline.test.sh`. Lazy imports and fewer git calls per verb.
- `tests/affected.py` reach is per file: most `scripts/assetgen/*` changes and any `scripts/factory-pipeline.py`
  change select every case group. A per-function or per-module reach for the case maps.
- Re-QA in `--phase qa` unions the task check suites with the failed suites; use `--within` the failed suites.
- Full `tests/assetgen.test.sh` wall times before and after were never measured (every full run was killed for low
  memory); measure once on a quiet machine.

### core-style-v2

Bump the six core styles under `templates/assetgen/styles/` to structured v2 (`palette.colors`, `tone`, `canvas`),
and only after a game project has real derived values from `assetgen.py style derive`. Reason: the bump changes every
core style hash, so every existing run, anchor and rejection recorded against a core style drifts
(`assetgen.py drift` reports `older-version`: the bump moves the six core styles from version 1 to version 2, and the
version is checked before the hash).

### external-path-uri

`stylelock.EXTERNAL_PATH` still accepts `file:` URIs (with a drive letter) and `$HOME` / `%USERPROFILE%` forms in the
`external_source` `origin` and `rights_note`. Refuse a `file:` scheme and environment-variable paths, with a test.

### assetgen-run-followups

Left open by the plans assetgen-hybrid, assetgen-style and assetgen-batch (review notes and lead reports, none
blocking). Plan assetgen-followups covered the rest (see Covered); what remains:

- Environment: the check "registry paths exist in workspace" fails inside Orca agent terminals and passes in a
  direct shell and in integration QA; the workspace path resolves differently there.
- The local SDXL, IPAdapter and ControlNet paths of plan assetgen-hybrid have never run on the target hardware:
  the owner runs `docs/plans/assetgen-hybrid/e2e-local.md` on the RTX 5060.
- The model-hash cache writer is missing: no command in this repo writes `<state>/comfy/model-hashes.json`, so
  the manifest records local model sha256 as unverified (the assetgen check warns) until one exists.

### agent-runtime-quirks

Seen while running plan plugin-flow-2, not reproduced yet: a Codex session's start prompt sometimes stays
unsubmitted in its terminal, and Codex under PowerShell resolves `bash` to WSL instead of Git Bash (CLAUDE.md
"Operating lessons": Git Bash, never WSL). Find the cause; make dispatch detect or prevent each one.




### generic-explorer-name

`skills/delivery/pipeline-defaults.json` and the generic `skills/delivery/references/delivery.md` name the
RPG plugin's agent type `rpg-factory:factory-explorer`. The generic copy should name the subagent type through the
registry (`pipeline.subagents.models.claude.agent`) only, with a neutral default for a project without the plugin
agent.

### codex-subagent-model-enforce

`orca orchestration worker-start` and `orca agent launch` take no Codex `-c` override, so a Codex dispatch cannot set
`agents.default_subagent_model`; doctor only warns (`codex-subagents`). Ask Orca for a pass-through of agent CLI
config, or write the model into the session prompt as a hard rule, and re-check doctor's reach (project
`.codex/config.toml`, active Codex profile).

### workflow-slim-followups

Follow-ups and lows from plan workflow-slim (`docs/plans/workflow-slim/report.md`):

- Tier XS is accepted only for a one-task plan. A small prose follow-up found mid-run (final-pointers) had to become
  a full task with a task lead. Consider an XS task inside a multi-task plan, reviewed and gated like the one-task form.
- The plain `tier -- --repo` form counts files, not changed lines; only `tier --plan` and the gate measure lines.
- `factory-pipeline.py` usage text: `verdict` lists no `verify` phase and still says a subtask needs its own review;
  factory-core `SKILL.md` step 11 is still titled "Review + QA".
- The base health hint of `dispatch --phase lead` goes to stderr only (the run lead sees it, the task lead does not);
  `changelog.d/base-health.md` does not say the verify prompt carries `known_failing` too.
- Three low nits of the base-health review: `known_failing_text(plan)` computed twice per prompt; an entry with an
  unknown key gets both the error and the warning; the test fixture's origin remote is removed only on success.
- `orca terminal close --terminal <handle>` of a finished task lead returned `runtime_error`; `orca worktree rm`
  then deleted the branch a few seconds later (asynchronously), so `git branch -d` right after it failed with
  "used by worktree". Cleanup should wait for the worktree record to go before deleting the branch.
- `gate` reports files that came in with a merge of the default branch (`changelog.d/qa-lean.md`,
  `tests/affected.test.sh` through main-sync) and the run lead's `docs/plans/backlog.md` edit as "changes outside
  every task's owned paths"; credit both, like the plan file and the run report.

### plugin-flow-5-followups

Follow-ups and lows from plan plugin-flow-5 (`docs/plans/plugin-flow-5/report.md`):

- The task-lead report and READY_FOR_PR are in `status` notes, not structured fields:
  `docs/schemas/pipeline-status.schema.json` forbids extra fields (add them).
- `docs/pipeline-cli.md` lacks the `report` verb, READY_FOR_PR, the slot and BUSY? notes and orca-wait exit 6;
  `scripts/README.md` line 22 still says the waiter wakes on three message types and leaves messages unacked.
- `tests/pipeline.test.sh` runs ALL cases for `factory-pipeline.py` and `pipeline_route.py` (its case map is outside
  the plan task's owned paths); `--list-suites` hides `tests/plan-paths.test.sh` until it is wired.
- Lesson: a `status` message sent to a dispatch that has already finished creates an Orca follow-up worker (two
  appeared in this run). Send lead messages only to the run (`--to run:<id>`) of a live task lead, and put context in
  the start prompt.
- The `orca worktree set` call that follows `git worktree add` runs before Orca knows the worktree and sets nothing;
  `dispatch --phase lead` must wait for or retry until `orca worktree list` shows it.
- `dispatch --phase review` diffs `main...<sha>` in its spec. A task that merged another integrated task (here
  checks-lows, after ci-coverage) then shows nine foreign files as scope findings (a false FAIL). Use the task's
  recorded base or the integration base it merged.
- The integration QA verdict is not a clean pass on this host: `wire-parity` (Netcode `406a1b6` against server
  `633a792`) fails because the sibling repos drift. Reconcile Netcode and server before the next workspace gate.
- A QA worker's permission prompt on `rm -f $S/*.log` (a possibly-empty variable) stalls an unattended run; the QA
  spec template should use `"${S:?}"` or a literal path.

### policy-followups-leftovers

From plans policy-followups and owner-policy (`docs/plans/policy-followups/report.md`,
`docs/plans/owner-policy/report.md`):

- `plan_branch` in `scripts/factory-pipeline.py` treats `<topic>-*` as this plan's, so a plan whose topic extends
  this one (`<topic>-v2`) can count as a child when Orca's lineage names this plan's worktree as its parent; an
  Orca-prefixed branch equal to the topic (`codex/<topic>`) is not matched by lineage.
- With concise `worker-list` rows (Orca without `--full`), a worker released through `terminalState` but without
  `state` is still counted in the "settledness not checked" note.
- Codex "Hooks need review" trust prompt: documented in `docs/codex.md`; `agents` detection still cannot see it.

- `status --json` prints the `model_scope_widen` lines on stderr (`pipeline-status.schema.json` has no field for
  them).
- A released verify session left its `tests/run-all.sh` alive, holding a test slot (plan owner-policy); a verify
  session must stop its own run before it reports.

### plan-edit-followups

From plan plan-edit (`docs/plans/plan-edit/report.md`):

- `plan-edit` re-reads the copy after validation, and repeats the no-worktree marker step instead of using
  `read_plan` (low, from review).
- `validate` prints no staleness note for changed paths or acceptance; only `plan-edit` does.
- Released verify sessions leave their `tests/run-all.sh` alive, holding test slots for hours (plans owner-policy and
  plan-edit); a verify session must stop its own run before it reports.
- Orca `worker-start` with a Claude worker left the prompt typed but unsubmitted (`turn_start_unobserved`) in every
  start of plan plan-edit; the task lead had to send Enter. Detect it in the task lead's spec or the dispatch text.

### run-lows-followups

From plan run-lows (`docs/plans/run-lows/report.md`):

- `cleanup` still treats `<topic>-*` branches as the plan's own (status no longer does, `Lineage.owns`).
- The no-duplicate ERROR assertion of the `model_scope_widen` case would not catch a re-appended "; "-joined
  multi-problem error.

### path-audit-followups

Lows and findings from plan path-audit (`docs/plans/path-audit/report.md`):

- An Orca Codex worker can start with an empty prompt and idle with no escalation (task citation-drift: about 4.5
  hours), and a Claude implementer ended its turn without sending `worker_done`. Same class as agent-runtime-quirks:
  the task lead should time out a dispatch that shows no turn start and re-dispatch it.
- In Git Bash, `git -C` with the Git Bash drive spelling of the workspace failed for one worker while the drive-letter
  spelling worked (not reproduced).

## Covered

- **test-flakes** (load-sensitive flakes of netcode-headless, routing, test_lab and orca-wait; the orca-wait INT
  skip; slot message, netcode prune order, doctor setup faults, scripts README conventions; MACHINE_PATH file: URLs,
  relative git -C english-only scope, the facts LFS note): shipped in plan test-flakes (`changelog.d/test-flakes-load.md`,
  `changelog.d/test-flakes-runall-doctor.md`, `changelog.d/test-flakes-guard-paths.md`).

- **test-speed** (owner request 2026-11-18; the checks-contain-suites item of workflow-slim-followups, the
  low-memory lesson of path-audit-followups): shipped in plan test-speed (`changelog.d/test-speed-runall.md`,
  `changelog.d/test-speed-policy.md`, `changelog.d/test-speed-pipeline.md`, `changelog.d/test-speed-assetgen.md`).

- **run-lows** (flow-lows-followups; the root_default, slot_holders, status-on-QA-FAIL and frontmatter items of
  plugin-flow-5-followups; the cleanup, dead slot, run-all log and git timeout items of path-audit-followups; the
  status foreign worktree item of workflow-slim-followups; most `model_scope_widen` lows): shipped in plan run-lows
  (`changelog.d/run-lows-paths.md`, `changelog.d/run-lows-evidence.md`, `changelog.d/run-lows-pipeline.md`).

- **review-base-topic** and **run-all-orphan-after-reap**: shipped in plan assetgen-followups (task topic-start-base,
  `changelog.d/topic-start-base.md`: a task whose deps are all integrated starts from the topic and gets no stack
  record; task run-all-result-record, `changelog.d/run-all-result-record.md`: the run-all result record,
  `--last-result`, duplicate-run detection and the `parallel-work.md` lesson).

- **assetgen-run-followups** (engine, hybrid templates, comfy-desktop-setup, batch, style report and docs notes):
  shipped in plan assetgen-followups (tasks engine-notes, batch-report-notes and followup-docs;
  `changelog.d/assetgen-engine-notes.md`, `changelog.d/assetgen-batch-report-notes.md`,
  `changelog.d/assetgen-followup-docs.md`: comfy-desktop-setup ends with saving `hardware-profile.json`, the
  architecture doc states the tech skill count); the environment note, the owner's local e2e run and the missing
  model-hash cache writer stay under assetgen-run-followups in Open.

- **delivery.md headroom** (plan-edit-followups, workflow-slim-followups), the `tests/README.md` QA tiers restatement
  and four plugin-flow-5-followups lows (hook-perf `.new`, gitcfg re-snapshot, netcode-headless evidence, `/mnt/`
  segment in `plan_paths.py`): shipped in plan flow-lows (`changelog.d/flow-lows.md`, delivery.md at 31497 bytes);
  the lows moved to flow-lows-followups.

- **plan-edit-verb**, **plan-edit-commit-guard** and **run-lead-waiter-reaped**: shipped in plan plan-edit
  (`changelog.d/plan-edit-verb.md`, the waiter lesson in `skills/factory-core/references/parallel-work.md`); the lows
  moved to plan-edit-followups.

- **policy-followups-leftovers, the two owner decisions of 2026-11-17**: shipped in plan owner-policy
  (`changelog.d/owner-policy-scope-widen.md`, `changelog.d/owner-policy-english-scope.md`); the lows stay in
  policy-followups-leftovers.

- **repo-path-audit**: shipped in plan path-audit (`changelog.d/path-audit-pattern.md`,
  `changelog.d/path-audit-check.md`, `changelog.d/path-audit-affected.md`); the lows moved to path-audit-followups.

- **language-policy-followups**: shipped in plan policy-followups (`changelog.d/policy-file-guard-allowlist.md`,
  `changelog.d/policy-git-guard-lows.md`, `changelog.d/policy-language-line.md`, `changelog.d/policy-pipeline-orca.md`);
  the two owner decisions and the low findings moved to policy-followups-leftovers.

- **affected-selection-followups**: shipped in plan affected-followups (`changelog.d/affected-rpgf-guard.md`); the
  two-hop `workspace.sh` callers stay accepted (they run in a full run).

- **workspace-leftovers-followups**: shipped in plan leftovers-followups
  (`changelog.d/leftovers-gate-allowlist-case.md`, `changelog.d/leftovers-affected-syspath.md`,
  `changelog.d/leftovers-tmpdir.md`); the two-hop `workspace.sh` callers were accepted as they are.

- **workspace-followups-leftovers**: shipped in plan workspace-leftovers (`changelog.d/workspace-leftovers-cygwin.md`,
  `changelog.d/workspace-leftovers-gate-english.md`, `changelog.d/workspace-leftovers-affected.md`,
  `changelog.d/workspace-leftovers-pin-loader.md`).

- **workspace-default-followups**: shipped in plan workspace-followups
  (`changelog.d/workspace-default-followups.md`).

- **workspace-default-by-platform**: shipped in plan workspace-default (`changelog.d/workspace-default.md`,
  `changelog.d/gate-lead-files.md`).

- **ci-backlog-followups**: shipped in plan ci-backlog-followups (`changelog.d/routing-workspace.md`,
  `changelog.d/alias-probe.md`, `changelog.d/codex-config-reuse.md`).

- **ci-matrix-followups** and the Codex availability item of plugin-flow-5-followups: shipped in plans ci-followups
  (`changelog.d/ci-cases.md`, `changelog.d/pipeline-followups.md`, `changelog.d/orca-wait-stall.md`) and ci-backlog
  (`changelog.d/dispatch-notes.md`, `changelog.d/codex-detect.md`, delivery.md trimmed to 1582 bytes under its cap).

- **child-worktree-when-needed** (Orca child worktrees per subtask, UTF-8 BOM in plan and subplan loaders,
  per-candidate verdict records): shipped in plan plugin-flow (`changelog.d/child-worktrees.md`).
- **guard-polish** (duplicate import, generic package name, stale docs index, blank end-of-file lines, standalone
  `tests/artifact-quality.test.sh`): shipped in plan plugin-flow, except guard-package-rename above.
- **flaky-wall-clock-tests** (`run-checks.py --timeout 1` wall-clock bound, `ui-commands` `components settings`):
  shipped in plan plugin-flow.
- **Verdict file name collision** (task `a__sub-b` against task `a` subtask `b`): shipped; a subtask's verdict is
  `<task>@<subtask>__<phase>.json`, and no task id contains `@`.
- **model-fallback** and **agent-routing** (routing by model strength, `available_agents`, `RPG_FACTORY_AGENTS`,
  `SAME_MODEL (fallback: <model> unavailable)`): plan plugin-flow-2 task agent-routing.
- **agent-routing follow-ups and own-start-qa-only lows** (legacy verdict suppression prefix, QA PASS comment):
  plan plugin-flow-2 task routing-followups.
- **work-state-in-repo** (plans and backlog in the repo, portable repo paths, the run lead's waiter, run reports,
  atomic plan edits; the orca-wait suite runs inside `tests/parallel-policy.test.sh`): plan plugin-flow-2 task
  work-state-in-repo.
- **run-all-robust** (`run-all -j` hang on a dead suite, `tests/git-guard.test.sh` empty-output flake under load,
  shared `.git/config` changes by other sessions): plan plugin-flow-2 task run-all-robust, except
  run-all-robust-lows above.
- **Facts probe of the committed tree** (an uncommitted Unity `EditorSettings.asset` change failed
  `enter-playmode-options`): plan plugin-flow-2 task checks-hygiene, except checks-hygiene-lows above.
- **Gate and status on multi-wave plans** (review attribution by merge commits, true implementer, task QA in
  `status`, `verdict --note`, agent-routing changelog entries under Added, kind enum copies tied to the plan
  schema): plan plugin-flow-2 task gate-multiwave.
- **wave-close** (subtask review staleness with multi-wave attribution and the subtask's own paths, `verdict
  --fallback` after the fact, `plan_paths.resolve_repo_path` in `repo_info`, CR-stripped skill names in
  `tests/routing.test.sh`, `tests/affected.py` selection for orca-wait, `scripts/orca-wait.sh` in
  `scripts/README.md`, `merge --no-ff` for later waves and the `verdict` options in `parallel-work.md`, now `delivery.md`): plan
  plugin-flow-2 task wave-close.
- **plugin-flow-5** (`delivery-generic` in run-all and `affected.py`, bare-bash probes, `routing-golden --update`
  on Windows, run-all-robust lows, narrower selection for `factory-pipeline.py`; task-lead reports reaching the run
  lead and `status`, released-worker and slot-holder notes, tier-plan-arg, implementer-refusal-scope,
  `pipeline.test.sh --help`, orca-wait lows, Orca `externalWorktreeVisibility`, `verdict --fallback` text,
  model-unavailable probe; checks-hygiene lows, plan-paths-native, guard package rename): plan plugin-flow-5, except
  plugin-flow-5-followups above.
