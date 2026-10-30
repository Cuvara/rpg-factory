#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; T="${TMPDIR:-/tmp}/artifact-quality-$$"; mkdir -p "$T/repo/specs" "$T/repo/reviews"; trap 'rm -rf "$T"' EXIT
cat > "$T/reg.json" <<EOF
{"domains":{"fixture":{"artifact_kinds":["spec"],"quality_plugin":"scripts/checks/domains/noop.py"}},"artifact_lifecycles":{"spec":{"states":["draft","proposed","reviewed","approved","in-implementation","verified","released","rejected","blocked"],"transitions":{"draft":["proposed"],"proposed":["reviewed"],"reviewed":["approved"],"approved":["in-implementation"],"in-implementation":["verified"],"verified":["released"],"rejected":["draft"]},"requirements":{"proposed":{"acceptance":true},"reviewed":{"independent_review":true},"rejected":{"rejection_record":true},"blocked":{"blocked_by":true}}}},"kind_schemas":{"spec":"docs/schemas/kinds/feature-spec.schema.json"}}
EOF
git -C "$T/repo" init -q -b main; git -C "$T/repo" config user.email test@example.com; git -C "$T/repo" config user.name Test
cat > "$T/repo/specs/a.artifact.json" <<'EOF'
{"schema_version":1,"id":"FX-one-001","kind":"spec","domain":"fixture","status":"draft","title":"One","upstream":[],"acceptance":[{"id":"A1","text":"Works","verify":"test"}],"trace":[],"authors":[{"kind":"human","id":"author"}],"spec":{"summary":"One","goals":["Work"],"requirements":[{"id":"A1","description":"Works"}]}}
EOF
git -C "$T/repo" add .; git -C "$T/repo" commit -qm fixture
python3 -B - "$ROOT" "$T" <<'PY'
import importlib.util,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); p=t/'repo/specs/a.artifact.json'; obj=json.loads(p.read_text()); obj['status']='review'; p.write_text(json.dumps(obj))
PY
out=$(python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/repo" --registry "$T/reg.json" --json)
python3 -B - "$out" "$ROOT" "$T" <<'PY'
import importlib.util,json,pathlib,sys
d=json.loads(sys.argv[1]); root=pathlib.Path(sys.argv[2]); t=pathlib.Path(sys.argv[3]); assert d['schema']=='rpg-factory.validation/1'; assert any(x['state']=='PASS' and x['check']=='plugin-example' for x in d['results'])
sp=importlib.util.spec_from_file_location('lint',root/'scripts/checks/artifact-lint.py'); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
schema=json.loads((root/'docs/schemas/validation-result.schema.json').read_text()); assert not m.schema_errors(d,schema,schema)
assert any(x['state']=='WARN' and x['reasons']==['deprecated-state review -> proposed'] for x in d['results'])
import subprocess
p=t/'repo/specs/a.artifact.json'; obj=json.loads(p.read_text())
def check(mutator):
    value=dict(obj); mutator(value); p.write_text(json.dumps(value)); result=subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True,encoding='utf-8'); return json.loads(result.stdout)['results']
