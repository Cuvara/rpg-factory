#!/usr/bin/env bash
# UI plan (scripts/ui/ui_plan.py) behind the /rpg-factory:ui* commands: schema, intent and the minimal skill
# list per verb, NOT_UI, NEEDS_CONTEXT (exit 3) with exact missing items, Figma URL parsing, --project,
# Markdown next steps, and that the lead route really routes. Fixture workspace with a UIToolkit git repo.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
CMD="$ROOT/scripts/factory-cmd.py"; FIX="$ROOT/tests/fixtures/ui-catalog"
G=(-c user.email=t@t -c user.name=t -c commit.gpgsign=false -c tag.gpgsign=false)

WS="$TMP/ws"; U="$WS/UIToolkit"; C="$WS/IndieRPGMMOAdventure"; S="$WS/rpg-mmo-server"
mkdir -p "$S/backend" "$C/ProjectSettings" "$C/Packages" "$C/Assets/Scripts/UI" "$U"
touch "$S/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt" "$C/Assets/Scripts/UI/.keep"
printf '{\n  "dependencies": {\n    "com.cuvara.uitoolkit": "https://github.com/Cuvara/UIToolkit.git#v0.7.2"\n  }\n}\n' > "$C/Packages/manifest.json"
git init -q -b main "$U"
cp -R "$FIX/v0.7.2/." "$U/"; git -C "$U" add -A; git -C "$U" "${G[@]}" commit -qm "v0.7.2"; git -C "$U" "${G[@]}" tag v0.7.2
cp -R "$FIX/v0.8.0/." "$U/"; git -C "$U" add -A; git -C "$U" "${G[@]}" commit -qm "v0.8.0"; git -C "$U" "${G[@]}" tag v0.8.0
for r in "$S" "$C"; do git -C "$r" init -q -b develop; git -C "$r" add -A; git -C "$r" "${G[@]}" commit -qm init; done
export RPG_FACTORY_WORKSPACE="$WS"
URL='https://www.figma.com/design/AbC123xyz/Shop-Demo?node-id=1-2&t=k9'

plan() { (cd "$WS" && python3 -B "$CMD" "$@" --json) > "$TMP/p.json" 2>"$TMP/err"; }
q() { jq -r "$1" "$TMP/p.json"; }
skills() { q '[.skills[].name] | join(",")'; }
expect() {  # expect <label> <rc> <status> <intent> <skills csv> -- <factory-cmd args...>
  local label=$1 erc=$2 st=$3 it=$4 sk=$5; shift 6
  plan "$@"; local rc=$?
  if [ $rc -eq "$erc" ] && [ "$(q .status)" = "$st" ] && [ "$(q '.intent // "null"')" = "$it" ] && [ "$(skills)" = "$sk" ]; then ok "$label"
  else no "$label: rc=$rc status=$(q .status) intent=$(q .intent) skills=$(skills) $(head -c 200 "$TMP/err")"; fi
}

# -- schema
plan ui "Create an inventory screen"; rc=$?
keys=$(q 'keys_unsorted | join(",")')
[ "$keys" = "schema,request,verb,status,intent,skills,not_loaded,lead,context,missing,components,next" ] && [ "$(q .schema)" = "rpg-factory.ui-plan/1" ] \
  && ok "plan JSON has the rpg-factory.ui-plan/1 keys in order" || no "plan keys: $keys"
[ "$(q '.context | keys_unsorted | join(",")')" = "figma,project,uitoolkit,screen" ] && ok "context keys" || no "context keys: $(q '.context | keys')"
[ $rc -eq 0 ] && [ "$(q .intent)" = screen ] && [ "$(skills)" = "ui-component-selection,ui-toolkit-screen,ui-validation" ] \
  && [ "$(q '.not_loaded | join(",")')" = "ui-figma-import" ] && [ "$(q .context.screen)" = inventory ] \
  && ok "ui: inventory screen -> screen intent, 3 skills, ui-figma-import not loaded" || no "inventory plan: rc=$rc $(skills) $(q .not_loaded)"
[ "$(q '.lead.skill + " " + (.lead.route | join(" "))')" = "client-integration --repo client --paths Assets/Scripts/UI/Inventory/" ] \
  && ok "lead client-integration, route to Assets/Scripts/UI/Inventory/" || no "lead: $(q .lead)"
