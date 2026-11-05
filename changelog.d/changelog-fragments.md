### Added

- **Changelog fragments.** Each change adds `changelog.d/<topic>.md` (Keep a Changelog `###` sections) instead of
  editing `CHANGELOG.md`, which conflicted in about 19 of the merges in this repository's history.
  `scripts/changelog.py` validates (`check`), previews (`preview`) and, at release, writes the `## [X.Y.Z]` section and
  removes the fragments (`release X.Y.Z [--summary TEXT]`). run-all fails when `[Unreleased]` gets a direct entry, and
  `scripts/release-check.py` requires `changelog.d/` to hold no fragment (`tests/changelog.test.sh`,
  `tests/release-check.test.sh`).