def has(rows, check_name, state, fragment=None): return any(x['check']==check_name and x['state']==state and (fragment is None or fragment in ' '.join(x['reasons'])) for x in rows)
assert has(check(lambda x:x.update(spec=[])),'schema','FAIL')
assert has(check(lambda x:x.update(sources=['FX-missing-009'])),'dependencies','FAIL','unknown source')
assert has(check(lambda x:x.update(blocked_by=['FX-missing-009'],reason='waiting')),'dependencies','FAIL','unknown blocked_by')
rows=check(lambda x:x.update(status='released')); assert has(rows,'lifecycle','FAIL','illegal transition'), rows
rows=check(lambda x:x.update(status='rejected')); assert has(rows,'lifecycle','FAIL','rejection reason'), rows
rows=check(lambda x:x.update(status='blocked')); assert has(rows,'lifecycle','FAIL','blocked_by'), rows
obj['status']='reviewed'; p.write_text(json.dumps(obj)); rev=subprocess.run(['git','-C',str(t/'repo'),'rev-parse','HEAD:specs/a.artifact.json'],capture_output=True,text=True).stdout.strip(); review_dir=t/'repo/reviews/FX-one-001'; review_dir.mkdir(exist_ok=True); (review_dir/f'{rev}-author.json').write_text(json.dumps({'artifact':'FX-one-001','rev':rev,'reviewer':{'kind':'human','id':'author'},'verdict':'approve','findings':[],'date':'2026-10-30T00:00:00Z'})); rows=json.loads(subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True).stdout)['results']; assert has(rows,'lifecycle','FAIL','independent review')
obj['status']='proposed'; p.write_text(json.dumps(obj)); subprocess.run(['git','-C',str(t/'repo'),'add','specs/a.artifact.json'],check=True); subprocess.run(['git','-C',str(t/'repo'),'commit','-qm','proposed'],check=True); rev=subprocess.run(['git','-C',str(t/'repo'),'rev-parse','HEAD:specs/a.artifact.json'],capture_output=True,text=True).stdout.strip()
# Empty front-matter authors plus the same git identity used for review must fail.
obj['authors']=[]; obj['status']='reviewed'; p.write_text(json.dumps(obj)); subprocess.run(['git','-C',str(t/'repo'),'add','specs/a.artifact.json'],check=True); subprocess.run(['git','-C',str(t/'repo'),'commit','-qm','author omitted'],check=True); rev=subprocess.run(['git','-C',str(t/'repo'),'rev-parse','HEAD:specs/a.artifact.json'],capture_output=True,text=True).stdout.strip()
obj['status']='reviewed'; p.write_text(json.dumps(obj)); review_dir=t/'repo/reviews/FX-one-001'; review_dir.mkdir(exist_ok=True); review_path=review_dir/f'{rev}-test@example.com.json'; review_path.write_text(json.dumps({'artifact':'FX-one-001','rev':rev,'reviewer':{'kind':'human','id':'test@example.com'},'verdict':'approve','findings':[],'date':'2026-10-30T00:00:00Z'})); subprocess.run(['git','-C',str(t/'repo'),'add','reviews'],check=True); subprocess.run(['git','-C',str(t/'repo'),'commit','-qm','same identity review'],check=True); rows=json.loads(subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True).stdout)['results']; assert has(rows,'lifecycle','FAIL','independent review')
# A distinct git reviewer with a matching declaration passes process assurance.
subprocess.run(['git','-C',str(t/'repo'),'config','user.email','reviewer@example.com'],check=True); subprocess.run(['git','-C',str(t/'repo'),'config','user.name','Reviewer'],check=True); rev=subprocess.run(['git','-C',str(t/'repo'),'rev-parse','HEAD:specs/a.artifact.json'],capture_output=True,text=True).stdout.strip(); review_path=review_dir/f'{rev}-reviewer@example.com.json'; review_path.write_text(json.dumps({'artifact':'FX-one-001','rev':rev,'reviewer':{'kind':'human','id':'reviewer@example.com'},'verdict':'approve','findings':[],'date':'2026-10-30T00:00:00Z'})); subprocess.run(['git','-C',str(t/'repo'),'add','reviews'],check=True); subprocess.run(['git','-C',str(t/'repo'),'commit','-qm','independent review'],check=True); rows=json.loads(subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True).stdout)['results']; assert has(rows,'lifecycle','PASS') and has(rows,'review-assurance','PASS')
# A declared reviewer mismatch is an explicit failure even when the commit author is trusted by process identity.
wrong_path=review_dir/f'{rev}-fake@example.com.json'; wrong_path.write_text(json.dumps({'artifact':'FX-one-001','rev':rev,'reviewer':{'kind':'human','id':'fake@example.com'},'verdict':'approve','findings':[],'date':'2026-10-30T00:00:00Z'})); subprocess.run(['git','-C',str(t/'repo'),'add','reviews'],check=True); subprocess.run(['git','-C',str(t/'repo'),'commit','-qm','mismatched declaration'],check=True); rows=json.loads(subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True).stdout)['results']; assert has(rows,'lifecycle','FAIL','review identity mismatch')

