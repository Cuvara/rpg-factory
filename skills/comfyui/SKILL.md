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
  purpose < `render --param`. `resolve` prints the source file of every field and param.
- **Template format** (`templates/assetgen/workflows/image-generate.json`): `params` (`type` string, int, number,
  bool or enum with `options`; `default`; `required`), `output_node` (a SaveImage node id), `workflow` (ComfyUI API
  format `{"<id>": {"class_type", "inputs"}}`, links `["<node id>", <output index>]`). `{{name}}` as the whole string
  takes the typed value; inside a longer string it is text. `render` fails on an undeclared or missing param.
- **Image node:** the core templates use the 9router custom node `NineRouterImage` (`user_prompt`, `model`, `size`,
  `quality`, `background`, optional `reference_images`) into `SaveImage`; `NineRouterChat` is the text node. Their
  inputs are snapshotted in `scripts/assetgen/data/known-nodes.json` for offline lint.
- **comfy-mcp** is the official Comfy-Org MCP server (stdio), MCP name `comfy-mcp`, tool ids
  `mcp__comfy-mcp__<tool>`. It talks to the ComfyUI its `COMFY_LOCAL_URL` env names. Ports: registry services
  `comfyui` (headless `main.py`, default port) and `comfyui-desktop` (Comfy Desktop's own port):
  `jq .services registry.json`. The `comfy-mcp` dev tool probes the MCP name and either service.

## Idioms

- **Run sequence:** `server_info` (version, nodes present) -> `validate_workflow` (`<run>/workflow.json` against the
  live node list) -> `upload_file` (image-edit reference; returns the input-folder name) -> `run_workflow`
  (`workflow_path`, `wait`) -> `job` (status by prompt id) -> `fetch_outputs` (`prompt_id`, `out_dir` `<run>/outputs`).
  `nodes`, `list_workflow_slots` and `set_workflow_slot` inspect or patch; asset-gen renders instead of patching.
- **Setup** (once, the user's machine): install the `comfy-mcp` package into a Python env, register it for Claude as
  `comfy-mcp` with `COMFY_LOCAL_URL` set to the running ComfyUI, start ComfyUI (Desktop or headless). A newly added
  MCP server loads only in a new session.
- **Add a purpose:** copy the closest `templates/assetgen/purposes/*.json` (game layer for one game, core for all),
  keep the schema id, write guidance, both rubrics, `qa` (size `mode` exact|min|aspect|any, `alpha`
  required|forbidden|any, `transparent_corners`, `tileable`, `not_blank`) and `handoff_domain`. Add a style the
  same way. **Add a template:** API-format graph with placeholders, every placeholder a declared param, `output_node`
  set; then `assetgen.py lint [--authoring <A>]` and a live `validate_workflow`.
- **Game override:** prefer `extends` with only the changed fields, so core fixes still reach the game.

## Pitfalls

- **The returned size can differ from the requested one:** the gateway has answered a square request with a
  landscape image. The purpose QA's size mode handles it; `exact` is opt-in (`scripts/assetgen/qa.py` docstring,
  `size` param description in `templates/assetgen/workflows/image-generate.json`).
- **A model id the gateway does not serve passes `validate_workflow`** (the `model` input is a free STRING) and fails
  only at run time. Known bad ids are `warn_values` in `scripts/assetgen/data/known-nodes.json`; the working default
  is the template's `model` param - never hard-code an id in a prompt or skill.
- **Credentials are read by the node at run time** from the user's local provider configuration; templates, params
  and run records carry none. `assetgen.py lint` fails a file with a URL, host address or credential-shaped key
  (`FORBIDDEN` in `scripts/assetgen/lint.py`).
- **No local models:** the install runs API nodes only, so a graph with a checkpoint loader or sampler has nothing
  to load; the offline snapshot knows only the 9router and IO nodes (`scripts/assetgen/data/known-nodes.json`).
- **LoadImage reads ComfyUI's input folder, not the run directory:** upload the reference with `upload_file` and pass
  the returned name as `reference_image` (`templates/assetgen/workflows/image-edit.json`); keep the original as
  `<run>/references/<that name>` too, or the gen-run quality plugin fails provenance and cannot bind it.
- **SaveImage writes into ComfyUI's output folder** under `filename_prefix` (`render --run` sets
  `assetgen/<run-id>`, `scripts/assetgen/assetgen.py` `render`); only `fetch_outputs` puts the PNGs into the run.
- **Desktop and headless use different ports** (`registry/core.json` services `comfyui`, `comfyui-desktop`):
  `COMFY_LOCAL_URL` pointing at the one that is not running makes every tool fail while the snapshot shows the other
  service up.

## Testing

- `tests/assetgen.test.sh`: layers, override precedence, render goldens per purpose, lint, review-cmd, PNG QA,
  manifest and the quality plugin (temp authoring repo, no network, no ComfyUI).
- `assetgen.py lint --authoring <A>` for data; `validate_workflow` for the live node check. A real generation needs
  ComfyUI and comfy-mcp up; without them it is `NOT_RUN`, never PASS.

## Tools

- `comfy-mcp`: the run sequence above (Idioms). Not OK: `assetgen.py render` only; generation `NOT_RUN` and a
  person runs `workflow.json` in ComfyUI.
