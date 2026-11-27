#!/usr/bin/env bash
# VFX production helpers: the vfx-style profile schema and the capture mirror, scripts/vfx/vfx_style.py show and
# lint (every rule PASS, FAIL and NOT_AVAILABLE, exit codes 0, 1, 2, 3; fixtures and their table in
# tests/fixtures/vfx/lint/CASES.md), scripts/vfx/vfx_plan.py (PLAN, NOT_VFX, NEEDS_CONTEXT, the five steps, step
# states, and that it writes nothing), the VFX Graph text adapter scripts/adapters/vfx/vfxgraph.py, and that the
# scripts need no network and no Unity (no socket, no subprocess).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

STYLE="$ROOT/scripts/vfx/vfx_style.py"; PLAN="$ROOT/scripts/vfx/vfx_plan.py"
ADAPTER="$ROOT/scripts/adapters/vfx/vfxgraph.py"
FX="$ROOT/tests/fixtures/vfx"; L="$FX/lint"; PROFILE="$FX/style/profile.json"; PROFILE_MD="$FX/style/profile.md"
RULES="recipe-schema,vfx-graph-version,timing-sum,timing-ratios,hdr-intensity,palette,texture-size,texture-flipbook-grid,texture-color-space,output-type,blend-mode,shader,budget-capacity,budget-systems,budget-texture-memory,budget-alive,capture-conditions,recipe-hash,spec-match"

# Every Python run of the scripts goes through a sitecustomize that makes any socket or subprocess use fail:
# a script that reaches the network or launches Unity (or any other program) errors instead of passing.
NONET="$TMP/nonet"; mkdir -p "$NONET"
cat > "$NONET/sitecustomize.py" <<'PY'
import socket, subprocess
def _blocked(*a, **k):
    raise RuntimeError("vfx-production suite: network and subprocess use are blocked")
socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
subprocess.Popen.__init__ = _blocked
PY
export PYTHONPATH="$NONET"
py() { python3 -B "$@"; }

# Snapshot of everything the scripts could write into: the fixtures, the scripts' own folders and the state dir.
snapshot() {
  python3 -B - "$ROOT" "$RPG_FACTORY_STATE_DIR" <<'PY'
import hashlib, os, sys
root, state = sys.argv[1], sys.argv[2]
for top in (os.path.join(root, "tests", "fixtures", "vfx"), os.path.join(root, "scripts", "vfx"),
            os.path.join(root, "scripts", "adapters", "vfx"), os.path.join(root, "scripts", "lib"), state):
    for d, dirs, files in os.walk(top):
        dirs.sort()
        for n in sorted(files) + [x + "/" for x in dirs]:
            p = os.path.join(d, n.rstrip("/"))
            h = hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else "dir"
            print(os.path.relpath(p, root).replace(os.sep, "/"), h)
PY
}
snapshot > "$TMP/before.txt"

# -- sandbox: the blocker is active
# (output captured first: under pipefail the probe's own non-zero exit would fail a `| grep -q` pipeline)
probe_net=$(py -c 'import socket; socket.create_connection(("127.0.0.1", 9))' 2>&1)
probe_sub=$(py -c 'import subprocess; subprocess.run(["git", "--version"])' 2>&1)
if [[ "$probe_net" == *"network and subprocess use are blocked"* && "$probe_sub" == *"network and subprocess use are blocked"* ]]; then
  ok "sandbox: socket and subprocess use fail in every script run"
else no "sandbox: the sitecustomize blocker is not active (PYTHONPATH=$NONET)"; fi
bad_imports=$(grep -nE '^\s*(import|from)\s+(socket|subprocess|urllib|http|requests|ssl|ftplib|asyncio)\b' \
  "$STYLE" "$ROOT/scripts/vfx/vfx_lint_rules.py" "$PLAN" "$ADAPTER")
[ -z "$bad_imports" ] && ok "no network or subprocess module imported by vfx_style, vfx_lint_rules, vfx_plan, vfxgraph" \
  || no "network or subprocess import: $bad_imports"

# -- schemas: the fixture profile validates against the vfx-style schema, the stats against the capture mirror
py - "$ROOT" <<'PY' > "$TMP/schema.txt" 2>&1
import importlib.util, json, re, sys
root = sys.argv[1]
spec = importlib.util.spec_from_file_location("artifact_lint", root + "/scripts/checks/artifact-lint.py")
al = importlib.util.module_from_spec(spec); spec.loader.exec_module(al)
try:
    import jsonschema
except ImportError:
    jsonschema = None
def load(p):
    t = open(p, encoding="utf-8").read()
    m = re.match(r"\A---json\s*\n(.*?)\n---", t, re.S)
    return json.loads(m.group(1) if m else t)
def errors(obj, schema_path):
    schema = json.load(open(schema_path, encoding="utf-8"))
    errs = al.schema_errors(obj, schema, schema)
    if jsonschema is not None:
        errs += ["jsonschema: " + e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(obj)]
    return errs
style = root + "/docs/schemas/kinds/vfx-style.schema.json"
capture = root + "/docs/schemas/vfx-capture.schema.json"
fx = root + "/tests/fixtures/vfx"
profile = load(fx + "/style/profile.json")
cases = [
    ("profile.json validates against vfx-style.schema.json", errors(profile, style) == []),
    ("profile.md spec validates against vfx-style.schema.json", errors(load(fx + "/style/profile.md")["spec"], style) == []),
    ("plan fixture vfx-style artifacts validate against vfx-style.schema.json",
     all(errors(load(fx + "/plan/%s/authoring/vfx/style/vfx-style.md" % c)["spec"], style) == [] for c in ("done", "style-only"))),
]
broken = json.loads(json.dumps(profile)); del broken["budgets"]
cases.append(("vfx-style schema rejects a profile without budgets", errors(broken, style) != []))
broken = json.loads(json.dumps(profile)); broken["bogus"] = 1
cases.append(("vfx-style schema rejects an unknown top-level field", errors(broken, style) != []))
broken = json.loads(json.dumps(profile)); broken["palette"]["elements"]["fire"]["colors"]["ember_core"] = "orange"
cases.append(("vfx-style schema rejects a palette colour that is not #RRGGBB", errors(broken, style) != []))
stats = [fx + "/lint/good.stats.json", fx + "/lint/bad-budget-alive.stats.json", fx + "/lint/bad-capture-conditions.stats.json",
         fx + "/lint/bad-recipe-hash.stats.json", fx + "/vfxgraph/Captures/Sparks/stats.json",
         fx + "/plan/done/project/Captures/FireBolt/seed-1234-gameplay-dusk/stats.json"]