obj['status']='proposed'; obj['acceptance']=[]; p.write_text(json.dumps(obj)); rows=json.loads(subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True).stdout)['results']; assert has(rows,'lifecycle','FAIL','acceptance criteria')
reg=json.loads((t/'reg.json').read_text()); reg['artifact_lifecycles']['spec']['requirements']['proposed'].pop('acceptance'); reg['artifact_lifecycles']['spec']['requirements'].pop('reviewed'); (t/'reg.json').write_text(json.dumps(reg)); obj['status']='reviewed'; p.write_text(json.dumps(obj)); rows=json.loads(subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True).stdout)['results']; assert has(rows,'lifecycle','PASS')
PY
printf '{invalid json' > "$T/repo/specs/bad.artifact.json"
printf '{"id":"FX-missing-kind-002"}' > "$T/repo/specs/missing-kind.artifact.json"
printf '{"kind":"spec"}' > "$T/repo/specs/missing-id.artifact.json"
python3 -B - "$ROOT" "$T" <<'PY'
import json,os,pathlib,shutil,subprocess,sys,tempfile
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); p=subprocess.run([sys.executable,str(root/'scripts/checks/artifact-quality.py'),str(t/'repo'),'--registry',str(t/'reg.json'),'--json'],capture_output=True,text=True)
data=json.loads(p.stdout); broken=[x for x in data['results'] if x['check']=='parse']; assert p.returncode==1 and len(broken)==3 and any('bad.artifact.json' in x['artifact'] and x['reasons'][0] for x in broken) and any('missing kind' in x['reasons'][0] for x in broken) and any('missing id' in x['reasons'][0] for x in broken)
for script,args in [('artifact-lint.py',[]),('artifact-trace.py',['--registry',str(t/'reg.json')])]:
 result=subprocess.run([sys.executable,str(root/'scripts/checks'/script),str(t/'repo'),*args],capture_output=True,text=True)
 assert result.returncode==1 and 'bad.artifact.json' in result.stdout and 'missing kind' in result.stdout and 'missing id' in result.stdout,(script,result.stdout,result.stderr)
