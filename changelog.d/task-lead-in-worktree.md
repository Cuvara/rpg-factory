### Added

- **Pipeline task lead.** `factory-pipeline.py dispatch <plan.json> --task <id> --phase lead [--report-to <run id>]`
  starts ONE task-lead session per plan task, with the task spec plus the task-lead rules: plan and split the task
  into subtasks with disjoint paths, one fresh Claude or Codex session per subtask in the same worktree, sub-sessions
  that do not commit, the task lead commits per subtask, cross-model review and QA sessions in that worktree, a fresh
  fix session after a FAIL, every session released as it reports, a `status` report to the run lead (branch, HEAD,
  verdicts, checks), never push, merge or remove the worktree. Orca forbids nested workers, so `--runner orca` prints
  a handoff instead of a worker start: `orca worktree create --branch <topic>-<task> --no-parent --agent ... --prompt
  ...` for a new task worktree, `orca agent launch --worktree path:<dir> --prompt ...` to resume in it; the task lead
  creates its own Orca Run and reports with `orca orchestration send --to run:<id> --type status`. In a no-worktree
  repo (Unity project) the task lead runs in the main checkout and dispatch never prints a worktree create or a new
  top-level worker. `status` names `--phase lead` as the next command of a pending task.
- **Pipeline subplan.** `factory-pipeline.py subplan validate <subplan.json> [--plan PATH] [--json]`
  (`docs/schemas/pipeline-subplan.schema.json`) checks a task lead's split of one plan task: subtask paths inside the
  task's owned paths and outside its exclusions, overlapping subtasks ordered by deps, known deps and no cycle, an
  implementer that is a pipeline agent and a reviewer of the other model (registry `pipeline.review_pairing`), and
  well-formed subtasks; it prints the waves (one subtask per wave in a no-worktree repo).

### Changed

- **Pipeline placement.** `dispatch --phase implement|review|qa` joins the task's existing worktree (found by the task
  branch in `git worktree list`, `--worktree path:<it>`) and never creates one: a missing task worktree is an error
  (exit 1, run `--phase lead` first). `--phase implement --paths <subtask paths>` starts a sub-session limited to those
  paths that does not commit. Integration QA (`--task integration:<repo> --phase qa`) runs in the existing checkout of
  the integration branch, never in a task worktree; none is an error, no worktree is created.
- **Agent fallback.** `--runner agent` starts Claude sessions only: a session planned for Codex runs as a fresh Claude
  session whose prompt says SAME_MODEL, and its review counts as SAME_MODEL.
- **Parallel work.** `parallel-work.md` describes the two levels (sections 1, 3, 4, 5, 6, 7, 8 and 10): the run lead
  gives each task one worktree and one task-lead session and integrates; the task lead runs subtasks, cross-model
  review, QA and fixes as fresh sessions in that worktree. It records the Orca nesting limit and the Unity rule (task
  lead, subtasks, review and QA in the main checkout, one after another; Unity test runs exclusive). Every session is
  released as it reports, in every repo; a no-worktree repo serializes only its task work. `.claude/CLAUDE.md`,
  `AGENTS.md` and the skill-author skill point to it.

### Fixed

- **Pipeline paths.** Owned and subtask paths that are absolute or contain a `..` segment are rejected (plan
  `validate`, `subplan validate`, `dispatch --paths`) before any containment, exclusion or overlap comparison.
- **Parallel-policy test.** `tests/parallel-policy.test.sh` makes its plugin copy writable (tar kept read-only modes,
  so `echo >> file` mutations silently did nothing and their cases failed) and reports a FAIL when a mutation command
  itself fails; a regression case copies a read-only source file and mutates it.
