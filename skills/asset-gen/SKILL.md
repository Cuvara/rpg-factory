---
name: asset-gen
description: Use when an image asset is to be generated with AI for the game - a 2D concept or sprite, an icon, a UI element part, a tileable texture, a 3D reference turnaround or an edit of a reference image - from a purpose, a game style and a ComfyUI workflow template, through a reviewed prompt, a comfy-mcp run, image QA and review, to a gen-run record a person approves and hands off. Not for hand-made art direction, specs or exports (art-2d, art-3d, ui-ux, vfx own those), not for Unity import (engineering), and never for approving a run.
argument-hint: "[asset to generate]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*), Bash(codex exec:*), mcp__comfy-mcp__server_info, mcp__comfy-mcp__validate_workflow, mcp__comfy-mcp__upload_file, mcp__comfy-mcp__run_workflow, mcp__comfy-mcp__job, mcp__comfy-mcp__fetch_outputs, mcp__comfy-mcp__nodes
---

# Asset generation (ComfyUI through comfy-mcp)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks. Also invoke `rpg-factory:comfyui` first, in every mode (a `plan` or `analyze` task too, even when nothing will run): the template format, the comfy-mcp sequence and the image node's pitfalls are there, and a plan that skips them is wrong.

Task: $ARGUMENTS

