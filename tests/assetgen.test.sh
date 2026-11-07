#!/usr/bin/env bash
# asset-gen engine (scripts/assetgen/): list/show/resolve with core + game layers (override, extends, per-field
# source, param precedence, purpose constraints over style hints), strict render per purpose against golden workflows (tests/fixtures/assetgen/golden/),
# the prompt node (PrimitiveStringMultiline, review state in its title), workflow.ui.json (converted back to
# workflow.json by a stdlib UI->API converter), one filename_prefix (assetgen/<run-id>) in every run record,
# lint errors and warnings (blamed on the game file holding a bad value), review-cmd output (prints, never runs Codex; absolute paths from any cwd, true pixel sizes,
# the 2x2 tile preview of tileable purposes and --no-write), embed (workflow tEXt chunk in the outputs), publish
# (against an in-process fake ComfyUI: POST, HTTP error, connection refused), PNG QA on fixture PNGs generated here
# (alpha, corners, seam, blank, size modes incl. aspect + min area, orientation, area + min pixels, real 9router sizes, stdlib decoder incl. gray/RGB/palette tRNS, NOT_AVAILABLE), manifest run.md
# (gen-run front matter, review bindings, Claude's visual review, failed attempts in trace), the gen-run quality plugin (pass and fail cases: review files and their
# prompt/output/requirements binding, qa.json as the QA evidence; through artifact-quality and called directly),
# malformed purpose data and link indices (FAIL rows, no traceback), artifact-lint on
# manifest-produced run.md, the style lock data side (stylelock.py: project.json precedence, refusal and override,
# deprecated styles, anchor validity, deterministic reference selection, rejection relevance, drift; their lint rows),
# the style lock through the CLI (resolve --family/--style-override into spec.style_lock, render wiring of 0/1/3 anchors
# and image-edit as LoadImage + ImageBatch into reference_images, anchor copies, hashes bound only with style_lock,
# manifest, promote-anchor, reject, drift), style lock QA rows through qa (palette PASS/WARN/FAIL/NOT_AVAILABLE, tone vs
# the run's anchor copies, edges, canvas; older specs without rows) and the gen-run plugin's style-* row rule, the
# anchor-aware review-cmd (anchors after outputs in -i, anchor and rejection rubric items, binding style + anchors kept
# by read_verdict, direction rejections in the prompt review's Must avoid, older specs unchanged), review prompts listing
# the params render used (workflow.json) and leaving deterministic checks to QA, --run RUN-ID resolution, the short
# resolve summary and --verbose, the consistency signals self-test (tests/fixtures/assetgen/consistency_selftest.py),
# the e2e3 fixes (png-edge-fringe on a speckled low-alpha fringe, defringe and its record and refusals, dark/light
# composites in the image review, approve-record refusals and record, manifest keeping or resetting an approval, the
# proposed -> approved lifecycle, an uncommitted approval HUMAN_REQUIRED in gen-run-style, cross-family anchor
# warnings and anchor_family_fallback false, drift style-id-mismatch, 1322x1190 square tolerance and allow_swap, the
# embed stale chunk, the style-field lint WARN), the imaging and style engine self-tests (imaging_selftest.py,
# style_selftest.py), and no endpoints or credentials in templates/assetgen or scripts/assetgen.
# Usage: tests/assetgen.test.sh [--update-golden]   (standalone; temp authoring git repo; no network)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
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

# -- temp authoring repo with a game layer
AUTH="$TMP/game-authoring"; GL="$AUTH/assetgen"
mkdir -p "$GL/purposes" "$GL/styles" "$GL/templates" "$GL/runs"
cat > "$GL/purposes/icon.json" <<'EOF'
{"extends": "icon", "title": "RPG item icon", "params": {"quality": "medium"}, "qa": {"size": {"mode": "exact"}}}
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

