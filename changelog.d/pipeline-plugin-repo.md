### Added

- **Pipeline status.** `factory-pipeline.py status <plan.json> [--json]` (schema `rpg-factory.pipeline-status/1`,
  `docs/schemas/pipeline-status.schema.json`) shows how far each task got - pending, implementing, candidate, reviewed
  (PASS or FAIL with its SHA), integrated or qa - derived from git and the recorded verdicts, with the next command per
  task, the ready wave and the tasks to dispatch now, and the gate once every task has QA and every repo has its
  integration QA PASS at the integration HEAD (also after the per-task QA of a Unity project; until then the next
  command is that integration QA), so status names the gate only when the gate can pass. A new lead session resumes a
  run from it without the old session's context. Read-only. `/rpg-factory:pipeline status` runs it.

### Fixed

- **Pipeline tier for unregistered repos.** `factory-pipeline.py tier --plan <plan.json> --repo <key> --paths <files>`
  tiers a `plan.repos` entry the registry does not know (the plugin repo itself) from the paths alone (modules:
  `skills/<name>`, `scripts/lib`, `scripts`, `tests`, `registry`, `docs`, `hooks`, `commands`, and one `other` module for
  anything else; no contracts or generated paths) instead of failing with
  `factory-context: unknown repo`. A registry repo key still goes through `factory-context.sh`.
