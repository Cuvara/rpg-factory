#!/usr/bin/env python3
"""Aggregate artifact schema, lifecycle, trace, review, approval and plugin checks."""
import argparse, datetime, importlib.util, json, os, re, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT/'scripts'))
from lib import tools as tool_detector
import importlib.util as iu
spec=iu.spec_from_file_location('artifact_lint',HERE/'artifact-lint.py'); lint=iu.module_from_spec(spec); spec.loader.exec_module(lint)
VALID={'PASS','FAIL','WARN','HUMAN_REQUIRED','NOT_AVAILABLE','BLOCKED'}

def valid_review(record, artifact, revision, filename):
    reviewer=record.get('reviewer',{})
    try: datetime.datetime.fromisoformat(record.get('date','').replace('Z','+00:00'))
    except (ValueError,AttributeError): return False
    return (record.get('artifact')==artifact and record.get('rev')==revision and
            isinstance(reviewer,dict) and reviewer.get('kind') in ('agent','human') and
            isinstance(reviewer.get('id'),str) and reviewer.get('id') and
            filename==f"{revision}-{reviewer['id']}.json" and
            record.get('verdict') in ('approve','changes-requested','reject') and
            isinstance(record.get('findings'),list))

def read_artifact(path):
    raw=path.read_text(encoding='utf-8')
    if path.suffix=='.json': return json.loads(raw)
    m=re.match(r'\A---json\s*\n(.*?)\n---',raw,re.S)
    return json.loads(m.group(1)) if m else None

def git_statuses(root, rel):
    commits=subprocess.run(['git','-C',str(root),'log','--follow','--format=%H','HEAD','--',rel],capture_output=True,text=True,encoding='utf-8').stdout.splitlines()
    statuses=[]
    for commit in commits:
        raw=subprocess.run(['git','-C',str(root),'show',f'{commit}:{rel}'],capture_output=True,text=True,encoding='utf-8')
        if raw.returncode==0:
            try:
                data=json.loads(raw.stdout) if rel.endswith('.json') else read_artifact_text(raw.stdout)
                if isinstance(data,dict): statuses.append(data.get('status'))
            except Exception: pass
    return list(reversed(statuses))

def read_artifact_text(raw):
    m=re.match(r'\A---json\s*\n(.*?)\n---',raw,re.S)
    return json.loads(m.group(1)) if m else None

