# AGENTS.md - rpg-factory

Read `.claude/CLAUDE.md` before changing anything: it is the authoritative guide for this repo (rules,
commands, layout, release order) for every agent runtime, Codex included. This file adds only the
Codex-specific notes and does not restate those rules.

## Codex-only notes

- **Operating lessons:** `.claude/CLAUDE.md` "Operating lessons" (worktrees and branches during run-all, Git Bash
  never WSL, citation drift, run-all load limit, executable bit, quoting) applies to Codex too; add new lessons there.
- **Loading your edits:** after editing the checkout, run `codex plugin add rpg-factory@rpg-factory`
  and restart Codex so the session loads the changed plugin.
- **No slash commands:** Codex skips `commands/`. Run the same verbs directly:
  `python3 -B <plugin root>/scripts/factory-cmd.py <verb> [args]` (`status`, `route`, `check`, `doctor`, `ui`, ...).
- **Hooks need a trust review:** Codex runs the plugin hooks (`hooks/codex-hooks.json` through
  `scripts/codex_hook.py`) only after you review and trust them. They are advisory only.
- **Plugin tasks:** Codex takes part in the plugin-development flow (`.claude/CLAUDE.md` "Developing this plugin")
  only as a session a Claude task lead starts in the task worktree: an implementation sub-session, a cross-model
  reviewer or a QA worker. The run lead is the main Claude Code session and the task lead is always Claude (registry
  `pipeline.lead_agent`); the roles and rules are in `skills/factory-core/references/parallel-work.md`. Follow the
  spec you were given: edit only its paths, commit only where it says so, and report to the task lead.
- **Skills:** the factory-core skill names how to resolve the plugin root and load routed skills on Codex.

More: `docs/codex.md` (manifests, hook adapter contract, Codex dogfood). Script index: `scripts/README.md`.