echo "-- list / show"
AG list --json > "$TMP/l.json" 2>"$TMP/err"; rc=$?
n=$(jq '[.entries[] | select(.layer == "core")] | length' "$TMP/l.json")
[ $rc -eq 0 ] && [ "$n" = 15 ] && ok "core list: 7 purposes + 6 styles + 2 templates" || no "core list rc=$rc n=$n" "$(cat "$TMP/err")"
ids=$(jq -r '[.entries[] | select(.kind != "template") | .kind + ":" + .id] | sort | join(" ")' "$TMP/l.json")
[ "$ids" = "purpose:concept-2d purpose:icon purpose:image-edit purpose:ref-3d-turnaround purpose:sprite-2d purpose:texture-tileable purpose:ui-element style:anime-cel style:flat-ui style:low-poly style:pixel-art style:realistic-pbr style:stylized-painterly" ]   && ok "every core purpose and style id is listed" || no "ids: $ids"
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
AG resolve --purpose icon --style pixel-art --authoring "$AUTH" --json > "$TMP/r.json" 2>"$TMP/err"; rc=$?
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
AG resolve --purpose icon --style pixel-art --authoring "$BAD" >/dev/null 2>"$TMP/err"; rc=$?
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
for p in concept-2d sprite-2d icon ui-element texture-tileable ref-3d-turnaround image-edit; do
  mkrun "golden-$p-001" "$p" --style stylized-painterly || { no "resolve $p"; continue; }
  extra=(); [ "$p" = image-edit ] && extra=(--param reference_image=ref.png)
  out=$(AG render --run "$RUNS/golden-$p-001" "${extra[@]}" 2>&1); rc=$?
  wf="$RUNS/golden-$p-001/workflow.json"
  if $update_golden && [ $rc -eq 0 ]; then cp "$wf" "$GOLD/$p.json"; fi
  if [ $rc -eq 0 ] && [ -f "$GOLD/$p.json" ] && [ "$(jq -S . "$wf")" = "$(jq -S . "$GOLD/$p.json")" ] && ! grep -q '{{' "$wf"; then
    ok "render $p = golden (no placeholder left)"
  else no "render $p rc=$rc" "$out
$(diff <(jq -S . "$wf" 2>/dev/null) <(jq -S . "$GOLD/$p.json" 2>/dev/null))"; fi
done
AG review-cmd --phase prompt --run "$RUNS/golden-ref-3d-turnaround-001" --json | jq -r .stdin > "$TMP/rp.txt"
grep -qF "lighting: $(jq -r .constraints.lighting "$ROOT/templates/assetgen/purposes/ref-3d-turnaround.json")" "$TMP/rp.txt" \
  && ! grep -qF "$(jq -r .lighting "$ROOT/templates/assetgen/styles/stylized-painterly.json")" "$TMP/rp.txt" \
  && ok "prompt review: the reviewer judges against the purpose lighting, not the overridden style lighting" || no "review hints" "$(grep -n Hints "$TMP/rp.txt")"
w="$RUNS/golden-icon-001/workflow.json"
[ "$(jq -r '.["3"].inputs.value' "$w")" = "Test prompt for icon: one subject, centered." ] && [ "$(jq -c '.["2"].inputs.images' "$w")" = '["1",0]' ] \
  && [ "$(jq -r '.["1"].inputs.background' "$w")" = transparent ] && ok "icon workflow: prompt verbatim (trimmed), link kept, transparent background" || no "icon workflow content"
[ "$(jq -c '.["2"].inputs.reference_images' "$RUNS/golden-image-edit-001/workflow.json")/$(jq -r '.["1"].inputs.image' "$RUNS/golden-image-edit-001/workflow.json")" = '["1",0]/ref.png' ] \
  && ok "image-edit: LoadImage -> reference_images" || no "image-edit links"
