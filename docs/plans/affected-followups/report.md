# Run report: affected-followups

Tier M plan, one task, on branch `affected-followups` (base `main` `1826ca4`). It closes backlog topic
`affected-selection-followups`.

## Summary

- `tests/affected.py` gives a statically loaded file an importer edge from its loader
  (`spec_from_file_location(name, FILE, ...)` with a FILE that resolves to a tracked file of the repo; a computed FILE
  stays unsure). A change to `scripts/lib/rpgf_guard/__init__.py` now selects 30 of 75 suites (was 75): git-guard,
  file-guard and the other suites that reach the git guard, not changelog or release-check. Suite reuse hashes stay
  conservative. Every line of `tests/affected.py` is 120 characters or less (task `rpgf-guard-selection`).
- The two-hop callers of `scripts/lib/workspace.sh` stay as accepted in plan workspace-leftovers.

Mode: implement. Model rule (owner request): the registry profiles only, Claude Sonnet 5.5 implements, Claude Opus
5.5 leads and reviews; no Codex, so the review is SAME_MODEL (owner-approved).

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| rpgf-guard-selection | claude-sonnet-5-5 high | claude-opus-5-5 medium: PASS | dea36ab | 612 checks: 373 passed, 0 failed, 239 skipped |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | 5df3f4a | 24 checks: 24 passed, 0 failed, 0 skipped |

## Limitations

- The new loader edges also link `artifact-trace.py` to `artifact-review.py` and an asset-gen fixture to its loaded
  modules; no selection change for them.
- Cost: NOT_AVAILABLE (no usage reported through Orca).
