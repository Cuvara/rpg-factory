# Domains

Domains describe who owns a discipline's artifacts, which registry paths route work to its lead, and which quality and human gates apply. Factory Core reads this information from `registry.json`; the domain lead holds the discipline workflow. See [the multi-discipline architecture](multi-discipline-factory.md#5-domain-ownership-and-skill-classification) and [the shared artifact contract](artifacts.md).

## Domain table

| Domain | Lead | Authoring repo | Artifact kinds | Routing |
|---|---|---|---|---|
| Game Design | `game-design` | Optional `authoring` (`game-authoring`) | `gdd`, `feature-spec`, `design-decision` | `--domain design`, `--kind`, or registered paths under `design/` |
| UI/UX | Planned | Optional `authoring` | UI specifications | `--domain ui` (planned) |
| 2D Art | Planned | Optional `authoring` | Art briefs and asset manifests | `--domain art2d` (planned) |
| 3D Art | Planned | Optional `authoring` | Model, material, rig and LOD manifests | `--domain art3d` (planned) |
| VFX | Planned | Optional `authoring` | Effect specifications and budgets | `--domain vfx` (planned) |
| Engineering | Existing Engineering leads | Product repos | Code, tests, packages and deployment outputs | Existing `--repo` / `--paths` routing |

Planned rows describe the accepted architecture. Only domains registered as active in `registry.json` are routable.

## Game Design

The Game Design domain is native to rpg-factory and has no required external plugin. It owns GDDs, feature specifications, design decisions, feature lifecycle and traceability. The optional `authoring` repo is named `game-authoring`; agents never create or publish it. Until it exists, route and registry checks tolerate its absence, and `game-design` returns the artifact text in the response while stating that the repo is absent.

| Module | Registered path | Purpose |
|---|---|---|
| `authoring.root` | Fallback | Domain lead for authoring files without a narrower owner |
| `authoring.design-gdd` | `design/gdd/` | GDD lifecycle |
| `authoring.design-features` | `design/features/` | Feature specifications and feature state |
| `authoring.design-decisions` | `design/decisions/` | Proposed and accepted design decisions |
| `authoring.approvals` | `approvals/` | Immutable approval records; human-only, agents never write them |

The registered quality gates are `artifact-lint` and `artifact-trace`. `design-review` requires a maintainer to review and accept an artifact before approval; agents never approve their own proposals. `gameplay-rules` is required to bind gameplay values or rules. GDD approval always requires `design-review`; feature-spec approval requires `gameplay-rules` only when `binding_values: true`; design decisions require that gate when accepted binding values are present. Drafts and value-free feature specs need no approval.

During `core-plumbing`, design may draft content and propose values, but numbers remain `TBD` or labelled proposals until verified approval. Engineering may use approved artifacts or existing code, subject to product-repo `TEAM.md` phase rules. Read [artifact lifecycles and approvals](artifacts.md) for schema, trace and trust details.

Feature state may live only in registered authoring paths of a domain with `may_own_feature_state: true`. Product-repo `.ai/`, `docs/registry/` and `docs/features/` remain forbidden, and `.ai/` is never read as configuration. P6 adds registered engineering handoff contracts; P5 leaves the design domain's handoffs empty.
