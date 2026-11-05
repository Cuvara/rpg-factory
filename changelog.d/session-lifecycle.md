### Added

- **Parallel work.** `parallel-work.md` section 8 gains "Session lifecycle": one fresh worker session per task, never reused; the lead releases an implementer, pushes its task branch and removes its worktree in the `worker_done` turn, and a review or QA session in the turn its verdict is recorded; a task is integrated when its review PASS is recorded, in wave order; review and QA run in their own fresh sessions; the lead keeps only `plan.json` and integration state and hands off after each wave through `factory-pipeline.py status plan.json`.
- **Docs.** `.claude/CLAUDE.md` "Developing this plugin": every plugin task runs through `factory-pipeline.py` with a `plan.json` naming the plugin checkout, small disjoint tasks and cross-model review. The skill-author skill plans scaffold, content and routing/dogfood as separate tasks; `AGENTS.md` points Codex at the same flow.

### Fixed

- **Skill author.** The validate step names a changelog fragment instead of a `CHANGELOG.md` `[Unreleased]` entry.
