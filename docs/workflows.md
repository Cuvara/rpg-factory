# Production workflows

Production workflows use the shared artifact envelope, lifecycle, domain quality plugins, and registry handoff contracts. Start a single-domain task with its lead skill or `scripts/factory-context.sh --domain <domain>`; use `/rpg-factory:workflow` when work crosses domains.

## Lifecycle and validation

Artifacts progress from `draft` to `proposed`, `reviewed`, `approved`, `verified`, and `released` as their registered requirements are met. Rejected and blocked artifacts recover by creating a new draft revision; blocked records identify the blocker. Reviews record an independent review and are distinct from approvals. Approvals are human decisions tied to the exact artifact blob revision. Binding gameplay values remain `HUMAN_REQUIRED` until a trusted signing key is registered. Validation results are `PASS`, `FAIL`, `HUMAN_REQUIRED`, or `NOT_AVAILABLE`; unavailable tools never produce a pass.

## Plan, dispatch, and report

Create a JSON workflow spec whose `targets` identify artifact kinds, source target IDs, optional repository/path routing, and acceptance criteria. The planner maps kinds through the registry, orders dependency waves from handoff contracts, and treats sync contracts as revalidation links without wave ordering.

```bash
python3 -B scripts/factory-workflow.py plan workflow.json --authoring <authoring-repo>
python3 -B scripts/factory-workflow.py status workflow.json --authoring <authoring-repo>
python3 -B scripts/factory-workflow.py report workflow.json --authoring <authoring-repo>
```

Dispatch ready targets wave by wave. A changed upstream payload revision makes dependent artifacts stale; lifecycle bookkeeping does not change the payload revision. Revalidate stale targets and their sync partners before handing them onward. The integrated report collects planned targets, artifact revisions, quality results, human gates, handoffs, and stale reasons.

## Domain handoffs

Each domain lead authors its registered kinds and prepares the next registered handoff. Game Design's `game-design` hands feature and system artifacts to UI, 2D/3D Art, VFX, and Engineering. `ui-ux` hands screen and UI records to Engineering and illustration briefs to `art-2d`; UI/VFX sync references use the non-ordering `ui-vfx-sync` contract. `art-2d` hands runtime export paths, hashes, and asset-spec revisions to Engineering. `art-3d` hands delivery records to VFX and Engineering. `vfx` hands approved specs and delivery records to Engineering. Engineering owns product-repository implementation and import work.

## Integration scenarios

The examples use the factory workflow CLI for planning, status, and reports. Replace `<authoring-repo>` with the registered authoring repository path when available; authoring is optional.

1. **Game Design only:** draft a `game-concept` and `gameplay-system`, then run `python3 -B scripts/factory-workflow.py plan workflows/design.json --authoring <authoring-repo>`, `python3 -B scripts/factory-workflow.py status workflows/design.json --authoring <authoring-repo>`, and `python3 -B scripts/factory-workflow.py report workflows/design.json --authoring <authoring-repo>`. Leave unapproved numbers as proposals.
2. **UI/UX only:** draft `ux-requirements`, `screen-spec`, and `ui-handoff`; run `python3 -B scripts/factory-workflow.py plan workflows/ui.json --authoring <authoring-repo>`, then matching `status` and `report` commands.
3. **2D Art only:** draft `asset-spec-2d` and `runtime-export-2d`; run `python3 -B scripts/factory-workflow.py plan workflows/art2d.json --authoring <authoring-repo>`, then matching `status` and `report` commands.
4. **3D Art only:** draft `model-spec`, `material-spec`, and `asset-3d`; run `python3 -B scripts/factory-workflow.py plan workflows/art3d.json --authoring <authoring-repo>`, then matching `status` and `report` commands.
5. **VFX only:** draft `vfx-spec` and `vfx-asset`; run `python3 -B scripts/factory-workflow.py plan workflows/vfx.json --authoring <authoring-repo>`, then matching `status` and `report` commands.
6. **Design → UI → Engineering:** link a `gameplay-system` to `ux-requirements` and `screen-spec`, then target an Engineering implementation. Run `python3 -B scripts/factory-workflow.py plan workflows/design-ui-engineering.json --authoring <authoring-repo>`; dispatch each reported wave and run the matching `status` and `report` commands.
7. **Design → 3D Art → VFX → Engineering:** source `art-direction-3d` from the design artifact, source `vfx-spec` from the delivered `asset-3d`, and route implementation to Engineering. Run `python3 -B scripts/factory-workflow.py plan workflows/design-art3d-vfx-engineering.json --authoring <authoring-repo>`, then status/report after each wave.
8. **UI ↔ VFX sync revalidation:** record each side's artifact ID and revision in the sync references. Run `python3 -B scripts/factory-workflow.py status workflows/ui-vfx.json --authoring <authoring-repo>`; after either side changes, revalidate both and run the same command again. Sync does not impose a wave order.
9. **Upstream change makes downstream stale:** update the upstream payload, then run `python3 -B scripts/factory-workflow.py status workflows/downstream.json --authoring <authoring-repo>`; revise and revalidate stale dependents before `python3 -B scripts/factory-workflow.py report workflows/downstream.json --authoring <authoring-repo>`.
10. **Rejected/blocked recovery:** record the review rejection or blocker, create a new draft revision with the issue resolved, then run `python3 -B scripts/factory-workflow.py plan workflows/recovery.json --authoring <authoring-repo>`, followed by `status` and `report`. Never change a rejected artifact directly into an approved state.