AG lint "$w" "$RUNS/golden-image-edit-001/workflow.json" > "$TMP/o" 2>&1 && grep -q "2 PASS, 0 WARN, 0 FAIL" "$TMP/o" && ok "rendered workflows lint clean" || no "rendered lint" "$(cat "$TMP/o")"
AG render --run "$RUNS/golden-icon-001" --param size=1536x1024 --param quality=low >/dev/null && [ "$(jq -r '.["1"].inputs.size + " " + .["1"].inputs.quality' "$w")" = "1536x1024 low" ] \
  && ok "--param overrides purpose params" || no "--param override"
d="$RUNS/golden-image-edit-001"; rm -f "$d/workflow.json"
out=$(AG render --run "$d" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "param reference_image is required" <<<"$out" && [ ! -f "$d/workflow.json" ] && ok "missing required param: FAIL, nothing written" || no "missing required rc=$rc" "$out"
out=$(AG render --run "$d" --param reference_image=r.png --param size=999x999 --param tint=red --param prompt=x --param bare 2>&1); rc=$?
{ [ $rc -eq 1 ] && grep -q "param size: '999x999' is not one of" <<<"$out" && grep -q "param tint is not declared" <<<"$out" \
  && grep -q "the prompt comes from the prompt file only" <<<"$out" && grep -q "expected NAME=VALUE" <<<"$out"; } \
  && ok "render rejects bad enum, undeclared param, prompt override, malformed --param" || no "render errors rc=$rc" "$out"
: > "$d/prompt.md"; out=$(AG render --run "$d" --param reference_image=r.png 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "is empty" <<<"$out" && ok "empty prompt file: error" || no "empty prompt rc=$rc" "$out"
AG render --spec "$RUNS/golden-icon-001/spec.json" --prompt-file "$RUNS/golden-icon-001/prompt.md" --out "$TMP/wf.json" >/dev/null && [ -f "$TMP/wf.json" ] \
  && ok "render --spec/--prompt-file/--out" || no "render explicit paths"
printf 'Test prompt for image-edit: one subject, centered.
' > "$d/prompt.md"; AG render --run "$d" --param reference_image=ref.png >/dev/null
# item 1: the prompt is a visible PrimitiveStringMultiline node linked into NineRouterImage.user_prompt
for pw in "golden-icon-001 1 3" "golden-image-edit-001 2 4"; do
  set -- $pw; f="$RUNS/$1/workflow.json"
  [ "$(jq -c --arg n "$2" '.[$n].inputs.user_prompt' "$f")" = "[\"$3\",0]" ] \
    && [ "$(jq -r --arg n "$3" '.[$n].class_type + "|" + .[$n]._meta.title' "$f")" = "PrimitiveStringMultiline|Prompt (Claude, Codex review NOT_RUN)" ] \
    && [ "$(jq -r --arg n "$3" '.[$n].inputs.value' "$f")" = "$(sed 's/[[:space:]]*$//' "$RUNS/$1/prompt.md")" ] \
    && ok "$1: prompt node $3 (Text (Multiline), review state in the title) feeds node $2 user_prompt" || no "$1 prompt node" "$(jq -c . "$f")"
done
for t in image-generate image-edit; do
  jq -e '[.workflow[] | select(.class_type == "NineRouterImage") | .inputs.user_prompt | type] == ["array"]' "$ROOT/templates/assetgen/workflows/$t.json" >/dev/null \
    && ok "core template $t: no inline prompt, user_prompt is a link" || no "template $t user_prompt"
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
mkrun title-icon-001 icon --style stylized-painterly; td="$RUNS/title-icon-001"
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
jq '.["3"].inputs.value = "changed"' "$RUNS/golden-icon-001/workflow.json" > "$TMP/changed-wf.json"
python3 -B - "$ROOT" "$RUNS/golden-icon-001/spec.json" "$RUNS/golden-icon-001/workflow.json" "$TMP/changed-wf.json" > "$TMP/o" 2>&1 <<'EOF'
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
for p in concept-2d sprite-2d icon ui-element texture-tileable ref-3d-turnaround image-edit; do
  d="$RUNS/golden-$p-001"; [ "$p" = icon ] && AG render --run "$d" >/dev/null
  [ "$p" = image-edit ] && AG render --run "$d" --param reference_image=ref.png >/dev/null
  out=$(python3 -B "$TMP/ui2api.py" "$KN" "$d/workflow.ui.json" "$d/workflow.json" 2>&1)
  [ "$out" = ok ] && [ "$(jq -r '.extra.assetgen.run_id + "|" + (.version | tostring)' "$d/workflow.ui.json")" = "golden-$p-001|0.4" ] \
    && ok "workflow.ui.json $p: converts back to workflow.json; run id in extra" || no "ui workflow $p" "$out"
done
u="$RUNS/golden-image-edit-001/workflow.ui.json"
[ "$(jq -c '[.nodes[] | select(.type == "LoadImage") | .widgets_values][0]' "$u")" = '["ref.png","image"]' ] \
  && [ "$(jq -c '[.nodes[] | select(.type == "NineRouterImage") | .inputs[] | {name, link: (.link != null), widget: (.widget.name // null)}]' "$u")" = \
       '[{"name":"user_prompt","link":true,"widget":"user_prompt"},{"name":"reference_images","link":true,"widget":null}]' ] \
  && [ "$(jq -r '[.nodes[] | select(.type == "PrimitiveStringMultiline") | .title][0]' "$u")" = "Prompt (Claude, Codex review NOT_RUN)" ] \
  && ok "workflow.ui.json image-edit: LoadImage upload widget, linked prompt widget socket, prompt node title" || no "ui image-edit" "$(jq -c .nodes "$u")"
[ "$(jq -c '[.nodes[] | {id, x: .pos[0]}] | sort_by(.id)' "$RUNS/golden-icon-001/workflow.ui.json")" = '[{"id":1,"x":500},{"id":2,"x":940},{"id":3,"x":60}]' ] \
  && ok "workflow.ui.json layout: one column per link depth (prompt -> image -> save)" || no "ui layout" "$(jq -c '[.nodes[] | {id, pos}]' "$RUNS/golden-icon-001/workflow.ui.json")"
[ -f "$TMP/wf.ui.json" ] && [ "$(jq -r '.extra.assetgen.run_id' "$TMP/wf.ui.json")" = null ] \
  && [ "$(python3 -B "$TMP/ui2api.py" "$KN" "$TMP/wf.ui.json" "$TMP/wf.json" 2>&1)" = ok ] \
  && ok "render --out X.json also writes X.ui.json (no run id)" || no "render --out ui file"

echo "-- filename_prefix: one value in spec.json, workflow.json, review prompts and run.md"
mkrun prefix-icon-001 icon --style stylized-painterly; pd="$RUNS/prefix-icon-001"; want=assetgen/prefix-icon-001
AG render --run "$pd" >/dev/null 2>"$TMP/err" && AG manifest --run "$pd" >/dev/null 2>>"$TMP/err"
got="$(jq -r .params.filename_prefix "$pd/spec.json")|$(jq -r '[.[] | select(.class_type == "SaveImage")][0].inputs.filename_prefix' "$pd/workflow.json")"
got="$got|$(sed -n '/^---json$/,/^---$/p' "$pd/run.md" | sed '1d;$d' | jq -r .spec.params.filename_prefix)"
AG review-cmd --phase prompt --run "$pd" --json | jq -r .stdin > "$TMP/rp.txt"
[ "$got" = "$want|$want|$want" ] && grep -q "filename_prefix=$want" "$TMP/rp.txt" && ! grep -q 'assetgen/run\b' "$pd/workflow.json" "$pd/workflow.ui.json" "$pd/run.md" "$TMP/rp.txt" \
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
lst() { jq -r --arg p "$1" '[.results[] | select(.path == $p) | .state] | join(",")' "$TMP/o"; }
[ "$(lst core:templates/assetgen/purposes/icon.json)/$(lst game:assetgen/purposes/icon.json)" = "PASS/FAIL" ] \
  && [ "$(lst core:templates/assetgen/workflows/image-generate.json)" = PASS ] \
  && ok "lint blames the game file holding the bad values, not the unchanged core file it extends" \
  || no "lint blame: core $(lst core:templates/assetgen/purposes/icon.json), game $(lst game:assetgen/purposes/icon.json)" "$(jq -c '.results[] | select(.path | test("icon|image-generate"))' "$TMP/o")"
got=$(AG lint "$LA/assetgen/purposes/icon.json" --authoring "$LA" 2>&1)
{ grep -q "handoff_domain 'audio' is not a registry domain" <<<"$got" && grep -q "qa.size.mode must be one of" <<<"$got" \
  && grep -q "qa.alpha must be one of" <<<"$got" && grep -q "prompt_rubric must be a non-empty list" <<<"$got"; } \
  && ok "lint purpose: domain, qa modes, rubric (merged game extension)" || no "purpose lint" "$got"
jq '.["1"].inputs.user_prompt = "{{prompt}}"' "$RUNS/golden-icon-001/workflow.json" > "$TMP/left.json"
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
mal mal-sqtol '{"extends": "icon", "qa": {"size": {"square_tolerance": 1.5}}}'
expect_mal() { # expect_mal ID TEXT LABEL
  local out rc; out=$(AG lint "$LA/assetgen/purposes/$1.json" --authoring "$LA" --json 2>"$TMP/err"); rc=$?
  local got; got=$(jq -r '.results[0] | .state + " " + (.reasons | join("; "))' <<<"$out" 2>/dev/null)
  case "$rc/$got" in "1/FAIL "*"$2"*) grep -q Traceback "$TMP/err" && no "lint $3: traceback" "$(cat "$TMP/err")" || ok "lint $3" ;;
    *) no "lint $3 rc=$rc" "$got
$(cat "$TMP/err")" ;; esac
}
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
AG lint --authoring "$AUTH" > "$TMP/o" 2>&1 && grep -q "17 PASS, 3 WARN, 0 FAIL" "$TMP/o" && grep -q "^WARN game:assetgen/project.json: no assetgen/project.json" "$TMP/o" \
  && grep -q "^WARN game:assetgen/styles/pixel-art.json: active game style has no structured style fields (palette.colors, tone, canvas, outline.edge_darkness)" "$TMP/o" \
  && grep -q "^WARN game:assetgen/styles/rpg-dark.json: active game style has no structured style fields" "$TMP/o" \
  && ok "core + game layer lint: 0 FAIL; WARN no assetgen/project.json and (e2e3 item 9) two active game styles without structured style fields" || no "full lint" "$(tail -5 "$TMP/o")"

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
  mkrun "$name" "$p" --style stylized-painterly || return 1
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
ed="$RUNS/embed-icon-001"; mkrun embed-icon-001 icon --style stylized-painterly && AG render --run "$ed" >/dev/null
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
fr="$RUNS/fringe-icon-001"; mkrun fringe-icon-001 icon --style stylized-painterly && AG render --run "$fr" >/dev/null
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
[ $rc -eq 1 ] && grep -qF "qa.json already bind(s) the current outputs" "$TMP/o" && grep -qF "or pass --force and then re-run qa" "$TMP/o" \
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
# several outputs: composites per output with alpha (review/composite-<stem>-<bg>.png); an opaque output gets none and defringe skips it
f2="$RUNS/fringe-two-001"; mkrun fringe-two-001 icon --style stylized-painterly && AG render --run "$f2" >/dev/null
cp "$FX/fringe.png" "$f2/outputs/a.png"; cp "$FX/icon-opaque.png" "$f2/outputs/b.png"; ob=$(sha256sum "$f2/outputs/b.png" | cut -d' ' -f1)
AG defringe --run "$f2" > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q "^skipped outputs/b.png: no transparent pixels" "$TMP/o" && grep -q "1 defringed, 1 skipped, 0 FAIL" "$TMP/o" \
  && [ "$(sha256sum "$f2/outputs/b.png" | cut -d' ' -f1)" = "$ob" ] && [ ! -e "$f2/outputs-raw/b.png" ] \
  && ok "defringe skips an output without transparent pixels (untouched, no raw copy)" || no "defringe skip rc=$rc" "$(cat "$TMP/o")"
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
d="$RUNS/iron-sword-icon-001"; mkrun iron-sword-icon-001 icon --style pixel-art; AG render --run "$d" >/dev/null
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
good="$RUNS/qp-icon-001"; mkrun qp-icon-001 sprite-2d --style stylized-painterly --authoring "$AUTH"
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
edit="$RUNS/qp-edit-001"; mkrun qp-edit-001 image-edit --style stylized-painterly --authoring "$AUTH"
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
case_ qp-same-001 gen-run-prompt-review FAIL 'SAME_MODEL:claude-sonnet' "unmarked review by the author's model family: FAIL, names the explicit marker"
case_ qp-fallback-001 gen-run-prompt-review WARN 'same-model fallback' "explicit SAME_MODEL:<model> fallback: WARN, never PASS"
case_ qp-badmark-001 gen-run-prompt-review FAIL 'is not the prompt author' "SAME_MODEL marker on another model's review: FAIL"
case_ qp-tamper-001 gen-run-outputs FAIL 'sha256 on disk differs' "output bytes changed after the record: FAIL"
case_ qp-extra-001 gen-run-outputs FAIL 'outputs/second.png is not recorded' "unrecorded outputs/*.png: FAIL"
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
case_ qp-noclaude-001 gen-run-claude-review WARN 'review-image-claude.json is missing' "no Claude visual review file: WARN"
[ "$(st AGEN-qp-noclaude-001 gen-run-image-review)" = PASS ] && ok "a missing Claude review leaves the Codex image review PASS" || no "noclaude image review: $(st AGEN-qp-noclaude-001 gen-run-image-review)"
case_ qp-claudeonly-001 gen-run-image-review FAIL 'review-image.json is missing' "a Claude PASS never replaces the missing Codex image review: FAIL"
[ "$(st AGEN-qp-claudeonly-001 gen-run-claude-review)" = PASS ] && ok "claude-only run: the Claude review itself grades PASS" || no "claudeonly claude review: $(st AGEN-qp-claudeonly-001 gen-run-claude-review)"
case_ qp-claudefail-001 gen-run-claude-review FAIL "Claude's visual review is FAIL (1 finding(s))" "Claude's own review FAIL on a proposed run: FAIL"
case_ qp-claudediff-001 gen-run-claude-review FAIL 'differs from review-image-claude.json (file: FAIL' "review-image-claude.json contradicting run.md: FAIL"
case_ qp-claudestale-001 gen-run-claude-review WARN 'not bound to the current prompt' "unbound Claude review: WARN"
case_ qp-claudeby-001 gen-run-claude-review WARN 'is by codex, not claude' "review-image-claude.json by another model: WARN"
case_ qp-tool-001 gen-run-provenance FAIL 'provenance.tool must be comfyui' "provenance tool other than comfyui: FAIL"
case_ qp-ref-001 gen-run-refs FAIL "style 'no-such-style' does not resolve" "unresolvable style ref: FAIL"
case_ qp-drift-001 gen-run-refs WARN 'changed since the run' "template content changed since the run: WARN (the record keeps what was used)"
case_ qp-prompt-001 gen-run-refs FAIL 'prompt.md differs' "prompt.md edited after the record: FAIL"
[ "$(st AGEN-somewhere-else-001 gen-run-location)" = FAIL ] && why AGEN-somewhere-else-001 gen-run-location | grep -qF 'id must be AGEN-qp-where-001' \
  && ok "id that does not match the run directory: FAIL" || no "location: $(why AGEN-somewhere-else-001 gen-run-location)"
