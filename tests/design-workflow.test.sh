#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp_win)" || exit 1; trap 'rm -rf "$T"' EXIT
python3 - "$ROOT" "$T" <<'PY'
import importlib.util,json,pathlib,sys,subprocess
root=pathlib.Path(sys.argv[1]); temp=pathlib.Path(sys.argv[2]); spec=importlib.util.spec_from_file_location('lint',root/'scripts/checks/artifact-lint.py'); lint=importlib.util.module_from_spec(spec);spec.loader.exec_module(lint)
reg=json.loads((root/'registry.json').read_text());common=json.loads((root/'docs/artifact.schema.json').read_text())
for p in sorted((root/'templates/design').glob('*.md')):
 obj=json.loads(p.read_text().split('\n',1)[1].rsplit('\n---',1)[0]); errors=lint.validate(obj,reg,common); assert not errors,(p.name,errors)
assert set(p.stem for p in (root/'templates/design').glob('*.md'))==set(reg['domains']['design']['artifact_kinds'])
print('PASS all kind templates validate as draft')
sys.path.insert(0,str(root/'scripts/checks')); spec=importlib.util.spec_from_file_location('design',root/'scripts/checks/domains/design.py'); plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)
class C: registry=reg; artifacts={}
for name,obj,expected in [
 ('bare-number',{'kind':'game-concept','spec':{'count':3}},'design-numbers'),
 ('envelope',{'kind':'game-concept','schema_version':2,'spec':{}},'design-envelope'),
 ('no-sources',{'kind':'gameplay-system','spec':{'economy':{'currencies':['x'],'sources':[],'sinks':['y']}}},'design-economy'),
 ('bad-curve',{'kind':'level-spec','spec':{'difficulty_curve':[3,2]}},'design-difficulty'),
 ('handoff',{'kind':'technical-handoff','spec':{'acceptance_criteria':[{'id':'A','text':'works'}],'engineering_dependencies':['not-a-module'] }},'design-technical-handoff'),
 ('unresolved-source',{'kind':'feature-spec','schema_version':2,'sources':['GD-missing-001'],'spec':{'game_concept':'GD-missing-001'}},'design-sources'),
 ('orphan-content',{'kind':'npc-spec','spec':{'game_concept':'GD-missing-001','content_refs':['GD-missing-002']}},'design-content-ids')]:
 C.artifacts={}; C.registry=reg; C.repo='';C.artifact_path='';C.tools=lambda _:None
 results=plugin.check(obj,C()); assert any(r.check==expected and r.state=='FAIL' for r in results),(name,[(r.check,r.state,r.reasons) for r in results])
print('PASS domain rule failure cases')
# Binding values pass only when the shared verifier confirms this artifact revision.
binding={'id':'GD-binding-001','kind':'gameplay-system','binding_values':True,'spec':{'damage':12}}
class ApprovalContext(C):
 def __init__(self,state,reasons=None): self.registry=reg; self.artifacts={}; self.state=state; self.reasons=reasons or []
 def approval(self,artifact_id): assert artifact_id==binding['id']; return {'state':self.state,'reasons':self.reasons}
for state,expected,reasons in [('verified','PASS',[]),('missing','HUMAN_REQUIRED',['human gameplay-rules approval required']),('invalid','FAIL',['signature invalid']),('untrusted','FAIL',['signer not trusted'])]:
 results=plugin.check(binding,ApprovalContext(state,reasons)); number=next(r for r in results if r.check=='design-numbers')
 assert number.state==expected,(state,number.state,number.reasons)
 if state in ('invalid','untrusted'): assert number.reasons==reasons,(state,number.reasons)
class NoApprovalContext: registry=reg; artifacts={}
number=next(r for r in plugin.check(binding,NoApprovalContext()) if r.check=='design-numbers')
assert number.state=='HUMAN_REQUIRED',(number.state,number.reasons)
print('PASS binding approval states: verified, missing, invalid, untrusted, and unavailable API')
# Each production quality rule also accepts a complete, linked draft fixture.
concept={'id':'GD-concept-001','kind':'game-concept','schema_version':2,'authors':[{'kind':'agent','id':'tester'}],'sources':[],'spec':{}}
system={'id':'GD-system-001','kind':'gameplay-system','schema_version':2,'authors':[{'kind':'agent','id':'tester'}],'sources':['GD-concept-001'],'spec':{'game_concept':'GD-concept-001','gameplay_systems':['GD-system-001'],'economy':{'currencies':['coin'],'sources':['quest'],'sinks':['vendor']},'difficulty_curve':[{'value':1,'status':'proposal','rationale':'starting point'},{'value':2,'status':'proposal','rationale':'later stage'}]}}
feature={'id':'GD-feature-001','kind':'feature-spec','schema_version':2,'authors':[{'kind':'agent','id':'tester'}],'sources':['GD-concept-001','GD-system-001'],'spec':{'game_concept':'GD-concept-001','gameplay_systems':['GD-system-001']}}
level={'id':'GD-level-001','kind':'level-spec','schema_version':2,'authors':[{'kind':'agent','id':'tester'}],'sources':['GD-concept-001','GD-system-001'],'spec':{'game_concept':'GD-concept-001','gameplay_systems':['GD-system-001'],'content_refs':['GD-npc-001'],'difficulty_curve':[{'value':1,'status':'proposal','rationale':'entry'}]}}
npc={'id':'GD-npc-001','kind':'npc-spec','schema_version':2,'authors':[{'kind':'agent','id':'tester'}],'sources':['GD-concept-001','GD-system-001'],'spec':{'game_concept':'GD-concept-001','gameplay_systems':['GD-system-001'],'content_refs':['GD-level-001']}}
handoff={'id':'GD-handoff-001','kind':'technical-handoff','schema_version':2,'authors':[{'kind':'agent','id':'tester'}],'sources':['GD-feature-001'],'spec':{'state_and_data_requirements':['state'],'events_and_interactions':['event'],'edge_cases':['edge'],'acceptance_criteria':[{'id':'AC1','text':'testable','verify':'test'}],'engineering_dependencies':['server:backend/gameserver-dotnet/']}}
C.artifacts={x['id']:(x['id'],x) for x in [concept,system,feature,level,npc,handoff]}
for art in [system,feature,level,npc,handoff]:
 failures=[(r.check,r.reasons) for r in plugin.check(art,C()) if r.state!='PASS']
 assert not failures,(art['kind'],failures)
