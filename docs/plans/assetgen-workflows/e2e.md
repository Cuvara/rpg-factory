# asset-gen workflows live e2e

Date: 2026-11-13. Run id: `e2e-icon-001` (purpose `icon`, template `staged-icon`).

Result: NOT_RUN - comfy-mcp could not run any tool (its venv has no comfy-cli, the `comfy` binary every tool wraps),
so no generation ran; the offline steps, publish and the graph screenshot did run and passed.

## Approval and budget

- Authorised: one real low-quality generation (`quality=low`, 1024x1024), no second `run_workflow`, no node or
  ComfyUI update.
- Used: 0 `run_workflow` calls, 0 images. No image credits were spent.
- `assetgen.py budget --run e2e-icon-001`: 0 used of 4 allowed (advisory).

## Setup

- ComfyUI: version 0.45.2 (Comfy Desktop, Python 3.13.12, PyTorch 2.12.1+cpu), read read-only from ComfyUI's own
  system stats because comfy-mcp `server_info` failed. Only the version fields were read; the launch arguments were not.
- Image node: `NineRouterImage` present in the live node list (module `custom_nodes.comfyui_9router`; inputs
  `user_prompt`, `model`, `size`, `quality`, `background`, optional `reference_images`). The pack version and its
  outdated flag come from `server_info` and were not available.
- comfy-mcp: package 0.10.0 in its own venv. comfy-cli: not installed there and not on `PATH`; `COMFY_BIN` is not set
  in the MCP server's environment. comfy-mcp resolves the CLI with `shutil.which(COMFY_BIN)` (default `comfy`),
  so every tool call returned only "Error executing tool".
- Rendered params: `model=cx/gpt-5.6-sol-image`, `size=1024x1024`, `quality=low`, `background=transparent`,
  `filename_prefix=assetgen/e2e-icon-001` (SaveImage suffix `-icon`).
- Style: `stylized-painterly` v1 (core), passed with `--style`: `icon` has no default style and there is no
  `project.json`.
- Authoring: scratch dir `<state dir>/pipeline/assetgen-workflows/live-e2e/authoring` (a fresh git repo). The
  workspace has no `game-authoring` checkout, so there was no `assetgen/project.json` or `styles/` to copy: no style
  lock, no anchors, and `upload_file` had nothing to upload.
- Run dir: `<state dir>/pipeline/assetgen-workflows/live-e2e/authoring/assetgen/runs/e2e-icon-001`.

## Steps

| Step | Command or tool | Result |
| --- | --- | --- |
| 1 | comfy-mcp `server_info` (twice), then `nodes` action `get` `NineRouterImage` | Error executing tool (all three); cause: no comfy-cli. ComfyUI itself answered and has the node (Setup) |
| 2 | `assetgen.py resolve --purpose icon --authoring <A> --out <run>/spec.json` | exit 1: no default style and no `project.json`; with `--style stylized-painterly` exit 0, warning "style is not locked by a project" |
| 3 | `<run>/prompt.md` | an iron sword item icon, diagonal, centered, transparent background, bold shapes readable at 64 px, style prefix and suffix, avoid list |
| 4 | `assetgen.py review-cmd --phase prompt --run <run>`, printed `codex exec` run as printed | exit 0; `review-prompt.json` state PASS, no findings, `by: codex` (bound to the `quality=low` render) |
| 5 | `assetgen.py render --run <run> --param quality=low` | exit 0; 5 API nodes; run again after the review, prompt node title `Prompt (Claude, Codex review PASS)` |
| 6a | `assetgen.py graph-lint templates/assetgen/workflows/staged-icon.json` | exit 0; 1 PASS, 0 WARN, 0 FAIL |
| 6b | `assetgen.py graph-lint --run <run>` | exit 0; 1 PASS, 0 WARN, 0 FAIL |
| 7 | comfy-mcp `validate_workflow` `<run>/workflow.json` | Error executing tool (no comfy-cli): NOT_RUN |
| 8 | comfy-mcp `upload_file` | nothing to upload (no `references/`): not called |
| 9 | `assetgen.py budget --run <run>` | exit 0; 0 used of 4 |
| 10 | comfy-mcp `run_workflow` (`wait=False`), `job`, `fetch_outputs` | NOT_RUN: not called; step 1 and 7 failed |
| 11 | `assetgen.py finalize --run <run>` | NOT_RUN: no outputs to defringe, embed or QA |
| 12 | `assetgen.py publish --run e2e-icon-001 --authoring <A> --comfy-url "$COMFY_URL"` | exit 0 PASS: `workflows/assetgen/e2e-icon-001.json` (Workflows > assetgen) |
| 13 | headless Chrome over the DevTools protocol (the Chrome extension was not connected): open the frontend, load the published file from userdata, fit to view, capture | PNG saved; 10 nodes, 5 groups loaded |

