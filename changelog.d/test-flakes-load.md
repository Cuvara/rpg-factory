### Fixed

- **Tests under host load.** `tests/netcode-headless.test.sh` runs its fake `dotnet` with an 8 s timeout instead of 2 s (the fake sleep mode now sleeps 20 s, so the timeout case still times out), so cases no longer fail at random with `dotnet test timed out after 2 s` on a loaded host.
- **Tests under host load.** `tests/orca-wait.test.sh`: the young-guard case no longer depends on scheduling delay, and the INT case runs under run-all (or states why it cannot).
- **Tests under host load.** `tests/routing.test.sh` retries a scenario once, and only when the snapshot failed with a git timeout; any other failure is reported at once.
- **Tests under host load.** `testlab` live host-guard test bounds the sampler's own CPU tolerant of a busy host; the read-only assertion stays.
