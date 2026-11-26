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

- The test_lab idle-host CPU assertion branch has not run on this host (busy during QA).

### test-speed-followups

From plan test-speed (`docs/plans/test-speed/report.md`):

- Full `tests/assetgen.test.sh` wall times before and after were never measured (every full run was killed for low
  memory); measure once on a quiet machine.

### core-style-v2

Bump the six core styles under `templates/assetgen/styles/` to structured v2 (`palette.colors`, `tone`, `canvas`),
and only after a game project has real derived values from `assetgen.py style derive`. Reason: the bump changes every
core style hash, so every existing run, anchor and rejection recorded against a core style drifts
(`assetgen.py drift` reports `older-version`: the bump moves the six core styles from version 1 to version 2, and the
version is checked before the hash).

### assetgen-run-followups

Left open by the plans assetgen-hybrid, assetgen-style and assetgen-batch (review notes and lead reports, none
blocking). Plan assetgen-followups covered the rest (see Covered); what remains:

- The local SDXL, IPAdapter and ControlNet paths of plan assetgen-hybrid have never run on the target hardware:
  the owner runs `docs/plans/assetgen-hybrid/e2e-local.md` on the RTX 5060.

### agent-runtime-quirks

Seen while running plan plugin-flow-2, not reproduced yet: Codex under PowerShell resolves `bash` to WSL instead of
Git Bash (CLAUDE.md "Operating lessons": Git Bash, never WSL). Find the cause; make dispatch detect or prevent it. The
unsubmitted start prompt of the same report is covered by `factory-pipeline.py nudge` (plan runtime-quirks).

### codex-subagent-model-enforce

`orca orchestration worker-start` and `orca agent launch` take no Codex `-c` override, so a Codex dispatch cannot set
`agents.default_subagent_model`; doctor only warns (`codex-subagents`). Ask Orca for a pass-through of agent CLI
config, or write the model into the session prompt as a hard rule, and re-check doctor's reach (project
`.codex/config.toml`, active Codex profile).

### workflow-slim-followups

Follow-ups and lows from plan workflow-slim (`docs/plans/workflow-slim/report.md`):

- Tier XS is accepted only for a one-task plan. A small prose follow-up found mid-run (final-pointers) had to become
  a full task with a task lead. Consider an XS task inside a multi-task plan, reviewed and gated like the one-task form.

### plugin-flow-5-followups

Follow-ups and lows from plan plugin-flow-5 (`docs/plans/plugin-flow-5/report.md`):

- The integration QA verdict is not a clean pass on this host: `wire-parity` (Netcode `406a1b6` against server
  `633a792`) fails because the sibling repos drift. Reconcile Netcode and server before the next workspace gate.

### policy-followups-leftovers

From plans policy-followups and owner-policy (`docs/plans/policy-followups/report.md`,
`docs/plans/owner-policy/report.md`):

- Codex "Hooks need review" trust prompt: documented in `docs/codex.md`; `agents` detection still cannot see it.

### path-audit-followups

Lows and findings from plan path-audit (`docs/plans/path-audit/report.md`):

- In Git Bash, `git -C` with the Git Bash drive spelling of the workspace failed for one worker while the drive-letter
  spelling worked (not reproduced).

### session-lows-followups

Review nits from plan session-lows (`docs/plans/session-lows/report.md`):

- The `nudge` usage text overstates when `lastError` counts as no turn start; the released-worker leg of the
  LEFT BY VERIFY slot check could flag a non-verify worker released in the same checkout.
- The `tier_of` docstring still says changed lines are known only for `tier --plan`; a `--base` whose merge-base
  fails falls back to HEAD silently.
- The integration workspace check `registry paths exist in workspace` fails while the `game-authoring` checkout is
  on a branch without `assetgen/runs/` and `ui/requirements/` (seen in plan session-lows, also on main): decide
  whether empty handoff directories belong in the authoring repo or the check should skip absent ones.