bad = [p for p in stats if errors(load(p), capture)]
cases.append(("every fixture stats.json validates against the vfx-capture mirror", not bad))
broken = load(stats[0]); broken["schema"] = "cuvara.vfx-capture/2"
cases.append(("vfx-capture mirror rejects another schema id", errors(broken, capture) != []))
for label, good in cases:
    print(("PASS " if good else "FAIL ") + label)
if bad: print("  not valid:", bad, [errors(load(p), capture)[:3] for p in bad])
print("validator: artifact-lint schema_errors" + (" + jsonschema Draft 2020-12" if jsonschema else " (jsonschema not installed)"))
PY
while IFS= read -r line; do
  case "$line" in "PASS "*) ok "${line#PASS }" ;; "FAIL "*) no "${line#FAIL }" ;; *) echo "      $line" ;; esac
done < "$TMP/schema.txt"
grep -qE '^(PASS|FAIL) ' "$TMP/schema.txt" || no "schema checks did not run: $(head -c 300 "$TMP/schema.txt")"

# -- vfx_style.py show
run() { rm -f "$TMP/o.json" "$TMP/err"; py "$@" > "$TMP/o.json" 2>"$TMP/err"; }
q() { jq -r "$1" "$TMP/o.json"; }
run "$STYLE" show --style "$PROFILE"; rc=$?
[ $rc -eq 0 ] && [ "$(q '.schema')" = rpg-factory.vfx-style/1 ] && [ "$(q '.artifact')" = null ] \
  && [ "$(q '.profile.assetgen_style + " " + .profile.vfx_graph')" = "realistic-pbr 17.6" ] \
  && [ "$(q '.profile.timing.sum_tolerance_seconds')" = 0.05 ] \
  && ok "show: profile.json resolves (rpg-factory.vfx-style/1, no artifact, its own sum tolerance kept)" \
  || no "show profile.json: rc=$rc $(head -c 300 "$TMP/o.json") $(head -c 200 "$TMP/err")"
q '.profile' > "$TMP/profile-json.txt"
run "$STYLE" show --style "$PROFILE_MD"; rc=$?
[ $rc -eq 0 ] && [ "$(q '.artifact.id + " " + .artifact.kind + " " + .artifact.status')" = "VFX-style-001 vfx-style approved" ] \
  && [ "$(q '.artifact.binding_values')" = true ] && ok "show: profile.md artifact summary (id, kind, status, binding_values)" \
  || no "show profile.md: rc=$rc $(q .artifact) $(head -c 200 "$TMP/err")"
q '.profile' > "$TMP/profile-md.txt"
cmp -s "$TMP/profile-json.txt" "$TMP/profile-md.txt" && ok "show: profile.md resolves to the same profile as profile.json" \
  || no "show: profile.md and profile.json differ: $(diff "$TMP/profile-json.txt" "$TMP/profile-md.txt" | head -5)"
jq 'del(.timing.sum_tolerance_seconds, .textures.linear_textures, .textures.channel_packing)' "$PROFILE" > "$TMP/defaults.json"
run "$STYLE" show --style "$TMP/defaults.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q '.profile.timing.sum_tolerance_seconds')" = 0.01 ] \
  && [ "$(q '.profile.textures.linear_textures | tojson')" = '[]' ] && [ "$(q '.profile.textures.channel_packing | tojson')" = '{}' ] \
  && ok "show: defaults filled in (sum_tolerance_seconds 0.01, linear_textures [], channel_packing {})" \
  || no "show defaults: rc=$rc $(q '.profile.timing') $(head -c 200 "$TMP/err")"
cmp -s "$PROFILE" "$FX/style/profile.json" && [ "$(jq -r '.timing.sum_tolerance_seconds' "$PROFILE")" = 0.05 ] \
  && ok "show: the profile file is left unchanged" || no "show changed the profile"
jq 'del(.budgets)' "$PROFILE" > "$TMP/nobudget.json"
run "$STYLE" show --style "$TMP/nobudget.json"; rc=$?
[ $rc -eq 3 ] && grep -q 'missing or malformed: budgets' "$TMP/err" && ok "show: a profile without budgets exits 3 and names budgets" \
  || no "show without budgets: rc=$rc $(head -c 200 "$TMP/err")"

# -- vfx_style.py lint: the good effect, every rule PASS
lint() { run "$STYLE" lint --style "$PROFILE" "$@"; }
ids_in() { q "[.rows[] | select(.state == \"$1\") | .id] | join(\",\")"; }
lint --recipe "$L/good.vfxrecipe.json" --inspect "$L/good.inspect.json" --stats "$L/good.stats.json" --spec "$L/good.vfx-spec.md"; rc=$?
[ $rc -eq 0 ] && [ "$(q .schema)" = rpg-factory.vfx-lint/1 ] && [ "$(q .status)" = PASS ] \
  && ok "lint good, all inputs: exit 0, rpg-factory.vfx-lint/1, status PASS" || no "lint good: rc=$rc status=$(q .status) $(head -c 200 "$TMP/err")"
[ "$(q 'keys_unsorted | join(",")')" = "schema,effect,style,inputs,element,tier,status,counts,rows" ] \
  && ok "lint JSON has the rpg-factory.vfx-lint/1 keys in order" || no "lint keys: $(q 'keys_unsorted')"
