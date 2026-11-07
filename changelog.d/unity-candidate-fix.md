### Fixed

- **Pipeline: no-worktree dependent tasks.** In a no-worktree (Unity) repo, a task starts only after its serial
  predecessor's current QA PASS on the shared integration branch: until then `status` keeps it pending (it waits for
  the predecessor) instead of offering a review of the predecessor's commits in the paths both tasks own. A pending
  task that both depends on and follows its predecessor names it once in its "waits for" note.
- **Pipeline: STALE QA in dispatch.** `dispatch --task integration:<key> --phase qa` of a no-worktree checkout, and
  `dispatch --phase lead|implement` of the next task in it, read each task's QA as `status` does: a QA PASS recorded
  for an older version of the task is STALE and still counts as open.
- **Pipeline: subtask verdict files.** A subtask's verdicts are named `<task>@<subtask>__<phase>...`, which no task id
  can produce: task `a__sub-b` and subtask `b` of task `a` no longer share `a__sub-b__review.json`. Task verdict file
  names are unchanged; older `<task>__sub-<subtask>__...` records still count for the task and subtask they name unless
  new-style records exist for that subtask and phase, in which case the new-style records take precedence.
- **Pipeline: command hint.** `/rpg-factory:pipeline`'s argument hint lists `subplan`; `status` no longer runs an
  unused git call after the integration QA rows.
