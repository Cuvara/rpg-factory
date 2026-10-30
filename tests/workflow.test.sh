#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1
trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
mkdir -p "$TMP/authoring"
cp "$ROOT/registry.json" "$TMP/registry.json"
cat >"$TMP/design.json" <<'EOF'
{"id":"demo","title":"Demo","goal":"A demo","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["Works"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --json >"$TMP/out"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert len(p["nodes"])==1 and p["nodes"]["design"]["domain"]=="design" and p["waves"]==[["design"]]' "$TMP/out" || exit 1
echo 'PASS one-domain design plan'
cat >"$TMP/eng.json" <<'EOF'
{"id":"demo","title":"Demo","goal":"A demo","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["Works"]},{"id":"impl","kind":"implementation","repo":"server","paths":["backend/gameserver-dotnet/"],"sources":["design"],"acceptance":["Implemented"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/eng.json" --registry "$TMP/registry.json" --json >"$TMP/out"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["waves"]==[["design"],["impl"]] and p["nodes"]["impl"]["domain"]=="engineering"' "$TMP/out" || exit 1
echo 'PASS design to engineering graph'
python3 -B "$ROOT/scripts/factory-workflow.py" dispatch "$TMP/eng.json" --node impl --registry "$TMP/registry.json" --authoring "$TMP/authoring" >"$TMP/out" 2>&1
rc=$?
[ "$rc" -eq 2 ] && grep -q 'not ready' "$TMP/out" || { echo 'FAIL missing dependency blocks dispatch'; exit 1; }
echo 'PASS missing dependency blocks dispatch'
cat >"$TMP/unknown.json" <<'EOF'
{"id":"bad","title":"Bad","goal":"Bad","targets":[{"kind":"unknown-kind","sources":[],"acceptance":[]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/unknown.json" --registry "$TMP/registry.json" >"$TMP/out" 2>&1
rc=$?
[ "$rc" -eq 3 ] && grep -q 'unknown' "$TMP/out" || { echo 'FAIL unknown kind'; exit 1; }
echo 'PASS unknown kind rejected'
cat >"$TMP/cycle.json" <<'EOF'
{"id":"cycle","title":"Cycle","goal":"Cycle","targets":[{"id":"a","kind":"feature-spec","sources":["b"],"acceptance":[]},{"id":"b","kind":"ui-spec","sources":["a"],"acceptance":[]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/cycle.json" --registry "$TMP/registry.json" >"$TMP/out" 2>&1
rc=$?
[ "$rc" -eq 3 ] && grep -q 'CYCLE' "$TMP/out" || { echo 'FAIL dependency cycle'; exit 1; }
echo 'PASS dependency cycle reports exit 3'
cat >"$TMP/domains.json" <<'EOF'
{"id":"domains","title":"Domains","goal":"Cross domain","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["A"]},{"id":"ui","kind":"ui-spec","sources":["design"],"acceptance":["B"]},{"id":"art","kind":"art2d-brief","sources":["ui"],"acceptance":["C"]},{"id":"art3d","kind":"art3d-asset","sources":[],"acceptance":["D"]},{"id":"vfx","kind":"vfx-spec","sources":["art3d"],"acceptance":["E"]},{"id":"impl","kind":"implementation","repo":"client","paths":["Assets/Scripts/"],"sources":[],"acceptance":["F"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/domains.json" --registry "$TMP/registry.json" --json >"$TMP/out"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["waves"]==[["art3d","design"],["ui","vfx"],["art"],["impl"]]' "$TMP/out" || exit 1
echo 'PASS handoff graph produces ordered waves with parallel siblings'
cat >"$TMP/art2d.json" <<'EOF'
{"id":"art2d","title":"Art","goal":"Art","targets":[{"id":"art","kind":"art2d-brief","sources":[],"acceptance":["Brief"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/art2d.json" --registry "$TMP/registry.json" --json >"$TMP/out"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); ds={n["domain"] for n in p["nodes"].values()}; assert {"design","ui","art2d"} <= ds and len(p["waves"])==3' "$TMP/out" || exit 1
echo 'PASS implicit design and UI upstream handoffs for art2d'
python3 -m json.tool "$TMP/registry.json" >/dev/null || exit 1
echo 'workflow tests: 7 run, 7 passed, 0 failed'
