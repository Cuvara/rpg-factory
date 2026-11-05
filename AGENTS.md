# AGENTS.md - rpg-factory

Read `.claude/CLAUDE.md` before changing anything: it is the authoritative guide for this repo (rules,
commands, layout, release order) for every agent runtime, Codex included. This file adds only the
Codex-specific notes and does not restate those rules.

## Codex-only notes

- **Shell:** on Windows use Git Bash, never WSL. A WSL git run once rewrote the shared `.git/config`.
- **Loading your edits:** after editing the checkout, run `codex plugin add rpg-factory@rpg-factory`
  and restart Codex so the session loads the changed plugin.
- **No slash commands:** Codex skips `commands/`. Run the same verbs directly:
  `python3 -B <plugin root>/scripts/factory-cmd.py <verb> [args]` (`status`, `route`, `check`, `doctor`, `ui`, ...).
- **Hooks need a trust review:** Codex runs the plugin hooks (`hooks/codex-hooks.json` through
  `scripts/codex_hook.py`) only after you review and trust them. They are advisory only.
- **Skills:** the factory-core skill names how to resolve the plugin root and load routed skills on Codex.

More: `docs/codex.md` (manifests, hook adapter contract, Codex dogfood). Script index: `scripts/README.md`.
