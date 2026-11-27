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
assert len(list((root/'templates/vfx').glob('*.md')))==4
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
# Style profile and production evidence checks, on a work copy of the vfx-production "done" fixture
# (authoring repo + effect project with its capture and the vfx_style.py lint result next to it).
cp -r "$ROOT/tests/fixtures/vfx/plan/done" "$T/st"
python3 -B - "$ROOT" "$T/st" <<'PY'
import hashlib,importlib.util,json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]); st=pathlib.Path(sys.argv[2]); sys.path.insert(0,str(root/'scripts/checks'))
from domains._api import Context
ps=importlib.util.spec_from_file_location('vfx_quality_style',root/'scripts/checks/domains/vfx.py'); plugin=importlib.util.module_from_spec(ps); ps.loader.exec_module(plugin)
registry=json.loads((root/'registry.json').read_text(encoding='utf-8'))
auth=st/'authoring'; project=st/'project'; cap=project/'Captures/FireBolt/seed-1234-gameplay-dusk'
FRONT=re.compile(r'\A---json\s*\n(.*?)\n---',re.S)
def load(p): return json.loads(FRONT.match(p.read_text(encoding='utf-8')).group(1))
def dump(p,obj): p.parent.mkdir(parents=True,exist_ok=True); p.write_text('---json\n'+json.dumps(obj,indent=1)+'\n---\n',encoding='utf-8',newline='\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(p): d=p.read_bytes(); return hashlib.sha1(b'blob %d\x00'%len(d)+d).hexdigest()
def clone(x): return json.loads(json.dumps(x))
base={}
for p in sorted(auth.rglob('*.md')):
    if p.read_text(encoding='utf-8').startswith('---json'): o=load(p); base[o['id']]=(p.relative_to(auth).as_posix(),o)
style_rel,style=base['VFX-style-001']; spec_rel,fspec=base['VFX-spec-001']; asset_rel,fasset=base['VFX-asset-001']
VERIFIED={'state':'verified','reasons':['test double']}
def ctx_for(extra=(),drop=(),approval=VERIFIED,roots=True):
    arts={k:v for k,v in base.items() if k not in drop}
    for rel,obj in extra: arts[obj['id']]=(rel,obj)
    c=Context(str(auth),registry,'',arts,lambda _:None,{'authoring':auth,'unityvfx':project} if roots else {})
    c.approval=lambda _aid:approval
    return c
def state(a,check,c=None):
    rows={r.check:r for r in plugin.check(a,c or ctx_for())}
    return rows[check].state if check in rows else None
def reasons(a,check,c=None): return [x for r in plugin.check(a,c or ctx_for()) if r.check==check for x in r.reasons]
n=0
def expect(label,got,want):
    global n
    assert got==want,(label,got,want); n+=1
# vfx-style: the kind is graded (no vfx-kind FAIL) and the profile resolves with vfx_style.py.
expect('style profile',{r.check:r.state for r in plugin.check(style,ctx_for())},{'vfx-style-profile':'PASS'})
bad=clone(style); bad['binding_values']=False; expect('style not binding',state(bad,'vfx-style-profile'),'FAIL')
bad=clone(style); bad['id']='VFX-style-002'; del bad['spec']['palette']; dump(auth/'vfx/style/broken.md',bad)
expect('style malformed',state(bad,'vfx-style-profile',ctx_for([('vfx/style/broken.md',bad)],drop=['VFX-style-001'])),'FAIL')
assert any('palette' in x for x in reasons(bad,'vfx-style-profile',ctx_for([('vfx/style/broken.md',bad)],drop=['VFX-style-001'])))
second=clone(style); second['id']='VFX-style-003'; dump(auth/'vfx/style/second.md',second)
expect('two live profiles',state(style,'vfx-style-profile',ctx_for([('vfx/style/second.md',second)])),'FAIL')
second['status']='superseded'; expect('superseded profile',state(style,'vfx-style-profile',ctx_for([('vfx/style/second.md',second)])),'PASS')
(auth/'vfx/style/broken.md').unlink(); (auth/'vfx/style/second.md').unlink()
# vfx-spec-style: a spec naming the profile keeps its budgets and phase shares inside the profile's bands.
sspec=clone(fspec); sspec['id']='VFX-spec-style'
sspec['spec'].update(style='VFX-style-001',triggers=[],curves=[],materials=[],dependencies=[],platform_constraints=[],
    particle_systems=[{'id':'bolt','max_particles':300,'lifetime_seconds':1,'spawn_per_second':300}],
    platforms={'android':{'budget':{'max_particles':500,'max_overdraw':1,'max_draw_calls':2,'max_ms':0.5},'constraints':[]}})
expect('spec style',state(sspec,'vfx-spec-style'),'PASS')
expect('spec without style',state(fspec,'vfx-spec-style'),None)
bad=clone(sspec); bad['spec']['platforms']['android']['budget']['max_particles']=5000; expect('spec budget over profile',state(bad,'vfx-spec-style'),'FAIL')
bad=clone(sspec); bad['spec']['particle_systems']=[{'id':'s%d'%i,'max_particles':1,'lifetime_seconds':1,'spawn_per_second':1} for i in range(5)]; expect('spec systems over profile',state(bad,'vfx-spec-style'),'FAIL')
bad=clone(sspec); bad['spec']['phases']=[{'name':'anticipation','duration_seconds':0.5},{'name':'impact','duration_seconds':0.2},{'name':'dissipation','duration_seconds':0.3}]; expect('spec phase share',state(bad,'vfx-spec-style'),'FAIL')
bad=clone(sspec); bad['spec']['style']='VFX-style-missing'; expect('spec unknown profile',state(bad,'vfx-spec-style'),'FAIL')
bad=clone(sspec); bad['spec']['platforms']['desktop']=clone(bad['spec']['platforms']['android']); expect('spec platform the profile does not budget',state(bad,'vfx-spec-style'),'WARN')
# vfx-asset evidence: capture, style lint and textures, bound to the fixture's files.
stats=json.loads((cap/'stats.json').read_text(encoding='utf-8'))
good=clone(fasset); good['spec'].update(
    capture={'stats_hash':sha(cap/'stats.json'),'seed':stats['seed'],'alive_peak':stats['alive']['peak'],'contact_sheet_hash':stats['contact_sheet']['sha256']},
    style={'profile_id':'VFX-style-001','blob_revision':blob(auth/style_rel)},
    lint={'state':'WARN','report_hash':sha(cap/'vfx-lint.json')},
    textures=[{'gen_run_id':'AGEN-fire-bolt-glow-001','output_hash':'1'*64,'transform':'luminance_to_alpha','game_texture_hash':'3'*64}])
rows={r.check:r.state for r in plugin.check(good,ctx_for())}
expect('evidence graded',{k:rows[k] for k in ('vfx-asset-capture','vfx-asset-style-lint','vfx-asset-textures','vfx-graph-visual-verification')},
       {'vfx-asset-capture':'PASS','vfx-asset-style-lint':'WARN','vfx-asset-textures':'PASS','vfx-graph-visual-verification':'HUMAN_REQUIRED'})
assert any('recorded lint state is WARN' in x for x in reasons(good,'vfx-asset-style-lint')),reasons(good,'vfx-asset-style-lint')
# capture
bad=clone(good); del bad['spec']['capture']; expect('.vfx without capture',state(bad,'vfx-asset-capture'),'HUMAN_REQUIRED')
bad=clone(good); bad['spec']['capture']['alive_peak']=299; expect('capture differs from stats.json',state(bad,'vfx-asset-capture'),'FAIL')
bad=clone(good); bad['spec']['capture']['contact_sheet_hash']='4'*64; expect('capture contact sheet differs',state(bad,'vfx-asset-capture'),'FAIL')
bad=clone(good); bad['spec']['capture']['stats_hash']='XYZ'; expect('capture malformed',state(bad,'vfx-asset-capture'),'FAIL')
bad=clone(good); bad['spec']['capture']['seed']=-1; expect('capture seed malformed',state(bad,'vfx-asset-capture'),'FAIL')
expect('capture without project roots',state(good,'vfx-asset-capture',ctx_for(roots=False)),'PASS')
prefab=clone(fasset); prefab['spec']['asset_path']='Assets/VFX/a.prefab'
expect('prefab without capture',state(prefab,'vfx-asset-capture'),None)
expect('prefab visual review',state(prefab,'vfx-visual-review'),'HUMAN_REQUIRED')
assert any('vfx-visual-review' in x for x in reasons(prefab,'vfx-visual-review'))
# style lint
bad=clone(good); bad['spec']['style']['blob_revision']='0'*40; expect('lint of another profile revision',state(bad,'vfx-asset-style-lint'),'FAIL')
bad=clone(good); bad['spec']['lint']['state']='PASS'; expect('lint state differs from report',state(bad,'vfx-asset-style-lint'),'FAIL')
bad=clone(good); bad['spec']['lint']['state']='FAIL'; expect('lint state FAIL',state(bad,'vfx-asset-style-lint'),'FAIL')
bad=clone(good); bad['spec']['style']['profile_id']='VFX-style-missing'; expect('lint unknown profile',state(bad,'vfx-asset-style-lint'),'FAIL')
bad=clone(good); del bad['spec']['capture']; expect('lint without capture',state(bad,'vfx-asset-style-lint'),'FAIL')
bad=clone(good); bad['spec']['lint']['report_hash']='5'*64; expect('lint report not found',state(bad,'vfx-asset-style-lint'),'NOT_AVAILABLE')
expect('lint without project roots',state(good,'vfx-asset-style-lint',ctx_for(roots=False)),'NOT_AVAILABLE')
named=clone(fspec); named['spec']['style']='VFX-style-other'
expect('spec names another profile',state(good,'vfx-asset-style-lint',ctx_for([(spec_rel,named)])),'FAIL')
named['spec']['style']='VFX-style-001'; bare=clone(fasset)
expect('spec names a profile, no lint past draft',state(bare,'vfx-asset-style-lint',ctx_for([(spec_rel,named)])),'FAIL')
bare['status']='draft'; expect('spec names a profile, no lint at draft',state(bare,'vfx-asset-style-lint',ctx_for([(spec_rel,named)])),'WARN')
# A capture edited after the lint (stats_hash recorded anew): vfx_style.py lint now computes other rows.
original=(cap/'stats.json').read_bytes(); edited=json.loads(original); edited['alive']['peak']=5000
(cap/'stats.json').write_text(json.dumps(edited,indent=2),encoding='utf-8',newline='\n')
bad=clone(good); bad['spec']['capture'].update(stats_hash=sha(cap/'stats.json'),alive_peak=5000)
expect('lint stale against the capture',state(bad,'vfx-asset-style-lint'),'FAIL')
assert any('budget-alive' in x for x in reasons(bad,'vfx-asset-style-lint')),reasons(bad,'vfx-asset-style-lint')
expect('old stats hash no longer found',state(good,'vfx-asset-style-lint'),'NOT_AVAILABLE')
(cap/'stats.json').write_bytes(original)
# textures
expect('textures without verified approval past draft',state(good,'vfx-asset-textures',ctx_for(approval={'state':'missing','reasons':['no record']})),'FAIL')
draft=clone(good); draft['status']='draft'
expect('textures without verified approval at draft',state(draft,'vfx-asset-textures',ctx_for(approval={'state':'missing','reasons':['no record']})),'WARN')
bad=clone(good); bad['spec']['textures'][0]['gen_run_id']='AGEN-missing'; expect('textures unknown gen-run',state(bad,'vfx-asset-textures'),'FAIL')
bad['status']='draft'; expect('textures unknown gen-run at draft',state(bad,'vfx-asset-textures'),'WARN')
run_rel,run=base['AGEN-fire-bolt-glow-001']; unapproved=clone(run); unapproved['status']='proposed'
expect('textures gen-run not approved',state(good,'vfx-asset-textures',ctx_for([(run_rel,unapproved)])),'FAIL')
bad=clone(good); bad['spec']['textures'][0]['output_hash']='6'*64; expect('textures output not of the gen-run',state(bad,'vfx-asset-textures'),'FAIL')
bad['status']='draft'; expect('textures output not of the gen-run at draft',state(bad,'vfx-asset-textures'),'FAIL')
other=clone(run); other['spec']['style']['id']='pixel-art'
expect('textures gen-run in another asset-gen style',state(good,'vfx-asset-textures',ctx_for([(run_rel,other)])),'FAIL')
print('VFX style and evidence checks: %d passed, 0 failed' % n)
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
jq -e '.nodes.effect.domain == "vfx" and .nodes.effect.lead_skill == "vfx" and (.waves|length) == 3 and (.nodes|keys|length) == 3' "$T/plan.json" >/dev/null
python3 -B "$ROOT/scripts/factory-workflow.py" status "$T/workflow.json" --json > "$T/status.json"
jq -e '.states.effect == "blocked" and (.waves|length) == 3' "$T/status.json" >/dev/null
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
echo 'vfx workflow: PASS'
