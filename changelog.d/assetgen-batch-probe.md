### Added

- **Asset generation.** `docs/plans/assetgen-batch/probe.md` records the `n` greater than 1 probe of the image gateway:
  one low-quality call returned one image for `n=2`, at 1254x1254 for a 1024x1024 request, so batch variants stay
  separate calls and image QA reads the real size.
