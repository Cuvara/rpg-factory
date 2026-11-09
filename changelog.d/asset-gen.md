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
  premultiply-safe), runs after `fetch_outputs` and before `embed` and QA, keeps the originals under `outputs-raw/`,
  records the params and the hashes before and after in `defringe.json` (a `- Defringe:` line in `run.md`), starts
  from the originals when run again, and refuses an approved run and outputs `qa.json` or an image review already
  binds (unless `--force`, which names the records to re-run).
- **Composite previews for alpha review.** `review-cmd --phase image` writes and attaches
  `review/composite-dark.png` and `review/composite-light.png` for every output with alpha, and the rubric asks to
  judge the edges on both; Claude's own image review uses the same composites. `--no-write` uses them only when
  they are current, like the tile preview.
- **Approval verb.** `assetgen.py approve-record --run DIR --by NAME [--note TEXT]` writes the approval record and the
  `run.md` status `approved` for a person; it refuses a missing `--by`, an agent or model name and a name the run
  records as an agent or reviewer. The person commits `run.md` and the record in one SSH-signed commit whose signer
  principal is that name. The `asset-gen` skill runs it only on the person's explicit word and quotes it; the
  `gen-run` lifecycle allows `proposed` -> `approved`, and `factory-cmd` does not forward the verb.
- **Cross-family anchors.** `resolve` warns when a selected anchor's family differs from the run's family, and
  `anchor_family_fallback: false` in a purpose or `project.json` forbids such anchors (`resolve` records the
  warnings as `spec.warnings`).

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
  runs again, nothing the approval binds changed and `run.md` stays byte for byte the same; otherwise it goes back to
  `proposed` and names the changed fields.
- **Style bootstrap.** `asset-gen` `references/style-lock.md`: a new game style id has no anchors until runs under it
  are approved and promoted, so promote again under the game style id or explore under it; step 5 checks the
  structured `palette`, `tone` and `canvas` fields, and `lint` WARNs on an active game style none of whose
  structured fields a style check can grade with: absent, empty (`canvas: {}`, `tone: {}`, `palette.colors: []`,
  `outline.edge_darkness: {}`, a canvas entry with neither `aspect` nor `min_side`) or malformed. The WARN names
  each field's state; the rule is `consistency.field_states`, the same parsing the `style-*` QA rows use, and such
  an empty settings object is now `NOT_AVAILABLE` in QA instead of being graded on defaults.
- **`drift` reports style-id mismatches.** Gen-runs and anchors recorded under another style id than `project.json`
  are listed (`style-id-mismatch`, the text naming the project style), not only older versions of the same style.

### Fixed

- **Style QA is bound to its style inputs.** `qa.json` now records `style_binding` (`runfiles.qa_style_binding`: the
  style ref with id, version and hash, a hash of the effective style data, the family, and each selected anchor copy
  under `references/` with its SHA-256, the tone references `style-tone` reads). The quality plugin recomputes it from
  `spec.json` and the run's anchor copies, and `gen-run-qa` fails a report graded with other style data, version,
  family or anchors (also one without `style_binding`) as stale: re-run `qa` and `manifest`. Before, a style
  re-resolved with a fail-severity rule kept an old PASS report acceptable.

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
  "approval present but not committed/signed" instead of "missing" in `gen-run-style`, graded `HUMAN_REQUIRED` like
  the trace grades it. `artifact-trace` uses the same phrase (still `HUMAN_REQUIRED`) when the record file is on disk
  but not committed, both with `run.md` uncommitted (it said "missing approval") and with `run.md` committed (it said
  "approval is not immutable"); no record file for the artifact still reads "missing approval".
- **`approve-record` immutability and line endings.** `approve-record` never overwrites an approval record: the same
  approval again is a no-op, another one (by, date or note) for the same `run.md` revision is refused before `run.md`
  is touched, and a changed `run.md` gets a new revision and a new record. A `run.md` with CRLF line endings parses
  and keeps them, and the record's `rev` is what `git hash-object` gives the file in its repository (line-ending
  filters such as `core.autocrlf` applied), so it is the blob the commit binds.
