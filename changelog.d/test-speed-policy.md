### Changed

- **QA policy: scoped task QA, CI as breadth gate, affected workspace checks.** Task QA now runs only the task's
  check suites, each limited to the cases the change reaches (`tests/run-all.sh --affected --base <base> --within
  <check suites> -j 1`); the suites outside the task's checks are left to CI, the breadth gate: it runs every affected
  suite on Linux and Windows per PR, and its `ci-ok` must be green before merging. Integration QA runs
  `tests/run-all.sh --workspace-only --base <plan base>`, only the workspace checks the change reaches (all of them
  without a base and in `--release`). A plan task's `checks` name the suites that test the changed behaviour (the
  precise set); the verify session may add one it finds missing and says so. Low memory: run `-j 1`, one task QA at a
  time, and a task lead reports NOT_RUN after one retry instead of looping, because verify sessions lost their tier
  run many times when Claude Code stopped background shells under low memory. Updates `delivery.md` section 10,
  `parallel-work.md`, `CLAUDE.md` and `tests/README.md`.
