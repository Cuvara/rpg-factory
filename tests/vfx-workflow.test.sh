#!/usr/bin/env bash
# VFX schema, quality plugin, adapter and workflow coverage.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp_win)" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/authoring/vfx/specs" "$T/unity/Assets"
python3 -B - "$ROOT" "$T" <<'PY'
import importlib.util,json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]); temp=pathlib.Path(sys.argv[2]); sys.path.insert(0,str(root/'scripts/checks'))
from domains._api import Context
plugin_spec=importlib.util.spec_from_file_location('vfx_quality',root/'scripts/checks/domains/vfx.py'); plugin=importlib.util.module_from_spec(plugin_spec); plugin_spec.loader.exec_module(plugin)
registry=json.loads((root/'registry.json').read_text())
for path in sorted((root/'templates/vfx').glob('*.md')):
 data=json.loads(re.search(r'^---json\s*\n(.*?)\n---',path.read_text(),re.S).group(1)); assert data['status']=='draft'; assert data['schema_version']==2
 (temp/'authoring/vfx/specs'/(path.stem+'.artifact.json')).write_text(json.dumps(data))
assert len(list((root/'templates/vfx').glob('*.md')))==3
design={'id':'DS-event-001','kind':'feature-spec','domain':'design','spec':{'gameplay_events':['combat.hit']}}
valid={'id':'VFX-burst-001','kind':'vfx-spec','domain':'vfx','status':'approved','spec':{'purpose':'proposal','triggers':['DS-event-001'],'duration_seconds':1,'phases':[{'name':'active','duration_seconds':1}],'curves':[{'property':'size','keyframes':[{'time':0,'value':0},{'time':1,'value':1}]}],'particle_systems':[{'id':'main','max_particles':8,'lifetime_seconds':1,'spawn_per_second':8}],'materials':[],'platforms':{'desktop':{'budget':{'max_particles':10,'max_overdraw':1,'max_draw_calls':1,'max_ms':1},'constraints':[]}},'platform_constraints':[],'dependencies':[{'id':'UI-cue-001','kind':'ui','status':'tbd'}]}}
ctx=Context(str(temp/'authoring'),registry,'',{'DS-event-001':('design/features/event.json',design),'VFX-burst-001':('vfx/specs/spec.json',valid)},lambda _:None)
def states(a): return {r.check:r.state for r in plugin.check(a,ctx)}
assert all(x=='PASS' for x in states(valid).values()),states(valid)
cases=[]
bad=json.loads(json.dumps(valid)); bad['spec']['triggers']=['missing']; cases.append(('trigger',bad,'vfx-triggers'))
bad=json.loads(json.dumps(valid)); bad['spec']['phases'][0]['duration_seconds']=-1; cases.append(('negative phase',bad,'vfx-timing'))
bad=json.loads(json.dumps(valid)); bad['spec']['phases'][0]['duration_seconds']=0.5; cases.append(('phase sum',bad,'vfx-timing'))
bad=json.loads(json.dumps(valid)); bad['spec']['curves'][0]['keyframes'].reverse(); cases.append(('unsorted curve',bad,'vfx-curves'))
bad=json.loads(json.dumps(valid)); bad['spec']['curves'][0]['keyframes'][0]['time']=2; cases.append(('curve range',bad,'vfx-curves'))
bad=json.loads(json.dumps(valid)); bad['spec']['platforms']['desktop']['budget']['max_particles']=2; cases.append(('particle maximum',bad,'vfx-platform-budgets'))
bad=json.loads(json.dumps(valid)); bad['spec']['dependencies']=[{'id':'missing-ui','kind':'ui','status':'required'}]; cases.append(('sync dependency',bad,'vfx-sync-dependencies'))
bad=json.loads(json.dumps(valid)); bad['kind']='vfx-asset'; bad['sources']=['VFX-burst-001']; bad['spec']={'asset_path':'Assets/VFX/a.prefab','stats':{}}; cases.append(('missing asset stats',bad,'vfx-asset-budget'))
bad=json.loads(json.dumps(valid)); bad['kind']='vfx-asset'; bad['sources']=['VFX-burst-001']; bad['spec']={'asset_path':'Assets/VFX/a.prefab','stats':{'mobile':{'particles':1,'overdraw':0.1,'draw_calls':1,'ms':0.1}}}; cases.append(('missing expected platform stats',bad,'vfx-asset-budget'))
for name,artifact,check in cases: assert states(artifact)[check]=='FAIL',(name,states(artifact))
# Numeric budgets, particle maxima and measurements must reject NaN, infinity and negatives.
numeric_failures=[]
for key,value in [('max_particles',float('nan')),('max_overdraw',float('inf')),('max_draw_calls',-1),('max_ms',float('nan'))]:
    bad=json.loads(json.dumps(valid)); bad['spec']['platforms']['desktop']['budget'][key]=value
    try:
        if states(bad)['vfx-platform-budgets']!='FAIL': numeric_failures.append('invalid budget '+key)
    except Exception: numeric_failures.append('invalid budget '+key+' crashed')
