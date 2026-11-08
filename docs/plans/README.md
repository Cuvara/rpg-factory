# Plugin plans

Everything a run of the plugin's own delivery pipeline needs to continue on another machine lives here, in the
plugin repo. A fresh clone plus `python3 -B scripts/factory-pipeline.py status docs/plans/<topic>.json` is enough to
resume a run (`skills/factory-core/references/parallel-work.md` sections 8 and 10).

## What lives here

- `docs/plans/<topic>.json`: a pipeline plan for work on this plugin (schema
  `docs/schemas/pipeline-plan.schema.json`). It is the plan the run lead dispatches from, not a copy of it.
- `docs/plans/backlog.md`: the backlog of topics not planned yet. A topic leaves the backlog when a plan task
  covers it.
- `docs/plans/<plan>/report.md`: the run report, written by the run lead at integration and committed with it
  (`parallel-work.md` section 8): sessions per task with model and Orca Run, verdicts with SHA and model, checks
  with exact counts, limitations.

## What does not live here

Verdicts, task specs, subplans, model records and Orca state stay in the per-machine state dir
(`pipeline/<plan id>/` under the directory `scripts/lib/fstate.py` resolves). They are derived and bound to one
machine's sessions. A new machine never reuses them: it re-runs review and QA on the candidate SHA, and the gate
grades those new verdicts.

## Repo paths in a plan

`repos.<key>.path` takes one of two portable forms:

- **Plan-relative:** resolved against the directory of the plan file. `"../.."` is the checkout that holds the
  plan (`docs/plans/<topic>.json` sits two levels below the root), so the plan works in any clone or worktree.
- **Workspace-relative:** `"${RPG_FACTORY_WORKSPACE}/<repo>"` (or `$RPG_FACTORY_WORKSPACE/<repo>`), resolved
  against the workspace root from the environment, else the registry's workspace discovery.

`scripts/lib/plan_paths.py` (`resolve_repo_path`) implements both forms, and `factory-pipeline.py` resolves every
repo path through it (`repo_info`), so both plan-relative and workspace-relative paths work wherever the pipeline
reads a repo path.

## Rules

- **No machine-specific absolute paths.** No drive letters, no user home directories, no per-user application data
  or temporary directories, in plans, the backlog or reports. Name a state-dir file by its role ("the task's
  verdicts in the pipeline state dir"), never by its path on one machine. `tests/parallel-policy.test.sh` fails on
  any such path under `docs/plans/`.
- **Plan edits are atomic.** Write the edit to a copy, run `python3 -B scripts/factory-pipeline.py validate <copy>`,
  then replace the plan with the copy. Never edit the live plan in place: a task lead may read it mid-dispatch
  (`parallel-work.md` section 8).
- English only, like the rest of the repo.
