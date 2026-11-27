# Run report: workspace-default

Tier M plan, three tasks, on branch `workspace-default` (base `main` `38537c3`, the merge of plan ci-backlog-followups,
PR #112). It closes backlog topic `workspace-default-by-platform`.

## Summary

- One workspace default for shell and Python: `scripts/lib/workspace.sh` (`rpgf_default_workspace`) and
  `scripts/lib/workspace.py` (`default_workspace`). An explicit `RPG_FACTORY_WORKSPACE` wins; otherwise the Git Bash
  drive form on MINGW, MSYS and Cygwin, the WSL form elsewhere, and the drive-letter form for Windows Python. New
  suite `tests/workspace-default.test.sh` (task `workspace-helper`).
- Every caller uses it: `tests/run-all.sh`, `tests/routing.test.sh`, `tests/routing-properties.test.py`,
  `tests/dogfood.sh`, `tests/dogfood-codex.sh`, `scripts/checks/pin-plan.py`, `pin-status.py`, `wire-parity.sh`,
  `netcode-headless.sh`; `.claude/CLAUDE.md` describes the platform default (task `workspace-callers`).
- `gate` keeps the integration QA current when every commit after it changes only run lead files (plan, report,
  backlog), and blocks run lead files that hold machine-specific path text with the same rule as the portable-plans
  case (now one regex in `scripts/lib/plan_paths.py`). `status` agrees with the gate. `docs/pipeline-cli.md` has no
  line over 120 columns (task `gate-lead-files`).

Mode: implement

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| workspace-helper | codex gpt-6.1-terra high | claude-opus-5-5 high: QA FAIL at 8751dd2 (parity on Git Bash), then PASS | 13a5596 | 538 checks: 526 passed, 11 failed (live-workspace checks of callers not yet switched, pass with the workspace set), 1 skipped |
| gate-lead-files | codex gpt-6.1-terra high, claude-opus-5-5 high (docs) | claude-opus-5-5 high: PASS at e8b5e7d; QA FAIL at f3afbe6 (one status assertion), then PASS | 855ac57 | 532 checks: 369 passed, 1 failed (registry paths, workspace unset), 162 skipped |
| workspace-callers | codex gpt-6.1-terra high, claude-opus-5-5 high (docs) | claude-opus-5-5 high: PASS | b36a9d5 | 539 checks: 532 passed, 6 failed (live-workspace checks, worktree outside the workspace, pass with it set), 1 skipped; workspace-default 24/24, netcode-headless 20/20 |

## Incidents

- Orca crashed while two verify sessions ran. The run lead stopped their orphaned test runs by PID and restarted
  the task leads. The original gate-lead-files lead had survived, so for about two hours the task had two leads; the
  run lead stopped the duplicate (no commit, no verdict) and the original lead finished the task.
- Background runs were stopped twice by the host for low memory; specs carried a note to run one test at a time.

## Limitations

- `tests/dogfood.sh` and `tests/dogfood-codex.sh` are release-only and were reviewed by reading.
- An empty `RPG_FACTORY_WORKSPACE` now falls back to the default in the Python callers.
- Open follow-ups: `docs/plans/backlog.md` "workspace-default-followups".
- Cost: NOT_AVAILABLE (no usage reported through Orca).
