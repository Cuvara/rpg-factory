# 2D Art production workflow

## Boundary and readiness

The `art2d` domain owns style direction, nonbinding concepts, production specifications, reference records, and verifiable runtime export records. Readiness is **production** when runtime exports match their asset specifications and pass the domain plugin; visual quality, rights, and binding gameplay decisions remain human gates. Engineering owns engine import and all product-repository writes.

## Kinds and lifecycle

| Kind | Purpose | Production state |
|---|---|---|
| `art-direction-2d` | Palette, line, shading, proportions, references, naming rules | Shared lifecycle v2 |
| `concept-2d` | Character, environment, prop/item, UI illustration exploration | Draft/proposed/reviewed only |
| `asset-spec-2d` | Purpose, resolution, format, transparency, animation, naming, export targets | Shared lifecycle v2 |
| `runtime-export-2d` | Repo path, SHA-256, dimensions, format, alpha, atlas record | Shared lifecycle v2 |
| `reference-2d` | Source, rights/license, relevance | Draft/proposed/reviewed only |

Legacy `art2d-brief` and `art2d-asset` stay registered and valid. Every record uses stable IDs, schema version 2, source and author metadata, and a kind-specific `spec` validated by its versioned schema under `docs/schemas/kinds/`.

## Workflow and quality

Create direction first, then concepts and specifications. Each asset spec cites an art-direction ID. A runtime export must cite its spec and point to a file in a registered repository. `scripts/checks/domains/art2d.py` rejects concept/reference promotion, requires specs to have runtime exports, verifies PNG/JPEG/WebP headers, SHA-256, dimensions, format, alpha and naming, and checks sprite dimensions and declared atlas constraints. Pillow is optional; unavailable palette inspection returns `NOT_AVAILABLE`. Checks are read-only and never write product repos.

Optional image generation is a concept-only exploration step. Record `{generated_by, tool, model}` provenance and keep generated imagery at draft; availability never gates the normal authoring workflow. References require a rights basis and never qualify as deliverables.

## Handoffs

- UI/UX → 2D Art: `ui-spec` ID/revision through `ui-spec-to-art2d-brief`.
- 2D Art → UI/UX: illustration/icon runtime export IDs and usage constraints through `art2d-illustration-to-ui`.
- 2D Art → Engineering: runtime export IDs, asset spec revisions, and paths under client `Assets/` using `art2d-asset-to-impl` and registered `client.unity-assets` routing. Checks only inspect; engineering performs imports.

## Example workflow spec

```json
{"id":"inventory-icon","title":"Inventory icon","goal":"Produce a verified icon export","targets":[{"id":"direction","kind":"art-direction-2d","sources":[],"acceptance":["Palette follows UI direction"]},{"id":"spec","kind":"asset-spec-2d","sources":["direction"],"acceptance":["Export dimensions and format are fixed"]},{"id":"export","kind":"runtime-export-2d","sources":["spec"],"acceptance":["Hash and image metadata match"]}],"existing":[]}
```

The `/rpg-factory:workflow` plan carries each kind to lead `art-2d`; dependency waves order direction before specification and export. Quality failures block downstream use, changed upstream revisions mark dependents stale, and rejected artifacts recover through a new draft revision. Human review owns artistic acceptance, rights, and binding values.
