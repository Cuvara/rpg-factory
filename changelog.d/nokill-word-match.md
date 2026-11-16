### Fixed

- **Tests.** The pipeline test's no-kill refute matches `kill`, `taskkill` and `Stop-Process` as whole words, so the
  settled-workers case no longer fails in a checkout whose path contains `skill` (status and cleanup print `next:`
  commands with the script path). `--force` is still refuted anywhere in the output.