case_ qp-escape-001 gen-run-outputs FAIL 'not a path inside the run directory' "output path escaping the run directory: FAIL"
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
core_p = {p: layers.load("purpose", p)["data"] for p in ("icon", "sprite-2d", "concept-2d", "ui-element", "texture-tileable", "ref-3d-turnaround", "image-edit")}
check(all(isinstance(d.get("dimensions"), list) and d.get("max_references") == 3 for d in core_p.values())
      and core_p["icon"]["default_family"] == "props" and core_p["sprite-2d"]["default_family"] == "characters"
      and "default_family" not in core_p["image-edit"], "core purposes declare dimensions, max_references and default_family (none for image-edit)")
check(all(layers.load("style", s)["data"].get("version") == 1 and layers.load("style", s)["data"].get("status") == "active"
          for s in ("anime-cel", "flat-ui", "low-poly", "pixel-art", "realistic-pbr", "stylized-painterly")), "core styles are version 1, active")

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
slrun sl-icon-001 icon || no "resolve icon in the style lock repo" "$(cat "$TMP/err")"
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
slrun sl-one-001 icon-one && [ "$(lk '[.style_lock.max_references, (.style_lock.references | length)] | join(",")' sl-one-001)" = "1,1" ] \
  && [ "$(lk '.style_lock.references[0].anchor_id' sl-one-001)" = b-strong ] && ok "resolve: purpose max_references 1 caps the selection" \
  || no "resolve cap" "$(lk .style_lock sl-one-001)"
