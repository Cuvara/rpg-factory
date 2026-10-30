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
ui_route() {
  python3 -B - "$ROOT" "$1" <<'PY'
import json,pathlib,re,sys
root,case=map(pathlib.Path,sys.argv[1:])
(case/'game-authoring/ui/specs').mkdir(parents=True,exist_ok=True)
for name in ('screen-spec','ui-handoff'):
    raw=(root/'templates/ui'/f'{name}.md').read_text(encoding='utf-8')
    obj=json.loads(re.search(r'^---json\s*\n(.*?)\n---',raw,re.S).group(1))
    (case/'game-authoring/ui/specs'/f'{obj["id"]}.artifact.json').write_text(json.dumps(obj)+'\n',encoding='utf-8')
rows=[json.loads(x) for x in (case/'transcript.jsonl').read_text(encoding='utf-8').splitlines()]
rows[0]['message']['content']=[{'type':'tool_result','is_error':False,'content':'Launching skill: rpg-factory:ui-ux'}]
(case/'transcript.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8')
PY
  python3 -B "$ROOT/tests/dogfood/write-grade.py" --root "$ROOT" --workspace "$1" --scenario ui-route --transcript "$1/transcript.jsonl" --expected-skills ui-ux --expected-kinds 'screen-spec ui-handoff' --domain ui
}
seed_lifecycle() {
  local seed; mkdir -p "$T/seeds"
  for seed in feature-spec design-event asset-3d approved-feature field-tool-system asset-3d-vfx stale-pair; do
    mkdir -p "$T/seeds/$seed"
    python3 -B "$ROOT/tests/dogfood/write-setup.py" "$ROOT" "$T/seeds/$seed" "$seed" || return 1
    python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/seeds/$seed" --registry "$ROOT/registry.json" || return 1
  done
}
newcase good
check 'good fixture passes' pass grade "$T/good"
newcase msys
python3 -B - "$T/msys/transcript.jsonl" <<'PY'
import json,re,sys
p=sys.argv[1]; rows=[json.loads(x) for x in open(p,encoding='utf-8')]
path=rows[1]['message']['content'][0]['input']['file_path']
rows[1]['message']['content'][0]['input']['file_path']=re.sub(r'^([A-Za-z]):/',lambda m:'/'.join(('',m.group(1).lower(),''))+path[3:],path)
open(p,'w',encoding='utf-8').write(''.join(json.dumps(x)+'\n' for x in rows))
PY
check 'MSYS write path matches native scratch path' pass grade "$T/msys"
newcase route
check 'UI handoff under UI specs route passes registry ownership' pass ui_route "$T/route"
check 'scenario seeds use registered kinds and valid draft lifecycles' pass seed_lifecycle
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
