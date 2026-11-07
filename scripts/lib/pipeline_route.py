"""Model routing and best-effort per-run availability for the delivery pipeline."""
import json
import os
import shutil
import subprocess
import fstate

KINDS = ('lead', 'plan', 'docs', 'policy', 'design', 'code', 'test', 'fix', 'refactor', 'generated')


def marks_path(plan):
    return os.path.join(fstate.persistent(), 'pipeline', ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(plan.get('id'))), 'agents.json')


def mark(plan, agent, reason=None):
    path = marks_path(plan)
    marks = fstate.read_json(path, {})
    if reason is None:
        marks.pop(agent, None)
    else:
        marks[agent] = reason
    fstate.write_json(path, marks, indent=2)


_cache = {}


def available(pipe, plan):
    path = marks_path(plan)
    stamp = os.stat(path).st_mtime_ns if os.path.exists(path) else None
    key = (id(pipe), plan.get('id'), os.environ.get('RPG_FACTORY_AGENTS'), os.environ.get('PATH'), stamp)
    if key in _cache:
        return _cache[key]
    override = os.environ.get('RPG_FACTORY_AGENTS')
    chosen = {x.strip() for x in override.split(',')} if override is not None else None
    out = {}
    for agent, cfg in pipe['agents'].items():
        yes = agent in chosen if chosen is not None else bool(shutil.which(cfg['bin']))
        out[agent] = {'available': yes, 'why': 'RPG_FACTORY_AGENTS override' if chosen is not None else
                      (cfg['bin'] + (' on PATH' if yes else ' missing from PATH'))}
    if chosen is None and any(k.startswith('ORCA_') for k in os.environ) and shutil.which('orca'):
        try:
            p = subprocess.run(['orca', 'account', 'list', '--json'], capture_output=True, text=True, timeout=5)
            data = json.loads(p.stdout) if p.returncode == 0 else {}
            accounts = data.get('result', {}).get('accounts', data.get('result', {}))
            def visit(node):
                if isinstance(node, dict):
                    for agent in out:
                        row = node.get(agent)
                        if isinstance(row, dict) and row.get('status') in ('unavailable', 'error'):
                            # Network/usage probe errors alone do not prove a model cannot run.
                            err = str(row.get('error', ''))
                            if row.get('status') == 'unavailable' or any(s in err.lower() for s in ('401', 'revoked', 'unauthorized')):
                                out[agent] = {'available': False, 'why': 'Orca account unavailable'}
                    for value in node.values():
                        visit(value)
                elif isinstance(node, list):
                    for value in node:
                        visit(value)
            visit(accounts)
        except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
            pass
    for agent, reason in fstate.read_json(marks_path(plan), {}).items():
        if agent in out:
            out[agent] = {'available': False, 'why': 'MODEL_UNAVAILABLE: ' + reason}
    _cache[key] = out
    return out


def choose(agent, why, avail):
    if avail.get(agent, {}).get('available'):
        return agent, why
    other = next((a for a, state in avail.items() if state['available']), None)
    return (other, 'fallback: ' + str(agent) + ' unavailable') if other else (agent, why + '; WARNING no agents available')


def route(pipe, item, avail):
    kind = item.get('kind')
    agent = item.get('implementer') or pipe.get('agent_routing', {}).get(kind if isinstance(kind, str) else None) or pipe['default_implementer']
    why = 'explicit implementer' if item.get('implementer') else ('kind: ' + str(kind) if kind else 'default_implementer')
    return choose(agent, why, avail)


def paired(pipe, item, impl):
    reviewer = item.get("reviewer")
    return reviewer if reviewer and reviewer != impl else pipe["review_pairing"].get(impl)


def roles(pipe, item, avail):
    impl = route(pipe, item, avail)
    pair = paired(pipe, item, impl[0])
    review = choose(pair, 'review_pairing', avail)
    if review[0] == impl[0] and pair != impl[0] and not avail.get(pair, {}).get('available'):
        review = (review[0], 'SAME_MODEL (fallback: ' + str(pair) + ' unavailable)')
    qa = pipe.get('qa_prefer', pipe['review_pairing'].get(impl[0]))
    if qa == impl[0]:
        qa = pipe['review_pairing'].get(impl[0])
    return {'implement': impl, 'lead': choose(pipe.get('lead_agent', 'claude'), 'lead_agent', avail),
            'review': review, 'qa': choose(qa, 'qa_prefer / review_pairing', avail)}


def warnings(pipe, items, avail):
    out = []
    for item in items:
        kind = item.get('kind')
        if kind is not None and kind not in KINDS:
            continue
        expected = pipe.get('agent_routing', {}).get(kind)
        if expected and item.get('implementer') and item['implementer'] != expected and not (item.get('reason') or '').strip():
            out.append(str(item.get('id', '?')) + ': implementer overrides kind routing without reason')
    if len(items) >= 3 and len({route(pipe, i, avail)[0] for i in items}) == 1:
        out.append('one-model plan: 3 or more tasks/subtasks use one model')
    return out