[ "$(q '[.rows[].id] | join(",")')" = "$RULES" ] && ok "lint: one row per rule, the 19 rule ids in order" \
  || no "lint rule ids: $(q '[.rows[].id] | join(",")')"
[ "$(ids_in PASS)" = "$RULES" ] && [ "$(q '.counts | tojson')" = '{"PASS":19,"FAIL":0,"WARN":0,"NOT_AVAILABLE":0}' ] \
  && ok "lint good: PASS case of all 19 rules (counts 19 PASS)" || no "lint good: not PASS: $(q '[.rows[] | select(.state != "PASS") | .id]') counts $(q .counts)"
[ "$(q '[.rows[] | select((.evidence | type) == "array" and (.evidence | length) > 0 and all(.evidence[]; type == "string"))] | length')" = 19 ] \
  && ok "lint: every row carries a list of evidence strings" || no "lint evidence shape"
[ "$(q '.effect + " " + .element + " " + .tier')" = "fire-burst fire primary" ] && ok "lint: effect, element and tier from recipe meta.tags" \
  || no "lint effect/element/tier: $(q '[.effect,.element,.tier]')"

# NOT_AVAILABLE when an optional input is absent; the recipe fallback rules say so
lint --recipe "$L/good.vfxrecipe.json"; rc=$?
NA="texture-size,texture-color-space,shader,budget-texture-memory,budget-alive,capture-conditions,recipe-hash,spec-match"
[ $rc -eq 0 ] && [ "$(ids_in NOT_AVAILABLE)" = "$NA" ] && [ "$(q '.counts.PASS')" = 11 ] && [ "$(q '.status')" = PASS ] \
  && ok "lint recipe only: 11 PASS, NOT_AVAILABLE for the 8 rules whose input is absent" \
  || no "lint recipe only: rc=$rc NA=$(ids_in NOT_AVAILABLE) counts=$(q .counts)"
[ "$(q '[.rows[] | select(.id == ("hdr-intensity","output-type","blend-mode","budget-capacity","budget-systems")) | select(.state == "PASS" and any(.evidence[]; test("recipe")))] | length')" = 5 ] \
  && ok "lint recipe only: hdr-intensity, output-type, blend-mode, budget-capacity, budget-systems fall back to the recipe" \
  || no "lint fallback evidence: $(q '[.rows[] | select(.id == ("hdr-intensity","output-type","blend-mode","budget-capacity","budget-systems")) | [.id,.state,.evidence[0]]]')"
lint --recipe "$L/good.vfxrecipe.json" --inspect "$L/good.inspect.json"; rc=$?
[ $rc -eq 0 ] && [ "$(ids_in NOT_AVAILABLE)" = "budget-alive,capture-conditions,spec-match" ] \
  && ok "lint without --stats and --spec: budget-alive, capture-conditions, spec-match NOT_AVAILABLE" \
  || no "lint recipe+inspect: rc=$rc NA=$(ids_in NOT_AVAILABLE)"
lint --recipe "$L/good.vfxrecipe.json" --stats "$L/good.stats.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q '[.rows[] | select(.id == ("budget-alive","capture-conditions","recipe-hash")) | .state] | join(",")')" = "PASS,PASS,PASS" ] \
  && ok "lint with --stats alone: budget-alive, capture-conditions, recipe-hash graded from the capture" \
  || no "lint recipe+stats: rc=$rc $(q '[.rows[] | select(.state != "PASS") | [.id,.state]]')"
run "$STYLE" lint --style "$PROFILE_MD" --recipe "$L/good.vfxrecipe.json" --inspect "$L/good.inspect.json" --stats "$L/good.stats.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q '.counts.PASS')" = 18 ] && [ "$(ids_in NOT_AVAILABLE)" = spec-match ] && [ "$(q '.style.artifact.id')" = VFX-style-001 ] \
  && ok "lint with the artifact profile (profile.md): 18 PASS, spec-match NOT_AVAILABLE, style artifact named" \
  || no "lint profile.md: rc=$rc counts=$(q .counts) artifact=$(q .style.artifact.id)"

# WARN: a recipe without vfx_graph warns, status WARN, exit 0
jq -c 'del(.vfx_graph)' "$L/good.vfxrecipe.json" > "$TMP/nograph.vfxrecipe.json"
lint --recipe "$TMP/nograph.vfxrecipe.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q .status)" = WARN ] && [ "$(ids_in WARN)" = vfx-graph-version ] && [ "$(q '.counts.WARN')" = 1 ] \
  && ok "lint: a recipe without vfx_graph is WARN on vfx-graph-version, status WARN, exit 0" \
  || no "lint WARN: rc=$rc status=$(q .status) WARN=$(ids_in WARN)"

