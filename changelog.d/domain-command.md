### Added

- **Commands.** `/rpg-factory:domain [<id>] [--json]` (`factory-cmd.py domain`): every registry domain with its lead,
  repos and artifact counts, or one domain with artifact kinds, quality and human gates, handoffs, artifacts by
  status, stale upstreams, FAIL and HUMAN_REQUIRED artifacts and next steps (JSON schema `rpg-factory.domain/1`).
  Read-only and data-driven: a new registry domain needs no code change; an unknown id exits 2 listing the domains.
- **Commands.** `factory-cmd.py help [--json]` lists every verb with its arguments, read-only flag, an example, the
  Claude form (`/rpg-factory:<verb>`) and the Codex form (`python3 -B <plugin root>/scripts/factory-cmd.py <verb>`)
  (JSON schema `rpg-factory.commands/1`); agents and Codex discover the commands there.
- **Commands.** `--json` for `status`, `route` (file and `--domain`/`--kind` forms), `check` (passed to
  `run-checks.py --json`) and `doctor` (`rpg-factory.doctor/1`: install, registry, workspace, repos, tools, hooks,
  dev_tools).

### Changed

- **Docs.** README, `docs/codex.md` and the factory-core "Commands" section list every verb with its Claude and
  Codex form.