for value in (float('nan'),float('inf'),-1):
    bad=json.loads(json.dumps(valid)); bad['spec']['particle_systems'][0]['max_particles']=value
    try:
        if states(bad)['vfx-platform-budgets']!='FAIL': numeric_failures.append('invalid particle maximum '+str(value))
    except Exception: numeric_failures.append('invalid particle maximum '+str(value)+' crashed')
for label,mutate in [('non-finite phase',lambda a:a['spec']['phases'][0].update(duration_seconds=float('nan'))),('non-finite curve',lambda a:a['spec']['curves'][0]['keyframes'][0].update(value=float('inf')))]:
    bad=json.loads(json.dumps(valid)); mutate(bad)
    try:
        check='vfx-timing' if label.endswith('phase') else 'vfx-curves'
        if states(bad)[check]!='FAIL': numeric_failures.append(label)
    except Exception: numeric_failures.append(label+' crashed')
source=valid
ctx.artifacts['VFX-burst-001']=('vfx/specs/spec.json',source)
for stat,value in [('particles',float('nan')),('overdraw',float('inf')),('draw_calls',-1),('ms',float('nan'))]:
    bad={'id':'VFX-stat-test','kind':'vfx-asset','domain':'vfx','sources':['VFX-burst-001'],'spec':{'asset_path':'Assets/VFX/a.prefab','stats':{'desktop':{'particles':1,'overdraw':0.1,'draw_calls':1,'ms':0.1}}}}
    bad['spec']['stats']['desktop'][stat]=value
    try:
        if states(bad)['vfx-asset-budget']!='FAIL': numeric_failures.append('invalid stat '+stat)
    except Exception: numeric_failures.append('invalid stat '+stat+' crashed')
adapter_spec=importlib.util.spec_from_file_location('unity_vfx',root/'scripts/adapters/vfx/unity.py'); adapter=importlib.util.module_from_spec(adapter_spec); adapter_spec.loader.exec_module(adapter)
prefab=temp/'unity/Assets/test.prefab'; prefab.write_text('ParticleSystem:\n  maxNumParticles: 2\n')
for value in (float('nan'),float('inf'),-1,2.5):
    try:
        result=adapter.inspect(temp/'unity','Assets/test.prefab',budget={'max_particles':value})
        if result['state']!='FAIL' or result['comparisons']: numeric_failures.append('Unity invalid numeric budget '+str(value))
    except Exception: numeric_failures.append('Unity invalid numeric budget '+str(value)+' crashed')
