---
name: asset-gen
description: Use when an image asset is to be generated with AI for the game - a 2D concept or sprite, an icon, a UI element part, a tileable texture, a 3D reference turnaround or an edit of a reference image - from a purpose, a game style and a ComfyUI workflow template, through a reviewed prompt, a comfy-mcp run, image QA and review, to a gen-run record a person approves and hands off. Not for hand-made art direction, specs or exports (art-2d, art-3d, ui-ux, vfx own those), not for Unity import (engineering), and never for approving a run.
argument-hint: "[asset to generate]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*), Bash(codex exec:*), mcp__comfy-mcp__server_info, mcp__comfy-mcp__validate_workflow, mcp__comfy-mcp__upload_file, mcp__comfy-mcp__run_workflow, mcp__comfy-mcp__job, mcp__comfy-mcp__fetch_outputs, mcp__comfy-mcp__nodes
---

# Asset generation (ComfyUI through comfy-mcp)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

`assetgen.py` below is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py` (its docstring documents every
verb, the data layers and the run directory). `<A>` is the authoring repo root from the snapshot.

## Applies when / Not when

- **Applies:** generating or regenerating an image for the game with ComfyUI, reviewing a generation run, recording
  it as a `gen-run`, or tuning a purpose, style or workflow template in the game layer `assetgen/`.
- **Not when:** art direction, asset specs and runtime exports (`art-2d`, `art-3d`), UI specs (`ui-ux`), effect specs
  (`vfx`), importing an image into Unity (engineering), or how ComfyUI, the template format and the image node work
  (`rpg-factory:comfyui`, below).

## Scope

Repo `authoring`, module `authoring.assetgen` (`assetgen/`): the game layer `assetgen/{purposes,styles,templates}/`
and run directories `assetgen/runs/<run-id>/`. Core purposes, styles and templates live in the plugin
(`templates/assetgen/`) and change only through a plugin task. Drives the handoffs `assetgen-to-art2d`,
`assetgen-to-art3d`, `assetgen-to-ui` and `assetgen-to-vfx`; the receiving lead owns everything after the handoff.

## Workflow delta

1. **Route and pick.** `factory-context.sh --domain assetgen` (lead, gates, the `comfy-mcp` and `codex` tool states).
   Invoke `rpg-factory:comfyui` now: the template format, the comfy-mcp sequence and the image node's pitfalls are
   there. Pick a purpose and a style with `assetgen.py list --authoring <A>` (game layer first, then core; ask the user
   when the asset fits no purpose). Run id `<slug>-NNN`, next free number under `<A>/assetgen/runs/`.
2. **Resolve.** `assetgen.py resolve --purpose P --style S [--template T] --authoring <A> --out <run>/spec.json`.
   Read the param sources it prints: game-layer values win over core, and a param nobody set comes from the template.
3. **Prompt.** Write `<run>/prompt.md` (the prompt text only) from the purpose's `prompt.guidance`, `must_include`
   and `avoid` (`assetgen.py show <purpose> --authoring <A>`), the style prefix, suffix, palette and lighting, and the
   user's subject. No text, logos or brands unless the purpose asks for them.
4. **Prompt review (Codex).** `assetgen.py review-cmd --phase prompt --run <run>` prints a read-only `codex exec`
   command; run it as printed. It writes `<run>/review-prompt.json`. On `FAIL` fix `prompt.md` from the findings and
   review again, at most 2 fix rounds; still `FAIL` -> stop, report `BLOCKED` with the findings, ask the user.
   When `codex` is not OK or the command fails, review it yourself against the same text (`review-cmd --json`, field
   `stdin`) and write the verdict with its `binding` fields and `"by": "SAME_MODEL:claude"` - it grades `WARN`,
   never `PASS`; say so. A verdict binds the prompt and images it saw (`prompt_sha256`, `outputs`): change either
   and the review is stale until it runs again.
5. **Render.** `assetgen.py render --run <run> [--param name=value]` writes `<run>/workflow.json` (strict: an
   undeclared or missing param is an error). For `image-edit`, copy the original into `<run>/references/` (the image review binds its sha256),
   upload it first (step 6) and pass `--param reference_image=<name it returned>`.
6. **Generate** (spends image credits: only when the task asks for generation). comfy-mcp: `server_info` (ComfyUI
   up, the image node present) -> `validate_workflow` on `<run>/workflow.json` -> `upload_file` for an edit's
   reference -> `run_workflow` (wait) -> `job` until done -> `fetch_outputs` with `out_dir` `<run>/outputs`. Tool
   not OK: render only, generation `NOT_RUN`; a person may run `workflow.json` in ComfyUI and drop the PNGs into
   `outputs/`. Never claim a generation that did not run.
7. **Check the images.** `assetgen.py qa --run <run>` (exit 0 PASS, 1 FAIL, 3 NOT_AVAILABLE) writes `qa.json`.
   Then look at every PNG yourself (Read) against the purpose's `image_rubric` and note each finding. Then the image
   review: `review-cmd --phase image --run <run>`, run as printed -> `review-image.json` (same SAME_MODEL fallback as
   step 4). Any FAIL: fix the prompt or params and regenerate in a new run directory (next NNN) with a new prompt
   review, at most 2 regenerations; then stop and report the failed attempts. A failed attempt gets no `run.md`.
8. **Record.** `assetgen.py manifest --run <run> [--title T]` writes `run.md` (`gen-run`, status `proposed`). Never
   edit `run.md` by hand: fix the run and run `manifest` again. Run the fast checks (validation delta). A person
   approves (gate below); after that, hand off to the lead of `spec.handoff_domain` through its contract:
   `rpg-factory:art-2d` (art2d), `rpg-factory:art-3d` (art3d), `rpg-factory:ui-ux` (ui), `rpg-factory:vfx` (vfx),
   with the gen-run ID, output paths and SHA-256. Before approval the images are concept drafts only.
9. **Promote** a tuned purpose, style or template into the game layer (`<A>/assetgen/{purposes,styles,templates}/`,
   `extends` with only the changed fields) only when the user asks; then `assetgen.py lint --authoring <A>`.

## Rules

- The prompt author and the reviewer are different models; Claude writes, Codex reviews (domain doc
  `docs/architecture/domains/assetgen.md` "Same-model fallback (decision)").
- Model ids, sizes and quality are template or purpose params, never prompt text; a ComfyUI node reads its own
  provider settings, so nothing about the provider goes into `<A>/assetgen/`.
- Generated images reach production only through an approved gen-run and its handoff (`docs/architecture/domains/art2d.md`).

## Generated & protected paths

- `<run>/spec.json`, `workflow.json`, `qa.json`, `run.md`: written by `assetgen.py` (resolve, render, qa, manifest).
- `<run>/review-prompt.json`, `review-image.json`: the reviewer's verdict (the `-o` file of the printed command).
- `<run>/outputs/*.png`: comfy-mcp `fetch_outputs`; never edited, their SHA-256 is the record.
- `approvals/AGEN-<run_id>/`: human only.

## Validation delta

- Fast: `artifact-lint`, `artifact-trace`, `assetgen-quality`
  (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py <A> --registry ${CLAUDE_PLUGIN_ROOT}/registry.json --domain assetgen --json`).
  Read `gen-run-prompt-review`, `-image-review`, `-qa`, `-outputs`, `-provenance`, `-refs`; resolve every `FAIL`.
- `assetgen.py lint --authoring <A>` for game-layer data; comfy-mcp `validate_workflow` is the live node check.
- `qa.json` state per output; the image QA's size check follows the purpose's size mode (`rpg-factory:comfyui`).
- Generation without comfy-mcp: `NOT_RUN`; a `SAME_MODEL` review: `WARN`, named in the report.

## Human gates

- `assetgen-approval`: a person approves the gen-run; stop at `proposed` and ask. Agents never write approvals.
- Running a generation spends credits on the user's provider; a batch beyond the task's request needs their yes.

## Review checklist

- [ ] Purpose, style and template fit the asset; the game layer was used when it has the id.
- [ ] `prompt.md` follows the purpose guidance and style; reviewed by Codex (or a marked SAME_MODEL fallback).
- [ ] `workflow.json` validated live; outputs fetched into the run, hashes recorded by `manifest`.
- [ ] QA PASS for every output; the visual review and the Codex image review agree, or their findings are listed.
- [ ] `run.md` is `proposed`, the checks pass, and no handoff happened before a human approval.

## Report additions

Run id and gen-run ID, purpose / style / template with their layer, the prompt, the prompt and image review states
and reviewers (SAME_MODEL named), tool states (comfy-mcp, codex), the outputs (path, size, SHA-256), the QA table,
your visual findings, regeneration count, the record status, the approval waiting on a person and the handoff target.

## Tools

- `comfy-mcp`: step 6 (server_info, validate_workflow, upload_file, run_workflow, job, fetch_outputs). Not OK:
  render only, generation `NOT_RUN`, a person runs `workflow.json`.
- `codex`: the prompt review (step 4) and the image review (step 7) through `codex exec`. Not OK: the marked
  `SAME_MODEL:claude` review.
