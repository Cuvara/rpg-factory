### Changed

- **`run-checks.py` grading moved to `scripts/lib/runchecks_grade.py`.** `parser_for()` and `grade()` (which parser a
  registry check uses and how its output grades) now live in the library module; `run-checks.py` imports them back,
  so its `--json` output is unchanged and the script is back under its 500-line budget.

### Added

- **Line-budget test.** `tests/line-budget.test.sh` fails when `scripts/lib/gitguard.py`, `scripts/lib/context.py` or
  `scripts/run-checks.py` reaches 500 lines, so the split-big-scripts budget cannot regress silently.
