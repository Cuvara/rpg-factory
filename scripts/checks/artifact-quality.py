#!/usr/bin/env python3
"""Aggregate artifact schema, lifecycle, trace, review, approval and plugin checks."""
import argparse, datetime, importlib.util, json, os, re, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/'domains'))
sys.path.insert(0,str(ROOT/'scripts'))
from lib import tools as tool_detector
import importlib.util as review_loader
review_spec=review_loader.spec_from_file_location('artifact_review',HERE/'artifact-review.py'); review=review_loader.module_from_spec(review_spec); review_spec.loader.exec_module(review)
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
    paths=[]; discovery_errors=[]
    def discovery_error(exc): discovery_errors.append((Path(getattr(exc,'filename',None) or root), str(exc)))
    for base, dirs, names in os.walk(root, onerror=discovery_error):
        dirs[:] = [d for d in dirs if d not in ('.git','approvals')]
        for name in sorted(names):
            p=Path(base)/name
            if name.endswith(('.artifact.json','.asset.json')): paths.append(p)
            elif p.suffix=='.md':
                try:
                    if p.read_text(encoding='utf-8').startswith('---json'): paths.append(p)
                except Exception as exc: discovery_errors.append((p, str(exc)))
    artifacts={}; selected=[]; malformed=[]
    for p in sorted(paths):
        try:
            obj=read_artifact(p)
            if not isinstance(obj,dict): raise ValueError('artifact document must be a JSON object')
            if not obj.get('id'): raise ValueError('missing id')
            if not obj.get('kind'): raise ValueError('missing kind')
        except Exception as exc:
            malformed.append((p, str(exc))); continue
        rel=p.relative_to(root).as_posix(); artifacts[obj['id']]=(rel,obj)
        # --kind/--domain select what is reported; every artifact stays resolvable (cross-domain sources, upstream)
        if not (a.kind and obj.get('kind')!=a.kind or a.domain and obj.get('domain')!=a.domain): selected.append(obj['id'])
    results=[]
    for p, error in malformed + discovery_errors:
        results.append({'artifact':p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p),'kind':'','domain':'','status':'','check':'parse','state':'FAIL','reasons':[error]})
    def add(aid,obj,rel,check,state,reasons=()): results.append({'artifact':aid,'kind':obj.get('kind',''),'domain':obj.get('domain',''),'status':obj.get('status',''),'check':check,'state':state,'reasons':list(reasons)})
    repo_map={}
    for item in a.repos:
        if '=' in item:
            k,v=item.split('=',1); repo_map[k]=os.path.abspath(v)
    repo_roots={k:Path(v).resolve() for k,v in repo_map.items() if k in reg.get('repos',{})}
    repo_roots.setdefault('authoring', root.resolve())
    for aid in selected:
        rel,obj=artifacts[aid]
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
        if requirements.get('schema_complete') and errors: reason.append('complete artifact schema required')
        if requirements.get('acceptance') and not obj.get('acceptance'): reason.append('acceptance criteria required')
        if requirements.get('independent_review'):
            authors={x.get('id') for x in obj.get('authors',[]) if isinstance(x,dict)} | review.author_emails(root,rel)
            candidates=[]
            rev=subprocess.run(['git','-C',str(root),'rev-parse',f'HEAD:{rel}'],capture_output=True,text=True,encoding='utf-8').stdout.strip()
            for rp in (root/'reviews'/aid).glob('*.json') if (root/'reviews'/aid).exists() else []:
                try:
                    rv=json.loads(rp.read_text(encoding='utf-8')); reviewer=rv.get('reviewer',{}).get('id')
                    relative=rp.relative_to(root).as_posix(); identity,error=review.review_commit(root,relative)
                    if error: continue
                    commit,email=identity
                    if valid_review(rv,aid,rev,rp.name) and reviewer!=email: reason.append('review identity mismatch')
                    if valid_review(rv,aid,rev,rp.name) and email not in authors and reviewer==email:
                        assurance='process'; requirement=requirements.get('review_assurance',reg.get('artifact_lifecycles',{}).get('default',{}).get('review_assurance','process'))
                        if requirement=='signed':
                            assurance,_=review.signed(root,commit,reg.get('domains',{}).get(obj.get('domain'),{}));
                            if assurance!='PASS': reason.append('signed review required: '+_); continue
                            assurance='signed'
                        candidates.append((rv,assurance))
                except Exception: pass
            if not candidates and not any(x.startswith('signed review required:') for x in reason): reason.append('independent review record required')
            elif candidates: add(aid,obj,rel,'review-assurance','PASS',[candidates[0][1]])
        required_traces=requirements.get('needs_trace',[])
        for trace_kind in required_traces:
            if not any(t.get('kind')==trace_kind for t in obj.get('trace',[])): reason.append(trace_kind+' trace required')
        if requirements.get('needs_review') and not (root/'reviews'/aid).exists(): reason.append('review evidence required')
        if requirements.get('coverage_by_acceptance'):
            traces={(t.get('kind'),ac) for t in obj.get('trace',[]) for ac in t.get('ac',[])}
            reviews=False
            if (root/'reviews'/aid).exists():
                for rp in (root/'reviews'/aid).glob('*.json'):
                    try:
                        rv=json.loads(rp.read_text(encoding='utf-8')); reviewer=rv.get('reviewer',{}).get('id')
                        rev=subprocess.run(['git','-C',str(root),'rev-parse',f'HEAD:{rel}'],capture_output=True,text=True,encoding='utf-8').stdout.strip()
                        identity,error=review.review_commit(root,rp.relative_to(root).as_posix())
                        if not error and identity[1]==reviewer and identity[1] not in ({x.get('id') for x in obj.get('authors',[]) if isinstance(x,dict)} | review.author_emails(root,rel)) and valid_review(rv,aid,rev,rp.name): reviews=True
                    except Exception: pass
            for ac in obj.get('acceptance',[]):
                coverage=requirements.get('verify_type_coverage',{}).get(ac.get('verify'), {})
                if coverage.get('needs_review') and not reviews: reason.append('review evidence required for '+ac.get('id','?'))
                if coverage.get('needs_evidence') and not (ac.get('evidence') and ((ac.get('evidence') in artifacts) or (root/ac.get('evidence','')).exists())): reason.append('existing measure evidence required for '+ac.get('id','?'))
                need=coverage.get('needs_trace', [])
                if need and not all((k,ac.get('id')) in traces for k in need): reason.append('test implementation coverage required for '+ac.get('id','?'))
        if requirements.get('requires_approved_verified') and not all(st in history for st in ('approved','verified')): reason.append('release must pass approved and verified')
        if requirements.get('rejection_record') and not (obj.get('rejection') or {}).get('reason'): reason.append('rejection reason required')
        if requirements.get('blocked_by') and (not obj.get('blocked_by') or not obj.get('reason')): reason.append('blocked_by and reason required')
        if reason:
            signed_unavailable=any(x.startswith('signed review required: no trusted reviewer keys') or x.startswith('signed review required: review signature untrusted or invalid') for x in reason)
            add(aid,obj,rel,'lifecycle','HUMAN_REQUIRED' if signed_unavailable else 'FAIL',reason)
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
                ctx=Context(str(root),reg,rel,artifacts,tool_detector.find_tool,repo_roots)
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
