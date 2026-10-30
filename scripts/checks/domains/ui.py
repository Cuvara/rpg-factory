"""UI/UX production checks for the CORE artifact-quality plugin interface."""
import re
from domains._api import Result

STATES = ('empty', 'loading', 'success', 'error', 'disabled')

def _spec(a):
    return a.get('spec', {}) if isinstance(a.get('spec'), dict) else {}

def check(artifact, ctx):
    kind, s = artifact.get('kind'), _spec(artifact)
    all_specs = [o.get('spec', {}) for _, o in ctx.artifacts.values() if isinstance(o.get('spec'), dict)]
    components = {x.get('component_id') for x in all_specs if isinstance(x.get('component_id'), str)}
    tokens = {name for x in all_specs if isinstance(x.get('tokens'), dict) for name in x['tokens']}
    tokens |= {t for x in all_specs if isinstance(x.get('tokens'), list) for t in x['tokens'] if isinstance(t, str)}
    if kind == 'screen-spec':
        missing = [x for x in STATES if x not in s.get('states', {}) or not (s['states'][x] is True or isinstance(s['states'][x], dict) and (s['states'][x].get('implemented') is True or s['states'][x].get('not_applicable') is True and s['states'][x].get('reason')))]
        yield Result('ui-screen-states', 'FAIL' if missing else 'PASS', ['missing states: '+', '.join(missing)] if missing else [])
        bad=[]
        for i,e in enumerate(s.get('elements', [])):
            c=e.get('interaction',{}); a=e.get('accessibility',{})
            if not all(c.get(k) for k in ('trigger','result','feedback','error_path')): bad.append(f'element {i} missing trigger/result/feedback/error_path')
            if not all(a.get(k) for k in ('label','focus_order','contrast_target','input_methods')): bad.append(f'element {i} missing accessibility fields')
        yield Result('ui-interactions-accessibility','FAIL' if bad else 'PASS',bad)
        absent=sorted(set(s.get('components',[]))-components); absent_t=sorted(set(s.get('tokens',[]))-tokens)
        refs=['unknown components: '+', '.join(absent)] if absent else [];refs += ['unknown tokens: '+', '.join(absent_t)] if absent_t else []
        yield Result('ui-reference-integrity','FAIL' if refs else 'PASS',refs)
        if not s.get('platforms') and not s.get('breakpoints'): yield Result('ui-responsive-platform','FAIL',['declare platforms or numeric breakpoints'])
        else: yield Result('ui-responsive-platform','PASS')
        fig=s.get('figma')
        if fig:
            valid=bool(re.fullmatch(r'[A-Za-z0-9_-]{3,128}',str(fig.get('file_key',''))) and re.fullmatch(r'[A-Za-z0-9:._-]{1,160}',str(fig.get('node_id',''))))
            yield Result('ui-figma-reference','PASS' if valid else 'FAIL',['invalid Figma file_key/node_id format'] if not valid else [])
            yield Result('ui-figma-visual-verification','HUMAN_REQUIRED',['visual verification requires an attached screenshot/export or human inspection'])
        else:
            tool=ctx.tools('figma') if callable(ctx.tools) else None
            yield Result('ui-figma-adapter','NOT_AVAILABLE',['Figma MCP/tool not available; structured UI specification remains sufficient']) if not tool else Result('ui-figma-adapter','HUMAN_REQUIRED',['Figma tool detected; visual verification requires human review'])
    if kind == 'ia-map':
        screens=set(s.get('screens',[])); graph={x:set() for x in screens};bad=[]
        for edge in s.get('navigation',[]):
            src,dst=edge.get('from'),edge.get('to')
            if src not in screens or dst not in screens: bad.append(f'dangling navigation {src} -> {dst}')
            else: graph[src].add(dst)
        start=s.get('entry_screen'); seen=set(); stack=[start] if start in graph else []
        while stack:
            x=stack.pop()
            if x not in seen: seen.add(x);stack.extend(graph[x]-seen)
        if start not in graph: bad.append('entry_screen must name a listed screen')
        bad += ['unreachable screens: '+', '.join(sorted(screens-seen))] if screens-seen else []
        yield Result('ui-navigation-graph','FAIL' if bad else 'PASS',bad)
    if kind == 'ui-handoff':
        bad=[]
        for screen in s.get('screens',[]):
            sid=screen.get('screen_id')
            if not sid: bad.append('handoff screen missing screen_id')
            if not screen.get('target_engine_paths'): bad.append(f'{sid}: target_engine_paths required')
            if not screen.get('acceptance_criteria'): bad.append(f'{sid}: acceptance criteria required')
            for ac in screen.get('acceptance_criteria',[]):
                if not ac.get('id') or not ac.get('test'): bad.append(f'{sid}: acceptance criterion needs id and test')
        yield Result('ui-handoff-acceptance','FAIL' if bad else 'PASS',bad)
    if kind == 'design-tokens':
        bad=[]
        for name,value in s.get('tokens',{}).items():
            if not isinstance(name,str) or not name: bad.append('token names must be non-empty')
            if isinstance(value,str) and ('color' in name.lower() or 'colour' in name.lower()) and not re.fullmatch(r'#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?',value): bad.append(f'{name}: colour must be #RRGGBB or #RRGGBBAA')
            if isinstance(value,(int,float)) and value<0: bad.append(f'{name}: numeric scales must be non-negative')
            if isinstance(value,dict) and 'value' in value:
                v=value['value'];typ=value.get('type','')
                if typ in ('color','colour') and (not isinstance(v,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?',v)):bad.append(f'{name}: invalid color value')
                if isinstance(v,(int,float)) and v<0:bad.append(f'{name}: numeric scale must be non-negative')
        yield Result('ui-token-format','FAIL' if bad else 'PASS',bad)
