# vfx_style.py lint fixtures

Fixtures of `scripts/vfx/vfx_style.py lint`. The style profile is `tests/fixtures/vfx/style/profile.json`
(`profile.md` is the same profile as a vfx-style artifact). The effect is `fire-burst`: element `fire`, tier
`primary` (recipe `meta.tags`). All `.json` files validate against the com.cuvara.vfx schemas
(`Schemas~/vfx-recipe`, `vfx-inspect`, `vfx-capture`) and the `.vfx-spec.md` specs against
`docs/schemas/kinds/vfx-spec.schema.json`, except `bad-recipe-schema.vfxrecipe.json`, whose `schema` is wrong on
purpose.

`good.inspect.json` and `good.stats.json` carry the SHA-256 of the bytes of `good.vfxrecipe.json`
(`90e40473da6c49fe17e07e05c61757033988975b8ac3d845e78e75d26a57fb02`). `.gitattributes` keeps every file here
byte for byte (`-text`), so a checkout with `core.autocrlf true` does not change that hash. Editing
`good.vfxrecipe.json` changes the hash: update `recipe.sha256` in every `*.inspect.json` and `recipe_sha256` in
every `*.stats.json` to match.

## Good cases (exit 0, no FAIL, no WARN)

| Case | Arguments after `lint --style <profile>` | Rows |
|---|---|---|
| all inputs | `--recipe good.vfxrecipe.json --inspect good.inspect.json --stats good.stats.json --spec good.vfx-spec.md` | 19 PASS |
| recipe only | `--recipe good.vfxrecipe.json` | 11 PASS, 8 NOT_AVAILABLE (texture-size, texture-color-space, shader, budget-texture-memory, budget-alive, capture-conditions, recipe-hash, spec-match need their input; hdr-intensity, output-type, blend-mode, budget-capacity, budget-systems fall back to the recipe) |
| artifact profile | `--style tests/fixtures/vfx/style/profile.md` with the all-inputs arguments minus `--spec` | 18 PASS, 1 NOT_AVAILABLE (spec-match) |

## Bad cases (exit 1, exactly the named rule FAILs)

Each bad file breaks one rule. A bad recipe is linted alone (`--recipe <file>`), because the good inspect and
stats files carry the hash of the good recipe. A bad inspect or stats file is linted with `--recipe
good.vfxrecipe.json`; a bad stats file also with `--inspect good.inspect.json`. A bad spec is linted with
`--recipe good.vfxrecipe.json --spec <file>`.

| File | Arguments after `lint --style <profile>` | Rule that FAILs | What is broken |
|---|---|---|---|
| `bad-recipe-schema.vfxrecipe.json` | `--recipe <file>` | `recipe-schema` | `schema` is `cuvara.vfx-recipe/2` |
| `bad-vfx-graph-version.vfxrecipe.json` | `--recipe <file>` | `vfx-graph-version` | `vfx_graph` 17.4, profile 17.6 |
| `bad-timing-sum.vfxrecipe.json` | `--recipe <file>` | `timing-sum` | phases sum to 0.8 s, duration 1 s (ratios stay inside the bands) |
| `bad-timing-ratios.vfxrecipe.json` | `--recipe <file>` | `timing-ratios` | anticipation 0.4 of 1 s, band 0..0.25 |
| `bad-hdr-intensity.vfxrecipe.json` | `--recipe <file>` | `hdr-intensity` | `Tint` is 32 times the flame colour: intensity 5, primary band 1..4 (recipe fallback, no inspect) |
| `bad-palette.vfxrecipe.json` | `--recipe <file>` | `palette` | a colour-over-life key is green (hue 127 deg), far from every fire colour |
| `bad-texture-flipbook-grid.vfxrecipe.json` | `--recipe <file>` | `texture-flipbook-grid` | `flipBookSize` 3x3, allowed 2x2, 4x4, 8x8 |
| `bad-blend-mode.vfxrecipe.json` | `--recipe <file>` | `blend-mode` | `set_output` `blend_mode` Opaque (recipe fallback) |
| `bad-output-type.vfxrecipe.json` | `--recipe <file>` | `output-type` | output context `VFXComposedParticleOutput` (recipe fallback) |
| `bad-budget-capacity.vfxrecipe.json` | `--recipe <file>` | `budget-capacity` | Initialize `capacity` 2500, android budget 2000 (recipe fallback) |
| `bad-hdr-intensity.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `hdr-intensity` | `hdr_colors` intensity 5, primary band 1..4 |
| `bad-texture-size.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `texture-size` | flipbook texture 1024x1024, `max_size` 512 (DXT5, so texture memory stays inside the budget) |
| `bad-texture-color-space.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `texture-color-space` | `FireBurst_Mask.png` is sRGB but matches `linear_textures` `*_Mask.png` |
| `bad-output-type.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `output-type` | output `VFXComposedParticleOutput` |
| `bad-blend-mode.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `blend-mode` | output `blend_mode` Opaque |
| `bad-shader.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `shader` | shader `Custom/FireUnlit`, allowed `Hidden/VFX/*` |
| `bad-budget-capacity.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `budget-capacity` | capacity 2500, android budget 2000 |
| `bad-budget-systems.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `budget-systems` | 5 particle systems (capacity 100 each), android and webgl budget 4 |
| `bad-budget-texture-memory.inspect.json` | `--recipe good.vfxrecipe.json --inspect <file>` | `budget-texture-memory` | 4281681 texture bytes, android and webgl budget 4194304 |
| `bad-budget-alive.stats.json` | `--recipe good.vfxrecipe.json --inspect good.inspect.json --stats <file>` | `budget-alive` | `alive.peak` 2400, android budget 2000 |
| `bad-capture-conditions.stats.json` | `--recipe good.vfxrecipe.json --inspect good.inspect.json --stats <file>` | `capture-conditions` | `lighting` day, profile dusk |
| `bad-recipe-hash.stats.json` | `--recipe good.vfxrecipe.json --inspect good.inspect.json --stats <file>` | `recipe-hash` | `recipe_sha256` of another recipe |
| `bad-spec-match.vfx-spec.md` | `--recipe good.vfxrecipe.json --spec <file>` | `spec-match` | spec duration 1.5 s and other phase seconds |

## Exit 3 and 2

| Arguments | Exit |
|---|---|
| `lint --style <profile> --recipe missing.json` (no such file) | 3 |
| `lint --style missing.json --recipe good.vfxrecipe.json` | 3 |
| `lint --style good.vfxrecipe.json --recipe good.vfxrecipe.json` (not a profile) | 3 |
| `lint ... --stats good.inspect.json` (wrong schema id) or `--spec <a vfx-style artifact>` (wrong kind) | 3 |
| no command, an unknown command, an unknown option, an option without a value, `lint` without `--recipe`, `show` without `--style` | 2 |
