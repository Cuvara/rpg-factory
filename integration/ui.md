# UI integration notes

CHANGELOG bullets:
- Add production UI/UX artifact schemas, draft templates, quality rules, workflow guidance, and registry handoffs.

Exact run-all.sh line:
- `bash tests/ui-workflow.test.sh`

Dogfood scenarios (tests/dogfood.sh format):
- PROMPT: Draft a production inventory screen from the approved feature spec and route it to client UI.
- EXPECT: UI requirements, navigation, screen specification and ui-handoff artifacts have stable IDs, five states, interaction/accessibility contracts and testable acceptance criteria.
- SHOWS: Use `factory-workflow.py plan/status`; show validation results from artifact-quality.
- HANDOFF: ui-ux -> client-integration through ui-spec-to-client.
- PROMPT: Add a status screen with a visual icon and a success animation, based on the crafting feature spec.
- EXPECT: UI screen and handoff records include the icon brief and VFX dependency with no invented data bindings.
- SHOWS: Route design input, UI artifact checks, and downstream handoff graph.
- HANDOFF: game-design -> ui-ux -> art-2d and vfx, then engineering.

Eval case: none.

README / CLAUDE.md / factory-core table text if skills changed:
- UI/UX: production workflow for ux-requirements, ia-map, screen-spec, component-spec, design-tokens and ui-handoff; optional Figma, CORE UI quality plugin.

Shared-file changes required:
- None.

Registry handoff limitation:
- The UI/VFX edge is not registered as a `kind: handoff`. Adding `ui -> vfx` changes the existing exact workflow wave contract (`tests/workflow.test.sh`, which expects UI and VFX siblings); adding the reverse edge creates a cycle. The UI specs can still name VFX artifact IDs/revisions in `sources`/`upstream`. A future scoped or non-ordering dependency contract in CORE is needed before an executable UI/VFX edge can preserve existing workflow semantics.
