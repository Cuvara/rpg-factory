# VFX production loop

The five steps of one effect, as `scripts/vfx/vfx_plan.py` reports them (rules in `scripts/vfx/data/plan.json`).
Each step has a lead, an output, the evidence that proves it and the state the plan gives it (the `states` map of
`plan.json`: DONE, IN_PROGRESS, NEEDS_APPROVAL, STALE, FAIL, BLOCKED, or not started yet). Work the first step that
is not DONE; never skip a NEEDS_APPROVAL step.

## 1. Style profile (`style`, lead `vfx`)

- Output: the approved `vfx-style` profile ([style-profile.md](style-profile.md)).
- Evidence: `vfx_style.py show` resolves it; its approval record matches its current revision.
- NEEDS_APPROVAL: finished but not approved. Stop and ask a person.

## 2. Textures (`textures`, lead `asset-gen`)

- Output: one approved gen-run per effect texture, made by `rpg-factory:asset-gen` with a vfx purpose and the
  profile's `assetgen_style`:

| Purpose | Use |
|---|---|
| `vfx-flipbook` | animated sheet, a 4 x 4 grid of frames |
| `vfx-noise-tileable` | grayscale noise, tileable on both axes (erosion, distortion, masks) |
| `vfx-trail` | landscape strip, tileable on the x axis only |
| `vfx-sprite` | one centred glow, flare, puff or debris shape |

- All four render on an opaque pure-black background. Alpha extraction, channel packing and the power-of-two resize
  are not asset-gen's job: the engine leg applies them with com.cuvara.vfx `import-texture`, which records the source
  and output SHA-256.
- Gate `assetgen-approval`: a person approves each gen-run. Until then the images are concept drafts and the step is
  NEEDS_APPROVAL. Then cite each `AGEN-<run id>` in the `sources` of the effect's `vfx-spec` (handoff
  `assetgen-to-vfx`).

## 3. Recipe and built asset (`recipe`, engine leg)

- Handoff: `vfx-spec-to-impl` to the `unity-package` lead, which invokes `rpg-factory:vfx-graph`. Hand over the
  approved spec ID and revision, the profile ID, and per texture the gen-run ID, output path, output SHA-256 and the
  transform wanted (for example `luminance_to_alpha`).
- The leg writes `<Name>.vfxrecipe.json` (`cuvara.vfx-recipe/1`, `id` = the effect id, `meta.tags` with element and
  tier), builds `<Name>.vfx` next to it, imports the textures and runs `inspect`.
- This skill writes none of these files and never launches Unity.

## 4. Capture and lint (`capture`, then gate `vfx-visual-review`)

- Input from the leg: the capture folder with `stats.json` (`cuvara.vfx-capture/1`, carries `recipe_sha256` and the
  alive peak), `contact-sheet.png`, the per-sample PNGs, and the `inspect` result (`cuvara.vfx-inspect/1`). The
  capture must use the profile's camera, lighting and seed.
- Lint: `/rpg-factory:vfx-lint --style <profile> --recipe <recipe> --inspect <inspect> --stats <stats.json> --spec
  <spec>` for a summary, or `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vfx/vfx_style.py lint` with the same arguments
  for the `rpg-factory.vfx-lint/1` JSON. Save that JSON as `vfx-lint.json` in the capture folder, next to
  `stats.json`; the quality check finds the pair there. Exit 1 is a FAIL row; exit 3 is a missing input.
- A FAIL row sends the effect back to step 3 with the row ids and evidence. A lint of another recipe (its
  `inputs.recipe.sha256` differs from the capture's `recipe_sha256`) is STALE: capture and lint again.
- Gate `vfx-visual-review`: a person opens the effect in Play mode and judges look, readability, overdraw and frame
  time. Show them the contact sheet, the lint rows and the spec's budgets. The agent never records this result.

## 5. Record (`record`, lead `vfx`)

Write the `vfx-asset` from `templates/vfx/vfx-asset.md`: `asset_path` of the built effect, its content hash, the
stats, `checks` (include `vfx-lint`), and `sources` citing the `vfx-spec` and every gen-run. Production evidence:

| Field | Value | Checked by |
|---|---|---|
| `capture.stats_hash` | SHA-256 of the capture's `stats.json` | `vfx-asset-capture` (equal to the file when found under a `Captures/` folder) |
| `capture.seed`, `capture.alive_peak` | the capture seed and `alive.peak` | `vfx-asset-capture` |
| `capture.contact_sheet_hash` | SHA-256 of `contact-sheet.png` | `vfx-asset-capture` |
| `style.profile_id`, `style.blob_revision` | the profile id and `git hash-object <profile>` | `vfx-asset-style-lint` |
| `textures[].gen_run_id`, `output_hash` | the approved gen-run and the output SHA-256 it recorded | `vfx-asset-textures` |
| `textures[].transform`, `game_texture_hash` | the `import-texture` transform and the written texture's SHA-256 | `vfx-asset-textures` |
| `lint.state`, `lint.report_hash` | the lint status and the SHA-256 of `vfx-lint.json` | `vfx-asset-style-lint` |

`vfx-asset-style-lint` recomputes the lint from the bound profile, recipe and capture; a different result, another
profile revision or a capture the report did not grade is FAIL, and a capture or report it cannot find is
NOT_AVAILABLE. A `.vfx` asset without capture evidence is HUMAN_REQUIRED. A texture whose gen-run is not approved
WARNs while the record is a draft and FAILs past it. Look, readability, overdraw and frame time stay HUMAN_REQUIRED.
