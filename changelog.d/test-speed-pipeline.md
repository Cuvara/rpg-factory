### Changed

- **Pipeline: task QA is scoped.** The verify and QA specs name `tests/run-all.sh --affected --base <review base>
  --within <check suites> -j 1`: only the suites the plan's checks name run, each with its affected cases, and the rest
  of the selection is left to CI. Integration QA names `tests/run-all.sh --workspace-only --base <plan base>`, which runs
  only the workspace checks the change reaches. The stderr selection line reports the scoped count and the suites left
  to CI.
- **Pipeline: `validate` asks checks to name the suites that test the changed behaviour.** The warning that checks
  contain test suites is replaced by that rule.
- **Tests: `tests/pipeline.test.sh` is faster with a narrower case map.** Every assertion is kept; a change to
  `scripts/factory-pipeline.py` no longer always selects every case when a narrower group is safe.
