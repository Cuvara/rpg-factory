---
name: vfx
description: Use when planning, specifying, reviewing, or recording production visual effects in the registered VFX authoring domain. Not for implementing engine runtime integration or editing production assets directly.
argument-hint: "[effect or artifact task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*)
---

# VFX production

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. Respect the active Factory mode.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** Effect direction, trigger and timing specifications, production budgets, and delivered effect records.
- **Not when:** Writing runtime code or authoring engine-ready client paths; hand off to Engineering.

## Scope

Use only the routed `authoring` paths `vfx/directions/`, `vfx/specs/`, and `vfx/assets/`. Keep engine files in paths owned by Engineering.

## Workflow

1. Start with `/rpg-factory:workflow` when coordinating dependencies, or run `factory-context.sh --domain vfx` (or `--kind vfx-spec`) to route and inspect registered inputs and tools.
2. **Direction (`vfx-direction`):** cite design/art references by artifact ID and revision; set visual language, palette, and constraints. Keep unapproved values labelled proposals or explicitly unresolved.
3. **Specification (`vfx-spec`):** identify every gameplay event by upstream artifact ID or existing engineering event ID. Define total duration and phases, normalized curves, emitters, materials, per-platform budgets and constraints, plus UI/audio sync IDs. Do not invent gameplay binding values; mark unresolved values or labelled proposals until upstream approval.
4. **Delivery (`vfx-asset`):** record the engine, project-relative asset path, content hash, per-platform measured or declared stats, and checks performed. Link the source spec ID and revision.
5. Use the matching skeleton under `templates/vfx/`, retain `schema_version`, `sources`, and `authors`, and author valid draft JSON before advancing lifecycle state. Never create approval records.
6. Run artifact schema/lifecycle/trace checks and `artifact-quality.py --domain vfx`. If a Unity project is explicitly available, run `scripts/adapters/vfx/unity.py <project-root> <prefab-path>`; it reads text only. VFX Graph visual and performance review always needs a human.
7. Request independent review for artistic readability, gameplay legibility, budget suitability, dependency sync, and platform limitations. Hand off approved specs/assets to Engineering through `vfx-spec-to-impl`.

## Inputs and outputs

- Inputs: design gameplay events (`design-event-to-vfx`), 3D asset IDs (`art3d-asset-to-vfx`), and UI/audio cue IDs (`ui-vfx-sync`), each with artifact ID and revision.
- Outputs: direction and effect specification artifacts for design/UI/Engineering; delivery records and runtime integration handoff for Engineering. No engine-ready paths are authored by VFX.

## Rules

- Keep concept proposals distinct from approved production values. Mark unresolved requirements explicitly; do not turn illustrative values into binding gameplay facts.
- Phase durations must sum to total duration within tolerance. Curve times are normalized, sorted, and numeric. Every target platform declares all four budget limits.
- Unavailable tools or files report `NOT_AVAILABLE`; non-automatable visual/performance review reports `HUMAN_REQUIRED`. Never treat either as PASS.
- If upstream revisions change, refresh affected assumptions and references, then rerun checks and review.

## Validation

CORE validates the shared artifact envelope, schema, lifecycle, trace, approvals, and staleness. The VFX plugin checks event references, timing sums, curves, platform particle maxima, UI/audio dependencies, delivery stats, and verification evidence. `FAIL` blocks progression; `NOT_AVAILABLE` means an input/tool is absent; `HUMAN_REQUIRED` needs a documented human result. Recover rejected work in a new draft revision; resolve blockers and stale upstream references before resubmission.

## Human gates

Humans decide artistic acceptance, VFX Graph appearance, perceptual quality, and any Unity editor or runtime profiling that cannot be established from text and evidence. Agents do not approve artifacts.

## Review checklist

- [ ] Trigger IDs and source revisions resolve to approved upstream intent.
- [ ] Timing, normalized curves, emitter limits, materials, and platform constraints match the gameplay purpose.
- [ ] UI/audio sync IDs are valid or explicitly unresolved; effect reads clearly at target scale.
- [ ] Asset path/hash and measured stats are recorded and within every declared budget.
- [ ] Required human review and Engineering handoff are recorded.

## Report additions

Report artifact IDs/revisions, upstream IDs, effect duration and platform budgets, validation states, adapter availability, human gates, and Engineering handoff destinations.

## Tools

Unity Editor availability is detected for reporting only; it is never launched.
