### Added

- **Delivery pipeline: stacked dispatch gate.** A stacked task's `dispatch --phase verify|review|qa` exits 2 until its
  dependency's review PASS SHA is in the candidate (the reason names the `git merge`, never a rebase), and `verdict`
  refuses a review or QA PASS on such a SHA (FAIL is still recorded). The gate blocks a dependent integrated before (or
  together with) its dependency and a dependent whose review PASS lacks the dependency's PASS SHA; a clean merge of the
  dependency into the dependent is a sync merge and no longer makes the dependency's review STALE (its conflict
  resolutions still do). `status` notes `verify waits: <reason>` with the merge as next, and `integrate <dep> first`
  for a reviewed dependent whose dependency is not integrated yet (dependency first, then `git merge --no-ff`).
