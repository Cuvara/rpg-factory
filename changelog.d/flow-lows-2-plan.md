### Changed

- `factory-pipeline.py validate` now prints a `NOTE` (also in `--json` `notes`) for each recorded review or QA verdict of
  a task, or integration QA of a repo, that a later plan change made stale (objective, paths, acceptance, checks or
  agents changed since it was recorded), as `plan-edit` already did. Read-only: a note, never an error or another exit
  code; no record, no note.
- `factory-pipeline.py plan-edit` reads the edited copy once through `read_plan` (same `cannot read edited copy` error,
  same `no_worktree_markers` handling) and writes exactly the bytes it validated. No behaviour change.

### Fixed

- `tests/pipeline.test.sh` case map: a change confined to one function of `scripts/lib/pipeline_route.py` no longer
  selects every pipeline case group (`tests/affected.py cases`). Each group names the `pipeline_route.py` symbols its
  `factory-pipeline.py` symbols reach (or `::*` when it exercises the file whole), and a cli-selftest case recomputes
  that closure with `ast` and fails when the map misses one.
