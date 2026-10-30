"""UI/UX production checks for the CORE artifact-quality plugin interface."""
import math
import re
from domains._api import Result

STATES = ('empty', 'loading', 'success', 'error', 'disabled')

def _spec(a):
    return a.get('spec', {}) if isinstance(a.get('spec'), dict) else {}

def check(artifact, ctx):
    kind, s = artifact.get('kind'), _spec(artifact)
    all_artifacts = [o for _, o in ctx.artifacts.values() if isinstance(o, dict)]
    components = {_spec(o).get('component_id') for o in all_artifacts if o.get('kind') == 'component-spec' and isinstance(_spec(o).get('component_id'), str)}
    tokens = {name for o in all_artifacts if o.get('kind') == 'design-tokens' and isinstance(_spec(o).get('tokens'), dict) for name in _spec(o)['tokens']}
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
        breakpoints = s.get('breakpoints', [])
        responsive_bad = []
        if not s.get('platforms') and not breakpoints:
            responsive_bad.append('declare platforms or numeric breakpoints')
        if breakpoints:
            if not isinstance(breakpoints, list):
                responsive_bad.append('breakpoints must be an ordered array of positive numbers')
            elif any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in breakpoints):
                responsive_bad.append('breakpoints must contain only positive numbers')
            elif any(left >= right for left, right in zip(breakpoints, breakpoints[1:])):
                responsive_bad.append('breakpoints must be strictly increasing')
        yield Result('ui-responsive-platform', 'FAIL' if responsive_bad else 'PASS', responsive_bad)
        bindings_bad = []
        declared = {x for x in artifact.get('sources', []) if isinstance(x, str)}
        declared.update(x.get('id') for x in artifact.get('upstream', []) if isinstance(x, dict) and isinstance(x.get('id'), str))
        artifacts_by_id = {o.get('id'): o for o in all_artifacts if isinstance(o.get('id'), str)}
        bindings = s.get('data_bindings', [])
        if not isinstance(bindings, list):
            bindings_bad.append('data_bindings must be an array')
            bindings = []
        for index, binding in enumerate(bindings):
            if not isinstance(binding, dict):
                bindings_bad.append(f'data binding {index} must be an object')
                continue
            source_id, field = binding.get('source_artifact_id'), binding.get('field')
            if not isinstance(source_id, str) or not source_id or not isinstance(field, str) or not field:
                bindings_bad.append(f'data binding {index} requires source_artifact_id and field')
                continue
            if 'value' in binding:
                bindings_bad.append(f'data binding {index} must reference a source field instead of embedding a value')
            if source_id not in declared:
                bindings_bad.append(f'data binding {index} source {source_id} is not declared in sources or upstream')
            source = artifacts_by_id.get(source_id)
            if source is None:
                bindings_bad.append(f'data binding {index} references unknown source artifact {source_id}')
                continue
            value = source.get('spec')
            for part in field.split('.'):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                    value = value[int(part)]
                else:
                    value = None
                    break
            if value is None:
                bindings_bad.append(f'data binding {index} field {field} does not resolve in {source_id}')
        yield Result('ui-data-bindings', 'FAIL' if bindings_bad else 'PASS', bindings_bad)
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
        screens_by_id = {}
        for source_artifact in all_artifacts:
            if source_artifact.get('kind') == 'screen-spec':
                screen_id = _spec(source_artifact).get('screen_id')
                if isinstance(screen_id, str) and screen_id:
                    screens_by_id.setdefault(screen_id, []).append(source_artifact.get('id'))
        for screen in s.get('screens',[]):
            sid=screen.get('screen_id')
            if not sid: bad.append('handoff screen missing screen_id')
            elif not screens_by_id.get(sid): bad.append(f'{sid}: screen_id does not resolve to a screen-spec')
            elif len(screens_by_id[sid]) != 1: bad.append(f'{sid}: screen_id resolves to multiple screen-spec artifacts')
            if not screen.get('target_engine_paths'): bad.append(f'{sid}: target_engine_paths required')
            if not screen.get('acceptance_criteria'): bad.append(f'{sid}: acceptance criteria required')
            for ac in screen.get('acceptance_criteria',[]):
                if not ac.get('id') or not ac.get('test'): bad.append(f'{sid}: acceptance criterion needs id and test')
        yield Result('ui-handoff-acceptance','FAIL' if bad else 'PASS',bad)
    if kind == 'component-spec':
        bad = []
        component_id = s.get('component_id')
        if not isinstance(component_id, str) or not component_id.strip():
            bad.append('component_id must be a non-empty string')
        def records(key, required, label):
            values = s.get(key)
            if not isinstance(values, list) or not values:
                bad.append(f'{key} must contain at least one {label}')
                return []
            for index, item in enumerate(values):
                if not isinstance(item, dict) or any(not isinstance(item.get(field), str) or not item[field].strip() for field in required):
                    bad.append(f'{key}[{index}] requires non-empty {", ".join(required)}')
            return values
        records('variants', ('name', 'description'), 'variant')
        records('props', ('name', 'type', 'description'), 'prop')
        records('states', ('name', 'description'), 'state')
        component_tokens = s.get('tokens')
        if not isinstance(component_tokens, list) or not component_tokens or any(not isinstance(t, str) or not t.strip() for t in component_tokens):
            bad.append('tokens must contain at least one non-empty token name')
        else:
            missing_tokens = sorted(set(component_tokens) - tokens)
            if missing_tokens:
                bad.append('unknown tokens: ' + ', '.join(missing_tokens))
        access = s.get('accessibility')
        if (not isinstance(access, dict) or
                any(not isinstance(access.get(k), str) or not access[k].strip() for k in ('label', 'focus_order', 'contrast_target')) or
                not isinstance(access.get('input_methods'), list) or not access['input_methods'] or
                any(not isinstance(x, str) or not x.strip() for x in access['input_methods'])):
            bad.append('accessibility requires non-empty label, focus_order, contrast_target, and input_methods')
        yield Result('ui-component-quality', 'FAIL' if bad else 'PASS', bad)
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
