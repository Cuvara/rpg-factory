### Added

- **`tests/run-all.sh --workspace-only`.** Runs only what CI cannot run: the live-workspace suites and checks
  (facts, live pin status, skill citations, routing history replay, `claude plugin validate`), with the suite reuse.
- **`-h` / `--help`.** `tests/run-all.sh` prints its usage header and exits 0. An unknown argument exits 2 with the
  usage header and never starts a run.

### Changed

- **CI is the full-suite gate.** Integration QA before the PR is `tests/run-all.sh --workspace-only`; after the PR
  opens, CI green (`gh pr checks <pr> --watch`) is the merge gate; no full local run before a PR.
  `dispatch --task integration:<repo> --phase qa` prints `--workspace-only` for the plugin repo, `gate` prints the CI watch with the PR commands, and registry
  `pipeline.qa_tiers` integration is `ci+workspace`. The full
  `tests/run-all.sh --release` and `tests/dogfood.sh --installed` run only for releases. While CI runs, start the next
  task (`.claude/CLAUDE.md`, `parallel-work.md` section 10 "QA tiers").
- **Lead worktree.** `dispatch --phase lead` creates a new task worktree with
  `git worktree add --no-track -b <branch> <path> <base>` and starts the lead with
  `orca agent launch --worktree path:<path>`: `orca worktree create` writes `branch.<name>.base` into the shared
  `.git/config`, which breaks other sessions' full runs (`parallel-work.md` section 4).
- **Cleanup after the PR merges.** `parallel-work.md` section 8 adds the after-merge step: once the integration PR
  is merged into main, the run lead removes the integration checkout or worktree (not the main checkout), deletes
  every merged task branch and the integration branch locally (`git branch -d`) and on origin
  (`git push origin --delete <branch>`, only branches of this plan that main contains), releases every worker and
  starts the next plan from main. The run lead passes `factory-pipeline.py cleanup plan.json --after-merge` once the
  PR is merged: it lists these commands and reports CLEAN only when none is left (a plan `repos` path that no longer
  exists is LEFTOVER; the path must point at the main checkout).
