# Backlog

Topics for the next plugin plans (base `main`). A topic leaves this file when a plan task covers it; the list
below says where each earlier topic went. Conventions: `docs/plans/README.md`.

When a topic becomes a plan task, its `checks` name the task's own suites or
`tests/run-all.sh --affected --base <task base> -j 2`, never a full `tests/run-all.sh`, and its acceptance never
requires a full run: the one full run of a batch is integration QA (`skills/delivery/references/delivery.md` section 10, "QA tiers").

## In plan

None.

## Open

### core-style-v2

Bump the six core styles under `templates/assetgen/styles/` to structured v2 (`palette.colors`, `tone`, `canvas`),
and only after a game project has real derived values from `assetgen.py style derive`. Reason: the bump changes every
core style hash, so every existing run, anchor and rejection recorded against a core style drifts
(`assetgen.py drift` reports `older-version`: the bump moves the six core styles from version 1 to version 2, and the
version is checked before the hash).

### external-path-uri

`stylelock.EXTERNAL_PATH` still accepts `file:` URIs (with a drive letter) and `$HOME` / `%USERPROFILE%` forms in the
`external_source` `origin` and `rights_note`. Refuse a `file:` scheme and environment-variable paths, with a test.

### review-base-topic

`review_base` for a task with no deps that was cut from the topic branch uses the plan base (`main`) and so selects
every suite. Use the topic branch as the review base. Same root: `dispatch --phase lead` for a task added late, whose
deps are all integrated, printed a worktree cut from the first dependency's old branch tip and wrote a
`<task>__stack.json` naming it; the stale record later blocked verify and the gate ("integrated before its
dependency") in plan assetgen-style until it was set aside by hand. A task whose deps are all integrated must start
from the topic and get no stack record.

### assetgen-run-followups

Left open by the plans assetgen-hybrid, assetgen-style and assetgen-batch (review notes and lead reports, none
blocking):

- Engine: strip the host from `fetch.json` entries; a preprocessor/annotator model kind for pose and depth;
  provenance for `KSamplerAdvanced` and the literal CLIP text check; the run.md `- Fit:` line and the `fit`/`raw`
  docstrings in `assetgen.py`; lint re-reads known-nodes once per template.
- Hybrid templates: the staged layout test globs only `staged-*.json`, while the hybrid and local templates have wires
  crossing unrelated nodes; `anchor_target` lint checks only `results[0]`, and the fixture
  `local/hybrid-anchor-template.json` uses `VAEDecode` where `local-8gb` wants tiled VAE.
- comfy-desktop-setup: write the model-hash cache and `hardware-profile.json` from the skill's own steps.
- Batch: in `finalize.py` the local `rows` of the `--discard-qa-fail` branch shadows the sheet `rows` parameter;
  the manifest line "Sheet: ... -> N outputs" counts cells that were discarded later; the budget counts a discarded
  output differently with and without a sheet (without one it leaves the count, with one a fully discarded sheet
  still counts as one generation): decide the rule and test it.
- Style report: the text label "selected anchor copies" and the JSON `anchors` count (one anchor selected by two
  runs counts twice); the setup heredoc of the selected-anchor regression case is not checked for its exit status.
- Docs: `docs/architecture/multi-discipline-factory.md` still says "5 tech skills".
- Environment: the check "registry paths exist in workspace" fails inside Orca agent terminals and passes in a
  direct shell and in integration QA; the workspace path resolves differently there.
- The local SDXL, IPAdapter and ControlNet paths of plan assetgen-hybrid have never run on the target hardware:
  the owner runs `docs/plans/assetgen-hybrid/e2e-local.md` on the RTX 5060.

### run-all-orphan-after-reap

When Claude Code stops a background command under memory pressure, the `tests/run-all.sh` it wrapped keeps running
and keeps its test slot, while the session believes the run is dead. In the assetgen-style and assetgen-batch runs
this produced duplicate runs of one checkout (both slots held), lost results (the log went to a closed terminal)
and reruns of 30 to 60 minutes each. Make it visible and safe: `run-all.sh` writes its result summary to the slot's
state directory so a later session can read it, a second run of the same checkout and arguments joins or refuses
instead of starting a copy, and `parallel-work.md` tells a session to check the slot's `checkout` and `winpid`
before a rerun. Related: `run-lead-waiter-reaped`.

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

- `factory-pipeline.py status` lists another coordinator's worktree (`plugin-qa-lean-qa-lean`, plan plugin-qa-lean)
  as a leftover child of `integration:plugin`; it must list only worktrees of its own plan.
- Tier XS is accepted only for a one-task plan. A small prose follow-up found mid-run (final-pointers) had to become
  a full task with a task lead. Consider an XS task inside a multi-task plan, reviewed and gated like the one-task form.
- The plain `tier -- --repo` form counts files, not changed lines; only `tier --plan` and the gate measure lines.
- `validate` warns "checks contain test suites" for every task whose `checks` name suites (single-verify rule of
  plan plugin-qa-lean), while `docs/plans/backlog.md` and `docs/plans/README.md` still tell plans to name suites in
  `checks`. Align the plan convention with the verify rule.
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

- `claude plugin validate --strict` fails on YAML frontmatter in `skills/pin-bump/SKILL.md`,
  `skills/unity-client-tech/SKILL.md` and `commands/assetgen.md` (it also fails at main, so it is not from this plan).
  Fix the frontmatter; the two run-all checks then pass.
- The registry `root_default` (a WSL drive spelling) is not converted by Windows Python (`scripts/lib/workspace.py`); with
  `RPG_FACTORY_WORKSPACE` unset, 11 workspace checks fail on Windows. Convert it like `plan_paths.py` does.
- LFS: the facts export says "LFS files stay pointers" (`tests/facts.test.sh:37,38,49`, the checks-lows changelog
  fragment), which is wrong when git-lfs is configured (`git archive` smudges, the suite is then not offline). No
  product repo has `filter=lfs` today.
- The task-lead report and READY_FOR_PR are in `status` notes, not structured fields:
  `docs/schemas/pipeline-status.schema.json` forbids extra fields (add them).
- `docs/pipeline-cli.md` lacks the `report` verb, READY_FOR_PR, the slot and BUSY? notes and orca-wait exit 6;
  `scripts/README.md` line 22 still says the waiter wakes on three message types and leaves messages unacked.
- `scripts/factory-pipeline.py:3167`: the `slot_holders` docstring omits `winpid`.
- `tests/orca-wait.test.sh` INT case SKIPs under run-all (a background job ignores SIGINT at entry), so that suite
  gets no reuse record; an orphaned waiter is detected between checks, so it can lag one wait.
- `tests/pipeline.test.sh` runs ALL cases for `factory-pipeline.py` and `pipeline_route.py` (its case map is outside
  the plan task's owned paths); `--list-suites` hides `tests/plan-paths.test.sh` until it is wired.
- Lesson: a `status` message sent to a dispatch that has already finished creates an Orca follow-up worker (two
  appeared in this run). Send lead messages only to the run (`--to run:<id>`) of a live task lead, and put context in
  the start prompt.
- Machine setup on Windows: `python3` in Git Bash is the Microsoft Store stub and `jq` was absent, which made task QA
  report NOT_RUN or fail with `jq: command not found` until a PATH shim was used. Make `doctor` name both.
- The `orca worktree set` call that follows `git worktree add` runs before Orca knows the worktree and sets nothing;
  `dispatch --phase lead` must wait for or retry until `orca worktree list` shows it.
- `dispatch --phase review` diffs `main...<sha>` in its spec. A task that merged another integrated task (here
  checks-lows, after ci-coverage) then shows nine foreign files as scope findings (a false FAIL). Use the task's
  recorded base or the integration base it merged.
- `status` still proposes `git merge --no-ff <task branch>` while the task QA is FAIL; the reviewed phase looks only at
  the review. Look at the QA verdict too (same class as the READY_FOR_PR fix of `lead-report`).
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

- Lows of `model_scope_widen` (plan owner-policy): `validate` reports a malformed entry twice (once in `validate()`,
  once through `load_for_plan`); `"model_scope_widen": null` passes `validate` while the schema requires an array;
  `status --json` prints the widening lines on stderr (`pipeline-status.schema.json` has no field for them);
  `lead_prompt` loads the policy twice.
- The git guard's english-only check inspects only absolute path tokens: a relative `git -C ../clone` from an
  unrelated directory gets no advisory.
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

### flow-lows-followups

From plan flow-lows (`docs/plans/flow-lows/report.md`):

- `scripts/lib/workspace.py` `native_abs` keeps the broad rewrite of a drive path with a `/mnt/<letter>/` segment for its other callers
  (`context.py`, `run-checks.py`); only `plan_paths.py` is guarded. Move the Git-root check into `native_abs`.
- The Git for Windows root check in `plan_paths.py` is a heuristic (last segment `Git`, or it holds `usr/bin/bash.exe`
  or `git-bash.exe`): a user directory named `Git` with a `/mnt/<letter>/` child still reads as the MSYS rewrite.
- `netcode-headless` evidence directories under the Factory state dir are never pruned.
- `tests/orca-wait.test.sh` failed one case once under memory pressure inside `tests/parallel-policy.test.sh` and passed
  two reruns; the nested output prints only its tail, so the case name was lost. Print the failing case names.

### path-audit-followups

Lows and findings from plan path-audit (`docs/plans/path-audit/report.md`):

- `MACHINE_PATH` (`scripts/lib/plan_paths.py`) does not flag a `file:` URL with a home or Users path (same as the
  existing drive form); decide whether to reject `file:` URLs, and add an explicit allowed case for an inner path
  segment named home.
- `factory-pipeline.py cleanup` lists each leftover directory twice, once with forward slashes and once with
  backslashes; normalise the path before the duplicate check.
- A test slot stays recorded for a process that was stopped by the low-memory kill (`status`: "not running", "the user
  decides"); a holder whose PID is gone could be released by the next run.
- Task QA under memory pressure: verify sessions lost their tier run five times in plans policy-followups and
  path-audit (Claude Code stops background shells of an idle session when memory is low). Write the lesson into
  `parallel-work.md`: on a loaded machine the tier command runs with `-j 1`, one task QA at a time, and a task lead
  reports NOT_RUN after one retry instead of looping.
- A new script under `scripts/checks/` met two repo conventions only in CI (the UTF-8 stdio block of
  `tests/compat.test.sh`, the workspace reader guard of `tests/workspace-default.test.sh`). Name both in
  `scripts/README.md` next to the checks list, or give `scripts/checks/` a template.
- An Orca Codex worker can start with an empty prompt and idle with no escalation (task citation-drift: about 4.5
  hours), and a Claude implementer ended its turn without sending `worker_done`. Same class as agent-runtime-quirks:
  the task lead should time out a dispatch that shows no turn start and re-dispatch it.
- In Git Bash, `git -C` with the Git Bash drive spelling of the workspace failed for one worker while the drive-letter
  spelling worked (not reproduced).
- `tests/run-all.sh` keeps no log of a run: a caller that keeps only the tail of the output loses the FAIL lines
  (integration QA had to be rerun to see one failure). Write the FAIL blocks to a file under the state dir and print
  its path in the summary.
- Under heavy load the snapshot reports a product repo as "not a git work tree" (seen once in `tests/routing.test.sh`,
  scenario "Redis servers:id -> wire-contract leads"; `git_out` in `scripts/lib/workspace.py` has a 5 s timeout). A
  timeout should be reported as a timeout, not as a missing work tree, and the scenario should retry once.
- testlab `test_lab.py` case `test_live_guard_samples_the_host_read_only_and_its_own_cpu_is_small` fails under load
  (sampler CPU 1.56 % against a 1.0 % bound); it measures the live host. Make the bound load-tolerant or skip on a
  busy machine.

## Covered

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
