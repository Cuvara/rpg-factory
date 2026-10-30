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
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["waves"]==[["art3d","design"],["ui","vfx"],["art"],["impl"]]' "$TMP/out" || exit 1
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
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["waves"]==[["design","upstream-art3d-asset-to-vfx"],["ui"],["art2d"],["vfx"],["impl"]]; assert [(e["from"],e["to"]) for e in p["edges"] if e["from"] in ("design","ui","art2d","vfx") and e["to"] in ("ui","art2d","vfx","impl")]' "$TMP/out" || exit 1
echo 'PASS multi-domain workflow orders registered dependencies with parallel roots'
python3 -B "$ROOT/scripts/factory-workflow.py" status "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --json >"$TMP/status" || exit 1
python3 -B "$ROOT/scripts/factory-workflow.py" dispatch "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --node design --json >"$TMP/dispatch" || exit 1
python3 -B "$ROOT/scripts/factory-workflow.py" report "$TMP/design.json" --registry "$TMP/registry.json" --authoring "$TMP/authoring" --json >"$TMP/report" || exit 1
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
modspec=importlib.util.spec_from_file_location('workflow',root/'scripts/factory-workflow.py'); mod=importlib.util.module_from_spec(modspec); modspec.loader.exec_module(mod)
node={'id':'x','artifact_id':'x'}; plan={'existing':{'x':{'id':'x','rev':'1','status':'rejected','path':'x'}},'nodes':{'x':node},'edges':[]}
assert mod.state_for(node,plan,{})=='rejected'; plan['existing']['x'].update(status='draft',rev='2'); assert mod.state_for(node,plan,{})=='draft'; plan['existing']['x'].update(status='proposed',rev='3'); assert mod.state_for(node,plan,{})=='proposed'
plan['existing']['x'].update(status='approved'); assert mod.state_for(node,plan,{'x':{'results':[{'state':'HUMAN_REQUIRED'}]}})=='human-required'
PY
[ "$?" -eq 0 ] || exit 1
echo 'PASS stale upstream, ordered revalidation, rejected recovery, approval state, and ID/revision-only dispatch inputs'
echo 'workflow tests: 11 run, 11 passed, 0 failed'
