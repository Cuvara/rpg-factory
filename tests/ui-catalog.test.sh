#!/usr/bin/env bash
# UI component catalog and selection (scripts/ui/ui_catalog.py, ui_select.py) on a mini UIToolkit git
# fixture built from tests/fixtures/ui-catalog/ (tags v0.7.2 and v0.8.0) and a client manifest pin.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
CAT="$ROOT/scripts/ui/ui_catalog.py"; SEL="$ROOT/scripts/ui/ui_select.py"; FIX="$ROOT/tests/fixtures/ui-catalog"
G=(-c user.email=t@t -c user.name=t -c commit.gpgsign=false -c tag.gpgsign=false)

# -- fixture workspace: UIToolkit git repo (v0.7.2, then v0.8.0 on top), client pinned to v0.7.2
WS="$TMP/ws"; U="$WS/UIToolkit"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$WS/rpg-mmo-server/backend" "$C/ProjectSettings" "$C/Packages" "$U"
touch "$WS/rpg-mmo-server/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt"
pin() { printf '{\n  "dependencies": {\n    "com.cuvara.uitoolkit": "%s"\n  }\n}\n' "$1" > "$C/Packages/manifest.json"; }
pin "https://github.com/Cuvara/UIToolkit.git#v0.7.2"
git init -q -b main "$U"
cp -R "$FIX/v0.7.2/." "$U/"; git -C "$U" add -A; git -C "$U" "${G[@]}" commit -qm "v0.7.2"; git -C "$U" "${G[@]}" tag v0.7.2
cp -R "$FIX/v0.8.0/." "$U/"; git -C "$U" add -A; git -C "$U" "${G[@]}" commit -qm "v0.8.0"; git -C "$U" "${G[@]}" tag v0.8.0
export RPG_FACTORY_WORKSPACE="$WS"
cat_json() { python3 -B "$CAT" --json "$@" 2>"$TMP/err"; }
q() { jq -r "$1" "$TMP/c.json"; }
line_of() { grep -n -m1 -F -- "$2" "$U/$1" | cut -d: -f1; }   # line in the v0.8.0 checkout (same blob at the tag)

# -- ref selection
cat_json > "$TMP/c.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q .status)" = PASS ] && [ "$(q .uitoolkit.ref)" = v0.7.2 ] && [ "$(q .uitoolkit.source)" = client-pin ] \
  && ok "default ref = client pin v0.7.2 (source client-pin)" || no "default ref: rc=$rc $(q '.uitoolkit | {ref,source}' | tr -d '\n')"
q '.uitoolkit.warnings[]' | grep -q "newest tag is v0.8.0" && ok "read at the pin: says a newer tag exists" || no "no newer-tag note"
q '[.entries[].id] | index("pkg:ICuvaraThemeService")' | grep -qx null && ok "v0.7.2 catalog has no theme service (absent at the pin)" || no "theme service at v0.7.2"
cat_json --ref v0.8.0 > "$TMP/c.json"
[ "$(q .uitoolkit.ref)/$(q .uitoolkit.source)" = "v0.8.0/arg" ] && ok "--ref v0.8.0 (source arg)" || no "--ref: $(q .uitoolkit.ref)"
q '.uitoolkit.warnings[]' | grep -q "client pins com.cuvara.uitoolkit v0.7.2, older than v0.8.0" && q '.uitoolkit.warnings[]' | grep -q "pin-bump" \
  && ok "client pin behind the ref used -> pin-bump warning" || no "pin-behind warning missing: $(q '.uitoolkit.warnings')"
pin "1.0.0"
cat_json > "$TMP/c2.json"
[ "$(jq -r '.uitoolkit.ref + "/" + .uitoolkit.source' "$TMP/c2.json")" = "v0.8.0/latest-tag" ] && ok "no #vX.Y.Z pin -> highest v* tag (latest-tag)" || no "latest-tag: $(jq -c .uitoolkit "$TMP/c2.json")"
pin "https://github.com/Cuvara/UIToolkit.git#v0.7.2"
cat_json --project "$TMP/nowhere" --ref v0.8.0 > "$TMP/c2.json"
[ "$(jq -r '.uitoolkit.client_pin' "$TMP/c2.json")" = null ] && [ "$(jq '.uitoolkit.warnings | length' "$TMP/c2.json")" = 0 ] \
  && ok "--project without a manifest: no pin, no pin warning" || no "--project pin: $(jq -c .uitoolkit "$TMP/c2.json")"