def main():
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    ap=argparse.ArgumentParser(); ap.add_argument('repo_dir'); ap.add_argument('--registry',required=True); ap.add_argument('--repos',nargs='*',default=[]); ap.add_argument('--json',action='store_true'); ap.add_argument('--kind'); ap.add_argument('--domain'); a=ap.parse_args()
    root=Path(a.repo_dir).resolve(); reg=json.loads(Path(a.registry).read_text(encoding='utf-8')); schema=json.loads((ROOT/'docs/artifact.schema.json').read_text(encoding='utf-8'))
    paths=[]
    for p in root.rglob('*'):
        if p.is_file() and (p.name.endswith(('.artifact.json','.asset.json')) or p.suffix=='.md' and p.read_text(encoding='utf-8',errors='replace').startswith('---json')) and '.git' not in p.parts and 'approvals' not in p.parts: paths.append(p)
    artifacts={}; entries=[]
    for p in sorted(paths):
        try: obj=read_artifact(p)
        except Exception: continue
        if not isinstance(obj,dict) or not obj.get('id'): continue
        if a.kind and obj.get('kind')!=a.kind or a.domain and obj.get('domain')!=a.domain: continue
        rel=p.relative_to(root).as_posix(); artifacts[obj['id']]=(rel,obj)
    results=[]
    def add(aid,obj,rel,check,state,reasons=()): results.append({'artifact':aid,'kind':obj.get('kind',''),'domain':obj.get('domain',''),'status':obj.get('status',''),'check':check,'state':state,'reasons':list(reasons)})
    repo_map={}
    for item in a.repos:
        if '=' in item:
            k,v=item.split('=',1); repo_map[k]=os.path.abspath(v)
    for aid,(rel,obj) in artifacts.items():
        life=lint.lifecycle(reg,obj.get('kind')); state=obj.get('status'); errors=lint.validate(obj,reg,schema)
        if state=='review':
            add(aid,obj,rel,'lifecycle','WARN',['deprecated-state review -> proposed']); state='proposed'
        if errors: add(aid,obj,rel,'schema','FAIL',errors)
        else: add(aid,obj,rel,'schema','PASS')
        reason=[]
        history=git_statuses(root,rel)
        transitions=life.get('transitions',{})
        before=history[-2] if len(history)>1 and history[-1]==state else (history[-1] if history and history[-1]!=state else None)
        if before:
            old='proposed' if before=='review' else before; new='proposed' if state=='review' else state
            allowed=transitions.get(old,[])
            if before=='review' and 'proposed' in transitions: allowed=transitions.get('proposed',[])
            if new not in allowed: reason.append('illegal transition '+str(before)+' -> '+str(state))
        requirements=life.get('requirements',{}).get(state,{})
        # v2 standard states; legacy lifecycle-specific behavior remains in artifact-trace.
        if state=='proposed' and not obj.get('acceptance'): reason.append('acceptance criteria required')
        if state=='reviewed':
            authors={x.get('id') for x in obj.get('authors',[]) if isinstance(x,dict)}
            candidates=[]
            rev=subprocess.run(['git','-C',str(root),'rev-parse',f'HEAD:{rel}'],capture_output=True,text=True,encoding='utf-8').stdout.strip()
            for rp in (root/'reviews'/aid).glob('*.json') if (root/'reviews'/aid).exists() else []:
                try:
                    rv=json.loads(rp.read_text(encoding='utf-8')); reviewer=rv.get('reviewer',{}).get('id')
                    if valid_review(rv,aid,rev,rp.name) and reviewer not in authors: candidates.append(rv)
                except Exception: pass
            if not candidates: reason.append('independent review record required')
        if state=='approved':
            # Existing signed approval verifier remains authoritative in artifact-trace.
            if not any(t.get('kind')=='approval' for t in obj.get('trace',[])) and not obj.get('binding_values'): pass
        if state=='in-implementation' and not any(t.get('kind')=='impl' for t in obj.get('trace',[])): reason.append('implementation trace required')
        if state=='verified':
            traces={(t.get('kind'),ac) for t in obj.get('trace',[]) for ac in t.get('ac',[])}
            reviews=False
            if (root/'reviews'/aid).exists():
                for rp in (root/'reviews'/aid).glob('*.json'):
                    try:
                        rv=json.loads(rp.read_text(encoding='utf-8')); reviewer=rv.get('reviewer',{}).get('id')
                        rev=subprocess.run(['git','-C',str(root),'rev-parse',f'HEAD:{rel}'],capture_output=True,text=True,encoding='utf-8').stdout.strip()
                        if valid_review(rv,aid,rev,rp.name) and reviewer not in {x.get('id') for x in obj.get('authors',[]) if isinstance(x,dict)}: reviews=True
                    except Exception: pass
            for ac in obj.get('acceptance',[]):
                need={'test':('impl','test'),'review':('review',),'measure':('evidence',)}.get(ac.get('verify'),())
                if ac.get('verify')=='review' and not reviews: reason.append('review evidence required for '+ac.get('id','?'))
                elif ac.get('verify')=='measure' and not (ac.get('evidence') and ((ac.get('evidence') in artifacts) or (root/ac.get('evidence','')).exists())): reason.append('existing measure evidence required for '+ac.get('id','?'))
                elif ac.get('verify')=='test' and not all((k,ac.get('id')) in traces for k in need): reason.append('test implementation coverage required for '+ac.get('id','?'))
        if state=='released':
            if not any(t.get('kind')=='release' for t in obj.get('trace',[])): reason.append('release trace required')
            if not any(st in ('approved','verified') for st in history): reason.append('release must pass approved or verified')
        if state=='rejected' and not (obj.get('rejection') or {}).get('reason'): reason.append('rejection reason required')
        if state=='blocked' and (not obj.get('blocked_by') or not obj.get('reason')): reason.append('blocked_by and reason required')
        if reason: add(aid,obj,rel,'lifecycle','FAIL',reason)
        else: add(aid,obj,rel,'lifecycle','PASS')
        deps=[]
        for source in obj.get('sources',[]):
            if isinstance(source,str) and re.match(r'^[A-Z]{2,5}-[a-z0-9-]+-\d{3}$',source) and source not in artifacts: deps.append('unknown source '+source)
        for up in obj.get('upstream',[]):
            if up.get('id') not in artifacts: deps.append('unknown upstream '+str(up.get('id')))
        for dep in obj.get('blocked_by',[]):
            if isinstance(dep,str) and re.match(r'^[A-Z]{2,5}-[a-z0-9-]+-\d{3}$',dep) and dep not in artifacts: deps.append('unknown blocked_by '+dep)
        add(aid,obj,rel,'dependencies','FAIL' if deps else 'PASS',deps)
        # Existing staleness and immutable signature logic remains intact.
        cmd=[sys.executable,str(HERE/'artifact-trace.py'),str(root),'--registry',a.registry]+sum((['--repos',f'{k}={v}'] for k,v in repo_map.items()),[])
        tr=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8')
        own=[line for line in tr.stdout.splitlines() if aid in line]
        human=any(line.startswith('HUMAN_REQUIRED ') for line in own)
        trace_fail=tr.returncode!=0 or any(line.startswith('FAIL ') for line in own)
        add(aid,obj,rel,'trace-approval','FAIL' if trace_fail else ('HUMAN_REQUIRED' if human else 'PASS'),own if trace_fail or human else [])
        domain=reg.get('domains',{}).get(obj.get('domain'),{}); plugin=domain.get('quality_plugin')
        if plugin:
            pp=(ROOT/plugin).resolve()
            try:
                ps=iu.spec_from_file_location('domain_quality_plugin',pp); mod=iu.module_from_spec(ps); ps.loader.exec_module(mod)
                from domains._api import Context
                ctx=Context(str(root),reg,rel,artifacts,tool_detector.find_tool)
                for result in mod.check(obj,ctx):
                    if isinstance(result,dict): check=result.get('check','plugin'); st=result.get('state','PASS'); reasons=result.get('reasons',[])
                    else: check=result.check; st=result.state; reasons=result.reasons
                    if st not in VALID: st='FAIL'; reasons=list(reasons)+['plugin returned an unknown result state']
                    add(aid,obj,rel,check,st,reasons)
            except Exception as e: add(aid,obj,rel,'plugin','FAIL',[str(e)])
    counts={s:sum(1 for r in results if r['state']==s) for s in ('PASS','FAIL','WARN','HUMAN_REQUIRED','NOT_AVAILABLE','BLOCKED')}
    if a.json: print(json.dumps({'schema':'rpg-factory.validation/1','tool':'artifact-quality','repo':str(root),'head':subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,encoding='utf-8').stdout.strip(),'results':results,'summary':counts},sort_keys=True))
    else:
        for x in results: print(f"{x['state']} {x['artifact']} {x['check']}"+(': '+'; '.join(x['reasons']) if x['reasons'] else ''))
        print('Artifact quality: '+', '.join(f'{k} {v}' for k,v in counts.items()))
    return 1 if counts['FAIL'] else 0
if __name__=='__main__': sys.exit(main())
