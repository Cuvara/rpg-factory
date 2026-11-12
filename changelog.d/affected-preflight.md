### Added

- **Delivery pipeline: selected-suite pre-flight.** `dispatch --phase verify|qa` prints on stderr
  `factory-pipeline: selected N of M suites (tests/affected.py)` (N: the Affected cases suites, M: run-all's
  `--list-suites`; `selected suites: not computed (<reason>)` without a selection) and, when N is above
  `--suite-warn N` (default 40), a warning to narrow the task paths or its checks before QA. Advisory: the prompt and
  the exit code are unchanged; `--suite-warn` below 1 is a usage error (exit 2).
- **run-all: per-suite timings.** Every suite that ran records its wall seconds, exit status and case list in the
  persistent state dir's `run-all/timings.json` (JSON Lines, one line per suite; a suite run again replaces its line),
  for later estimates. A reused PASS record, a syntax line or a block is not timed, and a timings error never changes a
  count, a result line, the exit code or suite reuse.

### Fixed

- **run-all: `--affected` without a working python3.** When python3 is missing or cannot run (the Microsoft Store stub
  Git Bash finds on Windows), `tests/run-all.sh --affected` prints the reason and exits 2 before any suite, lock or
  slot, instead of silently widening to every suite. A run without `--affected` does not probe.