# -- entries at v0.8.0, each with a path:line@ref source read from git
e() { jq -c --arg id "$1" '.entries[] | select(.id == $id)' "$TMP/c.json"; }
src() { e "$1" | jq -r .source; }
[ "$(src pkg:ConfirmDialog)" = "Runtime/Flow/ConfirmDialog.cs:$(line_of Runtime/Flow/ConfirmDialog.cs 'public static class ConfirmDialog')@v0.8.0" ] \
  && [ "$(e pkg:ConfirmDialog | jq -r .kind)" = package-service ] && e pkg:ConfirmDialog | jq -e '.config | index("ShowAsync")' >/dev/null \
  && ok "ConfirmDialog: package-service, ShowAsync, exact source line" || no "ConfirmDialog entry: $(e pkg:ConfirmDialog | head -c 300)"
e pkg:ConfirmDialog | jq -r .purpose | grep -q "Reusable modal confirmation dialog" && ok "purpose comes from the XML doc summary" || no "purpose: $(e pkg:ConfirmDialog | jq -r .purpose)"
[ "$(e pkg:SettingsModel | jq -r .kind)" = package-service ] && e pkg:SettingsModel | jq -e '.config | index("SetMusicVolume")' >/dev/null \
  && ok "SettingsModel: service with its setters" || no "SettingsModel: $(e pkg:SettingsModel | head -c 300)"
[ "$(e pkg:SafeAreaElement | jq -r .kind)" = package-uxml-element ] \
  && [ "$(e pkg:SafeAreaElement | jq -c .config)" = '["conform-x (bool)","conform-y (bool)","apply-mode (SafeAreaApplyMode)"]' ] \
  && [ "$(src pkg:SafeAreaElement)" = "Runtime/Utilities/SafeAreaElement.cs:$(line_of Runtime/Utilities/SafeAreaElement.cs 'public partial class SafeAreaElement')@v0.8.0" ] \
  && ok "[UxmlElement] SafeAreaElement with its [UxmlAttribute]s" || no "SafeAreaElement: $(e pkg:SafeAreaElement | head -c 300)"
[ -n "$(e 'pkg:BaseUIToolkitScreenPresenter<TView>')" ] && [ -n "$(e 'pkg:BaseUIToolkitScreenPresenter<TView,TModel>')" ] \
  && [ "$(e 'pkg:BaseUIToolkitScreenPresenter<TView>' | jq -r .kind)" = package-type ] && ok "presenter bases: both generic arities, package-type" || no "presenter bases"
[ "$(e pkg:ToastType | jq -r .kind)" = package-type ] && ok "public enum in a service file is its own entry" || no "ToastType"
[ "$(e token:--cuvara-color-primary | jq -r '.kind + " " + .config[0]')" = "theme-token default rgba(51, 127.5, 229.5, 1)" ] \
  && [ "$(src token:--cuvara-color-primary)" = "Runtime/Theme/Resources/CuvaraTheme.uss:$(line_of Runtime/Theme/Resources/CuvaraTheme.uss '--cuvara-color-primary:')@v0.8.0" ] \
  && ok "theme token with default and source line" || no "token: $(e token:--cuvara-color-primary)"
[ "$(q '[.entries[] | select(.kind == "theme-token")] | length')" = 5 ] && ok "every --cuvara-* token declared in CuvaraTheme.uss (5), no var() uses" || no "token count $(q '[.entries[] | select(.kind == "theme-token")] | length')"
for c in cuvara-confirm-dialog cuvara-toast cuvara-safe-area cuvara-grid-row; do
  [ "$(e "uss:$c" | jq -r .kind)" = uss-class ] && ok "uss class $c (from a *UssClassName constant)" || no "uss class $c"
done
[ -z "$(e uss:CuvaraTheme)" ] && ok "a non-USS const string (ResourcesPath) is not a USS class" || no "ResourcesPath listed"
[ "$(e 'editor:Window/Cuvara/Figma Diagnostics' | jq -r '.kind')" = editor-tool ] \
  && e 'editor:Window/Cuvara/Figma Diagnostics' | jq -e '.requires | index("package com.unity.ui.figma 0.3.0-exp.1")' >/dev/null \
  && ok "Figma menu item: editor-tool gated on com.unity.ui.figma (asmdef versionDefines)" || no "figma menu: $(e 'editor:Window/Cuvara/Figma Diagnostics')"
[ -n "$(e 'editor:Assets/Cuvara/Create Screen')" ] && [ -n "$(e editor:FigmaImportValidator)" ] && [ -n "$(e editor:figma-import.py)" ] \
  && ok "ScreenCreator menu, FigmaImportValidator, Tools~ figma-import.py" || no "editor tools"
