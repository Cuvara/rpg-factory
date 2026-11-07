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
- **Style lock: project style config.** `<authoring>/assetgen/project.json` (`rpg-factory.assetgen-project/1`:
  default `style` `{id, version}`, `allowed_styles`, `families` mapping an asset family to a game sub-style,
  `art_direction` refs) is the single source of the game's style. `resolve --family F` (else the purpose's
  `default_family`) picks the style, refuses a style outside the project or a deprecated one unless
  `--style-override REASON` (recorded in `spec.style_lock.override` and `run.md`), and keeps today's behaviour with a
  lint `WARN` when the game has no `project.json`. Schemas `docs/schemas/assetgen-{project,anchor,rejection}.schema.json`.
- **Style lock: versioned, structured styles.** Styles carry `version` and `status` (`draft`, `active`,
  `deprecated`) and optional structured fields (`palette` colours, `lighting`, `outline` with `edge_darkness`,
  `shape_language`, `forbidden[]`, `canvas` per family, `tone`); a prose string still works. Purposes gain
  `default_family`, `dimensions`, `max_references` and `qa.outlines`. Every spec, review binding, anchor, rejection
  and gen-run records the style reference `{style_id, version, sha256}`.
- **Style lock: anchors and rejections.** `assetgen.py promote-anchor` writes a `proposed` anchor from a manifested
  run output under `assetgen/styles/<style-id>/anchors/`; only a person activates it, and it is valid only while its
  source gen-run is approved (the quality check `gen-run-style` also checks the signed approval, the image hash and
  that the approver is not an agent or model). `assetgen.py reject` records a rejected asset or direction with a
  fixed reason under `rejections/`; relevant rejections feed the prompt's avoid list and the review rubric, and the requirements hash binds them
  and the family, so a changed rejection set makes earlier reviews stale. Both reviews also show the style's
  `forbidden` list, `outline` and `shape_language`.
- **Style lock: deterministic reference selection.** `resolve` selects valid active anchors of the run's style
  version (family match, dimension overlap, strength, id; capped by `max_references`) with `reason[]` per pick, and
  `render --run` copies them to `<run>/references/anchor-<id>.png` and wires them through `LoadImage` and core
  `ImageBatch` nodes into `NineRouterImage.reference_images` (an image-edit reference stays first).
- **Style lock: consistency QA.** `qa` adds the soft rows `style-palette`, `style-tone`, `style-edges` and
  `style-canvas` (`scripts/assetgen/consistency.py`; `WARN` by default, `FAIL` only when the style says so,
  `NOT_AVAILABLE` without the style field), and the image review attaches the selected anchors, adds an anchor
  rubric item and one `Not repeated:` item per relevant rejection, and binds the style ref and anchor hashes.
- **Style lock: drift.** `assetgen.py drift --authoring DIR` (read-only, `rpg-factory.assetgen-drift/1`) lists
  gen-runs, anchors and rejections recorded on an older style version, a changed style hash or a missing style.
  `/rpg-factory:assetgen drift` forwards it; `factory-cmd.py assetgen` refuses `promote-anchor` and `reject`,
  because they write into the authoring repo.
- **Style lock: quality checks.** The quality plugin adds `gen-run-style` (style reference, recorded anchors exist,
  are active, approved by a person, with matching image bytes and an approved source gen-run; an active anchor
  promoted from an unapproved run fails; image reviews bind the style reference and anchors). The new fast check
  `assetgen-lint` (`assetgen.py lint --authoring .`) lints the game layer, `project.json`, anchors and rejections.
- **Style lock docs and skills.** `docs/architecture/domains/assetgen.md` section "Style lock"; `asset-gen` gains
  the family, override, anchor upload, style-row and rejection steps and a reference
  `references/style-lock.md` (bootstrap a new game style: exploration `concept-2d` runs, a person picks,
  `promote-anchor`, a person approves, then `project.json` and the game style at version 1; style change and drift);
  `comfyui` documents the anchor wiring and uploading every `references/*` file.
- **Edge fringe QA and `defringe`.** `qa` adds the row `png-edge-fringe` for purposes with alpha (the colour of
  low-alpha edge pixels against the adjacent opaque pixels and the output composited on black and white), and
  `assetgen.py defringe --run DIR [--alpha-floor N]` bleeds opaque neighbour colour into low-alpha pixels (stdlib,
  premultiply-safe), runs after generation and before QA, keeps the originals and is recorded in the run.
- **Composite previews for alpha review.** `review-cmd --phase image` writes and attaches
  `review/composite-dark.png` and `review/composite-light.png` for every output with alpha, and the rubric asks to
  judge the edges on both; Claude's own image review uses the same composites.
