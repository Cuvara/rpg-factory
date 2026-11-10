### Fixed

- **Pipeline: cleanup.** `cleanup` reports a leftover task directory (empty or not), an Orca record of a removed worktree and a prunable git worktree record as LEFTOVER, never CLEAN, with `git worktree prune` and `orca worktree rm --worktree path:<dir>`; a plain git task worktree is removed with `git worktree remove` (no `--force`). A directory Windows reports busy is named (PID, command) and never killed. `delivery.md` section 8 records the cleanup rules and section 4 names `orca worktree set` as the only lineage step (no live session or process may use a task worktree when it is removed).
- **Tests: affected.** `tests/affected.py` maps `agents/*` to `tests/skills-lint.sh`, so `run-all --affected` and suite reuse no longer skip the agent lint when only an agent file changes.
- **Docs: README.** The doctor row lists the dev-tool state WARN next to OK / DOWN / MISSING.
