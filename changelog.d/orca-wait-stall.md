### Fixed

- **Orca wait.** `scripts/orca-wait.sh --stall-ms 0` reported every active worker as a frozen stall on the first poll
  (exit 5) instead of disabling the frozen-output check. 0 now disables that check only: provider-error stalls are
  still reported, and `--stall-poll-ms 0` still disables the whole worker poll. The usage line says what 0 does for
  each option. Covered by `tests/orca-wait.test.sh`.
