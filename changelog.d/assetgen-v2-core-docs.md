### Changed

- **asset-gen.** The asset-gen and comfyui skills, the asset-gen domain doc and `scripts/README.md` now describe
  `finalize` in place of the separate defringe, embed and qa chain, the light review tier, and the `budget` check
  before each `run_workflow`; the comfyui skill and the domain doc state that image QA reads the real returned size.
  The conclusion of `docs/plans/assetgen-batch/probe.md` is reworded to one unambiguous decision: the optional node
  `n` parameter is dropped (the gateway ignored `n` greater than 1) and batch variants are separate calls.
