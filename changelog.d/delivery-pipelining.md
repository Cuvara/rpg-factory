### Changed

- **Delivery policy: stacked dispatch.** `skills/delivery/references/delivery.md` section 4 "Stacked dependents"
  (`policy:stacked-dispatch`) states when a dependent task stacks on its one in-flight dependency (a sibling
  `<topic>-<id>` worktree cut from the dependency's tip), that it implements at once but verifies only after the
  dependency's review PASS SHA is in its HEAD, merges the dependency (never rebases) and is integrated after it.
  `docs/pipeline-cli.md` documents the `sync` verb, the stacked `status` notes and `cleanup` lines, the dispatch and
  verdict refusals, the gate rules and the selected-suite pre-flight; `skills/factory-core/references/parallel-work.md`
  records the operating lessons with their reasons.
