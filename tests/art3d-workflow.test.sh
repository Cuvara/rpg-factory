#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
export TMPDIR="$TASK_TMP/tmp"
export RPG_FACTORY_STATE_DIR="$TASK_TMP/state"
mkdir -p "$TMPDIR" "$RPG_FACTORY_STATE_DIR"
python3 -B - "$ROOT" "$TASK_TMP" <<'PY'
import hashlib, importlib.util, json, os, pathlib, struct, subprocess, sys
root=pathlib.Path(sys.argv[1]); temp=pathlib.Path(sys.argv[2])
sys.path.insert(0,str(root/'scripts'))
lint_spec=importlib.util.spec_from_file_location('artifact_lint',root/'scripts/checks/artifact-lint.py'); artifact_lint=importlib.util.module_from_spec(lint_spec); lint_spec.loader.exec_module(artifact_lint)
reg=json.loads((root/'registry.json').read_text(encoding='utf-8'))
common=json.loads((root/'docs/artifact.schema.json').read_text(encoding='utf-8'))
templates=sorted((root/'templates/art3d').glob('*.md'))
assert len(templates)==8, f'expected 8 templates, got {len(templates)}'
for path in templates:
    obj=artifact_lint.load_file(str(path))
    errors=artifact_lint.validate(obj,reg,common)
    assert not errors, f'{path.name}: {errors}'
print(f'PASS templates schema-valid drafts ({len(templates)})')
schema_ids=[]
for kind in reg['domains']['art3d']['artifact_kinds']:
    schema_path=root/reg['kind_schemas'][kind]
    schema_ids.append(json.loads(schema_path.read_text(encoding='utf-8'))['$id'])
assert len(schema_ids)==len(set(schema_ids)), 'art3d artifact schema $id values must be unique, including aliases'
print(f'PASS artifact schema ids unique ({len(schema_ids)} kinds)')

spec_file=root/'scripts/checks/domains/art3d.py'
spec=importlib.util.spec_from_file_location('art3d_plugin',spec_file); plugin=importlib.util.module_from_spec(spec); spec.loader.exec_module(plugin)
repo=temp/'authoring'; repo.mkdir()
model={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':'LOD0_root','mesh':0}], 'meshes':[{'name':'LOD0_mesh','primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'material':0}]}], 'accessors':[{'count':3},{'count':3}], 'materials':[{'name':'mat'}], 'images':[],'skins':[],'animations':[],'extras':{'scale':1,'units':'meters','up_axis':'Y'}}
raw=json.dumps(model,separators=(',',':')).encode(); raw+=b' '*((-len(raw))%4); glb=struct.pack('<4sII',b'glTF',2,12+8+len(raw))+struct.pack('<I4s',len(raw),b'JSON')+raw
(repo/'asset.glb').write_bytes(glb)
asset={'id':'ARTD-asset-001','kind':'asset-3d','domain':'art3d','schema_version':2,'status':'draft','title':'Fixture asset','authors':[],'sources':[],'upstream':[],'acceptance':[],'trace':[],'spec':{'file':'asset.glb','hash':hashlib.sha256(glb).hexdigest(),'format':'glb','lods':['LOD0'],'collision':[],'physics':{},'textures':[],'export_settings':{'scale':1,'units':'meters','up_axis':'Y'},'engine_constraints':[],'required_deliverables':[],'polygon_budget_by_lod':{'default':1},'uv_required':True,'naming_pattern':'^LOD[0-9]+_mesh$','node_naming_pattern':'^LOD[0-9]+_root$','materials_required':True,'root_required':True,'rig_required':False,'animation_required':False}}
(repo/'asset.artifact.json').write_text(json.dumps(asset),encoding='utf-8')
subprocess.run(['git','-C',str(repo),'init','-q'],check=True); subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','add','.'],check=True); subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)
class Context: pass
from lib import tools as tool_detector
ctx=Context(); ctx.repo=str(repo); ctx.tools=tool_detector.find_tool
result=plugin.check(asset,ctx); assert result[0]['state']=='PASS', result
print('PASS generated minimal GLB production validation')

