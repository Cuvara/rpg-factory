# asset-gen test cases

`tests/assetgen.test.sh` renders every core purpose (`templates/assetgen/purposes/*.json`) with the style
`stylized-painterly` and compares the rendered `workflow.json` with a golden file. A new core purpose or template
needs no edit of the test: add its golden file (run `tests/assetgen.test.sh --update-golden` and review the diff)
and, only when its render needs more than the resolved defaults, a cases file here.

## Cases file

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

## Golden naming

- `golden/<purpose>.json`: the purpose rendered with its default template.
- `golden/<purpose>--<template>.json`: a variant rendered with `--template <template>`.

`--update-golden` writes both kinds.
