### Fixed

- **Affected tier.** `tests/affected.py` maps the portable-paths check: `scripts/checks/portable-paths.py` is a global
  enforce line (selected for every change, like the English-only check) and `tests/portable-paths.test.sh` runs when the
  check changes, so `run-all --affected` and `scripts/ci-plan.py` no longer skip them on a docs-only or unrelated change.
- **Fixture scrub.** `tests/fixtures/failed.trx` holds obviously fake user and host names instead of the real Windows
  ones, so it needs no entry in `tests/fixtures/portable-paths-allow.txt` any more.
