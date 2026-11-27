# Recipe format, ops, build and apply, texture import

Source: UnityVFX `Documentation~/AUTHORING.md`, sections "Recipe: build and apply", "Texture import" and
"Differences from DESIGN.md" (items 21-33), and `Schemas~/vfx-recipe.schema.json` (`cuvara.vfx-recipe/1`). When
this page and those disagree, they win: re-read them, and `catalog` prints the formats as the build reads them
(`recipe_ops`, `recipe_op_fields`, `texture_steps`, `texture_step_fields`).

## Top level

| Field | Required | Meaning |
|---|---|---|
| `schema` | yes | `"cuvara.vfx-recipe/1"`; anything else fails before any op runs |
| `id` | yes | kebab-case effect id (`chain-lightning`), the id a `VfxLibrary` entry and `VfxPlayer.Play` use; CI `check_recipes.py` enforces the pattern |
| `vfx_graph` | no | the VFX Graph major.minor written for; another installed one is a warning |
| `meta` | no | `duration_seconds`, `looping`, `tags`, `phases` (`name`, `seconds`); not read by `build`, read by capture and lint |
| `ops` | yes | run in order; the first failing op stops the build |

An unknown top-level or op field is an error. For the `vfx` lead's `/rpg-factory:vfx-lint`, `meta.tags` carry
`element:<name>` and `tier:<primary|secondary|ambient>`, and `meta.phases` use `anticipation`, `impact`,
`dissipation` summing to `duration_seconds` (`scripts/vfx/vfx_lint_rules.py` docstring and `PHASES`, `TIERS`).

## Ids and slot addresses

