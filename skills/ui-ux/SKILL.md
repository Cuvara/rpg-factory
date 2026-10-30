---
name: ui-ux
description: Use when authoring or reviewing production UI/UX requirements, information architecture, screens, components, tokens, and handoffs. Not for Unity implementation, artwork, icons, or effects.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*)
---

# UI/UX production workflow

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. Respect the active Factory mode.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** production UI requirements, information architecture, screens, components, design tokens, and UI engineering handoffs.
- **Not when:** implementing Unity code, scenes, prefabs, art, icons, or effects; route those to engineering, art2d, or VFX.

## Start and inputs

1. Start with `/rpg-factory:workflow` for multi-domain work, or run `factory-context.sh --domain ui` for a UI-only task. Follow the routed lead and path.
2. Read upstream design `feature-spec` and any relevant `vfx-spec` by artifact ID and revision. Record exact IDs in `sources` and revisions in `upstream`; request missing goals, player constraints, engine paths, or effect behavior instead of inventing them.
3. Set stable artifact IDs, `schema_version: 2`, `authors`, `sources`, and a domain-specific `spec`. Use the matching `templates/ui/<kind>.md` as a valid draft.

## Production steps by artifact kind

1. `ux-requirements`: identify users, goals, and task flows from upstream design.
2. `ia-map`: list screens, choose an entry screen, and connect every screen with a reachable navigation graph.
3. `design-tokens`: define named color, typography, spacing, radius, elevation, and motion tokens. Reference token names elsewhere; never inline token values there. Use `an explicit unresolved value or labelled proposal for gameplay-relevant numbers.
4. `component-spec`: describe component variants, props, states, accessibility, and token references.
5. `screen-spec`: describe purpose, layout regions, components, navigation, platforms or breakpoints, bindings by known design/engineering IDs, five required states, and per-element interaction and accessibility contracts. Mark a state not applicable only with a reason.
6. `ui-handoff`: map screen IDs to testable acceptance criteria and exact registered client engine paths. Send illustrations/icons to art2d and effect dependencies to VFX through registered contracts.

## Rules and handoffs

- Deliver outputs as stable UI artifact IDs/revisions. Design inputs arrive from `feature-spec`; engineering receives `ui-handoff` and screen specs; art2d receives visual briefs; VFX dependencies remain explicit in both directions.
- Do not invent binding data, identifiers, or paths. For unknown gameplay values, state that the value is unresolved or label it as a proposal pending design approval. Mark concept and production readiness explicitly in the artifact status/title when relevant.
- Figma is optional. Checks never call network APIs. A Figma reference requires a file key and node ID; visual verification remains `HUMAN_REQUIRED` without attached screenshot/export evidence. Structured specs work without Figma.

## Validation delta

Run CORE artifact lint/trace and `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py <repo> --registry ${CLAUDE_PLUGIN_ROOT}/registry.json --domain ui`. Read each plugin check by name: screen states, interaction/accessibility, reference integrity, navigation graph, responsive/platform declaration, handoff acceptance, token format, and Figma adapter state. `FAIL` requires correction; `NOT_AVAILABLE` explains optional tooling absence; `HUMAN_REQUIRED` needs human visual review. Also run workflow `plan` and `status` for multi-artifact work and address stale upstream revisions.

## Scope

Repo `authoring`; registered UI artifact paths. Do not write engine-ready client files.

## Validation checks

Use CORE artifact lint and trace checks plus the UI plugin.

## Review checklist

- IDs and upstream revisions are current; schemas and lifecycle transitions pass.
- Every screen has all five states or reasoned exceptions; each interactive element has trigger, result, feedback, error path, and accessibility fields.
- Component/token references exist, navigation is reachable, platform behavior is explicit, and handoff criteria are testable against screen IDs and registered paths.
- Tokens use valid color formats and nonnegative numeric scales. Independent reviewer checks consistency with design and product constraints.

## Human gates

Independent review, approval, gameplay binding, and visual acceptance remain human decisions; agents never create approval records.

## Failure and recovery

- Rejected artifacts recover through a new draft revision, then normal proposal and review. Never jump lifecycle states.
- Missing upstream data blocks authoring of affected bindings; record `blocked_by` and a reason. Refresh `upstream` revisions and revalidate after source changes.
- Request independent review before reviewed status. Approval, gameplay binding, and visual acceptance remain human decisions; agents never create approval records.

## Report additions

Report artifact IDs/revisions, upstream sources, plugin results and any `NOT_AVAILABLE`, `HUMAN_REQUIRED`, or `BLOCKED` outcomes, downstream contracts, stale dependencies, and unresolved human gates.

## Tools

Use registered Factory workflow/context and artifact-quality tools. Figma is optional and is not required for authoring or checks.
