### Fixed

- **CI plan.** `scripts/ci-plan.py` now passes the base it resolved to `tests/affected.py cases --base <base>`, so a
  pull request's CI matrix gets the per-symbol case reach whenever the base is usable, instead of file-level cases
  whenever the changed list differed from affected.py's default-base changed set. Every full-plan fallback is
  unchanged (no base, an all-zero or unknown base, a failing affected.py), and `--changed-file` without a base still
  calls `cases` without `--base` (file-level). New cases in `tests/ci-plan.test.sh` use a stand-in affected.py.
