---
name: factory-core
description: Shared Factory workflow for every registered discipline domain in the UnityIndie game workspace (rpg-mmo-server, IndieRPGMMOAdventure, Netcode, UnityDots, UIToolkit and the domains' authoring artifacts). Use at the start of ANY task that changes code, configuration, CI, deployment, measurements, documents or domain artifacts there, when resuming interrupted cross-repo work, and before reporting such work as done. Provides the live snapshot, deterministic domain and skill routing, coordination, validation with evidence, human gates, git safety and the verify-a-result report; domain workflows live with their registered leads. Game Design is a native domain for design artifacts. Not for web-game projects; web-game-factory owns those.
argument-hint: "[mode: analyze|plan|implement|validate|review|resume] [task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py:*)
---

# Factory Core

The Factory workflow for every discipline domain. Engineering is the first domain and keeps its existing behavior. Task: $ARGUMENTS
**Codex:** resolve `${CLAUDE_PLUGIN_ROOT}` as `PLUGIN_ROOT` in hooks, otherwise two directories above this skill's containing directory; use that absolute root for commands and run the live snapshot explicitly. Load routed skills using Codex's skill mechanism (read their `SKILL.md`); Claude's Skill tool and inline shell expansion are unavailable.
**Domains:** use `--domain` / `--kind` for domain entry points; non-engineering leads come from registry `domains`.

## Live snapshot (computed now - uncommitted paths shown are the user's baseline, not routed)

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh`

Domain-specific artifact knowledge belongs to the registered domain lead; Factory Core coordinates the shared workflow.
Module rules, docs, changelogs, generated paths, dependencies, checks, contracts and facts live
in `${CLAUDE_PLUGIN_ROOT}/registry.json`; read them through the scripts, never guess them. If the
header says the install state is not CURRENT, tell the user (this session may run an old copy).

## Mode (decide first, declare it, and keep to it)
`analyze` (what exists, what a change would touch) and `plan` ("don't implement yet"): route, **invoke the lead**,
explain or produce its plan; change nothing. `implement` (build/fix/add; the default): the full workflow below.
`validate`: `run-checks.py --status`, then run the checks; change no files. `review` (a diff or branch): the lead's
review checklist + registry rules; change nothing. `resume`: `factory-status.py`, then the first incomplete step.
Declare it in the skill arguments (`mode: <mode>`) and the Route call (`factory-context.sh --mode <mode> ...`); the
snapshot then prints its contract. The hooks **flag** departures (advisory only, they never block); respect the mode
yourself and switch only when the user asks (e.g. "now implement it").
Two levels (`references/parallel-work.md` sections 1, 8, 10): the main session is the **run lead** (plans, dispatches,
integrates, reports; never edits task files); one **task lead** per task does the work. A dispatched session follows its spec.

## Workflow
Steps are **M** mandatory, **O** optional, **H** need the user.
1. **Resume (M for cross-repo or interrupted work).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py`
   lists pending work derived from the repos (wire rollout stage, READY_TO_TAG packages,
   released-but-unpinned, in-flight `<type>/<area>/<topic>` branches) with the owning skill.
2. **Scope (M).** Name repos and modules; read each touched module's `claude_md`. A task that
   would bind gameplay values without verified approval stops here (**H**, `phase-scope`).
3. **Baseline (M).** Snapshot paths are the user's; never modify, stage, stash, clean, reset or
   commit them unless named. Submodule contents are user state unless the task is about them.
4. **Route (M).** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --mode <mode> --repo <key> --paths <files the task will write>`
   (repo-relative; for a benchmark: the bench harness / `docs/BENCHMARK.md` / results, not the measured code). Run Factory
   scripts with the **absolute path exactly as printed here** (the permission allowlist matches it). Only this call (or
   branch commits) routes the task; the bare snapshot never routes uncommitted baseline paths.
   Then **call the Skill tool with the lead** (`rpg-factory:<lead>`) before planning or editing, in every mode - naming
   it is not enough and reading its `SKILL.md` is no substitute; invoke each routed domain lead for multi-domain work.
   `no specialised lead - factory-core only` means no Skill call. Cross-repo lead, co-leads, legs, follow-ups, tech
   skills, tools, AMBIGUOUS, `--lead`, `--explain`: `references/skill-contract.md` "Routing". Non-engineering or
   cross-domain routes: `references/workflows.md`.
5. **Branch (M).** On a protected branch, create `<type>/<area>/<topic>` from the default branch
   before committing; reuse the **same topic** in every repo of a cross-repo task (factory-status
   links them). Commit, push, PR, merge are **H** (only on request); tags and releases only with the user's
   explicit release authorization in this task (`references/git-safety.md` rule 5).
6. **Plan (M).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py tier -- --repo <key> --paths <files>`, then a
   `plan.json` + `validate` for every tier (S = a one-task plan with its own task lead). Per ready task:
   `factory-pipeline.py dispatch plan.json --task <id> --phase lead --report-to <run id> --runner orca` (one Claude task
   lead per task worktree; Unity: main checkout, in sequence). Resume: `status plan.json`. How: `references/parallel-work.md` section 10.
7. **Implement (M, task lead).** `subplan validate`, then one short, fresh sub-session per subtask
   (`--phase implement --subplan subplan.json --subtask <sid>`; shared worktree or an Orca child per its `placement`:
   parallel-work.md section 4); the task lead commits or merges each. Requested scope only; module rules; generated paths via their generator.
8. **Obligations (M).** CHANGELOG `[Unreleased]` per touched module, docs, regenerated artifacts,
   both sides of contracts, `.meta` files, version bump (no tag unless the release is authorized).
9. **Validate (M).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py --repo <key> --paths <changed files>`.
   The runner executes and grades the checks; its table and evidence are the only acceptable
   evidence. Evidence is bound to the tree it ran on: after any further edit, `--status` shows it
   **STALE** - rerun before reporting. Extended checks: ask the user, then `--approve <check-id>`.
10. **Verify (M).** verify-a-result on every number you report (below).
11. **Review + QA (M, task lead).** On a frozen SHA, `dispatch ... --phase review --sha <sha>`: Codex reviews Claude's
    code and Claude reviews Codex's; Codex unavailable: a fresh Claude session, marked SAME_MODEL (gate: `--allow-same-model`).
    Use the lead's checklist and every `routing.tech` review file (e.g. `unity-dots` ECS checklist); then `--phase qa`.
    Record each `verdict`. The run lead integrates (section 7) and runs QA on the integration HEAD.
12. **Gate, PR, cleanup, report (M, run lead).** `gate` READY_FOR_PR + user's `deliver: pr`: push, open the PR (no merge).
    Remove the run's worktrees, release every Claude/Codex session (section 8), `cleanup` until CLEAN; report
    (`references/report.md`); releases stop at **READY_TO_TAG** unless explicitly authorized.

## Validation states (from run-checks.py)

PASS / FAIL / BLOCKED / NOT_AVAILABLE / HUMAN_REQUIRED / SKIPPED / NOT_RUN / STALE - meanings and when each is done:
`references/validation.md`. Never write PASS yourself; never convert NOT_AVAILABLE / HUMAN_REQUIRED into success.

## verify-a-result (non-negotiable)

Count passes (exit 0 on zero tests is not a pass); prove a zero can be non-zero; name the object a
number describes; write the expected value before running; an absent CI check is not a pass.
Canonical: `IndieRPGMMOAdventure/.claude/skills/verify-a-result/SKILL.md`, `rpg-mmo-server/backend/docs/MEASUREMENT.md`.

## Git safety and human gates

The hooks are **advisory only**: a matching call runs and you receive `rpg-factory advisory (high|warn): <rule>` -
weigh it. `high`: tags, releases, repository deletion; `warn`: destructive or protected-branch git, pushes, `add -A`,
registry `human_gates`, risky file writes. Stage explicit paths only. Policy and full list: `references/git-safety.md`.

## Commands (read-only except `check`; `factory-cmd.py help [--json]` lists every verb with args and an example)
Claude `/rpg-factory:<verb>`, Codex `python3 -B <plugin root>/scripts/factory-cmd.py <verb>`: `status`, `route`, `check`,
`doctor`, `domain`, `workflow`, `pipeline`, `ui*`, `assetgen`, `help`; `--json` for agents. Suggest them for "what is pending", "what would
this touch", "is it validated", "is Factory healthy", "where does this domain stand".

## Skills

Engineering leads (the registry remains authoritative); supporting Engineering skills: `dotnet-gameserver`, `go-backend`, `unity-client-tech`, `unity-dots`, `netcode-client`; UI (client, through `client-integration`, entry `ui-orchestrator`): `ui-orchestrator`, `ui-component-selection`, `ui-figma-import`, `ui-toolkit-screen`, `ui-validation`; asset generation (through `asset-gen` and the art, UI and VFX leads): `comfyui`.

| Situation | Lead skill |
|---|---|
| Game concepts, gameplay systems, production specs and design decisions | `game-design` (optional authoring repo) |
| Production UI/UX requirements, screens, components, tokens and handoffs | `ui-ux` (optional Figma; quality plugin) |
| 2D art direction, concepts, asset specifications or runtime exports | `art-2d` (optional `authoring`; `artifact-lint`, `artifact-trace`, `art2d-quality`) |
| Production 3D art specifications, assets and delivery | `art-3d` (optional Blender; quality plugin) |
| VFX direction, specifications, budgets and delivery | `vfx` (optional Unity; quality plugin) |
| AI image generation (concept, sprite, icon, UI part, texture, 3D reference) through ComfyUI, reviewed and human-approved | `asset-gen` (comfy-mcp, Codex review; `assetgen-quality`) |
| wire message/field, protocol version, JSON encoding, JoinToken claims, Redis servers:id | `wire-contract` (server → Netcode → client) |
| move a client pin (package / sgl tag) or the unity-build-workflows submodule | `pin-bump` |
| C# game server, ECS systems, knobs, metrics, content, Shared.GameLogic | `server-realtime` |
| Go gateway, Nakama RPCs, Redis store, persistence/migrations | `server-services` |
| Docker, compose, k8s/Agones, monitoring, backups, CD; TLS / sealed-transport switches (contract `transport-security`) | `server-ops` |
| Netcode / UnityDots / UIToolkit package code, up to READY_TO_TAG | `unity-package` |
| client VContainer wiring, Nakama/session, HUD/UI, DotsViews, build scripts | `client-integration` |
| benchmark harness (`GameServer.Tests/Bench/`), encoding sweep, re-baseline, multi-client verification | `measure` |

Orientation only, not routing: naming a lead from this table is not doing the task. In every mode, run
Route (step 4) and **invoke** the lead it prints before answering; supporting skills come after the lead.
The Skill hook never blocks: a supporting skill requested before factory-core loads factory-core instead;
one requested before its lead runs with an advisory - then route and invoke the lead. Engineering-specific tool details are in [references/engineering.md](references/engineering.md).

## References - read when
- `references/repos.md` - first time in a repo, unmapped or repo-level paths.
- `references/validation.md` - before running or reporting any check.
- `references/engineering.md` - Engineering repository map, tool evidence and procedures.
- `references/git-safety.md` - before any branch, stage, commit or cleanup.
- `references/report.md` - before the final report (always).
- `references/skill-contract.md` - routing precedence and how skills compose.
- `references/parallel-work.md` - before delegating, dispatching workers or integrating their branches.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