# FAIL case of every rule: each bad fixture breaks exactly the named rule (CASES.md "Bad cases")
G_R="$L/good.vfxrecipe.json"; G_I="$L/good.inspect.json"
BAD=(
  "bad-recipe-schema.vfxrecipe.json recipe recipe-schema"
  "bad-vfx-graph-version.vfxrecipe.json recipe vfx-graph-version"
  "bad-vfx-graph-version-unparsable.vfxrecipe.json recipe vfx-graph-version"
  "bad-timing-sum.vfxrecipe.json recipe timing-sum"
  "bad-timing-ratios.vfxrecipe.json recipe timing-ratios"
  "bad-hdr-intensity.vfxrecipe.json recipe hdr-intensity"
  "bad-palette.vfxrecipe.json recipe palette"
  "bad-texture-flipbook-grid.vfxrecipe.json recipe texture-flipbook-grid"
  "bad-blend-mode.vfxrecipe.json recipe blend-mode"
  "bad-output-type.vfxrecipe.json recipe output-type"
  "bad-budget-capacity.vfxrecipe.json recipe budget-capacity"
  "bad-hdr-intensity.inspect.json inspect hdr-intensity"
  "bad-texture-size.inspect.json inspect texture-size"
  "bad-texture-color-space.inspect.json inspect texture-color-space"
  "bad-output-type.inspect.json inspect output-type"
  "bad-blend-mode.inspect.json inspect blend-mode"
  "bad-shader.inspect.json inspect shader"
  "bad-budget-capacity.inspect.json inspect budget-capacity"
  "bad-budget-systems.inspect.json inspect budget-systems"
  "bad-budget-texture-memory.inspect.json inspect budget-texture-memory"
  "bad-budget-alive.stats.json stats budget-alive"
  "bad-capture-conditions.stats.json stats capture-conditions"
  "bad-recipe-hash.stats.json stats recipe-hash"
  "bad-spec-match.vfx-spec.md spec spec-match"
)
failed_rules=","
for c in "${BAD[@]}"; do
  read -r file mode rule <<< "$c"
  case "$mode" in
    recipe)  lint --recipe "$L/$file" ;;
    inspect) lint --recipe "$G_R" --inspect "$L/$file" ;;
    stats)   lint --recipe "$G_R" --inspect "$G_I" --stats "$L/$file" ;;
    spec)    lint --recipe "$G_R" --spec "$L/$file" ;;
  esac; rc=$?
  if [ $rc -eq 1 ] && [ "$(q .status)" = FAIL ] && [ "$(ids_in FAIL)" = "$rule" ] && [ "$(q '.counts.FAIL')" = 1 ]; then
    ok "lint FAIL $rule: $file (exit 1, only $rule FAILs)"; failed_rules="$failed_rules$rule,"
  else no "lint FAIL $rule: $file rc=$rc FAIL=$(ids_in FAIL) WARN=$(ids_in WARN) $(head -c 200 "$TMP/err")"; fi
done
missing_fail=""
for r in ${RULES//,/ }; do case "$failed_rules" in *",$r,"*) ;; *) missing_fail="$missing_fail $r" ;; esac; done
[ -z "$missing_fail" ] && ok "every one of the 19 lint rules has a PASS case and a FAIL case" || no "rules without a FAIL case:$missing_fail"
lint --recipe "$L/bad-vfx-graph-version-unparsable.vfxrecipe.json"
q '[.rows[] | select(.id == "vfx-graph-version") | .evidence[0]] | .[0]' | grep -q "'latest' is not a major.minor version" \
  && ok "lint: an unparsable recipe vfx_graph is a FAIL that says so (never PASS by None == None)" \
  || no "lint unparsable vfx_graph evidence: $(q '[.rows[] | select(.id == "vfx-graph-version")]')"

# Edge: an output event context (VFXOutputEvent) renders nothing and is not graded as an output
lint --recipe "$L/edge-output-event.vfxrecipe.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q .status)" = PASS ] \
  && [ "$(q '[.rows[] | select(.id == ("output-type","blend-mode")) | .state + ":" + (.evidence[1:] | join(";"))] | join(",")')" = "PASS:output: VFXPlanarPrimitiveOutput,PASS:output: Additive" ] \
  && ok "lint: a VFXOutputEvent context is not an output (output-type and blend-mode grade only the render output)" \
  || no "lint output event: rc=$rc status=$(q .status) $(q '[.rows[] | select(.id == ("output-type","blend-mode"))]')"

# -- exit 3: a required input missing, unreadable or not of its format
exit3() {  # exit3 <label> <grep pattern for stderr> -- <vfx_style args...>
  local label=$1 pat=$2; shift 3
  run "$STYLE" "$@"; local rc=$?
  if [ $rc -eq 3 ] && [ ! -s "$TMP/o.json" ] && grep -qE "$pat" "$TMP/err"; then ok "exit 3: $label"
  else no "exit 3: $label rc=$rc err=$(head -c 200 "$TMP/err")"; fi
}
exit3 "recipe file missing" 'recipe .*cannot read' -- lint --style "$PROFILE" --recipe "$TMP/missing.json"
exit3 "style file missing" 'style .*cannot read' -- lint --style "$TMP/missing.json" --recipe "$G_R"
exit3 "style is not a profile (a recipe)" 'not a vfx-style profile' -- lint --style "$G_R" --recipe "$G_R"
exit3 "--stats with another schema id (an inspect file)" 'stats .*schema is' -- lint --style "$PROFILE" --recipe "$G_R" --stats "$G_I"
exit3 "--inspect with another schema id (a stats file)" 'inspect .*schema is' -- lint --style "$PROFILE" --recipe "$G_R" --inspect "$L/good.stats.json"
exit3 "--spec of another kind (a vfx-style artifact)" 'spec .*kind is' -- lint --style "$PROFILE" --recipe "$G_R" --spec "$PROFILE_MD"
exit3 "--style of another kind (a vfx-spec artifact)" 'style .*kind is' -- lint --style "$L/good.vfx-spec.md" --recipe "$G_R"
printf 'not json {' > "$TMP/garbage.vfxrecipe.json"
exit3 "recipe is not JSON" 'recipe .*not JSON' -- lint --style "$PROFILE" --recipe "$TMP/garbage.vfxrecipe.json"
exit3 "show: style file missing" 'style .*cannot read' -- show --style "$TMP/missing.json"
exit3 "style with an unparsable vfx_graph" "missing or malformed: vfx_graph \('latest' is not a major.minor version\)" \
  -- lint --style "$L/bad-profile-vfx-graph.style.json" --recipe "$G_R"
exit3 "style whose palette ramp names a colour not in its element's colors" \
  'missing or malformed: palette.elements.fire.ramp \(names not in its colors: ember_glow\)' \
  -- lint --style "$L/bad-profile-ramp.style.json" --recipe "$G_R"
exit3 "show: style whose palette ramp names an unknown colour" 'palette.elements.fire.ramp' -- show --style "$L/bad-profile-ramp.style.json"

