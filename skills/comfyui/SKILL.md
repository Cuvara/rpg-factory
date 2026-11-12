---
name: comfyui
description: How asset-gen's ComfyUI side actually works - the comfy-template format (rpg-factory.comfy-template/1, {{param}} placeholders, typed params, output_node, extends), core versus game-layer precedence, the comfy-mcp setup and tool sequence, the 9router image node's behaviour and pitfalls (credentials read by the node, returned size, unsupported model ids, no local models), Desktop versus headless ports, and how to add a purpose, style or template. Use when you render, run, debug or review a ComfyUI workflow for an asset-gen run, or extend the generation data. Not for deciding scope, rules, checks or gates of a run (asset-gen and the art, UI and VFX leads own those), and not for approving or handing off images.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py:*)
---

# ComfyUI for asset generation (templates, comfy-mcp, 9router node)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `asset-gen`, `art-2d`, `art-3d`, `ui-ux`, `vfx`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths `scripts/`, `templates/`, `registry/` are the plugin root (`${CLAUDE_PLUGIN_ROOT}`); `assetgen/` is the
authoring repo. `assetgen.py` is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`.

## Applies when / Not when

- **Applies:** rendering or validating a workflow, running it through comfy-mcp, a ComfyUI or image-node error, a
  returned image that looks wrong for its params, writing or overriding a purpose, style or workflow template.
- **Not when:** which asset to make, the review and approval flow, the record and the handoff (`asset-gen`); art,
  UI or VFX specs (`art-2d`, `art-3d`, `ui-ux`, `vfx`).

## Scope

Repos `authoring`. Owns no module, contract or check. Reads the plugin's core data and engine; writes only what the
lead's workflow asks for in a run directory or the game layer.

## Architecture

- **Three data kinds, two layers** (`scripts/assetgen/layers.py` docstring): purpose
  (`rpg-factory.assetgen-purpose/1`: prompt guidance, prompt and image rubrics, params, QA expectations, default
  template, handoff domain), style (`rpg-factory.assetgen-style/1`: prefix, suffix, avoid, palette, lighting, params)
  and workflow template (`rpg-factory.comfy-template/1`). Core: `templates/assetgen/{purposes,styles,workflows}/`;
  game: `assetgen/{purposes,styles,templates}/`. The id is the file name.
- **Precedence:** a game file with a core id and no `extends` replaces it; `"extends": "<id>"` deep-merges onto it
  (objects key by key, the game wins; lists and scalars replace). Params, low to high: template default < style <
  purpose < `render --param`. `resolve --verbose` prints the source file of every field and param. A purpose's
  `constraints` (`scripts/assetgen/data/precedence.json`) win over the style's hint of the same name (`spec.hints`).
- **Template format** (`templates/assetgen/workflows/image-generate.json`): `params` (`type` string, int, number,
  bool or enum with `options`; `default`; `required`), `output_node` (a SaveImage node id), `workflow` (ComfyUI API
  format `{"<id>": {"class_type", "inputs"}}`, links `["<node id>", <output index>]`). `{{name}}` as the whole string
  takes the typed value; inside a longer string it is text. `render` fails on an undeclared or missing param.
- **Two renders of one graph:** `render` writes `<run>/workflow.json` (API format, what `run_workflow` runs and the
  review binds) and `<run>/workflow.ui.json` (ComfyUI frontend / LiteGraph format: node positions and sizes, titles,
  links, `widgets_values` in input order, the run id in `extra`), which converts back to the same API graph. The prompt
  is a `PrimitiveStringMultiline` node ("Text (Multiline)", input `value`) titled `Prompt (Claude, Codex review <state>)`
  linked into `NineRouterImage.user_prompt`; `render --run` fills the state of `review-prompt.json` (`STALE` when its prompt or requirements hash no longer matches; a non-Codex reviewer replaces `Codex review`, e.g. `review SAME_MODEL:claude WARN`).
- **Image node:** the core templates use the 9router custom node `NineRouterImage` (`user_prompt`, `model`, `size`,
  `quality`, `background`, optional `reference_images`) into `SaveImage`; `NineRouterChat` is the text node. Their
  inputs are snapshotted in `scripts/assetgen/data/known-nodes.json` for offline lint.
- **Anchor wiring** (style lock, `scripts/assetgen/assetgen.py` `wire_references`): for each anchor
  `spec.style_lock.references` selected, `render --run` copies its image to `<run>/references/anchor-<id>.png` and adds
  a `LoadImage` (`image` `anchor-<id>.png`, title `Anchor <id> (<strength>)`) plus a chain of core `ImageBatch` nodes
  (`image1`, `image2`) into `NineRouterImage.reference_images`; an existing `reference_images` link (image-edit) is
  `image1` of the first batch, so the edit's own image stays first. New node ids are the next free integers in both
  files. Selection and its order are the engine's (`scripts/assetgen/stylelock.py` docstring), never edited in the graph.
- **comfy-mcp** is the official Comfy-Org MCP server (stdio), MCP name `comfy-mcp`, tool ids
  `mcp__comfy-mcp__<tool>`. It talks to the ComfyUI its `COMFY_LOCAL_URL` env names. Ports: registry services
  `comfyui` (headless `main.py`, default port) and `comfyui-desktop` (Comfy Desktop's own port):
  `jq .services registry.json`. The `comfy-mcp` dev tool probes the MCP name and either service.

## Idioms

- **Run sequence:** `server_info` (version, nodes present) -> `assetgen.py graph-lint --run <run>` (exit 0) ->
  `validate_workflow` (`<run>/workflow.json` against the live node list) -> `upload_file` (every `<run>/references/*`
  file under its own name: the image-edit reference and each `anchor-<id>.png`; returns the input-folder name) ->
  `assetgen.py budget --run <run>` (exit 1 or `remaining 0` (at-limit): no `run_workflow`, stop and ask the user) ->
  `run_workflow` (`workflow_path`, `wait`) -> `job` (status by prompt id) -> `fetch_outputs` (`prompt_id`, `out_dir`
  `<run>/outputs`) -> `assetgen.py finalize --run <run>` (defringe for a purpose with `qa.alpha` required, then embed,
  then qa, in that fixed order; never `qa` alone). `nodes` and `list_workflow_slots` only inspect.
- **Authoring rule (comfy-mcp):** comfy-mcp runs only a graph from `assetgen.py render` of the purpose's template (core
  or a game-layer one that `extends` it), laid out per [references/workflow-style.md](references/workflow-style.md).
  Before any `run_workflow`, `assetgen.py lint`, `assetgen.py graph-lint` (the template, and `--run <run>`) and a live
  `validate_workflow` pass (graph-lint exit 1: no `run_workflow`; fix the template, render again). Never run a graph
  patched with `set_workflow_slot` or by hand without rendering it again (render, not patch). No free-form graph for an
  asset-gen run: no hand-built graph, no `run_template`, `generate_image`, `fetch_template`, `vary_workflow` or `emit_partner_workflow`.
- **Node pack version:** `server_info` shows the `comfyui_9router` pack; when outdated, report its version and let the
  user update it - never `update_comfyui`, `install_node` or any other update yourself. The flag compares the pack's
  hash with ComfyUI's own commit: for a pack inside the ComfyUI checkout report it as unverified, never an update on it alone.
- **See the run in ComfyUI:** `run_workflow` only queues the API graph on `/prompt` and opens no canvas tab; optional
  `assetgen.py publish --run <run> --comfy-url <URL>` uploads `workflow.ui.json` via the userdata API to Workflows >
  assetgen, writing nothing locally (exit 0 PASS, 1 FAIL: HTTP error, 2 usage: bad run id or URL, 3 `NOT_AVAILABLE`:
  connection refused). An embedded output PNG dragged in restores the graph.
- **Setup** (once, the user's machine): invoke `rpg-factory:comfy-desktop-setup` (a local Desktop instance, the vendored
  9router node, comfy-mcp registered with the running port for Claude and Codex; its own `--check` first). Headless ComfyUI: install `comfy-mcp` yourself and set `COMFY_LOCAL_URL`. New MCP servers load only in a new session.
- **Add a purpose:** copy the closest `templates/assetgen/purposes/*.json` (game layer for one game, core for all),
  keep the schema id, write guidance, both rubrics, `constraints` (only the technical hints of
  `data/precedence.json`; lint fails any other), `qa` (size `mode` exact|min|aspect|orientation|area|any;
  aspect, orientation and area take the floors `min_side` and `min_pixels`, aspect `aspect_tolerance` and `min_area`
  (the share of the expected pixel count), orientation `orientation`, `square_tolerance` and `allow_swap`; `alpha`
  required|forbidden|any, `transparent_corners`, `tileable`, `not_blank`) and `handoff_domain`. `lint` reports a bad
  game value on the game file that holds it, never on the core file it extends. Add a style the same way.
- **Add or change a template:** [references/workflow-style.md](references/workflow-style.md) "Changing a template";
  a game override `extends` with only the changed fields, so core fixes still reach the game.
- **Style data for the checks:** structured style fields (`palette` colours, `outline.edge_darkness`, `canvas` per
  family, `tone`, `forbidden`) and purpose `default_family`, `dimensions`, `max_references`, `qa.outlines` are data;
  a field may stay prose (its `text` is the hint). A changed style gets a new `version` (`docs/architecture/domains/assetgen.md` "Style lock").

## Pitfalls

- **The returned size can differ from the requested one, or ignore it entirely** (known issue): a 1536x1024 turnaround
  came back from the gateway as a 2172x724 strip (same pixel count); the live style-lock e2e of 2026-11-08 got 1672x941 for both a
  1536x1024 and a 1024x1024 request, 1322x1190 for a square sprite, 1024x1536 for 1536x1024; the batch probe of 2026-11-12
  (`docs/plans/assetgen-batch/probe.md`) got 1254x1254 for 1024x1024 and, in its one call (model `cx/gpt-5.6-sol-image`),
  one image for `n=2`, so batch variants are separate calls. Image QA reads the real size from the file; no core
  purpose grades the exact size (`exact` is opt-in) but orientation, aspect or area and a minimum area and short side
  real outputs meet (square `icon`, `sprite-2d`, `texture-tileable`: `square_tolerance` 0.15, so 1322x1190 is square;
  `qa.size.allow_swap`, default false, false in `ref-3d-turnaround`, accepts the swapped orientation), per purpose in data
  (`scripts/assetgen/qa.py` docstring, `size` param in `templates/assetgen/workflows/image-generate.json`). A size FAIL
  from the service is not fixed by a new prompt: `asset-gen` stops regenerating. `review-cmd --phase image` states each
  output's true size and QA's verdict; the reviewer does not grade size again.
- **A model id the gateway does not serve passes `validate_workflow`** (the `model` input is a free STRING) and fails
  only at run time. Known bad ids are `warn_values` in `scripts/assetgen/data/known-nodes.json`; the working default
  is the template's `model` param - never hard-code an id in a prompt or skill.
- **Credentials are read by the node at run time** from the user's local provider configuration; templates, params
  and run records carry none. `assetgen.py lint` fails a file with a URL, host address or credential-shaped key
  (`FORBIDDEN` in `scripts/assetgen/lint.py`).
- **No local models:** the install runs API nodes only; a checkpoint loader or sampler has nothing to load and is not
  in the offline snapshot (9router, IO and core image nodes: `scripts/assetgen/data/known-nodes.json`).
- **LoadImage reads ComfyUI's input folder, not the run directory:** upload the reference with `upload_file` and pass
  the returned name as `reference_image` (`templates/assetgen/workflows/image-edit.json`); keep the original as
  `<run>/references/<that name>` too, or the gen-run quality plugin fails provenance and cannot bind it.
- **Fetched PNGs carry no workflow:** comfy-mcp sends no `extra_pnginfo`, so a PNG holds only the `prompt` text chunk;
  `embed` adds the `workflow` chunk (keeps `prompt`; idempotent when equal, a stale chunk is replaced). QA and the
  reviews bind the hash of the embedded file, so `finalize` always embeds before `qa` (`scripts/assetgen/assetgen.py` `embed`).
- **Transparent outputs carry an edge fringe:** the service leaves orange or red speckled colour in the RGB of pixels
  with alpha 1-31 (and body alpha 251-254), invisible on a checkerboard and visible on a dark background. `finalize`
  runs `defringe` first (originals in `outputs-raw/`, the step in `defringe.json`; skipped while it still matches),
  which bleeds opaque neighbour colour into those pixels, QA's `png-edge-fringe` row (`qa.alpha` required) grades it
  (`scripts/assetgen/qa.py`), and the image reviews see `review/composite-dark.png` and `-light.png`. Both take 8-bit PNGs only (IHDR bit depth): another depth is `skipped` untouched, no preview (`depth_refusal`).
  A `png-edge-fringe` FAIL once `qa.json` or a review binds the outputs: `assetgen.py defringe --run <run> --force [--alpha-floor N]`, then `finalize` (`embed`, `qa`), then both image reviews again (`review-cmd --phase image`, `review-image-claude.json`); `finalize --force` only for bound outputs never defringed.
- **SaveImage writes into ComfyUI's output folder** under `filename_prefix`: `resolve --out <run>/spec.json` records
  `assetgen/<run-id>` and `render --run` requires that value and refuses `--param filename_prefix`
  (`scripts/assetgen/assetgen.py` `bind_run`, `render`), so a run directory copied under a new id needs `resolve`
  again. Only `fetch_outputs` puts the PNGs into the run.
- **Anchors need the same upload as an edit reference:** the anchor `LoadImage` nodes name `anchor-<id>.png` in
  ComfyUI's input folder, so upload every `references/anchor-*.png` before `run_workflow`. `render --run` refuses an
  anchor whose image changed since `resolve` (resolve again), and a template with other than exactly one
  `NineRouterImage` node cannot take anchors (`scripts/assetgen/assetgen.py` `copy_anchors`, `wire_references`).
- **Desktop and headless use different ports** (`registry/core.json` services `comfyui`, `comfyui-desktop`): a
  `COMFY_LOCAL_URL` at the one not running fails every tool while the snapshot shows the other service up.

## Testing

- `tests/assetgen.test.sh`: layers, override precedence, render goldens per purpose (API and UI format, the UI
  graph converted back equals the API graph), hints and lint blame, review-cmd, embed, defringe, finalize, budget, publish
  against a fake HTTP server, PNG QA (real returned sizes, a coloured low-alpha fringe), style lock (project config, anchors,
  selection, anchor wiring, consistency rows, drift), manifest and the quality plugin (temp authoring repo, no network, no ComfyUI).
- `assetgen.py lint --authoring <A>` for data; `validate_workflow` for the live node check. A real generation needs
  ComfyUI and comfy-mcp up; without them it is `NOT_RUN`, never PASS.

## Tools

- `comfy-mcp`: the run sequence above (Idioms). Not OK: `assetgen.py render` only; generation `NOT_RUN` and a
  person loads `workflow.ui.json` in ComfyUI.
