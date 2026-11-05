### Added

- **Delivery pipeline.** `scripts/factory-pipeline.py` (and `/rpg-factory:pipeline`) runs the parallel-work policy
  end to end: `tier` (S/M/L from the routing snapshot), `validate` for a `plan.json` (disjoint owned paths,
  cycles, waves, cross-model reviewer, exclusive resources; schema `docs/schemas/pipeline-plan.schema.json`),
  `planner` and `dispatch` (exact `orca orchestration` worker starts or the Agent fallback for implement, review
  and QA), `verdict` (review and QA results keyed by the candidate SHA) and `gate` (READY_FOR_PR only when every
  task is integrated, reviewed PASS by the other model on unchanged paths, QA PASS on the integration HEAD, the
  trees are clean, every change sits in a task's owned paths, each verdict matches the current plan's task and
  the fast checks are PASS and current; `--no-run-checks` gives UNVERIFIED, never a delivery). With the user's `deliver: pr` the lead pushes and
  opens the PR the gate prints; merging stays with the user (`git-safety.md` rule 5). Settings live in registry
  `pipeline`; QA uses `templates/pipeline/qa-report.md` (`tests/pipeline.test.sh`).
- **No worktrees in Unity projects.** `repos.client.worktrees: false` (and any repo with
  `ProjectSettings/ProjectVersion.txt` at its root): every role works in the main checkout, the repo's tasks run
  one after another with review and QA each, and Unity test runs are one shared exclusive resource
  (`pipeline.exclusive_resources`).
- **Cleanup after every task.** `parallel-work.md` section 8 is mandatory: when a task is done the lead removes
  the run's worktrees (`git worktree remove`, never `--force`), deletes task branches already in the integration
  branch (`git branch -d`), and ends every Claude and Codex worker session (`orca orchestration worker-release`,
  background agents stopped). `factory-pipeline.py cleanup` lists what is left and prints the commands; it must
  report CLEAN before the final report.

### Fixed

- **Workflow dispatch for Orca.** `factory-workflow.py dispatch --runner orca` printed
  `orca orchestration worker-start --task "<spec>"`, which Orca rejects (`--task` takes a task id and a start needs
  `--agent`); it now prints `--spec ... --agent ... --worktree ...` and never a new worktree for a Unity project.
