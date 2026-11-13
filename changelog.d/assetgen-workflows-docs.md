### Changed

- **asset-gen.** The domain doc `docs/architecture/domains/assetgen.md` gains a "Generation data" section: the ten core
  purposes with their default template and handoff domain, the seven staged templates and the legacy `image-generate`
  and `image-edit`, the template ui block, the workflow style guide with every `graph-lint` rule id, the node registry
  and `nodesync.py`, and the limits (API and core image nodes only, no generation quality from extra nodes,
  `PreviewImage` files through `fetch_outputs` unverified until the live end-to-end run). Its quality rules add
  `gen-run-workflow-style` (WARN), and the skills section names `graph-lint --run` before `validate_workflow` and the
  comfyui authoring rule.
- **asset-gen.** The domain doc moves `finalize` out of the gen-run record fields into its own paragraph, and the
  fringe repair now reads `defringe --force`, then `finalize`, then both image reviews again, as the skills do.
- **asset-gen.** `scripts/README.md` names the new `assetgen.py` verbs and modules.
- **asset-gen.** The `asset-gen-icon` eval criteria follow the staged template flow: `graph-lint --run` before
  `validate_workflow`, `budget` before `run_workflow`, `finalize` after `fetch_outputs`, and the light review tier in
  which Claude's own image review is optional.
