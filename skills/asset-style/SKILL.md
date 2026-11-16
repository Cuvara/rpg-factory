---
name: asset-style
description: How a game project's asset-gen art style is bootstrapped, locked, versioned and tuned - art bible, rights-clean reference set, exploration runs, anchors, rejections, game styles over core styles, structured fields, and the style init, derive, bump and report verbs. Use when asset-gen gets a style-only request - bootstrapping or picking a game style, promoting or reading anchors, recording a rejection, a style version bump and its drift, deriving or reporting on style fields, or reading a style-* QA row of a run. Not for running a generation (asset-gen), not for the ComfyUI side (comfyui), and never for activating an anchor or a style version, writing approved_by or approving a run - those are human gates.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py:*)
---

# Asset style (game styles, anchors, rejections, versions, drift)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `asset-gen`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths `scripts/`, `templates/`, `docs/` are the plugin root (`${CLAUDE_PLUGIN_ROOT}`); `assetgen/` is the authoring
repo (`<A>` below). `assetgen.py` is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`.

## Applies when / Not when

- **Applies:** bootstrapping or choosing a game style, promoting or reading anchors, recording a rejection, preparing
  a style version and reading its drift, deriving or reporting on structured fields, explaining a `style-*` QA row.
- **Not when:** running a generation, review or handoff (`asset-gen` owns the workflow and every gate); the ComfyUI
  template, node or comfy-mcp side (`comfyui`).
- **Human gates, never yours:** setting an anchor `active`, writing `approved_by` or `approved_on`, activating a bumped
  style version (replacing the style file, `status: active`, `project.json` `style.version`), and approving a run
  (the person approves; `approve-record` runs only on their explicit word, per `asset-gen`). Prepare, list and
  report; name what awaits the person.

## Scope

Repos `authoring`. Owns no module, contract or check. Reads the plugin's core styles and engine; writes only what the
lead's workflow asks for in the game layer (`<A>/assetgen/`).

## Architecture

- **Core styles are never edited:** `templates/assetgen/styles/<id>.json` (`flat-ui`, `pixel-art`, `anime-cel`, ...)
  carry `schema` `rpg-factory.assetgen-style/1`, `version`, `status` (draft, active, deprecated), prefix, suffix,
  avoid, palette, lighting and params. A game style `<A>/assetgen/styles/<id>.json` with `"extends": "<core id>"`
  deep-merges onto it (layers precedence: `rpg-factory:comfyui` Architecture). The id is the file name.
- **Project config:** `<A>/assetgen/project.json` (`rpg-factory.assetgen-project/1`) holds `style` `{id, version}`,
  `allowed_styles`, `families` (asset family -> game style) and `art_direction` upstream refs. `style.version` must
  equal the style file's `version`, else lint fails and `resolve` refuses (`docs/architecture/domains/assetgen.md`
  section "Project config").
- **Structured style fields** are data the checks read, each may stay prose (its `text` is the prompt hint):
  `palette.colors`, `tone`, `outline.edge_darkness`, `canvas` per family, `forbidden`; shapes and the verbs that fill
  them: `references/style-fields.md`. Absent, prose-only or empty gives its QA row `NOT_AVAILABLE`.
- **Anchors:** `<A>/assetgen/styles/<style-id>/anchors/<id>.json` plus the PNG (`rpg-factory.assetgen-anchor/1`), status
  `proposed` (written by `promote-anchor` or carried by `style bump`) or `active` (a person sets it with `approved_by`
  and `approved_on`); retired anchors stay on record. Selection is deterministic and only uses active anchors of the
  run's style id and version (`scripts/assetgen/stylelock.py` `select_references`).
- **Rejections:** `<A>/assetgen/styles/<style-id>/rejections/<id>.json` (`rpg-factory.assetgen-rejection/1`), type
  asset or direction. Data, not an approval: they feed the avoid list and the reviews.
- **Versions:** an active style version is never edited in place. `style bump` writes the draft
  `<A>/assetgen/styles/<ID>/versions/<N+1>.json` and carries anchors only as `proposed`; a person activates the draft
  and the anchors (`scripts/assetgen/style_cmd.py` `bump`).
- **Drift reasons** (`assetgen.py drift --authoring <A>`, read-only): `older-version`, `hash-changed`,
  `style-missing`, `style-id-mismatch` for gen-runs, anchors and rejections (`scripts/assetgen/stylelock.py` `drift`).
- **Style QA rows** (`scripts/assetgen/consistency.py` docstring): `style-palette`, `style-tone`, `style-edges`,
  `style-canvas`; a miss is `WARN`, or `FAIL` when the field sets `severity` `fail`; `NOT_AVAILABLE` without the
  structured field, anchors (tone), the purpose's `qa.outlines` (edges) or a canvas entry for the family.
- **Pixel art finalizes on the grid:** a `pixel-art` run (or any pixel style) finalizes with `--pixel-grid [--max-colors N]`
  (`scripts/assetgen/pixelgrid.py` docstring, `scripts/assetgen/finalize.py` `pixelgrid_step`): the style's structured
  `palette.colors` wins over `--max-colors`, so a palette change changes the output; the `png-pixel-grid` QA row grades
  it; no grid found is a WARN and the output stays untouched; defringe is skipped for gridded outputs; originals in
  `outputs-raw/pixelgrid/`.

## Workflow

1. **Art bible, references, exploration, picks, anchors:** `references/bootstrap.md`. Order: art bible (camera, palette,
   lighting, proportions, material rules, negative prompts), 6-12 rights-clean reference images, `style init`,
   `concept-2d` exploration runs, a person picks, `promote-anchor` writes `proposed`, a person approves the runs and
   activates the anchors.
2. **Fields:** `style derive` proposes `palette.colors`, `tone.tolerance` and `canvas` from the valid active anchors;
   `--apply` only into a `draft` style. `style derive --family F --apply` replaces `palette.colors` and
   `tone.tolerance` from that family's anchors only, and `canvas` merges per family. Show the numbers first.
   Details of every verb: `references/style-fields.md`.
3. **Change:** `style bump` for a new version, then a person activates; read `drift` after. Runs, rejections and
   drift: `references/runs-and-drift.md`.
4. **Measure:** `style report` is read-only and only suggests thresholds; it never edits a style.

## Idioms

- **Lint the game layer:** `assetgen.py lint --authoring <A>` must show 0 FAIL; a `WARN` that the active game style has
  no usable structured field (`palette.colors`, `tone`, `canvas`, `outline.edge_darkness`) means no `style-*` row can
  grade an output, so ask the person for the fields (`scripts/assetgen/lint.py` `style_warnings`).
- **Read a verb before you run it:** each `style` verb's docstring in `scripts/assetgen/style_cmd.py`,
  `scripts/assetgen/style_derive.py` and `scripts/assetgen/style_report.py` is the reference. `--list-only` and no
  `--apply` first; a refusal exits 1 with nothing written.
- **Report, never decide:** name each `style-*` `WARN` with its detail, each `warning: reference ...` family fallback,
  each drift line and each `bump` row (`carried`, `reapprove`, `rerecord`); regenerate or re-review only what the
  user names.
- **Ask for the art bible, never invent it:** a missing camera, palette or negative-prompt answer is a question for the
  person, not a default.

## Pitfalls

- **Anchors of another style id or version feed nothing:** a new game style id has no anchors until runs under it are
  approved and promoted; `drift` shows the old ones as `style-id-mismatch` (`scripts/assetgen/stylelock.py` `drift`;
  `references/bootstrap.md` step 6).
- **An agent approval is a failed check:** an anchor `approved_by` naming an agent (`scripts/assetgen/stylelock.py`
  `AGENT_FAMILIES`, `SAME_MODEL:*`) fails `gen-run-style` (`docs/architecture/domains/assetgen.md` section "Anchors and
  approval").
- **A carried anchor is not an approved one:** `style bump` writes `proposed` anchors with `approved_by` null; until a
  person activates them the new version has no anchors and the `style-tone` row is `NOT_AVAILABLE`
  (`scripts/assetgen/style_cmd.py` `bump`).
- **`derive --apply` refuses an active style:** `style derive` reads and `--apply` writes only
  `assetgen/styles/<ID>.json`, and only while its status is `draft` (a `style init` draft;
  `scripts/assetgen/style_derive.py` `_run`). `style bump` writes `assetgen/styles/<ID>/versions/<N+1>.json`, which
  derive never touches. For an active style: `style derive` without `--apply` (a read-only proposal from the version-N
  anchors), `style bump`, then the person merges the proposed values into the bump draft by hand before activating it.
- **An empty field is not a field:** `canvas: {}` or `tone: {}` counts as absent, so the row stays `NOT_AVAILABLE`
  (`scripts/assetgen/consistency.py` docstring).
- **Reference images need a licence:** never use an image the person has not confirmed as theirs or licensed
  (`references/bootstrap.md` section "2. Reference set").

## Testing

- `tests/assetgen.test.sh` covers the style lock engine, the style verbs and the QA rows; `assetgen.py lint --authoring
  <A>` checks the data. A real generation needs ComfyUI and comfy-mcp: without them it is `NOT_RUN`, never PASS.

## Tools

- No registry dev tool: `assetgen.py` (`lint`, `resolve`, `promote-anchor`, `reject`, `drift`, `qa`, `style init`,
  `style derive`, `style bump`, `style report`) as above.
