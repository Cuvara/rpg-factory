### Added

- **Delivery pipeline: stacked handoff and merge order.** `dispatch --phase lead` for a stackable task prints
  `git worktree add --no-track -b <topic>-<id> <path> <dependency tip SHA>` for a sibling worktree beside the
  integration checkout (never a child of the dependency's worktree), `orca worktree set` with the integration checkout
  (else the main checkout) as parent, then the launch; the lead prompt says to implement now and run no verify, review
  or QA dispatch before `status` clears it. `status` notes and `cleanup` `STACK` lines (`stacked` in `--json`) name the
  stacked siblings and the merge order into the topic: dependency first, then each dependent (`git merge --no-ff`),
  `git branch -d` only after its merge. Tier XS and no-worktree tasks keep the unchanged handoff.

### Fixed

- **Delivery pipeline: leftover sync records.** A fresh task-lead dispatch removes a leftover `<task>__sync.json`, and
  `status` shows a `sync:` note only for the task's current dependency.
