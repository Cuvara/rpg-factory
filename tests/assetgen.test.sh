#!/usr/bin/env bash
# asset-gen engine (scripts/assetgen/): list/show/resolve with core + game layers (override, extends, per-field
# source, param precedence), strict render per purpose against golden workflows (tests/fixtures/assetgen/golden/),
# lint errors and warnings, review-cmd output (prints, never runs Codex), PNG QA on fixture PNGs generated here
# (alpha, corners, seam, blank, size modes, stdlib decoder, NOT_AVAILABLE), manifest run.md (gen-run front matter),
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

echo "-- manifest (run.md, gen-run)"
d="$RUNS/iron-sword-icon-001"; mkrun iron-sword-icon-001 icon --style pixel-art; AG render --run "$d" >/dev/null
cp "$FX/icon-ok.png" "$d/outputs/iron-sword.png"; AG qa --run "$d" >/dev/null
printf '{"state": "PASS", "findings": [], "by": "codex"}\n' > "$d/review-prompt.json"
printf 'Review done.\n{"state": "FAIL", "findings": [{"rubric": 2, "severity": "major", "text": "off style"}], "by": "codex"}\n' > "$d/review-image.json"
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
