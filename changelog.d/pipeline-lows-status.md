### Added

- **Delivery pipeline: structured `status --json` fields.** Each task carries `lead_report` (`at`, `sha`, `summary`,
  `current`, or null without a `report` record) and `ready_for_pr` (`ready`, `missing`: the first missing reason, or
  null where no `READY_FOR_PR` note applies), and the top level carries `model_scope_widen` (the plan's widenings,
  `[]` when none), all typed in `docs/schemas/pipeline-status.schema.json`. A run lead no longer parses the task row
  notes or stderr for them; the text output and the stderr `model scope widening:` lines are unchanged.
- **Delivery pipeline docs.** `docs/pipeline-cli.md` documents the `report` verb, the `lead report:` and
  `READY_FOR_PR:` notes of `status` with their conditions, the new `status --json` fields, the `BUSY?` candidates and
  `SLOT` lines of `cleanup`, and every exit code of `scripts/orca-wait.sh`, including exit 6 when its parent process
  is gone.

### Fixed

- **Delivery pipeline: `verdict` usage text.** The usage of `factory-pipeline.py verdict` now names the `verify` phase
  (review and QA of one SHA in one call) and no longer says a subtask needs its own review: the task's verify review
  covers every subtask.
