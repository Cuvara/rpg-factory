### Added

- **Operating lessons in the repo.** `.claude/CLAUDE.md` gains an "Operating lessons" section (no worktree or
  branch creation while run-all runs, `git switch --no-track -c`, Git Bash never WSL, citation `--fix` before a
  release gate, at most two concurrent full run-all runs, `git update-index --chmod=+x` on Windows, quoting shell
  examples, the learning loop), pointed to from `AGENTS.md`. New `docs/dogfood.md` (linked from the
  `tests/dogfood.sh` and `tests/dogfood-codex.sh` headers) says how to classify and report nondeterministic dogfood
  failures and lists the known traps. `parallel-work.md` adds the full test run as a shared resource, the
  Codex-else-Claude rule, Orca message traps (escalation from non-workers, heartbeats in `check --wait`, multi-line
  prompts under `cmd.exe`, confirming a Codex worker picked up its prompt), session count under memory pressure and
  which plan edits keep verdicts.

### Fixed

- **Pipeline.** `factory-pipeline.py dispatch --phase lead|implement` branches a later-wave task (one with deps)
  from the plan's `topic` integration branch when it exists, so it carries the earlier waves; `repos.<key>.base`
  stays the comparison base of `status` and the gate.
