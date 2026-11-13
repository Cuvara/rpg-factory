# Workflow style: staged, grouped graphs

The enforced rules are the `scripts/assetgen/graphstyle.py` docstring (rule ids in brackets below); the ui block
(groups, notes, node colours, row hints) is the `scripts/assetgen/uiworkflow.py` docstring and its `PALETTE`; the
node set is `scripts/assetgen/data/known-nodes.json`. `assetgen.py` is
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`, `<A>` the authoring repo root. Who checks it:
`assetgen.py lint` adds one `assetgen-graph-style` row per template, `assetgen.py graph-lint` checks templates and a
run's `workflow.ui.json` (exit 0 PASS or WARN, 1 FAIL, 2 usage), and the quality check `gen-run-workflow-style`
(`scripts/checks/domains/assetgen.py` `workflow_style_warnings`) reports the same rules on a gen-run as WARN.
The seven `templates/assetgen/workflows/staged-*.json` follow this guide; copy from them.

## Stage blueprint

| Stage | Colour | Holds | Its Note says |
|---|---|---|---|
| Prompt | `pale_blue` | the one `PrimitiveStringMultiline`, `value` `{{prompt}}`, titled `Prompt (Claude, Codex review <state>)` (render fills the state) | the reviewed prompt comes from `prompt.md` via render and is wired straight into the image node |
| References | `cyan` | only when the purpose takes a reference: `LoadImage` `{{reference_image}}`; render adds the style-lock anchor `LoadImage` and `ImageBatch` nodes here itself | which image guides the generation |
| Generate | `green` | exactly one `NineRouterImage` | what the image node generates |
| Post-process | `yellow` | core image nodes that only feed a preview (`ImageScale`, `ImageCrop`, `ImageSharpen`) | what the preview checks, and that it is not the deliverable |
| Preview | `blue` | a `PreviewImage` for every intermediate | what to look at |
| Output | `purple` | `SaveImage` of the deliverable only, `filename_prefix` `{{filename_prefix}}-<suffix>` | what is saved |

- Only the stages a purpose needs, left to right in that order, no stage twice [vocabulary, order]; the sprite
  template has Prompt, Generate and Output only.
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
- No checkpoint loader or sampler: the install has no local models. A node type outside the list fails [unknown];
  adding one is a plugin task that registers it from a saved `object_info` with `scripts/assetgen/nodesync.py`
  (docstring), never an edit in a run.
- Extra nodes add no image quality. Post-process feeds previews only, the deliverable is the image node's output,
  and the alpha defringe runs in `assetgen.py finalize`, not in ComfyUI.

## Limits

- **[prompt]** `NineRouterImage.user_prompt` is linked directly from the `PrimitiveStringMultiline` that holds the
  reviewed prompt; in a template its value is `{{prompt}}` and nothing else. No node rewrites the prompt.
- **[one-image-node]** exactly one `NineRouterImage` per graph (anchors need it too).
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
2. `assetgen.py lint --authoring <A>` and `assetgen.py graph-lint <template file>`: exit 0 before going on.
3. Render a run (`assetgen.py render --run <run>`), then `assetgen.py graph-lint --run <run>` (exit 0) and a live
   `validate_workflow` on `<run>/workflow.json` before any `run_workflow` (SKILL.md Idioms "Authoring rule").
4. A graph-lint FAIL is fixed in the template and rendered again, never patched in the run.

The legacy `image-generate` and `image-edit` templates have no ui block: lint WARNs on them as templates, and
`graph-lint --run` FAILs on their runs (`template_row` / `ui_row` in `graphstyle.py`), so under the rule they are
not run through comfy-mcp. Use a staged template instead.
