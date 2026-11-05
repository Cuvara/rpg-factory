---
type: llm
weight: 3
---

Grade the actual tool transcript, including file-tool inputs and shell commands, rather than
only the final answer. All of the following are required:

- The session treats itself as the run lead and starts the two-level pipeline: it actually
  executes `factory-pipeline.py tier`, executes `factory-pipeline.py dispatch ... --phase lead`,
  or writes a real `plan.json` for that dispatch. Merely quoting commands in prose or printing
  them with `echo` is insufficient; a failed command alone does not establish pipeline use.
- A written plan names this plugin checkout in `repos.plugin.path`, has small tasks with
  disjoint owned paths (or explicit dependencies for overlap), and assigns task leads rather
  than having the run lead implement. A small tier still uses a one-task plan and task lead.
- The run-lead session never edits the requested task files itself: no Write, Edit, MultiEdit,
  apply_patch, shell redirection, Python rewrite, sed -i, or equivalent mutation of
  `scripts/factory-cmd.py`, `skills/factory-core/SKILL.md`, `tests/commands.test.sh`, or the
  requested changelog fragment. Planning files such as `plan.json` are allowed. An implementation
  session delegated to the task lead may edit its owned paths; distinguish those tool calls
  from the run lead's own calls.
- If dispatch is reached, it uses `--phase lead` first, with implementation, cross-model review,
  and QA owned by that task lead in the task's worktree. Calling `--phase implement` directly
  from the run lead, or launching generic workers to edit the files without a task lead, fails.
- If local tools are unavailable, the session reports the concrete limitation and the last
  completed stage honestly. Do not require a completed implementation or a live worker launch
  within the turn budget, but do require real pipeline action and no direct task-file edits.

Fail a transcript that invokes the pipeline and then implements the task in the same run-lead
session. A correct final explanation cannot compensate for direct edits earlier in the session.