def errors_for(changes):
    changed=dict(asset); changed['spec']=dict(asset['spec']); changed['spec'].update(changes)
    return plugin.check(changed,ctx)[0]
for change,needle in [({'polygon_budget_by_lod':{'default':0}},'exceeds budget'),({'uv_required':False,'node_naming_pattern':'^NoMatch$'},'node naming'),({'format':'gltf'},'format'),({'required_deliverables':['absent.bin']},'deliverable')]:
    out=errors_for(change); assert out['state']=='FAIL' and any(needle in x for x in out['reasons']), (change,out)
print('PASS production rule failures (4 cases)')
import copy
base_spec=asset['spec']
domain_cases=[]
for changed_model,changed_spec,needle in [
    (lambda x:x,dict(base_spec,polygon_budget_by_lod={'default':0}),'exceeds budget'),
    (lambda x:x['meshes'][0]['primitives'][0]['attributes'].pop('TEXCOORD_0'),base_spec,'UV set'),
    (lambda x:x,dict(base_spec,naming_pattern='^never$'),'naming convention'),
    (lambda x:x['materials'].clear(),dict(base_spec,materials_required=True),'materials required'),
    (lambda x:x['images'].append({'uri':'missing.png'}),base_spec,'texture image missing'),
    (lambda x:x['scenes'].clear(),dict(base_spec,root_required=True),'scene/root'),
    (lambda x:x,dict(base_spec,rig_required=True),'skin/rig missing'),
    (lambda x:x,dict(base_spec,animation_required=True),'animations missing'),
    (lambda x:x,dict(base_spec,export_settings={'scale':2,'units':'meters','up_axis':'Y'}),'scale mismatch'),
    (lambda x:x,dict(base_spec,lods=['LOD1']),'required LOD missing'),
    (lambda x:x['meshes'].clear(),base_spec,'asset contains no meshes'),
    (lambda x:x['scenes'][0].update(nodes=[99]),dict(base_spec,root_required=True),'scene/root structure missing or invalid')]:
    data=copy.deepcopy(model); changed_model(data)
    errs=plugin.gltf_errors(data,repo,changed_spec)
    assert any(needle in e for e in errs),(needle,errs)
    domain_cases.append(needle)
