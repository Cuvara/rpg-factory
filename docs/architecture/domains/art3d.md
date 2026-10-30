# 3D Art production workflow

## Responsibility and readiness

The `art3d` domain owns production specifications and the delivery record for 3D assets. It is production-ready when every required deliverable passes schema, lifecycle, trace, and domain quality checks and an independent human reviewer accepts the visual result. Engineering owns client import settings, runtime integration, and files under the client `Assets/` tree. VFX consumes approved mesh/material references.

## Artifact kinds

Every artifact uses stable ids, `schema_version: 2`, `sources`, `authors`, upstream id/revision pairs, acceptance criteria, trace, and a kind-specific `spec`. Templates in `templates/art3d/` are schema-valid drafts.

| Kind | Payload |
|---|---|
| `art3d-brief`, `art-direction-3d` | Visual direction, palette, references, constraints; the first kind remains a compatibility alias. |
| `model-spec` | Topology, per-LOD polygon budget, UV requirements, naming, scale, units, pivot, scene/rig requirements. |
| `material-spec` | Material assignments and texture maps, resolution, format, colour space. |
| `rig-spec` | Skeleton and root-bone naming, units, scale, deformation policy. |
| `animation-spec` | Clips, fps, looping, root motion and duration. |
| `asset-3d`, `art3d-asset` | File and SHA-256, format, LODs, collision/physics, textures, export settings, engine constraints and required deliverables. `art3d-asset` remains a compatibility alias. |

Each kind uses the shared lifecycle v2 state graph and kind-specific schema-complete proposal requirements. Rejected artifacts recover through a new draft; blocked artifacts require a reason and blocker ids; upstream revision changes require revalidation. No shortcut may skip review, approval, or evidence requirements.

## Production sequence

1. Start one-domain work with `factory-context.sh --domain art3d`; use `/rpg-factory:workflow` when design, UI, VFX, or Engineering participates.
2. Resolve required upstream artifacts by id and revision. Author art direction and brief first; unknown gameplay-impacting values remain `TBD` or labelled proposals owned by the design authority.
3. Author model, material, rig, and animation specs as needed. State measurable technical requirements and mark irrelevant deliverables explicitly.
4. Create an `asset-3d` record tied to the exported file hash. List every required LOD, collision mesh, texture, and export/integration constraint.
5. Run shared artifact checks and the `art3d` quality plugin. Fix failures; inspect `HUMAN_REQUIRED` and `NOT_AVAILABLE` reasons and gather human evidence where automation cannot decide.
6. Obtain independent visual and rights review, then use only registered human approval gates. Hand the approved asset record to VFX and Engineering with current upstream revisions.

## Quality rules and adapters

The plugin parses glTF JSON and GLB JSON chunks using Python's standard library. It checks triangle counts against per-LOD budgets, required LODs, material indices and presence, UV sets, texture URI files, node names, scene structure, rig/animation presence, file hash/format, export scale/units/up-axis, and required collision/texture/deliverable files. A file's existence alone never passes.

Blender is optional and detected through `scripts/lib/tools.py`. The headless adapter emits scene object, mesh triangle, material, UV, armature, and action statistics for Blend, FBX, and OBJ. Missing Blender is `NOT_AVAILABLE`; timeout or unusable adapter output is `HUMAN_REQUIRED`. The core workflow does not require Blender. Visual quality, rights, and binding gameplay decisions remain human gates.

## Handoffs

`art3d-asset-to-vfx` sends approved mesh and material references from `authoring:art3d/assets/` to `authoring:vfx/specs/`. `art3d-asset-to-impl` sends the approved delivery record from the same source to `client:Assets/`; Engineering owns the import and runtime work. Both require traceable current artifact revisions and the visual review gate.

## Example workflow spec

```json
{"id":"hero-prop","title":"Hero prop","goal":"Produce a production-ready prop","targets":[{"id":"direction","kind":"art-direction-3d","sources":[],"acceptance":["Style approved"]},{"id":"asset","kind":"asset-3d","sources":["direction"],"acceptance":["All LODs and textures validate"]},{"id":"client-import","kind":"implementation","repo":"client","paths":["Assets/Art3D/"],"sources":["asset"],"acceptance":["Asset imports in client"]}],"existing":[]}
```

Plan and inspect with `python3 -B scripts/factory-workflow.py plan|status <spec.json> --authoring <repo>`. A completed production handoff has current artifact revisions, passing automatic checks, resolved human decisions, and an Engineering integration result.