print('PASS malformed artifacts fail closed with path and parse reason')
PY
python3 -B - "$ROOT" "$T" <<'PY'
import importlib.util,json,os,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); sys.path.insert(0,str(root/'scripts/checks')); exe=t/'fake-tool.py'; exe.write_text('print("fake 1.0")\n'); os.environ['RPG_FACTORY_TOOL_NODE']=str(exe)
s=importlib.util.spec_from_file_location('tools',root/'scripts/lib/tools.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); found=m.find_tool('node'); assert found and found['path']==str(exe.resolve()) and 'fake' in found['version']
print('PASS tool override discovery')
clean_settings=t/'clean-settings.json'; clean_settings.write_text('{}')
for env_name in ('RPG_FACTORY_CLAUDE_SETTINGS','RPG_FACTORY_PROJECT_SETTINGS','RPG_FACTORY_PROJECT_SETTINGS_LOCAL','RPG_FACTORY_USER_MCP_FILE','RPG_FACTORY_MCP_FILE','RPG_FACTORY_INSTALLED_PLUGINS'):
    os.environ[env_name]=str(clean_settings)
for name in ('game-art-mcp','ai-pixel-art-image-generation','figma'):
    os.environ.pop('RPG_FACTORY_TOOL_'+name.upper().replace('-','_'),None)
    assert m.find_tool(name) is None, name
print('PASS optional MCP providers are absent by default')
PY
python3 -B - "$ROOT" "$T" <<'PY'
import importlib.util,json,os,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); marker=t/'unity-invoked.log'; fake=t/'unity.py'; fake.write_text(f"import pathlib; pathlib.Path({str(marker)!r}).write_text('invoked')\n")
os.environ['RPG_FACTORY_TOOL_UNITY']=str(fake); spec=importlib.util.spec_from_file_location('tools_safe',root/'scripts/lib/tools.py'); tools=importlib.util.module_from_spec(spec); spec.loader.exec_module(tools); found=tools.find_tool('unity'); direct_invoked=marker.exists(); marker.unlink(missing_ok=True)
repo=t/'vfx-tool-fixture'; (repo/'specs').mkdir(parents=True); (repo/'specs/asset.artifact.json').write_text(json.dumps({'schema_version':1,'id':'VFX-tool-001','kind':'vfx-asset','domain':'vfx','status':'draft','title':'Tool probe','upstream':[],'acceptance':[],'trace':[],'spec':{'summary':'No launch'}}))
registry={'repos':{},'domains':{'vfx':{'artifact_kinds':['vfx-asset'],'quality_plugin':'scripts/checks/domains/vfx.py'}},'artifact_lifecycles':{}}
reg=t/'vfx-tool-registry.json'; reg.write_text(json.dumps(registry)); result=subprocess.run([sys.executable,'-B',str(root/'scripts/checks/artifact-quality.py'),str(repo),'--registry',str(reg),'--domain','vfx','--json'],capture_output=True,text=True,env=os.environ.copy()); data=json.loads(result.stdout); quality_invoked=marker.exists(); assert any(x['check']=='unity-editor-availability' and x['state']=='WARN' for x in data['results']),data; assert not direct_invoked and not quality_invoked,{'direct_invoked':direct_invoked,'quality_invoked':quality_invoked}
print('PASS Unity tool detection is path-only in direct and artifact-quality calls')
PY
python3 -B - "$ROOT" "$T" <<'PY'
import importlib.util,json,os,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); sys.path.insert(0,str(root/'scripts/checks')); spec=importlib.util.spec_from_file_location('tools_provider',root/'scripts/lib/tools.py'); tools=importlib.util.module_from_spec(spec); spec.loader.exec_module(tools)
provider='game-art-mcp'; secret='fixture-never-print-this-secret'; clean=t/'clean-settings.json'; clean.write_text('{}')
for env_name in ('RPG_FACTORY_CLAUDE_SETTINGS','RPG_FACTORY_PROJECT_SETTINGS','RPG_FACTORY_PROJECT_SETTINGS_LOCAL','RPG_FACTORY_USER_MCP_FILE','RPG_FACTORY_MCP_FILE','RPG_FACTORY_INSTALLED_PLUGINS'): os.environ[env_name]=str(clean)
settings=t/'mcp-fixture.json'; settings.write_text(json.dumps({'mcpServers':{provider:{'command':'hidden-command','env':{'TOKEN':secret}}}})); os.environ['RPG_FACTORY_MCP_FILE']=str(settings); assert tools.find_tool(provider)=={'name':provider,'source':'mcp'}
os.environ['RPG_FACTORY_TOOL_'+provider.upper().replace('-','_')]='configured-value'; assert tools.find_tool(provider)=={'name':provider,'source':'environment override'}
result=subprocess.run([sys.executable,str(root/'scripts/lib/tools.py'),provider],capture_output=True,text=True,env=os.environ.copy()); assert result.returncode==0 and secret not in result.stdout+result.stderr and 'configured-value' not in result.stdout+result.stderr
os.environ['RPG_FACTORY_MCP_FILE']=str(clean); os.environ['RPG_FACTORY_PROJECT_SETTINGS']=str(clean); os.environ['RPG_FACTORY_INSTALLED_PLUGINS']=str(clean); from domains._api import Context; from domains import ui as ui_plugin
screen={'id':'UI-provider-001','kind':'screen-spec','spec':{'states':{},'elements':[],'components':[],'tokens':[],'platforms':['desktop']}}; ctx=Context(str(t),{},'',{},tools.find_tool,{})
missing=next(x for x in ui_plugin.check(screen,ctx) if x.check=='ui-figma-adapter'); assert missing.state=='NOT_AVAILABLE' and 'not available' in ' '.join(missing.reasons).lower(),missing
plugins=t/'plugin-settings.json'; plugins.write_text(json.dumps({'enabledPlugins':{'figma@fixture-market':True,'other@fixture-market':True},'apiKey':secret})); os.environ['RPG_FACTORY_PROJECT_SETTINGS']=str(plugins); os.environ.pop('RPG_FACTORY_TOOL_FIGMA',None); assert tools.find_tool('figma')=={'name':'figma','source':'plugin'}
installed=t/'installed-plugins.json'; installed.write_text(json.dumps({'plugins':{'ai-pixel-art-image-generation@custom-market':{'installPath':secret}}})); os.environ['RPG_FACTORY_INSTALLED_PLUGINS']=str(installed); assert tools.find_tool('ai-pixel-art-image-generation')=={'name':'ai-pixel-art-image-generation','source':'plugin'}
print('PASS optional provider absence, MCP/plugin/override detection and name-only reporting')
PY
python3 -B - "$ROOT" "$T" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1]); temp=pathlib.Path(sys.argv[2]); sys.path.insert(0,str(root/'scripts/checks'))
from domains._api import Context
repo=temp/'contained'; outside=temp/'outside'; repo.mkdir(); outside.mkdir(); (repo/'ok.png').write_bytes(b'x'); (outside/'escape.png').write_bytes(b'x')
ctx=Context(str(repo),{'repos':{'client':{}}},'',{},lambda _:None,{'client':repo})
assert ctx.resolve_repo_path('client','ok.png')==(repo/'ok.png').resolve()
assert ctx.resolve_repo_path('client','../outside/escape.png') is None
assert ctx.resolve_repo_path('client',str(outside/'escape.png')) is None
try:
    (repo/'link.png').symlink_to(outside/'escape.png')