print('PASS linked production fixtures pass domain rules')
# Run the shared quality workflow over a committed, linked production set.
author=temp/'authoring'; folder=author/'design'; folder.mkdir(parents=True)
concept_art={'schema_version':2,'id':'GD-concept-001','kind':'game-concept','domain':'design','status':'draft','title':'Concept','authors':[{'kind':'agent','id':'tester'}],'sources':[],'upstream':[],'acceptance':[],'trace':[],'spec':{'concept':'Adventure','target_audience':'Players','pillars':['Discovery'],'genre':'RPG','platforms':['PC'],'usp':'Choices','design_constraints':['Scope']}}
system_art={'schema_version':2,'id':'GD-system-001','kind':'gameplay-system','domain':'design','status':'draft','title':'Combat','authors':[{'kind':'agent','id':'tester'}],'sources':['GD-concept-001'],'upstream':[],'acceptance':[],'trace':[],'spec':{'system_type':'combat','core_loop':'TBD','mechanics':['TBD'],'progression':['TBD'],'combat_interaction':['TBD'],'economy':{'currencies':['coin'],'sources':['quest'],'sinks':['vendor']},'difficulty_balancing':['TBD'],'difficulty_curve':[{'value':1,'status':'proposal','rationale':'entry'}],'meta_progression':['TBD']}}
feature_art={'schema_version':2,'id':'GD-feature-001','kind':'feature-spec','domain':'design','status':'draft','title':'Feature','authors':[{'kind':'agent','id':'tester'}],'sources':['GD-concept-001','GD-system-001'],'upstream':[],'acceptance':[],'trace':[],'spec':{'summary':'Feature','goals':['Goal'],'requirements':[{'id':'R1','description':'Works'}],'game_concept':'GD-concept-001','gameplay_systems':['GD-system-001']}}
for art in (concept_art,system_art,feature_art): (folder/(art['id']+'.artifact.json')).write_text(json.dumps(art))
subprocess.run(['git','init','-q','-b','main',str(author)],check=True);subprocess.run(['git','-C',str(author),'config','user.email','test@example.com'],check=True);subprocess.run(['git','-C',str(author),'config','user.name','Test'],check=True);subprocess.run(['git','-C',str(author),'add','.'],check=True);subprocess.run(['git','-C',str(author),'commit','-qm','production fixtures'],check=True)
quality=subprocess.run([sys.executable,'-B',str(root/'scripts/checks/artifact-quality.py'),str(author),'--registry',str(root/'registry.json'),'--domain','design','--json'],capture_output=True,text=True,check=True)
report=json.loads(quality.stdout); assert report['summary']['FAIL']==0,report
print('PASS full artifact-quality workflow accepts linked production artifacts')


PY
[ "$?" -eq 0 ] || exit 1
python3 - "$ROOT" "$T" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); temp=pathlib.Path(sys.argv[2]); spec=temp/'workflow.json'
spec.write_text(json.dumps({'id':'design-production','title':'Design production','goal':'Produce system and handoff','targets':[{'id':'concept','kind':'game-concept','sources':[],'acceptance':['Concept ready']},{'id':'system','kind':'gameplay-system','sources':['concept'],'acceptance':['System ready']},{'id':'handoff','kind':'technical-handoff','sources':['system'],'acceptance':['Handoff ready']}],'existing':[]}))
plan=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'plan',str(spec),'--json'],capture_output=True,text=True,check=True); plan=json.loads(plan.stdout)
assert plan['waves']==[['concept'],['system'],['handoff']],plan['waves']
status=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'status',str(spec),'--json'],capture_output=True,text=True,check=True); states=json.loads(status.stdout)['states']
assert states=={'concept':'missing','system':'blocked','handoff':'blocked'},states
print('PASS workflow plan waves and missing/blocked statuses across design production nodes')
PY
[ "$?" -eq 0 ] || exit 1
echo 'design-workflow: 31 run, 31 passed, 0 failed'
