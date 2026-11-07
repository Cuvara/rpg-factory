### Changed

- **run-all.** The shared git config check reports WARN with the `diff -u` when the only change during the run is whole added `[branch "..."]` or `[worktree]` sections (another session adding a branch or worktree). Any other change still fails: a changed or removed key, a key added inside an existing section, a duplicate of an existing section, or an added unrelated section.

### Fixed

- **run-all.** `tests/run-all.sh -j N` no longer hangs when a suite worker dies without writing its result: the scheduler records each worker's PID and grades the suite FAIL with its buffered output and the line `suite worker died without a result (pid N)`. Later suites still run and the counts stay correct (`tests/run-all-parallel.test.sh` kills a stand-in suite).
- **Tests.** `tests/git-guard.test.sh` retries a case once when it expects an advisory and the guard printed nothing, and prints a `RETRY` line with the first try's return code; empty output twice still fails, and an expected allow is never retried. The root cause of the empty output under load is not proven: the guard fails open (git probes time out after 5 s and return nothing, and internal errors are swallowed), so this is mitigated by a visible retry, not fixed at the root.
- **Tests.** `tests/ui-figma-env.test.sh` fresh-heartbeat fixtures no longer go stale on a loaded machine: they stamp the heartbeat one hour ahead (`figma_env.py` has no clock override and only treats ages over 60 s as stale); the stale case keeps its 2020 timestamp.
