#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1
trap 'rm -rf "$TMP"' EXIT
export RPG_FACTORY_STATE_DIR="$TMP/state" TMPDIR="$TMP" RPG_FACTORY_AGENTS=claude,codex
unset RPG_FACTORY_WORKSPACE RPG_FACTORY_REGISTRY
for v in $(compgen -e | grep '^ORCA_'); do unset "$v"; done
python3 -B - "$ROOT" "$TMP" <<'PY'
import json, os, pathlib, subprocess, sys
root, tmp = map(pathlib.Path, sys.argv[1:])
pipeline = root / 'scripts/factory-pipeline.py'
repo = tmp / 'plain'; repo.mkdir(); (repo / 'src').mkdir(); (repo / 'src/file.txt').write_text('base\n')
def git(*args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()
git('init', '-q', '-b', 'main'); git('add', '.'); git('-c', 'user.name=Test', '-c', 'user.email=t@t', 'commit', '-qm', 'base'); git('branch', 'feat/core/generic'); git('branch', 'feat/core/generic-one')
sha = git('rev-parse', 'HEAD')
plan = {'schema':'rpg-factory.pipeline-plan/1', 'id':'generic', 'title':'Generic', 'topic':'feat/core/generic', 'tier':'S', 'repos':{'plain':{'path':'plain','base':'main'}}, 'tasks':[{'id':'one','repo':'plain','objective':'Change file','paths':['src/file.txt'],'acceptance':['Works'], 'kind':'code'}]}
pf = tmp / 'plan.json'
def write(): pf.write_text(json.dumps(plan), encoding='utf-8')
write()
passed = failed = 0
def run(args, registry='none', env=None):
    return subprocess.run([sys.executable, '-B', str(pipeline), '--registry', str(registry), *map(str,args)], capture_output=True, text=True, env=env)
def check(name, ok, detail=''):
    global passed, failed
    if ok: passed += 1; print('PASS ', name)
    else: failed += 1; print('FAIL ', name, detail[:1200])
def expect(name, args, pattern='', registry='none', rc=0):
    p=run(args,registry); check(name, p.returncode == rc and pattern in p.stdout+p.stderr, p.stdout+p.stderr); return p
reg=json.loads((root/'registry.json').read_text(encoding='utf-8'))['pipeline']
defaults=json.loads((root/'skills/delivery/pipeline-defaults.json').read_text(encoding='utf-8'))
check('defaults drift', all(reg.get(k)==v for k,v in defaults['pipeline'].items()) and 'exclusive_resources' not in defaults['pipeline'])
for registry in ('none', tmp/'missing.json'):
    plan['id']='generic'+('missing' if registry != 'none' else 'none'); write()
    expect('tier '+str(registry), ['tier','--json','--plan',pf,'--repo','plain','--paths','src/file.txt'], '"tier": "S"', registry)
    expect('validate '+str(registry), ['validate',pf], 'OK', registry)
    git('switch', '-q', 'feat/core/generic-one')
    for phase in ('lead','implement','review','qa'):
        args=['dispatch',pf,'--task','one','--phase',phase,'--runner','agent','--orca-unavailable','test']
        if phase in ('review','qa'): args += ['--sha',sha]
        expect('dispatch '+phase+' '+str(registry), args, '', registry)
    expect('dispatch orca lead '+str(registry), ['dispatch',pf,'--task','one','--phase','lead','--runner','orca'], 'orca', registry)
    expect('review verdict '+str(registry), ['verdict',pf,'--task','one','--phase','review','--sha',sha,'--by','codex','--state','PASS'], 'PASS', registry)
    expect('qa verdict '+str(registry), ['verdict',pf,'--task','integration:plain','--phase','qa','--sha',sha,'--by','claude','--state','PASS'], 'PASS', registry)
    git('switch', '-q', 'feat/core/generic')
    expect('gate '+str(registry), ['gate',pf,'--no-run-checks'], 'READY_FOR_PR', registry)
(repo/'marker').write_text('marker')
plan['no_worktree_markers']=['marker']; write()
expect('marker disables worktrees', ['validate',pf,'--json'], '"plain"')
p=run(['dispatch',pf,'--task','one','--phase','lead','--runner','orca']); check('marker placement', p.returncode==0 and 'worktree add' not in p.stdout, p.stdout+p.stderr)
plan['no_worktree_markers']=[]; write()
p=run(['dispatch',pf,'--task','one','--phase','lead','--runner','orca']); check('empty marker override', p.returncode==0 and 'worktree add' in p.stdout, p.stdout+p.stderr)
plan['no_worktree_markers']='marker'; write()
expect('invalid marker type', ['validate',pf], 'no_worktree_markers must be an array of strings', rc=1)
for arg in ('-h','--help'):
    p=subprocess.run([sys.executable,'-B',str(pipeline),arg], capture_output=True,text=True); check(arg, p.returncode==0 and 'usage:' in p.stdout)
p=subprocess.run([sys.executable,'-B',str(pipeline),'--unknown'], capture_output=True,text=True); check('unknown argument',p.returncode==2 and 'usage:' in p.stderr)
env=os.environ.copy(); env['RPG_FACTORY_REGISTRY']='none'
p=subprocess.run([sys.executable,'-B',str(pipeline),'tier','--json','--plan',str(pf),'--repo','plain','--paths','src/file.txt'],capture_output=True,text=True,env=env); check('environment fallback',p.returncode==0,p.stderr)
print(f'delivery-generic: {passed+failed} checks, {passed} passed, {failed} failed')
sys.exit(bool(failed))
PY
