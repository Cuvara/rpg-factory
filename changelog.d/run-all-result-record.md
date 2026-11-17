### Added

- **run-all result record.** Every admitted `tests/run-all.sh` run (past the lock or slot) writes its arguments into its slot or lock directory at start
  and a JSON result record (checkout, arguments, start and end time, exit status, pass, fail and skip counts, summary
  line, failed check names and the last 40 output lines of each failure) under the persistent run-all state directory at exit, also when the wrapping command was
  stopped (INT, TERM, HUP). The newest 20 records of a checkout are kept.
- **`tests/run-all.sh --last-result [--checkout DIR]`.** Prints the newest result record of a checkout read-only, so a
  later session reads the result of a run whose terminal is gone.
- **Duplicate run guard.** A second targeted run of the same checkout with the same arguments while the first is alive
  starts no copy: it names the holder (slot, pid, winpid, started, arguments) and exits 4; with `--attach` it waits for
  the holder, prints its record and exits with its status (5 when the holder died without a record).
- **Operating lesson.** `parallel-work.md` tells sessions to check the slot directories and read the result record
  before rerunning a tier command whose wrapper is gone.

### Fixed

- **run-all double count.** At `-j 1`, a `cmd && bad X || ok Y` check whose command succeeded counted both a FAIL and
  a PASS (`_bad` without detail returned non-zero); it now counts the FAIL only.
