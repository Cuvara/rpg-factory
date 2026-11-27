### Added

- **vfx-graph skill.** New tech skill `rpg-factory:vfx-graph` (used by `unity-package` and `vfx`): how an effect is
  authored with com.cuvara.vfx - the recipe format and ops, catalog before writing, describe to learn from existing
  graphs, build and apply, texture import, the Sandbox project and the `Tools~/vfxcli.py` sequence, deterministic
  capture, reading a contact sheet and `stats.json`, and a review checklist. References `recipe-format.md`,
  `capture.md` and `vfxgraph-review.md`; every pitfall cites a recorded failure in UnityVFX
  `Documentation~/AUTHORING.md`. A route for a UnityVFX recipe or `.vfx` path names lead `unity-package` and tech
  `vfx-graph`.

### Changed

- **vfx lead.** `skills/vfx/SKILL.md` runs the five-step production loop of one effect: the approved vfx-style
  profile, textures through `rpg-factory:asset-gen` (stop at `assetgen-approval`), the `vfx-spec-to-impl` handoff to
  the `unity-package` leg with `rpg-factory:vfx-graph`, capture evidence and vfx-lint (stop at the human Play-mode
  review `vfx-visual-review`), and the `vfx-asset` record. New references `style-profile.md` and `production-loop.md`;
  the input handoff is named `gameplay-event-to-vfx`; the vfx lead and its scripts still never launch Unity.
- **asset-gen and unity-package.** asset-gen names the vfx purposes and the handoff to `rpg-factory:vfx`;
  unity-package lists the modules `unityvfx.effects`, `unityvfx.library` and `unityvfx.samples` and loads
  `rpg-factory:vfx-graph` for effect work.

### Fixed

- **vfx-plan.** A request such as "make a fire burst" plans as a VFX request; the stale note that the vfx-style
  module is not registered is gone.
- **vfx capture schema.** `docs/schemas/vfx-capture.schema.json` mirrors the optional UnityVFX capture fields
  `characters` and `binders`.
- **vfx-asset template.** A fresh `templates/vfx/vfx-asset.md` no longer FAILs `vfx-asset-style-lint` on a
  placeholder blob revision: it leaves the style and lint evidence out until a lint exists.