print(f'PASS glTF domain rule failures ({len(domain_cases)} cases)')
strip=copy.deepcopy(model); strip['meshes'][0]['primitives'][0]['mode']=5; strip['accessors'][0]['count']=5
fan=copy.deepcopy(model); fan['meshes'][0]['primitives'][0]['mode']=6; fan['accessors'][0]['count']=5
assert plugin.triangles(strip,strip['meshes'][0]['primitives'][0])==3
assert plugin.triangles(fan,fan['meshes'][0]['primitives'][0])==3
print('PASS glTF triangle strip and fan counts')
missing=dict(asset); missing['spec']=dict(asset['spec'],file='missing.glb')
assert plugin.check(missing,ctx)[0]['state']=='FAIL'
fake=dict(asset); fake['spec']=dict(asset['spec'],file='asset.fbx',format='fbx')
(repo/'asset.fbx').write_bytes(b'fixture')
absent=plugin.check(fake,ctx); assert absent[0]['state']!='PASS', absent
if tool_detector.find_tool('blender'):
    blender=tool_detector.find_tool('blender')['path']
    generator=temp/'make_dcc_fixtures.py'
    generator.write_text('''import bpy, json, sys
from pathlib import Path
out=Path(sys.argv[sys.argv.index("--")+1])
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new("mesh"); mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)]); mesh.update()
mesh.uv_layers.new(name="UVMap")
obj=bpy.data.objects.new("LOD0_mesh",mesh); bpy.context.collection.objects.link(obj)
mat=bpy.data.materials.new("FixtureMaterial"); mesh.materials.append(mat)
bpy.context.scene["rpg_factory_export_settings"]={"scale":1,"units":"meters","up_axis":"Z"}
bpy.ops.wm.save_as_mainfile(filepath=str(out/"valid.blend"))
bpy.data.objects["LOD0_mesh"].data.materials.clear(); bpy.ops.wm.save_as_mainfile(filepath=str(out/"nomat.blend"))
bpy.data.objects["LOD0_mesh"].data.materials.append(mat)
bpy.ops.object.select_all(action="SELECT"); bpy.ops.wm.obj_export(filepath=str(out/"valid.obj"),export_selected_objects=True)
bpy.ops.export_scene.fbx(filepath=str(out/"valid.fbx"),use_selection=True)
''',encoding='utf-8')
    generated=subprocess.run([blender,'-b','--python',str(generator),'--',str(temp)],capture_output=True,text=True,encoding='utf-8',timeout=90)
    assert generated.returncode==0,generated.stderr
    dcc_spec=dict(asset['spec'],naming_pattern='.*',node_naming_pattern='.*',export_settings={'scale':1,'units':'meters','up_axis':'Z'})
    for ext in ('blend','obj','fbx'):
        path=temp/f'valid.{ext}'; target=repo/path.name; target.write_bytes(path.read_bytes())
        if ext!='blend': target.with_suffix(target.suffix+'.rpgfactory.json').write_text(json.dumps({'export_settings':dcc_spec['export_settings']}),encoding='utf-8')
        dcc_asset=dict(asset); dcc_asset['spec']=dict(dcc_spec,file=target.name,format=ext,hash=hashlib.sha256(target.read_bytes()).hexdigest(),lods=['LOD0'])
        checked=plugin.check(dcc_asset,ctx)
        assert checked[0]['state']=='PASS' and checked[1]['state']=='PASS', (ext,checked)
        print(f'PASS Blender {ext.upper()} imported/inspected with checked scene statistics')
    bad=dict(asset); bad['spec']=dict(dcc_spec,file='valid.blend',format='blend',lods=['LOD0','LOD1'],naming_pattern='^NO_MATCH$',polygon_budget_by_lod={'default':-1},materials_required=True,export_settings={'scale':5,'units':'feet','up_axis':'Y'})
    failed=plugin.check(bad,ctx)
    assert failed[0]['state']=='FAIL' and failed[1]['state']=='FAIL' and all(any(word in reason for reason in failed[1]['reasons']) for word in ('LOD1','naming','exceeds budget','scale mismatch','units mismatch','up_axis mismatch')),failed
    missing_files=dict(asset); missing_files['spec']=dict(dcc_spec,file='valid.blend',format='blend',required_deliverables=['missing.texture'],textures=['missing.texture'])
    file_failure=plugin.check(missing_files,ctx); assert file_failure[0]['state']=='FAIL' and all(any(needle in reason for reason in file_failure[0]['reasons']) for needle in ('required deliverable missing','required textures deliverable missing')),file_failure
    nomat=repo/'nomat.blend'; nomat.write_bytes((temp/'nomat.blend').read_bytes())
    no_material=dict(asset); no_material['spec']=dict(dcc_spec,file='nomat.blend',format='blend',hash=hashlib.sha256(nomat.read_bytes()).hexdigest(),materials_required=True)
    missing_material=plugin.check(no_material,ctx); assert missing_material[1]['state']=='FAIL' and any('materials required' in x for x in missing_material[1]['reasons']),missing_material
    print('PASS Blender production requirements reject LOD, naming, budget, materials, scale, units, up-axis and deliverable violations')
else:
    assert absent[1]['state']=='NOT_AVAILABLE', absent
    print('SKIP Blender adapter: Blender not available; explicit NOT_AVAILABLE confirmed')

