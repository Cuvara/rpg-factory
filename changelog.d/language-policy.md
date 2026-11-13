### Changed

- **Language policy.** The registry `english-only` global rule now covers everything written: code, comments, docs,
  changelogs, commit messages, PR and issue text, plan files (including the harness plan-mode file), briefs and specs
  for agents, messages between sessions, artifacts and memory files. Only the report to the owner (chat replies, status
  updates, questions, the final report) uses the workspace report language. `report.md`, `delivery.md` section 3 and
  the plugin `CLAUDE.md` state the policy.

### Added

- **Report language.** Registry `workspace.report_language` (Vietnamese here) and `workspace.language_allow` (globs for
  localisation data that may hold non-English text); `skills/delivery/pipeline-defaults.json` carries the matching
  optional setting for workspaces without a registry (unset means the user's own language).
- **Language line.** Every snapshot (not only `--full`) and every spec kind printed by `factory-pipeline.py` carries a
  `Language:` line with the English and report-language halves.
- **Advisories.** `file-guard.py` (Write, Edit, MultiEdit, NotebookEdit into a registered repo, the plugin, a
  `docs/plans/` directory, or a harness plan or memory directory) and the git guard (`git commit` message, `gh pr` and
  `gh issue` text, `orca orchestration send` and `orca agent launch` text) emit an `rpg-factory advisory (warn)` naming
  rule `english-only` and the first offending line. Advisory only: no hook blocks or asks.
- **Shared detection.** `scripts/lib/english.py` holds the english-only detection used by
  `scripts/checks/english-only.py`, `file-guard.py` and the git guard.
