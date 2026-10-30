# art2d integration notes

## CHANGELOG bullets

- Add production 2D art direction, concepts, asset specifications, runtime export records, references, schemas, and image integrity quality rules.
- Replace the 2D Art foundation skill with a production workflow and add valid draft templates and handoff contracts.

## run-all.sh lines

```bash
tests/art2d-workflow.test.sh
```

## Dogfood scenarios

```text
PROMPT: Create a production 2D character sprite specification from the approved art direction and verify its runtime export record.
EXPECT: art-2d leads; creates asset-spec-2d and runtime-export-2d drafts; runs artifact-quality; identifies any human gates.
SHOWS: Single-domain production workflow, asset integrity validation, and no product-repo writes.
HANDOFF: Engineering receives export path, hash, and asset-spec revision through art2d-asset-to-impl.

PROMPT: Use the UI specification for an inventory icon, create its 2D art export record, then plan client import.
EXPECT: ui-ux and art-2d lead in dependency order; source artifact ID/revision is carried to the art handoff and runtime export.
SHOWS: Cross-domain UI → art2d → engineering routing and stale-upstream behavior.
HANDOFF: Engineering imports the verified export through client.unity-assets routing.
```

## Skill touchpoints

The lead remains `art-2d`; no new skill is introduced. Apply these exact table and map updates during lead integration.

### README.md exact text

Replace the art2d diagram row:

```text
art-2d                                 2D art direction, concepts, production specifications and runtime exports
```

Replace the skill map row:

```markdown
| 2D art direction, concepts, asset specifications or runtime exports | `art-2d` | optional `authoring` | `artifact-lint`, `artifact-trace`, `art2d-quality` |
```

### .claude/CLAUDE.md exact text

Keep the existing skill count and replace only the list with:

```text
13 specialised skills: wire-contract, pin-bump, measure, server-realtime, server-services, server-ops,
unity-package, client-integration, game-design, ui-ux, art-2d, art-3d and vfx.
```

The current count stays 13; this domain replaces the foundation skill in place.

### skills/factory-core/references/skill-contract.md exact text

Replace the domain lead sequence in the Layering diagram with:

```text
domain + Engineering leads - game-design; ui-ux -> art-2d -> engineering; art-3d -> vfx -> engineering, server-realtime, server-services, server-ops, unity-package, client-integration
```

The sequence is already present on this base, so no factory-core file change is needed for this integration.

## run-all.sh exact line

```bash
tests/art2d-workflow.test.sh
```

The lead adds this line to `tests/run-all.sh`; it is outside this task's write scope.

- `registry.json`: the requested formal art2d ? UI contract creates a cycle with existing `ui-spec-to-art2d-brief` in domain routing (`domains-routing.test.sh`). Current registry retains the UI ? art2d requirements contract; integrate reverse flow support or make the UI contract directional metadata instead of a graph dependency.

## Shared CORE3 integration dependencies

These are implemented in the concurrent CORE3 task and must arrive in the integrated base before final end-to-end checks:

- `scripts/checks/artifact-quality.py` and `scripts/checks/domains/_api.py`: pass the caller's registered repo roots into plugin context. The art2d plugin consumes `ctx.repo_roots` as an optional fallback so it also works before CORE3 merges; it retains the legacy registry lookup for clean merge compatibility.
- `scripts/factory-workflow.py`: recognize the five art2d kinds and attach their dependency/wave/status behavior. The domain test will exercise the shared planner after this change lands.
- `scripts/lib/tools.py`: advertise optional provider tool names; the adapter itself calls `ctx.tools(name)` via safe attribute access and never makes network calls.

## Shared-file change requests

- No additional shared-file edits are requested from this branch beyond the concurrent CORE3 integration dependencies listed above.
