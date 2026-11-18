#!/usr/bin/env bash
# asset-gen engine (scripts/assetgen/): list/show/resolve with core + game layers (override, extends, per-field
# source, param precedence, purpose constraints over style hints), strict render of every core purpose
# (templates/assetgen/purposes/*.json) against golden workflows (tests/fixtures/assetgen/golden/<purpose>.json
# for the default template, <purpose>--<template>.json for a variant; extra render params from the optional
# tests/fixtures/assetgen/cases/<purpose>.json and a variant's cases/<purpose>--<template>.json; every variant's
# workflow.ui.json converts back too; every core template declaring anchor_target gets its style-lock anchors there,
# graph-lint --run PASS and a byte-identical repeat render; a core template with a local requires.profile FAILS
# graph-lint --profile api-only naming the profile),
# the prompt node (PrimitiveStringMultiline, review state in its title), workflow.ui.json (converted back to
# workflow.json by a stdlib UI->API converter), a run filename_prefix (with optional inline output suffix),
# lint errors and warnings (blamed on the game file holding a bad value), offline node registry sync and UI layout,
# the local node registry (UNTESTED on RTX 5060: the 13 core SDXL nodes from the saved object_info, the 4 pack nodes
# from object_info-packs.json, known-nodes packs and local_model_nodes against data/hardware.json) and the template
# requires block (profile, peak_vram_gb, ram_gb, packs, models, offload: accepted complete, refused without a profile,
# with an undeclared or foreign pack, above the profile's VRAM or RAM, with a link, path or credential, a non-bool
# offload, missing next to local nodes, or naming a profile without a GPU (api-only) next to a local or pack node;
# hardware.json missing or malformed, a non-bool requires.gpu included, is one FAIL reason, no traceback),
# the graph style lint (tests/fixtures/assetgen/graphstyle_selftest.py: every rule passing and failing on the template
# and the frontend form, anchor nodes without exemption; graph-lint exits 0/1/2, --profile (an unknown id exits 2, a
# hybrid template under local-8gb PASSES and under api-only FAILS naming the profile, core templates keep their
# result; UNTESTED on RTX 5060: static checks only), assetgen-graph-style lint rows, legacy
# templates WARN; a style-locked render of a grouped template lays its anchors into References; the gen-run
# quality check gen-run-workflow-style: WARN, never FAIL, no row without workflow.ui.json),
# review-cmd output (prints, never runs Codex; absolute paths from any cwd, true pixel sizes,
# the 2x2 tile preview of tileable purposes and --no-write), embed (workflow tEXt chunk in the outputs), publish
# (against an in-process fake ComfyUI: POST, HTTP error, connection refused), PNG QA on fixture PNGs generated here
# (alpha, corners, seam, blank, size modes incl. aspect + min area, orientation, area + min pixels, real 9router sizes, stdlib decoder incl. gray/RGB/palette tRNS, NOT_AVAILABLE), manifest run.md
# (gen-run front matter, review bindings, Claude's visual review, failed attempts in trace), the gen-run quality plugin (pass and fail cases: review files and their
# prompt/output/requirements binding, qa.json as the QA evidence; through artifact-quality and called directly), review
# tiers (scripts/assetgen/data/review-tiers.json: a light purpose needs no Claude visual review but a present file is still
# graded, style-lock anchors force full, no tier recorded in run.md or spec.json; review_tier unit cases and the data file),
# local and hybrid provenance (UNTESTED on RTX 5060: graph binding, prompts, model hashes and sampler records),
# malformed purpose data and link indices (FAIL rows, no traceback), artifact-lint on
# manifest-produced run.md, the style lock data side (stylelock.py: project.json precedence, refusal and override,
# deprecated styles, anchor validity, deterministic reference selection, rejection relevance, drift; their lint rows),
# the style lock through the CLI (resolve --family/--style-override into spec.style_lock, render wiring of 0/1/3 anchors
# and image-edit as LoadImage + ImageBatch into reference_images, anchor copies, hashes bound only with style_lock,
# manifest, promote-anchor, reject, drift), anchor_target (anchors into NineRouterImage or IPAdapterAdvanced; render
# errors for a missing node or input; lint FAILs a template whose anchor_target or primary_node is bad, render keeps
# its messages; primary_node and requested_size; UNTESTED on RTX 5060),
# profile routing (resolve --profile: route, fallback, refusal above the profile, auto; UNTESTED on RTX 5060), style lock QA rows
# through qa (palette PASS/WARN/FAIL/NOT_AVAILABLE, tone vs the run's anchor copies, edges, canvas; older specs
# without rows) and the gen-run plugin's style-* row rule, the
# anchor-aware review-cmd (anchors after outputs in -i, anchor and rejection rubric items, binding style + anchors kept
# by read_verdict, direction rejections in the prompt review's Must avoid, older specs unchanged), review prompts listing
# the params render used (workflow.json) and leaving deterministic checks to QA, --run RUN-ID resolution, the short
# resolve summary and --verbose, the consistency signals self-test (tests/fixtures/assetgen/consistency_selftest.py),
# the e2e3 fixes (png-edge-fringe on a speckled low-alpha fringe, defringe and its record and refusals, dark/light
# composites in the image review, approve-record refusals and record, manifest keeping or resetting an approval, the
# proposed -> approved lifecycle, an uncommitted approval HUMAN_REQUIRED in gen-run-style, cross-family anchor
# warnings and anchor_family_fallback false, drift style-id-mismatch, 1322x1190 square tolerance and allow_swap, the
# embed stale chunk, the style-field lint WARN), the imaging and style engine self-tests (imaging_selftest.py,
# style_selftest.py, pixelgrid_selftest.py, slicer_selftest.py), sheet slicing at gateway sizes, failed cell counts,
# repeat and discard behavior, opt-in finalize, slice and sheet-hint CLI; pixel-grid finalize (grid detection, palette limits, determinism,
# unsupported depths and opt-in QA), the advisory spend guard (resolve --max-outputs into spec.budget, default 4, invalid values exit 2;
# the read-only budget verb: outputs + failed attempts against the limit, ok/at-limit/exceeded/unlimited/invalid and
# their exits; finalize's budget line and --json key with its exit unchanged), the output filter (finalize's first step
# moves the PreviewImage files fetch_outputs downloads into outputs/ to previews/, classified by fetch.json or job state
# under RPG_FACTORY_COMFY_JOBS_DIR, the SaveImage prefix and ComfyUI temp names; unknown files stay; every output a
# preview FAILs at filter; a name collision never overwrites; budget counts deliverables only; gen-run-outputs FAILs a
# recorded previews/ path), finalize size fitting (transparent bands, original preservation, skips and refusals),
# batch discard (QA failures, all-fail and opt-in behavior, manual selection, collisions, refusals, stale reviews,
# reversible moves, manifest trace and quality checks for unrecorded or changed files; single-output compatibility),
# style init (style_cmd.py: a draft game style, a family stub and project.json written into a fresh authoring dir; lint
# 0 FAIL and no WARN for them, the expected WARN once the style is active, resolve locks it; an existing style or
# project.json is never overwritten, exit 1; a non-core --extends or a malformed --family exits 2; templates/assetgen
# unchanged), style derive (style_derive.py: palette colours, tone tolerance and a canvas aspect per family proposed from
# the valid active anchors, byte-identical output for the same anchors, --family restricts, an anchor whose PNG no longer
# matches image_sha256 is skipped; --apply merges only into a draft style (an active style or one without anchors exits 1
# and stays byte-identical), after it lint has 0 FAIL and the style-palette, style-tone and style-canvas rows are ok in
# field_states and available in qa; a canvas entry with only min_side passes lint),
# style bump (style_cmd.py: an active game style gets a draft version N+1 under styles/<id>/versions/ and carried anchors
# written only as proposed copies; nothing active is edited, no anchor is written active; the report names every anchor,
# run and rejection that needs re-approval; no new artifact-quality FAIL on the bumped fixture; a quality rejection or a
# check that cannot run removes the carried anchors and limits the verb to listing; --list-only writes nothing; a draft
# style, a core-only id and a second bump exit 1, a malformed --id exits 2),
# style report (style_report.py: read-only, byte-identical output and an untouched authoring dir; per style and family the
# runs by status, the tone spread and palette share over the approved outputs, the WARN and FAIL rate of each style-* QA
# row, rejections by reason and suggested palette.max_distance and tone.tolerance printed with their data and never
# applied; a group without approved outputs gives null suggestions with a reason; an unreadable output is skipped;
# --style restricts, a malformed --style exits 2, an unknown style exits 1),
# the engine notes (an older fetch.json with hosts is finalized and rewritten host-free; the annotators model kind, pose and
# depth preprocessor models and an unknown one; KSamplerAdvanced provenance and the literal CLIP text check like KSampler;
# lint reading known-nodes.json once; the layout check over every core workflow template, the re-laid templates differing
# only in ui.positions and ui.positions validation; every result row of the anchor_target lint cases; the tiled VAE decode
# of the hybrid anchor fixture),
# and no endpoints or credentials in templates/assetgen or scripts/assetgen.
# Usage: tests/assetgen.test.sh [--update-golden]   (standalone; temp authoring git repo; no network)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
# no case reads the machine's comfy-cli job state: the output filter cases write their own job files here
export RPG_FACTORY_COMFY_JOBS_DIR="$TMP/comfy-jobs"; mkdir -p "$RPG_FACTORY_COMFY_JOBS_DIR"
unset ASSETGEN_NO_PIL
update_golden=false; [ "${1:-}" = "--update-golden" ] && update_golden=true
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | head -20 | sed 's/^/      /'; return 0; }
AG() { python3 -B "$ROOT/scripts/assetgen/assetgen.py" "$@"; }
# bound RUN PHASE STATE BY [FINDINGS-JSON]: a verdict carrying the binding review-cmd hands the reviewer (stdout)
bound() { AG review-cmd --phase "$2" --run "$1" --json | jq -c --arg s "$3" --arg b "$4" --argjson f "${5:-[]}" '.binding + {state: $s, by: $b, findings: $f}'; }
GOLD="$ROOT/tests/fixtures/assetgen/golden"
G=(-c user.email=t@t -c user.name=t -c commit.gpgsign=false)
has_pil() { python3 -c "import PIL" 2>/dev/null; }

# Sheet cases have their own fixtures so each can also run independently via --case.
sh_setup() {
  sh_run="$TMP/$1-001"; mkdir -p "$sh_run/outputs"
  AG resolve --purpose icon --style stylized-painterly --template image-generate --out "$sh_run/spec.json" >/dev/null || return 1
  printf 'A sheet of separate icons.\n' > "$sh_run/prompt.md"
  AG render --run "$sh_run" >/dev/null || return 1
  jq '.purpose.data.qa.size = {"mode":"any", "fit":"none"}' "$sh_run/spec.json" > "$TMP/sh-spec.json" && cp "$TMP/sh-spec.json" "$sh_run/spec.json"
}
sh_fixture() {
  python3 -B - "$ROOT" "$sh_run/outputs/prop.png" "$1" "$2" "$3" <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'assetgen'))
import png
path, w, h, variant = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
data = bytearray(w * h * 4)
for r, (ya, yb) in enumerate(((.05, .29), (.38, .61), (.70, .94))):
    for c, (xa, xb) in enumerate(((.04, .38), (.43, .65), (.72, .96))):
        if variant == 'missing' and (r, c) == (1, 1):
            continue
        x0, x1 = int(w * xa) + r * 3, int(w * xb) - r * 2
        y0, y1 = int(h * ya) + c * 3, int(h * yb) - c * 2
        row = (bytes((50 + r * 40, 60 + c * 40, 120, 255)) * ((x1 - x0) // 2)
               + bytes((200, 190, 160, 255)) * ((x1 - x0 + 1) // 2))
        for y in range(y0, y1):
            data[(y * w + x0) * 4:(y * w + x1) * 4] = row
if variant == 'merged':
    for y in range(int(h * .17), int(h * .17) + 5):
        x0, x1 = int(w * .37), int(w * .45)
        data[(y * w + x0) * 4:(y * w + x1) * 4] = bytes((50, 60, 120, 255)) * (x1 - x0)
open(path, 'wb').write(png.encode(w, h, data))
EOF
}
sh_signature() { (cd "$1" && sha256sum ./*.png | LC_ALL=C sort); }
sh_case() {
  case "$1" in
    sheet-sizes)
      for sh_size in 1322x1190 1672x941 2172x724; do
        sh_setup "sh-size-$sh_size" && sh_fixture "${sh_size%x*}" "${sh_size#*x}" good || { no "sheet setup $sh_size"; continue; }
        cp "$sh_run/outputs/prop.png" "$TMP/sh-input.png"
        AG finalize --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-result.json" 2> "$TMP/sh-err"; sh_rc=$?
        AG manifest --run "$sh_run" > "$TMP/sh-manifest" 2>> "$TMP/sh-err"; sh_manifest_rc=$?
        [ "$sh_rc" -eq 0 ] && [ "$sh_manifest_rc" -eq 0 ] \
          && jq -e '[.steps[].step] == ["filter","slice","fit","defringe","embed","qa"] and any(.steps[]; .step == "slice" and .state == "sliced")' "$TMP/sh-result.json" >/dev/null \
          && [ "$(find "$sh_run/outputs" -name 'prop-r?c?.png' | wc -l)" -eq 9 ] \
          && jq -e '.rows == 3 and .cols == 3 and (.sheets | length) == 1 and (.sheets[0].cells | length) == 9' "$sh_run/sheet.json" >/dev/null \
          && cmp -s "$TMP/sh-input.png" "$sh_run/sheets/prop.png" \
          && grep -q '^- Sheet:' "$sh_run/run.md" \
          && [ "$(sed -n '/^---json$/,/^---$/p' "$sh_run/run.md" | sed '1d;$d' | jq '[.spec.outputs[] | select(.path | test("^outputs/prop-r[1-3]c[1-3]\\.png$"))] | length')" -eq 9 ] \
          && ok "sheet: $sh_size yields nine recorded cells and preserves the sheet" || no "sheet $sh_size rc=$sh_rc manifest=$sh_manifest_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")"
      done ;;
    sheet-failures)
      for sh_variant in merged missing; do
        sh_setup "sh-$sh_variant" && sh_fixture 600 450 "$sh_variant" || { no "sheet $sh_variant setup"; continue; }
        sh_before=$(sh_signature "$sh_run/outputs")
        AG finalize --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-result.json" 2> "$TMP/sh-err"; sh_rc=$?
        [ "$sh_rc" -eq 1 ] && [ "$sh_before" = "$(sh_signature "$sh_run/outputs")" ] && [ ! -e "$sh_run/sheets" ] && [ ! -e "$sh_run/sheet.json" ] \
          && jq -e '.failed_at == "slice" and any(.steps[]; .step == "slice" and .state == "FAIL" and any(.results[]; .state == "FAIL" and (.reason | contains("2 cells found, 3 expected"))))' "$TMP/sh-result.json" >/dev/null \
          && ok "sheet: $sh_variant cells fail atomically with counts" || no "sheet $sh_variant rc=$sh_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")"
      done
      sh_setup sh-write-failure && sh_fixture 600 450 good || { no "sheet write failure setup"; return; }
      python3 -B - "$ROOT" "$sh_run" > "$TMP/sh-fault" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'assetgen'))
import assetgen, finalize
original = assetgen.write_atomic
calls = 0
def fail_write(path, data, suffix):
    global calls
    calls += 1
    if calls == 3:
        raise OSError('injected write failure')
    original(path, data, suffix)
assetgen.write_atomic = fail_write
result = finalize.slice_step(assetgen, sys.argv[2], 3, 3, False)
assert result['state'] == 'FAIL', result
assert os.listdir(os.path.join(sys.argv[2], 'outputs')) == ['prop.png']
assert not os.path.exists(os.path.join(sys.argv[2], 'sheet.json'))
EOF
      sh_rc=$?
      [ "$sh_rc" -eq 0 ] && ok "sheet: write failure removes cells and preserves source" || no "sheet write failure rc=$sh_rc" "$(cat "$TMP/sh-fault")" ;;
    sheet-repeat)
      sh_setup sh-repeat && sh_fixture 600 450 good || { no "sheet repeat setup"; return; }
      AG finalize --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-first.json" 2> "$TMP/sh-err"; sh_first_rc=$?
      AG budget --run "$sh_run" > "$TMP/sh-budget" 2>> "$TMP/sh-err"; sh_budget_rc=$?
      AG budget --run "$sh_run" --json > "$TMP/sh-budget.json" 2>> "$TMP/sh-err"; sh_budget_json_rc=$?
      [ "$sh_budget_rc" -eq 0 ] && [ "$sh_budget_json_rc" -eq 0 ] \
        && grep -q '^budget ok: 1 used ' "$TMP/sh-budget" \
        && jq -e '.used == 1 and .outputs == 1 and .state == "ok" and .sheet_cells == 9' "$TMP/sh-budget.json" >/dev/null \
        && ok "sheet: budget counts nine cells as one generation" || no "sheet budget rc=$sh_budget_rc json=$sh_budget_json_rc" "$(cat "$TMP/sh-budget" "$TMP/sh-budget.json" "$TMP/sh-err")"
      sh_before=$(sh_signature "$sh_run/outputs")
      AG finalize --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-result.json" 2>> "$TMP/sh-err"; sh_rc=$?
      [ "$sh_first_rc" -eq 0 ] && [ "$sh_rc" -eq 0 ] && [ "$sh_before" = "$(sh_signature "$sh_run/outputs")" ] \
        && jq -e 'any(.steps[]; .step == "slice" and .state == "skipped" and (.reason | contains("already sliced")))' "$TMP/sh-result.json" >/dev/null \
        && ok "sheet: repeat finalize skips slicing and preserves cell bytes" || no "sheet repeat rc=$sh_rc first=$sh_first_rc" "$(jq -c '[.results[] | select(.state == "FAIL")]' "$sh_run/qa.json")"
      AG finalize --run "$sh_run" --rows 2 --cols 3 --json > "$TMP/sh-result.json" 2>> "$TMP/sh-err"; sh_rc=$?
      [ "$sh_rc" -eq 1 ] && jq -e '.failed_at == "slice" and any(.steps[]; .step == "slice" and .state == "FAIL")' "$TMP/sh-result.json" >/dev/null \
        && ok "sheet: changed dimensions fail" || no "sheet changed dimensions rc=$sh_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")"
      AG discard --run "$sh_run" --output prop-r1c1.png --reason 'discard one cell' > "$TMP/sh-discard" 2>> "$TMP/sh-err"; sh_discard_rc=$?
      AG finalize --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-result.json" 2>> "$TMP/sh-err"; sh_rc=$?
      [ "$sh_discard_rc" -eq 0 ] && [ "$sh_rc" -eq 0 ] && [ ! -e "$sh_run/outputs/prop-r1c1.png" ] \
        && jq -e 'any(.steps[]; .step == "slice" and .state == "skipped" and (.reason | contains("already sliced")))' "$TMP/sh-result.json" >/dev/null \
        && ok "sheet: repeat after discarding a cell skips slicing" || no "sheet discard repeat rc=$sh_rc discard=$sh_discard_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")" ;;
    sheet-cli)
      sh_setup sh-plain && sh_fixture 600 450 good || { no "sheet plain setup"; return; }
      AG finalize --run "$sh_run" --json > "$TMP/sh-result.json" 2> "$TMP/sh-err"; sh_rc=$?
      [ ! -e "$sh_run/sheet.json" ] && jq -e '[.steps[].step] | index("slice") | not' "$TMP/sh-result.json" >/dev/null \
        && ok "sheet: finalize without dimensions has no slice step" || no "sheet opt-in rc=$sh_rc" "$(cat "$TMP/sh-err")"
      sh_setup sh-slice && sh_fixture 600 450 good || { no "sheet slice setup"; return; }
      AG slice --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-result.json" 2> "$TMP/sh-err"; sh_rc=$?
      [ "$sh_rc" -eq 0 ] && jq -e '.state == "sliced"' "$TMP/sh-result.json" >/dev/null && [ -f "$sh_run/sheet.json" ] \
        && ok "sheet: slice verb succeeds" || no "sheet slice rc=$sh_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")"
      sh_setup sh-slice-bad && sh_fixture 600 450 merged || { no "sheet slice bad setup"; return; }
      AG slice --run "$sh_run" --rows 3 --cols 3 --json > "$TMP/sh-result.json" 2> "$TMP/sh-err"; sh_rc=$?
      [ "$sh_rc" -eq 1 ] && jq -e '.state == "FAIL"' "$TMP/sh-result.json" >/dev/null && [ ! -e "$sh_run/sheet.json" ] \
        && ok "sheet: slice verb rejects merged cells" || no "sheet slice failure rc=$sh_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")"
      sh_before=$(find "$TMP" -type f | LC_ALL=C sort)
      sh_hint=$(AG sheet-hint --rows 3 --cols 3 2>&1); sh_rc=$?
      [ "$sh_rc" -eq 0 ] && [[ "$sh_hint" = *'3 rows and 3 columns'* ]] && [ "$sh_before" = "$(find "$TMP" -type f | LC_ALL=C sort)" ] \
        && ok "sheet: hint prints the grid without writing files" || no "sheet hint rc=$sh_rc" "$sh_hint"
      AG sheet-hint --rows 0 --cols 3 > /dev/null 2>&1; sh_zero=$?
      AG sheet-hint --rows 9 --cols 3 > /dev/null 2>&1; sh_nine=$?
      AG finalize --run "$sh_run" --rows 3 > /dev/null 2>&1; sh_partial=$?
      [ "$sh_zero" -eq 2 ] && [ "$sh_nine" -eq 2 ] && [ "$sh_partial" -eq 2 ] \
        && ok "sheet: invalid dimensions exit 2" || no "sheet invalid arguments: $sh_zero $sh_nine $sh_partial" ;;
    sheet-discard)
      sh_setup sh-discard && sh_fixture 600 450 good || { no "sheet discard setup"; return; }
      AG finalize --run "$sh_run" --rows 3 --cols 3 --discard-qa-fail --json > "$TMP/sh-result.json" 2> "$TMP/sh-err"; sh_rc=$?
      [ "$sh_rc" -eq 0 ] \
        && jq -e '[.steps[].step] == ["filter","slice","fit","defringe","embed","qa","discard"] and any(.steps[]; .step == "slice" and .state == "sliced") and any(.steps[]; .step == "discard" and .state == "skipped") and (.discarded | length) == 0' "$TMP/sh-result.json" >/dev/null \
        && jq -e '.rows == 3 and .cols == 3 and (.sheets[0].cells | length) == 9' "$sh_run/sheet.json" >/dev/null \
        && [ "$(find "$sh_run/outputs" -name 'prop-r?c?.png' | wc -l)" -eq 9 ] \
        && [ ! -e "$sh_run/outputs-rejected" ] \
        && ok "sheet: finalize --discard-qa-fail with --rows and --cols slices the given grid and discards nothing when QA passes" \
        || no "sheet discard flags rc=$sh_rc" "$(cat "$TMP/sh-err" "$TMP/sh-result.json")"
      AG budget --run "$sh_run" --json > "$TMP/sh-budget-before.json" 2>> "$TMP/sh-err"
      # one cell now fails QA (opaque corners): the same flags slice nothing again and discard exactly that cell
      python3 -B - "$ROOT" "$sh_run/outputs/prop-r2c2.png" > "$TMP/sh-fault" 2>&1 <<'EOF2'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'assetgen'))
import png
img = png.decode(sys.argv[2])
open(sys.argv[2], 'wb').write(png.encode(img.width, img.height, bytes((90, 90, 90, 255)) * (img.width * img.height)))
EOF2
      sh_opaque_rc=$?
      AG finalize --run "$sh_run" --rows 3 --cols 3 --discard-qa-fail --json > "$TMP/sh-result.json" 2>> "$TMP/sh-err"; sh_rc=$?
      AG manifest --run "$sh_run" > "$TMP/sh-manifest" 2>> "$TMP/sh-err"; sh_manifest_rc=$?
      [ "$sh_opaque_rc" -eq 0 ] && [ "$sh_rc" -eq 0 ] && [ "$sh_manifest_rc" -eq 0 ] \
        && jq -e 'any(.steps[]; .step == "slice" and .state == "skipped") and any(.steps[]; .step == "discard" and .state == "discarded") and [.discarded[].output] == ["outputs/prop-r2c2.png"]' "$TMP/sh-result.json" >/dev/null \
        && [ ! -e "$sh_run/outputs/prop-r2c2.png" ] && [ -f "$sh_run/outputs-rejected/prop-r2c2.png" ] && [ "$(find "$sh_run/outputs" -name 'prop-r?c?.png' | wc -l)" -eq 8 ] \
        && jq -e '.rows == 3 and .cols == 3' "$sh_run/sheet.json" >/dev/null \
        && jq -e '(.discards | length) == 1 and .discards[0].output == "outputs/prop-r2c2.png"' "$sh_run/discards.json" >/dev/null \
        && ok "sheet: --discard-qa-fail with --rows and --cols discards the QA-FAIL cell and keeps the recorded grid" \
        || no "sheet discard cell rc=$sh_rc opaque=$sh_opaque_rc manifest=$sh_manifest_rc" "$(cat "$TMP/sh-fault" "$TMP/sh-err" "$TMP/sh-result.json")"
      sh_discards=$(jq '.discards | length' "$sh_run/discards.json")
      grep -q "^- Sheet: 3x3, sheets/prop.png (sha256 [0-9a-f]\{12\}) -> 8 outputs, ${sh_discards} discarded (sheet.json, discards.json)\$" "$sh_run/run.md" \
        && ! grep -q 'STALE' <(grep '^- Sheet:' "$sh_run/run.md") \
        && ok "sheet: the manifest Sheet line names the remaining cells and the discarded count of discards.json" \
        || no "sheet manifest line" "$(grep '^- Sheet:' "$sh_run/run.md")"
      AG budget --run "$sh_run" --json > "$TMP/sh-budget-after.json" 2>> "$TMP/sh-err"; sh_json_rc=$?
      AG budget --run "$sh_run" > "$TMP/sh-budget" 2>> "$TMP/sh-err"; sh_text_rc=$?
      [ "$sh_json_rc" -eq 0 ] && [ "$sh_text_rc" -eq 0 ] \
        && jq -e '[.used, .outputs, .discarded, .sheet_cells, .sheet_cells_discarded] == [1,1,0,9,0]' "$TMP/sh-budget-before.json" >/dev/null \
        && jq -e '[.used, .outputs, .discarded, .sheet_cells, .sheet_cells_discarded, .state] == [1,1,0,8,1,"ok"]' "$TMP/sh-budget-after.json" >/dev/null \
        && grep -q '^budget ok: 1 used (1 output + 0 failed attempts) ' "$TMP/sh-budget" \
        && ok "sheet: budget with a sheet counts one generation before and after a cell is discarded (sheet_cells_discarded 1, discarded 0)" \
        || no "sheet budget after discard rc=$sh_json_rc/$sh_text_rc" "$(cat "$TMP/sh-budget-before.json" "$TMP/sh-budget-after.json" "$TMP/sh-budget" "$TMP/sh-err")"
      # every cell discarded: the sheet still counts as one generation, and the text and --json name it
      mkdir -p "$sh_run/outputs-rejected"
      for sh_cell in "$sh_run"/outputs/prop-r?c?.png; do
        sh_name=$(basename "$sh_cell"); sh_sha=$(sha256sum "$sh_cell" | cut -d' ' -f1)
        mv "$sh_cell" "$sh_run/outputs-rejected/$sh_name"
        jq --arg o "outputs/$sh_name" --arg p "outputs-rejected/$sh_name" --arg s "$sh_sha" \
          '.discards += [{output: $o, path: $p, sha256: $s, reason: "test: discard every cell", by: "discard"}]' "$sh_run/discards.json" > "$TMP/sh-discards.json" \
          && cp "$TMP/sh-discards.json" "$sh_run/discards.json" || no "sheet record discard $sh_name"
      done
      AG budget --run "$sh_run" --json > "$TMP/sh-budget-all.json" 2>> "$TMP/sh-err"; sh_json_rc=$?
      AG budget --run "$sh_run" > "$TMP/sh-budget-all" 2>> "$TMP/sh-err"; sh_text_rc=$?
      [ "$sh_json_rc" -eq 0 ] && [ "$sh_text_rc" -eq 0 ] \
        && jq -e '[.used, .outputs, .discarded, .sheet_cells, .sheet_cells_discarded, .state] == [1,1,1,0,9,"ok"]' "$TMP/sh-budget-all.json" >/dev/null \
        && grep -q '^budget ok: 1 used (1 output, 1 discarded + 0 failed attempts) ' "$TMP/sh-budget-all" \
        && ok "sheet: a fully discarded sheet still counts as one generation (text and --json name the discard)" \
        || no "sheet fully discarded budget rc=$sh_json_rc/$sh_text_rc" "$(cat "$TMP/sh-budget-all.json" "$TMP/sh-budget-all" "$TMP/sh-err")" ;;
    *) echo "Unknown case: $1" >&2; return 2 ;;
  esac
}
if [ "${1:-}" = --case ]; then
  [ "$#" -eq 2 ] || { echo 'Usage: assetgen.test.sh --case NAME' >&2; exit 2; }
  sh_case "$2" || exit $?
  echo "assetgen: $pass passed, $fail failed"
  [ "$fail" -eq 0 ]; exit $?
fi

# -- temp authoring repo with a game layer
AUTH="$TMP/game-authoring"; GL="$AUTH/assetgen"
mkdir -p "$GL/purposes" "$GL/styles" "$GL/templates" "$GL/runs"
cat > "$GL/purposes/icon.json" <<'EOF'
{"extends": "icon", "title": "RPG item icon", "params": {"quality": "medium"}, "qa": {"size": {"mode": "exact", "fit": "none"}}}
EOF
cat > "$GL/styles/pixel-art.json" <<'EOF'
{"schema": "rpg-factory.assetgen-style/1", "title": "RPG pixel art", "prefix": "16-bit RPG pixel art,", "params": {"quality": "low"}}
EOF
cat > "$GL/styles/rpg-dark.json" <<'EOF'
{"extends": "stylized-painterly", "title": "RPG dark fantasy", "lighting": "Low moonlight", "avoid": ["bright pastel colors"]}
EOF
cat > "$GL/templates/image-generate.json" <<'EOF'
{"extends": "image-generate", "params": {"model": {"default": "cx/game-image-model"}}}
EOF
git init -q -b main "$AUTH" && git -C "$AUTH" add -A && git -C "$AUTH" "${G[@]}" commit -qm "game layer"

# core ids come from the core data files, so a new purpose, style or template needs no edit here
CORE="$ROOT/templates/assetgen"
core_ids() { local f; for f in "$CORE/$1"/*.json; do [ -f "$f" ] && basename "$f" .json; done | LC_ALL=C sort; }
CORE_PURPOSES=$(core_ids purposes); CORE_STYLES=$(core_ids styles); CORE_TEMPLATES=$(core_ids workflows)
n_p=$(wc -w <<<"$CORE_PURPOSES"); n_s=$(wc -w <<<"$CORE_STYLES"); n_t=$(wc -w <<<"$CORE_TEMPLATES"); n_core=$((n_p + n_s + n_t))

echo "-- list / show"
AG list --json > "$TMP/l.json" 2>"$TMP/err"; rc=$?
n=$(jq '[.entries[] | select(.layer == "core")] | length' "$TMP/l.json")
[ $rc -eq 0 ] && [ "$n" = "$n_core" ] && ok "core list: $n_p purposes + $n_s styles + $n_t templates" || no "core list rc=$rc n=$n (want $n_core)" "$(cat "$TMP/err")"
listed=$(jq -r '.entries[] | select(.layer == "core") | .kind + ":" + .id' "$TMP/l.json")
missing=$(for k in purpose style template; do
  case $k in purpose) ids_=$CORE_PURPOSES ;; style) ids_=$CORE_STYLES ;; template) ids_=$CORE_TEMPLATES ;; esac
  for i in $ids_; do grep -qxF "$k:$i" <<<"$listed" || printf '%s ' "$k:$i"; done
done)
[ $rc -eq 0 ] && [ -n "$CORE_PURPOSES" ] && [ -n "$CORE_STYLES" ] && [ -z "$missing" ] && ok "every core purpose, style and template id is listed" || no "not listed as core: $missing"
AG list --authoring "$AUTH" --json > "$TMP/l.json"
lay() { jq -r --arg k "$1" --arg i "$2" '.entries[] | select(.kind == $k and .id == $i) | .layer' "$TMP/l.json"; }
[ "$(lay purpose icon)/$(lay style pixel-art)/$(lay style rpg-dark)/$(lay template image-generate)/$(lay purpose sprite-2d)" = \
  "game-extends/game-override/game-extends/game-extends/core" ] && ok "game layer: extends, override, game-only extends, core untouched" \
  || no "layers: $(jq -c '[.entries[] | {k: .kind, i: .id, l: .layer}]' "$TMP/l.json")"
AG show icon --authoring "$AUTH" --json > "$TMP/s.json" 2>"$TMP/err"
[ "$(jq -r '.data.title + "|" + .data.qa.alpha + "|" + (.files | length | tostring)' "$TMP/s.json")" = "RPG item icon|required|2" ] \
  && ok "show icon: merged (game title, core qa.alpha), two files" || no "show icon: $(head -c 400 "$TMP/s.json")" "$(cat "$TMP/err")"
AG show image-edit > /dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "ambiguous" "$TMP/err" && ok "show: an id used by two kinds needs --kind" || no "ambiguous show rc=$rc" "$(cat "$TMP/err")"
AG show image-edit --kind template --json | jq -e '.data.workflow["1"].class_type == "LoadImage"' >/dev/null \
  && ok "show --kind template image-edit" || no "show --kind template"

echo "-- resolve: precedence and per-field sources"
AG resolve --purpose icon --style pixel-art --template image-generate --authoring "$AUTH" --json > "$TMP/r.json" 2>"$TMP/err"; rc=$?
r() { jq -r "$1" "$TMP/r.json"; }
[ $rc -eq 0 ] && [ "$(r .schema)" = rpg-factory.assetgen-spec/1 ] && ok "resolve with the game layer" || no "resolve rc=$rc" "$(cat "$TMP/err")"
[ "$(r '.sources["purpose.qa.size.mode"]')" = "game:assetgen/purposes/icon.json" ] \
  && [ "$(r '.sources["purpose.qa.size.expect"]')" = "core:templates/assetgen/purposes/icon.json" ] \
  && [ "$(r '.purpose.data.qa.size | .mode + " " + .expect')" = "exact 1024x1024" ] \
  && ok "extends deep-merges: qa.size.mode from the game, qa.size.expect kept from core" || no "deep merge: $(r '.purpose.data.qa.size') $(r '.sources | with_entries(select(.key | startswith("purpose.qa")))')"
[ "$(r '.sources["purpose.qa.alpha"]')" = "core:templates/assetgen/purposes/icon.json" ] && ok "untouched leaf keeps its core source" || no "qa.alpha source"
[ "$(r '.style.layer')" = game-override ] && [ "$(r '.style.data.avoid')" = null ] && [ "$(r '.sources["style.prefix"]')" = "game:assetgen/styles/pixel-art.json" ] \
  && ok "override (no extends) replaces the core style entirely" || no "override: $(r .style)"
[ "$(r .params.quality)" = medium ] && [ "$(r .param_sources.quality)" = "game:assetgen/purposes/icon.json" ] \
  && ok "param precedence: purpose (game) quality beats style quality" || no "quality: $(r .params.quality) [$(r .param_sources.quality)]"
[ "$(r .params.model)" = cx/game-image-model ] && [ "$(r .param_sources.model)" = "game:assetgen/templates/image-generate.json" ] \
  && ok "template default from the game template extension" || no "model: $(r .params.model) [$(r .param_sources.model)]"
[ "$(r .params.background)" = transparent ] && [ "$(r .param_sources.background)" = "core:templates/assetgen/purposes/icon.json" ] \
  && ok "purpose params beat template defaults" || no "background: $(r .params.background)"
[ "$(r '.purpose.sha256')" != "$(AG resolve --purpose icon --style pixel-art --json | jq -r .purpose.sha256)" ] \
  && ok "content hash changes with the game layer" || no "purpose sha256 same with and without game layer"
AG resolve --purpose texture-tileable --style flat-ui --json > "$TMP/r.json"
[ "$(r .params.background)/$(r .param_sources.background)" = "opaque/core:templates/assetgen/purposes/texture-tileable.json" ] \
  && ok "purpose background (opaque) beats style background (flat-ui transparent)" || no "flat-ui texture: $(r .params.background)"
AG resolve --purpose icon --style rpg-dark --authoring "$AUTH" --json > "$TMP/r.json"
[ "$(r .style.data.lighting)" = "Low moonlight" ] && [ "$(r .style.data.prefix)" = "$(jq -r .prefix "$ROOT/templates/assetgen/styles/stylized-painterly.json")" ] \
  && [ "$(r .style.data.avoid[0])" = "bright pastel colors" ] && ok "game-only style extends another core id (lists replaced)" || no "rpg-dark: $(r .style.data)"
AG resolve --purpose icon --style pixel-art --out "$TMP/spec-out.json" > /dev/null && [ -f "$TMP/spec-out.json" ] \
  && ok "resolve --out writes the spec" || no "resolve --out"
AG resolve --purpose nope --style pixel-art >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "purpose 'nope' not found" "$TMP/err" && ok "unknown purpose: error" || no "unknown purpose rc=$rc" "$(cat "$TMP/err")"
AG resolve --purpose icon >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "pass --style" "$TMP/err" && ok "no style and no default_style: error" || no "missing style rc=$rc"
BAD="$TMP/bad-authoring"; mkdir -p "$BAD/assetgen/styles" "$BAD/assetgen/purposes"
echo '{"extends": "loop-b", "title": "a"}' > "$BAD/assetgen/styles/loop-a.json"
echo '{"extends": "loop-a", "title": "b"}' > "$BAD/assetgen/styles/loop-b.json"
AG resolve --purpose icon --style loop-a --authoring "$BAD" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "extends cycle" "$TMP/err" && ok "extends cycle detected" || no "cycle rc=$rc" "$(cat "$TMP/err")"
echo '{"extends": "icon", "params": {"tint": "red"}}' > "$BAD/assetgen/purposes/icon.json"
AG resolve --purpose icon --style pixel-art --template image-generate --authoring "$BAD" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "param 'tint' that template 'image-generate' does not declare" "$TMP/err" && ok "purpose param not declared by the template: error" || no "undeclared purpose param rc=$rc" "$(cat "$TMP/err")"

echo "-- resolve: purpose constraints beat style hints (data/precedence.json)"
AG resolve --purpose ref-3d-turnaround --style stylized-painterly --json > "$TMP/r.json"
[ "$(r .hints.lighting.from)" = purpose ] && [ "$(r .hints.lighting.text)" = "$(jq -r .constraints.lighting "$ROOT/templates/assetgen/purposes/ref-3d-turnaround.json")" ] \
  && [ "$(r .hints.lighting.overrides.text)" = "$(jq -r .lighting "$ROOT/templates/assetgen/styles/stylized-painterly.json")" ] \
  && [ "$(r .hints.lighting.overrides.source)" = "core:templates/assetgen/styles/stylized-painterly.json" ] \
  && ok "turnaround + painterly: purpose lighting wins, the style's key + rim light is marked overridden" || no "hints: $(r .hints)"
[ "$(r .hints.palette.from)/$(r '.hints.palette | has("overrides")')" = "style/false" ] && [ "$(r .hints.background.from)" = purpose ] \
  && ok "palette stays a style hint; background comes from the purpose constraint" || no "palette/background hints: $(r .hints)"
[ "$(r .style.data.lighting)" = "$(jq -r .lighting "$ROOT/templates/assetgen/styles/stylized-painterly.json")" ] \
  && ok "the style data itself is unchanged (the content hash binding keeps what was resolved)" || no "style data changed"
AG resolve --purpose texture-tileable --style low-poly --json | jq -e '.hints.lighting.from == "purpose" and (.hints.lighting.overrides.text | test("directional"))' >/dev/null \
  && ok "texture + low-poly: even lighting beats the single directional light" || no "texture/low-poly hints"
AG resolve --purpose icon --style stylized-painterly --json | jq -e '.hints.lighting.from == "style" and (.hints.lighting | has("overrides") | not)' >/dev/null \
  && ok "a purpose without a lighting constraint keeps the style's lighting hint" || no "icon/painterly hints"
out=$(AG resolve --purpose ref-3d-turnaround --style low-poly --verbose)
grep -q "^hint lighting = Flat, even lighting.*style hint overridden by the purpose\]$" <<<"$out" && ! grep -q "Single soft directional light" <<<"$out" \
  && ok "resolve text: one lighting hint (the purpose's), marked as overriding the style; the style text is not shown" || no "resolve text hints" "$(grep hint <<<"$out")"
HA="$TMP/hint-authoring"; mkdir -p "$HA/assetgen/purposes"
echo '{"extends": "ref-3d-turnaround", "constraints": {"lighting": "Overcast even daylight."}}' > "$HA/assetgen/purposes/ref-3d-turnaround.json"
AG resolve --purpose ref-3d-turnaround --style stylized-painterly --authoring "$HA" --json > "$TMP/r.json"
[ "$(r .hints.lighting.text)|$(r .hints.lighting.source)|$(r .hints.background.source)" = "Overcast even daylight.|game:assetgen/purposes/ref-3d-turnaround.json|core:templates/assetgen/purposes/ref-3d-turnaround.json" ] \
  && ok "a game purpose extension overrides one constraint; each hint names its source file" || no "game constraint: $(r .hints)"
echo '{"extends": "icon", "constraints": {"palette": "Only greens."}}' > "$HA/assetgen/purposes/icon.json"
echo '{"extends": "sprite-2d", "constraints": {"lighting": ["flat"]}}' > "$HA/assetgen/purposes/sprite-2d.json"
got=$(AG lint "$HA/assetgen/purposes/icon.json" --authoring "$HA" 2>&1)
grep -q "^FAIL game:assetgen/purposes/icon.json: constraints.palette: not a technical constraint a purpose may set" <<<"$got" \
  && ok "lint: a purpose may not constrain a style-only hint (palette)" || no "palette constraint lint" "$got"
got=$(AG lint "$HA/assetgen/purposes/sprite-2d.json" --authoring "$HA" 2>&1)
grep -q "constraints.lighting must be a non-empty string" <<<"$got" && ok "lint: a constraint must be a non-empty string" || no "constraint type lint" "$got"

echo "-- render: every purpose against its golden workflow"
RUNS="$GL/runs"
mkrun() { # mkrun NAME PURPOSE [resolve args...]
  local d="$RUNS/$1" p="$2"; shift 2; mkdir -p "$d/outputs"
  AG resolve --purpose "$p" "$@" --out "$d/spec.json" > /dev/null || return 1
  printf 'Test prompt for %s: one subject, centered.\n' "$p" > "$d/prompt.md"
}
mkdir -p "$GOLD"
# cases files (optional): tests/fixtures/assetgen/cases/<purpose>.json and cases/<purpose>--<template>.json, see its README.md
CASES="$ROOT/tests/fixtures/assetgen/cases"
# case_params PURPOSE [TEMPLATE]: two lines, --param and NAME=VALUE, per render param of the purpose (or of its variant
# TEMPLATE: the top-level render_params of cases/<purpose>--<template>.json, else variants.<template> of cases/<purpose>.json)
case_params() {
  local f="$CASES/$1.json" v="$CASES/$1--${2:-}.json"
  if [ -n "${2:-}" ] && [ -f "$v" ]; then
    jq -r '(.render_params // {}) | to_entries[] | "--param", (.key + "=" + (.value | tostring))' "$v"; return 0
  fi
  [ -f "$f" ] || return 0
  jq -r --arg t "${2:-}" '(if $t == "" then .render_params else .variants[$t].render_params end) // {}
    | to_entries[] | "--param", (.key + "=" + (.value | tostring))' "$f"
}
# case_variants PURPOSE: the variant template ids of the purpose, from variants in cases/<purpose>.json and from the
# cases/<purpose>--<template>.json files, sorted, each once
case_variants() {
  local f="$CASES/$1.json" v
  { [ -f "$f" ] && jq -r '(.variants // {}) | keys[]' "$f"
    for v in "$CASES/$1--"*.json; do [ -f "$v" ] && { v=$(basename "$v" .json); echo "${v#"$1--"}"; }; done
  } | LC_ALL=C sort -u; return 0
}
# a variant is declared once: either in cases/<purpose>.json variants or as cases/<purpose>--<template>.json
for p in $CORE_PURPOSES; do
  for t in $(case_variants "$p"); do
    if [ -f "$CASES/$p--$t.json" ] && [ -f "$CASES/$p.json" ] && jq -e --arg t "$t" '(.variants // {}) | has($t)' "$CASES/$p.json" >/dev/null; then
      no "cases: variant $p--$t is declared twice (cases/$p.json variants and cases/$p--$t.json)"
    fi
  done
done
for v in "$CASES"/*--*.json; do
  [ -f "$v" ] || continue; b=$(basename "$v" .json)
  [ -f "$CORE/purposes/${b%%--*}.json" ] && [ -f "$CORE/workflows/${b#*--}.json" ] \
    || no "cases: $b.json names no core purpose and core template (cases/<purpose>--<template>.json)"
done
# golden_render RUN-NAME PURPOSE GOLDEN-NAME [TEMPLATE]: render the run and compare it with golden/<GOLDEN-NAME>.json
golden_render() {
  local run="$1" p="$2" g="$3" t="${4:-}" out rc wf args=() targs=()
  [ -n "$t" ] && targs=(--template "$t")
  mkrun "$run" "$p" --style stylized-painterly "${targs[@]}" || { no "resolve $g"; return 0; }
  mapfile -t args < <(case_params "$p" "$t")
  out=$(AG render --run "$RUNS/$run" "${args[@]}" 2>&1); rc=$?
  wf="$RUNS/$run/workflow.json"
  if $update_golden && [ $rc -eq 0 ]; then cp "$wf" "$GOLD/$g.json"; fi
  if [ $rc -eq 0 ] && [ -f "$GOLD/$g.json" ] && [ "$(jq -S . "$wf")" = "$(jq -S . "$GOLD/$g.json")" ] && ! grep -q '{{' "$wf"; then
    ok "render $g = golden (no placeholder left)"
  else no "render $g rc=$rc" "$out
$(diff <(jq -S . "$wf" 2>/dev/null) <(jq -S . "$GOLD/$g.json" 2>/dev/null))"; fi
}
for p in $CORE_PURPOSES; do
  golden_render "golden-$p-001" "$p" "$p"
  for t in $(case_variants "$p"); do golden_render "golden-$p--$t-001" "$p" "$p--$t" "$t"; done
done
# Dedicated legacy renders keep node-shape checks independent of purpose defaults.
mkrun legacy-shape-icon-001 icon --style stylized-painterly --template image-generate
AG render --run "$RUNS/legacy-shape-icon-001" >/dev/null
mkrun legacy-shape-edit-001 image-edit --style stylized-painterly --template image-edit
AG render --run "$RUNS/legacy-shape-edit-001" --param reference_image=ref.png >/dev/null
AG graph-lint --run "$RUNS/golden-icon-001" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q '^PASS ' "$TMP/o" \
  && [ "$(jq -r '[.[] | select(.class_type == "SaveImage")][0].inputs.filename_prefix' "$RUNS/golden-icon-001/workflow.json")" = assetgen/golden-icon-001-icon ] \
  && ok "staged icon: graph-lint --run PASS and SaveImage has inline icon suffix" || no "staged icon graph-lint rc=$rc" "$(cat "$TMP/o")"
AG review-cmd --phase prompt --run "$RUNS/golden-ref-3d-turnaround-001" --json | jq -r .stdin > "$TMP/rp.txt"
grep -qF "lighting: $(jq -r .constraints.lighting "$ROOT/templates/assetgen/purposes/ref-3d-turnaround.json")" "$TMP/rp.txt" \
  && ! grep -qF "$(jq -r .lighting "$ROOT/templates/assetgen/styles/stylized-painterly.json")" "$TMP/rp.txt" \
  && ok "prompt review: the reviewer judges against the purpose lighting, not the overridden style lighting" || no "review hints" "$(grep -n Hints "$TMP/rp.txt")"
w="$RUNS/legacy-shape-icon-001/workflow.json"
[ "$(jq -r '.["3"].inputs.value' "$w")" = "Test prompt for icon: one subject, centered." ] && [ "$(jq -c '.["2"].inputs.images' "$w")" = '["1",0]' ] \
  && [ "$(jq -r '.["1"].inputs.background' "$w")" = transparent ] && ok "icon workflow: prompt verbatim (trimmed), link kept, transparent background" || no "icon workflow content"
[ "$(jq -c '.["2"].inputs.reference_images' "$RUNS/legacy-shape-edit-001/workflow.json")/$(jq -r '.["1"].inputs.image' "$RUNS/legacy-shape-edit-001/workflow.json")" = '["1",0]/ref.png' ] \
  && ok "image-edit: LoadImage -> reference_images" || no "image-edit links"
AG lint "$w" "$RUNS/legacy-shape-edit-001/workflow.json" > "$TMP/o" 2>&1 && grep -q "2 PASS, 0 WARN, 0 FAIL" "$TMP/o" && ok "rendered workflows lint clean" || no "rendered lint" "$(cat "$TMP/o")"
AG render --run "$RUNS/legacy-shape-icon-001" --param size=1536x1024 --param quality=low >/dev/null && [ "$(jq -r '.["1"].inputs.size + " " + .["1"].inputs.quality' "$w")" = "1536x1024 low" ] \
  && ok "--param overrides purpose params" || no "--param override"
d="$RUNS/legacy-shape-edit-001"; rm -f "$d/workflow.json"
out=$(AG render --run "$d" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "param reference_image is required" <<<"$out" && [ ! -f "$d/workflow.json" ] && ok "missing required param: FAIL, nothing written" || no "missing required rc=$rc" "$out"
out=$(AG render --run "$d" --param reference_image=r.png --param size=999x999 --param tint=red --param prompt=x --param bare 2>&1); rc=$?
{ [ $rc -eq 1 ] && grep -q "param size: '999x999' is not one of" <<<"$out" && grep -q "param tint is not declared" <<<"$out" \
  && grep -q "the prompt comes from the prompt file only" <<<"$out" && grep -q "expected NAME=VALUE" <<<"$out"; } \
  && ok "render rejects bad enum, undeclared param, prompt override, malformed --param" || no "render errors rc=$rc" "$out"
: > "$d/prompt.md"; out=$(AG render --run "$d" --param reference_image=r.png 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "is empty" <<<"$out" && ok "empty prompt file: error" || no "empty prompt rc=$rc" "$out"
AG render --spec "$RUNS/legacy-shape-icon-001/spec.json" --prompt-file "$RUNS/legacy-shape-icon-001/prompt.md" --out "$TMP/wf.json" >/dev/null && [ -f "$TMP/wf.json" ] \
  && ok "render --spec/--prompt-file/--out" || no "render explicit paths"
printf 'Test prompt for image-edit: one subject, centered.
' > "$d/prompt.md"; AG render --run "$d" --param reference_image=ref.png >/dev/null
# item 1: the prompt is a visible PrimitiveStringMultiline node linked into NineRouterImage.user_prompt
for pw in "legacy-shape-icon-001 1 3" "legacy-shape-edit-001 2 4"; do
  set -- $pw; f="$RUNS/$1/workflow.json"
  [ "$(jq -c --arg n "$2" '.[$n].inputs.user_prompt' "$f")" = "[\"$3\",0]" ] \
    && [ "$(jq -r --arg n "$3" '.[$n].class_type + "|" + .[$n]._meta.title' "$f")" = "PrimitiveStringMultiline|Prompt (Claude, Codex review NOT_RUN)" ] \
    && [ "$(jq -r --arg n "$3" '.[$n].inputs.value' "$f")" = "$(sed 's/[[:space:]]*$//' "$RUNS/$1/prompt.md")" ] \
    && ok "$1: prompt node $3 (Text (Multiline), review state in the title) feeds node $2 user_prompt" || no "$1 prompt node" "$(jq -c . "$f")"
done
# an API template links NineRouterImage.user_prompt; a local-only template (no NineRouterImage) links a CLIP encoder's
# text; either way no input outside the prompt node inlines {{prompt}} (graphstyle checks the full fan-out)
for t in $CORE_TEMPLATES; do
  jq -e '([.workflow[] | select(.class_type == "NineRouterImage")] | length) as $n
    | (if $n > 0 then [.workflow[] | select(.class_type == "NineRouterImage") | .inputs.user_prompt | type] == ["array"]
       else any(.workflow[] | select(.class_type | test("^CLIPTextEncode")) | .inputs | (.text, .text_g, .text_l); type == "array") end)
    and ([.workflow[] | select(.class_type != "PrimitiveStringMultiline") | .inputs | .. | strings | select(contains("{{prompt}}"))] | length == 0)' \
    "$ROOT/templates/assetgen/workflows/$t.json" >/dev/null \
    && ok "core template $t: no inline prompt, $(jq -r 'if any(.workflow[]; .class_type == "NineRouterImage") then "user_prompt" else "the encoder text" end' "$ROOT/templates/assetgen/workflows/$t.json") is a link" \
    || no "template $t user_prompt"
done
python3 -B - "$ROOT" "$w" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import runfiles
wf = json.load(open(sys.argv[2], encoding="utf-8"))
assert runfiles.workflow_prompts(wf) == [wf["3"]["inputs"]["value"]], runfiles.workflow_prompts(wf)
inline = {"1": {"class_type": "NineRouterImage", "inputs": {"user_prompt": "inline text"}}}
assert runfiles.workflow_prompts(inline) == ["inline text"]
chat = {"1": {"class_type": "NineRouterImage", "inputs": {"user_prompt": ["2", 0]}}, "2": {"class_type": "NineRouterChat", "inputs": {"user_prompt": "idea"}}}
assert runfiles.workflow_prompts(chat) == [["2", 0], "idea"], runfiles.workflow_prompts(chat)
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "runfiles.workflow_prompts follows the link to the prompt node (inline and other links unchanged)" || no "workflow_prompts" "$(cat "$TMP/o")"
# the prompt node's title carries the prompt review state of this prompt (PASS, STALE when the prompt changed)
mkrun title-icon-001 icon --style stylized-painterly --template image-generate; td="$RUNS/title-icon-001"
bound "$td" prompt PASS codex > "$td/review-prompt.json"
AG render --run "$td" >/dev/null && t1=$(jq -r '.["3"]._meta.title' "$td/workflow.json")
echo "Another prompt." > "$td/prompt.md"; AG render --run "$td" >/dev/null && t2=$(jq -r '.["3"]._meta.title' "$td/workflow.json")
[ "$t1|$t2" = "Prompt (Claude, Codex review PASS)|Prompt (Claude, Codex review STALE)" ] \
  && ok "prompt node title: Codex review PASS, STALE once the prompt changed" || no "prompt node title: $t1|$t2"
# requirements changed, prompt kept: the verdict no longer binds the spec (STALE, never PASS)
bound "$td" prompt PASS codex > "$td/review-prompt.json"
jq '.params.quality = "low"' "$td/spec.json" > "$TMP/spec.json" && cp "$TMP/spec.json" "$td/spec.json"
AG render --run "$td" >/dev/null && t3=$(jq -r '.["3"]._meta.title' "$td/workflow.json")
[ "$t3" = "Prompt (Claude, Codex review STALE)" ] \
  && ok "prompt node title: STALE when the requirements changed and the prompt did not" || no "prompt node title after requirements change: $t3"
# a verdict without a requirements binding is not bound to this spec either
bound "$td" prompt PASS codex | jq -c 'del(.requirements_sha256)' > "$td/review-prompt.json"
AG render --run "$td" >/dev/null && t4=$(jq -r '.["3"]._meta.title' "$td/workflow.json")
[ "$t4" = "Prompt (Claude, Codex review STALE)" ] && ok "prompt node title: STALE without requirements_sha256" || no "unbound requirements title: $t4"
# a fallback or other reviewer never reads "Codex review PASS": SAME_MODEL PASS is WARN, other FAIL keeps its reviewer
for c in "SAME_MODEL:claude PASS|Prompt (Claude, review SAME_MODEL:claude WARN)" "claude-sonnet FAIL|Prompt (Claude, review claude-sonnet FAIL)" \
         "gpt-5 PASS|Prompt (Claude, review gpt-5 WARN)" "codex-mini PASS|Prompt (Claude, Codex review PASS)" " PASS|Prompt (Claude, review without reviewer WARN)"; do
  by=${c%% *}; rest=${c#* }; st=${rest%%|*}; want=${c#*|}
  if [ -z "$by" ]; then bound "$td" prompt PASS x | jq -c 'del(.by)' > "$td/review-prompt.json"; else bound "$td" prompt "$st" "$by" > "$td/review-prompt.json"; fi
  AG render --run "$td" >/dev/null && t=$(jq -r '.["3"]._meta.title' "$td/workflow.json")
  ul=$(jq -r '[.nodes[] | select(.type == "PrimitiveStringMultiline") | .title][0]' "$td/workflow.ui.json")
  [ "$t|$ul" = "$want|$want" ] && ok "prompt node title for by=${by:-none} $st: $want" || no "prompt node title by=${by:-none}: $t|$ul (want $want)"
done
# the image review binding covers the prompt node: another prompt value is another requirements hash
jq '.["3"].inputs.value = "changed"' "$RUNS/legacy-shape-icon-001/workflow.json" > "$TMP/changed-wf.json"
python3 -B - "$ROOT" "$RUNS/legacy-shape-icon-001/spec.json" "$RUNS/legacy-shape-icon-001/workflow.json" "$TMP/changed-wf.json" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import runfiles
spec = json.load(open(sys.argv[2], encoding="utf-8"))
a, b = (runfiles.requirements_sha256(spec, runfiles.generation_inputs(json.load(open(f, encoding="utf-8")), spec)) for f in sys.argv[3:5])
assert a != b
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "image review requirements hash covers the prompt node value (whole rendered graph)" || no "binding covers prompt node" "$(cat "$TMP/o")"

echo "-- workflow.ui.json: the same graph for the ComfyUI frontend"
# stdlib UI -> API converter (as comfy-9router run_sample.py, object_info from data/known-nodes.json): widgets_values in
# input order, then each linked socket; the result must equal workflow.json
cat > "$TMP/ui2api.py" <<'EOF'
import json, sys
known = json.load(open(sys.argv[1], encoding="utf-8"))["nodes"]
ui = json.load(open(sys.argv[2], encoding="utf-8"))
api = json.load(open(sys.argv[3], encoding="utf-8"))
WIDGETS = ("STRING", "INT", "FLOAT", "BOOLEAN", "COMBO")
by_id = {n["id"]: n for n in ui["nodes"]}
links = {l[0]: l for l in ui["links"]}
assert len(links) == len(ui["links"]) and ui["last_link_id"] == max(links, default=0) and ui["last_node_id"] == max(by_id)
assert sorted(n["order"] for n in ui["nodes"]) == list(range(len(ui["nodes"])))
graph = {}
for node in ui["nodes"]:
    spec = known[node["type"]]
    assert len(node["pos"]) == 2 and len(node["size"]) == 2 and node["title"]
    if spec.get("ui_only"):
        continue
    values, inputs = iter(node["widgets_values"]), {}
    for name, decl in spec["inputs"].items():
        if decl["type"] in WIDGETS:
            try:
                inputs[name] = next(values)
            except StopIteration:
                if decl.get("required"):
                    raise ValueError("missing widget %s.%s" % (node["type"], name))
    for i, socket in enumerate(node.get("inputs", [])):
        if socket.get("link") is None:
            continue
        link = links[socket["link"]]
        assert link[3] == node["id"] and link[4] == i, link
        src = by_id[link[1]]
        assert src["outputs"][link[2]]["type"] == link[5] and link[0] in src["outputs"][link[2]]["links"], link
        inputs[socket["name"]] = [str(link[1]), link[2]]
    graph[str(node["id"])] = {"class_type": node["type"], "inputs": inputs, "_meta": {"title": node["title"]}}
for nid in api:
    api[nid].setdefault("_meta", {"title": api[nid]["class_type"]})
assert graph == api, json.dumps({"ui->api": graph, "workflow.json": api}, indent=1, sort_keys=True)
print("ok")
EOF
KN="$ROOT/scripts/assetgen/data/known-nodes.json"
for p in $CORE_PURPOSES; do
  # re-render with the cases params only: earlier tests re-rendered some runs with other params
  d="$RUNS/golden-$p-001"; mapfile -t args < <(case_params "$p"); AG render --run "$d" "${args[@]}" >/dev/null
  out=$(python3 -B "$TMP/ui2api.py" "$KN" "$d/workflow.ui.json" "$d/workflow.json" 2>&1)
  [ "$out" = ok ] && [ "$(jq -r '.extra.assetgen.run_id + "|" + (.version | tostring)' "$d/workflow.ui.json")" = "golden-$p-001|0.4" ] \
    && ok "workflow.ui.json $p: converts back to workflow.json; run id in extra" || no "ui workflow $p" "$out"
  for t in $(case_variants "$p"); do
    d="$RUNS/golden-$p--$t-001"; mapfile -t args < <(case_params "$p" "$t")
    AG render --run "$d" "${args[@]}" >/dev/null 2>&1
    out=$(python3 -B "$TMP/ui2api.py" "$KN" "$d/workflow.ui.json" "$d/workflow.json" 2>&1)
    [ "$out" = ok ] && [ "$(jq -r '.extra.assetgen.run_id + "|" + (.version | tostring)' "$d/workflow.ui.json")" = "golden-$p--$t-001|0.4" ] \
      && ok "workflow.ui.json $p--$t: converts back to workflow.json; run id in extra" || no "ui workflow $p--$t" "$out"
  done
done
u="$RUNS/legacy-shape-edit-001/workflow.ui.json"
[ "$(jq -c '[.nodes[] | select(.type == "LoadImage") | .widgets_values][0]' "$u")" = '["ref.png","image"]' ] \
  && [ "$(jq -c '[.nodes[] | select(.type == "NineRouterImage") | .inputs[] | {name, link: (.link != null), widget: (.widget.name // null)}]' "$u")" = \
       '[{"name":"user_prompt","link":true,"widget":"user_prompt"},{"name":"reference_images","link":true,"widget":null}]' ] \
  && [ "$(jq -r '[.nodes[] | select(.type == "PrimitiveStringMultiline") | .title][0]' "$u")" = "Prompt (Claude, Codex review NOT_RUN)" ] \
  && ok "workflow.ui.json image-edit: LoadImage upload widget, linked prompt widget socket, prompt node title" || no "ui image-edit" "$(jq -c .nodes "$u")"
[ "$(jq -c '[.nodes[] | {id, x: .pos[0]}] | sort_by(.id)' "$RUNS/legacy-shape-icon-001/workflow.ui.json")" = '[{"id":1,"x":500},{"id":2,"x":940},{"id":3,"x":60}]' ] \
  && ok "workflow.ui.json layout: one column per link depth (prompt -> image -> save)" || no "ui layout" "$(jq -c '[.nodes[] | {id, pos}]' "$RUNS/legacy-shape-icon-001/workflow.ui.json")"
[ -f "$TMP/wf.ui.json" ] && [ "$(jq -r '.extra.assetgen.run_id' "$TMP/wf.ui.json")" = null ] \
  && [ "$(python3 -B "$TMP/ui2api.py" "$KN" "$TMP/wf.ui.json" "$TMP/wf.json" 2>&1)" = ok ] \
  && ok "render --out X.json also writes X.ui.json (no run id)" || no "render --out ui file"

echo "-- workflow.ui.json: ui block groups, notes, colors"
python3 -B - "$ROOT" >"$TMP/staged-layout-check" 2>&1 <<'EOF'
import json, math, sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts/assetgen"))
import uiworkflow

known = json.loads((root / "scripts/assetgen/data/known-nodes.json").read_text(encoding="utf-8"))["nodes"]
def rect(node):
    x, y = node["pos"]
    w, h = node["size"]
    return (x, y - 30, x + w, y + h)
def bounds(group):
    x, y, w, h = group["bounding"]
    return (x, y, x + w, y + h)
def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]
def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

templates = sorted((root / "templates/assetgen/workflows").glob("*.json"))
assert templates, "no core workflow templates found"
for path in templates:
    t = json.loads(path.read_text(encoding="utf-8"))
    block = t.get("ui") or {}  # legacy templates (image-edit, image-generate) have no ui block: no groups, no notes
    ui = uiworkflow.to_ui(t["workflow"], known, None, t.get("ui"))
    nodes = {n["id"]: n for n in ui["nodes"]}
    for link in ui["links"]:
        _, src, src_slot, dst, dst_slot, _ = link
        source, target = nodes[src], nodes[dst]
        a = (source["pos"][0] + source["size"][0], source["pos"][1] + 14 + 20 * src_slot)
        b = (target["pos"][0], target["pos"][1] + 14 + 20 * dst_slot)
        d = math.hypot(b[0] - a[0], b[1] - a[1]) * 0.25
        controls = (a, (a[0] + d, a[1]), (b[0] - d, b[1]), b)
        for i in range(1, 65):
            u = i / 65
            x, y = (sum(weight * point[axis] for weight, point in zip(
                ((1-u)**3, 3*(1-u)**2*u, 3*(1-u)*u*u, u**3), controls)) for axis in (0, 1))
            for nid, node in nodes.items():
                if nid in (src, dst):
                    continue
                x1, y1, x2, y2 = rect(node)
                assert not (x1 < x < x2 and y1 < y < y2), (path.name, link, nid)
    notes = [n for n in ui["nodes"] if n["type"] == "Note"]
    assert len(notes) == len(block.get("notes", [])), path.name
    assert len(ui["groups"]) == len(block.get("groups", [])), path.name
    for group, decl in zip(ui["groups"], block.get("groups", [])):
        members = {int(n) for n in decl["nodes"]}
        members.update(n["id"] for n, note in zip(notes, block.get("notes", [])) if note["group"] == group["title"])
        box = bounds(group)
        assert all(contains(box, rect(nodes[n])) for n in members), (path.name, group)
        assert all(not intersects(box, rect(n)) for nid, n in nodes.items() if nid not in members), (path.name, group)
    for left, right in zip(ui["groups"], ui["groups"][1:]):
        assert bounds(left)[0] <= bounds(right)[0], (path.name, left, right)
    if path.name == "staged-icon.json":
        save = next(n for n in nodes.values() if n["type"] == "SaveImage")
        for node in (n for n in nodes.values() if n["type"] in ("ImageScale", "PreviewImage")):
            assert rect(save)[3] <= rect(node)[1] or rect(node)[3] <= rect(save)[1], (path.name, save, node)
print("ok")
EOF
staged_layout_rc=$?
[ $staged_layout_rc -eq 0 ] && ok "workflow.ui.json every core workflow template: no wire crosses an unrelated node, Save off the preview row, groups hold members and notes" \
  || no "workflow.ui.json core templates layout rc=$staged_layout_rc" "$(cat "$TMP/staged-layout-check")"
# Each re-laid template's ui.positions apply to its layout, and ui.positions validates: unknown node id, non-pair, non-finite number,
# bool and a non-object each raise a ValueError naming ui positions; a position overrides the computed one.
python3 -B - "$ROOT" > "$TMP/positions-check" 2>&1 <<'EOF'
import copy, json, math, sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts/assetgen"))
import uiworkflow

known = json.loads((root / "scripts/assetgen/data/known-nodes.json").read_text(encoding="utf-8"))["nodes"]
RELAID = ("hybrid-character", "hybrid-environment", "hybrid-icon-ui", "local-variation")
workflows = root / "templates/assetgen/workflows"
for name in RELAID:
    t = json.loads((workflows / (name + ".json")).read_text(encoding="utf-8"))
    positions = t["ui"].get("positions")
    assert isinstance(positions, dict) and positions and set(positions) <= set(t["workflow"]), name
    ui = uiworkflow.to_ui(t["workflow"], known, None, t["ui"])
    nodes = {str(n["id"]): n for n in ui["nodes"]}
    assert all(nodes[nid]["pos"] == list(pos) for nid, pos in positions.items()), name

graph = json.loads((root / "tests/fixtures/assetgen/local/hybrid-anchor-template.json").read_text(encoding="utf-8"))
def lay(positions, groups=True):
    ui = copy.deepcopy(graph["ui"]) if groups else {}
    if positions is not None:
        ui["positions"] = positions
    return uiworkflow.to_ui(graph["workflow"], known, None, ui)
def refuses(positions, *words):
    try:
        lay(positions)
    except ValueError as exc:
        assert "ui positions" in str(exc), (positions, str(exc))
        assert all(w in str(exc) for w in words), (positions, str(exc))
        return
    raise AssertionError("accepted %r" % (positions,))
refuses({"99": [0, 0]}, "unknown node id")
refuses({"1": [0]}, "pair")
refuses({"1": [0, 1, 2]}, "pair")
refuses({"1": "0,1"}, "pair")
refuses({"1": [0, float("nan")]}, "finite")
refuses({"1": [float("inf"), 0]}, "finite")
refuses({"1": [True, 0]}, "finite")
refuses({"1": [0, "1"]}, "finite")
refuses([["1", 0, 0]], "must be an object")
refuses({1: [0, 0]}, "unknown node id")
for groups in (True, False):
    plain = {str(n["id"]): n for n in lay(None, groups)["nodes"]}
    moved = lay({"5": [123, 456.5]}, groups)
    nodes = {str(n["id"]): n for n in moved["nodes"]}
    assert nodes["5"]["pos"] == [123, 456.5], (groups, nodes["5"]["pos"])
    assert all(nodes[k]["pos"] == plain[k]["pos"] for k in plain if k != "5" and plain[k]["type"] != "Note"), groups
# a moved member stays inside its group box: positions apply before the group bounds
moved = lay({"5": [9000, 40000]})
node = next(n for n in moved["nodes"] if str(n["id"]) == "5")
group = next(g for g in moved["groups"] if g["title"] == "Generate")
x, y, w, h = group["bounding"]
assert x <= node["pos"][0] and node["pos"][0] + node["size"][0] <= x + w and y <= node["pos"][1] - 30 and node["pos"][1] + node["size"][1] <= y + h
print("ok")
EOF
positions_rc=$?
[ $positions_rc -eq 0 ] && grep -qx ok "$TMP/positions-check" \
  && ok "ui.positions: unknown id, non-pair, non-finite, bool and non-object raise a ValueError naming ui positions; a position overrides the computed one and stays inside its group" \
  || no "ui.positions validation rc=$positions_rc" "$(cat "$TMP/positions-check")"
cp "$ROOT/tests/fixtures/assetgen/ui-layout.json" "$GL/templates/ui-layout.json"
mkrun ui-layout-001 icon --style stylized-painterly --authoring "$AUTH" --template ui-layout
ud="$RUNS/ui-layout-001"
AG render --run "$ud" >"$TMP/o" 2>"$TMP/err"; rc=$?
python3 -B - "$ud/workflow.ui.json" "$ud/workflow.json" "$ROOT/tests/fixtures/assetgen/ui-layout.json" >"$TMP/ui-layout-check" 2>&1 <<'EOF'
import json, sys
ui, api, fixture = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:])
groups, nodes = ui["groups"], {n["id"]: n for n in ui["nodes"]}
settings = fixture["ui"]
assert [(g["id"], g["title"], g["color"], g["font_size"], g["flags"]) for g in groups] == [
    (1, "Prompt", "#3f789e", 24, {}), (2, "Generate", "#abc", 24, {}),
    (3, "Post-process", "#8A8", 24, {}), (4, "Output", "#a1309b", 24, {})]
notes = [n for n in ui["nodes"] if n["type"] == "Note"]
assert len(notes) == len(settings["notes"]) == 4
assert [n["widgets_values"] for n in notes] == [[n["text"]] for n in settings["notes"]]
assert [n["id"] for n in notes] == list(range(max(map(int, api)) + 1, max(map(int, api)) + 5))
assert ui["last_node_id"] == max(nodes)
assert (nodes[1]["color"], nodes[1]["bgcolor"]) == ("#232", "#353")
assert (nodes[4]["color"], nodes[4]["bgcolor"]) == ("#232", "#353")
assert nodes[4]["pos"][0] == nodes[5]["pos"][0] and nodes[5]["pos"][1] < nodes[4]["pos"][1]
def rect(node):
    x, y = node["pos"]
    w, h = node["size"]
    return (x, y - 30, x + w, y + h)
def bounds(group):
    x, y, w, h = group["bounding"]
    return (x, y, x + w, y + h)
def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]
def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
for group, decl in zip(groups, settings["groups"]):
    members = {int(n) for n in decl["nodes"]}
    members.update(n["id"] for n, note in zip(notes, settings["notes"]) if note["group"] == group["title"])
    box = bounds(group)
    assert all(contains(box, rect(nodes[n])) for n in members), group
    assert all(not intersects(box, rect(n)) for nid, n in nodes.items() if nid not in members), group
for left, right in zip(groups, groups[1:]):
    assert bounds(left)[2] <= bounds(right)[0], (left, right)
print("ok")
EOF
layout_rc=$?
out=$(python3 -B "$TMP/ui2api.py" "$KN" "$ud/workflow.ui.json" "$ud/workflow.json" 2>&1)
[ $rc -eq 0 ] && [ $layout_rc -eq 0 ] && [ "$out" = ok ] \
  && ok "ui block: group bounds, notes, colors, row order and API round trip" \
  || no "ui block render rc=$rc layout rc=$layout_rc" "$(cat "$TMP/err" "$TMP/ui-layout-check"); $out"
cp "$ud/workflow.json" "$TMP/ui-layout-workflow.json"
cp "$ud/spec.json" "$TMP/ui-layout-spec.json"
jq 'del(.template.data.ui)' "$TMP/ui-layout-spec.json" > "$ud/spec.json"
AG render --run "$ud" >"$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && cmp -s "$TMP/ui-layout-workflow.json" "$ud/workflow.json" \
  && ok "ui block leaves workflow.json identical" || no "ui block changes workflow.json rc=$rc" "$(cat "$TMP/err")"
for bad in unknown-node duplicate-node unknown-group; do
  case "$bad" in
    unknown-node) filter='.template.data.ui.groups[0].nodes += ["999"]' ;;
    duplicate-node) filter='.template.data.ui.groups[1].nodes += ["3"]' ;;
    unknown-group) filter='.template.data.ui.notes[0].group = "Missing"' ;;
  esac
  jq "$filter" "$TMP/ui-layout-spec.json" > "$ud/spec.json"
  AG render --run "$ud" >"$TMP/o" 2>"$TMP/err"; rc=$?
  [ $rc -eq 1 ] && grep -q 'workflow.ui.json' "$TMP/o" "$TMP/err" \
    && ok "ui block rejects $bad" || no "ui block $bad rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
done
rm -f "$GL/templates/ui-layout.json"

echo "-- filename_prefix: one value in spec.json, workflow.json, review prompts and run.md"
mkrun prefix-icon-001 icon --style stylized-painterly; pd="$RUNS/prefix-icon-001"; want=assetgen/prefix-icon-001
AG render --run "$pd" >/dev/null 2>"$TMP/err" && AG manifest --run "$pd" >/dev/null 2>>"$TMP/err"
got="$(jq -r .params.filename_prefix "$pd/spec.json")|$(jq -r '[.[] | select(.class_type == "SaveImage")][0].inputs.filename_prefix' "$pd/workflow.json")"
got="$got|$(sed -n '/^---json$/,/^---$/p' "$pd/run.md" | sed '1d;$d' | jq -r .spec.params.filename_prefix)"
AG review-cmd --phase prompt --run "$pd" --json | jq -r .stdin > "$TMP/rp.txt"
[[ "$got" = "$want|$want|$want" || "$got" = "$want|$want-"*"|$want" ]] && grep -q "filename_prefix=$want" "$TMP/rp.txt" && ! grep -q 'assetgen/run\b' "$pd/workflow.json" "$pd/workflow.ui.json" "$pd/run.md" "$TMP/rp.txt" \
  && [ "$(jq -r .param_sources.filename_prefix "$pd/spec.json")" = "run id prefix-icon-001" ] \
  && ok "filename_prefix $want in spec.json, workflow.json, run.md and the review prompt (never assetgen/run)" || no "filename_prefix: $got" "$(cat "$TMP/err"; grep -n filename_prefix "$TMP/rp.txt")"
mkdir -p "$RUNS/prefix-copy-001"; cp "$TMP/spec-out.json" "$RUNS/prefix-copy-001/spec.json"; cp "$pd/prompt.md" "$RUNS/prefix-copy-001/"
[ "$(jq -r .params.filename_prefix "$TMP/spec-out.json")" = assetgen/run ] && ok "resolve --out outside a run dir keeps the template default prefix" || no "default prefix"
out=$(AG render --run "$RUNS/prefix-copy-001" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "spec.json records filename_prefix 'assetgen/run', run prefix-copy-001 needs 'assetgen/prefix-copy-001'" <<<"$out" \
  && [ ! -f "$RUNS/prefix-copy-001/workflow.json" ] && ok "render --run refuses a spec.json resolved for another prefix, nothing written" || no "foreign spec rc=$rc" "$out"
out=$(AG render --run "$pd" --param filename_prefix=elsewhere 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "a run's prefix is $want" <<<"$out" && ok "render --run refuses --param filename_prefix" || no "prefix override rc=$rc" "$out"
rm -rf "$RUNS/prefix-copy-001"

echo "-- lint: errors and warnings"
LA="$TMP/lint-authoring"; mkdir -p "$LA/assetgen/templates" "$LA/assetgen/purposes"
tmpl() { printf '{"schema": "rpg-factory.comfy-template/1", "title": "t", "output_node": "2", "params": {"prompt": {"type": "string", "required": true}%s}, "workflow": %s}\n' "$2" "$3" > "$LA/assetgen/templates/$1.json"; }
SAVE='"2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x", "images": ["1", 0]}}'
tmpl unknown-node '' "{\"1\": {\"class_type\": \"FluxSampler\", \"inputs\": {\"text\": \"{{prompt}}\"}}, $SAVE}"
tmpl bad-input '' "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\", \"seed\": 1}}, $SAVE}"
tmpl missing-link '' "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\"}}, \"2\": {\"class_type\": \"SaveImage\", \"inputs\": {\"filename_prefix\": \"x\", \"images\": [\"9\", 0]}}}"
tmpl type-mismatch '' "{\"1\": {\"class_type\": \"NineRouterChat\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"system_prompt\": \"s\"}}, $SAVE}"
tmpl bad-combo '' "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"size\": \"999x999\", \"quality\": \"auto\", \"background\": \"auto\"}}, $SAVE}"
tmpl undeclared '' "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}} {{mood}}\", \"model\": \"m\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\"}}, $SAVE}"
tmpl unsupported-model ', "model": {"type": "string", "default": "cx/gpt-image-2.5"}' "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"{{model}}\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\"}}, $SAVE}"
scheme=https
tmpl endpoint ", \"base_url\": {\"type\": \"string\", \"default\": \"$scheme://router.example.invalid/v1\"}" "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\"}}, $SAVE}"
lint_of() { AG lint "$LA/assetgen/templates/$1.json" --authoring "$LA" --json 2>&1 | jq -r '.results[0] | .state + " " + (.reasons | join("; "))'; }
expect_lint() { # expect_lint ID STATE TEXT LABEL
  local got; got=$(lint_of "$1")
  case "$got" in "$2 "*"$3"*) ok "lint $4" ;; *) no "lint $4" "$got" ;; esac
}

echo "-- node registry"
NS="$ROOT/scripts/assetgen/nodesync.py"; OI="$ROOT/tests/fixtures/assetgen/object_info.json"
local_names=(CheckpointLoaderSimple CLIPTextEncode CLIPTextEncodeSDXL EmptyLatentImage VAEEncode VAEDecode VAEDecodeTiled KSampler LoraLoader ControlNetLoader ControlNetApplyAdvanced UpscaleModelLoader ImageUpscaleWithModel)
node_names=(ImageScale ImageSharpen ImageBlur ImageInvert ImageCrop PreviewImage SplitImageWithAlpha JoinImageWithAlpha ImageQuantize PrimitiveString "${local_names[@]}")
node_args=(); for name in "${node_names[@]}"; do node_args+=(--node "$name"); done
python3 -B "$NS" "$OI" "${node_args[@]}" > "$TMP/nodes.json" 2>"$TMP/err"; rc=$?
jq -c . "$TMP/nodes.json" > "$TMP/nodes-actual" 2>/dev/null
jq -c --slurpfile generated "$TMP/nodes.json" '.nodes as $nodes | reduce ($generated[0] | keys_unsorted[]) as $name ({}; .[$name] = $nodes[$name])' "$KN" > "$TMP/nodes-expected" 2>"$TMP/jqerr"
[ $rc -eq 0 ] && cmp -s "$TMP/nodes-actual" "$TMP/nodes-expected" && ok "nodesync fixture entries match registry including key order" \
  || no "nodesync fixture entries differ rc=$rc" "$(cat "$TMP/err" "$TMP/jqerr")"
python3 -B "$NS" "$OI" "${node_args[@]}" --check > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && ok "nodesync --check accepts committed entries" || no "nodesync --check rc=$rc" "$(cat "$TMP/err")"
# pack nodes: no saved object_info from a machine with the packs existed, so object_info-packs.json is written from the
# pack sources (known-nodes packs[].signatures names each); the registry entries must still be nodesync's output of it
OIP="$ROOT/tests/fixtures/assetgen/object_info-packs.json"; HW="$ROOT/scripts/assetgen/data/hardware.json"
pack_names=(IPAdapterUnifiedLoader IPAdapterAdvanced CannyEdgePreprocessor InspyrenetRembg)
# the registry lists two more pack nodes (the annotator preprocessors) that object_info-packs.json does not carry
registry_pack_names=(IPAdapterUnifiedLoader IPAdapterAdvanced CannyEdgePreprocessor DepthAnythingPreprocessor DWPosePreprocessor InspyrenetRembg)
# local_model_nodes also holds KSamplerAdvanced, a core node that object_info.json does not carry; the preprocessors are pack
# nodes, so lint and graphstyle already require the requires block for them and they stay out of local_model_nodes
registry_local_names=("${local_names[@]}" KSamplerAdvanced)
pack_args=(); for name in "${pack_names[@]}"; do pack_args+=(--node "$name"); done
python3 -B "$NS" "$OIP" "${pack_args[@]}" > "$TMP/pack-nodes.json" 2>"$TMP/err"; rc=$?
jq -c . "$TMP/pack-nodes.json" > "$TMP/pack-nodes-actual" 2>/dev/null
jq -c --slurpfile generated "$TMP/pack-nodes.json" '.nodes as $nodes | reduce ($generated[0] | keys_unsorted[]) as $name ({}; .[$name] = $nodes[$name])' "$KN" > "$TMP/pack-nodes-expected" 2>"$TMP/jqerr"
[ $rc -eq 0 ] && [ "$(jq 'length' "$TMP/pack-nodes.json")" = "${#pack_names[@]}" ] && cmp -s "$TMP/pack-nodes-actual" "$TMP/pack-nodes-expected" \
  && ok "nodesync pack fixture entries match registry including key order (${#pack_names[@]} pack nodes)" \
  || no "nodesync pack fixture entries differ rc=$rc" "$(cat "$TMP/err" "$TMP/jqerr")"
python3 -B "$NS" "$OIP" "${pack_args[@]}" --check > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && ok "nodesync --check accepts committed pack entries" || no "nodesync --check packs rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
python3 -B - "$KN" "$HW" "${#registry_local_names[@]}" "${registry_local_names[@]}" "${registry_pack_names[@]}" > "$TMP/o" 2>&1 <<'EOF'
import json, sys
known_path, hardware_path, n_local = sys.argv[1], sys.argv[2], int(sys.argv[3])
local_names, pack_names = sys.argv[4:4 + n_local], sys.argv[4 + n_local:]
with open(known_path, encoding="utf-8") as f:
    known = json.load(f)
with open(hardware_path, encoding="utf-8") as f:
    hardware = json.load(f)
nodes, packs, local = known["nodes"], known["packs"], known["local_model_nodes"]
profile_packs = [p["id"] for prof in hardware["profiles"] if prof["id"] == "local-8gb" for p in prof["packs"]]
assert packs and profile_packs and all(pid in profile_packs for pid in packs), (list(packs), profile_packs)
for pid, spec in packs.items():
    assert spec["nodes"] and all(name in nodes for name in spec["nodes"]), pid
    assert spec["provider"] and spec["signatures"], pid
pack_nodes = [name for spec in packs.values() for name in spec["nodes"]]
assert sorted(pack_nodes) == sorted(pack_names), pack_nodes
assert local == local_names and all(name in nodes for name in local), local
assert not set(local) & set(pack_nodes)
assert "UNTESTED on RTX 5060" in known["note"]
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "known-nodes: every pack node and local_model_nodes name is a registry node, every pack id is a local-8gb pack of hardware.json, the note says UNTESTED on RTX 5060" \
  || no "known-nodes packs / local_model_nodes" "$(cat "$TMP/o")"
jq '.nodes.ImageScale.inputs.upscale_method.options[0] = "changed"' "$KN" > "$TMP/known-changed.json"
python3 -B "$NS" "$OI" "${node_args[@]}" --known "$TMP/known-changed.json" --check > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -qx ImageScale "$TMP/o" && ok "nodesync --check detects a changed combo option" || no "nodesync changed option rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
for name in MissingNode Note; do
  python3 -B "$NS" "$OI" --node "$name" > "$TMP/o" 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && ok "nodesync rejects $name" || no "nodesync $name rc=$rc" "$(cat "$TMP/err")"
done
python3 -B - "$NS" "$OI" > "$TMP/o" 2>&1 <<'EOF'
import ast, runpy, socket, sys
path, fixture = sys.argv[1:]
tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        names = [alias.name.split('.')[0] for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        names = [(node.module or '').split('.')[0]]
    else:
        continue
    assert not set(names) & {'socket', 'urllib', 'http', 'requests', 'subprocess'}, names
def forbidden(*args, **kwargs):
    raise AssertionError('network access attempted')
socket.socket = forbidden
sys.argv = [path, fixture, '--node', 'ImageScale', '--check']
runpy.run_path(path, run_name='__main__')
EOF
rc=$?; [ $rc -eq 0 ] && ok "nodesync has no network imports and runs with sockets disabled" || no "nodesync offline rc=$rc" "$(cat "$TMP/o")"

# Keep these templates outside lint-authoring, whose complete contents are counted later.
lint_la=$LA; LA="$TMP/node-registry-authoring"; mkdir -p "$LA/assetgen/templates"
graph='{"1":{"class_type":"NineRouterImage","inputs":{"user_prompt":"{{prompt}}","model":"m","size":"auto","quality":"auto","background":"auto"}},
"2":{"class_type":"SaveImage","inputs":{"images":["10",0],"filename_prefix":["12",0]}},
"3":{"class_type":"ImageScale","inputs":{"image":["1",0],"upscale_method":"bilinear","width":512,"height":256,"crop":"center"}},
"4":{"class_type":"ImageSharpen","inputs":{"image":["3",0],"sharpen_radius":2,"sigma":1.5,"alpha":0.8}},
"5":{"class_type":"ImageBlur","inputs":{"image":["4",0],"blur_radius":3,"sigma":1.2}},
"6":{"class_type":"ImageInvert","inputs":{"image":["5",0]}},
"7":{"class_type":"ImageCrop","inputs":{"image":["6",0],"width":128,"height":64,"x":4,"y":8}},
"8":{"class_type":"SplitImageWithAlpha","inputs":{"image":["7",0]}},
"9":{"class_type":"JoinImageWithAlpha","inputs":{"image":["8",0],"alpha":["8",1]}},
"10":{"class_type":"ImageQuantize","inputs":{"image":["9",0],"colors":32,"dither":"none"}},
"11":{"class_type":"PreviewImage","inputs":{"images":["5",0]}},
"12":{"class_type":"PrimitiveString","inputs":{"value":"assetgen/test"}}}'
tmpl registry-chain '' "$graph"
expect_lint registry-chain PASS "" "core image node chain"
python3 -B - "$ROOT" "$LA/assetgen/templates/registry-chain.json" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
root, template = sys.argv[1:]
sys.path.insert(0, os.path.join(root, 'scripts', 'assetgen'))
import uiworkflow
with open(template, encoding='utf-8') as f:
    graph = json.load(f)['workflow']
with open(os.path.join(root, 'scripts', 'assetgen', 'data', 'known-nodes.json'), encoding='utf-8') as f:
    known = json.load(f)['nodes']
ui = uiworkflow.to_ui(graph, known)
nodes = {n['type']: n for n in ui['nodes']}
assert len(ui['nodes']) == len(graph)
assert nodes['ImageScale']['widgets_values'] == ['bilinear', 512, 256, 'center']
assert nodes['ImageSharpen']['widgets_values'] == [2, 1.5, 0.8]
assert nodes['ImageBlur']['widgets_values'] == [3, 1.2]
assert nodes['ImageCrop']['widgets_values'] == [128, 64, 4, 8]
assert nodes['ImageQuantize']['widgets_values'] == [32, 'none']
assert len(nodes['JoinImageWithAlpha']['inputs']) == 2
EOF
rc=$?; [ $rc -eq 0 ] && ok "UI lays out node chain with numeric widgets in input order" || no "UI node chain rc=$rc" "$(cat "$TMP/o")"
for name in Note MarkdownNote; do
  jq --arg name "$name" '.workflow["13"] = {class_type: $name, inputs: {text: "note"}}' "$LA/assetgen/templates/registry-chain.json" > "$LA/assetgen/templates/ui-$name.json"
  expect_lint "ui-$name" FAIL "UI-only" "$name is UI-only"
done
jq '.workflow["3"].inputs.scale_by = 2' "$LA/assetgen/templates/registry-chain.json" > "$LA/assetgen/templates/registry-input.json"
expect_lint registry-input FAIL "unknown input scale_by" "unknown input on ImageScale"
jq '.workflow["3"].class_type = "UnknownImageNode"' "$LA/assetgen/templates/registry-chain.json" > "$LA/assetgen/templates/registry-unknown.json"
expect_lint registry-unknown FAIL "unknown node type UnknownImageNode" "unknown node in image chain"

# local nodes and the template requires block (UNTESTED on RTX 5060: the fixture declares, lint compares the
# declaration with data/hardware.json; nothing here was generated or measured). File names and sizes are placeholders.
LOCAL="$LA/assetgen/templates/local-full.json"
cat > "$LOCAL" <<'EOF'
{"schema": "rpg-factory.comfy-template/1", "title": "Local SDXL chain (lint fixture)",
 "description": "UNTESTED on RTX 5060: lint fixture for the local node registry; no image was generated and no number measured.",
 "output_node": "16",
 "params": {"prompt": {"type": "string", "required": true}, "negative": {"type": "string", "default": "blurry"},
  "checkpoint": {"type": "string", "default": "sdxl-checkpoint-fp16.safetensors"}, "seed": {"type": "int", "default": 1}},
 "requires": {"profile": "local-8gb", "peak_vram_gb": 7.0, "ram_gb": 16,
  "packs": ["comfyui_ipadapter_plus", "comfyui_controlnet_aux", "cut-out (BiRefNet or rembg)"],
  "models": [{"kind": "checkpoints", "name": "sdxl-checkpoint-fp16.safetensors", "size_gb": 6.5},
   {"kind": "controlnet", "name": "sdxl-controlnet-canny.safetensors", "size_gb": 2.5},
   {"kind": "ipadapter", "name": "sdxl-ipadapter-plus.safetensors", "size_gb": 0.8},
   {"kind": "clip_vision", "name": "clip-vision-vit-h.safetensors", "size_gb": 2.5},
   {"kind": "upscale_models", "name": "upscaler-4x.safetensors", "size_gb": 0.1}]},
 "workflow": {
  "1": {"class_type": "NineRouterImage", "inputs": {"user_prompt": "{{prompt}}", "model": "m", "size": "auto", "quality": "auto", "background": "auto"}},
  "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{checkpoint}}"}},
  "3": {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": ["2", 0], "preset": "PLUS (high strength)"}},
  "4": {"class_type": "IPAdapterAdvanced", "inputs": {"model": ["3", 0], "ipadapter": ["3", 1], "image": ["1", 0], "weight": 0.8, "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only"}},
  "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["2", 1]}},
  "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["2", 1]}},
  "7": {"class_type": "CannyEdgePreprocessor", "inputs": {"image": ["1", 0], "low_threshold": 100, "high_threshold": 200, "resolution": 1024}},
  "8": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "sdxl-controlnet-canny.safetensors"}},
  "9": {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["5", 0], "negative": ["6", 0], "control_net": ["8", 0], "image": ["7", 0], "strength": 0.6, "start_percent": 0.0, "end_percent": 1.0, "vae": ["2", 2]}},
  "10": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
  "11": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": "{{seed}}", "steps": 24, "cfg": 6.5, "sampler_name": "euler", "scheduler": "karras", "positive": ["9", 0], "negative": ["9", 1], "latent_image": ["10", 0], "denoise": 1.0}},
  "12": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["11", 0], "vae": ["2", 2], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
  "13": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "upscaler-4x.safetensors"}},
  "14": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["13", 0], "image": ["12", 0]}},
  "15": {"class_type": "InspyrenetRembg", "inputs": {"image": ["14", 0], "torchscript_jit": "default"}},
  "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": "assetgen/local"}}}}
EOF
lv() { local id=$1; shift; jq "$@" "$LOCAL" > "$LA/assetgen/templates/$id.json"; }  # lv ID JQ-ARGS: a variant of local-full
expect_clean() { local got; got=$(lint_of "$1"); [ "$got" = "PASS " ] && ok "lint $2" || no "lint $2" "$got"; }  # PASS, no reason
jq -e '.description | startswith("UNTESTED on RTX 5060:")' "$LOCAL" >/dev/null && expect_clean local-full "local template: a local SDXL chain with all four pack nodes and a complete requires block PASSES, no reasons" \
  || no "local template fixture description must start with UNTESTED on RTX 5060:"
hw_profiles=$(jq -r '[.profiles[].id] | join(", ")' "$HW")
hw_lim() { jq -r --arg f "$1" '.profiles[] | select(.id == "local-8gb") | .requires[$f]' "$HW"; }
vram_max=$(hw_lim min_vram_gb); ram_max=$(hw_lim min_ram_gb)
lv local-vram-edge --argjson v "$vram_max" --argjson r "$ram_max" '.requires.peak_vram_gb = $v | .requires.ram_gb = $r'
expect_clean local-vram-edge "requires: peak_vram_gb and ram_gb equal to the profile's values PASS"
lv local-extra-kinds '.requires.models += [{"kind": "loras", "name": "style.safetensors", "size_gb": 0.2}, {"kind": "vae", "name": "sdxl-vae.safetensors", "size_gb": 0.3}]'
expect_clean local-extra-kinds "requires.models: kinds loras and vae are accepted"
jq '.requires = {"profile": "api-only", "peak_vram_gb": 0, "ram_gb": 0}' "$LA/assetgen/templates/registry-chain.json" > "$LA/assetgen/templates/api-requires.json"
expect_clean api-requires "requires on an API-only template: profile api-only, packs and models left out, PASS"
# a local or pack node needs a profile with a GPU (hardware.json requires.gpu true): api-only excludes any local model
# and stays valid for an API-only graph. local-core has core local nodes only, no pack node.
tmpl local-core '' '{"1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"sd15-checkpoint.safetensors"}},
"2":{"class_type":"SaveImage","inputs":{"images":["7",0],"filename_prefix":"assetgen/local-core"}},
"3":{"class_type":"CLIPTextEncode","inputs":{"text":"{{prompt}}","clip":["1",1]}},
"4":{"class_type":"CLIPTextEncode","inputs":{"text":"blurry","clip":["1",1]}},
"5":{"class_type":"EmptyLatentImage","inputs":{"width":512,"height":512,"batch_size":1}},
"6":{"class_type":"KSampler","inputs":{"model":["1",0],"seed":1,"steps":20,"cfg":7.0,"sampler_name":"euler","scheduler":"karras","positive":["3",0],"negative":["4",0],"latent_image":["5",0],"denoise":1.0}},
"7":{"class_type":"VAEDecode","inputs":{"samples":["6",0],"vae":["1",2]}}}'
lc() { local id=$1; shift; jq "$@" "$LA/assetgen/templates/local-core.json" > "$LA/assetgen/templates/$id.json"; }  # lc ID JQ-ARGS: a variant of local-core
hw_gpu=$(jq -r '[.profiles[] | select(.requires.gpu == true) | .id] | join(", ")' "$HW")
NO_GPU="runs a local model, but profile api-only has no GPU (hardware.json requires.gpu false); declare a local profile ($hw_gpu)"
lc local-core-api '.requires = {"profile": "api-only", "peak_vram_gb": 0, "ram_gb": 0}'
got=$(lint_of local-core-api)
case "$got" in "FAIL "*"node 1 (CheckpointLoaderSimple) $NO_GPU"*) : ;; *) false ;; esac \
  && grep -qF "node 6 (KSampler) $NO_GPU" <<<"$got" && ! grep -qF "node 2 (SaveImage)" <<<"$got" && ! grep -qE "requires\.(profile|peak_vram_gb|ram_gb|packs|models)" <<<"$got" \
  && ok "lint requires: core local nodes on profile api-only FAIL, every local node says the profile has no GPU and lists the local profiles" \
  || no "lint requires: core local nodes on profile api-only" "$got"
lc local-core-4gb --argjson r "$(jq -c '.profiles[] | select(.id == "local-4gb") | .requires | {profile: "local-4gb", peak_vram_gb: .min_vram_gb, ram_gb: .min_ram_gb}' "$HW")" '.requires = $r'
expect_clean local-core-4gb "requires: the same core local nodes on profile local-4gb with fitting numbers PASS"
tmpl api-plain '' "{\"1\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\"}}, $SAVE}"
jq '.requires = {"profile": "api-only", "peak_vram_gb": 0, "ram_gb": 0}' "$LA/assetgen/templates/api-plain.json" > "$LA/assetgen/templates/api-plain-requires.json"
expect_clean api-plain-requires "requires: NineRouterImage + SaveImage on profile api-only (no local or pack node) PASS"
lv local-no-profile 'del(.requires.profile)'
expect_lint local-no-profile FAIL "requires.profile missing" "requires without profile"
lv local-bad-profile '.requires.profile = "local-80gb"'
expect_lint local-bad-profile FAIL "requires.profile 'local-80gb' is not a hardware profile ($hw_profiles" "requires: unknown profile, the ids are listed"
lv local-pack-undeclared '.requires.packs -= ["comfyui_controlnet_aux"]'
expect_lint local-pack-undeclared FAIL "node 7 uses CannyEdgePreprocessor from pack comfyui_controlnet_aux, not declared in requires.packs" "pack node whose pack is missing from requires.packs"
lv local-pack-foreign '.requires.profile = "api-only" | .requires.peak_vram_gb = 0 | .requires.ram_gb = 0'
expect_lint local-pack-foreign FAIL "requires.packs: 'comfyui_ipadapter_plus' is not a pack of profile api-only (it has no packs)" "requires.packs: a pack id that is not of the profile"
expect_lint local-pack-foreign FAIL "node 15 (InspyrenetRembg) $NO_GPU" "requires: a pack node on profile api-only says the profile has no GPU"
lv local-pack-twice '.requires.packs += ["comfyui_controlnet_aux"]'
expect_lint local-pack-twice FAIL "requires.packs lists 'comfyui_controlnet_aux' more than once" "requires.packs: a pack listed twice"
lv local-pack-unused 'del(.workflow["15"]) | .workflow["16"].inputs.images = ["14", 0]'
expect_lint local-pack-unused WARN "requires.packs declares cut-out (BiRefNet or rembg), but no workflow node comes from that pack" "requires.packs: a declared pack no node uses (warning)"
lv local-no-requires 'del(.requires)'
got=$(lint_of local-no-requires)
case "$got" in "FAIL "*"node 2 (CheckpointLoaderSimple) runs a local model: the template needs a requires block (profile, peak_vram_gb, ram_gb, packs, models, offload)"*) : ;; *) false ;; esac \
  && grep -qF "node 15 (InspyrenetRembg) runs a local model" <<<"$got" && grep -qF "node 11 (KSampler) runs a local model" <<<"$got" \
  && ! grep -qF "node 1 (NineRouterImage)" <<<"$got" && ! grep -qF "requires.packs" <<<"$got" \
  && ok "lint local nodes with no requires block: every local and pack node is named, API nodes are not" || no "lint local nodes with no requires block" "$got"
lv local-requires-list '.requires = ["local-8gb"]'
expect_lint local-requires-list FAIL "requires must be an object (profile, peak_vram_gb, ram_gb, packs, models, offload)" "requires that is not an object"
lv local-vram-over '.requires.peak_vram_gb = 7.6'
expect_lint local-vram-over FAIL "requires.peak_vram_gb 7.6 is above min_vram_gb $vram_max of profile local-8gb" "requires.peak_vram_gb 7.6 above profile local-8gb"
lv local-ram-over '.requires.ram_gb = 64'
expect_lint local-ram-over FAIL "requires.ram_gb 64 is above min_ram_gb $ram_max of profile local-8gb" "requires.ram_gb above the profile"
lv local-vram-bool '.requires.peak_vram_gb = true'
expect_lint local-vram-bool FAIL "requires.peak_vram_gb must be a number >= 0" "requires.peak_vram_gb true (a bool is not a number)"
lv local-ram-missing 'del(.requires.ram_gb)'
expect_lint local-ram-missing FAIL "requires.ram_gb missing" "requires without ram_gb"
lv local-model-url --arg u "$scheme://models.example.invalid/sdxl-checkpoint-fp16.safetensors" '.requires.models[0].name = $u'
MODEL_NAME="requires.models[0].name must be a model file name; source links live in docs/hardware.md, never in templates"
expect_lint local-model-url FAIL "$MODEL_NAME" "requires.models name that is a URL: not a file name"
expect_lint local-model-url FAIL "requires contains a URL" "requires.models name that is a URL: the reason names requires"
lv local-model-host '.requires.models[0].name = "huggingface.co/x/y.safetensors"'
expect_lint local-model-host FAIL "$MODEL_NAME" "requires.models name with a host and path (no scheme)"
lv local-model-path '.requires.models[0].name = "C:\\models\\sdxl-checkpoint-fp16.safetensors"'
expect_lint local-model-path FAIL "$MODEL_NAME" "requires.models name that is a local path"
lv local-model-extra '.requires.models[0].source = "see docs"'
expect_lint local-model-extra FAIL "requires.models[0] must be an object with exactly kind, name, size_gb" "requires.models entry with an extra key"
lv local-model-size '.requires.models[1].size_gb = 0'
expect_lint local-model-size FAIL "requires.models[1].size_gb must be a number > 0" "requires.models size_gb 0"
lv local-model-kind '.requires.models[0].kind = "diffusers"'
expect_lint local-model-kind FAIL "requires.models[0].kind 'diffusers' is not a model kind (" "requires.models: unknown model kind"
lv local-credential '.requires.api_key = "placeholder"'
expect_lint local-credential FAIL "requires contains a credential or endpoint key" "credential key inside requires"
lv local-unknown-key '.requires.notes = "fits"'
expect_lint local-unknown-key FAIL "requires.notes: unknown key (a requires block holds only profile, peak_vram_gb, ram_gb, packs, models, offload)" "unknown requires key"
# requires.offload (UNTESTED on RTX 5060: a declaration the graph-style checkpoints rule reads, nothing measured)
lv local-offload-true '.requires.offload = true'
expect_clean local-offload-true "requires.offload true is accepted"
lv local-offload-false '.requires.offload = false'
expect_clean local-offload-false "requires.offload false is accepted"
lv local-offload-string '.requires.offload = "yes"'
expect_lint local-offload-string FAIL "requires.offload must be true or false" "requires.offload that is not a bool (\"yes\")"
lv local-offload-number '.requires.offload = 1'
expect_lint local-offload-number FAIL "requires.offload must be true or false" "requires.offload that is not a bool (1)"
lv local-bad-input '.workflow["11"].inputs.cfg_scale = 7'
expect_lint local-bad-input FAIL "node 11 (KSampler): unknown input cfg_scale" "unknown input on KSampler"
lv local-bad-combo '.workflow["11"].inputs.scheduler = "fastest"'
expect_lint local-bad-combo FAIL "node 11.scheduler: 'fastest' is not one of" "combo value outside KSampler's scheduler options"
lv local-unknown-node '.workflow["12"].class_type = "VAEDecodeTurbo"'
expect_lint local-unknown-node FAIL "unknown node type VAEDecodeTurbo" "unknown node type in a local template"
jq -c '.workflow' "$LOCAL" | sed 's/{{[a-z]*}}/x/g' > "$TMP/local-rendered.json"
jq -c '.["12"].class_type = "VAEDecodeTurbo"' "$TMP/local-rendered.json" > "$TMP/local-rendered-unknown.json"
got=$(AG lint "$TMP/local-rendered.json" --json 2>&1 | jq -r '.results[0] | .state + " " + (.reasons | join("; "))')
got2=$(AG lint "$TMP/local-rendered-unknown.json" --json 2>&1 | jq -r '.results[0] | .state + " " + (.reasons | join("; "))')
[ "$got" = "PASS " ] && case "$got2" in "FAIL "*"unknown node type VAEDecodeTurbo"*) : ;; *) false ;; esac \
  && ok "rendered workflow lint unchanged: local nodes PASS without a requires rule, an unknown node type still FAILs" || no "rendered local workflow lint" "$got
$got2"
# hardware.json missing or malformed: one FAIL reason on a template with requires, never a traceback; a template
# without requires and without local nodes does not read it
printf 'not json\n' > "$TMP/hw-notjson.json"; echo '{"schema": "rpg-factory.assetgen-hardware/1", "profiles": [{"id": "local-8gb"}]}' > "$TMP/hw-shape.json"
jq '.profiles[0].requires.gpu = "no"' "$HW" > "$TMP/hw-gpu.json"  # requires.gpu must be a bool
python3 -B - "$ROOT" "$LA" "$TMP" > "$TMP/o" 2>&1 <<'EOF'
import os, sys
root, authoring, tmp = sys.argv[1:]
sys.path.insert(0, os.path.join(root, "scripts", "assetgen"))
import lint
template = lambda name: os.path.join(authoring, "assetgen", "templates", name + ".json")
for name in ("hw-none.json", "hw-notjson.json", "hw-shape.json", "hw-gpu.json"):
    lint.HARDWARE = os.path.join(tmp, name)
    row = lint.lint_file(template("local-full"), authoring)
    assert row["state"] == "FAIL" and len(row["reasons"]) == 1, (name, row)
    assert row["reasons"][0].startswith("data/hardware.json is missing or malformed ("), (name, row)
    row = lint.lint_file(template("registry-chain"), authoring)
    assert row["state"] == "PASS" and not row["reasons"], (name, row)
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "lint requires: hardware.json missing, not JSON, malformed or with a non-bool requires.gpu is one FAIL reason, no traceback; a template without requires is unaffected" \
  || no "lint requires with a bad hardware.json" "$(cat "$TMP/o")"
LA=$lint_la

expect_lint unknown-node FAIL "unknown node type FluxSampler" "unknown node type"
expect_lint bad-input FAIL "unknown input seed" "unknown input name"
expect_lint missing-link FAIL "link to missing node 9" "link to a missing node"
expect_lint type-mismatch FAIL "expects IMAGE, linked output is STRING" "link type mismatch"
expect_lint bad-combo FAIL "'999x999' is not one of" "combo value outside the node options"
expect_lint undeclared FAIL "placeholder {{mood}} is not a declared param" "undeclared placeholder"
expect_lint unsupported-model WARN "cx/gpt-image-2.5 is unsupported by the 9router gateway" "known unsupported model id (warning)"
expect_lint endpoint FAIL "contains a URL" "URL in a template"
tmpl named-ids '' "{\"gen\": {\"class_type\": \"NineRouterImage\", \"inputs\": {\"user_prompt\": \"{{prompt}}\", \"model\": \"m\", \"size\": \"auto\", \"quality\": \"auto\", \"background\": \"auto\"}}, \"2\": {\"class_type\": \"SaveImage\", \"inputs\": {\"filename_prefix\": \"x\", \"images\": [\"gen\", 0]}}}"
expect_lint named-ids FAIL "node id 'gen': must be digits" "non-numeric node id (workflow.ui.json needs numeric ids)"
AG lint "$LA/assetgen/templates/unsupported-model.json" --authoring "$LA" >/dev/null 2>&1 && ok "warnings alone exit 0" || no "warn exit code"
AG lint "$LA/assetgen/templates/unknown-node.json" --authoring "$LA" >/dev/null 2>&1; [ $? -eq 1 ] && ok "a FAIL exits 1" || no "fail exit code"
echo '{"extends": "icon", "handoff_domain": "audio", "qa": {"size": {"mode": "huge"}, "alpha": "maybe"}, "prompt_rubric": []}' > "$LA/assetgen/purposes/icon.json"
AG lint --authoring "$LA" --json > "$TMP/o" 2>&1
lst() { jq -r --arg p "$1" '[.results[] | select(.path == $p and .check == "assetgen-lint") | .state] | join(",")' "$TMP/o"; }
[ "$(lst core:templates/assetgen/purposes/icon.json)/$(lst game:assetgen/purposes/icon.json)" = "PASS/FAIL" ] \
  && [ "$(lst core:templates/assetgen/workflows/image-generate.json)" = PASS ] \
  && ok "lint blames the game file holding the bad values, not the unchanged core file it extends" \
  || no "lint blame: core $(lst core:templates/assetgen/purposes/icon.json), game $(lst game:assetgen/purposes/icon.json)" "$(jq -c '.results[] | select(.path | test("icon|image-generate"))' "$TMP/o")"
got=$(AG lint "$LA/assetgen/purposes/icon.json" --authoring "$LA" 2>&1)
{ grep -q "handoff_domain 'audio' is not a registry domain" <<<"$got" && grep -q "qa.size.mode must be one of" <<<"$got" \
  && grep -q "qa.alpha must be one of" <<<"$got" && grep -q "prompt_rubric must be a non-empty list" <<<"$got"; } \
  && ok "lint purpose: domain, qa modes, rubric (merged game extension)" || no "purpose lint" "$got"
jq '.["1"].inputs.user_prompt = "{{prompt}}"' "$RUNS/legacy-shape-icon-001/workflow.json" > "$TMP/left.json"
got=$(AG lint "$TMP/left.json" 2>&1); grep -q "unfilled placeholder prompt" <<<"$got" && ok "rendered workflow with a leftover placeholder: FAIL" || no "leftover placeholder lint"
echo '{"schema": "x"}' > "$TMP/other.json"
got=$(AG lint "$TMP/other.json" 2>&1); grep -q "not an asset-gen" <<<"$got" && ok "unrelated JSON: FAIL" || no "unrelated JSON lint"
# malformed nested data and link indices are FAIL rows, never a traceback (review findings 2 and 3)
mal() { echo "$2" > "$LA/assetgen/purposes/$1.json"; }
mal mal-size '{"extends": "icon", "qa": {"size": []}}'
mal mal-qa '{"extends": "icon", "qa": "strict"}'
mal mal-params '{"extends": "icon", "params": ["quality"]}'
mal mal-rubric '{"extends": "icon", "image_rubric": "looks good"}'
mal mal-blank '{"extends": "texture-tileable", "qa": {"tileable": true, "not_blank": 1, "size": {"mode": "min", "expect": 1024}}}'
mal mal-zero '{"extends": "icon", "qa": {"size": {"mode": "aspect", "expect": "1024x0"}}}'
mal mal-zerow '{"extends": "icon", "qa": {"size": {"mode": "min", "expect": "0x1024"}}}'
mal mal-prompt '{"extends": "icon", "prompt": {"must_include": "a sword"}, "default_style": 7}'
mal mal-area '{"extends": "ref-3d-turnaround", "qa": {"size": {"min_area": 1.5}}}'
mal mal-orient '{"extends": "icon", "qa": {"size": {"mode": "orientation", "orientation": "wide"}}}'
mal mal-pixels '{"extends": "concept-2d", "qa": {"size": {"mode": "area", "min_pixels": 0}}}'
mal mal-fit-forbidden '{"extends": "icon", "qa": {"alpha": "forbidden", "size": {"fit": "pad"}}}'
mal mal-fit-any '{"extends": "icon", "qa": {"alpha": "any", "size": {"fit": "pad"}}}'
mal mal-fit-swap '{"extends": "icon", "qa": {"size": {"allow_swap": true}}}'
mal mal-fit-crop '{"extends": "icon", "qa": {"size": {"fit": "crop"}}}'
mal mal-sqtol '{"extends": "icon", "qa": {"size": {"square_tolerance": 1.5}}}'
expect_mal() { # expect_mal ID TEXT LABEL
  local out rc; out=$(AG lint "$LA/assetgen/purposes/$1.json" --authoring "$LA" --json 2>"$TMP/err"); rc=$?
  local got; got=$(jq -r '.results[0] | .state + " " + (.reasons | join("; "))' <<<"$out" 2>/dev/null)
  case "$rc/$got" in "1/FAIL "*"$2"*) grep -q Traceback "$TMP/err" && no "lint $3: traceback" "$(cat "$TMP/err")" || ok "lint $3" ;;
    *) no "lint $3 rc=$rc" "$got
$(cat "$TMP/err")" ;; esac
}
expect_mal mal-fit-forbidden "qa.size.fit pad needs qa.alpha required" "fit pad rejects forbidden alpha"
expect_mal mal-fit-any "qa.size.fit pad needs qa.alpha required" "fit pad rejects any alpha"
expect_mal mal-fit-swap "qa.size.fit pad needs qa.size.allow_swap false" "fit pad rejects allow_swap"
expect_mal mal-fit-crop "qa.size.fit must be one of" "unknown fit value"
expect_mal mal-size "qa.size must be an object" "malformed purpose: qa.size a list -> FAIL row, exit 1, no traceback"
expect_mal mal-qa "qa must be an object" "malformed purpose: qa not an object -> FAIL row"
expect_mal mal-params "params must be an object" "malformed purpose: params not an object -> FAIL row"
expect_mal mal-rubric "image_rubric must be a non-empty list of strings" "malformed purpose: rubric not a list -> FAIL row"
expect_mal mal-blank "qa.not_blank must be an object" "malformed purpose: tileable true, not_blank 1, numeric expect -> FAIL rows"
got=$(AG lint "$LA/assetgen/purposes/mal-blank.json" --authoring "$LA" 2>&1)
grep -q "qa.tileable.max_seam_error must be" <<<"$got" && grep -q "qa.size.expect must be WIDTHxHEIGHT" <<<"$got" \
  && ok "malformed purpose: every malformed qa field is named" || no "mal-blank reasons" "$got"
expect_mal mal-zero "qa.size.expect must be WIDTHxHEIGHT" "malformed purpose: zero height in qa.size.expect -> FAIL row"
expect_mal mal-zerow "qa.size.expect must be WIDTHxHEIGHT" "malformed purpose: zero width in qa.size.expect -> FAIL row"
expect_mal mal-prompt "prompt.must_include must be a list of strings" "malformed purpose: prompt guidance and default_style types -> FAIL row"
expect_mal mal-area "qa.size.min_area must be a number above 0 and at most 1" "malformed purpose: qa.size.min_area above 1 -> FAIL row"
expect_mal mal-orient "qa.size.orientation must be one of" "malformed purpose: unknown qa.size.orientation -> FAIL row"
expect_mal mal-pixels "qa.size.min_pixels must be a number >= 1" "malformed purpose: qa.size.min_pixels 0 -> FAIL row"
expect_mal mal-sqtol "qa.size.square_tolerance must be a number between 0 and 1" "malformed purpose: qa.size.square_tolerance 1.5 -> FAIL row"
python3 -B - "$ROOT" > "$TMP/o" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import runfiles
for bad in ([], "x", None, {"size": []}, {"tileable": True, "not_blank": 1}, {"transparent_corners": "yes"}):
    runfiles.required_checks(bad)
    assert runfiles.qa_errors(bad) or bad is None, bad
assert runfiles.qa_errors(None) == ["qa must be an object"]
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "runfiles.required_checks and qa_errors never raise on malformed qa blocks" || no "required_checks robustness" "$(cat "$TMP/o")"
LINKOK='"1": {"class_type": "NineRouterImage", "inputs": {"user_prompt": "{{prompt}}", "model": "m", "size": "auto", "quality": "auto", "background": "auto"}}'
for idx in -1 -99 5 true; do
  tmpl "link-$idx" '' "{$LINKOK, \"2\": {\"class_type\": \"SaveImage\", \"inputs\": {\"filename_prefix\": \"x\", \"images\": [\"1\", $idx]}}}"
done
expect_lint link--1 FAIL "node 1 has no output -1" "link output index -1: FAIL (negative index never passes bounds)"
expect_lint link--99 FAIL "node 1 has no output -99" "link output index -99: FAIL, no traceback"
expect_lint link-5 FAIL "node 1 has no output 5" "link output index past the node's outputs: FAIL"
expect_lint link-true FAIL "IMAGE input must be a link" "link output index true (bool, not an int): FAIL"
# Full lint PASS count: every core data file plus the two game-layer files that pass (purposes/icon.json,
# templates/image-generate.json). Each template also gets one assetgen-graph-style row: PASS for a template with ui
# groups, WARN for a legacy one (no ui groups); the game image-generate extension has its core template's ui block.
has_groups() { jq -e '(.ui.groups // []) | length > 0' "$1" >/dev/null 2>&1; }
gs_pass=0; gs_warn=0
for f in $(for t in $CORE_TEMPLATES; do echo "$CORE/workflows/$t.json"; done) "$CORE/workflows/image-generate.json"; do
  if has_groups "$f"; then gs_pass=$((gs_pass + 1)); else gs_warn=$((gs_warn + 1)); fi
done
AG lint --authoring "$AUTH" > "$TMP/o" 2>&1 && grep -q "$((n_core + 2 + gs_pass)) PASS, $((3 + gs_warn)) WARN, 0 FAIL" "$TMP/o" && grep -q "^WARN game:assetgen/project.json: no assetgen/project.json" "$TMP/o" \
  && grep -q "^WARN game:assetgen/styles/pixel-art.json: active game style has no usable structured style fields (palette.colors, tone, canvas, outline.edge_darkness): .*no style-\* QA row can grade" "$TMP/o" \
  && grep -q "^WARN game:assetgen/styles/rpg-dark.json: active game style has no usable structured style fields" "$TMP/o" \
  && ok "core + game layer lint: 0 FAIL; WARN no assetgen/project.json and (e2e3 item 9) two active game styles without usable structured style fields" || no "full lint" "$(tail -5 "$TMP/o")"

echo "-- graph style lint: graph-lint verb and assetgen-graph-style lint rows (graphstyle.py)"
# every rule with a passing and a failing case, template and UI form: tests/fixtures/assetgen/graphstyle_selftest.py
python3 -B "$ROOT/tests/fixtures/assetgen/graphstyle_selftest.py" > "$TMP/cs" 2>&1; rc=$?
n_ok=$(grep -c '^ok ' "$TMP/cs"); n_no=$(grep -c '^not ok ' "$TMP/cs")
[ $rc -eq 0 ] && [ "$n_ok" -gt 0 ] && [ "$n_no" -eq 0 ] && ok "graphstyle self-test: $n_ok cases passed" || no "graphstyle self-test rc=$rc ($n_ok ok, $n_no not ok)" "$(grep -v '^ok ' "$TMP/cs")"
GS="$ROOT/tests/fixtures/assetgen/graph-style"
AG graph-lint "$GS/clean.json" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q '^PASS .*tests/fixtures/assetgen/graph-style/clean.json$' "$TMP/o" && grep -qx 'assetgen graph-lint: 1 PASS, 0 WARN, 0 FAIL' "$TMP/o" \
  && ok "graph-lint: the clean fixture template PASSES, exit 0" || no "graph-lint clean rc=$rc" "$(cat "$TMP/o")"
AG graph-lint "$GS/clean.json" --json > "$TMP/o" 2>&1
[ "$(jq -r '.schema + " " + .tool + " " + ([.results[].check] | unique | join(",")) + " " + (.summary | "\(.PASS)/\(.WARN)/\(.FAIL)")' "$TMP/o" 2>&1)" \
  = "rpg-factory.validation/1 assetgen-graph-lint assetgen-graph-style 1/0/0" ] && ok "graph-lint --json: rpg-factory.validation/1, tool assetgen-graph-lint, one assetgen-graph-style row" \
  || no "graph-lint --json" "$(cat "$TMP/o")"
jq 'del(.workflow["4"]._meta)' "$GS/clean.json" > "$TMP/gs-untitled.json"
jq '.workflow["3"].inputs.user_prompt = "{{prompt}}"' "$GS/clean.json" > "$TMP/gs-literal.json"
AG graph-lint "$GS/clean.json" "$TMP/gs-untitled.json" "$TMP/gs-literal.json" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q '^FAIL .*gs-untitled.json: title: node 4 (ImageScale' "$TMP/o" && grep -q '^FAIL .*gs-literal.json: prompt: node 3 (NineRouterImage' "$TMP/o" \
  && grep -qx 'assetgen graph-lint: 1 PASS, 0 WARN, 2 FAIL' "$TMP/o" && ok "graph-lint: a violating template FAILS naming the node (rule id first), exit 1" \
  || no "graph-lint violation rc=$rc" "$(cat "$TMP/o")"
printf 'not json\n' > "$TMP/gs-notjson.json"; echo '{"schema": "x"}' > "$TMP/gs-other.json"; mkdir -p "$TMP/gs-noui-run"
for u in "missing path|$TMP/gs-no-such.json" "non-JSON file|$TMP/gs-notjson.json" "JSON neither template nor frontend workflow|$TMP/gs-other.json" \
         "API-format workflow.json (not a frontend workflow)|$RUNS/golden-icon-001/workflow.json" "unknown flag|$GS/clean.json --bogus" \
         "--run without workflow.ui.json|--run $TMP/gs-noui-run"; do
  # shellcheck disable=SC2086 # the case's arguments are split on purpose (no path holds a space)
  AG graph-lint ${u#*|} > "$TMP/o" 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && ! grep -q '^assetgen graph-lint:' "$TMP/o" && ok "graph-lint usage error exits 2: ${u%%|*}" || no "graph-lint usage ${u%%|*} rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
done
AG graph-lint --json > "$TMP/gl.json" 2>"$TMP/err"; rc=$?
gst() { jq -r --arg p "$1" '[.results[] | select(.path == $p) | .state] | join(",")' "$TMP/gl.json"; }
gs_rows=$(for t in $CORE_TEMPLATES; do printf '%s=%s ' "$t" "$(gst "core:templates/assetgen/workflows/$t.json")"; done)
gs_want=$(for t in $CORE_TEMPLATES; do if has_groups "$CORE/workflows/$t.json"; then printf '%s=PASS ' "$t"; else printf '%s=WARN ' "$t"; fi; done)
[ $rc -eq 0 ] && [ "$gs_rows" = "$gs_want" ] && [ "$(gst core:templates/assetgen/workflows/image-generate.json)/$(gst core:templates/assetgen/workflows/image-edit.json)" = WARN/WARN ] \
  && jq -e '.summary.FAIL == 0 and ([.results[] | select(.path | test("workflows/image-(generate|edit)\\.json$")) | .reasons[0] | startswith("legacy template without a ui block")] | length == 2 and all)' "$TMP/gl.json" >/dev/null \
  && ok "graph-lint without a path: one row per core template; legacy image-generate and image-edit WARN (never FAIL), exit 0" \
  || no "graph-lint core templates rc=$rc: $gs_rows (want $gs_want)" "$(cat "$TMP/err"; jq -c '.results[] | select(.state != "PASS")' "$TMP/gl.json")"
# --profile (UNTESTED on RTX 5060: the profile rules are static checks of a template's declarations against
# data/hardware.json; nothing is generated or measured)
gl_rows() { jq -c '[.results[] | {path, state, reasons}]' "$1"; }
AG graph-lint --profile api-only --json > "$TMP/gl-api.json" 2>"$TMP/err"; rc=$?
# a core template declaring a local requires.profile (a hybrid or local template) FAILS under api-only with a profile:
# reason naming api-only; every other core template keeps its row
local_tpls=$(for t in $CORE_TEMPLATES; do
  jq -e '(.requires.profile // "api-only") != "api-only"' "$CORE/workflows/$t.json" >/dev/null 2>&1 && echo "core:templates/assetgen/workflows/$t.json"; done)
local_json=$(printf '%s\n' "$local_tpls" | jq -R . | jq -sc 'map(select(. != ""))')
gl_api_rows() { jq -c --argjson l "$local_json" '[.results[] | select(.path as $p | $l | index($p) | not) | {path, state, reasons}]' "$1"; }
want_rc=0; [ -n "$local_tpls" ] && want_rc=1
[ $rc -eq $want_rc ] && [ "$(gl_api_rows "$TMP/gl-api.json")" = "$(gl_api_rows "$TMP/gl.json")" ] \
  && ok "graph-lint --profile api-only over the core templates: the same rows as without --profile for every template without a local requires.profile (API-only staged templates keep their result), exit $want_rc" \
  || no "graph-lint --profile api-only core templates rc=$rc (want $want_rc)" "$(cat "$TMP/err"; diff <(gl_api_rows "$TMP/gl.json") <(gl_api_rows "$TMP/gl-api.json"))"
for p in $local_tpls; do
  jq -e --arg p "$p" '[.results[] | select(.path == $p)] | length == 1 and .[0].state == "FAIL"
      and ([.[0].reasons[] | select(startswith("profile:") and contains("api-only"))] | length > 0)' "$TMP/gl-api.json" >/dev/null \
    && ok "graph-lint --profile api-only: local template ${p##*/} FAILS with a profile: reason naming api-only" \
    || no "graph-lint --profile api-only local template ${p##*/}" "$(jq -c --arg p "$p" '.results[] | select(.path == $p)' "$TMP/gl-api.json")"
done
AG graph-lint --profile bogus "$GS/clean.json" > "$TMP/o" 2>"$TMP/err"; rc=$?
hw_ids=$(jq -r '[.profiles[].id] | join(", ")' "$ROOT/scripts/assetgen/data/hardware.json")
[ $rc -eq 2 ] && ! grep -q '^assetgen graph-lint:' "$TMP/o" && grep -qF -- "--profile bogus: one of $hw_ids (data/hardware.json)" "$TMP/err" \
  && ok "graph-lint --profile bogus: usage error naming the hardware profile ids, exit 2" || no "graph-lint --profile bogus rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
AG graph-lint --profile auto "$GS/clean.json" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && ok "graph-lint --profile auto: not a hardware profile id (auto is resolve only), exit 2" || no "graph-lint --profile auto rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
AG graph-lint --profile local-8gb "$GS/hybrid-clean.json" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q '^PASS .*tests/fixtures/assetgen/graph-style/hybrid-clean.json$' "$TMP/o" \
  && ok "graph-lint --profile local-8gb: the clean hybrid template PASSES, exit 0" || no "graph-lint hybrid local-8gb rc=$rc" "$(cat "$TMP/o")"
AG graph-lint --profile api-only "$GS/hybrid-clean.json" --json > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && [ "$(jq -r '.results[0].state' "$TMP/o")" = FAIL ] \
  && jq -e '[.results[0].reasons[] | select(startswith("profile:") and contains("api-only"))] | length > 0' "$TMP/o" >/dev/null \
  && ok "graph-lint --profile api-only: the hybrid template FAILS with a profile: reason naming api-only, exit 1" \
  || no "graph-lint hybrid api-only rc=$rc" "$(cat "$TMP/o")"
AG lint --authoring "$AUTH" --json > "$TMP/o" 2>&1
want_paths=$( { for t in $CORE_TEMPLATES; do echo "core:templates/assetgen/workflows/$t.json"; done
  for f in "$GL"/templates/*.json; do echo "game:assetgen/templates/$(basename "$f")"; done; } | LC_ALL=C sort)
got_paths=$(jq -r '.results[] | select(.check == "assetgen-graph-style") | .path' "$TMP/o" | LC_ALL=C sort)
[ -n "$want_paths" ] && [ "$got_paths" = "$want_paths" ] \
  && [ "$(jq -r '[.results[] | select(.check == "assetgen-graph-style" and (.path | test("image-(generate|edit)\\.json$"))) | .state] | unique | join(",")' "$TMP/o")" = WARN ] \
  && [ "$(jq -r '[.results[] | select(.check == "assetgen-graph-style" and (.path | test("workflows/staged-(icon|ui-element)\\.json$"))) | .state] | sort | join(",")' "$TMP/o")" = PASS,PASS ] \
  && ok "lint: one assetgen-graph-style row per core and game template, staged icon and ui-element PASS, legacy templates WARN" \
  || no "lint graph-style rows" "got: $got_paths
want: $want_paths
$(jq -c '.results[] | select(.check == "assetgen-graph-style")' "$TMP/o")"
[ "$(jq -r '[.results[] | select(.path | test("purposes/|styles/")) | .check] | unique | join(",")' "$TMP/o")" = assetgen-lint ] \
  && ok "lint: purposes and styles get no assetgen-graph-style row" || no "graph-style rows on non-templates" "$(jq -c '.results[] | select(.check == "assetgen-graph-style")' "$TMP/o")"
# a clean template in the game layer: lint and graph-lint PASS it; a run rendered from it passes graph-lint --run
cp "$GS/clean.json" "$GL/templates/graph-clean.json"
AG lint "$GL/templates/graph-clean.json" --authoring "$AUTH" --json > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '[.results[] | .check + "=" + .state] | join(" ")' "$TMP/o")" = "assetgen-lint=PASS assetgen-graph-style=PASS" ] \
  && ok "lint of the clean game template: assetgen-lint PASS, then assetgen-graph-style PASS" || no "lint game clean template rc=$rc" "$(cat "$TMP/o")"
AG graph-lint "$GL/templates/graph-clean.json" --authoring "$AUTH" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qx 'PASS game:assetgen/templates/graph-clean.json' "$TMP/o" && ok "graph-lint of the clean game layer template: PASS" || no "graph-lint game template rc=$rc" "$(cat "$TMP/o")"
mkrun gs-clean-001 icon --style stylized-painterly --authoring "$AUTH" --template graph-clean; gsd="$RUNS/gs-clean-001"
AG render --run "$gsd" --param reference_image=ref.png > "$TMP/o" 2>&1; rc=$?
AG graph-lint --run "$gsd" --authoring "$AUTH" > "$TMP/o2" 2>&1; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && grep -q '^PASS .*gs-clean-001/workflow.ui.json$' "$TMP/o2" \
  && [ "$(jq -r '[.[] | select(.class_type == "SaveImage") | .inputs.filename_prefix] | join(",")' "$gsd/workflow.json")" = assetgen/gs-clean-001-final ] \
  && ok "graph-lint --run on a run rendered from the clean template: PASS (filename_prefix assetgen/<run-id>-final), exit 0" \
  || no "graph-lint --run rc=$rc/$rc2" "$(cat "$TMP/o" "$TMP/o2")"
jq -c '(.nodes[] | select(.id == 4) | .pos) = [5000, 5000]' "$gsd/workflow.ui.json" > "$TMP/gs-moved.ui.json"
AG graph-lint "$TMP/gs-moved.ui.json" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q '^FAIL .*gs-moved.ui.json: .*group: node 4 (ImageScale' "$TMP/o" \
  && ok "graph-lint on a frontend workflow with a node outside every group: FAIL naming the node, exit 1" || no "graph-lint moved node rc=$rc" "$(cat "$TMP/o")"
# a workflow.ui.json that lost extra.assetgen: --run still checks SaveImage suffixes against assetgen/<run dir name>;
# a bare PATH without a run id FAILS as unchecked (the run prefix is unknown), never a silent skip
gsx="$TMP/gs-noextra/gs-clean-001"; mkdir -p "$gsx"
jq -c 'del(.extra.assetgen)' "$gsd/workflow.ui.json" > "$gsx/workflow.ui.json"
AG graph-lint --run "$gsx" > "$TMP/o" 2>&1; rc=$?
AG graph-lint "$gsx/workflow.ui.json" > "$TMP/o2" 2>&1; rc2=$?
jq -c 'del(.extra.assetgen) | (.nodes[] | select(.id == 6) | .widgets_values) = ["assetgen/gs-clean-001"]' "$gsd/workflow.ui.json" > "$gsx/workflow.ui.json"
AG graph-lint --run "$gsx" > "$TMP/o3" 2>&1; rc3=$?
[ "$(jq -r '.extra.assetgen // "gone"' "$gsx/workflow.ui.json")" = gone ] && [ $rc -eq 0 ] \
  && [ $rc2 -eq 1 ] && grep -q '^FAIL .*save-suffix: node 6 (SaveImage.*run prefix is unknown' "$TMP/o2" \
  && [ $rc3 -eq 1 ] && grep -q '^FAIL .*gs-clean-001/workflow.ui.json: .*save-suffix: node 6 (SaveImage.*"assetgen/gs-clean-001" plus an inline suffix' "$TMP/o3" \
  && ! grep -q 'run prefix is unknown' "$TMP/o3" \
  && ok "graph-lint without extra.assetgen: --run checks the suffix against the run (suffixed exit 0, unsuffixed exit 1); a bare PATH FAILS as unchecked" \
  || no "graph-lint lost extra.assetgen rc=$rc/$rc2/$rc3" "$(cat "$TMP/o" "$TMP/o2" "$TMP/o3")"

echo "-- fixture PNGs"
FX="$TMP/png"; mkdir -p "$FX"
cat > "$TMP/mk.py" <<'EOF'
import math, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
out = sys.argv[2]
def save(name, w, h, fn, alpha=True):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes(fn(x, y))
    open(os.path.join(out, name), "wb").write(png.encode(w, h, bytes(px), alpha))
def disc(w, h, bg):
    def f(x, y):
        inside = (x - w / 2) ** 2 + (y - h / 2) ** 2 < (min(w, h) * 0.3) ** 2
        return (200, 40 + (x * 200) // w, 40 + (y * 150) // h, 255) if inside else bg
    return f
save("icon-ok.png", 512, 512, disc(512, 512, (0, 0, 0, 0)))  # 512x512: the icon, sprite and texture floors
save("icon-small.png", 256, 256, disc(256, 256, (0, 0, 0, 0)))  # under every core purpose floor
save("icon-opaque.png", 512, 512, disc(512, 512, (30, 30, 30, 255)), alpha=False)
save("icon-wide.png", 384, 256, disc(384, 256, (0, 0, 0, 0)))
save("preview-64.png", 64, 64, disc(64, 64, (0, 0, 0, 0)))  # the staged icon's 64 px PreviewImage
save("empty.png", 256, 256, lambda x, y: (0, 0, 0, 0))
save("flat.png", 256, 256, lambda x, y: (90, 90, 90, 255), alpha=False)
def wave(x, y):
    v = int(128 + 60 * math.sin(2 * math.pi * x / 256) * math.cos(2 * math.pi * y / 256))
    return (v, v // 2 + 40, 255 - v, 255)
save("tile-ok.png", 512, 512, wave, alpha=False)
save("tile-small.png", 256, 256, wave, alpha=False)
save("tile-bad.png", 512, 512, lambda x, y: (x // 2, x // 2, 128, 255), alpha=False)
row = bytes(c for x in range(1536) for c in (x % 256, (x // 6) % 256, 100))
open(os.path.join(out, "big.png"), "wb").write(png.encode_raw(1536, 1024, 8, 2, [row] * 1024))
for name, w, h in (("strip.png", 2172, 724), ("sheet-small.png", 768, 512), ("sheet-near.png", 1700, 940),
                   ("svc-wide.png", 1672, 941), ("svc-tiny.png", 512, 288)):  # real 9router sizes (e2e2) + too small
    r = bytes(c for x in range(w) for c in (x % 256, (x // 6) % 256, 100))
    open(os.path.join(out, name), "wb").write(png.encode_raw(w, h, 8, 2, [r] * h))
row16 = bytes(b for x in range(512) for b in (x % 256, 0, 255 - x % 256, 0, 60, 0))
def disc_rows(w, h):
    return [bytes(c for x in range(w) for c in ((200, 40 + (x * 200) // w, 40 + (y * 150) // h, 255) if (x - w / 2) ** 2 + (y - h / 2) ** 2 < (w * 0.3) ** 2 else (0, 0, 0, 0)))
            for y in range(h)]
open(os.path.join(out, "svc-small.png"), "wb").write(png.encode_raw(600, 300, 8, 6, disc_rows(600, 300)))
open(os.path.join(out, "svc-fit.png"), "wb").write(png.encode_raw(1536, 1024, 8, 6, disc_rows(1536, 1024)))  # landscape SaveImage
open(os.path.join(out, "svc-square.png"), "wb").write(png.encode_raw(1254, 1254, 8, 6, disc_rows(1254, 1254)))  # real 9router icon size
open(os.path.join(out, "deep16.png"), "wb").write(png.encode_raw(512, 512, 16, 2, [row16] * 512))
# e2e3: real near-square 9router size, a portrait answer to a landscape request, and a prop whose low-alpha edge pixels
# carry a yellow/red speckle in their RGB (barrel-prop-001): body alpha 254, edge alpha 8-31
open(os.path.join(out, "svc-nearsq.png"), "wb").write(png.encode_raw(1322, 1190, 8, 6, disc_rows(1322, 1190)))
r = bytes(c for x in range(1024) for c in (x % 256, (x // 6) % 256, 100))
open(os.path.join(out, "svc-portrait.png"), "wb").write(png.encode_raw(1024, 1536, 8, 2, [r] * 1536))
def fringe(x, y):
    d = math.hypot(x - 256, y - 256)
    if d <= 150:
        return (110 + (x * 80) // 512, 70 + (y * 60) // 512, 40, 254)
    if d <= 156:
        return ((255, 220, 0) if (x + y) % 2 else (255, 40, 0)) + (8 + (x * 7 + y * 3) % 24,)
    return (0, 0, 0, 0)
save("fringe.png", 512, 512, fringe)
data = bytearray(open(os.path.join(out, "icon-ok.png"), "rb").read()); data[60] ^= 0xFF
open(os.path.join(out, "corrupt.png"), "wb").write(bytes(data))
open(os.path.join(out, "not-a-png.png"), "wb").write(b"GIF89a not a png")
EOF
python3 -B "$TMP/mk.py" "$ROOT" "$FX" && [ -f "$FX/corrupt.png" ] && ok "fixture PNGs generated (stdlib encoder)" || no "fixture generation"

echo "-- qa"
qarun() { # qarun NAME PURPOSE PNG...  -> rc in $rc, report in $TMP/q.json
  local name="$1" p="$2"; shift 2
  mkrun "$name" "$p" --style stylized-painterly --template "$(if [ "$p" = image-edit ]; then echo image-edit; else echo image-generate; fi)" || return 1
  AG render --run "$RUNS/$name" >/dev/null 2>&1
  for f in "$@"; do cp "$FX/$f" "$RUNS/$name/outputs/"; done
  AG qa --run "$RUNS/$name" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
}
st() { jq -r --arg c "$1" '[.results[] | select(.check == $c) | .state] | join(",")' "$TMP/q.json"; }
qarun qa-icon-ok-001 icon icon-ok.png
[ $rc -eq 0 ] && [ "$(jq -r .state "$TMP/q.json")" = PASS ] && [ "$(st png-alpha)/$(st png-corners)/$(st png-not-blank)/$(st png-size)" = "PASS/PASS/PASS/PASS" ] \
  && ok "icon: transparent disc passes alpha, corners, not-blank, square aspect" || no "icon ok rc=$rc" "$(jq -c '.results' "$TMP/q.json")"
[ -f "$RUNS/qa-icon-ok-001/qa.json" ] && [ "$(jq -r .schema "$RUNS/qa-icon-ok-001/qa.json")" = rpg-factory.validation/1 ] \
  && [ "$(jq -r '.outputs[0].sha256' "$RUNS/qa-icon-ok-001/qa.json")" = "$(sha256sum "$FX/icon-ok.png" | cut -d' ' -f1)" ] \
  && ok "qa.json written (rpg-factory.validation/1, output sha256)" || no "qa.json"
qb="$RUNS/qa-icon-ok-001"; want_size=$(jq -r '[.[] | select(.class_type == "NineRouterImage")][0].inputs.size' "$qb/workflow.json")
[ "$(jq -r '.purpose_sha256 | test("^[0-9a-f]{64}$")' "$qb/qa.json")/$(jq -r .requested_size "$qb/qa.json")" = "true/$want_size" ] \
  && ok "qa.json binds the purpose content hash and the requested size it graded with" || no "qa.json binding" "$(jq -c '{purpose_sha256, requested_size}' "$qb/qa.json")"
ASSETGEN_NO_PIL=1 AG qa --run "$RUNS/qa-icon-ok-001" --json > "$TMP/q.json"; rc=$?
[ $rc -eq 0 ] && jq -r '.results[] | select(.check == "png-valid") | .reasons[0]' "$TMP/q.json" | grep -q "decoder stdlib" \
  && ok "stdlib decoder path gives the same PASS" || no "stdlib qa rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-icon-opaque-001 icon icon-opaque.png
[ $rc -eq 1 ] && [ "$(st png-alpha)/$(st png-corners)" = "FAIL/FAIL" ] && ok "icon: opaque image fails alpha required and corners" || no "opaque icon rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-icon-wide-001 icon icon-wide.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && ok "icon: 384x256 fails the square aspect" || no "wide icon rc=$rc $(st png-size)"
qarun qa-icon-empty-001 icon empty.png
[ $rc -eq 1 ] && [ "$(st png-not-blank)" = FAIL ] && ok "icon: fully transparent image is blank" || no "empty icon rc=$rc $(st png-not-blank)"
qarun qa-tile-ok-001 texture-tileable tile-ok.png
[ $rc -eq 0 ] && [ "$(st png-tileable)/$(st png-alpha)" = "PASS/PASS" ] && ok "texture: wrapping pattern passes the seam check, opaque" || no "tile ok rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-tile-bad-001 texture-tileable tile-bad.png
[ $rc -eq 1 ] && [ "$(st png-tileable)" = FAIL ] && jq -r '.results[] | select(.check == "png-tileable") | .reasons[0]' "$TMP/q.json" | grep -q "seam error" \
  && ok "texture: horizontal gradient fails the seam check" || no "tile bad rc=$rc $(st png-tileable)"
qarun qa-tile-flat-001 texture-tileable flat.png
[ $rc -eq 1 ] && [ "$(st png-not-blank)" = FAIL ] && ok "texture: uniform color is blank" || no "flat rc=$rc $(st png-not-blank)"
qarun qa-tile-alpha-001 texture-tileable icon-ok.png
[ $rc -eq 1 ] && [ "$(st png-alpha)" = FAIL ] && ok "texture: transparency fails alpha forbidden" || no "alpha forbidden rc=$rc $(st png-alpha)"
qarun qa-concept-big-001 concept-2d big.png
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && ok "concept-2d: 1536x1024 passes size mode area (gateway size drift)" || no "concept big rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-icon-big-001 icon big.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && ok "icon: 1536x1024 returned for a square request fails orientation square" || no "icon big rc=$rc $(st png-size)"
qarun qa-turn-ok-001 ref-3d-turnaround big.png
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && ok "ref-3d-turnaround: 1536x1024 (real e2e size) passes orientation landscape + min pixels" || no "turnaround ok rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-turn-near-001 ref-3d-turnaround sheet-near.png
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && ok "ref-3d-turnaround: 1700x940 passes" || no "turnaround near rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-turn-strip-001 ref-3d-turnaround strip.png
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" \
  | grep -qF "2172x724 is landscape, expected orientation landscape (square within 5%): short side 724 (min 512), area 1572528 px (min 1000000)" \
  && ok "ref-3d-turnaround: the real e2e 2172x724 strip passes orientation landscape, detail names the floors" || no "turnaround strip rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-turn-small-001 ref-3d-turnaround sheet-small.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "area 393216 px (min 1000000)" \
  && ok "ref-3d-turnaround: 768x512 (right orientation, a quarter of the pixels) fails min_pixels" || no "turnaround small rc=$rc" "$(jq -c .results "$TMP/q.json")"
# e2e2: the 9router image service ignores the requested size; every real size passes its core purpose
for req in 1536x1024 1024x1024; do
  sr="$RUNS/qa-svc-concept-${req%%x*}-001"; mkrun "$(basename "$sr")" concept-2d --style stylized-painterly \
    && AG render --run "$sr" --param size=$req >/dev/null 2>&1 && cp "$FX/svc-wide.png" "$sr/outputs/"
  AG qa --run "$sr" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
  [ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && [ "$(jq -r .requested_size "$sr/qa.json")" = "$req" ] \
    && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "1672x941, expected area (any aspect): short side 941 (min 768), area 1573352 px (min 1000000)" \
    && ok "concept-2d: real 1672x941 for a $req request passes png-size (area mode)" || no "concept svc $req rc=$rc" "$(cat "$TMP/err"; jq -c .results "$TMP/q.json")"
done
qarun qa-svc-tiny-001 concept-2d svc-tiny.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "short side 288 (min 768), area 147456 px (min 1000000)" \
  && ok "concept-2d: 512x288 fails png-size (short side and min pixels)" || no "concept tiny rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-svc-turn-tiny-001 ref-3d-turnaround svc-tiny.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && ok "ref-3d-turnaround: 512x288 fails png-size" || no "turnaround tiny rc=$rc $(st png-size)"
qarun qa-svc-icon-001 icon svc-square.png
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "1254x1254 is square, expected orientation square (from 1024x1024)" \
  && ok "icon: real 1254x1254 passes png-size (orientation square)" || no "icon svc rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-svc-icon-wide-001 icon svc-wide.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "1672x941 is landscape, expected orientation square" \
  && ok "icon: 1672x941 fails orientation square" || no "icon svc wide rc=$rc $(st png-size)"
# e2e2 review: every core purpose has a short side and an area floor; 256x256 fails each, the real sizes pass
for pf in icon:icon-small.png sprite-2d:icon-small.png texture-tileable:tile-small.png ui-element:icon-small.png image-edit:icon-small.png; do
  qarun "qa-floor-${pf%%:*}-001" "${pf%%:*}" "${pf#*:}"
  [ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "short side 256 (min 512), area 65536 px (min 262144)"     && ok "${pf%%:*}: 256x256 fails png-size (short side and area floors)" || no "${pf%%:*} floor rc=$rc $(st png-size)" "$(jq -c .results "$TMP/q.json")"
done
for pf in sprite-2d:svc-square.png texture-tileable:svc-square.png ui-element:svc-square.png ui-element:svc-wide.png image-edit:svc-wide.png image-edit:svc-square.png; do
  qarun "qa-real-${pf%%:*}-$(echo "${pf#*:}" | tr -dc a-z)-001" "${pf%%:*}" "${pf#*:}"
  [ "$(st png-size)" = PASS ] && ok "${pf%%:*}: real ${pf#*:} passes png-size" || no "${pf%%:*} real ${pf#*:} $(st png-size)" "$(jq -c .results "$TMP/q.json")"
done
# e2e3 item 7: the service's near-square 1322x1190 (10% longer side) passes the square purposes (square_tolerance 0.15)
for p in sprite-2d icon; do
  qarun "qa-nearsq-$p-001" "$p" svc-nearsq.png
  [ "$(st png-size)" = PASS ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "1322x1190 is square, expected orientation square (from 1024x1024) (square within 15%)" \
    && ok "$p: real 1322x1190 passes png-size (square within 15%)" || no "$p near-square $(st png-size)" "$(jq -c '.results[] | select(.check == "png-size")' "$TMP/q.json")"
done
# portrait 1024x1536 for a 1536x1024 request: ref-3d-turnaround (allow_swap false) fails it, a purpose with allow_swap true passes
qarun qa-swap-turn-001 ref-3d-turnaround svc-portrait.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "1024x1536 is portrait, expected orientation landscape, swap not accepted (qa.size.allow_swap)" \
  && ok "ref-3d-turnaround: a portrait 1024x1536 answer fails (allow_swap false names the swap)" || no "turnaround swap rc=$rc" "$(jq -c '.results[] | select(.check == "png-size")' "$TMP/q.json")"
SWA="$TMP/swap-authoring"; mkdir -p "$SWA/assetgen/purposes"
echo '{"extends": "ref-3d-turnaround", "qa": {"size": {"allow_swap": true}}}' > "$SWA/assetgen/purposes/turn-swap.json"
mkrun qa-swap-ok-001 turn-swap --style stylized-painterly --authoring "$SWA" && AG render --run "$RUNS/qa-swap-ok-001" >/dev/null 2>&1 \
  && cp "$FX/svc-portrait.png" "$RUNS/qa-swap-ok-001/outputs/"
AG qa --run "$RUNS/qa-swap-ok-001" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
[ "$(st png-size)" = PASS ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -qF "swap accepted (qa.size.allow_swap)" \
  && ok "a purpose with qa.size.allow_swap true accepts the portrait 1024x1536 answer" || no "allow_swap true rc=$rc" "$(cat "$TMP/err"; jq -c '.results[] | select(.check == "png-size")' "$TMP/q.json")"
echo '{"extends": "ref-3d-turnaround", "qa": {"size": {"allow_swap": "yes"}}}' > "$SWA/assetgen/purposes/turn-bad.json"
out=$(AG lint "$SWA/assetgen/purposes/turn-bad.json" --authoring "$SWA" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "qa.size.allow_swap must be true or false" <<<"$out" && ok "lint: qa.size.allow_swap must be a boolean" || no "allow_swap lint rc=$rc" "$out"
qarun qa-edit-wide-001 image-edit icon-wide.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && ok "image-edit: 384x256 fails the short side floor (any aspect)" || no "edit wide rc=$rc $(st png-size)"
mkrun qa-exact-001 icon --style pixel-art --authoring "$AUTH"; cp "$FX/icon-ok.png" "$RUNS/qa-exact-001/outputs/"
AG qa --run "$RUNS/qa-exact-001" --json > "$TMP/q.json"; rc=$?
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -q "expected exact 1024x1024" \
  && ok "game override qa.size.mode exact: 512x512 fails exact 1024x1024" || no "exact rc=$rc $(st png-size)"
qarun qa-deep-001 image-edit deep16.png
if has_pil; then
  [ $rc -eq 0 ] && [ "$(st png-valid)" = PASS ] && ok "16-bit PNG decodes with Pillow" || no "16-bit with Pillow rc=$rc $(st png-valid)"
fi
ASSETGEN_NO_PIL=1 AG qa --run "$RUNS/qa-deep-001" --json > "$TMP/q.json"; rc=$?
[ $rc -eq 3 ] && [ "$(st png-valid)" = NOT_AVAILABLE ] && [ "$(jq -r .state "$TMP/q.json")" = NOT_AVAILABLE ] \
  && ok "16-bit PNG without Pillow: NOT_AVAILABLE (exit 3)" || no "NOT_AVAILABLE rc=$rc $(st png-valid)"
qarun qa-corrupt-001 icon corrupt.png not-a-png.png
[ $rc -eq 1 ] && [ "$(st png-valid)" = "FAIL,FAIL" ] && ok "bad CRC and non-PNG bytes: png-valid FAIL" || no "corrupt rc=$rc $(st png-valid)"
mkrun qa-none-001 icon --style pixel-art; AG qa --run "$RUNS/qa-none-001" --json > "$TMP/q.json"; rc=$?
[ $rc -eq 1 ] && [ "$(st png-present)" = FAIL ] && ok "no outputs: FAIL" || no "no outputs rc=$rc"
mkrun qa-malformed-001 mal-size --style stylized-painterly --authoring "$LA" && cp "$FX/icon-ok.png" "$RUNS/qa-malformed-001/outputs/"
AG qa --run "$RUNS/qa-malformed-001" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ "$(st purpose-qa)" = FAIL ] && jq -r '.results[0].reasons[0]' "$TMP/q.json" | grep -q "qa.size must be an object" \
  && [ "$(jq -r '.outputs[0].path' "$TMP/q.json")" = outputs/icon-ok.png ] && ! grep -q Traceback "$TMP/err" \
  && ok "qa: malformed purpose qa block (qa.size a list) is a purpose-qa FAIL row, outputs still hashed, no traceback" \
  || no "malformed qa rc=$rc" "$(cat "$TMP/err"; jq -c . "$TMP/q.json" 2>/dev/null)"
mal zero-req '{"extends": "image-edit", "qa": {"size": {"mode": "aspect"}}}'   # expect defaults to the requested size
for z in 1024x0 0x1024; do
  zr="$RUNS/qa-zero-${z%%x*}-001"; mkrun "$(basename "$zr")" zero-req --style stylized-painterly --authoring "$LA"     && AG render --run "$zr" --param reference_image=ref.png >/dev/null
  jq --arg z "$z" '(.[] | select(.class_type == "NineRouterImage") | .inputs.size) = $z' "$zr/workflow.json" > "$TMP/wf" && mv "$TMP/wf" "$zr/workflow.json"
  cp "$FX/icon-ok.png" "$zr/outputs/"; AG qa --run "$zr" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
  [ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && ! grep -q Traceback "$TMP/err"     && ok "qa: requested size $z (zero dimension) is a png-size FAIL, no traceback" || no "zero size $z rc=$rc" "$(cat "$TMP/err"; jq -c .results "$TMP/q.json" 2>/dev/null)"
done
if has_pil; then
  python3 -B - "$ROOT" "$FX" > "$TMP/o" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
from PIL import Image
src = Image.open(os.path.join(sys.argv[2], "tile-ok.png")).convert("RGBA")
for mode in ("RGBA", "RGB", "L", "LA", "P"):
    path = os.path.join(sys.argv[2], "pil-%s.png" % mode)
    img = src.convert(mode)
    if mode == "P":
        img.info["transparency"] = 0
    img.save(path, optimize=True)
    os.environ["ASSETGEN_NO_PIL"] = "1"; a = png.decode(path)
    del os.environ["ASSETGEN_NO_PIL"]; b = png.decode(path)
    assert (a.width, a.height) == (b.width, b.height) and a.rgba == b.rgba and a.has_alpha == b.has_alpha, mode
    assert a.decoder == "stdlib" and b.decoder == "pillow", mode
print("ok")
EOF
  grep -qx ok "$TMP/o" && ok "stdlib decoder = Pillow on Pillow-written PNGs (all filters; RGBA, RGB, L, LA, P+tRNS)" || no "stdlib vs Pillow" "$(cat "$TMP/o")"
fi

python3 -B - "$ROOT" "$FX" > "$TMP/o" 2>&1 <<'EOF'
import os, struct, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
out = sys.argv[2]
cases = {  # name: (png bytes, expected alpha per pixel)
    "trns-gray": (png.encode_raw(4, 1, 8, 0, [bytes([0, 50, 50, 200])], extra=[(b"tRNS", struct.pack(">H", 50))]), [255, 0, 0, 255]),
    "trns-rgb": (png.encode_raw(3, 1, 8, 2, [bytes([1, 2, 3, 9, 9, 9, 1, 2, 3])], extra=[(b"tRNS", struct.pack(">HHH", 1, 2, 3))]), [0, 255, 0]),
    "trns-pal": (png.encode_raw(3, 1, 8, 3, [bytes([0, 1, 2])], extra=[(b"PLTE", bytes([10, 10, 10, 20, 20, 20, 30, 30, 30])),
                                                                      (b"tRNS", bytes([0, 128]))]), [0, 128, 255]),
}
try:
    import PIL  # noqa: F401
    pil = True
except ImportError:
    pil = False
for name, (data, want) in cases.items():
    path = os.path.join(out, name + ".png")
    open(path, "wb").write(data)
    os.environ["ASSETGEN_NO_PIL"] = "1"; a = png.decode(path)
    assert a.decoder == "stdlib" and list(a.rgba[3::4]) == want and a.has_alpha, (name, list(a.rgba[3::4]))
    del os.environ["ASSETGEN_NO_PIL"]
    if pil:
        b = png.decode(path)
        assert b.decoder == "pillow" and a.rgba == b.rgba and a.has_alpha == b.has_alpha, (name, list(b.rgba[3::4]))
# a gray icon whose background is transparent only through its tRNS key: corners and alpha must see it
rows = [bytes(0 if (x - 256) ** 2 + (y - 256) ** 2 > 180 ** 2 else 40 + (x + y) % 200 for x in range(512)) for y in range(512)]
open(os.path.join(out, "trns-icon.png"), "wb").write(png.encode_raw(512, 512, 8, 0, rows, extra=[(b"tRNS", struct.pack(">H", 0))]))
print("ok pillow" if pil else "ok stdlib-only")
EOF
grep -q "^ok" "$TMP/o" && ok "stdlib decoder applies gray, RGB and palette tRNS ($(cat "$TMP/o"): same pixels as Pillow when present)" \
  || no "tRNS decode" "$(cat "$TMP/o")"
qarun qa-trns-001 icon trns-icon.png
ASSETGEN_NO_PIL=1 AG qa --run "$RUNS/qa-trns-001" --json > "$TMP/q.json"; rc=$?
[ $rc -eq 0 ] && [ "$(st png-alpha)/$(st png-corners)/$(st png-not-blank)" = "PASS/PASS/PASS" ] \
  && ok "QA without Pillow: a gray PNG transparent through tRNS passes alpha required and corners" || no "tRNS qa rc=$rc" "$(jq -c .results "$TMP/q.json")"

echo "-- review-cmd (prints only)"
d="$RUNS/qa-icon-ok-001"
out=$(AG review-cmd --phase prompt --run "$d" 2>&1); rc=$?
{ [ $rc -eq 0 ] && grep -q "^codex exec --sandbox read-only -C $d -o $d/review-prompt.json - <<'ASSETGEN_REVIEW'" <<<"$out" \
  && grep -qF "$(jq -r '.prompt_rubric[0]' "$ROOT/templates/assetgen/purposes/icon.json")" <<<"$out" \
  && grep -q "Test prompt for icon" <<<"$out" && grep -q '"by": "codex"' <<<"$out" && grep -qx "ASSETGEN_REVIEW" <<<"$out" \
  && ! grep -q -- " -i " <<<"$out"; } && ok "prompt review: codex read-only command, rubric, prompt, JSON verdict instruction, no image" || no "prompt review-cmd rc=$rc" "$out"
[ ! -e "$d/review-prompt.json" ] && ok "review-cmd writes nothing" || no "review-cmd wrote a file"
AG review-cmd --phase image --run "$d" --json > "$TMP/rc.json"; rc=$?
{ [ $rc -eq 0 ] && [ "$(jq -r '.argv[0:4] | join(" ")' "$TMP/rc.json")" = "codex exec --sandbox read-only" ] \
  && [ "$(jq -r '.argv | index("-i") as $i | .[$i + 1]' "$TMP/rc.json")" = "$d/outputs/icon-ok.png" ] \
  && [ "$(jq -r '.argv[-1]' "$TMP/rc.json")" = - ] && [ "$(jq -r .verdict "$TMP/rc.json")" = "$d/review-image.json" ] \
  && jq -r .stdin "$TMP/rc.json" | grep -qF "$(jq -r '.image_rubric[0]' "$ROOT/templates/assetgen/purposes/icon.json")" \
  && jq -r .stdin "$TMP/rc.json" | grep -q "Deterministic QA: PASS"; } \
  && ok "image review: -i per output, image rubric, QA summary, verdict file review-image.json" || no "image review-cmd rc=$rc" "$(head -c 600 "$TMP/rc.json")"
AG review-cmd --phase image --run "$RUNS/qa-none-001" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "no outputs" "$TMP/err" && ok "image review without outputs: error" || no "image review no outputs rc=$rc"
got=$(AG review-cmd --phase prompt --run "$d" --codex codex-nightly); grep -q "^codex-nightly exec" <<<"$got" && ok "--codex selects the binary" || no "--codex"
psha=$(python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], encoding='utf-8').read().strip().encode()).hexdigest())" "$d/prompt.md")
{ [ "$(jq -r .binding.prompt_sha256 "$TMP/rc.json")" = "$psha" ] \
  && [ "$(jq -r '.binding.outputs[0].path + " " + .binding.outputs[0].sha256' "$TMP/rc.json")" = "outputs/icon-ok.png $(sha256sum "$d/outputs/icon-ok.png" | cut -d' ' -f1)" ] \
  && jq -r .stdin "$TMP/rc.json" | grep -qF "\"prompt_sha256\": \"$psha\"" && jq -r .stdin "$TMP/rc.json" | grep -q "Copy these binding fields unchanged"; } \
  && ok "image review-cmd binds the verdict: prompt sha256 and output sha256s in the instruction and --json binding" || no "binding" "$(jq -c .binding "$TMP/rc.json")"
python3 -B - "$ROOT" "$d" "$TMP/rc.json" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import runfiles
run, image = sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
spec = json.load(open(os.path.join(run, "spec.json"), encoding="utf-8"))
gen = runfiles.generation_inputs(json.load(open(os.path.join(run, "workflow.json"), encoding="utf-8")), spec,
                                 lambda n: os.path.join(run, "references", n))
img = [n["inputs"] for n in gen["graph"].values() if n["class_type"] == "NineRouterImage"][0]
assert runfiles.workflow_prompts(gen["graph"]) == [open(os.path.join(run, "prompt.md"), encoding="utf-8").read().strip()], gen
assert img["user_prompt"] == ["3", 0] and "size" in img and "quality" in img and gen["references"] == {}, gen
want = runfiles.requirements_sha256(spec, gen)
assert image["binding"]["requirements_sha256"] == want, (image["binding"], want)
assert runfiles.SHA256.match(want) and want != runfiles.requirements_sha256(spec, None)
for bad in (None, [], {"purpose": 3, "params": [1]}, {"purpose": {"sha256": None}, "params": {"x": object()}}):
    assert runfiles.SHA256.match(runfiles.requirements_sha256(bad, {"size": "auto"})), bad
    assert isinstance(runfiles.generation_inputs(bad, bad), dict), bad
print("ok")
EOF
AG review-cmd --phase prompt --run "$d" --json > "$TMP/rcp.json"
python3 -B -c "
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'assetgen'))
import runfiles
spec = json.load(open(os.path.join(sys.argv[2], 'spec.json'), encoding='utf-8'))
print(runfiles.requirements_sha256(spec, None))" "$ROOT" "$d" > "$TMP/req"
{ grep -qx ok "$TMP/o" && [ "$(jq -r .binding.requirements_sha256 "$TMP/rcp.json")" = "$(cat "$TMP/req")" ] \
  && jq -r .stdin "$TMP/rc.json" | grep -qF "\"requirements_sha256\": \"$(jq -r .binding.requirements_sha256 "$TMP/rc.json")\""; } \
  && ok "review-cmd binds requirements_sha256 (prompt: purpose/style/template/params; image: + generation inputs); malformed specs still hash" \
  || no "requirements binding" "$(cat "$TMP/o"; jq -c .binding "$TMP/rcp.json")"

echo "-- review-cmd: absolute paths, true pixel sizes, 2x2 tile preview"
d="$RUNS/qa-icon-ok-001"
(cd "$TMP" && AG review-cmd --phase image --run "game-authoring/assetgen/runs/qa-icon-ok-001" --json) > "$TMP/rc.json" 2>"$TMP/err"; rc=$?
python3 -B - "$TMP/rc.json" "$d" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
cmd, run = json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2]
argv = cmd["argv"]
paths = [argv[i + 1] for i, a in enumerate(argv) if a in ("-C", "-i", "-o")]
assert all(os.path.isabs(p) and "\\" not in p for p in paths), paths
assert os.path.samefile(argv[argv.index("-C") + 1], run), argv
os.chdir(os.path.splitdrive(run)[0] + os.sep)  # another cwd: every path still resolves
assert all(os.path.isfile(argv[i + 1]) for i, a in enumerate(argv) if a == "-i"), argv
assert os.path.samefile(os.path.dirname(cmd["verdict"]), run) and cmd["verdict"].endswith("/review-image.json")
assert cmd["binding"]["outputs"][0]["path"] == "outputs/icon-ok.png" and cmd["tiles"] == [], cmd
print("ok")
EOF
[ $rc -eq 0 ] && grep -qx ok "$TMP/o" && ok "review-cmd with a relative --run from another cwd prints absolute -C, -i and -o paths (binding paths stay run-relative)" \
  || no "review-cmd absolute paths rc=$rc" "$(cat "$TMP/err" "$TMP/o")"
want=$(jq -r '[.[] | select(.class_type == "NineRouterImage")][0].inputs.size' "$d/workflow.json")
jq -r .stdin "$TMP/rc.json" | grep -qxF "True pixel size (PNG header) of outputs/icon-ok.png: 512x512 (requested $want)" \
  && [ -z "$(ls "$d/review" | grep -v '^composite-\(dark\|light\)\.png$')" ] && ok "image review prompt states each output's true pixel size from the PNG header; no tile for a non-tileable purpose (only the alpha composites)" \
  || no "pixel size line" "$(jq -r .stdin "$TMP/rc.json" | grep -n 'pixel size'; ls "$d")"
AG review-cmd --phase image --run "$RUNS/qa-concept-big-001" --json | jq -r .stdin | grep -qF "outputs/big.png: 1536x1024 (requested" \
  && ok "pixel size of a 1536x1024 output (concept-2d)" || no "concept pixel size"
td="$RUNS/qa-tile-ok-001"
AG review-cmd --phase image --run "$td" --json > "$TMP/rt.json" 2>"$TMP/err"; rc=$?
python3 -B - "$ROOT" "$td" "$TMP/rt.json" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
run, cmd = sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
src, tile = png.decode(os.path.join(run, "outputs", "tile-ok.png")), png.decode(os.path.join(run, "review", "tile-2x2.png"))
assert (tile.width, tile.height) == (2 * src.width, 2 * src.height), (tile.width, tile.height)
for x, y in ((0, 0), (17, 200), (255, 255)):
    for dx, dy in ((0, 0), (src.width, 0), (0, src.height), (src.width, src.height)):
        assert tile.pixel(x + dx, y + dy) == src.pixel(x, y), (x, y, dx, dy)
ims = [cmd["argv"][i + 1] for i, a in enumerate(cmd["argv"]) if a == "-i"]
assert len(ims) == 2 and ims[0].endswith("/outputs/tile-ok.png") and ims[1].endswith("/review/tile-2x2.png"), ims
assert os.path.samefile(ims[1], os.path.join(run, "review", "tile-2x2.png"))
assert cmd["tiles"] == ["review/tile-2x2.png"] and [o["path"] for o in cmd["binding"]["outputs"]] == ["outputs/tile-ok.png"], cmd
assert "review/tile-2x2.png is not an output: review-cmd tiled outputs/tile-ok.png 2x2" in cmd["stdin"], cmd["stdin"]
assert "Attached images (one per -i): outputs/tile-ok.png, review/tile-2x2.png" in cmd["stdin"]
print("ok")
EOF
[ $rc -eq 0 ] && grep -qx ok "$TMP/o" && ok "tileable purpose: review/tile-2x2.png (stdlib encode, output repeated 2x2) passed with -i after the output, never in the binding" \
  || no "tile preview rc=$rc" "$(cat "$TMP/err" "$TMP/o")"
sum0=$(sha256sum "$td/review/tile-2x2.png" | cut -d' ' -f1)
AG review-cmd --phase image --run "$td" --no-write --json > "$TMP/rt2.json"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c .argv "$TMP/rt2.json")" = "$(jq -c .argv "$TMP/rt.json")" ] && [ "$(sha256sum "$td/review/tile-2x2.png" | cut -d' ' -f1)" = "$sum0" ] \
  && ok "--no-write uses a current tile (same command)" || no "--no-write current tile rc=$rc"
python3 -B "$ROOT/scripts/factory-cmd.py" assetgen review-cmd --phase image --run "$td" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && ok "factory-cmd assetgen review-cmd image with a current tile: exit 0" || no "factory-cmd current tile rc=$rc" "$(cat "$TMP/err")"
cp "$FX/tile-bad.png" "$td/review/tile-2x2.png"
AG review-cmd --phase image --run "$td" --no-write >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -q "review/tile-2x2.png is missing or stale" "$TMP/err" && cmp -s "$FX/tile-bad.png" "$td/review/tile-2x2.png" \
  && ok "--no-write with a stale tile: exit 2, nothing rewritten" || no "--no-write stale rc=$rc" "$(cat "$TMP/err")"
rm -rf "$td/review"
python3 -B "$ROOT/scripts/factory-cmd.py" assetgen review-cmd --phase image --run "$td" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && [ ! -e "$td/review" ] && grep -q "missing or stale" "$TMP/err" \
  && ok "factory-cmd assetgen review-cmd image passes --no-write: no tile built (exit 2, nothing written)" || no "factory-cmd tile rc=$rc" "$(cat "$TMP/err"; ls "$td")"
mkrun qa-tile-two-001 texture-tileable --style stylized-painterly && AG render --run "$RUNS/qa-tile-two-001" >/dev/null
cp "$FX/tile-ok.png" "$RUNS/qa-tile-two-001/outputs/a.png"; cp "$FX/flat.png" "$RUNS/qa-tile-two-001/outputs/b.png"
AG review-cmd --phase image --run "$RUNS/qa-tile-two-001" --json > "$TMP/rt.json"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c .tiles "$TMP/rt.json")" = '["review/tile-2x2-a.png","review/tile-2x2-b.png"]' ] \
  && [ -f "$RUNS/qa-tile-two-001/review/tile-2x2-a.png" ] && [ -f "$RUNS/qa-tile-two-001/review/tile-2x2-b.png" ] \
  && [ "$(jq '[.argv[] | select(. == "-i")] | length' "$TMP/rt.json")" = 4 ] \
  && ok "several outputs: one tile per output (review/tile-2x2-<stem>.png)" || no "two tiles rc=$rc" "$(jq -c .tiles "$TMP/rt.json")"

echo "-- review prompts: params as rendered, QA owns the deterministic checks, --run takes a run id (e2e2)"
sr="$RUNS/qa-svc-concept-1024-001"  # resolved with size 1536x1024, rendered with --param size=1024x1024
AG review-cmd --phase image --run "$sr" --json 2>"$TMP/err" | jq -r .stdin > "$TMP/ri.txt"
AG review-cmd --phase prompt --run "$sr" --json 2>>"$TMP/err" | jq -r .stdin > "$TMP/rp.txt"
{ [ "$(jq -r .params.size "$sr/spec.json")" = 1536x1024 ] \
  && grep -q "^Requested params (workflow.json): .*size=1024x1024" "$TMP/ri.txt" && grep -q "^Requested params (workflow.json): .*size=1024x1024" "$TMP/rp.txt" \
  && grep -qF "1672x941 (requested 1024x1024)" "$TMP/ri.txt" && ! grep -q "1536x1024" "$TMP/ri.txt" "$TMP/rp.txt"; } \
  && ok "render --param size=1024x1024: both review prompts request only 1024x1024 (params read back from workflow.json, not spec.json)" \
  || no "rendered params in review prompts" "$(cat "$TMP/err"; grep -n "equested" "$TMP/ri.txt" "$TMP/rp.txt")"
AG manifest --run "$sr" >/dev/null 2>"$TMP/err"
mp=$(sed -n '/^---json$/,/^---$/p' "$sr/run.md" | sed '1d;$d' | jq -r '.spec.params.size')
[ "$mp" = 1024x1024 ] && [ "$(jq -r .params.size "$sr/spec.json")" = 1536x1024 ]   && [ "$mp" = "$(jq -r '[.[] | select(.class_type == "NineRouterImage")][0].inputs.size' "$sr/workflow.json")" ]   && ok "manifest after render --param size=1024x1024: run.md spec.params.size is the rendered 1024x1024, not spec.json's 1536x1024"   || no "run.md spec.params from workflow.json: $mp" "$(cat "$TMP/err")"
mkrun review-unrendered-001 concept-2d --style stylized-painterly
AG review-cmd --phase prompt --run "$RUNS/review-unrendered-001" --json | jq -r .stdin \
  | grep -q "^Requested params (spec.json): .*size=1536x1024" && ok "review prompt before render: spec.json params, named as such" || no "unrendered params"
python3 -B - "$ROOT" "$TMP/rparams" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import assetgen
run = sys.argv[2]; os.makedirs(run, exist_ok=True)
spec = {"params": {"size": "1024x1024", "tag": "a", "count": 1, "extra": "kept"},
        "template": {"data": {"params": {"size": {"type": "string"}, "tag": {"type": "string"}, "count": {"type": "int"},
                                         "extra": {"type": "string"}, "prompt": {"type": "string"}},
                              "workflow": {"1": {"class_type": "X", "inputs": {"size": "{{size}}", "count": "{{ count }}",
                                                                              "text": "{{prompt}}", "name": "run/{{tag}}-v{{count}}"}}}}}}
assert assetgen.rendered_params(run, spec) == (spec["params"], "spec.json")
json.dump({"1": {"class_type": "X", "inputs": {"size": "640x480", "count": 3, "text": "the prompt", "name": "run/hero-v3"}},
           "9": {"class_type": "LoadImage", "inputs": {"image": "anchor-a.png"}}}, open(os.path.join(run, "workflow.json"), "w"))
got = assetgen.rendered_params(run, spec)
assert got == ({"size": "640x480", "tag": "hero", "count": 3, "extra": "kept"}, "workflow.json"), got
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "rendered_params: whole placeholders, placeholders inside strings and typed values come from workflow.json; prompt left out" \
  || no "rendered_params" "$(cat "$TMP/o")"
qarun review-qafail-001 concept-2d svc-tiny.png
AG review-cmd --phase image --run "$RUNS/review-qafail-001" --json | jq -r .stdin > "$TMP/ri.txt"
mkrun review-noqa-001 icon --style stylized-painterly && AG render --run "$RUNS/review-noqa-001" >/dev/null \
  && cp "$FX/icon-ok.png" "$RUNS/review-noqa-001/outputs/"
AG review-cmd --phase image --run "$RUNS/review-noqa-001" --json | jq -r .stdin > "$TMP/rn.txt"
{ grep -q "^Deterministic QA: FAIL (FAIL outputs/svc-tiny.png png-size.*); context only, qa.json is graded separately$" "$TMP/ri.txt" \
  && grep -qF "Deterministic checks (size, alpha, corners, tileable, blank) belong to QA only: do not re-grade them." "$TMP/ri.txt" \
  && grep -qF "never fail a rubric item, or report a finding, for a size or another deterministic check" "$TMP/ri.txt" \
  && grep -q "^Deterministic QA: NOT_RUN; it is graded separately (qa.json)$" "$TMP/rn.txt" \
  && grep -qF "belong to QA only: do not re-grade them." "$TMP/rn.txt"; } \
  && ok "image review prompt: QA's verdict (FAIL or NOT_RUN) is context only; the reviewer must not re-grade size, alpha, corners, tileable, blank" \
  || no "QA owns deterministic checks" "$(grep -n "QA\|Deterministic" "$TMP/ri.txt" "$TMP/rn.txt")"
# --run RUN-ID: under <authoring>/assetgen/runs/, with --authoring from anywhere or from inside the authoring repo
d="$RUNS/qa-icon-ok-001"
(cd "$TMP" && AG review-cmd --phase prompt --run qa-icon-ok-001 --authoring "$AUTH" --json) > "$TMP/rid.json" 2>"$TMP/err"; rc1=$?
(cd "$AUTH/assetgen" && AG review-cmd --phase prompt --run qa-icon-ok-001 --json) > "$TMP/rid2.json" 2>>"$TMP/err"; rc2=$?
AG review-cmd --phase prompt --run "$d" --json > "$TMP/rid3.json"
[ $rc1 -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(jq -r .verdict "$TMP/rid.json")" = "$d/review-prompt.json" ] \
  && cmp -s "$TMP/rid.json" "$TMP/rid3.json" && cmp -s "$TMP/rid2.json" "$TMP/rid3.json" \
  && ok "--run qa-icon-ok-001 (a run id): resolved with --authoring from another directory and from inside the authoring repo, same command as the path" \
  || no "--run id rc=$rc1/$rc2" "$(cat "$TMP/err"; jq -r .verdict "$TMP/rid.json")"
(cd "$AUTH" && AG qa --run qa-icon-ok-001 --json) > "$TMP/q.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .run "$TMP/q.json")" = qa-icon-ok-001 ] && [ -f "$d/qa.json" ] && ok "qa --run RUN-ID inside the authoring repo grades that run" \
  || no "qa --run id rc=$rc" "$(cat "$TMP/err")"
(cd "$AUTH" && AG manifest --run nope-icon-001) >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -qF "no run directory at nope-icon-001 or $AUTH/assetgen/runs/nope-icon-001" "$TMP/err" \
  && ok "--run with an unknown run id: exit 2 naming the tried paths" || no "unknown run id rc=$rc" "$(cat "$TMP/err")"
NG="$TMP/not-a-repo"; mkdir -p "$NG"
if ! git -C "$NG" rev-parse --show-toplevel >/dev/null 2>&1; then
  (cd "$NG" && AG qa --run qa-icon-ok-001) >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && grep -q "no --authoring and the current directory is not in a git repository" "$TMP/err" \
    && ok "--run RUN-ID outside any git repository without --authoring: exit 2, says why" || no "run id outside repo rc=$rc" "$(cat "$TMP/err")"
fi
AG embed --run "$TMP/missing/dir-001" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -qF "no run directory at $TMP/missing/dir-001 (" "$TMP/err" && ok "--run with a missing path (not a run id): exit 2 naming the path" \
  || no "missing run path rc=$rc" "$(cat "$TMP/err")"
AG qa --help | grep -q "run id <slug>-NNN" && AG resolve --help | grep -q -- "--verbose" && ok "CLI help documents --run RUN-ID and resolve --verbose" || no "CLI help"

echo "-- embed: the UI workflow as a workflow tEXt chunk of each output"
ed="$RUNS/embed-icon-001"; mkrun embed-icon-001 icon --style stylized-painterly --template image-generate && AG render --run "$ed" >/dev/null
python3 -B - "$ROOT" "$FX/icon-ok.png" "$ed/outputs/comfy.png" <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
data = open(sys.argv[2], "rb").read()  # a ComfyUI-like output: a prompt tEXt chunk (comfy-mcp sends no extra_pnginfo)
open(sys.argv[3], "wb").write(png.add_text(data, "prompt", '{"1": {"class_type": "NineRouterImage"}}'))
EOF
cp "$FX/icon-ok.png" "$ed/outputs/plain.png"; before=$(sha256sum "$ed/outputs/plain.png" | cut -d' ' -f1)
AG embed --run "$ed" --json > "$TMP/e.json" 2>"$TMP/err"; rc=$?
python3 -B - "$ROOT" "$ed" "$FX/icon-ok.png" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
run = sys.argv[2]
ui = json.load(open(os.path.join(run, "workflow.ui.json"), encoding="utf-8"))
orig = png.decode(sys.argv[3])
for name, prompt in (("comfy.png", True), ("plain.png", False)):
    data = open(os.path.join(run, "outputs", name), "rb").read()
    chunks = list(png.chunks(data))  # signature, lengths and every CRC checked
    kinds = [c for c, _ in chunks]
    assert kinds[-1] == b"IEND" and kinds[-2] == b"tEXt" and kinds.count(b"IEND") == 1, kinds
    texts = dict(b.split(b"\0", 1) for c, b in chunks if c == b"tEXt")
    assert json.loads(texts[b"workflow"].decode("latin-1")) == ui, name
    assert (b"prompt" in texts) == prompt and (not prompt or texts[b"prompt"].startswith(b'{"1"')), (name, list(texts))
    img = png.decode(os.path.join(run, "outputs", name))
    assert (img.width, img.height, img.rgba) == (orig.width, orig.height, orig.rgba), name
    try:
        from PIL import Image
    except ImportError:
        continue
    assert json.loads(Image.open(os.path.join(run, "outputs", name)).text["workflow"]) == ui, name  # .text reads past IDAT
print("ok")
EOF
[ $rc -eq 0 ] && grep -qx ok "$TMP/o" && [ "$(jq -r '([.results[].state] | join(",")) + " " + (.summary.embedded | tostring)' "$TMP/e.json")" = "embedded,embedded 2" ] \
  && [ "$(sha256sum "$ed/outputs/plain.png" | cut -d' ' -f1)" != "$before" ] && [ -z "$(ls "$ed/outputs" | grep -v '\.png$')" ] \
  && ok "embed: workflow tEXt chunk = workflow.ui.json right before IEND, CRCs valid, prompt chunk kept, pixels unchanged, no temp file left" \
  || no "embed rc=$rc" "$(cat "$TMP/err" "$TMP/o" "$TMP/e.json")"
sums=$(sha256sum "$ed"/outputs/*.png)
AG embed --run "$ed" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(sha256sum "$ed"/outputs/*.png)" = "$sums" ] && grep -q "0 embedded, 0 replaced, 2 kept, 0 FAIL" "$TMP/o" \
  && ok "embed is idempotent (a PNG that carries a workflow chunk is kept byte for byte)" || no "embed idempotent rc=$rc" "$(cat "$TMP/o")"
# e2e3 item 8: a workflow chunk from an older workflow.ui.json is replaced (one chunk, prompt kept), then kept again
jq -c '.extra.assetgen.note = "re-rendered"' "$ed/workflow.ui.json" > "$TMP/ui" && mv "$TMP/ui" "$ed/workflow.ui.json"
AG embed --run "$ed" > "$TMP/o" 2>&1; rc=$?
python3 -B - "$ROOT" "$ed" > "$TMP/o2" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
run = sys.argv[2]
ui = json.load(open(os.path.join(run, "workflow.ui.json"), encoding="utf-8"))
for name, prompt in (("comfy.png", True), ("plain.png", False)):
    data = open(os.path.join(run, "outputs", name), "rb").read()
    texts = [b.split(b"\0", 1) for c, b in png.chunks(data) if c in png.TEXT_CHUNKS]
    flows = [v for k, v in texts if k == b"workflow"]
    assert len(flows) == 1 and json.loads(flows[0].decode("latin-1")) == ui, name
    assert any(k == b"prompt" for k, _ in texts) == prompt, name
print("ok")
EOF
[ $rc -eq 0 ] && grep -q "^replaced outputs/comfy.png: stale workflow chunk replaced" "$TMP/o" && grep -q "0 embedded, 2 replaced, 0 kept, 0 FAIL" "$TMP/o" && grep -qx ok "$TMP/o2" \
  && ok "embed replaces a stale workflow chunk (one chunk, the current workflow.ui.json, prompt chunk kept)" || no "embed stale rc=$rc" "$(cat "$TMP/o" "$TMP/o2")"
s1=$(sha256sum "$ed"/outputs/*.png); AG embed --run "$ed" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(sha256sum "$ed"/outputs/*.png)" = "$s1" ] && grep -q "0 embedded, 0 replaced, 2 kept, 0 FAIL" "$TMP/o" \
  && ok "embed after a replace is idempotent again (current chunk kept byte for byte)" || no "embed stale idempotent rc=$rc" "$(cat "$TMP/o")"
AG render --run "$ed" >/dev/null && AG embed --run "$ed" >/dev/null
[ "$(sha256sum "$ed"/outputs/*.png)" = "$sums" ] && ok "render again and embed: the outputs are byte for byte what the first embed wrote" || no "embed restore"
AG qa --run "$ed" --json > "$TMP/q.json"; AG review-cmd --phase image --run "$ed" --json > "$TMP/rc.json"
emb=$(sha256sum "$ed/outputs/comfy.png" | cut -d' ' -f1)
[ "$(jq -r '.outputs[] | select(.path == "outputs/comfy.png") | .sha256' "$TMP/q.json")" = "$emb" ] \
  && [ "$(jq -r '.binding.outputs[] | select(.path == "outputs/comfy.png") | .sha256' "$TMP/rc.json")" = "$emb" ] \
  && [ "$(jq -r .state "$TMP/q.json")" = PASS ] \
  && ok "QA (PASS) and the image review binding hash the embedded file" || no "embedded hashes" "$(jq -c .outputs "$TMP/q.json")"
cp "$FX/corrupt.png" "$ed/outputs/zz-corrupt.png"
AG embed --run "$ed" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q "^FAIL outputs/zz-corrupt.png: bad CRC" "$TMP/o" && cmp -s "$FX/corrupt.png" "$ed/outputs/zz-corrupt.png" \
  && ok "embed: a broken PNG is a FAIL row (exit 1) and stays untouched" || no "embed corrupt rc=$rc" "$(cat "$TMP/o")"
rm -f "$ed/outputs/zz-corrupt.png"
mkdir -p "$RUNS/embed-noui-001/outputs"; cp "$FX/icon-ok.png" "$RUNS/embed-noui-001/outputs/"
AG embed --run "$RUNS/embed-noui-001" > /dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "workflow.ui.json" "$TMP/err" && cmp -s "$FX/icon-ok.png" "$RUNS/embed-noui-001/outputs/icon-ok.png" \
  && ok "embed without workflow.ui.json: error, outputs untouched" || no "embed no ui rc=$rc" "$(cat "$TMP/err")"
rm -rf "$RUNS/embed-noui-001"

echo "-- e2e3: edge fringe QA, defringe, composites in the image review"
# item 1: a prop whose low-alpha edge pixels carry a coloured speckle (barrel-prop-001) fails png-edge-fringe;
# defringe (refused while qa.json binds the outputs, --force names what is stale) repairs it and QA passes
fr="$RUNS/fringe-icon-001"; mkrun fringe-icon-001 icon --style stylized-painterly --template image-generate && AG render --run "$fr" >/dev/null
python3 -B - "$ROOT" "$FX/fringe.png" "$fr/outputs/prop.png" <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
open(sys.argv[3], "wb").write(png.add_text(open(sys.argv[2], "rb").read(), "prompt", '{"1": {"class_type": "NineRouterImage"}}'))
EOF
orig=$(sha256sum "$fr/outputs/prop.png" | cut -d' ' -f1)
AG qa --run "$fr" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ "$(st png-edge-fringe)" = FAIL ] && [ "$(jq -r '[.results[] | select(.state == "FAIL") | .check] | join(",")' "$TMP/q.json")" = png-edge-fringe ] \
  && jq -r '.results[] | select(.check == "png-edge-fringe") | .reasons | join(" ")' "$TMP/q.json" | grep -q "run assetgen.py defringe on the run" \
  && ok "qa: a coloured low-alpha fringe is a png-edge-fringe FAIL (the only FAIL row), pointing at defringe" || no "fringe qa rc=$rc" "$(jq -c '.results[] | select(.state != "PASS")' "$TMP/q.json")"
AG defringe --run "$fr" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -qF "qa.json already bind(s) the current outputs" "$TMP/o" && grep -qF "or pass --force and then re-run embed, qa" "$TMP/o" \
  && [ "$(sha256sum "$fr/outputs/prop.png" | cut -d' ' -f1)" = "$orig" ] && [ ! -e "$fr/outputs-raw" ] \
  && ok "defringe refuses outputs qa.json already binds (says to re-run them), nothing written" || no "defringe bound rc=$rc" "$(cat "$TMP/o")"
AG defringe --run "$fr" --alpha-floor 300 > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 2 ] && grep -q "alpha-floor must be from 0 to 224" "$TMP/o" && ok "defringe --alpha-floor out of range: exit 2" || no "alpha floor range rc=$rc" "$(cat "$TMP/o")"
AG defringe --run "$fr" --force --json > "$TMP/d.json" 2>"$TMP/err"; rc=$?
after=$(sha256sum "$fr/outputs/prop.png" | cut -d' ' -f1)
[ $rc -eq 0 ] && [ "$(jq -r '.results[0].state + " " + (.stale | join(","))' "$TMP/d.json")" = "defringed qa.json" ] \
  && [ "$(sha256sum "$fr/outputs-raw/prop.png" | cut -d' ' -f1)" = "$orig" ] && [ "$after" != "$orig" ] \
  && [ "$(jq -r '.schema + " " + (.params.alpha_floor | tostring) + " " + (.params.rings | tostring) + " " + .outputs[0].output + " " + .outputs[0].raw' "$fr/defringe.json")" = "rpg-factory.assetgen-defringe/1 null 8 outputs/prop.png outputs-raw/prop.png" ] \
  && [ "$(jq -r '.outputs[0].before_sha256 + " " + .outputs[0].after_sha256' "$fr/defringe.json")" = "$orig $after" ] \
  && [ "$(jq -r '.outputs[0].stats | (.recoloured == .soft and .soft > 0 and .unreached == 0) | tostring' "$fr/defringe.json")" = true ] \
  && [ -z "$(ls "$fr/outputs" | grep -v '^prop\.png$')" ] \
  && ok "defringe --force: original kept in outputs-raw/, defringe.json records params, before/after sha256 and stats, qa.json named stale" \
  || no "defringe force rc=$rc" "$(cat "$TMP/err" "$TMP/d.json"; cat "$fr/defringe.json")"
python3 -B - "$ROOT" "$fr" > "$TMP/o" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
run = sys.argv[2]
a, b = png.decode(os.path.join(run, "outputs-raw", "prop.png")), png.decode(os.path.join(run, "outputs", "prop.png"))
assert (a.width, a.height) == (b.width, b.height) and a.rgba[3::4] == b.rgba[3::4], "alpha changed"
assert any(a.rgba[i:i + 3] != b.rgba[i:i + 3] for i in range(0, len(a.rgba), 4) if 0 < a.rgba[i + 3] < 32), "no soft pixel recoloured"
assert all(a.rgba[i:i + 4] == b.rgba[i:i + 4] for i in range(0, len(a.rgba), 4) if a.rgba[i + 3] in (0, 254)), "body or background changed"
assert "prompt" in png.text_keywords(open(os.path.join(run, "outputs", "prop.png"), "rb").read()), "prompt chunk lost"
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "defringe: alpha unchanged, soft pixels recoloured, body and background bytes kept, prompt chunk carried over" || no "defringe pixels" "$(cat "$TMP/o")"
AG qa --run "$fr" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(st png-edge-fringe)" = PASS ] && [ "$(jq -r .state "$TMP/q.json")" = PASS ] \
  && ok "qa after defringe: png-edge-fringe PASS, QA PASS" || no "qa after defringe rc=$rc" "$(jq -c '.results[] | select(.state != "PASS")' "$TMP/q.json")"
rm -f "$fr/qa.json"; AG defringe --run "$fr" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q "from the kept original" "$TMP/o" && [ "$(sha256sum "$fr/outputs/prop.png" | cut -d' ' -f1)" = "$after" ] \
  && [ "$(sha256sum "$fr/outputs-raw/prop.png" | cut -d' ' -f1)" = "$orig" ] \
  && ok "defringe again starts from the kept original: same output bytes, original untouched" || no "defringe again rc=$rc" "$(cat "$TMP/o")"
AG defringe --run "$fr" --alpha-floor 16 --json > "$TMP/d.json" 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.outputs[0].stats.floored > 0 and .params.alpha_floor == 16' "$fr/defringe.json")" = true ] \
  && [ "$(jq -r .outputs[0].before_sha256 "$fr/defringe.json")" = "$orig" ] && [ "$(sha256sum "$fr/outputs/prop.png" | cut -d' ' -f1)" != "$after" ] \
  && ok "defringe --alpha-floor 16: from the original again, alpha below 16 floored and recorded" || no "defringe floor rc=$rc" "$(cat "$TMP/d.json")"
AG defringe --run "$fr" > /dev/null 2>&1; AG embed --run "$fr" > /dev/null; AG qa --run "$fr" > /dev/null; AG manifest --run "$fr" > /dev/null
grep -qx -- "- Defringe: 1 output(s), alpha floor none, originals in outputs-raw/ (defringe.json)" "$fr/run.md" \
  && ok "defringe, then embed, qa, manifest: run.md records the defringe step (embed keeps its pixels: not stale)" || no "run.md defringe line" "$(grep -n Defringe "$fr/run.md")"
cp "$fr/outputs-raw/prop.png" "$fr/outputs/prop.png"; AG manifest --run "$fr" > /dev/null
grep -q -- "^- Defringe: .*; STALE, the outputs changed since: outputs/prop.png$" "$fr/run.md" \
  && ok "run.md: a defringe record whose pixels are no longer the outputs is STALE" || no "run.md defringe stale" "$(grep -n Defringe "$fr/run.md")"
AG defringe --run "$fr" > /dev/null 2>&1; AG embed --run "$fr" > /dev/null; AG qa --run "$fr" > /dev/null; AG manifest --run "$fr" > /dev/null
# item 2: the image review attaches the output composited on dark and on light and asks to judge edges on both
AG review-cmd --phase image --run "$fr" --codex codex --json > "$TMP/rc.json" 2>"$TMP/err"; rc=$?
python3 -B - "$ROOT" "$fr" "$TMP/rc.json" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import imaging, png
run, cmd = sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
assert cmd["composites"] == ["review/composite-dark.png", "review/composite-light.png"], cmd["composites"]
ims = [cmd["argv"][i + 1] for i, a in enumerate(cmd["argv"]) if a == "-i"]
assert [i.split("/fringe-icon-001/")[1] for i in ims] == ["outputs/prop.png", "review/composite-dark.png", "review/composite-light.png"], ims
src = png.decode(os.path.join(run, "outputs", "prop.png"))
for bg in ("dark", "light"):
    assert open(os.path.join(run, "review", "composite-%s.png" % bg), "rb").read() == imaging.composite(src, bg), bg
assert [o["path"] for o in cmd["binding"]["outputs"]] == ["outputs/prop.png"], cmd["binding"]
assert cmd["rubric"][-1].startswith("The edges of every output with alpha are clean on both the dark and the light composite"), cmd["rubric"]
assert "review/composite-dark.png is not an output: review-cmd composited outputs/prop.png on a dark background (#202020)" in cmd["stdin"]
assert "review/composite-light.png is not an output: review-cmd composited outputs/prop.png on a light background (#e0e0e0)" in cmd["stdin"]
assert "Attached images (one per -i): outputs/prop.png, review/composite-dark.png, review/composite-light.png" in cmd["stdin"]
assert "%d. The edges of every output with alpha" % len(cmd["rubric"]) in cmd["stdin"]
print("ok")
EOF
[ $rc -eq 0 ] && grep -qx ok "$TMP/o" \
  && ok "review-cmd image: composites on dark and light (imaging.composite) attached after the output, listed, edge rubric item, never in the binding" \
  || no "composites rc=$rc" "$(cat "$TMP/err" "$TMP/o")"
rm -f "$fr/review/composite-light.png"
AG review-cmd --phase image --run "$fr" --no-write > /dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -q "review/composite-light.png is missing or stale and --no-write builds nothing" "$TMP/err" && [ ! -e "$fr/review/composite-light.png" ] \
  && ok "review-cmd --no-write: a missing composite exits 2 and builds nothing" || no "composite no-write rc=$rc" "$(cat "$TMP/err")"
AG review-cmd --phase image --run "$fr" > /dev/null && AG review-cmd --phase image --run "$fr" --no-write --json > "$TMP/rc2.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c .argv "$TMP/rc2.json")" = "$(jq -c .argv "$TMP/rc.json")" ] \
  && ok "review-cmd --no-write uses current composites (same command)" || no "composite no-write current rc=$rc" "$(cat "$TMP/err")"
# final review P3: the documented post-QA fringe repair (SKILL.md step 7) works end to end: embed, qa FAIL, both image
# reviews bind the outputs, defringe without --force is refused, defringe --force names qa.json and both reviews stale,
# then embed, qa PASS and both image reviews again bind the repaired outputs
fx="$RUNS/fringe-repair-001"; mkrun fringe-repair-001 icon --style stylized-painterly --template image-generate && AG render --run "$fx" >/dev/null
cp "$fr/outputs-raw/prop.png" "$fx/outputs/prop.png"; AG embed --run "$fx" > /dev/null
AG qa --run "$fx" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
bound "$fx" image FAIL codex '[{"rubric": 1, "severity": "major", "text": "orange edge speckle"}]' > "$fx/review-image.json"
bound "$fx" image FAIL claude '[{"rubric": 1, "severity": "major", "text": "orange edge speckle"}]' > "$fx/review-image-claude.json"
fxo=$(sha256sum "$fx/outputs/prop.png" | cut -d' ' -f1)
[ $rc -eq 1 ] && [ "$(st png-edge-fringe)" = FAIL ] && [ "$(jq -r '.outputs[0].sha256' "$fx/review-image.json")" = "$fxo" ] \
  && ok "fringe repair: embedded output fails png-edge-fringe, both image reviews bind it" || no "fringe repair qa rc=$rc" "$(cat "$TMP/err")"
AG defringe --run "$fx" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -qF "qa.json, review-image.json, review-image-claude.json already bind(s) the current outputs" "$TMP/o" \
  && grep -qF "pass --force and then re-run embed, qa, review-cmd --phase image (Codex) and Claude's image review (review-image-claude.json)" "$TMP/o" \
  && [ "$(sha256sum "$fx/outputs/prop.png" | cut -d' ' -f1)" = "$fxo" ] && [ ! -e "$fx/outputs-raw" ] && [ ! -e "$fx/defringe.json" ] \
  && ok "fringe repair: defringe without --force is refused after qa and the reviews, naming --force and the records to re-run" || no "fringe repair refuse rc=$rc" "$(cat "$TMP/o")"
AG defringe --run "$fx" --force > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qF "1 defringed, 0 skipped, 0 FAIL" "$TMP/o" \
  && grep -qF "next: embed, qa, review-cmd --phase image (Codex) and Claude's image review (review-image-claude.json)" "$TMP/o" \
  && grep -qx "stale now (re-run them): qa.json, review-image.json, review-image-claude.json" "$TMP/o" \
  && [ "$(sha256sum "$fx/outputs/prop.png" | cut -d' ' -f1)" != "$fxo" ] \
  && ok "fringe repair: defringe --force rewrites the output and lists qa.json and both image reviews as stale" || no "fringe repair force rc=$rc" "$(cat "$TMP/o")"
AG embed --run "$fx" > "$TMP/o" 2>&1; rc1=$?
AG qa --run "$fx" --json > "$TMP/q.json" 2>"$TMP/err"; rc=$?
[ $rc1 -eq 0 ] && [ $rc -eq 0 ] && [ "$(st png-edge-fringe)" = PASS ] && [ "$(jq -r .state "$TMP/q.json")" = PASS ] \
  && ok "fringe repair: embed, then qa again PASS (png-edge-fringe PASS)" || no "fringe repair requa rc=$rc1/$rc" "$(cat "$TMP/o" "$TMP/err")"
fxn=$(sha256sum "$fx/outputs/prop.png" | cut -d' ' -f1)
bound "$fx" image PASS codex > "$fx/review-image.json"; bound "$fx" image PASS claude > "$fx/review-image-claude.json"
[ "$(jq -r '.outputs[0].sha256' "$fx/review-image.json") $(jq -r '.outputs[0].sha256' "$fx/review-image-claude.json")" = "$fxn $fxn" ] \
  && [ "$(jq -r '.outputs[0].sha256' "$fx/qa.json")" = "$fxn" ] \
  && ok "fringe repair: qa.json and both image reviews run again bind the repaired, embedded output" || no "fringe repair rebind" "$(jq -c .outputs "$fx/qa.json" "$fx/review-image.json")"
step7=$(awk '/^7\. /{p=1} /^8\. /{p=0} p' "$ROOT/skills/asset-gen/SKILL.md" | tr '\n' ' ' | tr -s ' ')
case "$step7" in *'`assetgen.py defringe --run <run> --force [--alpha-floor N]`'*'`embed`'*'`qa`'*'both image reviews'*'`review-cmd --phase image`'*'`review-image-claude.json`'*)
  ok "SKILL.md step 7 documents the fringe repair: defringe --run <run> --force, then embed, qa and both image reviews" ;;
  *) no "SKILL.md step 7 fringe repair" "$step7" ;; esac
rm -rf "$fx"
# several outputs: composites per output with alpha (review/composite-<stem>-<bg>.png); an opaque output gets none and defringe skips it
f2="$RUNS/fringe-two-001"; mkrun fringe-two-001 icon --style stylized-painterly --template image-generate && AG render --run "$f2" >/dev/null
cp "$FX/fringe.png" "$f2/outputs/a.png"; cp "$FX/icon-opaque.png" "$f2/outputs/b.png"; ob=$(sha256sum "$f2/outputs/b.png" | cut -d' ' -f1)
AG defringe --run "$f2" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q "^skipped outputs/b.png: no transparent pixels" "$TMP/o" && grep -q "1 defringed, 1 skipped, 0 FAIL" "$TMP/o" \
  && [ "$(sha256sum "$f2/outputs/b.png" | cut -d' ' -f1)" = "$ob" ] && [ ! -e "$f2/outputs-raw/b.png" ] \
  && ok "defringe skips an output without transparent pixels (untouched, no raw copy)" || no "defringe skip rc=$rc" "$(cat "$TMP/o")"
# defringe keeps the colour-management and other safe ancillary chunks (in file order, right after IHDR) and the text
# chunks, never adds sRGB next to iCCP, and drops chunks bound to the old pixel format (PLTE, tRNS, sBIT, bKGD, hIST)
cc="$TMP/colour-chunks"; mkdir -p "$cc"
python3 -B - "$ROOT" "$FX/fringe.png" "$cc" <<'EOF'
import os, struct, sys, zlib
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
src, cc = open(sys.argv[2], "rb").read(), sys.argv[3]
def ihdr_then(data, extra):
    pos = 8 + 12 + 13
    return data[:pos] + b"".join(png.chunk(t, b) for t, b in extra) + data[pos:]
def save(name, data):
    os.makedirs(os.path.join(cc, name, "outputs"), exist_ok=True)
    open(os.path.join(cc, name, "outputs", "prop.png"), "wb").write(data)
chrm = struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)
save("gama", png.add_text(ihdr_then(src, [(b"sBIT", b"\x08\x08\x08\x08"), (b"cHRM", chrm), (b"gAMA", struct.pack(">I", 45455)),
                                          (b"bKGD", b"\x00\x10\x00\x10\x00\x10"), (b"pHYs", struct.pack(">IIB", 2835, 2835, 1))]),
                          "prompt", "p"))
save("iccp", ihdr_then(src, [(b"iCCP", b"icc\0\0" + zlib.compress(b"fake profile"))]))
save("srgb", ihdr_then(src, [(b"sRGB", b"\x00")]))
# 16x16 palette image: transparent background, an 8x8 opaque body and a 1-pixel low-alpha cyan ring around it
rows = [bytes(0 if not (3 <= x <= 12 and 3 <= y <= 12) else 1 if (4 <= x <= 11 and 4 <= y <= 11) else 2 for x in range(16))
        for y in range(16)]
save("palette", png.encode_raw(16, 16, 8, 3, rows, extra=[(b"gAMA", struct.pack(">I", 45455)),
                                                         (b"PLTE", b"\x00\x00\x00\x78\x3c\x14\x00\xc8\xff"),
                                                         (b"bKGD", b"\x00"), (b"hIST", b"\x00\x01\x00\x01\x00\x01"),
                                                         (b"tRNS", b"\x00\xff\x10")]))
EOF
for r in gama iccp srgb palette; do AG defringe --run "$cc/$r" > "$TMP/o-$r" 2>&1 || echo "rc $r" >> "$TMP/o-$r"; done
python3 -B - "$ROOT" "$cc" > "$TMP/o" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
cc = sys.argv[2]
def types(run, where="outputs"):
    data = open(os.path.join(cc, run, where, "prop.png"), "rb").read()
    out = []
    for t, _ in png.chunks(data):  # every CRC checked
        if not (t == b"IDAT" and out and out[-1] == "IDAT"):
            out.append(t.decode())
    img = png.decode(os.path.join(cc, run, where, "prop.png"))
    return out, img
want = {"gama": ["IHDR", "cHRM", "gAMA", "pHYs", "IDAT", "tEXt", "IEND"], "iccp": ["IHDR", "iCCP", "IDAT", "IEND"],
        "srgb": ["IHDR", "sRGB", "IDAT", "IEND"], "palette": ["IHDR", "gAMA", "IDAT", "IEND"]}
for run, chunks in want.items():
    got, img = types(run)
    assert got == chunks, (run, got)
    raw = png.decode(os.path.join(cc, run, "outputs-raw", "prop.png"))
    assert (img.width, img.height) == (raw.width, raw.height) and img.rgba[3::4] == raw.rgba[3::4], run
    assert any(img.rgba[i:i + 3] != raw.rgba[i:i + 3] for i in range(0, len(img.rgba), 4) if 0 < raw.rgba[i + 3] < 255), run
a = open(os.path.join(cc, "gama", "outputs-raw", "prop.png"), "rb").read()
b = open(os.path.join(cc, "gama", "outputs", "prop.png"), "rb").read()
assert [x for x in png.chunks(a) if x[0] in (b"cHRM", b"gAMA", b"pHYs", b"tEXt")] == [x for x in png.chunks(b) if x[0] in (b"cHRM", b"gAMA", b"pHYs", b"tEXt")]
print("ok")
EOF
! grep -q "^rc " "$TMP"/o-* && grep -qx ok "$TMP/o" \
  && ok "defringe keeps cHRM/gAMA/pHYs (file order, after IHDR) and tEXt, iCCP without sRGB, sRGB; drops PLTE/tRNS/sBIT/bKGD/hIST; output decodes, CRCs valid" \
  || no "defringe colour chunks" "$(cat "$TMP"/o-* "$TMP/o")"
# review previews carry the output's colour chunks (all but pHYs, after IHDR): a composite or tile of a gAMA/iCCP/sRGB
# output displays its values as the output does; an untagged output keeps untagged previews (bytes as before)
for r in gama iccp srgb both plain; do
  mkrun "cprev-$r-001" texture-tileable --style stylized-painterly && AG render --run "$RUNS/cprev-$r-001" >/dev/null
done
python3 -B - "$ROOT" "$FX/fringe.png" "$RUNS" <<'EOF'
import os, struct, sys, zlib
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
src, runs = open(sys.argv[2], "rb").read(), sys.argv[3]
def ihdr_then(data, extra):
    pos = 8 + 12 + 13
    return data[:pos] + b"".join(png.chunk(t, b) for t, b in extra) + data[pos:]
chrm = struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)
iccp = (b"iCCP", b"icc\0\0" + zlib.compress(b"fake profile"))
extra = {"gama": [(b"cHRM", chrm), (b"gAMA", struct.pack(">I", 100000)), (b"pHYs", struct.pack(">IIB", 2835, 2835, 1))],
         "iccp": [iccp], "srgb": [(b"sRGB", b"\x00")], "both": [(b"sRGB", b"\x00"), iccp], "plain": []}
for r, chunks in extra.items():
    open(os.path.join(runs, "cprev-%s-001" % r, "outputs", "prop.png"), "wb").write(ihdr_then(src, chunks))
EOF
: > "$TMP/cp-err"
for r in gama iccp srgb both plain; do
  AG review-cmd --phase image --run "$RUNS/cprev-$r-001" --json > "$TMP/cp-$r.json" 2>>"$TMP/cp-err" || echo "rc $r" >> "$TMP/cp-err"
done
python3 -B - "$ROOT" "$RUNS" "$TMP" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import imaging, png
runs, tmp = sys.argv[2], sys.argv[3]
want = {"gama": ["cHRM", "gAMA"], "iccp": ["iCCP"], "srgb": ["sRGB"], "both": ["iCCP"], "plain": []}
for r, colour in want.items():
    run = os.path.join(runs, "cprev-%s-001" % r)
    cmd = json.load(open(os.path.join(tmp, "cp-%s.json" % r), encoding="utf-8"))
    assert cmd["tiles"] == ["review/tile-2x2.png"], (r, cmd["tiles"])
    assert cmd["composites"] == ["review/composite-dark.png", "review/composite-light.png"], (r, cmd["composites"])
    out = open(os.path.join(run, "outputs", "prop.png"), "rb").read()
    src_chunks = {t: b for t, b in png.chunks(out)}
    img = png.decode(os.path.join(run, "outputs", "prop.png"))
    built = {"review/tile-2x2.png": png.tile_2x2(img), "review/composite-dark.png": imaging.composite(img, "dark"),
             "review/composite-light.png": imaging.composite(img, "light")}
    for name, plain in built.items():
        data = open(os.path.join(run, *name.split("/")), "rb").read()
        got = list(png.chunks(data))  # every CRC checked
        types = [t.decode() for t, _ in got]
        assert types[0] == "IHDR" and types[1:1 + len(colour)] == colour and types[1 + len(colour)] == "IDAT", (r, name, types)
        assert "pHYs" not in types and not ("sRGB" in types and "iCCP" in types), (r, name, types)
        assert all(b == src_chunks[t] for t, b in got if t.decode() in colour), (r, name)
        if not colour:
            assert data == plain, (r, name, "untagged preview bytes changed")
        png.decode(os.path.join(run, *name.split("/")))  # Pillow too when installed
        prev, ref = png.decode_stdlib(data), png.decode_stdlib(plain)
        assert (prev.width, prev.height, prev.rgba) == (ref.width, ref.height, ref.rgba), (r, name, "pixels differ")
print("ok")
EOF
AG review-cmd --phase image --run "$RUNS/cprev-gama-001" --no-write --json > "$TMP/cp-nw.json" 2>>"$TMP/cp-err"; rc=$?
[ ! -s "$TMP/cp-err" ] && grep -qx ok "$TMP/o" && [ $rc -eq 0 ] && [ "$(jq -c .argv "$TMP/cp-nw.json")" = "$(jq -c .argv "$TMP/cp-gama.json")" ] \
  && ok "review previews (composites, 2x2 tile) carry the output's cHRM/gAMA, iCCP (never with sRGB) or sRGB after IHDR, no pHYs, CRCs valid, same pixels; untagged output: bytes as before; --no-write accepts them" \
  || no "preview colour chunks rc=$rc" "$(cat "$TMP/cp-err" "$TMP/o")"
# grayscale outputs stay grayscale with their GRAY ICC profile (defringe and review previews), and no RGB(A) PNG ever
# carries a GRAY profile: an iCCP of the other colour space than the written colour type is dropped (sRGB kept then)
gy="$TMP/gray-icc"; mkdir -p "$gy"
for r in ga ga-preview; do mkrun "gicc-$r-001" texture-tileable --style stylized-painterly && AG render --run "$RUNS/gicc-$r-001" >/dev/null; done
python3 -B - "$ROOT" "$FX/fringe.png" "$gy" "$RUNS" <<'EOF'
import os, struct, sys, zlib
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
src, gy, runs = png.decode(sys.argv[2]), sys.argv[3], sys.argv[4]
def icc(space, tags):
    # ICC v2 display profile: 128-byte header, tag table, tag data (4-byte aligned)
    table, data, off = b"", b"", 128 + 4 + 12 * len(tags)
    for sig, body in tags:
        body += b"\0" * (-len(body) % 4)
        table += sig + struct.pack(">II", off + len(data), len(body))
        data += body
    size = off + len(data)
    head = (struct.pack(">I", size) + b"lcms" + struct.pack(">I", 0x02100000) + b"mntr" + space + b"XYZ "
            + struct.pack(">6H", 2026, 1, 1, 0, 0, 0) + b"acsp" + b"\0" * 4 + b"\0" * 4 + b"\0" * 8 + b"\0" * 8
            + struct.pack(">I", 0) + struct.pack(">3i", 0xF6D6, 0x10000, 0xD32D) + b"\0" * 4 + b"\0" * 16 + b"\0" * 28)
    assert len(head) == 128
    return head + struct.pack(">I", len(tags)) + table + data
desc = b"desc" + b"\0" * 4 + struct.pack(">I", 5) + b"gray\0" + struct.pack(">II", 0, 0) + struct.pack(">HB", 0, 0) + b"\0" * 67
wtpt = b"XYZ " + b"\0" * 4 + struct.pack(">3i", 0xF6D6, 0x10000, 0xD32D)
trc = b"curv" + b"\0" * 4 + struct.pack(">IH", 1, 0x0233)
gray_icc = icc(b"GRAY", [(b"desc", desc), (b"wtpt", wtpt), (b"kTRC", trc)])
rgb_icc = icc(b"RGB ", [(b"desc", desc), (b"wtpt", wtpt), (b"rTRC", trc), (b"gTRC", trc), (b"bTRC", trc)])
open(os.path.join(gy, "gray.icc"), "wb").write(gray_icc)
iccp = lambda name, prof: (b"iCCP", name + b"\0\0" + zlib.compress(prof))
w, h, d = src.width, src.height, src.rgba
# gray+alpha (type 4) from the fringe fixture: its red channel as gray, its alpha kept (the soft edge is off-colour)
ga = [bytes(v for x in range(w) for v in (d[(y * w + x) * 4], d[(y * w + x) * 4 + 3])) for y in range(h)]
def save(where, data):
    os.makedirs(os.path.join(where, "outputs"), exist_ok=True)
    open(os.path.join(where, "outputs", "prop.png"), "wb").write(data)
save(os.path.join(gy, "ga"), png.encode_raw(w, h, 8, 4, ga, extra=[iccp(b"gray", gray_icc)]))
save(os.path.join(runs, "gicc-ga-preview-001"), png.encode_raw(w, h, 8, 4, ga, extra=[iccp(b"gray", gray_icc)]))
# gray (type 0) + tRNS key 0: transparent background, gray body
g0 = [bytes(0 if not (4 <= x <= 11 and 4 <= y <= 11) else 200 for x in range(16)) for y in range(16)]
save(os.path.join(gy, "g0"), png.encode_raw(16, 16, 8, 0, g0, extra=[iccp(b"gray", gray_icc), (b"tRNS", b"\x00\x00")]))
# RGBA with an RGB profile: unchanged behaviour (RGBA, the profile kept)
rgba = png.encode(w, h, d)
save(os.path.join(gy, "rgb"), rgba[:33] + png.chunk(*iccp(b"rgb", rgb_icc)) + rgba[33:])
# RGBA forced: an RGBA output with a GRAY profile (invalid input) and sRGB: the GRAY profile is dropped, sRGB kept
save(os.path.join(gy, "forced"), rgba[:33] + png.chunk(b"sRGB", b"\x00") + png.chunk(*iccp(b"gray", gray_icc)) + rgba[33:])
EOF
for r in ga g0 rgb forced; do AG defringe --run "$gy/$r" > "$TMP/o-g-$r" 2>&1 || echo "rc $r" >> "$TMP/o-g-$r"; done
cp "$RUNS/gicc-ga-preview-001/outputs/prop.png" "$RUNS/gicc-ga-001/outputs/prop.png" && AG defringe --run "$RUNS/gicc-ga-001" > "$TMP/o-g-run" 2>&1 \
  && AG review-cmd --phase image --run "$RUNS/gicc-ga-001" --json > "$TMP/gp.json" 2>>"$TMP/o-g-run" \
  && AG review-cmd --phase image --run "$RUNS/gicc-ga-preview-001" --json > "$TMP/gp2.json" 2>>"$TMP/o-g-run" || echo "rc run" >> "$TMP/o-g-run"
python3 -B - "$ROOT" "$gy" "$RUNS" > "$TMP/o" 2>&1 <<'EOF'
import io, os, sys, zlib
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import assetgen, imaging, png
gy, runs = sys.argv[2], sys.argv[3]
gray_icc = open(os.path.join(gy, "gray.icc"), "rb").read()
def info(path):
    data = open(path, "rb").read()
    found = {t: b for t, b in png.chunks(data)}  # every CRC checked
    prof = zlib.decompress(found[b"iCCP"].split(b"\0", 1)[1][1:]) if b"iCCP" in found else None
    return png.header(data)[3], prof, found, data
def pillow_profile(path):
    pil = png.pillow()
    if pil is None:
        return gray_icc
    img = pil.open(path)
    img.load()
    prof = img.info.get("icc_profile")
    try:
        from PIL import ImageCms
        assert ImageCms.ImageCmsProfile(io.BytesIO(prof)).profile.xcolor_space.strip() == "GRAY", path
    except ImportError:
        pass
    return prof
for r, want in (("ga", 4), ("g0", 4)):
    out = os.path.join(gy, r, "outputs", "prop.png")
    ctype, prof, _, _ = info(out)
    assert (ctype, prof) == (want, gray_icc), (r, ctype, prof is not None)
    assert pillow_profile(out) == gray_icc, r
    raw, new = png.decode(os.path.join(gy, r, "outputs-raw", "prop.png")), png.decode(out)
    assert raw.rgba[3::4] == new.rgba[3::4] and png.is_gray(new.rgba), r
ctype, prof, found, _ = info(os.path.join(gy, "rgb", "outputs", "prop.png"))
assert ctype == 6 and png.icc_space(found[b"iCCP"]) == b"RGB ", "rgb"
ctype, prof, found, _ = info(os.path.join(gy, "forced", "outputs", "prop.png"))
assert ctype == 6 and prof is None and found.get(b"sRGB") == b"\x00", ("forced", ctype, sorted(found))
# imaging and colour_chunks directly: a non-gray image never comes out gray, a GRAY profile never goes on RGB(A)
src = png.decode(os.path.join(gy, "rgb", "outputs-raw", "prop.png"))
assert png.header(imaging.defringe(src, gray=True)[0])[3] == 6
assert png.header(imaging.composite(src, "dark", gray=True))[3] == 2 and png.header(png.tile_2x2(src, True))[3] == 6
ga = open(os.path.join(gy, "ga", "outputs-raw", "prop.png"), "rb").read()
for t in (2, 3, 6):
    assert [c for c, _ in assetgen.colour_chunks(ga, t)] == [], t
assert [c for c, _ in assetgen.colour_chunks(ga, 4)] == [b"iCCP"] == [c for c, _ in assetgen.colour_chunks(ga, 0)]
# review previews of a grayscale output (defringed and as fetched): gray composites, gray+alpha tile, the GRAY profile
for run in ("gicc-ga-001", "gicc-ga-preview-001"):
    for name, want in (("composite-dark", 0), ("composite-light", 0), ("tile-2x2", 4)):
        path = os.path.join(runs, run, "review", name + ".png")
        ctype, prof, _, _ = info(path)
        assert (ctype, prof) == (want, gray_icc), (run, name, ctype)
        assert pillow_profile(path) == gray_icc, (run, name)
    img = png.decode(os.path.join(runs, run, "outputs", "prop.png"))
    plain = png.decode_stdlib(open(os.path.join(runs, run, "review", "composite-dark.png"), "rb").read())
    ref = png.decode_stdlib(imaging.composite(img, "dark"))
    assert plain.rgba == ref.rgba, (run, "composite pixels differ from the RGB composite")
print("ok")
EOF
! grep -q "^rc " "$TMP"/o-g-* && grep -qx ok "$TMP/o" \
  && ok "grayscale outputs stay grayscale: defringe writes gray+alpha (type 4, also from gray+tRNS) with the GRAY iCCP Pillow reads, composites gray and tile gray+alpha with it; RGB profile kept on RGBA; a GRAY profile never on RGB(A) (sRGB kept)" \
  || no "gray ICC" "$(cat "$TMP"/o-g-* "$TMP/o")"
# only 8-bit PNGs (IHDR bit depth) are defringed or previewed: a 16-bit gray+tRNS output is skipped with the reason, left
# byte-identical (no outputs-raw copy) and gets no composite or tile (reason on stderr, the image still reviewed);
# an 8-bit gray+alpha output next to it still defringes
bd="$TMP/bit-depth"; mkdir -p "$bd/outputs"
mkrun "bd16-001" texture-tileable --style stylized-painterly && AG render --run "$RUNS/bd16-001" >/dev/null
python3 -B - "$ROOT" "$bd" "$RUNS/bd16-001" "$gy/ga/outputs-raw/prop.png" <<'EOF'
import os, shutil, struct, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
# 3x1 gray (colour type 0), bit depth 16, samples 0, 32768, 65535, tRNS key 0
d16 = png.encode_raw(3, 1, 16, 0, [b"".join(struct.pack(">H", v) for v in (0, 32768, 65535))], extra=[(b"tRNS", b"\x00\x00")])
open(os.path.join(sys.argv[2], "outputs", "d16.png"), "wb").write(d16)
os.makedirs(os.path.join(sys.argv[3], "outputs"), exist_ok=True)
open(os.path.join(sys.argv[3], "outputs", "prop.png"), "wb").write(d16)
shutil.copyfile(sys.argv[4], os.path.join(sys.argv[2], "outputs", "ga8.png"))
EOF
before=$(sha256sum "$bd/outputs/d16.png" | cut -d' ' -f1)
AG defringe --run "$bd" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qx "skipped outputs/d16.png: bit depth 16 not supported: only 8-bit PNGs are defringed" "$TMP/o" \
  && grep -q "^defringed outputs/ga8.png" "$TMP/o" && grep -q "1 defringed, 1 skipped, 0 FAIL" "$TMP/o" \
  && [ "$(sha256sum "$bd/outputs/d16.png" | cut -d' ' -f1)" = "$before" ] && [ ! -e "$bd/outputs-raw/d16.png" ] && [ -f "$bd/outputs-raw/ga8.png" ] \
  && [ "$(jq -c '[.outputs[].output]' "$bd/defringe.json")" = '["outputs/ga8.png"]' ] \
  && ok "defringe: a 16-bit gray+tRNS output is skipped with the bit-depth reason, byte-identical, no raw copy; 8-bit gray+alpha still defringed" \
  || no "defringe bit depth rc=$rc" "$(cat "$TMP/o")"
AG review-cmd --phase image --run "$RUNS/bd16-001" --json > "$TMP/bd.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c '[.composites, .tiles]' "$TMP/bd.json")" = '[[],[]]' ] && [ ! -e "$RUNS/bd16-001/review" ] \
  && grep -q "no composite preview of outputs/prop.png: bit depth 16 not supported: only 8-bit PNGs are previewed" "$TMP/err" \
  && grep -q "no tiled preview of outputs/prop.png: bit depth 16 not supported" "$TMP/err" \
  && [ "$(jq -r '[.argv[] | select(endswith("outputs/prop.png"))] | length' "$TMP/bd.json")" = 1 ] \
  && ok "review-cmd: a 16-bit output gets no composite or tile (reason on stderr), the output itself still goes to the reviewer" \
  || no "review bit depth rc=$rc" "$(cat "$TMP/err"; jq -c '[.composites, .tiles]' "$TMP/bd.json")"
AG review-cmd --phase image --run "$f2" --json > "$TMP/rc.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c .composites "$TMP/rc.json")" = '["review/composite-a-dark.png","review/composite-a-light.png"]' ] \
  && [ "$(jq '[.argv[] | select(. == "-i")] | length' "$TMP/rc.json")" = 4 ] \
  && ok "several outputs: review/composite-<stem>-dark/light.png for the output with alpha only" || no "composites two rc=$rc" "$(cat "$TMP/err"; jq -c .composites "$TMP/rc.json")"
# item 3: approve-record for a person (refusals write nothing), manifest keeps an approved status while nothing bound
# changed; the lifecycle allows a committed proposed run.md -> approved
APA="$TMP/approve-auth"; mkdir -p "$APA/assetgen/runs"; cp -R "$GL/purposes" "$GL/styles" "$GL/templates" "$APA/assetgen/"
cp -R "$fr" "$APA/assetgen/runs/"; ar="$APA/assetgen/runs/fringe-icon-001"
AG manifest --run "$ar" --prompt-author robin > /dev/null
git init -q -b main "$APA" && git -C "$APA" add -A && git -C "$APA" "${G[@]}" commit -qm "proposed run"
md0=$(git -C "$APA" hash-object assetgen/runs/fringe-icon-001/run.md)
AG approve-record --run "$ar" > /dev/null 2>"$TMP/err"; rc1=$?
grep -q "approve-record needs --by NAME" "$TMP/err"; e1=$?
AG approve-record --run "$ar" --by "  " > /dev/null 2>"$TMP/err"; rc2=$?
AG approve-record --run "$ar" --by claude-opus > /dev/null 2>"$TMP/err"; rc3=$?
grep -q "'claude-opus' is an agent or model name; only a person approves a gen-run" "$TMP/err"; e3=$?
AG approve-record --run "$ar" --by Codex > /dev/null 2>"$TMP/err"; rc4=$?
AG approve-record --run "$ar" --by Robin > /dev/null 2>"$TMP/err"; rc5=$?
grep -q "'Robin' is recorded in this run as an agent or reviewer" "$TMP/err"; e5=$?
[ "$rc1/$e1/$rc2/$rc3/$e3/$rc4/$rc5/$e5" = "2/0/2/1/0/1/1/0" ] && [ -z "$(git -C "$APA" status --porcelain)" ] \
  && ok "approve-record refuses without --by (exit 2), an agent or model name and a name the run records as an agent (exit 1); nothing written" \
  || no "approve-record refusals $rc1/$e1/$rc2/$rc3/$e3/$rc4/$rc5/$e5" "$(cat "$TMP/err"; git -C "$APA" status --porcelain)"
# model names of other vendors and agent suffixes are refused the same way (the shared stylelock.is_agent_name guard)
bad=""
for who in gemini-2.5-pro google/gemini-pro llama-3 Mistral-Large o3-mini deepseek-r1 my-agent; do
  AG approve-record --run "$ar" --by "$who" > /dev/null 2>"$TMP/err"; rc=$?
  { [ $rc -eq 1 ] && grep -q "'$who' is an agent or model name" "$TMP/err"; } || bad="$bad $who:$rc"
done
[ -z "$bad" ] && [ "$(git -C "$APA" hash-object assetgen/runs/fringe-icon-001/run.md)" = "$md0" ] && [ ! -d "$APA/approvals" ] \
  && [ -z "$(git -C "$APA" status --porcelain)" ] \
  && ok "approve-record refuses gemini-2.5-pro, google/gemini-pro, llama-3, Mistral-Large, o3-mini, deepseek-r1, my-agent (exit 1); run.md bytes unchanged, no approvals/" \
  || no "approve-record other-vendor refusals:$bad" "$(cat "$TMP/err"; git -C "$APA" status --porcelain)"
AG approve-record --run "$ar" --by Dana --note "edges clean on dark and light" > "$TMP/o" 2>"$TMP/err"; rc=$?
rev=$(git -C "$APA" hash-object assetgen/runs/fringe-icon-001/run.md); recf="$APA/approvals/AGEN-fringe-icon-001/assetgen-approval-$rev.json"
[ $rc -eq 0 ] && [ "$(sed -n '/^---json$/,/^---$/p' "$ar/run.md" | sed '1d;$d' | jq -r .status)" = approved ] && grep -qx -- "- Status: approved (approval is human-only)" "$ar/run.md" \
  && [ "$(jq -r '[.artifact, .gate, .scope, .rev, .by, .note] | join("|")' "$recf")" = "AGEN-fringe-icon-001|assetgen-approval|assetgen|$rev|Dana|edges clean on dark and light" ] \
  && grep -qF "Dana commits run.md and this record together in one SSH-signed commit (git commit -S) whose signer principal is Dana" "$TMP/o" \
  && ok "approve-record --by Dana: run.md approved, record {artifact, gate, scope, rev = git blob of run.md, by, note}, says to commit both SSH-signed as Dana" \
  || no "approve-record rc=$rc" "$(cat "$TMP/err" "$TMP/o"; ls -R "$APA/approvals" 2>&1)"
AG manifest --run "$ar" --prompt-author robin > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q "AGEN-fringe-icon-001 approved$" "$TMP/o" && [ "$(git -C "$APA" hash-object assetgen/runs/fringe-icon-001/run.md)" = "$rev" ] \
  && ok "manifest after approve-record keeps approved and writes the same run.md bytes (the record's rev still binds)" || no "manifest after approval rc=$rc" "$(cat "$TMP/o")"
# a CRLF run.md (a Windows checkout, or an editor that wrote CRLF) approved with approve-record: manifest keeps the
# file's line endings, so a no-op manifest leaves it approved and byte-identical; a real change still resets
APC="$TMP/approve-crlf"; cp -R "$APA" "$APC"; cr="$APC/assetgen/runs/fringe-icon-001"
crlf() { python3 -B -c 'import sys; t = open(sys.argv[1], "rb").read(); sys.exit(0 if t.count(b"\r\n") == t.count(b"\n") > 0 else 1)' "$1"; }
fstatus() { tr -d '\r' < "$1" | sed -n '/^---json$/,/^---$/p' | sed '1d;$d' | jq -r .status; }
python3 -B -c 'import sys; p = sys.argv[1]; t = open(p, "rb").read().replace(b"\r\n", b"\n"); open(p, "wb").write(t.replace(b"\n", b"\r\n"))' "$cr/run.md"
AG approve-record --run "$cr" --by Dana --note "edges clean on dark and light" > /dev/null 2>"$TMP/err"; rc1=$?
b0=$(sha256sum < "$cr/run.md")
AG manifest --run "$cr" --prompt-author robin > "$TMP/o" 2>&1; rc=$?
[ $rc1 -eq 0 ] && [ $rc -eq 0 ] && grep -q "AGEN-fringe-icon-001 approved$" "$TMP/o" && [ "$(sha256sum < "$cr/run.md")" = "$b0" ] \
  && crlf "$cr/run.md" && [ "$(fstatus "$cr/run.md")" = approved ] \
  && ok "manifest on an approved CRLF run.md: still approved, bytes unchanged (CRLF kept, the approval blob still binds)" \
  || no "manifest CRLF approved rc1=$rc1 rc=$rc" "$(cat "$TMP/err" "$TMP/o")"
AG manifest --run "$cr" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qF "AGEN-fringe-icon-001 proposed (approval no longer binds, changed: spec.prompt_author" "$TMP/o" \
  && [ "$(fstatus "$cr/run.md")" = proposed ] && crlf "$cr/run.md" \
  && ok "manifest with a real change on an approved CRLF run.md: proposed, names the field, keeps CRLF" \
  || no "manifest CRLF change rc=$rc" "$(cat "$TMP/o")"
python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$APA" --registry "$ROOT/registry.json" --domain assetgen --json > "$TMP/aq.json" 2>"$TMP/err"
lc=$(jq -r '[.results[] | select(.artifact == "AGEN-fringe-icon-001" and .check == "lifecycle") | .state] | join(",")' "$TMP/aq.json")
ta=$(jq -r '[.results[] | select(.artifact == "AGEN-fringe-icon-001" and .check == "trace-approval") | .state] | join(",")' "$TMP/aq.json")
[ "$lc" = PASS ] && [ "$ta" = HUMAN_REQUIRED ] \
  && ok "artifact-quality: committed proposed run.md approved with approve-record passes the lifecycle (proposed -> approved); the unsigned approval is HUMAN_REQUIRED" \
  || no "lifecycle after approve-record: lifecycle=$lc trace-approval=$ta" "$(cat "$TMP/err"; jq -c '.results[] | select(.artifact == "AGEN-fringe-icon-001" and (.check == "lifecycle" or .check == "trace-approval"))' "$TMP/aq.json")"
AG defringe --run "$ar" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q "run.md is approved: defringe would change the approved outputs" "$TMP/o" && ok "defringe refuses an approved run" || no "defringe approved rc=$rc" "$(cat "$TMP/o")"
AG manifest --run "$ar" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -qF "AGEN-fringe-icon-001 proposed (approval no longer binds, changed: spec.prompt_author; status reset to proposed)" "$TMP/o" \
  && ok "manifest with another --prompt-author on an approved run: the bytes would differ from the approved run.md, so proposed, naming the field" \
  || no "manifest unbound change rc=$rc" "$(cat "$TMP/o")"
AG approve-record --run "$ar" --by Dana > /dev/null 2>"$TMP/err" || no "approve-record again" "$(cat "$TMP/err")"
cp "$FX/icon-ok.png" "$ar/outputs/prop.png"; AG manifest --run "$ar" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q "AGEN-fringe-icon-001 proposed (approval no longer binds, changed: outputs" "$TMP/o" \
  && [ "$(sed -n '/^---json$/,/^---$/p' "$ar/run.md" | sed '1d;$d' | jq -r .status)" = proposed ] \
  && ok "manifest after the approved outputs changed: proposed, names what the approval no longer binds" || no "manifest reset rc=$rc" "$(cat "$TMP/o")"

echo "-- finalize: filter, fit, defringe (alpha purposes only), embed, qa in one fixed order"
# finrun NAME PURPOSE PNG [render args...]: a rendered run with the fixture PNG as its only output
finrun() {
  local name="$1" p="$2" f="$3"; shift 3
  mkrun "$name" "$p" --style stylized-painterly --template "$(if [ "$p" = image-edit ]; then echo image-edit; else echo image-generate; fi)" && AG render --run "$RUNS/$name" "$@" > /dev/null 2>&1 && cp "$FX/$f" "$RUNS/$name/outputs/prop.png"
}
sha() { sha256sum "$1" | cut -d' ' -f1; }
steps() { grep -E '^(filter|fit|defringe|embed|qa) ' "$1" | cut -d' ' -f1 | tr '\n' ' '; }

echo "-- finalize: experimental sheet mode"
for sh_name in sheet-sizes sheet-failures sheet-repeat sheet-cli sheet-discard; do sh_case "$sh_name"; done
echo "-- finalize: pixel-grid detection, palette and opt-in QA"
# A 128x128 pattern enlarged fourfold, with transparent corners and several opaque colours.
python3 -B - "$ROOT" "$TMP" <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
colors = [(220, 40, 30, 255), (30, 180, 70, 255), (40, 60, 220, 255),
          (230, 190, 30, 255), (130, 40, 180, 255), (30, 190, 190, 255)]
rgba = bytearray()
for y in range(512):
    for x in range(512):
        xx, yy = x // 4, y // 4
        rgba.extend(colors[(xx * 7 + yy * 11) % len(colors)] if 16 <= xx < 112 and 16 <= yy < 112 else (0, 0, 0, 0))
open(os.path.join(sys.argv[2], "pg-source.png"), "wb").write(png.encode(512, 512, rgba))
row = b"\x80\x00\x40\x00\xc0\x00" * 512
open(os.path.join(sys.argv[2], "pg-depth.png"), "wb").write(png.encode_raw(512, 512, 16, 2, [row] * 512))
EOF
pg_first="$RUNS/pg-first-001"; pg_second="$RUNS/pg-second-001"
finrun pg-first-001 icon icon-ok.png && finrun pg-second-001 icon icon-ok.png || no "pixel-grid run setup"
cp "$pg_first/workflow.json" "$pg_second/workflow.json"
cp "$pg_first/workflow.ui.json" "$pg_second/workflow.ui.json"
cp "$TMP/pg-source.png" "$pg_first/outputs/prop.png"; cp "$TMP/pg-source.png" "$pg_second/outputs/prop.png"
AG embed --run "$pg_first" > /dev/null 2>"$TMP/pg-err"
AG embed --run "$pg_second" > /dev/null 2>>"$TMP/pg-err"
cp "$pg_first/outputs/prop.png" "$TMP/pg-input.png"
AG finalize --run "$pg_first" --pixel-grid --max-colors 4 --json > "$TMP/pg-first.json" 2>>"$TMP/pg-err"; pg_rc=$?
python3 -B - "$ROOT" "$pg_first/outputs/prop.png" <<'EOF' > "$TMP/pg-pixels"
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
image = png.decode(sys.argv[2])
colors = {tuple(image.rgba[i:i+3]) for i in range(0, len(image.rgba), 4) if image.rgba[i+3]}
print("ok" if (image.width, image.height) == (128, 128) and len(colors) <= 4 else "bad")
EOF
[ "$pg_rc" -eq 0 ] && grep -qx ok "$TMP/pg-pixels" \
  && jq -e '[.steps[] | select(.step == "pixel-grid" and .state == "pixelated")] | length == 1' "$TMP/pg-first.json" >/dev/null \
  && jq -e '.outputs[0].scale == 4 and .outputs[0].source_size == "512x512" and .outputs[0].size == "128x128"' "$pg_first/pixelgrid.json" >/dev/null \
  && cmp -s "$TMP/pg-input.png" "$pg_first/outputs-raw/pixelgrid/prop.png" \
  && jq -e 'any(.results[]; .check == "png-pixel-grid" and .state == "PASS") and any(.results[]; .check == "png-size" and .state == "PASS" and any(.reasons[]; contains("graded at source size 512x512")))' "$pg_first/qa.json" >/dev/null \
  && ok "pixel-grid: scale 4, at most four colours, original preserved and QA grades source size" \
  || no "pixel-grid first rc=$pg_rc" "$(cat "$TMP/pg-err" "$TMP/pg-first.json")"

AG finalize --run "$pg_second" --pixel-grid --max-colors 4 --json > "$TMP/pg-second.json" 2>>"$TMP/pg-err"; pg_rc=$?
[ "$pg_rc" -eq 0 ] && cmp -s "$pg_first/outputs/prop.png" "$pg_second/outputs/prop.png" \
  && [ "$(jq -c .outputs "$pg_first/pixelgrid.json")" = "$(jq -c .outputs "$pg_second/pixelgrid.json")" ] \
  && ok "pixel-grid: fresh runs produce identical bytes and output records" || no "pixel-grid deterministic rc=$pg_rc" "$(cat "$TMP/pg-err" "$TMP/pg-second.json")"
cp "$pg_first/outputs/prop.png" "$TMP/pg-result.png"
AG finalize --run "$pg_first" --pixel-grid --max-colors 4 --json > "$TMP/pg-again.json" 2>>"$TMP/pg-err"; pg_rc=$?
[ "$pg_rc" -eq 0 ] && cmp -s "$TMP/pg-result.png" "$pg_first/outputs/prop.png" \
  && jq -e 'any(.steps[]; .step == "pixel-grid" and .state == "skipped" and any(.results[]; .reason == "already pixel-gridded"))' "$TMP/pg-again.json" >/dev/null \
  && ok "pixel-grid: repeat finalize skips already pixel-gridded output with bytes unchanged" || no "pixel-grid repeat rc=$pg_rc" "$(cat "$TMP/pg-err" "$TMP/pg-again.json")"

pg_deep="$RUNS/pg-deep-001"; finrun pg-deep-001 icon icon-ok.png || no "pixel-grid depth setup"
cp "$TMP/pg-depth.png" "$pg_deep/outputs/prop.png"
AG embed --run "$pg_deep" > /dev/null 2>"$TMP/pg-err"
cp "$pg_deep/outputs/prop.png" "$TMP/pg-deep-input.png"
AG finalize --run "$pg_deep" --pixel-grid --json > "$TMP/pg-deep.json" 2>>"$TMP/pg-err"; pg_rc=$?
cmp -s "$TMP/pg-deep-input.png" "$pg_deep/outputs/prop.png" && [ ! -e "$pg_deep/outputs-raw/pixelgrid/prop.png" ] \
  && jq -e 'any(.outputs[]; .state == "skipped" and (.reason | contains("bit depth 16")))' "$pg_deep/pixelgrid.json" >/dev/null \
  && ok "pixel-grid: 16-bit output skipped with reason, unchanged and no raw copy" || no "pixel-grid depth rc=$pg_rc" "$(cat "$TMP/pg-err" "$TMP/pg-deep.json")"

pg_plain="$RUNS/pg-plain-001"; finrun pg-plain-001 icon icon-ok.png || no "pixel-grid opt-in setup"
AG finalize --run "$pg_plain" --json > "$TMP/pg-plain.json" 2>"$TMP/pg-err"; pg_rc=$?
[ "$pg_rc" -eq 0 ] && [ ! -e "$pg_plain/pixelgrid.json" ] \
  && jq -e '[.steps[].step] == ["filter", "fit", "defringe", "embed", "qa"]' "$TMP/pg-plain.json" >/dev/null \
  && jq -e '[.results[] | select(.check == "png-pixel-grid")] | length == 0' "$pg_plain/qa.json" >/dev/null \
  && ok "finalize without pixel-grid keeps the usual steps and no pixel-grid QA row" || no "pixel-grid opt-in rc=$pg_rc" "$(cat "$TMP/pg-err" "$TMP/pg-plain.json")"

pg_style="$RUNS/pg-style-001"; finrun pg-style-001 icon icon-ok.png || no "pixel-grid style setup"
cp "$TMP/pg-source.png" "$pg_style/outputs/prop.png"
jq '.style.data.palette = {"text":"Two colours", "colors":[{"hex":"#ff0000"},{"hex":"#0000ff"}]}' "$pg_style/spec.json" > "$TMP/pg-spec.json" && cp "$TMP/pg-spec.json" "$pg_style/spec.json"
AG finalize --run "$pg_style" --pixel-grid --max-colors 8 --json > "$TMP/pg-style.json" 2>"$TMP/pg-err"; pg_rc=$?
python3 -B - "$ROOT" "$pg_style/outputs/prop.png" <<'EOF' > "$TMP/pg-style-pixels"
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
image = png.decode(sys.argv[2])
colors = {tuple(image.rgba[i:i+3]) for i in range(0, len(image.rgba), 4) if image.rgba[i+3]}
print("ok" if colors and colors <= {(255, 0, 0), (0, 0, 255)} else "bad")
EOF
[ "$pg_rc" -eq 0 ] && grep -qx ok "$TMP/pg-style-pixels" && jq -e '.params.palette == "style"' "$pg_style/pixelgrid.json" >/dev/null \
  && ok "pixel-grid: structured style palette supplies output colours" || no "pixel-grid style rc=$pg_rc" "$(cat "$TMP/pg-err" "$TMP/pg-style.json")"
AG finalize --run "$pg_plain" --max-colors 4 > "$TMP/pg-invalid" 2>&1; pg_rc=$?
[ "$pg_rc" -eq 2 ] && ok "finalize --max-colors without --pixel-grid exits 2" || no "pixel-grid missing flag rc=$pg_rc" "$(cat "$TMP/pg-invalid")"

# Live fetch_outputs names encode the prompt and index, not the source type. Each run gets its own rendered prefix.
filter_run() {
  local name="$1"
  finrun "$name" icon icon-ok.png || return 1
  FILTER_RUN="$RUNS/$name"
  mv "$FILTER_RUN/outputs/prop.png" "$FILTER_RUN/outputs/937cc86a_000.png"
  cp "$FX/preview-64.png" "$FILTER_RUN/outputs/937cc86a_001.png"
  mkdir -p "$FILTER_RUN/previews"
  local prefix base dir
  prefix=$(jq -r '[.[] | select(.class_type == "SaveImage") | .inputs.filename_prefix][0]' "$FILTER_RUN/workflow.json")
  base=${prefix##*/}; dir=${prefix%/*}
  jq -n --arg prompt '937cc86a-b67c-4a32-ad68-2652a5ef3425' \
    --arg save "http://127.0.0.1:8188/view?filename=${base}_00001_.png&subfolder=${dir}&type=output" \
    --arg temp 'http://127.0.0.1:8188/view?filename=ComfyUI_temp_abcde_00001_.png&subfolder=&type=temp' \
    '{prompt_id: $prompt, urls: [$save, $temp]}' > "$FILTER_RUN/fetch.json"
}
filter_count() { find "$1/outputs" "$1/previews" -type f | wc -l | tr -d ' '; }
filter_files_intact() { [ "$(filter_count "$1")" = "$2" ]; }

filter_run filter-live-icon-001 || no "filter live setup"
fl="$FILTER_RUN"; count=$(filter_count "$fl")
AG budget --run "$fl" --json > "$TMP/filter-budget-before.json" 2>"$TMP/err"; brc=$?
AG finalize --run "$fl" --json > "$TMP/filter-finalize.json" 2>>"$TMP/err"; rc=$?
AG budget --run "$fl" --json > "$TMP/filter-budget-after.json" 2>>"$TMP/err"; arc=$?
AG manifest --run "$fl" > "$TMP/o" 2>>"$TMP/err"; mrc=$?
sed -n '/^---json$/,/^---$/p' "$fl/run.md" | sed '1d;$d' > "$TMP/filter-manifest.json"
[ "$brc/$rc/$arc/$mrc" = 0/0/0/0 ] \
  && jq -e '[.outputs,.previews,.used] == [1,1,1]' "$TMP/filter-budget-before.json" >/dev/null && jq -e '[.outputs,.previews,.used] == [1,1,1]' "$TMP/filter-budget-after.json" >/dev/null \
  && jq -e '.steps[0].step == "filter" and .steps[0].state == "moved" and ([.steps[0].results[] | select(.state == "moved") | .output] == ["outputs/937cc86a_001.png"])' "$TMP/filter-finalize.json" >/dev/null \
  && [ -f "$fl/outputs/937cc86a_000.png" ] && [ ! -e "$fl/outputs/937cc86a_001.png" ] \
  && cmp -s "$FX/preview-64.png" "$fl/previews/937cc86a_001.png" && filter_files_intact "$fl" "$count" \
  && jq -e '([.results[].output] | unique) == ["outputs/937cc86a_000.png"] and ([.outputs[].path] == ["outputs/937cc86a_000.png"])' "$fl/qa.json" >/dev/null \
  && jq -e '[.spec.outputs[].path] == ["outputs/937cc86a_000.png"]' "$TMP/filter-manifest.json" >/dev/null \
  && ok "filter fetch evidence: preview moved, QA and manifest see only the deliverable; budget counts one before and after" \
  || no "filter live rc=$brc/$rc/$arc/$mrc" "$(cat "$TMP/err" "$TMP/filter-finalize.json")"

filter_run filter-job-icon-001 || no "filter job setup"
fj="$FILTER_RUN"; count=$(filter_count "$fj")
jq --slurpfile fetch "$fj/fetch.json" '.prompt_id = $fetch[0].prompt_id | .outputs = $fetch[0].urls' "$ROOT/tests/fixtures/assetgen/comfy-job-state.json" > "$RPG_FACTORY_COMFY_JOBS_DIR/937cc86a-b67c-4a32-ad68-2652a5ef3425.json"
rm "$fj/fetch.json"
AG finalize --run "$fj" --json > "$TMP/filter-finalize.json" 2>"$TMP/err"; rc=$?
[ "$rc" -eq 0 ] && jq -e '.steps[0].state == "moved"' "$TMP/filter-finalize.json" >/dev/null \
  && [ -f "$fj/outputs/937cc86a_000.png" ] && [ ! -e "$fj/outputs/937cc86a_001.png" ] \
  && cmp -s "$FX/preview-64.png" "$fj/previews/937cc86a_001.png" && filter_files_intact "$fj" "$count" \
  && ok "filter falls back to job-state URLs when fetch.json is absent" || no "filter job rc=$rc" "$(cat "$TMP/err" "$TMP/filter-finalize.json")"

# An empty, queued-like job has no output evidence: retain both files with actionable reasons.
filter_run filter-unknown-icon-001 || no "filter unknown setup"
fu="$FILTER_RUN"; count=$(filter_count "$fu")
rm "$fu/fetch.json"
jq '.prompt_id = "937cc86a-b67c-4a32-ad68-2652a5ef3425" | .status = "queued"' "$ROOT/tests/fixtures/assetgen/comfy-job-state.json" > "$RPG_FACTORY_COMFY_JOBS_DIR/937cc86a-b67c-4a32-ad68-2652a5ef3425.json"
AG finalize --run "$fu" --json > "$TMP/filter-finalize.json" 2>"$TMP/err"; rc=$?
[ "$rc" -eq 1 ] && jq -e '.steps[0].state == "skipped" and ([.steps[0].results[] | select(.state == "kept" and (.reason | contains("save the fetch_outputs url_only=true result as <run>/fetch.json")))] | length == 2)' "$TMP/filter-finalize.json" >/dev/null \
  && [ -f "$fu/outputs/937cc86a_000.png" ] && [ -f "$fu/outputs/937cc86a_001.png" ] && filter_files_intact "$fu" "$count" \
  && ok "filter keeps unknown files and explains how to save fetch evidence" || no "filter unknown rc=$rc" "$(cat "$TMP/err" "$TMP/filter-finalize.json")"
rm "$RPG_FACTORY_COMFY_JOBS_DIR/937cc86a-b67c-4a32-ad68-2652a5ef3425.json"

filter_run filter-collision-icon-001 || no "filter collision setup"
fc="$FILTER_RUN"; cp "$FX/icon-ok.png" "$fc/previews/937cc86a_001.png"; count=$(filter_count "$fc")
AG finalize --run "$fc" --json > "$TMP/filter-finalize.json" 2>"$TMP/err"; rc=$?
[ "$rc" -eq 0 ] && jq -e '.steps[0].state == "moved"' "$TMP/filter-finalize.json" >/dev/null \
  && cmp -s "$FX/icon-ok.png" "$fc/previews/937cc86a_001.png" && cmp -s "$FX/preview-64.png" "$fc/previews/937cc86a_001.1.png" \
  && [ ! -e "$fc/outputs/937cc86a_001.png" ] && filter_files_intact "$fc" "$count" \
  && ok "filter preserves a collision and moves the preview to a numbered name" || no "filter collision rc=$rc" "$(cat "$TMP/err" "$TMP/filter-finalize.json")"

filter_run filter-allpreview-icon-001 || no "filter all preview setup"
fp="$FILTER_RUN"; cp "$FX/preview-64.png" "$fp/outputs/937cc86a_000.png"
jq '.urls[0] = .urls[1]' "$fp/fetch.json" > "$TMP/filter-fetch.json" && mv "$TMP/filter-fetch.json" "$fp/fetch.json"
count=$(filter_count "$fp")
AG finalize --run "$fp" --json > "$TMP/filter-finalize.json" 2>"$TMP/err"; rc=$?
[ "$rc" -eq 1 ] && jq -e '.failed_at == "filter" and .steps[0].state == "FAIL"' "$TMP/filter-finalize.json" >/dev/null \
  && [ -f "$fp/outputs/937cc86a_000.png" ] && [ -f "$fp/outputs/937cc86a_001.png" ] \
  && [ ! -e "$fp/previews/937cc86a_000.png" ] && [ ! -e "$fp/previews/937cc86a_001.png" ] && filter_files_intact "$fp" "$count" \
  && ok "filter fails before moving any file when all outputs are previews" || no "filter all preview rc=$rc" "$(cat "$TMP/err" "$TMP/filter-finalize.json")"

for malformed in invalid missing-urls; do
  filter_run "filter-${malformed}-icon-001" || no "filter malformed setup: $malformed"
  fmrun="$FILTER_RUN"; count=$(filter_count "$fmrun")
  if [ "$malformed" = invalid ]; then printf 'not json\n' > "$fmrun/fetch.json"; else printf '{"prompt_id":"937cc86a-b67c-4a32-ad68-2652a5ef3425"}\n' > "$fmrun/fetch.json"; fi
  AG finalize --run "$fmrun" --json > "$TMP/filter-finalize.json" 2>"$TMP/err"; rc=$?
  [ "$rc" -eq 1 ] && jq -e '.steps[0].state == "skipped" and ([.steps[0].results[] | select(.state == "kept")] | length == 2)' "$TMP/filter-finalize.json" >/dev/null \
    && [ -f "$fmrun/outputs/937cc86a_000.png" ] && [ -f "$fmrun/outputs/937cc86a_001.png" ] && filter_files_intact "$fmrun" "$count" \
    && ok "filter ignores malformed fetch evidence ($malformed), retaining both files" || no "filter malformed $malformed rc=$rc" "$(cat "$TMP/err" "$TMP/filter-finalize.json")"
done
# Fetch evidence the engine keeps has no host: an older fetch.json that still has one (scheme, host and port) filters and
# finalizes as before and is rewritten host-free; a host-free fetch.json (path and query only) filters identically.
filter_run filter-hosted-icon-001 || no "filter hosted setup"
fh="$FILTER_RUN"; count=$(filter_count "$fh")
fhprefix=$(jq -r '[.[] | select(.class_type == "SaveImage") | .inputs.filename_prefix][0]' "$fh/workflow.json")
fhbase=${fhprefix##*/}; fhdir=${fhprefix%/*}
cp "$fh/fetch.json" "$TMP/fetch-legacy.json"
AG finalize --run "$fh" --json > "$TMP/filter-hosted.json" 2>"$TMP/err"; rc=$?
hits=$(grep -rFl -e '127.0.0.1' -e ':8188' "$fh" "$TMP/filter-hosted.json" 2>/dev/null)
[ "$rc" -eq 0 ] && jq -e 'all(.urls[]; startswith("http://127.0.0.1:8188/view?"))' "$TMP/fetch-legacy.json" >/dev/null \
  && jq -e '.steps[0].step == "filter" and .steps[0].state == "moved" and ([.steps[0].results[] | select(.state == "moved") | .output] == ["outputs/937cc86a_001.png"])' "$TMP/filter-hosted.json" >/dev/null \
  && [ -f "$fh/outputs/937cc86a_000.png" ] && [ ! -e "$fh/outputs/937cc86a_001.png" ] \
  && cmp -s "$FX/preview-64.png" "$fh/previews/937cc86a_001.png" && filter_files_intact "$fh" "$count" \
  && jq -e '([.results[].output] | unique) == ["outputs/937cc86a_000.png"]' "$fh/qa.json" >/dev/null \
  && jq -e --arg save "/view?filename=${fhbase}_00001_.png&subfolder=${fhdir}&type=output" \
       '.prompt_id == "937cc86a-b67c-4a32-ad68-2652a5ef3425" and .urls == [$save, "/view?filename=ComfyUI_temp_abcde_00001_.png&subfolder=&type=temp"]' "$fh/fetch.json" >/dev/null \
  && [ -z "$hits" ] \
  && ok "filter: an older fetch.json with hosts still filters and finalizes as before, is rewritten host-free, and no run file or finalize output names the host" \
  || no "filter hosted fetch.json rc=$rc" "$(cat "$TMP/err" "$TMP/filter-hosted.json"; echo "host in: $hits"; cat "$fh/fetch.json")"
filter_run filter-hostfree-icon-001 || no "filter host-free setup"
fn="$FILTER_RUN"; count=$(filter_count "$fn")
jq '.urls |= map(sub("^http://[^/]+"; ""))' "$fn/fetch.json" > "$TMP/fetch-hostfree.json" && cp "$TMP/fetch-hostfree.json" "$fn/fetch.json"
AG finalize --run "$fn" --json > "$TMP/filter-hostfree.json" 2>"$TMP/err"; rc=$?
[ "$rc" -eq 0 ] && jq -e 'all(.urls[]; startswith("/view?filename="))' "$fn/fetch.json" >/dev/null \
  && jq -e '.steps[0].step == "filter" and .steps[0].state == "moved" and ([.steps[0].results[] | select(.state == "moved") | .output] == ["outputs/937cc86a_001.png"])' "$TMP/filter-hostfree.json" >/dev/null \
  && [ -f "$fn/outputs/937cc86a_000.png" ] && [ ! -e "$fn/outputs/937cc86a_001.png" ] \
  && cmp -s "$FX/preview-64.png" "$fn/previews/937cc86a_001.png" && filter_files_intact "$fn" "$count" \
  && cmp -s "$TMP/fetch-hostfree.json" "$fn/fetch.json" \
  && ok "filter: a host-free fetch.json classifies the same files and stays byte-identical" \
  || no "filter host-free fetch.json rc=$rc" "$(cat "$TMP/err" "$TMP/filter-hostfree.json")"
# A malformed URL (an unterminated IPv6 authority) is kept as recorded by rewrite_fetch, never replaced by an empty string;
# a well-formed hosted URL in the same entry is still rewritten host-free.
python3 -B - "$ROOT" "$TMP/fetch-malformed" > "$TMP/fetch-malformed.out" 2>&1 <<'EOF'
import json, os, sys
root, work = sys.argv[1:3]
sys.path.insert(0, os.path.join(root, "scripts/assetgen"))
import runfiles
os.makedirs(work, exist_ok=True)
bad = "http://[::1/view?filename=x.png"
with open(os.path.join(work, "fetch.json"), "w", encoding="utf-8") as f:
    json.dump({"prompt_id": "p1", "urls": [bad, "http://127.0.0.1:8188/view?filename=y.png&type=output"]}, f)
assert runfiles.host_free_source(bad) == bad
runfiles.rewrite_fetch(work)
data = json.load(open(os.path.join(work, "fetch.json"), encoding="utf-8"))
assert data["urls"] == [bad, "/view?filename=y.png&type=output"], data
print("ok")
EOF
[ $? -eq 0 ] && grep -qx ok "$TMP/fetch-malformed.out" \
  && ok "rewrite_fetch keeps a malformed fetch URL unchanged and still strips the host of a valid one" \
  || no "rewrite_fetch malformed URL" "$(cat "$TMP/fetch-malformed.out")"
# A live-shaped staged SaveImage output is fitted before embedding and QA.
fitlive="$RUNS/fit-live-icon-001"
mkrun fit-live-icon-001 icon --style stylized-painterly --template staged-icon && AG render --run "$fitlive" >/dev/null 2>"$TMP/err" \
  && cp "$FX/svc-fit.png" "$fitlive/outputs/937cc86a_000.png" || no "fit live setup" "$(cat "$TMP/err")"
fitprefix=$(jq -r '[.[] | select(.class_type == "SaveImage") | .inputs.filename_prefix][0]' "$fitlive/workflow.json")
fitbase=${fitprefix##*/}; fitdir=${fitprefix%/*}
jq -n --arg save "http://127.0.0.1:8188/view?filename=${fitbase}_00001_.png&subfolder=${fitdir}&type=output" \
  '{prompt_id: "937cc86a-b67c-4a32-ad68-2652a5ef3425", urls: [$save]}' > "$fitlive/fetch.json"
AG finalize --run "$fitlive" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
python3 -B - "$ROOT" "$FX/svc-fit.png" "$fitlive/outputs/937cc86a_000.png" > "$TMP/fit-pixels" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
original, fitted = map(png.decode, sys.argv[2:])
assert (original.width, original.height) == (1536, 1024)
assert (fitted.width, fitted.height) == (1536, 1536)
stride = 1536 * 4
assert fitted.rgba[256 * stride:1280 * stride] == original.rgba
assert not any(fitted.rgba[:256 * stride][3::4])
assert not any(fitted.rgba[1280 * stride:][3::4])
EOF
pixels_rc=$?
[ $rc -eq 0 ] && [ $pixels_rc -eq 0 ] \
  && jq -e '[.steps[] | select(.step == "fit") | select(.state == "fitted") | .results[] | select(.state == "padded" and .output == "outputs/937cc86a_000.png" and .raw == "raw/937cc86a_000.png" and .original_size == "1536x1024" and .fitted_size == "1536x1536" and .offset == [0,256])] | length == 1' "$TMP/fit.json" >/dev/null \
  && [ "$(sha "$fitlive/raw/937cc86a_000.png")" = "$(sha "$FX/svc-fit.png")" ] \
  && jq -e '.fitted | length == 1 and .[0].original_size == "1536x1024" and .[0].fitted_size == "1536x1536" and .[0].raw == "raw/937cc86a_000.png"' "$fitlive/finalize.json" >/dev/null \
  && jq -e '[.results[] | select(.check == "png-size" and .state == "PASS")] | length == 1' "$fitlive/qa.json" >/dev/null \
  && ok "fit: staged landscape icon is centered on transparent bands, original preserved and png-size PASS" \
  || no "fit live rc=$rc pixels=$pixels_rc" "$(cat "$TMP/err" "$TMP/fit-pixels" "$TMP/fit.json")"
fitsha=$(sha "$fitlive/outputs/937cc86a_000.png")
AG finalize --run "$fitlive" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e '[.steps[] | select(.step == "fit" and .state == "skipped")] | length == 1' "$TMP/fit.json" >/dev/null \
  && [ "$(sha "$fitlive/outputs/937cc86a_000.png")" = "$fitsha" ] && [ "$(find "$fitlive/raw" -type f | wc -l | tr -d ' ')" = 1 ] \
  && [ "$(sha "$fitlive/raw/937cc86a_000.png")" = "$(sha "$FX/svc-fit.png")" ] \
  && jq -e '.fitted | length == 1 and .[0].original_size == "1536x1024" and .[0].fitted_size == "1536x1536" and .[0].raw == "raw/937cc86a_000.png"' "$fitlive/finalize.json" >/dev/null \
  && jq -e '.fitted | length == 1' "$TMP/fit.json" >/dev/null \
  && ok "fit: second finalize skips fitting and preserves output and raw" || no "fit repeat rc=$rc" "$(cat "$TMP/err" "$TMP/fit.json")"
AG manifest --run "$fitlive" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(grep -c '^- Fit:' "$fitlive/run.md")" -eq 1 ] \
  && grep -qF -- '- Fit: orientation padding; originals in raw/ (finalize.json): outputs/937cc86a_000.png 1536x1024 -> 1536x1536' "$fitlive/run.md" \
  && ok "manifest: the run.md Fit line names each fitted output with its original and fitted size from finalize.json" \
  || no "manifest fit line rc=$rc" "$(cat "$TMP/err"; grep -n 'Fit' "$fitlive/run.md")"
fitplain="$RUNS/fit-plain-001"; finrun fit-plain-001 icon icon-ok.png
AG finalize --run "$fitplain" >/dev/null 2>&1 && AG manifest --run "$fitplain" >/dev/null 2>&1 && ! grep -q '^- Fit:' "$fitplain/run.md" \
  && ok "manifest: a run with no fitted output has no Fit line" || no "manifest without fit line" "$(grep -n 'Fit' "$fitplain/run.md" 2>&1)"

fitsmall="$RUNS/fit-small-001"; finrun fit-small-001 icon svc-small.png
AG finalize --run "$fitsmall" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ ! -e "$fitsmall/raw" ] \
  && jq -e '.failed_at == "qa" and ([.steps[] | select(.step == "fit") | .results[] | select(.state == "skipped" and (.reason | contains("fails the size floors")))] | length == 1)' "$TMP/fit.json" >/dev/null \
  && jq -e '[.results[] | select(.check == "png-size" and .state == "FAIL")] | length == 1' "$fitsmall/qa.json" >/dev/null \
  && ok "fit: undersized output is not padded and fails QA" || no "fit small rc=$rc" "$(cat "$TMP/err" "$TMP/fit.json")"

fitlegacy="$RUNS/fit-legacy-001"; finrun fit-legacy-001 icon svc-fit.png
AG defringe --run "$fitlegacy" > /dev/null 2>"$TMP/err"; legacysha=$(sha "$fitlegacy/outputs-raw/prop.png")
AG finalize --run "$fitlegacy" --force --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ ! -e "$fitlegacy/raw" ] && [ "$(sha "$fitlegacy/outputs-raw/prop.png")" = "$legacysha" ] \
  && jq -e '.failed_at == "qa" and ([.steps[] | select(.step == "fit") | .results[] | select(.state == "skipped" and .reason == "already defringed before fit (outputs-raw/prop.png): not padded; start a new attempt")] | length == 1)' "$TMP/fit.json" >/dev/null \
  && ok "fit: legacy defringed output is not padded" || no "fit legacy rc=$rc" "$(cat "$TMP/err" "$TMP/fit.json")"

fitsquare="$RUNS/fit-square-001"; finrun fit-square-001 icon icon-ok.png
AG finalize --run "$fitsquare" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
python3 -B - "$ROOT" "$FX/icon-ok.png" "$fitsquare/outputs/prop.png" > "$TMP/fit-pixels" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
a, b = map(png.decode, sys.argv[2:])
assert (a.width, a.height, a.rgba) == (b.width, b.height, b.rgba)
EOF
pixels_rc=$?
[ $rc -eq 0 ] && [ $pixels_rc -eq 0 ] && [ ! -e "$fitsquare/raw" ] \
  && jq -e '[.steps[] | select(.step == "fit" and .state == "skipped") | .results[] | select(.state == "skipped" and (.reason | contains("as expected: untouched")))] | length == 1' "$TMP/fit.json" >/dev/null \
  && ok "fit: matching square icon pixels stay unchanged and no raw copy is made" || no "fit square rc=$rc pixels=$pixels_rc" "$(cat "$TMP/err" "$TMP/fit-pixels" "$TMP/fit.json")"

fittile="$RUNS/fit-tile-001"; finrun fit-tile-001 texture-tileable big.png
AG finalize --run "$fittile" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && jq -e '.failed_at == "qa" and ([.steps[] | select(.step == "fit" and .state == "skipped" and .reason == "qa.size.fit is none")] | length == 1)' "$TMP/fit.json" >/dev/null \
  && jq -e '[.results[] | select(.check == "png-size" and .state == "FAIL" and (any(.reasons[]; contains("landscape") and contains("square"))))] | length == 1' "$fittile/qa.json" >/dev/null \
  && ok "fit: landscape texture stays unpadded and fails square size QA" || no "fit texture rc=$rc" "$(cat "$TMP/err" "$TMP/fit.json" "$fittile/qa.json")"

fitbound="$RUNS/fit-bound-001"; finrun fit-bound-001 icon svc-fit.png
AG qa --run "$fitbound" >/dev/null 2>"$TMP/err"
fitbefore=$(sha "$fitbound/outputs/prop.png"); fitqa=$(sha "$fitbound/qa.json")
AG finalize --run "$fitbound" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && jq -e '.failed_at == "fit" and ([.steps[] | select(.step == "fit" and .state == "FAIL" and (.reason | contains("qa.json")))] | length == 1)' "$TMP/fit.json" >/dev/null \
  && [ "$(sha "$fitbound/outputs/prop.png")" = "$fitbefore" ] && [ "$(sha "$fitbound/qa.json")" = "$fitqa" ] && [ ! -e "$fitbound/raw" ] \
  && ok "fit: bound QA prevents padding without force and leaves files untouched" || no "fit bound rc=$rc" "$(cat "$TMP/err" "$TMP/fit.json")"

fitrgb="$RUNS/fit-rgb-001"; finrun fit-rgb-001 icon big.png
AG finalize --run "$fitrgb" --json > "$TMP/fit.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ ! -e "$fitrgb/raw" ] \
  && jq -e '[.steps[] | select(.step == "fit" and .state == "skipped") | .results[] | select(.state == "skipped" and (.reason | contains("no alpha channel")))] | length == 1' "$TMP/fit.json" >/dev/null \
  && ok "fit: RGB output is not padded and QA grades the missing alpha" || no "fit RGB rc=$rc" "$(cat "$TMP/err" "$TMP/fit.json")"

# alpha purpose: filter, fit, defringe, embed, qa in that order; the run ends embedded, defringed and graded
fz="$RUNS/fin-icon-001"; finrun fin-icon-001 icon fringe.png
AG finalize --run "$fz" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(steps "$TMP/o")" = "filter fit defringe embed qa " ] && grep -q "^defringe defringed: 1 defringed, 0 skipped, 0 FAIL" "$TMP/o" \
  && grep -q "^embed done: 1 embedded, 0 replaced, 0 kept, 0 FAIL" "$TMP/o" && grep -qx "assetgen finalize: PASS" "$TMP/o" \
  && [ "$(jq -r .state "$fz/qa.json")" = PASS ] && [ -f "$fz/defringe.json" ] && [ -f "$fz/outputs-raw/prop.png" ] \
  && [ "$(sha "$fz/outputs-raw/prop.png")" = "$(sha "$FX/fringe.png")" ] && grep -qa "workflow" "$fz/outputs/prop.png" \
  && [ "$(jq -r '.outputs[0].sha256' "$fz/qa.json")" = "$(sha "$fz/outputs/prop.png")" ] \
  && ok "finalize on an alpha purpose: defringe, embed, qa in that order, exit 0 (original kept, workflow embedded, qa.json binds the final bytes)" \
  || no "finalize alpha rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
# a second finalize on the unchanged run is idempotent: no defringe refusal (qa.json binds the outputs), same bytes
b1=$(sha "$fz/outputs/prop.png"); d1=$(sha "$fz/defringe.json")
AG finalize --run "$fz" --json > "$TMP/f.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.schema + " " + .state + " " + (.exit | tostring) + " " + ([.steps[] | .step + ":" + .state] | join(","))' "$TMP/f.json")" \
  = "rpg-factory.assetgen-finalize/1 PASS 0 filter:skipped,fit:skipped,defringe:skipped,embed:done,qa:PASS" ] \
  && [ "$(jq -r '.steps[0].reason' "$TMP/f.json")" = "no preview file in outputs/" ] \
  && jq -r '.steps[] | select(.step == "defringe") | .reason' "$TMP/f.json" | grep -q "^already defringed" && jq -r '.steps[] | select(.step == "embed") | .reason' "$TMP/f.json" | grep -q "0 embedded, 0 replaced, 1 kept" \
  && [ "$(jq -c '[.stale, .failed_at]' "$TMP/f.json")" = '[[],null]' ] \
  && [ "$(sha "$fz/outputs/prop.png")" = "$b1" ] && [ "$(sha "$fz/defringe.json")" = "$d1" ] && [ "$(jq -r .state "$fz/qa.json")" = PASS ] \
  && ok "finalize again on an unchanged run: filter skipped (no preview), defringe skipped (already defringed), embed kept, qa PASS, bytes unchanged, --json object" \
  || no "finalize idempotent rc=$rc" "$(cat "$TMP/err" "$TMP/f.json")"
# a non-alpha purpose never defringes; embed changes the bytes, so the image reviews that bound them are stale; qa.json is not listed
ft="$RUNS/fin-tile-001"; finrun fin-tile-001 texture-tileable tile-ok.png
AG qa --run "$ft" > /dev/null 2>&1
bound "$ft" image PASS codex > "$ft/review-image.json"; bound "$ft" image PASS claude > "$ft/review-image-claude.json"
AG finalize --run "$ft" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(steps "$TMP/o")" = "filter fit defringe embed qa " ] && grep -q "^defringe skipped: not an alpha purpose" "$TMP/o" \
  && [ ! -e "$ft/defringe.json" ] && [ ! -e "$ft/outputs-raw" ] && grep -q "^embed done: 1 embedded" "$TMP/o" \
  && grep -qx "stale now (re-run them): review-image.json, review-image-claude.json" "$TMP/o" \
  && ok "finalize on a non-alpha purpose: defringe skipped (nothing written), embed, qa PASS; the image reviews it made stale are named, not qa.json" \
  || no "finalize non-alpha rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
# a run qa and the image reviews already bind: defringe's refusal is a FAIL at defringe (nothing written) unless --force
fb="$RUNS/fin-force-001"; finrun fin-force-001 icon fringe.png
AG embed --run "$fb" > /dev/null; AG qa --run "$fb" > /dev/null 2>&1
bound "$fb" image FAIL codex '[{"rubric": 1, "severity": "major", "text": "orange edge speckle"}]' > "$fb/review-image.json"
bound "$fb" image FAIL claude '[{"rubric": 1, "severity": "major", "text": "orange edge speckle"}]' > "$fb/review-image-claude.json"
fb0=$(sha "$fb/outputs/prop.png"); q0=$(sha "$fb/qa.json")
AG finalize --run "$fb" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ "$(steps "$TMP/o")" = "filter fit defringe " ] && grep -q "^assetgen finalize: FAIL at defringe: .*qa.json, review-image.json, review-image-claude.json already bind(s) the current outputs" "$TMP/o" \
  && grep -q "pass --force" "$TMP/o" && ! grep -q "^stale now" "$TMP/o" \
  && [ "$(sha "$fb/outputs/prop.png")" = "$fb0" ] && [ "$(sha "$fb/qa.json")" = "$q0" ] && [ ! -e "$fb/outputs-raw" ] && [ ! -e "$fb/defringe.json" ] \
  && ok "finalize: outputs the records bind stop at FAIL at defringe without --force (exit 1, nothing written, embed and qa not run)" \
  || no "finalize bound rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
AG finalize --run "$fb" --force --json > "$TMP/f.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.state + " " + (.stale | join(","))' "$TMP/f.json")" = "PASS review-image.json,review-image-claude.json" ] \
  && [ "$(jq -r '.steps[] | select(.step == "defringe") | .step + ":" + .state' "$TMP/f.json")" = defringe:defringed ] && [ "$(sha "$fb/outputs/prop.png")" != "$fb0" ] && [ "$(sha "$fb/outputs-raw/prop.png")" = "$fb0" ] \
  && [ "$(jq -r .state "$fb/qa.json")" = PASS ] \
  && ok "finalize --force: defringe runs, embed and qa PASS, both image reviews listed stale (qa.json is rewritten, not listed)" \
  || no "finalize force rc=$rc" "$(cat "$TMP/err" "$TMP/f.json")"
# stops at the first FAIL, naming the step: defringe (an unreadable output of an alpha purpose), embed, qa
fd="$RUNS/fin-fail-def-001"; finrun fin-fail-def-001 icon not-a-png.png
AG finalize --run "$fd" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ "$(steps "$TMP/o")" = "filter fit defringe " ] && grep -q "^assetgen finalize: FAIL at defringe: " "$TMP/o" && [ ! -e "$fd/qa.json" ] && [ "$(sha "$fd/outputs/prop.png")" = "$(sha "$FX/not-a-png.png")" ] \
  && ok "finalize: a FAIL at defringe stops there (exit 1, embed and qa not run, output untouched)" || no "finalize fail defringe rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
fe="$RUNS/fin-fail-emb-001"; finrun fin-fail-emb-001 texture-tileable not-a-png.png
AG finalize --run "$fe" --json > "$TMP/f.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ "$(jq -r '.failed_at + " " + .state + " " + ([.steps[] | .step + ":" + .state] | join(","))' "$TMP/f.json")" = "embed FAIL filter:skipped,fit:skipped,defringe:skipped,embed:FAIL" ] && [ ! -e "$fe/qa.json" ] \
  && ok "finalize: a FAIL at embed stops there (exit 1, qa not run, failed_at embed)" || no "finalize fail embed rc=$rc" "$(cat "$TMP/err" "$TMP/f.json")"
fq="$RUNS/fin-fail-qa-001"; finrun fin-fail-qa-001 icon icon-opaque.png
AG finalize --run "$fq" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ "$(steps "$TMP/o")" = "filter fit defringe embed qa " ] && grep -q "^defringe skipped: no output needs it" "$TMP/o" && grep -q "^assetgen finalize: FAIL at qa: " "$TMP/o" \
  && [ "$(jq -r .state "$fq/qa.json")" = FAIL ] \
  && ok "finalize: a qa FAIL is FAIL at qa, exit 1 (an opaque output needs no defringe)" || no "finalize fail qa rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
# NOT_AVAILABLE (a 16-bit output without Pillow) exits 3 like qa
fn="$RUNS/fin-na-001"; finrun fin-na-001 image-edit deep16.png --param reference_image=ref.png
ASSETGEN_NO_PIL=1 AG finalize --run "$fn" --json > "$TMP/f.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 3 ] && [ "$(jq -r '.state + " " + (.exit | tostring) + " " + (.failed_at | tostring)' "$TMP/f.json")" = "NOT_AVAILABLE 3 null" ] && [ "$(jq -r .state "$fn/qa.json")" = NOT_AVAILABLE ] \
  && ok "finalize: exit codes follow qa (0 PASS, 1 FAIL, 3 NOT_AVAILABLE)" || no "finalize not available rc=$rc" "$(cat "$TMP/err" "$TMP/f.json")"
# refusals before anything is written: no spec.json, no outputs, no workflow.ui.json, an approved run
mkdir -p "$RUNS/fin-nospec-001/outputs"; cp "$FX/icon-ok.png" "$RUNS/fin-nospec-001/outputs/prop.png"
AG finalize --run "$RUNS/fin-nospec-001" > "$TMP/o" 2>&1; rc1=$?
mkrun fin-noout-001 icon --style stylized-painterly --template image-generate && AG render --run "$RUNS/fin-noout-001" > /dev/null 2>&1
AG finalize --run "$RUNS/fin-noout-001" > "$TMP/o2" 2>&1; rc2=$?
mkrun fin-noui-001 icon --style stylized-painterly && cp "$FX/icon-ok.png" "$RUNS/fin-noui-001/outputs/prop.png"
AG finalize --run "$RUNS/fin-noui-001" > "$TMP/o3" 2>&1; rc3=$?
[ $rc1 -eq 1 ] && grep -q "finalize needs .*fin-nospec-001/spec.json" "$TMP/o" && [ $rc2 -eq 1 ] && grep -q "no outputs/\*.png" "$TMP/o2" \
  && [ $rc3 -eq 1 ] && grep -q "workflow.ui.json" "$TMP/o3" \
  && [ "$(sha "$RUNS/fin-noui-001/outputs/prop.png")" = "$(sha "$FX/icon-ok.png")" ] && [ ! -e "$RUNS/fin-noui-001/qa.json" ] && [ ! -e "$RUNS/fin-nospec-001/qa.json" ] \
  && ok "finalize refuses a run without spec.json, outputs or workflow.ui.json (exit 1, nothing written)" || no "finalize refusals rc=$rc1/$rc2/$rc3" "$(cat "$TMP/o" "$TMP/o2" "$TMP/o3")"
FZA="$TMP/fin-approve"; mkdir -p "$FZA/assetgen/runs"; cp -R "$GL/purposes" "$GL/styles" "$GL/templates" "$FZA/assetgen/"
cp -R "$fz" "$FZA/assetgen/runs/"; fa="$FZA/assetgen/runs/fin-icon-001"
AG manifest --run "$fa" --prompt-author robin > /dev/null
git init -q -b main "$FZA" && git -C "$FZA" add -A && git -C "$FZA" "${G[@]}" commit -qm "finalized run"
AG approve-record --run "$fa" --by Dana > /dev/null 2>"$TMP/err" || no "finalize: approve-record" "$(cat "$TMP/err")"
find "$FZA" -path "$FZA/.git" -prune -o -type f -exec sha256sum {} + | sort > "$TMP/tree0"
AG finalize --run "$fa" > "$TMP/o" 2>&1; rc=$?
find "$FZA" -path "$FZA/.git" -prune -o -type f -exec sha256sum {} + | sort > "$TMP/tree1"
[ $rc -eq 1 ] && grep -q "run.md is approved: finalize would rewrite the approved outputs" "$TMP/o" && cmp -s "$TMP/tree0" "$TMP/tree1" \
  && [ "$(sed -n '/^---json$/,/^---$/p' "$fa/run.md" | sed '1d;$d' | jq -r .status)" = approved ] \
  && ok "finalize refuses an approved run (exit 1) and writes nothing" || no "finalize approved rc=$rc" "$(cat "$TMP/o"; diff "$TMP/tree0" "$TMP/tree1")"
f_help=$(AG finalize --help 2>&1); grep -q -- "--force" <<<"$f_help" && grep -q "finalize --run RUN" "$ROOT/scripts/assetgen/assetgen.py" \
  && ok "finalize is a subcommand (--run, --authoring, --force, --json) listed in the assetgen.py usage" || no "finalize usage" "$f_help"

echo "-- batch discard and finalize QA failures"
batch_run() {
  finrun "$1" icon icon-ok.png || return 1
  local run="$RUNS/$1"
  cp "$FX/icon-ok.png" "$run/outputs/a.png"
  cp "$FX/icon-ok.png" "$run/outputs/b.png"
  cp "$FX/icon-opaque.png" "$run/outputs/bad.png"
}
batch_front() { sed -n '/^---json$/,/^---$/p' "$1/run.md" | sed '1d;$d'; }
batch_run batch-plain-001
bp="$RUNS/batch-plain-001"
AG finalize --run "$bp" --json > "$TMP/batch.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && jq -e '.failed_at == "qa"' "$TMP/batch.json" >/dev/null && [ "$(find "$bp/outputs" -name '*.png' | wc -l)" -eq 4 ] \
  && [ ! -e "$bp/outputs-rejected" ] && [ ! -e "$bp/discards.json" ] \
  && ok "batch finalize without discard flag fails QA and moves nothing" || no "batch without flag rc=$rc" "$(cat "$TMP/err" "$TMP/batch.json")"

batch_run batch-discard-001
batchd="$RUNS/batch-discard-001"
AG embed --run "$batchd" >/dev/null 2>"$TMP/err"
cp "$batchd/outputs/bad.png" "$TMP/batch-bad.png"
AG finalize --run "$batchd" --discard-qa-fail --json > "$TMP/batch.json" 2>"$TMP/err"; rc=$?
AG manifest --run "$batchd" >/dev/null 2>>"$TMP/err"; mrc=$?
[ $rc -eq 0 ] && [ $mrc -eq 0 ] && jq -e '.stale | index("qa.json") | not' "$TMP/batch.json" >/dev/null && [ "$(find "$batchd/outputs" -name '*.png' | wc -l)" -eq 3 ] \
  && cmp -s "$TMP/batch-bad.png" "$batchd/outputs-rejected/bad.png" \
  && jq -e '.discards | length == 1 and .[0].by == "finalize" and .[0].output == "outputs/bad.png"' "$batchd/discards.json" >/dev/null \
  && jq -e '(.outputs | length == 3) and ([.results[].output] | unique | length == 3) and all(.results[]; .output != "outputs/bad.png")' "$batchd/qa.json" >/dev/null \
  && batch_front "$batchd" | jq -e '(.spec.outputs | length == 3) and (.spec.trace.discarded | length == 1 and .[0].output == "outputs/bad.png" and .[0].path == "outputs-rejected/bad.png")' >/dev/null \
  && grep -q '^- Discarded: outputs/bad.png' "$batchd/run.md" \
  && ok "batch finalize discards one QA failure byte-identically and manifests the three passing outputs" \
  || no "batch discard rc=$rc manifest=$mrc" "$(cat "$TMP/err" "$TMP/batch.json")"

# the budget counts generations: a discard never refunds one (no sheet)
batch_run batch-budget-001
bb="$RUNS/batch-budget-001"
AG embed --run "$bb" >/dev/null 2>"$TMP/err"
AG budget --run "$bb" --json > "$TMP/bb-before.json" 2>>"$TMP/err"; brc=$?
AG budget --run "$bb" > "$TMP/bb-before.txt" 2>>"$TMP/err"; brc2=$?
AG finalize --run "$bb" --discard-qa-fail --json > "$TMP/bb-finalize.json" 2>>"$TMP/err"; rc=$?
AG budget --run "$bb" --json > "$TMP/bb-after.json" 2>>"$TMP/err"; arc=$?
AG budget --run "$bb" > "$TMP/bb-after.txt" 2>>"$TMP/err"; arc2=$?
[ "$brc/$brc2/$rc/$arc/$arc2" = 0/0/0/0/0 ] && [ ! -e "$bb/outputs/bad.png" ] && [ -f "$bb/outputs-rejected/bad.png" ] \
  && jq -e '[.used, .outputs, .discarded, .state, (.failed_attempts | length)] == [4,4,0,"at-limit",0] and (has("sheet_cells") | not)' "$TMP/bb-before.json" >/dev/null \
  && jq -e '[.used, .outputs, .discarded, .state, (.failed_attempts | length)] == [4,4,1,"at-limit",0] and (has("sheet_cells") | not)' "$TMP/bb-after.json" >/dev/null \
  && jq -e '[.budget.used, .budget.outputs, .budget.discarded] == [4,4,1]' "$TMP/bb-finalize.json" >/dev/null \
  && grep -q '^budget at-limit: 4 used (4 outputs + 0 failed attempts) of 4 allowed' "$TMP/bb-before.txt" \
  && grep -q '^budget at-limit: 4 used (4 outputs, 1 discarded + 0 failed attempts) of 4 allowed' "$TMP/bb-after.txt" \
  && ok "budget without a sheet: the used count is the same before and after a discard, and the text and --json say how many counted outputs are discarded" \
  || no "budget discard refund rc=$brc/$brc2/$rc/$arc/$arc2" "$(cat "$TMP/err" "$TMP/bb-before.json" "$TMP/bb-after.json" "$TMP/bb-after.txt")"

finrun batch-allfail-001 icon icon-opaque.png
ba="$RUNS/batch-allfail-001"; cp "$FX/icon-opaque.png" "$ba/outputs/second.png"
AG finalize --run "$ba" --discard-qa-fail --json > "$TMP/batch.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && jq -e '.failed_at == "qa" and (.discarded | length == 0)' "$TMP/batch.json" >/dev/null \
  && [ "$(find "$ba/outputs" -name '*.png' | wc -l)" -eq 2 ] && [ ! -e "$ba/outputs-rejected" ] && [ ! -e "$ba/discards.json" ] \
  && ok "batch finalize leaves all outputs in place when all fail QA" || no "batch all fail rc=$rc" "$(cat "$TMP/err" "$TMP/batch.json")"

finrun discard-manual-001 icon icon-ok.png
dm="$RUNS/discard-manual-001"; cp "$FX/icon-ok.png" "$dm/outputs/a.png"; cp "$FX/icon-ok.png" "$dm/outputs/z.png"
AG qa --run "$dm" >/dev/null; bound "$dm" image PASS codex > "$dm/review-image.json"
AG discard --run "$dm" --output 1 --reason 'first choice' --json > "$TMP/discard.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e '.discarded[0].output == "outputs/a.png" and (.stale | index("qa.json")) and (.stale | index("review-image.json"))' "$TMP/discard.json" >/dev/null \
  && cmp -s "$FX/icon-ok.png" "$dm/outputs-rejected/a.png" \
  && ok "discard by index moves bytes and reports stale QA and image review" || no "discard index rc=$rc" "$(cat "$TMP/err" "$TMP/discard.json")"
cp "$FX/icon-opaque.png" "$dm/outputs/a.png"
AG discard --run "$dm" --output a.png --reason 'second choice' --json > "$TMP/discard.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e '.discarded[0].path == "outputs-rejected/a.1.png"' "$TMP/discard.json" >/dev/null \
  && cmp -s "$FX/icon-ok.png" "$dm/outputs-rejected/a.png" && cmp -s "$FX/icon-opaque.png" "$dm/outputs-rejected/a.1.png" \
  && ok "discard by name preserves an existing rejected file with a numbered collision" || no "discard name rc=$rc" "$(cat "$TMP/err" "$TMP/discard.json")"
AG discard --run "$dm" --output z.png --reason '  ' > "$TMP/o" 2>&1; rblank=$?
AG discard --run "$dm" --output missing.png --reason missing > "$TMP/o2" 2>&1; rmissing=$?
AG discard --run "$dm" --output z.png --reason valid >/dev/null 2>"$TMP/err"; rmove=$?
AG discard --run "$dm" --output 1 --reason last > "$TMP/o3" 2>&1; rlast=$?
[ $rblank -eq 2 ] && [ $rmissing -eq 1 ] && [ $rmove -eq 0 ] && [ $rlast -eq 1 ] \
  && [ -f "$dm/outputs/prop.png" ] && [ "$(jq '.discards | length' "$dm/discards.json")" -eq 3 ] \
  && ok "discard refuses blank reason, unknown output and last output without moving them" || no "discard refusals rc=$rblank/$rmissing/$rmove/$rlast" "$(cat "$TMP/o" "$TMP/o2" "$TMP/o3" "$TMP/err")"
AG discard --run "$fa" --output 1 --reason approved > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q 'run.md is approved' "$TMP/o" && [ ! -e "$fa/outputs-rejected" ] && [ -f "$fa/outputs/prop.png" ] \
  && ok "discard refuses an approved run without moving its output" || no "discard approved rc=$rc" "$(cat "$TMP/o")"

finrun discard-single-001 icon icon-ok.png
ds="$RUNS/discard-single-001"; AG finalize --run "$ds" >/dev/null; AG manifest --run "$ds" >/dev/null
batch_front "$ds" | jq -e '.spec.trace | has("discarded") | not' >/dev/null && ! grep -q '^- Discarded:' "$ds/run.md" \
  && ok "single-output manifest retains its existing trace and body without discards" || no "single-output discard compatibility"

echo "-- budget: advisory spend guard (resolve --max-outputs, budget --run, finalize)"
lf() { tr -d '\r' < "$1"; }
# resolve records spec.budget.max_outputs: default 4 (--json and --out), --max-outputs N, invalid values are usage errors
AG resolve --purpose icon --style pixel-art --json > "$TMP/r.json" 2>"$TMP/err"; rc=$?
AG resolve --purpose icon --style pixel-art --out "$TMP/bud-spec.json" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(jq -c .budget "$TMP/r.json")" = '{"max_outputs":4}' ] && [ "$(jq -c .budget "$TMP/bud-spec.json")" = '{"max_outputs":4}' ] \
  && lf "$TMP/o" | grep -q "^budget: at most 4 outputs" \
  && ok "resolve: spec.budget.max_outputs defaults to 4 (--json and the --out spec.json), the summary says 'budget: at most 4 outputs'" \
  || no "resolve default budget rc=$rc/$rc2 $(jq -c .budget "$TMP/r.json" 2>&1)" "$(cat "$TMP/err" "$TMP/o")"
AG resolve --purpose icon --style pixel-art --max-outputs 2 --json > "$TMP/r.json" 2>"$TMP/err"; rc=$?
AG resolve --purpose icon --style pixel-art --max-outputs 2 --out "$TMP/bud-spec2.json" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(jq -c .budget "$TMP/r.json")" = '{"max_outputs":2}' ] && [ "$(jq -c .budget "$TMP/bud-spec2.json")" = '{"max_outputs":2}' ] \
  && lf "$TMP/o" | grep -q "^budget: at most 2 outputs" \
  && ok "resolve --max-outputs 2 records spec.budget.max_outputs 2 (--json and --out) and prints it" \
  || no "resolve --max-outputs 2 rc=$rc/$rc2" "$(cat "$TMP/err" "$TMP/o")"
bad=""; i=0
for v in 0 -1 x 1.5; do
  i=$((i + 1)); AG resolve --purpose icon --style pixel-art --max-outputs="$v" --out "$TMP/bud-bad-$i.json" > /dev/null 2>"$TMP/err"; rc=$?
  { [ $rc -eq 2 ] && [ ! -e "$TMP/bud-bad-$i.json" ] && grep -q -- "--max-outputs" "$TMP/err"; } || bad="$bad $v:$rc"
done
[ -z "$bad" ] && ok "resolve --max-outputs 0, -1, x, 1.5: usage error (exit 2) naming --max-outputs, --out writes nothing" \
  || no "resolve invalid --max-outputs:$bad" "$(cat "$TMP/err")"
# a series bud-icon-NNN: 001 failed (no run.md, counted), 002 finished (run.md, not counted), 003 the run (limit 3),
# 009 a later attempt and xbud-icon-001 another slug (neither counted)
for n in bud-icon-001 bud-icon-002 bud-icon-009 xbud-icon-001; do mkdir -p "$RUNS/$n"; done; : > "$RUNS/bud-icon-002/run.md"
bd="$RUNS/bud-icon-003"; mkrun bud-icon-003 icon --style pixel-art --template image-generate --max-outputs 3 || no "budget: mkrun bud-icon-003"
cp "$FX/icon-ok.png" "$bd/outputs/a.png"
bsnap() { { find "$bd" -type f -exec sha256sum {} +; ls -a "$RUNS"; } | sort; }; bs0=$(bsnap)
AG budget --run "$bd" --json > "$TMP/b.json" 2>"$TMP/err"; rc=$?
AG budget --run "$bd" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] \
  && [ "$(jq -c '[.schema, .run, .outputs, .failed_attempts, .used, .allowed, .remaining, .state, .exit]' "$TMP/b.json")" \
     = '["rpg-factory.assetgen-budget/1","bud-icon-003",1,["bud-icon-001"],2,3,1,"ok",0]' ] \
  && [ "$(jq -r '.reason | type' "$TMP/b.json")" = string ] \
  && [ "$(jq -c 'keys' "$TMP/b.json")" = '["allowed","discarded","exit","failed_attempts","outputs","previews","reason","remaining","run","schema","state","used"]' ] \
  && [ "$(jq -c .previews "$TMP/b.json")" = 0 ] && ! lf "$TMP/o" | grep -q "not counted" \
  && [ "$(lf "$TMP/o" | wc -l)" -eq 1 ] && lf "$TMP/o" | grep -q "^budget ok: .*2 used.*of 3 allowed" \
  && ok "budget ok: used 2 = 1 output + 1 failed attempt (bud-icon-001; not the finished 002, the later 009 or another slug), allowed 3, remaining 1, exit 0" \
  || no "budget ok rc=$rc/$rc2" "$(cat "$TMP/err" "$TMP/b.json" "$TMP/o")"
[ "$(bsnap)" = "$bs0" ] && ok "budget is read-only (text and --json: the run dir and the runs dir unchanged)" || no "budget wrote something" "$(diff <(echo "$bs0") <(bsnap))"
AG budget --run bud-icon-003 --authoring "$AUTH" --json > "$TMP/b2.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -S . "$TMP/b2.json")" = "$(jq -S . "$TMP/b.json")" ] && ok "budget --run RUN-ID --authoring DIR resolves the run like the other verbs" \
  || no "budget --run id rc=$rc" "$(cat "$TMP/err" "$TMP/b2.json")"
cp "$FX/icon-ok.png" "$bd/outputs/b.png"
AG budget --run "$bd" --json > "$TMP/b.json" 2>"$TMP/err"; rc=$?
AG budget --run "$bd" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(jq -c '[.used, .allowed, .remaining, .state, .exit]' "$TMP/b.json")" = '[3,3,0,"at-limit",0]' ] \
  && lf "$TMP/o" | grep -q "^budget at-limit: .*3 used.*of 3 allowed" \
  && ok "budget at-limit: used == allowed (3 of 3), remaining 0, exit 0" || no "budget at-limit rc=$rc/$rc2" "$(cat "$TMP/err" "$TMP/b.json" "$TMP/o")"
cp "$FX/icon-ok.png" "$bd/outputs/c.png"
AG budget --run "$bd" --json > "$TMP/b.json" 2>"$TMP/err"; rc=$?
AG budget --run "$bd" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 1 ] && [ $rc2 -eq 1 ] && [ "$(jq -c '[.outputs, .failed_attempts, .used, .allowed, .remaining, .state, .exit]' "$TMP/b.json")" = '[3,["bud-icon-001"],4,3,0,"exceeded",1]' ] \
  && lf "$TMP/o" | grep -q "^budget exceeded: .*4 used.*of 3 allowed" \
  && ok "budget exceeded: used 4 > allowed 3, remaining 0, exit 1 (text and --json)" || no "budget exceeded rc=$rc/$rc2" "$(cat "$TMP/err" "$TMP/b.json" "$TMP/o")"
rm -f "$RUNS/bud-icon-002/run.md"  # the empty marker is no gen-run: the quality plugin loop below parses every runs/*/run.md
# a spec resolved before the spend guard (no budget key) is unlimited, never a failure
bo="$RUNS/bud-old-001"; mkrun bud-old-001 icon --style pixel-art --template image-generate || no "budget: mkrun bud-old-001"
jq 'del(.budget)' "$bo/spec.json" > "$TMP/spec.tmp" && cp "$TMP/spec.tmp" "$bo/spec.json"; cp "$FX/icon-ok.png" "$bo/outputs/a.png"
AG budget --run "$bo" --json > "$TMP/b.json" 2>"$TMP/err"; rc=$?
AG budget --run "$bo" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(jq -c '[.used, .allowed, .remaining, .state, .exit]' "$TMP/b.json")" = '[1,null,null,"unlimited",0]' ] \
  && lf "$TMP/o" | grep -q "^budget unlimited: .*1 used" && ! lf "$TMP/o" | grep -q "allowed" \
  && ok "budget on a spec.json without budget (resolved before the spend guard): unlimited, allowed and remaining null, exit 0" \
  || no "budget unlimited rc=$rc/$rc2" "$(cat "$TMP/err" "$TMP/b.json" "$TMP/o")"
# a malformed spec.budget is invalid (exit 1): a string, 0, a boolean
bad=""
for v in '"4"' 0 true; do
  jq --argjson v "$v" '.budget = {max_outputs: $v}' "$bo/spec.json" > "$TMP/spec.tmp" && cp "$TMP/spec.tmp" "$bo/spec.json"
  AG budget --run "$bo" --json > "$TMP/b.json" 2>"$TMP/err"; rc=$?
  AG budget --run "$bo" > "$TMP/o" 2>>"$TMP/err"; rc2=$?
  { [ $rc -eq 1 ] && [ $rc2 -eq 1 ] && [ "$(jq -c '[.state, .exit]' "$TMP/b.json")" = '["invalid",1]' ] && lf "$TMP/o" | grep -q "^budget invalid: "; } \
    || bad="$bad $v:$rc/$rc2"
done
[ -z "$bad" ] && ok "budget with a malformed spec.budget.max_outputs (\"4\", 0, true): invalid, exit 1" || no "budget invalid:$bad" "$(cat "$TMP/err" "$TMP/b.json" "$TMP/o")"
mkdir -p "$RUNS/bud-nospec-001/outputs"; cp "$FX/icon-ok.png" "$RUNS/bud-nospec-001/outputs/a.png"
AG budget --run "$RUNS/bud-nospec-001" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q "spec.json" "$TMP/o" && [ "$(find "$RUNS/bud-nospec-001" -type f | wc -l)" -eq 1 ] \
  && ok "budget on a run without spec.json: exit 1 naming spec.json, nothing written" || no "budget no spec rc=$rc" "$(cat "$TMP/o")"
# finalize prints the budget line right before its last line, adds .budget to --json and keeps its exit code
bf="$RUNS/bud-tile-001"; { mkrun bud-tile-001 texture-tileable --style stylized-painterly --template image-generate && AG render --run "$bf" > /dev/null 2>&1 \
  && cp "$FX/tile-ok.png" "$bf/outputs/a.png"; } || no "budget: finalize run bud-tile-001"
AG finalize --run "$bf" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(lf "$TMP/o" | tail -n 1)" = "assetgen finalize: PASS" ] && lf "$TMP/o" | tail -n 2 | head -n 1 | grep -q "^budget ok: .*1 used.*of 4 allowed" \
  && [ "$(lf "$TMP/o" | grep -c "^budget ")" -eq 1 ] && [ "$(steps "$TMP/o")" = "filter fit defringe embed qa " ] \
  && ok "finalize text: one 'budget ok' line right before the last 'assetgen finalize: PASS' line, exit 0" || no "finalize budget text rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
AG finalize --run "$bf" --json > "$TMP/f.json" 2>"$TMP/err"; rc=$?
AG budget --run "$bf" --json > "$TMP/b.json" 2>>"$TMP/err"
[ $rc -eq 0 ] && [ "$(jq -r '.state + " " + (.exit | tostring)' "$TMP/f.json")" = "PASS 0" ] && [ "$(jq -S .budget "$TMP/f.json")" = "$(jq -S . "$TMP/b.json")" ] \
  && [ "$(jq -r .budget.schema "$TMP/f.json")" = rpg-factory.assetgen-budget/1 ] \
  && ok "finalize --json: key budget is the budget --json object" || no "finalize budget json rc=$rc" "$(cat "$TMP/err" "$TMP/f.json")"
be="$RUNS/bud-over-001"; { mkrun bud-over-001 texture-tileable --style stylized-painterly --template image-generate --max-outputs 1 && AG render --run "$be" > /dev/null 2>&1 \
  && cp "$FX/tile-ok.png" "$be/outputs/a.png" && cp "$FX/tile-ok.png" "$be/outputs/b.png"; } || no "budget: finalize run bud-over-001"
AG finalize --run "$be" > "$TMP/o" 2>"$TMP/err"; rc=$?
AG finalize --run "$be" --json > "$TMP/f.json" 2>>"$TMP/err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(lf "$TMP/o" | tail -n 1)" = "assetgen finalize: PASS" ] \
  && lf "$TMP/o" | tail -n 2 | head -n 1 | grep -q "^budget exceeded: .*2 used.*of 1 allowed" \
  && [ "$(jq -r '.state + " " + (.exit | tostring) + " " + .budget.state + " " + (.budget.exit | tostring)' "$TMP/f.json")" = "PASS 0 exceeded 1" ] \
  && ok "finalize on a run over its budget (max 1, two outputs): still PASS exit 0, budget exceeded reported (text and --json)" \
  || no "finalize exceeded rc=$rc/$rc2" "$(cat "$TMP/o" "$TMP/err" "$TMP/f.json")"
bq="$RUNS/bud-qafail-001"; finrun bud-qafail-001 icon icon-opaque.png || no "budget: finalize run bud-qafail-001"
AG finalize --run "$bq" > "$TMP/o" 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && lf "$TMP/o" | tail -n 1 | grep -q "^assetgen finalize: FAIL at qa: " && lf "$TMP/o" | tail -n 2 | head -n 1 | grep -q "^budget ok: " \
  && ok "finalize FAIL at qa: exit 1 unchanged, the budget line still comes right before the last line" || no "finalize fail budget rc=$rc" "$(cat "$TMP/o" "$TMP/err")"
b_help=$(AG budget --help 2>&1); r_help=$(AG resolve --help 2>&1)
grep -q -- "--run" <<<"$b_help" && grep -q -- "--json" <<<"$b_help" && grep -q -- "--max-outputs" <<<"$r_help" \
  && ok "budget is a subcommand (--run, --json); resolve has --max-outputs" || no "budget usage" "$b_help $r_help"

echo "-- publish: workflow.ui.json to the ComfyUI Workflows sidebar (fake ComfyUI)"
cat > "$TMP/fake-comfy.py" <<'EOF'
import json, os, socket, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ag, run, mode = sys.argv[1], sys.argv[2], sys.argv[3]
seen = []
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        seen.append({"path": self.path, "type": self.headers["Content-Type"], "body": body})
        code = 409 if mode == "conflict" else 200
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b'"workflows/assetgen/x.json"')
    def log_message(self, *a):
        pass
if mode == "refused":
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
else:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
p = subprocess.run([sys.executable, "-B", ag, "publish", "--run", run, "--comfy-url", "http://127.0.0.1:%d/" % port, "--json"],
                   capture_output=True, text=True)
out = json.loads(p.stdout) if p.stdout.strip() else {}
req = [{"path": r["path"], "type": r["type"], "same_body": r["body"] == open(os.path.join(run, "workflow.ui.json"), "rb").read()} for r in seen]
print(json.dumps({"rc": p.returncode, "out": out, "requests": req, "stderr": p.stderr}))
EOF
pr="$RUNS/embed-icon-001"; snap() { find "$pr" -type f -exec sha256sum {} + | sort; }; s0=$(snap)
python3 -B "$TMP/fake-comfy.py" "$ROOT/scripts/assetgen/assetgen.py" "$pr" ok > "$TMP/p.json" 2>&1
jq -e '.rc == 0 and .out.state == "PASS" and .out.http_status == 200 and .out.workflow == "workflows/assetgen/embed-icon-001.json"
       and (.requests | length) == 1 and .requests[0].path == "/api/userdata/workflows%2Fassetgen%2Fembed-icon-001.json?overwrite=true"
       and .requests[0].type == "application/json" and .requests[0].same_body' "$TMP/p.json" >/dev/null \
  && [ "$(snap)" = "$s0" ] \
  && ok "publish: one POST /api/userdata/workflows%2Fassetgen%2F<run-id>.json?overwrite=true with workflow.ui.json as the body, exit 0, run dir unchanged" \
  || no "publish ok" "$(cat "$TMP/p.json")"
python3 -B "$TMP/fake-comfy.py" "$ROOT/scripts/assetgen/assetgen.py" "$pr" conflict > "$TMP/p.json" 2>&1
jq -e '.rc == 1 and .out.state == "FAIL" and .out.http_status == 409' "$TMP/p.json" >/dev/null && [ "$(snap)" = "$s0" ] \
  && ok "publish: an HTTP error from ComfyUI is FAIL (exit 1), nothing written" || no "publish conflict" "$(cat "$TMP/p.json")"
python3 -B "$TMP/fake-comfy.py" "$ROOT/scripts/assetgen/assetgen.py" "$pr" refused > "$TMP/p.json" 2>&1
jq -e '.rc == 3 and .out.state == "NOT_AVAILABLE" and .requests == []' "$TMP/p.json" >/dev/null && [ "$(snap)" = "$s0" ] \
  && ok "publish: connection refused is NOT_AVAILABLE (exit 3), nothing written" || no "publish refused" "$(cat "$TMP/p.json")"
for u in "ftp-host:8188" "file:///etc" "http://127.0.0.1:1/?x=1"; do
  AG publish --run "$pr" --comfy-url "$u" >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && grep -q "comfy-url must be" "$TMP/err" && ok "publish --comfy-url $u refused (exit 2)" || no "publish url $u rc=$rc" "$(cat "$TMP/err")"
done
[ "$(snap)" = "$s0" ] && ok "refused publish calls write nothing" || no "publish wrote into the run dir"

echo "-- manifest (run.md, gen-run)"
d="$RUNS/iron-sword-icon-001"; mkrun iron-sword-icon-001 icon --style pixel-art --template image-generate; AG render --run "$d" >/dev/null
cp "$FX/icon-ok.png" "$d/outputs/iron-sword.png"; AG qa --run "$d" >/dev/null
bound "$d" prompt PASS codex > "$d/review-prompt.json"
{ echo "Review done."; bound "$d" image FAIL codex '[{"rubric": 2, "severity": "major", "text": "off style"}]'; } > "$d/review-image.json"
AG manifest --run "$d" > "$TMP/o" 2>&1; rc=$?
fm() { python3 -c "import json,re,sys; print(json.dumps(json.loads(re.match(r'\A---json\s*\n(.*?)\n---', open(sys.argv[1], encoding='utf-8').read(), re.S).group(1))))" "$d/run.md" | jq -r "$1"; }
[ $rc -eq 0 ] && [ "$(fm '.id + " " + .kind + " " + .domain + " " + .status')" = "AGEN-iron-sword-icon-001 gen-run assetgen proposed" ] \
  && ok "run.md: id, kind gen-run, domain assetgen, status proposed" || no "manifest rc=$rc" "$(cat "$TMP/o"; head -20 "$d/run.md")"
[ "$(fm '.spec.purpose.sha256')" = "$(jq -r .purpose.sha256 "$d/spec.json")" ] && [ "$(fm '.spec.template.id + " " + .spec.style.id')" = "image-generate pixel-art" ] \
  && ok "refs carry id and content hash" || no "refs: $(fm .spec.purpose)"
[ "$(fm '.spec.outputs[0].path + " " + .spec.outputs[0].sha256')" = "outputs/iron-sword.png $(sha256sum "$d/outputs/iron-sword.png" | cut -d' ' -f1)" ] \
  && ok "outputs: path and sha256" || no "outputs: $(fm .spec.outputs)"
[ "$(fm '.spec.prompt_review.by + " " + .spec.prompt_review.state + " " + .spec.image_review.state + " " + (.spec.image_review.findings | tostring) + " " + .spec.qa.state')" = "codex PASS FAIL 1 PASS" ] \
  && ok "reviews (JSON found inside text) and QA state recorded" || no "reviews: $(fm '.spec | {prompt_review, image_review, q: .qa.state}')"
[ "$(fm '.spec.prompt_review.prompt_sha256 == .spec.prompt_sha256 and .spec.image_review.outputs == .spec.outputs and .spec.prompt_review.outputs == []')" = true ] \
  && ok "review bindings recorded (prompt sha256; outputs for the image review only)" || no "bindings: $(fm '.spec | {prompt_review, image_review}')"
[ "$(fm '.provenance.tool + " " + .provenance.model + " " + .spec.generation.generated_by + " " + .spec.prompt_author')" = "comfyui cx/gpt-5.6-sol-image claude claude" ] \
  && ok "provenance: tool comfyui, model from workflow.json, authors" || no "provenance: $(fm .provenance)"
[ "$(fm '.spec.prompt')" = "Test prompt for icon: one subject, centered." ] && ok "final prompt recorded verbatim" || no "prompt: $(fm .spec.prompt)"
python3 -B - "$ROOT/docs/artifact.schema.json" "$d/run.md" > "$TMP/o" 2>&1 <<'EOF'
import json, re, sys
schema = json.load(open(sys.argv[1], encoding="utf-8"))["$defs"]["artifact"]
obj = json.loads(re.match(r"\A---json\s*\n(.*?)\n---", open(sys.argv[2], encoding="utf-8").read(), re.S).group(1))
problems = [k for k in schema["required"] if k not in obj] + [k for k in obj if k not in schema["properties"]]
if not re.fullmatch(schema["properties"]["id"]["pattern"], obj["id"]): problems.append("id pattern")
if set(obj["provenance"]) - set(schema["properties"]["provenance"]["properties"]): problems.append("provenance keys")
print("ok" if not problems else problems)
EOF
grep -qx ok "$TMP/o" && ok "front matter fits the base artifact contract (required, no extra top-level keys, id pattern)" || no "artifact contract" "$(cat "$TMP/o")"
sed -i 's/"status": "proposed"/"status": "reviewed"/' "$d/run.md"
AG manifest --run "$d" >/dev/null && [ "$(fm .status)" = reviewed ] && ok "re-manifest keeps a later status while outputs are unchanged" || no "status kept: $(fm .status)"
cp "$FX/tile-ok.png" "$d/outputs/iron-sword.png"
out=$(AG manifest --run "$d"); [ "$(fm .status)" = proposed ] && grep -q "status reset to proposed" <<<"$out" && ok "changed outputs reset the status to proposed" || no "reset: $(fm .status) $out"
rm -f "$d/review-image.json"; AG manifest --run "$d" >/dev/null; [ "$(fm .spec.image_review.state)" = NOT_RUN ] && ok "missing review file: NOT_RUN" || no "NOT_RUN: $(fm .spec.image_review)"
bound "$d" image PASS claude > "$d/review-image-claude.json"; AG manifest --run "$d" >/dev/null
[ "$(fm '.spec.claude_image_review.by + " " + .spec.claude_image_review.state + " " + .spec.image_review.state')" = "claude PASS NOT_RUN" ] \
  && grep -q '^- Claude visual review: PASS by claude$' "$d/run.md" && grep -q '^- Image review: NOT_RUN by -$' "$d/run.md" \
  && ok "manifest records review-image-claude.json as claude_image_review and summarises it in run.md, apart from the image review" \
  || no "claude review: $(fm '.spec.claude_image_review')" "$(grep -n 'review' "$d/run.md" | head)"
for n in axe-icon-001 axe-icon-002 axe-icon-004 big-axe-icon-001; do mkdir -p "$RUNS/$n"; done
: > "$RUNS/axe-icon-002/run.md"; : > "$RUNS/axe-icon-not-a-run"
mkrun axe-icon-003 icon --style pixel-art && AG manifest --run "$RUNS/axe-icon-003" >/dev/null
d3="$RUNS/axe-icon-003"
[ "$(python3 -c "import json,re,sys; print(json.dumps(json.loads(re.match(r'\A---json\s*\n(.*?)\n---', open(sys.argv[1], encoding='utf-8').read(), re.S).group(1))['spec']['trace']))" "$d3/run.md")" = '{"failed_attempts": ["axe-icon-001"]}' ] \
  && grep -q '^- Failed attempts: axe-icon-001$' "$d3/run.md" \
  && ok "manifest: trace.failed_attempts lists earlier attempts of the series without run.md (not later ones, finished ones or other slugs)" \
  || no "failed attempts" "$(grep -n 'trace\|Failed' -A3 "$d3/run.md" | head)"
[ "$(fm '.spec.trace.failed_attempts | length')" = 0 ] && grep -q '^- Failed attempts: none$' "$d/run.md" && ok "manifest: no failed attempts -> empty trace" || no "empty trace: $(fm .spec.trace)"
rm -rf "$RUNS"/axe-icon-00[1-4] "$RUNS/big-axe-icon-001" "$RUNS/axe-icon-not-a-run"
mkdir -p "$RUNS/Bad_Name"; cp "$d/spec.json" "$d/prompt.md" "$RUNS/Bad_Name/"
AG manifest --run "$RUNS/Bad_Name" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "must be <slug>-NNN" "$TMP/err" && ok "run dir name must be <slug>-NNN" || no "bad run name rc=$rc"

echo "-- quality plugin (scripts/checks/domains/assetgen.py) and artifact-lint on manifest-produced run.md"
good="$RUNS/qp-icon-001"; mkrun qp-icon-001 sprite-2d --style stylized-painterly --template image-generate --authoring "$AUTH"
AG render --run "$good" >/dev/null && cp "$FX/icon-ok.png" "$good/outputs/qp-icon.png" && AG qa --run "$good" >/dev/null \
  || no "good run: render/qa did not PASS" "$(jq -c .results "$good/qa.json" 2>/dev/null)"
bound "$good" prompt PASS codex > "$good/review-prompt.json"; bound "$good" image PASS codex > "$good/review-image.json"
bound "$good" image PASS claude > "$good/review-image-claude.json"
AG manifest --run "$good" >/dev/null
fmset() { # fmset RUN-DIR PYTHON-STATEMENT: edit run.md front matter (obj) in place
  python3 -B -c '
import json, re, sys
path, stmt = sys.argv[1], sys.argv[2]
raw = open(path, encoding="utf-8").read()
m = re.match(r"\A---json\s*\n(.*?)\n---", raw, re.S)
obj = json.loads(m.group(1)); exec(stmt, {"obj": obj})
open(path, "w", encoding="utf-8", newline="\n").write("---json\n" + json.dumps(obj, indent=2) + "\n---" + raw[m.end():])
' "$1/run.md" "$2"
}
variant() { # variant NAME [prompt-review-by]: a copy of the good run, re-manifested under its own id
  local d="$RUNS/$1"; rm -rf "$d"; cp -R "$good" "$d"; rm -f "$d/run.md"
  [ -n "${2:-}" ] && bound "$d" prompt PASS "$2" > "$d/review-prompt.json"
  AG manifest --run "$d" >/dev/null
}
rebase() { # rebase NAME [render args...]: a copied run's spec.json takes its own filename_prefix, re-rendered and re-reviewed
  local d="$RUNS/$1"; shift
  python3 -B -c 'import json, os, sys; p = os.path.join(sys.argv[1], "spec.json"); s = json.load(open(p)); s["params"]["filename_prefix"] = "assetgen/" + os.path.basename(sys.argv[1]); json.dump(s, open(p, "w"))' "$d"
  AG render --run "$d" "$@" >/dev/null && AG qa --run "$d" >/dev/null
  bound "$d" prompt PASS codex > "$d/review-prompt.json"; bound "$d" image PASS codex > "$d/review-image.json"
  bound "$d" image PASS claude > "$d/review-image-claude.json"
}
qaset() { # qaset NAME PYTHON-STATEMENT: edit the run's qa.json (obj) in place
  python3 -B -c 'import json, sys; p = sys.argv[1]; obj = json.load(open(p, encoding="utf-8")); exec(sys.argv[2], {"obj": obj}); json.dump(obj, open(p, "w", encoding="utf-8"))' "$RUNS/$1/qa.json" "$2"
}
variant qp-same-001 claude-sonnet                      # unmarked review by the prompt author's model family
variant qp-fallback-001 SAME_MODEL:claude              # explicit same-model fallback
variant qp-badmark-001 SAME_MODEL:codex                # marker on another model's review
variant qp-tamper-001; printf 'x' >> "$RUNS/qp-tamper-001/outputs/qp-icon.png"
variant qp-extra-001; cp "$FX/icon-ok.png" "$RUNS/qp-extra-001/outputs/second.png"
# Copies of the manifested four-output batch isolate each rejected-file quality check.
for name in qp-batch-001 qp-batch-extra-001 qp-rejected-extra-001 qp-rejected-sha-001 qp-reverse-001; do
  cp -R "$batchd" "$RUNS/$name"; rm -f "$RUNS/$name/run.md"; AG manifest --run "$RUNS/$name" >/dev/null
done
cp "$FX/icon-ok.png" "$RUNS/qp-batch-extra-001/outputs/unrecorded.png"
cp "$FX/icon-ok.png" "$RUNS/qp-rejected-extra-001/outputs-rejected/unrecorded.png"
printf x >> "$RUNS/qp-rejected-sha-001/outputs-rejected/bad.png"
reverse="$RUNS/qp-reverse-001"
mv "$reverse/outputs-rejected/bad.png" "$reverse/outputs/bad.png"
AG qa --run "$reverse" >/dev/null 2>"$TMP/err"; reverseqa=$?
AG manifest --run "$reverse" >/dev/null 2>>"$TMP/err"; reversemanifest=$?
[ $reverseqa -eq 1 ] && [ $reversemanifest -eq 0 ] && cmp -s "$TMP/batch-bad.png" "$reverse/outputs/bad.png" \
  && batch_front "$reverse" | jq -e '(.spec.outputs | length == 4) and (.spec.trace | has("discarded") | not)' >/dev/null \
  && ! grep -q '^- Discarded:' "$reverse/run.md" \
  && ok "moving a discarded PNG back and rerunning QA and manifest removes its discard trace" \
  || no "discard reversal qa=$reverseqa manifest=$reversemanifest" "$(cat "$TMP/err")"
variant qp-qafail-001; cp "$FX/icon-opaque.png" "$RUNS/qp-qafail-001/outputs/qp-icon.png"
AG qa --run "$RUNS/qp-qafail-001" >/dev/null; AG manifest --run "$RUNS/qp-qafail-001" >/dev/null
variant qp-noqa-001; rm -f "$RUNS/qp-noqa-001/qa.json"; AG manifest --run "$RUNS/qp-noqa-001" >/dev/null
variant qp-prov-001; fmset "$RUNS/qp-prov-001" 'obj["provenance"]["model"] = ""'
variant qp-draft-001; rm -f "$RUNS/qp-draft-001/review-image.json"; AG manifest --run "$RUNS/qp-draft-001" >/dev/null
printf 'A draft prompt edited after its review.\n' > "$RUNS/qp-draft-001/prompt.md"; AG manifest --run "$RUNS/qp-draft-001" >/dev/null
fmset "$RUNS/qp-draft-001" 'obj["status"] = "draft"; obj["provenance"]["model"] = ""'
# review files are the evidence (finding 1): missing, contradicting run.md, unbound, stale
variant qp-norev-001; rm -f "$RUNS/qp-norev-001/review-prompt.json"
variant qp-revdiff-001; bound "$RUNS/qp-revdiff-001" image FAIL codex '[{"rubric": 1, "severity": "blocker", "text": "x"}]' > "$RUNS/qp-revdiff-001/review-image.json"
variant qp-unbound-001; printf '{"state": "PASS", "findings": [], "by": "codex"}\n' > "$RUNS/qp-unbound-001/review-prompt.json"; AG manifest --run "$RUNS/qp-unbound-001" >/dev/null
variant qp-staleprompt-001; printf 'Another prompt than the reviewed one.\n' > "$RUNS/qp-staleprompt-001/prompt.md"; AG manifest --run "$RUNS/qp-staleprompt-001" >/dev/null
variant qp-staleimg-001; cp "$FX/trns-icon.png" "$RUNS/qp-staleimg-001/outputs/qp-icon.png"
AG qa --run "$RUNS/qp-staleimg-001" >/dev/null; AG manifest --run "$RUNS/qp-staleimg-001" >/dev/null
variant qp-invalid-001; printf 'no verdict here\n' > "$RUNS/qp-invalid-001/review-image.json"; AG manifest --run "$RUNS/qp-invalid-001" >/dev/null
# qa.json is the QA evidence (finding 2): contradicts run.md, contradicts itself, incomplete, NOT_AVAILABLE, spec drift
variant qp-qadisk-001; qaset qp-qadisk-001 'obj["state"] = "FAIL"; obj["results"][0]["state"] = "FAIL"'
variant qp-qacontra-001; qaset qp-qacontra-001 'obj["results"][1]["state"] = "FAIL"'; AG manifest --run "$RUNS/qp-qacontra-001" >/dev/null
variant qp-qapart-001; qaset qp-qapart-001 'obj["results"] = [r for r in obj["results"] if r["check"] != "png-corners"]'; AG manifest --run "$RUNS/qp-qapart-001" >/dev/null
variant qp-qafringe-001; qaset qp-qafringe-001 'obj["results"] = [r for r in obj["results"] if r["check"] != "png-edge-fringe"]'; AG manifest --run "$RUNS/qp-qafringe-001" >/dev/null
variant qp-qana-001; qaset qp-qana-001 'obj["state"] = "NOT_AVAILABLE"; obj["results"] = [{"output": "outputs/qp-icon.png", "check": "png-valid", "state": "NOT_AVAILABLE", "reasons": ["16-bit"]}]'
AG manifest --run "$RUNS/qp-qana-001" >/dev/null
variant qp-qaspec-001; python3 -B -c 'import json, sys; p = sys.argv[1]; s = json.load(open(p)); s["purpose"]["data"]["qa"] = {}; json.dump(s, open(p, "w"))' "$RUNS/qp-qaspec-001/spec.json"
variant qp-qapurp-001; qaset qp-qapurp-001 'obj["purpose_sha256"] = "0" * 64'; AG manifest --run "$RUNS/qp-qapurp-001" >/dev/null
variant qp-qasize-001; python3 -B -c 'import json, sys; p = sys.argv[1]; w = json.load(open(p)); [n["inputs"].__setitem__("size", "1024x1536") for n in w.values() if n.get("class_type") == "NineRouterImage"]; json.dump(w, open(p, "w"))' "$RUNS/qp-qasize-001/workflow.json"
AG manifest --run "$RUNS/qp-qasize-001" >/dev/null
# style-* rows (style lock consistency signals): WARN and NOT_AVAILABLE neither grade nor contradict; a FAIL must agree
[ "$(jq -r '[.results[] | select(.check | startswith("style-")) | .check + "=" + .state] | join(",")' "$good/qa.json")" \
  = "style-palette=NOT_AVAILABLE,style-tone=NOT_AVAILABLE,style-edges=NOT_AVAILABLE,style-canvas=NOT_AVAILABLE" ] \
  && [ "$(jq -r .state "$good/qa.json")" = PASS ] && ok "qa: a style-locked run without style data gets four NOT_AVAILABLE style rows, state PASS" \
  || no "good run style rows" "$(jq -c '[.state, .results]' "$good/qa.json")"
variant qp-qastylewarn-001; qaset qp-qastylewarn-001 '[r.__setitem__("state", "WARN") for r in obj["results"] if r["check"] in ("style-palette", "style-tone")]'
AG manifest --run "$RUNS/qp-qastylewarn-001" >/dev/null
variant qp-qastylefail-001; qaset qp-qastylefail-001 '[r.__setitem__("state", "FAIL") for r in obj["results"] if r["check"] == "style-palette"]'
AG manifest --run "$RUNS/qp-qastylefail-001" >/dev/null
variant qp-qastyleagree-001; qaset qp-qastyleagree-001 'obj["state"] = "FAIL"; [r.__setitem__("state", "FAIL") for r in obj["results"] if r["check"] == "style-palette"]'
AG manifest --run "$RUNS/qp-qastyleagree-001" >/dev/null
# qa.json is bound to the style inputs it graded (final review P2): a style re-resolved at version 2 with a fail-severity
# red-only palette into the same run, the reviews refreshed but qa.json and the output bytes kept -> stale; re-running qa
# grades the new rule; a qa.json without style_binding (made before the binding) is stale too
STYA="$TMP/style-authoring"; mkdir -p "$STYA/assetgen"; cp -R "$GL/purposes" "$GL/styles" "$GL/templates" "$STYA/assetgen/"
echo '{"extends": "stylized-painterly", "version": 2, "palette": {"text": "Red only.", "colors": [{"hex": "#ff0000"}], "max_distance": 0, "min_share": 1, "severity": "fail"}}'   > "$STYA/assetgen/styles/stylized-painterly.json"
restyle() { # restyle NAME: re-resolve the run with the version 2 style, fresh bound reviews, manifest (qa.json kept)
  local d="$RUNS/$1"; variant "$1"
  AG resolve --purpose sprite-2d --style stylized-painterly --authoring "$STYA" --out "$d/spec.json" >/dev/null
  bound "$d" prompt PASS codex > "$d/review-prompt.json"; bound "$d" image PASS codex > "$d/review-image.json"
  bound "$d" image PASS claude > "$d/review-image-claude.json"; AG manifest --run "$d" >/dev/null
}
restyle qp-qastyle-001
restyle qp-qastyle2-001; AG qa --run "$RUNS/qp-qastyle2-001" >/dev/null; AG manifest --run "$RUNS/qp-qastyle2-001" >/dev/null
[ "$(jq -r '[.results[] | select(.check == "style-palette") | .state] | join(",")' "$RUNS/qp-qastyle2-001/qa.json")/$(jq -r .state "$RUNS/qp-qastyle2-001/qa.json")" = FAIL/FAIL ]   && cmp -s "$RUNS/qp-qastyle-001/qa.json" "$good/qa.json"   && ok "qa re-run after the style re-resolve grades the version 2 fail-severity palette rule: style-palette FAIL, qa FAIL"   || no "restyled qa" "$(jq -c '[.state, .style_binding, .results]' "$RUNS/qp-qastyle2-001/qa.json")"
[ "$(jq -r '.style_binding.style.style_id + " " + .style_binding.family + " " + (.style_binding.style_sha256 | test("^[0-9a-f]{64}$") | tostring) + " " + (.style_binding.anchors | length | tostring)' "$good/qa.json")"   = "stylized-painterly $(jq -r .style_lock.family "$good/spec.json") true 0" ]   && ok "qa.json style_binding: style ref, family, effective style data hash, anchors (none selected)" || no "style_binding" "$(jq -c .style_binding "$good/qa.json")"
variant qp-qanobind-001; qaset qp-qanobind-001 'del obj["style_binding"]'; AG manifest --run "$RUNS/qp-qanobind-001" >/dev/null
# with spec.style_lock the image reviews bind the style ref and the anchors shown
variant qp-stylebind-001; bound "$RUNS/qp-stylebind-001" image PASS codex | jq -c '.style.version = 99' > "$RUNS/qp-stylebind-001/review-image.json"
AG manifest --run "$RUNS/qp-stylebind-001" >/dev/null
variant qp-stylebindc-001; bound "$RUNS/qp-stylebindc-001" image PASS claude | jq -c 'del(.style, .anchors)' > "$RUNS/qp-stylebindc-001/review-image-claude.json"
AG manifest --run "$RUNS/qp-stylebindc-001" >/dev/null
# Claude's own visual review (review-image-claude.json): recorded, WARN when missing, never replaces the Codex review
variant qp-noclaude-001; rm -f "$RUNS/qp-noclaude-001/review-image-claude.json"; AG manifest --run "$RUNS/qp-noclaude-001" >/dev/null
variant qp-claudeonly-001; rm -f "$RUNS/qp-claudeonly-001/review-image.json"; AG manifest --run "$RUNS/qp-claudeonly-001" >/dev/null
variant qp-claudefail-001; bound "$RUNS/qp-claudefail-001" image FAIL claude '[{"rubric": 4, "severity": "major", "text": "broken hilt"}]' > "$RUNS/qp-claudefail-001/review-image-claude.json"
AG manifest --run "$RUNS/qp-claudefail-001" >/dev/null
variant qp-claudediff-001; bound "$RUNS/qp-claudediff-001" image FAIL claude > "$RUNS/qp-claudediff-001/review-image-claude.json"
variant qp-claudestale-001; printf '{"state": "PASS", "findings": [], "by": "claude"}\n' > "$RUNS/qp-claudestale-001/review-image-claude.json"; AG manifest --run "$RUNS/qp-claudestale-001" >/dev/null
variant qp-claudeby-001; bound "$RUNS/qp-claudeby-001" image PASS codex > "$RUNS/qp-claudeby-001/review-image-claude.json"; AG manifest --run "$RUNS/qp-claudeby-001" >/dev/null
variant qp-tool-001; fmset "$RUNS/qp-tool-001" 'obj["provenance"]["tool"] = "other"'
variant qp-ref-001; fmset "$RUNS/qp-ref-001" 'obj["spec"]["style"]["id"] = "no-such-style"'
variant qp-drift-001; fmset "$RUNS/qp-drift-001" 'obj["spec"]["template"]["sha256"] = "0" * 64'
variant qp-prompt-001; printf 'A different prompt.\n' > "$RUNS/qp-prompt-001/prompt.md"
variant qp-where-001; fmset "$RUNS/qp-where-001" 'obj["id"] = "AGEN-somewhere-else-001"'
variant qp-escape-001; fmset "$RUNS/qp-escape-001" 'obj["spec"]["outputs"][0]["path"] = "outputs/../../qp-icon-001/outputs/qp-icon.png"'
# output filter: a previews/ file beside the recorded outputs is ignored; a recorded previews/ path is never a deliverable
variant qp-preview-001; mkdir -p "$RUNS/qp-preview-001/previews" && cp "$FX/preview-64.png" "$RUNS/qp-preview-001/previews/qp-icon_001.png"
variant qp-precord-001; mkdir -p "$RUNS/qp-precord-001/previews" && mv "$RUNS/qp-precord-001/outputs/qp-icon.png" "$RUNS/qp-precord-001/previews/qp-icon.png"   && fmset "$RUNS/qp-precord-001" 'obj["spec"]["outputs"][0]["path"] = "previews/qp-icon.png"'
# reviews are bound to the requirements (review finding 1): a purpose re-resolved with a stricter rubric and qa, then
# qa and manifest re-run, keeps the old review files -> stale; a render --param size change -> stale image review
RUBA="$TMP/rubric-authoring"; mkdir -p "$RUBA/assetgen"; cp -R "$GL/purposes" "$GL/styles" "$GL/templates" "$RUBA/assetgen/"
echo '{"extends": "sprite-2d", "prompt_rubric": ["Names one subject only."], "image_rubric": ["Exactly one subject, nothing else."], "qa": {"not_blank": {"min_stddev": 3.0}}}' \
  > "$RUBA/assetgen/purposes/sprite-2d.json"
variant qp-rubric-001; AG resolve --purpose sprite-2d --style stylized-painterly --authoring "$RUBA" --out "$RUNS/qp-rubric-001/spec.json" >/dev/null
AG qa --run "$RUNS/qp-rubric-001" >/dev/null; AG manifest --run "$RUNS/qp-rubric-001" >/dev/null
variant qp-rsize-001; rebase qp-rsize-001; AG render --run "$RUNS/qp-rsize-001" --param size=1536x1024 >/dev/null
AG qa --run "$RUNS/qp-rsize-001" >/dev/null; AG manifest --run "$RUNS/qp-rsize-001" >/dev/null
# a rejection recorded after the reviews joins spec.style_lock (re-resolve): both reviews are stale
variant qp-rejbind-001; jq '.style_lock.rejections += [{"id": "r-late", "type": "direction", "reason": "too_detailed", "text": "No rivets."}]'   "$RUNS/qp-rejbind-001/spec.json" > "$TMP/s" && mv "$TMP/s" "$RUNS/qp-rejbind-001/spec.json"; AG manifest --run "$RUNS/qp-rejbind-001" >/dev/null
variant qp-wfprompt-001; jq '(.[] | select(.class_type == "NineRouterImage") | .inputs.user_prompt) = "Another prompt sent to the node."'   "$RUNS/qp-wfprompt-001/workflow.json" > "$TMP/wf" && mv "$TMP/wf" "$RUNS/qp-wfprompt-001/workflow.json"; AG manifest --run "$RUNS/qp-wfprompt-001" >/dev/null
variant qp-rqual-001; rebase qp-rqual-001; AG render --run "$RUNS/qp-rqual-001" --param quality=low >/dev/null
AG qa --run "$RUNS/qp-rqual-001" >/dev/null; AG manifest --run "$RUNS/qp-rqual-001" >/dev/null
# a review is bound to the params it was shown (the rendered ones): the same --param again keeps it bound
variant qp-rsame-001; rebase qp-rsame-001 --param size=1536x1024; AG render --run "$RUNS/qp-rsame-001" --param size=1536x1024 >/dev/null
AG manifest --run "$RUNS/qp-rsame-001" >/dev/null
# run.md spec.params tampered after manifest: never replaced by spec.json, compared with the rendered params
variant qp-tsize-001; fmset "$RUNS/qp-tsize-001" 'obj["spec"]["params"]["size"] = "1x1"'
variant qp-tmodel-001; fmset "$RUNS/qp-tmodel-001" 'obj["spec"]["params"]["model"] = "invented-model"; obj["spec"]["params"]["background"] = "invented-background"'
AG manifest --run "$RUNS/qa-malformed-001" >/dev/null
# image-edit: the reference image is bound by name and content (references/<name> in the run directory)
edit="$RUNS/qp-edit-001"; mkrun qp-edit-001 image-edit --style stylized-painterly --template image-edit --authoring "$AUTH"
mkdir -p "$edit/references"; cp "$FX/icon-ok.png" "$edit/references/ref-a.png"
AG render --run "$edit" --param reference_image=ref-a.png >/dev/null && cp "$FX/icon-ok.png" "$edit/outputs/edit.png" && AG qa --run "$edit" >/dev/null   || no "image-edit run: render/qa did not PASS" "$(jq -c .results "$edit/qa.json" 2>/dev/null)"
bound "$edit" prompt PASS codex > "$edit/review-prompt.json"; bound "$edit" image PASS codex > "$edit/review-image.json"
bound "$edit" image PASS claude > "$edit/review-image-claude.json"
AG manifest --run "$edit" >/dev/null
evariant() { local d="$RUNS/$1"; rm -rf "$d"; cp -R "$edit" "$d"; rm -f "$d/run.md"; }
evariant qp-eswap-001; rebase qp-eswap-001 --param reference_image=ref-a.png; cp "$FX/icon-opaque.png" "$RUNS/qp-eswap-001/references/ref-b.png"
AG render --run "$RUNS/qp-eswap-001" --param reference_image=ref-b.png >/dev/null; AG qa --run "$RUNS/qp-eswap-001" >/dev/null; AG manifest --run "$RUNS/qp-eswap-001" >/dev/null
evariant qp-ebytes-001; cp "$FX/icon-opaque.png" "$RUNS/qp-ebytes-001/references/ref-a.png"; AG manifest --run "$RUNS/qp-ebytes-001" >/dev/null
evariant qp-enoref-001; rm -f "$RUNS/qp-enoref-001/references/ref-a.png"; AG manifest --run "$RUNS/qp-enoref-001" >/dev/null
# review tiers (scripts/assetgen/data/review-tiers.json): a light purpose (icon) needs no Claude visual review, a present
# file is still graded; selected style-lock anchors make any run full. The tier is computed at check time, never recorded.
light="$RUNS/qp-light-001"; mkrun qp-light-001 icon --style stylized-painterly --template staged-icon
AG render --run "$light" >/dev/null && cp "$FX/icon-ok.png" "$light/outputs/light.png" && AG qa --run "$light" >/dev/null \
  || no "light run: render/qa did not PASS" "$(jq -c .results "$light/qa.json" 2>/dev/null)"
bound "$light" prompt PASS codex > "$light/review-prompt.json"; bound "$light" image PASS codex > "$light/review-image.json"
AG manifest --run "$light" >/dev/null
lvariant() { local d="$RUNS/$1"; rm -rf "$d"; cp -R "$light" "$d"; rm -f "$d/run.md"; AG manifest --run "$d" >/dev/null; }
lvariant qp-lightinv-001; printf 'no verdict here\n' > "$RUNS/qp-lightinv-001/review-image-claude.json"; AG manifest --run "$RUNS/qp-lightinv-001" >/dev/null
lvariant qp-lightstale-001; printf '{"state": "PASS", "findings": [], "by": "claude"}\n' > "$RUNS/qp-lightstale-001/review-image-claude.json"
AG manifest --run "$RUNS/qp-lightstale-001" >/dev/null
lvariant qp-lightanchor-001
fmset "$RUNS/qp-lightanchor-001" 'lock = obj["spec"].get("style_lock") or {}; lock["references"] = [{"anchor_id": "a-canon", "sha256": "0" * 64}]; obj["spec"]["style_lock"] = lock'
# gen-run-workflow-style (the quality plugin check workflow-style): only for a run whose directory holds workflow.ui.json;
# WARN, never FAIL in this first phase (also on a proposed run), for a legacy-template render (qp-icon-001,
# image-generate), a violating or unreadable workflow.ui.json; PASS for a render of the clean template (gs-clean-001)
gsd="$RUNS/gs-clean-001"; cp "$FX/icon-ok.png" "$gsd/outputs/gs.png"; AG manifest --run "$gsd" >/dev/null
gsvariant() { local d="$RUNS/$1"; rm -rf "$d"; cp -R "$gsd" "$d"; rm -f "$d/run.md"; }
gsvariant gs-moved-001; jq -c '(.nodes[] | select(.id == 4) | .pos) = [5000, 5000]' "$gsd/workflow.ui.json" > "$RUNS/gs-moved-001/workflow.ui.json"
AG manifest --run "$RUNS/gs-moved-001" >/dev/null
gsvariant gs-badjson-001; printf 'not json\n' > "$RUNS/gs-badjson-001/workflow.ui.json"; AG manifest --run "$RUNS/gs-badjson-001" >/dev/null
gsvariant gs-noextra-001  # lost extra.assetgen and an unsuffixed SaveImage: still checked against the run's run_id
jq -c 'del(.extra.assetgen) | (.nodes[] | select(.id == 6) | .widgets_values) = ["assetgen/gs-clean-001"]' "$gsd/workflow.ui.json" > "$RUNS/gs-noextra-001/workflow.ui.json"
AG manifest --run "$RUNS/gs-noextra-001" >/dev/null
variant qp-uitwin-001                                   # the same run twice: one keeps workflow.ui.json, one has none
variant qp-noui-001; rm -f "$RUNS/qp-noui-001/workflow.ui.json"; AG manifest --run "$RUNS/qp-noui-001" >/dev/null
# wired through the registry (artifact-quality --domain assetgen) on a small authoring repo: artifact-quality runs
# artifact-trace once per artifact over every artifact, so the case matrix below calls the plugin directly
QAUTH="$TMP/qauth"; mkdir -p "$QAUTH/assetgen/runs"; cp -R "$GL/purposes" "$GL/styles" "$GL/templates" "$QAUTH/assetgen/"
cp -R "$good" "$RUNS/qp-fallback-001" "$QAUTH/assetgen/runs/"; git init -q -b main "$QAUTH"
python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$QAUTH" --registry "$ROOT/registry.json" --domain assetgen --json > "$TMP/aq.json" 2>"$TMP/err"; rc=$?
st() { jq -r --arg a "$1" --arg c "$2" '[.results[] | select(.artifact == $a and .check == $c) | .state] | join(",")' "$TMP/aq.json"; }
why() { jq -r --arg a "$1" --arg c "$2" '[.results[] | select(.artifact == $a and .check == $c) | .reasons[]] | join("; ")' "$TMP/aq.json"; }
plugin_checks="gen-run-location gen-run-prompt-review gen-run-image-review gen-run-claude-review gen-run-outputs gen-run-qa gen-run-provenance gen-run-refs gen-run-style"
got=$(for c in schema lifecycle trace-approval $plugin_checks; do printf '%s=%s ' "$c" "$(st AGEN-qp-icon-001 "$c")"; done)
want=$(for c in schema lifecycle trace-approval $plugin_checks; do printf '%s=PASS ' "$c"; done)
[ $rc -eq 0 ] && [ "$got" = "$want" ] && ok "artifact-quality --domain assetgen: complete run (codex reviews, QA PASS, hashes, provenance, game-layer refs) all PASS" \
  || no "good run rc=$rc: $got" "$(cat "$TMP/err"; jq -c '.results[] | select(.artifact == "AGEN-qp-icon-001" and .state != "PASS")' "$TMP/aq.json")"
[ "$(st AGEN-qp-fallback-001 gen-run-prompt-review)" = WARN ] && ok "artifact-quality: a SAME_MODEL fallback review is WARN and does not fail the check (rc 0)" \
  || no "fallback through artifact-quality: $(st AGEN-qp-fallback-001 gen-run-prompt-review)"
[ $rc -eq 0 ] && [ "$(st AGEN-qp-icon-001 gen-run-workflow-style)" = WARN ] \
  && ok "artifact-quality: a legacy-template render's workflow.ui.json is a gen-run-workflow-style WARN and does not fail the check (rc 0)" \
  || no "workflow-style through artifact-quality rc=$rc: $(st AGEN-qp-icon-001 gen-run-workflow-style)" "$(why AGEN-qp-icon-001 gen-run-workflow-style)"
python3 -B - "$ROOT" "$AUTH" > "$TMP/aq.json" 2>"$TMP/err" <<'EOF'
import importlib.util, json, re, sys
from pathlib import Path
root, auth = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
sys.path.insert(0, str(root / "scripts" / "checks"))
from domains._api import Context
spec = importlib.util.spec_from_file_location("assetgen_plugin", root / "scripts" / "checks" / "domains" / "assetgen.py")
plugin = importlib.util.module_from_spec(spec); spec.loader.exec_module(plugin)
reg = json.load(open(root / "registry.json", encoding="utf-8"))
rows = []
for path in sorted((auth / "assetgen" / "runs").glob("*/run.md")):
    obj = json.loads(re.match(r"\A---json\s*\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S).group(1))
    ctx = Context(str(auth), reg, path.relative_to(auth).as_posix(), {}, None, {"authoring": auth})
    rows += [{"artifact": obj["id"], "check": r.check, "state": r.state, "reasons": r.reasons} for r in plugin.check(obj, ctx)]
print(json.dumps({"results": rows}))
EOF
got=$(for c in $plugin_checks; do printf '%s=%s ' "$c" "$(st AGEN-qp-icon-001 "$c")"; done)
[ "$got" = "$(for c in $plugin_checks; do printf '%s=PASS ' "$c"; done)" ] && ok "plugin called directly agrees on the complete run" || no "direct good run: $got" "$(cat "$TMP/err")"
case_() { # case_ RUN CHECK STATE REASON-SUBSTRING LABEL
  if [ "$(st "AGEN-$1" "$2")" = "$3" ] && why "AGEN-$1" "$2" | grep -qF -- "$4"; then ok "$5"
  else no "$5: $1 $2 = $(st "AGEN-$1" "$2")" "$(why "AGEN-$1" "$2")"; fi
}
gs_status() { sed -n '/^---json$/,/^---$/p' "$RUNS/$1/run.md" | sed '1d;$d' | jq -r .status; }
[ "$(gs_status qp-icon-001)/$(gs_status gs-clean-001)/$(gs_status gs-moved-001)" = proposed/proposed/proposed ] \
  && ok "workflow-style runs are proposed (missing work FAILS there; workflow-style still never does)" \
  || no "workflow-style run status: $(gs_status qp-icon-001)/$(gs_status gs-clean-001)/$(gs_status gs-moved-001)"
case_ qp-icon-001 gen-run-workflow-style WARN 'group: node' "legacy-template render (image-generate, no ui groups) on a proposed run: gen-run-workflow-style WARN naming the ungrouped nodes, never FAIL"
[ "$(st AGEN-gs-clean-001 gen-run-workflow-style)" = PASS ] && [ -z "$(why AGEN-gs-clean-001 gen-run-workflow-style)" ] \
  && ok "render of the clean template: gen-run-workflow-style PASS without reasons" \
  || no "clean render workflow-style: $(st AGEN-gs-clean-001 gen-run-workflow-style)" "$(why AGEN-gs-clean-001 gen-run-workflow-style)"
[ "$(st AGEN-qp-light-001 gen-run-workflow-style)" = PASS ] && [ -z "$(why AGEN-qp-light-001 gen-run-workflow-style)" ] \
  && ok "staged icon render: gen-run-workflow-style PASS without reasons" \
  || no "staged icon workflow-style: $(st AGEN-qp-light-001 gen-run-workflow-style)" "$(why AGEN-qp-light-001 gen-run-workflow-style)"
case_ gs-moved-001 gen-run-workflow-style WARN 'group: node 4 (ImageScale' "workflow.ui.json with a node moved outside every group on a proposed run: WARN naming the node, never FAIL"
case_ gs-badjson-001 gen-run-workflow-style WARN 'workflow.ui.json is not readable JSON' "unreadable workflow.ui.json: WARN"
case_ gs-noextra-001 gen-run-workflow-style WARN 'save-suffix: node 6 (SaveImage' "workflow.ui.json without extra.assetgen and an unsuffixed SaveImage: WARN, checked against the run's prefix"
if why AGEN-gs-noextra-001 gen-run-workflow-style | grep -q 'run prefix is unknown'; then
  no "gs-noextra-001: the quality check did not pass the run prefix" "$(why AGEN-gs-noextra-001 gen-run-workflow-style)"
else ok "gen-run-workflow-style passes the run's prefix (no 'run prefix is unknown' without extra.assetgen)"; fi
checks_of() { jq -r --arg a "AGEN-$1" '[.results[] | select(.artifact == $a) | .check + "=" + .state] | join(" ")' "$TMP/aq.json"; }
twin=$(checks_of qp-uitwin-001); noui=$(checks_of qp-noui-001)
[ "$(st AGEN-qp-uitwin-001 gen-run-workflow-style)" = WARN ] && [ -z "$(st AGEN-qp-noui-001 gen-run-workflow-style)" ] \
  && [ -n "$noui" ] && [ "$noui" = "${twin/ gen-run-workflow-style=WARN/}" ] \
  && ok "a run without workflow.ui.json gets no gen-run-workflow-style row; its other rows equal its twin's with the file" \
  || no "no workflow.ui.json: twin [$twin] noui [$noui]"
case_ qp-same-001 gen-run-prompt-review FAIL 'SAME_MODEL:claude-sonnet' "unmarked review by the author's model family: FAIL, names the explicit marker"
case_ qp-fallback-001 gen-run-prompt-review WARN 'same-model fallback' "explicit SAME_MODEL:<model> fallback: WARN, never PASS"
case_ qp-badmark-001 gen-run-prompt-review FAIL 'is not the prompt author' "SAME_MODEL marker on another model's review: FAIL"
case_ qp-tamper-001 gen-run-outputs FAIL 'sha256 on disk differs' "output bytes changed after the record: FAIL"
case_ qp-extra-001 gen-run-outputs FAIL 'outputs/second.png is not recorded' "unrecorded outputs/*.png: FAIL"
batch_front "$RUNS/qp-batch-001" | jq -e '.spec.trace.discarded | length == 1' >/dev/null \
  && ok "batch quality fixture records one discard" || no "batch quality fixture missing discard trace"
case_ qp-batch-001 gen-run-outputs PASS '' "manifested batch with a recorded discard: gen-run-outputs PASS"
case_ qp-batch-extra-001 gen-run-outputs FAIL 'outputs/unrecorded.png is not recorded' "batch with an unrecorded output: gen-run-outputs FAIL"
case_ qp-rejected-extra-001 gen-run-outputs FAIL 'outputs-rejected/unrecorded.png is not recorded' "unlisted rejected PNG: gen-run-outputs FAIL"
case_ qp-rejected-sha-001 gen-run-outputs FAIL 'sha256 on disk differs' "rejected PNG with changed bytes: gen-run-outputs FAIL"
case_ qp-qafail-001 gen-run-qa FAIL 'QA is FAIL' "QA not PASS on a proposed run: FAIL"
case_ qp-noqa-001 gen-run-qa FAIL 'qa.json is missing' "QA never run: FAIL"
case_ qp-prov-001 gen-run-provenance FAIL 'provenance.model is not recorded' "provenance without model on a proposed run: FAIL"
case_ qp-draft-001 gen-run-provenance WARN 'provenance.model is not recorded' "draft run: missing work is WARN (provenance)"
case_ qp-draft-001 gen-run-image-review WARN 'review-image.json is missing' "draft run: missing work is WARN (image review)"
case_ qp-draft-001 gen-run-prompt-review WARN 'is bound to prompt' "draft run: a stale prompt review is WARN"
case_ qp-norev-001 gen-run-prompt-review FAIL 'review-prompt.json is missing' "run.md claims a PASS review but review-prompt.json is gone: FAIL"
case_ qp-revdiff-001 gen-run-image-review FAIL 'differs from review-image.json (file: FAIL' "review file says FAIL while run.md says PASS: FAIL"
case_ qp-unbound-001 gen-run-prompt-review FAIL 'is bound to prompt None' "verdict without the prompt binding: FAIL on a proposed run"
case_ qp-staleprompt-001 gen-run-prompt-review FAIL 'is bound to prompt' "prompt changed after its review: FAIL"
case_ qp-staleprompt-001 gen-run-image-review FAIL 'is bound to prompt' "prompt changed after the image review: FAIL"
case_ qp-staleimg-001 gen-run-image-review FAIL 'bound to other outputs' "images changed after the image review: FAIL"
case_ qp-invalid-001 gen-run-image-review FAIL 'holds no JSON verdict' "review file without a verdict: FAIL"
case_ qp-qadisk-001 gen-run-qa FAIL 'differs from qa.json (FAIL)' "qa.json FAIL while run.md claims PASS: FAIL"
case_ qp-qacontra-001 gen-run-qa FAIL 'claims PASS but contradicts its own rows' "qa.json PASS with a failing row: FAIL"
case_ qp-qapart-001 gen-run-qa FAIL 'lacks the required check(s) png-corners' "qa.json PASS without a purpose-required check: FAIL"
case_ qp-qafringe-001 gen-run-qa FAIL 'lacks the required check(s) png-edge-fringe' "qa.json PASS without png-edge-fringe for an alpha purpose: FAIL (a required check)"
[ "$(jq -r '.purpose.data.qa.alpha' "$good/spec.json")" = required ] && [ "$(st AGEN-qp-icon-001 gen-run-qa)" = PASS ] \
  && [ "$(jq -r '[.results[] | select(.check == "png-edge-fringe") | .state] | unique | join(",")' "$good/qa.json")" = PASS ] \
  && ok "gen-run-qa PASS for an alpha purpose whose qa.json carries a PASS png-edge-fringe row" \
  || no "alpha purpose with png-edge-fringe: $(st AGEN-qp-icon-001 gen-run-qa)" "$(why AGEN-qp-icon-001 gen-run-qa)"
case_ qp-qana-001 gen-run-qa FAIL 'NOT_AVAILABLE does not grade PASS' "NOT_AVAILABLE QA never grades PASS"
case_ qp-qaspec-001 gen-run-qa FAIL 'spec.json purpose is not the purpose the run recorded' "spec.json purpose edited after the run: FAIL"
case_ qp-qapurp-001 gen-run-qa FAIL 'graded with another purpose qa block' "qa.json graded with an older purpose qa block: FAIL"
case_ qp-qasize-001 gen-run-qa FAIL 'graded for requested size' "requested size changed after QA: FAIL"
case_ qp-qastylewarn-001 gen-run-qa WARN 'style consistency outputs/qp-icon.png: style-palette WARN' "style-* WARN rows in a PASS qa.json stay WARN (soft signal), never FAIL"
[ "$(st AGEN-qp-qastylewarn-001 gen-run-qa)" = WARN ] && ! why AGEN-qp-qastylewarn-001 gen-run-qa | grep -q contradicts && ok "style-* WARN rows do not contradict a PASS qa.json" \
  || no "style WARN rows: $(st AGEN-qp-qastylewarn-001 gen-run-qa)" "$(why AGEN-qp-qastylewarn-001 gen-run-qa)"
case_ qp-stylebind-001 gen-run-image-review FAIL 'is not bound to the style lock' "image review bound to another style ref than spec.style_lock: stale, FAIL"
case_ qp-stylebindc-001 gen-run-claude-review WARN 'outputs and style lock' "Claude review without the style lock binding (style ref, anchors): WARN"
[ "$(st AGEN-qp-stylebind-001 gen-run-prompt-review)" = PASS ] && ok "style lock binding: the prompt review is unaffected" || no "stylebind prompt review: $(st AGEN-qp-stylebind-001 gen-run-prompt-review)"
case_ qp-qastylefail-001 gen-run-qa FAIL 'claims PASS but contradicts its own rows' "a style-* FAIL row in a PASS qa.json contradicts it: FAIL"
case_ qp-qastyleagree-001 gen-run-qa FAIL 'QA is FAIL' "a style-* FAIL row with a FAIL qa state: the run is not done (FAIL on a proposed run)"
case_ qp-qastyle-001 gen-run-qa FAIL 'graded with other style inputs (style, style_sha256' "style re-resolved at a new version with a fail palette rule, qa.json and output bytes kept: gen-run-qa FAIL as stale"
[ "$(st AGEN-qp-qastyle-001 gen-run-image-review)/$(st AGEN-qp-qastyle-001 gen-run-prompt-review)" = PASS/PASS ]   && ok "stale style QA is caught by gen-run-qa while the refreshed reviews are bound" || no "restyled reviews: $(st AGEN-qp-qastyle-001 gen-run-image-review)" "$(why AGEN-qp-qastyle-001 gen-run-image-review)"
! why AGEN-qp-qastyle2-001 gen-run-qa | grep -q 'other style inputs' && why AGEN-qp-qastyle2-001 gen-run-qa | grep -q 'QA is FAIL'   && ok "re-run qa after the style change: bound to the current style inputs (not stale), QA FAIL from the new rule" || no "restyled qa rerun" "$(why AGEN-qp-qastyle2-001 gen-run-qa)"
case_ qp-qanobind-001 gen-run-qa FAIL 'does not record the style inputs it graded with' "a PASS qa.json without style_binding (made before the binding): stale, FAIL"
case_ qp-noclaude-001 gen-run-claude-review WARN 'review-image-claude.json is missing' "no Claude visual review file: WARN"
[ "$(st AGEN-qp-noclaude-001 gen-run-image-review)" = PASS ] && ok "a missing Claude review leaves the Codex image review PASS" || no "noclaude image review: $(st AGEN-qp-noclaude-001 gen-run-image-review)"
case_ qp-claudeonly-001 gen-run-image-review FAIL 'review-image.json is missing' "a Claude PASS never replaces the missing Codex image review: FAIL"
[ "$(st AGEN-qp-claudeonly-001 gen-run-claude-review)" = PASS ] && ok "claude-only run: the Claude review itself grades PASS" || no "claudeonly claude review: $(st AGEN-qp-claudeonly-001 gen-run-claude-review)"
case_ qp-claudefail-001 gen-run-claude-review FAIL "Claude's visual review is FAIL (1 finding(s))" "Claude's own review FAIL on a proposed run: FAIL"
case_ qp-claudediff-001 gen-run-claude-review FAIL 'differs from review-image-claude.json (file: FAIL' "review-image-claude.json contradicting run.md: FAIL"
case_ qp-claudestale-001 gen-run-claude-review WARN 'not bound to the current prompt' "unbound Claude review: WARN"
case_ qp-claudeby-001 gen-run-claude-review WARN 'is by codex, not claude' "review-image-claude.json by another model: WARN"
# review tiers: light (icon) without the Claude review PASS; a present file graded as in the full tier; anchors -> full
[ "$(st AGEN-qp-light-001 gen-run-claude-review)/$(st AGEN-qp-light-001 gen-run-image-review)/$(st AGEN-qp-light-001 gen-run-prompt-review)" = PASS/PASS/PASS ] \
  && ok "light tier (icon) without review-image-claude.json: Claude review PASS, Codex reviews PASS" \
  || no "light run: $(st AGEN-qp-light-001 gen-run-claude-review)/$(st AGEN-qp-light-001 gen-run-image-review)/$(st AGEN-qp-light-001 gen-run-prompt-review)" \
        "$(why AGEN-qp-light-001 gen-run-claude-review; why AGEN-qp-light-001 gen-run-image-review)"
case_ qp-lightinv-001 gen-run-claude-review WARN 'holds no JSON verdict' "light tier: an invalid review-image-claude.json is still WARN"
case_ qp-lightstale-001 gen-run-claude-review WARN 'not bound to the current prompt' "light tier: an unbound review-image-claude.json is still WARN"
case_ qp-lightanchor-001 gen-run-claude-review WARN 'review-image-claude.json is missing' "light purpose with style-lock anchors is full: missing Claude review WARN"
tierkeys() { jq -r '[paths | .[] | strings | select(test("tier"; "i"))] | unique | join(",")'; }
fmj() { sed -n '/^---json$/,/^---$/p' "$1/run.md" | sed '1d;$d'; }
lk="$(fmj "$light" | tierkeys)|$(tierkeys < "$light/spec.json")|$(fmj "$RUNS/qp-noclaude-001" | tierkeys)"
[ "$lk" = "||" ] && [ "$(fmj "$light" | jq -r .spec.purpose.id)" = icon ] && [ "$(st AGEN-qp-noclaude-001 gen-run-claude-review)" = WARN ] \
  && ok "no tier is recorded (run.md, spec.json); a full-tier run (sprite-2d) without the Claude review keeps its WARN" \
  || no "tier fields: $lk, noclaude $(st AGEN-qp-noclaude-001 gen-run-claude-review)"
python3 -B - "$ROOT" > "$TMP/rt" 2>&1 <<'EOF'
import importlib.util, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts" / "checks"))
spec = importlib.util.spec_from_file_location("assetgen_plugin", root / "scripts" / "checks" / "domains" / "assetgen.py")
plugin = importlib.util.module_from_spec(spec); spec.loader.exec_module(plugin)
def check(cond, label, detail=""):
    print(("ok " if cond else "no ") + label + ("" if cond else " :: " + str(detail)[:400]))
def tier(*args):
    try:
        return plugin.review_tier(*args)
    except Exception as exc:  # review_tier never raises
        return "raised %r" % exc
def run(pid, **extra):
    s = {"purpose": {"id": pid}}
    s.update(extra)
    return s
for pid in ("icon", "ui-element", "texture-tileable"):
    check(tier(run(pid)) == "light", "review_tier: %s is light" % pid, tier(run(pid)))
for pid in ("sprite-2d", "concept-2d", "no-such-purpose"):
    check(tier(run(pid)) == "full", "review_tier: %s is full" % pid, tier(run(pid)))
for label, s in (("no purpose", {}), ("purpose without id", {"purpose": {}}), ("purpose not an object", {"purpose": "icon"}),
                 ("spec None", None), ("spec a list", [])):
    check(tier(s) == "full", "review_tier: %s is full" % label, tier(s))
anchored = run("icon", style_lock={"references": [{"anchor_id": "a", "sha256": "0" * 64}]})
check(tier(anchored) == "full", "review_tier: icon with a selected style-lock anchor is full", tier(anchored))
check(tier(run("icon", style_lock={"references": []})) == "light", "review_tier: icon with a style lock but no anchors stays light",
      tier(run("icon", style_lock={"references": []})))
for label, table in (("{}", {}), ("purposes a list", {"purposes": []}), ("unknown value", {"purposes": {"icon": "weird"}}),
                     ("a list", []), ("a string", "light")):
    check(tier(run("icon"), table) == "full", "review_tier: malformed table (%s) is full" % label, tier(run("icon"), table))
check(tier(run("sprite-2d"), {"purposes": {"sprite-2d": "light"}}) == "light", "review_tier: an explicit table is used",
      tier(run("sprite-2d"), {"purposes": {"sprite-2d": "light"}}))
print("end")
EOF
while IFS= read -r line; do
  line=${line%$'\r'}
  case "$line" in "ok "*) ok "${line#ok }" ;; "no "*) no "${line#no }" ;; end) ;; *) no "review_tier: unexpected output" "$line" ;; esac
done < "$TMP/rt"
tr -d '\r' < "$TMP/rt" | grep -qx end && ok "review_tier cases ran to the end" || no "review_tier cases stopped early" "$(tail -5 "$TMP/rt")"
RTD="$ROOT/scripts/assetgen/data/review-tiers.json"
rt_bad=$(jq -r '.purposes | to_entries[] | select(.value != "light" and .value != "full") | .key' "$RTD" 2>&1)
rt_missing=$(for p in $(jq -r '.purposes | keys[]' "$RTD" 2>/dev/null); do [ -f "$ROOT/templates/assetgen/purposes/$p.json" ] || printf '%s ' "$p"; done)
[ "$(jq -r '.schema + " " + .default' "$RTD" 2>/dev/null)" = "rpg-factory.assetgen-review-tiers/1 full" ] && [ -z "$rt_bad$rt_missing" ] \
  && [ "$(jq -r '[.purposes | to_entries[] | select(.value == "light") | .key] | sort | join(",")' "$RTD")" = "icon,texture-tileable,ui-element" ] \
  && ok "review-tiers.json: schema id, default full, light = icon, texture-tileable, ui-element, every listed purpose exists" \
  || no "review-tiers.json: bad values '$rt_bad', unknown purposes '$rt_missing'" "$(cat "$RTD" 2>&1)"
case_ qp-tool-001 gen-run-provenance FAIL 'provenance.tool must be comfyui' "provenance tool other than comfyui: FAIL"
case_ qp-ref-001 gen-run-refs FAIL "style 'no-such-style' does not resolve" "unresolvable style ref: FAIL"
case_ qp-drift-001 gen-run-refs WARN 'changed since the run' "template content changed since the run: WARN (the record keeps what was used)"
case_ qp-prompt-001 gen-run-refs FAIL 'prompt.md differs' "prompt.md edited after the record: FAIL"
[ "$(st AGEN-somewhere-else-001 gen-run-location)" = FAIL ] && why AGEN-somewhere-else-001 gen-run-location | grep -qF 'id must be AGEN-qp-where-001' \
  && ok "id that does not match the run directory: FAIL" || no "location: $(why AGEN-somewhere-else-001 gen-run-location)"
case_ qp-escape-001 gen-run-outputs FAIL 'not a path inside the run directory' "output path escaping the run directory: FAIL"
case_ qp-preview-001 gen-run-outputs PASS '' "a preview file under previews/ is not an unrecorded output: PASS"
case_ qp-precord-001 gen-run-outputs FAIL 'is not under outputs/' "a recorded previews/ path is never a deliverable: FAIL"
case_ qp-rubric-001 gen-run-prompt-review FAIL 'bound to other requirements' "purpose re-resolved with a stricter rubric after the prompt review: FAIL"
case_ qp-rubric-001 gen-run-image-review FAIL 'bound to other requirements' "purpose re-resolved with a stricter rubric after the image review: FAIL"
[ "$(st AGEN-qp-rubric-001 gen-run-qa)/$(st AGEN-qp-rubric-001 gen-run-outputs)" = "PASS/PASS" ] \
  && ok "re-resolved run: qa and manifest re-run are consistent, only the reviews are stale" \
  || no "rubric run qa/outputs: $(st AGEN-qp-rubric-001 gen-run-qa)/$(st AGEN-qp-rubric-001 gen-run-outputs)" "$(why AGEN-qp-rubric-001 gen-run-qa)"
case_ qp-rsize-001 gen-run-image-review FAIL 'bound to other requirements' "render --param size after the image review: FAIL (requested size is bound)"
case_ qp-wfprompt-001 gen-run-provenance FAIL 'sends another prompt than the recorded one' "workflow.json prompt edited after the record: provenance FAIL"
case_ qp-wfprompt-001 gen-run-image-review FAIL 'bound to other requirements' "workflow.json prompt edited after the image review: FAIL (prompts are bound)"
case_ qp-rqual-001 gen-run-image-review FAIL 'bound to other requirements' "render --param quality=low after the image review: FAIL (every generation input is bound)"
case_ qp-rejbind-001 gen-run-prompt-review FAIL 'bound to other requirements' "a relevant rejection added to spec.style_lock after the prompt review: FAIL (rejections are bound)"
case_ qp-rejbind-001 gen-run-image-review FAIL 'bound to other requirements' "a relevant rejection added to spec.style_lock after the image review: FAIL"
rs="$RUNS/qp-rsize-001"; rs_params=$(sed -n '/^---json$/,/^---$/p' "$rs/run.md" | sed '1d;$d' | jq -r .spec.params.size)
case_ qp-rsize-001 gen-run-prompt-review FAIL 'bound to other requirements' "render --param size after the prompt review: FAIL (the review is bound to the params it was shown)"
case_ qp-rqual-001 gen-run-prompt-review FAIL 'bound to other requirements' "render --param quality=low after the prompt review: FAIL"
[ "$rs_params" = 1536x1024 ] && [ "$(jq -r .params.size "$rs/spec.json")" != 1536x1024 ] && [ "$(st AGEN-qp-rsize-001 gen-run-provenance)" = PASS ] \
  && ok "run.md spec.params records the rendered size 1536x1024 (spec.json keeps its own), provenance PASS" \
  || no "rsize params: $rs_params, provenance $(st AGEN-qp-rsize-001 gen-run-provenance)" "$(why AGEN-qp-rsize-001 gen-run-provenance)"
ptitle() { jq -r '[.[] | select(.class_type == "PrimitiveStringMultiline") | ._meta.title] | join(",")' "$1/workflow.json"; }
rcb() { AG review-cmd --phase prompt --run "$1" --no-write --json | jq -r .binding.requirements_sha256; }
[ "$(ptitle "$rs")" = "Prompt (Claude, Codex review STALE)" ] && [ "$(rcb "$rs")" != "$(jq -r .requirements_sha256 "$rs/review-prompt.json")" ] \
  && ok "render --param size after the prompt review: render title STALE and review-cmd hands out another binding, as the plugin grades" \
  || no "rsize consistency: title $(ptitle "$rs"), review-cmd $(rcb "$rs"), verdict $(jq -r .requirements_sha256 "$rs/review-prompt.json")"
rq="$RUNS/qp-rsame-001"
[ "$(st AGEN-qp-rsame-001 gen-run-prompt-review)/$(st AGEN-qp-rsame-001 gen-run-image-review)/$(st AGEN-qp-rsame-001 gen-run-provenance)" = PASS/PASS/PASS ] \
  && [ "$(ptitle "$rq")" = "Prompt (Claude, Codex review PASS)" ] && [ "$(rcb "$rq")" = "$(jq -r .requirements_sha256 "$rq/review-prompt.json")" ] \
  && ok "render repeating the reviewed --param size: reviews stay bound (plugin PASS, render title PASS, review-cmd binding equal)" \
  || no "rsame: $(st AGEN-qp-rsame-001 gen-run-prompt-review)/$(st AGEN-qp-rsame-001 gen-run-image-review)/$(st AGEN-qp-rsame-001 gen-run-provenance), title $(ptitle "$rq")" "$(why AGEN-qp-rsame-001 gen-run-prompt-review)"
case_ qp-tsize-001 gen-run-provenance FAIL 'spec.params differ from the rendered params (workflow.json over spec.json) in size' "run.md spec.params size tampered to 1x1: FAIL (never substituted from spec.json)"
case_ qp-tmodel-001 gen-run-provenance FAIL 'in background, model' "run.md spec.params with an invented model and background: FAIL"
[ "$(st AGEN-qp-tsize-001 gen-run-prompt-review)/$(st AGEN-qp-tsize-001 gen-run-image-review)" = PASS/PASS ] \
  && ok "tampered run.md params: the reviews stay bound to the rendered params they were shown; only provenance FAILs" \
  || no "tsize reviews: $(st AGEN-qp-tsize-001 gen-run-prompt-review)/$(st AGEN-qp-tsize-001 gen-run-image-review)"
got=$(for c in $plugin_checks; do printf '%s=%s ' "$c" "$(st AGEN-qp-edit-001 "$c")"; done)
[ "$got" = "$(for c in $plugin_checks; do printf '%s=PASS ' "$c"; done)" ] && ok "image-edit run with its reference kept in references/: every plugin check PASS"   || no "image-edit good run: $got" "$(jq -c '.results[] | select(.artifact == "AGEN-qp-edit-001" and .state != "PASS")' "$TMP/aq.json")"
case_ qp-eswap-001 gen-run-image-review FAIL 'bound to other requirements' "image-edit re-rendered with another reference after the image review: FAIL"
case_ qp-ebytes-001 gen-run-image-review FAIL 'bound to other requirements' "reference image bytes changed after the image review: FAIL"
case_ qp-enoref-001 gen-run-provenance FAIL 'is not kept as references/ref-a.png' "image-edit reference not kept in the run directory: FAIL"
case_ qa-malformed-001 gen-run-qa FAIL 'purpose qa block is malformed' "malformed purpose qa block in spec.json: gen-run-qa FAIL, no traceback"
[ "$(st AGEN-qp-fallback-001 gen-run-outputs)/$(st AGEN-qp-tamper-001 gen-run-prompt-review)" = "PASS/PASS" ] \
  && ok "cases stay independent (a fallback run's outputs PASS, a tampered run's review PASS)" \
  || no "independence: $(st AGEN-qp-fallback-001 gen-run-outputs)/$(st AGEN-qp-tamper-001 gen-run-prompt-review)"
python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$AUTH" --registry "$ROOT/registry.json" > "$TMP/lint" 2>&1
grep -q '^PASS AGEN-qp-icon-001$' "$TMP/lint" && grep -q '^PASS AGEN-iron-sword-icon-001$' "$TMP/lint" \
  && ok "artifact-lint passes manifest-produced run.md (gen-run kind schema, envelope, lifecycle)" || no "artifact-lint run.md" "$(grep -v '^PASS' "$TMP/lint")"
grep -q '^FAIL AGEN-qp-escape-001 .*does not match pattern' "$TMP/lint" && ok "kind schema rejects an output path outside outputs/" \
  || no "schema outputs path" "$(grep qp-escape "$TMP/lint")"
T2="$TMP/tmpl"; mkdir -p "$T2" && cp "$ROOT/templates/assetgen/gen-run.md" "$T2/" && git init -q "$T2"
python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T2" --registry "$ROOT/registry.json" | grep -q '^PASS AGEN-example-icon-001$' \
  && ok "kind template templates/assetgen/gen-run.md is a schema-valid draft" || no "gen-run template lint"

echo "-- local and hybrid provenance (UNTESTED on RTX 5060)"
cp "$ROOT/tests/fixtures/assetgen/local/hybrid-template.json" "$GL/templates/hybrid-provenance.json"
cp "$ROOT/tests/fixtures/assetgen/local/literal-seed-template.json" "$GL/templates/literal-seed.json"
python3 -B - "$ROOT" > "$TMP/local-unit" 2>&1 <<'EOF'
import copy, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'assetgen'))
import runfiles as r
root = sys.argv[1]
t = json.load(open(os.path.join(root, 'tests/fixtures/assetgen/local/hybrid-template.json'), encoding='utf-8'))
golden = json.load(open(os.path.join(root, 'tests/fixtures/assetgen/golden/icon--image-generate.json'), encoding='utf-8'))
spec = {'params': {'seed': 123}, 'template': {'data': t}}
def old_generation_inputs(workflow, spec, locate=None):
    if isinstance(workflow, dict) and any(isinstance(n, dict) and n.get("class_type") == "NineRouterImage"
                                          for n in workflow.values()):
        graph = {}
        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = dict(node["inputs"]) if isinstance(node.get("inputs"), dict) else {}
            graph[str(nid)] = {"class_type": node.get("class_type"), "inputs": inputs}
        refs = {}
        for name in r.reference_names(workflow):
            try:
                refs[name] = r._file_sha256(locate(os.path.basename(name)) if locate else None)
            except (OSError, TypeError, ValueError):
                refs[name] = None
        out = {"graph": graph, "references": refs}
        lock = r.style_lock_binding(spec)
        if lock is not None:
            out["anchors"] = [{"anchor_id": x.get("anchor_id"), "sha256": x.get("sha256")} for x in r.style_lock_references(spec)]
        return out
    params = spec.get("params") if isinstance(spec, dict) else None
    return params if isinstance(params, dict) else {}
def check(label, f):
    try:
        assert f()
        print('ok ' + label)
    except Exception as e:
        print('no ' + label + ' | ' + repr(e))
check('generation inputs bind local graphs and preserve legacy hashes', lambda: set(r.generation_inputs({'9': {'class_type': 'KSampler'}}, spec)) == {'graph', 'references'} and all(r.generation_inputs(g, spec) == old_generation_inputs(g, spec) and r._canonical_sha256(r.generation_inputs(g, spec)) == r._canonical_sha256(old_generation_inputs(g, spec)) for g in (golden, {'1': {'class_type': 'SaveImage'}})))
def prompts():
    g={'1': {'class_type':'PrimitiveString','inputs':{'value':'hello'}}, '2': {'class_type':'PrimitiveStringMultiline','inputs':{'value':'world'}}, '3': {'class_type':'CLIPTextEncode','inputs':{'text':['1',0]}}, '4': {'class_type':'CLIPTextEncodeSDXL','inputs':{'text_g':['1',0], 'text_l':['2',0]}}, '5': {'class_type':'CLIPTextEncode','inputs':{'text':'literal'}}, '6': {'class_type':'CLIPTextEncode','inputs':{'text':['2',0]}}, '7': {'class_type':'ControlNetApplyAdvanced','inputs':{'positive':['3',0], 'negative':['6',0]}}, '8': {'class_type':'KSampler','inputs':{'positive':['7',0], 'negative':['7',1]}}, '9': {'class_type':'CLIPTextEncode','inputs':{'text':['2',0]}}, '10': {'class_type':'KSampler','inputs':{'negative':['9',0]}}}
    return r.workflow_prompts(g) == ['hello','hello','world'] and all(isinstance(r.workflow_prompts(x), list) for x in (None, [], {'x': None}, {'x': {'class_type':'KSampler','inputs':{'negative':['x',0]}}}))
check('CLIP prompts include linked positive text and exclude literals and negative-only paths', prompts)
def local():
    wf=copy.deepcopy(t['workflow']); wf['9']['inputs']['seed']=123
    a=r.local_generation(wf,spec); b=r.local_generation(wf,spec,{'checkpoints/sdxl.safetensors':'a'*64,'loras/style.safetensors':'b'*64})
    literal=copy.deepcopy(spec); literal['template']['data']['workflow']['9']['inputs']['seed']=123
    return (a['models'][0]['name']=='sdxl.safetensors' and not a['models'][0]['verified'] and a['loras'][0]['strength_model']==0.8 and a['loras'][0]['strength_clip']==0.7 and a['samplers'][0] == {'node':'9','class_type':'KSampler','seed':123,'seed_param':'seed','sampler_name':'dpmpp_2m','scheduler':'karras','steps':20,'cfg':5.5,'denoise':0.45} and a['requires_sha256']==r._canonical_sha256(t['requires']) and all(x['verified'] for x in b['models']+b['loras']) and r.local_generation(golden,spec) is None and r.local_generation(wf,literal)['samplers'][0]['seed_param'] is None)
check('local record shape, cache, requires and seed provenance', local)
def linked_seed():
    wf = copy.deepcopy(t['workflow']); linked_spec = copy.deepcopy(spec)
    wf['9']['inputs']['seed'] = ['12', 0]; wf['12'] = {'inputs': {'value': 123}}
    linked_spec['template']['data']['workflow']['9']['inputs']['seed'] = ['12', 0]
    linked_spec['template']['data']['workflow']['12'] = {'inputs': {'value': '{{seed}}'}}
    sampler = r.local_generation(wf, linked_spec)['samplers'][0]
    return sampler['seed'] == 123 and sampler['seed_param'] == 'seed'
check('linked rendered seed records its value and parameter', linked_seed)
def local_model():
    import assetgen, tempfile
    with tempfile.TemporaryDirectory() as run_dir:
        with open(os.path.join(run_dir, 'workflow.json'), 'w', encoding='utf-8') as f:
            json.dump({'10': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'second.safetensors'}},
                       '4': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'first.safetensors'}},
                       '9': {'class_type': 'KSampler', 'inputs': {}}}, f)
        return assetgen.workflow_model(run_dir, {'params': {'model': 'fallback'}}) == 'first.safetensors'
check('local-only workflow provenance uses the first checkpoint', local_model)
EOF
while IFS= read -r line; do
  case "$line" in "ok "*) ok "${line#ok }" ;; "no "*) no "${line#no }" ;; *) no "local unit unexpected output" "$line" ;; esac
done < "$TMP/local-unit"
[ "$(grep -c '^ok ' "$TMP/local-unit")" -eq 5 ] || no "local unit cases stopped early" "$(cat "$TMP/local-unit")"

localrun="$RUNS/local-hybrid-001"
local_step() { # Report setup failures so a refused render or manifest cannot make a case vacuous.
  local label="$1" out rc; shift
  out=$("$@" 2>&1); rc=$?
  [ "$rc" -eq 0 ] || no "$label" "$out"
}
mkrun local-hybrid-001 sprite-2d --style stylized-painterly --template hybrid-provenance --authoring "$AUTH"
local_step 'local hybrid render' AG render --run "$localrun" --param seed=123
cp "$FX/icon-ok.png" "$localrun/outputs/local.png"; local_step 'local hybrid qa' AG qa --run "$localrun"
bound "$localrun" prompt PASS codex > "$localrun/review-prompt.json"; bound "$localrun" image PASS codex > "$localrun/review-image.json"
bound "$localrun" image PASS claude > "$localrun/review-image-claude.json"
ASSETGEN_MODEL_HASHES="$TMP/missing-hashes.json" local_step 'local hybrid unverified manifest' AG manifest --run "$localrun"
cp "$localrun/run.md" "$TMP/local-unverified.md"
ASSETGEN_MODEL_HASHES="$ROOT/tests/fixtures/assetgen/local/model-hashes.json" local_step 'local hybrid verified manifest' AG manifest --run "$localrun"
cp "$localrun/run.md" "$TMP/local-verified.md"
# Preserve independent variants for each plugin check.
for id in local-cached-001 local-prompt-001 local-cfg-001 local-missing-001 local-hash-001 local-stale-001; do
  cp -R "$localrun" "$RUNS/$id"; rm "$RUNS/$id/run.md"
  python3 -B -c 'import json, sys; p = sys.argv[1]; s = json.load(open(p)); s["params"]["filename_prefix"] = "assetgen/" + sys.argv[2]; json.dump(s, open(p, "w"))' "$RUNS/$id/spec.json" "$id"
  ASSETGEN_MODEL_HASHES="$TMP/missing-hashes.json" local_step "$id manifest" AG manifest --run "$RUNS/$id"
done
ASSETGEN_MODEL_HASHES="$ROOT/tests/fixtures/assetgen/local/model-hashes.json" local_step 'local cached manifest' AG manifest --run "$RUNS/local-cached-001"
jq ' .["11"] = {"class_type":"PrimitiveString", "inputs":{"value":"another prompt"}} | .["6"].inputs.text = ["11",0]' "$RUNS/local-prompt-001/workflow.json" > "$TMP/wf" && mv "$TMP/wf" "$RUNS/local-prompt-001/workflow.json"
fmset "$RUNS/local-cfg-001" 'obj["spec"]["generation"]["local"]["samplers"][0]["cfg"] = 99'
fmset "$RUNS/local-missing-001" 'del obj["spec"]["generation"]["local"]'
fmset "$RUNS/local-hash-001" 'obj["spec"]["generation"]["local"]["models"][0]["verified"] = True'
stale="$RUNS/local-stale-001"
local_step 'local stale initial render' AG render --run "$stale" --param seed=123
local_step 'local stale qa' AG qa --run "$stale"
bound "$stale" prompt PASS codex > "$stale/review-prompt.json" || no 'local stale prompt binding'
bound "$stale" image PASS codex > "$stale/review-image.json" || no 'local stale image binding'
bound "$stale" image PASS claude > "$stale/review-image-claude.json" || no 'local stale Claude binding'
local_step 'local stale changed render' AG render --run "$stale" --param seed=456
ASSETGEN_MODEL_HASHES="$TMP/missing-hashes.json" local_step 'local stale manifest' AG manifest --run "$stale"
literal="$RUNS/local-literal-001"; mkrun local-literal-001 sprite-2d --style stylized-painterly --template literal-seed --authoring "$AUTH"
local_step 'local literal render' AG render --run "$literal" --param seed=123
cp "$FX/icon-ok.png" "$literal/outputs/local.png"; local_step 'local literal qa' AG qa --run "$literal"
bound "$literal" prompt PASS codex > "$literal/review-prompt.json"; bound "$literal" image PASS codex > "$literal/review-image.json"
ASSETGEN_MODEL_HASHES="$TMP/missing-hashes.json" local_step 'local literal manifest' AG manifest --run "$literal"
# Engine notes: pose and depth preprocessor models (annotators kind) and the KSamplerAdvanced form of the hybrid fixture
# get full provenance runs; both are also checked below against the unverified-hash path.
LOCALFX="$ROOT/tests/fixtures/assetgen/local"
cp "$LOCALFX/hybrid-advanced-template.json" "$GL/templates/hybrid-advanced.json"
cp "$LOCALFX/annotator-template.json" "$GL/templates/annotator-provenance.json"
local_run() { # local_run RUN-ID TEMPLATE-ID HASH-CACHE: a rendered, reviewed and manifested hybrid run
  local id="$1" tmpl="$2" cache="$3" d="$RUNS/$1"
  mkrun "$id" sprite-2d --style stylized-painterly --template "$tmpl" --authoring "$AUTH"
  local_step "$id render" AG render --run "$d" --param seed=123
  cp "$FX/icon-ok.png" "$d/outputs/local.png"; local_step "$id qa" AG qa --run "$d"
  bound "$d" prompt PASS codex > "$d/review-prompt.json"; bound "$d" image PASS codex > "$d/review-image.json"
  bound "$d" image PASS claude > "$d/review-image-claude.json"
  ASSETGEN_MODEL_HASHES="$cache" local_step "$id manifest" AG manifest --run "$d"
}
local_run local-adv-001 hybrid-advanced "$LOCALFX/model-hashes.json"
local_run local-annot-001 annotator-provenance "$LOCALFX/model-hashes-annotators.json"
local_run local-annot-unverified-001 annotator-provenance "$TMP/missing-hashes.json"
for id in local-adv-prompt-001 local-adv-cfg-001; do
  cp -R "$RUNS/local-adv-001" "$RUNS/$id"; rm "$RUNS/$id/run.md"
  python3 -B -c 'import json, sys; p = sys.argv[1]; s = json.load(open(p)); s["params"]["filename_prefix"] = "assetgen/" + sys.argv[2]; json.dump(s, open(p, "w"))' "$RUNS/$id/spec.json" "$id"
  ASSETGEN_MODEL_HASHES="$LOCALFX/model-hashes.json" local_step "$id manifest" AG manifest --run "$RUNS/$id"
done
jq ' .["11"] = {"class_type":"PrimitiveString", "inputs":{"value":"another prompt"}} | .["6"].inputs.text = ["11",0]' "$RUNS/local-adv-prompt-001/workflow.json" > "$TMP/wf" && mv "$TMP/wf" "$RUNS/local-adv-prompt-001/workflow.json"
fmset "$RUNS/local-adv-cfg-001" 'obj["spec"]["generation"]["local"]["samplers"][0]["cfg"] = 99'
cp -R "$RUNS/local-annot-001" "$RUNS/local-annot-drop-001"; rm "$RUNS/local-annot-drop-001/run.md"
python3 -B -c 'import json, sys; p = sys.argv[1]; s = json.load(open(p)); s["params"]["filename_prefix"] = "assetgen/local-annot-drop-001"; json.dump(s, open(p, "w"))' "$RUNS/local-annot-drop-001/spec.json"
ASSETGEN_MODEL_HASHES="$LOCALFX/model-hashes-annotators.json" local_step 'local-annot-drop-001 manifest' AG manifest --run "$RUNS/local-annot-drop-001"
fmset "$RUNS/local-annot-drop-001" 'obj["spec"]["generation"]["local"]["models"] = [m for m in obj["spec"]["generation"]["local"]["models"] if m["kind"] != "annotators"]'
cp "$TMP/local-unverified.md" "$localrun/run.md"
python3 -B - "$ROOT" "$AUTH" > "$TMP/aq.json" 2> "$TMP/err" <<'EOF'
import importlib.util, json, re, sys
from pathlib import Path
root, auth = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
sys.path.insert(0, str(root / 'scripts' / 'checks'))
from domains._api import Context
s = importlib.util.spec_from_file_location('assetgen_plugin', root / 'scripts/checks/domains/assetgen.py')
p = importlib.util.module_from_spec(s); s.loader.exec_module(p)
reg = json.load(open(root / 'registry.json', encoding='utf-8')); rows = []
for path in sorted((auth / 'assetgen/runs').glob('*/run.md')):
    obj = json.loads(re.match(r'\A---json\s*\n(.*?)\n---', path.read_text(encoding='utf-8'), re.S).group(1))
    ctx = Context(str(auth), reg, path.relative_to(auth).as_posix(), {}, None, {'authoring': auth})
    rows += [{'artifact': obj['id'], 'check': x.check, 'state': x.state, 'reasons': x.reasons} for x in p.check(obj, ctx)]
print(json.dumps({'results':rows}))
EOF
case_ local-stale-001 gen-run-image-review FAIL 'bound to other requirements' 'local seed change invalidates image review binding'
case_ local-hybrid-001 gen-run-provenance WARN 'sha256 unverified' 'local unverified hashes warn'
python3 -B - "$TMP/local-unverified.md" "$TMP/local-verified.md" <<'EOF' > "$TMP/local-record"
import json, re, sys
def read(p):
    s=open(p,encoding='utf-8').read(); return json.loads(re.match(r'\A---json\s*\n(.*?)\n---',s,re.S).group(1)),s
a, text=read(sys.argv[1]); b,_=read(sys.argv[2]); x=a['spec']['generation']['local']; y=b['spec']['generation']['local']
assert x['models'][0]['name']=='sdxl.safetensors' and x['loras'][0]['name']=='style.safetensors' and x['samplers'][0]['seed']==123 and x['samplers'][0]['cfg']==5.5
assert all(not v['verified'] and v['sha256'] is None for v in x['models']+x['loras'])
assert [v['sha256'] for v in y['models']+y['loras']]==['a'*64,'b'*64] and all(v['verified'] for v in y['models']+y['loras'])
assert 'Local stage (UNTESTED on RTX 5060)' in text
EOF
[ $? -eq 0 ] && ok "local manifest records models, LoRA, sampler, cache and untested body" || no "local manifest record" "$(cat "$TMP/local-record")"
case_ local-cached-001 gen-run-provenance PASS '' 'cache verifies all model hashes and provenance passes'
case_ local-prompt-001 gen-run-provenance FAIL 'sends another prompt than the recorded one' 'CLIP prompt mismatch fails provenance'
case_ local-cfg-001 gen-run-provenance FAIL 'spec.generation.local differs' 'tampered sampler fails provenance'
case_ local-missing-001 gen-run-provenance FAIL 'records no spec.generation.local' 'missing local record fails provenance'
case_ local-hash-001 gen-run-provenance FAIL 'claims a verified sha256 it does not carry' 'invalid verified hash fails provenance'
case_ local-literal-001 gen-run-provenance FAIL 'seed is not a rendered param' 'literal seed fails provenance'
case_ local-annot-001 gen-run-provenance PASS '' 'annotator models (pose and depth) with a cached hash pass provenance'
case_ local-annot-unverified-001 gen-run-provenance WARN 'annotators/depth_anything_vitl14.pth sha256 unverified' 'an annotator model without a cached hash warns like the other local model kinds'
case_ local-annot-drop-001 gen-run-provenance FAIL 'spec.generation.local differs from workflow.json in models' 'a record that omits the annotator models fails provenance'
case_ local-adv-001 gen-run-provenance PASS '' 'KSamplerAdvanced form passes provenance with a cached hash (same as the KSampler form)'
case_ local-adv-prompt-001 gen-run-provenance FAIL 'sends another prompt than the recorded one' 'KSamplerAdvanced: CLIP prompt mismatch fails provenance like KSampler'
case_ local-adv-cfg-001 gen-run-provenance FAIL 'spec.generation.local differs' 'KSamplerAdvanced: tampered sampler fails provenance like KSampler'
python3 -B - "$RUNS/local-annot-001/run.md" "$RUNS/local-annot-unverified-001/run.md" "$RUNS/local-adv-001/run.md" "$RUNS/local-cached-001/run.md" > "$TMP/local-engine-record" 2>&1 <<'EOF'
import json, re, sys
def local(p):
    s = open(p, encoding='utf-8').read()
    return json.loads(re.match(r'\A---json\s*\n(.*?)\n---', s, re.S).group(1))['spec']['generation']['local']
annot, bare, adv, plain = (local(p) for p in sys.argv[1:5])
rows = [(m['node'], m['class_type'], m['kind'], m['name'], m['sha256'], m['verified']) for m in annot['models']]
assert rows == [('4', 'CheckpointLoaderSimple', 'checkpoints', 'sdxl.safetensors', 'a' * 64, True),
                ('11', 'DepthAnythingPreprocessor', 'annotators', 'depth_anything_vitl14.pth', 'c' * 64, True),
                ('12', 'DWPosePreprocessor', 'annotators', 'yolox_l.onnx', 'd' * 64, True),
                ('12', 'DWPosePreprocessor', 'annotators', 'dw-ll_ucoco_384.onnx', 'e' * 64, True)], rows
assert [(m['kind'], m['verified'], m['sha256']) for m in bare['models'] if m['kind'] == 'annotators'] == [('annotators', False, None)] * 3
assert [x['name'] for x in annot['loras']] == [x['name'] for x in bare['loras']] == ['style.safetensors'] and annot['requires_sha256'] != plain['requires_sha256']
# the KSamplerAdvanced record equals the KSampler one except class_type and the denoise it does not have
a, p = adv['samplers'][0], plain['samplers'][0]
assert a['class_type'] == 'KSamplerAdvanced' and a['denoise'] is None and p['denoise'] == 0.45, (a, p)
assert {k: v for k, v in a.items() if k not in ('class_type', 'denoise')} == {k: v for k, v in p.items() if k not in ('class_type', 'denoise')}, (a, p)
assert a['seed'] == 123 and a['seed_param'] == 'seed'
assert adv['models'] == plain['models'] and adv['loras'] == plain['loras']
print('ok')
EOF
grep -qx ok "$TMP/local-engine-record" && ok "manifest records annotator models under kind annotators with their hashes and the KSamplerAdvanced sampler row like the KSampler row" \
  || no "local engine record" "$(cat "$TMP/local-engine-record")"
! grep -q '"local"\|Local stage' "$good/run.md" && [ "$(st AGEN-qp-icon-001 gen-run-provenance)" = PASS ] && ok 'old run retains provenance PASS without local record' || no 'old run changed' "$(why AGEN-qp-icon-001 gen-run-provenance)"
python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$AUTH" --registry "$ROOT/registry.json" > "$TMP/local-lint" 2>&1
grep -q '^PASS AGEN-local-hybrid-001$' "$TMP/local-lint" && ok 'hybrid manifest passes artifact schema lint' || no 'hybrid artifact lint' "$(grep 'AGEN-local-hybrid-001' "$TMP/local-lint")"

echo "-- engine notes: annotator model kind, KSamplerAdvanced like KSampler, lint reads known-nodes once (UNTESTED on RTX 5060)"
python3 -B - "$ROOT" > "$TMP/engine-notes-unit" 2>&1 <<'EOF'
import copy, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'assetgen'))
import runfiles as r
root = sys.argv[1]
def load(name):
    return json.load(open(os.path.join(root, 'tests/fixtures/assetgen/local', name), encoding='utf-8'))
def check(label, f):
    try:
        assert f()
        print('ok ' + label)
    except Exception as e:
        print('no ' + label + ' | ' + repr(e))
hybrid, adv, annot = load('hybrid-template.json'), load('hybrid-advanced-template.json'), load('annotator-template.json')
def rendered(t, seed=123):
    wf = copy.deepcopy(t['workflow'])
    for n in wf.values():
        for k, v in n['inputs'].items():
            if v == '{{seed}}':
                n['inputs'][k] = seed
    return wf, {'params': {'seed': seed}, 'template': {'data': t}}
def annotators():
    wf, spec = rendered(annot)
    rows = r.local_generation(wf, spec, {'annotators/yolox_l.onnx': 'd' * 64})['models']
    got = [(m['node'], m['class_type'], m['kind'], m['name'], m['verified']) for m in rows]
    assert got == [('4', 'CheckpointLoaderSimple', 'checkpoints', 'sdxl.safetensors', False),
                   ('11', 'DepthAnythingPreprocessor', 'annotators', 'depth_anything_vitl14.pth', False),
                   ('12', 'DWPosePreprocessor', 'annotators', 'yolox_l.onnx', True),
                   ('12', 'DWPosePreprocessor', 'annotators', 'dw-ll_ucoco_384.onnx', False)], got
    assert r.local_record_key(rows[1]) == 'annotators/depth_anything_vitl14.pth'
    # a disabled DWPose model input (None) is not a model
    wf['12']['inputs']['bbox_detector'] = 'None'; wf['12']['inputs']['pose_estimator'] = 'none'
    assert [m['name'] for m in r.local_generation(wf, spec)['models'] if m['kind'] == 'annotators'] == ['depth_anything_vitl14.pth']
    # a preprocessor graph is a local graph even without a sampler
    only = {'11': copy.deepcopy(annot['workflow']['11'])}
    return r.local_generation(only, spec) is not None
check('annotator preprocessors are recorded under the annotators kind with node order, hashes and None skipped', annotators)
def sampler_rows():
    wk, sk = rendered(hybrid); wa, sa = rendered(adv)
    a = r.local_generation(wa, sa)['samplers'][0]; k = r.local_generation(wk, sk)['samplers'][0]
    strip = lambda row: {x: y for x, y in row.items() if x not in ('class_type', 'denoise')}
    assert (a['class_type'], a['denoise'], k['class_type'], k['denoise']) == ('KSamplerAdvanced', None, 'KSampler', 0.45)
    assert strip(a) == strip(k) and a['seed'] == 123 and a['seed_param'] == 'seed'
    # a linked noise_seed resolves to the rendered value and parameter, like seed on KSampler
    wl, sl = copy.deepcopy(wa), copy.deepcopy(sa)
    wl['9']['inputs']['noise_seed'] = ['12', 0]; wl['12'] = {'inputs': {'value': 123}}
    sl['template']['data']['workflow']['9']['inputs']['noise_seed'] = ['12', 0]
    sl['template']['data']['workflow']['12'] = {'inputs': {'value': '{{seed}}'}}
    linked = r.local_generation(wl, sl)['samplers'][0]
    assert linked['seed'] == 123 and linked['seed_param'] == 'seed', linked
    # a literal noise_seed has no seed_param, like a literal seed
    wf = copy.deepcopy(wa); wf['9']['inputs']['noise_seed'] = 123
    spec = copy.deepcopy(sa); spec['template']['data']['workflow']['9']['inputs']['noise_seed'] = 123
    return r.local_generation(wf, spec)['samplers'][0]['seed_param'] is None
check('KSamplerAdvanced sampler row equals the KSampler row (seed from noise_seed, linked and literal)', sampler_rows)
def prompts():
    g = {'1': {'class_type': 'PrimitiveString', 'inputs': {'value': 'hello'}}, '2': {'class_type': 'PrimitiveStringMultiline', 'inputs': {'value': 'world'}}, '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': ['1', 0]}}, '4': {'class_type': 'CLIPTextEncodeSDXL', 'inputs': {'text_g': ['1', 0], 'text_l': ['2', 0]}}, '5': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'literal'}}, '6': {'class_type': 'CLIPTextEncode', 'inputs': {'text': ['2', 0]}}, '7': {'class_type': 'ControlNetApplyAdvanced', 'inputs': {'positive': ['3', 0], 'negative': ['6', 0]}}, '8': {'class_type': 'KSampler', 'inputs': {'positive': ['7', 0], 'negative': ['7', 1]}}, '9': {'class_type': 'CLIPTextEncode', 'inputs': {'text': ['2', 0]}}, '10': {'class_type': 'KSampler', 'inputs': {'negative': ['9', 0]}}}
    h = copy.deepcopy(g)
    for n in h.values():
        if n['class_type'] == 'KSampler':
            n['class_type'] = 'KSamplerAdvanced'
    assert r.workflow_prompts(g) == ['hello', 'hello', 'world']
    # same linked positive texts, same literal and negative-only exclusions
    assert r.workflow_prompts(h) == r.workflow_prompts(g)
    only_advanced = {k: v for k, v in h.items() if k in ('1', '2', '3', '5', '6', '8')}
    only_advanced['8'] = {'class_type': 'KSamplerAdvanced', 'inputs': {'positive': ['3', 0], 'negative': ['6', 0]}}
    out = r.workflow_prompts(only_advanced)
    assert out == ['hello'] and 'literal' not in out, out
    return all(isinstance(r.workflow_prompts(x), list) for x in ({'x': {'class_type': 'KSamplerAdvanced', 'inputs': {'negative': ['x', 0]}}},))
check('CLIP prompts follow KSamplerAdvanced positive and negative like KSampler (literals and negative-only excluded)', prompts)
def generation():
    wf, spec = rendered(adv)
    gi = r.generation_inputs({'9': {'class_type': 'KSamplerAdvanced'}}, spec)
    assert set(gi) == {'graph', 'references'}, gi
    size = {'1': {'class_type': 'EmptyLatentImage', 'inputs': {'width': 1024, 'height': 1536}},
            '9': {'class_type': 'KSamplerAdvanced', 'inputs': {'latent_image': ['1', 0]}}}
    sized = {'params': {}, 'template': {'data': {'primary_node': '9'}}}  # the primary node is the sampler
    assert r.requested_size(size, sized) == '1024x1536', r.requested_size(size, sized)
    return r.local_generation({'9': {'class_type': 'KSamplerAdvanced', 'inputs': {}}}, spec) is not None
check('KSamplerAdvanced counts as a generation node: inputs bound, requested size read, local record made', generation)
EOF
while IFS= read -r line; do
  case "$line" in "ok "*) ok "${line#ok }" ;; "no "*) no "${line#no }" ;; *) no "engine notes unit unexpected output" "$line" ;; esac
done < "$TMP/engine-notes-unit"
[ "$(grep -c '^ok ' "$TMP/engine-notes-unit")" -eq 4 ] || no "engine notes unit cases stopped early" "$(cat "$TMP/engine-notes-unit")"
# profile lint of an annotator template: the requires block accepts the annotators kind and the pack; an unknown
# preprocessor model kind, an unknown preprocessor node and an undeclared pack still FAIL
an_lint() { AG lint "$1" --json 2>&1; }
an_lint "$LOCALFX/annotator-template.json" > "$TMP/an-lint.json"
jq -e '([.results[] | select(.check == "assetgen-lint") | .state] == ["PASS"]) and ([.results[] | select(.state == "FAIL")] | length == 0) and ([.results[].reasons[] | select(test("unknown|not a model kind|not declared|requires"))] | length == 0)' "$TMP/an-lint.json" >/dev/null \
  && jq -e '[.requires.models[] | select(.kind == "annotators")] | length == 3' "$LOCALFX/annotator-template.json" >/dev/null \
  && ok "lint: a template with pose and depth preprocessor models (kind annotators, pack comfyui_controlnet_aux) passes the requires and profile rules" \
  || no "lint annotator template" "$(cat "$TMP/an-lint.json")"
for c in "kind|.requires.models[2].kind = \"preprocessors\"|requires.models[2].kind 'preprocessors' is not a model kind" \
         "node|.workflow[\"11\"].class_type = \"OpenposePreprocessor\"|node 11: unknown node type OpenposePreprocessor" \
         "pack|.requires.packs = []|node 11 uses DepthAnythingPreprocessor from pack comfyui_controlnet_aux, not declared in requires.packs"; do
  IFS='|' read -r label filter want <<< "$c"
  jq "$filter" "$LOCALFX/annotator-template.json" > "$TMP/an-$label.json"
  an_lint "$TMP/an-$label.json" > "$TMP/an-$label.out"; rc=$?
  [ "$rc" -eq 1 ] && jq -e --arg w "$want" '([.results[] | select(.check == "assetgen-lint") | .state] == ["FAIL"]) and ([.results[] | select(.check == "assetgen-lint") | .reasons[] | select(contains($w))] | length == 1)' "$TMP/an-$label.out" >/dev/null \
    && ok "lint FAILs an unknown preprocessor model ($label): $want" || no "lint annotator $label rc=$rc" "$(cat "$TMP/an-$label.out")"
done
# KSamplerAdvanced gets the same lint and graph-style result as its KSampler form (only the node name differs)
an_lint "$LOCALFX/hybrid-template.json" | jq -c '[.results[] | [.check, .state, (.reasons | map(sub("KSamplerAdvanced"; "KSampler")))]]' > "$TMP/adv-lint-plain.json"
an_lint "$LOCALFX/hybrid-advanced-template.json" | jq -c '[.results[] | [.check, .state, (.reasons | map(sub("KSamplerAdvanced"; "KSampler")))]]' > "$TMP/adv-lint-adv.json"
[ -s "$TMP/adv-lint-plain.json" ] && cmp -s "$TMP/adv-lint-plain.json" "$TMP/adv-lint-adv.json" \
  && jq -e 'length == 2 and (map(.[1]) | all(. != "FAIL")) and ([.[1][2][] | select(startswith("tiled-vae:"))] | length == 1)' "$TMP/adv-lint-adv.json" >/dev/null \
  && ok "lint and graph-style rows of the KSamplerAdvanced hybrid fixture equal the KSampler form's (the tiled-VAE walk passes through KSamplerAdvanced)" \
  || no "KSamplerAdvanced lint parity" "$(cat "$TMP/adv-lint-plain.json" "$TMP/adv-lint-adv.json")"
# lint over several templates reads data/known-nodes.json once per invocation (lint._load_known_registry, process-wide
# cache) and the rows equal those of one fresh process per template
python3 -B - "$ROOT" > "$TMP/lint-once" 2>&1 <<'EOF'
import copy, json, os, subprocess, sys
root = sys.argv[1]
sys.path.insert(0, os.path.join(root, 'scripts', 'assetgen'))
os.chdir(root)
import lint
lint._load_known_registry.cache_clear()
paths = ['templates/assetgen/workflows/image-edit.json', 'templates/assetgen/workflows/image-generate.json',
         'templates/assetgen/workflows/hybrid-character.json', 'templates/assetgen/workflows/local-variation.json',
         'tests/fixtures/assetgen/local/annotator-template.json', 'tests/fixtures/assetgen/local/hybrid-advanced-template.json']
rows = [lint.lint_rows(path) for path in paths]
assert len(rows) == len(paths) and all(len(result) == 2 for result in rows), rows
info = lint._load_known_registry.cache_info()
assert info.misses == 1 and info.hits > 0, info
# the copies are defensive: changing one never changes what the next call sees
first = lint.known_registry()
first['nodes'].clear(); first['packs'].clear()
assert lint.known_registry()['nodes'] and lint.known_registry()['packs'] and lint.known_nodes()
assert lint._load_known_registry.cache_info().misses == 1
fresh = []
for path in paths:
    out = subprocess.run([sys.executable, '-B', 'scripts/assetgen/assetgen.py', 'lint', path, '--json'], capture_output=True, text=True)
    assert out.returncode in (0, 1), out.stderr
    fresh.append(json.loads(out.stdout)['results'])
assert [[dict(row) for row in result] for result in rows] == fresh, (rows, fresh)
print('ok')
EOF
grep -qx ok "$TMP/lint-once" && ok "lint over six templates loads known-nodes.json once (cache misses 1) with the same rows as one process per template" \
  || no "lint reads known-nodes once" "$(cat "$TMP/lint-once")"

echo "-- style lock: project config, anchors, rejections, selection, drift (stylelock.py, lint)"
SL="$TMP/stylelock-authoring"
python3 -B - "$ROOT" "$SL" > "$TMP/sl" 2>&1 <<'EOF'
import hashlib, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import layers, lint, stylelock
A = sys.argv[2]
G = os.path.join(A, "assetgen")
def w(rel, obj):
    p = os.path.join(G, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))
    return p
def check(cond, label, detail=""):
    print(("ok " if cond else "no ") + label + ("" if cond else " :: " + str(detail)[:600]))
def refused(fn, text):
    try:
        fn()
    except stylelock.StyleLockError as exc:
        return text in str(exc), str(exc)
    return False, "not refused"
def lint_of(*rel):
    return lint.lint_file(os.path.join(G, *rel), A)
def failed(res, *texts):
    return res["state"] == "FAIL" and all(any(t in x for x in res["reasons"]) for t in texts)

# a game style family: rpg-base v2 (active, structured fields), rpg-chars extends it, rpg-old deprecated
w("styles/rpg-base.json", {"schema": "rpg-factory.assetgen-style/1", "title": "RPG base", "version": 2, "status": "active",
  "palette": {"text": "Warm earthy palette.", "colors": [{"hex": "#aa5533", "role": "primary"}], "max_distance": 40},
  "lighting": "Soft top light.", "outline": {"text": "Dark 2px outline.", "edge_darkness": {"max_luminance": 70, "min_ratio": 0.5}},
  "forbidden": ["photo texture"], "canvas": {"props": {"aspect": "1:1", "min_side": 512}}, "tone": {"tolerance": 0.05}})
w("styles/rpg-chars.json", {"extends": "rpg-base", "title": "RPG characters"})
w("styles/rpg-old.json", {"schema": "rpg-factory.assetgen-style/1", "title": "RPG old", "version": 1, "status": "deprecated"})
proj = {"schema": "rpg-factory.assetgen-project/1", "style": {"id": "rpg-base", "version": 2}, "allowed_styles": ["pixel-art", "rpg-old"],
        "families": {"characters": "rpg-chars"}, "art_direction": [{"artifact": "ART2D-DIR-001", "rev": 3}]}
w("project.json", proj)
icon, sprite, edit = (layers.load("purpose", p, A) for p in ("icon", "sprite-2d", "image-edit"))

# project precedence, refusal, override
c = stylelock.choose(icon, A)
check((c["family"], c["family_source"], c["style_id"], c["override"]) == ("props", "purpose", "rpg-base", None)
      and c["project"]["path"] == "assetgen/project.json" and len(c["project"]["sha256"]) == 64,
      "project: purpose default_family props, project default style rpg-base", c)
c = stylelock.choose(sprite, A)
check((c["family"], c["style_id"]) == ("characters", "rpg-chars"), "project: families[characters] picks the sub-style", c)
c = stylelock.choose(icon, A, family="characters")
check((c["family"], c["family_source"], c["style_id"]) == ("characters", "flag", "rpg-chars"), "project: --family beats the purpose default_family", c)
c = stylelock.choose(edit, A)
check((c["family"], c["family_source"], c["style_id"]) == (None, None, "rpg-base"), "project: purpose without default_family -> no family, project style", c)
c = stylelock.choose(icon, A, style="pixel-art")
check(c["style_id"] == "pixel-art" and c["override"] is None, "project: --style in allowed_styles is accepted", c)
check(stylelock.choose(icon, A, style="rpg-chars")["style_id"] == "rpg-chars", "project: --style naming a family sub-style is accepted")
r = refused(lambda: stylelock.choose(icon, A, style="anime-cel"), "is not allowed by assetgen/project.json")
check(r[0], "project: --style outside allowed_styles is refused", r[1])
c = stylelock.choose(icon, A, style="anime-cel", override="one-off key art")
check(c["style_id"] == "anime-cel" and c["override"] == "one-off key art", "project: --style-override REASON accepts and records the reason", c)
r = refused(lambda: stylelock.choose(icon, A, style="rpg-old"), "is deprecated")
check(r[0], "deprecated style is refused even when allowed", r[1])
check(stylelock.choose(icon, A, style="rpg-old", override="legacy fix")["override"] == "legacy fix", "deprecated style with an override reason is accepted")
w("project.json", dict(proj, style={"id": "rpg-base", "version": 1}))
r = refused(lambda: stylelock.choose(icon, A), "pins style rpg-base version 1")
check(r[0], "project style version must equal the style file's version (resolve refuses)", r[1])
check(failed(lint_of("project.json"), "project version 1 is not the style's version 2"), "lint: project version mismatch FAIL", lint_of("project.json"))
w("project.json", dict(proj, families={"characters": "pixel-art"}, allowed_styles="all"))
check(failed(lint_of("project.json"), "must extend the project style", "allowed_styles must be a list"),
      "lint: family style not extending the base, malformed allowed_styles FAIL", lint_of("project.json"))
w("project.json", {"schema": "x"})
r = refused(lambda: stylelock.choose(icon, A), "assetgen/project.json")
check(r[0], "malformed project.json is refused by resolve", r[1])
w("project.json", proj)
check(lint_of("project.json")["state"] == "PASS", "lint: valid project.json PASS", lint_of("project.json"))

# without project.json: today's behaviour
B = os.path.join(os.path.dirname(A), "stylelock-none")
os.makedirs(os.path.join(B, "assetgen"), exist_ok=True)
c = stylelock.choose(layers.load("purpose", "icon", B), B, style="pixel-art")
check(c["project"] is None and c["style_id"] == "pixel-art" and c["family"] == "props", "no project.json: --style as today, project null", c)
r = refused(lambda: stylelock.choose(layers.load("purpose", "icon", B), B), "pass --style")
check(r[0], "no project.json and no default_style: refused as today", r[1])
res = lint.lint_file(stylelock.project_path(B), B)
check(res["state"] == "WARN" and "no assetgen/project.json" in res["reasons"][0], "lint: WARN without assetgen/project.json", res)
check(os.path.abspath(stylelock.project_path(B)) in map(os.path.abspath, lint.default_paths(B)), "lint default paths include assetgen/project.json")

# style refs, hints from structured fields, style and purpose lint
base = layers.load("style", "rpg-base", A)
ref = stylelock.style_ref(base)
check(ref == {"style_id": "rpg-base", "version": 2, "sha256": layers.content_hash(base["data"])}, "style ref {style_id, version, sha256}", ref)
spec = layers.resolve("icon", "rpg-base", authoring=A)
check(spec["hints"]["palette"] == {"text": "Warm earthy palette.", "from": "style", "source": "game:assetgen/styles/rpg-base.json"},
      "hints: an object palette gives its text and source", spec["hints"].get("palette"))
check(stylelock.style_ref(layers.load("style", "rpg-chars", A))["version"] == 2, "an extending style inherits the version")
for name, data, text in (
        ("bad-version", {"version": 0}, "version must be an integer >= 1"),
        ("bad-status", {"status": "live"}, "status must be one of"),
        ("bad-palette", {"palette": {"text": "x", "colors": [{"hex": "red"}], "max_distance": 500}}, "palette.colors must be"),
        ("bad-share", {"palette": {"text": "x", "min_share": 2}}, "palette.min_share must be"),
        ("bad-text", {"lighting": {"severity": "warn"}}, "lighting.text must be a non-empty string"),
        ("bad-edges", {"outline": {"text": "x", "edge_darkness": {"max_luminance": 300}}}, "max_luminance must be a number from 0 to 255"),
        ("bad-canvas", {"canvas": {"props": {"aspect": "1x1"}}}, "canvas.props.aspect must be W:H"),
        ("bad-pixels", {"canvas": {"props": {"aspect": "1:1", "width": 512}}}, "an exact pixel canvas is never set"),
        ("bad-canvas-sev", {"canvas": {"props": {"aspect": "1:1", "severity": "loud"}}}, "canvas.props.severity must be warn or fail"),
        ("bad-forbidden", {"forbidden": "text"}, "forbidden must be a list"),
        ("bad-tone", {"tone": {"tolerance": 3}}, "tone.tolerance must be a number from 0 to 1")):
    p = w("styles/%s.json" % name, dict({"schema": "rpg-factory.assetgen-style/1", "title": name}, **data))
    res = lint.lint_file(p, A)
    check(failed(res, text), "lint style: " + text, res)
    os.remove(p)
check(lint_of("styles", "rpg-base.json")["state"] == "PASS", "lint: structured style fields PASS", lint_of("styles", "rpg-base.json"))
for sev in ("warn", "fail"):
    p = w("styles/canvas-%s.json" % sev, {"schema": "rpg-factory.assetgen-style/1", "title": sev,
                                         "canvas": {"props": {"aspect": "1:1", "min_side": 256, "severity": sev}}})
    res = lint.lint_file(p, A)
    check(res["state"] == "PASS", "lint style: canvas severity %s is accepted (consistency.check_canvas grades it)" % sev, res)
    os.remove(p)
p = w("purposes/bad-dims.json", {"extends": "icon", "dimensions": ["palette", "smell"], "max_references": -1, "default_family": "Props!", "qa": {"outlines": "yes"}})
res = lint.lint_file(p, A)
check(failed(res, "dimensions must be", "max_references must be", "default_family must be", "qa.outlines must be"),
      "lint purpose: dimensions, max_references, default_family, qa.outlines", res)
os.remove(p)

# anchors: validity in the engine view
PNG = b"\x89PNG\r\n\x1a\nanchor-bytes"
PNG_SHA = hashlib.sha256(PNG).hexdigest()
def anchor(aid, family, dims, strength, status="active", version=2, run="good-001", by="Dana", sha=None):
    d = os.path.join(G, "styles", "rpg-base", "anchors")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, aid + ".png"), "wb") as f:
        f.write(PNG)
    w("styles/rpg-base/anchors/%s.json" % aid, {
        "schema": "rpg-factory.assetgen-anchor/1", "id": aid, "status": status,
        "style": {"style_id": "rpg-base", "version": version, "sha256": sha or ref["sha256"]}, "family": family,
        "dimensions": dims, "strength": strength, "image": aid + ".png", "image_sha256": PNG_SHA,
        "source_run": {"run_id": run, "output": "outputs/a.png", "sha256": "0" * 64},
        "approved_by": by if status == "active" else None, "approved_on": "2026-11-01" if status == "active" else None})
def run(rid, status, style_ref):
    front = {"id": "AGEN-" + rid, "status": status, "spec": {"style": {"id": style_ref["style_id"], "sha256": style_ref["sha256"]},
                                                              "style_lock": {"style": style_ref}}}
    w("runs/%s/run.md" % rid, "---json\n%s\n---\n# run\n" % json.dumps(front))
def anchors():
    return {r["id"]: r for r in stylelock.load_anchors(A, "rpg-base")}
run("good-001", "approved", ref)
run("draft-001", "proposed", ref)
anchor("a-canon", "props", ["palette", "line"], "canonical")
anchor("a-strong", "props", ["palette", "shape", "line"], "strong")
anchor("b-strong", "props", ["palette", "shape", "line"], "strong")
anchor("c-chars", "characters", ["palette", "shape", "line"], "canonical")
anchor("d-props-tex", "props", ["texture"], "supporting")
anchor("p-proposed", "props", ["palette", "shape", "line"], "canonical", status="proposed")
anchor("u-unapproved", "props", ["palette", "shape", "line"], "canonical", run="draft-001")
anchor("v-old", "props", ["palette", "shape", "line"], "canonical", version=1, sha="1" * 64)
v = {k: stylelock.anchor_validity(r, A) for k, r in anchors().items()}
check(not v["p-proposed"][0] and "status proposed" in v["p-proposed"][1], "anchor: proposed is not valid", v["p-proposed"])
check(not v["u-unapproved"][0] and "draft-001 is proposed, not approved" in v["u-unapproved"][1], "anchor: active with an unapproved source run is not valid", v["u-unapproved"])
check(v["a-canon"][0], "anchor: active with an approved source run is valid", v["a-canon"])
check(v["v-old"][0], "anchor: an older style version stays valid", v["v-old"])
valid = stylelock.valid_anchors(A, "rpg-base")
check(sorted(a["id"] for a in valid) == ["a-canon", "a-strong", "b-strong", "c-chars", "d-props-tex", "v-old"], "valid_anchors keeps only valid active anchors", [a["id"] for a in valid])
check(failed(lint_of("styles", "rpg-base", "anchors", "u-unapproved.json"), "not approved"), "lint: active anchor with an unapproved source run FAIL",
      lint_of("styles", "rpg-base", "anchors", "u-unapproved.json"))
check(lint_of("styles", "rpg-base", "anchors", "p-proposed.json")["state"] == "PASS", "lint: proposed anchor PASS", lint_of("styles", "rpg-base", "anchors", "p-proposed.json"))
check(lint_of("styles", "rpg-base", "anchors", "a-canon.json")["state"] == "PASS", "lint: approved active anchor PASS", lint_of("styles", "rpg-base", "anchors", "a-canon.json"))
anchor("x-agent", "props", ["palette"], "strong", by="claude")
check(failed(lint_of("styles", "rpg-base", "anchors", "x-agent.json"), "is an agent or model"), "lint: anchor approved_by an agent FAIL")
check(not stylelock.anchor_validity(anchors()["x-agent"], A)[0], "anchor approved by an agent is never valid")
os.remove(os.path.join(G, "styles", "rpg-base", "anchors", "x-agent.json"))
with open(os.path.join(G, "styles", "rpg-base", "anchors", "b-strong.png"), "wb") as f:
    f.write(b"changed")
check(failed(lint_of("styles", "rpg-base", "anchors", "b-strong.json"), "does not match image_sha256"), "lint: anchor image changed after promotion FAIL")
with open(os.path.join(G, "styles", "rpg-base", "anchors", "b-strong.png"), "wb") as f:
    f.write(PNG)
w("styles/rpg-base/anchors/m-bad.json", {"schema": "rpg-factory.assetgen-anchor/1", "id": "other", "status": "active", "style": {"style_id": "rpg-chars"},
                                         "family": "props", "dimensions": ["smell"], "strength": "huge"})
res = lint_of("styles", "rpg-base", "anchors", "m-bad.json")
check(failed(res, "is not the file name", "is not the style directory", "dimensions must be", "strength must be", "needs approved_by"),
      "lint: malformed anchor names every bad field", res)
check(not stylelock.anchor_validity(anchors()["m-bad"], A)[0], "malformed anchor is never valid")
check(os.path.abspath(os.path.join(G, "styles", "rpg-base", "anchors", "m-bad.json")) in map(os.path.abspath, lint.default_paths(A)), "lint default paths include anchors")
os.remove(os.path.join(G, "styles", "rpg-base", "anchors", "m-bad.json"))

# deterministic selection: family, dimension overlap, strength, id; cap; style version
dims = icon["data"]["dimensions"]
picks = stylelock.select_references(valid, ref, "props", dims, 3)
check([p["anchor_id"] for p in picks] == ["a-strong", "b-strong", "a-canon"], "selection order: family, then dimension overlap, then strength, then id", [p["anchor_id"] for p in picks])
check(picks[0] == {"anchor_id": "a-strong", "family": "props", "strength": "strong", "dimensions": ["palette", "shape", "line"],
                   "image": "references/anchor-a-strong.png", "sha256": PNG_SHA,
                   "reason": ["family match", "dimensions: palette, shape, line", "strength strong"]}, "pick record with reasons", picks[0])
allp = stylelock.select_references(valid, ref, "props", dims, 10)
check([p["anchor_id"] for p in allp] == ["a-strong", "b-strong", "a-canon", "d-props-tex", "c-chars"] and allp[-1]["reason"][0] == "same style"
      and allp[3]["reason"] == ["family match", "strength supporting"], "selection: other family last as same style, older version excluded",
      [(p["anchor_id"], p["reason"]) for p in allp])
check(len(stylelock.select_references(valid, ref, "props", dims, 2)) == 2 and stylelock.select_references(valid, ref, "props", dims, 0) == [], "selection cap")
check(stylelock.select_references(list(reversed(valid)), ref, "props", dims, 3) == picks, "same inputs in another order -> same selection")
old_ref = {"style_id": "rpg-base", "version": 1, "sha256": "1" * 64}
check([p["anchor_id"] for p in stylelock.select_references(valid, old_ref, "props", dims, 3)] == ["v-old"], "an older style version selects only its own anchors")
check(stylelock.max_references({"max_references": 3}, {"max_references": 2}) == 2 and stylelock.max_references({}, {}) == 3
      and stylelock.max_references({"max_references": 1}, None) == 1, "max_references: the smaller of purpose and template, default 3")
CORE = os.path.join(sys.argv[1], "templates", "assetgen")
core_ids = lambda kind: sorted(f[:-5] for f in os.listdir(os.path.join(CORE, kind)) if f.endswith(".json"))
core_p = {p: layers.load("purpose", p)["data"] for p in core_ids("purposes")}
check(all(isinstance(d.get("dimensions"), list) and d.get("max_references") == 3 for d in core_p.values())
      and core_p["icon"]["default_family"] == "props" and core_p["sprite-2d"]["default_family"] == "characters"
      and "default_family" not in core_p["image-edit"], "core purposes declare dimensions, max_references and default_family (none for image-edit)")
check(all(layers.load("style", s)["data"].get("version") == 1 and layers.load("style", s)["data"].get("status") == "active"
          for s in core_ids("styles")), "core styles are version 1, active")

# rejections: relevance by style, family and version
def rej(rid, **kw):
    return w("styles/rpg-base/rejections/%s.json" % rid, dict({"schema": "rpg-factory.assetgen-rejection/1", "id": rid, "type": "direction",
             "style": dict(ref), "family": None, "reason": "too_detailed", "text": "No fine filigree."}, **kw))
ASSET_RUN = {"run_id": "good-001", "output": "outputs/a.png", "sha256": "0" * 64}
rej("r-all")
rej("r-props", family="props", reason="palette_off", text="Neon green.")
rej("r-chars", family="characters")
rej("r-anyver", style={"style_id": "rpg-base", "version": None, "sha256": "2" * 64})
rej("r-oldver", style={"style_id": "rpg-base", "version": 1, "sha256": "1" * 64})
rej("r-asset", type="asset", reason="anatomy", text=None, run=ASSET_RUN)
rel = stylelock.relevant_rejections(stylelock.load_rejections(A, "rpg-base"), ref, "props")
check([r["id"] for r in rel] == ["r-all", "r-anyver", "r-asset", "r-props"], "rejections: same style, family null or equal, version null or equal", [r["id"] for r in rel])
check(rel[3] == {"id": "r-props", "type": "direction", "reason": "palette_off", "text": "Neon green."} and rel[2]["run"] == ASSET_RUN and "text" not in rel[2],
      "rejection item carries its text or run", rel)
other = {"style_id": "rpg-chars", "version": 2, "sha256": ref["sha256"]}
check(stylelock.relevant_rejections(stylelock.load_rejections(A, "rpg-base"), other, "props") == [], "rejections of another style id are not relevant")
for rid, kw, text in (("bad-1", {"text": ""}, "text is required"), ("bad-2", {"reason": "ugly"}, "reason must be one of"),
                      ("bad-3", {"type": "asset", "run": {"run_id": "x"}}, "run must be"),
                      ("bad-4", {"reason": "other", "type": "asset", "text": None, "run": ASSET_RUN}, "text is required")):
    check(failed(lint.lint_file(rej(rid, **kw), A), text), "lint rejection: " + text, lint_of("styles", "rpg-base", "rejections", rid + ".json"))
    os.remove(os.path.join(G, "styles", "rpg-base", "rejections", rid + ".json"))
check(lint_of("styles", "rpg-base", "rejections", "r-asset.json")["state"] == "PASS", "lint: valid asset rejection PASS", lint_of("styles", "rpg-base", "rejections", "r-asset.json"))

# drift: older version, hash changed, style missing (read-only)
run("old-001", "approved", {"style_id": "rpg-base", "version": 1, "sha256": "1" * 64})
run("hash-001", "approved", {"style_id": "rpg-base", "version": 2, "sha256": "3" * 64})
run("gone-001", "approved", {"style_id": "rpg-gone", "version": 1, "sha256": "4" * 64})
d = stylelock.drift(A)
got = sorted((i["kind"], i["id"], i["state"]) for i in d["items"])
want = sorted([("gen-run", "AGEN-old-001", "older-version"), ("gen-run", "AGEN-hash-001", "hash-changed"), ("gen-run", "AGEN-gone-001", "style-missing"),
               ("anchor", "v-old", "older-version"), ("rejection", "r-oldver", "older-version"), ("rejection", "r-anyver", "hash-changed")])
check(d["schema"] == "rpg-factory.assetgen-drift/1" and got == want, "drift lists older-version, hash-changed and style-missing only", got)
EOF
while IFS= read -r line; do
  case "$line" in "ok "*) ok "${line#ok }" ;; "no "*) no "${line#no }" ;; *) no "style lock: unexpected output" "$line" ;; esac
done < "$TMP/sl"
grep -qE '^(ok|no) drift' "$TMP/sl" && ok "style lock cases ran to the end" || no "style lock cases stopped early" "$(tail -5 "$TMP/sl")"

echo "-- style lock through the CLI: resolve --family/--style-override, render wiring, promote-anchor, reject, drift"
SC="$TMP/stylelock-cli"; SG="$SC/assetgen"; SR="$SG/runs"
mkdir -p "$SG/styles" "$SG/purposes" "$SR"
cat > "$SG/styles/rpg-base.json" <<'EOF'
{"schema": "rpg-factory.assetgen-style/1", "title": "RPG base", "version": 2, "status": "active", "prefix": "RPG base art,",
 "palette": {"text": "Warm earthy palette.", "colors": [{"hex": "#aa5533", "role": "primary"}]}}
EOF
echo '{"extends": "rpg-base", "title": "RPG characters"}' > "$SG/styles/rpg-chars.json"
cat > "$SG/project.json" <<'EOF'
{"schema": "rpg-factory.assetgen-project/1", "style": {"id": "rpg-base", "version": 2}, "allowed_styles": ["pixel-art"],
 "families": {"characters": "rpg-chars"}, "art_direction": []}
EOF
echo '{"extends": "icon", "title": "Icon, one reference", "max_references": 1}' > "$SG/purposes/icon-one.json"
# approved seed run + anchors of rpg-base v2 (props x3, characters x1, one proposed, one with an unapproved run)
python3 -B - "$ROOT" "$SC" "$FX/icon-ok.png" > "$TMP/o" 2>&1 <<'EOF'
import hashlib, json, os, shutil, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import layers, stylelock
A, png = sys.argv[2], sys.argv[3]
G = os.path.join(A, "assetgen")
ref = stylelock.style_ref(layers.load("style", "rpg-base", A))
for rid, status in (("seed-001", "approved"), ("draft-001", "proposed")):
    os.makedirs(os.path.join(G, "runs", rid), exist_ok=True)
    with open(os.path.join(G, "runs", rid, "run.md"), "w", encoding="utf-8") as f:
        f.write("---json\n%s\n---\n# seed\n" % json.dumps({"id": "AGEN-" + rid, "status": status, "spec": {"style_lock": {"style": ref}}}))
d = os.path.join(G, "styles", "rpg-base", "anchors")
os.makedirs(d, exist_ok=True)
for n, (aid, fam, dims, strength, status, run) in enumerate((
        ("a-canon", "props", ["palette", "line"], "canonical", "active", "seed-001"),
        ("b-strong", "props", ["palette", "shape", "line"], "strong", "active", "seed-001"),
        ("c-supp", "props", ["texture"], "supporting", "active", "seed-001"),
        ("d-chars", "characters", ["palette", "shape", "line"], "canonical", "active", "seed-001"),
        ("e-proposed", "props", ["palette", "shape", "line"], "canonical", "proposed", "seed-001"),
        ("f-unapproved", "props", ["palette", "shape", "line"], "canonical", "active", "draft-001"))):
    data = open(png, "rb").read() + bytes([n])  # distinct bytes per anchor (trailing byte: content only, never decoded)
    open(os.path.join(d, aid + ".png"), "wb").write(data)
    json.dump({"schema": stylelock.ANCHOR_SCHEMA, "id": aid, "status": status, "style": ref, "family": fam, "dimensions": dims,
               "strength": strength, "image": aid + ".png", "image_sha256": hashlib.sha256(data).hexdigest(),
               "source_run": {"run_id": run, "output": "outputs/a.png", "sha256": "0" * 64},
               "approved_by": "Dana" if status == "active" else None, "approved_on": "2026-11-01" if status == "active" else None},
              open(os.path.join(d, aid + ".json"), "w", encoding="utf-8"))
r = os.path.join(G, "styles", "rpg-base", "rejections")
os.makedirs(r, exist_ok=True)
for rid, fam in (("r-props", "props"), ("r-chars", "characters")):
    json.dump({"schema": stylelock.REJECTION_SCHEMA, "id": rid, "type": "direction", "style": ref, "family": fam,
               "reason": "too_detailed", "text": "No fine filigree on " + fam + "."}, open(os.path.join(r, rid + ".json"), "w", encoding="utf-8"))
print("ok")
EOF
grep -qx ok "$TMP/o" || no "style lock CLI fixture" "$(cat "$TMP/o")"
git init -q -b main "$SC" && git -C "$SC" add -A && git -C "$SC" "${G[@]}" commit -qm "style lock fixture"
slrun() { # slrun NAME PURPOSE [resolve args...]: resolve into a run of the style lock repo, with a prompt
  local d="$SR/$1" p="$2"; shift 2; mkdir -p "$d/outputs"
  AG resolve --purpose "$p" --authoring "$SC" "$@" --out "$d/spec.json" --verbose > "$TMP/slr.out" 2>"$TMP/err" || return 1
  printf 'Style lock prompt for %s.\n' "$p" > "$d/prompt.md"
}
lk() { jq -r "$1" "$SR/$2/spec.json"; }

# resolve: project style, family, selection with reasons, relevant rejections
slrun sl-icon-001 icon --template image-generate || no "resolve icon in the style lock repo" "$(cat "$TMP/err")"
[ "$(lk '.style.id + "|" + .style_lock.style.style_id + "|" + (.style_lock.style.version | tostring) + "|" + .style_lock.family + "|" + .style_lock.family_source + "|" + .style_lock.project.path + "|" + (.style_lock.override | tostring)' sl-icon-001)" \
  = "rpg-base|rpg-base|2|props|purpose|assetgen/project.json|null" ] && [ "$(lk '.style_lock.style.sha256 == .style.sha256' sl-icon-001)" = true ] \
  && ok "resolve: project style rpg-base v2, purpose family props, project recorded, no override" || no "resolve style_lock" "$(lk .style_lock sl-icon-001)"
[ "$(lk '[.style_lock.references[].anchor_id] | join(",")' sl-icon-001)" = "b-strong,a-canon,c-supp" ] \
  && [ "$(lk '.style_lock.references[0].reason | join("; ")' sl-icon-001)" = "family match; dimensions: palette, shape, line; strength strong" ] \
  && [ "$(lk '.style_lock.references[0].image + " " + (.style_lock.max_references | tostring)' sl-icon-001)" = "references/anchor-b-strong.png 3" ] \
  && ok "resolve: 3 valid anchors (overlap, then strength), each with reason[]; proposed and unapproved-run anchors left out" \
  || no "resolve references" "$(lk '.style_lock.references' sl-icon-001)"
[ "$(lk '[.style_lock.rejections[] | .id + ":" + .text] | join(",")' sl-icon-001)" = "r-props:No fine filigree on props." ] \
  && ok "resolve: only the rejections relevant to the family are recorded" || no "resolve rejections" "$(lk .style_lock.rejections sl-icon-001)"
grep -q "^style lock: style rpg-base v2 (sha256 [0-9a-f]\{12\}), family props \[purpose\], project assetgen/project.json$" "$TMP/slr.out" \
  && grep -q "^reference b-strong  \[family match; dimensions: palette, shape, line; strength strong\]$" "$TMP/slr.out" \
  && grep -q "^rejection r-props direction too_detailed: No fine filigree on props.$" "$TMP/slr.out" \
  && ok "resolve text: style lock, references with reasons, rejections" || no "resolve text" "$(cat "$TMP/slr.out")"
# e2e3 item 5: anchors of another family are a fallback resolve warns about; anchor_family_fallback: false forbids them
[ "$(lk '.warnings | length' sl-icon-001)" = 0 ] && ! grep -q "^warning: reference" "$TMP/slr.out" \
  && ok "resolve: every selected anchor of the run's family, no cross-family warning" || no "same-family warnings" "$(lk .warnings sl-icon-001)"
AG resolve --purpose icon --family vfx --authoring "$SC" --json > "$TMP/xf.json" 2>"$TMP/err"; rc1=$?
AG resolve --purpose icon --family vfx --authoring "$SC" > "$TMP/xf.txt" 2>>"$TMP/err"; rc2=$?
[ $rc1 -eq 0 ] && [ $rc2 -eq 0 ] && [ "$(jq -r '.style_lock.references | length' "$TMP/xf.json")" = 3 ] && [ "$(jq -r '.warnings | length' "$TMP/xf.json")" = 3 ] \
  && grep -q "^warning: reference b-strong is a props anchor, the run's family is vfx (cross-family fallback; set anchor_family_fallback: false in the purpose or project.json to forbid it)$" "$TMP/xf.txt" \
  && ok "resolve --family vfx: the props anchors fill in as a cross-family fallback, one warning per pick (text and spec.warnings)" \
  || no "cross-family warning rc=$rc1/$rc2" "$(cat "$TMP/err" "$TMP/xf.txt"; jq -c .warnings "$TMP/xf.json")"
echo '{"extends": "icon", "title": "Icon, own family only", "anchor_family_fallback": false}' > "$SG/purposes/icon-own.json"
AG resolve --purpose icon-own --family vfx --authoring "$SC" --json > "$TMP/xf.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.style_lock.references | length' "$TMP/xf.json")" = 0 ] \
  && jq -r '.warnings[]' "$TMP/xf.json" | grep -q "^anchor_family_fallback is false: [1-9][0-9]* anchor(s) of other families than vfx were not selected$" \
  && [ "$(AG resolve --purpose icon-own --authoring "$SC" --json | jq -r '[.style_lock.references[].anchor_id] | join(",")')" = "b-strong,a-canon,c-supp" ] \
  && ok "anchor_family_fallback: false in the purpose: no cross-family anchor (warning says how many were left out); its own family still selected" \
  || no "fallback false rc=$rc" "$(cat "$TMP/err"; jq -c '[.style_lock.references, .warnings]' "$TMP/xf.json")"
rm -f "$SG/purposes/icon-own.json"
# e2e2: resolve prints a short summary by default; --verbose adds every source, --json is the whole spec
AG resolve --purpose icon --authoring "$SC" > "$TMP/short.out" 2>"$TMP/err"; rc=$?
AG resolve --purpose icon --authoring "$SC" --verbose > "$TMP/long.out" 2>>"$TMP/err"
cmp -s <(AG resolve --purpose icon --authoring "$SC" --json) <(AG resolve --purpose icon --authoring "$SC" --json --verbose); same=$?
{ [ $rc -eq 0 ] && [ "$(wc -l < "$TMP/short.out")" -le 12 ] \
  && grep -q "^params: .*size=" "$TMP/short.out" && grep -q "^hints: " "$TMP/short.out" \
  && grep -q "^style lock: style rpg-base v2 (sha256 [0-9a-f]\{12\}), family props \[purpose\], project assetgen/project.json$" "$TMP/short.out" \
  && grep -q "^references: b-strong, a-canon, c-supp (max 3)$" "$TMP/short.out" \
  && grep -q "^rejections: r-props (direction too_detailed)$" "$TMP/short.out" \
  && grep -q "^warning: filename_prefix assetgen/run is not bound to a run" "$TMP/short.out" \
  && ! grep -q "  \[core:\|  \[game:" "$TMP/short.out" && grep -q -- "--verbose or --json" "$TMP/short.out" \
  && grep -q "^param size = .*  \[core:templates/assetgen/purposes/icon.json\]$" "$TMP/long.out" \
  && grep -q "^purpose.title  \[core:" "$TMP/long.out" && [ "$(wc -l < "$TMP/long.out")" -gt 30 ] && [ $same -eq 0 ]; } \
  && ok "resolve: short summary by default (params, hints, style lock, references, rejections, warnings, no field sources); --verbose lists the sources; --json unchanged by --verbose" \
  || no "resolve summary rc=$rc same=$same" "$(cat "$TMP/err" "$TMP/short.out")"
AG resolve --purpose icon --authoring "$SC" --style anime-cel --style-override "one-off key art" > "$TMP/short.out" 2>"$TMP/err"
grep -q "^warning: style override: one-off key art$" "$TMP/short.out" && ! grep -q "no assetgen/project.json" "$TMP/short.out" \
  && AG resolve --purpose icon --style pixel-art --authoring "$AUTH" | grep -q "^warning: no assetgen/project.json" \
  && ! AG resolve --purpose icon --style pixel-art | grep -q "project.json" \
  && ok "resolve summary warnings: style override, a game layer without project.json (none for the core only)" || no "resolve warnings" "$(cat "$TMP/err" "$TMP/short.out")"
slrun sl-icon-002 icon && [ "$(jq -S .style_lock "$SR/sl-icon-001/spec.json")" = "$(jq -S .style_lock "$SR/sl-icon-002/spec.json")" ] \
  && ok "resolve: same inputs -> same style lock and selection" || no "resolve determinism"
slrun sl-chars-001 icon --family characters
[ "$(lk '.style.id + "|" + .style_lock.family + "|" + .style_lock.family_source + "|" + (.style_lock.references | length | tostring)' sl-chars-001)" = "rpg-chars|characters|flag|0" ] \
  && ok "resolve --family characters: families sub-style rpg-chars (its own anchors: none)" || no "resolve --family" "$(lk .style_lock sl-chars-001)"
AG resolve --purpose icon --authoring "$SC" --family Props! >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -q "must be a lowercase id" "$TMP/err" && ok "resolve --family: not a lowercase id, usage error" || no "bad --family rc=$rc" "$(cat "$TMP/err")"
slrun sl-one-001 icon-one --template image-generate && [ "$(lk '[.style_lock.max_references, (.style_lock.references | length)] | join(",")' sl-one-001)" = "1,1" ] \
  && [ "$(lk '.style_lock.references[0].anchor_id' sl-one-001)" = b-strong ] && ok "resolve: purpose max_references 1 caps the selection" \
  || no "resolve cap" "$(lk .style_lock sl-one-001)"
slrun sl-pixel-001 icon --style pixel-art --template image-generate && [ "$(lk '.style.id + "|" + (.style_lock.references | length | tostring) + "|" + (.style_lock.override | tostring)' sl-pixel-001)" = "pixel-art|0|null" ] \
  && ok "resolve --style in allowed_styles: accepted, no anchors of that style" || no "resolve allowed style" "$(cat "$TMP/err")"
AG resolve --purpose icon --authoring "$SC" --style anime-cel >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "is not allowed by assetgen/project.json" "$TMP/err" && grep -q "style-override REASON" "$TMP/err" \
  && ok "resolve --style outside allowed_styles: refused (exit 1)" || no "refusal rc=$rc" "$(cat "$TMP/err")"
slrun sl-override-001 icon --style anime-cel --style-override "one-off key art" \
  && [ "$(lk '.style.id + "|" + .style_lock.override' sl-override-001)" = "anime-cel|one-off key art" ] && grep -q "^style override: one-off key art$" "$TMP/slr.out" \
  && ok "resolve --style-override REASON: accepted, reason recorded in spec.style_lock.override" || no "override" "$(cat "$TMP/err")"

# render: anchors as LoadImage + ImageBatch chain into reference_images, in workflow.json and workflow.ui.json
wiring() { # wiring WORKFLOW: NineRouterImage reference chain as "img1>img2>..." of LoadImage image names
  python3 -B - "$1" <<'EOF'
import json, sys
wf = json.load(open(sys.argv[1], encoding="utf-8"))
node = [n for n in wf.values() if n["class_type"] == "NineRouterImage"][0]
def walk(link):
    if link is None:
        return []
    n = wf[link[0]]
    if n["class_type"] == "ImageBatch":
        return walk(n["inputs"]["image1"]) + walk(n["inputs"]["image2"])
    return [n["inputs"]["image"]]
print(">".join(walk(node["inputs"].get("reference_images"))) or "none")
EOF
}
d="$SR/sl-icon-001"
AG render --run "$d" > "$TMP/o" 2>&1 || no "render with 3 anchors" "$(cat "$TMP/o")"
[ "$(wiring "$d/workflow.json")" = "anchor-b-strong.png>anchor-a-canon.png>anchor-c-supp.png" ] \
  && [ "$(jq -r '[.[] | select(.class_type == "ImageBatch")] | length' "$d/workflow.json")" = 2 ] \
  && [ "$(jq -r '[to_entries[] | select(.value.class_type == "LoadImage") | .key + ":" + .value._meta.title] | join(",")' "$d/workflow.json")" \
       = "4:Anchor b-strong (strong),5:Anchor a-canon (canonical),6:Anchor c-supp (supporting)" ] \
  && ok "render 3 anchors: LoadImage per anchor (next free ids, titled) and an ImageBatch chain in selection order" \
  || no "render wiring 3" "$(jq -c . "$d/workflow.json")"
same=true; for a in b-strong a-canon c-supp; do
  cmp -s "$d/references/anchor-$a.png" "$SG/styles/rpg-base/anchors/$a.png" || same=false; done
$same && [ "$(ls "$d/references" | wc -l | tr -d ' ')" = 3 ] && ok "render --run copies each selected anchor to references/anchor-<id>.png" \
  || no "anchor copies" "$(ls -la "$d/references" 2>&1)"
out=$(python3 -B "$TMP/ui2api.py" "$KN" "$d/workflow.ui.json" "$d/workflow.json" 2>&1)
[ "$out" = ok ] && [ "$(jq -r '[.nodes[] | select(.type == "ImageBatch")] | length' "$d/workflow.ui.json")" = 2 ] \
  && ok "workflow.ui.json with anchors: ImageBatch nodes, converts back to workflow.json" || no "ui with anchors" "$out"
AG lint "$d/workflow.json" > "$TMP/o" 2>&1 && grep -q "1 PASS, 0 WARN, 0 FAIL" "$TMP/o" && ok "rendered workflow with anchors lints clean (ImageBatch is a known node)" || no "lint anchors" "$(cat "$TMP/o")"
d1="$SR/sl-one-001"; AG render --run "$d1" >/dev/null 2>&1
[ "$(wiring "$d1/workflow.json")" = "anchor-b-strong.png" ] && [ "$(jq -c '.["1"].inputs.reference_images' "$d1/workflow.json")" = '["4",0]' ] \
  && [ "$(jq -r '[.[] | select(.class_type == "ImageBatch")] | length' "$d1/workflow.json")" = 0 ] \
  && ok "render 1 anchor: LoadImage linked straight into reference_images (no batch)" || no "render wiring 1" "$(jq -c . "$d1/workflow.json")"
d0="$SR/sl-pixel-001"; AG render --run "$d0" >/dev/null 2>&1
[ "$(wiring "$d0/workflow.json")" = none ] && [ "$(jq 'length' "$d0/workflow.json")" = 3 ] && [ ! -d "$d0/references" ] \
  && ok "render 0 anchors: the template graph unchanged, no references/" || no "render wiring 0" "$(jq -c . "$d0/workflow.json")"
slrun sl-edit-001 image-edit --template image-edit && AG render --run "$SR/sl-edit-001" --param reference_image=ref.png >/dev/null 2>"$TMP/err"
de="$SR/sl-edit-001"
[ "$(wiring "$de/workflow.json")" = "ref.png>anchor-a-canon.png>anchor-d-chars.png>anchor-b-strong.png" ] \
  && [ "$(jq -c '[.["8"].inputs.image1, .["2"].inputs.reference_images]' "$de/workflow.json")" = '[["1",0],["10",0]]' ] \
  && ok "render image-edit: its own reference stays first, anchors follow (family none: same style, overlap order)" \
  || no "render image-edit wiring" "$(cat "$TMP/err"; jq -c . "$de/workflow.json")"
AG render --spec "$d/spec.json" --prompt-file "$d/prompt.md" --out "$TMP/sl-wf.json" >/dev/null 2>&1
[ "$(wiring "$TMP/sl-wf.json")" = "anchor-b-strong.png>anchor-a-canon.png>anchor-c-supp.png" ] && [ -f "$TMP/sl-wf.ui.json" ] \
  && ok "render --spec wires the same anchors (no copy outside a run)" || no "render --spec wiring" "$(jq -c . "$TMP/sl-wf.json")"
# a grouped (graph style) template: render lays the style-lock nodes into its References group; workflow.json is the
# same API graph (the ui block never leaks into it) and graph-lint --run PASSES with no exemption for anchors
mkdir -p "$SG/templates" && cp "$ROOT/tests/fixtures/assetgen/graph-style/clean.json" "$SG/templates/graph-clean.json"
dg="$SR/sl-gs-001"
slrun sl-gs-001 icon --template graph-clean && AG render --run "$dg" --param reference_image=ref.png > "$TMP/o" 2>&1; rc=$?
AG graph-lint --run "$dg" > "$TMP/o2" 2>&1; rc2=$?
AG render --spec "$dg/spec.json" --prompt-file "$dg/prompt.md" --param reference_image=ref.png --out "$TMP/sl-gs.json" >/dev/null 2>&1
out=$(python3 -B "$TMP/ui2api.py" "$KN" "$dg/workflow.ui.json" "$dg/workflow.json" 2>&1)
refs=$(python3 -B - "$dg/workflow.ui.json" "$dg/workflow.json" "$ROOT/tests/fixtures/assetgen/graph-style/clean.json" <<'EOF'
import json, sys
ui, wf, tmpl = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:4])
added = sorted((n for n in wf if n not in tmpl["workflow"]), key=int)
box = {g["title"]: g["bounding"] for g in ui["groups"]}
def inside(n, b):
    x, y = n["pos"]; w, h = n["size"]
    return x >= b[0] and y - 30 >= b[1] and x + w <= b[0] + b[2] and y + h <= b[1] + b[3]
nodes = {str(n["id"]): n for n in ui["nodes"]}
homes = {nid: [t for t, b in box.items() if inside(nodes[nid], b)] for nid in ["2"] + added}
print(" ".join([t for t, _ in sorted(box.items(), key=lambda kv: kv[1][0])])
      + " | " + ",".join(sorted({wf[n]["class_type"] for n in added})) + " " + str(len(added))
      + " | " + ("References" if all(h == ["References"] for h in homes.values()) else repr(homes)))
EOF
)
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && grep -q '^PASS .*sl-gs-001/workflow.ui.json$' "$TMP/o2" && [ "$out" = ok ] \
  && [ "$(wiring "$dg/workflow.json")" = "ref.png>anchor-b-strong.png>anchor-a-canon.png>anchor-c-supp.png" ] \
  && [ "$refs" = "Prompt References Generate Post-process Output | ImageBatch,LoadImage 6 | References" ] \
  && [ "$(jq -S . "$dg/workflow.json")" = "$(jq -S . "$TMP/sl-gs.json")" ] \
  && [ "$(jq -r '[.[] | select(.class_type == "Note" or .class_type == "MarkdownNote")] | length' "$dg/workflow.json")" = 0 ] \
  && [ "$(jq length "$dg/workflow.json")" = 12 ] \
  && ok "render of a grouped template with 3 anchors: anchor LoadImage/ImageBatch nodes in its References group, workflow.json unchanged API graph, graph-lint --run PASS" \
  || no "graph style render with anchors rc=$rc/$rc2 ui2api=$out refs=$refs" "$(cat "$TMP/o" "$TMP/o2")"
rm -rf "$dg" "$SG/templates/graph-clean.json"; rmdir "$SG/templates" 2>/dev/null || true
cp -R "$d" "$SR/sl-changed-001"; dc="$SR/sl-changed-001"; rm -rf "$dc/references" "$dc/workflow.json"
jq '.params.filename_prefix = "assetgen/sl-changed-001"' "$dc/spec.json" > "$TMP/s" && mv "$TMP/s" "$dc/spec.json"
printf 'x' >> "$SG/styles/rpg-base/anchors/a-canon.png"
out=$(AG render --run "$dc" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "anchor a-canon image changed since resolve" <<<"$out" && [ ! -f "$dc/workflow.json" ] && [ ! -d "$dc/references" ] \
  && ok "render --run: an anchor image changed after resolve is refused, nothing written" || no "changed anchor rc=$rc" "$out"
git -C "$SC" checkout -q -- assetgen/styles/rpg-base/anchors/a-canon.png

# hashes: style ref and anchor hashes bound only when style_lock is present; an old spec renders and hashes as before
python3 -B - "$ROOT" "$d/spec.json" "$d/workflow.json" "$d" > "$TMP/o" 2>&1 <<'EOF'
import copy, hashlib, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import runfiles
spec = json.load(open(sys.argv[2], encoding="utf-8"))
wf = json.load(open(sys.argv[3], encoding="utf-8"))
locate = lambda n: os.path.join(sys.argv[4], "references", n)
old = copy.deepcopy(spec); del old["style_lock"]
legacy = hashlib.sha256(json.dumps({"purpose": old["purpose"]["sha256"], "style": old["style"]["sha256"], "template": old["template"]["sha256"],
                                    "params": old["params"], "generation": None}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
assert runfiles.requirements_sha256(old) == legacy, "old spec hash changed"
assert runfiles.requirements_sha256(spec) != legacy, "style_lock not bound"
gen = runfiles.generation_inputs(wf, spec, locate)
assert gen["anchors"] == [{"anchor_id": r["anchor_id"], "sha256": r["sha256"]} for r in spec["style_lock"]["references"]], gen.get("anchors")
assert gen["references"]["anchor-b-strong.png"] == spec["style_lock"]["references"][0]["sha256"], gen["references"]
assert "anchors" not in runfiles.generation_inputs(wf, old, locate)
other = copy.deepcopy(spec); other["style_lock"]["references"][0]["sha256"] = "f" * 64
assert runfiles.requirements_sha256(other) != runfiles.requirements_sha256(spec), "anchor hash not bound"
other = copy.deepcopy(spec); other["style_lock"]["style"]["version"] = 3
assert runfiles.requirements_sha256(other) != runfiles.requirements_sha256(spec), "style ref not bound"
other = copy.deepcopy(spec); other["style_lock"]["override"] = "x"; other["style_lock"]["max_references"] = 9
assert runfiles.requirements_sha256(other) == runfiles.requirements_sha256(spec), "override and max_references are not bound"
rej = {"id": "r-new", "type": "direction", "reason": "too_detailed", "text": "No rivets."}
other = copy.deepcopy(spec); other["style_lock"]["rejections"] = spec["style_lock"]["rejections"] + [rej]
assert runfiles.requirements_sha256(other) != runfiles.requirements_sha256(spec), "an added rejection not bound"
changed = copy.deepcopy(other); changed["style_lock"]["rejections"][-1]["text"] = "No bolts."
assert runfiles.requirements_sha256(changed) != runfiles.requirements_sha256(other), "rejection content not bound"
assert runfiles.style_lock_binding(other)["rejections"][-1] == {"id": "r-new", "sha256": hashlib.sha256(json.dumps(
    rej, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}, runfiles.style_lock_binding(other)
other = copy.deepcopy(spec); other["style_lock"]["family"] = "characters"
assert runfiles.requirements_sha256(other) != runfiles.requirements_sha256(spec), "family not bound"
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "requirements_sha256/generation_inputs: style ref, family, anchor hashes and rejections (id + content) bound with style_lock only; old spec hash unchanged" || no "style lock hashes" "$(cat "$TMP/o")"
dg="$RUNS/golden-icon-001"; jq 'del(.style_lock)' "$dg/spec.json" > "$TMP/old-spec.json"
AG render --spec "$TMP/old-spec.json" --prompt-file "$dg/prompt.md" --out "$TMP/old-wf.json" >/dev/null 2>&1
[ "$(jq -S . "$TMP/old-wf.json")" = "$(jq -S . "$GOLD/icon.json")" ] \
  && ok "old spec.json without style_lock renders as before (golden icon)" || no "old spec render" "$(diff <(jq -S . "$TMP/old-wf.json") <(jq -S . "$GOLD/icon.json"))"

# manifest: spec.style_lock and the override in run.md
do_="$SR/sl-override-001"; AG render --run "$do_" >/dev/null && cp "$FX/icon-ok.png" "$do_/outputs/out.png" && AG qa --run "$do_" >/dev/null
AG manifest --run "$do_" >/dev/null 2>"$TMP/err"
fm() { python3 -B -c 'import json, re, sys; m = re.match(r"\A---json\s*\n(.*?)\n---", open(sys.argv[1], encoding="utf-8").read(), re.S); print(json.dumps(json.loads(m.group(1))))' "$1/run.md"; }
[ "$(fm "$do_" | jq -c --slurpfile s "$do_/spec.json" '.spec.style_lock == $s[0].style_lock')" = true ] \
  && grep -q "^- Style override: one-off key art$" "$do_/run.md" && grep -q "^- Style lock: style \`anime-cel\` v1, family props, project assetgen/project.json, references: none$" "$do_/run.md" \
  && ok "manifest: run.md records spec.style_lock and prints the style lock and the override" || no "manifest style lock" "$(cat "$TMP/err"; sed -n '/^# /,$p' "$do_/run.md")"
fm "$RUNS/qp-icon-001" | jq -e '.spec | has("style_lock")' >/dev/null && ok "manifest: a run resolved with the style lock records it (no project.json)" || no "style_lock missing in run.md"
jq 'del(.style_lock)' "$dg/spec.json" > "$TMP/s" && cp -R "$dg" "$RUNS/legacy-icon-001" && mv "$TMP/s" "$RUNS/legacy-icon-001/spec.json"
jq '.params.filename_prefix = "assetgen/legacy-icon-001"' "$RUNS/legacy-icon-001/spec.json" > "$TMP/s" && mv "$TMP/s" "$RUNS/legacy-icon-001/spec.json"
AG manifest --run "$RUNS/legacy-icon-001" >/dev/null 2>&1
fm "$RUNS/legacy-icon-001" | jq -e '.spec | has("style_lock") | not' >/dev/null && ! grep -q "Style lock" "$RUNS/legacy-icon-001/run.md" \
  && ok "manifest: an old spec without style_lock keeps the old run.md shape" || no "legacy manifest"

# promote-anchor: proposed only, output bound to run.md and qa.json, refusals
dp="$SR/sl-icon-001"; cp "$FX/icon-ok.png" "$dp/outputs/out.png"; AG qa --run "$dp" >/dev/null; AG manifest --run "$dp" >/dev/null
AG promote-anchor --run "$dp" --output 1 --family props --dimensions palette,line --strength strong --json > "$TMP/pa.json" 2>"$TMP/err"; rc=$?
pa="$SG/styles/rpg-base/anchors/sl-icon-001-1"
[ $rc -eq 0 ] && [ "$(jq -r '[.status, (.approved_by | tostring), (.approved_on | tostring), .family, (.dimensions | join(",")), .strength, .source_run.run_id, .source_run.output, .style.style_id, (.style.version | tostring)] | join("|")' "$pa.json")" \
  = "proposed|null|null|props|palette,line|strong|sl-icon-001|outputs/out.png|rpg-base|2" ] \
  && [ "$(jq -r '.image_sha256 == .source_run.sha256' "$pa.json")" = true ] && cmp -s "$pa.png" "$dp/outputs/out.png" \
  && [ "$(jq -r .path "$TMP/pa.json")" = "assetgen/styles/rpg-base/anchors/sl-icon-001-1.json" ] \
  && ok "promote-anchor: writes a proposed anchor (approved_by null), copies the output PNG, records the run's style ref" \
  || no "promote-anchor rc=$rc" "$(cat "$TMP/err"; cat "$pa.json" 2>/dev/null)"
AG lint "$pa.json" --authoring "$SC" > "$TMP/o" 2>&1 && ok "promote-anchor: the proposed anchor lints clean" || no "promoted anchor lint" "$(cat "$TMP/o")"
slrun sl-icon-003 icon && [ "$(jq -S .style_lock.references "$SR/sl-icon-003/spec.json")" = "$(jq -S .style_lock.references "$SR/sl-icon-001/spec.json")" ] \
  && ok "a proposed anchor is never selected" || no "proposed anchor selected" "$(lk .style_lock.references sl-icon-003)"
AG promote-anchor --run "$dp" --output outputs/out.png --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "anchor sl-icon-001-1 already exists" "$TMP/err" && ok "promote-anchor: an existing id is refused" || no "existing anchor rc=$rc" "$(cat "$TMP/err")"
AG promote-anchor --run "$dp" --output out.png --family props --dimensions palette,smell --strength strong --id x-1 >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "dimensions must be" "$TMP/err" && [ ! -e "$SG/styles/rpg-base/anchors/x-1.json" ] && ok "promote-anchor: unknown dimension refused, nothing written" || no "bad dims rc=$rc" "$(cat "$TMP/err")"
AG promote-anchor --run "$dp" --output 1 --family props --dimensions palette --strength huge >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "promote-anchor: unknown strength is a usage error" || no "bad strength rc=$rc"
AG promote-anchor --run "$dp" --output 2 --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "run.md records 1 output" "$TMP/err" && ok "promote-anchor: output index out of range refused" || no "index rc=$rc" "$(cat "$TMP/err")"
printf 'x' >> "$dp/outputs/out.png"
AG promote-anchor --run "$dp" --output 1 --family props --dimensions palette --strength strong --id y-1 >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "does not match run.md" "$TMP/err" && [ ! -e "$SG/styles/rpg-base/anchors/y-1.json" ] \
  && ok "promote-anchor: output changed after manifest (sha256 mismatch with run.md) refused" || no "sha mismatch rc=$rc" "$(cat "$TMP/err")"
AG manifest --run "$dp" >/dev/null
AG promote-anchor --run "$dp" --output 1 --family props --dimensions palette --strength strong --id y-1 >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "does not match qa.json" "$TMP/err" && ok "promote-anchor: output not the one qa.json graded refused" || no "qa mismatch rc=$rc" "$(cat "$TMP/err")"
mkdir -p "$TMP/sl-wf-run-001"; AG promote-anchor --run "$TMP/sl-wf-run-001" --output 1 --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "must be <authoring>/assetgen/runs/<slug>-NNN" "$TMP/err" && ok "promote-anchor: a run outside <authoring>/assetgen/runs refused" || no "run layout rc=$rc" "$(cat "$TMP/err")"
grep -rq '"status": "active"' "$pa.json" && no "promote-anchor wrote an active anchor" || ok "promote-anchor never writes status active"

# External art is copied into the authoring repo without recording its original path.
mkdir -p "$TMP/outside"; cp "$FX/icon-ok.png" "$TMP/outside/art.png"
ext="$SG/styles/rpg-base/anchors/ext-1"
AG promote-anchor --external "$TMP/outside/art.png" --origin 'art bible v2 p.14' --rights-note 'studio-owned' --authoring "$SC" --id ext-1 --family props --dimensions palette --strength strong --json > "$TMP/ext.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e '.status == "proposed" and .approved_by == null and .approved_on == null and .external_source.attested_by == null and .external_source.attested_on == null and (has("source_run") | not) and .external_source.origin == "art bible v2 p.14" and .external_source.rights_note == "studio-owned" and .external_source.sha256 == .image_sha256' "$ext.json" >/dev/null \
  && [ "$(jq -r .image_sha256 "$ext.json")" = "$(sha256sum "$ext.png" | cut -d' ' -f1)" ] && cmp -s "$ext.png" "$TMP/outside/art.png" \
  && ! grep -Fq "$TMP/outside" "$ext.json" && ! grep -Fq 'outside' "$ext.json" \
  && ok "external promote: proposed record, copied bytes and digest, no source path" || no "external promote rc=$rc" "$(cat "$TMP/err")"
AG lint "$ext.json" --authoring "$SC" > "$TMP/o" 2>&1 && ok "external promote: proposed anchor lints clean" || no "external anchor lint" "$(cat "$TMP/o")"
! grep -q '"status": "active"' "$ext.json" && ok "external promote: never writes an active anchor" || no "external promote wrote active status"
AG promote-anchor --external "$TMP/outside/art.png" --run "$dp" --origin art --rights-note owned --authoring "$SC" --id ext-bad --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && ok "external promote: --run conflicts with --external" || no "external with run rc=$rc" "$(cat "$TMP/err")"
for missing in origin rights-note id; do
  args=(--external "$TMP/outside/art.png" --authoring "$SC" --family props --dimensions palette --strength strong)
  [ "$missing" = origin ] || args+=(--origin art)
  [ "$missing" = rights-note ] || args+=(--rights-note owned)
  [ "$missing" = id ] || args+=(--id ext-bad)
  AG promote-anchor "${args[@]}" >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && ok "external promote: missing $missing is a usage error" || no "external missing $missing rc=$rc" "$(cat "$TMP/err")"
done
printf 'not a png' > "$TMP/outside/not-png"
AG promote-anchor --external "$TMP/outside/not-png" --origin art --rights-note owned --authoring "$SC" --id ext-bad --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.json" ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.png" ] && ok "external promote: non-PNG refused without writes" || no "external non-PNG rc=$rc" "$(cat "$TMP/err")"
for origin in 'C:/art/x.png' '/home/me/art.png'; do
  AG promote-anchor --external "$TMP/outside/art.png" --origin "$origin" --rights-note owned --authoring "$SC" --id ext-bad --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 1 ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.json" ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.png" ] && ok "external promote: absolute origin $origin refused without writes" || no "external absolute origin rc=$rc" "$(cat "$TMP/err")"
done
for uri_env in 'file:///C:/art/a.png' 'file:/art/a.png' 'FILE://host/share/a.png' '$HOME/art/a.png' '${HOME}/art/a.png' '%USERPROFILE%\art\a.png' '%USERPROFILE%/art/a.png'; do
  for ext_field in origin rights-note; do
    ext_origin=art; ext_rights=owned
    [ "$ext_field" = origin ] && ext_origin="$uri_env" || ext_rights="$uri_env"
    AG promote-anchor --external "$TMP/outside/art.png" --origin "$ext_origin" --rights-note "$ext_rights" --authoring "$SC" --id ext-bad --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
    [ $rc -eq 1 ] && grep -Fq 'must not contain an absolute path or credential' "$TMP/err" && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.json" ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.png" ] \
      && ok "external promote: $uri_env in $ext_field refused without writes" || no "external uri/env $uri_env in $ext_field rc=$rc" "$(cat "$TMP/err")"
  done
done
AG promote-anchor --external "$TMP/outside/art.png" --origin art --rights-note 'token=abc123' --authoring "$SC" --id ext-bad --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.json" ] && [ ! -e "$SG/styles/rpg-base/anchors/ext-bad.png" ] && ok "external promote: credential refused without writes" || no "external credential rc=$rc" "$(cat "$TMP/err")"
AG promote-anchor --external "$TMP/outside/art.png" --origin art --rights-note owned --authoring "$SC" --id ext-1 --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q 'already exists' "$TMP/err" && ok "external promote: existing id refused" || no "external existing id rc=$rc" "$(cat "$TMP/err")"
jq '.status = "active" | .approved_by = "Ana Silva" | .approved_on = "2026-11-01" | .external_source.attested_by = "Ana Silva" | .external_source.attested_on = "2026-11-01"' "$ext.json" > "$TMP/ext-active.json" && cp "$TMP/ext-active.json" "$ext.json"
python3 -B - "$ROOT" "$SC" "$ext.json" > "$TMP/o" 2>&1 <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import stylelock
data = json.load(open(sys.argv[3], encoding="utf-8"))
assert not stylelock.anchor_errors(data, "rpg-base", "ext-1")
assert any(a["data"]["id"] == "ext-1" for a in stylelock.valid_anchors(sys.argv[2], "rpg-base"))
EOF
[ $? -eq 0 ] && ok "external anchor: human activation is valid and selectable" || no "external active validity" "$(cat "$TMP/o")"
rm -f "$ext.json" "$ext.png"

AG promote-anchor --external "$TMP/outside/art.png" --origin art --rights-note owned --authoring "$SC" --id ext-family --family characters --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
ext_family="$SG/styles/rpg-chars/anchors/ext-family"
[ $rc -eq 0 ] && [ -f "$ext_family.png" ] && jq -e '.style.style_id == "rpg-chars" and .family == "characters"' "$ext_family.json" >/dev/null \
  && ok "external promote: mapped family uses its style and anchor directory" || no "external family rc=$rc" "$(cat "$TMP/err")"
rm -f "$ext_family.json" "$ext_family.png"
before_external=$(find "$SG" -type f | sort)
AG promote-anchor --external "$TMP/outside/art.png" --origin art --rights-note owned --authoring "$SC" --style unlisted-style --id ext-disallowed --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q 'not allowed' "$TMP/err" && [ "$before_external" = "$(find "$SG" -type f | sort)" ] \
  && ok "external promote: disallowed explicit style refused without writes" || no "external disallowed style rc=$rc" "$(cat "$TMP/err")"
AG promote-anchor --external "$TMP/outside/art.png" --origin 'art bible / page 4' --rights-note 'monkey: yes' --authoring "$SC" --id ext-prose --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
ext_prose="$SG/styles/rpg-base/anchors/ext-prose"
[ $rc -eq 0 ] && jq -e '.external_source.origin == "art bible / page 4" and .external_source.rights_note == "monkey: yes"' "$ext_prose.json" >/dev/null \
  && ok "external promote: ordinary prose accepted" || no "external prose rc=$rc" "$(cat "$TMP/err")"
rm -f "$ext_prose.json" "$ext_prose.png"
AG promote-anchor --external "$TMP/outside/art.png" --origin 'https://example.com/a.png' --rights-note 'bought for $5' --authoring "$SC" --id ext-prose --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e '.external_source.origin == "https://example.com/a.png" and .external_source.rights_note == "bought for $5"' "$ext_prose.json" >/dev/null \
  && ok "external promote: https URL and a price accepted" || no "external url/price rc=$rc" "$(cat "$TMP/err")"
rm -f "$ext_prose.json" "$ext_prose.png"
AG promote-anchor --external "$TMP/outside/art.png" --origin art --rights-note '100% original work' --authoring "$SC" --id ext-prose --family props --dimensions palette --strength strong >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e '.external_source.rights_note == "100% original work"' "$ext_prose.json" >/dev/null \
  && ok "external promote: a percentage accepted" || no "external percentage rc=$rc" "$(cat "$TMP/err")"
rm -f "$ext_prose.json" "$ext_prose.png"

# reject: validation, deterministic ids, asset rejections bound to a recorded output
AG reject --type direction --reason too_detailed --authoring "$SC" --style rpg-base --family props >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "text is required" "$TMP/err" && ok "reject direction without text refused" || no "reject no text rc=$rc" "$(cat "$TMP/err")"
AG reject --type direction --reason ugly --authoring "$SC" --style rpg-base --text x >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && ok "reject: a reason outside the fixed list is a usage error" || no "reject bad reason rc=$rc"
AG reject --type direction --reason too_detailed --authoring "$SC" --text x >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -q "needs --authoring DIR and --style S" "$TMP/err" && ok "reject direction without --style: usage error" || no "reject no style rc=$rc" "$(cat "$TMP/err")"
AG reject --type asset --reason anatomy --authoring "$SC" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -q "needs --run DIR and --output" "$TMP/err" && ok "reject asset without --run/--output: usage error" || no "reject asset no run rc=$rc" "$(cat "$TMP/err")"
AG reject --type direction --reason too_detailed --authoring "$SC" --style rpg-base --family props --text "No gold trim." --json > "$TMP/rj1.json" 2>"$TMP/err" \
  && AG reject --type direction --reason too_detailed --authoring "$SC" --style rpg-base --any-version --text "No noise." --json > "$TMP/rj2.json" 2>>"$TMP/err"
[ "$(jq -r '.id + "|" + .path + "|" + .family + "|" + (.style.version | tostring)' "$TMP/rj1.json")" = "too-detailed-001|assetgen/styles/rpg-base/rejections/too-detailed-001.json|props|2" ] \
  && [ "$(jq -r '.id + "|" + (.family | tostring) + "|" + (.style.version | tostring)' "$TMP/rj2.json")" = "too-detailed-002|null|null" ] \
  && ok "reject direction: written with the current style ref, next free <reason>-NNN id, --any-version records version null" \
  || no "reject direction" "$(cat "$TMP/err" "$TMP/rj1.json" "$TMP/rj2.json" 2>/dev/null)"
AG manifest --run "$dp" >/dev/null; AG qa --run "$dp" >/dev/null; AG manifest --run "$dp" >/dev/null
AG reject --type asset --reason palette_off --run "$dp" --output out.png --json > "$TMP/rj3.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.id + "|" + .family + "|" + .run.run_id + "|" + .run.output + "|" + .style.style_id' "$TMP/rj3.json")" = "palette-off-001|props|sl-icon-001|outputs/out.png|rpg-base" ] \
  && [ "$(jq -r .run.sha256 "$TMP/rj3.json")" = "$(sha256sum "$dp/outputs/out.png" | cut -d' ' -f1)" ] \
  && ok "reject asset: run output, its sha256, the run's style ref and family" || no "reject asset rc=$rc" "$(cat "$TMP/err" "$TMP/rj3.json")"
AG reject --type direction --reason too_detailed --authoring "$SC" --style rpg-base --text "Again." --id too-detailed-001 >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "already exists" "$TMP/err" && ok "reject: an existing id is refused" || no "reject existing rc=$rc" "$(cat "$TMP/err")"
AG lint --authoring "$SC" "$SG/styles/rpg-base/rejections/too-detailed-001.json" "$SG/styles/rpg-base/rejections/palette-off-001.json" > "$TMP/o" 2>&1 \
  && grep -q "2 PASS, 0 WARN, 0 FAIL" "$TMP/o" && ok "reject: written rejections lint clean" || no "rejection lint" "$(cat "$TMP/o")"
slrun sl-icon-004 icon && [ "$(lk '[.style_lock.rejections[].id] | join(",")' sl-icon-004)" = "palette-off-001,r-props,too-detailed-001,too-detailed-002" ] \
  && ok "resolve records the new relevant rejections (family props, any version)" || no "rejections after reject" "$(lk .style_lock.rejections sl-icon-004)"

echo "-- anchor_target: anchors into NineRouterImage or IPAdapterAdvanced (UNTESTED on RTX 5060)"
mkdir -p "$SG/templates"
cp "$ROOT/tests/fixtures/assetgen/local/hybrid-anchor-template.json" "$SG/templates/hybrid-anchor.json"
echo '{"extends": "icon", "title": "Icon, two references", "max_references": 2}' > "$SG/purposes/icon-two.json"
dh="$SR/hybrid-anchor-001"
slrun hybrid-anchor-001 icon-two --template hybrid-anchor && AG render --run "$dh" > "$TMP/anchor-out" 2>&1; rc=$?
python3 -B - "$dh/workflow.json" "$dh/workflow.ui.json" "$ROOT/tests/fixtures/assetgen/local/hybrid-anchor-template.json" > "$TMP/anchor-check" 2>&1 <<'EOF'
import json, sys
wf, ui, tmpl = (json.load(open(p, encoding='utf-8')) for p in sys.argv[1:])
def walk(link):
    node = wf[link[0]]
    if node['class_type'] == 'ImageBatch':
        return walk(node['inputs']['image1']) + walk(node['inputs']['image2'])
    if node['class_type'] == 'NineRouterImage':
        return ['base:' + link[0]]
    return [node['inputs']['image']]
assert walk(wf['12']['inputs']['image']) == ['base:1', 'anchor-b-strong.png', 'anchor-a-canon.png']
assert 'reference_images' not in wf['1']['inputs']
added = set(wf) - set(tmpl['workflow'])
assert len(added) == 4
box = next(g['bounding'] for g in ui['groups'] if g['title'] == 'References')
nodes = {str(n['id']): n for n in ui['nodes']}
def inside(n):
    x, y = n['pos']; w, h = n['size']
    return x >= box[0] and y - 30 >= box[1] and x + w <= box[0] + box[2] and y + h <= box[1] + box[3]
assert all(inside(nodes[n]) for n in added)
assert any(n['type'] == 'Note' and n['widgets_values'][0] == 'Style-lock anchors added by render: references/anchor-<id>.png, batched into IPAdapterAdvanced.image.' and inside(n) for n in ui['nodes'])
print('ok')
EOF
[ $rc -eq 0 ] && grep -qx ok "$TMP/anchor-check" && ok "hybrid render: base and two anchors into IPAdapterAdvanced, References group and target note" \
  || no "hybrid anchor wiring rc=$rc" "$(cat "$TMP/anchor-out" "$TMP/anchor-check")"
cp "$dh/workflow.json" "$TMP/hybrid-first.json"; cp "$dh/workflow.ui.json" "$TMP/hybrid-first.ui.json"
AG render --run "$dh" > "$TMP/anchor-out" 2>&1; rc=$?
[ $rc -eq 0 ] && cmp -s "$TMP/hybrid-first.json" "$dh/workflow.json" && cmp -s "$TMP/hybrid-first.ui.json" "$dh/workflow.ui.json" \
  && ok "hybrid render --run: both workflow files byte-identical on repeat" || no "hybrid render determinism rc=$rc" "$(cat "$TMP/anchor-out")"
slrun anchor-api-001 icon-two --template image-generate && AG render --run "$SR/anchor-api-001" > "$TMP/anchor-out" 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(wiring "$SR/anchor-api-001/workflow.json")" = 'anchor-b-strong.png>anchor-a-canon.png' ] \
  && ok "API-only template keeps NineRouterImage reference_images wiring" || no "API-only anchor wiring rc=$rc" "$(cat "$TMP/anchor-out")"

# Mutate a resolved spec, so render validates even without selected anchors and never writes a workflow on failure.
anchor_bad() { # label jq-filter expected-message
  local label="$1" filter="$2" expected="$3" dir="$SR/anchor-bad-$1"
  mkdir -p "$dir"; jq --arg p "assetgen/anchor-bad-$label" "$filter | .style_lock.references = [] | .params.filename_prefix = \$p" "$dh/spec.json" > "$dir/spec.json"
  cp "$dh/prompt.md" "$dir/prompt.md"; rm -f "$dir/workflow.json" "$dir/workflow.ui.json"
  AG render --run "$dir" > "$TMP/anchor-bad" 2>&1; local status=$?
  [ "$status" -ne 0 ] && grep -Fq "$expected" "$TMP/anchor-bad" && [ ! -e "$dir/workflow.json" ] && [ ! -e "$dir/workflow.ui.json" ] \
    && ok "render rejects $label before writing workflows" || no "render $label rc=$status" "$(cat "$TMP/anchor-bad")"
}
anchor_bad missing-node '.template.data.anchor_target.node = "missing"' "FAIL anchor_target.node 'missing' is not a node of the workflow"
anchor_bad missing-input '.template.data.anchor_target.input = "images"' "FAIL anchor_target.input 'images' is not an input of node 12 (IPAdapterAdvanced)"
anchor_bad disallowed '.template.data.anchor_target = {"node":"9","input":"latent_image"}' 'FAIL anchor_target KSampler.latent_image cannot take anchors'
anchor_bad primary-missing '.template.data.primary_node = "missing"' "FAIL primary_node 'missing' is not a node of the workflow"
anchor_bad primary-class '.template.data.primary_node = "4"' 'FAIL primary_node 4 (CheckpointLoaderSimple) is not a generation node'
anchor_bad primary-ambiguous 'del(.template.data.primary_node) | .template.data.workflow["13"] = .template.data.workflow["1"]' 'FAIL the template has 2 NineRouterImage nodes: declare primary_node'
# lint runs the same check on the template's own workflow: a bad anchor_target or primary_node FAILs lint, not only render
LF="$ROOT/tests/fixtures/assetgen/local"
# lint_target prints the result count, then check|state|reasons of every entry of .results (lint and graph-style rows):
# a wrong state or reason in any entry, or a changed count, fails the case, not only results[0]
lint_target() { AG lint "$LF/$1.json" --json 2>&1 | jq -r '"results=\(.results | length)", (.results[] | "\(.check)|\(.state)|\(.reasons | join("; "))")'; }
got=$(lint_target hybrid-anchor-template)
[ "$got" = "$(printf 'results=2\nassetgen-lint|PASS|\nassetgen-graph-style|PASS|')" ] \
  && ok "lint: the hybrid anchor template (anchor_target 12.image, primary_node 1) PASSES every result row" || no "lint hybrid anchor template" "$got"
# the fixture decodes with VAEDecodeTiled, which the local-8gb profile wants for a base image above 1024 px
# (data/hardware.json, data/template-profiles.json): the graph-style row has no tiled-vae reason, and the plain decode has
jq -e '.workflow["10"].class_type == "VAEDecodeTiled" and (.requires.profile == "local-8gb")' "$LF/hybrid-anchor-template.json" >/dev/null \
  && ! printf '%s\n' "$got" | grep -q 'tiled-vae' \
  && jq '.workflow["10"] |= (.class_type = "VAEDecode" | .inputs |= {samples, vae})' "$LF/hybrid-anchor-template.json" > "$TMP/anchor-untiled.json" \
  && { AG lint "$TMP/anchor-untiled.json" --json > "$TMP/anchor-untiled.out" 2>&1; true; } \
  && jq -e '[.results[] | select(.check == "assetgen-graph-style" and .state == "FAIL") | .reasons[] | select(startswith("tiled-vae:") and contains("VAEDecodeTiled"))] | length == 1' "$TMP/anchor-untiled.out" >/dev/null \
  && ok "hybrid anchor fixture decodes with VAEDecodeTiled: no tiled-vae reason under local-8gb (the plain VAEDecode form is reported)" \
  || no "hybrid anchor fixture tiled decode" "$got"
for c in "target-anchor-missing-node|anchor_target.node '99' is not a node of the workflow" \
         "target-anchor-missing-input|anchor_target.input 'images' is not an input of node 12 (IPAdapterAdvanced)" \
         "target-anchor-disallowed|anchor_target KSampler.latent_image cannot take anchors" \
         "target-primary-missing|primary_node '99' is not a node of the workflow" \
         "target-primary-not-generation|primary_node 4 (CheckpointLoaderSimple) is not a generation node"; do
  f=${c%%|*}; got=$(lint_target "$f")
  jq -e '.description | startswith("UNTESTED on RTX 5060:")' "$LF/$f.json" >/dev/null \
    && case "$got" in "results=2"$'\n'"assetgen-lint|FAIL|${c#*|}"*$'\n'"assetgen-graph-style|PASS|") : ;; *) false ;; esac \
    && ok "lint FAILs $f: ${c#*|} (two results, graph-style PASS)" || no "lint $f" "$got"
done
# every core template that declares anchor_target, rendered in the style lock repo for the purpose its cases file
# names (the first cases/<purpose>--<template>.json), family props: its anchors reach anchor_target after the template's
# own link, graph-lint --run passes (anchor nodes laid into References) and render --run is byte-identical on repeat.
# Discovery finds nothing while no core template declares anchor_target. UNTESTED on RTX 5060: nothing is generated.
cat > "$TMP/anchor-core.py" <<'EOF'
import json, sys
wf, spec, tmpl = (json.load(open(p, encoding='utf-8')) for p in sys.argv[1:4])
target = tmpl['anchor_target']
def walk(link):
    node = wf[link[0]]
    if link[0] not in tmpl['workflow'] and node['class_type'] == 'ImageBatch':
        return walk(node['inputs']['image1']) + walk(node['inputs']['image2'])
    if link[0] not in tmpl['workflow'] and node['class_type'] == 'LoadImage':
        return [node['inputs']['image']]
    return ['node:' + link[0]]
want = ['anchor-%s.png' % r['anchor_id'] for r in spec['style_lock']['references']]
assert want, 'the purpose selected no anchor in the style lock repo'
own = tmpl['workflow'][target['node']]['inputs'].get(target['input'])
head = ['node:' + own[0]] if isinstance(own, list) else []
got = walk(wf[target['node']]['inputs'][target['input']])
assert got == head + want, (got, head + want)
print('ok %d' % len(want))
EOF
for t in $CORE_TEMPLATES; do
  jq -e 'has("anchor_target")' "$CORE/workflows/$t.json" >/dev/null 2>&1 || continue
  p=""; for v in "$CASES"/*--"$t".json; do [ -f "$v" ] && { p=$(basename "$v" .json); p=${p%--"$t"}; break; }; done
  [ -n "$p" ] || { no "anchor_target $t: no cases/<purpose>--$t.json names a purpose to render it with"; continue; }
  da="$SR/anchor-core-$t-001"; mapfile -t args < <(case_params "$p" "$t")
  # family props: the fixture's anchors are props anchors of rpg-base (a purpose's own family may select none)
  if slrun "anchor-core-$t-001" "$p" --template "$t" --family props; then
    AG render --run "$da" "${args[@]}" > "$TMP/anchor-out" 2>&1; rc=$?
  else rc=1; { echo "resolve failed:"; cat "$TMP/err"; } > "$TMP/anchor-out"; fi
  out=$(python3 -B "$TMP/anchor-core.py" "$da/workflow.json" "$da/spec.json" "$CORE/workflows/$t.json" 2>&1)
  AG graph-lint --run "$da" > "$TMP/anchor-gl" 2>&1; rc2=$?
  [ $rc -eq 0 ] && [ "${out%% *}" = ok ] && [ $rc2 -eq 0 ] \
    && ok "anchor_target $t ($p): ${out#ok } style-lock anchors reach $(jq -r '.anchor_target | .node + "." + .input' "$CORE/workflows/$t.json") after the template's own link; graph-lint --run PASS" \
    || no "anchor_target $t ($p) rc=$rc graph-lint rc=$rc2" "$(cat "$TMP/anchor-out" "$TMP/anchor-gl"; echo "$out")"
  cp "$da/workflow.json" "$TMP/anchor-core-first.json"; cp "$da/workflow.ui.json" "$TMP/anchor-core-first.ui.json"
  AG render --run "$da" "${args[@]}" > "$TMP/anchor-out" 2>&1; rc=$?
  [ $rc -eq 0 ] && cmp -s "$TMP/anchor-core-first.json" "$da/workflow.json" && cmp -s "$TMP/anchor-core-first.ui.json" "$da/workflow.ui.json" \
    && ok "anchor_target $t: render --run byte-identical on repeat (workflow.json and workflow.ui.json)" || no "anchor_target $t determinism rc=$rc" "$(cat "$TMP/anchor-out")"
done

python3 -B - "$ROOT" > "$TMP/anchor-size" 2>&1 <<'EOF'
import glob, json, os, sys
root = sys.argv[1]
sys.path.insert(0, os.path.join(root, 'scripts', 'assetgen'))
import runfiles
def nine(size): return {'class_type': 'NineRouterImage', 'inputs': {'size': size}}
workflow = {'10': nine('ten'), '2': nine('two')}
spec = {'template': {'data': {'primary_node': '10'}}, 'params': {'size': 'fallback'}}
assert runfiles.requested_size(workflow, spec) == 'ten'
assert runfiles.requested_size(workflow, {}) == 'two'
local = {'1': {'class_type': 'KSampler', 'inputs': {'latent_image': ['2', 0]}},
         '2': {'class_type': 'EmptyLatentImage', 'inputs': {'width': 832, 'height': 1216}}}
assert runfiles.requested_size(local, {'template': {'data': {'primary_node': '1'}}}) == '832x1216'
for bad in (None, [], {'template': None}, {'template': {'data': []}}, {'template': {'data': {'primary_node': []}}}, {'params': []}):
    assert runfiles.requested_size({}, bad) == 'auto'
for path in glob.glob(os.path.join(root, 'tests', 'fixtures', 'assetgen', 'golden', '*.json')):
    graph = json.load(open(path, encoding='utf-8'))
    nodes = [n for n in graph.values() if isinstance(n, dict) and n.get('class_type') == 'NineRouterImage']
    if len(nodes) == 1:
        assert runfiles.requested_size(graph, {}) == nodes[0].get('inputs', {}).get('size', 'auto'), path
print('ok')
EOF
grep -qx ok "$TMP/anchor-size" && ok "requested_size: declared primary, numeric fallback, latent dimensions, malformed specs and golden graphs" \
  || no "requested_size cases" "$(cat "$TMP/anchor-size")"
rm -f "$SG/templates/hybrid-anchor.json" "$SG/purposes/icon-two.json"

echo "-- profile routing: resolve --profile (UNTESTED on RTX 5060)"
# Nothing here generates or measures anything: routing picks a template id and refuses one above the chosen profile.
PR="$TMP/profile-authoring"; PF="$TMP/profile-fallback"; PB="$TMP/profile-badroutes"
mkdir -p "$PR/assetgen/templates" "$PR/assetgen/runs" "$PF/assetgen" "$PB/assetgen"
cp "$ROOT/tests/fixtures/assetgen/local/hybrid-anchor-template.json" "$PR/assetgen/templates/hybrid-icon-ui.json"
echo '{"schema": "rpg-factory.assetgen-template-profiles/1", "routes": {"icon": {"local-8gb": "no-such-template"}}}' > "$PF/assetgen/template-profiles.json"
echo '{"schema": "rpg-factory.assetgen-template-profiles/1", "routes": {"icon": {"gpu-99": "x"}}}' > "$PB/assetgen/template-profiles.json"
# AGS STATE-DIR ARGS...: assetgen with its own state dir (auto cases never read or write the suite's $TMP/state)
AGS() { local s="$1"; shift; RPG_FACTORY_STATE_DIR="$s" python3 -B "$ROOT/scripts/assetgen/assetgen.py" "$@"; }
pq() { jq -r "$1" "$TMP/prof.json"; }

# 1. the data file
python3 -B - "$ROOT" > "$TMP/prof-data" 2>&1 <<'EOF'
import json, os, sys
root = sys.argv[1]
data = json.load(open(os.path.join(root, 'scripts', 'assetgen', 'data', 'template-profiles.json'), encoding='utf-8'))
hw = json.load(open(os.path.join(root, 'scripts', 'assetgen', 'data', 'hardware.json'), encoding='utf-8'))
ids = {p['id'] for p in hw['profiles']}
assert data['schema'] == 'rpg-factory.assetgen-template-profiles/1', data.get('schema')
assert data['description'].startswith('UNTESTED on RTX 5060:'), data.get('description')
assert isinstance(data['routes'], dict) and data['routes']
for purpose, routes in data['routes'].items():
    assert os.path.isfile(os.path.join(root, 'templates', 'assetgen', 'purposes', purpose + '.json')), purpose
    for profile, template in routes.items():
        assert profile in ids, (purpose, profile)
        assert isinstance(template, str) and template, (purpose, profile)
print('ok')
EOF
grep -qx ok "$TMP/prof-data" && ok "template-profiles.json: schema, UNTESTED description, core purposes, hardware profile ids" \
  || no "template-profiles.json data file" "$(cat "$TMP/prof-data")"

# 2. local-8gb on icon picks the hybrid template
AG resolve --purpose icon --style pixel-art --profile local-8gb --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
cp "$TMP/prof.json" "$TMP/prof-8gb.json"
[ $rc -eq 0 ] && [ "$(pq .template.id)" = hybrid-icon-ui ] && [ "$(pq .profile.id)" = local-8gb ] && [ "$(pq .profile.source)" = --profile ] \
  && [ "$(pq .profile.requires)" = local-8gb ] && jq -e '.profile.template_from | endswith("routes.icon.local-8gb")' "$TMP/prof.json" >/dev/null \
  && ok "resolve --profile local-8gb on icon picks hybrid-icon-ui from routes.icon.local-8gb" \
  || no "profile local-8gb rc=$rc" "$(cat "$TMP/err"; jq -c .profile "$TMP/prof.json" 2>&1)"

# 3. api-only keeps the staged API template
AG resolve --purpose icon --style pixel-art --profile api-only --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
cp "$TMP/prof.json" "$TMP/prof-api.json"
[ $rc -eq 0 ] && [ "$(pq .template.id)" = staged-icon ] && [ "$(pq .profile.template_from)" = "purpose default_template" ] \
  && [ "$(pq .profile.requires)" = api-only ] && ok "resolve --profile api-only on icon keeps staged-icon (purpose default_template)" \
  || no "profile api-only rc=$rc" "$(cat "$TMP/err"; jq -c .profile "$TMP/prof.json" 2>&1)"

# 4. a 4 GB machine is never handed the local-8gb template
AG resolve --purpose icon --style pixel-art --profile local-4gb --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(pq .template.id)" = staged-icon ] && [ "$(pq .profile.id)" = local-4gb ] \
  && ok "resolve --profile local-4gb on icon falls back to staged-icon, never the local-8gb template" \
  || no "profile local-4gb rc=$rc" "$(cat "$TMP/err"; jq -c .profile "$TMP/prof.json" 2>&1)"

# 5. --template above the chosen profile is refused with the VRAM reason
AG resolve --purpose icon --style pixel-art --profile local-4gb --template hybrid-icon-ui --authoring "$PR" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -qF VRAM "$TMP/err" && grep -qF "requires profile local-8gb" "$TMP/err" && grep -qF "chosen profile local-4gb" "$TMP/err" \
  && ok "--profile local-4gb --template hybrid-icon-ui: refused with the VRAM reason (exit 1)" || no "local-4gb refusal rc=$rc" "$(cat "$TMP/err")"
AG resolve --purpose icon --style pixel-art --profile api-only --template hybrid-icon-ui --authoring "$PR" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -qF "chosen profile api-only" "$TMP/err" \
  && ok "--profile api-only --template hybrid-icon-ui: refused (exit 1)" || no "api-only refusal rc=$rc" "$(cat "$TMP/err")"

# 6. without --profile nothing changes
AG resolve --purpose icon --style pixel-art --authoring "$PR" --json > "$TMP/prof-none.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && jq -e 'has("profile") | not' "$TMP/prof-none.json" >/dev/null && [ "$(jq -r .template.id "$TMP/prof-none.json")" = staged-icon ] \
  && diff <(jq -S . "$TMP/prof-none.json") <(jq -S 'del(.profile)' "$TMP/prof-api.json") > "$TMP/prof-diff" 2>&1 \
  && ok "without --profile: no profile key, staged-icon, equal to the --profile api-only spec minus .profile" \
  || no "no --profile spec rc=$rc" "$(cat "$TMP/err" "$TMP/prof-diff" 2>&1)"
AG resolve --purpose icon --style pixel-art --authoring "$PR" > "$TMP/prof-none.txt" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && ! grep -q '^profile ' "$TMP/prof-none.txt" && ok "without --profile: no profile line in the text output" \
  || no "no --profile text rc=$rc" "$(cat "$TMP/prof-none.txt" "$TMP/err")"
AG resolve --purpose icon --style pixel-art --template hybrid-icon-ui --authoring "$PR" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && ok "without --profile: --template hybrid-icon-ui still resolves (today's behaviour)" || no "no --profile --template rc=$rc" "$(cat "$TMP/err")"

# 7. purpose files unchanged: the same purpose hash with and without --profile
[ -n "$(jq -r .purpose.sha256 "$TMP/prof-none.json")" ] && [ "$(jq -r .purpose.sha256 "$TMP/prof-8gb.json")" = "$(jq -r .purpose.sha256 "$TMP/prof-none.json")" ] \
  && ok "--profile local-8gb keeps the purpose sha256 (no purpose file change)" \
  || no "purpose sha256 $(jq -r .purpose.sha256 "$TMP/prof-8gb.json") vs $(jq -r .purpose.sha256 "$TMP/prof-none.json")"

# 8. --template still overrides the route
AG resolve --purpose icon --style pixel-art --profile local-8gb --template staged-icon --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(pq .template.id)" = staged-icon ] && [ "$(pq .profile.template_from)" = --template ] \
  && ok "--profile local-8gb --template staged-icon: --template overrides the route" || no "template override rc=$rc" "$(cat "$TMP/err"; jq -c .profile "$TMP/prof.json" 2>&1)"

# 9. a route naming a template no layer has falls back with a warning
AG resolve --purpose icon --style pixel-art --profile local-8gb --authoring "$PF" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(pq .template.id)" = staged-icon ] \
  && jq -e 'any(.warnings[]; contains("no-such-template") and contains("falling back"))' "$TMP/prof.json" >/dev/null \
  && ok "route to a missing template falls back to staged-icon with a warning" || no "fallback rc=$rc" "$(cat "$TMP/err"; jq -c .warnings "$TMP/prof.json" 2>&1)"

# 10. auto: no recorded file, a recorded local-8gb, a recorded unknown profile (each with its own state dir)
AGS "$TMP/pstate-10a" resolve --purpose icon --style pixel-art --profile auto --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(pq .profile.id)" = api-only ] && [ "$(pq .profile.requested)" = auto ] \
  && jq -e '.profile.source | startswith("auto: no recorded profile")' "$TMP/prof.json" >/dev/null \
  && ok "auto without a recorded profile: api-only (requested auto)" || no "auto no file rc=$rc" "$(cat "$TMP/err"; jq -c .profile "$TMP/prof.json" 2>&1)"
mkdir -p "$TMP/pstate-10b/assetgen" "$TMP/pstate-10c/assetgen"
echo '{"profile": {"id": "local-8gb"}}' > "$TMP/pstate-10b/assetgen/hardware-profile.json"
echo '{"profile": {"id": "gpu-99"}}' > "$TMP/pstate-10c/assetgen/hardware-profile.json"
AGS "$TMP/pstate-10b" resolve --purpose icon --style pixel-art --profile auto --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(pq .template.id)" = hybrid-icon-ui ] && [ "$(pq .profile.id)" = local-8gb ] \
  && jq -e '.profile.source | startswith("recorded ")' "$TMP/prof.json" >/dev/null \
  && ok "auto with a recorded local-8gb profile picks hybrid-icon-ui" || no "auto recorded rc=$rc" "$(cat "$TMP/err"; jq -c .profile "$TMP/prof.json" 2>&1)"
AGS "$TMP/pstate-10c" resolve --purpose icon --style pixel-art --profile auto --authoring "$PR" --json > "$TMP/prof.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(pq .profile.id)" = api-only ] && jq -e 'any(.warnings[]; contains("gpu-99"))' "$TMP/prof.json" >/dev/null \
  && ok "auto with a recorded unknown profile: api-only and a warning" || no "auto unknown rc=$rc" "$(cat "$TMP/err"; jq -c '.profile, .warnings' "$TMP/prof.json" 2>&1)"
[ ! -e "$TMP/state/assetgen/hardware-profile.json" ] && ok "auto cases leave the suite's state dir untouched" \
  || no "suite state dir has assetgen/hardware-profile.json"

# 11. an unknown profile value
AG resolve --purpose icon --style pixel-art --profile bogus >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -qF "api-only, local-4gb, local-8gb, auto" "$TMP/err" && ok "--profile bogus: exit 2 naming the profiles" \
  || no "--profile bogus rc=$rc" "$(cat "$TMP/err")"

# 12. a malformed game routes file is blamed on the game file
AG resolve --purpose icon --style pixel-art --profile local-8gb --authoring "$PB" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -qF "game:assetgen/template-profiles.json" "$TMP/err" && grep -qF gpu-99 "$TMP/err" \
  && ok "malformed game template-profiles.json: exit 1 naming the file and the bad profile" || no "bad routes rc=$rc" "$(cat "$TMP/err")"

# 13. --out keeps spec.profile
mkdir -p "$PR/assetgen/runs/prof-001"
AG resolve --purpose icon --style pixel-art --profile local-8gb --authoring "$PR" --out "$PR/assetgen/runs/prof-001/spec.json" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .profile.id "$PR/assetgen/runs/prof-001/spec.json")" = local-8gb ] \
  && [ "$(jq -r .profile.template "$PR/assetgen/runs/prof-001/spec.json")" = hybrid-icon-ui ] \
  && ok "resolve --out writes spec.profile (local-8gb, hybrid-icon-ui)" || no "--out profile rc=$rc" "$(cat "$TMP/err")"

# 14. the text output names the profile; local profiles are marked UNTESTED
AG resolve --purpose icon --style pixel-art --profile local-8gb --authoring "$PR" > "$TMP/prof.txt" 2>"$TMP/err"; rc=$?
line=$(awk 'index($0, "profile local-8gb [--profile], template hybrid-icon-ui") == 1' "$TMP/prof.txt")
[ $rc -eq 0 ] && [ -n "$line" ] && printf '%s\n' "$line" | grep -qF "UNTESTED on RTX 5060" \
  && ok "text output: profile local-8gb line marked UNTESTED on RTX 5060" || no "local-8gb text rc=$rc" "$(cat "$TMP/prof.txt" "$TMP/err")"
AG resolve --purpose icon --style pixel-art --profile api-only --authoring "$PR" > "$TMP/prof.txt" 2>"$TMP/err"; rc=$?
line=$(grep '^profile api-only ' "$TMP/prof.txt")
[ $rc -eq 0 ] && [ -n "$line" ] && ! printf '%s\n' "$line" | grep -qF UNTESTED \
  && ok "text output: profile api-only line without UNTESTED" || no "api-only text rc=$rc" "$(cat "$TMP/prof.txt" "$TMP/err")"

echo "-- style lock consistency QA and the anchor-aware review (qa style-* rows, review-cmd --phase image/prompt)"
# fixture icons on a transparent background (icon qa: alpha, corners, not-blank): a two-tone disc, an outlined disc
python3 -B - "$ROOT" "$FX" > "$TMP/o" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
out = sys.argv[2]
def disc(name, a, b, ring=None, w=256, h=256):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            d = ((x - w / 2) ** 2 + (y - h / 2) ** 2) ** 0.5
            r = min(w, h) * 0.3
            if d < r - 6 or (ring is None and d < r):
                px += bytes((a if x < w // 2 else b) + (255,))
            elif ring is not None and d < r:
                px += bytes(ring + (255,))
            else:
                px += bytes((0, 0, 0, 0))
    open(os.path.join(out, name), "wb").write(png.encode(w, h, bytes(px)))
disc("sl-warm.png", (170, 85, 51), (190, 105, 71))            # inside 48 of #aa5533
disc("sl-blue.png", (40, 60, 200), (60, 80, 220))             # far from #aa5533
disc("sl-dark.png", (20, 20, 30), (35, 35, 45))               # tone far below the icon-ok anchors
disc("sl-outlined.png", (230, 200, 120), (240, 210, 130), ring=(10, 10, 10))
disc("sl-wide.png", (170, 85, 51), (190, 105, 71), w=384, h=256)
print("ok")
EOF
grep -qx ok "$TMP/o" || no "style QA fixtures" "$(cat "$TMP/o")"
sq="$SR/sl-qa-001"; slrun sl-qa-001 icon && AG render --run "$sq" >/dev/null 2>"$TMP/err" || no "style QA run" "$(cat "$TMP/err")"
# the style fixtures are 256x256: the run keeps the default size floor so only the style rows vary
jq '.purpose.data.qa.size |= del(.min_side, .min_pixels)' "$sq/spec.json" > "$TMP/sq-spec.json"
sqa() { # sqa PNG JQ-EDIT: the style QA run with outputs/out.png = PNG and spec.json = the resolved spec edited by JQ-EDIT
  rm -f "$sq/outputs/"*.png; cp "$FX/$1" "$sq/outputs/out.png"
  jq "$2" "$TMP/sq-spec.json" > "$sq/spec.json"
  AG qa --run "$sq" --json > "$TMP/sq.json" 2>"$TMP/err"; rc=$?
}
sst() { jq -r --arg c "$1" '[.results[] | select(.check == $c) | .state] | join(",")' "$TMP/sq.json"; }
swhy() { jq -r --arg c "$1" '[.results[] | select(.check == $c) | .reasons[]] | join("; ")' "$TMP/sq.json"; }
PAL='.style.data.palette = {"text": "Warm earthy palette.", "colors": [{"hex": "#aa5533", "role": "primary"}]}'
sqa sl-warm.png "$PAL"
[ $rc -eq 0 ] && [ "$(sst style-palette)" = PASS ] && [ "$(jq -r .state "$TMP/sq.json")" = PASS ] && swhy style-palette | grep -q "100.0% of opaque pixels within 48 of 1 palette colours" \
  && ok "qa style-palette PASS: every opaque pixel near the palette" || no "palette PASS rc=$rc $(sst style-palette)" "$(swhy style-palette; cat "$TMP/err")"
sqa sl-blue.png "$PAL"
[ $rc -eq 0 ] && [ "$(sst style-palette)" = WARN ] && [ "$(jq -r '.state + " " + (.summary.WARN | tostring)' "$TMP/sq.json")" = "PASS 1" ] \
  && ok "qa style-palette WARN (default severity): the qa state stays PASS, exit 0, summary counts the WARN" || no "palette WARN rc=$rc $(sst style-palette)" "$(jq -c . "$TMP/sq.json")"
AG qa --run "$sq" > "$TMP/o" 2>&1; grep -q "^WARN outputs/out.png style-palette: " "$TMP/o" && grep -q "^assetgen qa: PASS ([0-9]* PASS, 1 WARN, 0 FAIL, [0-9]* NOT_AVAILABLE)$" "$TMP/o" \
  && ok "qa text: the WARN row and the WARN count" || no "qa text WARN" "$(cat "$TMP/o")"
sqa sl-blue.png "$PAL | .style.data.palette.severity = \"fail\""
[ $rc -eq 1 ] && [ "$(sst style-palette)" = FAIL ] && [ "$(jq -r .state "$TMP/sq.json")" = FAIL ] \
  && ok "qa style-palette FAIL (palette severity fail): the qa state is FAIL, exit 1" || no "palette FAIL rc=$rc $(sst style-palette)" "$(jq -c . "$TMP/sq.json")"
sqa sl-blue.png '.style.data.palette = "Warm earthy palette."'
[ $rc -eq 0 ] && [ "$(sst style-palette)" = NOT_AVAILABLE ] && [ "$(jq -r .state "$TMP/sq.json")" = PASS ] \
  && ok "qa style-palette NOT_AVAILABLE (prose palette): the qa state stays PASS, exit 0 (not 3)" || no "palette NA rc=$rc $(sst style-palette)" "$(jq -c . "$TMP/sq.json")"
req=$(jq -r '[.results[] | select(.check | startswith("png-")) | .check] | unique | join(",")' "$TMP/sq.json")
[ "$req" = "png-alpha,png-corners,png-edge-fringe,png-not-blank,png-size,png-valid" ] && [ "$(jq -r '[.results[].check] | map(select(startswith("style-"))) | join(",")' "$TMP/sq.json")" = "style-palette,style-tone,style-edges,style-canvas" ] \
  && python3 -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import runfiles, json; q = json.load(open(sys.argv[2]))["purpose"]["data"]["qa"]; sys.exit(0 if not any(c.startswith("style-") for c in runfiles.required_checks(q)) else 1)' "$ROOT/scripts/assetgen" "$sq/spec.json" \
  && ok "style rows come after the required checks and are never required checks (runfiles.required_checks)" || no "style rows order/required: $req"
# tone against the selected anchors (references/anchor-*.png copies of icon-ok.png)
sqa icon-ok.png '.style.data.tone = {"tolerance": 0.05}'
[ $rc -eq 0 ] && [ "$(sst style-tone)" = PASS ] && swhy style-tone | grep -q "inside .* of 3 anchor(s)" \
  && ok "qa style-tone PASS: the output's luminance and saturation inside the 3 anchors' range" || no "tone PASS rc=$rc $(sst style-tone)" "$(swhy style-tone)"
sqa sl-dark.png '.style.data.tone = {"tolerance": 0.05}'
[ $rc -eq 0 ] && [ "$(sst style-tone)" = WARN ] && swhy style-tone | grep -q "mean luminance [0-9.]* outside" \
  && ok "qa style-tone WARN: a far darker output than the anchors" || no "tone WARN rc=$rc $(sst style-tone)" "$(swhy style-tone)"
sqa sl-dark.png '.style.data.tone = {"tolerance": 0.05, "severity": "fail"}'
[ $rc -eq 1 ] && [ "$(sst style-tone)" = FAIL ] && ok "qa style-tone FAIL with severity fail" || no "tone FAIL rc=$rc $(sst style-tone)"
mv "$sq/references" "$TMP/sq-refs"
sqa sl-dark.png '.style.data.tone = {"tolerance": 0.05}'
[ $rc -eq 0 ] && [ "$(sst style-tone)" = NOT_AVAILABLE ] && swhy style-tone | grep -q "no anchors" \
  && ok "qa style-tone NOT_AVAILABLE without the run's anchor copies" || no "tone NA rc=$rc $(sst style-tone)" "$(swhy style-tone)"
mv "$TMP/sq-refs" "$sq/references"
# edges (purpose qa.outlines + outline.edge_darkness) and canvas (style.canvas[family])
EDGE='.purpose.data.qa.outlines = true | .style.data.outline = {"text": "Dark outlines.", "edge_darkness": {"max_luminance": 80, "min_ratio": 0.5}}'
sqa sl-outlined.png "$EDGE"
[ $rc -eq 0 ] && [ "$(sst style-edges)" = PASS ] && ok "qa style-edges PASS: an outlined icon" || no "edges PASS rc=$rc $(sst style-edges)" "$(swhy style-edges)"
sqa sl-outlined.png '.style.data.outline = {"text": "x", "edge_darkness": {}}'
[ "$(sst style-edges)" = NOT_AVAILABLE ] && swhy style-edges | grep -q "qa.outlines" && ok "qa style-edges NOT_AVAILABLE for a purpose without qa.outlines" || no "edges NA $(sst style-edges)"
sqa sl-warm.png '.style.data.canvas = {"props": {"aspect": "1:1", "min_side": 128}}'
[ $rc -eq 0 ] && [ "$(sst style-canvas)" = PASS ] && swhy style-canvas | grep -q "^family props: 256x256" && ok "qa style-canvas PASS for the run's family (props)" || no "canvas PASS $(sst style-canvas)" "$(swhy style-canvas)"
sqa sl-wide.png '.style.data.canvas = {"props": {"aspect": "1:1"}} | .purpose.data.qa.size = {"mode": "any"}'
[ $rc -eq 0 ] && [ "$(sst style-canvas)" = WARN ] && ok "qa style-canvas WARN: 3:2 output for a 1:1 family canvas" || no "canvas WARN rc=$rc $(sst style-canvas)" "$(swhy style-canvas)"
sqa sl-warm.png '.style.data.canvas = {"characters": {"aspect": "1:1"}}'
[ "$(sst style-canvas)" = NOT_AVAILABLE ] && ok "qa style-canvas NOT_AVAILABLE without a canvas entry for the family" || no "canvas NA $(sst style-canvas)"
# old runs: a spec without style_lock gets exactly the old rows
sqa sl-blue.png "del(.style_lock) | $PAL"
[ $rc -eq 0 ] && [ "$(jq -r '[.results[] | select(.check | startswith("style-"))] | length' "$TMP/sq.json")" = 0 ] && [ "$(jq -r .state "$TMP/sq.json")" = PASS ] \
  && ok "qa: a spec without style_lock (older run) gets no style rows" || no "old run style rows" "$(jq -c .results "$TMP/sq.json")"

# review-cmd --phase image: anchors attached after outputs, anchor rubric item, rejection items, binding style + anchors
cp "$TMP/sq-spec.json" "$sq/spec.json"; rm -f "$sq/outputs/"*.png; cp "$FX/sl-warm.png" "$sq/outputs/out.png"; AG qa --run "$sq" >/dev/null
AG review-cmd --phase image --run "$sq" --codex codex --json > "$TMP/rv.json" 2>"$TMP/err"; rc=$?
sqabs=$(cd "$sq" && { pwd -W 2>/dev/null || pwd; })
want="$sqabs/outputs/out.png $sqabs/review/composite-dark.png $sqabs/review/composite-light.png $sqabs/references/anchor-b-strong.png $sqabs/references/anchor-a-canon.png $sqabs/references/anchor-c-supp.png"
[ $rc -eq 0 ] && [ "$(jq -r '[.argv | to_entries[] | select(.value == "-i") | .key + 1] as $i | [.argv[$i[]]] | join(" ")' "$TMP/rv.json")" = "$want" ] \
  && [ "$(jq -r '.anchors | join(",")' "$TMP/rv.json")" = "references/anchor-b-strong.png,references/anchor-a-canon.png,references/anchor-c-supp.png" ] \
  && ok "review-cmd image: -i outputs first, then the alpha composites, then the selected anchors in selection order" || no "review argv rc=$rc" "$(cat "$TMP/err"; jq -c .argv "$TMP/rv.json")"
jq -r .stdin "$TMP/rv.json" > "$TMP/rv.txt"
grep -qF "The image matches the attached anchors in palette, lighting, line, detail density and rendering." "$TMP/rv.txt" \
  && grep -qF "Not repeated: too_detailed - No fine filigree on props." "$TMP/rv.txt" \
  && grep -q "^Attached images (one per -i): outputs/out.png, review/composite-dark.png, review/composite-light.png, references/anchor-b-strong.png, references/anchor-a-canon.png, references/anchor-c-supp.png$" "$TMP/rv.txt" \
  && grep -q "^references/anchor-b-strong.png is not an output: style anchor b-strong (strong; palette, shape, line) of style rpg-base" "$TMP/rv.txt" \
  && ok "review-cmd image: anchor rubric item, one item per relevant rejection, anchors named as not outputs" || no "review rubric" "$(cat "$TMP/rv.txt")"
n_rub=$(jq '.purpose.data.image_rubric | length' "$sq/spec.json")
[ "$(jq -r --argjson n "$n_rub" '.rubric[$n:] | join("|")' "$TMP/rv.json")" = "The image matches the attached anchors in palette, lighting, line, detail density and rendering.|Not repeated: palette_off - the rejected asset sl-icon-001 outputs/out.png|Not repeated: too_detailed - No fine filigree on props.|Not repeated: too_detailed - No gold trim.|Not repeated: too_detailed - No noise.|The edges of every output with alpha are clean on both the dark and the light composite: no coloured fringe, halo, speckle or matte line around the subject." ] \
  && grep -q "^$((n_rub + 2))\. Not repeated: palette_off" "$TMP/rv.txt" \
  && ok "review-cmd --json prints the same rubric items (purpose rubric, then anchor, rejection and edge items) for Claude's own review" || no "rubric json" "$(jq -c .rubric "$TMP/rv.json")"
[ "$(jq -c '.binding.style == ($s[0].style_lock.style)' --slurpfile s "$sq/spec.json" "$TMP/rv.json")" = true ] \
  && [ "$(jq -c '[.binding.anchors[] | .anchor_id] | join(",")' -r "$TMP/rv.json")" = "b-strong,a-canon,c-supp" ] \
  && [ "$(jq -c --slurpfile s "$sq/spec.json" '[.binding.anchors[].sha256] == [$s[0].style_lock.references[].sha256]' "$TMP/rv.json")" = true ] \
  && grep -qF '"style": {"sha256": ' "$TMP/rv.txt" \
  && ok "review-cmd image binding: style ref and [{anchor_id, sha256}] of the attached anchors (also in the prompt)" || no "binding" "$(jq -c .binding "$TMP/rv.json")"
bound "$sq" image PASS codex > "$sq/review-image.json"
python3 -B - "$ROOT" "$sq/review-image.json" "$TMP/rv.json" > "$TMP/o" 2>&1 <<'EOF'
import json, sys
sys.path.insert(0, sys.argv[1] + "/scripts/assetgen")
import runfiles
v = runfiles.read_verdict(sys.argv[2], "image")
b = json.load(open(sys.argv[3], encoding="utf-8"))["binding"]
assert v["style"] == b["style"] and v["anchors"] == b["anchors"], v
assert "style" not in runfiles.read_verdict(sys.argv[2], "prompt"), "prompt phase keeps no image binding"
print("ok")
EOF
grep -qx ok "$TMP/o" && ok "read_verdict keeps the style and anchors of an image verdict" || no "read_verdict style lock" "$(cat "$TMP/o")"
mv "$sq/references/anchor-a-canon.png" "$TMP/a-canon.png"
AG review-cmd --phase image --run "$sq" --codex codex --json > /dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "references/anchor-a-canon.png is missing: run .*render --run" "$TMP/err" && ok "review-cmd image: a selected anchor copy missing is refused (render --run copies it)" || no "missing anchor rc=$rc" "$(cat "$TMP/err")"
mv "$TMP/a-canon.png" "$sq/references/anchor-a-canon.png"
# prompt phase: direction rejections join Must avoid; no anchors and no style binding there
AG review-cmd --phase prompt --run "$sq" --codex codex --json > "$TMP/rp.json" 2>"$TMP/err"
jq -r .stdin "$TMP/rp.json" | grep -q "^Must avoid: .*, No fine filigree on props. (rejected direction r-props), No gold trim. (rejected direction too-detailed-001), No noise. (rejected direction too-detailed-002)$" \
  && [ "$(jq -r '(.binding | has("style") or has("anchors")) or (.argv | index("-i") != null) or (.rubric | map(startswith("Not repeated")) | any)' "$TMP/rp.json")" = false ] \
  && ok "review-cmd prompt: direction rejections in Must avoid; no -i, no anchor binding, no rejection rubric items" || no "prompt review" "$(cat "$TMP/err"; jq -r .stdin "$TMP/rp.json")"
# both phases name the style's forbidden list and the resolved outline and shape_language text (lighting, palette as hints)
sr_="$SR/sl-rules-001"; rm -rf "$sr_"; cp -R "$sq" "$sr_"
jq '.style.data.forbidden = ["photo texture", "lens flare"] | .style.data.outline = {"text": "Dark 2px outline.", "severity": "warn"}
    | .style.data.shape_language = "Chunky rounded silhouettes."' "$sq/spec.json" > "$sr_/spec.json"
for ph in prompt image; do
  AG review-cmd --phase $ph --run "$sr_" --codex codex --json > "$TMP/rr.json" 2>"$TMP/err"; rc=$?
  jq -r .stdin "$TMP/rr.json" > "$TMP/rr.txt"
  [ $rc -eq 0 ] && grep -qx "Style forbidden (never in the prompt or the image): photo texture, lens flare" "$TMP/rr.txt"     && grep -qx "Style outline: Dark 2px outline." "$TMP/rr.txt" && grep -qx "Style shape language: Chunky rounded silhouettes." "$TMP/rr.txt"     && grep -q "^Hints (the purpose wins for technical constraints): .*palette: " "$TMP/rr.txt"     && ok "review-cmd $ph: style forbidden list, outline and shape_language text for the reviewer" || no "review rules $ph rc=$rc" "$(cat "$TMP/err" "$TMP/rr.txt")"
done
# old runs: a spec without style_lock reviews exactly as before
sl_="$SR/sl-legacy-001"; cp -R "$sq" "$sl_"; jq 'del(.style_lock)' "$sq/spec.json" > "$sl_/spec.json"; rm -rf "$sl_/references"
AG review-cmd --phase image --run "$sl_" --codex codex --json > "$TMP/rl.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '(.binding | keys | join(",")) + " " + (.anchors | length | tostring) + " " + ([.argv[] | select(. == "-i")] | length | tostring) + " " + (.composites | length | tostring)' "$TMP/rl.json")" = "outputs,prompt_sha256,requirements_sha256 0 3 2" ] \
  && ! jq -r .stdin "$TMP/rl.json" | grep -q "attached anchors\|Not repeated" \
  && ok "review-cmd image on an old spec without style_lock: old binding keys, no anchors, no style rubric items" || no "legacy review rc=$rc" "$(cat "$TMP/err"; jq -c '[.binding, .argv]' "$TMP/rl.json")"
jq 'del(.style.data.forbidden, .style.data.outline, .style.data.shape_language)' "$sl_/spec.json" > "$TMP/s" && mv "$TMP/s" "$sl_/spec.json"
AG review-cmd --phase prompt --run "$sl_" --codex codex --json > "$TMP/rl.json" 2>"$TMP/err"; jq -r .stdin "$TMP/rl.json" > "$TMP/rr.txt"
grep -qx "Style forbidden (never in the prompt or the image): none" "$TMP/rr.txt" && grep -qx "Style outline: none" "$TMP/rr.txt" && grep -qx "Style shape language: none" "$TMP/rr.txt"   && ok "review-cmd: a style without forbidden, outline or shape_language says none" || no "review rules none" "$(cat "$TMP/err" "$TMP/rr.txt")"

# qa.json binds the anchor copies style-tone read (final review P2): an anchor copy changed with the output bytes kept
# makes the report stale in the quality plugin; qa re-run binds the new copy
gqa() { # gqa RUN-DIR AUTHORING: "STATE|reasons" of the plugin's gen-run-qa row for the run's run.md
  python3 -B - "$ROOT" "$2" "$1" <<'EOF2'
import importlib.util, json, os, re, sys
from pathlib import Path
root, auth, run = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
sys.path.insert(0, str(root / "scripts" / "checks"))
from domains._api import Context
spec = importlib.util.spec_from_file_location("assetgen_plugin_gqa", root / "scripts" / "checks" / "domains" / "assetgen.py")
plugin = importlib.util.module_from_spec(spec); spec.loader.exec_module(plugin)
reg = json.load(open(root / "registry.json", encoding="utf-8"))
path = run / "run.md"
obj = json.loads(re.match(r"\A---json\s*\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S).group(1))
ctx = Context(str(auth), reg, path.relative_to(auth).as_posix(), {}, None, {"authoring": auth})
print("\n".join("%s|%s" % (r.state, "; ".join(r.reasons)) for r in plugin.check(obj, ctx) if r.check == "gen-run-qa"))
EOF2
}
jq '.style.data.tone = {"tolerance": 0.05}' "$TMP/sq-spec.json" > "$sq/spec.json"
python3 -B -c 'import json, sys; sys.path.insert(0, sys.argv[1]); import layers; p = sys.argv[2]; s = json.load(open(p)); s["purpose"]["sha256"] = layers.content_hash(s["purpose"]["data"]); json.dump(s, open(p, "w"))' "$ROOT/scripts/assetgen" "$sq/spec.json"
rm -f "$sq/outputs/"*.png; cp "$FX/icon-ok.png" "$sq/outputs/out.png"
AG qa --run "$sq" >/dev/null; bound "$sq" prompt PASS codex > "$sq/review-prompt.json"; bound "$sq" image PASS codex > "$sq/review-image.json"
bound "$sq" image PASS claude > "$sq/review-image-claude.json"; AG manifest --run "$sq" >/dev/null
[ "$(jq -r '[.style_binding.anchors[] | .anchor_id + ":" + .path] | join(",")' "$sq/qa.json")" = "b-strong:references/anchor-b-strong.png,a-canon:references/anchor-a-canon.png,c-supp:references/anchor-c-supp.png" ]   && [ "$(jq -r '.style_binding.anchors[1].sha256' "$sq/qa.json")" = "$(sha256sum "$sq/references/anchor-a-canon.png" | cut -d' ' -f1)" ]   && [ "$(jq -r .style_binding.family "$sq/qa.json")" = props ]   && ok "qa.json style_binding records the family and each selected anchor copy (path, sha256) style-tone read" || no "anchor style_binding" "$(jq -c .style_binding "$sq/qa.json")"
gqa "$sq" "$SC" > "$TMP/gqa"; grep -Eq "^(PASS|WARN)\|" "$TMP/gqa" && ! grep -q "re-run qa" "$TMP/gqa"   && ok "gen-run-qa PASS (style WARN rows aside) on a style-locked run with anchors and a current style_binding" || no "anchor run gen-run-qa" "$(cat "$TMP/gqa")"
cp "$sq/references/anchor-a-canon.png" "$TMP/a-canon.png"; cp "$FX/sl-dark.png" "$sq/references/anchor-a-canon.png"
gqa "$sq" "$SC" > "$TMP/gqa"; grep -q "^FAIL|.*qa.json was graded with other style inputs (anchors differ" "$TMP/gqa" && cmp -s "$FX/icon-ok.png" "$sq/outputs/out.png"   && ok "tone-reference input changed (an anchor copy), output bytes kept: gen-run-qa FAIL as stale" || no "anchor changed gen-run-qa" "$(cat "$TMP/gqa")"
AG qa --run "$sq" >/dev/null; AG manifest --run "$sq" >/dev/null; gqa "$sq" "$SC" > "$TMP/gqa"
! grep -q "style inputs" "$TMP/gqa" && ok "qa re-run after the anchor change binds the new copy (not stale)" || no "anchor rerun gen-run-qa" "$(cat "$TMP/gqa")"
jq '.style_lock.family = "characters"' "$sq/spec.json" > "$TMP/s" && mv "$TMP/s" "$sq/spec.json"
gqa "$sq" "$SC" > "$TMP/gqa"; grep -q "^FAIL|.*other style inputs (family differ" "$TMP/gqa" && ok "family changed in spec.json after qa: gen-run-qa FAIL as stale" || no "family changed gen-run-qa" "$(cat "$TMP/gqa")"
cp "$TMP/a-canon.png" "$sq/references/anchor-a-canon.png"; cp "$TMP/sq-spec.json" "$sq/spec.json"
rm -f "$sq/run.md" "$sq/review-prompt.json" "$sq/review-image.json" "$sq/review-image-claude.json"

# drift (read-only): older version and hash changed
git -C "$SC" add -A && git -C "$SC" "${G[@]}" commit -qm "runs and records"
AG drift --authoring "$SC" --json > "$TMP/dr.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '[.items[] | .kind + " " + .id + " " + .state + " " + .project_style + " " + .version_state] | join(",")' "$TMP/dr.json")" = "gen-run AGEN-sl-override-001 style-id-mismatch rpg-base " ] \
  && ok "drift: nothing behind the current style; the --style-override run under anime-cel is a style-id-mismatch (project style rpg-base)" || no "drift clean rc=$rc" "$(cat "$TMP/err" "$TMP/dr.json")"
AG drift --authoring "$SC" > "$TMP/dr.txt" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && grep -q "^style-id-mismatch gen-run AGEN-sl-override-001 (assetgen/runs/sl-override-001/run.md): recorded anime-cel v[^ ]* [0-9a-f-]*, current v[^ ]* [0-9a-f]*, project style rpg-base$" "$TMP/dr.txt" \
  && grep -qx "assetgen drift: 1 item(s) behind the current style or outside the project's styles" "$TMP/dr.txt" \
  && ok "drift text: the style-id-mismatch line names the project style; the footer fits every item" || no "drift text mismatch rc=$rc" "$(cat "$TMP/err" "$TMP/dr.txt")"
jq '.version = 3' "$SG/styles/rpg-base.json" > "$TMP/s" && mv "$TMP/s" "$SG/styles/rpg-base.json"
git -C "$SC" "${G[@]}" commit -qam "style v3"
AG drift --authoring "$SC" --json > "$TMP/dr.json" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '[.items[] | select(.style.style_id == "rpg-base" and .id != "too-detailed-002") | .state] | unique | join(",")' "$TMP/dr.json")" = older-version ] \
  && jq -e '[.items[] | select(.kind == "gen-run" and .id == "AGEN-sl-icon-001")] | length == 1' "$TMP/dr.json" >/dev/null \
  && jq -e '[.items[] | select(.kind == "anchor" and .id == "sl-icon-001-1")] | length == 1' "$TMP/dr.json" >/dev/null \
  && [ "$(jq -r '[.items[] | select(.kind == "rejection" and .id == "too-detailed-002") | .state] | join(",")' "$TMP/dr.json")" = hash-changed ] \
  && [ -z "$(git -C "$SC" status --porcelain)" ] \
  && ok "drift: gen-runs, anchors and rejections on version 2 listed older-version (version-free rejection hash-changed only), nothing written" \
  || no "drift older-version rc=$rc" "$(cat "$TMP/err"; jq -c '[.items[] | [.kind, .id, .state]]' "$TMP/dr.json"; git -C "$SC" status --porcelain)"
jq '.version = 2' "$SG/styles/rpg-base.json" > "$TMP/s" && mv "$TMP/s" "$SG/styles/rpg-base.json"
jq '.prefix = "RPG base art, revised,"' "$SG/styles/rpg-base.json" > "$TMP/s" && mv "$TMP/s" "$SG/styles/rpg-base.json"
AG drift --authoring "$SC" > "$TMP/dr.txt" 2>"$TMP/err"; rc=$?
[ $rc -eq 0 ] && grep -q "^hash-changed anchor a-canon (assetgen/styles/rpg-base/anchors/a-canon.json): recorded rpg-base v2 [0-9a-f]\{12\}, current v2 [0-9a-f]\{12\}$" "$TMP/dr.txt" \
  && grep -q "^hash-changed gen-run AGEN-sl-icon-001 " "$TMP/dr.txt" && ! grep -q "^older-version" "$TMP/dr.txt" && grep -q "^assetgen drift: [1-9][0-9]* item(s) behind the current style or outside the project's styles$" "$TMP/dr.txt" \
  && ok "drift text: same version, changed style data -> hash-changed" || no "drift hash-changed rc=$rc" "$(cat "$TMP/err" "$TMP/dr.txt")"
git -C "$SC" checkout -q -- .

echo "-- gen-run-style (quality plugin): style lock refs, anchor approval, image bytes, source runs, override"
python3 -B - "$ROOT" "$TMP/style-plugin" "$FX/icon-ok.png" > "$TMP/gs" 2>&1 <<'EOF'
import hashlib, importlib.util, json, os, sys
root, A, png = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, os.path.join(root, "scripts", "checks"))
from domains._api import Context
spec_ = importlib.util.spec_from_file_location("assetgen_plugin_style", os.path.join(root, "scripts", "checks", "domains", "assetgen.py"))
plugin = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(plugin)
layers, stylelock = plugin.engine("layers"), plugin.engine("stylelock")
G = os.path.join(A, "assetgen")
os.makedirs(os.path.join(G, "styles"), exist_ok=True)
v1 = {"schema": "rpg-factory.assetgen-style/1", "title": "RPG base", "version": 1, "status": "active", "prefix": "RPG base art,"}
v2 = dict(v1, version=2, prefix="RPG base art, warmer,")
json.dump(v2, open(os.path.join(G, "styles", "rpg-base.json"), "w", encoding="utf-8"))
ref2 = stylelock.style_ref(layers.load("style", "rpg-base", A))
ref1 = {"style_id": "rpg-base", "version": 1, "sha256": layers.content_hash(v1)}
img = open(png, "rb").read()
SIGNED = {"seed-001", "src-ok-001", "src-agent-001"}  # runs whose signed approval verifies (ctx.approval stub)


class Ctx(Context):
    def approval(self, artifact_id):
        ok = artifact_id[len("AGEN-"):] in SIGNED
        return {"state": "verified" if ok else "missing", "reasons": [] if ok else ["no signed approval"]}


for rid, status in (("seed-001", "approved"), ("seed2-001", "approved"), ("draft-001", "proposed")):
    os.makedirs(os.path.join(G, "runs", rid), exist_ok=True)
    with open(os.path.join(G, "runs", rid, "run.md"), "w", encoding="utf-8") as f:
        f.write("---json\n%s\n---\n" % json.dumps({"id": "AGEN-" + rid, "status": status}))


def anchor(aid, ref, run="seed-001", status="active", by="Dana", n=0, output="outputs/a.png"):
    d = os.path.join(G, "styles", "rpg-base", "anchors"); os.makedirs(d, exist_ok=True)
    data = img + bytes([n])  # distinct bytes per anchor (a trailing byte, never decoded)
    open(os.path.join(d, aid + ".png"), "wb").write(data)
    sha = hashlib.sha256(data).hexdigest()
    json.dump({"schema": stylelock.ANCHOR_SCHEMA, "id": aid, "status": status, "style": ref, "family": "props",
               "dimensions": ["palette"], "strength": "canonical", "image": aid + ".png", "image_sha256": sha,
               "source_run": {"run_id": run, "output": output, "sha256": sha},
               "approved_by": by if status == "active" else None, "approved_on": "2026-11-01" if status == "active" else None},
              open(os.path.join(d, aid + ".json"), "w", encoding="utf-8"))
    return sha


shas = {"a-good": anchor("a-good", ref2, n=1), "a-agent": anchor("a-agent", ref2, by="claude-opus", n=2),
        "a-old": anchor("a-old", ref1, n=3), "a-noimg": anchor("a-noimg", ref2, n=4),
        "a-draftsrc": anchor("a-draftsrc", ref2, run="draft-001", n=5), "a-unsigned": anchor("a-unsigned", ref2, run="seed2-001", n=6),
        "a-proposed": anchor("a-proposed", ref2, status="proposed", n=7), "a-retired": anchor("a-retired", ref2, status="retired", n=8),
        "a-bytes": anchor("a-bytes", ref2, n=9)}
os.remove(os.path.join(G, "styles", "rpg-base", "anchors", "a-noimg.png"))
open(os.path.join(G, "styles", "rpg-base", "anchors", "a-bytes.png"), "ab").write(b"x")
reg = json.load(open(os.path.join(root, "registry.json"), encoding="utf-8"))


def style_rows(rid, status="proposed", refs=(), ref=ref2, override=None, lock=True, outputs=()):
    spec = {"run_id": rid, "style": {"id": ref["style_id"], "layer": "game", "sha256": ref["sha256"]},
            "outputs": [{"path": p, "sha256": s} for p, s in outputs]}
    if lock:
        spec["style_lock"] = {"project": None, "family": "props", "family_source": "purpose", "style": ref, "override": override,
                              "max_references": 3, "rejections": [],
                              "references": [{"anchor_id": a, "sha256": shas.get(a, "0" * 64)} for a in refs]}
    obj = {"id": "AGEN-" + rid, "kind": "gen-run", "status": status, "spec": spec}
    rows = plugin.check(obj, Ctx(A, reg, "assetgen/runs/%s/run.md" % rid, {}, None, {"authoring": A}))
    return [r for r in rows if r.check == "gen-run-style"], [r.check for r in rows]


def case(rid, want, needles, label, **kw):
    rows, _ = style_rows(rid, **kw)
    text = "; ".join(sum((r.reasons for r in rows), []))
    good = len(rows) == 1 and rows[0].state == want and all(n in text for n in needles)
    print(("ok " if good else "no ") + label + ("" if good else " | %s %s" % ([r.state for r in rows], text)))


case("u-good-001", "PASS", [], "gen-run-style: a human-approved active anchor (approved source run, signed approval, bytes match) PASS", refs=["a-good"])
# A recorded reference exercises the same quality path even when malformed attestation prevents new selection.
ext_sha = anchor("a-external", ref2, by="Ana Silva", n=12)
ext_path = os.path.join(G, "styles", "rpg-base", "anchors", "a-external.json")
ext_data = json.load(open(ext_path, encoding="utf-8"))
del ext_data["source_run"]
ext_data["external_source"] = {"origin": "art bible v2 p.14", "rights_note": "studio-owned", "sha256": ext_sha,
                               "attested_by": "Ana Silva", "attested_on": "2026-11-01"}
shas["a-external"] = ext_sha
for attester, label in (("claude", "claude"), ("codex", "codex"), ("gpt-5", "gpt-5"),
                        ("SAME_MODEL:claude-opus", "SAME_MODEL:claude-opus"), (None, "null"), ("Other Person", "another person"),
                        ("Ana Silva", "approving person")):
    ext_data["external_source"]["attested_by"] = attester
    with open(ext_path, "w", encoding="utf-8") as f:
        json.dump(ext_data, f)
    case("u-external-001", "PASS" if attester == "Ana Silva" else "FAIL",
         [] if attester == "Ana Silva" else ["external_source.attested_by"],
         "gen-run-style: external anchor attested by %s %s" % (label, "PASS" if attester == "Ana Silva" else "FAIL"),
         refs=["a-external"])
os.remove(ext_path)
os.remove(os.path.join(G, "styles", "rpg-base", "anchors", "a-external.png"))
case("u-agent-001", "FAIL", ["is an agent or model"], "gen-run-style: an active anchor approved_by an agent/model name FAIL", refs=["a-agent"])
case("u-old-001", "WARN", ["changed since the run"], "gen-run-style: an anchor of an older style version stays valid (style drift WARN only)", refs=["a-old"], ref=ref1)
case("u-gone-001", "FAIL", ["a-gone is not in assetgen/styles/rpg-base/anchors/"], "gen-run-style: a recorded anchor without its JSON FAIL", refs=["a-gone"])
case("u-noimg-001", "FAIL", ["a-noimg image a-noimg.png is missing"], "gen-run-style: a recorded anchor without its image file FAIL", refs=["a-noimg"])
case("u-bytes-001", "FAIL", ["sha256 on disk differs from image_sha256"], "gen-run-style: anchor image bytes changed FAIL", refs=["a-bytes"])
case("u-draftsrc-001", "FAIL", ["source gen-run draft-001 is proposed, not approved"], "gen-run-style: an anchor whose source run is not approved FAIL", refs=["a-draftsrc"])
case("u-unsigned-001", "FAIL", ["approval of source gen-run AGEN-seed2-001 is missing"],
     "gen-run-style: source run approved in run.md without a verified signed approval FAIL", refs=["a-unsigned"])
case("u-proposed-001", "FAIL", ["is proposed, not active"], "gen-run-style: a proposed anchor in the references FAIL", refs=["a-proposed"])
case("u-retired-001", "WARN", ["retired since the run"], "gen-run-style: an anchor retired after the run WARN", refs=["a-retired"])
case("u-override-001", "WARN", ["style override recorded: one-off key art"], "gen-run-style: an override with a reason WARN", override="one-off key art")
case("u-blank-001", "FAIL", ["override must be null or a non-empty reason"], "gen-run-style: an override without a reason FAIL", override="  ")
case("u-noref-001", "FAIL", ["does not resolve"], "gen-run-style: a style ref that does not resolve FAIL",
     ref={"style_id": "no-such-style", "version": 1, "sha256": "1" * 64})
rows, names = style_rows("legacy-001", lock=False)
print(("ok " if not rows and "gen-run-refs" in names else "no ") + "gen-run-style: an old run without style_lock and no promoted anchor gets no row (unchanged)")
# anchors promoted from the run itself
sha = anchor("s-active", ref2, run="src-001", n=10, output="outputs/s.png")
case("src-001", "FAIL", ["is active but its source gen-run AGEN-src-001 is proposed, not approved"],
     "gen-run-style: an active anchor whose source run (this run) is not approved FAIL", lock=False, outputs=[("outputs/s.png", sha)])
sha = anchor("s-ok", ref2, run="src-ok-001", n=11, output="outputs/s.png")
case("src-ok-001", "PASS", [], "gen-run-style: an active anchor promoted from this approved run PASS", status="approved", lock=False,
     outputs=[("outputs/s.png", sha)])
sha = anchor("s-agent", ref2, run="src-agent-001", by="codex", n=12, output="outputs/s.png")
case("src-agent-001", "FAIL", ["without a person's approval", "codex"], "gen-run-style: an active anchor of this run approved by an agent FAIL",
     status="approved", lock=False, outputs=[("outputs/s.png", sha)])
case("src-agent-001", "FAIL", ["which this run does not record"], "gen-run-style: an anchor naming output bytes the run does not record FAIL",
     status="approved", lock=False, outputs=[("outputs/s.png", "0" * 64)])
# e2e3 item 4: a source run approved with assetgen.py approve-record but not yet committed and signed is HUMAN_REQUIRED
# ("present but not committed/signed"), not a missing approval
import subprocess
os.makedirs(os.path.join(G, "runs", "seed3-001"), exist_ok=True)
with open(os.path.join(G, "runs", "seed3-001", "run.md"), "w", encoding="utf-8", newline="\n") as f:
    f.write("---json\n%s\n---\n# seed3\n\n- Status: proposed (approval is human-only)\n" % json.dumps(
        {"id": "AGEN-seed3-001", "kind": "gen-run", "domain": "assetgen", "status": "proposed", "spec": {}}, indent=2))
p = subprocess.run([sys.executable, "-B", os.path.join(root, "scripts", "assetgen", "assetgen.py"), "approve-record", "--run",
                    os.path.join(G, "runs", "seed3-001"), "--by", "Dana"], capture_output=True, text=True)
print(("ok " if p.returncode == 0 else "no ") + "approve-record on the source run (not committed)" + ("" if p.returncode == 0 else " | " + p.stderr))
shas["a-pending"] = anchor("a-pending", ref2, run="seed3-001", n=13)
case("u-pending-001", "HUMAN_REQUIRED", ["approval of source gen-run AGEN-seed3-001 is present but not committed/signed"],
     "gen-run-style: an approval written by approve-record but not committed/signed is HUMAN_REQUIRED, not missing", refs=["a-pending"])
print("ok gen-run-style cases ran to the end")
EOF
while IFS= read -r line; do
  case "$line" in "ok "*) ok "${line#ok }" ;; "no "*) no "${line#no }" ;; *) no "gen-run-style: unexpected output" "$line" ;; esac
done < "$TMP/gs"
grep -qx "ok gen-run-style cases ran to the end" "$TMP/gs" || no "gen-run-style cases stopped early" "$(tail -5 "$TMP/gs")"
# registry fast check assetgen-lint: catches an active anchor whose source gen-run has no run.md (no gen-run to check)
cmd=$(jq -r '.modules[] | select(.id == "authoring.assetgen") | .checks.fast[] | select(.id == "assetgen-lint") | .run' "$ROOT/registry.json")
[ -n "$cmd" ] && jq -e '.domains.assetgen.quality_gates | index("assetgen-lint")' "$ROOT/registry.json" >/dev/null \
  && ok "registry: authoring.assetgen fast check assetgen-lint is a quality gate of the assetgen domain" || no "registry assetgen-lint" "$cmd"
SP="$TMP/style-plugin"; rm -rf "$SP/assetgen/runs/seed-001"
(cd "$SP" && eval "${cmd//\{plugin_root\}/\"$ROOT\"}") > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q "a-good.json: .*seed-001 is missing" "$TMP/o" \
  && ok "assetgen-lint (registry command, in the authoring repo): an active anchor whose source run.md is gone FAILS" || no "assetgen-lint rc=$rc" "$(grep -v '^PASS' "$TMP/o")"

echo "-- style init: draft game style, family stub and project.json skeleton (style_cmd.py)"
SI="$TMP/style-init"; mkdir -p "$SI"
tpl_hash() { find "$ROOT/templates/assetgen" -type f -exec sha256sum {} + | LC_ALL=C sort | sha256sum | cut -d' ' -f1; }
tpl0=$(tpl_hash)
AG style init --id demo-game --extends pixel-art --family characters=demo-game-characters --authoring "$SI" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
SS="$SI/assetgen/styles"; SPJ="$SI/assetgen/project.json"
grep -Fq 'WARN: the new style has no structured style fields (palette.colors, tone, canvas, outline.edge_darkness)' "$TMP/si.out" \
  && grep -q 'no style-\* QA row can grade an output until one is added' "$TMP/si.out" \
  && grep -q 'Lint WARNs once the style is active; add fields by hand or use style derive --apply once valid active anchors exist' "$TMP/si.out" \
  && ok "style init text warns about missing structured fields and how to add them" || no "style init warning" "$(cat "$TMP/si.out")"
[ $rc -eq 0 ] && [ -f "$SS/demo-game.json" ] && [ -f "$SS/demo-game-characters.json" ] && [ -f "$SPJ" ] \
  && ok "style init exits 0 and writes the style, the family stub and project.json" || no "style init rc=$rc" "$(cat "$TMP/si.err" "$TMP/si.out")"
[ "$(jq -c '[.extends, .version, .status]' "$SS/demo-game.json")" = '["pixel-art",1,"draft"]' ] \
  && ok "style init: the main style extends pixel-art, version 1, status draft" || no "style init main style" "$(cat "$SS/demo-game.json")"
[ "$(jq -c '[.extends, .status]' "$SS/demo-game-characters.json")" = '["demo-game","draft"]' ] \
  && ok "style init: the family stub extends the main style and is draft" || no "style init family stub" "$(cat "$SS/demo-game-characters.json")"
[ "$(jq -c '[.schema, .style, .families, .allowed_styles]' "$SPJ")" \
  = '["rpg-factory.assetgen-project/1",{"id":"demo-game","version":1},{"characters":"demo-game-characters"},["demo-game","demo-game-characters"]]' ] \
  && ok "style init: project.json has the schema, style {id, 1}, families and allowed_styles" || no "style init project.json" "$(cat "$SPJ")"
AG lint --authoring "$SI" --json > "$TMP/si-lint.json" 2>&1; rc=$?
nfail=$(jq '[.results[] | select(.state == "FAIL")] | length' "$TMP/si-lint.json")
nwarn=$(jq '[.results[] | select(.state == "WARN" and (.path | test("project[.]json|assetgen/styles/")))] | length' "$TMP/si-lint.json")
npass=$(jq '[.results[] | select(.state == "PASS" and (.path == "game:assetgen/project.json" or (.path | test("^game:assetgen/styles/demo-game"))))] | length' "$TMP/si-lint.json")
[ $rc -eq 0 ] && [ "$nfail" = 0 ] && [ "$nwarn" = 0 ] && [ "$npass" = 3 ] \
  && ok "lint after style init: 0 FAIL, project.json and both draft styles PASS with no WARN" || no "lint after init rc=$rc fail=$nfail warn=$nwarn pass=$npass" "$(jq -c '.results[] | select(.state != "PASS")' "$TMP/si-lint.json")"
jq '.status = "active"' "$SS/demo-game.json" > "$TMP/si-active.json" && cp "$TMP/si-active.json" "$SS/demo-game.json"
AG lint --authoring "$SI" --json > "$TMP/si-lint.json" 2>&1; rc=$?
nfail=$(jq '[.results[] | select(.state == "FAIL")] | length' "$TMP/si-lint.json")
siw=$(jq -r '[.results[] | select(.path == "game:assetgen/styles/demo-game.json" and .state == "WARN") | .reasons[]] | join(" ")' "$TMP/si-lint.json")
[ $rc -eq 0 ] && [ "$nfail" = 0 ] && grep -q "active game style has no usable structured style fields" <<<"$siw" \
  && ok "an active style from init WARNs 'no usable structured style fields' (0 FAIL)" || no "active style lint rc=$rc fail=$nfail" "$siw"
AG resolve --purpose icon --authoring "$SI" --out "$TMP/si-spec.json" > /dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.style_lock.style.style_id' "$TMP/si-spec.json")" = demo-game ] \
  && ok "resolve --authoring locks the new project style (spec.style_lock.style.style_id)" || no "resolve after init rc=$rc" "$(jq -c .style_lock "$TMP/si-spec.json" 2>&1)"
h_style=$(sha256sum "$SS/demo-game.json" | cut -d' ' -f1); h_proj=$(sha256sum "$SPJ" | cut -d' ' -f1); n_files=$(find "$SI/assetgen" -type f | wc -l | tr -d ' ')
AG style init --id demo-game --extends pixel-art --authoring "$SI" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 1 ] && grep -q "already exists" "$TMP/si.err" && [ "$(sha256sum "$SS/demo-game.json" | cut -d' ' -f1)" = "$h_style" ] \
  && [ "$(sha256sum "$SPJ" | cut -d' ' -f1)" = "$h_proj" ] && [ "$(find "$SI/assetgen" -type f | wc -l | tr -d ' ')" = "$n_files" ] \
  && ok "a second style init exits 1 with a message and leaves the files byte-identical" || no "second init rc=$rc" "$(cat "$TMP/si.err")"
SJ="$TMP/style-init-proj"; mkdir -p "$SJ/assetgen"; echo '{"keep": true}' > "$SJ/assetgen/project.json"; h_keep=$(sha256sum "$SJ/assetgen/project.json" | cut -d' ' -f1)
AG style init --id other-game --extends pixel-art --authoring "$SJ" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 1 ] && grep -q "project.json already exists" "$TMP/si.err" && [ ! -e "$SJ/assetgen/styles/other-game.json" ] \
  && [ "$(sha256sum "$SJ/assetgen/project.json" | cut -d' ' -f1)" = "$h_keep" ] \
  && ok "an existing project.json alone exits 1: no style file is written, project.json untouched" || no "existing project.json rc=$rc" "$(cat "$TMP/si.err")"
SU="$TMP/style-init-usage"; mkdir -p "$SU"
AG style init --id bad-game --extends no-such-core-style --authoring "$SU" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 2 ] && grep -q "not a core style" "$TMP/si.err" && [ ! -e "$SU/assetgen" ] \
  && ok "--extends naming a non-core style exits 2 and writes nothing" || no "non-core extends rc=$rc" "$(cat "$TMP/si.err")"
AG style init --id demo-game --extends demo-game --authoring "$SU" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 2 ] && [ ! -e "$SU/assetgen" ] && ok "--extends naming a game style exits 2 (core styles only)" || no "game extends rc=$rc" "$(cat "$TMP/si.err")"
for badfam in "characters" "Characters=x" "characters=" "=x"; do
  AG style init --id bad-game --extends pixel-art --family "$badfam" --authoring "$SU" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
  [ $rc -eq 2 ] && grep -q "must be FAM=STYLE" "$TMP/si.err" && [ ! -e "$SU/assetgen" ] \
    && ok "malformed --family '$badfam' exits 2 and writes nothing" || no "malformed --family '$badfam' rc=$rc" "$(cat "$TMP/si.err")"
done
SF="$TMP/style-init-family"; mkdir -p "$SF"
AG style init --id demo-game --extends pixel-art --family characters=pixel-art --authoring "$SF" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 1 ] && grep -q "is a core style" "$TMP/si.err" && [ ! -e "$SF/assetgen" ] \
  && ok "--family naming a core style exits 1 and writes nothing" || no "core family style rc=$rc" "$(cat "$TMP/si.err"; find "$SF" -type f)"
SG="$TMP/style-init-gamefam"; mkdir -p "$SG/assetgen/styles"
echo '{"schema":"rpg-factory.assetgen-style/1","title":"other","extends":"pixel-art","version":1,"status":"draft"}' > "$SG/assetgen/styles/other-fam.json"
h_fam=$(sha256sum "$SG/assetgen/styles/other-fam.json" | cut -d' ' -f1)
AG style init --id demo-game --extends pixel-art --family characters=other-fam --authoring "$SG" > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 1 ] && grep -q "must extend the project style" "$TMP/si.err" && [ ! -e "$SG/assetgen/styles/demo-game.json" ] && [ ! -e "$SG/assetgen/project.json" ] \
  && [ "$(sha256sum "$SG/assetgen/styles/other-fam.json" | cut -d' ' -f1)" = "$h_fam" ] && [ "$(find "$SG/assetgen" -type f | wc -l | tr -d ' ')" = 1 ] \
  && ok "an existing game family style that does not extend the new id exits 1 and writes nothing" || no "foreign family style rc=$rc" "$(cat "$TMP/si.err"; find "$SG" -type f)"
SK="$TMP/style-init-json"; mkdir -p "$SK"
AG style init --id demo-game --extends pixel-art --family characters=demo-game-characters --authoring "$SK" --json > "$TMP/si.out" 2> "$TMP/si.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .schema "$TMP/si.out")" = "rpg-factory.assetgen-style-init/1" ] \
  && [ "$(jq -c '.files | sort' "$TMP/si.out")" = '["assetgen/project.json","assetgen/styles/demo-game-characters.json","assetgen/styles/demo-game.json"]' ] \
  && [ "$(jq -c '.project | [.schema, .style, .families]' "$TMP/si.out")" = '["rpg-factory.assetgen-project/1",{"id":"demo-game","version":1},{"characters":"demo-game-characters"}]' ] \
  && [ "$(jq -cS '.project' "$TMP/si.out")" = "$(jq -cS . "$SK/assetgen/project.json")" ] \
  && ok "style init --json prints schema rpg-factory.assetgen-style-init/1 with files and project" || no "style init --json rc=$rc" "$(cat "$TMP/si.err" "$TMP/si.out")"
jq -e '.warnings | length == 1 and (.[0] | contains("WARN:") and contains("palette.colors, tone, canvas, outline.edge_darkness") and contains("no style-* QA row can grade an output until one is added") and contains("Lint WARNs once the style is active") and contains("by hand") and contains("style derive --apply") and contains("valid active anchors"))' "$TMP/si.out" >/dev/null \
  && ok "style init JSON includes the structured fields warning" || no "style init JSON warning" "$(cat "$TMP/si.out")"
[ "$(tpl_hash)" = "$tpl0" ] && [ -z "$(git -C "$ROOT" status --porcelain -- templates/assetgen)" ] \
  && ok "style init changed nothing under templates/assetgen" || no "templates/assetgen changed" "$(git -C "$ROOT" status --porcelain -- templates/assetgen)"

echo "-- style derive: palette, tone and canvas proposed from the anchors, --apply into a draft only (style_derive.py)"
SD="$TMP/style-derive"; mkdir -p "$SD"
AG style init --id demo-game --extends pixel-art --authoring "$SD" > "$TMP/sd.out" 2> "$TMP/sd.err" || no "style derive setup: style init" "$(cat "$TMP/sd.err")"
# valid active anchors for the draft style: two props (256x256) and one characters (256x384) with distinct colours,
# PNGs encoded here, an approved source gen-run, the style ref of the merged style at version 1
python3 -B - "$ROOT" "$SD" > "$TMP/sd.setup" 2>&1 <<'EOF'
import hashlib, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import layers, png, stylelock
A = sys.argv[2]
G = os.path.join(A, "assetgen")
ref = stylelock.style_ref(layers.load("style", "demo-game", A))
def disc(w, h, a, b):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            d = ((x - w / 2) ** 2 + (y - h / 2) ** 2) ** 0.5
            px += bytes((a if x < w // 2 else b) + (255,)) if d < min(w, h) * 0.3 else bytes((0, 0, 0, 0))
    return png.encode(w, h, bytes(px))
os.makedirs(os.path.join(G, "runs", "derive-001"), exist_ok=True)
with open(os.path.join(G, "runs", "derive-001", "run.md"), "w", encoding="utf-8") as f:
    f.write("---json\n%s\n---\n# run\n" % json.dumps({"id": "AGEN-derive-001", "status": "approved"}))
d = os.path.join(G, "styles", "demo-game", "anchors")
os.makedirs(d, exist_ok=True)
for aid, family, w, h, a, b in (("chars-a", "characters", 256, 384, (40, 60, 200), (220, 200, 40)),
                                ("props-a", "props", 256, 256, (200, 40, 40), (40, 160, 60)),
                                ("props-b", "props", 256, 256, (200, 40, 40), (40, 160, 60))):
    data = disc(w, h, a, b)
    with open(os.path.join(d, aid + ".png"), "wb") as f:
        f.write(data)
    with open(os.path.join(d, aid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"schema": "rpg-factory.assetgen-anchor/1", "id": aid, "status": "active", "style": ref, "family": family,
                   "dimensions": ["palette", "shape"], "strength": "strong", "image": aid + ".png",
                   "image_sha256": hashlib.sha256(data).hexdigest(),
                   "source_run": {"run_id": "derive-001", "output": "outputs/a.png", "sha256": "0" * 64},
                   "approved_by": "Dana", "approved_on": "2026-11-01"}, f)
print("ok")
EOF
grep -qx ok "$TMP/sd.setup" || no "style derive setup: anchors" "$(cat "$TMP/sd.setup")"
SDS="$SD/assetgen/styles/demo-game.json"
h_sd=$(sha256sum "$SDS" | cut -d' ' -f1)
cp -r "$SD" "$TMP/style-derive-pre"   # the draft style as init wrote it, anchors included (QA and min_side cases below)
AG style derive --style demo-game --authoring "$SD" --json > "$TMP/sd1.json" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .schema "$TMP/sd1.json")" = "rpg-factory.assetgen-style-derive/1" ] && [ "$(jq -r .applied "$TMP/sd1.json")" = false ] \
  && [ "$(jq -c '[.anchors[].id]' "$TMP/sd1.json")" = '["chars-a","props-a","props-b"]' ] && [ "$(jq -c .skipped "$TMP/sd1.json")" = '[]' ] \
  && ok "style derive --json exits 0: a proposal from the 3 valid active anchors, nothing skipped, not applied" || no "style derive --json rc=$rc" "$(cat "$TMP/sd.err" "$TMP/sd1.json")"
[ "$(jq -c '[.proposal.palette.colors[].hex] | sort' "$TMP/sd1.json")" = '["#283cc8","#28a03c","#c82828","#dcc828"]' ] \
  && [ -n "$(jq -r '.proposal.palette.text // empty' "$TMP/sd1.json")" ] && [ "$(jq -r '.proposal.tone.tolerance' "$TMP/sd1.json")" = 0.05 ] \
  && ok "style derive proposes palette.colors (the four anchor colours as hex, with text) and tone.tolerance 0.05" || no "style derive palette/tone" "$(jq -c .proposal "$TMP/sd1.json")"
[ "$(jq -c '.proposal.canvas' "$TMP/sd1.json")" = '{"characters":{"aspect":"2:3","tolerance":0.02},"props":{"aspect":"1:1","tolerance":0.02}}' ] \
  && ok "style derive proposes a canvas per family: props 1:1, characters 2:3" || no "style derive canvas" "$(jq -c .proposal.canvas "$TMP/sd1.json")"
AG style derive --style demo-game --authoring "$SD" --json > "$TMP/sd2.json" 2> "$TMP/sd.err"
cmp -s "$TMP/sd1.json" "$TMP/sd2.json" && ok "two style derive --json runs on the same anchors are byte-identical" || no "style derive output differs between runs" "$(diff "$TMP/sd1.json" "$TMP/sd2.json")"
AG style derive --style demo-game --authoring "$SD" > "$TMP/sd1.txt" 2> "$TMP/sd.err"; rc=$?
AG style derive --style demo-game --authoring "$SD" > "$TMP/sd2.txt" 2> "$TMP/sd.err"
[ $rc -eq 0 ] && cmp -s "$TMP/sd1.txt" "$TMP/sd2.txt" && grep -q "chars-a" "$TMP/sd1.txt" && grep -q "props-a" "$TMP/sd1.txt" && grep -q "props-b" "$TMP/sd1.txt" \
  && grep -q "canvas.props: aspect 1:1" "$TMP/sd1.txt" && grep -q "not applied" "$TMP/sd1.txt" \
  && ok "style derive text output is byte-identical, names the anchors and the canvas, and says not applied" || no "style derive text rc=$rc" "$(cat "$TMP/sd1.txt")"
AG style derive --style demo-game --authoring "$SD" --family props --json > "$TMP/sdp.json" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c '.proposal.canvas | keys' "$TMP/sdp.json")" = '["props"]' ] && [ "$(jq -c '[.anchors[].id]' "$TMP/sdp.json")" = '["props-a","props-b"]' ] \
  && [ "$(jq -c '[.proposal.palette.colors[].hex] | sort' "$TMP/sdp.json")" = '["#28a03c","#c82828"]' ] && [ "$(jq -r .family "$TMP/sdp.json")" = props ] \
  && ok "style derive --family props restricts the anchors, the palette and the canvas to props" || no "style derive --family props rc=$rc" "$(cat "$TMP/sd.err"; jq -c .proposal "$TMP/sdp.json")"
AG style derive --style demo-game --authoring "$SD" --family characters --json > "$TMP/sdc.json" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.proposal.tone.tolerance' "$TMP/sdc.json")" = 0.1 ] && [ "$(jq -c '.proposal.canvas | keys' "$TMP/sdc.json")" = '["characters"]' ] \
  && ok "style derive --family characters (one anchor): tone.tolerance 0.1, canvas characters only" || no "style derive --family characters rc=$rc" "$(cat "$TMP/sd.err"; jq -c .proposal "$TMP/sdc.json")"
[ "$(sha256sum "$SDS" | cut -d' ' -f1)" = "$h_sd" ] && ok "a derive without --apply leaves the style file byte-identical" || no "plain derive changed the style file" "$(cat "$SDS")"
AG style derive --style no-such-game --authoring "$SD" > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 1 ] && grep -q "has no game file" "$TMP/sd.err" && ok "style derive for a style without a game file exits 1 with a message" || no "missing style rc=$rc" "$(cat "$TMP/sd.err")"
AG style derive --style demo-game --family "Bad Family" --authoring "$SD" > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 2 ] && ok "style derive with a malformed --family exits 2" || no "malformed --family rc=$rc" "$(cat "$TMP/sd.err")"

# an anchor whose PNG bytes no longer match image_sha256 is skipped (and reported), never sampled
SDT="$TMP/style-derive-tamper"; cp -r "$SD" "$SDT"
printf 'x' >> "$SDT/assetgen/styles/demo-game/anchors/props-b.png"
AG style derive --style demo-game --authoring "$SDT" --json > "$TMP/sdt.json" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c '[.anchors[].id]' "$TMP/sdt.json")" = '["chars-a","props-a"]' ] && [ "$(jq -r '.skipped | map(.id) | join(",")' "$TMP/sdt.json")" = props-b ] \
  && jq -r '.skipped[0].reason' "$TMP/sdt.json" | grep -q "does not match image_sha256" \
  && ok "an anchor whose PNG no longer matches image_sha256 is skipped and reported" || no "tampered anchor rc=$rc" "$(cat "$TMP/sd.err"; jq -c '[.anchors, .skipped]' "$TMP/sdt.json")"
AG style derive --style demo-game --authoring "$SDT" > "$TMP/sdt.txt" 2> "$TMP/sd.err"
grep -q "anchor skipped: props-b" "$TMP/sdt.txt" && ok "the text output reports the skipped anchor" || no "skipped anchor not in the text output" "$(cat "$TMP/sdt.txt")"

# refusals: a style without valid anchors, an active style, a style without status (= active): exit 1, file byte-identical
SDN="$TMP/style-derive-noanchor"; mkdir -p "$SDN"
AG style init --id demo-game --extends pixel-art --authoring "$SDN" > /dev/null 2>&1
h_n=$(sha256sum "$SDN/assetgen/styles/demo-game.json" | cut -d' ' -f1)
for flags in "" "--apply"; do
  AG style derive --style demo-game --authoring "$SDN" $flags > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
  [ $rc -eq 1 ] && grep -q "no usable anchor" "$TMP/sd.err" && [ "$(sha256sum "$SDN/assetgen/styles/demo-game.json" | cut -d' ' -f1)" = "$h_n" ] \
    && ok "style derive ${flags:-(plain)} on a style without anchors exits 1 and leaves the file byte-identical" || no "no-anchor derive $flags rc=$rc" "$(cat "$TMP/sd.err")"
done
SDU="$TMP/style-derive-unusable"; cp -r "$SD" "$SDU"
for f in "$SDU"/assetgen/styles/demo-game/anchors/*.png; do printf 'x' >> "$f"; done
h_u=$(sha256sum "$SDU/assetgen/styles/demo-game.json" | cut -d' ' -f1)
AG style derive --style demo-game --authoring "$SDU" --apply > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 1 ] && grep -q "no usable anchor" "$TMP/sd.err" && [ "$(sha256sum "$SDU/assetgen/styles/demo-game.json" | cut -d' ' -f1)" = "$h_u" ] \
  && ok "style derive --apply where every anchor PNG is tampered exits 1 and leaves the file byte-identical" || no "all-tampered apply rc=$rc" "$(cat "$TMP/sd.err")"
SDA="$TMP/style-derive-active"; cp -r "$SD" "$SDA"
jq '.status = "active"' "$SDS" > "$TMP/sd-active.json" && cp "$TMP/sd-active.json" "$SDA/assetgen/styles/demo-game.json"
h_a=$(sha256sum "$SDA/assetgen/styles/demo-game.json" | cut -d' ' -f1)
AG style derive --style demo-game --authoring "$SDA" --apply > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 1 ] && grep -q "only merges into a draft" "$TMP/sd.err" && [ "$(sha256sum "$SDA/assetgen/styles/demo-game.json" | cut -d' ' -f1)" = "$h_a" ] \
  && ok "style derive --apply on an active style exits 1 and leaves the file byte-identical" || no "active apply rc=$rc" "$(cat "$TMP/sd.err")"
AG style derive --style demo-game --authoring "$SDA" --json > "$TMP/sda.json" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .applied "$TMP/sda.json")" = false ] && [ "$(jq -r .style.status "$TMP/sda.json")" = active ] \
  && [ "$(sha256sum "$SDA/assetgen/styles/demo-game.json" | cut -d' ' -f1)" = "$h_a" ] \
  && ok "a plain derive on an active style still proposes (exit 0) and writes nothing" || no "active plain derive rc=$rc" "$(cat "$TMP/sd.err")"
SDM="$TMP/style-derive-nostatus"; cp -r "$SD" "$SDM"
jq 'del(.status)' "$SDS" > "$TMP/sd-nostatus.json" && cp "$TMP/sd-nostatus.json" "$SDM/assetgen/styles/demo-game.json"
h_m=$(sha256sum "$SDM/assetgen/styles/demo-game.json" | cut -d' ' -f1)
AG style derive --style demo-game --authoring "$SDM" --apply > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 1 ] && grep -q "only merges into a draft" "$TMP/sd.err" && [ "$(sha256sum "$SDM/assetgen/styles/demo-game.json" | cut -d' ' -f1)" = "$h_m" ] \
  && ok "style derive --apply on a style without status (active) exits 1 and leaves the file byte-identical" || no "no-status apply rc=$rc" "$(cat "$TMP/sd.err")"

# QA availability: dqa AUTHORING NAME resolves an icon run (family props), renders it (the anchor copies) and runs qa
dqa() {
  local d="$1/assetgen/runs/dq-$2-001"; rm -rf "$d"; mkdir -p "$d/outputs"
  AG resolve --purpose icon --authoring "$1" --out "$d/spec.json" > /dev/null 2> "$TMP/err" || return 1
  printf 'Derive prompt.\n' > "$d/prompt.md"
  AG render --run "$d" > /dev/null 2>> "$TMP/err" || return 1
  cp "$FX/icon-ok.png" "$d/outputs/out.png"
  AG qa --run "$d" --json > "$TMP/dq-$2.json" 2>> "$TMP/err"   # exit 1 is fine: only the style rows matter here
  rm -rf "$d"
  [ -s "$TMP/dq-$2.json" ]
}
dst() { jq -r --arg c "$2" '[.results[] | select(.check == $c) | .state] | join(",")' "$TMP/dq-$1.json"; }
dqa "$TMP/style-derive-pre" before || no "style derive QA setup (before apply)" "$(cat "$TMP/err")"
[ "$(dst before style-palette)" = NOT_AVAILABLE ] && [ "$(dst before style-tone)" = NOT_AVAILABLE ] && [ "$(dst before style-canvas)" = NOT_AVAILABLE ] \
  && ok "before --apply the draft style's style-palette, style-tone and style-canvas QA rows are NOT_AVAILABLE" \
  || no "QA rows before apply: $(dst before style-palette) $(dst before style-tone) $(dst before style-canvas)" "$(jq -c '[.results[] | select(.check | startswith("style-"))]' "$TMP/dq-before.json")"

# --apply on the draft style with anchors
AG style derive --style demo-game --authoring "$SD" --apply > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && grep -q "wrote assetgen/styles/demo-game.json" "$TMP/sd.out" \
  && [ "$(jq -c '[.status, .extends, .version, .tone.tolerance]' "$SDS")" = '["draft","pixel-art",1,0.05]' ] \
  && [ "$(jq -c '[.palette.colors[].hex] | sort' "$SDS")" = '["#283cc8","#28a03c","#c82828","#dcc828"]' ] && [ -n "$(jq -r '.palette.text // empty' "$SDS")" ] \
  && [ "$(jq -c '.canvas' "$SDS")" = '{"characters":{"aspect":"2:3","tolerance":0.02},"props":{"aspect":"1:1","tolerance":0.02}}' ] \
  && ok "style derive --apply on the draft style exits 0 and writes palette, tone and canvas (status, extends, version kept)" || no "draft apply rc=$rc" "$(cat "$TMP/sd.err" "$TMP/sd.out"; cat "$SDS")"
[ "$(jq -cS '.proposal' "$TMP/sd1.json")" = "$(jq -cS '{palette: .palette, tone: .tone, canvas: .canvas}' "$SDS")" ]   && ok "the written fields equal the proposal" || no "written fields differ from the proposal" "$(cat "$SDS")"
h_after=$(sha256sum "$SDS" | cut -d' ' -f1)
AG style derive --style demo-game --authoring "$SD" --apply > "$TMP/sd.out" 2> "$TMP/sd.err"; rc=$?
[ $rc -eq 0 ] && [ "$(sha256sum "$SDS" | cut -d' ' -f1)" = "$h_after" ] && ok "a second --apply on the same anchors rewrites the same bytes" || no "second apply rc=$rc" "$(cat "$TMP/sd.err")"
AG lint --authoring "$SD" --json > "$TMP/sd-lint.json" 2>&1; rc=$?
nfail=$(jq '[.results[] | select(.state == "FAIL")] | length' "$TMP/sd-lint.json")
[ $rc -eq 0 ] && [ "$nfail" = 0 ] && [ "$(jq -r '[.results[] | select(.path == "game:assetgen/styles/demo-game.json") | .state] | join(",")' "$TMP/sd-lint.json")" = PASS ] \
  && ok "lint after style derive --apply: 0 FAIL, the derived style PASSes" || no "lint after derive rc=$rc fail=$nfail" "$(jq -c '.results[] | select(.state != "PASS")' "$TMP/sd-lint.json")"
python3 -B - "$ROOT" "$SD" 2>&1 <<'EOF' | tr -d '\r' > "$TMP/sd.fs"
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import consistency, layers
st = consistency.field_states(layers.load("style", "demo-game", sys.argv[2])["data"])
for row in ("style-palette", "style-tone", "style-canvas"):
    print(row, st[row][0])
EOF
[ "$(cat "$TMP/sd.fs")" = "$(printf 'style-palette ok\nstyle-tone ok\nstyle-canvas ok')" ] \
  && ok "consistency.field_states of the derived style: style-palette, style-tone, style-canvas are ok" || no "field_states after derive" "$(cat "$TMP/sd.fs")"
dqa "$SD" after || no "style derive QA setup (after apply)" "$(cat "$TMP/err")"
s_pal=$(dst after style-palette); s_tone=$(dst after style-tone); s_can=$(dst after style-canvas)
all_rows="$s_pal$s_tone$s_can"
[ -n "$s_pal" ] && [ -n "$s_tone" ] && [ -n "$s_can" ] && [ "$all_rows" = "${all_rows//NOT_AVAILABLE/}" ] \
  && ok "after --apply the style-palette ($s_pal), style-tone ($s_tone) and style-canvas ($s_can) QA rows are available, not NOT_AVAILABLE" \
  || no "QA rows after apply: palette=$s_pal tone=$s_tone canvas=$s_can" "$(jq -c '[.results[] | select(.check | startswith("style-"))]' "$TMP/dq-after.json")"

# a canvas entry with only min_side: lint accepts it (it was FAIL while stylelock.style_errors wanted an aspect) and QA can grade it
for st_ in draft active; do
  SDX="$TMP/style-derive-minside-$st_"; cp -r "$TMP/style-derive-pre" "$SDX"
  jq --arg s "$st_" '.status = $s | .canvas = {"props": {"min_side": 128}}' "$TMP/style-derive-pre/assetgen/styles/demo-game.json" > "$SDX/assetgen/styles/demo-game.json"
  AG lint --authoring "$SDX" --json > "$TMP/sd-lint.json" 2>&1; rc=$?
  nfail=$(jq '[.results[] | select(.state == "FAIL")] | length' "$TMP/sd-lint.json")
  srow=$(jq -r '[.results[] | select(.path == "game:assetgen/styles/demo-game.json") | .state] | join(",")' "$TMP/sd-lint.json")
  [ $rc -eq 0 ] && [ "$nfail" = 0 ] && [ "$srow" = PASS ] \
    && ok "lint accepts a $st_ style whose canvas entry has only min_side (0 FAIL, the style PASSes)" || no "min_side-only canvas ($st_) lint rc=$rc fail=$nfail style=$srow" "$(jq -c '.results[] | select(.state != "PASS")' "$TMP/sd-lint.json")"
done
python3 -B - "$ROOT" "$TMP/style-derive-minside-draft" > "$TMP/sd.fs" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import consistency, layers, stylelock
d = layers.load("style", "demo-game", sys.argv[2])["data"]
print(consistency.field_states(d)["style-canvas"][0], stylelock.style_errors(d))
EOF
[ "$(cat "$TMP/sd.fs")" = "ok []" ] && ok "a min_side-only canvas: field_states style-canvas ok and stylelock.style_errors empty" || no "min_side-only canvas states" "$(cat "$TMP/sd.fs")"
[ "$(tpl_hash)" = "$tpl0" ] && [ -z "$(git -C "$ROOT" status --porcelain -- templates/assetgen)" ] \
  && ok "style derive changed nothing under templates/assetgen" || no "templates/assetgen changed by derive" "$(git -C "$ROOT" status --porcelain -- templates/assetgen)"

echo "-- style bump: draft version N+1, proposed anchor copies and the re-approval report (style_cmd.py)"
# fixture: an ACTIVE game style at version 1 (init, anchors, derive --apply into the draft, then activated), anchors
# chars-a and props-a-v1 (active), props-p (proposed), props-old (retired), a run of the style at version 1, and the
# rejections rej-v1 (version 1) and rej-any (version null); built once in SB0, every case works on a copy
SB0="$TMP/style-bump-base"; mkdir -p "$SB0"; git init -q -b main "$SB0"
AG style init --id demo-game --extends pixel-art --authoring "$SB0" > "$TMP/sb.out" 2> "$TMP/sb.err" || no "style bump setup: style init" "$(cat "$TMP/sb.err")"
sb_setup() {   # sb_setup MODE: anchors (draft ref, before derive) | final (every record and the run carry the active style ref)
python3 -B - "$ROOT" "$SB0" "$1" 2>&1 <<'EOF' | tr -d '\r'
import hashlib, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import layers, png, stylelock
A, mode = sys.argv[2], sys.argv[3]
G = os.path.join(A, "assetgen")
D = os.path.join(G, "styles", "demo-game")
AD, RD = os.path.join(D, "anchors"), os.path.join(D, "rejections")
ref = stylelock.style_ref(layers.load("style", "demo-game", A))
def jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")
def front(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(os.path.join(sys.argv[1], "templates", "assetgen", "gen-run.md"), encoding="utf-8") as f:
        envelope = json.loads(f.read().split("---", 2)[1].removeprefix("json\n"))
    envelope.update(obj)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("---json\n%s\n---\n# run\n" % json.dumps(envelope))
def disc(w, h, a, b):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            d = ((x - w / 2) ** 2 + (y - h / 2) ** 2) ** 0.5
            px += bytes((a if x < w // 2 else b) + (255,)) if d < min(w, h) * 0.3 else bytes((0, 0, 0, 0))
    return png.encode(w, h, bytes(px))
if mode == "anchors":
    front(os.path.join(G, "runs", "derive-001", "run.md"), {"id": "AGEN-derive-001", "status": "approved", "spec": {}})
    for aid, family, w, h, a, b, status in (
            ("chars-a", "characters", 256, 384, (40, 60, 200), (220, 200, 40), "active"),
            ("props-a-v1", "props", 256, 256, (200, 40, 40), (40, 160, 60), "active"),
            ("props-p", "props", 256, 256, (180, 40, 40), (40, 160, 60), "proposed"),
            ("props-old", "props", 256, 256, (200, 40, 40), (60, 160, 40), "retired")):
        data = disc(w, h, a, b)
        os.makedirs(AD, exist_ok=True)
        with open(os.path.join(AD, aid + ".png"), "wb") as f:
            f.write(data)
        person = status != "proposed"
        jdump(os.path.join(AD, aid + ".json"),
              {"schema": "rpg-factory.assetgen-anchor/1", "id": aid, "status": status, "style": ref, "family": family,
               "dimensions": ["palette", "shape"], "strength": "strong", "image": aid + ".png",
               "image_sha256": hashlib.sha256(data).hexdigest(),
               "source_run": {"run_id": "derive-001", "output": "outputs/a.png", "sha256": "0" * 64},
               "approved_by": "Dana" if person else None, "approved_on": "2026-11-01" if person else None})
else:
    for name in sorted(os.listdir(AD)):
        if name.endswith(".json"):
            p = os.path.join(AD, name)
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            data["style"] = ref
            jdump(p, data)
    jdump(os.path.join(RD, "rej-v1.json"),
          {"schema": "rpg-factory.assetgen-rejection/1", "id": "rej-v1", "type": "direction", "style": ref,
           "family": None, "reason": "other", "text": "no neon glow on version 1 props"})
    jdump(os.path.join(RD, "rej-any.json"),
          {"schema": "rpg-factory.assetgen-rejection/1", "id": "rej-any", "type": "direction",
           "style": {"style_id": "demo-game", "version": None, "sha256": "0" * 64},
           "family": None, "reason": "other", "text": "no text or logos on any version"})
    front(os.path.join(G, "runs", "bump-run-001", "run.md"),
          {"id": "AGEN-bump-001", "status": "approved",
           "spec": {"style": {"id": "demo-game", "sha256": ref["sha256"]}, "style_lock": {"style": ref}}})
print("ok")
EOF
}
sb_setup anchors > "$TMP/sb.setup"; grep -qx ok "$TMP/sb.setup" || no "style bump setup: anchors" "$(cat "$TMP/sb.setup")"
AG style derive --style demo-game --authoring "$SB0" --apply > "$TMP/sb.out" 2> "$TMP/sb.err" || no "style bump setup: style derive --apply" "$(cat "$TMP/sb.err")"
jq '.status = "active"' "$SB0/assetgen/styles/demo-game.json" > "$TMP/sb-active.json" && cp "$TMP/sb-active.json" "$SB0/assetgen/styles/demo-game.json"
sb_setup final > "$TMP/sb.setup"; grep -qx ok "$TMP/sb.setup" || no "style bump setup: records" "$(cat "$TMP/sb.setup")"
# tsig DIR: one hash over every file below DIR but .git; sb_files DIR: the sorted file list; sb_changed PRE POST: files of PRE that differ or vanished
tsig() { (cd "$1" && find . -type f -not -path './.git/*' -exec sha256sum {} + | LC_ALL=C sort | sha256sum | cut -d' ' -f1); }
sb_files() { (cd "$1" && find . -type f -not -path './.git/*' | LC_ALL=C sort); }
sb_changed() { local f; sb_files "$1" | while read -r f; do cmp -s "$1/$f" "$2/$f" || echo "$f"; done; }
sb_copy() { rm -rf "$1"; cp -r "$SB0" "$1"; }

SBX="$TMP/style-bump-external"; sb_copy "$SBX"
SBXA="$SBX/assetgen/styles/demo-game/anchors"
cp "$SBXA/props-a-v1.png" "$SBXA/external-v1.png"
jq --slurpfile base "$SBXA/props-a-v1.json" '.id = "external-v1" | .image = "external-v1.png" | .style = $base[0].style | .image_sha256 = $base[0].image_sha256 | .external_source.sha256 = $base[0].image_sha256' "$TMP/ext-active.json" > "$SBXA/external-v1.json"
cp "$SBXA/external-v1.json" "$TMP/sb-external-before.json"
AG style bump --id demo-game --authoring "$SBX" --json > "$TMP/sbx.json" 2> "$TMP/sb.err"; rc=$?
AG lint "$SBXA/external-v2.json" --authoring "$SBX" > "$TMP/sbx-lint" 2>&1; lint_rc=$?
[ $rc -eq 0 ] && [ $lint_rc -eq 0 ] && cmp -s "$TMP/sb-external-before.json" "$SBXA/external-v1.json" \
  && jq -e '.status == "proposed" and .style.version == 2 and .approved_by == null and .approved_on == null and .external_source.attested_by == null and .external_source.attested_on == null' "$SBXA/external-v2.json" >/dev/null \
  && jq -e '.anchors[] | select(.id == "external-v1" and .action == "carried" and .new_id == "external-v2")' "$TMP/sbx.json" >/dev/null \
  && ok "style bump carries an external anchor as an unattested proposed record and preserves the original" \
  || no "external anchor bump rc=$rc lint=$lint_rc" "$(cat "$TMP/sb.err" "$TMP/sbx-lint" "$TMP/sbx.json")"

SBP="$TMP/style-bump-pre"; sb_copy "$SBP"          # the authoring repo as it was before the bump
SB="$TMP/style-bump"; sb_copy "$SB"; SBS="$SB/assetgen/styles"; SBD="$SBS/demo-game/versions/2.json"
AG style bump --id demo-game --authoring "$SB" --json > "$TMP/sb1.json" 2> "$TMP/sb.err"; rc=$?
# (1) the draft is a copy at version 2, nothing that existed changed
[ $rc -eq 0 ] && [ "$(jq -r .schema "$TMP/sb1.json")" = "rpg-factory.assetgen-style-bump/1" ] && [ "$(jq -r .draft.written "$TMP/sb1.json")" = true ] \
  && [ "$(jq -r .draft.path "$TMP/sb1.json")" = "assetgen/styles/demo-game/versions/2.json" ] && [ -f "$SBD" ] \
  && [ "$(jq -c '[.version, .status]' "$SBD")" = '[2,"draft"]' ] \
  && [ "$(jq -cS 'del(.version, .status)' "$SBD")" = "$(jq -cS 'del(.version, .status)' "$SBS/demo-game.json")" ] \
  && ok "style bump --json exits 0 and writes versions/2.json: version 2, status draft, every other key of the active file" || no "style bump rc=$rc" "$(cat "$TMP/sb.err"; cat "$SBD" 2>&1)"
[ "$(jq -c '[.version, .status]' "$SBS/demo-game.json")" = '[1,"active"]' ] && [ -z "$(sb_changed "$SBP" "$SB")" ] \
  && ok "the active style file, project.json and every pre-existing anchor, rejection and run file are byte-identical after the bump" \
  || no "a pre-existing file changed" "$(sb_changed "$SBP" "$SB")"
sb_files "$SBP" > "$TMP/sb.before"; sb_files "$SB" > "$TMP/sb.after"
[ "$(LC_ALL=C comm -13 "$TMP/sb.before" "$TMP/sb.after" | tr '\n' ' ')" = "./assetgen/styles/demo-game/anchors/chars-a-v2.json ./assetgen/styles/demo-game/anchors/chars-a-v2.png ./assetgen/styles/demo-game/anchors/props-a-v2.json ./assetgen/styles/demo-game/anchors/props-a-v2.png ./assetgen/styles/demo-game/versions/2.json " ] \
  && ok "the bump added exactly the draft and two carried anchors (json + png each), no file was removed" || no "files added by the bump" "$(LC_ALL=C comm -3 "$TMP/sb.before" "$TMP/sb.after")"
# (2) carried anchors are proposed copies for version 2
AGD="$SBS/demo-game/anchors"; carried_ok=true; carried_why=""
for pair in "chars-a chars-a-v2" "props-a-v1 props-a-v2"; do
  read -r old new <<<"$pair"
  [ "$(jq -c '[.status, .approved_by, .approved_on, .style.version, .style.sha256, .id, .image]' "$AGD/$new.json")" \
    = "[\"proposed\",null,null,2,\"$(jq -r .draft.style.sha256 "$TMP/sb1.json")\",\"$new\",\"$new.png\"]" ] \
    && [ "$(jq -r .image_sha256 "$AGD/$new.json")" = "$(jq -r .image_sha256 "$AGD/$old.json")" ] && cmp -s "$AGD/$old.png" "$AGD/$new.png" \
    || { carried_ok=false; carried_why="$carried_why $new: $(cat "$AGD/$new.json" 2>&1 | head -c 400)"; }
done
$carried_ok && [ ! -e "$AGD/props-a-v1-v2.json" ] && [ ! -e "$AGD/props-a-v1-v2.png" ] \
  && ok "carried anchors chars-a-v2 and props-a-v2 are proposed, approved_by null, style.version 2, same image sha256 and bytes (the -v1 suffix is replaced: no props-a-v1-v2)" \
  || no "carried anchors" "$carried_why"
[ "$(jq -r 'select(.status == "active") | .id' "$AGD"/*.json | LC_ALL=C sort | tr '\n' ' ')" = "chars-a props-a-v1 " ] \
  && ok "no anchor is written active: only the two pre-existing active anchors have status active" || no "anchor statuses" "$(jq -c '[.id, .status]' "$AGD"/*.json)"
# (3) the report names what needs re-approval
[ "$(jq -c '.needs_reapproval | [.anchors, .runs, .rejections]' "$TMP/sb1.json")" = '[["chars-a","props-a-v1","props-p"],["AGEN-bump-001"],["rej-v1"]]' ] \
  && ok "needs_reapproval lists the carried and proposed anchors, the version 1 run and the version 1 rejection" \
  || no "needs_reapproval" "$(jq -c .needs_reapproval "$TMP/sb1.json")"
[ "$(jq -r '[.anchors[] | "\(.id)=\(.action)"] | join(",")' "$TMP/sb1.json")" = "chars-a=carried,props-a-v1=carried,props-old=none,props-p=reapprove" ] \
  && [ "$(jq -r '[.anchors[] | select(.new_id != null) | "\(.id)>\(.new_id)"] | join(",")' "$TMP/sb1.json")" = "chars-a>chars-a-v2,props-a-v1>props-a-v2" ] \
  && [ "$(jq -r '[.rejections[] | "\(.id)=\(.action)"] | join(",")' "$TMP/sb1.json")" = "rej-any=applies,rej-v1=rerecord" ] \
  && [ "$(jq -r '[.runs[] | "\(.id)=\(.action)"] | join(",")' "$TMP/sb1.json")" = "AGEN-bump-001=reapprove" ] \
  && ok "report rows: anchors carried/reapprove/none with new_id on carried rows, the version null rejection applies, the retired anchor is none" \
  || no "report rows" "$(jq -c '[.anchors, .runs, .rejections]' "$TMP/sb1.json")"
SBT="$TMP/style-bump-text"; sb_copy "$SBT"
AG style bump --id demo-game --authoring "$SBT" > "$TMP/sb1.txt" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 0 ] && grep -q "^anchor props-p " "$TMP/sb1.txt" && grep -q "^anchor chars-a " "$TMP/sb1.txt" && grep -q "^anchor props-a-v1 " "$TMP/sb1.txt" \
  && grep -q "^run AGEN-bump-001 " "$TMP/sb1.txt" && grep -q "^rejection rej-v1 .*rerecord" "$TMP/sb1.txt" && grep -q "^rejection rej-any .*applies" "$TMP/sb1.txt" \
  && grep -q "nothing active was edited" "$TMP/sb1.txt" && ! grep -q "limited to listing" "$TMP/sb1.txt" \
  && ok "the text report names every anchor, run and rejection and says nothing active was edited" || no "text report rc=$rc" "$(cat "$TMP/sb1.txt" "$TMP/sb.err")"
# (4) quality: the bump's own check passes, and artifact-quality shows no FAIL that was not there before
aq_fails() { python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$1" --registry "$ROOT/registry.json" --domain assetgen --json > "$2" 2>> "$TMP/err"
  jq -r '.results[] | select(.state == "FAIL") | "\(.artifact)|\(.check)"' "$2" | LC_ALL=C sort -u; }
aq_fails "$SBP" "$TMP/sb-aq-before.json" > "$TMP/sb-fails-before"; aq_fails "$SB" "$TMP/sb-aq-after.json" > "$TMP/sb-fails-after"
[ "$(jq -r .quality.state "$TMP/sb1.json")" = PASS ] && [ "$(jq -c .quality.new_fails "$TMP/sb1.json")" = '[]' ] \
  && jq -e '([.results[] | select(.check == "parse" and .state == "FAIL")] | length) == 0 and (["AGEN-derive-001", "AGEN-bump-001"] | all(. as $id | any($rows[]; .artifact == $id and (.check | startswith("gen-run-")))))' --argjson rows "$(jq '.results' "$TMP/sb-aq-before.json")" "$TMP/sb-aq-before.json" >/dev/null \
  && jq -e '([.results[] | select(.check == "parse" and .state == "FAIL")] | length) == 0 and (["AGEN-derive-001", "AGEN-bump-001"] | all(. as $id | any($rows[]; .artifact == $id and (.check | startswith("gen-run-")))))' --argjson rows "$(jq '.results' "$TMP/sb-aq-after.json")" "$TMP/sb-aq-after.json" >/dev/null \
  && [ -z "$(LC_ALL=C comm -13 "$TMP/sb-fails-before" "$TMP/sb-fails-after")" ] \
  && ok "quality.state PASS, and artifact-quality --domain assetgen shows no FAIL on the bumped authoring that was not there before ($(wc -l < "$TMP/sb-fails-before" | tr -d ' ') FAIL before, $(wc -l < "$TMP/sb-fails-after" | tr -d ' ') after)" \
  || no "quality after the bump: $(jq -r .quality.state "$TMP/sb1.json")" "$(LC_ALL=C comm -13 "$TMP/sb-fails-before" "$TMP/sb-fails-after"; jq -c .quality "$TMP/sb1.json")"
# (5) a second bump of the same style: the draft exists, nothing is written
h_sb=$(tsig "$SB")
AG style bump --id demo-game --authoring "$SB" > "$TMP/sb2.out" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 1 ] && grep -q "already exists" "$TMP/sb.err" && [ "$(tsig "$SB")" = "$h_sb" ] \
  && ok "a second style bump exits 1 (the draft exists) and writes nothing" || no "second bump rc=$rc" "$(cat "$TMP/sb.err")"
# (6) --list-only writes nothing and still lists
SBL="$TMP/style-bump-list"; sb_copy "$SBL"; h_sbl=$(tsig "$SBL"); g_sbl=$(git -C "$SBL" status --porcelain)
AG style bump --id demo-game --authoring "$SBL" --list-only --json > "$TMP/sbl.json" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 0 ] && [ "$(tsig "$SBL")" = "$h_sbl" ] && [ "$(git -C "$SBL" status --porcelain)" = "$g_sbl" ] && [ ! -e "$SBL/assetgen/styles/demo-game/versions" ] \
  && [ "$(jq -r .draft.written "$TMP/sbl.json")" = false ] && [ "$(jq -r .list_only "$TMP/sbl.json")" = true ] && [ "$(jq -r .quality.state "$TMP/sbl.json")" = SKIPPED ] \
  && [ "$(jq -c .needs_reapproval "$TMP/sbl.json")" = "$(jq -c .needs_reapproval "$TMP/sb1.json")" ] \
  && ok "style bump --list-only writes nothing (tree and git status unchanged), skips the quality check and lists the same re-approvals" \
  || no "list-only rc=$rc" "$(cat "$TMP/sb.err"; jq -c '[.draft, .quality, .needs_reapproval]' "$TMP/sbl.json")"
AG style bump --id demo-game --authoring "$SBL" --list-only > "$TMP/sbl.txt" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 0 ] && grep -q "nothing written" "$TMP/sbl.txt" && grep -q "^anchor props-p " "$TMP/sbl.txt" && [ "$(tsig "$SBL")" = "$h_sbl" ] \
  && ok "the --list-only text says nothing was written and still names the anchors" || no "list-only text rc=$rc" "$(cat "$TMP/sbl.txt" "$TMP/sb.err")"
# (7) refusals
SBDR="$TMP/style-bump-draft"; rm -rf "$SBDR"; mkdir -p "$SBDR"
AG style init --id demo-game --extends pixel-art --authoring "$SBDR" > /dev/null 2>&1; h_dr=$(tsig "$SBDR")
AG style bump --id demo-game --authoring "$SBDR" > "$TMP/sb.out" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 1 ] && grep -q "only works on an active style" "$TMP/sb.err" && [ "$(tsig "$SBDR")" = "$h_dr" ] \
  && ok "style bump of a draft style exits 1 and writes nothing" || no "draft bump rc=$rc" "$(cat "$TMP/sb.err")"
SBC="$TMP/style-bump-core"; sb_copy "$SBC"; h_c=$(tsig "$SBC")
AG style bump --id pixel-art --authoring "$SBC" > "$TMP/sb.out" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 1 ] && grep -q "has no game file" "$TMP/sb.err" && [ "$(tsig "$SBC")" = "$h_c" ] \
  && ok "style bump of a core-only style id exits 1 and writes nothing" || no "core-only bump rc=$rc" "$(cat "$TMP/sb.err")"
AG style bump --id "Bad_Id" --authoring "$SBC" > "$TMP/sb.out" 2> "$TMP/sb.err"; rc=$?
[ $rc -eq 2 ] && grep -q "must be a lowercase id" "$TMP/sb.err" && [ "$(tsig "$SBC")" = "$h_c" ] \
  && ok "style bump with a malformed --id exits 2 and writes nothing" || no "malformed --id rc=$rc" "$(cat "$TMP/sb.err")"
# (8) the quality plugin rejects the carried anchors (a stub FAILs once any *-v2.json anchor exists) or cannot run (non-JSON)
cat > "$TMP/sb-quality-stub.py" <<'EOF'
import glob, json, os, sys
fail = glob.glob(os.path.join(sys.argv[1], "assetgen", "styles", "*", "anchors", "*-v2.json"))
print(json.dumps({"results": [{"artifact": "AGEN-stub", "check": "gen-run-style", "state": "FAIL" if fail else "PASS",
                               "reasons": ["a carried anchor broke the stub"] if fail else []}]}))
EOF
printf 'print("this is not json")\n' > "$TMP/sb-quality-garbage.py"
for kind in "stub REJECTED" "garbage NOT_RUN"; do
  read -r k want <<<"$kind"
  SBQ="$TMP/style-bump-q-$k"; sb_copy "$SBQ"; sb_files "$SBQ" > "$TMP/sb.before"
  ( export RPG_FACTORY_ASSETGEN_QUALITY_SCRIPT="$TMP/sb-quality-$k.py"; AG style bump --id demo-game --authoring "$SBQ" --json > "$TMP/sbq.json" 2> "$TMP/sb.err" ); rc=$?
  sb_files "$SBQ" > "$TMP/sb.after"
  [ $rc -eq 0 ] && [ "$(jq -r .quality.state "$TMP/sbq.json")" = "$want" ] && [ -f "$SBQ/assetgen/styles/demo-game/versions/2.json" ] && [ "$(jq -r .draft.written "$TMP/sbq.json")" = true ] \
    && [ -z "$(find "$SBQ/assetgen/styles/demo-game/anchors" -name '*-v2.*')" ] \
    && [ "$(LC_ALL=C comm -13 "$TMP/sb.before" "$TMP/sb.after")" = "./assetgen/styles/demo-game/versions/2.json" ] && [ -z "$(sb_changed "$SBP" "$SBQ")" ] \
    && [ "$(jq '[.anchors[] | select(.action == "carried" or .new_id != null)] | length' "$TMP/sbq.json")" = 0 ] \
    && [ "$(jq -c '.needs_reapproval.anchors' "$TMP/sbq.json")" = '["chars-a","props-a-v1","props-p"]' ] \
    && ok "quality $want ($k stub): exit 0, the draft stays, no carried anchor file remains, every anchor is still listed for re-approval" \
    || no "quality $want ($k) rc=$rc" "$(cat "$TMP/sb.err"; jq -c '[.quality, .anchors]' "$TMP/sbq.json"; find "$SBQ/assetgen/styles/demo-game" -type f)"
  [ "$want" != REJECTED ] || { [ "$(jq -c '[.quality.new_fails[] | [.artifact, .check]]' "$TMP/sbq.json")" = '[["AGEN-stub","gen-run-style"]]' ] \
    && ok "a quality rejection names the new FAIL (artifact and check)" || no "new_fails" "$(jq -c .quality "$TMP/sbq.json")"; }
  sb_copy "$SBQ"
  ( export RPG_FACTORY_ASSETGEN_QUALITY_SCRIPT="$TMP/sb-quality-$k.py"; AG style bump --id demo-game --authoring "$SBQ" > "$TMP/sbq.txt" 2> "$TMP/sb.err" ); rc=$?
  [ $rc -eq 0 ] && grep -q "^quality: $want" "$TMP/sbq.txt" && grep -q "the verb was limited to listing" "$TMP/sbq.txt" && grep -q "nothing active was edited" "$TMP/sbq.txt" \
    && ! grep -q "^wrote assetgen/styles/demo-game/anchors/" "$TMP/sbq.txt" \
    && ok "quality $want ($k stub): the text output says the verb was limited to listing" || no "limited-to-listing text ($k) rc=$rc" "$(cat "$TMP/sbq.txt" "$TMP/sb.err")"
done
# (9) style derive keeps passing its own cases above (unchanged); (10) core data untouched
[ "$(tpl_hash)" = "$tpl0" ] && [ -z "$(git -C "$ROOT" status --porcelain -- templates/assetgen)" ] \
  && ok "style bump changed nothing under templates/assetgen" || no "templates/assetgen changed by bump" "$(git -C "$ROOT" status --porcelain -- templates/assetgen)"

echo "-- style report: spreads, QA rates, rejections and suggested thresholds, read-only (style_report.py)"
# fixture: a draft game style at version 1 (init, anchors chars-a / props-a / props-b, derive --apply: palette of 4 colours,
# tone.tolerance 0.05, palette.max_distance 48 and min_share 0.6 by default), then runs, qa.json files and rejections:
#   r-props-1 approved props   outputs ok (d_needed 0), near (40), bad.png (garbage), clear.png (transparent)
#                              qa palette PASS, tone PASS, edges NOT_AVAILABLE (+ a non-style row)
#   r-props-2 approved props   output far (d_needed 80)               qa palette FAIL, tone WARN, edges PASS
#   r-props-3 rejected props   no outputs                             qa palette WARN, tone WARN, edges PASS
#   r-chars-1 approved characters output chars (d_needed 40)          qa palette PASS, tone FAIL
#   r-ui-1    rejected ui      no outputs                             qa.json is not JSON
#   r-none    approved, no family, no outputs directory
#   r-other   a run of another style; r-broken: run.md without front matter; derive-001: the anchors' source run
# rejections: two props palette_off, one characters anatomy (asset), one family-less other, one malformed props record
SR="$TMP/style-report"; mkdir -p "$SR"
AG style init --id demo-game --extends pixel-art --authoring "$SR" > "$TMP/sr.out" 2> "$TMP/sr.err" || no "style report setup: style init" "$(cat "$TMP/sr.err")"
sr_setup() {   # sr_setup MODE: anchors (before derive) | records (runs, qa, rejections; writes $TMP/sr.expect)
python3 -B - "$ROOT" "$SR" "$1" "$TMP/sr.expect" 2>&1 <<'EOF' | tr -d '\r'
import hashlib, json, math, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import consistency, layers, png, stylelock
A, mode, expect = sys.argv[2], sys.argv[3], sys.argv[4]
G = os.path.join(A, "assetgen")
D = os.path.join(G, "styles", "demo-game")
AD, RD = os.path.join(D, "anchors"), os.path.join(D, "rejections")
ref = stylelock.style_ref(layers.load("style", "demo-game", A))
def jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")
def front(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("---json\n%s\n---\n# run\n" % json.dumps(obj))
def disc(w, h, a, b):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            d = ((x - w / 2) ** 2 + (y - h / 2) ** 2) ** 0.5
            px += bytes((a if x < w // 2 else b) + (255,)) if d < min(w, h) * 0.3 else bytes((0, 0, 0, 0))
    return png.encode(w, h, bytes(px))
def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
if mode == "anchors":
    front(os.path.join(G, "runs", "derive-001", "run.md"), {"id": "AGEN-derive-001", "status": "approved"})
    for aid, family, w, h, a, b in (("chars-a", "characters", 256, 384, (40, 60, 200), (220, 200, 40)),
                                    ("props-a", "props", 256, 256, (200, 40, 40), (40, 160, 60)),
                                    ("props-b", "props", 256, 256, (200, 40, 40), (40, 160, 60))):
        data = disc(w, h, a, b)
        put(os.path.join(AD, aid + ".png"), data)
        jdump(os.path.join(AD, aid + ".json"),
              {"schema": "rpg-factory.assetgen-anchor/1", "id": aid, "status": "active", "style": ref, "family": family,
               "dimensions": ["palette", "shape"], "strength": "strong", "image": aid + ".png",
               "image_sha256": hashlib.sha256(data).hexdigest(),
               "source_run": {"run_id": "derive-001", "output": "outputs/a.png", "sha256": "0" * 64},
               "approved_by": "Dana", "approved_on": "2026-11-01"})
else:
    def run(rid, status, family, outputs, qa=None, style=ref, raw_qa=None):
        lock = {"style": style}
        ids = {"props": ["props-a", "props-b"], "characters": ["chars-a"]}.get(family, []) if status == "approved" and style == ref else []
        lock["references"] = [{"anchor_id": aid, "image": "references/anchor-" + aid + ".png"} for aid in ids]
        for aid in ids:
            put(os.path.join(G, "runs", rid, "references", "anchor-" + aid + ".png"), open(os.path.join(AD, aid + ".png"), "rb").read())
        if family:
            lock["family"] = family
        front(os.path.join(G, "runs", rid, "run.md"), {"id": "AGEN-" + rid, "status": status, "spec": {"style_lock": lock}})
        for name, data in outputs.items():
            put(os.path.join(G, "runs", rid, "outputs", name), data)
        if qa is not None:
            jdump(os.path.join(G, "runs", rid, "qa.json"), {"results": [{"check": c, "state": s} for c, s in qa]})
        if raw_qa is not None:
            put(os.path.join(G, "runs", rid, "qa.json"), raw_qa)
    red, green = (200, 40, 40), (40, 160, 60)
    props = {"ok.png": disc(256, 256, red, green), "near.png": disc(256, 256, red, (40, 160, 100)),
             "bad.png": b"this is not a png", "clear.png": png.encode(64, 64, bytes(64 * 64 * 4))}
    run("r-props-1", "approved", "props", props,
        [("style-palette", "PASS"), ("style-tone", "PASS"), ("style-edges", "NOT_AVAILABLE"), ("artifact-quality", "FAIL")])
    run("r-props-2", "approved", "props", {"far.png": disc(256, 256, red, (40, 160, 140))},
        [("style-palette", "FAIL"), ("style-tone", "WARN"), ("style-edges", "PASS")])
    run("r-props-3", "rejected", "props", {}, [("style-palette", "WARN"), ("style-tone", "WARN"), ("style-edges", "PASS")])
    run("r-chars-1", "approved", "characters", {"chars.png": disc(128, 192, (40, 60, 200), (220, 200, 80))},
        [("style-palette", "PASS"), ("style-tone", "FAIL")])
    run("r-ui-1", "rejected", "ui", {}, raw_qa=b"{ not json")
    run("r-none", "approved", None, {"unanchored.png": disc(256, 256, red, green)})
    run("r-other", "approved", "props", {}, [("style-palette", "FAIL")], style={"style_id": "other-game", "version": 1, "sha256": "1" * 64})
    os.makedirs(os.path.join(G, "runs", "r-broken"), exist_ok=True)
    with open(os.path.join(G, "runs", "r-broken", "run.md"), "w", encoding="utf-8") as f:
        f.write("no front matter\n")
    def rej(rid, rtype, family, reason, text=None, run_ref=None):
        obj = {"schema": "rpg-factory.assetgen-rejection/1", "id": rid, "type": rtype, "style": ref, "family": family,
               "reason": reason, "text": text}
        if run_ref:
            obj["run"] = run_ref
        jdump(os.path.join(RD, rid + ".json"), obj)
        errs = stylelock.rejection_errors(json.load(open(os.path.join(RD, rid + ".json"), encoding="utf-8")), "demo-game", rid)
        return errs
    errs = {}
    errs["rej-1"] = rej("rej-1", "direction", "props", "palette_off", "too saturated")
    errs["rej-2"] = rej("rej-2", "direction", "props", "palette_off", "off palette again")
    errs["rej-3"] = rej("rej-3", "asset", "characters", "anatomy", None, {"run_id": "r-chars-1", "output": "outputs/chars.png", "sha256": "2" * 64})
    errs["rej-4"] = rej("rej-4", "direction", None, "other", "no text on any family")
    rej("rej-bad", "direction", "props", "bogus", "malformed on purpose")
    bad = [k for k, v in errs.items() if v]
    if bad or not stylelock.rejection_errors(json.load(open(os.path.join(RD, "rej-bad.json"), encoding="utf-8")), "demo-game", "rej-bad"):
        print("fixture rejections invalid:", bad, errs)
        sys.exit(0)
    # expected tone numbers, from the PNGs and anchors on disk, independent of the report's grouping code
    def tone(path):
        return consistency.tone_stats(png.decode(path))
    def need(anchors, outs):
        n = 0.0
        for k in (0, 1):
            lo, hi = min(a[k] for a in anchors), max(a[k] for a in anchors)
            n = max(n, max(max(0.0, lo - o[k], o[k] - hi) for o in outs))
        return n
    def inside(anchors, outs, tol):
        return sum(1 for o in outs if all(min(a[k] for a in anchors) - tol <= o[k] <= max(a[k] for a in anchors) + tol for k in (0, 1)))
    out = lambda rid, name: tone(os.path.join(G, "runs", rid, "outputs", name))
    anc = lambda aid: tone(os.path.join(AD, aid + ".png"))
    p_out = [out("r-props-1", "ok.png"), out("r-props-1", "near.png"), out("r-props-2", "far.png")]
    c_out = [out("r-chars-1", "chars.png")]
    p_anc, c_anc = [anc("props-a"), anc("props-b")], [anc("chars-a")]
    exp = {"props_need": need(p_anc, p_out), "props_inside": inside(p_anc, p_out, 0.05),
           "chars_need": need(c_anc, c_out), "chars_inside": inside(c_anc, c_out, 0.05),
           "total_need": max(need(p_anc, p_out), need(c_anc, c_out)), "total_inside": inside(p_anc, p_out, 0.05) + inside(c_anc, c_out, 0.05),
           "props_lum": [round(min(o[0] for o in p_out), 3), round(max(o[0] for o in p_out), 3)],
           "props_sat": [round(min(o[1] for o in p_out), 3), round(max(o[1] for o in p_out), 3)]}
    jdump(expect, exp)
print("ok")
EOF
}
sr_setup anchors > "$TMP/sr.setup"; grep -qx ok "$TMP/sr.setup" || no "style report setup: anchors" "$(cat "$TMP/sr.setup")"
AG style derive --style demo-game --authoring "$SR" --apply > "$TMP/sr.out" 2> "$TMP/sr.err" || no "style report setup: style derive --apply" "$(cat "$TMP/sr.err")"
sr_setup records > "$TMP/sr.setup"; grep -qx ok "$TMP/sr.setup" || no "style report setup: records" "$(cat "$TMP/sr.setup")"
sr_sig() { (cd "$1" && { find . -not -path './.git/*' | LC_ALL=C sort; find . -type f -not -path './.git/*' -exec sha256sum {} + | LC_ALL=C sort; } | sha256sum | cut -d' ' -f1); }
SRJ() { jq -c "($1) | walk(if type == \"number\" then . + 0 else . end)" "$TMP/sr1.json"; }   # a query over the full report, numbers canonical
DG='.styles[] | select(.style_id == "demo-game")'
sig_sr=$(sr_sig "$SR"); h_srs=$(sha256sum "$SR/assetgen/styles/demo-game.json" | cut -d' ' -f1)
AG style report --authoring "$SR" --json > "$TMP/sr1.json" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .schema "$TMP/sr1.json")" = "rpg-factory.assetgen-style-report/1" ] && [ "$(SRJ '[.styles[].style_id]')" = '["demo-game","other-game"]' ] \
  && [ "$(SRJ '.style_filter')" = null ] && [ "$(SRJ "$DG | [.version, .status, .game_file]")" = '[1,"draft",true]' ] \
  && ok "style report --json exits 0: schema rpg-factory.assetgen-style-report/1, the game style and the style only a run names" || no "style report --json rc=$rc" "$(cat "$TMP/sr.err"; head -c 600 "$TMP/sr1.json")"
AG style report --authoring "$SR" > "$TMP/sr1.txt" 2> "$TMP/sr.err"; rc2=$?
[ $rc2 -eq 0 ] && grep -q "^style demo-game version 1 status draft" "$TMP/sr1.txt" && grep -q "^  family props:" "$TMP/sr1.txt" && grep -q "^  all families:" "$TMP/sr1.txt" \
  && ok "style report (text) exits 0 and prints the style, each family and the all-families total" || no "style report text rc=$rc2" "$(cat "$TMP/sr.err" "$TMP/sr1.txt")"
# read-only: the authoring dir (files, directories, content) is exactly as before, so is core data
[ "$(sr_sig "$SR")" = "$sig_sr" ] && [ "$(sha256sum "$SR/assetgen/styles/demo-game.json" | cut -d' ' -f1)" = "$h_srs" ] \
  && [ "$(tpl_hash)" = "$tpl0" ] && [ -z "$(git -C "$ROOT" status --porcelain -- templates/assetgen)" ] \
  && ok "style report writes nothing: the authoring dir (files, directories, content), the style file and templates/assetgen are unchanged" || no "style report changed files" "$(git -C "$ROOT" status --porcelain -- templates/assetgen)"
AG style report --authoring "$SR" --json > "$TMP/sr2.json" 2> "$TMP/sr.err"; AG style report --authoring "$SR" > "$TMP/sr2.txt" 2>> "$TMP/sr.err"
cmp -s "$TMP/sr1.json" "$TMP/sr2.json" && cmp -s "$TMP/sr1.txt" "$TMP/sr2.txt" && [ -s "$TMP/sr1.txt" ] \
  && ok "two style report runs give byte-identical --json and text output" || no "style report output differs between runs" "$(diff "$TMP/sr1.json" "$TMP/sr2.json" | head -20)"
# --style restricts to one style, and its entry is the same as in the full report
AG style report --authoring "$SR" --style demo-game --json > "$TMP/sr-s.json" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c '[.style_filter, (.styles | map(.style_id))]' "$TMP/sr-s.json")" = '["demo-game",["demo-game"]]' ] \
  && [ "$(jq -cS '.styles[0]' "$TMP/sr-s.json")" = "$(jq -cS "$DG" "$TMP/sr1.json")" ] \
  && ok "style report --style demo-game restricts to that style (same data as in the full report)" || no "--style restriction rc=$rc" "$(cat "$TMP/sr.err"; jq -c '[.style_filter, (.styles | map(.style_id))]' "$TMP/sr-s.json")"
AG style report --authoring "$SR" --style other-game --json > "$TMP/sr-o.json" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c '.styles | map(.style_id)' "$TMP/sr-o.json")" = '["other-game"]' ] && [ "$(jq -c '.styles[0] | [.game_file, .total.runs.total, (.error != null)]' "$TMP/sr-o.json")" = '[false,1,true]' ] \
  && ok "style report --style of a style only a run names: exit 0, no game file, its one run counted, the load error reported" || no "other-game report rc=$rc" "$(cat "$TMP/sr.err"; head -c 500 "$TMP/sr-o.json")"
# per-family grouping and the runs by status
[ "$(SRJ "$DG | .families | keys")" = '["(none)","characters","props","ui"]' ] \
  && [ "$(SRJ "$DG | .families | map_values(.runs)")" = '{"(none)":{"by_status":{"approved":1},"total":1},"characters":{"by_status":{"approved":1},"total":1},"props":{"by_status":{"approved":2,"rejected":1},"total":3},"ui":{"by_status":{"rejected":1},"total":1}}' ] \
  && [ "$(SRJ "$DG | .total.runs")" = '{"by_status":{"approved":4,"rejected":2},"total":6}' ] \
  && ok "style report groups per family (a run without a family is (none)); the total counts the style's 6 runs by status, not other-game's or the unstyled ones" \
  || no "family grouping" "$(SRJ "$DG | [.families | map_values(.runs), .total.runs]")"
[ "$(SRJ "$DG | .families | map_values(.approved_outputs)")" = '{"(none)":1,"characters":1,"props":3,"ui":0}' ] && [ "$(SRJ "$DG | .total.approved_outputs")" = 5 ] \
  && ok "style report counts five approved outputs across the families" || no "approved outputs" "$(SRJ "$DG | [.families | map_values(.approved_outputs), .total.approved_outputs]")"
# QA: the WARN and FAIL rate of every style-* row equals the fixture counts; non-style rows are not counted
[ "$(SRJ "$DG | .families.props.qa")" = '{"style-edges":{"FAIL":0,"NOT_AVAILABLE":1,"PASS":2,"WARN":0,"fail_rate":0,"rows":3,"warn_rate":0},"style-palette":{"FAIL":1,"NOT_AVAILABLE":0,"PASS":1,"WARN":1,"fail_rate":0.333,"rows":3,"warn_rate":0.333},"style-tone":{"FAIL":0,"NOT_AVAILABLE":0,"PASS":1,"WARN":2,"fail_rate":0,"rows":3,"warn_rate":0.667}}' ] \
  && ok "style report QA rates (props): style-palette warn/fail 0.333/0.333, style-tone 0.667/0, style-edges 0/0 with its NOT_AVAILABLE counted; artifact-quality not a style row" \
  || no "props QA rates" "$(SRJ "$DG | .families.props.qa")"
[ "$(SRJ "$DG | .families.characters.qa | map_values([.rows, .warn_rate, .fail_rate])")" = '{"style-palette":[1,0,0],"style-tone":[1,0,1]}' ] \
  && [ "$(SRJ "$DG | .total.qa | map_values([.rows, .PASS, .WARN, .FAIL, .NOT_AVAILABLE, .warn_rate, .fail_rate])")" = '{"style-edges":[3,2,0,0,1,0,0],"style-palette":[4,2,1,1,0,0.25,0.25],"style-tone":[4,1,2,1,0,0.5,0.25]}' ] \
  && [ "$(SRJ "$DG | (.families.ui.qa, .families.\"(none)\".qa)")" = '{}
{}' ] \
  && ok "style report QA rates (characters, total): style-palette 0.25/0.25 over 4 rows, style-tone 0.5/0.25, a family without rows has none" \
  || no "total QA rates" "$(SRJ "$DG | [.families.characters.qa, .total.qa]")"
[ "$(SRJ "$DG | [.qa_runs, .qa_unreadable]")" = '[4,["r-ui-1"]]' ] && [ "$(SRJ '.runs_unreadable')" = '["r-broken"]' ] \
  && grep -q "qa.json read from 4 run(s); unreadable: r-ui-1" "$TMP/sr1.txt" && grep -q "runs with unreadable run.md: r-broken" "$TMP/sr1.txt" \
  && ok "style report: a qa.json that is not JSON and a run.md without front matter are listed, not a crash" || no "unreadable qa/run" "$(SRJ "$DG | [.qa_runs, .qa_unreadable]") $(SRJ '.runs_unreadable')"
# rejections by reason
[ "$(SRJ "$DG | .total.rejections")" = '{"by_reason":{"anatomy":1,"malformed":1,"other":1,"palette_off":2},"total":5}' ] \
  && [ "$(SRJ "$DG | .families.props.rejections")" = '{"by_reason":{"malformed":1,"palette_off":2},"total":3}' ] \
  && [ "$(SRJ "$DG | .families.characters.rejections")" = '{"by_reason":{"anatomy":1},"total":1}' ] \
  && [ "$(SRJ "$DG | .families.\"(none)\".rejections")" = '{"by_reason":{"other":1},"total":1}' ] && [ "$(SRJ "$DG | .families.ui.rejections.total")" = 0 ] \
  && grep -q "rejections: 5 (anatomy 1, malformed 1, other 1, palette_off 2)" "$TMP/sr1.txt" \
  && ok "style report counts the rejections by reason, per family and in total (a malformed record under malformed)" || no "rejections" "$(SRJ "$DG | [.total.rejections, (.families | map_values(.rejections))]")"
# tone spread and the skipped outputs
exp() { jq -c "($1) | walk(if type == \"number\" then . + 0 else . end)" "$TMP/sr.expect"; }
[ "$(SRJ "$DG | .families.props.tone | [.luminance.min, .luminance.max]")" = "$(exp .props_lum)" ] && [ "$(SRJ "$DG | .families.props.tone | [.saturation.min, .saturation.max]")" = "$(exp .props_sat)" ] \
  && [ "$(SRJ "$DG | .families.ui.tone")" = '{"luminance":null,"saturation":null}' ] \
  && ok "style report tone spread over the approved props outputs: min and max luminance and saturation match the PNGs; a group without outputs has none" || no "tone spread" "$(SRJ "$DG | .families.props.tone") $(cat "$TMP/sr.expect")"
[ "$(jq -c '.styles[] | select(.style_id == "demo-game") | [.skipped.outputs[] | [.run, .output, (.reason | split(" (")[0])]]' "$TMP/sr1.json")" = '[["r-props-1","outputs/bad.png","not readable"],["r-props-1","outputs/clear.png","no opaque pixels"]]' ] \
  && grep -q "output skipped: r-props-1 outputs/bad.png: not readable" "$TMP/sr1.txt" \
  && ok "style report skips an unreadable and a fully transparent approved output (listed with a reason), the other outputs still count" || no "skipped outputs" "$(SRJ "$DG | .skipped")"
# suggestions: palette.max_distance with its data
[ "$(SRJ "$DG | .families.props.suggestions.\"palette.max_distance\"")" = '{"applied":false,"data":{"current":48,"d_needed":{"max":80,"median":40,"min":0},"min_share":0.6,"outputs":3,"pass_at_current":2},"reason":null,"value":80}' ] \
  && [ "$(SRJ "$DG | .families.characters.suggestions.\"palette.max_distance\" | [.value, .data.current, .data.outputs, .data.pass_at_current]")" = '[40,48,1,1]' ] \
  && [ "$(SRJ "$DG | .total.suggestions.\"palette.max_distance\" | [.value, .data.outputs, .data.d_needed.median, .data.pass_at_current]")" = '[80,5,40,4]' ] \
  && ok "suggested palette.max_distance = the largest d_needed (props 80, characters 40, total 80), with current 48, min_share 0.6, the d_needed spread and how many pass at current" || no "palette suggestion" "$(SRJ "$DG | .total.suggestions")"
# suggestions: tone.tolerance with its data (value is the smallest 2-decimal tolerance that keeps every approved output inside the anchor range)
sr_tone_qa() {
python3 -B - "$ROOT" "$SR" "$TMP/sr1.json" "$1" <<'EOF'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import consistency, png, qa, re
root, report, group = sys.argv[2:]
style = next(s for s in json.load(open(report, encoding="utf-8"))["styles"] if s["style_id"] == "demo-game")
selection = style["total"] if group == "total" else style["families"][{"props": "props", "chars": "characters"}[group]]
tol = selection["suggestions"]["tone.tolerance"]["value"]
outputs = {"props": [("r-props-1", "ok.png"), ("r-props-1", "near.png"), ("r-props-2", "far.png")],
           "chars": [("r-chars-1", "chars.png")]}
chosen = outputs["props"] + outputs["chars"] if group == "total" else outputs[group]
def passes(t):
    states = []
    for rid, name in chosen:
        run = os.path.join(root, "assetgen", "runs", rid)
        front = json.loads(re.match(r"\A---json\s*\n(.*?)\n---", open(os.path.join(run, "run.md"), encoding="utf-8").read(), re.S).group(1))
        anchors = qa.style_anchors(run, front["spec"])
        img = png.decode(os.path.join(run, "outputs", name))
        states.append(consistency.check_tone(img, {"tone": {"tolerance": t}}, anchors)[0] == "PASS")
    return all(states)
assert passes(tol)
if tol > 0:
    assert not passes(round(tol - 0.01, 2))
EOF
}
for g in props:props chars:characters total:total; do
  k=${g%%:*}; sel=".families.${g#*:}"; [ "${g#*:}" = total ] && sel=".total"
  [ "$(SRJ "$DG | $sel.suggestions.\"tone.tolerance\" | [.applied, .reason, .data.current, (.data | has(\"selected_anchor_range\") and has(\"output_range\"))]")" = '[false,null,0.05,true]' ] \
    && [ "$(SRJ "$DG | $sel.suggestions.\"tone.tolerance\".data.inside_at_current")" = "$(exp .${k}_inside)" ] \
    && sr_tone_qa "$k" > "$TMP/sr-tone-qa" 2>&1 \
    && ok "style report tone.tolerance suggestion ($k): the smallest two-decimal value that passes QA for all outputs" \
    || no "tone suggestion ($k)" "$(SRJ "$DG | $sel.suggestions.\"tone.tolerance\"") $(cat "$TMP/sr-tone-qa")"
done
[ "$(SRJ "$DG | .families.props.suggestions.\"tone.tolerance\".data | [.anchors, .anchor_copies, .outputs]")" = '[2,4,3]' ] && [ "$(SRJ "$DG | .families.characters.suggestions.\"tone.tolerance\".data | [.anchors, .anchor_copies, .outputs]")" = '[1,1,1]' ] \
  && [ "$(SRJ "$DG | .total.suggestions.\"tone.tolerance\".data | [.anchors, .anchor_copies, .outputs]")" = '[3,5,5]' ] \
  && [ "$(SRJ "$DG | .total.suggestions.\"tone.tolerance\".data.outputs_without_anchors")" = 1 ] \
  && [ "$(SRJ "$DG | .families.\"(none)\".suggestions.\"tone.tolerance\" | [.value, .data.outputs_without_anchors, (.reason | type)]")" = '[null,1,"string"]' ] \
  && ok "style report counts distinct anchors and selected copies separately and excludes outputs without usable anchors" || no "tone scope" "$(SRJ "$DG | .total.suggestions")"
# One anchor selected by two runs is one anchor and two selected copies (the label and the JSON count agree).
SRD="$TMP/sr-dup-anchor"
cp -R "$SR" "$SRD"
python3 -B - "$SRD" > "$TMP/sr-dup.setup" 2>&1 <<'EOF'
import json, os, re, sys
for rid in ("r-props-1", "r-props-2"):
    path = os.path.join(sys.argv[1], "assetgen", "runs", rid, "run.md")
    text = open(path, encoding="utf-8", newline="").read()
    match = re.match(r"\A---json\n(.*?)\n---\n", text, re.S)
    front = json.loads(match.group(1))
    refs = front["spec"]["style_lock"]["references"]
    front["spec"]["style_lock"]["references"] = [r for r in refs if r["anchor_id"] == "props-a"]
    assert len(front["spec"]["style_lock"]["references"]) == 1, refs
    open(path, "w", encoding="utf-8", newline="").write("---json\n" + json.dumps(front) + "\n---\n" + text[match.end():])
EOF
sr_dup_rc=$?
AG style report --authoring "$SRD" --style demo-game --json > "$TMP/sr-dup.json" 2> "$TMP/sr-dup.err"; rc=$?
AG style report --authoring "$SRD" --style demo-game > "$TMP/sr-dup.txt" 2>> "$TMP/sr-dup.err"; rc2=$?
[ "$sr_dup_rc" -eq 0 ] && [ $rc -eq 0 ] && [ $rc2 -eq 0 ] \
  && [ "$(jq -c '.styles[0].families.props.suggestions["tone.tolerance"].data | [.anchors, .anchor_copies, .outputs]' "$TMP/sr-dup.json")" = '[1,2,3]' ] \
  && [ "$(jq -c '.styles[0].total.suggestions["tone.tolerance"].data | [.anchors, .anchor_copies]' "$TMP/sr-dup.json")" = '[2,3]' ] \
  && grep -qF "1 selected anchor(s) (distinct); 2 selected anchor copy/copies; 3 approved output(s)" "$TMP/sr-dup.txt" \
  && ok "style report: one anchor selected by two runs is 1 distinct anchor and 2 selected copies (text and --json)" \
  || no "style report anchor copies rc=$sr_dup_rc/$rc/$rc2" "$(cat "$TMP/sr-dup.setup" "$TMP/sr-dup.err"; jq -c '.styles[0].families.props.suggestions["tone.tolerance"].data' "$TMP/sr-dup.json" 2>&1; grep 'tone.tolerance' "$TMP/sr-dup.txt")"
# The selected black and white anchors must not be pooled across families.
SR_REPRO="$TMP/sr-selected"
cp -R "$SR" "$SR_REPRO"
python3 -B - "$ROOT" "$SR_REPRO" > "$TMP/sr-selected.setup" 2>&1 <<'EOF'
import hashlib, json, os, shutil, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
root = os.path.join(sys.argv[2], "assetgen")
runs = os.path.join(root, "runs")
ref = json.loads(open(os.path.join(runs, "r-props-1", "run.md"), encoding="utf-8").read().split("---")[1][4:])["spec"]["style_lock"]["style"]
shutil.rmtree(runs)
for family, anchor, output in (("props", 0, 128), ("characters", 255, 255)):
    run = os.path.join(runs, family)
    for sub in ("references", "outputs"):
        os.makedirs(os.path.join(run, sub))
    def write(path, value):
        open(path, "wb").write(png.encode(1, 1, bytes((value, value, value, 255))))
    write(os.path.join(run, "references", "anchor.png"), anchor)
    write(os.path.join(run, "outputs", "output.png"), output)
    aid = "props-a" if family == "props" else "chars-a"
    ad = os.path.join(root, "styles", "demo-game", "anchors")
    write(os.path.join(ad, aid + ".png"), anchor)
    metadata = os.path.join(ad, aid + ".json")
    data = json.load(open(metadata, encoding="utf-8"))
    data["image_sha256"] = hashlib.sha256(open(os.path.join(ad, aid + ".png"), "rb").read()).hexdigest()
    json.dump(data, open(metadata, "w", encoding="utf-8"))
    front = {"status": "approved", "spec": {"style_lock": {"style": ref, "family": family,
             "references": [{"anchor_id": family, "image": "references/anchor.png"}]}}}
    open(os.path.join(run, "run.md"), "w", encoding="utf-8").write("---json\n" + json.dumps(front) + "\n---\n")
EOF
sr_setup_rc=$?
[ "$sr_setup_rc" -eq 0 ] || no "selected-anchor regression: setup script failed rc=$sr_setup_rc" "$(cat "$TMP/sr-selected.setup")"
AG style report --authoring "$SR_REPRO" --style demo-game --json > "$TMP/sr-selected.json" 2> "$TMP/sr-selected.err"
python3 -B - "$ROOT" "$SR_REPRO" "$TMP/sr-selected.json" >> "$TMP/sr-selected.err" 2>&1 <<'EOF'
import json, os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import consistency, png, qa
style = json.load(open(sys.argv[3], encoding="utf-8"))["styles"][0]
for group, families in ((style["families"]["props"], ["props"]), (style["families"]["characters"], ["characters"]), (style["total"], ["props", "characters"])):
    tol = group["suggestions"]["tone.tolerance"]["value"]
    if len(families) == 2:
        assert tol == 0.51, tol
    def passes(t):
        results = []
        for family in families:
            run = os.path.join(sys.argv[2], "assetgen", "runs", family)
            front = json.loads(re.match(r"\A---json\s*\n(.*?)\n---", open(os.path.join(run, "run.md"), encoding="utf-8").read(), re.S).group(1))
            results.append(consistency.check_tone(png.decode(os.path.join(run, "outputs", "output.png")),
                           {"tone": {"tolerance": t}}, qa.style_anchors(run, front["spec"]))[0] == "PASS")
        return all(results)
    assert passes(tol)
    assert tol == 0 or not passes(round(tol - 0.01, 2))
EOF
sr_verify_rc=$?
[ "$sr_setup_rc" -eq 0 ] && [ "$sr_verify_rc" -eq 0 ] && ok "tone suggestions pass QA against each run's selected black or white anchor" \
  || no "selected-anchor tone regression (setup rc=$sr_setup_rc, check rc=$sr_verify_rc)" "$(cat "$TMP/sr-selected.setup" "$TMP/sr-selected.err")"
# the text prints each suggestion with its numbers and says not applied
grep -q "^    palette.max_distance = 80 (suggestion only, not applied): current 48; min_share 0.6; 3 approved output(s); d_needed min 0 median 40 max 80; 2 pass at current" "$TMP/sr1.txt" \
  && grep -Eq "^    tone.tolerance = 0\.[0-9]+ \(suggestion only, not applied\): current 0.05; 2 selected anchor\(s\) \(distinct\); 4 selected anchor copy/copies; 3 approved output\(s\); 0 output\(s\) without anchors; luminance selected anchors \[.*\] outputs \[.*\]; saturation selected anchors \[.*\] outputs \[.*\]; [0-9] inside at current" "$TMP/sr1.txt" \
  && grep -q "^read-only report: nothing was written; every suggestion is for a person to apply" "$TMP/sr1.txt" \
  && ok "style report text: each suggestion carries 'not applied' and its supporting numbers (current, d_needed, ranges), and the report says nothing was written" || no "suggestion text" "$(grep -n 'suggestion only' "$TMP/sr1.txt")"
[ "$(grep -c 'suggestion only, not applied' "$TMP/sr1.txt")" -eq "$(grep -cE '^ +(palette\.max_distance|tone\.tolerance)' "$TMP/sr1.txt")" ] && [ "$(jq '[.. | objects | select(has("applied")) | .applied] | all(. == false)' "$TMP/sr1.json")" = true ] \
  && ok "style report prints every suggestion as not applied (text) and applied false (--json)" || no "applied flags" "$(grep -n 'suggestion' "$TMP/sr1.txt" | head)"
# a group without approved outputs: null suggestions with a reason
[ "$(SRJ "$DG | [.families.ui] | map(.suggestions | map_values([.value, (.reason | type), .applied]))")" = '[{"palette.max_distance":[null,"string",false],"tone.tolerance":[null,"string",false]}]' ] \
  && [ "$(SRJ "$DG | .families.ui.suggestions | map(.reason) | unique")" = '["no approved output with opaque pixels"]' ] \
  && grep -q "^    palette.max_distance: no suggestion (no approved output with opaque pixels) (suggestion only, not applied): current 48; min_share 0.6; 0 approved output(s)" "$TMP/sr1.txt" \
  && ok "style report: a family without approved outputs (ui) gets null suggestions with the reason, printed as 'no suggestion'" || no "null suggestions" "$(SRJ "$DG | .families.ui.suggestions")"
# White against a black-only palette requires distance 442, outside the permitted range.
SRX="$TMP/style-report-extreme"; cp -r "$SR" "$SRX"
jq '.palette.colors = [{"hex":"#000000"}] | .palette.min_share = 1' "$SRX/assetgen/styles/demo-game.json" > "$TMP/srx-style.json" && cp "$TMP/srx-style.json" "$SRX/assetgen/styles/demo-game.json"
python3 -B - "$ROOT" "$SRX/assetgen/runs/r-props-1/outputs/ok.png" <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png
with open(sys.argv[2], "wb") as f:
    f.write(png.encode(1, 1, bytes((255, 255, 255, 255))))
EOF
AG style report --authoring "$SRX" --style demo-game --json > "$TMP/srx.json" 2> "$TMP/sr.err"; rc=$?
AG style report --authoring "$SRX" --style demo-game > "$TMP/srx.txt" 2>> "$TMP/sr.err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] \
  && jq -e '.styles[0].total.suggestions["palette.max_distance"] | .value == null and .data.d_needed.max == 442 and (.reason | contains("no permitted max_distance (0..441) makes every approved output pass") and contains("442"))' "$TMP/srx.json" >/dev/null \
  && grep -Fq 'palette.max_distance: no suggestion (no permitted max_distance (0..441) makes every approved output pass; largest needed distance is 442)' "$TMP/srx.txt" \
  && ok "style report refuses an impossible palette threshold in JSON and text" || no "extreme palette report rc=$rc/$rc2" "$(cat "$TMP/sr.err" "$TMP/srx.json")"
jq '.palette.min_share = 0' "$SRX/assetgen/styles/demo-game.json" > "$TMP/srx-style.json" && cp "$TMP/srx-style.json" "$SRX/assetgen/styles/demo-game.json"
AG style report --authoring "$SRX" --style demo-game --json > "$TMP/srx-zero.json" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 0 ] && jq -e '.styles[0].total.suggestions["palette.max_distance"] | .value == 0 and .data.d_needed.max == 0 and .reason == null' "$TMP/srx-zero.json" >/dev/null \
  && ok "style report suggests distance zero when min_share is zero" || no "zero min_share rc=$rc" "$(cat "$TMP/sr.err" "$TMP/srx-zero.json")"

# Seven of ten pixels meet min_share 0.7 at distance 6; floating-point multiplication must not select the eighth.
python3 -B - "$ROOT" > "$TMP/sr-float" 2>&1 <<'EOF'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import png, style_report
pixels = bytes(channel for red in range(10) for channel in (red, 0, 0, 255))
img = png.Image(10, 1, pixels, True, "fixture")
record = style_report._output_record(img, ({}, [(0, 0, 0)], 0, 0.7))
assert record["d_needed"] == 6, record
EOF
rc=$?
[ $rc -eq 0 ] && ok "style report selects the seventh pixel for min_share 0.7 of ten" \
  || no "style report floating-point rank rc=$rc" "$(cat "$TMP/sr-float")"

python3 -B - "$ROOT" > "$TMP/sr-qa-regressions" 2>&1 <<'EOF'
import os, random, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "assetgen"))
import consistency, png, style_report

def image(colors):
    return png.Image(len(colors), 1, bytes(c for rgb in colors for c in (*rgb, 255)), True, "fixture")

def palette_case(img, colors, share):
    style = {"palette": {"colors": [{"hex": "#%02x%02x%02x" % rgb} for rgb in colors],
                         "max_distance": 0, "min_share": share}}
    config = consistency.palette_config(style)[1]
    record = style_report._output_record(img, config)
    suggestion = style_report._suggest_palette([record], config, None)
    d = record["d_needed"]
    if d <= 441:
        assert suggestion["value"] == d
        style["palette"]["max_distance"] = d
        assert consistency.check_palette(img, style)[0] == "PASS", (d, share)
        if d:
            style["palette"]["max_distance"] = d - 1
            assert consistency.check_palette(img, style)[0] != "PASS", (d, share)
    else:
        assert suggestion["value"] is None and "no permitted max_distance" in suggestion["reason"]
    return d

def tone_case(cases):
    def record(img):
        lum, sat = consistency.tone_stats(img)
        return {"luminance": lum, "saturation": sat}
    suggestion = style_report._suggest_tone([dict(record(img), run=str(n), selected_anchors=[consistency.tone_stats(a) for a in anchors]) for n, (anchors, img) in enumerate(cases)], 0.05)
    tol = suggestion["value"]
    assert tol is not None, suggestion
    def passes(t):
        return all(consistency.check_tone(img, {"tone": {"tolerance": t}}, anchors)[0] == "PASS" for anchors, img in cases)
    assert passes(tol), tol
    assert tol == 0 or not passes(round(tol - 0.01, 2)), tol
    return tol

assert palette_case(image([(r, 0, 0) for r in range(10)]), [(0, 0, 0)], 0.70000000001) == 7
assert tone_case([([image([(39, 39, 39)])], image([(90, 90, 90)]))]) == 0.21
rng = random.Random(7941)
shares = [0, 0.1, 0.3, 0.7, 0.70000000001, 1 / 3, 1]
def color():
    return tuple(rng.randrange(256) for _ in range(3))
for i in range(200):
    palette_case(image([color() for _ in range(rng.randint(1, 20))]),
                 [color() for _ in range(rng.randint(1, 4))], shares[i % len(shares)])
    tone_case([([image([color() for _ in range(rng.randint(1, 5))]) for _ in range(rng.randint(1, 3))],
                image([color() for _ in range(rng.randint(1, 5))])) for _ in range(rng.randint(1, 3))])
EOF
rc=$?
[ $rc -eq 0 ] && ok "style report suggestions pass palette and tone QA at the smallest permitted thresholds in 202 regression cases" \
  || no "style report QA threshold regressions rc=$rc" "$(cat "$TMP/sr-qa-regressions")"

# a draft style with no palette, no anchors and no runs: still exit 0, suggestions null with reasons, nothing written
SRN="$TMP/style-report-bare"; mkdir -p "$SRN"
AG style init --id demo-game --extends pixel-art --authoring "$SRN" > "$TMP/sr.out" 2> "$TMP/sr.err" || no "style report bare setup: style init" "$(cat "$TMP/sr.err")"
sig_n=$(sr_sig "$SRN")
AG style report --authoring "$SRN" --style demo-game --json > "$TMP/srn.json" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 0 ] && [ "$(jq -c '.styles[0].total.suggestions | map_values([.value, .reason != null])' "$TMP/srn.json")" = '{"palette.max_distance":[null,true],"tone.tolerance":[null,true]}' ] \
  && [ "$(jq -c '.styles[0].total | [.runs.total, .approved_outputs, .rejections.total, .qa]' "$TMP/srn.json")" = '[0,0,0,{}]' ] && [ "$(sr_sig "$SRN")" = "$sig_n" ] \
  && ok "style report of a fresh draft style (no palette, no anchors, no runs) exits 0 with null suggestions and a reason, and writes nothing" || no "bare style report rc=$rc" "$(cat "$TMP/sr.err"; jq -c '.styles[0].total.suggestions' "$TMP/srn.json")"
# an authoring dir with nothing to report: exit 0 and still nothing written
SRE="$TMP/style-report-empty"; mkdir -p "$SRE"; sig_e=$(sr_sig "$SRE")
AG style report --authoring "$SRE" > "$TMP/sre.txt" 2> "$TMP/sr.err"; rc=$?; AG style report --authoring "$SRE" --json > "$TMP/sre.json" 2>> "$TMP/sr.err"; rc2=$?
[ $rc -eq 0 ] && [ $rc2 -eq 0 ] && grep -q "no style data to report" "$TMP/sre.txt" && [ "$(jq -c '.styles' "$TMP/sre.json")" = '[]' ] && [ "$(sr_sig "$SRE")" = "$sig_e" ] \
  && ok "style report of an authoring dir with no style data exits 0 (also --json) and creates nothing" || no "empty authoring rc=$rc/$rc2" "$(cat "$TMP/sr.err" "$TMP/sre.txt")"
# exit codes: a malformed --style is usage (2), a style no data knows is a refusal (1); neither writes
AG style report --authoring "$SR" --style "Bad_Id" > "$TMP/sr.out" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 2 ] && grep -q "lowercase id" "$TMP/sr.err" && ok "style report with a malformed --style exits 2" || no "malformed --style rc=$rc" "$(cat "$TMP/sr.err")"
AG style report --authoring "$SR" --style no-such-style > "$TMP/sr.out" 2> "$TMP/sr.err"; rc=$?
[ $rc -eq 1 ] && grep -q "no game style file" "$TMP/sr.err" && [ ! -s "$TMP/sr.out" ] && [ "$(sr_sig "$SR")" = "$sig_sr" ] \
  && ok "style report of an unknown style exits 1 with a message and prints no report" || no "unknown style rc=$rc" "$(cat "$TMP/sr.err" "$TMP/sr.out")"
[ "$(sr_sig "$SR")" = "$sig_sr" ] && [ "$(tpl_hash)" = "$tpl0" ] && [ -z "$(git -C "$ROOT" status --porcelain -- templates/assetgen)" ] \
  && ok "style report left the authoring fixture and templates/assetgen unchanged after every case" || no "fixture or templates/assetgen changed by report" "$(git -C "$ROOT" status --porcelain -- templates/assetgen)"

echo "-- consistency signals self-test (tests/fixtures/assetgen/consistency_selftest.py)"
python3 -B "$ROOT/tests/fixtures/assetgen/consistency_selftest.py" > "$TMP/cs" 2>&1; rc=$?
n_ok=$(grep -c '^ok ' "$TMP/cs"); n_no=$(grep -c '^not ok ' "$TMP/cs")
[ $rc -eq 0 ] && [ "$n_ok" -gt 0 ] && [ "$n_no" -eq 0 ] && ok "consistency self-test: $n_ok cases passed" || no "consistency self-test rc=$rc ($n_ok ok, $n_no not ok)" "$(grep -v '^ok ' "$TMP/cs")"

for st_ in imaging_selftest style_selftest pixelgrid_selftest slicer_selftest; do
  echo "-- $st_ (tests/fixtures/assetgen/$st_.py)"
  python3 -B "$ROOT/tests/fixtures/assetgen/$st_.py" > "$TMP/cs" 2>&1; rc=$?
  n_ok=$(grep -c '^ok ' "$TMP/cs"); n_no=$(grep -c '^not ok ' "$TMP/cs")
  [ $rc -eq 0 ] && [ "$n_ok" -gt 0 ] && [ "$n_no" -eq 0 ] && ok "$st_: $n_ok cases passed" || no "$st_ rc=$rc ($n_ok ok, $n_no not ok)" "$(grep -v '^ok ' "$TMP/cs")"
done

echo "-- no endpoints or credentials in core data or engine"
hits=$(grep -rnIE '://|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|localhost:[0-9]|Bearer [A-Za-z0-9]|sk-[A-Za-z0-9]{12}|"(api[_-]?key|authorization|base_url)" *:' \
  "$ROOT/templates/assetgen" "$ROOT/scripts/assetgen" 2>/dev/null)
[ -z "$hits" ] && ok "no URL, IP address, host:port or credential in templates/assetgen or scripts/assetgen" || no "endpoint or credential found" "$hits"
for f in "$ROOT"/templates/assetgen/*/*.json "$ROOT"/scripts/assetgen/data/*.json; do
  jq -e '.schema | test("^rpg-factory\\.[a-z0-9-]+/1$")' "$f" >/dev/null || no "schema id missing: $f"
done
ok "every data file carries a versioned schema id"
[ -z "$(find "$ROOT/scripts/assetgen" -name '__pycache__')" ] && ok "no __pycache__ left by -B runs" || no "__pycache__ in scripts/assetgen"

echo "assetgen: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