[ "$(q '[.skills[] | select(.why | length > 10)] | length')" = 3 ] && ok "every skill says why" || no "why missing"
[ "$(q '.context.uitoolkit.ref + "/" + .context.uitoolkit.source')" = "v0.7.2/client-pin" ] && ok "uitoolkit ref from the client pin" || no "uitoolkit ctx: $(q .context.uitoolkit)"
[ "$(fwd "$(q .context.project)")" = "$(fwd "$C")" ] && ok "project = workspace client repo" || no "project: $(q .context.project)"
[ "$(q '.components.selections[0].need')" = screen-container ] && [ "$(q '.components.screen')" = inventory ] && ok "components: inventory selection attached" || no "components: $(q .components | head -c 200)"
q '.next[0]' | grep -q '^invoke rpg-factory:factory-core (mode implement) and Route with: factory-context.sh --repo client --paths Assets/Scripts/UI/Inventory/$' \
  && q '.next[1]' | grep -q '^then invoke the lead rpg-factory:client-integration, then, in order: rpg-factory:ui-component-selection, rpg-factory:ui-toolkit-screen, rpg-factory:ui-validation' \
  && ok "next: factory-core first, then the lead, then only the listed skills in order" || no "next: $(q .next)"
[ "$(jq '[.. | strings | select(test("ui-orchestrator"))] | length' "$TMP/p.json")" = 0 ] && ok "ui-orchestrator is never listed" || no "orchestrator listed"

# -- intents and skill lists per verb
expect "ui-figma URL -> figma-import, 4 skills" 0 PLAN figma-import "ui-figma-import,ui-component-selection,ui-toolkit-screen,ui-validation" -- ui-figma "$URL import into the client"
[ "$(q '.context.figma | .file_key + " " + .node_id + " " + .url')" = "AbC123xyz 1:2 $URL" ] && ok "Figma URL: file_key, node-id 1-2 -> 1:2, full URL" || no "figma ctx: $(q .context.figma)"
[ "$(q '.lead.route | join(" ")')" = "--repo client --paths Assets/Figma/ Assets/Scripts/UI/" ] && ok "figma-import route covers Assets/Figma/" || no "figma route: $(q .lead.route)"
expect "Figma URL in plain ui verb -> figma-import" 0 PLAN figma-import "ui-figma-import,ui-component-selection,ui-toolkit-screen,ui-validation" -- ui "Import $URL into Unity"
plan ui-figma "https://www.figma.com/file/Key9/Name?type=design&node-id=12%3A345 import"
[ "$(q '.context.figma.file_key + " " + .context.figma.node_id')" = "Key9 12:345" ] && ok "file/ URL with node-id 12%3A345 -> 12:345" || no "encoded node: $(q .context.figma)"
expect "URL without scheme or www, extra query -> PLAN" 0 PLAN figma-import "ui-figma-import,ui-component-selection,ui-toolkit-screen,ui-validation" -- ui-figma "import figma.com/design/KeyBare03/Hud?node-id=7-8&t=AbCdEf-0"
[ "$(q '.context.figma.file_key + " " + .context.figma.node_id')" = "KeyBare03 7:8" ] && ok "bare figma.com URL: file_key + node-id 7-8 -> 7:8" || no "bare url: $(q .context.figma)"
expect "validate imported UXML and USS -> figma-validate (connector output)" 0 PLAN figma-validate "ui-figma-import,ui-validation" -- ui "Validate imported UXML and USS"
expect "ui-figma analyze ->ui-figma-import, ui-component-selection" 0 PLAN figma-analyze "ui-figma-import,ui-component-selection" -- ui-figma "Analyze $URL and list the components"
expect "ui-figma validate -> ui-figma-import, ui-validation" 0 PLAN figma-validate "ui-figma-import,ui-validation" -- ui-figma "Validate the import of $URL"
expect "ui-figma FIG023 -> troubleshoot with ui-figma-import" 0 PLAN troubleshoot "ui-figma-import" -- ui-figma "Fix FIG023 in the imported shop screen"
expect "ui-components settings -> components only" 0 PLAN components "ui-component-selection" -- ui-components "Find components needed for a settings screen"
[ "$(q '.components.selections[] | select(.need == "settings-data") | .choice[0]')" = pkg:SettingsModel ] && [ "$(q '.lead.route[-1]')" = Assets/Scripts/UI/Settings/ ] \
  && ok "ui-components: settings selection reuses SettingsModel" || no "components settings: $(q .components.selections[1])"
