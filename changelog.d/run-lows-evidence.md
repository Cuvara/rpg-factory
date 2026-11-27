### Added

- `tests/run-all.sh` names its persistent result record in its last output line, so a caller that keeps only the tail
  of a run's output can still find the FAIL blocks (`tests/run-all.sh --last-result`).

### Fixed

- `tests/parallel-policy.test.sh` prints every failing case name of the nested `tests/orca-wait.test.sh` run, not only
  its last 15 lines, and says so when the nested run fails without a FAIL line.
- `scripts/checks/netcode-headless.sh` prunes its failed-run evidence directories under the Factory state dir to the
  newest few.