except (OSError,NotImplementedError):
    pass
else:
    assert ctx.resolve_repo_path('client','link.png') is None
print('PASS registered repo paths reject absolute, traversal and symlink escapes')
PY
echo "artifact-quality: expanded review identity assertions passed, 0 failed"
python3 -B - "$ROOT" "$T" <<'PY'
import json,pathlib,shutil,subprocess,sys,tempfile
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); repo=t/'signed-review'; (repo/'specs').mkdir(parents=True)
subprocess.run(['git','init','-q','-b','main',str(repo)],check=True)
def git(*args,check=True): return subprocess.run(['git','-C',str(repo),*args],check=check,capture_output=True,text=True)
git('config','user.name','Artifact Author'); git('config','user.email','author@example.com')
artifact=repo/'specs/a.artifact.json'; artifact.write_text(json.dumps({'schema_version':1,'id':'FX-signed-001','kind':'spec','domain':'fixture','status':'draft','title':'Signed','upstream':[],'acceptance':[{'id':'A1','text':'Works','verify':'test'}],'trace':[],'authors':[]}))
git('add','.'); git('commit','-qm','author artifact')
obj=json.loads(artifact.read_text()); obj['status']='proposed'; artifact.write_text(json.dumps(obj)); git('add','.'); git('commit','-qm','propose artifact')
obj['status']='reviewed'; artifact.write_text(json.dumps(obj)); git('add','.'); git('commit','-qm','reviewed artifact')
rev=git('rev-parse','HEAD:specs/a.artifact.json').stdout.strip(); rd=repo/'reviews/FX-signed-001'; rd.mkdir(parents=True)
review=rd/f'{rev}-reviewer@example.com.json'; review.write_text(json.dumps({'artifact':'FX-signed-001','rev':rev,'reviewer':{'kind':'human','id':'reviewer@example.com'},'verdict':'approve','findings':[],'date':'2026-10-30T00:00:00Z'}))
keydir=pathlib.Path(tempfile.mkdtemp(prefix='artifact-review-key-',dir='/tmp' if sys.platform.startswith('linux') else None)); key=keydir/'throwaway-review-key'; subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True)
public_key=(pathlib.Path(str(key)+'.pub').read_text().strip().split(' ',2)[:2]); principal='reviewer@example.com'
git('config','user.name','Artifact Reviewer'); git('config','user.email',principal); git('config','gpg.format','ssh'); git('config','user.signingkey',str(key)); git('config','commit.gpgsign','true')
git('add','reviews'); signed_commit=git('commit','-S','-m','signed independent review').stdout
reg=json.loads((t/'reg.json').read_text()); reg['domains']['fixture']['reviewers']=[{'principal':principal,'ssh_public_key':' '.join(public_key)}]; reg['artifact_lifecycles']['spec']['requirements'].setdefault('reviewed',{'independent_review':True})['review_assurance']='signed'; reg_path=t/'signed-reg.json'; reg_path.write_text(json.dumps(reg))
checker=[sys.executable,'-B',str(root/'scripts/checks/artifact-quality.py'),str(repo),'--registry',str(reg_path),'--json']
def results(): return json.loads(subprocess.run(checker,capture_output=True,text=True).stdout)['results']
rows=results(); assert any(x['check']=='review-assurance' and x['state']=='PASS' and x['reasons']==['signed'] for x in rows),rows
reg['domains']['fixture']['reviewers']=[{'principal':principal,'ssh_public_key':'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeFakeFakeFakeFakeFakeFakeFakeFakeFakeFake'}]; reg_path.write_text(json.dumps(reg)); rows=results(); assert any(x['check']=='lifecycle' and x['state']=='HUMAN_REQUIRED' and 'signature untrusted or invalid' in ' '.join(x['reasons']) for x in rows),rows
reg['domains']['fixture']['reviewers']=[]; reg_path.write_text(json.dumps(reg)); rows=results(); assert any(x['check']=='lifecycle' and x['state']=='HUMAN_REQUIRED' and 'no trusted reviewer keys' in ' '.join(x['reasons']) for x in rows),rows
print('PASS signed review trusted key, untrusted key, and empty key registry')