q '.next[0]' | grep -q "(mode plan)" && ok "component selection runs factory-core in plan mode" || no "mode: $(q .next[0])"
expect "ui-screen imported UXML -> integrate" 0 PLAN integrate "ui-toolkit-screen,ui-validation" -- ui-screen "Implement this imported UXML in the current screen architecture"
expect "ui-screen plain -> screen" 0 PLAN screen "ui-component-selection,ui-toolkit-screen,ui-validation" -- ui-screen "Add a quest panel"
[ "$(q .context.screen)" = quest-panel ] && ok "quest panel archetype" || no "quest archetype: $(q .context.screen)"
expect "ui-review -> ui-validation only" 0 PLAN review "ui-validation" -- ui-review "Review this screen for architecture, layout, theme and runtime issues"
q '.next[0]' | grep -q "(mode review)" && ok "review runs factory-core in review mode" || no "review mode"
expect "ui-review with a Figma URL -> ui-figma-import first" 0 PLAN review "ui-figma-import,ui-validation" -- ui-review "Review the import of $URL"
expect "ui troubleshoot (Figma terms) -> ui-figma-import" 0 PLAN troubleshoot "ui-figma-import" -- ui "The Figma connector does not connect"
expect "ui troubleshoot (no Figma) -> screen + validation" 0 PLAN troubleshoot "ui-toolkit-screen,ui-validation" -- ui "The inventory screen does not render after opening"
expect "ui design -> lead ui-ux, no UI tech skill" 0 PLAN design "" -- ui "Design the settings flow"
[ "$(q '.lead.skill + " " + (.lead.route | join(" "))')" = "ui-ux --domain ui" ] && ok "design lead ui-ux --domain ui" || no "design lead: $(q .lead)"
expect "ui design + components -> ui-component-selection" 0 PLAN design "ui-component-selection" -- ui "Design a shop screen and which components it should reuse"
expect "ui analyze -> ui-toolkit-screen" 0 PLAN analyze "ui-toolkit-screen" -- ui "Analyze the existing UI architecture"
expect "ui-components HUD -> components" 0 PLAN components "ui-component-selection" -- ui-components "Which components for the HUD"
[ "$(q .context.screen)" = hud ] && ok "HUD archetype" || no "hud: $(q .context.screen)"
plan ui "Add a tooltip control to the UIToolkit package"
[ "$(q '.lead.skill + " " + (.lead.route | join(" "))')" = "unity-package --repo uitoolkit --paths Runtime/" ] && ok "package work -> lead unity-package" || no "package lead: $(q .lead)"

# -- NOT_UI
expect "not a UI request -> NOT_UI, exit 0, no skills" 0 NOT_UI null "" -- ui "Add a health field to the wire protocol"
[ "$(q '.next[0]')" = "not a UI request: use rpg-factory:factory-core directly" ] && [ "$(q .lead)" = null ] && ok "NOT_UI message, no lead" || no "NOT_UI next: $(q .next)"
expect "forced verb is never NOT_UI" 0 PLAN components "ui-component-selection" -- ui-components "health field"

# -- component phrasing and dependency changes (Codex review 2)
expect "component phrasing + archetype is UI" 0 PLAN components "ui-component-selection" -- ui "What components for settings?"
[ "$(q .lead.skill)" = client-integration ] && ok "components for settings -> lead client-integration" || no "lead: $(q .lead)"
expect "Go components are not UI" 0 NOT_UI null "" -- ui "Which Go components does the gateway use?"
expect "adding the package dependency is not UI" 0 NOT_UI null "" -- ui "Add com.cuvara.uitoolkit to the client project"
q '.next[1]' | grep -q "pin-bump" && [ "$(q '.next[0]')" = "not a UI request: use rpg-factory:factory-core directly" ] && ok "dependency NOT_UI names factory-core and pin-bump" || no "dep next: $(q .next)"
md=$(cd "$WS" && python3 -B "$CMD" ui "Add com.cuvara.uitoolkit to the client project"); grep -q "pin-bump" <<<"$md" && ok "Markdown dependency NOT_UI names pin-bump" || no "dep markdown"
expect "dependency + UI work stays a UI plan" 0 PLAN screen "ui-component-selection,ui-toolkit-screen,ui-validation" -- ui "Add com.cuvara.uitoolkit to the client project and build a settings screen"

