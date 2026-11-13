### Added

- **Asset generation.** Added staged-icon and staged-ui-element workflows. The icon workflow previews readability at 64 px, and the UI workflow previews a 256 px top-left crop for the nine-slice border.

### Changed

- **Asset generation.** Icon and UI element purposes now default to their staged workflows. The legacy image-generate and image-edit templates stay unchanged, with an icon--image-generate golden covering the legacy icon render.
- **Asset generation.** Legacy-shape assertions in tests/assetgen.test.sh select their templates explicitly so purpose defaults can change independently.
