# Run report: language-policy

Tier M plan, one task, on branch `fix/core/language-policy` (base `main` `38537c3`, the merge of plan
ci-backlog-followups, PR #112).

## Summary

Verified failure (2026-11-13): a run lead wrote a harness plan-mode plan file in the owner's language. The
`english-only` rule named only code, comments, docs, changelogs and commit messages, the snapshot printed only the
rule id, and nothing looked at what a session writes. Task `policy` closes that:

- Registry: `workspace.report_language` and `workspace.language_allow`; `english-only` now names everything written
  (plans including the harness plan-mode file, briefs and specs, inter-agent messages, artifacts, memory files) and
  leaves only the report to the owner in the report language.
- Every snapshot and every dispatched spec prints a `Language:` line.
- `scripts/file-guard.py` warns on a Write or Edit of non-English text into a governed path; the git guard warns on
  the text of `git commit -m`, `gh pr` and `gh issue` titles and bodies, `orca orchestration send`,
  `orca agent launch --prompt` and Agent-tool prompts. Advisory only.
- The detection moved to `scripts/lib/english.py`, shared with `scripts/checks/english-only.py`.

Mode: implement

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| policy | claude-sonnet-5-5 high, seven sessions (six subtasks, one fix) | claude-opus-5-5 medium: FAIL at review on `3900a42` (the routing-golden assertion stripped every LF), PASS on `2afcf48`; SAME_MODEL | 2afcf48 | 539 checks: 537 passed, 0 failed, 2 skipped |
| integration | - | claude-opus-5-5 medium, `tests/run-all.sh --workspace-only` | see the gate output of the PR | 24 checks: 23 passed, 0 failed, 1 skipped (pin-status: user changes in the client pins) |

Task lead: claude-opus-5-5 medium, Orca Run `run_dfeaffdf392c`. Run lead Orca Run `run_cdc66a37215d`.

## Limitations

- Review is SAME_MODEL (Opus reviewed Sonnet). Every Codex session, implement and verify, stopped at the Codex
  "Hooks need review" trust prompt (Orca: `agent-hooks-review-prompt`); nobody trusted the hooks on the owner's
  behalf. Codex was marked down for the run and the gate ran with `--allow-same-model`.
- The owner's decision that implement sessions run on Claude Opus arrived after all seven Sonnet sessions had
  finished; none was redone.
- The plan was edited after verify: `scripts/lib/rpgf_guard/language.py` and `scripts/lib/rpgf_guard/runtime.py`
  joined the task's owned paths (`scripts/lib/gitguard.py` is only a facade over `rpgf_guard`). The reviewer had read
  and accepted both files at `2afcf48`; the verify verdict was recorded again for the new task fingerprint from the
  same report, and no test was run again for that.
- The Agent-prompt check exists for Claude only; Codex has no Agent tool event.
- Hooks stay advisory: a session can still write non-English text after the warning.
- Cost: NOT_AVAILABLE (no usage reported through Orca).

## Follow-ups

Backlog topic `language-policy-followups` in `docs/plans/backlog.md`.
