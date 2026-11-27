### Added

- **VFX style module.** Module `authoring.vfx-style` (authoring `vfx/style/`) holds the project's `vfx-style`
  profile, with the artifact-lint, artifact-trace and VFX quality checks of the other VFX modules.
- **Gate `vfx-visual-review`.** New human gate in `registry/core.json`, listed in `domains.vfx.human_gates`: a person
  judges the look, readability, overdraw and frame time of an effect in Play mode; agents never record this review.
- **UnityVFX effects modules.** `registry/engineering/unityvfx.json` registers `unityvfx.effects` (`Effects/`, with
  the recipe lint and the obligation that a recipe change rebuilds the `.vfx` and its capture), `unityvfx.library`
  (`Library/`) and `unityvfx.samples` (`Samples~/`), owned by `unity-package`. The `vfx-spec-to-impl` handoff gains
  the copy `unityvfx:Effects/`.
- **Showcase event ids.** `domains.vfx.engineering_event_ids` gains `vfx.showcase.chain-lightning` and
  `vfx.showcase.ground-slam`, described in the new `engineering_event_descriptions` map as showcase triggers of the
  UnityVFX Showcase scene, not gameplay bindings.
- **Production evidence on `vfx-asset`.** Optional `capture` (stats hash, seed, alive peak, contact sheet hash),
  `style` (profile id and blob revision), `textures` (gen-run id, output hash, named transform, game texture hash)
  and `lint` (state, report hash); `vfx-spec` gains an optional `style` profile id. The VFX templates show the
  fields.
- **VFX quality checks.** `scripts/checks/domains/vfx.py` adds `vfx-style-profile` (the profile resolves with
  `scripts/vfx/vfx_style.py`, is binding and the only live one), `vfx-spec-style` (spec budgets and phase shares within
  the profile's bands), `vfx-asset-capture` (capture evidence well formed and equal to its `stats.json` when found;
  a `.vfx` asset without capture evidence is HUMAN_REQUIRED), `vfx-asset-style-lint` (the lint is bound to the
  profile's current blob revision and the capture's stats hash and is recomputed with `vfx_style.py lint`; a mismatch
  is FAIL) and `vfx-asset-textures` (every game texture traces to an approved gen-run that recorded its output hash,
  else FAIL past draft). Look, readability, overdraw and frame time stay HUMAN_REQUIRED for every `vfx-asset`
  (`vfx-visual-review` for non-`.vfx` assets).

### Changed

- **Unity gates name the Sandbox exemption.** `unity-batch` and `unity-asset-edit` now cover the user's Unity
  projects and exempt the agent-owned UnityVFX `Sandbox~` project (module `unityvfx.sandbox`); their match patterns
  are unchanged and `tests/git-guard.test.sh` pins them.

### Fixed

- **`vfx-style` artifacts no longer FAIL the VFX quality plugin.** The plugin returned `vfx-kind` FAIL
  ("unrecognized VFX artifact kind") for every `vfx-style` artifact; it now grades them with `vfx-style-profile`.
