# asset-gen workflows live e2e

Date: 2026-11-13. Run id: `e2e-icon-002` (purpose `icon`, template `staged-icon`, style `stylized-painterly`).

Result: FAIL at qa - the one real generation ran, but finalize's QA failed because the gateway returned a 1536x1024
image for a 1024x1024 request and the 64 px PreviewImage fetched by `fetch_outputs` was graded as a second output.

Neither PASS nor NOT_RUN is true: the run ran and its QA failed. Step by step:

- Ran: steps 1-7, 9, 10a-10c, 12 and 13 (Steps table).
- Ran with a FAIL: step 11 (`finalize`, exit 1, "FAIL at qa": `png-size` FAIL on both outputs).
- Exercised only with a fixture: step 8 (`upload_file`, called once after the run with a credential-free
  fixture outside the run dir; the workflow consumes no upload, so the References group and anchor wiring stay
  unexercised).
- Not exercised: image reviews (`review-cmd --phase image`, `review-image-claude.json`), `manifest` (no `run.md`),
  the style rows of QA (NOT_AVAILABLE), anchors and the style lock (Limitations).

## Approval and budget

- Authorised: one real low-quality generation (`quality=low`, 1024x1024); no second `run_workflow`, also not on
  failure; no node or ComfyUI update.
- Used: 1 `run_workflow` call, 1 generated image (plus its 64 px downscale, made locally by `ImageScale`, no
  second gateway call). No `confirm_spend`: `validate_workflow` reported `spends_credits: false` and no partner
  nodes, and the run was not gated.
- `assetgen.py budget --run e2e-icon-002` before the run: 1 used (0 outputs + 1 failed attempt) of 4; after finalize:
  3 used (2 outputs + 1 failed attempt) of 4 (Findings 3).

## Setup

- comfy-mcp `server_info`: ComfyUI running, v0.45.2 (Comfy Desktop install `9router`), comfy-cli 1.26.0, envelope
  schema 1, no compatibility warnings, `freshness.packs` empty (no `comfyui_9router` pack version or outdated flag
  shown). One warning: the default comfy-cli workspace directory does not exist (the Desktop install is used).
- Image node: `NineRouterImage` (pack `comfyui_9router`, `is_api_node: false`) with inputs `user_prompt`, `model`,
  `size` (auto, 1024x1024, 1536x1024, 1024x1536), `quality` (auto, low, medium, high), `background`, optional
  `reference_images`.
- Rendered params: `model=cx/gpt-5.6-sol-image`, `size=1024x1024`, `quality=low` (`render --param`),
  `background=transparent`, `filename_prefix=assetgen/e2e-icon-002` (SaveImage `assetgen/e2e-icon-002-icon`).
- Graph (`workflow.json`, 5 nodes): 3 `PrimitiveStringMultiline` "Prompt (Claude, Codex review PASS)" -> 1
  `NineRouterImage` "Generate icon" -> 2 `SaveImage` "Save icon"; 1 -> 4 `ImageScale` "Downscale to 64 px" -> 5
  `PreviewImage` "Preview at 64 px".
- Style: `stylized-painterly` v1 (core) via `--style`: `icon` has no default style and there is no `project.json`.
- Authoring: scratch dir `<state dir>/pipeline/assetgen-workflows/live-e2e/authoring`. The workspace has no
  `game-authoring` checkout, so no `project.json` or `styles/` to copy: no style lock, no anchors, and the run had
  nothing to upload (`upload_file` was exercised separately with a fixture: Upload probe).
- Run dir: `<state dir>/pipeline/assetgen-workflows/live-e2e/authoring/assetgen/runs/e2e-icon-002`.
- Prompt reviewer: codex-cli 0.167.1 (model gpt-6.1-sol, reasoning medium); log
  `<state dir>/pipeline/assetgen-workflows/live-e2e/codex-prompt-review-002.log`.

## Steps

Placeholders: `<state dir>` is the Factory state dir (`scripts/lib/fstate.py`); `<A>` is the authoring scratch dir
and `<run>` the run dir (Setup); `assetgen.py` is `python3 -B scripts/assetgen/assetgen.py` run from the plugin
checkout; `$COMFY_URL` holds the local ComfyUI base address (the one comfy-mcp `server_info` reports as `url`).
comfy-mcp rows give the tool name and every argument passed; arguments not listed were left at their defaults.

