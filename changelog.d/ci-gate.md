### Added

- **`tests/run-all.sh --workspace-only`.** Runs only what CI cannot run: the live-workspace suites and checks
  (facts, live pin status, skill citations, routing history replay, `claude plugin validate`), with the suite reuse.
- **`-h` / `--help`.** `tests/run-all.sh` prints its usage header and exits 0. An unknown argument exits 2 with the
  usage header and never starts a run.

### Changed

- **CI is the full-suite gate.** Integration QA is now `tests/run-all.sh --workspace-only` plus
  `gh pr checks <pr> --watch` (CI green); no full local run before a PR. `dispatch --task integration:<repo> --phase qa`
  prints both commands for the plugin repo, and registry `pipeline.qa_tiers` integration is `ci+workspace`. The full
  `tests/run-all.sh --release` and `tests/dogfood.sh --installed` run only for releases. While CI runs, start the next
  task (`.claude/CLAUDE.md`, `parallel-work.md` section 10 "QA tiers").
- **Lead worktree.** `dispatch --phase lead` creates a new task worktree with
  `git worktree add --no-track -b <branch> <path> <base>` and starts the lead with
  `orca agent launch --worktree path:<path>`: `orca worktree create` writes `branch.<name>.base` into the shared
  `.git/config`, which breaks other sessions' full runs (`parallel-work.md` section 4).
