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
copy_ui_templates(){
  local source_dir="$1" destination_dir="$2"; shopt -s nullglob
  local files=("$source_dir"/*.md)
  [ "${#files[@]}" -gt 0 ] || return 1
  for f in "${files[@]}"; do cp "$f" "$destination_dir/$(basename "$f")" || return 1; done
  printf '%s\n' "${#files[@]}"
}
mkdir -p "$T/no-templates" "$T/copy-source"
printf 'template\n' > "$T/copy-source/one.md"; printf 'not a directory\n' > "$T/copy-target"
if copy_ui_templates "$T/no-templates" "$T/empty-dest" >/dev/null; then no 'empty template source is rejected'; else ok 'empty template source is rejected'; fi
if copy_ui_templates "$T/copy-source" "$T/copy-target" >/dev/null 2>&1; then no 'template copy error is rejected'; else ok 'template copy error is rejected'; fi
template_count=$(copy_ui_templates "$ROOT/templates/ui" "$T/author/ui" 2>/dev/null)
if [ -n "$template_count" ] && [ "$template_count" -gt 0 ]; then ok "nonempty UI template count: $template_count"; else no 'nonempty UI template count'; fi
if [ -n "$template_count" ] && [ "$template_count" -gt 0 ]; then
  python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/author" --registry "$ROOT/registry.json" >"$T/lint.log" 2>&1 && ok 'all UI templates validate as draft' || no 'all UI templates validate as draft'
else
  no 'UI template copy failed or template count was empty'
fi
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
python3 -B - "$ROOT" "$T" <<'PY3' >"$T/artifact-quality-ui.log" 2>&1
import copy,json,pathlib,re,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); repo=t/'quality-author'; (repo/'ui').mkdir(parents=True); (repo/'design').mkdir()
subprocess.run(['git','init','-q','-b','main',str(repo)],check=True)
def template(name, directory='ui'):
    raw=(root/'templates'/directory/f'{name}.md').read_text(encoding='utf-8'); return json.loads(re.search(r'\A---json\s*\n(.*?)\n---',raw,re.S).group(1))
def production_component():
    value=template('component-spec'); value['spec'].update({'variants':[{'name':'default','description':'Standard appearance.'}],'props':[{'name':'statusText','type':'string','description':'Text from a source artifact.'}],'states':[{'name':'default','description':'Ready state.'}],'tokens':['color.surface'],'accessibility':{'label':'Player status','focus_order':'After header','contrast_target':'WCAG AA','input_methods':['keyboard']}}); return value
source=template('game-concept','design'); screen=template('screen-spec'); component=production_component(); tokens=template('design-tokens'); handoff=template('ui-handoff')
source['spec']['concept']='Player status experience'; source_id=source['id']
screen['id']='UI-screen-valid-101'; screen['spec']['breakpoints']=[480,960]; screen['spec']['platforms']=[]; screen['sources']=[source_id]
screen['spec']['data_bindings']=[{'source_artifact_id':source_id,'field':'concept'}]
component['id']='UI-component-valid-102'; component['spec']['tokens']=['color.surface']
screen['spec']['components']=['status-panel']; screen['spec']['tokens']=['color.surface']
handoff['id']='UI-handoff-valid-103'
def save(name,obj): (repo/'ui'/f'{name}.artifact.json').write_text(json.dumps(obj),encoding='utf-8')
def run():
    p=subprocess.run([sys.executable,'-B',str(root/'scripts/checks/artifact-quality.py'),str(repo),'--registry',str(root/'registry.json'),'--json'],capture_output=True,text=True,encoding='utf-8')
    return p.returncode,json.loads(p.stdout)['results']
def state(rows,name): return next((x['state'] for x in rows if x['check']==name),None)
failures=[]
def expect(condition,label):
    if condition: print('CASE PASS '+label)
    else:
        print('CASE FAIL '+label); failures.append(label)
        print('CASE EVIDENCE '+json.dumps([(x['check'],x['state'],x['reasons']) for x in rows if x['state']=='FAIL'],sort_keys=True))
save('source',source); save('screen',screen); save('component',component); save('tokens',tokens); save('handoff',handoff)
code,rows=run(); expect(code==0 and state(rows,'ui-responsive-platform')=='PASS' and state(rows,'ui-data-bindings')=='PASS' and state(rows,'ui-component-quality')=='PASS' and state(rows,'ui-handoff-acceptance')=='PASS','valid breakpoints, resolved binding, populated component and unique handoff screen pass')
screen['spec']['breakpoints']=['not-a-number']; save('screen',screen); code,rows=run(); expect(code==1 and state(rows,'ui-responsive-platform')=='FAIL','review blindspot nonnumeric breakpoint fails')
screen['spec']['breakpoints']=[960,480]; save('screen',screen); code,rows=run(); expect(code==1 and state(rows,'ui-responsive-platform')=='FAIL','unordered breakpoints fail')
screen['spec']['breakpoints']=[480,960]; screen['spec']['data_bindings']=[{'id':'NONEXISTENT','value':'invented'}]; save('screen',screen); code,rows=run(); expect(code==1 and state(rows,'ui-data-bindings')=='FAIL' and 'requires source_artifact_id and field' in ' '.join(next((x for x in rows if x['check']=='ui-data-bindings'),{'reasons':[]})['reasons']),'review blindspot invented/incomplete binding fails')
screen['spec']['data_bindings']=[{'source_artifact_id':'NONEXISTENT','field':'concept'}]; save('screen',screen); code,rows=run(); expect(code==1 and state(rows,'ui-data-bindings')=='FAIL','unknown binding source id fails')
screen['spec']['data_bindings']=[{'source_artifact_id':source_id,'field':'missing.field'}]; save('screen',screen); code,rows=run(); expect(code==1 and state(rows,'ui-data-bindings')=='FAIL','unknown binding source field fails')
screen['spec']['data_bindings']=[{'source_artifact_id':source_id,'field':'concept'}]; save('screen',screen)
component['spec']={'component_id':'','variants':[],'props':[],'states':[],'tokens':[],'accessibility':{}}; save('component',component); code,rows=run(); expect(code==1 and state(rows,'ui-component-quality')=='FAIL' and state(rows,'schema')=='FAIL','review blindspot empty component fails schema and production quality')
component=production_component(); component['id']='UI-component-valid-102'; component['spec']['variants'][0]['name']=''; save('component',component); code,rows=run(); expect(code==1 and state(rows,'ui-component-quality')=='FAIL' and state(rows,'schema')=='FAIL','component variant missing required nested name fails')
component=production_component(); component['id']='UI-component-valid-102'; component['spec']['accessibility']['label']=''; save('component',component); code,rows=run(); expect(code==1 and state(rows,'ui-component-quality')=='FAIL' and state(rows,'schema')=='FAIL','component accessibility requirement missing fails')
component=production_component(); component['id']='UI-component-valid-102'; component['spec']['tokens']=['unknown.token']; save('component',component); code,rows=run(); expect(code==1 and state(rows,'ui-component-quality')=='FAIL','unknown component token fails')
component=production_component(); component['id']='UI-component-valid-102'; save('component',component)
handoff['spec']['screens'][0]['screen_id']='DOES-NOT-EXIST'; save('handoff',handoff); code,rows=run(); expect(code==1 and state(rows,'ui-handoff-acceptance')=='FAIL','review blindspot missing handoff screen fails')
handoff['spec']['screens'][0]['screen_id']='home'; save('handoff',handoff); screen['spec']['screen_id']='home'; save('screen',screen); duplicate=copy.deepcopy(screen); duplicate['id']='UI-screen-duplicate-104'; save('duplicate',duplicate); code,rows=run(); expect(code==1 and state(rows,'ui-handoff-acceptance')=='FAIL' and 'multiple screen-spec' in ' '.join(next((x for x in rows if x['check']=='ui-handoff-acceptance'),{'reasons':[]})['reasons']),'duplicate handoff screen id fails')
screen['spec']['screen_id']='home'; (repo/'ui'/'duplicate.artifact.json').unlink(); save('screen',screen); code,rows=run(); expect(code==0 and state(rows,'ui-handoff-acceptance')=='PASS','handoff resolving to exactly one screen passes')
if failures: raise SystemExit('failed cases: '+', '.join(failures))
print('PASS artifact-quality UI positive cases: ordered numeric breakpoints, resolved source field, complete component/token reference, unique handoff screen')
print('PASS artifact-quality UI negative cases: invalid and unordered breakpoints, blindspot invented/incomplete binding, unknown source/field, empty component, unknown component token, missing and duplicate handoff screens')
PY3
if [ $? -eq 0 ]; then ok 'artifact-quality UI negative and positive integration cases'; else cat "$T/artifact-quality-ui.log"; no 'artifact-quality UI negative and positive integration cases'; fi
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
