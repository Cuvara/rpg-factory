### Added

- **Delivery pipeline: sync of a moved dependency.** New verb `sync <plan.json> --task D [--send]`: for each stacked
  dependent whose HEAD lacks D's latest SHA (its task branch tip, else its review PASS) it prints the `git merge` the
  dependent needs (never a rebase) and records `<dependent>__sync.json`; `--send` also sends an Orca `status` message to
  the dependent's lead (`run:<task orca_run>`, else `@worktree:<id>`). `status` shows `sync: D moved to <sha>` until the
  dependent's HEAD contains the SHA, a stacked task lead merges it at each subtask boundary, and every task lead in a
  worktree repo runs `sync --send` after each new candidate. Without Orca it prints the commands and exits 0.
