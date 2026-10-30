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

## Workflow spec and CLI reference

Write a JSON workflow spec with an `id`, `title`, `goal`, `targets`, and `existing` artifact IDs. Each artifact target names a registered kind, sources by artifact ID, and acceptance criteria. Engineering targets use `kind: "implementation"`, a registered `repo`, and repo-relative `paths`.

```json
{"id":"crafting","title":"Crafting","goal":"Add crafting","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["Recipe can be crafted"]},{"id":"server","kind":"implementation","repo":"server","paths":["backend/gameserver-dotnet/"],"sources":["design"],"acceptance":["Crafting is implemented"]}],"existing":[]}
```

Plan and inspect the resulting dependency waves:

```sh
python3 -B scripts/factory-workflow.py plan workflow.json --authoring /path/to/game-authoring
```

Dispatch nodes in wave order; independent nodes in a wave can run in parallel. Dispatch refuses a node with exit 2 until its dependencies are usable. The `print`, `orca`, and `agent` runners all include only artifact IDs and current blob revisions, output paths, allowed paths, checks, and acceptance criteria; they never paste artifact contents. Add `--json` to emit the dispatch contract as JSON. Contracts identify artifacts by ID and current working-tree blob revision. Run status as artifacts land, then produce the integrated report:

When artifacts already exist, their `upstream` and `sources` artifact IDs determine the wave order. Ordered domain handoff contracts provide fallback ordering for planned nodes without artifact references; they do not override the order recorded by written artifacts. A cycle in artifact references, or among contract-ordered planned nodes, is reported as `CYCLE`. Contracts with `ordering: "none"` remain synchronization links and never order waves.

```sh
python3 -B scripts/factory-workflow.py status workflow.json --authoring /path/to/game-authoring
python3 -B scripts/factory-workflow.py dispatch workflow.json --node design --authoring /path/to/game-authoring
python3 -B scripts/factory-workflow.py report workflow.json --authoring /path/to/game-authoring
```

Status reports each node's lifecycle (`missing`, `draft`, `proposed`, `reviewed`, `approved`, `in-implementation`, `verified`, `released`, `rejected`, `blocked`, `stale`, or `human-required`), ready nodes, stale upstream references, and downstream nodes to revalidate in wave order. A rejected artifact is recoverable by authoring a new draft revision, then proposing it again. An absent dependency blocks dispatch. Approval is verified from signed approval results returned by artifact quality; a missing trusted signature is `human-required` and cannot produce a complete report.

Reports include artifact revisions, quality checks, reviews, approval results, and engineering implementation trace entries checked against `--repos key=path` repositories. A report is complete only when every workflow node is `verified` or `released` and none is stale, blocked, or human-required. Output contracts are documented in `docs/schemas/workflow-{plan,status,dispatch,report}.schema.json`.
