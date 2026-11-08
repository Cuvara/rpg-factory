# Asset generation workflow

## Responsibility and readiness

The `assetgen` domain owns AI image generation: the game layer of generation data (purposes, styles and ComfyUI workflow templates) and one record per generation run. Its lead is `asset-gen`. A run turns a purpose, a style and a workflow template into a reviewed prompt, runs the workflow in ComfyUI through the `comfy-mcp` MCP server, checks the images, and records the result as a `gen-run`. The images reach production only through a human-approved handoff to 2D Art, 3D Art, UI/UX or VFX. Readiness: **production** for records and checks. The generation step needs ComfyUI and comfy-mcp; without them it stays `NOT_RUN`.

| Module | Registered path | Purpose |
|---|---|---|
| `authoring.assetgen` | `assetgen/` | Game layer `assetgen/{purposes,styles,templates}/`, which overrides or extends the core data under the plugin's `templates/assetgen/`, run directories `assetgen/runs/<run_id>/`, the style lock's `assetgen/project.json`, and anchors and rejections under `assetgen/styles/<style-id>/` |

Fast checks: `artifact-lint`, `artifact-trace`, `assetgen-quality` (`artifact-quality.py --domain assetgen`), and `assetgen-lint` (`assetgen.py lint --authoring .`: the game-layer data, `assetgen/project.json`, anchors and rejections, so an active anchor whose source run has no `run.md` fails too). The engine is `scripts/assetgen/assetgen.py`. Its module docstring documents the data layers, the commands and the run directory.

## Kind and lifecycle

`gen-run` (schema `docs/schemas/kinds/gen-run.schema.json`, kind template `templates/assetgen/gen-run.md`) is `assetgen/runs/<run_id>/run.md`. The `run_id` is `<slug>-NNN` and the artifact ID is `AGEN-<run_id>`. `assetgen.py manifest` writes it with `---json` front matter. The `spec` records:

- `purpose`, `style` and `template` refs: ID, layer, source files and the content hash of the merged data
- the `handoff_domain` (`art2d`, `art3d`, `ui` or `vfx`), the params as rendered (`spec.params`: read back from `workflow.json` by `assetgen.py` `rendered_params`, so a `render --param` value shows; `spec.json` before the first render; the reviews are shown and bound to these params, and `gen-run-provenance` FAILs a record whose `spec.params` differ from them), and the final prompt with its SHA-256 and `prompt_author`
- `prompt_review` and `image_review` (`by`, `state`, `findings`, `prompt_sha256`, `requirements_sha256`, `outputs`, read from `review-prompt.json` and `review-image.json`; `scripts/assetgen/runfiles.py`). `review-cmd` hands the reviewer the SHA-256 of the prompt, a requirements hash and, for the image review, the SHA-256 of every output, and asks it to copy them into its verdict. That binding ties the verdict to the bytes it reviewed and the requirements it judged against. The requirements hash (`runfiles.requirements_sha256`) covers the purpose, style and template content hashes and the rendered params the review prompt showed (`runfiles.rendered_params`: `workflow.json` read back over `spec.json`), so a `render --param` that changes a param after a review makes it stale, and for the image review also the effective generation inputs (`runfiles.generation_inputs`: the whole `workflow.json` graph, prompts included, so every `render --param` override is bound, plus the SHA-256 of each image-edit reference kept as `references/<name>` in the run directory).
- `generation` (`generated_by`, `tool: comfyui`, `model`, `workflow`) and `outputs` (`path`, `sha256` of each `outputs/*.png`)
- `qa`: the deterministic image QA from `qa.json`. For a purpose with alpha it includes `png-edge-fringe`: the colour of low-alpha edge pixels against their opaque neighbours, and the output composited on black and on white. The image service leaves a coloured fringe in the RGB of pixels with alpha 1-31 (the live style-lock e2e of 2026-11-08: an orange and red speckle around a barrel prop, visible only on a dark background), and body pixels at alpha 251-254. `assetgen.py defringe --run DIR [--alpha-floor N]` runs after `fetch_outputs` and before `embed` and `qa`. It bleeds the colour of opaque neighbours into low-alpha pixels (premultiply-safe, stdlib) and with `--alpha-floor N` sets every alpha below N to 0. It keeps each original under `outputs-raw/`, records the params and each output's SHA-256 before and after in `defringe.json`, and `manifest` adds a `- Defringe:` line to the `run.md` body (`STALE` when the outputs no longer carry the pixels it wrote). A second run starts from the kept originals. It refuses an approved run, and outputs that `qa.json` or an image review already binds unless `--force`; those records must then run again.
- `claude_image_review`: Claude's own visual review, read from `review-image-claude.json` (the review schema and the image review binding, `"by": "claude"`, written by the agent). It is recorded for the human approver and never stands in for `image_review`.
- `trace.failed_attempts`: the run ids of earlier attempts of the same series (`<slug>-NNN` with a lower number) whose directory has no `run.md`. A failed attempt keeps its directory, and the next attempt takes the next number.