# Any modification or rename after the immutable review addition invalidates it.
reg['domains']['fixture']['reviewers']=[{'principal':principal,'ssh_public_key':' '.join(public_key)}]; reg_path.write_text(json.dumps(reg))
review.write_text(review.read_text()+' '); git('add','reviews'); git('commit','-qm','edit review'); rows=results(); assert any(x['check']=='lifecycle' and x['state']=='FAIL' and 'independent review record required' in ' '.join(x['reasons']) for x in rows),rows
git('mv',str(review.relative_to(repo)),str((rd/'renamed.json').relative_to(repo))); git('commit','-qm','rename review'); rows=results(); assert any(x['check']=='lifecycle' and x['state']=='FAIL' and 'independent review record required' in ' '.join(x['reasons']) for x in rows),rows
shutil.rmtree(keydir)
print('PASS edited and renamed review files fail immutability validation')
PY
python3 -B - "$ROOT" "$T" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); temp=pathlib.Path(sys.argv[2]); repo=temp/'approval-context'; (repo/'specs').mkdir(parents=True)
key=temp/'approval-key'; subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True); public=' '.join(pathlib.Path(str(key)+'.pub').read_text().strip().split()[:2]); principal='context-approver@example.com'
def git(*args): return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,text=True)
git('init','-q','-b','main'); git('config','user.email','author@example.com'); git('config','user.name','Author')
ids=('missing','invalid','untrusted','verified')
for aid in ids: (repo/'specs'/f'{aid}.artifact.json').write_text(json.dumps({'schema_version':1,'id':aid,'kind':'approval-case','domain':'fixture','status':'approved','title':aid,'upstream':[],'acceptance':[],'trace':[],'spec':{'summary':'Approval context fixture'}}))
git('add','.'); git('commit','-qm','artifacts'); gate='fixture-approval'
for aid in ('invalid','untrusted','verified'):
    rel=f'specs/{aid}.artifact.json'; rev=git('rev-parse',f'HEAD:{rel}').stdout.strip(); folder=repo/'approvals'/aid; folder.mkdir(parents=True)
    record={'artifact':aid,'gate':gate,'scope':'fixture','rev':rev,'date':'2026-10-31T00:00:00Z','by':principal}
    if aid=='invalid': record['rev']='0'*40
    (folder/f'{gate}-{rev}.json').write_text(json.dumps(record)); git('add',f'approvals/{aid}')
    git('config','commit.gpgsign','true' if aid=='verified' else 'false')
    if aid=='verified': git('config','gpg.format','ssh'); git('config','user.signingkey',str(key))
    git('commit','-qm',f'{aid} approval')
