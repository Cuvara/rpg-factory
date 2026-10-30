#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp_win)" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/authoring/art2d" "$T/client/Assets/Sprites"
pass=0; fail=0
ok() { pass=$((pass+1)); echo "PASS $1"; }
no() { fail=$((fail+1)); echo "FAIL $1"; }
for file in "$ROOT"/templates/art2d/*.md; do
  data=$(sed -n '/^---json$/,/^---$/p' "$file" | sed '1d;$d')
  kind=$(jq -r .kind <<<"$data")
  printf '%s\n' "$data" > "$T/authoring/art2d/$kind.artifact.json"
  out=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/authoring" --registry "$ROOT/registry.json" 2>&1); rc=$?
  if [ "$rc" -eq 0 ]; then ok "$kind draft template passes artifact schema/lifecycle"; else no "$kind draft template passes artifact schema/lifecycle: $out"; fi
done
python3 -B - "$ROOT" <<'PY'
import hashlib, importlib.util, json, pathlib, struct, sys, tempfile
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'scripts/checks/domains')); spec=importlib.util.spec_from_file_location('art2d',root/'scripts/checks/domains/art2d.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class C: repo='.'; registry={'repos':{}}; artifact_path=''; artifacts={}; repo_roots={}; tools=lambda self,n:None
C.resolve_repo_path=lambda self,r,p: __import__('pathlib').Path(self.repo_roots[r])/p if r in self.repo_roots and p and '..' not in p else None
for kind in ('concept-2d','reference-2d'):
 obj={'kind':kind,'status':'released','spec':{}}
 assert any(x.state=='FAIL' for x in m.check(obj,C()))
print('PASS concepts and references cannot be released')
spec_obj={'kind':'asset-spec-2d','id':'A2D-icon-001','spec':{'art_direction_id':'A2D-style-001'}}
ctx=C(); ctx.artifacts={'A2D-style-001':('style',{'kind':'art-direction-2d','spec':{}})}
assert any(x.check=='art2d-runtime-export' and x.state=='FAIL' for x in m.check(spec_obj,ctx))
print('PASS spec without export fails')
with tempfile.TemporaryDirectory() as td:
 repo=pathlib.Path(td); image=repo/'art2d_prop_icon_idle.png'
 image.write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',8,4)+bytes([8,6,0,0,0]))
 digest=hashlib.sha256(image.read_bytes()).hexdigest()
 guide={'id':'ARTD-style-001','kind':'art-direction-2d','spec':{'naming_pattern':r'^[a-z0-9]+_[a-z0-9]+_[a-z0-9]+_[a-z0-9]+$'}}
 exp={'id':'ARTD-export-001','kind':'runtime-export-2d','spec':{'asset_spec_id':'A2D-icon-001','art_direction_id':'ARTD-style-001','repo':'client','file_path':image.name,'sha256':digest,'dimensions':{'width':8,'height':4},'format':'png','alpha':True}}
 ctx.registry={'repos':{'client':{'path':'client'}}}; ctx.repo_roots={'client':td}; ctx.artifacts={'ARTD-style-001':('style',guide),'ARTD-export-001':('export',exp)}
 result=m.check(exp,ctx)
 assert next(x for x in result if x.check=='art2d-export-integrity').state=='PASS'
 spec_obj['spec']['art_direction_id']='ARTD-style-001'; ctx.artifacts['ARTD-export-001']=('export',exp)
 assert next(x for x in m.check(spec_obj,ctx) if x.check=='art2d-runtime-export').state=='PASS'
 exp['spec']['sha256']='0'*64
 assert next(x for x in m.check(exp,ctx) if x.check=='art2d-export-integrity').state=='FAIL'
 assert next(x for x in m.check(spec_obj,ctx) if x.check=='art2d-runtime-export').state=='FAIL'
 print('PASS PNG header, alpha, naming and SHA-256 integrity')
PY
[ $? -eq 0 ] && ok 'domain lifecycle/export rules' || no 'domain lifecycle/export rules'
python3 -B - "$ROOT" "$T" <<'PY'
import hashlib,json,pathlib,struct,subprocess,sys
root=pathlib.Path(sys.argv[1]); t=pathlib.Path(sys.argv[2]); author=t/'authoring'; client=t/'client'
image=client/'Assets/Sprites/hero_prop_icon_idle.png'; image.write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',8,4)+bytes([8,6,0,0,0]))
direction=json.loads((root/'templates/art2d/art-direction-2d.md').read_text().split('---json\n',1)[1].split('\n---',1)[0]); direction['id']='ARTD-style-002'; direction['spec']['naming_pattern']=r'^[a-z0-9]+_[a-z0-9]+_[a-z0-9]+_[a-z0-9]+$'
export=json.loads((root/'templates/art2d/runtime-export-2d.md').read_text().split('---json\n',1)[1].split('\n---',1)[0]); export['id']='ARTD-export-002'; export['spec'].update(file_path='Assets/Sprites/'+image.name,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),dimensions={'width':8,'height':4},alpha=True)
folder=author/'art2d'; folder.mkdir(parents=True,exist_ok=True); (folder/'direction.artifact.json').write_text(json.dumps(direction)); (folder/'export.artifact.json').write_text(json.dumps(export))
base=[sys.executable,'-B',str(root/'scripts/checks/artifact-quality.py'),str(author),'--registry',str(root/'registry.json'),'--domain','art2d']
ok_run=subprocess.run(base+['--repos','client='+str(client),'--json'],capture_output=True,text=True); data=json.loads(ok_run.stdout); checks=[x for x in data['results'] if x['artifact']==export['id'] and x['check']=='art2d-export-integrity']; assert checks and checks[0]['state']=='PASS',(ok_run.returncode,checks,data)
no_root=subprocess.run(base+['--json'],capture_output=True,text=True); missing=json.loads(no_root.stdout); rows=[x for x in missing['results'] if x['artifact']==export['id'] and x['check']=='art2d-export-file']; assert rows and rows[0]['state']=='FAIL' and 'root is unavailable' in ' '.join(rows[0]['reasons']),rows
print('PASS artifact-quality resolves registered client export root and fails explicitly when missing')
PY
printf 'art2d workflow: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