if numeric_failures: print('FAIL '+', '.join(numeric_failures),file=sys.stderr)
assert not numeric_failures, 'invalid numeric budgets or stats were accepted'
ctx.registry['domains']['vfx']['engineering_event_ids']=['EVT-combat-hit']
event_spec=json.loads(json.dumps(valid)); event_spec['spec']['triggers']=['EVT-combat-hit']; assert states(event_spec)['vfx-triggers']=='PASS'
ctx.artifacts['UI-cue-001']=('ui/specs/cue.json',{'domain':'ui'})
sync_spec=json.loads(json.dumps(valid)); sync_spec['spec']['dependencies']=[{'id':'UI-cue-001','kind':'ui','status':'required'}]; assert states(sync_spec)['vfx-sync-dependencies']=='PASS'
graph=json.loads(json.dumps(valid)); graph['kind']='vfx-asset'; graph['spec']={'asset_path':'Assets/VFX/burst.vfx','stats':{}}
assert states(graph)['vfx-graph-visual-verification']=='HUMAN_REQUIRED'
asset={'id':'VFX-asset-001','kind':'vfx-asset','domain':'vfx','sources':['VFX-burst-001'],'spec':{'stats':{'desktop':{'particles':11,'overdraw':0.5,'draw_calls':1,'ms':0.5}},'asset_path':'Assets/VFX/a.prefab'}}
ctx.artifacts['VFX-asset-001']=('vfx/assets/a.asset.json',asset)
assert states(asset)['vfx-asset-budget']=='FAIL'
verified=json.loads(json.dumps(valid)); verified['status']='verified'; assert states(verified)['vfx-verification-evidence']=='FAIL'
asset['status']='verified'; asset['spec']['checks']=['prefab-inspection']; assert states(verified)['vfx-verification-evidence']=='PASS'
print('VFX domain failure cases: %d passed, 0 failed' % len(cases))
PY
python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/authoring" --registry "$ROOT/registry.json"
# The shared lifecycle rejects a direct draft -> released shortcut.
git -C "$T/authoring" init -q -b main
git -C "$T/authoring" -c user.name=VFX -c user.email=vfx@example.test add -A
git -C "$T/authoring" -c user.name=VFX -c user.email=vfx@example.test commit -qm templates
python3 -B - "$T/authoring" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); p=root/'vfx/specs/shortcut.artifact.json'
data=json.loads((root/'vfx/specs/vfx-spec.artifact.json').read_text()); data['id']='VFX-shortcut-001'; data['status']='draft'; p.write_text(json.dumps(data))
PY
git -C "$T/authoring" -c user.name=VFX -c user.email=vfx@example.test add -A
git -C "$T/authoring" -c user.name=VFX -c user.email=vfx@example.test commit -qm draft
python3 -B - "$T/authoring/vfx/specs/shortcut.artifact.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); data=json.loads(p.read_text()); data['status']='released'; p.write_text(json.dumps(data))
PY
git -C "$T/authoring" -c user.name=VFX -c user.email=vfx@example.test add -A
git -C "$T/authoring" -c user.name=VFX -c user.email=vfx@example.test commit -qm shortcut
if python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/authoring" --registry "$ROOT/registry.json" --domain vfx --json > "$T/quality.json"; then echo 'Lifecycle shortcut unexpectedly passed' >&2; exit 1; fi
jq -e '[.results[] | select(.artifact == "VFX-shortcut-001" and .check == "lifecycle" and .state == "FAIL" and (any(.reasons[]; contains("illegal transition draft -> released"))))] | length == 1' "$T/quality.json" >/dev/null
python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/no-project" Assets/Particle.prefab > "$T/adapter.json" || true
jq -e '.state == "NOT_AVAILABLE"' "$T/adapter.json" >/dev/null
mkdir -p "$T/unity/Assets/VFX"
cat > "$T/unity/Assets/VFX/test.prefab" <<'EOF'
ParticleSystem:
  maxNumParticles: 12
  startLifetime: 0.4
  looping: 0
  duration: 1.2
EOF
printf 'guid: abcdef1234567890\n' > "$T/unity/Assets/VFX/test.prefab.meta"
printf '{"max_particles":16}\n' > "$T/budget.json"
python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" Assets/VFX/test.prefab --budget-json "$T/budget.json" > "$T/present.json" || true
jq -e '.state == "HUMAN_REQUIRED" and .fields.max_particles == "12" and .guid == "abcdef1234567890" and (.comparisons|index("max_particles") != null)' "$T/present.json" >/dev/null
python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" Assets/VFX/test.prefab > "$T/missing-budget.json" || true
jq -e '.state == "HUMAN_REQUIRED" and any(.reasons[]; contains("spec budget missing"))' "$T/missing-budget.json" >/dev/null
python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" --guid abcdef1234567890 --budget-json "$T/budget.json" > "$T/guid.json" || true
jq -e '.state == "HUMAN_REQUIRED" and (.asset | contains("test.prefab"))' "$T/guid.json" >/dev/null
printf '{"max_particles":4}\n' > "$T/budget.json"
if python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" Assets/VFX/test.prefab --budget-json "$T/budget.json" > "$T/over-budget.json"; then echo 'Unity adapter budget overrun unexpectedly passed' >&2; exit 1; fi
jq -e '.state == "FAIL" and any(.reasons[]; contains("exceed spec budget"))' "$T/over-budget.json" >/dev/null
python3 -B - "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" <<'PY'
import importlib.util,pathlib,sys
spec=importlib.util.spec_from_file_location('unity_vfx',sys.argv[1]); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
for value in (float('nan'),float('inf'),-1,2.5):
    result=module.inspect(sys.argv[2],'Assets/VFX/test.prefab',budget={'max_particles':value})
    assert result['state']=='FAIL' and result['comparisons']==[] and any('finite non-negative integer' in reason for reason in result['reasons']), (value,result)
print('Unity invalid numeric budgets: 4 passed, 0 failed')
PY
# A prefab with several ParticleSystems: the effect budget covers their sum, not only the first one.
cat > "$T/unity/Assets/VFX/multi.prefab" <<'EOF'
--- !u!198 &1
ParticleSystem:
  maxNumParticles: 10
--- !u!198 &2
ParticleSystem:
  maxNumParticles: 12
