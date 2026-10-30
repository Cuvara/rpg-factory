# 2D Art domain foundation

## Responsibility and boundary

2D Art owns briefs and delivery records for sprites, illustrations, textures and 2D animation. Engineering owns engine import, runtime integration and client repository files; `client-integration` retains `client.unity-assets` until a later ownership plan moves it. Art artifacts reference external source files rather than routing to them.

## Inputs and outputs

Inputs are approved or draft `ui-spec` artifacts and art direction supplied by a human or existing artifacts. Outputs are `art2d-brief` and `art2d-asset` artifacts under `art2d/`; asset records use the shared asset-manifest schema and identify delivery paths inside registered repos.

## Artifacts and lifecycle

Kinds: `art2d-brief`, `art2d-asset`. Both use the shared lifecycle; asset records additionally pass `asset-manifest` validation.

## Quality gates and handoffs

Run shared `artifact-lint`, `artifact-trace`, and `asset-manifest` for asset records. UI/UX hands visual requirements to 2D Art; engineering receives delivery/import paths. Human review is responsible for artistic acceptance and rights questions.

## Deliberate exclusions and readiness

This foundation does not include production workflows, art generation, DCC tools, pipelines, or asset creation tooling. Readiness: **foundation**.
