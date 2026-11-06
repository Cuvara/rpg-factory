# Asset generation workflow

## Responsibility and readiness

The `assetgen` domain owns AI image generation: the game layer of generation data (purposes, styles and ComfyUI workflow templates) and one record per generation run. Its lead is `asset-gen`. A run turns a purpose, a style and a workflow template into a reviewed prompt, runs the workflow in ComfyUI through the `comfy-mcp` MCP server, checks the images, and records the result as a `gen-run`. The images reach production only through a human-approved handoff to 2D Art, 3D Art, UI/UX or VFX. Readiness: **production** for records and checks. The generation step needs ComfyUI and comfy-mcp; without them it stays `NOT_RUN`.

| Module | Registered path | Purpose |
|---|---|---|
| `authoring.assetgen` | `assetgen/` | Game layer `assetgen/{purposes,styles,templates}/`, which overrides or extends the core data under the plugin's `templates/assetgen/`, and run directories `assetgen/runs/<run_id>/` |

Fast checks: `artifact-lint`, `artifact-trace`, and `assetgen-quality` (`artifact-quality.py --domain assetgen`). The engine is `scripts/assetgen/assetgen.py`. Its module docstring documents the data layers, the commands and the run directory.

## Kind and lifecycle

`gen-run` (schema `docs/schemas/kinds/gen-run.schema.json`, kind template `templates/assetgen/gen-run.md`) is `assetgen/runs/<run_id>/run.md`. The `run_id` is `<slug>-NNN` and the artifact ID is `AGEN-<run_id>`. `assetgen.py manifest` writes it with `---json` front matter. The `spec` records:

- `purpose`, `style` and `template` refs: ID, layer, source files and the content hash of the merged data
- the `handoff_domain` (`art2d`, `art3d`, `ui` or `vfx`), the resolved params, and the final prompt with its SHA-256 and `prompt_author`
- `prompt_review` and `image_review` (`by`, `state`, `findings`, `prompt_sha256`, `requirements_sha256`, `outputs`, read from `review-prompt.json` and `review-image.json`; `scripts/assetgen/runfiles.py`). `review-cmd` hands the reviewer the SHA-256 of the prompt, a requirements hash and, for the image review, the SHA-256 of every output, and asks it to copy them into its verdict. That binding ties the verdict to the bytes it reviewed and the requirements it judged against. The requirements hash (`runfiles.requirements_sha256`) covers the purpose, style and template content hashes and the resolved params, and for the image review also the effective generation inputs (`runfiles.generation_inputs`: the `workflow.json` graph without the 9router prompt inputs, so every `render --param` override is bound, plus the SHA-256 of each image-edit reference kept as `references/<name>` in the run directory).
- `generation` (`generated_by`, `tool: comfyui`, `model`, `workflow`) and `outputs` (`path`, `sha256` of each `outputs/*.png`)
- `qa`: the deterministic image QA from `qa.json`

The envelope `provenance` is `{generated_by, tool: comfyui, model}`. Do not hand-edit a record. Fix the run, then run `manifest` again. A changed set of outputs resets the status to `proposed`.

The lifecycle is the shared lifecycle v2. `manifest` writes `proposed`, an independent review record moves a run to `reviewed`, and `approved` always needs the human gate `assetgen-approval`. An approval is a signed record under `approvals/AGEN-<run_id>/`, checked by `artifact-trace` against the domain's `approvers` keys. No keys are registered yet, so an `approved` run stays `HUMAN_REQUIRED` until a maintainer adds one. Agents never approve, including their own generations.

## Quality rules

`scripts/checks/domains/assetgen.py` adds these checks to the shared envelope, schema, lifecycle, trace and approval checks:

| Check | Rule |
|---|---|
| `gen-run-location` | The record is `assetgen/runs/<run_id>/run.md` and its ID is `AGEN-<run_id>`. |
| `gen-run-prompt-review`, `gen-run-image-review` | The state is `PASS`. The reviewer (`by`) is a model other than `prompt_author`, compared by model family: the name up to the first `-`, `_`, `/`, `.`, `:`, `@` or space, so `claude-sonnet` counts as `claude`. The review file is the evidence: it must exist, the record must equal what is read from it (else `FAIL`), and its binding must name the current prompt, the current requirements (purpose, style and template content hashes and params, recomputed from the record; for the image review also the generation inputs of `workflow.json`) and, for the image review, the recorded outputs. A missing, invalid, unbound or stale review file is missing work, so re-resolving a purpose with a stricter rubric invalidates the old reviews. |
| `gen-run-qa` | `qa.json` is the evidence. It hashed the recorded output bytes, and the record's `qa` equals its state and results (else `FAIL`). Its state is `PASS`, and every output has a `PASS` row for each check its purpose requires (from the run's `spec.json`, whose purpose content hash must equal the recorded one). `NOT_AVAILABLE` never grades `PASS`. A `qa.json` that claims `PASS` with a failing row or a missing required check always fails. Rows for unrecorded outputs fail. A `qa.json` graded with another purpose content hash (`purpose_sha256`) or requested size (`requested_size`, from `workflow.json`) than the run has now is stale and fails. A malformed purpose `qa` block fails (`qa` writes a `purpose-qa` FAIL row instead of grading). |
| `gen-run-outputs` | Outputs are recorded and lie inside the run directory. Every file exists with the recorded SHA-256, and no `outputs/*.png` is unrecorded. |
| `gen-run-provenance` | `provenance` has `generated_by`, `tool: comfyui` and `model`, and equals `spec.generation`. The rendered `workflow.json` is present, and every LoadImage reference it names is kept as `references/<name>` in the run directory. |
| `gen-run-refs` | Purpose, style and template resolve in the core and game layers. A content hash that changed since the run is a `WARN`, because the record keeps what was used. `prompt_sha256` and `prompt.md` match the recorded prompt, and the contract `assetgen-to-<handoff_domain>` is registered. |

These violations always `FAIL`: a hash or prompt mismatch, a path that escapes the run directory, an unmarked same-model review, and an unresolved ref. Missing work also fails once the run is `proposed` or later: a review, QA, an output file or the model. While the run is `draft`, `rejected`, `blocked`, `superseded` or `deprecated`, missing work is a `WARN`.

**Same-model fallback (decision).** Claude writes the prompt and Codex reviews it and the images. When Codex is unavailable, a Claude review is still allowed, but only as an explicit fallback: the verdict file records `"by": "SAME_MODEL:<model>"`, for example `SAME_MODEL:claude`. The `by` field is the one reviewer field that `manifest` copies into the record, so the marker survives every `manifest` run. A marked same-model review grades `WARN`, never `PASS`, so the human approver sees that no independent model reviewed the run. An unmarked same-model review fails. A marker on a review by another model also fails, because that review is not a fallback.

## Skills and commands

The lead skill `asset-gen` runs a generation from routing to handoff: pick a purpose and style, resolve, write the prompt, the Codex prompt review, render, generate through comfy-mcp, QA plus a visual and a Codex image review, `manifest`, then a human approval and the handoff. The tech skill `comfyui` (paths `assetgen/`, used by `asset-gen`, `art-2d`, `art-3d`, `ui-ux` and `vfx`) explains the template format, the layer precedence, the comfy-mcp tool sequence, the image node's pitfalls and how to add a purpose, style or template. `/rpg-factory:assetgen` (`factory-cmd.py assetgen`) runs the read-only engine verbs `list`, `show`, `resolve`, `lint` and `review-cmd`. It refuses `render`, `qa`, `manifest` and `resolve --out`, because they write into a run directory.

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