## Covered

- **session-lows** (a verify run left holding its test slot, stalled and silent workers, plain `tier` line count,
  the base health line in the lead spec, the Codex runner name, the style lock dollar word, five suites run-all never
  ran): shipped in plan session-lows (`changelog.d/session-lows-dispatch.md`, `changelog.d/session-lows-tier.md`,
  `changelog.d/session-lows-defaults.md`, `changelog.d/session-lows-suites.md`).

- **flow-lows-2** (Orca lineage wait, cleanup order, concise worker rows, plan-edit and validate lows, the
  `pipeline_route.py` case map, the follow-up worker lesson, the reader guard selection; `plan_branch` was already
  fixed by `Lineage.owns`): shipped in plan flow-lows-2 (`changelog.d/flow-lows-2-orca.md`,
  `changelog.d/flow-lows-2-plan.md`, `changelog.d/flow-lows-2-guard.md`).

- **pipeline-lows** (status fields, pipeline CLI docs, dispatch and gate lows of plugin-flow-5-followups,
  policy-followups-leftovers, workflow-slim-followups and qa-reach-followups-2): shipped in plan pipeline-lows
  (`changelog.d/pipeline-lows-status.md`, `changelog.d/pipeline-lows-dispatch.md`).

- **qa-reach-followups** (qa-reach-followups except the reader-guard selection note, external-path-dollar,
  generic-explorer-name): shipped in plan qa-reach-followups (`changelog.d/qa-reach-followups-pipeline.md`,
  `changelog.d/qa-reach-followups-ci.md`, `changelog.d/external-path-dollar.md`, `changelog.d/generic-explorer-name.md`).

- **qa-reach** (pipeline-speed-followups except the reader-guard selection note; the case reach item of
  test-speed-followups): shipped in plan qa-reach (`changelog.d/qa-reach-slot-progress.md`,
  `changelog.d/qa-reach-lows.md`, `changelog.d/qa-reach-cases.md`).

- **pipeline-speed** (the pipeline start cost and the re-QA scope of test-speed-followups; run-lows-followups; the
  reader guard, guard-script spec text, `extra_model_paths.yaml`, `file:` URL host and `cd x && git -C` items of
  test-flakes-followups): shipped in plan pipeline-speed (`changelog.d/pipeline-speed.md`,
  `changelog.d/pipeline-speed-reader-guard.md`, `changelog.d/pipeline-speed-path-gaps.md`,
  `changelog.d/pipeline-speed-model-hashes.md`).

- **qa-guards** (the scoped-QA enforcement gap, the netcode prune mapping and the doctor near-duplicate of
  test-flakes-followups; the model-hash cache writer of assetgen-run-followups): shipped in plan qa-guards
  (`changelog.d/qa-guards-within.md`, `changelog.d/qa-guards-model-hashes.md`, `changelog.d/qa-guards-doctor.md`).

- **external-path-uri**, the start-prompt item of **agent-runtime-quirks** and the environment note of
  **assetgen-run-followups**: shipped in plan runtime-quirks (task external-path-uri,
  `changelog.d/external-path-uri.md`: `file:` URIs and environment-variable paths are refused in external sources;
  tasks launch-note-file and stuck-prompt-nudge, `changelog.d/launch-note-file.md` and
  `changelog.d/stuck-prompt-nudge.md`: launch notes travel through the spec file, `factory-pipeline.py nudge` finds
  and submits stuck start prompts; task quirks-docs, `changelog.d/runtime-quirks-docs.md`). Evidence for the
  environment note: the check "registry paths exist in workspace" was fixed by 6b1ba64 "shell callers convert the
  registry workspace default"; every recorded failure ran on a tree without it, and task QA in Orca terminals passes
  since.

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
  architecture doc states the tech skill count); the owner's local e2e run and the missing
  model-hash cache writer stay under assetgen-run-followups in Open (the environment note moved to the
  runtime-quirks entry above).

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