EOF
printf '{"max_particles":16}\n' > "$T/budget.json"
if python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" Assets/VFX/multi.prefab --budget-json "$T/budget.json" > "$T/multi.json"; then echo 'Unity adapter ignored the second ParticleSystem' >&2; exit 1; fi
jq -e '.state == "FAIL" and .fields.max_particles == "22" and .fields.particle_systems == 2' "$T/multi.json" >/dev/null
printf '{"max_particles":30}\n' > "$T/budget.json"
python3 -B "$ROOT/scripts/adapters/vfx/unity.py" "$T/unity" Assets/VFX/multi.prefab --budget-json "$T/budget.json" > "$T/multi-ok.json" || true
jq -e '.state != "FAIL" and (.comparisons|index("max_particles") != null)' "$T/multi-ok.json" >/dev/null
python3 -B - "$ROOT" "$T" <<'PY'
import json,pathlib,sys
r=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2])
spec={'id':'workflow','title':'VFX task','goal':'Author production effect','targets':[{'id':'effect','kind':'vfx-spec','domain':'vfx','sources':[],'acceptance':['Spec meets event and budget requirements']}],'existing':[]}
(t/'workflow.json').write_text(json.dumps(spec))
PY
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$T/workflow.json" --json > "$T/plan.json"
jq -e '.nodes.effect.domain == "vfx" and .nodes.effect.lead_skill == "vfx" and (.waves|length) == 2 and (.nodes|keys|length) == 3' "$T/plan.json" >/dev/null
python3 -B "$ROOT/scripts/factory-workflow.py" status "$T/workflow.json" --json > "$T/status.json"
jq -e '.states.effect == "blocked" and (.waves|length) == 2' "$T/status.json" >/dev/null
# A changed upstream blob revision marks an existing VFX artifact stale.
python3 -B - "$T/authoring" "$T/workflow.json" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); workflow=pathlib.Path(sys.argv[2])
(root/'design/features').mkdir(parents=True,exist_ok=True)
design={'id':'DS-event-001','kind':'feature-spec','domain':'design','status':'approved','rev':'new'}
effect={'id':'effect','kind':'vfx-spec','domain':'vfx','status':'approved','upstream':[{'id':'DS-event-001','rev':'0000000000000000000000000000000000000000'}]}
(root/'design/features/DS-event-001.artifact.json').write_text(json.dumps(design))
(root/'vfx/specs/effect.artifact.json').write_text(json.dumps(effect))
workflow.write_text(json.dumps({'id':'workflow','title':'VFX task','goal':'Author production effect','targets':[{'id':'effect','kind':'vfx-spec','domain':'vfx','sources':[],'acceptance':[]}],'existing':[]}))
PY
python3 -B "$ROOT/scripts/factory-workflow.py" status "$T/workflow.json" --authoring "$T/authoring" --json > "$T/stale.json"
jq -e '.states.effect == "stale" and (.stale_upstream|length) == 1' "$T/stale.json" >/dev/null
# Overlay this updated behavioral suite on archives and require behavior assertions to fail there.
for BASE in acec91692797bc0204e6a72bb5c92594c295fc45 fc8d435f4ea1c73124701d3e0af64bec035334e5; do
  mkdir -p "$T/base-$BASE"
  PROOF_DIR="${VFX_PROOF_DIR:-$T}"
  mkdir -p "$PROOF_DIR"
  git -C "$ROOT" archive "$BASE" | tar -x -C "$T/base-$BASE"
  cp "$ROOT/tests/vfx-workflow.test.sh" "$T/base-$BASE/tests/vfx-workflow.test.sh"
  PROOF_LOG="$PROOF_DIR/base-$BASE-proof.log"
  if (cd "$(cygpath -u "$T/base-$BASE")" && bash tests/vfx-workflow.test.sh) > "$PROOF_LOG" 2>&1; then echo "Base proof unexpectedly passed: $BASE" >&2; exit 1; fi
  if [[ "$BASE" == acec916* ]]; then
    # acec916 predates the VFX plugin; the test executes it and records its missing behavior entry point.
    grep -q 'FileNotFoundError' "$PROOF_LOG"
    grep -q 'domains.*vfx.py' "$PROOF_LOG"
    echo "Behavior proof: VFX behavior could not be exercised because the domain plugin is absent on git archive $BASE (log: $PROOF_LOG)"
  else
    grep -q 'invalid budget max_particles' "$PROOF_LOG"
    grep -q 'invalid stat particles' "$PROOF_LOG"
    grep -q 'Unity invalid numeric budget nan' "$PROOF_LOG"
    grep -q 'non-finite phase' "$PROOF_LOG"
    grep -q 'non-finite curve' "$PROOF_LOG"
    echo "Behavior proof: invalid budgets, stats and Unity NaN cases failed against git archive $BASE (log: $PROOF_LOG)"
  fi
done
echo 'vfx workflow: PASS'