The envelope `provenance` is `{generated_by, tool: comfyui, model}`. Do not hand-edit a record. Fix the run, then run `manifest` again. A changed set of outputs resets the status to `proposed`. When nothing the approval binds changed and the new `run.md` is byte for byte the approved one, `manifest` keeps an `approved` status and the approval stays bound. Any other change (also another `--title` or `--prompt-author`) resets it to `proposed` and names the changed fields.

The lifecycle is the shared lifecycle v2. `manifest` writes `proposed`, an independent review record moves a run to `reviewed`, and `approved` always needs the human gate `assetgen-approval`. A `proposed` run may go straight to `approved`: the reviews are verdict files the quality plugin requires, so `run.md` never has to pass through `reviewed`. An approval is a signed record under `approvals/AGEN-<run_id>/`, checked by `artifact-trace` against the domain's `approvers` keys. No keys are registered yet, so an `approved` run stays `HUMAN_REQUIRED` until a maintainer adds one. `assetgen.py approve-record --run DIR --by NAME [--note TEXT]` writes the approval record and the `run.md` status `approved` for a person. It refuses a missing `--by` and an agent or model name (`claude*`, `codex*`, `gpt*`, `SAME_MODEL:*`). The person commits `run.md` and the record in one SSH-signed commit whose signer principal is the `--by` name (the record binds the git blob of that `run.md`). Until then `gen-run-style` reports "approval present but not committed/signed" for an anchor's source run, and the trace grades the approval `HUMAN_REQUIRED`, like a missing approval. Agents never approve on their own judgement, including their own generations: an agent runs `approve-record` only on the person's explicit word and quotes it in its report.

## Quality rules

`scripts/checks/domains/assetgen.py` adds these checks to the shared envelope, schema, lifecycle, trace and approval checks:

| Check | Rule |
|---|---|
| `gen-run-location` | The record is `assetgen/runs/<run_id>/run.md` and its ID is `AGEN-<run_id>`. |
| `gen-run-prompt-review`, `gen-run-image-review` | The state is `PASS`. The reviewer (`by`) is a model other than `prompt_author`, compared by model family: the name up to the first `-`, `_`, `/`, `.`, `:`, `@` or space, so `claude-sonnet` counts as `claude`. The review file is the evidence: it must exist, the record must equal what is read from it (else `FAIL`), and its binding must name the current prompt, the current requirements (purpose, style and template content hashes and the rendered params of `workflow.json` over `spec.json`, never `spec.json` substituted for the record; for the image review also the generation inputs of `workflow.json`) and, for the image review, the recorded outputs. A missing, invalid, unbound or stale review file is missing work, so re-resolving a purpose with a stricter rubric invalidates the old reviews. |
| `gen-run-claude-review` | Claude's own visual review (`review-image-claude.json`). The record must equal the file (else `FAIL`). A missing, invalid, unbound or stale file, or one by another model than Claude, is a `WARN`. A `FAIL` verdict is missing work. It never grades the independent image review: a run with only a Claude review still fails `gen-run-image-review`. |
| `gen-run-qa` | `qa.json` is the evidence. It hashed the recorded output bytes, and the record's `qa` equals its state and results (else `FAIL`). Its state is `PASS`, and every output has a `PASS` row for each check its purpose requires (from the run's `spec.json`, whose purpose content hash must equal the recorded one). `NOT_AVAILABLE` never grades `PASS`. A `qa.json` that claims `PASS` with a failing row or a missing required check always fails. Rows for unrecorded outputs fail. A `qa.json` graded with another purpose content hash (`purpose_sha256`) or requested size (`requested_size`, from `workflow.json`) than the run has now is stale and fails. A malformed purpose `qa` block fails (`qa` writes a `purpose-qa` FAIL row instead of grading). |
| `gen-run-outputs` | Outputs are recorded and lie inside the run directory. Every file exists with the recorded SHA-256, and no `outputs/*.png` is unrecorded. |
| `gen-run-provenance` | `provenance` has `generated_by`, `tool: comfyui` and `model`, and equals `spec.generation`. The rendered `workflow.json` is present, its 9router prompt inputs equal the recorded prompt, and every LoadImage reference it names is kept as `references/<name>` in the run directory. `spec.params` equals the rendered params (`runfiles.rendered_params` of `workflow.json` over `spec.json`), else `FAIL` (re-run `manifest`). |
| `gen-run-style` | The style lock (`spec.style_lock`). The style reference is well formed, names the run's style and resolves. A newer version or another hash is a `WARN`, because anchors of the recorded version stay valid. `run.md` equals `spec.json`, and an override carries a reason (`WARN`). Every recorded reference names an anchor that exists and is active (retired since the run: `WARN`), approved by a person, with image bytes equal to its `image_sha256`, the pick and the source output, and a source gen-run approved in `run.md` and by its signed approval. An active anchor promoted from a run fails while that run is not approved. The image reviews also bind the style reference and the anchors shown, else they are stale. A run recorded before the style lock with no anchor promoted from it gets no row. |
| `gen-run-refs` | Purpose, style and template resolve in the core and game layers. A content hash that changed since the run is a `WARN`, because the record keeps what was used. `prompt_sha256` and `prompt.md` match the recorded prompt, and the contract `assetgen-to-<handoff_domain>` is registered. |

