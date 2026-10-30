# Game Design production workflow

Game Design owns production artifacts under the registered authoring modules. Read [artifact lifecycle and quality](../artifacts.md) and [routing contracts](../routing.md) for shared behavior.

## Kinds and lifecycle

The domain owns `game-concept`, `gameplay-system`, `feature-spec`, `level-spec`, `quest-spec`, `npc-spec`, `item-spec`, `gdd`, `design-decision`, and `technical-handoff`. Every artifact uses stable ids, `schema_version: 2`, authors, sources, and a kind-specific `spec`. Versioned schemas live in `docs/schemas/kinds/`; draft templates are in `templates/design/`. Lifecycle v2 is registered per kind. Drafts progress through proposed and independently reviewed to approved; rejected and blocked work recovers to draft. Binding gameplay values require the human `gameplay-rules` gate.

## Production sequence

1. Capture audience, pillars, genre, platforms, USP and constraints in a game concept.
2. Author one gameplay system per system type, including its core loop, mechanics, progression, interaction/combat, economy, difficulty and meta progression.
3. Write features and level, quest, NPC/enemy and item specs against resolving concept/system ids. Integrate production decisions into the GDD and record changes as design decisions.
4. Prepare technical handoffs with state/data, events, edge cases, testable acceptance criteria and registered engineering dependencies.
5. Run Core artifact schema, lifecycle, dependency, trace and approval checks plus `scripts/checks/domains/design.py`. A production artifact is ready when checks pass, sources are current and required human gates are complete.

## Domain quality and tools

Gameplay numbers are `TBD` or labelled proposals (`value`, `status: proposal`, `rationale`) unless the artifact declares `binding_values: true` and the shared verifier confirms approval for its current revision. Verified approval lets the numbers pass the design quality rule. Missing approval is `HUMAN_REQUIRED`; invalid or untrusted approval fails with the verifier's reasons. Agents never create approvals. Economy specs declare currencies and non-empty sources and sinks. Declared difficulty curves are monotonic. Content references resolve to existing artifact ids. Technical handoffs cover state, events, edge cases and acceptance criteria with verify types, and dependencies route through registered modules or repository paths. Optional balancing CSVs need no external program; no tool is required for the core workflow.

## Handoffs

`feature-spec-to-impl` remains supported. `gameplay-system-to-ui` routes systems to UI authoring; `technical-handoff-to-engineering` routes implementation requirements; `design-to-art2d` and `design-to-art3d` route content briefs; `gameplay-event-to-vfx` routes event effects. The workflow graph schedules these contracts by domain.

## Example

```json
{"schema_version":2,"id":"GD-system-001","kind":"gameplay-system","domain":"design","status":"draft","title":"Combat","authors":[{"kind":"agent","id":"game-design"}],"sources":["GD-concept-001"],"upstream":[],"acceptance":[],"trace":[],"spec":{"system_type":"combat","core_loop":"TBD","mechanics":["TBD"],"progression":["TBD"],"combat_interaction":["TBD"],"economy":{"currencies":["TBD"],"sources":["TBD"],"sinks":["TBD"]},"difficulty_balancing":["TBD"],"meta_progression":["TBD"]}}
```
