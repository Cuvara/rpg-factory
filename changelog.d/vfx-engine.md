### Added

- **VFX style profile.** New artifact kind `vfx-style` (`docs/schemas/kinds/vfx-style.schema.json`, skeleton
  `templates/vfx/vfx-style.md`): one binding profile per project with the palette and colour ramps per element, HDR
  intensity bands per importance tier (primary, secondary, ambient), phase timing ratios (anticipation, impact,
  dissipation), texture conventions, allowed outputs, blend modes and shaders, per-platform budgets, the capture
  viewing conditions and the asset-gen style the effect textures use. `docs/schemas/vfx-capture.schema.json` mirrors
  the com.cuvara.vfx capture statistics (`cuvara.vfx-capture/1`).
- **VFX lint.** `scripts/vfx/vfx_style.py show` prints the resolved profile; `lint --style <profile> --recipe <file>
  [--inspect <file>] [--stats <file>] [--spec <file>]` grades one effect against it and prints
  `rpg-factory.vfx-lint/1` with one row per rule (recipe schema and VFX Graph version, timing sum and ratios, HDR
  intensity, palette, texture size, flipbook grid and colour space, output type, blend mode, shader, capacity, system
  count, texture memory and alive peak against each platform budget, capture conditions, recipe hash, spec match),
  each PASS, FAIL, WARN or NOT_AVAILABLE when its input is absent. Exit 0 no FAIL, 1 a FAIL, 3 a required input
  missing, 2 usage. The result names the recipe it graded (`inputs.recipe` with `path` and `sha256`).
- **VFX production plan.** `scripts/vfx/vfx_plan.py` (`rpg-factory.vfx-plan/1`, rules in `scripts/vfx/data/plan.json`)
  reports for one effect the state of the five production steps (style profile, texture gen-runs, recipe and built
  asset, capture and lint, vfx-asset record; a lint result of another recipe is STALE), the missing inputs and the lead route, and writes nothing. Exit 0 PLAN
  or NOT_VFX, 3 NEEDS_CONTEXT, 2 usage.
- **VFX Graph adapter.** `scripts/adapters/vfx/vfxgraph.py` reads a text-serialized `.vfx` asset and its `.meta`
  (asset GUID, system capacities, referenced GUIDs) and optional capture statistics, and checks that the statistics
  belong to the asset; `scripts/adapters/vfx/unity.py` stays for Shuriken prefabs. None of the scripts needs Unity or
  the network.
- **Suite `tests/vfx-production.test.sh`.** A PASS and a FAIL case for every lint rule, NOT_AVAILABLE and the exit
  codes, the plan states and step states, that the plan writes nothing, the adapter on a fixture `.vfx`, and a
  sandbox in which any socket or subprocess use fails.