These violations always `FAIL`: a hash or prompt mismatch, a path that escapes the run directory, an unmarked same-model review, and an unresolved ref. Missing work also fails once the run is `proposed` or later: a review, QA, an output file or the model. While the run is `draft`, `rejected`, `blocked`, `superseded` or `deprecated`, missing work is a `WARN`.

**Same-model fallback (decision).** Claude writes the prompt and Codex reviews it and the images. When Codex is unavailable, a Claude review is still allowed, but only as an explicit fallback: the verdict file records `"by": "SAME_MODEL:<model>"`, for example `SAME_MODEL:claude`. The `by` field is the one reviewer field that `manifest` copies into the record, so the marker survives every `manifest` run. A marked same-model review grades `WARN`, never `PASS`, so the human approver sees that no independent model reviewed the run. An unmarked same-model review fails. A marker on a review by another model also fails, because that review is not a fallback.

## Style lock

Prompt text alone drifts between generations. The style lock keeps every asset of one game on one approved, versioned style. It has five parts: structured style data, approved anchor images passed to the image node as `reference_images`, rejections as data, deterministic consistency checks, and an image review that sees the anchors. The engine is `scripts/assetgen/stylelock.py` (records, resolution, selection, drift) and `scripts/assetgen/consistency.py` (the QA signals). Their module docstrings are the reference. All of it is deterministic: no clock and no recency, so the same inputs give the same selection.

### Project config

`<authoring>/assetgen/project.json` (`rpg-factory.assetgen-project/1`, `docs/schemas/assetgen-project.schema.json`) is the single source of truth for the game's style:

| Field | Meaning |
|---|---|
| `style` | `{id, version}` of the default game style. `version` must equal the style file's `version`, else lint fails and `resolve` refuses. |
| `allowed_styles` | The style IDs a run may name with `--style`. |
| `families` | Maps an asset family (`characters`, `environment`, `props`, `ui`, `vfx`, ...) to a game style that `extends` the base style. |
| `art_direction` | Upstream refs `{artifact, rev}` of the approved `art-direction-2d` or `-3d` artifacts the style follows. |

`resolve` picks the family from `--family`, else the purpose's `default_family`, else none (`family_source` is `flag`, `purpose` or null). It picks the style from `--style`, else `families[family]`, else `project.style.id`. It refuses (exit 1) a `--style` that is neither in `allowed_styles` nor a `families` value, and a `deprecated` style, unless `--style-override REASON` is given. The reason is recorded as `spec.style_lock.override` and printed in `run.md`, and the quality plugin gives a `WARN` so the approver weighs it. Without `project.json` the behaviour stays as before the style lock: the purpose's `default_style` or `--style`, and `spec.style_lock.project` is null. `assetgen.py lint --authoring` then reports a `WARN` row `no assetgen/project.json`.

