### Fixed

- `tests/affected.py` no longer selects every suite for a `scripts/assetgen/*.py` change: a leaf file that only a suite's EXTRA patterns cover (`tests/fixtures/assetgen/*` for `tests/assetgen.test.sh`, run under a computed name) now counts as named by that suite, so `reaches()` is not unsure for it and the selection is the short list of suites that mention the path. A leaf that no suite names or covers is still unsure.
