# VFX domain foundation

## Responsibility and boundary

VFX owns effect behavior specifications and delivery records. Engineering owns runtime implementation, client integration, performance profiling and engine-ready client files; `client-integration` retains `client.unity-assets` until a later plan moves it. VFX specifies intent and budgets without authoring runtime code.

## Inputs and outputs

Inputs are design feature specs and 3D asset references. Outputs are `vfx-spec` and `vfx-asset` artifacts under `vfx/`; asset records use the shared asset-manifest schema and registered-repository delivery paths.

## Artifacts and lifecycle

Kinds: `vfx-spec`, `vfx-asset`. Both use the shared lifecycle; asset records additionally pass `asset-manifest` validation.

## Quality gates and handoffs

Run shared `artifact-lint`, `artifact-trace`, and `asset-manifest` for asset records. Art3D references and VFX specifications hand off to engineering for implementation. Human review decides readability and artistic acceptance.

## Deliberate exclusions and readiness

The exact client asset folders are decided by the per-domain production plans. This foundation does not include production workflows, VFX tools, effect generation, implementation pipelines or runtime authoring. Readiness: **foundation**.
