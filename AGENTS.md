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
  as a session a task lead starts in the task worktree: an implementation sub-session, a cross-model reviewer or a
  QA worker. Codex is the default implementer for the code, test, fix, refactor and generated kinds (registry
  `pipeline.agent_routing`) and runs the full-suite QA of work Claude implemented. The run lead is the main
  Claude Code session; the task lead is Claude (registry `pipeline.lead_agent`), and
  Codex leads a task only when Claude is unavailable. The roles, the "Which model" table and the fallback rules are in
  `skills/delivery/references/delivery.md` (RPG specifics: `skills/factory-core/references/parallel-work.md`). Follow the spec you were given: edit only its paths, commit
  only where it says so, and report to the task lead.
- **In-session subagents:** Codex uses the `multi_agent` feature; the subagent model comes from registry
  `pipeline.subagents` (codex). Set `[agents] default_subagent_model` in the Codex config to a model inside
  `pipeline.models.scope`. No nested subagents. Rules: `skills/delivery/references/delivery.md` section 8 "In-session subagents".
- **Skills:** the factory-core skill names how to resolve the plugin root and load routed skills on Codex. The
  generic delivery flow lives in the `delivery` skill (`skills/delivery/SKILL.md`, policy in
  `skills/delivery/references/delivery.md`); factory-core calls it, and it also works in any other repository.

More: `docs/codex.md` (manifests, hook adapter contract, Codex dogfood). Script index: `scripts/README.md`.
