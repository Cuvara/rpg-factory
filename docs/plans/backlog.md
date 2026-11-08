# Backlog

Topics for the next plugin plans (base `main`). A topic leaves this file when a plan task covers it; the list
below says where each earlier topic went. Conventions: `docs/plans/README.md`.

When a topic becomes a plan task, its `checks` name the task's own suites or
`tests/run-all.sh --affected --base <task base> -j 2`, never a full `tests/run-all.sh`, and its acceptance never
requires a full run: the one full run of a batch is integration QA (`parallel-work.md` section 10, "QA tiers").

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

`parallel-work.md` section 8 documents the rule "plan edits are atomic: write a copy, validate it, then replace the
plan". Optional follow-up: a `factory-pipeline.py plan-edit` verb (or a `validate --replace <plan>` mode) that does
the copy, validation and replace in one step, with a test that an invalid edit never replaces the plan.

### model-unavailable-probe

agent-routing marks a model down by hand (`factory-pipeline.py agents <plan> --down <model> --reason <text>`).
Optional: a failed dispatch whose terminal shows a 401 or a 5xx from the model gateway is reported as
`MODEL_UNAVAILABLE` and marks the model down for the run, instead of being a task failure.

### guard-package-rename

`scripts/lib/gitguard.py` loads `scripts/lib/guard/` by path under the name `rpgf_guard` (guard-polish), but
`importlib.util.find_spec("guard")` still resolves the directory when `scripts/lib` is on `sys.path`. Rename the
directory to `scripts/lib/rpgf_guard/` (low).

### run-all-robust-lows

Lows from the run-all-robust review and QA (plan plugin-flow-2):

- The shared git config check keeps its `GITCFG_COPY` temp file on the WARN path (`tests/run-all.sh`, the
  "shared git config" block; `scripts/lib/gitcfg-guard.sh` removes it only when the config is unchanged).
- No end-to-end test of the config WARN wiring in `tests/run-all.sh`, and a config WARN is not counted in the summary.
- `RETRY` lines from `tests/git-guard.test.sh` are hidden when the suite passes.
- The root cause of the empty git-guard output under load is unproven (5 s probe timeouts fail open); the suite
  only retries the case once.

### checks-hygiene-lows

Lows from the checks-hygiene review and QA (plan plugin-flow-2):

- `tests/fixtures/run-checks-cleanup-failure.py` patches `runner.signal`; patch `runner.procrun.signal`, then drop
  the unused `import signal` in `scripts/run-checks.py`.
- `tests/facts.test.sh` does not check the return code of `git read-tree` into the disposable index.
- The `scripts/ui/ui_catalog.py` reason for a failed `git ls-tree` omits git's stderr.
- The facts suite exports each repo with `git archive`, which skips submodules and LFS content.

### orca-wait-lows

Lows from the work-state-in-repo review and QA of `scripts/orca-wait.sh`: a stale `.acquire` guard after a SIGKILL;
the failure tail shows only keepalives; no tests for an interrupt (INT) or a batch that mixes heartbeats with a real
message; heartbeats pile up unacknowledged between wakes.

### plan-paths-native

`scripts/lib/plan_paths.py` joins the workspace root from the environment with `os.path.abspath` only; a root in a
Git Bash or WSL drive spelling is not converted to the native form Windows Python needs (low, from the
work-state-in-repo review).

### implementer-refusal-scope

`verdict --implementer` on a task-level review is refused only when it conflicts with the task-level implementer
record; it does not check the subtask implementer records that `review_implementer` would otherwise use
(`scripts/factory-pipeline.py`, `verdict`). Check them too (low, from the gate-multiwave review).

### agent-runtime-quirks

Seen while running plan plugin-flow-2, not reproduced yet: a Codex session's start prompt sometimes stays
unsubmitted in its terminal, and Codex under PowerShell resolves `bash` to WSL instead of Git Bash (CLAUDE.md
"Operating lessons": Git Bash, never WSL). Find the cause; make dispatch detect or prevent each one.

## Covered

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
  `scripts/README.md`, `merge --no-ff` for later waves and the `verdict` options in `parallel-work.md`): plan
  plugin-flow-2 task wave-close.
