### Added

- **Delivery.** `skills/delivery/references/delivery.md` section 8 has a new subsection "In-session subagents": a
  subagent is a read-only scout, never a writer, a review or a QA verdict. It holds the per-role table (access, when,
  max parallel, limits; the data lives in registry `pipeline.subagents`), the default subagent model (Claude Sonnet 5.5
  through `rpg-factory:factory-explorer`; Codex uses the `pipeline.subagents` codex model) and the general rules. The
  canonical sentence sits under the marker `policy:subagents-read-only`, and `tests/parallel-policy.test.sh` checks
  it (marker deleted, duplicated or changed).

### Fixed

- **Tests.** The marker, which-model, qa-tiers and Orca-first checks in `tests/parallel-policy.test.sh` now read
  `skills/delivery/references/delivery.md`, where the generic policy moved; the lint-driven mutations stay on
  `parallel-work.md`.
