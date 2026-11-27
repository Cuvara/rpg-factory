### Added

- **VFX commands.** `/rpg-factory:vfx-plan` (also `factory-cmd.py vfx-plan`) prints the deterministic plan of one VFX
  effect through its five production steps (style profile, textures, recipe, capture, record) from
  `scripts/vfx/vfx_plan.py`, and `/rpg-factory:vfx-lint` (`factory-cmd.py vfx-lint`) lints a
  `<Name>.vfxrecipe.json` against the project's vfx-style profile with `scripts/vfx/vfx_style.py lint`. Both are
  read-only and support `--json`. `vfx-lint` resolves a relative `--style` or `--spec` under the workspace authoring
  repo, prints a short summary (or the `rpg-factory.vfx-lint/1` JSON) with the lint exit code, and refuses every
  writing option (`--out`, `--output`, `--write` and their prefixes). Both verbs are listed in `help` with an example.
