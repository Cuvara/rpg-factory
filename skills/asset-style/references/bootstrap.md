# Bootstrap a game style: art bible, references, exploration, picks, anchors

Use when the game has no `<A>/assetgen/project.json` yet, or the user asks for a new game style. `<A>` is the
authoring repo root and `assetgen.py` is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`. The engine
and data are documented in `docs/architecture/domains/assetgen.md` section "Bootstrap a game style" and "Style lock".
Every step that a person decides is marked **person**: ask, quote their word in the report, never decide for them.

## 1. Art bible first (person)

Before any image is generated, get a short written art bible from the person (or from the approved `art-direction-2d`
artifact, whose refs go into `project.json` `art_direction`). It answers, one line each:

- **Camera:** projection and angle (top-down, 3/4, side), framing, and the default asset canvas per family.
- **Palette:** the key colours with a role each (primary, shadow, accent, background), as hex values when known.
- **Lighting:** light direction, contrast, shadow style, rim or ambient light.
- **Proportions:** head-to-body ratio, shape language (round, angular), detail level, readable size in game.
- **Material rules:** how metal, cloth, skin, stone, glow are drawn (flat, cel, painted, pixel), line weight, outline.
- **Negative prompts:** what the style never shows (text or logos, photorealism, gradients, a given colour, a
  perspective). These become the style's `forbidden` list and the direction rejections.

Write only what the person confirmed. A missing answer stays a question, not a guess. Each answer maps to a style
field later (`style-fields.md`): palette to `palette.colors`, outline to `outline.edge_darkness`, canvas to `canvas`.

## 2. Reference set (person)

Collect 6-12 reference images from a **rights-clean** set: images the person owns or created, licensed for this use, or
generated and approved in this project. Never a scraped or third-party image without a licence the person confirms,
and never an artist's name used as a style shortcut in a prompt. Record each image's source and licence in the report.
References steer exploration prompts and the art bible; they are not anchors (an anchor is an approved gen-run
output).

## 3. Draft the style (optional, recommended)

When the game style id is known, create the draft first so exploration runs record it and their anchors need no
second promotion: `assetgen.py style init --id ID --extends CORE [--family FAM=STYLE]... --authoring <A>` (see
`scripts/assetgen/style_cmd.py` `init`). It writes a draft `assetgen/styles/<ID>.json` and a `project.json` skeleton, and
never overwrites a file. Choose `CORE` from `templates/assetgen/styles/` with the person.

## 4. Exploration runs

Run the normal workflow of `asset-gen` (its SKILL.md workflow steps) with purpose `concept-2d` for a few subjects, each
with candidate styles (core, or the draft) or prompt variants taken from the art bible. Every run is a normal gen-run:
reviewed, QA'd, `manifest`ed, status `proposed`. Spend only the credits the user agreed to.

## 5. A person picks

Show the outputs with their run ids and ask which images define the style, for which family (`characters`,
`environment`, `props`, `ui`, `vfx`, ...) and which dimensions (`palette`, `lighting`, `shape`, `texture`,
`composition`, `line`), with a strength (`canonical`, `strong`, `supporting`). Never pick for them. Ask too which
outputs and directions are rejected (`runs-and-drift.md` section "Rejections").

## 6. Promote, then a person approves and activates

For each pick: `assetgen.py promote-anchor --run <run> --output N --family F --dimensions a,b --strength S [--id ID]`
(`scripts/assetgen/assetgen.py` `promote_anchor`). It writes the anchor with status `proposed` and copies the PNG next
to it; it refuses an output that does not match `run.md` or `qa.json` (run `qa` and `manifest` again first).

Then the human gates, which an agent never performs: the source gen-runs need the signed approval (`asset-gen` gate
`assetgen-approval`: on the person's explicit word, quoted in the report, `approve-record --run <run> --by <their
name>`, the person commits it), and **a person** edits each anchor to `status: active` with `approved_by` (their name)
and `approved_on`. An anchor approved by `claude`, `codex`, `gpt*` or any name in `scripts/assetgen/stylelock.py`
`AGENT_FAMILIES` fails the quality check `gen-run-style`. Tell the person which anchors await activation; do not edit
them.

## 7. Fields, project, lint

Once active anchors exist, propose the structured fields with `style derive` and report the result (`style-fields.md`).
Setting the confirmed fields, `version: 1` and `status: active` in the game style, and the `project.json` refs, is the
person's decision: do it only on their explicit request. Then `assetgen.py lint --authoring <A>` must show 0 FAIL and no
`WARN` that the active game style lacks a usable `palette`, `tone` or `canvas` field (`canvas: {}` does not count);
otherwise every `style-*` QA row is `NOT_AVAILABLE`, so ask the person for the missing fields.

Anchors feed only runs of their own style id and version. Anchors promoted under another exploration style id feed
nothing of the game style; `drift` lists them as `style-id-mismatch`. Either promote again from approved runs under the
game style id, or explore under the game style id (step 3) next time.
