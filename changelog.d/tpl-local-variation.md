### Added

- **asset-gen.** Core template `local-variation` for `prop-2d` and `image-edit` (choose it with `--template
  local-variation`): a seeded low-denoise SDXL variation of an approved base image with IPAdapter style anchors
  (`anchor_target` IPAdapterAdvanced.image), fixed seed and sampler as rendered params, tiled VAE decode, the base
  alpha joined back, previews and one SaveImage; no API call and no credit; requires profile local-8gb. UNTESTED on
  RTX 5060: the local branch has not run on the target hardware, nothing was generated or measured; the owner tests
  it on the RTX 5060 8 GB machine after merge.
- **Tests.** `tests/assetgen.test.sh` reads a variant's own cases file `cases/<purpose>--<template>.json`, converts
  every variant's workflow.ui.json back to workflow.json, renders every core template that declares `anchor_target`
  with style-lock anchors (anchors reach the target, graph-lint --run passes, render --run is byte-identical on
  repeat), and expects a core template with a local `requires.profile` to FAIL `graph-lint --profile api-only`.