# -- exit 2: usage
exit2() {  # exit2 <label> -- <vfx_style args...>
  local label=$1; shift 2
  run "$STYLE" "$@"; local rc=$?
  if [ $rc -eq 2 ] && [ ! -s "$TMP/o.json" ] && grep -q 'Usage:' "$TMP/err"; then ok "exit 2: $label"
  else no "exit 2: $label rc=$rc err=$(head -c 200 "$TMP/err")"; fi
}
exit2 "no command" --
exit2 "unknown command" -- grade --style "$PROFILE"
exit2 "unknown option" -- lint --style "$PROFILE" --recipe "$G_R" --budget x
exit2 "option without a value" -- lint --style "$PROFILE" --recipe
exit2 "option followed by another option" -- lint --style --recipe "$G_R"
exit2 "option given twice" -- lint --style "$PROFILE" --recipe "$G_R" --recipe "$G_R"
exit2 "lint without --recipe" -- lint --style "$PROFILE"
exit2 "show without --style" -- show
exit2 "show with a lint option" -- show --style "$PROFILE" --recipe "$G_R"
run "$STYLE" --help; rc=$?
[ $rc -eq 0 ] && grep -q 'Usage:' "$TMP/o.json" && ok "--help prints the usage, exit 0" || no "--help: rc=$rc"

# -- vfx_plan.py
P="$FX/plan"
plan() { rm -f "$TMP/o.json" "$TMP/err"; py "$PLAN" "$@" > "$TMP/o.json" 2>"$TMP/err"; }
steps() { q '[.steps[] | .id + "=" + .state] | join(",")'; }
plan --json --effect fire-bolt --root "$P/done/authoring" --project "$P/done/project"; rc=$?
[ $rc -eq 0 ] && [ "$(q .schema)" = rpg-factory.vfx-plan/1 ] && [ "$(q .status)" = PLAN ] && [ "$(q .effect)" = fire-bolt ] \
  && ok "plan done: exit 0, rpg-factory.vfx-plan/1, PLAN, effect fire-bolt" || no "plan done: rc=$rc status=$(q .status) $(head -c 200 "$TMP/err")"
[ "$(q 'keys_unsorted | join(",")')" = "schema,request,status,effect,context,steps,current_step,missing,lead,next" ] \
  && ok "plan JSON has the rpg-factory.vfx-plan/1 keys in order" || no "plan keys: $(q 'keys_unsorted')"
[ "$(q '[.steps[] | (.n | tostring) + ":" + .id] | join(",")')" = "1:style,2:textures,3:recipe,4:capture,5:record" ] \
  && [ "$(q '[.steps[] | select((.title | length) > 5 and (.action | length) > 10 and (.lead | length) > 0 and (.evidence | length) > 0)] | length')" = 5 ] \
  && ok "plan: the five steps in order, each with title, state, evidence, lead and action" || no "plan steps: $(q '[.steps[] | [.n,.id]]')"
[ "$(steps)" = "style=DONE,textures=DONE,recipe=DONE,capture=DONE,record=DONE" ] && [ "$(q .current_step)" = null ] && [ "$(q '.missing | length')" = 0 ] \
  && ok "plan done: every step DONE, no current step, nothing missing" || no "plan done steps: $(steps) current=$(q .current_step)"
[ "$(q '.lead.skill + " " + (.lead.route | join(" "))')" = "vfx --domain vfx" ] && [ "$(q '[.steps[].lead] | join(",")')" = "vfx,asset-gen,vfx,vfx,vfx" ] \
  && ok "plan: lead route vfx --domain vfx; textures step led by asset-gen" || no "plan lead: $(q .lead) $(q '[.steps[].lead]')"
[ "$(q '.context.style.id + " " + .context.spec.id + " " + .context.asset.id + " " + .context.gen_runs[0].id')" = "VFX-style-001 VFX-spec-001 VFX-asset-001 AGEN-fire-bolt-glow-001" ] \
  && [ "$(q '.context.recipe.path + " " + .context.built_asset.path')" = "Effects/FireBolt/FireBolt.vfxrecipe.json Effects/FireBolt/FireBolt.vfx" ] \
  && ok "plan done: context names the profile, spec, record, gen-run, recipe and built asset" || no "plan context: $(q '.context | tojson' | head -c 300)"
q '.next[0]' | grep -q '^invoke rpg-factory:factory-core and Route with: factory-context.sh --domain vfx$' \
  && ok "plan next: factory-core first with the lead route" || no "plan next: $(q .next)"

plan --json --effect fire-bolt --root "$P/style-only/authoring" --project "$P/style-only/project"; rc=$?
[ $rc -eq 0 ] && [ "$(q .status)" = PLAN ] && [ "$(steps)" = "style=DONE,textures=TODO,recipe=TODO,capture=TODO,record=TODO" ] \
  && [ "$(q .current_step)" = textures ] && ok "plan style-only: style DONE, the rest TODO, current step textures" \
  || no "plan style-only: rc=$rc $(steps) current=$(q .current_step)"
plan --json --effect fire-bolt --root "$P/empty/authoring" --project "$P/empty/project"; rc=$?
[ $rc -eq 0 ] && [ "$(q .status)" = PLAN ] && [ "$(steps)" = "style=TODO,textures=TODO,recipe=TODO,capture=TODO,record=TODO" ] \
  && [ "$(q .current_step)" = style ] && ok "plan empty: every step TODO, current step style" \
  || no "plan empty: rc=$rc $(steps) current=$(q .current_step)"
plan --effect fire-bolt --root "$P/style-only/authoring" --project "$P/style-only/project"; rc=$?
[ $rc -eq 0 ] && grep -q '^\*\*Status: PLAN\*\* - effect `fire-bolt`$' "$TMP/o.json" \
  && [ "$(grep -cE '^[1-5]\. \*\*' "$TMP/o.json")" = 5 ] && grep -q 'Texture gen-runs approved\*\* - TODO' "$TMP/o.json" \
  && ok "plan Markdown: status line and the five numbered steps" || no "plan Markdown: rc=$rc $(head -c 300 "$TMP/o.json")"

plan --json "$(cat "$P/not-vfx/request.txt")"; rc=$?
[ $rc -eq 0 ] && [ "$(q .status)" = NOT_VFX ] && [ "$(q '.steps | length')" = 0 ] && [ "$(q .lead)" = null ] \
  && ok "plan NOT_VFX: a Nakama request has no VFX signal (exit 0, no steps, no lead)" || no "plan NOT_VFX: rc=$rc status=$(q .status)"
