#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp_win)" || exit 1; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/author/ui"; git -C "$T/author" init -q -b main
export TMPDIR="$T" RPG_FACTORY_STATE_DIR="$T/state"
pass=0; fail=0
ok(){ pass=$((pass+1)); echo "PASS $1"; }
no(){ fail=$((fail+1)); echo "FAIL $1"; }
for f in "$ROOT"/templates/ui/*.md; do cp "$f" "$T/author/ui/$(basename "$f")"; done
python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/author" --registry "$ROOT/registry.json" >"$T/lint.log" 2>&1 && ok 'all UI templates validate as draft' || no 'all UI templates validate as draft'
git -C "$T/author" config user.name Fixture; git -C "$T/author" config user.email fixture@example.test
git -C "$T/author" add ui; git -C "$T/author" commit -qm 'fixture drafts'
python3 -B - "$T/author/ui/ui-handoff.md" <<'PY2'
import json,re,sys
p=sys.argv[1];s=open(p,encoding='utf-8').read();m=re.match(r'\A---json\s*\n(.*?)\n---',s,re.S);o=json.loads(m.group(1));o['status']='released';open(p,'w',encoding='utf-8').write('---json\n'+json.dumps(o)+'\n---\n')
PY2
git -C "$T/author" add ui/ui-handoff.md; git -C "$T/author" commit -qm 'fixture illegal lifecycle shortcut'
if python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/author" --registry "$ROOT/registry.json" >"$T/shortcut.log" 2>&1; then no 'lifecycle shortcut is rejected'; else ok 'lifecycle shortcut is rejected'; fi
# Direct plugin rule fixtures keep every failure independent and readable.
python3 -B - "$ROOT" <<'PY' >"$T/plugin.log" 2>&1
import importlib.util,sys;sys.path.insert(0,sys.argv[1]+'/scripts/checks')
from types import SimpleNamespace
p=sys.argv[1]+'/scripts/checks/domains/ui.py';s=importlib.util.spec_from_file_location('uiq',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
ctx=SimpleNamespace(artifacts={},tools=lambda name:None)
def states():
 a={'kind':'screen-spec','spec':{'screen_id':'x','states':{},'elements':[],'platforms':['mobile']}}
 assert any(x.check=='ui-screen-states' and x.state=='FAIL' for x in m.check(a,ctx))
def interaction():
 a={'kind':'screen-spec','spec':{'states':{x:{'implemented':True} for x in ('empty','loading','success','error','disabled')},'elements':[{}],'platforms':['mobile']}}
 assert any(x.check=='ui-interactions-accessibility' and x.state=='FAIL' for x in m.check(a,ctx))
def navigation():
 a={'kind':'ia-map','spec':{'entry_screen':'a','screens':['a','b'],'navigation':[]}}
 assert any(x.check=='ui-navigation-graph' and x.state=='FAIL' for x in m.check(a,ctx))
def handoff():
 a={'kind':'ui-handoff','spec':{'screens':[{'screen_id':'x','acceptance_criteria':[{'id':'AC1','test':'test'}]}]}}
 assert any(x.check=='ui-handoff-acceptance' and x.state=='FAIL' for x in m.check(a,ctx))
def tokens():
 a={'kind':'design-tokens','spec':{'tokens':{'color.bad':'red','space.bad':-1}}}
 assert any(x.check=='ui-token-format' and x.state=='FAIL' for x in m.check(a,ctx))
for f in (states,interaction,navigation,handoff,tokens): f()
print('PASS domain rule failure cases')
PY
[ $? -eq 0 ] && ok 'domain rule failure cases' || no 'domain rule failure cases'
python3 -B - "$ROOT" "$T" <<'PY' >"$T/adapter.log" 2>&1
import importlib.util,sys,os
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1]+'/scripts/checks');p=sys.argv[1]+'/scripts/checks/domains/ui.py';sp=importlib.util.spec_from_file_location('uiq',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);ctx=SimpleNamespace(artifacts={},tools=lambda n:None)
a={'kind':'screen-spec','spec':{'screen_id':'x','states':{x:{'implemented':True} for x in ('empty','loading','success','error','disabled')},'elements':[],'platforms':['mobile'],'components':[],'tokens':[]}}
out=list(m.check(a,ctx));assert all(x.state=='PASS' for x in out if x.check!='ui-figma-adapter');assert next(x for x in out if x.check=='ui-figma-adapter').state=='NOT_AVAILABLE'
sys.path.insert(0,sys.argv[1]+'/scripts');from lib import tools
fake=Path(sys.argv[2])/'fake-figma.py';fake.write_text("print('Fake Figma adapter 1')\n");os.environ['RPG_FACTORY_TOOL_FIGMA']=str(fake);ctx.tools=tools.find_tool
out=list(m.check(a,ctx));assert next(x for x in out if x.check=='ui-figma-adapter').state=='HUMAN_REQUIRED'
os.environ.pop('RPG_FACTORY_TOOL_FIGMA')
a['spec']['figma']={'file_key':'abc_12','node_id':'12:34'};out=list(m.check(a,ctx));assert next(x for x in out if x.check=='ui-figma-visual-verification').state=='HUMAN_REQUIRED'
print('PASS valid production screen and optional Figma states')
PY
[ $? -eq 0 ] && ok 'valid screen and optional Figma states' || no 'valid screen and optional Figma states'
python3 -B - "$ROOT" "$T" <<'PY' >"$T/workflow.log" 2>&1
import json,sys
root,t=sys.argv[1:];spec={'id':'ui-sample','title':'UI sample','goal':'Ship a UI flow','targets':[{'id':'requirements','kind':'ux-requirements','sources':[],'acceptance':['Users can complete the task']},{'id':'screen','kind':'screen-spec','sources':['requirements'],'acceptance':['Screen states are complete']},{'id':'client','kind':'implementation','repo':'client','paths':['Assets/Scripts/UI/'],'sources':['screen'],'acceptance':['UI implemented']}],'existing':[]}
source={'id':'DESIGN-ui-001','kind':'feature-spec','domain':'design','status':'approved','title':'Source feature','upstream':[],'acceptance':[],'trace':[],'sources':[],'spec':{}}
open(t+'/author/design.artifact.json','w').write(json.dumps(source))
screen={'id':'screen','kind':'screen-spec','domain':'ui','status':'draft','title':'Screen','upstream':[{'id':'DESIGN-ui-001','rev':'0'*40}],'acceptance':[],'trace':[],'sources':[],'spec':{}}
open(t+'/author/screen.artifact.json','w').write(json.dumps(screen))
open(t+'/workflow.json','w').write(json.dumps(spec))
PY
python3 -B "$ROOT/scripts/factory-workflow.py" plan "$T/workflow.json" --authoring "$T/author" --json >"$T/plan.json" 2>"$T/plan.log" && python3 -B - "$T/plan.json" <<'PY2'
import json,sys
p=json.load(open(sys.argv[1])); assert {"screen","client"} <= p["nodes"].keys() and len(p["waves"]) >= 2
PY2
[ $? -eq 0 ] && ok 'workflow plan includes UI/client nodes and waves' || no 'workflow plan includes UI/client nodes and waves'
python3 -B "$ROOT/scripts/factory-workflow.py" status "$T/workflow.json" --authoring "$T/author" --json >"$T/status.json" 2>"$T/status.log" && python3 -B - "$T/status.json" <<'PY2'
import json,sys
p=json.load(open(sys.argv[1])); assert p["schema"]=="rpg-factory.workflow-status/1" and p["states"].get("screen")=="stale" and p["stale_upstream"] and p["waves"]
PY2
[ $? -eq 0 ] && ok 'workflow status detects stale UI upstream and reports waves' || no 'workflow status detects stale UI upstream and reports waves'
[ "$fail" -eq 0 ] || exit 1
echo "UI workflow tests: PASS $pass FAIL $fail"
