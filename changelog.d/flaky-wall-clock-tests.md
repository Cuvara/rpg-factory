### Fixed

- **Timeout test no longer depends on machine load.** `tests/run-checks.test.sh` bounded the whole
  `run-checks.py --timeout 1` call at 8 s wall clock, which failed under two concurrent full run-all runs (8.97 s,
  10.83 s). A timed-out check's result now carries a `timeout` record measured by the runner
  (`limit_s`, `timed_out_after_s`, `killed_after_s`, `cleanup_grace_s`, `verified`; `scripts/lib/procrun.py`), and the
  test asserts that the tree was killed after the limit and within the runner's cleanup grace. A negative case keeps a
  never-killed hung child failing the bound.
- **`tests/ui-commands.test.sh` diagnostics.** The `components settings` case prints every asserted value on failure
  and no longer reads a previous case's output.
- **Remaining load-sensitive tests.** The Windows grandchild probe in `tests/run-checks.test.sh` no longer takes a
  reused PID for a survivor: a live process at that PID counts only when it started no later than the check's own
  post-spawn timestamp, and the probe prints the tasklist row and both times on failure (a live grandchild still
  fails). `tests/session-state.test.sh` checks the file-lock retries on a fake clock instead of real elapsed time,
  and `tests/run-all-parallel.test.sh` relies on overlap evidence instead of comparing `-j 3` and `-j 1` wall time.
- **Timeout tree check under load.** When bash needs more than the 1 s limit to reach `echo $!`, the check is killed
  before it writes `child.pid` (seen in 6 of 90 runs under a process-spawn storm). The test now accepts that case when
  the runner's own record verifies the whole tree is gone, and still fails without a verified record. Every
  `t-timeout-tree` failure now prints the result's state, reason, exit, duration, timeout record and output tail
  (or the raw output head when there is no result).
- **`run-checks.py` bash flavor probe.** On Windows, a `uname` probe that fails to start or exits non-zero no longer makes
  the flavor `unknown` at once (that BLOCKs every check of the run). The probe now runs up to 3 times, and a probe that
  ran keeps its answer. The "cannot be resolved" BLOCKED reason now names what is missing (workspace, workspace path,
  checkout path, HEAD), the selected bash, its flavor and each probe answer. A timeout reason no longer repeats
  `cleanup=`.