plan --json "add a fire effect to the fireball spell" --root "$P/empty/authoring" --project "$P/empty/project"; rc=$?
[ $rc -eq 3 ] && [ "$(q .status)" = NEEDS_CONTEXT ] && [ "$(q '[.missing[].item] | join(",")')" = effect-id ] \
  && q '.next[0]' | grep -q '^ask the user for exactly: effect-id' \
  && ok "plan NEEDS_CONTEXT: a VFX request without an effect id (exit 3, missing effect-id, ask for exactly it)" \
  || no "plan NEEDS_CONTEXT effect-id: rc=$rc status=$(q .status) missing=$(q '[.missing[].item]')"
plan --json --effect fire-bolt --root "$P/empty/authoring"; rc=$?
[ $rc -eq 3 ] && [ "$(q .status)" = NEEDS_CONTEXT ] && [ "$(q '[.missing[].item] | join(",")')" = project ] \
  && ok "plan NEEDS_CONTEXT: no --project is never guessed (missing project)" || no "plan no project: rc=$rc missing=$(q '[.missing[].item]')"
plan --json --effect fire-bolt --root "$TMP/no-such-root" --project "$TMP/no-such-project"; rc=$?
[ $rc -eq 3 ] && [ "$(q '[.missing[].item] | join(",")')" = "authoring-root,project" ] \
  && ok "plan NEEDS_CONTEXT: a --root and --project that are not directories" || no "plan bad dirs: rc=$rc missing=$(q '[.missing[].item]')"
plan --json --effect fire-bolt --root "$P/done/authoring" --project "$P/done/project" --style "$TMP/missing-style.md"; rc=$?
[ $rc -eq 3 ] && [ "$(q '[.missing[].item] | join(",")')" = style-profile ] \
  && ok "plan NEEDS_CONTEXT: a --style that cannot be read (missing style-profile)" || no "plan bad style: rc=$rc missing=$(q '[.missing[].item]')"

for args in "" "--json" "--effect" "--json --bogus x fire effect"; do
  plan $args; rc=$?
  [ $rc -eq 2 ] && [ ! -s "$TMP/o.json" ] && ok "plan usage exit 2: '${args:-no arguments}'" || no "plan usage '${args}': rc=$rc $(head -c 200 "$TMP/err")"
done

# Step states beyond DONE and TODO, on a copy of the done fixture (the fixture itself stays untouched).
W="$TMP/work"; mkdir -p "$W"; cp -R "$P/done" "$W/done"
wplan() { plan --json --effect fire-bolt --root "$W/done/authoring" --project "$W/done/project"; }
REC="$W/done/project/Effects/FireBolt/FireBolt.vfxrecipe.json"; cp "$REC" "$TMP/recipe.bak"
printf ' ' >> "$REC"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[3].state')" = STALE ] && [ "$(q .current_step)" = capture ] \
  && ok "plan: a recipe edited after its capture makes the capture step STALE" || no "plan stale capture: rc=$rc $(steps)"
cp "$TMP/recipe.bak" "$REC"; mv "$W/done/project/Effects/FireBolt/FireBolt.vfx" "$TMP/FireBolt.vfx.bak"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[2].state')" = IN_PROGRESS ] && [ "$(q .current_step)" = recipe ] \
  && ok "plan: a recipe without its built .vfx makes the recipe step IN_PROGRESS" || no "plan unbuilt recipe: rc=$rc $(steps)"
mv "$TMP/FireBolt.vfx.bak" "$W/done/project/Effects/FireBolt/FireBolt.vfx"
CAP="$W/done/project/Captures/FireBolt/seed-1234-gameplay-dusk"
# The done fixture's vfx-lint.json is what vfx_style.py lint prints on the fixture's own inputs (paths relative to
# plan/done, so the file names no absolute path): regenerate it with exactly this command when an input changes.
DONE_LINT=(lint --style authoring/vfx/style/vfx-style.md --recipe project/Effects/FireBolt/FireBolt.vfxrecipe.json
  --stats project/Captures/FireBolt/seed-1234-gameplay-dusk/stats.json --spec authoring/vfx/specs/fire-bolt.md)
DONE_LINT_FILE="$P/done/project/Captures/FireBolt/seed-1234-gameplay-dusk/vfx-lint.json"
(cd "$P/done" && py "$STYLE" "${DONE_LINT[@]}") > "$TMP/o.json" 2>"$TMP/err"; rc=$?
tr -d '\r' < "$TMP/o.json" | cmp -s - "$DONE_LINT_FILE" && [ $rc -eq 0 ] \
  && [ "$(q '.inputs.recipe.sha256')" = "$(sha256sum "$P/done/project/Effects/FireBolt/FireBolt.vfxrecipe.json" | cut -d' ' -f1)" ] \
  && ok "plan fixture: done vfx-lint.json is the vfx_style.py lint output (exit 0), inputs.recipe.sha256 the recipe's SHA-256" \
  || no "plan fixture lint: rc=$rc $(tr -d '\r' < "$TMP/o.json" | diff - "$DONE_LINT_FILE" | head -5) $(head -c 200 "$TMP/err")"
# A lint result vfx_style.py prints on the work copy, saved next to the capture, binds the capture step to the recipe.
run "$STYLE" lint --style "$W/done/authoring/vfx/style/vfx-style.md" --recipe "$REC" --stats "$CAP/stats.json"
cp "$TMP/o.json" "$CAP/vfx-lint.json"; cp "$TMP/o.json" "$TMP/bound-lint.json"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[3].state')" = DONE ] && [ "$(q '.context.lint.recipe_sha256')" = "$(q '.context.recipe.sha256')" ] \
  && [ "$(q '.context.lint.recipe_sha256 | length')" = 64 ] && q '.steps[3].evidence[-1]' | grep -q '^lint bound to recipe sha256 ' \
  && ok "plan: a vfx_style.py lint result is bound to its recipe (inputs.recipe.sha256) and the capture step DONE" \
  || no "plan lint bound: rc=$rc $(steps) lint=$(q .context.lint) recipe=$(q .context.recipe.sha256)"