slrun sl-pixel-001 icon --style pixel-art && [ "$(lk '.style.id + "|" + (.style_lock.references | length | tostring) + "|" + (.style_lock.override | tostring)' sl-pixel-001)" = "pixel-art|0|null" ] \
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
slrun sl-edit-001 image-edit && AG render --run "$SR/sl-edit-001" --param reference_image=ref.png >/dev/null 2>"$TMP/err"
de="$SR/sl-edit-001"
[ "$(wiring "$de/workflow.json")" = "ref.png>anchor-a-canon.png>anchor-d-chars.png>anchor-b-strong.png" ] \
  && [ "$(jq -c '[.["8"].inputs.image1, .["2"].inputs.reference_images]' "$de/workflow.json")" = '[["1",0],["10",0]]' ] \
  && ok "render image-edit: its own reference stays first, anchors follow (family none: same style, overlap order)" \
  || no "render image-edit wiring" "$(cat "$TMP/err"; jq -c . "$de/workflow.json")"
AG render --spec "$d/spec.json" --prompt-file "$d/prompt.md" --out "$TMP/sl-wf.json" >/dev/null 2>&1
[ "$(wiring "$TMP/sl-wf.json")" = "anchor-b-strong.png>anchor-a-canon.png>anchor-c-supp.png" ] && [ -f "$TMP/sl-wf.ui.json" ] \
  && ok "render --spec wires the same anchors (no copy outside a run)" || no "render --spec wiring" "$(jq -c . "$TMP/sl-wf.json")"
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

echo "-- consistency signals self-test (tests/fixtures/assetgen/consistency_selftest.py)"
python3 -B "$ROOT/tests/fixtures/assetgen/consistency_selftest.py" > "$TMP/cs" 2>&1; rc=$?
n_ok=$(grep -c '^ok ' "$TMP/cs"); n_no=$(grep -c '^not ok ' "$TMP/cs")
[ $rc -eq 0 ] && [ "$n_ok" -gt 0 ] && [ "$n_no" -eq 0 ] && ok "consistency self-test: $n_ok cases passed" || no "consistency self-test rc=$rc ($n_ok ok, $n_no not ok)" "$(grep -v '^ok ' "$TMP/cs")"

for st_ in imaging_selftest style_selftest; do
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
