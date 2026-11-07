# Style lock: bootstrap, anchors, rejections, drift

The engine and its data are documented in `docs/architecture/domains/assetgen.md` section "Style lock" and the
`scripts/assetgen/stylelock.py` and `scripts/assetgen/consistency.py` docstrings. `<A>` is the authoring repo root,
`assetgen.py` is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`.

## New game style (bootstrap)

Use when the game has no `<A>/assetgen/project.json` yet, or the user asks for a new game style.

1. **Explore.** Run the normal workflow (SKILL.md steps 1-8) with purpose `concept-2d` for a few subjects, each with
   one or more candidate styles (core or a draft game style) or prompt variants. Every exploration run is a normal
   gen-run: reviewed, QA'd, `manifest`ed, status `proposed`. Spend only the credits the user agreed to.
2. **A person picks.** Show the outputs with their run ids and ask which images define the style and for which family
   (`characters`, `environment`, `props`, `ui`, `vfx`, ...) and dimensions (`palette`, `lighting`, `shape`,
   `texture`, `composition`, `line`). Never pick for them.
3. **Promote.** For each pick: `assetgen.py promote-anchor --run <run> --output N --family F --dimensions a,b
   --strength canonical|strong|supporting [--id ID]`. It writes
   `<A>/assetgen/styles/<style-id>/anchors/<id>.json` with status `proposed` and copies the PNG next to it. It refuses
   an output that does not match `run.md` or `qa.json`: run `qa` and `manifest` again first.
4. **A person approves.** The source gen-runs need the human gate `assetgen-approval` (signed approval), and a person
   edits each anchor to `status: active` with `approved_by` (their name) and `approved_on`. Agents never set either:
   an anchor approved by `claude`, `codex`, `gpt*` or `SAME_MODEL:*` fails the quality check `gen-run-style`.
5. **Write the game style and project.** Only after the approval, and only when the user asks: a game style
   `<A>/assetgen/styles/<id>.json` (`extends` the explored base style) with `version: 1`, `status: active` and the
   structured fields the person confirmed (palette colours, outline, canvas per family, `forbidden`, `tone`), and
   `<A>/assetgen/project.json` (`rpg-factory.assetgen-project/1`: `style` `{id, version}`, `allowed_styles`,
   `families`, `art_direction` refs of the approved art direction). Then `assetgen.py lint --authoring <A>` must
   show 0 FAIL.

The anchors of step 3 were promoted under the exploration style's id and version. Anchors only feed runs of the same
style id and version, so promote again from runs of the new game style when its id differs.

## Runs under the style lock

- `resolve --family F` (else the purpose's `default_family`) picks the family's style from `project.json`. A
  `--style` outside `allowed_styles` and the `families` values, or a `deprecated` style, is refused. Use
  `--style-override REASON` only when the user asks for it; the reason is shown to the approver in `run.md`.
- Read the `style lock`, `reference` and `rejection` lines `resolve` prints. The prompt follows the structured style
  fields (`text` of each), the `forbidden` list and the direction rejections.
- The references are `references/anchor-<id>.png` in the run after `render --run`; upload each with comfy-mcp
  `upload_file` under that name before `run_workflow` (`rpg-factory:comfyui`).
- `qa` adds `style-palette`, `style-tone`, `style-edges` and `style-canvas` rows. Report every `WARN` with its detail;
  a style `FAIL` row fails the QA state and counts like any other QA FAIL.
- Your own visual review and the Codex image review judge the anchor rubric item and each `Not repeated:` item.

## Rejections

When a person rejects an output or a direction, record it so later prompts and reviews avoid it:

- an output: `assetgen.py reject --type asset --reason R --run <run> --output N [--text T]`
- a direction: `assetgen.py reject --type direction --reason R --text T --style S --authoring <A> [--family F]`

`R` is one of `style_drift`, `palette_off`, `too_detailed`, `wrong_lighting`, `wrong_perspective`, `text_or_logo`,
`anatomy`, `other` (`other` needs `--text`). `--any-version` makes it apply to every style version. A rejection is
data, not an approval: an agent may write one on the person's word, never on its own judgement alone.

## Style change and drift

A style change is a new `version` of the style file (and `project.json` `style.version` with it); never edit an
active version in place. Then `assetgen.py drift --authoring <A>` (or `/rpg-factory:assetgen drift`, read-only)
lists the gen-runs, anchors and rejections recorded on an older version (`older-version`), a changed hash of the same
version (`hash-changed`) or a style that no longer resolves (`style-missing`). Report them; regenerate or re-review
only the ones the user names. Old anchors stay valid for their version but feed no run of the new version, so the
new version needs its own approved anchors (bootstrap steps 3-4).
