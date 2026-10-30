# VFX production workflow

## Responsibility and readiness

VFX owns effect art direction, gameplay-facing behavior specifications, and delivery records. Engineering owns runtime integration and engine-ready client paths. Readiness: **production**.

## Kinds and lifecycle

`vfx-direction` records visual intent and constraints. `vfx-spec` records purpose, gameplay event triggers, lifecycle phases and total duration, normalized animation curves, particle systems, materials, platform budgets and constraints, and UI/audio synchronization dependencies. `vfx-asset` records engine, delivered asset path and hash, checks, and per-platform measured or declared statistics. Each kind has a versioned schema under `docs/schemas/kinds/` and uses the shared lifecycle v2 states and transitions; VFX verification requires implementation trace plus delivery evidence.

All records retain stable IDs, `schema_version`, `sources`, `authors`, and the shared artifact envelope. Templates under `templates/vfx/` start as schema-valid drafts. Concept values remain proposals or `TBD` until approved upstream.

## Quality rules

The CORE quality aggregator applies shared envelope, schema, lifecycle, trace, approval, and staleness checks. `scripts/checks/domains/vfx.py` adds event reference, phase sum, curve ordering/range/numeric, complete platform budget, particle maximum, UI/audio dependency, asset budget, and verified-delivery evidence checks. A verified spec requires a linked asset record with checks; a VFX Graph asset always requires human visual/performance review.

## Adapters

`scripts/adapters/vfx/unity.py` reads a supplied Unity project prefab's YAML text and `.meta` GUID, extracting ParticleSystem maximum particles, lifetime, looping, and duration. It never launches the Editor. Missing project/assets return `NOT_AVAILABLE`; VFX Graph appearance and runtime performance return `HUMAN_REQUIRED`. The optional Unity Editor detector is report-only, and the core workflow never depends on Unity.

## Handoffs

- Design supplies gameplay event IDs and approved timing intent through `design-event-to-vfx`.
- Art3D supplies mesh/asset references through `art3d-asset-to-vfx`.
- UI and VFX resolve cue synchronization references through `ui-vfx-sync`.
- VFX sends approved specs and delivery records to Engineering through `vfx-spec-to-impl`, with destination resolved by path routing.

## Example production spec

```json
{
  "purpose": "Proposal: short impact burst",
  "triggers": ["approved-event-artifact-id"],
  "duration_seconds": 0.4,
  "phases": [{"name": "burst", "duration_seconds": 0.4}],
  "curves": [{"property": "intensity", "keyframes": [{"time": 0, "value": 0}, {"time": 1, "value": 1}]}],
  "particle_systems": [{"id": "sparks", "max_particles": 12, "lifetime_seconds": 0.3, "spawn_per_second": 40}],
  "materials": [],
  "platforms": {"desktop": {"budget": {"max_particles": 16, "max_overdraw": 1.2, "max_draw_calls": 2, "max_ms": 0.2}, "constraints": []}},
  "platform_constraints": [],
  "dependencies": [{"id": "UI-hit-cue-001", "kind": "ui", "status": "tbd"}]
}
```
