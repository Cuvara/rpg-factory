### Changed

- **Pipeline: task QA is scoped.** The verify and QA specs name `tests/run-all.sh --affected --base <review base>
  --within <check suites> -j 1`: only the suites the plan's checks name run, each with its affected cases, and the rest
  of the selection is left to CI. Integration QA names `tests/run-all.sh --workspace-only --base <plan base>`, which runs
  only the workspace checks the change reaches. The stderr selection line reports the scoped count and the suites left
  to CI.
- **Pipeline: `validate` asks checks to name the suites that test the changed behaviour.** The warning that checks
  contain test suites is replaced by that rule.
- **Tests: `tests/pipeline.test.sh` starts fewer processes.** It loads `scripts/factory-pipeline.py` from a bytecode
  cache under its temp dir, reuses repeated dispatch runs and runs stdout and stderr checks in one process; every
  assertion is kept. Its case map still selects every case for a change to `scripts/factory-pipeline.py`, because
  every case runs it.
