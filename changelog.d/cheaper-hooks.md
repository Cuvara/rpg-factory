### Changed

- **Hooks.** Cheaper hook calls. The file guard no longer loads the whole git guard (it compiled it on every Read only
  to find the workspace): the shared path helpers (`find_workspace`, `main_checkout`, `linked_worktree`,
  `native_path`, `native_abs`) live once in `scripts/lib/workspace.py`, used by the git guard, the file guard and
  the routing engine. The git guard moved to `scripts/lib/gitguard.py`; `scripts/git-guard.py` is a small hook
  entry that re-exports every guard name. Hook entry points (git guard, file guard, Skill hook, Codex hook,
  SessionStart) cache compiled bytecode under `<state dir>/pycache` (`scripts/lib/hookspeed.py`; the plugin tree stays
  free of `__pycache__`; `RPG_FACTORY_PYCACHE=off` disables it). Write tools cache a repository's submodule paths
  (`git ls-files -s`) in the state dir per work tree and `.git/index` stat, and recompute when the index changes.
  Measured on Windows (median of 10, real interpreter): git guard `git status` 63-95 ms to 55-66 ms, file guard
  Read 71-80 ms to 58-60 ms, Write 87-88 ms to 55-66 ms (`tests/hook-perf.test.sh`).

### Added

- **Doctor and SessionStart.** When `python3` on PATH is the Windows Store alias (`\WindowsApps\`), doctor and the
  SessionStart advisory say each hook call starts about 70 ms slower and suggest putting the real interpreter first
  on PATH. Detection only: nothing is changed (`tests/install-status.test.sh`, `tests/hook-perf.test.sh`).
