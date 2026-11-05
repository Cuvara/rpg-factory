### Added

- **Parallel run-all.** `tests/run-all.sh -j N` (`--jobs N`) runs up to N independent suites at once. Each suite's
  output is buffered and every line, inline checks included, prints in the `-j 1` order with its time; the count and
  the exit code are those of a serial run. The read-only live-workspace checks (`runl`, `block`) form a lane that runs
  one suite at a time next to the fixture suites; `run1` suites (the shared git config guard suite, the
  installed-plugin safety suite, `claude plugin validate`) wait for every queued suite and run alone. The longest
  suites start first. The default stays `-j 1`; the run ends with its wall time, and CI uses `-j 4`
  (`tests/run-all-parallel.test.sh`).
- **testlab dev tool.** Registry `dev_tools` lists `testlab` for `measure`, probed by the new `plugin-file:<path>`
  kind (a file of this plugin exists, here `testlab/testlab.py`) in `scripts/lib/devtools.py`, `check-registry.sh` and
  the registry schema (`tests/devtools.test.sh`).

### Changed

- **Faster test cycle.** `tests/parallel-policy.test.sh` builds one minimal plugin copy with a single `tar` pipe
  instead of one `cp` per file and runs its mutation lints concurrently (`PARALLEL_POLICY_JOBS`, default 4; about 11 to
  4 minutes on Windows). `tests/new-skill.test.sh` copies only the tracked and untracked files the scaffolder and
  lints read, no longer the whole checkout including `.git`. Assertions and counts are unchanged.
- **run-all.** Suites read `/dev/null` instead of the caller's stdin, the Codex packaging suite runs through the
  scheduler (so `--affected` can skip it), the live workspace checks sit together after the fixture suites, and the
  git environment isolation suite moved next to `claude plugin validate` at the end.

### Fixed

- **testlab.** `testlab/tests/test_framegc.py` now runs in run-all next to the other testlab unit tests.
- **domains test.** The base P4 regression proof drops dev tools probed by `plugin-file:`, a kind its frozen checker
  predates.
