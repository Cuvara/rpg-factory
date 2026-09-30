# CLAUDE.md - rpg-factory

Claude Code plugin providing Factory Core for the UnityIndie RPG MMO workspace. See README.md.

## Rules for changing this repo

- `registry.json` is the source of truth for module knowledge. Never hard-code module paths,
  commands, or rules in `SKILL.md` or the references - put them in the registry and read them.
- Keep `factory-context.sh` read-only: no fetch, no writes, no persisted state.
- The git guard never approves and never crashes a session (errors mean "no opinion"); it denies only tag
  creation/deletion/pushes. Each human gate regex and the git evaluation must fail independently.
- Every behaviour change gets a test in `tests/` and a `CHANGELOG.md` entry under [Unreleased].
- Before committing: `tests/run-all.sh` must report 0 failed. Report the pass count.
- English only. Conventional Commits (`feat(core): ...`, `fix(guard): ...`, `docs(registry): ...`).
- New or changed skills follow `skills/factory-core/references/skill-contract.md`; `tests/skills-lint.sh`
  enforces the mechanical part. Routing changes need a scenario in `tests/routing.test.sh`.
- Registry facts must be verified against the product repos (file paths, CI workflow
  contents, run logs), not copied from docs that may be stale.

## Layout

- `.claude-plugin/` manifests - `skills/<name>/` factory-core + 8 specialised skills
- `scripts/` context, guard, registry check, `lib/resolve.jq` (routing), `checks/` (read-only evidence scripts)
- `hooks/hooks.json` - `tests/` - `evals/` - `docs/registry.schema.json`
