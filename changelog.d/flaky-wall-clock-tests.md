### Fixed

- **Timeout test no longer depends on machine load.** `tests/run-checks.test.sh` bounded the whole
  `run-checks.py --timeout 1` call at 8 s wall clock, which failed under two concurrent full run-all runs (8.97 s,
  10.83 s). A timed-out check's result now carries a `timeout` record measured by the runner
  (`limit_s`, `timed_out_after_s`, `killed_after_s`, `cleanup_grace_s`, `verified`; `scripts/lib/procrun.py`), and the
  test asserts that the tree was killed after the limit and within the runner's cleanup grace. A negative case keeps a
  never-killed hung child failing the bound.
- **`tests/ui-commands.test.sh` diagnostics.** The `components settings` case prints every asserted value on failure
  and no longer reads a previous case's output.