- Every created node has a recipe-local `id` (`^[A-Za-z_][A-Za-z0-9_-]*$`, unique); blocks have their own ids.
- `apply` starts from the ids `describe` prints (`c0`, `c0.b1`, `o2`, `p0`); new nodes may not reuse one.
- A slot is `<id>.<slot path>` (`init.bounds.center`, `burst.Count`, `tint._Color`); an unnamed slot (math operator
  output) is `<id>.#<index>`; `<id>.out` is the only output of a node with exactly one (a parameter's `o`).
- `link_slots` goes from an output slot to an input slot; `set_slot` and `slots` maps address input slots or a
  parameter's value.

## Ops

| Op | Required | Optional |
|---|---|---|
| `add_parameter` | `id`, `type`, `name` | `value`, `exposed` (default true), `category`, `tooltip` |
| `add_context` | `id`, `type` | `variant`, `label`, `settings`, `slots` |
| `add_block` | `id`, `context`, `type` | `variant`, `settings`, `slots` |
| `add_operator` | `id`, `type` | `variant`, `settings`, `slots` |
| `set_setting` | `node`, `name`, `value` | |
| `set_slot` | `slot` | `value`, `space` (`None`, `Local`, `World`) |
| `link_slots` | `from`, `to` | |
| `link_flow` | `from`, `to` | `from_slot`, `to_slot` (default 0) |
| `use_subgraph` | `id`, `asset` | `context` (required for a `.vfxblock`, refused otherwise), `slots` |
| `set_output` | `node` | `texture`, `blend_mode`, `color_mapping`, `gradient` |
| `comment` | `text` | `title` |

- **`type`** is the catalog `type` (`VFXSpawnerBurst`) or `type_full`; **`variant`** a catalog `variant.id`
  (`Spawn/Single Burst`, `Context/#2Output Basic/Output Particle|Unlit|Quad`). Without `variant` a type with several
  entries (`SetAttribute`, `AttributeFromCurve`) gets its field defaults and `settings` pick the attribute.
- **`settings` run before `slots`**: a setting can change the slots (`attribute` turns `_Lifetime` into `_Color`,
  `Random` gives `A` and `B`).
- **Values:** enums by name (flags `"A, B"` or a list); `Vector2/3/4` arrays; `Color` `[r, g, b(, a)]`, HDR above 1
  allowed, linear; `Gradient` `{"mode", "color_space", "color_keys": [{"t", "color"}], "alpha_keys": [{"t",
  "alpha"}]}` (at most 8 keys each); `AnimationCurve` `[[t, v], ...]` or `{"keys": [...], "pre_wrap", "post_wrap"}`;
  VFX structs as objects of their fields (`{"center": [0, 1, 0], "size": [4, 4, 4]}`), a one-field struct also as
  that value. A map changes only the fields it names.
- **Asset values** (texture slot, `Texture2D` parameter, `set_output` `texture`): a project path (`Assets/...`,
  `Packages/com.cuvara.vfx/...`), `{"guid": ...}` or `{"path": ...}`; a missing asset or wrong type is an error.

## Graph shapes the VFX Graph samples use

From AUTHORING.md "What Unity's sample graphs show": a system is `VFXBasicSpawner` -> `VFXBasicInitialize` ->
`VFXBasicUpdate` -> one or more outputs, joined by `link_flow`. A burst is `VFXSpawnerBurst` (`repeat` `Single` or
`Periodic`, `Count`, `Delay`); a rate is `VFXSpawnerConstantRate` (`Rate`). GPU events are slot links (`TriggerEvent`
`evt` -> a `VFXBasicGPUEvent` context). Colour over life is `AttributeFromCurve` (`attribute` `color`, `SampleMode`
`OverLife`, `Composition` `Multiply` in an output). Blend is the output setting `blendMode` (`Opaque`, `Alpha`,
`Additive`, `AlphaPremultiplied`); an additive quad is `VFXPlanarPrimitiveOutput` with an `Orient` `FaceCameraPlane`.

## Worked example

`Tests/Fixtures/BurstQuads/BurstQuads.vfxrecipe.json`: an exposed `Color` parameter `Tint`; spawner with a single
burst of 24; Initialize with `capacity` 32, `boundsMode` `Manual` and a 4 m box, lifetime `Random` `Uniform`
0.6-0.9, velocity `Random` `PerComponent`; Update; an unlit quad output with `Orient`, a `color` block fed by
`p_tint.out -> tint._Color`, colour over life, `set_output` `blend_mode` `Additive`; three `link_flow` ops.
Copy its shape, not names from memory.

## What build and apply do

Check the recipe -> create the graph in `Assets/CuvaraVfxBuildTemp/` (`apply` copies the asset there) -> bring it to
the current graph and resource versions before the first op -> run the ops through the bridge -> compile in memory,
re-import, collect node, log and shader errors (any error stops; the real asset is untouched; a logged graph
upgrade is an error for `build`) -> copy over `<Name>.vfx`, keep its `.meta` (`guid_stable`). Payload: `recipe_sha256`,
`recipe_id`, `asset`, `ops_applied`, `compile_errors`, `created`, `guid_stable`, `previous_sha256`, `sha256`,
`describe_sha256`, `systems`, and `op_error` (`index`, `op`, `message`, `valid_names`) on failure.

Subgraphs (`use_subgraph`): `.vfxoperator` -> operator `VFXSubgraphOperator`, `.vfxblock` -> block in `context`
(its `m_SuitableContexts` must allow it), `.vfx` -> context `VFXSubgraphContext`; `slots` are the subgraph's
exposed parameters. Create subgraph assets in the graph window or with `VfxGraphBridge.GraphEdit.CreateSubgraph`.

## import-texture

Arguments: `source` (PNG, absolute allowed), `target` (`.png` inside the project or the package), `transform`
(ordered steps, a name or `{"step": name, ...}`).

| Step | Parameters | Does |
|---|---|---|
| `luminance_to_alpha` | `color`: `keep`, `white`, `unpremultiply` | alpha = Rec. 709 luminance; `unpremultiply` turns an image on black into straight alpha |
| `premultiply` | none | RGB times alpha |
| `pack_channels` | `r`, `g`, `b`, `a` | each channel from a constant or `{"file", "channel"}` (`r`, `g`, `b`, `a`, `luminance`) |
| `resize_pot` | `max_size` | nearest power of two per axis, then halve to `max_size`; integer box filter |
| `flipbook` | `columns`, `rows` | records and checks the frame grid; moves no pixel |
| `wrap` | `u`, `v` or `mode` | `repeat` or `clamp` (default clamp) |
| `linear` / `srgb` | none | import as data (masks, noise, flow) or as colour (default) |

Resize straight-alpha colour after `premultiply`, or the transparent black darkens the edges. Same source and
transform give the same `output_sha256`. Import settings: Default texture, mip maps, bilinear, `npotScale` `None`
(a non-power-of-two size is a warning), compressed, not readable. A failed write restores the previous PNG and
`.meta`. Record `source_sha256` (the approved generation) and `output_sha256` (the game texture) in the delivery
record.
