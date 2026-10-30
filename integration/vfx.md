# VFX integration notes

## CHANGELOG bullets

- Add production VFX direction, specification, and delivery artifact workflows, domain quality rules, and optional Unity prefab inspection.

## `tests/run-all.sh` lines

```bash
bash tests/vfx-workflow.test.sh
```

## Dogfood scenarios

```text
PROMPT: Create a production VFX spec for the approved combat impact event. Use the design event ID and art references, define timing and platform particle budgets, validate it, and report the Engineering handoff.
EXPECT: Routes to `vfx`; drafts a schema-valid `vfx-spec`; checks trigger IDs, duration sum, normalized curves, per-platform budgets and sync references; reports unresolved values as TBD and requests human review where needed.
SHOWS: skills/vfx/SKILL.md; templates/vfx/vfx-spec.md; scripts/checks/domains/vfx.py
HANDOFF: vfx-spec-to-impl -> Engineering client path

PROMPT: Coordinate a UI hit cue and its matching VFX effect for the same approved gameplay event, then prepare the implementation handoff.
EXPECT: Plans design/UI/VFX dependencies through `factory-workflow.py`; preserves UI and VFX artifact IDs/revisions; checks synchronization references and produces the VFX-to-Engineering handoff.
SHOWS: docs/architecture/domains/vfx.md; registry contracts design-event-to-vfx, ui-vfx-sync, vfx-spec-to-impl
HANDOFF: ui-vfx-sync -> vfx -> Engineering client path
```

## Eval cases

- Verify an unregistered trigger, stale source revision, phase mismatch, unsorted curve, over-budget emitter, unresolved UI dependency, or over-budget asset is reported as FAIL.
- Verify Unity absence is NOT_AVAILABLE and VFX Graph review is HUMAN_REQUIRED; neither may be described as PASS.

## README / CLAUDE / factory-core table text

Add `vfx` to the README's discipline lead list and describe it as owning production effect direction, specifications, budgets, and delivery records; Engineering owns runtime integration. Add VFX production workflow to the factory-core specialized lead list. The `## Skills` table for `factory-core` is the only necessary core prose touchpoint.

## Required shared-file changes

None. The production domain uses the existing artifact-quality plugin interface and `factory-workflow.py` planner/status runner unchanged.
