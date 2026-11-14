# Workflow style: staged, grouped graphs

The enforced rules are the `scripts/assetgen/graphstyle.py` docstring (rule ids in brackets below); the ui block
(groups, notes, node colours, row hints) is the `scripts/assetgen/uiworkflow.py` docstring and its `PALETTE`; the
node set is `scripts/assetgen/data/known-nodes.json`. `assetgen.py` is
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`, `<A>` the authoring repo root. Who checks it:
`assetgen.py lint` adds one `assetgen-graph-style` row per template, `assetgen.py graph-lint` checks templates and a
run's `workflow.ui.json` (exit 0 PASS or WARN, 1 FAIL, 2 usage), and the quality check `gen-run-workflow-style`
(`scripts/checks/domains/assetgen.py` `workflow_style_warnings`) reports the same rules on a gen-run as WARN.
The seven `templates/assetgen/workflows/staged-*.json` follow this guide; copy from them. So do the four
hybrid and local templates `hybrid-icon-ui`, `hybrid-character`, `hybrid-environment` and `local-variation` (each
has a `requires` block; all UNTESTED on RTX 5060: the user tests them on that 8 GB machine after merge, and no
measured number, passing generation or quality result is claimed for them).

## Stage blueprint

| Stage | Colour | Holds | Its Note says |
|---|---|---|---|
| Prompt | `pale_blue` | the one `PrimitiveStringMultiline`, `value` `{{prompt}}`, titled `Prompt (Claude, Codex review <state>)` (render fills the state) | the reviewed prompt comes from `prompt.md` via render and is wired straight into the image node |
| References | `cyan` | only when the purpose takes a reference: `LoadImage` `{{reference_image}}`; render adds the style-lock anchor `LoadImage` and `ImageBatch` nodes here itself | which image guides the generation |
| Generate | `green` | exactly one `NineRouterImage` (none in `local-variation`, where a local sampler generates) | what the image node generates |
| Models | `brown` | local template only: the loaders (checkpoint, LoRA, ControlNet, IPAdapter, upscale model) that feed the Refine (local) sampler | which models load, and that the user installs them |
| Refine (local) | `blue` | local template only: the sampler chain on the local GPU (`KSampler` and the nodes around it) | what is refined and under which profile |
| Post-process | `yellow` | core image nodes (`ImageScale`, `ImageCrop`, `ImageSharpen`; in a local template also the upscale, the cut-out and `JoinImageWithAlpha`); they feed a preview, or the deliverable when the purpose needs it (rule under Allowed nodes) | what the stage does, and whether its output is a preview or the saved file |
| Preview | `blue` (`red` in the hybrid and local templates, where Refine (local) is `blue`) | a `PreviewImage` for every intermediate | what to look at |
| Output | `purple` | `SaveImage` of the deliverable only, `filename_prefix` `{{filename_prefix}}-<suffix>` | what is saved |

- Only the stages a purpose needs, left to right in that order (`scripts/assetgen/graphstyle.py` `STAGES`: Prompt,
  References, Generate, Models, Refine (local), Post-process, Preview, Output), no stage twice [vocabulary, order]; the
  sprite template has Prompt, Generate and Output only. The Models and Refine (local) colours are `brown` and `blue`
  as in the hybrid templates' ui blocks (`PALETTE` in `scripts/assetgen/uiworkflow.py`).
- Every API node has a title of its own, not its class name [title], and sits in exactly one group [group].
- Every group holds a Note in plain English saying what the stage does [note].
- The layout lives in the template's `ui` block (`groups` `{title, color, nodes}`, `notes` `{text, group}`, node
  colours), never in `workflow`: the ui block never changes the API graph or `workflow.json`.

## Allowed nodes

- API nodes, the ones `known-nodes.json` lists: `NineRouterImage`, `NineRouterChat`, `PrimitiveStringMultiline`,
  `PrimitiveString`, `LoadImage`, `ImageBatch`, `ImageScale`, `ImageSharpen`, `ImageBlur`, `ImageInvert`,
  `ImageCrop`, `ImageQuantize`, `SplitImageWithAlpha`, `JoinImageWithAlpha`, `PreviewImage`, `PreviewAny`,
  `SaveImage`.
- `Note` and `MarkdownNote` are `ui_only`: they exist only as ui notes, and lint rejects them in `workflow`.
- "No checkpoint loader or sampler: the install has no local models" is superseded: profile `api-only` still has no
  local models and its templates use only the API nodes above, while a template with a `requires` block may use the
  local core nodes and pack nodes of `known-nodes.json` (`local_model_nodes`, `packs`), only under a profile that
  meets its `requires.profile`, with the user installing the packs and models (UNTESTED on RTX 5060). A node type
  outside the lists fails [unknown]; adding one is a plugin task that registers it from a saved `object_info` with
  `scripts/assetgen/nodesync.py` (docstring), never an edit in a run.
- A Post-process node may produce the deliverable when the purpose needs it (resize to the tile size, sharpen,
  upscale, cut-out alpha, alpha re-join); it then feeds the Output `SaveImage` directly, and the template says so
  in its Notes. [save-output] only requires every `SaveImage` to sit in the Output group; nothing restricts what
  feeds it. Today: `staged-texture` saves its `ImageScale` (the tile size), `staged-turnaround` its `ImageSharpen`,
  `hybrid-environment` its `ImageScale` (the deliverable width after the 4x upscale), `hybrid-icon-ui` and
  `hybrid-character` the cut-out `InspyrenetRembg`, `local-variation` its `JoinImageWithAlpha`; every other
  Post-process node feeds a `PreviewImage`. The alpha defringe still runs in `assetgen.py finalize`, not in ComfyUI.
- On an API-only graph extra nodes add no image quality: its deliverable is the image node's output unless the
  purpose needs a resize or sharpen as above.

## Limits

- **[prompt]** `NineRouterImage.user_prompt` is linked directly from the `PrimitiveStringMultiline` that holds the
  reviewed prompt; in a template its value is `{{prompt}}` and nothing else. No node rewrites the prompt.
- **[one-image-node]** exactly one `NineRouterImage` per graph (anchors need it too), or none when a local `KSampler` generates the image.
- **Profile rules** (`scripts/assetgen/graphstyle.py` docstring, template form only, under the `--profile` argument of `graph-lint` or else the template's `requires.profile`; static checks of the graph against `scripts/assetgen/data/hardware.json`, nothing is generated or measured, UNTESTED on RTX 5060): **[profile]** a profile below `requires.profile`, **[vram]** `requires.peak_vram_gb` above the profile's VRAM, **[checkpoints]** two different checkpoints without `requires.offload`, **[controlnet]** more than one ControlNet apply on a path, **[batch]** a `batch_size` other than 1, **[tiled-vae]** a `VAEDecode` where a latent may exceed 1024 px (use `VAEDecodeTiled`), **[flux]** a Flux model unquantized under local-8gb or any under local-4gb. `graph-lint --run` does not run them, so a local run needs both `graph-lint <template> --profile <resolved>` and `graph-lint --run <run>`.
- **[save-output] [save-suffix]** `SaveImage` only for deliverables, in the Output group, with an inline suffix after
  the run prefix (`{{filename_prefix}}-icon`); every intermediate is a `PreviewImage`.
- **[load-image]** a template's `LoadImage.image` is exactly one `{{placeholder}}`, never a static file name.
- **No URL, host, IP address or credential-shaped key** anywhere in the file, Note text included (`FORBIDDEN` in
  `scripts/assetgen/lint.py`): the node reads credentials at run time.
- Model ids, sizes and quality are template params, never literals in the graph, a Note or a prompt.

## Changing a template

1. Start from the purpose's template, or the closest `staged-*.json`. For one game: a game-layer file
   `<A>/assetgen/templates/<id>.json` with `"extends": "<core id>"` and only the changed fields. A core template
   changes only through a plugin task. Every `{{placeholder}}` is a declared param, and `output_node` names the
   Output `SaveImage`.
2. `assetgen.py lint --authoring <A>` and `assetgen.py graph-lint <template file>` (a template with a `requires` block:
   also `--profile <the profile the machine meets>`): exit 0 before going on.
3. Render a run (`assetgen.py render --run <run>`), then `assetgen.py graph-lint --run <run>` (exit 0) and a live
   `validate_workflow` on `<run>/workflow.json` before any `run_workflow` (SKILL.md Idioms "Authoring rule").
4. A graph-lint FAIL is fixed in the template and rendered again, never patched in the run.

The legacy `image-generate` and `image-edit` templates have no ui block: lint WARNs on them as templates, and
`graph-lint --run` FAILs on their runs (`template_row` / `ui_row` in `graphstyle.py`), so under the rule they are
not run through comfy-mcp. Use a staged template instead.
