#!/usr/bin/env bash
# UI skill routing, black box: the UI plan (`factory-cmd.py ui|ui-figma|ui-components|ui-screen|ui-review --json`)
# against the golden matrix tests/fixtures/ui-plan-cases.json (status, intent, EXACT skill order, not_loaded,
# missing items, exit codes 0/3/2), component selection (`scripts/ui/ui_select.py`) against
# tests/fixtures/ui-select-cases.json on a UIToolkit fixture repo, the registry's five `domain: ui` tech
# skills, their path-scoped routing.tech in factory-context.sh, and unchanged factory-core routing.
# Runs on fixture workspaces in a temp dir (no product repo, no network). When the engine is absent the
# plan and selection sections are replaced by one FAIL "engine missing" (exit 1, no crash).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
CMD="$ROOT/scripts/factory-cmd.py"; CTX="$ROOT/scripts/factory-context.sh"
PLAN="$ROOT/scripts/ui/ui_plan.py"; SELECT="$ROOT/scripts/ui/ui_select.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
gitq() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }

# -- fixture workspaces: full (server + client pinned to the UIToolkit fixture's v0.8.0 tag) and no-client
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"; U="$WS/UIToolkit"; WS2="$TMP/ws-no-client"
mkdir -p "$S/backend/gateway/server" "$C/ProjectSettings" "$C/Packages" "$WS2/rpg-mmo-server/backend"
touch "$S/backend/TEAM.md" "$S/backend/gateway/server/server.go" "$WS2/rpg-mmo-server/backend/TEAM.md"
printf 'm_EditorVersion: 6000.3.9f1\n' > "$C/ProjectSettings/ProjectVersion.txt"
printf '{\n  "dependencies": {\n    "com.cuvara.uitoolkit": "https://github.com/Cuvara/UIToolkit.git#v0.8.0"\n  }\n}\n' > "$C/Packages/manifest.json"
cp -R "$ROOT/tests/fixtures/ui-select-repo" "$U"
for r in "$S" "$C" "$U" "$WS2/rpg-mmo-server"; do
  git -C "$r" init -q -b develop && gitq "$r" add -A && gitq "$r" commit -qm init || { no "fixture repo $r"; }
done
gitq "$U" tag v0.8.0
export RPG_FACTORY_WORKSPACE="$WS"

# -- registry: exactly five tech skills with domain ui, scoped to client UI paths, used by client-integration
reg=$(jq -c '[.skills | to_entries[] | select(.value.kind == "tech" and .value.domain == "ui") | .key] | sort' "$ROOT/registry.json")
[ "$reg" = '["ui-component-selection","ui-figma-import","ui-orchestrator","ui-toolkit-screen","ui-validation"]' ] \
  && ok "registry: the five UI tech skills (domain ui)" || no "registry UI tech skills: $reg"
jq -e '[.skills | to_entries[] | select(.value.domain == "ui" and .value.kind == "tech") | .value]
  | all(.used_by == ["client-integration"] and (.paths | length > 0) and .repos == ["client"])' "$ROOT/registry.json" >/dev/null \
  && ok "registry: UI tech skills used_by client-integration, repo client, path-scoped" || no "registry UI tech skill fields"
for s in ui-orchestrator ui-component-selection ui-figma-import ui-toolkit-screen ui-validation; do
  [ -f "$ROOT/skills/$s/SKILL.md" ] || no "skills/$s/SKILL.md missing"
done

# -- routing: path-scoped routing.tech, lead unchanged; factory-core domain and server routing unchanged
UI5='["ui-orchestrator","ui-component-selection","ui-figma-import","ui-toolkit-screen","ui-validation"]'
route() { (cd "$WS" && bash "$CTX" --repo "$1" --json --paths "${@:2}" 2>/dev/null); }
for p in "Assets/Scripts/UI/X/X.uxml" "Assets/UI Toolkit/Theme/Game.uss" "Assets/Scripts/UI/Settings/SettingsPresenter.cs"; do
  route client "$p" | jq -e --argjson ui "$UI5" '.repos[0].routing | .lead == "client-integration" and ([.tech[] | select(startswith("ui-"))] == $ui)' >/dev/null \
    && ok "route client $p: lead client-integration, routing.tech lists the five UI skills in order" || no "route client $p: $(route client "$p" | jq -c '.repos[0].routing | {lead, tech}')"