| Step | Command or tool | Result |
| --- | --- | --- |
| 1 | comfy-mcp `server_info` (no arguments); `nodes` `action="get"`, `name="NineRouterImage"` | ComfyUI running v0.45.2, comfy-cli 1.26.0; node present (Setup) |
| 2 | `python3 -B scripts/assetgen/assetgen.py resolve --purpose icon --style stylized-painterly --authoring <A> --out <run>/spec.json` | exit 0; params as in Setup with `quality=high`; warning "no assetgen/project.json: the style is not locked by a project"; references none |
| 3 | `<run>/prompt.md` | one iron sword item icon, diagonal, centered, transparent background, bold shapes readable at 64 px, style prefix, suffix and avoid list, no text |
| 4a | `assetgen.py render --run <run> --param quality=low` | exit 0, 5 nodes, `workflow.json` and `workflow.ui.json` |
| 4b | `assetgen.py review-cmd --phase prompt --run <run>`, then the printed command run as printed (Reviewer command) | exit 0 / exit 0; `review-prompt.json` state PASS, by codex, no findings (bound to the `quality=low` params) |
| 5 | `assetgen.py render --run <run> --param quality=low` (again, after the review) | exit 0; prompt node title "Prompt (Claude, Codex review PASS)" |
| 6 | `assetgen.py graph-lint templates/assetgen/workflows/staged-icon.json`; `assetgen.py graph-lint --run <run>` | exit 0, 1 PASS 0 WARN 0 FAIL; exit 0, 1 PASS 0 WARN 0 FAIL |
| 7 | comfy-mcp `validate_workflow` `workflow_path="<run>/workflow.json"` | `valid: true`, 0 errors, 0 warnings, `partner_nodes` empty, `spends_credits: false` |
| 8 | comfy-mcp `upload_file` `paths=[<state dir>/pipeline/assetgen-workflows/live-e2e/upload-probe/e2e-icon-002-upload-probe.png]`, `overwrite=false` | fixture only, after the run: no error, 1 upload, stored as `e2e-icon-002-upload-probe.png` (type input, subfolder empty); not consumed by the workflow (Upload probe). The run itself had no `<run>/references/` (no anchors, no edit reference) |
| 9 | `assetgen.py budget --run <run>` | exit 0, "1 used (0 outputs + 1 failed attempt) of 4 allowed, 3 remaining" |
| 10a | comfy-mcp `run_workflow` `workflow_path="<run>/workflow.json"`, `wait=false` (`confirm_spend` not set: false) | `queued`, one prompt id (Gateway proof) |
| 10b | comfy-mcp `job` `action="wait"`, `prompt_id="937cc86a-b67c-4a32-ad68-2652a5ef3425"`, `timeout_seconds=300` | `completed`, error none; outputs by node: 2 (output folder), 5 (temp folder) |
| 10c | comfy-mcp `fetch_outputs` `prompt_id="937cc86a-b67c-4a32-ad68-2652a5ef3425"`, `out_dir="<run>/outputs"` | 2 files: `937cc86a_000.png` (1445917 bytes), `937cc86a_001.png` (11172 bytes) |
| 11 | `assetgen.py finalize --run <run>` | exit 1, "FAIL at qa": defringe 2 defringed, embed 2 embedded, qa FAIL (10 PASS, 2 FAIL, 8 NOT_AVAILABLE) |
| 12 | `assetgen.py publish --run <run> --comfy-url "$COMFY_URL"` | exit 0 PASS, `workflows/assetgen/e2e-icon-002.json` (Workflows sidebar > assetgen) |
| 13 | `COMFY_URL="$COMFY_URL" node <state dir>/pipeline/assetgen-workflows/live-e2e/capture-graph.mjs --out <state dir>/pipeline/assetgen-workflows/live-e2e/graph-e2e-icon-002.png` (headless Chrome over the DevTools protocol; the claude-in-chrome extension was not connected) | exit 0; 10 nodes and 5 groups loaded, right-hand panel hidden, `Comfy.Canvas.FitView`; PNG 2600x1100 (Graph layout) |

QA rows per output (`qa.json`):

| Check | `937cc86a_000.png` (SaveImage) | `937cc86a_001.png` (PreviewImage) |
| --- | --- | --- |
| png-valid | PASS 1536x1024 | PASS 64x64 |
| png-size | FAIL: landscape, expected square within 15% | FAIL: short side 64 (min 512), area 4096 (min 262144) |
| png-alpha | PASS, 83.0% transparent | PASS, 73.2% transparent |
| png-corners | PASS | PASS |
| png-not-blank | PASS, stddev 56.36, coverage 17.0% | PASS, stddev 53.88, coverage 26.8% |
| png-edge-fringe | PASS, 0 of 4781 soft edge pixels off-colour | PASS, 0 of 53 |
| style-palette, -tone, -edges, -canvas | NOT_AVAILABLE (no structured style data, no style lock) | NOT_AVAILABLE |

