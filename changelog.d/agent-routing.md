### Added

- Route pipeline implementation, planning, review and QA by task kind and available models, with per-run MODEL_UNAVAILABLE marks and automatic SAME_MODEL fallback reviews.
- Warn about unexplained model overrides and plans using only one model; expose model choices and reasons in dispatch and status.

### Fixed

- Record the model `dispatch --phase implement` started per task and subtask; review, QA, `verdict` and the gate pair against that record (else the planned routing), never current availability, so a model that returns after a fallback no longer reviews its own work as cross-model.
- `verdict` stamps a SAME_MODEL fallback only when that candidate's `dispatch --phase review` was a fallback for the same reviewer, and refuses `--fallback` for available models, unknown agents and QA verdicts; `verdict --subtask` pairs against the subtask's routing (its record, its review dispatch, or `--subplan`), not the task's.
- The gate no longer lets a task review launder a subtask: a subtask whose recorded implementer differs from the one the task review paired against, or is the task reviewer's own model, needs its own PASS review by its pair or a dispatch-recorded SAME_MODEL fallback review (noted `SAME_MODEL (fallback: <pair> unavailable)`).
- `status` reports a plan task without `id` as INVALID instead of a traceback; `check-registry.sh` no longer fails in jq when `pipeline.qa_prefer` is absent; `validate` no longer probes availability and the planner reads no per-run MODEL_UNAVAILABLE marks.
- Require a subtask implementer or kind, honor registry routing defaults and candidate agents, and detect Orca account availability with UTF-8 output.
