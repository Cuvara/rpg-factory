### Added

- **Delivery pipeline: stacked dispatch (base, record, status).** A task whose one dependency in the same repo is still
  a candidate or reviewed (every other dependency integrated) no longer waits: `factory-pipeline.py status` lists it as
  ready with `stackable on <dep>@<sha>`, and `dispatch --phase lead` starts its task branch from that dependency's tip
  and records the SHA in `<task>__stack.json` (outside the task fingerprint, so verdicts stay valid). Review, verify and
  per-task QA of a stacked task use the newest dependency SHA in its HEAD as `--affected --base`, so they see only the
  task's own delta. `status` shows `stacked on <dep>@<sha>` and, when the dependency moved, `<dep> now at <sha> not in
  HEAD` with the `git merge` command as next. Two in-flight dependencies, tier XS and no-worktree repos never stack.
