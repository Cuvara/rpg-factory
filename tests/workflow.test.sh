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
python3 -B "$ROOT/scripts/factory-workflow.py" status "$TMP/eng.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --json >"$TMP/status" || exit 1
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["states"]["impl"]=="blocked"' "$TMP/status" || exit 1
echo 'PASS missing dependency is blocked and dispatch refuses it with exit 2'
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
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["waves"]==[["design"],["art3d","ui"],["art","vfx"],["impl"]]' "$TMP/out" || exit 1
echo 'PASS handoff graph produces ordered waves with parallel siblings'
cat >"$TMP/art2d.json" <<'EOF'
{"id":"art2d","title":"Art","goal":"Art","targets":[{"id":"art","kind":"art2d-brief","sources":[],"acceptance":["Brief"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/art2d.json" --registry "$TMP/registry.json" --json >"$TMP/out"
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); ds={n["domain"] for n in p["nodes"].values()}; assert {"design","ui","art2d"} <= ds and len(p["waves"])==3' "$TMP/out" || exit 1
echo 'PASS implicit design and UI upstream handoffs for art2d'
python3 -m json.tool "$TMP/registry.json" >/dev/null || exit 1
cat >"$TMP/routes.json" <<'EOF'
{"id":"routes","title":"Routes","goal":"Exercise registered routes","targets":[{"id":"art3d","kind":"art3d-asset","sources":[],"acceptance":["Asset"]},{"id":"impl3d","kind":"implementation","repo":"client","paths":["Assets/Scripts/Models/"],"sources":["art3d"],"acceptance":["Integrated"]},{"id":"vfx","kind":"vfx-spec","sources":[],"acceptance":["Effect"]},{"id":"implvfx","kind":"implementation","repo":"client","paths":["Assets/Scripts/VFX/"],"sources":["vfx"],"acceptance":["Integrated"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/routes.json" --registry "$TMP/registry.json" --json >"$TMP/out" || exit 1
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert {"art3d","impl3d","vfx","implvfx"} <= p["nodes"].keys(); assert {("art3d","impl3d"),("vfx","implvfx")} <= {(e["from"],e["to"]) for e in p["edges"]}; assert p["nodes"]["impl3d"]["domain"]==p["nodes"]["implvfx"]["domain"]=="engineering"' "$TMP/out" || exit 1
echo 'PASS art3d and vfx routes to engineering'
cat >"$TMP/fullchain.json" <<'EOF'
{"id":"chain","title":"Chain","goal":"Full chain","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["A"]},{"id":"ui","kind":"ui-spec","sources":["design"],"acceptance":["B"]},{"id":"art2d","kind":"art2d-brief","sources":["ui"],"acceptance":["C"]},{"id":"impl","kind":"implementation","repo":"client","paths":["Assets/Scripts/"],"sources":["art2d"],"acceptance":["D"]},{"id":"vfx","kind":"vfx-spec","sources":["art2d"],"acceptance":["E"]}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/fullchain.json" --registry "$TMP/registry.json" --json >"$TMP/out" || exit 1
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); expected={("art2d","impl"),("art2d","vfx"),("design","art2d"),("design","impl"),("design","ui"),("design","vfx"),("design","upstream-art3d-asset-to-vfx"),("ui","art2d"),("ui","impl"),("upstream-art3d-asset-to-vfx","impl"),("upstream-art3d-asset-to-vfx","vfx"),("vfx","impl")}; actual={(e["from"],e["to"]) for e in p["edges"]}; assert actual==expected,(actual,expected); assert p["waves"]==[["design"],["ui","upstream-art3d-asset-to-vfx"],["art2d"],["vfx"],["impl"]]; assert p["nodes"]["impl"]["domain"]=="engineering"; assert ("upstream-art3d-asset-to-vfx","vfx") in actual' "$TMP/out" || exit 1
echo 'PASS multi-domain workflow orders registered dependencies with parallel roots'
cat >"$TMP/new-kinds.json" <<'EOF'
{"id":"new-kinds","title":"New kinds","goal":"Route every production discipline","targets":[{"id":"ds-system","kind":"gameplay-system"},{"id":"ds-handoff","kind":"technical-handoff"},{"id":"ui-screen","kind":"screen-spec"},{"id":"a2-concept","kind":"concept-2d"},{"id":"a2-export","kind":"runtime-export-2d"},{"id":"a3-model","kind":"model-spec"},{"id":"fx-spec","kind":"vfx-spec"}],"existing":[]}
EOF
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$TMP/new-kinds.json" --registry "$TMP/registry.json" --json >"$TMP/new-kinds-plan" || exit 1
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); n=p["nodes"]; expected={"ds-system":("design","game-design"),"ds-handoff":("design","game-design"),"ui-screen":("ui","ui-ux"),"a2-concept":("art2d","art-2d"),"a2-export":("art2d","art-2d"),"a3-model":("art3d","art-3d"),"fx-spec":("vfx","vfx")}; assert all((n[k]["domain"],n[k]["lead_skill"])==v for k,v in expected.items()),[(k,n[k]["domain"],n[k]["lead_skill"]) for k in expected]; assert "sync_links" in p and all(not x["ordering"] for x in p["sync_links"])' "$TMP/new-kinds-plan" || exit 1
echo 'PASS new artifact kinds route to every registered production domain and lead'
python3 -B "$ROOT/scripts/factory-workflow.py" status "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --json >"$TMP/status" || exit 1
python3 -B "$ROOT/scripts/factory-workflow.py" dispatch "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --node design --json >"$TMP/dispatch" || exit 1
python3 -B "$ROOT/scripts/factory-workflow.py" report "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --json >"$TMP/report" || exit 1
python3 -B "$ROOT/scripts/factory-workflow.py" report "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" >"$TMP/report.txt" || exit 1
python3 - "$ROOT" "$TMP" <<'PY'
import importlib.util,json,pathlib,sys,subprocess
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('lint',root/'scripts/checks/artifact-lint.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for name,kind in [('out','workflow-plan'),('status','workflow-status'),('dispatch','workflow-dispatch'),('report','workflow-report')]:
    schema=json.loads((root/f'docs/schemas/{kind}.schema.json').read_text())
    value=json.loads((t/name).read_text())
    errors=m.schema_errors(value,schema,schema)
    assert not errors,(name,errors)
assert json.loads((t/'status').read_text())['states']['design']=='missing'
assert json.loads((t/'report').read_text())['overall']=='incomplete'
assert 'Validation:' in (t/'report.txt').read_text() and 'approval:' in (t/'report.txt').read_text()
contract=json.loads((t/'dispatch').read_text()); assert contract['allowed_write_paths'] and contract['inputs']==[]
for runner in ('print','orca','agent'):
    p=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'dispatch',str(t/'design.json'),'--registry',str(t/'registry.json'),'--authoring',str(t/'authoring'),'--node','design','--runner',runner],capture_output=True,text=True)
    assert p.returncode==0 and 'allowed_write_paths' in p.stdout and 'A demo' not in p.stdout
author=t/'authoring-contract'; folder=author/'design/features'; folder.mkdir(parents=True); artifact=folder/'DS-test-001.artifact.json'
artifact.write_text(json.dumps({'id':'DS-test-001','kind':'feature-spec','domain':'design','status':'approved','title':'SECRET ARTIFACT BODY','upstream':[],'acceptance':[],'trace':[]}))
subprocess.run(['git','init','-q','-b','main',str(author)],check=True); subprocess.run(['git','-C',str(author),'config','user.email','test@example.com'],check=True); subprocess.run(['git','-C',str(author),'config','user.name','Test'],check=True); subprocess.run(['git','-C',str(author),'add','.'],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','source'],check=True)
rev=subprocess.run(['git','-C',str(author),'hash-object',str(artifact)],capture_output=True,text=True,check=True).stdout.strip()
ws=t/'contract.json'; ws.write_text(json.dumps({'id':'contract','title':'Contract','goal':'Contract','targets':[{'id':'child','kind':'ui-spec','sources':['DS-test-001'],'acceptance':['Use source']}],'existing':['DS-test-001']}))
for runner in ('print','orca','agent'):
    p=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'dispatch',str(ws),'--authoring',str(author),'--node','child','--runner',runner],capture_output=True,text=True)
    assert p.returncode==0,(runner,p.stderr); assert 'DS-test-001' in p.stdout and rev in p.stdout and 'allowed_write_paths' in p.stdout and 'SECRET ARTIFACT BODY' not in p.stdout,(runner,p.stdout)
approval_repo=t/'authoring-approval'; approval_dir=approval_repo/'design/features'; approval_dir.mkdir(parents=True); approval_art=approval_dir/'DS-approval-001.artifact.json'
approval_art.write_text(json.dumps({'id':'DS-approval-001','kind':'feature-spec','domain':'design','status':'approved','title':'Needs approval','binding_values':True,'upstream':[],'acceptance':[],'trace':[]}))
subprocess.run(['git','init','-q','-b','main',str(approval_repo)],check=True); subprocess.run(['git','-C',str(approval_repo),'config','user.email','test@example.com'],check=True); subprocess.run(['git','-C',str(approval_repo),'config','user.name','Test'],check=True); subprocess.run(['git','-C',str(approval_repo),'add','.'],check=True); subprocess.run(['git','-C',str(approval_repo),'commit','-qm','approval fixture'],check=True)
approval_spec=t/'approval.json'; approval_spec.write_text(json.dumps({'id':'approval','title':'Approval','goal':'Approval required','targets':[{'id':'DS-approval-001','kind':'feature-spec','sources':[],'acceptance':[]}],'existing':[]}))
status_run=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'status',str(approval_spec),'--authoring',str(approval_repo),'--json'],capture_output=True,text=True,check=True); assert json.loads(status_run.stdout)['states']['DS-approval-001']=='human-required',status_run.stdout
report_run=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'report',str(approval_spec),'--authoring',str(approval_repo),'--json'],capture_output=True,text=True,check=True); approval_report=json.loads(report_run.stdout); assert approval_report['overall']=='incomplete' and approval_report['human_required']==['DS-approval-001'],approval_report
PY
[ "$?" -eq 0 ] || exit 1
echo 'PASS status, dispatch, report schemas and runner contracts'
python3 - "$ROOT" "$TMP" <<'PY'
import hashlib,importlib.util,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); author=t/'authoring-stale'; (author/'design/features').mkdir(parents=True); (author/'ui/specs').mkdir(parents=True)
subprocess.run(['git','init','-q','-b','main',str(author)],check=True); subprocess.run(['git','-C',str(author),'config','user.email','test@example.com'],check=True); subprocess.run(['git','-C',str(author),'config','user.name','Test'],check=True)
up=author/'design/features/design.artifact.json'; down=author/'ui/specs/ui.artifact.json'
up.write_text(json.dumps({'id':'design','kind':'feature-spec','domain':'design','status':'draft','title':'Design','upstream':[],'acceptance':[],'trace':[]})); old=subprocess.run(['git','-C',str(author),'hash-object',str(up)],capture_output=True,text=True,check=True).stdout.strip()
down.write_text(json.dumps({'id':'ui','kind':'ui-spec','domain':'ui','status':'draft','title':'UI','upstream':[{'id':'design','rev':old}],'acceptance':[],'trace':[]})); up.write_text(up.read_text()+' ')
subprocess.run(['git','-C',str(author),'add','.'],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','fixture'],check=True)
spec=t/'stale.json'; spec.write_text(json.dumps({'id':'stale','title':'Stale','goal':'stale','targets':[{'id':'design','kind':'feature-spec','sources':[],'acceptance':[]},{'id':'ui','kind':'ui-spec','sources':['design'],'acceptance':[]}],'existing':[]}))
p=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'status',str(spec),'--authoring',str(author),'--json'],capture_output=True,text=True,check=True); status=json.loads(p.stdout)
assert status['states']['ui']=='stale' and status['stale_upstream']==[{'node':'ui','upstream':['design']}] and status['revalidate']==['ui'],status
author=t/'authoring-recovery'; (author/'design/features').mkdir(parents=True); (author/'ui/specs').mkdir(parents=True)
parent_id='DS-recovery-001'; child_id='UI-recovery-001'; parent_path='design/features/DS-recovery-001.artifact.json'; child_path='ui/specs/UI-recovery-001.artifact.json'
parent={'schema_version':1,'id':parent_id,'kind':'feature-spec','domain':'design','status':'rejected','title':'Recovery parent','upstream':[],'acceptance':[{'id':'A1','text':'Feature works','verify':'test'}],'trace':[],'rejection':{'reason':'Original design failed review','by':'reviewer@example.com','date':'2026-10-30T00:00:00Z'},'spec':{'summary':'Recovery parent','goals':['Recover'],'requirements':[{'id':'A1','description':'Feature works'}]}}
child={'schema_version':1,'id':child_id,'kind':'ui-spec','domain':'ui','status':'draft','title':'Dependent UI','upstream':[],'acceptance':[{'id':'U1','text':'UI follows design','verify':'review'}],'trace':[],'spec':{'screen_id':'screen-recovery'}}
pp=author/parent_path; cp=author/child_path; pp.write_text(json.dumps(parent)); cp.write_text(json.dumps(child))
subprocess.run(['git','init','-q','-b','main',str(author)],check=True); subprocess.run(['git','-C',str(author),'config','user.email','author@example.com'],check=True); subprocess.run(['git','-C',str(author),'config','user.name','Author'],check=True); subprocess.run(['git','-C',str(author),'add','.'],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','rejected artifact with record'],check=True)
def blob(): return subprocess.run(['git','-C',str(author),'rev-parse',f'HEAD:{parent_path}'],capture_output=True,text=True,check=True).stdout.strip()
rejected_rev=blob(); ws=t/'recovery.json'; ws.write_text(json.dumps({'id':'recovery','title':'Recovery','goal':'Recover rejected artifact safely','targets':[{'id':parent_id,'kind':'feature-spec','sources':[],'acceptance':['Feature works']},{'id':child_id,'kind':'ui-spec','sources':[parent_id],'acceptance':['UI follows']}],'existing':[parent_id,child_id]}))
def workflow(command): return subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),command,str(ws),'--authoring',str(author),'--json'],capture_output=True,text=True)
status_run=workflow('status'); assert status_run.returncode==0,status_run.stderr; status=json.loads(status_run.stdout); assert status['states'][parent_id]=='rejected' and status['states'][child_id]=='blocked',(status,json.loads(workflow('report').stdout))
parent['status']='draft'; parent.pop('rejection'); pp.write_text(json.dumps(parent)); subprocess.run(['git','-C',str(author),'add',parent_path],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','recover rejected artifact to draft'],check=True)
draft_rev=blob(); assert draft_rev!=rejected_rev
status_run=workflow('status'); status=json.loads(status_run.stdout); assert status['states'][parent_id]=='draft' and status['states'][child_id]=='blocked' and parent_id in status['ready'],status
parent['status']='proposed'; pp.write_text(json.dumps(parent)); subprocess.run(['git','-C',str(author),'add',parent_path],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','propose recovery with acceptance'],check=True)
proposed_rev=blob(); assert proposed_rev!=draft_rev
status_run=workflow('status'); status=json.loads(status_run.stdout); assert status['states'][parent_id]=='proposed' and status['states'][child_id]=='blocked' and child_id not in status['ready'],status
parent['status']='reviewed'; pp.write_text(json.dumps(parent)); subprocess.run(['git','-C',str(author),'add',parent_path],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','submit recovered artifact for review'],check=True)
review_rev=blob(); review_dir=author/'reviews'/parent_id; review_dir.mkdir(parents=True); review=(review_dir/f'{review_rev}-reviewer@example.com.json'); review.write_text(json.dumps({'artifact':parent_id,'rev':review_rev,'reviewer':{'kind':'human','id':'reviewer@example.com'},'verdict':'approve','findings':[],'date':'2026-10-30T00:00:00Z'})); subprocess.run(['git','-C',str(author),'config','user.email','reviewer@example.com'],check=True); subprocess.run(['git','-C',str(author),'config','user.name','Reviewer'],check=True); subprocess.run(['git','-C',str(author),'add','reviews'],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','independent recovery review'],check=True)
status_run=workflow('status'); status=json.loads(status_run.stdout); assert status['states'][parent_id]=='reviewed' and status['states'][child_id]=='blocked' and child_id not in status['ready'],status
parent['status']='approved'; pp.write_text(json.dumps(parent)); subprocess.run(['git','-C',str(author),'config','user.email','author@example.com'],check=True); subprocess.run(['git','-C',str(author),'config','user.name','Author'],check=True); subprocess.run(['git','-C',str(author),'add',parent_path],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','approve recovered artifact'],check=True)
status_run=workflow('status'); status=json.loads(status_run.stdout); assert status['states'][parent_id]=='approved' and status['states'][child_id]=='draft' and status['ready']==[child_id],status
report_run=workflow('report'); report=json.loads(report_run.stdout); assert report['nodes'][parent_id]['status']=='approved' and report['nodes'][parent_id]['rev']!=rejected_rev and report['nodes'][child_id]['status']=='draft',report
PY
[ "$?" -eq 0 ] || exit 1
echo 'PASS stale upstream, ordered revalidation, end-to-end rejected recovery, approval state, and ID/revision-only dispatch inputs'
python3 -B - "$ROOT" "$TMP" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); author=t/'quality-failure-authoring'; (author/'design/features').mkdir(parents=True)
artifact={'schema_version':1,'id':'DS-quality-001','kind':'feature-spec','domain':'design','status':'approved','title':'Approved in front matter','upstream':[],'acceptance':[{'id':'A1','text':'Feature works','verify':'test'}],'trace':[],'authors':[],'spec':{'summary':'Quality gate','goals':['Fail closed'],'requirements':[{'id':'A1','description':'Feature works'}]}}
(author/'design/features/DS-quality-001.artifact.json').write_text(json.dumps(artifact))
subprocess.run(['git','init','-q','-b','main',str(author)],check=True); subprocess.run(['git','-C',str(author),'config','user.email','fixture@example.com'],check=True); subprocess.run(['git','-C',str(author),'config','user.name','Fixture'],check=True); subprocess.run(['git','-C',str(author),'add','.'],check=True); subprocess.run(['git','-C',str(author),'commit','-qm','approved front matter'],check=True)
spec=t/'quality-failure.json'; spec.write_text(json.dumps({'id':'quality-failure','title':'Quality failure','goal':'Fail closed','targets':[{'id':'DS-quality-001','kind':'feature-spec','sources':[],'acceptance':['Gated']},{'id':'impl','kind':'implementation','repo':'server','paths':['backend/gameserver-dotnet/'],'sources':['DS-quality-001'],'acceptance':['Implement']}],'existing':['DS-quality-001']}))
checker=t/'fake-artifact-quality.py'; checker.write_text("import json,os,sys\nmode=os.environ['FAKE_QUALITY_MODE']\nif mode=='exit': print(json.dumps({'results':[]})); sys.exit(23)\nelif mode=='invalid': print('{invalid json')\nelif mode=='nostate': print(json.dumps({'results':[{'artifact':'DS-quality-001','check':'lifecycle'}]}))\nelif mode=='badstate': print(json.dumps({'results':[{'artifact':'DS-quality-001','check':'lifecycle','state':'MAYBE','reasons':[]}]}))\nelse: print(json.dumps({'results':[{'artifact':'OTHER-001','check':'lifecycle','state':'PASS','reasons':[]}]}))\n")
for mode,fragment in [('exit','exited 23'),('invalid','invalid JSON'),('missing','no lifecycle result'),('nostate','invalid result'),('badstate','invalid result')]:
    env=dict(__import__('os').environ,FAKE_QUALITY_MODE=mode,RPG_FACTORY_ARTIFACT_QUALITY=str(checker))
    def run(command,*extra): return subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),command,str(spec),'--registry',str(t/'registry.json'),'--authoring',str(author),'--json',*extra],capture_output=True,text=True,env=env)
    status_run=run('status'); assert status_run.returncode==0,status_run.stderr; status=json.loads(status_run.stdout)
    assert status['states']['DS-quality-001']=='blocked' and status['states']['impl']=='blocked' and status['ready']==[],(mode,status)
    assert fragment in status['quality_check_unavailable']['DS-quality-001'],(mode,status)
    dispatch=run('dispatch','--node','impl'); assert dispatch.returncode==2 and 'not ready' in dispatch.stderr,(mode,dispatch.returncode,dispatch.stdout,dispatch.stderr)
    report_run=run('report'); assert report_run.returncode==0,report_run.stderr; report=json.loads(report_run.stdout)
    row=report['nodes']['DS-quality-001']; assert report['overall']=='incomplete' and row['status']=='blocked' and any(x['check']=='quality-check-unavailable' and fragment in ' '.join(x['reasons']) for x in row['validation']['results']),(mode,report)
print('PASS workflow fails closed for nonzero, invalid JSON, and missing quality results; approved front matter cannot ready dependent dispatch')
PY
[ "$?" -eq 0 ] || exit 1
python3 -B - "$ROOT" "$TMP" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); author=t/'sync-authoring'; (author/'ui/specs').mkdir(parents=True); (author/'vfx/specs').mkdir(parents=True)
vfx={'id':'VFX-sync-001','kind':'vfx-spec','domain':'vfx','status':'draft','title':'Cue effect','upstream':[],'acceptance':[],'trace':[],'spec':{}}
ui={'id':'UI-sync-001','kind':'screen-spec','domain':'ui','status':'draft','title':'Cue screen','upstream':[{'id':vfx['id'],'rev':'old-revision'}],'acceptance':[],'trace':[],'spec':{}}
(author/'vfx/specs/VFX-sync-001.artifact.json').write_text(json.dumps(vfx)); (author/'ui/specs/UI-sync-001.artifact.json').write_text(json.dumps(ui))
spec=t/'sync-status.json'; spec.write_text(json.dumps({'id':'sync-status','title':'Sync status','goal':'Revalidate synchronized cue peers','targets':[{'id':ui['id'],'kind':'screen-spec'},{'id':vfx['id'],'kind':'vfx-spec'}],'existing':[]}))
p=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'status',str(spec),'--registry',str(root/'registry.json'),'--authoring',str(author),'--json'],capture_output=True,text=True,check=True); status=json.loads(p.stdout)
assert status['states'][ui['id']]=='stale',status
assert any(x['contract']=='ui-vfx-sync' and ui['id'] in x['changed'] and vfx['id'] in x['needs_revalidation'] for x in status['sync_revalidation']),status
print('PASS sync contract reports the opposite side for revalidation without an ordering edge')
PY
[ "$?" -eq 0 ] || exit 1
echo 'workflow tests: 14 run, 14 passed, 0 failed'
