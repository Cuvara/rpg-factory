### Added

- **Citations.** `scripts/checks/skill-citations.py --fix` rewrites the line spec of every MOVED citation in place
  (only the digits inside the backticks; encoding and line endings are kept), and `--strict` counts MOVED as a failure.

### Changed

- **Citations.** A citation whose anchor is no longer within the cited lines +/- 3 but occurs exactly once in the
  file, or exactly once within +/- 40 lines, is now MOVED (reported with the shifted spec, exit 0) instead of FAIL.
  `tests/run-all.sh` prints MOVED citations as warnings with the `--fix` hint; `tests/run-all.sh --release` runs the
  check with `--strict`. A missing file or anchor, several far candidates, an unanchored citation and a line past the
  end still fail.
