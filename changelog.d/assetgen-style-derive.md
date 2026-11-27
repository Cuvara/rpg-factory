### Added

- **asset-gen.** `assetgen.py style derive --authoring DIR --style ID [--family FAM] [--apply] [--json]` proposes the
  structured fields of a game style from its valid active anchors (recorded for the style's current version, PNG present
  and matching `image_sha256`; the others are skipped and reported): `palette.colors` (at most 8 colours from the sampled
  opaque pixels, with `palette.text`), `tone.tolerance` and a `canvas` aspect and tolerance per family. The proposal is
  deterministic (no clock, no randomness), so the same anchors print byte-identical output. Without `--apply` nothing is
  written; `--apply` merges the proposal only into a style whose status is `draft` (an active style, or one without
  anchors, is refused with exit 1 and the file untouched), validates the merged style and writes it atomically, so the
  `style-palette`, `style-tone` and `style-canvas` QA rows can grade. The logic lives in `scripts/assetgen/style_derive.py`.

### Fixed

- **asset-gen.** lint now accepts a style `canvas` entry with only `min_side` (no `aspect`), as the `style-canvas` QA
  check already did.
