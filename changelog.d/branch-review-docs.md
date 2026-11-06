### Fixed

- **Codex role.** `AGENTS.md` no longer lets Codex act as the run lead or a task lead: Codex runs only as a session a
  Claude task lead starts (implementer, cross-model reviewer, QA); the run lead is the main Claude Code session and the
  task lead is always Claude (registry `pipeline.lead_agent`). `AGENTS.md` points to the `.claude/CLAUDE.md` operating
  lessons for Git Bash instead of restating the WSL lesson. `tests/parallel-policy.test.sh` fails when `AGENTS.md`
  names Codex as run lead or task lead.
- **Child implement sessions.** `parallel-work.md` section 10 step 4 states the child exception: a shared-placement
  implement session never commits, a child session commits on its own child branch and the task lead merges and
  removes it. `tests/parallel-policy.test.sh` checks the step under a policy marker.
- **Parallel-work wording.** Section 4 says which placement default applies to which phase (`dispatch --phase lead`
  defaults to `child`, every other session to `shared`) and that a no-worktree (Unity) repo's task branch is the plan
  `topic`; section 8 removes a leftover child with `orca worktree rm --worktree path:<child>`.
- **Changelog.** The task-lead and session-lifecycle fragments name `--parent-worktree` as the task worktree default and
  the child-worktree exception.
- **factory-core allowed-tools.** The `python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py` form the
  pipeline prints is granted, not only the form without `-B`.
