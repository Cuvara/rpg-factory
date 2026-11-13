### Added

- **Asset generation.** Add `qa.size.fit` and a finalize fit step to pad orientation mismatches while preserving originals.

### Changed

- **Asset generation.** Icon and sprite-2d outputs are padded to the expected aspect when needed.

- **Asset generation.** Lint refuses a game layer inheriting `qa.size.fit` pad from icon or sprite-2d while overriding `qa.size.mode`, alpha or allow_swap incompatibly; set `qa.size.fit` none in that game layer.