# -- NEEDS_CONTEXT (exit 3), exact missing items, never a guess
expect "ui-figma without URL -> NEEDS_CONTEXT" 3 NEEDS_CONTEXT figma-import "ui-figma-import,ui-component-selection,ui-toolkit-screen,ui-validation" -- ui-figma "Import this Figma frame into Unity"
[ "$(q '[.missing[].item] | join(",")')" = figma-frame-url ] && q '.missing[0].how' | grep -q "node-id" && [ "$(q .context.figma)" = null ] \
  && ok "missing exactly figma-frame-url, with how" || no "missing: $(q .missing)"
q '.next[0]' | grep -q "^ask the user for exactly: figma-frame-url" && q '.next[1]' | grep -q "^stop" && [ "$(q '.next | length')" = 2 ] \
  && ok "NEEDS_CONTEXT next: ask, then stop (no route)" || no "needs next: $(q .next)"
expect "ui-figma analyze without URL -> NEEDS_CONTEXT" 3 NEEDS_CONTEXT figma-analyze "ui-figma-import,ui-component-selection" -- ui-figma "Analyze the Figma frame"
plan ui-figma "https://www.figma.com/design/AbC123xyz/Shop-Demo import"; rc=$?
[ $rc -eq 3 ] && [ "$(q '[.missing[].item] | join(",")')" = figma-node-id ] && ok "URL without node-id -> missing figma-node-id" || no "node-id missing: rc=$rc $(q .missing)"
NOWS="$TMP/nows"; mkdir -p "$NOWS"
out=$(cd "$WS" && RPG_FACTORY_WORKSPACE="$NOWS" python3 -B "$CMD" ui-figma "$URL" --json); rc=$?   # cwd is a workspace: must not be used
[ $rc -eq 3 ] && [ "$(jq -r '[.missing[].item] | join(",")' <<<"$out")" = target-project ] && ok "no client repo (explicit empty workspace), no --project -> missing target-project" || no "target-project: rc=$rc $(jq -c .missing <<<"$out")"
P="$TMP/MyGame"; mkdir -p "$P/Packages"
out=$(cd "$NOWS" && RPG_FACTORY_WORKSPACE="$NOWS" python3 -B "$CMD" ui-figma --project "$P" "$URL" --json); rc=$?
[ $rc -eq 0 ] && [ "$(jq -r .status <<<"$out")" = PLAN ] && [ "$(fwd "$(jq -r .context.project <<<"$out")")" = "$(fwd "$P")" ] && ok "--project satisfies the target project" || no "--project: rc=$rc $(jq -c '{status,missing}' <<<"$out")"
out=$(cd "$NOWS" && RPG_FACTORY_WORKSPACE="$NOWS" python3 -B "$CMD" ui-figma "$URL into $P" --json); rc=$?
[ $rc -eq 0 ] && [ "$(fwd "$(jq -r .context.project <<<"$out")")" = "$(fwd "$P")" ] && ok "absolute project path in the text is used" || no "path in text: rc=$rc $(jq -c '{status,missing,project:.context.project}' <<<"$out")"
out=$(cd "$NOWS" && RPG_FACTORY_WORKSPACE="$NOWS" python3 -B "$CMD" ui-figma --project "$TMP/nope" "$URL" --json); rc=$?
[ $rc -eq 3 ] && jq -r '.missing[0].why' <<<"$out" | grep -q "is not a directory" && ok "--project that does not exist -> missing target-project" || no "bad project: rc=$rc"

