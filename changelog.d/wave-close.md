### Added

- **Pipeline.** The gate judges a subtask review's currency with the multi-wave attribution the task level uses, and
  from the subtask's own paths instead of the task's whole owned paths: a later wave merged with its own current
  PASS review does not make an earlier subtask review STALE, while unreviewed changes still do. A later sibling
  subtask's own current paired PASS review also covers its changes to an earlier subtask's paths (for example a fix
  session that edits files an earlier subtask implemented). That credit covers only the sibling's commits made after
  it started (its recorded implement dispatch); a sibling without a recorded start gets no credit.
- **Pipeline.** `verdict --subtask <id> --fallback '<model> unavailable' --note TEXT` records a SAME_MODEL fallback
  subtask review after the fact, for a review made before dispatch recorded fallbacks (for example during an outage
  of the paired model). The retrospective form is for subtask reviews only: without `--subtask` it is refused, and a
  task review keeps a dispatch-recorded fallback or `gate --allow-same-model`. `--note` is required and the reviewer must be the implementer's model; the gate shows it as an accepted fallback
  with its reason and note, never silently. The bare `verdict --fallback <model>` form also requires `--note`.
- **Pipeline.** A workspace-relative `repos.<key>.path` in a plan is resolved under the workspace wherever the
  pipeline reads a repo path.
- **Tests.** `tests/affected.py` selects the parallel-policy suite for changes to `scripts/orca-wait.sh` and
  `tests/orca-wait.test.sh`.

### Fixed

- **Tests.** `tests/routing.test.sh` strips the CR from skill names that Windows `jq -r` prints.
