### Added

- **Pipeline status.** `factory-pipeline.py status <plan.json> [--json]` (schema `rpg-factory.pipeline-status/1`,
  `docs/schemas/pipeline-status.schema.json`) shows how far each task got - pending, implementing, candidate, reviewed
  (PASS or FAIL with its SHA), integrated or qa - derived from git and the recorded verdicts, with the next command per
  task, the ready wave and the tasks to dispatch now, and the gate once every task has QA. A new lead session resumes a
  run from it without the old session's context. Read-only.

### Fixed

- **Pipeline tier for unregistered repos.** `factory-pipeline.py tier --plan <plan.json> --repo <key> --paths <files>`
  tiers a `plan.repos` entry the registry does not know (the plugin repo itself) from the paths alone (modules:
  `skills/<name>`, `scripts/lib` or the top-level directory; no contracts or generated paths) instead of failing with
  `factory-context: unknown repo`. A registry repo key still goes through `factory-context.sh`.
