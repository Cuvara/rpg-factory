# Review checklist for a VFX Graph effect

For a review of an effect change in UnityVFX (`Effects/<Name>/`, a fixture, a subgraph) or of the capture evidence
a `vfx/assets/` record cites. Each item names where the fact comes from. The lead (`unity-package` or `vfx`) grades
the result and owns the gates; the person's Play-mode review (gate `vfx-visual-review`) is never replaced by this list.

## Source and build

- [ ] The recipe is the change: `<Name>.vfx` differs only because its recipe changed, and no `.vfx`, `.prefab` or
      `.meta` YAML was written by hand (`Effects/README.md`; registry rules of `unityvfx.effects`).
- [ ] Layout and names: `Effects/<Name>/` in PascalCase, recipe `id` kebab-case, textures `<Name>_<Purpose>.png`,
      shared pieces in `Library/` (`Effects/README.md`).
- [ ] The recipe validates against `Schemas~/vfx-recipe.schema.json` and every type, variant, setting and slot name
      is a `catalog` name (an unknown name is a build error, not a warning).
- [ ] The build result is `ok` with no `compile_errors` and no `compile:` warnings (a `Recorded` bounds warning means
      `boundsMode` was left at its default); `guid_stable` true for an existing asset.
- [ ] Graph identity is checked by `describe_sha256` (build, inspect, capture's recipe), not by the `.vfx` file hash.

## Graph

- [ ] Each system is spawner -> Initialize -> Update -> output(s) with flow links; `capacity` and `boundsMode`
      (`Manual` with a box, or `Automatic`) are set on Initialize (AUTHORING.md "Catalog listed no settings for
      Initialize although `capacity` is set there", "The default bounds mode warns on every build").
- [ ] Random vector attributes that should fill a volume use `PerComponent`, not `Uniform` (AUTHORING.md Pitfalls).
- [ ] Colours are linear values as VFX Graph stores them; HDR peaks match the tier in the style profile (`inspect`
      `hdr_colors` `intensity` = log2 of the peak; `vfx-lint` row `hdr-intensity`).
- [ ] Output: `blendMode` intended (`Additive` for glows, `Alpha`/`AlphaPremultiplied` for smoke), `inspect`
      `effective.sorted` and `soft_particles` as intended, shader present (`inspect` `outputs[].shader`).
- [ ] Exposed properties have clear names and categories; a prefab's overrides match an exposed name (`inspect`
      warns on an orphan override). A chain effect exposes `SourcePosition` / `TargetPosition0..7` / `HopCount` for
      `ChainLightningBinder` (`Runtime/ChainLightningBinder.cs`).
- [ ] `meta.duration_seconds`, `meta.phases` and `meta.tags` (`element:`, `tier:`) are set for capture and lint
      (`scripts/vfx/vfx_lint_rules.py` docstring).

## Textures

- [ ] Imported with `import-texture` from the approved generation; `source_sha256` and `output_sha256` recorded.
- [ ] Power-of-two size within the profile's limit, `srgb` for colour and `linear` for masks, noise and flow,
      `premultiply` before `resize_pot` for straight-alpha colour, a `flipbook` grid that divides the size
      (AUTHORING.md "Texture import"; `inspect` `textures[]` `srgb`, `size`, `estimated_bytes`).

## Capture evidence

- [ ] A capture exists for the current recipe: `stats.json` `recipe_sha256` equals the recipe file's SHA-256.
- [ ] Camera, lighting and seed are the style profile's `capture` values (`vfx-lint` row `capture-conditions`).
- [ ] The reviewer looked at `contact-sheet.png` and says what it shows (readability at gameplay distance, colour
      over life, day and night if the profile asks), not only the numbers.
- [ ] `alive.peak` below every system's `capacity`; `duration_seconds` close to `meta.duration_seconds` (null only
      for a looping effect); `bounds` inside the intended area.
- [ ] A second capture with the same seed gave the same `alive` counts when determinism is claimed.
- [ ] Anything not run (Sandbox unavailable, `unity-mcp-cli` missing) is `NOT_RUN` with the exact command.

## Runtime and Showcase

- [ ] The prefab holds the `VisualEffect` (and a `ChainLightningBinder` when it needs source and targets); a
      `VfxLibrary` entry has the id, prefab, duration and tags, and `VfxLibrary.Validate()` reports nothing
      (`Documentation~/SHOWCASE.md`, "Add an effect").
- [ ] Scene and library edits were made through Unity in the Sandbox (`Assets/Showcase` junction), so the committed
      `.meta` files stay; a library reference set by script was checked in the saved scene (AUTHORING.md Pitfalls).
- [ ] The EditMode and PlayMode tests that cover a changed verb or runtime type ran on the open Sandbox, or are
      `NOT_RUN` with the command.
