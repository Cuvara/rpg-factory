---
name: vfx
description: Use when planning, specifying, reviewing, or recording production visual effects in the registered VFX authoring domain - the style profile, effect direction and specs, the production loop from approved textures through the engine leg's capture and lint to the human Play-mode review, and the delivery record. Not for implementing engine runtime integration, authoring VFX Graph recipes or editing production assets directly.
argument-hint: "[effect or artifact task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vfx/vfx_style.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vfx/vfx_plan.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/adapters/vfx/*:*)
---

# VFX production

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Respect the active Factory mode.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** the project's VFX style profile, effect direction, trigger and timing specifications, production
  budgets, the production loop of one effect (textures, engine handoff, capture evidence, lint, human review) and the
  delivered effect record.
- **Not when:** writing runtime code, VFX Graph recipes or `.vfx` assets, or authoring engine-ready client paths; that
  is the Engineering leg (`unity-package` with `rpg-factory:vfx-graph`).

## Scope

Use only the routed `authoring` paths `vfx/style/`, `vfx/directions/`, `vfx/specs/` and `vfx/assets/`. Engine files,
recipes, textures in the package and captures stay in paths owned by Engineering; this skill reads their evidence.

## Workflow

1. **Route.** `/rpg-factory:vfx-plan <request>` (or `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vfx/vfx_plan.py`) prints
   the state of the five production steps for one effect, what is missing and the lead of each step;
   `factory-context.sh --domain vfx` (or `--kind vfx-spec`) routes and lists inputs, gates and tools. A NEEDS_CONTEXT
   plan: ask for exactly the missing items. Use `/rpg-factory:workflow` when coordinating dependencies.
2. **Direction (`vfx-direction`):** cite design/art references by artifact ID and revision; set visual language,
   palette, and constraints. Keep unapproved values labelled proposals or explicitly unresolved.
3. **Specification (`vfx-spec`):** identify every gameplay event by the ID of a real design artifact present in the
   authoring repo (or a registered engineering event ID); put that ID in `spec.triggers` and record its current blob
   revision in `upstream` or `sources` using `git hash-object <path>`. An unresolved placeholder in `triggers` fails
   quality checks; when no event source exists, report that blocker instead of writing an invalid placeholder. Define
   total duration and phases, normalized curves, emitters, materials, per-platform budgets and constraints, plus UI/audio
   sync IDs, and name the profile in `spec.style`. Do not invent gameplay binding values; mark unresolved values or
   labelled proposals until upstream approval.
4. **Production loop** of one effect ([references/production-loop.md](references/production-loop.md)), each step
   gated on the one before:
   1. **Style profile.** Read the approved `vfx-style` profile (one live profile per project,
      [references/style-profile.md](references/style-profile.md)); check it with
      `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vfx/vfx_style.py show --style <profile>`. No approved profile: author it
      from `templates/vfx/vfx-style.md` and stop until a person approves it.
   2. **Textures.** Generate effect textures through `rpg-factory:asset-gen` with a vfx purpose (`vfx-flipbook`,
      `vfx-noise-tileable`, `vfx-trail`, `vfx-sprite`) and the profile's `assetgen_style`. **Stop at gate
      `assetgen-approval`:** a person approves each gen-run; then cite each gen-run ID in the spec's `sources`
      (handoff `assetgen-to-vfx`). Invoke `rpg-factory:comfyui` to inspect a run's template, params and returned size.
   3. **Engine handoff.** Hand the approved spec, profile and gen-run IDs (output paths and SHA-256) through
      `vfx-spec-to-impl` to the `unity-package` leg, which invokes `rpg-factory:vfx-graph` to write and build the
      recipe, import the textures and capture the effect at the profile's camera, lighting and seed.
   4. **Evidence, lint, human review.** Consume the leg's capture evidence (`stats.json`, `contact-sheet.png`, the
      inspect result); run the lint (`/rpg-factory:vfx-lint`, or `vfx_style.py lint` with the same arguments) and save
      its JSON as `vfx-lint.json` next to `stats.json`. A FAIL row goes back to step 3. **Stop at gate
      `vfx-visual-review`:** a person judges the effect in Play mode.
   5. **Record.** Write the `vfx-asset` from `templates/vfx/vfx-asset.md` with its `capture`, `style`, `textures` and
      `lint` evidence, the source spec ID and revision; the engine, project-relative asset path, content hash,
      per-platform measured or declared stats and the checks performed.