reg={'repos':{},'domains':{'fixture':{'artifact_kinds':['approval-case'],'quality_plugin':'tests/fixtures/approval-context-plugin.py','human_gates':[gate],'approvers':[{'principal':principal,'ssh_public_key':public}]}},'artifact_lifecycles':{'approval-case':{'states':['approved'],'requirements':{'approved':{'needs_approval':[gate]}}}}}
reg_path=temp/'approval-context-registry.json'; reg_path.write_text(json.dumps(reg)); command=[sys.executable,'-B',str(root/'scripts/checks/artifact-quality.py'),str(repo),'--registry',str(reg_path),'--domain','fixture','--json']
result=subprocess.run(command,capture_output=True,text=True); assert result.returncode==1,result.stderr; rows=[x for x in json.loads(result.stdout)['results'] if x['check']=='approval-context']; states={x['artifact']:x['reasons'][0] for x in rows}; assert states=={'missing':'missing','invalid':'invalid','untrusted':'untrusted','verified':'verified'},(states,rows)
print('PASS stub plugin reads Context approval states: missing, invalid, untrusted, verified')
PY
# --domain / --kind select what is reported, never what resolves: a UI artifact citing a design artifact stays valid
mkdir -p "$T/xd/design" "$T/xd/ui"; git -C "$T/xd" init -q -b main
cat > "$T/reg-xd.json" <<'JSON'
{"domains":{"design":{"artifact_kinds":["spec"]},"ui":{"artifact_kinds":["spec"]}},"artifact_lifecycles":{"spec":{"states":["draft"],"transitions":{},"requirements":{}}},"kind_schemas":{"spec":"docs/schemas/kinds/feature-spec.schema.json"}}
JSON
for x in design:DS-up-001: ui:UI-down-001:DS-up-001; do
  IFS=: read -r d id src <<<"$x"
  printf '{"schema_version":1,"id":"%s","kind":"spec","domain":"%s","status":"draft","title":"t","sources":[%s],"upstream":[],"acceptance":[{"id":"A1","text":"Works","verify":"test"}],"trace":[],"authors":[{"kind":"human","id":"author"}],"spec":{"summary":"s","goals":["g"],"requirements":[{"id":"A1","description":"d"}]}}\n' \
    "$id" "$d" "${src:+\"$src\"}" > "$T/xd/$d/$id.artifact.json"
