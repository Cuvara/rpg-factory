# scripts/

One line per entrypoint: purpose, then the suite that covers it (`run-all` = an inline check in
`tests/run-all.sh`). Run Python with `python3 -B`. Behaviour and rules: `.claude/CLAUDE.md`.

## Hook entrypoints (`hooks/hooks.json`, Codex through `codex_hook.py`; advisory only, never block)

- `git-guard.py` - PreToolUse Bash|PowerShell: git, `gh`, process-kill and human-gate advisories. `tests/git-guard.test.sh`, `tests/installed-safety.sh`
- `file-guard.py` - PreToolUse Write|Edit|MultiEdit|NotebookEdit|Read: clone, submodule, generated-path, secret and mode advisories. `tests/file-guard.test.sh`
- `factory_session.py` - PreToolUse Skill: records the execution mode, keeps tech skills behind their leads. `tests/session-state.test.sh`
- `install-status.py` - SessionStart: is the loaded plugin the installed, current version. `tests/install-status.test.sh`
- `codex_hook.py` - Codex hook input mapped onto the guards above (context only). `tests/codex-plugin.test.sh`

## User / agent CLI

- `factory-context.sh` - live snapshot and routing (lead, legs, checks, gates); read-only. `tests/routing.test.sh`, `tests/domains.test.sh`
- `factory-status.py` - pending cross-repo work derived from git (rollout, READY_TO_TAG, pin drift, STALE). `tests/factory-status.test.sh`
- `run-checks.py` - runs and grades registry checks, writes evidence; `--status` regrades. `tests/run-checks.test.sh`
- `factory-cmd.py` - entry point behind the slash commands (`status`, `route`, `check`, `doctor`, `ui*`). `tests/commands.test.sh`, `tests/ui-commands.test.sh`
- `factory-workflow.py` - plan, status, dispatch and report registry-routed artifact workflows. `tests/workflow.test.sh`

## Checks (`checks/`, read-only evidence scripts)

- `artifact-lint.py` - artifact metadata and schema validation. `tests/artifacts.test.sh`
- `artifact-trace.py` - artifact revisions, trace coverage, signed approvals. `tests/artifacts.test.sh`, `tests/artifact-quality.test.sh`
- `artifact-review.py` - git identity and SSH signature helpers for the artifact checks. `tests/artifact-quality.test.sh`
- `artifact-quality.py` - aggregates artifact checks and the domain plugins. `tests/artifact-quality.test.sh`
- `domains/*.py` - per-domain quality plugins (`_api.py` contract; design, ui, art2d, art3d, vfx, noop). `tests/artifact-quality.test.sh`, `tests/<domain>-workflow.test.sh`
- `asset-manifest.py` - asset manifest records against registered repos. `tests/asset-manifest.test.sh`
- `registry-ownership.py` - cross-domain ownership and handoff invariants. `tests/handoff-e2e.test.sh`
- `english-only.py` - English-only content policy (`--enforce`). `tests/english-only.test.sh`, `tests/skills-lint.sh`
- `skill-citations.py` - skill `path:line` citations against the integration branches. `tests/skill-citations.test.sh`
- `netcode-headless.sh` - Netcode headless tests without writing into the repo. `tests/netcode-headless.test.sh`
- `wire-parity.sh` - wire-generated and protocol-version contract evidence. `tests/checks-candidate.test.sh`
- `sgl-determinism.py` - ADR-10 determinism budget in Shared.GameLogic. run-all
- `unity-package-pins.py` - local mirror of the client's package-pins CI step plus a `file:` guard. run-all
- `pin-status.py` - client git-URL pins against upstream tags. run-all
- `pin-plan.py` - exact edits for moving one client pin. run-all
- `package-ready.py` - release readiness of a `com.cuvara.*` package repo. run-all

## Maintenance (plugin repo only)

- `build-registry.py` - builds `registry.json` from `registry/` fragments (`--check`, `--split`). `tests/registry-fragments.test.sh`
- `check-registry.sh` - registry structure and that every named path exists. `tests/check-registry.test.sh`
- `changelog.py` - `changelog.d/` fragments: check, preview, release assembly. `tests/changelog.test.sh`
- `release-check.py` - read-only release gate (versions, changelog, tag, clean tree). `tests/release-check.test.sh`
- `new-skill.py` - scaffolds a skill and its registry entry. `tests/new-skill.test.sh`
- `skill-touchpoints.py` - every place a skill must appear. `tests/new-skill.test.sh`, `tests/skills-lint.sh`

## Libraries

- `lib/` - `context.py` + `resolve.jq` (routing engine), `evidence.py`, `fstate.py` (state paths), `devtools.py`,
  `tools.py`, `registry_src.py`, `shells.py`, `pluginroot.py`, `codexconfig.py`, `compat.sh` and `gitcfg-guard.sh`
  (sourced by tests). `tests/routing-properties.test.py`, `tests/compat.test.sh`, `tests/devtools.test.sh`, `tests/git-env-isolation.test.sh`
- `ui/` - UI plan engine (`ui_plan.py`, data in `ui/data/`), `ui_catalog.py`, `ui_select.py`, `figma_env.py`.
  `tests/ui-commands.test.sh`, `tests/ui-catalog.test.sh`, `tests/ui-skill-routing.test.sh`, `tests/ui-figma-env.test.sh`
- `adapters/` - optional domain tool adapters (`art2d/provider.py`, `art3d/blender-stats.py` run inside Blender,
  `vfx/unity.py`). `tests/art2d-workflow.test.sh`, `tests/art3d-workflow.test.sh`, `tests/vfx-workflow.test.sh`
