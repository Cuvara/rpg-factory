### Added

- Route pipeline implementation, planning, review and QA by task kind and available models, with per-run MODEL_UNAVAILABLE marks and automatic SAME_MODEL fallback reviews.
- Warn about unexplained model overrides and plans using only one model; expose model choices and reasons in dispatch and status.

### Fixed

- Preserve the implementer covered by review evidence across availability changes and reject fallback claims for available models.
- Require a subtask implementer or kind, honor registry routing defaults and candidate agents, and detect Orca account availability with UTF-8 output.
