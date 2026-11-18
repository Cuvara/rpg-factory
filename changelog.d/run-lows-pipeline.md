### Fixed

- **`factory-pipeline.py cleanup`.** A leftover task directory reached through two spellings (forward and back
  slashes) is listed once: the candidates are deduplicated by `norm_wt()`, keeping the first spelling.
- **`factory-pipeline.py status`.** Orca lineage children of the integration checkout and of task worktrees count only
  when their branch is the plan's own (the topic, a task branch or `<task branch>-...`, with an optional Orca prefix such
  as `codex/<topic>`); a worktree of another plan whose topic extends this one (`<topic>-v2`) is no longer listed as a
  leftover child.
- **`factory-pipeline.py status`.** A reviewed task whose review is PASS but whose task QA is FAIL on that candidate no
  longer gets `git merge --no-ff <task branch>` as `next`: the note says the QA failed and the next step is the task lead
  (fix session, then a fresh verify).
- **`factory-pipeline.py` `model_scope_widen`.** `validate` reports a malformed entry once (the model-policy error that
  repeated it is dropped), `"model_scope_widen": null` fails `validate` (the schema requires an array), and `lead_prompt`
  loads the policy once. The `slot_holders` docstring names `winpid`.
