### Fixed

- **Pipeline: no-worktree dependent tasks.** In a no-worktree (Unity) repo, a task whose serial predecessor has no
  review or QA verdict on the shared integration branch yet has not started: `status` keeps it pending (it waits for
  the predecessor) instead of offering a review of the predecessor's commits in the paths both tasks own. A pending
  task that both depends on and follows its predecessor names it once in its "waits for" note.
- **Pipeline: STALE QA in dispatch.** `dispatch --task integration:<key> --phase qa` of a no-worktree checkout, and
  `dispatch --phase lead|implement` of the next task in it, read each task's QA as `status` does: a QA PASS recorded
  for an older version of the task is STALE and still counts as open.
- **Pipeline: subtask verdict files.** A subtask's verdicts are named `<task>@<subtask>__<phase>...`, which no task id
  can produce: task `a__sub-b` and subtask `b` of task `a` no longer share `a__sub-b__review.json`. Task verdict file
  names are unchanged; older `<task>__sub-<subtask>__...` records still count for the task and subtask they name.
- **Pipeline: command hint.** `/rpg-factory:pipeline`'s argument hint lists `subplan`; `status` no longer runs an
  unused git call after the integration QA rows.
