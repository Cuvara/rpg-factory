# Run report: ci-backlog

Tier M plan, three tasks, on branch `ci-backlog` (base `main` `c1c0902`, the merge of plan ci-followups, PR #107).
It closes backlog topic `ci-matrix-followups` and the Codex availability item of `plugin-flow-5-followups`.

## Summary

- `skills/delivery/references/delivery.md` trimmed from 32556 to 31186 bytes (1582 under its 32 KiB cap), with every
  policy block and pinned phrase kept (task `delivery-trim`).
- `factory-pipeline.py dispatch --note TEXT` (repeatable) and `RPG_FACTORY_SESSION_NOTE` append `Session note:` lines
  to every spec it writes; the lead spec passes them on. On Windows, when `python3` resolves to the Microsoft Store
  alias, specs tell the session to run the interpreter that runs `dispatch` (task `dispatch-notes`).
- `scripts/lib/pipeline_route.py` treats Codex as available when its `config.toml` selects a non-OpenAI
  `model_provider` with a `base_url`, or when `OPENAI_API_KEY` is set, even if Orca shows no Codex login. Before
  this, a Codex CLI on an API provider counted as unavailable and every review fell back to SAME_MODEL (task
  `codex-detect`).

Mode: implement

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| delivery-trim | claude-opus-5-5 high | codex gpt-6.1-sol high: review PASS, QA FAIL (routing.test.sh, workspace variable unset); rerun with the workspace: PASS | b548a01 | 530 checks: 321 passed, 0 failed, 209 skipped |
| dispatch-notes | codex gpt-6.1-terra high | claude-opus-5-5 high: review FAIL (a new helper shadowed `session_lines`: TypeError on every spec dispatch), then PASS on the fix | 3e11eba | 530 checks: 318 passed, 0 failed, 212 skipped |
| codex-detect | codex gpt-6.1-terra high | claude-opus-5-5 high: PASS | df9c6e3 | 530 checks: 311 passed, 0 failed, 219 skipped |

Codex was enabled with `RPG_FACTORY_AGENTS=claude,codex` while `codex-detect` was in progress; from then on every
review is cross-model. After `codex-detect` the pipeline routes Codex on this machine without the override.

## Limitations

- `tomllib` needs Python 3.11 or newer; older Python ignores the Codex config (`OPENAI_API_KEY` still counts).
- Open follow-ups are in `docs/plans/backlog.md` "ci-backlog-followups".
- Cost: NOT_AVAILABLE (no usage reported through Orca).
