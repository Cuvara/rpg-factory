# Architecture overview

How the rpg-factory plugin fits together and where things live. Moved from `.claude/CLAUDE.md`; the rules for changing the repo stay there.

## How it fits together

- **Routing:** `factory-context.sh` → `lib/context.py` collects git state per repo (worktree-aware) and
  pipes it through `lib/resolve.jq` over `registry.json`. Output: touched modules, dependents, contracts,
  lead / co-leads / legs / follow-ups, checks by tier (fast / extended / external), and human gates. The lead
  is deterministic: contract driver, then repo-kind driver, then primary owner, then secondary owner. Ties
  break on `skills.<name>.order`. Unmapped files fall back to `<repo>.root`.
- **Validation:** `run-checks.py` runs registry checks and grades them (PASS / FAIL / BLOCKED / NOT_AVAILABLE /
  HUMAN_REQUIRED / SKIPPED / NOT_RUN / STALE). Evidence is keyed by tree identity and written through
  `lib/evidence.py`. `--status` regrades that evidence without running checks.
- **Derived state:** `factory-status.py` covers rollout stage, READY_TO_TAG, pin drift, uncommitted work and
  STALE evidence. Nothing is stored; it re-derives everything from git each time.
- **Hooks** (`hooks/hooks.json`): every command ends with `; exit 0` (bash and PowerShell both accept it): exit 2
  is Claude Code's blocking code and python exits 2 on a missing script, so a missing or broken script must never
  block; stdout still passes through (run-all tests both).
  - SessionStart: `install-status.py --session` (never tracebacks; malformed plugin records mean no advisory).
  - PreToolUse Bash|PowerShell: `git-guard.py`.
  - PreToolUse Write|Edit|MultiEdit|NotebookEdit|Read: `file-guard.py`.
  - PreToolUse Skill: `factory_session.py --skill`, which records the execution mode and keeps `kind: tech` skills behind
    their leads without blocking: requested before factory-core, the call is auto-corrected to factory-core
    (`updatedInput`, once per session); before one of its `used_by` leads, it runs with a `high` advisory. Each advisory
    is logged to the session's `ADVISORIES` file (tests, dogfood). Both guards import `factory_session` for the mode.
  - No PostToolUse hooks.
- **Slash commands** (`commands/*.md`: status, route, check, doctor, workflow, pipeline, ui, ui-figma, ui-components, ui-screen,
  ui-review, assetgen) call `scripts/factory-cmd.py` and are covered by `tests/commands.test.sh`; the `ui*` verbs run
  `scripts/ui/ui_plan.py` (read-only UI plan; data in `scripts/ui/data/`), covered by `tests/ui-commands.test.sh`;
  `assetgen` forwards the read-only verbs of `scripts/assetgen/assetgen.py` (asset-gen engine, `tests/assetgen.test.sh`).
- **Skills:** `factory-core` (references: git-safety, report, repos, validation, skill-contract, parallel-work, engineering, workflows) routes to
  14 specialised skills: wire-contract, pin-bump, measure, server-realtime, server-services, server-ops,
  unity-package, client-integration, game-design, ui-ux, art-2d, art-3d, vfx and asset-gen. 12 tech skills (`kind: tech`: dotnet-gameserver, go-backend,
  unity-client-tech, unity-dots, netcode-client, the UI skills ui-orchestrator, ui-component-selection, ui-figma-import,
  ui-toolkit-screen, ui-validation, comfyui, and comfy-desktop-setup) own no module, are never routed, and appear as `routing.tech` for their `used_by`;
  a registry `paths` list narrows that to matching changed files (the UI skills: UXML/USS/TSS and UI folders; comfyui: `assetgen/`), and the
  snapshot's Next line loads the UI skills through `ui-orchestrator`, whose UI plan names the subset
  (`docs/architecture/ui-skills.md`). `delivery` (kind `core`, generic: the two-level delivery flow, agent routing, review,
  QA tiers and the plan/verdict/gate pipeline for any repository, in any project; one reference, `delivery.md`) owns no module and is never
  routed; factory-core steps 6, 7, 11 and 12 load it, and `factory-pipeline.py --registry none` reads its `pipeline-defaults.json`.
- **Delivery pipeline:** `factory-pipeline.py` (settings: registry `pipeline`; plan schema
  `docs/schemas/pipeline-plan.schema.json`, a task lead's subplan `docs/schemas/pipeline-subplan.schema.json`; verdicts under the persistent state dir `pipeline/<plan id>/`) prints Orca
  or Agent dispatch commands and grades READY_FOR_PR; it never runs agents, pushes or creates worktrees. A repo with
  `worktrees: false` (Unity project) never gets a worktree: tasks run in sequence in the main checkout. Two levels
  (run lead, one task lead per task worktree) as in `skills/delivery/references/delivery.md` section 1 (RPG specifics:
  `parallel-work.md`). Every dispatch carries `--model/--effort` from the
  registry `pipeline.models` policy (`lib/model_policy.py`; `delivery.md` section 10 "Model choice").
- **Dev tools:** registry `dev_tools[]` → `lib/devtools.py` probes (PATH, TCP services, MCP server and
  plugin names only - never config values) → snapshot "Tools for this change" and doctor "Dev tools".
  Every non-core skill's `## Tools` names exactly its `used_by` tools (skills-lint).

## CI

`.github/workflows/tests.yml` runs `--no-workspace --no-claude` only; workspace checks (registry paths, facts, pins,
wire parity, live context) run locally with `tests/run-all.sh --workspace-only`.

- **`plan` job:** `scripts/ci-plan.py` (which calls `tests/affected.py`) selects the suites a change affects; anything
  unsure (no base, an error, changed CI plumbing) plans every suite.
- **`suite` matrix:** one job per `{suite, os}`: every suite on `ubuntu-24.04`, plus `windows-2025` for the suites named
  in `tests/ci-windows-suites.txt`. A job runs every case of its suite through `tests/run-all.sh --only-suites`.
- **Inline checks:** `tests/run-all.sh --inline-only` on both OSes, also when no suite is selected.
- **`ci-ok`:** the single required check; it fails when any needed job failed or was cancelled and passes when the
  matrix is skipped because nothing is affected.
- **Full run:** `workflow_dispatch` with `full=true` (the default) runs every suite; releases use it (`docs/releasing.md`).

## Layout

- `AGENTS.md` (Codex entry: points here, Codex-only notes) - `.claude-plugin/` manifests (Codex: `.codex-plugin/`, `.agents/plugins/`, `docs/codex.md`) - `skills/` - `commands/` - `agents/` (read-only plugin agent `factory-explorer`, auto-discovered) - `scripts/` (index: `scripts/README.md`; + `lib/`, `checks/` read-only evidence
  scripts, `ui/` read-only UI plan engine, catalog, selection and Figma environment check) - `hooks/hooks.json` - `tests/` (+ `fixtures/`) - `evals/` - `docs/registry.schema.json`
