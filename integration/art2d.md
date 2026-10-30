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

The lead skill remains `art-2d`; shared skill maps and touchpoint references require integration edits in factory-core, skill-contract, README, `.claude/CLAUDE.md`, routing tests, dogfood, and evals. These files are outside this worker's allowed write set. Run `python3 -B scripts/skill-touchpoints.py --all` after lead integration updates.

- `registry.json`: the requested formal art2d ? UI contract creates a cycle with existing `ui-spec-to-art2d-brief` in domain routing (`domains-routing.test.sh`). Current registry retains the UI ? art2d requirements contract; integrate reverse flow support or make the UI contract directional metadata instead of a graph dependency.

## Shared-file change requests

- `scripts/checks/artifact-quality.py`: pass registered repo roots from `--repos` into `Context`; current `Context` exposes only the authoring root and registry metadata, so plugin cannot verify a file stored in the registered client repo. Until integrated, the plugin's export file check reports a clear failure when the target root is unavailable.
- `scripts/checks/domains/_api.py`: extend `Context` with `repo_roots: dict` sourced from artifact-quality's existing `--repos` mapping; domain plugins can then safely resolve exported file paths against caller-supplied registered repo roots.
- `scripts/factory-workflow.py`: accept `art-direction-2d`, `concept-2d`, `asset-spec-2d`, `runtime-export-2d`, and `reference-2d` workflow targets and map their authoring paths. Current planning does not generalize artifact node kinds to domain kinds, so the example plan requires this shared extension.
- `scripts/lib/tools.py`: add generic MCP provider discovery for optional image-generation providers (`game-art-mcp`, `ai-pixel-art-image-generation`, arbitrary MCP image tools). Current detector only handles a few binaries and Pillow; absent tools should remain optional.
- `scripts/checks/artifact-quality.py`: discover `.artifact.json` files, or document/use `.md` strict JSON front matter templates consistently. Current discovery misses `.artifact.json` only if suffix naming differs from target authoring convention.
