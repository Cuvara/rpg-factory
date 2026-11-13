### Added

- **asset-gen.** New comfyui skill reference `skills/comfyui/references/workflow-style.md` for an agent that creates or
  changes a ComfyUI workflow through comfy-mcp. It gives the stage blueprint (Prompt, References, Generate,
  Post-process, Preview, Output groups with node titles, a Note per group and group colours), the allowed node set and
  the limits: the reviewed prompt is wired directly into the one `NineRouterImage`, `SaveImage` is used only for
  deliverables, and there is no static `LoadImage` and no URL.

### Changed

- **asset-gen.** The comfyui skill's Idioms gain an authoring rule for comfy-mcp: only the rendered graph of the
  purpose's template (core or a game-layer `extends`) runs; it passes `lint`, `graph-lint` and a live
  `validate_workflow` before any `run_workflow`; a graph patched with `set_workflow_slot` or edited by hand runs only
  after a new `render`; and no free-form graph runs (a gallery template or `generate_image`). asset-gen step 6 now runs
  `assetgen.py graph-lint --run <run>` before `validate_workflow` (exit 1: no `run_workflow`), its Rules name the
  authoring rule, and the review checklist requires `workflow.json` to be graph-linted as well as validated live.
