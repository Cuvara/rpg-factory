### Added

- **Parallel work.** `parallel-work.md` section 8 gains "Session lifecycle": one worktree per task for its whole life, and one fresh worker session per dispatch, never reused. The implementer, reviewer, QA worker and any fix run as separate fresh sessions in that task worktree (reviewer and QA read-only, after checking that `git rev-parse HEAD` is the candidate SHA); review and QA never get a new worktree, and integration QA runs in the integration checkout. Each session is released in the turn it reports and the task worktree stays; a task is integrated when its review PASS is recorded, in wave order, and its worktree is removed only after that PASS and integration (no-worktree repo: its sessions settle after its QA). The lead keeps only `plan.json` and integration state and hands off after each wave through `factory-pipeline.py status plan.json`. Sections 1, 4, 6, 8 (cleanup) and 10 (review step) follow the same rule; `factory-pipeline.py dispatch --phase review|qa` still prints a new-worktree start, so the policy says to start those workers with `--worktree path:<task worktree>`.
- **Docs.** `.claude/CLAUDE.md` "Developing this plugin": every plugin task runs through `factory-pipeline.py` with a `plan.json` naming the plugin checkout, small disjoint tasks and cross-model review. The skill-author skill plans scaffold, content and routing/dogfood as separate tasks; `AGENTS.md` points Codex at the same flow.

### Fixed

- **Skill author.** The validate step names a changelog fragment instead of a `CHANGELOG.md` `[Unreleased]` entry.