done
for sel in "--domain ui" "--kind spec"; do
  out=$(python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/xd" --registry "$T/reg-xd.json" $sel --json || true)
  jq -e '[.results[] | select(.check=="dependencies")] as $d | ($d | length) > 0 and all($d[]; .state=="PASS")' <<<"$out" >/dev/null \
    || { echo "FAIL $sel lost the cross-domain source: $(jq -c '[.results[]|select(.check=="dependencies")]' <<<"$out")"; exit 1; }
done
jq -e '[.results[].artifact] | unique == ["UI-down-001"]' <<<"$(python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/xd" --registry "$T/reg-xd.json" --domain ui --json || true)" >/dev/null \
  || { echo "FAIL --domain ui reported artifacts of another domain"; exit 1; }
echo "PASS --domain/--kind report only the selection and still resolve cross-domain sources"
# trace rows are attributed to their subject: a stale downstream fails, its upstream (named in the row) does not
python3 -B - "$T/xd/ui/UI-down-001.artifact.json" <<'PY'
import json, sys
p = sys.argv[1]; o = json.load(open(p, encoding="utf-8")); o["upstream"] = [{"id": "DS-up-001", "rev": "0" * 40}]
open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(o))
PY
git -C "$T/xd" add -A; git -C "$T/xd" -c user.email=t@example.com -c user.name=t commit -qm xd
out=$(python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/xd" --registry "$T/reg-xd.json" --json || true)
jq -e '[.results[] | select(.check=="trace-approval") | {(.artifact): .state}] | add == {"DS-up-001": "PASS", "UI-down-001": "FAIL"}' <<<"$out" >/dev/null \
  || { echo "FAIL trace rows misattributed: $(jq -c '[.results[]|select(.check=="trace-approval")|[.artifact,.state]]' <<<"$out")"; exit 1; }
echo "PASS trace-approval fails only the stale downstream, not the upstream it names"
# a draft committed twice (edited, status unchanged) is not a draft -> draft transition
python3 -B - "$T/xd/design/DS-up-001.artifact.json" <<'PY'
import json, sys
p = sys.argv[1]; o = json.load(open(p, encoding="utf-8")); o["title"] = "t revised"
open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(o))
PY
git -C "$T/xd" add -A; git -C "$T/xd" -c user.email=t@example.com -c user.name=t commit -qm edit
out=$(python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/xd" --registry "$T/reg-xd.json" --json || true)
jq -e '[.results[] | select(.artifact=="DS-up-001" and .check=="lifecycle")][0].state == "PASS"' <<<"$out" >/dev/null \
  || { echo "FAIL edited draft graded as a transition: $(jq -c '[.results[]|select(.artifact=="DS-up-001" and .check=="lifecycle")]' <<<"$out")"; exit 1; }
echo "PASS an artifact edited without a status change has no lifecycle transition"
# upstream revisions are the blob a downstream author reads (git hash-object), committed or not
python3 -B - "$T/xd/design/DS-up-001.artifact.json" <<'PY'
import json, sys
p = sys.argv[1]; o = json.load(open(p, encoding="utf-8")); o["title"] = "t uncommitted edit"
open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(o))
PY
rev=$(git -C "$T/xd" hash-object design/DS-up-001.artifact.json)
python3 -B - "$T/xd/ui/UI-down-001.artifact.json" "$rev" <<'PY'
import json, sys
p = sys.argv[1]; o = json.load(open(p, encoding="utf-8")); o["upstream"] = [{"id": "DS-up-001", "rev": sys.argv[2]}]
open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(o))
PY
out=$(python3 -B "$ROOT/scripts/checks/artifact-quality.py" "$T/xd" --registry "$T/reg-xd.json" --json || true)
jq -e '[.results[] | select(.artifact=="UI-down-001" and .check=="trace-approval")][0].state == "PASS"' <<<"$out" >/dev/null \
  || { echo "FAIL uncommitted upstream graded stale: $(jq -c '[.results[]|select(.artifact=="UI-down-001" and .check=="trace-approval")]' <<<"$out")"; exit 1; }
echo "PASS a downstream citing the working-tree blob of an uncommitted upstream is current"
