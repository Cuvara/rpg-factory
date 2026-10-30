# Art3D integration notes

## Changelog bullets

- Added production 3D art artifact kinds, per-kind schemas and draft templates for art direction, models, materials, rigs, animation, and delivery.
- Added standard-library glTF/GLB production validation and optional Blender scene-statistics inspection for DCC formats.
- Replaced the foundation art-3d lead workflow with production steps, review criteria, recovery, evidence, and explicit VFX/Engineering handoffs.

## `tests/run-all.sh` lines

Add this single test invocation to the suite list:

```bash
tests/art3d-workflow.test.sh
```

## Dogfood scenarios

```text
PROMPT: Produce a production-ready 3D hero prop from the approved design artifact; define model and material requirements, deliver the asset record, and prepare the VFX handoff.
EXPECT: Routes to art-3d; asks for/references upstream artifact ids and revisions; uses schema-valid drafts; reports GLB geometry, material, UV, texture, naming, export, and deliverable checks; leaves visual acceptance with a human reviewer.
SHOWS: Single-domain production authoring, plugin results, draft/review lifecycle, and report additions.
HANDOFF: approved art3d asset record to VFX at authoring:vfx/specs/.

PROMPT: Turn the approved 3D asset record into an engine import in the client Assets tree and expose a mesh reference for a VFX spec.
EXPECT: Workflow plan orders art-3d before Engineering and VFX, carries artifact ids/revisions, routes client Assets work to Engineering, and does not let art-3d edit runtime/client files.
SHOWS: Cross-domain handoff graph, workflow waves, ownership boundaries, and stale-input recovery.
HANDOFF: art3d-asset-to-impl to client:Assets/; art3d-asset-to-vfx to authoring:vfx/specs/.
```

## Eval case

Input: a draft `asset-3d` artifact whose GLB exists but exceeds its per-LOD triangle budget and omits a required texture.
Expected: the schema passes, production quality fails with both concrete reasons, no handoff is declared production-ready, and the report names the artifact id and revision.

## README, CLAUDE, and Factory Core table text

README skill list: change `art-3d (3D art foundation)` to `art-3d (production 3D art workflow)`.
`.claude/CLAUDE.md` specialized skills list: retain `art-3d` and describe it as the production workflow for 3D specifications and delivery.
Factory Core table: no text change; it already routes domain work and owns the shared validation/report lifecycle.

## Shared-file changes requested

Add `tests/art3d-workflow.test.sh` to `tests/run-all.sh` after the domain/workflow tests. The test is domain-scoped and independently runnable; keeping the suite entry in the integration step preserves the parallel-work ownership boundary.

Add the art3d production workflow entry below to `docs/architecture/domains.md` under 3D Art:

```diff
-| 3D Art | `art-3d` | Optional `authoring` | `art3d-brief`, `art3d-asset` | `--domain art3d`, `--kind`, or `art3d/` paths |
+| 3D Art | `art-3d` | Optional `authoring` | `art-direction-3d`, `model-spec`, `material-spec`, `rig-spec`, `animation-spec`, `asset-3d` (plus legacy aliases) | `--domain art3d`, `--kind`, or `art3d/` paths |
```

Existing cross-domain architecture table mentions art-3d as a lead; it needs no technical change. The integration lead should add the three changelog bullets above under `[Unreleased]` and update README/CLAUDE skill descriptions as noted.
