#!/usr/bin/env bash
# UI skills content: ui-orchestrator, ui-toolkit-screen and ui-validation are filled (no SCAFFOLD:), keep the
# tech-skill shape, follow the shared UI plan contract (statuses, intents, only the listed skills), keep the
# UIToolkit v0.8.0 facts they must preserve, never claim unverified Figma features, and are reachable from
# client-integration. docs/architecture/ui-skills.md documents the system. The snapshot Next line for a UI path sends
# the agent to ui-orchestrator first (fixture workspace). Needs no real workspace.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"
python3 -B - "$ROOT" "$TMP/py.counts" <<'PY'
import json, os, re, sys

root = sys.argv[1]
reg = json.load(open(os.path.join(root, "registry.json"), encoding="utf-8"))
passed = failed = 0


def check(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {msg}")
    else:
        failed += 1
        print(f"FAIL  {msg}")


def read(rel):
    p = os.path.join(root, rel)
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def section(text, title):
    m = re.search(r"^## " + re.escape(title) + r"[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def frontmatter(text, key):
    head = text.split("\n---", 1)[0]
    m = re.search(r"^" + key + r": (.*)$", head, re.M)
    return m.group(1) if m else ""


MINE = ["ui-orchestrator", "ui-toolkit-screen", "ui-validation"]
ALL_UI = ["ui-orchestrator", "ui-component-selection", "ui-figma-import", "ui-toolkit-screen", "ui-validation"]
STATES = {"PASS", "FAIL", "BLOCKED", "NOT_AVAILABLE", "HUMAN_REQUIRED", "SKIPPED", "NOT_RUN", "STALE"}
SECTIONS = ["Applies when", "Scope", "Architecture", "Idioms", "Pitfalls", "Testing", "Tools"]

for s in MINE:
    text = read(f"skills/{s}/SKILL.md")
    spec = reg["skills"].get(s, {})
    check(text != "", f"{s}: SKILL.md exists")
    check("SCAFFOLD" not in text, f"{s}: no SCAFFOLD marker left")
    check(spec.get("kind") == "tech" and spec.get("domain") == "ui", f"{s}: registry kind tech, domain ui")
    check(text.count("\n") <= 160, f"{s}: SKILL.md at most 160 lines")
    desc = frontmatter(text, "description")
    check(len(desc) >= 120 and "Use when" in desc and "Not for" in desc, f"{s}: description says Use when and Not for")
    check("factory-context.sh" in frontmatter(text, "allowed-tools"), f"{s}: allowed-tools grants factory-context.sh")
    check("**Supporting skill, never the owner:** invoke the lead" in text, f"{s}: carries the lead-first guard")
    for sec in SECTIONS:
        check(re.search(r"^## .*" + re.escape(sec), text, re.M) is not None, f"{s}: has section {sec}")
    states = set(re.findall(r"\b[A-Z]+(?:_[A-Z]+)+\b|\b(?:PASS|FAIL|BLOCKED|SKIPPED|STALE)\b", text))
    states = {x for x in states if x in STATES or x.startswith(("NOT_", "HUMAN_"))} - {"NOT_UI"}  # NOT_UI: plan status
    check(states <= STATES, f"{s}: result states only from run-checks vocabulary ({sorted(states - STATES)})")
    tools = section(text, "Tools")
    check("`unity-mcp`" in tools or s == "ui-orchestrator", f"{s}: ## Tools names unity-mcp with a fallback")

# the lead names every UI tech skill at its UI step (skill-touchpoints and skills-lint require it)
ci = read("skills/client-integration/SKILL.md")
delta = section(ci, "Workflow delta")
for s in ALL_UI:
    check(f"rpg-factory:{s}" in delta, f"client-integration Workflow delta names rpg-factory:{s}")

# ui-orchestrator follows the shared UI plan contract
orch = read("skills/ui-orchestrator/SKILL.md")
check("Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)" in frontmatter(orch, "allowed-tools"),
      "ui-orchestrator: allowed-tools grants factory-cmd.py")
check("factory-cmd.py ui --json" in orch, "ui-orchestrator: runs the plan with factory-cmd.py ui --json")
for st in ("NOT_UI", "NEEDS_CONTEXT", "PLAN"):
    check(f"`{st}`" in orch, f"ui-orchestrator: handles status {st}")
check(re.search(r"[Nn]ever (invoke|load)[^.]*`not_loaded`", orch) is not None, "ui-orchestrator: never loads not_loaded skills")
check(re.search(r"never guess", orch, re.I) is not None, "ui-orchestrator: never guesses missing context")
check(re.search(r"re-run the plan", orch, re.I) is not None, "ui-orchestrator: re-plans when the task changes")
check(re.search(r"[Ss]elect before creating", orch) is not None, "ui-orchestrator: selection before creation")
check("parallel-work" in orch, "ui-orchestrator: points to factory-core parallel-work")
for intent in ("design", "figma-import", "figma-analyze", "figma-validate", "components", "screen", "integrate",
               "review", "troubleshoot", "analyze"):
    check(re.search(r"(^|[\s(])" + re.escape(intent) + r":", orch) is not None, f"ui-orchestrator: maps intent {intent}")
rep = section(orch, "Report additions")
for word in ("skipped", "reuse", "configure", "compose", "missing", "evidence"):
    check(word in rep.lower(), f"ui-orchestrator: report additions mention {word}")

# ui-toolkit-screen keeps the v0.8.0 facts
scr = read("skills/ui-toolkit-screen/SKILL.md")
for fact in ("Assets/Cuvara/Create Screen", "ExistingUxml", "IsInsideConnectorImportFolder", "OnBindAsync",
             "ScreenSubscriptions", "RegisterScreen", "RegisterPopup", "ScreenRegistry", "IScreenNavigator",
             "ScreenOptions", "BackNavigationSource", "Require", ".uxml.g.cs", "SettingsModel",
             "ConfirmDialog.ShowAsync", "ToastService", "RegisterModeSheets", "SetModeSheet", "AttachScreen",
             "AddOverride", "applyTheme", "themeOverrides", "themeModeSheet", "--cuvara-*", "UpdateAlpha"):
    check(fact in scr, f"ui-toolkit-screen: names {fact}")
check(re.search(r"never hand-edited", scr) is not None, "ui-toolkit-screen: generated bindings never hand-edited")
check(re.search(r"\(analyze mode: read only\)|analyze mode[^.]*read", scr, re.I) is not None, "ui-toolkit-screen: analyze mode is read-only")

# ui-validation: seven areas, artifact rule, the review checklist
val = read("skills/ui-validation/SKILL.md")
review = read("skills/ui-validation/references/ui-review.md")
for area in ("References", "Bindings", "Lifecycle", "Theme", "Responsive", "Runtime", "Tests"):
    check(re.search(r"^\| " + area + r" \|", val, re.M) is not None, f"ui-validation: evidence table row {area}")
    check(re.search(r"^## \d\. " + area, review, re.M) is not None, f"ui-review.md: section {area}")
check("references/ui-review.md" in val, "ui-validation: links its review checklist")
check("/rpg-factory:ui-review" in val and "/rpg-factory:ui-review" in review, "ui-validation: checklist serves /rpg-factory:ui-review")
check(re.search(r"[Nn]o artifact means no PASS", val) is not None, "ui-validation: no PASS without an artifact")
for fact in ("FIG023", "uxml-codegen-drift.yml", "SafeAreaElement", "PanelSettings", "two aspect ratios",
             "tests-run", "console-get-logs", "screenshot-game-view"):
    check(fact in val + review, f"ui-validation: names {fact}")

# never claim unverified Figma features or build an importer
doc = read("docs/architecture/ui-skills.md")
for name, text in [(s, read(f"skills/{s}/SKILL.md")) for s in MINE] + [("ui-review.md", review), ("ui-skills.md", doc)]:
    bad = [l.strip()[:80] for l in text.splitlines()
           if re.search(r"shadow|gradient", l, re.I) and not re.search(r"\bnot\b|\bnever\b", l, re.I)]
    check(not bad, f"{name}: shadow/gradient only as unverified ({bad[:1]})")

# docs/architecture/ui-skills.md
check(doc != "", "docs/architecture/ui-skills.md exists")
for s in ALL_UI + ["ui-ux", "client-integration", "unity-package", "unity-client-tech"]:
    check(f"`{s}`" in doc, f"ui-skills.md names {s}")
for verb in ("ui", "ui-figma", "ui-components", "ui-screen", "ui-review"):
    check(f"`/rpg-factory:{verb}`" in doc, f"ui-skills.md lists command /rpg-factory:{verb}")
for fact in ("rpg-factory.ui-plan/1", "`paths`", "new-skill.py", "--kind tech", "--domain ui", "scripts/ui/data/",
             "ui-figma-real-test.md", "v0.8.0", "FIG023", "skill-touchpoints.py", "NEEDS_CONTEXT", "NOT_UI"):
    check(fact in doc, f"ui-skills.md mentions {fact}")
check("ui-skills.md" in read("docs/architecture/README.md"), "docs/architecture/README.md links ui-skills.md")

with open(sys.argv[2], "w", encoding="utf-8") as out:
    print(passed, failed, file=out)
PY
read -r pass fail < <(tr -d '\r' < "$TMP/py.counts" 2>/dev/null) || { pass=0; fail=1; echo "FAIL  content checks crashed"; }
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

# snapshot Next line: a UI path names the UI skills once and sends the agent to ui-orchestrator first;
# a non-UI client path has no UI clause (fixture workspace, read-only)
WS="$TMP/ws"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$WS/rpg-mmo-server/backend" "$C/ProjectSettings" "$C/Assets/Scripts/UI/X" "$C/Assets/Scripts/DI"
touch "$WS/rpg-mmo-server/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt" "$C/Assets/Scripts/UI/X/X.uxml" "$C/Assets/Scripts/DI/Scope.cs"
git -C "$C" init -q -b develop && git -C "$C" -c user.email=t@t -c user.name=t add -A   && git -C "$C" -c user.email=t@t -c user.name=t commit -qm init
ui=$(cd "$WS" && RPG_FACTORY_WORKSPACE="$WS" CLAUDE_PLUGIN_ROOT="$ROOT" bash "$ROOT/scripts/factory-context.sh" --repo client --paths Assets/Scripts/UI/X/X.uxml 2>&1)
nonui=$(cd "$WS" && RPG_FACTORY_WORKSPACE="$WS" CLAUDE_PLUGIN_ROOT="$ROOT" bash "$ROOT/scripts/factory-context.sh" --repo client --paths Assets/Scripts/DI/Scope.cs 2>&1)
next_ui=$(grep -F '**Next:**' <<<"$ui"); next_nonui=$(grep -F '**Next:**' <<<"$nonui")
[ -n "$next_ui" ] && [ -n "$next_nonui" ] && ok "Next line printed for a UI and a non-UI client path" || no "no Next line: $(head -c 300 <<<"$ui")"
grep -qF 'invoke `rpg-factory:ui-orchestrator` first' <<<"$next_ui" && ok "UI path: Next line invokes rpg-factory:ui-orchestrator first"   || no "UI path: Next line lacks 'invoke \`rpg-factory:ui-orchestrator\` first': $(head -c 400 <<<"$next_ui")"
! grep -qF 'tech skill(s) `rpg-factory:ui-component-selection`' <<<"$next_ui" && ! grep -qE 'tech skill\(s\) [^.]*`rpg-factory:ui-(component-selection|figma-import|toolkit-screen|validation)`' <<<"$next_ui"   && ok "UI path: Next line does not list the UI skills as tech skills to invoke" || no "UI path: Next line asks to invoke UI skills directly"
! grep -qF 'UI skills (' <<<"$next_nonui" && ok "non-UI path: no 'UI skills (' clause" || no "non-UI path has a UI skills clause"
[ -z "$(git -C "$C" status --porcelain)" ] && ok "fixture client repo untouched" || no "fixture client repo changed"

echo "ui skills tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
