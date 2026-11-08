### Added

- **Model policy for the delivery pipeline.** Registry `pipeline.models` holds a model scope per agent (Claude, Codex),
  profiles per role (planner, lead, implement by grade, review, QA) and a grade rubric; `scripts/check-registry.sh` and
  `docs/registry.schema.json` reject a profile outside the scope. Plan tasks and subplan subtasks take an optional
  `grade` (`light|standard|heavy`) and `grade_reason`; without one the grade comes from the tier (S light, M standard,
  L, contract and generated paths heavy) and a subtask inherits its task's grade. `validate` and `subplan validate`
  print the resolved model and effort. `planner` and `dispatch` accept `--grade`, `--model` and `--effort` (a value
  outside the scope exits 2) and pass `--model/--effort` to `orca orchestration worker-start`, `orca worktree create`
  and `orca agent launch`; the Agent-tool runner passes a model alias and notes that effort cannot be set; `verdict`
  stores the optional model and effort. A personal override file (`$RPG_FACTORY_MODEL_POLICY` or
  `<persistent state dir>/model-policy.json`) may narrow the scope and replace profiles. The policy is described once, in
  `parallel-work.md` section 10, "Model choice" (`scripts/lib/model_policy.py`, `tests/pipeline.test.sh`).
