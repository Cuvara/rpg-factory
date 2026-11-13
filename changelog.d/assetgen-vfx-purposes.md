### Added

- **Effect texture purposes.** Asset-gen gains four core purposes for VFX textures, each with handoff domain `vfx`,
  default family `vfx` and an opaque pure-black background: `vfx-flipbook` (4 x 4 grid of frames), `vfx-noise-tileable`
  (grayscale noise, tileable on both axes), `vfx-trail` (landscape strip, tileable on the x axis only) and `vfx-sprite`
  (one centred glow, flare, puff or debris shape). Alpha extraction, channel packing and power-of-two resize stay with
  the consuming package's import tool, because the gen-run binds the output hashes and the image service ignores the
  requested size.
- **Effect texture QA.** New checks `png-flipbook-grid` (declared columns and rows, dark gutters, no blank cell) and
  `png-black-background` (border luminance below a threshold, optionally per edge), and an `axis` option for the
  `qa.tileable` check (`x`, `y` or `both`).
