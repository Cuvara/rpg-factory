### Added

- **Pipeline.** Multi-wave plans: the gate accepts an earlier wave's review when a later wave's changes under its paths
  are covered by the later task's own current PASS review (and QA where required), with commits attributed to tasks
  by the topic's merge commits. Unreviewed changes and evil merges still block. `status` judges review currency with
  the same rule, so `status` and the gate agree on shared dependent paths.
- **Pipeline.** `verdict` records the true implementer of a task (the task record, else the unanimous subtask records,
  else the review dispatch or the planned routing) and the subtask implementers; `--implementer` declares it, and the
  gate pairs the review against the recorded implementer.
- **Pipeline.** `status` shows a task's own current QA and reports integration QA staleness as such; a QA recorded a
  moment ago is never STALE.
- **Pipeline.** `verdict --report` requires an existing file; `--note TEXT` takes free text.
- **Registry.** `check-registry.sh` ties the kind enum copies (the subplan schema and the registry schema
  `agent_routing`) to `docs/schemas/pipeline-plan.schema.json` and fails when one differs.