[ "$(e sample:LoadingFlow | jq -c .config)" = '["Resources/SettingsPopup.uxml"]' ] && [ -n "$(e sample:LoadingFlow/Resources/SettingsPopup.uxml)" ] \
  && ok "sample and its UXML" || no "sample: $(e sample:LoadingFlow)"
[ "$(e unity:Slider | jq -r '.kind + " " + .name + " " + .source')" = "unity-builtin ui:Slider https://docs.unity.com/en-us/engine/6000.3/script-reference/unityengine/uielements/slider" ] \
  && ok "Unity built-in ui:Slider with docs URL" || no "builtin: $(e unity:Slider)"
[ "$(q '[.entries[] | select(.kind == "unity-builtin")] | length')" = 16 ] && ok "16 Unity built-ins" || no "builtin count"
bad=$(q '[.entries[] | select(.kind != "unity-builtin" and (.source | test("^[^:]+:[0-9]+@v0[.]8[.]0$") | not)) | .id] | join(",")')
[ -z "$bad" ] && ok "every package entry source is <path>:<line>@<ref>" || no "bad sources: $bad"
bad=$(q '[.entries[] | select((.related_skills | index("ui-component-selection")) == null) | .id] | join(",")')
[ -z "$bad" ] && ok "every entry relates to ui-component-selection" || no "related_skills: $bad"
[ "$(q '[.entries[].id] | length')" = "$(q '[.entries[].id] | unique | length')" ] && ok "entry ids are unique" || no "duplicate ids"

# -- git, never the working tree
echo '    --cuvara-color-uncommitted: red;' >> "$U/Runtime/Theme/Resources/CuvaraTheme.uss"
cat_json --ref v0.8.0 > "$TMP/c2.json"
[ "$(jq '[.entries[] | select(.id == "token:--cuvara-color-uncommitted")] | length' "$TMP/c2.json")" = 0 ] && ok "uncommitted working-tree token is ignored" || no "read the working tree"
git -C "$U" checkout -q -- .
[ -z "$(git -C "$U" status --porcelain)" ] && ok "catalog left the UIToolkit repo clean" || no "UIToolkit repo dirty"

# -- NOT_AVAILABLE, never an invented catalog
cat_json --ref v9.9.9 > "$TMP/c2.json"; rc=$?
[ $rc -eq 1 ] && [ "$(jq -r .status "$TMP/c2.json")" = NOT_AVAILABLE ] && jq -r .reason "$TMP/c2.json" | grep -q "v9.9.9" \
  && [ "$(jq '[.entries[] | select(.kind != "unity-builtin")] | length' "$TMP/c2.json")" = 0 ] \
  && ok "unknown ref -> NOT_AVAILABLE (exit 1), built-ins only" || no "unknown ref: rc=$rc $(jq -c '{status,reason}' "$TMP/c2.json")"
cat_json --uitoolkit "$TMP/no-repo" > "$TMP/c2.json"; rc=$?
[ $rc -eq 1 ] && [ "$(jq -r .status "$TMP/c2.json")" = NOT_AVAILABLE ] && jq -r .reason "$TMP/c2.json" | grep -q "no UIToolkit git repository" \
  && ok "no repository -> NOT_AVAILABLE with the reason" || no "no repo: rc=$rc $(jq -c '{status,reason}' "$TMP/c2.json")"
mkdir -p "$TMP/empty-ws"   # explicit workspace without markers: no fallback to the cwd (inside the fixture) or the host default
(cd "$U" && RPG_FACTORY_WORKSPACE="$TMP/empty-ws" python3 -B "$CAT" --json > "$TMP/c2.json" 2>/dev/null); rc=$?
[ $rc -eq 1 ] && [ "$(jq -r .status "$TMP/c2.json")" = NOT_AVAILABLE ] && ok "explicit workspace without markers -> NOT_AVAILABLE, even from inside a workspace" || no "no workspace: rc=$rc $(jq -c '{status,reason}' "$TMP/c2.json")"
python3 -B "$CAT" --ref >/dev/null 2>&1; [ $? -eq 2 ] && ok "catalog usage error -> exit 2" || no "catalog usage exit"
out=$(python3 -B "$CAT" --ref v0.8.0); grep -q '^| `pkg:ConfirmDialog` | package-service | Runtime/Flow/ConfirmDialog.cs:' <<<"$out" && ok "Markdown table output" || no "markdown: $(head -c 300 <<<"$out")"

