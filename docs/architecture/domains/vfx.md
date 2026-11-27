# VFX production workflow

## Responsibility and readiness

VFX owns effect art direction, gameplay-facing behavior specifications, and delivery records. Engineering owns runtime integration and engine-ready client paths. Readiness: **production**.

## Kinds and lifecycle

`vfx-direction` records visual intent and constraints. `vfx-style` is the project's one binding style profile (module `authoring.vfx-style`, authoring `vfx/style/`): palette and colour ramps per element, HDR intensity bands per importance tier, phase timing ratios, texture conventions, allowed outputs, blend modes and shaders, per-platform budgets, the capture viewing conditions and the asset-gen style the effect textures are generated with; `scripts/vfx/vfx_style.py show` prints it resolved and `lint` grades one effect against it. `vfx-spec` records purpose, gameplay event triggers, lifecycle phases and total duration, normalized animation curves, particle systems, materials, platform budgets and constraints, UI/audio synchronization dependencies and, optionally, the `style` profile id it is graded against. `vfx-asset` records engine, delivered asset path and hash, checks, per-platform measured or declared statistics and the optional production evidence: `capture` (stats.json SHA-256, seed, alive peak, contact sheet SHA-256), `style` (profile id and the git blob revision of the profile file the lint graded), `textures` (per game texture: the approved gen-run id, its output SHA-256, the named import-texture transform and the game texture SHA-256) and `lint` (state and the SHA-256 of the `rpg-factory.vfx-lint/1` result). Each kind has a versioned schema under `docs/schemas/kinds/` and uses the shared lifecycle v2 states and transitions; VFX verification requires implementation trace plus delivery evidence.

All records retain stable IDs, `schema_version`, `sources`, `authors`, and the shared artifact envelope. Templates under `templates/vfx/` start as schema-valid drafts. Concept values remain proposals or `TBD` until approved upstream.

## Quality rules

The CORE quality aggregator applies shared envelope, schema, lifecycle, trace, approval, and staleness checks. `scripts/checks/domains/vfx.py` adds event reference, phase sum, curve ordering/range/numeric, complete platform budget, particle maximum, UI/audio dependency, asset budget, and verified-delivery evidence checks. A verified spec requires a linked asset record with checks. The style profile and the production evidence add:

| Check | Kind | Grades |
|---|---|---|
| `vfx-style-profile` | vfx-style | the profile resolves with `vfx_style.py` (the lint's own reader), carries `binding_values: true`, and no other live (not rejected, superseded or deprecated) vfx-style profile exists |
| `vfx-spec-style` | vfx-spec with `style` | the profile resolves; per platform the profile also budgets, `max_particles` and the particle-system maxima stay within `max_alive_particles` and the system count within `max_systems` (a platform the profile does not budget is a WARN); each anticipation, impact and dissipation phase share is inside its band |
| `vfx-asset-capture` | vfx-asset | `capture` is well formed and, when its `stats.json` (found by SHA-256 under a `Captures/` folder at a registered repo root or one level below, such as `Sandbox~/Captures`) is present, equal to it in seed, alive peak and contact sheet hash; a `.vfx` asset without capture evidence is `HUMAN_REQUIRED` |
| `vfx-asset-style-lint` | vfx-asset with `style`/`lint`, or whose spec names a style | the lint is bound to the current git blob revision of the profile file and to the capture's stats hash: the lint result found next to the capture (by `report_hash`) must name the same status, profile and recipe as the capture, and `vfx_style.py lint` recomputed on the bound profile, recipe and capture must give the same status and row states. A mismatch is FAIL; a capture or lint result that is not found (pass the effect's repo with `--repos <repo>=<path>`) is NOT_AVAILABLE; missing evidence for a spec that names a style is a WARN at draft and a FAIL past draft |
| `vfx-asset-textures` | vfx-asset with `textures` | every game texture names a gen-run that is approved (status approved or later) with a verified `assetgen-approval`, recorded its `output_hash` among its outputs and used the profile's `assetgen_style`; a missing or unapproved gen-run is a WARN while the asset is draft, rejected, blocked, superseded or deprecated and a FAIL past draft; an output hash the gen-run did not record always FAILS |

The look, readability, overdraw and frame time of an effect always stay `HUMAN_REQUIRED` (`vfx-graph-visual-verification` for a `.vfx` asset, `vfx-visual-review` for any other): human gate `vfx-visual-review`, a person judges them in Play mode and agents never record that review.

## Human gates and the Sandbox exemption

`domains.vfx.human_gates` lists `vfx-visual-review`. The Unity gates `unity-batch` and `unity-asset-edit` cover the user's Unity projects; the agent-owned UnityVFX `Sandbox~` project (module `unityvfx.sandbox`) is exempt, so agents open, build, capture and test effects there without asking. The wording changed, not what the gates match.

## Showcase event ids

`domains.vfx.engineering_event_ids` holds `vfx.showcase.chain-lightning` and `vfx.showcase.ground-slam`: the triggers of the UnityVFX `Samples~/Showcase` scene, which a vfx-spec may cite as triggers. They are showcase triggers, not gameplay bindings (`engineering_event_descriptions`).

## Adapters

`scripts/adapters/vfx/unity.py` reads a supplied Unity project prefab's YAML text and `.meta` GUID, extracting ParticleSystem maximum particles, lifetime, looping, and duration. It never launches the Editor. Missing project/assets return `NOT_AVAILABLE`; VFX Graph appearance and runtime performance return `HUMAN_REQUIRED`. The optional Unity Editor detector is report-only, and the core workflow never depends on Unity.

## Handoffs

- Design supplies gameplay event IDs and approved timing intent through `design-event-to-vfx`.
- Art3D supplies mesh/asset references through `art3d-asset-to-vfx`.
- UI and VFX resolve cue synchronization references through `ui-vfx-sync`.
- VFX sends approved specs and delivery records to Engineering through `vfx-spec-to-impl`, with destination resolved by path routing: client `Assets/` or the UnityVFX package's `Effects/` (module `unityvfx.effects`, one folder per effect with its recipe, built `.vfx`, prefab and textures; `unityvfx.library` holds shared pieces and `unityvfx.samples` the Showcase).
- Asset generation supplies approved texture gen-runs through `assetgen-to-vfx`; the `vfx-asset` `textures` evidence traces each game texture to one.

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
