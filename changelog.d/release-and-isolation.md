### Added

- **Pipeline.** `factory-pipeline.py cleanup` and `status` list the settled Orca workers of a task lead's Run that are not released, with their `orca orchestration worker-release --dispatch <id>` commands. The Run comes from the new optional plan task field `orca_run` (not part of the verdict fingerprint) or from `--orca-run <id>` (repeatable, `run:<id>` accepted). The check is read-only (`orca orchestration worker-list --run <id> --json`, every page): a released worker and a running worker are no finding; an unreleased settled worker makes cleanup LEFTOVER and puts its release command first in the status `next` list. Without orca, or when the call fails, the Run prints a NOT_AVAILABLE line and nothing fails. `status --json` keeps stdout to the status schema and prints the same `Workers:` lines (NOT_AVAILABLE, UNRELEASED) on stderr.

### Changed

- **Pipeline.** The task-lead spec printed by `dispatch --phase lead` says to release every implement, review and QA session the moment it reports, its candidate is superseded or it stops, not at task end; to check with `status --orca-run <run id>`; and to name its Orca Run id in the report. `parallel-work.md` section 8 names the check.
- **Pipeline.** The task lead is Claude (`pipeline.lead_agent`), whatever the task's implementer: that registry key (`"claude"`, the default when the key is missing) picks the agent of `dispatch --phase lead`, and `--agent codex` on `--phase lead` prints a warning and keeps Claude. Implementation, review and QA sessions keep the cross-model pairing. `parallel-work.md` states the rule under the new `policy:task-lead-claude` marker, linted by `tests/parallel-policy.test.sh`, and factory-core `SKILL.md` step 6 says it.

### Fixed

- **Tests.** `tests/install-status.test.sh` isolates the caller's Codex runtime markers (`CODEX_THREAD_ID`, `PLUGIN_ROOT`, `PLUGIN_DATA`): inside a Codex session they made the plugin look like a Codex install and one of 47 cases failed.
