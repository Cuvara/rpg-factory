# UI/UX domain foundation

## Responsibility and boundary

UI/UX owns information architecture, user flows, interaction behavior, accessibility criteria and interface specifications. Engineering (`client-integration`) implements UI in the Unity client and owns `client.unity-assets` and its engine-ready files until a later plan explicitly moves that ownership. UI/UX describes intended behavior; it does not implement UI code or change client assets.

## Inputs and outputs

Inputs are approved or draft design `feature-spec` artifacts and relevant constraints. Outputs are `ui-flow` and `ui-spec` artifacts under `ui/`. A UI specification may hand visual requirements to `art2d-brief` and client implementation paths to engineering.

## Artifacts and lifecycle

Kinds: `ui-flow`, `ui-spec`. Both use the shared artifact front matter and default lifecycle (`draft`, `review`, `approved`, `superseded`). No domain-specific lifecycle or approval evidence is introduced here.

## Quality gates and handoffs

Use shared `artifact-lint` and `artifact-trace`; asset delivery checks apply only to registered asset manifests. The feature-spec-to-ui-spec contract feeds UI/UX; `ui-spec-to-art2d-brief` and `ui-spec-to-client` describe downstream work. Maintainer acceptance remains a human decision where required by lifecycle policy.

## Deliberate exclusions and readiness

This foundation does not include production workflows, design or prototyping tools, usability research operations, tooling integrations, or UI/art generation. Readiness: **foundation**.
