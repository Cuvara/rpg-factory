### Changed

- **docs: integration QA treats run-all exit 6 as NOT_RUN and falls back to the no-base run.** `delivery.md` (section
  10 "QA tiers", row Integration QA), `parallel-work.md` ("Integration QA is scoped too") and `docs/pipeline-cli.md`
  (integration QA paragraph) now say that exit 6 from `tests/run-all.sh --workspace-only --base <plan base>`
  (nothing the change reaches) is NOT_RUN, never a pass, and that integration QA then runs
  `tests/run-all.sh --workspace-only` without a base and grades that run, as the integration QA spec of
  `factory-pipeline.py dispatch` already says.
