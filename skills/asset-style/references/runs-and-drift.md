# Runs under the style lock, rejections, style change and drift

`<A>` is the authoring repo root, `assetgen.py` is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`. The
engine is `scripts/assetgen/stylelock.py` (`choose`, `select_references`, `drift`) and
`scripts/assetgen/consistency.py`; the data is documented in `docs/architecture/domains/assetgen.md` section "Style
lock".

## Runs under the style lock

- `resolve --family F` (else the purpose's `default_family`) picks the family's style from `project.json`. A `--style`
  outside `allowed_styles` and the `families` values, or a `deprecated` style, is refused (`stylelock.py` `choose`).
  Use `--style-override REASON` only when the user asks for it; the reason is shown to the approver in `run.md`.
- Read the `style lock`, `reference` and `rejection` lines `resolve` prints. A selected anchor of another family than
  the run's is a `warning: reference ...` line: name it in the report. `anchor_family_fallback: false` in the purpose or
  `project.json` forbids such anchors. The prompt follows the structured style fields (`text` of each), the
  `forbidden` list and the direction rejections.
- The references are `references/anchor-<id>.png` in the run after `render --run`; upload each with comfy-mcp
  `upload_file` under that name before `run_workflow` (`rpg-factory:comfyui`).
- `qa` adds `style-palette`, `style-tone`, `style-edges` and `style-canvas` rows. Report every `WARN` with its detail;
  a style `FAIL` row fails the QA state like any other QA FAIL.
- Your own visual review and the Codex image review judge the anchor rubric item and each `Not repeated:` item; for an
  output with alpha both look at the same `review/composite-dark.png` and `composite-light.png`.

## Rejections

When a person rejects an output or a direction, record it so later prompts and reviews avoid it:

- an output: `assetgen.py reject --type asset --reason R --run <run> --output N [--text T]`
- a direction: `assetgen.py reject --type direction --reason R --text T --style S --authoring <A> [--family F]`

`R` is one of `style_drift`, `palette_off`, `too_detailed`, `wrong_lighting`, `wrong_perspective`, `text_or_logo`,
`anatomy`, `other` (`other` needs `--text`). `--any-version` makes it apply to every style version. A rejection is
data, not an approval: write one on the person's word, never on your own judgement alone. Repeated direction
rejections are a candidate for the style's `forbidden` list: propose it, the person decides.

## Style change and drift

A style change is a new `version`; never edit an active version in place. Prepare it with `style bump`
(`style-fields.md`), after which a person activates the draft and its anchors. Then
`assetgen.py drift --authoring <A>` (or `/rpg-factory:assetgen drift`, read-only) lists gen-runs, anchors and
rejections recorded on an older version (`older-version`), a changed hash of the same version (`hash-changed`), a
style that no longer resolves (`style-missing`) or a style id that is neither the project style nor a family style
(`style-id-mismatch`, for example exploration anchors after the bootstrap). Report them; regenerate or re-review only
what the user names. Old anchors stay valid for their version but feed no run of the new version, so the new version
needs its own approved anchors (`bootstrap.md` step 6). `style report` shows how the approved runs of a style perform
before and after a change.
