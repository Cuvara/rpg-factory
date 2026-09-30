# CLAUDE.md - rpg-factory

Claude Code plugin providing Factory Core for the UnityIndie RPG MMO workspace. See README.md.

## Rules for changing this repo

- `registry.json` is the source of truth for module knowledge. Never hard-code module paths,
  commands, or rules in `SKILL.md` or the references - put them in the registry and read them.
- Keep `factory-context.sh`, `factory-status.py` and `scripts/checks/` read-only: no fetch (except
  opt-in `--remote` ls-remote), no writes, no persisted state. State is derived from git.
- `run-checks.py` never runs a check in place when it would write into a product repo; pollution is FAIL.
- Hooks must stay fast (guard + tripwire per command, measured: ~0.17 s read-only, ~0.9 s mutating) and must
  never crash a session. The tripwire only detects; it never repairs.
- The git guard never approves and never crashes a session (errors mean "no opinion"); it denies only tag
  creation/deletion/pushes (incl. `gh api` tag refs, `gh release create`). Every new bypass found gets a
  case in `tests/git-guard.test.sh`. Each human gate regex and the git evaluation must fail independently.
- Every behaviour change gets a test in `tests/` and a `CHANGELOG.md` entry under [Unreleased].
- Before committing: `tests/run-all.sh` must report 0 failed. Report the pass count.
- English only. Conventional Commits (`feat(core): ...`, `fix(guard): ...`, `docs(registry): ...`).
- New or changed skills follow `skills/factory-core/references/skill-contract.md`; `tests/skills-lint.sh`
  enforces the mechanical part. Routing changes need a scenario in `tests/routing.test.sh`.
- **Releases:** bump `VERSION`, `.claude-plugin/plugin.json` and `marketplace.json` together with a
  `CHANGELOG.md` section (run-all checks it). The local directory marketplace loads this checkout in
  place (what is checked out is what sessions run); the install record only updates on a version
  change: `claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory`,
  restart, then `tests/run-all.sh --release` and `tests/dogfood.sh --installed`.
  Never create the tag - the maintainer does (READY_TO_TAG).
- Point-in-time values go in registry `facts[]` with a probe, never in skill prose.
- Registry facts must be verified against the product repos (file paths, CI workflow
  contents, run logs), not copied from docs that may be stale.

## Layout

- `.claude-plugin/` manifests - `skills/<name>/` factory-core + 8 specialised skills
- `scripts/` context (`factory-context.sh` → `lib/context.py` + `lib/resolve.jq` routing), guard, tripwire,
  install-status, run-checks, factory-status, registry check, `checks/` (read-only evidence scripts)
- `hooks/hooks.json` - `tests/` - `evals/` - `docs/registry.schema.json`