## Reviewer command

`assetgen.py review-cmd --phase prompt --run <run>` printed the reviewer command; it was saved verbatim to
`<state dir>/pipeline/assetgen-workflows/live-e2e/review-cmd-002.sh` (3394 bytes; read for this record: no
credential, URL, host or key in it) and run as printed:

```bash
codex exec --sandbox read-only -C <run> -o <run>/review-prompt.json - <<'ASSETGEN_REVIEW'
<the prompt printed by review-cmd, saved in review-cmd-002.sh>
ASSETGEN_REVIEW
```

In the saved file `<run>` is the absolute run dir. The heredoc carries the rubric, the purpose and style
requirements, the requested params, the prompt under review and the binding fields `prompt_sha256` `d69448cb2009...`
and `requirements_sha256` `68019e87ab12...`; codex read it from stdin (`-`) and wrote its JSON answer to `-o`.

## PreviewImage outputs

Yes: `fetch_outputs` returns the PreviewImage (temp) files as well as the SaveImage output, and both land in
`outputs/`. `job` listed node 2 (`SaveImage`, type output, subfolder `assetgen`, file `e2e-icon-002-icon_00001_.png`)
and node 5 (`PreviewImage`, type temp, file `ComfyUI_temp_..._00001_.png`); `fetch_outputs` downloaded both and
renamed them by prompt id and index: `937cc86a_000.png` (SaveImage, 1536x1024) and `937cc86a_001.png` (PreviewImage,
64x64). The local names no longer say which node or type each came from. finalize treated the preview as a normal
output: defringed it (204 of 204 soft pixels), embedded the workflow into it, and QA graded it and failed its size.

## Upload probe

`upload_file` was not part of the generation (the run has no `<run>/references/`), so it was exercised once on its
own, after the run, with a harmless credential-free fixture outside the run dir. `<run>/references/` was not created.

- Fixture: a copy of the run's 64 px PreviewImage as fetched, `<run>/outputs-raw/937cc86a_001.png`, at
  `<state dir>/pipeline/assetgen-workflows/live-e2e/upload-probe/e2e-icon-002-upload-probe.png` (11172 bytes, sha256
  prefix `db82bd23e0daf9bb`).
