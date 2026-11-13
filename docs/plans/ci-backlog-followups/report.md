# Run report: ci-backlog-followups

Tier M plan, three tasks, on branch `ci-backlog-followups` (base `main` `a869ff8`, the merge of plan ci-backlog,
PR #111). It closes backlog topic `ci-backlog-followups`.

## Summary

- `tests/routing.test.sh` defaults the workspace by platform when `RPG_FACTORY_WORKSPACE` is unset: the Git Bash
  drive form on Git Bash (MINGW, MSYS, Cygwin), the WSL form elsewhere; an explicit value wins (task `routing-workspace`).
- `factory-pipeline.py dispatch` prints the Windows `python3` Store-alias line also when `python3` on PATH is a shim:
  on win32 it probes `python3.exe` in the per-user WindowsApps folder directly (task `alias-probe`).
- `scripts/lib/pipeline_route.py` reads the Codex config through `scripts/lib/codexconfig.py` (`config_path()`,
  `config()`); availability and its reasons are unchanged (task `codex-config-reuse`, which also aligned the alias
  wording in `docs/pipeline-cli.md` and `changelog.d/dispatch-notes.md`).

Mode: implement

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| routing-workspace | claude-opus-5-5 high | codex gpt-6.1-sol high: PASS | f206b99 | 531 checks: 315 passed, 0 failed, 216 skipped; routing.test.sh 129/129 without `RPG_FACTORY_WORKSPACE` |
| alias-probe | codex gpt-6.1-terra high | claude-opus-5-5 high: PASS | 247a4dc | 531 checks: 315 passed, 0 failed, 216 skipped |
| codex-config-reuse | codex gpt-6.1-terra high (reuse), claude-opus-5-5 high (wording) | claude-opus-5-5 high: PASS | 652e6ee | pipeline and delivery-generic PASS |
| integration | - | run lead, `tests/run-all.sh --workspace-only` | 7daa4fd | 24 checks: 24 passed, 0 failed, 0 skipped |

## Limitations

- The wording subtask of `codex-config-reuse` was implemented and reviewed by Claude (text only).
- The WSL default of `routing.test.sh` is covered only by a stubbed-platform test.
- Other scripts still default the workspace to the WSL form: backlog topic `workspace-default-by-platform`.
- Cost: NOT_AVAILABLE (no usage reported through Orca).
