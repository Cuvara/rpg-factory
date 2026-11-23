### Added

- **Pipeline.** `factory-pipeline.py nudge <plan.json> [--task ID] [--idle SECONDS] [--send]` finds a session whose start
  prompt stayed unsubmitted in its Orca terminal (a verify session once sat idle for about 30 minutes until the run lead
  pressed Enter). For each task with a live worktree it lists the Orca terminals of that worktree and marks one `STUCK`
  only when its screen still shows `Read your task spec at <a spec file of this plan>` (also when Orca wraps the line),
  it has had no output for the idle time (default 120 seconds), and the task made no commit, report or verdict since
  that spec file was written. Without `--send` it prints one row per terminal and the exact `orca terminal send`
  command; with `--send` it sends one carriage return per stuck terminal and records it in `<task>__nudge.json`. A spec
  that was already nudged is never sent again and is reported as `nudged, still stuck: relaunch the session`; `status`
  then shows a `stuck?` note on that task until it makes progress. Without Orca the verb prints a note and exits 0.
