---
type: llm
weight: 2
---

Routes through `factory-core` to lead `asset-gen` (domain `assetgen`) and loads `comfyui` for the ComfyUI side. Picks purpose `icon` and style `pixel-art` with `assetgen.py list`/`resolve` (game layer first), writes the prompt from the purpose guidance, gets it reviewed by Codex through `assetgen.py review-cmd --phase prompt` (a Claude review only as a marked `SAME_MODEL:` fallback that grades WARN), renders `workflow.json`, and runs it through comfy-mcp (`validate_workflow`, `run_workflow`, `fetch_outputs` into the run's `outputs/`). Checks the images with `assetgen.py qa`, its own visual review and the Codex image review, then writes `run.md` with `assetgen.py manifest` (status `proposed`) and runs the `assetgen-quality` check. Says a person approves (`assetgen-approval`), never an agent, and only then hands off to `art-2d` through `assetgen-to-art2d`. Puts no model id, endpoint or credential in the prompt; without comfy-mcp or ComfyUI the generation is NOT_RUN, never PASS.
