# Backlog

Topics for the next plugin plans (base `main`). A topic leaves this file when a plan task covers it; the list
below says where each earlier topic went. Conventions: `docs/plans/README.md`.

## Open

### repo-path-audit

The maintainer rule (2026-11-06): nothing the flow needs may live only on one machine.
`tests/parallel-policy.test.sh` enforces portable paths under `docs/plans/` only. Extend the audit to the rest of
the repo docs, skills and references: every machine-specific value comes from the environment or the registry
(`RPG_FACTORY_WORKSPACE`, `scripts/lib/fstate.py`), and a test fails on a hard-coded user path. Fixtures and
examples that need an absolute path use an obviously fake one.

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
  atomic plan edits): plan plugin-flow-2 task work-state-in-repo.
- **run-all-robust** (`run-all -j` hang on a dead suite, `tests/git-guard.test.sh` empty-output flake under load,
  shared `.git/config` changes by other sessions): plan plugin-flow-2 task run-all-robust.
- **Facts probe of the committed tree** (an uncommitted Unity `EditorSettings.asset` change failed
  `enter-playmode-options`): plan plugin-flow-2 task checks-hygiene.
- **Gate and status on multi-wave plans**: plan plugin-flow-2 task gate-multiwave.
