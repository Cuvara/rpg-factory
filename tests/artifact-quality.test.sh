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
import importlib.util,os,pathlib,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); exe=t/'fake-tool.py'; exe.write_text('print("fake 1.0")\n'); os.environ['RPG_FACTORY_TOOL_NODE']=str(exe)
s=importlib.util.spec_from_file_location('tools',root/'scripts/lib/tools.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); found=m.find_tool('node'); assert found and found['path']==str(exe.resolve()) and 'fake' in found['version']
print('PASS tool override discovery')
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
