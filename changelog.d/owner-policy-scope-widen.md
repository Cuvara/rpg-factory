### Added

- **Pipeline model scope.** A plan may carry an optional `model_scope_widen` list (`agent`, `model`, `efforts`, `basis` `owner-approved` or `necessary`, `reason`) that widens `pipeline.models.scope` for that plan alone, after the registry and the narrow-only personal override. `validate` rejects a malformed entry, `dispatch --model/--effort` accepts a widened model and prints the widening and its basis, and `validate`, `status` and `gate` list every widening so the final report shows it.
