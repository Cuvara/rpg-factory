### Added

- **Asset-gen graph lint for hybrid graphs.** The workflow style guide gains the stages Models and Refine (local)
  between Generate and Post-process, and a hybrid template must keep the reviewed prompt one
  PrimitiveStringMultiline node feeding every positive text input. New profile rules check a template against a
  `data/hardware.json` profile (its own `requires.profile`, or `graph-lint --profile PROFILE`): `requires.peak_vram_gb`
  fits, no two checkpoints without a declared offload, at most one ControlNet per sampler path, batch size 1, tiled
  VAE decode above 1024 px, no fp16 Flux under local-8gb, and a profile below the template's own is refused. Each
  violation names the node and the profile. `graph-lint --profile` takes a hardware profile id; another value exits 2.
  UNTESTED on RTX 5060: these rules and the local branch are static checks of a template's declarations against
  planning thresholds; nothing was generated or measured, and no VRAM number, generation or quality result is
  claimed. The user will test on the RTX 5060 8 GB machine after merge.
- **`requires.offload`.** A template's requires block may declare `offload` (true or false; anything else is a lint
  error): true says one checkpoint is unloaded before the next loads.

### Changed

- **Asset-gen lint checks render targets.** `assetgen.py lint` now FAILs a template whose `anchor_target` names a
  missing node or input or an input that cannot take anchors, or whose `primary_node` is missing or not a generation
  node (or that has more than one NineRouterImage and no `primary_node`), with the messages render already used;
  before, only render refused it. Render behaviour is unchanged.