- **Approval verb.** `assetgen.py approve-record --run DIR --by NAME [--note TEXT]` writes the approval record and the
  `run.md` status `approved` for a person; it refuses a missing `--by` and an agent or model name. The person commits
  and signs the record. The `asset-gen` skill runs it only on the person's explicit word and quotes it.
- **Cross-family anchors.** `resolve` warns when a selected anchor's family differs from the run's family, and
  `anchor_family_fallback: false` in a purpose or `project.json` forbids such anchors.

### Changed

- **`--run` takes a run id.** Every `--run` accepts the run id as well as the run directory; an id resolves under
  `<authoring>/assetgen/runs/` (with `--authoring`, else the current repo).
- **Short `resolve` output.** `resolve` prints a short summary (style lock, references, rejections, key params,
  warnings); the source file of every field and param only with `--verbose` or `--json`.
- **`asset-gen` skill: a service FAIL stops regenerating.** After a FAIL the service causes, not the prompt (for
  example a returned size that ignores the request), the agent stops regenerating, runs `manifest` on the last attempt
  with its QA FAIL visible and reports; the earlier attempts stay without `run.md`.
- **`comfyui` skill.** It names the service ignoring `size` as a known issue, and says that `server_info`'s outdated
  flag for a node pack compares the pack hash with ComfyUI's own commit, so it is unreliable for a pack inside the
  ComfyUI checkout: the agent reports it as unverified and never prompts or performs an update on that signal alone.
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
- **`manifest` keeps an approval.** An `approved` run stays `approved`, and its approval stays bound, when `manifest`
  runs again and nothing the approval binds changed.
- **Style bootstrap.** `asset-gen` `references/style-lock.md`: a new game style id has no anchors until runs under it
  are approved and promoted, so promote again under the game style id or explore under it; step 5 checks the
  structured `palette`, `tone` and `canvas` fields, and `lint` WARNs on an active game style without them (every
  `style-*` QA row would be `NOT_AVAILABLE`).
- **`drift` reports style-id mismatches.** Gen-runs and anchors recorded under another style id than `project.json`
  are listed, not only older versions of the same style.

### Fixed

- **Size QA vs the real image service.** The 9router image node can ignore `size` entirely (live style-lock e2e,
  2026-11-08: 1672x941 returned for 1536x1024 and 1024x1024 requests), so `concept-2d` could never pass and
  `promote-anchor` refused good outputs. No core purpose's size QA grades the exact size any more: it grades
  orientation or aspect with a tolerance, a minimum area and a minimum short side that real outputs meet, per purpose
  in data, with regression tests on the real returned sizes. Every core purpose has a short side and an area floor
  (`icon`, `sprite-2d`, `texture-tileable`, `ui-element` and `image-edit` 512 px and 512x512 pixels), so a 256x256
  output fails each.
- **Review prompt params.** The requested params in the review prompts and `run.md` `spec.params` come from the
  rendered workflow, so a `render --param` value is the one the reviewer and the record see, never the `spec.json`
  value it replaced. Each review is bound to exactly those params: a `render --param` that changes a param after a
  review makes it stale (render title, `review-cmd` and the quality check agree; the same params again keep it
  bound), and the quality check FAILs a `run.md` `spec.params` that differs from the rendered params instead of
  substituting `spec.json`.
- **Size double-counted in the image review.** The image review prompt states QA's verdict as context and tells the
  reviewer not to grade size or the other deterministic checks again; they belong to QA only.
- **`filename_prefix`.** `spec.json`, the review prompts and `run.md` record the same `assetgen/<run-id>` prefix that
  `render` writes into the workflow.
- **`review-cmd`.** The printed command uses absolute paths, so it works from any working directory.
- **`asset-gen` skill.** It documents `show --kind purpose <id>`: a bare `show image-edit` was ambiguous between the
  purpose and the template.
- **`lint`.** A bad game-layer value is blamed on the game file that holds it, not on the unchanged core file it
  extends.
- **Uncommitted approval message.** An approval record that is present but not committed and signed reads
  "approval present but not committed/signed" instead of "missing", graded `HUMAN_REQUIRED` in the trace and in
  `gen-run-style`.
- **Square size tolerance.** `sprite-2d` and `icon` square checks failed on real service outputs (1322x1190); square
  purposes now tolerate such outputs, and a landscape or portrait purpose can set `qa.size.allow_swap` to accept the
  swapped orientation (1024x1536 returned for 1536x1024), with these real sizes as regression tests.
- **`embed` stale chunk.** `embed` replaces an existing `workflow` chunk that differs from the current
  `workflow.ui.json` (idempotent when equal), so a re-render no longer leaves the old graph in the PNG.
