### Added

- **Asset generation engine.** `scripts/assetgen/assetgen.py` (`list`, `show`, `resolve`, `render`, `lint`,
  `review-cmd`, `qa`, `manifest`; stdlib only, Pillow optional) turns a purpose, a game style and a ComfyUI workflow
  template into a reviewed, QA'd and recorded generation run. Core data under `templates/assetgen/`: purposes
  `concept-2d`, `sprite-2d`, `icon`, `ui-element`, `texture-tileable`, `ref-3d-turnaround`, `image-edit`; styles
  `stylized-painterly`, `pixel-art`, `low-poly`, `realistic-pbr`, `anime-cel`, `flat-ui`; API-format templates
  `image-generate` and `image-edit` (`rpg-factory.comfy-template/1`: `{{param}}` placeholders, typed params,
  `output_node`). A game layer `<authoring>/assetgen/{purposes,styles,templates}/` overrides or `extends` core ids.
  `render` is strict, `lint` checks data and workflows offline against a node snapshot and rejects URLs, host
  addresses and credentials (malformed nested data and out-of-range link indices are FAIL rows, never a traceback), `review-cmd` only prints a read-only `codex exec` command, and `qa` checks PNG validity,
  size (exact, min, aspect or any), alpha, transparent corners, tileable seams and blank images. The stdlib PNG
  decoder applies gray, RGB and palette `tRNS` transparency like Pillow. Every parser refuses abbreviated options.
- **Domain `assetgen`.** Module `authoring.assetgen` (`assetgen/`), artifact kind `gen-run`
  (`docs/schemas/kinds/gen-run.schema.json`), quality plugin `scripts/checks/domains/assetgen.py` (the reviewer
  model differs from the prompt author; the review files, not the `run.md` summary, are the evidence and each verdict
  is bound to the prompt and output SHA-256s and a requirements hash (purpose, style and template content hashes,
  resolved params, and for the image review the whole `workflow.json` graph and the reference images kept in `references/`) that `review-cmd` handed the reviewer, so a missing,
  contradicting or stale review fails, also after a purpose is re-resolved with a stricter rubric; `qa.json` must be PASS with a PASS row for every check the purpose requires, `NOT_AVAILABLE` never
  grades PASS, and a QA report graded with an older purpose qa block or requested size is stale; output hashes, provenance, refs), human gate `assetgen-approval`,
  handoffs `assetgen-to-art2d`, `-art3d`, `-ui` and `-vfx`, and the `comfy-mcp` dev tool (MCP server plus a
  ComfyUI service probe, headless or Desktop). A same-model review is allowed only as the explicit fallback
  `"by": "SAME_MODEL:<model>"`, which grades WARN, never PASS.
- **Skills.** Lead `asset-gen`: the generation workflow (route, pick, resolve, prompt, Codex prompt review with at
  most 2 fix rounds, render, comfy-mcp `server_info` -> `validate_workflow` -> `run_workflow` -> `fetch_outputs`, QA
  plus visual and Codex image review with at most 2 regenerations, `manifest`, human approval, handoff, promotion
  into the game layer on request). Tech skill `comfyui` (paths `assetgen/`; used by `asset-gen`, `art-2d`,
  `art-3d`, `ui-ux`, `vfx`): template format, layer precedence, comfy-mcp setup and tool sequence, the 9router
  image node's pitfalls (credentials read by the node, returned size, unsupported model ids, no local models),
  Desktop and headless ports, and adding a purpose, style or template.
- **Commands.** `/rpg-factory:assetgen` (`factory-cmd.py assetgen`) runs the read-only engine verbs `list`, `show`,
  `resolve`, `lint` and `review-cmd`. It defaults `--authoring` to the workspace authoring repo when that repo has
  `assetgen/`, and it refuses `render`, `qa`, `manifest` and `--out` with any abbreviation of it (`--ou=FILE`).
- **Tests.** `tests/assetgen.test.sh` (in run-all, selected by `--affected` for engine, template and quality-plugin
  changes), routing scenarios (`assetgen/` -> lead `asset-gen` with tech `comfyui`; `art2d/` without it), the
  `asset-gen` dogfood scenario and the `asset-gen-icon` eval.

### Changed

- **2D Art.** Generated images may become production sources, but only through a human-approved `gen-run` handed
  off by `assetgen-to-art2d`. Any other generated image stays a concept draft. Art 3D, UI/UX and VFX accept
  approved gen-runs through their handoff contracts and name `rpg-factory:comfyui` for inspecting a generation.
- **Registry.** The `codex` dev tool is also used by `asset-gen`, for the independent prompt and image review.
- **Docs.** The skill counts are now 14 specialised skills and 11 tech skills (`.claude/CLAUDE.md`, plugin and
  marketplace manifests, README, factory-core Skills, skill-contract diagram).
- **Tests.** `tests/new-skill.test.sh` reads the lead count from the registry instead of a fixed number.