shortcut=dict(asset,status='approved')
(repo/'asset.artifact.json').write_text(json.dumps(shortcut),encoding='utf-8')
subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','add','.'],check=True)
subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','illegal lifecycle shortcut'],check=True)
lint=subprocess.run([sys.executable,'-B',str(root/'scripts/checks/artifact-lint.py'),str(repo),'--registry',str(root/'registry.json')],capture_output=True,text=True,encoding='utf-8')
assert lint.returncode and 'illegal transition' in lint.stdout, lint.stdout+lint.stderr
print('PASS lifecycle shortcut draft -> approved rejected')

workflow={'id':'art3d-fixture','title':'Art3D fixture','goal':'Plan art3d and engineering delivery','targets':[{'id':'direction','kind':'art-direction-3d','sources':[],'acceptance':['Direction reviewed']},{'id':'asset','kind':'asset-3d','sources':['direction'],'acceptance':['Asset validates']},{'id':'implementation','kind':'implementation','repo':'client','paths':['Assets/Art3D/'],'sources':['asset'],'acceptance':['Imported']}],'existing':[]}
wf=temp/'workflow.json'; wf.write_text(json.dumps(workflow),encoding='utf-8')
p=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'plan',str(wf),'--registry',str(root/'registry.json'),'--json'],capture_output=True,text=True,encoding='utf-8',check=True)
plan=json.loads(p.stdout); assert plan['nodes']['direction']['domain']=='art3d' and plan['nodes']['asset']['lead_skill']=='art-3d' and plan['nodes']['asset']['paths'][0].startswith('art3d/deliveries/') and plan['nodes']['implementation']['domain']=='engineering', plan
assert plan['edges'] and plan['waves'][0]==['direction'], plan
print('PASS workflow plan routes art3d and Engineering in dependency waves')

stale_repo=temp/'stale-authoring'; (stale_repo/'art3d/direction').mkdir(parents=True); (stale_repo/'art3d/deliveries').mkdir(parents=True)
direction={'id':'ARTD-direction-001','kind':'art-direction-3d','domain':'art3d','schema_version':2,'status':'draft','title':'Direction','authors':[],'sources':[],'upstream':[],'acceptance':[],'trace':[],'spec':{'style':'TBD','palette':[],'references':[],'constraints':[]}}
delivery={'id':'ARTD-asset-003','kind':'asset-3d','domain':'art3d','schema_version':2,'status':'draft','title':'Delivery','authors':[],'sources':[],'upstream':[{'id':direction['id'],'rev':'0'*40}],'acceptance':[],'trace':[],'spec':asset['spec']}
(stale_repo/'art3d/direction/direction.artifact.json').write_text(json.dumps(direction),encoding='utf-8')
(stale_repo/'art3d/deliveries/asset.artifact.json').write_text(json.dumps(delivery),encoding='utf-8')
subprocess.run(['git','-C',str(stale_repo),'init','-q'],check=True); subprocess.run(['git','-C',str(stale_repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','add','.'],check=True); subprocess.run(['git','-C',str(stale_repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','stale fixture'],check=True)
stale_spec={'id':'stale-fixture','title':'Stale fixture','goal':'Show changed upstream invalidation','targets':[{'id':delivery['id'],'kind':'asset-3d','domain':'art3d','sources':[direction['id']],'acceptance':['Revalidate after upstream changes']}],'existing':[]}
stale_file=temp/'stale-workflow.json'; stale_file.write_text(json.dumps(stale_spec),encoding='utf-8')
status=subprocess.run([sys.executable,'-B',str(root/'scripts/factory-workflow.py'),'status',str(stale_file),'--registry',str(root/'registry.json'),'--authoring',str(stale_repo),'--json'],capture_output=True,text=True,encoding='utf-8',check=True)
out=json.loads(status.stdout); assert out['states'][delivery['id']]=='stale' and out['stale_upstream'],out
print('PASS workflow status marks changed upstream artifact stale')
PY
