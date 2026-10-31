# Extending production workflows

Registry data is the source of truth for domains, kinds, repositories, tools, and contracts. Keep the registry canonical JSON and run the registry checks after changes.

## Add an artifact kind

Register the kind with its domain, schema path, lifecycle and quality requirements; add a versioned schema under `docs/schemas/kinds/` and a valid draft under the domain's `templates/` directory. Add or update the lead skill guidance and architecture page. Add positive and negative lifecycle/schema/quality cases to the relevant domain workflow suite, update routing and eval fixtures as needed, and run `scripts/check-registry.sh --structure-only`, artifact checks, `tests/routing-golden.test.sh`, and skill checks.

## Add a domain quality plugin

Implement `check(artifact, ctx)` under `scripts/checks/domains/`. The Context API provides `repo`, `registry`, `artifacts`, registry-derived `repo_roots`, safe `resolve_repo_path`, name-only optional `tools`, and `approval` state access. Return structured results with one of `PASS`, `FAIL`, `WARN`, `HUMAN_REQUIRED`, `NOT_AVAILABLE` and `BLOCKED` and a reason. Do not write to repositories, launch optional tools during detection, print secrets, or treat unavailable evidence as a pass. Add plugin unit/integration cases through `artifact-quality.py`, including absent-tool and human-gate outcomes.

## Add an adapter

Place a read-only adapter under `scripts/adapters/<domain>/`; consume only explicit input paths and discovered executable paths. Report unavailable tools as `NOT_AVAILABLE` and ambiguous or insufficient evidence as `HUMAN_REQUIRED`. Add fixtures for valid, invalid, unavailable, timeout, and malformed output where relevant. Register an optional tool only when discovery uses it.

## Add a handoff or sync contract

Register a handoff for an actual ownership transfer; this creates a planning dependency and can order workflow waves. Register a sync contract for artifacts that must be revalidated together without imposing ordering. Define source and destination kinds/paths, acceptance, and the responsible lead. Add registry validation and workflow planner/status tests, including stale revisions and cycles where applicable. Never encode a non-ordering relationship as a handoff.

## Add a domain lead skill

Create the skill with `python3 -B scripts/new-skill.py --name <skill> --kind repo --domain <domain> --repos authoring --summary "<text>" --owns-modules <module> --dry-run` (drop `--dry-run` to write; a lead must own a module or drive a contract) and follow the `skill-touchpoints` list. Document owned kinds, quality checks, lifecycle, recovery, optional tools, and handoffs; add its row to the Factory Core skill map and required Claude Code skill inventory. Add domain workflow and eval cases, then run `python3 -B scripts/skill-touchpoints.py <skill>`, `tests/skills-lint.sh`, and the relevant registry, workflow, and routing suites.
