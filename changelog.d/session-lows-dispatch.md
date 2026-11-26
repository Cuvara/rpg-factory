### Fixed

- **Pipeline.** A released verify session could leave its `tests/run-all.sh` alive, holding a machine-wide test slot
  for hours. The verify spec that `dispatch --phase verify` writes now ends with a fixed rule: before any verdict or
  report the session stops every run it started by that PID (`kill <pid>`; Windows Git Bash
  `taskkill //PID <winpid> //T //F`), never by pattern, then confirms its slot is free (no directory under the
  resolved `locks/run-all-slots/` names its checkout, or `status <plan>` prints no `Slots:` line for it); a slot still
  held is QA NOT_RUN or BLOCKED, never PASS.

### Changed

- **Pipeline.** `status <plan>` flags a test slot left by a verify dispatch: a slot whose holder is alive (or cannot
  be checked) in a task worktree of the plan (or one of its children) after that task's verify reported (a `qa`
  verdict, or a `review` FAIL, of the task or a subtask, recorded at or after the slot's start) or a worker of the
  task's Orca Run in that checkout was released. It prints `Slots: LEFT BY VERIFY ...` with the slot, PID, checkout,
  what reported or was released and when, and the stop command for that PID only, adds a note on the task row and
  puts the command first in `next`. Status stays read-only: it never runs the command, and it reuses its one
  `worker-list` call. With `--json` the flag is a stderr line only (the schema's slot entries take no extra field).

### Added

- **Pipeline.** `nudge <plan>` also lists STALLED Orca workers of the task leads' Runs (task `orca_run`, or the new
  repeatable `--orca-run RUN_ID`): a running worker whose agent terminal has been silent for at least `--stall` seconds
  (default 900) and that no human prompt holds (`observation.agentWait`) prints
  `<run>  <dispatch>  idle <n>s  STALLED  no turn start` (its dispatch input ended `turn_unobserved`) or
  `... turn ended without worker_done`, followed by re-dispatch advice (read the terminal, `worker-stop`, dispatch a
  fresh session with the same phase, `worker-release`). Settled or released workers are skipped, a recently active one
  is `ok  active`, missing data is no opinion. The check is read-only: `--send` still applies only to an unsubmitted
  start prompt, nothing is written for a STALLED row and the exit code is unchanged.
