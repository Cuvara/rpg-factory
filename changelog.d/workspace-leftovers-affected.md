### Changed

- **Tests.** A change to `scripts/lib/workspace.sh` now selects 21 of 74 suites in `tests/run-all.sh --affected` and in
  CI (its direct callers, the suites naming them and `tests/affected.test.sh`) instead of 43 (every transitive caller
  through `factory-cmd.py`). Only selection is narrowed (`CALLER_SUITES` in `tests/affected.py`); suite reuse hashes
  keep the conservative closure.
