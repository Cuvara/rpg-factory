### Added

- **Docs.** `AGENTS.md` at the repo root for Codex: it points at `.claude/CLAUDE.md` as the authoritative guide and
  adds only the Codex-only notes (Git Bash, reinstall after edits, `factory-cmd.py` instead of slash commands, hook
  trust review). `scripts/README.md` indexes every script entrypoint with its purpose and covering test suite.
- **Lint.** `tests/skills-lint.sh` prints a `WARN` line (not a failure) when `factory-core` `SKILL.md` exceeds a
  140-line budget; the 160-line cap is unchanged.

### Changed

- **Core.** `factory-core` `SKILL.md` shrinks from 160 to 124 lines: the mode table, the routing details of workflow
  step 4, the validation-state table and the git-safety advisory list now live only in their references
  (`skill-contract.md` "Routing", `validation.md`, `git-safety.md`, `workflows.md`). The 12 workflow steps keep their
  marks and commands.
