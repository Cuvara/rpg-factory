### Added

- **asset-gen.** Review tiers for gen-runs, computed at check time only (nothing is recorded in `run.md`, `spec.json`,
  purpose files or `requirements_sha256`): `scripts/assetgen/data/review-tiers.json` makes the `icon`, `ui-element` and
  `texture-tileable` purposes light, every other purpose stays full (today's behaviour). In the light tier a missing
  `review-image-claude.json` no longer WARNs in `gen-run-claude-review`; a present file is still validated (invalid,
  stale or by another model: WARN, FAIL verdict: missing work, `run.md` differs: FAIL). A run with selected style-lock
  anchors is always full. The Codex prompt and image reviews are required in every tier.