# The same lint result bound to another recipe (its inputs.recipe.sha256 differs) makes the capture step STALE.
jq '.inputs.recipe.sha256 = "0000000000000000000000000000000000000000000000000000000000000000"' "$TMP/bound-lint.json" > "$CAP/vfx-lint.json"
wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[3].state')" = STALE ] && [ "$(q .current_step)" = capture ] \
  && q '.steps[3].evidence[-1]' | grep -q 'bound to recipe sha256 000000000000, not the current recipe' \
  && ok "plan: a lint result whose recipe hash differs makes the capture step STALE" || no "plan lint other recipe: rc=$rc $(steps) $(q '.steps[3].evidence')"
# A lint result that names no recipe SHA-256 (inputs.recipe a bare path) is not bound: IN_PROGRESS, lint again.
jq '.inputs.recipe = .inputs.recipe.path' "$TMP/bound-lint.json" > "$CAP/vfx-lint.json"
wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[3].state')" = IN_PROGRESS ] && [ "$(q '.context.lint.recipe_sha256')" = null ] \
  && q '.steps[3].evidence[-1]' | grep -q 'names no recipe SHA-256' \
  && ok "plan: a lint result without inputs.recipe.sha256 is not bound (capture step IN_PROGRESS)" || no "plan lint unbound: rc=$rc $(steps) $(q '.steps[3].evidence')"
# A bound lint result with a FAIL row (alive.peak above every platform budget) makes the capture step FAIL.
jq '.alive.peak = 100000' "$CAP/stats.json" > "$TMP/stats-alive.json"
run "$STYLE" lint --style "$W/done/authoring/vfx/style/vfx-style.md" --recipe "$REC" --stats "$TMP/stats-alive.json"
cp "$TMP/o.json" "$CAP/vfx-lint.json"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[3].state')" = FAIL ] && [ "$(q .current_step)" = capture ] && [ "$(q '.context.lint.fail')" = 1 ] \
  && q '.steps[3].evidence[-1]' | grep -q 'budget-alive' \
  && ok "plan: a vfx_style.py lint result with a FAIL row makes the capture step FAIL" || no "plan lint FAIL: rc=$rc $(steps) lint=$(q .context.lint)"
rm -f "$CAP/vfx-lint.json"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[3].state')" = IN_PROGRESS ] && ok "plan: a capture without a lint result is IN_PROGRESS" \
  || no "plan no lint: rc=$rc $(steps)"
cp "$P/done/project/Captures/FireBolt/seed-1234-gameplay-dusk/vfx-lint.json" "$CAP/vfx-lint.json"
STY="$W/done/authoring/vfx/style/vfx-style.md"
python3 -B - "$STY" <<'PY'
import sys
p = sys.argv[1]; t = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8", newline="").write(t.replace('"status": "approved"', '"status": "in-review"', 1))
PY
wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[0].state')" = IN_PROGRESS ] && [ "$(q .current_step)" = style ] \
  && ok "plan: a style profile in review is IN_PROGRESS and the current step" || no "plan style in review: rc=$rc $(steps)"
cp "$P/done/authoring/vfx/style/vfx-style.md" "$STY"
printf '\n' >> "$STY"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(q '.steps[0].state')" = STALE ] \
  && ok "plan: a binding profile changed after its approval is STALE" || no "plan stale approval: rc=$rc $(steps)"
cp "$P/done/authoring/vfx/style/vfx-style.md" "$STY"
rm -rf "$W/done/authoring/approvals/VFX-style-001" "$W/done/authoring/approvals/AGEN-fire-bolt-glow-001"; wplan; rc=$?
[ $rc -eq 0 ] && [ "$(steps)" = "style=NEEDS_APPROVAL,textures=NEEDS_APPROVAL,recipe=DONE,capture=DONE,record=DONE" ] \
  && [ "$(q .current_step)" = style ] && q '.steps[0].evidence[0]' | grep -q 'no approval record' \
  && ok "plan: an approved profile and gen-run without approval records are NEEDS_APPROVAL" || no "plan needs approval: rc=$rc $(steps)"

# -- the VFX Graph text adapter
GX="$FX/vfxgraph"; GSTATS="$GX/Captures/Sparks/stats.json"
adapt() { rm -f "$TMP/o.json" "$TMP/err"; py "$ADAPTER" "$@" > "$TMP/o.json" 2>"$TMP/err"; }
adapt "$GX" Assets/VFX/Sparks/Sparks.vfx --stats "$GSTATS"; rc=$?
[ "$(q .guid)" = 9e1d2c3b4a5f60718293a4b5c6d7e8f9 ] && [ "$(q .resource)" = Sparks ] && [ "$(q .relative_path)" = Assets/VFX/Sparks/Sparks.vfx ] \
  && ok "adapter: asset GUID from the .meta, resource name and project-relative path" || no "adapter guid: rc=$rc $(head -c 300 "$TMP/o.json") $(head -c 200 "$TMP/err")"
[ "$(q '[.systems[].capacity] | join(",")')" = 64,128 ] && [ "$(q '[.systems[].data_type] | join(",")')" = Particle,ParticleStrip ] \
  && [ "$(q '.fields.max_particles + " " + (.fields.particle_systems | tostring)')" = "192 2" ] \
  && ok "adapter: system capacities 64 and 128 (a particle and a strip system), total 192" || no "adapter capacities: $(q .systems) $(q .fields)"
[ "$(q '.references | [.textures[0], .shaders[0], .subgraphs[0], .builtin[0]] | join(",")')" = "8aafaa78fe944854997fef757ff4ba72,5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f,3b1f0c6e2a9d4e7f8a5b6c7d8e9f0a1b,0000000000000000e000000000000000" ] \
  && [ "$(q '[.. | strings | select(. == "7d4c867f6b72b714dbb5fd1780afe208")] | length')" = 0 ] \
  && ok "adapter: referenced GUIDs grouped (texture, Shader Graph, subgraph, built-in), script GUIDs left out" || no "adapter references: $(q .references)"
