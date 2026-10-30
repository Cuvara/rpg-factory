# Integration notes for Game Design production workflow

- CHANGELOG: `feat(design): add production artifact workflow, schemas, templates and domain quality checks`
- `tests/run-all.sh`: add `tests/design-workflow.test.sh` after `tests/domains.test.sh`.
- Dogfood single domain: `PROMPT: Draft a production game concept and combat gameplay-system artifact with a proposed damage value. EXPECT: Valid version 2 draft artifacts, stable ids, upstream link, and proposal rationale; no approval is created. SHOWS: game-design workflow, artifact schemas, gameplay-number rule. HANDOFF: feature/system output available to UI and engineering.`
- Dogfood cross domain: `PROMPT: Turn an approved gameplay system into UI flow and engineering technical handoff. EXPECT: Workflow plan has design before UI and engineering, handoff acceptance includes verify types and dependency routes. SHOWS: gameplay-system-to-ui and technical-handoff-to-engineering contracts. HANDOFF: ui-ux and engineering.`
- Eval case: production game design numbers remain TBD/proposal without gameplay-rules approval.
- README/CLAUDE/factory-core table text: add Game Design production kinds and mention production workflow readiness.
- Shared file requested: `tests/workflow.test.sh` has a pre-production expected wave assertion that cannot reflect the newly registered design-to-art3d handoff. In the ?handoff graph produces ordered waves? assertion, replace `assert p["waves"]==[["art3d","design"],["ui","vfx"],["art"],["impl"]]` with `assert p["waves"]==[["design"],["art3d","ui"],["art","vfx"],["impl"]]`. The edge `design -> art3d` is required by `design-to-art3d`; the current test stops at this now-stale expectation. I did not edit the shared test.
