### Added

- **QA runner.** `tests/delivery-generic.test.sh` runs in `tests/run-all.sh` (it was in no suite list) and `tests/affected.py`
  selects it for a change under `skills/delivery/`, to `scripts/factory-pipeline.py` or to `scripts/lib/pipeline_route.py`.
  `tests/affected.test.sh` covers the selection. The `tests/plan-paths.test.sh` suite is wired the same way, but only runs
  once the file exists.
- **QA runner.** `tests/run-all.sh` counts a WARN apart: the summary reads `..., S skipped, W warned` only when `W > 0`,
  and the exit code ignores it. `tests/run-all-parallel.test.sh` checks this end to end with a config WARN.
- **Guard tests.** `tests/git-guard.test.sh` has a deterministic repro for the empty git-guard output: with no `git` on
  `PATH` the guard's git probe returns an empty string, the branch is unknown, the `commit on protected branch` advisory
  is never produced and the hook prints nothing at rc 0.

### Changed

- **QA runner.** A change to `scripts/factory-pipeline.py` or `scripts/lib/pipeline_route.py` selects only
  `tests/pipeline.test.sh`, `tests/delivery-generic.test.sh` and a suite that names the file itself, not the ~19 suites its
  import closure reaches. Only selection is narrowed; the suite-reuse hashes keep the conservative closure.
- **QA runner.** `RETRY` lines a passing suite printed (a flaky step it retried) are shown under its PASS line, at `-j 1` and
  in the `-j N` queue. They are no failure and the PASS record is published as before.
- **Guard tests.** The git-guard `RETRY` line now carries the first try's evidence: `rc`, `elapsed` in ms and the first
  300 characters of stderr. Its literal prefix is unchanged.
- **QA runner.** The py_compile and release-policy checks in `tests/run-all.sh` accept the guard package under either
  `scripts/lib/guard/` or `scripts/lib/rpgf_guard/`, and skip a glob that matches no file.

### Fixed

- **QA runner.** `tests/affected.py` no longer starts a bare `bash` for its tool-version hash: on Windows that is the WSL
  launcher. It uses `find_bash()` from `scripts/lib/shells.py`, and records `absent` when no bash is found.
- **Routing golden.** `tests/routing-golden.test.sh --update` keeps the host-dependent `absolute path (...)` scenarios the
  host cannot evaluate (the cygpath and `/mnt/c/` forms exist only on Windows) instead of deleting them. A scenario this run
  recorded takes the new record; an ordinary scenario missing from the run, or a host-dependent one no longer declared in
  `tests/routing.test.sh`, is dropped. The merge and the comparison are functions with a self-test on small fixtures.
- **QA runner.** The shared git config copy (`GITCFG_COPY`) is no longer left in the temp directory: it is removed at once
  when it could not be filled, and after a config WARN `runall_cleanup` removes it.
