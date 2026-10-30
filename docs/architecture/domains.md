# Domains

Domains describe who owns a discipline's artifacts, which registry paths route work to its lead, and which quality and human gates apply. Factory Core reads this information from `registry.json`; the domain lead holds the discipline workflow. See [the multi-discipline architecture](multi-discipline-factory.md#5-domain-ownership-and-skill-classification) and [the shared artifact contract](artifacts.md).

## Domain table

| Domain | Lead | Authoring repo | Artifact kinds | Routing |
|---|---|---|---|---|
| Game Design | `game-design` | Optional `authoring` (`game-authoring`) | `gdd`, `game-concept`, `gameplay-system`, `feature-spec`, `design-decision`, `level-spec`, `quest-spec`, `npc-spec`, `item-spec`, `technical-handoff`, `content-spec`, `gameplay-event` | `--domain design`, `--kind`, or registered paths under `design/` |
| UI/UX | `ui-ux` | Optional `authoring` | `ui-flow`, `ui-spec`, `ux-requirements`, `ia-map`, `screen-spec`, `component-spec`, `design-tokens`, `ui-handoff` | `--domain ui`, `--kind`, or `ui/` paths |
| 2D Art | `art-2d` | Optional `authoring` | `art-direction-2d`, `concept-2d`, `asset-spec-2d`, `runtime-export-2d`, `reference-2d` (plus legacy aliases) | `--domain art2d`, `--kind`, or `art2d/` paths |
| 3D Art | `art-3d` | Optional `authoring` | `art-direction-3d`, `model-spec`, `material-spec`, `rig-spec`, `animation-spec`, `asset-3d` (plus legacy aliases) | `--domain art3d`, `--kind`, or `art3d/` paths |
| VFX | `vfx` | Optional `authoring` | `vfx-direction`, `vfx-spec`, `vfx-asset` | `--domain vfx`, `--kind`, or `vfx/` paths |
| Engineering | Existing Engineering leads | Product repos | Code, tests, packages and deployment outputs | Existing `--repo` / `--paths` routing |

## Readiness

| Domain | Domain foundation | Production workflow |
|---|---|---|
| Game Design | Active; registered, routed, contracted and checked | Existing design workflow |
| UI/UX | Active; registered, routed, contracted and checked | Production UI/UX specification workflow |
| 2D Art | Active; registered, routed, contracted and checked | Production 2D art and export workflow |
| 3D Art | Active; registered, routed, contracted and checked | Production 3D art specification and delivery workflow |
| VFX | Active; registered, routed, contracted and checked | Production VFX specification and delivery workflow |

An active domain has registry ownership, routing, handoff contracts, shared checks and a production workflow. Domain details: [UI/UX](domains/ui.md), [2D Art](domains/art2d.md), [3D Art](domains/art3d.md), [VFX](domains/vfx.md).

## Game Design

The Game Design domain is native to rpg-factory and has no required external plugin. It owns GDDs, feature specifications, design decisions, feature lifecycle and traceability. The optional `authoring` repo is named `game-authoring`; agents never create or publish it. Until it exists, route and registry checks tolerate its absence, and `game-design` returns the artifact text in the response while stating that the repo is absent.

| Module | Registered path | Purpose |
|---|---|---|
| `authoring.root` | Fallback | Domain lead for authoring files without a narrower owner |
| `authoring.design-gdd` | `design/gdd/` | GDD lifecycle |
| `authoring.design-features` | `design/features/` | Feature specifications and feature state |
| `authoring.design-decisions` | `design/decisions/` | Proposed and accepted design decisions |
| `authoring.approvals` | `approvals/` | Immutable approval records; human-only, agents never write them |

The registered quality gates are `artifact-lint` and `artifact-trace`. `design-review` requires a maintainer to review and accept an artifact before approval; agents never approve their own proposals. `gameplay-rules` is required to bind gameplay values or rules. GDD approval always requires `design-review`; feature-spec approval requires `gameplay-rules` only when `binding_values: true`; design decisions require that gate when accepted binding values are present. Drafts and value-free feature specs need no approval. The `feature-spec-to-impl` handoff sends feature specifications to server and client engineering paths; the registry dependency graph and downstream invalidation rules are documented in [routing](routing.md).

During `core-plumbing`, design may draft content and propose values, but numbers remain `TBD` or labelled proposals until verified approval. Engineering may use approved artifacts or existing code, subject to product-repo `TEAM.md` phase rules. Read [artifact lifecycles and approvals](artifacts.md) for schema, trace and trust details.

Feature state may live only in registered authoring paths of a domain with `may_own_feature_state: true`. Product-repo `.ai/`, `docs/registry/` and `docs/features/` remain forbidden, and `.ai/` is never read as configuration. P6 registers engineering handoffs and implementation revision traces.
# Optional production providers

Domain plugins can discover these optional provider names through `ctx.tools(name)`:
`game-art-mcp`, `ai-pixel-art-image-generation`, `figma`, `blender`, and `unity`.
Discovery reads names from Claude Code MCP settings, `.mcp.json`, installed plugin
records, or `RPG_FACTORY_TOOL_<NAME>` overrides. Configuration values and credentials
are never returned or printed. Missing providers produce explicit `NOT_AVAILABLE` results.