# -- selection: reuse > configure > compose > missing, evidence from the catalog, nothing invented
sel() { python3 -B "$SEL" --json "$@" > "$TMP/s.json" 2>"$TMP/err"; }
s() { jq -c --arg n "$1" '.selections[] | select(.need == $n)' "$TMP/s.json"; }
sel --screen settings --ref v0.8.0; rc=$?
[ $rc -eq 0 ] && [ "$(s settings-data | jq -r '.status + " " + (.choice | join(","))')" = "reuse pkg:SettingsModel" ] \
  && [ "$(s settings-data | jq -r '.evidence[0]')" = "Runtime/Flow/SettingsModel.cs:$(line_of Runtime/Flow/SettingsModel.cs 'public sealed class SettingsModel')@v0.8.0" ] \
  && ok "settings-data -> reuse SettingsModel with catalog evidence" || no "settings-data: rc=$rc $(s settings-data)"
[ "$(s volume-slider | jq -r '.status + " " + .choice[0]')" = "compose unity:Slider" ] && ok "volume -> compose ui:Slider" || no "volume: $(s volume-slider)"
[ "$(s confirm-popup | jq -r '.status + " " + .choice[0]')" = "reuse pkg:ConfirmDialog" ] && ok "confirm -> reuse ConfirmDialog" || no "confirm: $(s confirm-popup)"
[ "$(s theme | jq -r '.status + " " + .choice[0]')" = "reuse pkg:ICuvaraThemeService" ] && ok "theme -> reuse ICuvaraThemeService at v0.8.0" || no "theme: $(s theme)"
[ "$(s tabs | jq -r '.status + " " + (.choice | join(","))')" = "compose unity:TabView,unity:Tab" ] && ok "tabs -> compose TabView + Tab" || no "tabs: $(s tabs)"
[ "$(jq -r '.selections[0].need' "$TMP/s.json")" = screen-container ] && [ "$(s screen-container | jq -r .status)" = reuse ] \
  && s screen-container | jq -e '.choice | index("editor:Assets/Cuvara/Create Screen")' >/dev/null && ok "screen container -> reuse presenter/view + ScreenCreator" || no "screen-container: $(s screen-container)"
sel --screen settings
[ "$(s theme | jq -r .status)" = missing ] && s theme | jq -r .notes | grep -q "not in the catalog at v0.7.2" && s theme | jq -r .notes | grep -q "pin-bump" \
  && [ "$(s theme | jq -r .owner_if_missing)" = unity-package ] && ok "theme at the v0.7.2 pin -> missing, pin-bump note, owner unity-package" || no "theme@0.7.2: $(s theme)"
[ "$(s audio-toggle | jq -r '.status + " " + (.choice | join(","))')" = "compose unity:Toggle" ] && s audio-toggle | jq -r .notes | grep -q "game USS" \
  && ok "toggle still composes at v0.7.2; absent tokens are a styling note" || no "toggle@0.7.2: $(s audio-toggle)"
sel --need item-grid --need hologram-gizmo --need item-tooltip --ref v0.8.0
[ "$(s item-grid | jq -r '.status + " " + .choice[0]')" = "configure pkg:UIToolkitGridAdapter<TModel,TView,TPresenter>" ] && ok "item-grid -> configure the grid adapter" || no "item-grid: $(s item-grid)"
[ "$(s hologram-gizmo | jq -r '.status + " " + (.choice | length | tostring) + " " + .owner_if_missing')" = "missing 0 client-integration" ] \
  && s hologram-gizmo | jq -r .notes | grep -q "stop for that decision" && ok "unknown need -> missing, no invented choice, stop for a decision" || no "unknown need: $(s hologram-gizmo)"
[ "$(s item-tooltip | jq -r '.status + " " + (.choice | length | tostring)')" = "missing 0" ] && ok "tooltip (no catalog control) -> missing" || no "tooltip: $(s item-tooltip)"
[ "$(jq -r '.summary.missing' "$TMP/s.json")" = 2 ] && ok "summary counts missing" || no "summary: $(jq -c .summary "$TMP/s.json")"
sel --screen settings --uitoolkit "$TMP/no-repo"; rc=$?
na() { jq -c --arg n "$1" '.not_available[] | select(.need == $n)' "$TMP/s.json"; }
[ $rc -eq 1 ] && [ "$(jq -r .status "$TMP/s.json")" = NOT_AVAILABLE ] && [ -z "$(s settings-data)" ] && [ -z "$(s volume-slider)" ] \
  && na settings-data | jq -e '.requires == ["pkg:SettingsModel"] and (has("status") | not)' >/dev/null && [ -n "$(na volume-slider)" ] \
  && [ "$(jq '[.selections[] | select(.status != "compose")] | length' "$TMP/s.json")" = 0 ] \
  && [ "$(s tabs | jq -r .status)" = compose ] && ok "no repo: package needs listed under not_available (no status, no choice), built-in-only needs still compose" || no "no-repo select: rc=$rc $(jq -c '{status,not_available}' "$TMP/s.json" | head -c 300)"