[ "$(q '.stats.schema + " " + (.stats.alive_peak | tostring) + " " + .stats.camera + " " + .stats.lighting + " " + (.stats.seed | tostring)')" = "cuvara.vfx-capture/1 150 gameplay dusk 1234" ] \
  && [ "$(q '.recipe.sha256')" = "$(q '.stats.recipe_sha256')" ] && [ "$(q '.comparisons | join(",")')" = "stats.effect,stats.systems.capacity,stats.recipe_sha256" ] \
  && ok "adapter: stats read and bound to the asset (effect, capacities, recipe SHA-256)" || no "adapter stats: $(q .stats) $(q .comparisons)"
[ $rc -eq 1 ] && [ "$(q .state)" = HUMAN_REQUIRED ] && q '.reasons[0]' | grep -q 'spec budget missing' \
  && ok "adapter: without a budget the asset is HUMAN_REQUIRED (exit 1)" || no "adapter no budget: rc=$rc state=$(q .state)"
printf '{"max_particles":256,"max_systems":2,"max_alive":200}\n' > "$TMP/budget.json"
adapt "$GX" Assets/VFX/Sparks/Sparks.vfx --stats "$GSTATS" --budget-json "$TMP/budget.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q .state)" = PASS ] && [ "$(q '.comparisons | join(",")')" = "stats.effect,stats.systems.capacity,stats.recipe_sha256,max_particles,max_systems,max_alive" ] \
  && ok "adapter: inside the budget is PASS (exit 0) with every comparison" || no "adapter budget PASS: rc=$rc state=$(q .state) $(q .reasons)"
printf '{"max_particles":256,"max_systems":2,"max_alive":100}\n' > "$TMP/budget-alive.json"
adapt "$GX" Assets/VFX/Sparks/Sparks.vfx --stats "$GSTATS" --budget-json "$TMP/budget-alive.json"; rc=$?
[ $rc -eq 1 ] && [ "$(q .state)" = FAIL ] && q '.reasons | join(" ")' | grep -q 'alive.peak exceeds' \
  && ok "adapter: alive.peak above max_alive is FAIL" || no "adapter alive FAIL: rc=$rc $(q .reasons)"
printf '{"max_particles":100,"max_systems":1}\n' > "$TMP/budget-small.json"
adapt "$GX" Assets/VFX/Sparks/Sparks.vfx --budget-json "$TMP/budget-small.json"; rc=$?
[ $rc -eq 1 ] && [ "$(q .state)" = FAIL ] && [ "$(q '.reasons | length')" = 2 ] \
  && ok "adapter: capacity and system count above the budget are FAIL" || no "adapter capacity FAIL: rc=$rc $(q .reasons)"
jq '.recipe_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"' "$GSTATS" > "$TMP/stats-other.json"
adapt "$GX" Assets/VFX/Sparks/Sparks.vfx --stats "$TMP/stats-other.json" --budget-json "$TMP/budget.json"; rc=$?
[ $rc -eq 1 ] && [ "$(q .state)" = FAIL ] && q '.reasons | join(" ")' | grep -q 'recipe_sha256' \
  && ok "adapter: stats of another recipe are FAIL (recapture)" || no "adapter recipe hash: rc=$rc $(q .reasons)"
jq '.systems[1].capacity = 256' "$GSTATS" > "$TMP/stats-caps.json"
adapt "$GX" Assets/VFX/Sparks/Sparks.vfx --stats "$TMP/stats-caps.json" --budget-json "$TMP/budget.json"; rc=$?
[ $rc -eq 1 ] && [ "$(q .state)" = FAIL ] && q '.reasons | join(" ")' | grep -q 'capacities' \
  && ok "adapter: stats whose capacities differ from the asset are FAIL" || no "adapter capacities mismatch: rc=$rc $(q .reasons)"
printf '{"max_particles":256,"max_systems":2}\n' > "$TMP/budget-asset.json"
adapt "$GX" --guid 9e1d2c3b4a5f60718293a4b5c6d7e8f9 --budget-json "$TMP/budget-asset.json"; rc=$?
[ $rc -eq 0 ] && [ "$(q .relative_path)" = Assets/VFX/Sparks/Sparks.vfx ] && ok "adapter: --guid finds the asset through its .meta" \
  || no "adapter --guid: rc=$rc $(q .relative_path) $(q .reasons)"
adapt "$TMP/no-project" Assets/VFX/x.vfx; rc=$?
[ $rc -eq 1 ] && [ "$(q .state)" = NOT_AVAILABLE ] && ok "adapter: a missing project is NOT_AVAILABLE" || no "adapter no project: rc=$rc $(q .state)"
adapt "$FX" particle-system.prefab; rc=$?
[ $rc -eq 1 ] && [ "$(q .state)" = NOT_AVAILABLE ] && q '.reasons[0]' | grep -q 'unity.py' \
  && ok "adapter: a Shuriken prefab is NOT_AVAILABLE and points to unity.py" || no "adapter prefab: rc=$rc $(q .reasons)"

# -- nothing was written: fixtures, scripts and the state dir are byte for byte as before
snapshot > "$TMP/after.txt"
if cmp -s "$TMP/before.txt" "$TMP/after.txt"; then ok "no script wrote a file: fixtures, scripts and state dir unchanged ($(wc -l < "$TMP/after.txt") entries)"
else no "files changed: $(diff "$TMP/before.txt" "$TMP/after.txt" | head -5)"; fi
[ ! -e "$RPG_FACTORY_STATE_DIR" ] && ok "no Factory state written (RPG_FACTORY_STATE_DIR absent)" || no "state written: $(ls -R "$RPG_FACTORY_STATE_DIR" | head -5)"

echo "vfx-production: $pass passed, $fail failed"
[ $fail -eq 0 ]
