---
type: llm
weight: 3
---

Grade the actual tool transcript, including file-tool inputs and shell commands, rather than
only the final answer. All of the following are required:

- The session treats itself as the run lead and dispatches a task lead: it actually executes
  `factory-pipeline.py dispatch <plan.json> --task <id> --phase lead` with the print runner
  (`--runner print` or no `--runner`), and that command succeeds. Running `factory-pipeline.py
  tier` alone, writing a `plan.json` alone, quoting commands in prose, printing them with `echo`,
  or a failed dispatch fails this criterion.
- The session causes no real side effects outside its checkout: it does not run `orca`, does
  not dispatch with `--runner orca` or `--runner agent`, does not launch agents or sub-sessions,
  and does not commit, merge or push. Doing any of these fails the transcript.
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
  completed stage honestly. Do not require a completed implementation or a live worker launch,
  but do require the successful lead dispatch above and no direct task-file edits.

Fail a transcript that invokes the pipeline and then implements the task in the same run-lead
session. A correct final explanation cannot compensate for direct edits earlier in the session.
