# 3D Art domain foundation

## Responsibility and boundary

3D Art owns briefs and delivery records for models, materials, rigs and animation. Engineering owns engine import, runtime integration, performance implementation and client repository files; `client-integration` retains `client.unity-assets` until a later ownership plan moves it. External DCC files are referenced through manifests.

## Inputs and outputs

Inputs are feature/design references and art direction. Outputs are `art3d-brief` and `art3d-asset` artifacts under `art3d/`; asset records use the shared asset-manifest schema and name a delivery path within a registered repository.

## Artifacts and lifecycle

Kinds: `art3d-brief`, `art3d-asset`. Both use the shared lifecycle; asset records additionally pass `asset-manifest` validation.

## Quality gates and handoffs

Run shared `artifact-lint`, `artifact-trace`, and `asset-manifest` for asset records. Art3D assets hand off to VFX as references and to engineering for import/integration. Human review decides visual acceptance and rights questions.

## Deliberate exclusions and readiness

This foundation does not include production workflows, modeling or animation tooling, pipelines, or asset generation. Readiness: **foundation**.