# natural-language needs resolve deterministically (id, exact alias, longest whole-word match); optional ids never make a need missing
for pair in "confirmation popup=confirm-popup" "settings data=settings-data" "music toggle=audio-toggle" "volume slider=volume-slider" \
            "graphics quality=graphics-quality" "back navigation=back-close" "screen container=screen-container" "Popup-Container=popup-container" \
            "a big inventory grid please=item-grid"; do
  sel --need "${pair%%=*}" --ref v0.8.0
  [ "$(jq -r '.selections | length' "$TMP/s.json")" = 1 ] && [ "$(jq -r '.selections[0].recipe' "$TMP/s.json")" = "${pair#*=}" ] \
    && [ "$(jq -r '.selections[0].need' "$TMP/s.json")" = "${pair%%=*}" ] && ok "need '${pair%%=*}' -> recipe ${pair#*=}" || no "need '${pair%%=*}': $(jq -c '.selections' "$TMP/s.json" | head -c 200)"
done
sel --need "confirmation popup" --ref v0.8.0
[ "$(jq -r '.selections[0].status + " " + .selections[0].choice[0]' "$TMP/s.json")" = "reuse pkg:ConfirmDialog" ] && jq -r '.selections[0].evidence[0]' "$TMP/s.json" | grep -q "ConfirmDialog.cs:.*@v0.8.0" \
  && ok "'confirmation popup' reuses ConfirmDialog with evidence" || no "confirmation popup: $(jq -c .selections "$TMP/s.json")"
git -C "$U" rm -q -r Editor/ScreenCreator; git -C "$U" "${G[@]}" commit -qm "no screen creator"; git -C "$U" "${G[@]}" tag v0.8.1
sel --need screen-container --ref v0.8.1
[ "$(s screen-container | jq -r '.status + " " + (.choice | join(","))')" = "reuse pkg:BaseUIToolkitScreenPresenter<TView>,pkg:BaseUIToolkitView" ] \
  && s screen-container | jq -r .notes | grep -q "Optional editor:Assets/Cuvara/Create Screen not in the catalog at v0.8.1" \
  && ok "absent optional id (ScreenCreator menu) is a note; the existing presenter/view are still reused" || no "optional: $(s screen-container)"
sel --screen popup --ref v0.8.0
s confirm-popup | jq -e '.status == "reuse"' >/dev/null && ok "popup recipe includes ConfirmDialog" || no "popup recipe: $(jq -c '[.selections[].need]' "$TMP/s.json")"
python3 -B "$SEL" --screen nosuch >/dev/null 2>&1; [ $? -eq 2 ] && ok "unknown archetype -> exit 2" || no "unknown archetype exit"
python3 -B "$SEL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "no --screen/--need -> exit 2" || no "select usage exit"
for a in settings inventory popup hud quest-panel shop confirm; do
  python3 -B "$SEL" --json --screen "$a" --ref v0.8.0 > "$TMP/s.json" 2>/dev/null
  n=$(jq '[.selections[] | select((.status == "missing" or .status == "NOT_AVAILABLE") and (.choice | length) > 0)] | length' "$TMP/s.json")
  [ "$n" = 0 ] && [ "$(jq '.selections | length' "$TMP/s.json")" -gt 0 ] && ok "recipe $a resolves (a missing need never carries a choice)" || no "recipe $a"
done
python3 -B - "$ROOT" <<'PY' && ok "every recipe choice is a catalog id form (pkg:/editor:/token:/uss:/unity:/sample:)" || no "recipe ids"
import json, sys
d = json.load(open(sys.argv[1] + "/scripts/ui/data/screen-recipes.json", encoding="utf-8"))
ids = [c for n in d["needs"].values() for c in n["choice"]]
assert all(c.split(":", 1)[0] in ("pkg", "editor", "token", "uss", "unity", "sample") for c in ids), ids
assert all(n in d["needs"] for s in d["screens"].values() for n in s)
assert all(n["status"] in ("reuse", "configure", "compose", "missing") for n in d["needs"].values())
assert all(n["owner_if_missing"] in ("unity-package", "client-integration") for n in d["needs"].values())
PY

total=$((pass + fail)); echo "ui-catalog tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
