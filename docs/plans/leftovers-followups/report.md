# Run report: leftovers-followups

Tier M plan, three tasks, on branch `leftovers-followups` (base `main` `3396c00`). It closes backlog topic
`workspace-leftovers-followups`.

## Summary

- `gate` looks the english-only allowlist up with the exact tree path, so a mixed-case run lead file entry matches on
  Windows as it does in CI (task `gate-allowlist-case`).
- `tests/affected.py` resolves the plugin's static `sys.path` idiom and the static `spec_from_file_location` loader of
  the git guard: a change to `scripts/lib/workspace.py` selects 55 of 75 suites (was 75), `scripts/lib/fstate.py` 50
  (was 75). Computed entries, `import_module` and `__import__` stay unsure; suite reuse hashes keep the old rule. The
  hash fixture checks of `tests/affected.test.sh`, which silently did not run on main, run again (task
  `affected-syspath`).
- `tests/workspace-default.test.sh` passes with a drive-form `TMPDIR` (82 of 82; 77 before) and with a POSIX one;
  `tests/README.md` lists `tests/plugin-registry.test.sh` (task `tmpdir-readme`).
- The two-hop callers of `scripts/lib/workspace.sh` stay as accepted in plan workspace-leftovers.

Mode: implement. Model rule (owner request): the registry profiles only, Claude Sonnet 5.5 implements, Claude Opus
5.5 leads and reviews; no Codex, so every review is SAME_MODEL (owner-approved).

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| gate-allowlist-case | claude-sonnet-5-5 high | claude-opus-5-5 medium: PASS | ad438d5 | 573 checks: 347 passed, 0 failed, 226 skipped |
| affected-syspath | claude-sonnet-5-5 high | claude-opus-5-5 medium: QA FAIL at 4858b07 (stale case, fixture checks not running), then PASS | ac4460b | 573 checks: 332 passed, 0 failed, 241 skipped |
| tmpdir-readme | claude-sonnet-5-5 high | claude-opus-5-5 medium: PASS | 29d6d93 | 573 checks: 336 passed, 0 failed |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | c14a367 | 24 checks: 24 passed, 0 failed, 0 skipped |

## Limitations

- Open follow-ups: `docs/plans/backlog.md` "affected-selection-followups".
- Cost: NOT_AVAILABLE (no usage reported through Orca).
