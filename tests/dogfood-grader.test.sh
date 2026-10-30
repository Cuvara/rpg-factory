#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
ok=0; bad=0
check() { local name="$1" expected="$2"; shift 2; local rc=0; "$@" >"$T/out" 2>&1 || rc=$?; if [ "$expected" = pass ] && [ "$rc" -eq 0 ]; then ok=$((ok+1)); echo "ok $name"; elif [ "$expected" = fail ] && [ "$rc" -ne 0 ]; then ok=$((ok+1)); echo "ok $name rejected"; else bad=$((bad+1)); echo "not ok $name (exit $rc; expected $expected)"; cat "$T/out"; fi; }
newcase() {
  local name="$1"; mkdir -p "$T/$name"; cp -R "$ROOT/tests/fixtures/dogfood/game-authoring" "$T/$name/game-authoring"; git -C "$T/$name/game-authoring" init -q; git -C "$T/$name/game-authoring" config user.name Fixture; git -C "$T/$name/game-authoring" config user.email fixture@example.invalid; git -C "$T/$name/game-authoring" add -- design; git -C "$T/$name/game-authoring" commit -qm seed
  local native; native="$(cygpath -m "$T/$name")"
  sed "s|SCRATCH|$native|g" "$ROOT/tests/fixtures/dogfood/transcript.jsonl" >"$T/$name/transcript.jsonl"
}
grade() { python3 -B "$ROOT/tests/dogfood/write-grade.py" --root "$ROOT" --workspace "$1" --scenario fixture --transcript "$1/transcript.jsonl" --expected-skills game-design --expected-kinds game-concept --domain design; }
newcase good
check 'good fixture passes' pass grade "$T/good"
newcase missing; rm "$T/missing/game-authoring/design/concepts/GD-game-concept-001.artifact.json"
check 'missing artifact fails' fail grade "$T/missing"
newcase quality; python3 -B - "$T/quality/game-authoring/design/concepts/GD-game-concept-001.artifact.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p,encoding='utf-8')); d['status']='bogus'; json.dump(d,open(p,'w',encoding='utf-8'))
PY
check 'quality FAIL fails' fail grade "$T/quality"
newcase approval; mkdir -p "$T/approval/game-authoring/approvals"; echo '{}' >"$T/approval/game-authoring/approvals/forbidden.json"
check 'approval file fails' fail grade "$T/approval"
newcase outside; python3 -B - "$T/outside/transcript.jsonl" <<'PY'
import json,sys
p=sys.argv[1]; rows=[json.loads(x) for x in open(p,encoding='utf-8')]; rows[1]['message']['content'][0]['input']['file_path']='/tmp/outside-game-authoring/file.artifact.json'; open(p,'w',encoding='utf-8').write(''.join(json.dumps(x)+'\n' for x in rows))
PY
check 'outside write fails' fail grade "$T/outside"
newcase waves; python3 -B - "$T/waves/transcript.jsonl" <<'PY'
import json,sys
p=sys.argv[1]; d=[json.loads(x) for x in open(p,encoding='utf-8')]; d[2]['message']['content'][0]['input']['command']='python scripts/factory-workflow.py status x; # wrong order engineering design ui'; open(p,'w',encoding='utf-8').write(''.join(json.dumps(x)+'\n' for x in d))
PY
check 'wrong workflow order fails' fail python3 -B "$ROOT/tests/dogfood/write-grade.py" --root "$ROOT" --workspace "$T/waves" --scenario fixture --transcript "$T/waves/transcript.jsonl" --expected-skills game-design --expected-kinds game-concept --domain design --plan design-ui-eng
newcase skill; sed -i 's/Launching skill: rpg-factory:game-design/Launching skill: rpg-factory:ui-ux/' "$T/skill/transcript.jsonl"
check 'missing lead skill fails' fail grade "$T/skill"
echo "dogfood grader: $((ok+bad)) run, $ok passed, $bad failed"
[ "$bad" -eq 0 ]
