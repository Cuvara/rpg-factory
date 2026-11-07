### Changed

- **Pipeline.** Refinements of the agent routing: `dispatch --runner print` is a preview and writes no implementer or
  reviewer model record; `agents --down` without `--reason` prints MODEL_UNAVAILABLE once; `validate` and
  `subplan validate` warn about an unexplained implementer override also for items without `kind`, against the default
  routing; a legacy subtask verdict is suppressed only by the modern record of the same subtask with the current
  fingerprint, not by a subtask id that extends it.
- **Pipeline.** The plan kind list comes from `docs/schemas/pipeline-plan.schema.json` instead of a hard-coded copy; the
  `factory-pipeline.py` docstring documents the `agents` verb and the print preview.
- **Workflow.** `factory-workflow.py dispatch` routes its agent through the pipeline routing helper (default routing,
  availability fallback) instead of reading `pipeline.default_implementer`.