done
route client Assets/Scripts/Session/MainSessionFlow.cs | jq -e '.repos[0].routing | .lead == "client-integration" and ([.tech[] | select(startswith("ui-"))] == [])' >/dev/null \
  && ok "route client MainSessionFlow.cs: no UI tech skill" || no "route MainSessionFlow.cs: $(route client Assets/Scripts/Session/MainSessionFlow.cs | jq -c '.repos[0].routing.tech')"
route server backend/gateway/server/server.go | jq -e '.repos[0].routing | .lead == "server-services" and ([.tech[] | select(startswith("ui-"))] == [])' >/dev/null \
  && ok "route server gateway: lead server-services, no UI tech skill" || no "route server gateway: $(route server backend/gateway/server/server.go | jq -c '.repos[0].routing')"
(cd "$WS" && bash "$CTX" --domain ui --json 2>/dev/null) | jq -e '.domain.lead == "ui-ux"' >/dev/null \
  && ok "route --domain ui: lead ui-ux" || no "route --domain ui lead"

# -- plan and selection engines
missing_engine=()
[ -f "$PLAN" ] || missing_engine+=("scripts/ui/ui_plan.py")
[ -f "$SELECT" ] || missing_engine+=("scripts/ui/ui_select.py")
if [ ${#missing_engine[@]} -gt 0 ]; then
  no "engine missing: ${missing_engine[*]} (plan and selection cases NOT_RUN)"
else
  python3 -B - "$ROOT" "$CMD" "$SELECT" "$WS" "$WS2" "$C" "$TMP/counts" <<'PY'
import json, os, re, subprocess, sys

root, cmd, select, ws, ws2, client, counts = sys.argv[1:8]
reg = json.load(open(os.path.join(root, "registry.json"), encoding="utf-8"))
UI = sorted(k for k, v in reg["skills"].items() if v.get("kind") == "tech" and v.get("domain") == "ui")
ENTRY = "ui-orchestrator"
VERBS = ("ui", "ui-figma", "ui-components", "ui-screen", "ui-review")
STATUS_RC = {"PLAN": 0, "NOT_UI": 0, "NEEDS_CONTEXT": 3}
res = {"pass": 0, "fail": 0}


def report(name, errs):
    key = "fail" if errs else "pass"
    res[key] += 1
    print(("FAIL  " if errs else "PASS  ") + name + ("" if not errs else ": " + "; ".join(errs)))


def run(argv, cwd):
    env = dict(os.environ, RPG_FACTORY_WORKSPACE=cwd)
    p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def plan(verb, request, args=(), cwd=ws, as_json=True):
    argv = [sys.executable, "-B", cmd, verb] + (["--json"] if as_json else []) + list(args) + ([request] if request else [])
    return run(argv, cwd)


def names(plan_obj):
    return [s.get("name") if isinstance(s, dict) else s for s in plan_obj.get("skills") or []]


cases = json.load(open(os.path.join(root, "tests", "fixtures", "ui-plan-cases.json"), encoding="utf-8"))["cases"]
seen = {"verbs": set(), "intents": set(), "not_ui": 0}
for c in cases:
    e = c["expect"]
    cwd = ws2 if c.get("workspace") == "no-client" else ws
    args = [a.replace("{client}", client) for a in c.get("args", [])]
    rc, out, err = plan(c["verb"], c["request"], args, cwd)
    errs = []
    try:
        p = json.loads(out)
    except ValueError:
        report(f"plan {c['id']}", [f"no JSON (rc={rc}): {(out or err)[:200]!r}"])
        continue
    seen["verbs"].add(c["verb"])
    got = names(p)
    if p.get("schema") != "rpg-factory.ui-plan/1":
        errs.append(f"schema={p.get('schema')!r}")
    if p.get("verb") != c["verb"]:
        errs.append(f"verb={p.get('verb')!r}")
    if p.get("status") != e["status"]:
        errs.append(f"status={p.get('status')!r} want {e['status']}")
    if rc != STATUS_RC.get(e["status"]):
        errs.append(f"exit {rc} want {STATUS_RC.get(e['status'])}")
    if "intent" in e:
        seen["intents"].add(e["intent"])
        if p.get("intent") != e["intent"]:
            errs.append(f"intent={p.get('intent')!r} want {e['intent']}")
    if "skills" in e and got != e["skills"]:
        errs.append(f"skills={got} want {e['skills']}")
    if ENTRY in got:
        errs.append("ui-orchestrator listed in skills (it is the entry)")
    if [s for s in got if s not in UI]:
        errs.append(f"not a registered domain-ui tech skill: {[s for s in got if s not in UI]}")
    if len(set(got)) == len(UI) - 1 and e.get("intent") != "figma-import":
        errs.append("every UI skill loaded outside figma-import")
    if e["status"] == "NOT_UI":
        seen["not_ui"] += 1
        if got:
            errs.append(f"NOT_UI loaded UI skills {got}")
    else:
        nl = p.get("not_loaded") or []
        for s in e.get("not_loaded_contains", []):
            if s not in nl:
                errs.append(f"not_loaded lacks {s}")
        if set(nl) & set(got):
            errs.append(f"skill both loaded and not_loaded: {sorted(set(nl) & set(got))}")
        if e["status"] == "PLAN" and sorted(set(got) | set(nl)) != sorted(s for s in UI if s != ENTRY):
            errs.append(f"skills + not_loaded != the four non-entry UI skills: {got} + {nl}")
    items = [m.get("item") for m in p.get("missing") or []]
    if "missing_items" in e and sorted(items) != sorted(e["missing_items"]):
        errs.append(f"missing={items} want {e['missing_items']}")
    for m in e.get("missing_contains", []):
        if m not in items:
            errs.append(f"missing lacks {m}")
    for m in e.get("missing_excludes", []):
        if m in items:
            errs.append(f"missing lists {m}")
    if e["status"] == "NEEDS_CONTEXT":
        if not items:
            errs.append("NEEDS_CONTEXT without missing items")
        if [m for m in p.get("missing") or [] if not (m.get("why") and m.get("how"))]:
            errs.append("a missing item lacks why/how")
    lead = (p.get("lead") or {}).get("skill")
    if "lead_skill" in e and lead != e["lead_skill"]:
        errs.append(f"lead={lead!r} want {e['lead_skill']}")
    ctx = p.get("context") or {}
    if "screen" in e and ctx.get("screen") != e["screen"]:
        errs.append(f"screen={ctx.get('screen')!r} want {e['screen']}")
    fig = ctx.get("figma") or {}
    if "figma_node_id" in e and fig.get("node_id") != e["figma_node_id"]:
        errs.append(f"node_id={fig.get('node_id')!r} want {e['figma_node_id']}")
    if "figma_file_key" in e and fig.get("file_key") != e["figma_file_key"]:
        errs.append(f"file_key={fig.get('file_key')!r} want {e['figma_file_key']}")
    if e["status"] == "PLAN" and "factory-core" not in ((p.get("next") or [""])[0]):
        errs.append("next[0] is not the factory-core step")
    report(f"plan {c['id']} [{c['verb']}] {c['request'][:60]!r}", errs)

all_intents = {"design", "figma-import", "figma-analyze", "figma-validate", "components", "screen",
               "integrate", "review", "troubleshoot", "analyze"}
report("matrix covers every verb, every intent, >= 8 NOT_UI, >= 40 cases",
       [x for x in [f"verbs {sorted(set(VERBS) - seen['verbs'])}" if set(VERBS) - seen["verbs"] else "",
                    f"intents {sorted(all_intents - seen['intents'])}" if all_intents - seen["intents"] else "",
                    f"NOT_UI {seen['not_ui']}" if seen["not_ui"] < 8 else "",
                    f"cases {len(cases)}" if len(cases) < 40 else ""] if x])

# determinism: the same request twice gives the same plan
a, b = plan("ui", "Create a settings screen.")[1], plan("ui", "Create a settings screen.")[1]
report("plan is deterministic (same request, same JSON)", [] if a and a == b else ["two runs differ"])
# Markdown (default) output: same exit codes, the next steps, not JSON
rc, out, _ = plan("ui", "Create a settings screen.", as_json=False)
errs = [] if rc == 0 else [f"exit {rc}"]
if out.lstrip().startswith("{"):
    errs.append("default output is JSON, want Markdown")
for w in ("factory-core", "ui-toolkit-screen"):
    if w not in out:
        errs.append(f"Markdown lacks {w}")
report("Markdown plan: exit 0, names factory-core and the skills", errs)
rc, out, _ = plan("ui", "Import this Figma screen into Unity.", as_json=False)
report("Markdown NEEDS_CONTEXT: exit 3, names figma-frame-url",
       [] if rc == 3 and "figma-frame-url" in out else [f"exit {rc}", out[:200]])
rc, out, _ = plan("ui", "Rotate the gateway TLS certificate.", as_json=False)
report("Markdown NOT_UI: exit 0, sends to factory-core directly",
       [] if rc == 0 and "not a ui request" in out.lower() and "factory-core" in out else [f"exit {rc}", out[:200]])
for verb in VERBS:
    rc, _, err = plan(verb, "")
    report(f"usage error: {verb} without a request -> exit 2", [] if rc == 2 else [f"exit {rc}"])

# -- component selection (UIToolkit fixture at v0.8.0, client pinned to it)
sel_cases = json.load(open(os.path.join(root, "tests", "fixtures", "ui-select-cases.json"), encoding="utf-8"))


def selections(obj):
    out = []
    if isinstance(obj, dict):
        if "need" in obj and "status" in obj:
            out.append(obj)
        for v in obj.values():
            out += selections(v)
    elif isinstance(obj, list):
        for v in obj:
            out += selections(v)
    return out


def select_run(flag, value, cwd=ws):
    rc, out, err = run([sys.executable, "-B", select, flag, value, "--json"], cwd)
    try:
        return rc, json.loads(out), out
    except ValueError:
        return rc, None, out or err


for c in sel_cases["needs"]:
    rc, obj, raw = select_run("--need", c["need"])
    if obj is None:
        report(f"select need {c['id']}", [f"no JSON (rc={rc}): {raw[:200]!r}"])
        continue
    sels = selections(obj)
    errs = [] if len(sels) == 1 else [f"{len(sels)} selections for one need"]
    for s in sels:
        choice = json.dumps(s.get("choice"), ensure_ascii=False)
        if s["status"] not in c["status_in"]:
            errs.append(f"status={s['status']!r} want {c['status_in']}")
        for pat in c.get("choice_contains", []):
            if not re.search(pat, choice):
                errs.append(f"choice {choice[:120]} lacks {pat}")
        if s["status"] == "missing":
            if s.get("owner_if_missing") not in c.get("owner_in", ["unity-package", "client-integration"]):
                errs.append(f"owner_if_missing={s.get('owner_if_missing')!r}")
            if s.get("choice"):
                errs.append(f"missing need has a choice {choice[:80]}")
        elif not s.get("evidence"):
            errs.append("no evidence for a selection")
    report(f"select need {c['id']}: {c['need']!r}", errs)

for c in sel_cases["screens"]:
    rc, obj, raw = select_run("--screen", c["screen"])
    if obj is None:
        report(f"select screen {c['id']}", [f"no JSON (rc={rc}): {raw[:200]!r}"])
        continue
    sels = selections(obj)
    blob = json.dumps([s.get("choice") for s in sels], ensure_ascii=False)
    errs = [f"choices lack {p}" for p in c["choices_contain"] if not re.search(p, blob)]
    errs += [f"need {s['need']!r} missing in a recipe" for s in sels if s["status"] == "missing"]
    if not sels:
        errs.append("no selections")
    report(f"select screen {c['id']}: reuse/configure/compose, nothing missing", errs)

errs = []
for need in sel_cases["never_missing"]:
    rc, obj, raw = select_run("--need", need)
    if obj is None or any(s["status"] == "missing" for s in selections(obj)) or not selections(obj):
        errs.append(need)
report("never duplicate: an existing component is never 'missing'", [f"missing or no selection: {errs}"] if errs else [])

rc, obj, raw = select_run("--need", "confirmation popup")
blob = json.dumps(selections(obj) if obj is not None else raw)
report("selection evidence cites Runtime/Flow/ConfirmDialog.cs at v0.8.0",
       [] if "ConfirmDialog.cs" in blob and "v0.8.0" in blob else [blob[:200]])
rc, obj, raw = select_run("--need", "toast", cwd=ws2)
report("no UIToolkit repo: NOT_AVAILABLE, no invented selection",
       [] if "NOT_AVAILABLE" in raw and not [s for s in selections(obj or {}) if s["status"] != "missing"] else [raw[:200]])

with open(counts, "w", encoding="utf-8", newline="\n") as f:
    f.write(f"{res['pass']} {res['fail']}\n")
PY
  if read -r p f < "$TMP/counts" 2>/dev/null; then pass=$((pass + p)); fail=$((fail + f)); else no "plan/selection runner crashed"; fi
fi
[ -z "$(git -C "$C" status --porcelain)" ] && [ -z "$(git -C "$U" status --porcelain)" ] \
  && ok "read-only: fixture client and UIToolkit repos untouched" || no "fixture repos changed"
total=$((pass + fail)); echo "ui-skill-routing tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
