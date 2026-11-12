### Added

- **asset-gen.** An advisory spend guard in the engine (before, only the skill prose limited generations).
  `assetgen.py resolve --max-outputs N` (default 4) records `spec.budget.max_outputs` in the spec; a value that is not a
  whole number of at least 1 is a usage error (exit 2) and `--out` writes nothing. The new read-only verb
  `assetgen.py budget --run <run> [--json]` (`scripts/assetgen/budget.py`) prints used versus allowed, where used is
  the run's `outputs/*.png` plus the failed attempts of its series (lower-numbered runs of the same slug without
  `run.md`), and exits 1 when used exceeds allowed or `spec.budget` is malformed (at the limit still exits 0).
  `finalize` prints the budget state as its second-to-last line and as `budget` in `--json`, without changing its exit
  code. The limit is advisory: the engine cannot stop comfy-mcp, so the asset-gen skill runs `budget` before each
  `run_workflow`. A `spec.json` resolved before this change has no budget and counts as unlimited, never as a failure.
