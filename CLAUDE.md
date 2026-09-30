# CLAUDE.md - rpg-factory

Claude Code plugin providing Factory Core for the UnityIndie RPG MMO workspace. See README.md.

## Rules for changing this repo

- `registry.json` is the source of truth for module knowledge. Never hard-code module paths,
  commands, or rules in `SKILL.md` or the references - put them in the registry and read them.
- Keep `factory-context.sh` read-only: no fetch, no writes, no persisted state.
- The git guard must never deny, never approve, and never crash a session. Errors mean "no opinion".
- Every behaviour change gets a test in `tests/` and a `CHANGELOG.md` entry under [Unreleased].
- Before committing: `tests/run-all.sh` must report 0 failed. Report the pass count.
- English only. Conventional Commits (`feat(core): ...`, `fix(guard): ...`, `docs(registry): ...`).
- Registry facts must be verified against the product repos (file paths, CI workflow
  contents, run logs), not copied from docs that may be stale.

## Layout

- `.claude-plugin/` manifests - `skills/factory-core/` skill + references
- `scripts/` context, guard, registry check, `lib/resolve.jq`, `checks/`
- `hooks/hooks.json` - `tests/` - `evals/` - `docs/registry.schema.json`
