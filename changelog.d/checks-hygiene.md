### Fixed

- **Checks.** `tests/facts.test.sh` grades each registry fact against the committed tree (a temporary `HEAD`
  export per repo) instead of the working tree, and prints a note when uncommitted changes would give a different
  result (untracked files included), so an uncommitted Unity `ProjectSettings` edit no longer fails
  `enter-playmode-options`. Probes run with a disposable index, so a git probe never rewrites a product repo's
  `.git/index`, and each repo is exported once per run.
- **Checks.** A timed-out check's process tree is killed even when the POSIX `ps` listing fails or is missing
  (`scripts/lib/procrun.py`); `tests/run-checks.test.sh` covers it and reaps zombies in the timeout-tree case.
- **UI.** `scripts/ui/ui_catalog.py` checks the `git cat-file --batch` and `ls-tree` return codes and guards
  truncated output: a failing read is NOT_AVAILABLE with its reason instead of a crash or a silently empty catalog.
- **Tests.** `tests/orca-commands.test.sh` checks flag values against the usage choice list and covers
  `orca orchestration worker-start --worktree new-child` and `orca worktree create --parent-worktree`.
