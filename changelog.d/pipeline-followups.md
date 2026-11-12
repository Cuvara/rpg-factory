### Fixed

- **Pipeline gate.** `factory-pipeline.py gate` no longer counts the run lead's `docs/plans/backlog.md` (or the
  `backlog.md` next to an in-repo plan file) as a change outside every task's owned paths: the follow-ups that
  `delivery.md` section 8 sends there in the integration commit no longer block the PR.
- **Test environment in worker specs.** When the run lead's environment sets `RPG_FACTORY_WORKSPACE`, the implement,
  verify, task QA and integration QA specs tell the worker to set it for every test run, so a worker session that does
  not inherit it (Windows) no longer fails the live suites. Unset or empty, the specs are unchanged.
- **Pipeline tests.** `tests/pipeline.test.sh` reads a dispatched spec from the prompt line only, so a quote character
  in a dispatch's stderr no longer breaks the spec check.
- **CI wording tests.** `tests/pipeline.test.sh` asserts the task QA clause of the CI wording (the verify and QA specs)
  besides the integration QA clause.