### Versioned, structured styles

A style file carries `version` (an integer from 1) and `status` (`draft`, `active` or `deprecated`; absent means active). A style change is a new version. Structured fields are data and are never parsed from prose. Each one may still be a prose string. As an object, its `text` is the prompt hint and the other keys feed the checks:

- `palette`: `colors` (`hex` and `role`), `max_distance`, `min_share`, `severity`.
- `lighting`, `shape_language`: `text` and structured keys.
- `outline`: `text`, and `edge_darkness` (`max_luminance`, `min_ratio`, `severity`) for the edge check.
- `forbidden[]`: like `avoid`, it joins the prompt's avoid list and the review checklist.
- `canvas`: per family `{aspect: "W:H", min_side, tolerance, severity}` (`severity` `warn` or `fail`), never an exact pixel canvas.
- `tone`: `{tolerance, severity}` turns on the luminance and saturation check against the anchors.

A purpose may declare these fields:

- `default_family`.
- `dimensions`: a subset of `palette`, `lighting`, `shape`, `texture`, `composition` and `line`.
- `max_references`: a template may set it too, and the smaller value wins (default `stylelock.DEFAULT_MAX_REFERENCES`).
- `qa.outlines`: turns on the edge check.
- `qa.size`: the `png-size` rule. `mode` is `exact` or `min` (against `expect`, default the requested size), `aspect` (ratio within `aspect_tolerance`, optional `min_area` share of the expected pixels), `orientation` (`orientation` `landscape`, `portrait` or `square`, or `auto` from `expect`; square when the long side is at most `square_tolerance` longer, default 0.05; the core square purposes `icon`, `sprite-2d` and `texture-tileable` set 0.15, which real service outputs such as 1322x1190 meet), `area` (no aspect at all) or `any`. A landscape or portrait purpose may set `allow_swap: true` (a boolean, default false; `ref-3d-turnaround` sets false), so the swapped orientation (1024x1536 returned for a 1536x1024 request) passes. `aspect`, `orientation` and `area` also need a short side of at least `min_side` (default 256) and, with `min_pixels`, at least that many pixels. The image service ignores the requested size (the e2e returned 1672x941 for both 1536x1024 and 1024x1024 requests), so the core purposes grade orientation or area plus these floors, never an exact size. Every core purpose sets both floors: `concept-2d` (area, short side 768) and `ref-3d-turnaround` (landscape, short side 512) 1000000 pixels, `icon`, `sprite-2d` and `texture-tileable` (square orientation), `ui-element` and `image-edit` (area) a 512 px short side and 512x512 pixels, so a 256x256 output fails each. The per-purpose values are data (`templates/assetgen/purposes/*.json`); `runfiles.qa_errors` validates them and `lint` reports the same rules.

A style's optional `STYLE.md` is explanation only. Art decisions stay ADR-style artifacts of the existing kinds. Machine-checkable constraints live only in the structured style data.

Every spec, review binding, anchor, rejection and gen-run records the same style reference `{style_id, version, sha256}`. The `sha256` is the content hash of the merged style data.

### Anchors and approval

An anchor is an approved image of one style version: `<authoring>/assetgen/styles/<style-id>/anchors/<anchor-id>.json` plus `<anchor-id>.png` (`rpg-factory.assetgen-anchor/1`, `docs/schemas/assetgen-anchor.schema.json`). Its fields:

- `status`: `proposed`, `active` or `retired`.
- `style` (the style reference), `family`, `dimensions[]`, and `strength`: `canonical`, `strong` or `supporting`.
- `image` and `image_sha256`, and `source_run` (`run_id`, `output`, `sha256`).
- `approved_by` and `approved_on`.

`assetgen.py promote-anchor --run DIR --output N|PATH --family F --dimensions a,b --strength S [--id ID]` writes a `proposed` anchor with `approved_by` null and copies the output PNG next to it. It refuses an output whose SHA-256 differs from `run.md` or `qa.json`, a style directory outside the authoring repo, and an existing ID. It never writes an `active` anchor: a person sets `status: active`, `approved_by` and `approved_on`.

