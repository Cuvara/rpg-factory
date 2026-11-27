# Run report: workspace-followups

Tier M plan, two tasks, on branch `workspace-followups` (base `main` `9fb910d`, the merge of plan workspace-default,
PR #115). It closes backlog topic `workspace-default-followups`.

## Summary

- The registry `workspace.root_default` is the one source of the workspace default and goes through the platform
  conversion everywhere: `scripts/lib/workspace.py` (`find_workspace`, `default_workspace(registry=...)`),
  `scripts/lib/fstate.py`, and in shell the new `rpgf_platform_path` in `scripts/lib/workspace.sh` (task
  `root-default-python`).
- Every reader uses it: `scripts/check-registry.sh`, `scripts/checks/netcode-headless.sh` (Netcode under the default
  workspace), `pin-plan.py`, `pin-status.py`, `skill-citations.py`, `scripts/factory-cmd.py`, `tests/facts.test.sh`
  and its fixture; `scripts/README.md` states the platform default. `tests/workspace-default.test.sh` fails when a
  script hard-codes the workspace literal or reads the registry default raw again (task `shell-callers`).
- Result: integration QA on Git Bash for Windows with `RPG_FACTORY_WORKSPACE` unset passes 24 of 24 checks (16 of
  22 before this plan).

Mode: implement

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| root-default-python | codex gpt-6.1-terra high | claude-opus-5-5 high: PASS | a0217a1 | 544 checks: 541 passed, 2 failed (shell readers, fixed by shell-callers), 1 skipped |
| shell-callers | codex gpt-6.1-terra high | claude-opus-5-5 high: QA FAIL at 6b1ba64 (two fixture cases, skill-citations import), then PASS | b095300 | 568 checks: 463 passed, 0 failed, 105 skipped |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | 7493036 | 24 checks: 24 passed, 0 failed, 0 skipped |

`shell-callers` grew during the run: task `root-default-python` found four more raw readers of the registry default,
and the verify needed `tests/skill-citations.test.sh` (approved scope change, plan commits on the topic branch).

## Limitations

- Open follow-ups: `docs/plans/backlog.md` "workspace-followups-leftovers".
- Cost: NOT_AVAILABLE (no usage reported through Orca).