- **Square size tolerance.** `sprite-2d` and `icon` square checks failed on real service outputs (1322x1190); the
  square purposes `icon`, `sprite-2d` and `texture-tileable` now set `square_tolerance` 0.15, and a landscape or portrait purpose can set `qa.size.allow_swap` to accept the
  swapped orientation (1024x1536 returned for 1536x1024; a boolean, default false, checked by `lint`), with these
  real sizes as regression tests.
- **`embed` stale chunk.** `embed` replaces an existing `workflow` chunk that differs from the current
  `workflow.ui.json` (idempotent when equal), so a re-render no longer leaves the old graph in the PNG.
- **Agent and model names as approvers.** The shared approver guard (`approve-record --by`, an active anchor's
  `approved_by`, `gen-run-style`) only knew claude, codex and gpt names, so `approve-record --by gemini-2.5-pro`
  approved a run. It now refuses the common model and agent families as a whole-word name start, also after a vendor
  prefix such as `google/` (gemini, llama, mistral, qwen, deepseek, grok, o1/o3/o4, phi-, copilot and others), the
  registry's `pipeline.agents`, and any name ending in `-bot` or `-agent`; person names such as `Grokowski` are
  accepted.
- **`defringe` dropped colour metadata.** `defringe` rebuilt each output from its pixels and kept only the text
  chunks, so `gAMA`, `cHRM`, `iCCP`, `sRGB` and `pHYs` were lost and the opaque body could look different. It now
  carries `cHRM`, `gAMA`, `iCCP` or `sRGB` (never both; `iCCP` wins), `cICP`, `mDCv`, `cLLI` and `pHYs` from before
  the first `IDAT`, in file order, right after `IHDR`, and still drops chunks bound to the old pixel format (`sBIT`,
  `PLTE`, `tRNS`, `bKGD`, `hIST`, `sPLT`).
- **Review previews dropped colour metadata.** The image review's dark and light composites and the 2x2 tile previews
  were written untagged, so an output with `gAMA`, `cHRM`, `iCCP` or `sRGB` displayed different body colours and
  fringe contrast in its preview than in the output (with `gAMA` 100000, opaque 128 displays as 188 in the output
  and 128 in the preview). Every review preview now carries the output's colour chunks right after `IHDR`, with the
  `defringe` rules minus `pHYs` (a preview is never placed); the blend runs on the stored values, with the backgrounds
  in that same space. An untagged output keeps untagged previews, byte for byte, and `--no-write` compares the tagged
  bytes.
- **Grayscale outputs became RGBA with a GRAY ICC profile.** `defringe` and the review previews rewrote a gray or
  gray+alpha output (colour type 0 with `tRNS`, or 4) as RGB(A) while copying its `iCCP`, so a GRAY profile sat on
  a colour image. A grayscale output now stays grayscale: `defringe` writes it as 8-bit gray+alpha (colour type 4)
  with its profile, its composites are gray and its tile preview gray+alpha. No PNG it writes carries a profile of
  the other colour space than its colour type (a GRAY profile on RGB(A), an RGB one on gray): such an `iCCP` is
  dropped, and the output's `sRGB`, if any, is kept instead. Palette and RGB outputs, and untagged previews, are
  unchanged byte for byte.
- **`defringe` and the review previews handled other bit depths as 8-bit.** Both now read the IHDR bit depth and
  handle only 8-bit PNGs (palette included), which is what the image service produces. Any other depth (16-bit, or
  1/2/4-bit) is refused with the reason `bit depth N not supported`: `defringe` records the output as `skipped` and
  leaves it byte-identical with no `outputs-raw/` copy, and `review-cmd` builds no composite or tile for it, prints
  the reason on stderr and still hands the output itself to the reviewer.
- **The documented fringe repair was refused after QA.** `asset-gen` step 7 said to run `defringe` after a
  `png-edge-fringe` FAIL, but `qa.json` then binds the outputs, so `defringe` refused. Step 7 (and the `comfyui`
  skill and the domain doc) now document `assetgen.py defringe --run <run> --force [--alpha-floor N]`, then `embed`,
  `qa` and both image reviews again (`review-cmd --phase image` and `review-image-claude.json`). The refusal and the
  `next:` hint after a forced run name `embed`, `qa` and both image reviews.
