# UI/UX production workflow

## Ownership and artifacts

UI/UX owns `ui-flow`, `ui-spec` and production kinds `ux-requirements`, `ia-map`, `screen-spec`, `component-spec`, `design-tokens`, and `ui-handoff`. Each production kind uses schema version 2, stable artifact metadata (`id`, `sources`, `authors`, `upstream`) and a kind-specific `spec`. The `templates/ui/` skeletons are valid starting drafts.

## Lifecycle

All production kinds reuse lifecycle v2. Drafts may be proposed only with complete schemas and acceptance criteria; reviewed requires an independent review record; approvals are immutable human gates; verified/released need trace evidence. Rejected artifacts recover to draft. UI artifacts do not bypass lifecycle checks.

## Quality rules

`scripts/checks/domains/ui.py` implements CORE's `check(artifact, ctx)` interface. It checks five screen states, interaction and accessibility contracts, known component/token references, reachable navigation, declared platform/breakpoint behavior, testable handoff acceptance, and token formats. Figma references are format-checked; visual verification is `HUMAN_REQUIRED` without human inspection. Missing Figma reports `NOT_AVAILABLE` with an explicit explanation; checks perform no network calls.

## Handoffs and workflow

Design `feature-spec` records provide user goals and constraints. UI sends illustration/icon briefs to art2d, screen acceptance and UI handoffs to registered client UI paths, and UI effect dependencies reference VFX artifact IDs/revisions in `sources` and `upstream` through the registered `ui-vfx-sync` contract (`ordering: "none"`): a change on either side marks the other for revalidation without ordering workflow waves. Use `/rpg-factory:workflow` to plan multi-domain work or `factory-context.sh --domain ui` for UI-only work, then validate with CORE artifact checks and `artifact-quality.py`.

## Example

A production `screen-spec` names `screen_id: inventory`, layout regions, component/token IDs, navigation in/out, platforms or breakpoints, all five states, element interaction/accessibility contracts, and data bindings to existing IDs. Its `ui-handoff` entry names that same screen ID, exact target engine paths, and measurable acceptance tests. Readiness: **production**.