## PreviewImage outputs

Not observed: `fetch_outputs` never ran, so it is still open whether it returns the `PreviewImage` (temp) file of
`Preview at 64 px` along with the `SaveImage` output, and whether `finalize` and `qa` would then see a 64 px PNG in
`outputs/`. The graph has one `SaveImage` (node 2, prefix `assetgen/e2e-icon-001-icon`) and one `PreviewImage`
(node 5, fed by `ImageScale` 64x64), so the next live run must list the returned files per node.

## Gateway proof

None: no gateway call was made (0 `run_workflow`, no prompt id, no image). Credential-free evidence of what would
have run: `workflow.json` sha256 prefix `6721685ef1c2`, `workflow.ui.json` `a84d9f4964f8`, `prompt.md`
`84a39d801ad0`; the live node list has `NineRouterImage` with the inputs the template uses.

## Graph layout

Screenshot: `<state dir>/pipeline/assetgen-workflows/live-e2e/graph-e2e-icon-001.png` (3200x1100, zoom about 104%,
ComfyUI frontend with the published workflow open as tab `e2e-icon-001`).

| Reference item | Verdict |
| --- | --- |
| One group per stage: Prompt, Generate, Post-process, Preview, Output (no References: no anchors) | matches |
| Groups titled and coloured | matches (blue, green, amber, slate, magenta) |
| A Note per group | matches (5 Notes; each titled just "Note", with one line of text) |
| Titled nodes | matches: `Prompt (Claude, Codex review PASS)`, `Generate icon`, `Downscale to 64 px`, `Preview at 64 px`, `Save icon` |
| Left-to-right flow | matches for groups and nodes |
| No overlapping nodes or groups | matches for boxes; differs for one link (finding 3) |

## Findings

1. Step 1/7: comfy-mcp 0.10.0 is installed without comfy-cli. Every tool fails with a bare "Error executing tool",
   which hides the cause. Fix (the user's, not done here): install `comfy-cli>=1.14.0` into the comfy-mcp venv,
   or set `COMFY_BIN` in the MCP server's environment to an existing comfy-cli, then rerun this e2e.
2. Step 2: `resolve --purpose icon` without `project.json` fails on a missing default style. That is by design, but the
   brief's command alone does not run in a fresh authoring dir; the staged templates need a style.
3. Step 13: the link `Generate icon` -> `Save icon` is drawn straight along the same row as the chain
   `Generate icon` -> `Downscale to 64 px` -> `Preview at 64 px` and crosses both nodes' slot row, so the graph
   reads as if `Save icon` were fed by the preview chain. Offsetting the Output node's input row (or the Post-process
   and Preview nodes) in the staged layout would remove the overlap.
4. Step 4: the review binds the rendered params, so the order that keeps it bound is render (`quality=low`), review,
   render again (same params, title shows PASS).

## Limitations

- No generation, so nothing about the gateway, the returned size, PreviewImage outputs, defringe, embed or QA was
  observed; this e2e must run again once comfy-mcp has a comfy-cli (one low-quality generation).
- No style lock or anchors: the References group, anchor wiring and `upload_file` were not exercised.
- The screenshot comes from a headless Chrome with a fresh profile loading the published file through the frontend's
  own graph loader, not from clicking Workflows > assetgen in the Desktop window; the view was fitted by script.
