# VFX style profile (`vfx-style`)

The project's one binding description of how its effects look and what they may cost. Every effect spec names it,
the lint grades every effect against it, and the delivery record binds to the revision it was graded against.
Schema: `docs/schemas/kinds/vfx-style.schema.json`; skeleton: `templates/vfx/vfx-style.md`; module
`authoring.vfx-style` (query its path with `factory-context.sh --kind vfx-style`).

## Lifecycle

- One live profile per authoring repo, with `binding_values: true`; a second live profile, or one that does not
  resolve, fails `vfx-style-profile`. Replace a profile through a new revision, not a sibling file.
- It is binding, so it needs a person's approval record before any effect counts as graded against it
  (vfx-plan step `style` stays NEEDS_APPROVAL until then). Agents never write that record.
- `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vfx/vfx_style.py show --style <profile>` prints the resolved profile
  (`rpg-factory.vfx-style/1`) with defaults filled in. It is the same reader the lint and the quality check use, so a
  profile that `show` rejects fails every downstream step. Exit 3 means the file is missing or not a profile.
- A profile change makes every recorded lint of it STALE: its `vfx-asset` records carry the old `style.blob_revision`
  (`git hash-object <profile>`), and `vfx-asset-style-lint` FAILs until the effect is linted again.

## Fields (spec body)

| Field | What it binds | Graded by lint rows |
|---|---|---|
| `purpose` | the game, art direction and effects the profile covers | none (review) |
| `assetgen_style` | asset-gen style id the effect textures are generated with | none (asset-gen step) |
| `vfx_graph` | VFX Graph `major.minor` every recipe and capture targets | `vfx-graph-version` |
| `palette` | `hue_tolerance_degrees`, `elements.<name>.colors` (`#RRGGBB`) and `ramp` | `palette` |
| `hdr_intensity` | `primary`, `secondary`, `ambient` bands (`min`/`max`, log2 of the largest channel) | `hdr-intensity` |
| `timing` | `anticipation`, `impact`, `dissipation` share bands of the duration; `sum_tolerance_seconds` | `timing-sum`, `timing-ratios` |
| `textures` | `max_size`, `flipbook_grids`, `channel_packing`, `color_space`, `linear_textures` | `texture-size`, `texture-flipbook-grid`, `texture-color-space` |
| `outputs` | allowed output context `types`, `blend_modes`, `shaders` (globs) | `output-type`, `blend-mode`, `shader` |
| `budgets` | per platform id: `max_alive_particles`, `max_systems`, `max_texture_memory_bytes` | `budget-capacity`, `budget-alive`, `budget-systems`, `budget-texture-memory` |
| `capture` | `camera` (`gameplay`, `close`, `side`), `lighting` (`day`, `dusk`, `night`), `seed` | `capture-conditions` |
| `notes` | free text | none |

The remaining lint rows (`recipe-schema`, `recipe-hash`, `spec-match`) check the recipe and its spec, not a profile
field. Each row is PASS, FAIL, WARN or NOT_AVAILABLE (its optional input is absent); the row ids come from
`scripts/vfx/vfx_lint_rules.py`.

## How an effect meets the profile

- The recipe names its element and tier in `meta.tags` as `element:<name>` and `tier:primary|secondary|ambient`;
  without them `palette` and `hdr-intensity` FAIL. The element must be a key of `palette.elements`.
- The spec names the profile id in `spec.style`; `vfx-spec-style` then checks the spec's platform budgets and phase
  shares against the profile before any engine work starts. A platform the profile does not budget is a WARN.
- Textures are generated with `assetgen_style` and imported within `textures` (size, grid, colour space); the
  capture uses exactly the `capture` camera, lighting and seed, or `capture-conditions` FAILs.

## Writing one

Start from the skeleton, replace its placeholder purpose, derive palette, ramps and HDR bands from the approved art
direction (cite it in `upstream`), and set budgets for every target platform the game ships. Values not yet approved
stay labelled proposals in `notes`; the profile goes to review only when `show` resolves it and
`artifact-quality.py --domain vfx` reports no FAIL.
