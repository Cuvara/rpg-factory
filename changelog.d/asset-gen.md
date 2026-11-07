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
- **ComfyUI-visible runs.** `render` also writes `<run>/workflow.ui.json`, the same graph in ComfyUI frontend
  (LiteGraph) format with node layout, titles, links, `widgets_values` and the run id, which converts back to the API
  graph. The core templates feed the prompt through a `PrimitiveStringMultiline` node titled
  `Prompt (Claude, Codex review <state>)`. New verbs: `assetgen.py embed --run DIR` (mandatory after
  `fetch_outputs`, before `qa`) writes the UI workflow as a `workflow` tEXt chunk into each output PNG, idempotent and
  keeping the `prompt` chunk, so dragging the PNG into ComfyUI restores the graph; `assetgen.py publish --run DIR
  --comfy-url URL` (optional, not exposed through `factory-cmd.py`) uploads `workflow.ui.json` through ComfyUI's
  userdata API to Workflows > assetgen, and reports `NOT_AVAILABLE` without writing anything when ComfyUI is not
  reachable.
- **Claude's visual review is recorded.** The agent writes `<run>/review-image-claude.json` (review schema and the
  image review binding, `"by": "claude"`), `manifest` records it as `spec.claude_image_review` and summarises it in
  `run.md`, and the quality check `gen-run-claude-review` WARNs when it is missing, unbound or stale and FAILs when it
  contradicts `run.md` or is a FAIL verdict on a proposed run; it never replaces the Codex image review.
- **Image review inputs.** `review-cmd --phase image` states the true pixel size of every output, and for purposes
  with a tileable check it passes a 2x2 tiled preview (`<run>/review/tile-2x2.png`) to the reviewer.
- **Skills.** `asset-gen` and `comfyui` document `embed` and `publish`, that comfy-mcp `run_workflow` posts to
  `/prompt` and never opens a canvas tab, Claude's own image review file, and that the generate step reports an
  outdated `comfyui_9router` node pack from `server_info` without updating it.

### Changed

- **2D Art.** Generated images may become production sources, but only through a human-approved `gen-run` handed
  off by `assetgen-to-art2d`. Any other generated image stays a concept draft. Art 3D, UI/UX and VFX accept
  approved gen-runs through their handoff contracts and name `rpg-factory:comfyui` for inspecting a generation.
- **Registry.** The `codex` dev tool is also used by `asset-gen`, for the independent prompt and image review.
- **Docs.** The skill counts are now 14 specialised skills and 11 tech skills (`.claude/CLAUDE.md`, plugin and
  marketplace manifests, README, factory-core Skills, skill-contract diagram).
- **Tests.** `tests/new-skill.test.sh` reads the lead count from the registry instead of a fixed number.
- **Purpose over style.** A purpose's `constraints` (lighting, background, framing; precedence in
  `scripts/assetgen/data/precedence.json`, the palette stays a style hint) win over the style's hint of the same name.
  `resolve` writes `spec.hints` and marks each overridden style hint, and the review prompts use those hints, so the
  prompt writer never sees both. `ref-3d-turnaround` and `texture-tileable` carry lighting constraints; lint fails a
  constraint on a style-only hint.
- **`ref-3d-turnaround`.** QA checks the aspect of the requested size with a 25% tolerance and a minimum area (90% of
  the requested pixel count, new `qa.size.min_area`) instead of a minimum width and height, and the prompt guidance
  asks for a compact landscape sheet whose views fill most of its height.
- **Failed attempts.** A failed attempt's run directory stays on disk without `run.md`, the next attempt takes the
  next number, and `manifest` lists the earlier attempts of the series without `run.md` in
  `spec.trace.failed_attempts` (the envelope `trace` stays the engineering trace; documented in `asset-gen`).

### Fixed

- **`filename_prefix`.** `spec.json`, the review prompts and `run.md` record the same `assetgen/<run-id>` prefix that
  `render` writes into the workflow.
- **`review-cmd`.** The printed command uses absolute paths, so it works from any working directory.
- **`asset-gen` skill.** It documents `show --kind purpose <id>`: a bare `show image-edit` was ambiguous between the
  purpose and the template.
- **`lint`.** A bad game-layer value is blamed on the game file that holds it, not on the unchanged core file it
  extends.