- Tool and args: comfy-mcp `upload_file`, `paths` = [that absolute path], `overwrite` = false.
- Returned: no error; `uploads` with 1 entry, stored name (`cloud_name`) `e2e-icon-002-upload-probe.png`, `subfolder`
  empty, `type` input (ComfyUI's input folder, the name a `LoadImage` would take). No explicit state field is
  returned; the call completing with the entry is the success signal.
- Not consumed: no workflow references the file, no generation ran for it (generation count stays 1), and with no
  anchors the References group and the anchor `LoadImage`/`ImageBatch` wiring stay unexercised.

## Gateway proof

- Job prompt id `937cc86a-b67c-4a32-ad68-2652a5ef3425`, status `completed`; ComfyUI history: `execution_start` to
  `execution_success` 40.7 s, no cached nodes.
- Node class that ran: `NineRouterImage` (node 1, `quality=low`, `size=1024x1024`, `background=transparent`).
- Returned image: true size 1536x1024, 8-bit RGBA, 1445917 bytes, sha256 prefix `b90c50317933e62b` as fetched
  (now `outputs-raw/937cc86a_000.png`), `6e45b4584eeb451e` after defringe and embed (`outputs/937cc86a_000.png`).
- The fetched PNGs carried only a `prompt` tEXt chunk (no `workflow` chunk) before `embed`, as the comfyui skill says.
- A visual check (Read) shows the requested subject: one painterly iron sword, hilt lower left to tip upper right,
  leather grip, round pommel, warm and cool rim light, transparent background, no text.

## Graph layout

Screenshot: `<state dir>/pipeline/assetgen-workflows/live-e2e/graph-e2e-icon-002.png` (re-captured with the saved
script below; 2600x1100, 166278 bytes, sha256 prefix `c7ec7e59c3a95f9b`; ComfyUI frontend, tab `e2e-icon-002`, view
fitted to the graph, 74% zoom). It replaces the first capture of this run, which the Workflow Overview panel cut off
at the right edge.

Capture script: `<state dir>/pipeline/assetgen-workflows/live-e2e/capture-graph.mjs` (Node 22+, built-in `fetch` and
`WebSocket`, no npm packages, no credential; sha256 prefix `4de173fced8dd022`). Command:

```bash
COMFY_URL="$COMFY_URL" node "<state dir>/pipeline/assetgen-workflows/live-e2e/capture-graph.mjs" \
  --out "<state dir>/pipeline/assetgen-workflows/live-e2e/graph-e2e-icon-002.png"
# defaults: --workflow workflows/assetgen/e2e-icon-002.json --width 2600 --height 1100 --port 9333
#           --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

The script starts Chrome itself, with a fresh temporary profile that it deletes afterwards:

```bash
chrome.exe --headless=new --remote-debugging-port=9333 --user-data-dir=<new temp dir> --no-first-run \
  --no-default-browser-check --disable-extensions --hide-scrollbars --window-size=2600,1100 about:blank
```

Then, over the DevTools protocol: viewport 2600x1100 at scale 1; navigate to `$COMFY_URL/`; wait for `window.app`;
in the page, `GET api/userdata/workflows%2Fassetgen%2Fe2e-icon-002.json` (read only) and
`app.loadGraphData(<that JSON>, true, true, "e2e-icon-002")` (an unsaved tab; nothing written back); close the left
sidebar tab if one is open and hide the right-hand panel column (the Workflow Overview panel) in the DOM; run the
`Comfy.Canvas.FitView` command; `Page.captureScreenshot` to `--out`. The run printed: 10 nodes and 5 groups in the
file and on the canvas, right-hand panel hidden, `Comfy.Canvas.FitView`. Afterwards the userdata listing of
`workflows/assetgen` still held only `e2e-icon-001.json` and `e2e-icon-002.json`.

Comparison with the reference look (the re-capture confirms the earlier verdicts; only the Capture item changed):

- One group per stage (Prompt, Generate, Post-process, Preview, Output; no References, correctly, without anchors):
  matches.
- Groups titled and coloured (blue, green, amber, slate, purple): matches.
- A Note per group (5 Notes, each with one stage sentence): matches.
- Titled nodes ("Prompt (Claude, Codex review PASS)", "Generate icon", "Downscale to 64 px", "Preview at 64 px",
  "Save icon"): matches.
- Left-to-right flow: matches.
- No overlapping nodes or groups: matches (groups are separated by an even gap).
- Link routing: differs - the Generate -> Save link (link 2 in the published file: node 1 output 0 to node 2) runs
  along the same row through Post-process and Preview and meets the `images` output that this frontend draws on
  "Preview at 64 px", so Save looks fed by the 64 px preview (seen in the earlier attempt too).
- Capture: the whole graph is visible, including the Output group, "Save icon" with `filename_prefix`
  `assetgen/e2e-icon-002-icon` and its Note.

## Findings

1. Step 10c/11: `fetch_outputs` returns PreviewImage temp files, and the staged templates all add a PreviewImage, so
   every staged run gets an extra output that finalize defringes, embeds and QA fails on size. The engine needs to
   keep only the template's `output_node` (SaveImage) files in `outputs/`, e.g. from `job`'s outputs by node.
2. Step 10b/11: the gateway answered a 1024x1024 request with 1536x1024 (known pitfall); `icon` grades orientation, so
   png-size FAILs. A service-caused size FAIL: no regeneration (and only one generation was authorised).
3. Step 9/11: `budget` counts `e2e-icon-001` (same slug, no `run.md`) as a failed attempt of this series and counts
   the preview as an output: 3 of 4 used after one generation.
4. Step 11: the image's subject runs nearly corner to corner of the landscape canvas with the tip close to the top
   right edge; the rubric item "centered with even margin" would likely FAIL in an image review.
5. Step 13: in the headless frontend the workflow store's `openWorkflow` returned without swapping the canvas; the
   first capture fell back to `loadGraphData` of the same published userdata file (an unsaved tab, nothing written:
   the userdata listing still holds only `e2e-icon-001.json` and `e2e-icon-002.json`). The saved capture script
   uses `loadGraphData` directly.

## Limitations

- No style lock and no anchors (no `game-authoring` checkout), so the style rows, the References group and the
  anchor wiring were not exercised; the upload path was exercised with a fixture only (Upload probe), never feeding a
  workflow.
- No image reviews (`review-cmd --phase image`, `review-image-claude.json`) and no `manifest`: outside steps 1-12;
  the run stays without `run.md`.
- The `comfyui_9router` pack version is not shown by `server_info` (`freshness.packs` empty): unverified.
- The earlier attempt `e2e-icon-001` (commit c21c583) was NOT_RUN because the comfy-mcp venv had no comfy-cli; it
  was left untouched and is replaced here by this run's evidence.
