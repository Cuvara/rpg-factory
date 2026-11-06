### Fixed

- **Timed-out check cleanup on POSIX.** In `scripts/lib/procrun.py`, the diagnostic `ps -eo pid=,pgid=` listing now
  runs in its own `try`. A missing or slow `ps` no longer skips `os.killpg`, so the process tree no longer leaks. A
  process group that is already gone (`ProcessLookupError`) now counts as killed instead of as a failed cleanup.
