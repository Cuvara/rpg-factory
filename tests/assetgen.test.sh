#!/usr/bin/env bash
# asset-gen engine (scripts/assetgen/): list/show/resolve with core + game layers (override, extends, per-field
# source, param precedence), strict render per purpose against golden workflows (tests/fixtures/assetgen/golden/),
# lint errors and warnings, review-cmd output (prints, never runs Codex), PNG QA on fixture PNGs generated here
# (alpha, corners, seam, blank, size modes, stdlib decoder incl. gray/RGB/palette tRNS, NOT_AVAILABLE), manifest run.md
# (gen-run front matter, review bindings), the gen-run quality plugin (pass and fail cases: review files and their
# prompt/output/requirements binding, qa.json as the QA evidence; through artifact-quality and called directly),
# malformed purpose data and link indices (FAIL rows, no traceback), artifact-lint on
# manifest-produced run.md,
# and no endpoints or credentials in templates/assetgen or scripts/assetgen.
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
w="$RUNS/golden-icon-001/workflow.json"
[ "$(jq -r '.["1"].inputs.user_prompt' "$w")" = "Test prompt for icon: one subject, centered." ] && [ "$(jq -c '.["2"].inputs.images' "$w")" = '["1",0]' ] \
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
AG lint "$LA/assetgen/templates/unsupported-model.json" --authoring "$LA" >/dev/null 2>&1 && ok "warnings alone exit 0" || no "warn exit code"
AG lint "$LA/assetgen/templates/unknown-node.json" --authoring "$LA" >/dev/null 2>&1; [ $? -eq 1 ] && ok "a FAIL exits 1" || no "fail exit code"
echo '{"extends": "icon", "handoff_domain": "audio", "qa": {"size": {"mode": "huge"}, "alpha": "maybe"}, "prompt_rubric": []}' > "$LA/assetgen/purposes/icon.json"
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
AG lint --authoring "$AUTH" > "$TMP/o" 2>&1 && grep -q "19 PASS, 0 WARN, 0 FAIL" "$TMP/o" && ok "core + game layer lint clean (19 files)" || no "full lint" "$(tail -5 "$TMP/o")"

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
save("icon-ok.png", 256, 256, disc(256, 256, (0, 0, 0, 0)))
save("icon-opaque.png", 256, 256, disc(256, 256, (30, 30, 30, 255)), alpha=False)
save("icon-wide.png", 384, 256, disc(384, 256, (0, 0, 0, 0)))
save("empty.png", 256, 256, lambda x, y: (0, 0, 0, 0))
save("flat.png", 256, 256, lambda x, y: (90, 90, 90, 255), alpha=False)
def wave(x, y):
    v = int(128 + 60 * math.sin(2 * math.pi * x / 256) * math.cos(2 * math.pi * y / 256))
    return (v, v // 2 + 40, 255 - v, 255)
save("tile-ok.png", 256, 256, wave, alpha=False)
save("tile-bad.png", 256, 256, lambda x, y: (x, x, 128, 255), alpha=False)
row = bytes(c for x in range(1536) for c in (x % 256, (x // 6) % 256, 100))
open(os.path.join(out, "big.png"), "wb").write(png.encode_raw(1536, 1024, 8, 2, [row] * 1024))
row16 = bytes(b for x in range(256) for b in (x, 0, 255 - x, 0, 60, 0))
open(os.path.join(out, "deep16.png"), "wb").write(png.encode_raw(256, 256, 16, 2, [row16] * 256))
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
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && ok "concept-2d: 1536x1024 passes size mode min 1024x1024 (gateway size drift)" || no "concept big rc=$rc" "$(jq -c .results "$TMP/q.json")"
qarun qa-icon-big-001 icon big.png
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && ok "icon: 1536x1024 returned for a square request fails aspect" || no "icon big rc=$rc $(st png-size)"
qarun qa-edit-any-001 image-edit icon-wide.png
[ $rc -eq 0 ] && [ "$(st png-size)" = PASS ] && ok "image-edit: size mode any" || no "edit any rc=$rc $(st png-size)"
mkrun qa-exact-001 icon --style pixel-art --authoring "$AUTH"; cp "$FX/icon-ok.png" "$RUNS/qa-exact-001/outputs/"
AG qa --run "$RUNS/qa-exact-001" --json > "$TMP/q.json"; rc=$?
[ $rc -eq 1 ] && [ "$(st png-size)" = FAIL ] && jq -r '.results[] | select(.check == "png-size") | .reasons[0]' "$TMP/q.json" | grep -q "expected exact 1024x1024" \
  && ok "game override qa.size.mode exact: 256x256 fails exact 1024x1024" || no "exact rc=$rc $(st png-size)"
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
rows = [bytes(0 if (x - 128) ** 2 + (y - 128) ** 2 > 90 ** 2 else 40 + (x + y) % 200 for x in range(256)) for y in range(256)]
open(os.path.join(out, "trns-icon.png"), "wb").write(png.encode_raw(256, 256, 8, 0, rows, extra=[(b"tRNS", struct.pack(">H", 0))]))
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
assert img["user_prompt"] == open(os.path.join(run, "prompt.md"), encoding="utf-8").read().strip() and "size" in img and "quality" in img and gen["references"] == {}, gen
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
mkdir -p "$RUNS/Bad_Name"; cp "$d/spec.json" "$d/prompt.md" "$RUNS/Bad_Name/"
AG manifest --run "$RUNS/Bad_Name" >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 1 ] && grep -q "must be <slug>-NNN" "$TMP/err" && ok "run dir name must be <slug>-NNN" || no "bad run name rc=$rc"

echo "-- quality plugin (scripts/checks/domains/assetgen.py) and artifact-lint on manifest-produced run.md"
good="$RUNS/qp-icon-001"; mkrun qp-icon-001 sprite-2d --style stylized-painterly --authoring "$AUTH"
AG render --run "$good" >/dev/null && cp "$FX/icon-ok.png" "$good/outputs/qp-icon.png" && AG qa --run "$good" >/dev/null \
  || no "good run: render/qa did not PASS" "$(jq -c .results "$good/qa.json" 2>/dev/null)"
bound "$good" prompt PASS codex > "$good/review-prompt.json"; bound "$good" image PASS codex > "$good/review-image.json"
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
variant qp-rsize-001; AG render --run "$RUNS/qp-rsize-001" --param size=1536x1024 >/dev/null
AG qa --run "$RUNS/qp-rsize-001" >/dev/null; AG manifest --run "$RUNS/qp-rsize-001" >/dev/null
variant qp-wfprompt-001; jq '(.[] | select(.class_type == "NineRouterImage") | .inputs.user_prompt) = "Another prompt sent to the node."'   "$RUNS/qp-wfprompt-001/workflow.json" > "$TMP/wf" && mv "$TMP/wf" "$RUNS/qp-wfprompt-001/workflow.json"; AG manifest --run "$RUNS/qp-wfprompt-001" >/dev/null
variant qp-rqual-001; AG render --run "$RUNS/qp-rqual-001" --param quality=low >/dev/null
AG qa --run "$RUNS/qp-rqual-001" >/dev/null; AG manifest --run "$RUNS/qp-rqual-001" >/dev/null
AG manifest --run "$RUNS/qa-malformed-001" >/dev/null
# image-edit: the reference image is bound by name and content (references/<name> in the run directory)
edit="$RUNS/qp-edit-001"; mkrun qp-edit-001 image-edit --style stylized-painterly --authoring "$AUTH"
mkdir -p "$edit/references"; cp "$FX/icon-ok.png" "$edit/references/ref-a.png"
AG render --run "$edit" --param reference_image=ref-a.png >/dev/null && cp "$FX/icon-ok.png" "$edit/outputs/edit.png" && AG qa --run "$edit" >/dev/null   || no "image-edit run: render/qa did not PASS" "$(jq -c .results "$edit/qa.json" 2>/dev/null)"
bound "$edit" prompt PASS codex > "$edit/review-prompt.json"; bound "$edit" image PASS codex > "$edit/review-image.json"
AG manifest --run "$edit" >/dev/null
evariant() { local d="$RUNS/$1"; rm -rf "$d"; cp -R "$edit" "$d"; rm -f "$d/run.md"; }
evariant qp-eswap-001; cp "$FX/icon-opaque.png" "$RUNS/qp-eswap-001/references/ref-b.png"
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
plugin_checks="gen-run-location gen-run-prompt-review gen-run-image-review gen-run-outputs gen-run-qa gen-run-provenance gen-run-refs"
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
[ "$(st AGEN-qp-rsize-001 gen-run-prompt-review)" = PASS ] && ok "render --param size leaves the prompt review bound (the prompt phase has no size)" \
  || no "rsize prompt review: $(st AGEN-qp-rsize-001 gen-run-prompt-review)" "$(why AGEN-qp-rsize-001 gen-run-prompt-review)"
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
