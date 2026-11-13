# asset-gen test cases

`tests/assetgen.test.sh` renders every core purpose (`templates/assetgen/purposes/*.json`) with the style
`stylized-painterly` and compares the rendered `workflow.json` with a golden file. A new core purpose or template
needs no edit of the test: add its golden file (run `tests/assetgen.test.sh --update-golden` and review the diff)
and, only when its render needs more than the resolved defaults, a cases file here.

## Cases file of a purpose

`cases/<purpose>.json` is optional. Without it the purpose renders with no `--param`.

```json
{
  "render_params": {"reference_image": "ref.png"},
  "variants": {
    "<template-id>": {"render_params": {"NAME": "VALUE"}}
  }
}
```

- `render_params`: each key becomes `render --param KEY=VALUE` for the purpose's default template (for example a
  required param such as `reference_image` of `image-edit`).
- `variants` (optional): each key is a non-default template id from `templates/assetgen/workflows/`. The test
  resolves a second run `golden-<purpose>--<template>-001` with `--template <template>` and renders it with the
  variant's own `render_params`; each variant is one more PASS line.

## Cases file of a variant

`cases/<purpose>--<template>.json` declares one variant in a file of its own (a new template adds its variants
without editing a purpose's cases file). `<purpose>` is a core purpose, `<template>` a core template id.

```json
{"render_params": {"reference_image": "ref.png"}}
```

- `render_params` (optional, `{}` when the render needs no param): the variant's `render --param` values, as in
  `variants.<template>.render_params` above.
- A variant is declared once: either under `variants` of `cases/<purpose>.json` or as its own file, never both (the
  test FAILs a duplicate and a file that names no core purpose or template).

For every variant, from either form, the test compares `golden/<purpose>--<template>.json`, converts the run's
`workflow.ui.json` back to `workflow.json`, and, when the template declares `anchor_target`, the first purpose
(by file name) with a `cases/<purpose>--<template>.json` is rendered in the style lock repo: the purpose's style-lock
anchors must reach the `anchor_target` input after the template's own link, `graph-lint --run` must pass and a repeat
`render --run` must be byte-identical. A core template that declares `anchor_target` needs at least one such file.

## Golden naming

- `golden/<purpose>.json`: the purpose rendered with its default template.
- `golden/<purpose>--<template>.json`: a variant rendered with `--template <template>`.

`--update-golden` writes both kinds.
