### Added

- **Two-level eval.** `evals/pipeline-two-level/` asks for a multi-file plugin change and grades the tool transcript:
  the session acts as the run lead and must run a successful `factory-pipeline.py dispatch --phase lead` with
  `--runner print` (running `tier` or writing a plan alone fails; the match is anchored on the Bash `command`, so an
  `echo` of the dispatch command does not count), and never edits the requested task files itself
  (implementing in the run lead's own session fails, even with a correct final report).
- **Two-level dogfood scenario.** The opt-in `tests/dogfood.sh --two-level` runs a real headless session on a throwaway
  clone of the plugin with a multi-file plugin task and passes only when the session dispatches a task lead
  (`factory-pipeline.py dispatch --phase lead --runner print`) and edits none of the task files. A dispatch counts only
  when its output carries the printed task-lead spec and no error (a pipe such as `| head` hides a failed exit status).
  The grading is offline too: `tests/dogfood.sh --grade-two-level <transcript.jsonl> [<clone dir>]` grades a recorded
  transcript without a model call (the disk check only with a clone dir); `tests/pipeline.test.sh` runs it on
  synthetic transcripts.
- **Cleanup names the dispatch specs.** `factory-pipeline.py cleanup` lists the plan's spec files under
  `<state dir>/pipeline/<plan id>/specs/` (count and directory) as kept state; it never deletes them and they do not
  affect CLEAN.

### Changed

- **factory-core drives the two-level flow.** `skills/factory-core/SKILL.md` names the main session the run lead
  (plans, dispatches, integrates, reports; never edits task files) and one task lead per task. Step 6 writes a
  `plan.json` for every tier (S is a one-task plan with its own task lead), runs `dispatch --phase lead` per ready
  task and `status` to resume; Unity (no-worktree) repos keep the task lead and every session in the main checkout,
  subtasks in sequence. Step 7 (task lead) runs `subplan validate` and one fresh sub-session per subtask, committing
  each with explicit paths. Step 11 (task lead) dispatches cross-model review (Codex reviews Claude's code and Claude
  reviews Codex's; without Codex a fresh Claude session marked SAME_MODEL) and QA; step 12 (run lead) gates, opens the
  PR, releases every session and runs `cleanup` until CLEAN. `AGENTS.md` and `.claude/CLAUDE.md` point to these steps.
- **Pipeline tier flows.** Registry `pipeline.tiers.S|M|L.flow` describe the two-level flow: the run lead writes the
  plan and dispatches one task lead per task (no-worktree repo: main checkout, in sequence), task leads run
  sub-sessions, cross-model review and QA, the run lead integrates and never implements.

### Fixed

- **One-line Orca prompts.** cmd.exe cut multi-line `orca` arguments at the first newline, so a dispatched session
  received only the first line of its spec. Every `--runner orca` dispatch (planner, task lead, implement, review, QA)
  now stores the full spec under `<state dir>/pipeline/<plan id>/specs/` and passes a one-line prompt pointing to that
  absolute file; the planner's prompt also ends with `Request: <text>`, whitespace collapsed to single spaces.
- **Pending status for unstarted tasks.** `factory-pipeline.py status` keeps a task with no branch, worktree or review
  pending: commits on the integration branch from an earlier task with the same owned paths no longer make it a
  `candidate` at the integration HEAD.
- **Planner specs in a reserved directory.** Planner specs moved from `pipeline/planner/` (which a plan with id
  `planner` would share) to `pipeline/_planner/`; `validate` rejects a plan id whose state directory is `_planner`.
- **Spec path test on short Windows paths.** `tests/pipeline.test.sh` compares spec directories by real, case-folded
  path, so an 8.3 short `TEMP` (Windows CI runners) no longer fails the check.
- **Note for unreviewed integration commits.** `status` keeps an unstarted task pending but notes when its owned paths
  already have commits on the integration branch and no review record exists ("integrated earlier? check before
  dispatching again").
