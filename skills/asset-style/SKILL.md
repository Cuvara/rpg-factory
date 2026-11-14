---
name: asset-style
description: How a game project's asset-gen art style is created, versioned and tuned - project.json and game styles over core styles, structured style fields, anchors, rejections, drift and the style QA rows. Use when the work is only about the style - picking or bootstrapping a game style, anchors, rejections, a style version change and its drift, or reading the style-* QA rows of a run. Not for running a generation (asset-gen), not for the ComfyUI side (comfyui), and never for activating an anchor or approving a run - those are human gates.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py:*)
---

# Asset style (game styles, anchors, rejections, drift)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `asset-gen`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths `scripts/`, `templates/`, `docs/` are the plugin root (`${CLAUDE_PLUGIN_ROOT}`); `assetgen/` is the authoring
repo (`<A>` below). `assetgen.py` is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`. The style tooling
(init, derive, bump, report) is being added; until it lands only the verbs and files below exist.

## Applies when / Not when

- **Applies:** choosing or bootstrapping a game style, promoting or reading anchors, recording a rejection, changing a
  style version and reading its drift, or explaining a `style-*` QA row.
- **Not when:** running a generation, review or handoff (`asset-gen` owns the workflow and every gate); the ComfyUI
  template, node or comfy-mcp side (`comfyui`). Never set an anchor `active`, write `approved_by` or approve a run.

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
  section "Style lock").
- **Structured style fields** are data the checks read, each may stay prose (its `text` is the prompt hint):
  `palette.colors`, `tone`, `outline.edge_darkness`, `canvas` per family, `forbidden`. A field that is absent or
  prose-only gives its QA row `NOT_AVAILABLE`.
- **Anchors:** `<A>/assetgen/styles/<style-id>/anchors/<id>.json` plus the PNG (`rpg-factory.assetgen-anchor/1`),
  status `proposed` (written by `promote-anchor`) or `active` (a person sets it with `approved_by` and `approved_on`);
  retired anchors stay on record. Selection is deterministic and only uses active anchors of the run's style id and
  version (`scripts/assetgen/stylelock.py` docstring).
- **Rejections:** `<A>/assetgen/styles/<style-id>/rejections/<id>.json` (`rpg-factory.assetgen-rejection/1`), type
  asset or direction. Data, not an approval: they feed the avoid list and the reviews.
- **Versions:** an active style version is never edited in place; a change is a new `version` (and
  `project.json` `style.version` with it).
- **Drift reasons** (`assetgen.py drift --authoring <A>`, read-only): `older-version`, `hash-changed`,
  `style-missing`, `style-id-mismatch` for gen-runs, anchors and rejections.
- **Style QA rows** (`scripts/assetgen/consistency.py` docstring): `style-palette`, `style-tone`, `style-edges`,
  `style-canvas`; a miss is `WARN`, or `FAIL` when the field sets `severity` `fail`; `NOT_AVAILABLE` without the
  structured field, anchors (tone), the purpose's `qa.outlines` (edges) or a canvas entry for the family.

## Idioms

- **Step by step bootstrap, anchors, rejections, drift:** the style-lock reference of the `asset-gen` skill (the steps move
  into this skill later). Explore with `concept-2d` runs, a person picks, `promote-anchor` writes `proposed`, a person
  approves.
- **Lint the game layer:** `assetgen.py lint --authoring <A>` must show 0 FAIL; a `WARN` that the active game style has
  no usable `palette`, `tone` or `canvas` field means every `style-*` row is `NOT_AVAILABLE`, so ask the person for
  the fields.
- **Report, never decide:** name each `style-*` `WARN` with its detail, each `warning: reference ...` family fallback
  and each drift line; regenerate or re-review only what the user names.

## Pitfalls

- **Anchors of another style id or version feed nothing:** a new game style id has no anchors until runs under it are
  approved and promoted; `drift` shows the old ones as `style-id-mismatch` (`scripts/assetgen/stylelock.py` drift docstring; the
  `asset-gen` style-lock reference, section "New game style (bootstrap)").
- **An agent approval is a failed check:** an anchor `approved_by` `claude`, `codex`, `gpt*` or `SAME_MODEL:*` fails
  `gen-run-style` (`docs/architecture/domains/assetgen.md` section "Style lock").
- **An empty field is not a field:** `canvas: {}` or `tone: {}` counts as absent, so the row stays `NOT_AVAILABLE` (`scripts/assetgen/consistency.py`).

## Testing

- `tests/assetgen.test.sh` covers the style lock engine and the QA rows; `assetgen.py lint --authoring <A>` checks the
  data. A real generation needs ComfyUI and comfy-mcp: without them it is `NOT_RUN`, never PASS.

## Tools

- No registry dev tool: `assetgen.py` (`lint`, `resolve`, `promote-anchor`, `reject`, `drift`, `qa`) as above.