`assetgen.py` below is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py` (its docstring documents every
verb, the data layers and the run directory). `<A>` is the authoring repo root from the snapshot.

## Applies when / Not when

- **Applies:** generating or regenerating an image for the game with ComfyUI, reviewing a generation run, recording
  it as a `gen-run`, or tuning a purpose, style or workflow template in the game layer `assetgen/`.
- **Not when:** art direction, asset specs and exports (`art-2d`, `art-3d`), UI specs (`ui-ux`), effect specs (`vfx`),
  Unity import (engineering), or how ComfyUI, the template format and the image node work (`rpg-factory:comfyui`).

## Scope

Repo `authoring`, module `authoring.assetgen` (`assetgen/`): game layer `{purposes,styles,templates}/`, run directories
`runs/<run-id>/`, style lock (`project.json`, `styles/<style-id>/` anchors and rejections). Core data (`templates/assetgen/`)
changes only through a plugin task. Drives the handoffs `assetgen-to-art2d`, `-art3d`, `-ui` and `-vfx`.

## Workflow delta

1. **Route and pick.** `factory-context.sh --domain assetgen` (lead, gates, the `comfy-mcp` and `codex` tool states).
   Invoke `rpg-factory:comfyui` now: the template format, the comfy-mcp sequence and the image node's pitfalls are
   there. Pick a purpose (`assetgen.py list --authoring <A>`, game layer first; ask when none fits) and the family.
   `<A>/assetgen/project.json` picks the style; without it pick one, or bootstrap a game style first when the user
   wants one ([references/style-lock.md](references/style-lock.md)). Run id `<slug>-NNN`, next free under `runs/`
   (`--run` takes the id, under `<A>/assetgen/runs/` with `--authoring <A>`, or the path).
2. **Resolve.** `assetgen.py resolve --purpose P [--family F] [--style S] [--template T] --authoring <A> --out
   <run>/spec.json`. A style outside `project.json` or a deprecated one is refused: `--style-override REASON` only
   when the user asks. It prints a short summary (style lock, references, rejections, key params, warnings; they feed
   steps 3 and 7; a selected anchor of another family warns, and `anchor_family_fallback: false` in the purpose or
   `project.json` forbids one); `--verbose` or `--json` adds every field's and param's source file (game layer wins).
   A run directory copied under a new id needs `resolve --out` again (`filename_prefix`). The purpose's technical
   `constraints` (`scripts/assetgen/data/precedence.json`) win over the style's hints; `resolve` marks each overridden
   style hint (`spec.hints`) and the prompt uses only the purpose's value.
3. **Prompt.** Write `<run>/prompt.md` (the prompt text only) from the purpose's `prompt.guidance`, `must_include`
   and `avoid` (`assetgen.py show --kind purpose <id> --authoring <A>`: an id like `image-edit` is both a purpose and
   a template, so always pass `--kind`), the style prefix and suffix, `spec.hints` (never an overridden one), the
   style's `forbidden`, the direction rejections and the user's subject. No text, logos or brands unless asked for.
4. **Prompt review (Codex).** `assetgen.py review-cmd --phase prompt --run <run>` prints a read-only `codex exec`
   command (absolute paths); run it as printed -> `<run>/review-prompt.json`. On `FAIL` fix `prompt.md` and review
   again, at most 2 fix rounds; still `FAIL` -> report `BLOCKED`, ask the user. `codex` not OK or failing: review
   it yourself against the same text (`review-cmd --json`, field `stdin`), verdict with its `binding` fields and
   `"by": "SAME_MODEL:claude"` - it grades `WARN`, never `PASS`; say so. A verdict binds the prompt, rendered params
   and images it saw: change any (a `render --param` too) and it is stale until it runs again.
5. **Render.** `assetgen.py render --run <run> [--param name=value]` writes `<run>/workflow.json` (API format, the
   one comfy-mcp runs; strict: an undeclared or missing param is an error) and `<run>/workflow.ui.json` (the same
   graph laid out for the ComfyUI frontend); the prompt node's title shows the prompt review state (`STALE` once
   the prompt, spec or rendered params changed; `rpg-factory:comfyui`). For `image-edit`, copy the original into
   `<run>/references/` (the image review binds its sha256), upload it (step 6), pass `--param reference_image=<name
   it returned>`. `render --run` copies each selected anchor to `<run>/references/anchor-<id>.png` and wires it.
6. **Generate** (spends image credits: only when the task asks for generation). comfy-mcp: `server_info` (ComfyUI
   up, the image node present; when it shows the `comfyui_9router` node pack outdated, name its version in the
   report and tell the user - never update or reinstall it) -> `validate_workflow` on `<run>/workflow.json` ->
   `upload_file` of every `<run>/references/*` file under its name -> `run_workflow` (wait) -> `job` until done ->
   `fetch_outputs` with `out_dir` `<run>/outputs` -> for a purpose with alpha `assetgen.py defringe --run <run>
   [--alpha-floor N]` (bleeds opaque neighbour colour into low-alpha edge pixels, originals in `outputs-raw/`,
   `defringe.json`; 8-bit PNGs only; refused once `qa.json` or an image review binds the outputs, unless `--force`) -> `assetgen.py embed --run <run>` (mandatory, before `qa`: writes the UI workflow into each PNG, replacing
   a stale one, so QA and the reviews hash the final file and the PNG restores the graph in ComfyUI).
   `run_workflow` opens no canvas tab; `assetgen.py publish --run <run> --comfy-url <URL of the running ComfyUI>`
   (optional) uploads `workflow.ui.json` to Workflows > assetgen (exit 0 PASS, 1 FAIL, 2 usage, 3 `NOT_AVAILABLE`:
   not reachable, nothing written; blocks nothing). Tool not OK: render only, generation `NOT_RUN`; a person may run
   `workflow.ui.json` in ComfyUI and drop the PNGs into `outputs/`, then `embed`. Never claim a generation that did not run.
7. **Check the images.** `assetgen.py qa --run <run>` (exit 0 PASS, 1 FAIL, 3 NOT_AVAILABLE) writes `qa.json`; its
   `style-*` rows are soft (`WARN`: report it; a style `FAIL` fails QA); `png-edge-fringe` (alpha purposes) fails a
   coloured fringe in low-alpha edge pixels: `qa.json` binds the outputs now, so `assetgen.py defringe --run <run> --force
   [--alpha-floor N]` (lists the records it made stale), then `embed`, `qa` and both image reviews below again
   (`review-cmd --phase image` and `review-image-claude.json`). `review-cmd --phase image --run <run>`, run as printed -> `review-image.json` (same SAME_MODEL fallback as step 4): its prompt states each output's
   true pixel size and attaches the anchors, for an output with alpha `<run>/review/composite-dark.png` and
   `composite-light.png` (edges judged on both), for a tileable purpose `<run>/review/tile-2x2.png`.
   `/rpg-factory:assetgen review-cmd` appends `--no-write`: it builds no preview and exits 2 when one is missing or
   stale, so run `assetgen.py review-cmd` directly then. Look at every PNG yourself (Read; for alpha the same two
   composites) against the purpose's `image_rubric` (with anchors also the anchor and `Not repeated:` items) and
   write `<run>/review-image-claude.json` (review schema, `"by": "claude"`, binding from `review-cmd --phase image
   --json`); `manifest` summarises it, the quality plugin WARNs when it is missing, and it never replaces the Codex review. Size and the other deterministic checks are QA's: neither review grades them again.
   Any FAIL: fix the prompt or params and regenerate in a new run directory (next free NNN) with a new prompt review,
   at most 2 regenerations, then stop and report; failed attempts stay without `run.md` and `manifest` lists them in
   `spec.trace.failed_attempts`. A FAIL the service causes, not the prompt (`rpg-factory:comfyui` Pitfalls): stop
   regenerating, `manifest` the last attempt with its QA FAIL visible and report.
8. **Record.** `assetgen.py manifest --run <run> [--title T]` writes `run.md` (`gen-run`, status `proposed`). Never
   edit `run.md` by hand: fix the run and run `manifest` again. Run the fast checks (validation delta). A person
   approves (gate below): only on their explicit word, quoted in the report, `assetgen.py approve-record --run <run>
   --by <their name> [--note T]` writes the approval record and status `approved`; the person commits both in one
   SSH-signed commit as that name (until then "approval present but not committed/signed", `HUMAN_REQUIRED`), and
   `manifest` keeps `approved` only while `run.md` stays byte for byte the same. Then hand off to the lead of `spec.handoff_domain` through its contract:
   `rpg-factory:art-2d` (art2d), `rpg-factory:art-3d` (art3d), `rpg-factory:ui-ux` (ui), `rpg-factory:vfx` (vfx),
   with the gen-run ID, output paths and SHA-256. Before approval the images are concept drafts only.
9. **Promote** a tuned purpose, style or template into the game layer (`extends` with only the changed fields) only
   when the user asks, then `lint`. **Style lock** ([references/style-lock.md](references/style-lock.md)):
   `promote-anchor` when a person picks an anchor, `reject` when a person rejects, `drift` after a style change.

## Rules

- The prompt author and the reviewer are different models; Claude writes, Codex reviews (domain doc
  `docs/architecture/domains/assetgen.md` "Same-model fallback (decision)").
- Model ids, sizes and quality are template or purpose params, never prompt text; a ComfyUI node reads its own
  provider settings, so nothing about the provider goes into `<A>/assetgen/`.
- Generated images reach production only through an approved gen-run and its handoff (`docs/architecture/domains/art2d.md`).

## Generated & protected paths

- `<run>/spec.json`, `workflow.json`, `workflow.ui.json`, `references/anchor-*.png`, `outputs-raw/`, `defringe.json`,
  `qa.json`, `review/*.png` (tile and composite previews), `run.md`: `assetgen.py`.
- `<run>/review-prompt.json`, `review-image.json`: the reviewer's (`-o` of the printed command); `review-image-claude.json`: yours.
- `<run>/outputs/*.png`: comfy-mcp `fetch_outputs`, then only `defringe` and `embed`; the SHA-256 after them is the record.
- `approvals/AGEN-<run_id>/`: `approve-record` on a person's explicit word; the person commits and signs it.
- `assetgen/styles/<style-id>/anchors/`: `promote-anchor` writes `proposed`; only a person sets `active`,
  `approved_by`, `approved_on`. `rejections/`: `reject`, on a person's word.

## Validation delta

- Fast: `artifact-lint`, `artifact-trace`, `assetgen-quality`, `assetgen-lint` (`assetgen.py lint --authoring <A>`)
  (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py <A> --registry ${CLAUDE_PLUGIN_ROOT}/registry.json --domain assetgen --json`).
  Read `gen-run-prompt-review`, `-image-review`, `-claude-review`, `-qa`, `-outputs`, `-provenance`, `-style`, `-refs`;
  resolve every `FAIL` (`-claude-review` only WARNs when your visual review is missing or stale).
- comfy-mcp `validate_workflow` is the live node check. `qa.json` state per output; size follows the purpose's size
  mode (`rpg-factory:comfyui`), `png-edge-fringe` grades alpha edges.
- Generation without comfy-mcp: `NOT_RUN`; a `SAME_MODEL` review: `WARN`, named in the report.

## Human gates

- `assetgen-approval`: a person approves the gen-run; stop at `proposed` and ask. Agents never approve on their own:
  `approve-record` only on the person's explicit word (quote it), and only the person commits and signs it.
- Anchors: a person picks and activates them; `project.json` and a new style version only on the user's request.
- Running a generation spends credits on the user's provider; a batch beyond the task's request needs their yes.

## Review checklist

- [ ] Purpose, style and template fit the asset; the game layer was used when it has the id.
- [ ] `prompt.md` follows the purpose guidance and style; reviewed by Codex (or a marked SAME_MODEL fallback).
- [ ] `workflow.json` validated live; outputs fetched, defringed (alpha) and embedded before QA, hashes by `manifest`.
- [ ] Alpha outputs: `png-edge-fringe` PASS, edges judged on the dark and light composites by both reviews.
- [ ] QA PASS for every output; `review-image-claude.json` and the Codex image review agree, or their findings are listed.
- [ ] No overridden style hint in `prompt.md`; failed attempts left without `run.md` and listed in `spec.trace`.
- [ ] Style lock: the project's style (override only on request), anchors uploaded and judged, no anchor activated by an agent.
- [ ] `run.md` is `proposed`, the checks pass, and no handoff happened before a human approval.

## Report additions

Run id and gen-run ID, purpose / style / template with their layer, the prompt, the prompt and image review states
and reviewers (SAME_MODEL named), tool states (comfy-mcp, codex), the outputs (path, size, SHA-256), the QA table,
your visual findings, regeneration count and failed attempt ids, the defringe state, the style ref, family, override,
selected anchors (cross-family named), drift items, the publish state, an outdated `comfyui_9router` pack, the record
status, approval (the person's quoted word, committed and signed or not) and handoff target.

## Tools

- `comfy-mcp`: step 6 (server_info, validate_workflow, upload_file, run_workflow, job, fetch_outputs). Not OK:
  render only, generation `NOT_RUN`, a person runs `workflow.ui.json`.
- `codex`: the prompt and image reviews (steps 4, 7) through `codex exec`. Not OK: the marked `SAME_MODEL:claude` review.