# -- options
plan ui --uitoolkit-ref v0.8.0 "Create a settings screen"
[ "$(q '.context.uitoolkit.ref + "/" + .context.uitoolkit.source')" = "v0.8.0/arg" ] && q '.context.uitoolkit.warnings[0]' | grep -q "pin-bump" \
  && [ "$(q '.components.selections[] | select(.need == "theme") | .status')" = reuse ] && ok "--uitoolkit-ref v0.8.0: arg ref, pin-bump warning, theme reusable" || no "--uitoolkit-ref: $(q .context.uitoolkit)"
plan ui "Create a settings screen"
[ "$(q '.components.selections[] | select(.need == "theme") | .status')" = missing ] && ok "at the v0.7.2 pin the theme service is missing (no invention)" || no "theme@pin: $(q '.components.selections[] | select(.need == "theme")')"
(cd "$WS" && python3 -B "$CMD" ui "Create a settings screen --json") > "$TMP/p.json"; [ "$(q .schema)" = rpg-factory.ui-plan/1 ] && ok "one quoted \$ARGUMENTS string with --json is split" || no "quoted args"
(cd "$WS" && python3 -B "$CMD" ui "\"Create a settings screen\"" --json) > "$TMP/p.json"; [ "$(q .request)" = "Create a settings screen" ] && ok "surrounding quotes are stripped once" || no "quotes: $(q .request)"
(cd "$WS" && python3 -B "$CMD" ui-figma "$URL, import it") > /dev/null 2>&1; plan ui-figma "$URL, import it"
[ "$(q .context.figma.node_id)" = 1:2 ] && ok "commas in the request are kept (no comma splitting for UI verbs)" || no "comma: $(q .context.figma)"

# -- Markdown
md=$(cd "$WS" && python3 -B "$CMD" ui "Create an inventory screen"); rc=$?
[ $rc -eq 0 ] && grep -q "^## rpg-factory UI plan (ui)" <<<"$md" && grep -q "^### Next steps" <<<"$md" && grep -q "^1. invoke rpg-factory:factory-core" <<<"$md" \
  && grep -q "^### Components" <<<"$md" && grep -q '^| screen-container | \*\*reuse\*\*' <<<"$md" && ok "Markdown: plan, components table, next steps" || no "markdown: $(head -c 400 <<<"$md")"
md=$(cd "$WS" && python3 -B "$CMD" ui-figma "Import this Figma frame"); rc=$?
[ $rc -eq 3 ] && grep -q "^### Missing (ask the user, then stop)" <<<"$md" && grep -q "figma-frame-url" <<<"$md" && ok "Markdown NEEDS_CONTEXT lists the missing item (exit 3)" || no "markdown missing rc=$rc"
md=$(cd "$WS" && python3 -B "$CMD" ui "Rebalance the gold drop rate"); rc=$?
[ $rc -eq 0 ] && grep -q "Not a UI request: use rpg-factory:factory-core directly" <<<"$md" && ok "Markdown NOT_UI" || no "markdown NOT_UI"

# -- usage errors (exit 2, factory-cmd usage)
for a in "ui" "ui-figma" "ui-components" "ui-screen" "ui-review" "ui --json" "ui --project" "ui-figma --uitoolkit-ref"; do
  python3 -B "$CMD" $a >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && grep -q "ui-figma | ui-components | ui-screen | ui-review" "$TMP/err" && ok "usage error -> exit 2: '$a'" || no "usage '$a' rc=$rc"
done
python3 -B "$ROOT/scripts/ui/ui_plan.py" --verb nope x >/dev/null 2>&1; [ $? -eq 2 ] && ok "ui_plan.py unknown verb -> exit 2" || no "ui_plan verb"

# -- the lead route really routes (factory-context.sh on the fixture workspace)
plan ui "Create an inventory screen"; mapfile -t R < <(q '.lead.route[]')
out=$(cd "$WS" && bash "$ROOT/scripts/factory-context.sh" "${R[@]}" 2>&1)
grep -q 'lead `rpg-factory:client-integration`' <<<"$out" && grep -q "ui-component-selection" <<<"$out" && ok "plan route -> factory-context lead client-integration, UI tech listed" || no "route: $(grep -i routing <<<"$out" | head -2)"
[ -z "$(git -C "$C" status --porcelain)" ] && [ -z "$(git -C "$U" status --porcelain)" ] && ok "plans left the fixture repos untouched" || no "fixture repos changed"

total=$((pass + fail)); echo "ui-commands tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
