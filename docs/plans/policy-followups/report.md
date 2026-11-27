# Run report: policy-followups

Tier M plan, four tasks, on branch `policy-followups` (base `main` `4356283`). It closes backlog topic
`language-policy-followups`; the open owner decisions and low findings moved to `policy-followups-leftovers`.

## Summary

- `scripts/file-guard.py` honours `path:line` entries of the english-only allowlist on Write and Edit (the line is
  recovered from the current file); `path:*` still works, and an unknown line keeps the old behaviour (task
  `file-guard-allowlist`).
- The git guard's `orca` parse skips the values of the global options `--environment` and `--pairing-code`, so the
  english-only check still sees `orchestration send` and `agent launch` text. The Agent-tool prompt check applies only
  to Agent-shaped input (string `prompt` and `description`); any other tool named Task gets no opinion.
  `tests/installed-safety.sh` has english-only cases for a commit message and an Agent prompt. The plugin-checkout
  rule (`in_scope()` in `scripts/lib/rpgf_guard/language.py`) is unchanged: its intended scope is an open owner
  question (task `git-guard-lows`).
- The `--domain` and `--graph` snapshot views print the `Language:` line (JSON: a `language` key).
  `changelog.d/language-policy.md` names the Agent prompt check, `plugin-review.md` states the full language policy,
  and `docs/codex.md` documents the Codex "Hooks need review" trust step (task `language-line-docs`).
- `factory-pipeline.py status` and `cleanup` retry `orca orchestration worker-list` without `--full` on Orca builds
  that reject it and use the concise rows; a worktree whose branch belongs to another topic is never listed as this
  plan's leftover child (task `pipeline-orca`).

Mode: implement. Model rule: the registry profiles, cross-model. Codex gpt-6.1-terra implements, Claude Opus 5.5 leads
and reviews, Claude Sonnet 5.5 runs QA where the verify session's own run was lost.

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| file-guard-allowlist | codex gpt-6.1-terra | claude-opus-5-5 medium: PASS | ed4d15b | 613 checks: 396 passed, 0 failed, 217 skipped |
| git-guard-lows | codex gpt-6.1-terra high | claude-opus-5-5 medium: PASS; QA rerun by the task lead | f4afcad | 613 checks: 371 passed, 0 failed, 242 skipped |
| language-line-docs | claude-sonnet-5-5 high (docs), codex gpt-6.1-terra high (views) | claude-opus-5-5 medium review PASS; claude-sonnet-5-5 QA PASS | 1c1eb4c | 618 checks: 505 passed, 0 failed, 113 skipped |
| pipeline-orca | codex gpt-6.1-terra high | first QA FAIL at 97321d4 (fixture), claude-opus-5-5 medium: PASS at fab63d2 | fab63d2 | 613 checks: 376 passed, 0 failed, 237 skipped |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | 4b5c2ad | 24 checks: 24 passed, 0 failed, 0 skipped |

## Limitations

- `tests/installed-safety.sh` is NOT_RUN (it targets the installed plugin; releases only); `bash -n` passed.
- Three verify sessions lost their tier run to Claude Code's low-memory kill; each was rerun in a fresh session or by
  the task lead, and the orphaned run-all processes were stopped by their own PID.
- `docs/codex.md` line 75 is one long line (cosmetic).
- `pipeline-orca` lows (recorded in the backlog): the `<topic>-` prefix also matches a topic that extends this one;
  `codex/<topic>` is not matched by lineage; the concise-row settledness note can over-count.
- Cost: NOT_AVAILABLE (no usage reported through Orca).
