### Added

- **Asset generation.** The workflow style guide is enforced by `scripts/assetgen/graphstyle.py`. The rules are: every
  node has its own title; every node is in exactly one group; group titles come from Prompt, References, Generate,
  Post-process, Preview, Output and run left to right in that order; each group has a Note; the reviewed prompt is
  linked from a `PrimitiveStringMultiline` directly into `NineRouterImage.user_prompt`, and in a template that node
  holds the `{{prompt}}` placeholder only; there is exactly one `NineRouterImage`; every `SaveImage` sits in Output
  and has an inline filename suffix (`{{filename_prefix}}-icon`), with `PreviewImage` for intermediates; and no
  `LoadImage` names a static file. Each violation starts with its rule id and names the node or group.
- **Asset generation.** New `assetgen.py graph-lint [PATH...] [--run RUN]` checks templates and ComfyUI frontend
  workflows (a run's `workflow.ui.json`). `--run` checks the SaveImage suffix against the run's own prefix, and a
  workflow whose run prefix is unknown fails that rule instead of skipping it. With no path it checks every core and
  game template. It exits 0 when clean, 1 on a violation and 2 on a usage error.
- **Asset generation.** `assetgen.py lint` adds one `assetgen-graph-style` row per template. Legacy templates without
  a ui block, such as the core `image-generate` and `image-edit`, get WARN, never FAIL.
- **Asset generation.** The gen-run quality plugin adds the check `gen-run-workflow-style` for a run whose directory
  holds `workflow.ui.json`. The check gives WARN for style violations and never FAIL in this first phase. Runs without
  the file get no such row.