5. Use the matching skeleton under `templates/vfx/`, retain `schema_version`, `sources`, and `authors`, and author
   valid draft JSON before advancing lifecycle state. Never create approval records.
6. Run artifact schema/lifecycle/trace checks and `artifact-quality.py --domain vfx`; resolve every `FAIL` and rerun
   until none remain. A Shuriken prefab in an available Unity project: `scripts/adapters/vfx/unity.py <project-root>
   <prefab-path>`; a `.vfx` asset: `scripts/adapters/vfx/vfxgraph.py` (both read text only).
7. Request independent review for artistic readability, gameplay legibility, budget suitability, dependency sync, and
   platform limitations.

## Inputs and outputs

- Inputs: design gameplay events (`gameplay-event-to-vfx`), approved gen-runs (`assetgen-to-vfx`), 3D asset IDs
  (`art3d-asset-to-vfx`), and UI/audio cue IDs (`ui-vfx-sync`), each with artifact ID and revision; capture and inspect
  evidence from the `unity-package` leg.
- Outputs: the style profile, direction and effect specification artifacts for design/UI/Engineering; delivery
  records and the runtime integration handoff (`vfx-spec-to-impl`) for Engineering. No engine-ready paths are authored
  by VFX.

## Rules

- Keep concept proposals distinct from approved production values. Mark unresolved requirements explicitly; do not
  turn illustrative values into binding gameplay facts.
- Phase durations must sum to total duration within tolerance. Curve times are normalized, sorted, and numeric. Every
  target platform declares all four budget limits; a spec that names a profile stays inside its budget and timing bands.
- Every game texture traces to an approved gen-run that recorded its output hash; never use an unapproved image.
- A lint result is bound to one recipe, one capture and one profile revision; any of them changes: lint again.
- Unavailable tools or files report `NOT_AVAILABLE`; non-automatable visual/performance review reports
  `HUMAN_REQUIRED`. Never treat either as PASS.
- If upstream revisions change, refresh affected assumptions and references, then rerun checks and review.

## Validation

CORE validates the shared artifact envelope, schema, lifecycle, trace, approvals, and staleness. The VFX plugin checks
event references, timing sums, curves, platform particle maxima, UI/audio dependencies, delivery stats and
verification evidence, and for the production loop `vfx-style-profile`, `vfx-spec-style`, `vfx-asset-capture`,
`vfx-asset-style-lint` and `vfx-asset-textures` (meanings in [references/production-loop.md](references/production-loop.md)).
`FAIL` blocks progression; `NOT_AVAILABLE` means an input/tool is absent; `HUMAN_REQUIRED` needs a documented human
result. Recover rejected work in a new draft revision; resolve blockers and stale upstream references before
resubmission.

## Human gates

- `assetgen-approval`: a person approves each texture gen-run before the effect uses it (step 4.2).
- `vfx-visual-review`: a person judges look, readability, overdraw and frame time in Play mode (step 4.4); these stay
  `HUMAN_REQUIRED` in every check, and agents never record the review.
- A person approves the style profile, the spec and the record; agents do not approve artifacts.

## Review checklist

- [ ] The spec names the approved style profile; its budgets and phase shares sit inside the profile's bands.
- [ ] Trigger IDs and source revisions resolve to approved upstream intent.
- [ ] Timing, normalized curves, emitter limits, materials, and platform constraints match the gameplay purpose.
- [ ] Every texture cites an approved gen-run; its transform and game texture hash are recorded.
- [ ] Capture evidence, the lint result (no FAIL) and the profile revision agree with each other and with the record.
- [ ] UI/audio sync IDs are valid or explicitly unresolved; effect reads clearly at target scale.
- [ ] Asset path/hash and measured stats are recorded and within every declared budget.
- [ ] Both human gates and the Engineering handoff are recorded.

## Report additions

Report artifact IDs/revisions, the style profile ID and blob revision, upstream IDs, gen-run IDs and approval states,
the plan's step states, effect duration and platform budgets, capture stats hash and seed, lint status with FAIL/WARN
rows, validation states, adapter availability, human gates, and Engineering handoff destinations.

## Tools

The VFX lead and the plugin scripts never launch Unity; Unity Editor availability is detected for reporting only.
Only the `unity-package` leg drives the agent-owned UnityVFX Sandbox, through `rpg-factory:vfx-graph`.