An active anchor is valid only when its source gen-run is `approved`. The quality plugin also checks three things: the signed approval of `AGEN-<run_id>`, that the image bytes equal `image_sha256` and the source output, and that `approved_by` names a person, not an agent or model (`claude*`, `codex*`, `gpt*`, `SAME_MODEL:*`). Anchors of an older style version stay valid. Selection uses only the run's version.

### Rejections

A rejection is `<authoring>/assetgen/styles/<style-id>/rejections/<id>.json` (`rpg-factory.assetgen-rejection/1`, `docs/schemas/assetgen-rejection.schema.json`). It records a rejected `asset` (with `run`: `run_id`, `output`, `sha256`) or a rejected `direction` (with `text`). The `reason` is one of `style_drift`, `palette_off`, `too_detailed`, `wrong_lighting`, `wrong_perspective`, `text_or_logo`, `anatomy` and `other`. A direction and the reason `other` need `text`. `assetgen.py reject --type asset|direction --reason R ...` writes one. `--any-version` records version null, so the rejection applies to every version. A rejection is data, not an approval, so an agent may record one.

A rejection is relevant to a run when all three hold: it names the run's style ID, its family is null or the run's family, and its version is null or the run's version.

### Deterministic selection

`resolve` records `spec.style_lock`: `project` (path and SHA-256, or null), `family`, `family_source`, `style` (the style reference), `override`, `max_references`, `references` and `rejections`.

The candidates for `references` are the valid active anchors of the run's style ID and version. They are sorted by these keys, in order, and capped by `max_references`:

1. Family match first.
2. The larger overlap of the anchor's dimensions with the purpose's.
3. Strength: `canonical`, `strong`, `supporting`.
4. ID.

An anchor of another family than the run's can still be selected after the family's own anchors. It is a fallback: `resolve` warns and names each such pick. `anchor_family_fallback: false` in the purpose, else in `project.json` (default true), forbids it, so only anchors of the run's family are selected.

Each pick records `anchor_id`, `family`, `strength`, `dimensions`, `image` (`references/anchor-<id>.png`), `sha256` and `reason[]` (for example `family match`, `dimensions: palette, line`, `strength canonical`). The requirements hash covers the style reference, the family, the reference hashes and the relevant rejections (ID and content hash of each `spec.style_lock.rejections` entry) only when `style_lock` is present, so a changed rejection set makes earlier reviews stale, and runs recorded before the style lock keep their hash.

`render --run` copies each selected anchor to `<run>/references/anchor-<id>.png`. It refuses when the anchor image no longer has the selected SHA-256. It adds one `LoadImage` node per anchor and a chain of core `ImageBatch` nodes into `NineRouterImage.reference_images`, in both `workflow.json` and `workflow.ui.json` (`scripts/assetgen/assetgen.py` `wire_references`). An `image-edit` reference stays the first image. The agent uploads every `references/*` file with comfy-mcp `upload_file` under its name before `run_workflow`.

### Consistency QA

With `spec.style_lock`, `qa` adds four rows per output (`scripts/assetgen/consistency.py`, sampled like the other QA checks):

| Row | Signal |
|---|---|
| `style-palette` | The share of opaque pixels within `max_distance` of a palette colour is at least `min_share`. |
| `style-tone` | Mean luminance and mean saturation lie within the anchors' range, widened by `tolerance`. |
| `style-edges` | Purposes with `qa.outlines` only: the share of dark pixels on strong edges is at least `edge_darkness.min_ratio`. |
| `style-canvas` | The aspect is within `tolerance` of the family's `aspect`, and the short side is at least `min_side`. |

A miss is a `WARN`. It is a `FAIL` only when the style field sets `severity: fail`. A row is `NOT_AVAILABLE` when its style field is absent or prose, when there are no anchors (tone), when the purpose has no `qa.outlines` (edges), or when the family has no canvas entry. The style rows are never required checks: `WARN` and `NOT_AVAILABLE` keep the `qa` state, and a style `FAIL` row fails it. The default thresholds are in the `consistency.py` docstring.

The image review (`review-cmd --phase image`) attaches the selected anchors with `-i` after the outputs and previews. For each output with alpha it writes and attaches `review/composite-dark.png` and `review/composite-light.png`, the output composited on a dark and on a light background, and the rubric asks to judge the edges on both. Claude's own review looks at the same composites. It adds the rubric item "The image matches the attached anchors in palette, lighting, line, detail density and rendering." and one item `Not repeated: <reason> - <text>` per relevant rejection. Its binding adds `style` and `anchors` (`anchor_id`, `sha256`). Claude's own review (`review-image-claude.json`) uses the same rubric and binding. The prompt review lists the direction rejections under "Must avoid". Both review phases also list the style's `forbidden` items and the resolved text of `outline` and `shape_language`, next to the lighting and palette hints, so the reviewer can enforce them.

