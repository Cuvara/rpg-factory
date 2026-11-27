### Changed

- **run-all: an affected run that reaches no check is NOT_RUN (exit 6), never a pass.** With a base (`--affected`,
  `--inline-only` or `--workspace-only --base`), a run with 0 passed, 0 failed and every skip counted as not affected
  still prints `run-all: nothing the change reaches: no check ran (not affected: N)` after the summary, then
  `run-all: exit 6 = NOT_RUN: no evidence; run without --base (or with --only-suites) for a verdict`, and exits 6
  instead of 0: nothing ran, so there is no evidence to grade. The result record's exit is 6 and no suite PASS record
  is written; exit codes 0-5 keep their meaning.
