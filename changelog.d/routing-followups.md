### Changed

- The plan kind list comes from `docs/schemas/pipeline-plan.schema.json` instead of a hard-coded copy; the `factory-pipeline.py` docstring documents the `agents` verb.

### Fixed

- `dispatch --runner print` is a preview: it no longer writes an implementer or reviewer model record.
- `agents --down` without `--reason` prints MODEL_UNAVAILABLE once instead of `MODEL_UNAVAILABLE: MODEL_UNAVAILABLE`.
- `validate` and `subplan validate` warn about an unexplained implementer override also for items without `kind`, against the default routing.
- A legacy subtask verdict is suppressed only by the modern record of the same subtask with the current fingerprint, not by a subtask id that extends it.
- `factory-workflow.py dispatch` routes its agent through the pipeline routing helper (kind routing, default, availability fallback) instead of reading `pipeline.default_implementer`.