### Drift

`assetgen.py drift --authoring DIR [--json]` is read-only, exits 0 and prints `rpg-factory.assetgen-drift/1`. It lists every gen-run, anchor and rejection whose recorded style reference is behind the current style:

- `older-version`: the recorded version is lower.
- `hash-changed`: the same version with another content hash.
- `style-missing`: the style no longer resolves.
- `style-id-mismatch`: the record names a style id that is neither the `project.json` style nor a family style, for example anchors and runs of the exploration style after the bootstrap. Their anchors never feed a run of the project's styles. The text line names the project style (and the version state when the record is also behind).

Review those runs again or regenerate them. The records stay valid for the version they name.

### Bootstrap a game style

1. Exploration `concept-2d` runs with several styles or prompts.
2. A person picks the images that define the style.
3. `promote-anchor` for each picked image.
4. A person approves the source gen-runs and activates the anchors.
5. `project.json` and the game style with `version: 1` and `status: active`, with the structured `palette`, `tone` and `canvas` fields. `lint` gives a `WARN` for an active game style without a usable one (absent, empty such as `canvas: {}`, or malformed), because every `style-*` QA row would be `NOT_AVAILABLE`.

Anchors feed only runs of their own style id and version, so a new game style id has no anchors until runs under it are approved and promoted. Either promote again from approved runs under the game style id, or use the game style id as the exploration style in step 1. The `asset-gen` skill runs this flow (`skills/asset-gen/references/style-lock.md`).

## Skills and commands

The lead skill `asset-gen` runs a generation from routing to handoff: pick a purpose and style, resolve, write the prompt, the Codex prompt review, render, generate through comfy-mcp, QA plus a visual and a Codex image review, `manifest`, then a human approval and the handoff. It also bootstraps a game style and records anchors and rejections. The tech skill `comfyui` (paths `assetgen/`, used by `asset-gen`, `art-2d`, `art-3d`, `ui-ux` and `vfx`) explains the template format, the layer precedence, the comfy-mcp tool sequence, the anchor wiring, the image node's pitfalls and how to add a purpose, style or template. `/rpg-factory:assetgen` (`factory-cmd.py assetgen`) runs the read-only engine verbs `list`, `show`, `resolve`, `lint`, `review-cmd` and `drift`. It refuses `render`, `defringe`, `embed`, `qa`, `manifest`, `approve-record` and `resolve --out`, because they write into a run directory. It refuses `promote-anchor` and `reject`, because they write style-lock records into the authoring repo, and `publish`, because it uploads to ComfyUI.

## Tools

The `comfy-mcp` dev tool (registry `dev_tools`, kind `mcp`) is the official Comfy-Org comfy-mcp server, configured as MCP server `comfy-mcp` (or `comfy`). Its availability probe also needs a reachable ComfyUI: the registry service `comfyui` (headless default port) or `comfyui-desktop` (the Comfy Desktop session). When only ComfyUI is down, the tool is `DOWN`. The doctor and the snapshot print names and reachability only, never configuration values. Model IDs and image sizes are template params (`templates/assetgen/workflows/*.json`), never prose. Templates and run records carry no endpoints or credentials, because the ComfyUI node reads its own provider configuration.

## Handoffs

| Contract | Destination | Use |
|---|---|---|
| `assetgen-to-art2d` | `authoring:art2d/exports/` | A runtime export or asset spec cites the gen-run. |
| `assetgen-to-art3d` | `authoring:art3d/models/`, `authoring:art3d/materials/` | Turnaround references for model specs, and tileable textures for material specs. |
| `assetgen-to-ui` | `authoring:ui/specs/` | UI element parts. |
| `assetgen-to-vfx` | `authoring:vfx/assets/` | Effect textures. |

Every handoff carries the gate `assetgen-approval`. Only an `approved` gen-run hands off. The receiving lead cites the gen-run ID in the `sources` of its artifact. 2D Art's rule is in [2D Art](art2d.md).
