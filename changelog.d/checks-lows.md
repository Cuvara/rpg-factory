### Fixed

- **Checks.** `tests/fixtures/run-checks-cleanup-failure.py` patches `runner.procrun.signal` (where the SIGKILL lookup
  lives) and asserts `scripts/run-checks.py` no longer carries a `signal` attribute; the unused `import signal` is gone.
- **Facts.** `tests/facts.test.sh` checks the return code of `git read-tree`: a HEAD tree that cannot be read is a FAIL
  for the fact (naming fact and repo) instead of a pass on a missing disposable index. The `git archive` HEAD export
  omits submodules (empty gitlinks) and leaves LFS-tracked files as pointers; the suite now prints one `NOTE` per repo
  with both counts and keeps grading the committed HEAD, so the suite stays offline.
- **UI catalog.** The `ls-tree` failure reason of `scripts/ui/ui_catalog.py` includes git's stderr, so an unreadable
  ref says why.
- **Pipeline.** `scripts/lib/plan_paths.py` converts Git Bash (`/c/ws`) and WSL (`/mnt/c/ws`) drive spellings in plan
  paths and in the workspace root environment variable on Windows Python; other platforms are unchanged.
- **Guard.** `scripts/lib/guard/` is renamed `scripts/lib/rpgf_guard/`, the name it was already imported under, so
  nothing called `guard` is importable from `scripts/lib`. Guard behaviour is unchanged.
