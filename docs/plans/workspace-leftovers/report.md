# Run report: workspace-leftovers

Tier M plan, four tasks, on branch `workspace-leftovers` (base `main` `c214747`, the merge of plan workspace-followups,
PR #116). It closes backlog topic `workspace-followups-leftovers`.

## Summary

- `scripts/lib/workspace.sh`: on Cygwin the WSL-form default maps to the `cygpath -u` answer, else the cygdrive form;
  MINGW and MSYS keep the drive form (task `cygwin-guard-tests`). `tests/workspace-default.test.sh` gained Cygwin
  cases, a negative self-test of the root_default reader guard and a fixture Netcode repo, so it no longer needs a
  real Netcode checkout.
- `gate` (and `status`) now block a run lead file on the integration HEAD with a non-English line, naming file, line
  and rule, and honour the english-only allowlist (task `gate-english`).
- `tests/affected.py`: a change to `scripts/lib/workspace.sh` selects its direct callers only: 21 of 74 suites
  instead of 43 (task `affected-workspace-lib`). The backlog's "about 55" and its stated cause did not hold.
- `scripts/checks/pin-plan.py` and `pin-status.py` load the registry through the new `scripts/lib/plugin_registry.py`,
  tested by the new suite `tests/plugin-registry.test.sh` (task `pin-loader`).

Mode: implement. Model rule (owner request): the registry profiles only, Claude Sonnet 5.5 implements and runs QA,
Claude Opus 5.5 leads and reviews; no Codex, so every review is SAME_MODEL (owner-approved).

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| cygwin-guard-tests | claude-sonnet-5-5 high | claude-opus-5-5 medium: QA FAIL at f46dd07 (guard self-flagged its fixture), then PASS; CI fix round PASS | 35c9daf | 568 checks: 426 passed, 0 failed, 142 skipped |
| gate-english | claude-sonnet-5-5 high | claude-opus-5-5 medium: PASS | d1c09b0 | 568 checks: 349 passed, 0 failed, 219 skipped |
| affected-workspace-lib | claude-sonnet-5-5 high | claude-opus-5-5 medium: PASS | f58b7c4 | 568 checks: 332 passed, 0 failed, 236 skipped |
| pin-loader | claude-sonnet-5-5 high | claude-opus-5-5 medium: QA FAIL at 631c12b (test expected lowercase booleans), then PASS | 4a2ddaf | 572 checks: 331 passed, 0 failed, 241 skipped |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | 0cb26de | 24 checks: 24 passed, 0 failed, 0 skipped |

## Limitations

- CI on PR #117 first failed in `tests/routing.test.sh` on Linux: its Cygwin self-test expected the drive form, and
  the task verify passed locally because Git Bash ships `cygpath`. Fix round: the case hides `cygpath` and expects
  the cygdrive form (plan commit gave the task `tests/routing.test.sh`).

- Open follow-ups: `docs/plans/backlog.md` "workspace-leftovers-followups".
- Cost: NOT_AVAILABLE (no usage reported through Orca).
