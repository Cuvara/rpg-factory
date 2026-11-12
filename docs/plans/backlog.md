# Backlog

Topics for the next plugin plans (base `main`). A topic leaves this file when a plan task covers it; the list
below says where each earlier topic went. Conventions: `docs/plans/README.md`.

When a topic becomes a plan task, its `checks` name the task's own suites or
`tests/run-all.sh --affected --base <task base> -j 2`, never a full `tests/run-all.sh`, and its acceptance never
requires a full run: the one full run of a batch is integration QA (`skills/delivery/references/delivery.md` section 10, "QA tiers").

## In plan

None. Plan `plugin-flow-5` is in PR review (`docs/plans/plugin-flow-5/report.md`).

## Open

### repo-path-audit

The maintainer rule (2026-11-06): nothing the flow needs may live only on one machine.
`tests/parallel-policy.test.sh` enforces portable paths under `docs/plans/` only. Extend the audit to the rest of
the repo docs, skills and references: every machine-specific value comes from the environment or the registry
(`RPG_FACTORY_WORKSPACE`, `scripts/lib/fstate.py`), and a test fails on a hard-coded user path. Fixtures and
examples that need an absolute path use an obviously fake one. Fold in the lows of the `machine_path` pattern in
`tests/parallel-policy.test.sh`: a WSL drive mount followed by punctuation (a comma, a closing parenthesis) is not
matched, and the macOS user-home alternative also matches the path part of a URL.

### plan-edit-verb

`delivery.md` section 8 documents the rule "plan edits are atomic: write a copy, validate it, then replace the
plan". Optional follow-up: a `factory-pipeline.py plan-edit` verb (or a `validate --replace <plan>` mode) that does
the copy, validation and replace in one step, with a test that an invalid edit never replaces the plan.








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
- `skills/delivery/references/delivery.md` is 32420 of its 32768-byte cap (`tests/delivery-generic.test.sh`); the next
  policy addition needs a move to `docs/pipeline-cli.md` first.
- `tests/README.md` restates the QA tiers summary and the one-full-run rule of `delivery.md` (low).
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

### run-lead-waiter-reaped

Claude Code stopped the run lead's background waiter (`scripts/orca-wait.sh --run <id>`) twice under memory pressure
in plan workflow-slim, and the rule is not to restart it on its own. Messages then waited until the user nudged the
session. Write the lesson into `parallel-work.md` (RPG Orca notes): on every wake the run lead runs
`orca orchestration check --run <id>` and `factory-pipeline.py status` instead of relying on the waiter, and keep
fewer task leads open at once on a loaded machine.

### plan-edit-commit-guard

In plan workflow-slim the run lead committed an INVALID plan for about a minute: the commit was chained with `&&`
after `validate | grep`, so the exit code was grep's. Fold into plan-edit-verb above: the verb replaces and commits
the plan only when `validate` itself exits 0, and a test proves an invalid copy is never committed.

### plugin-flow-5-followups

Follow-ups and lows from plan plugin-flow-5 (`docs/plans/plugin-flow-5/report.md`):

- `claude plugin validate --strict` fails on YAML frontmatter in `skills/pin-bump/SKILL.md`,
  `skills/unity-client-tech/SKILL.md` and `commands/assetgen.md` (it also fails at main, so it is not from this plan).
  Fix the frontmatter; the two run-all checks then pass.
- The registry `root_default` (a WSL drive spelling) is not converted by Windows Python (`scripts/lib/workspace.py`); with
  `RPG_FACTORY_WORKSPACE` unset, 11 workspace checks fail on Windows. Convert it like `plan_paths.py` does.
- `tests/hook-perf.test.sh:101` writes `"$cf.new"` with no guard; an empty `$cf` creates `.new` in the cwd.
- LFS: the facts export says "LFS files stay pointers" (`tests/facts.test.sh:37,38,49`, the checks-lows changelog
  fragment), which is wrong when git-lfs is configured (`git archive` smudges, the suite is then not offline). No
  product repo has `filter=lfs` today.
- `scripts/lib/plan_paths.py:57`: a not-yet-existing native path with a `/mnt/<letter>/` segment is rewritten by
  `native_abs`.
- The task-lead report and READY_FOR_PR are in `status` notes, not structured fields:
  `docs/schemas/pipeline-status.schema.json` forbids extra fields (add them).
- `docs/pipeline-cli.md` lacks the `report` verb, READY_FOR_PR, the slot and BUSY? notes and orca-wait exit 6;
  `scripts/README.md` line 22 still says the waiter wakes on three message types and leaves messages unacked.
- `scripts/factory-pipeline.py:3167`: the `slot_holders` docstring omits `winpid`.
- `tests/orca-wait.test.sh` INT case SKIPs under run-all (a background job ignores SIGINT at entry), so that suite
  gets no reuse record; an orphaned waiter is detected between checks, so it can lag one wait.
- `tests/pipeline.test.sh` runs ALL cases for `factory-pipeline.py` and `pipeline_route.py` (its case map is outside
  the plan task's owned paths); `--list-suites` hides `tests/plan-paths.test.sh` until it is wired.
- `tests/git-env-isolation.test.sh` re-snapshots the git config without removing the earlier copy.
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
- `netcode-headless` (`scripts/checks/netcode-headless.sh`) failed once (1 failed, 0 passed) and passed 720/720 on an
  immediate rerun in integration QA; its cleanup removed the TRX, so the cause is unknown. Keep the failing TRX
  (or its tail) when the check fails.
- The integration QA verdict is not a clean pass on this host: `wire-parity` (Netcode `406a1b6` against server
  `633a792`) fails because the sibling repos drift. Reconcile Netcode and server before the next workspace gate.
- A QA worker's permission prompt on `rm -f $S/*.log` (a possibly-empty variable) stalls an unattended run; the QA
  spec template should use `"${S:?}"` or a literal path.

### ci-backlog-followups

From plan ci-backlog (`docs/plans/ci-backlog/report.md`):

- `tests/routing.test.sh` defaults the workspace to `/mnt/c/Workspaces/UnityIndie`, so on Git Bash for Windows it
  fails unless `RPG_FACTORY_WORKSPACE` is exported (two task QA runs failed on it). Default by platform, or skip with
  a clear message when the workspace markers are missing.
- The Windows `python3` alias line of `dispatch` does not appear when the run lead itself runs through a shim (the
  shim hides the alias), so the run lead still adds a `--note` for it. Detect the alias by probing the WindowsApps
  path, not only `shutil.which`.
- `dispatch` renders a lead's `--note` as ` --note <quoted>`; a one-word note starting with `-` is then rejected by
  argparse. Render `--note=<quoted>`.
- `tests/pipeline.test.sh` unsets `RPG_FACTORY_SESSION_NOTE` only before the new cases; unset it beside the other
  environment exports so a caller's note cannot leak into the whole suite.
- `scripts/lib/pipeline_route.py` repeats the `CODEX_HOME` resolution and TOML load of `scripts/lib/codexconfig.py`;
  reuse it.

## Covered

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
