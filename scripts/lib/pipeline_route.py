"""Model routing and best-effort per-run availability for the delivery pipeline."""
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
import fstate

with (Path(__file__).resolve().parents[2] / 'docs/schemas/pipeline-plan.schema.json').open(encoding='utf-8') as _schema:
    KINDS = tuple(json.load(_schema)['properties']['tasks']['items']['properties']['kind']['enum'])


def _safe(x):
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(x))


def marks_path(plan):
    return os.path.join(fstate.persistent(), 'pipeline', _safe(plan.get('id')), 'agents.json')


def record_path(plan, task, subtask, role, sha=None):
    """<state>/pipeline/<plan>/<task>[@<subtask>]__<role>[__<sha12>].model.json: the model a dispatch started."""
    sub = '@' + _safe(subtask) if subtask else ''
    tail = '__' + sha[:12] if sha else ''
    return os.path.join(fstate.persistent(), 'pipeline', _safe(plan.get('id')),
                        _safe(task) + sub + '__' + role + tail + '.model.json')


def record(plan, task, subtask, role, data, sha=None):
    fstate.write_json(record_path(plan, task, subtask, role, sha), data, indent=2)


def recorded(plan, task, subtask, role, sha=None):
    rec = fstate.read_json(record_path(plan, task, subtask, role, sha))
    return rec if isinstance(rec, dict) and rec.get('agent') else None


def planned(pipe, item):
    """The implementer the plan names with every agent available (no availability, no record)."""
    return route(pipe, item, {a: {'available': True} for a in pipe['agents']})


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
    """plan None (the planner): no per-run marks."""
    path = marks_path(plan) if plan is not None else None
    stamp = os.stat(path).st_mtime_ns if path and os.path.exists(path) else None
    key = (id(pipe), plan.get('id') if plan is not None else None, os.environ.get('RPG_FACTORY_AGENTS'), os.environ.get('PATH'), stamp)
    if key in _cache:
        return _cache[key]
    override = os.environ.get('RPG_FACTORY_AGENTS')
    chosen = {x.strip() for x in override.split(',')} if override is not None else None
    out = {}
    candidates = pipe.get('available_agents', list(pipe['agents']))
    for agent, cfg in pipe['agents'].items():
        if agent not in candidates:
            out[agent] = {'available': False, 'why': 'not in pipeline.available_agents'}
            continue
        yes = agent in chosen if chosen is not None else bool(shutil.which(cfg['bin']))
        out[agent] = {'available': yes, 'why': 'RPG_FACTORY_AGENTS override' if chosen is not None else
                      (cfg['bin'] + (' on PATH' if yes else ' missing from PATH'))}
    if chosen is None and any(k.startswith('ORCA_') for k in os.environ) and shutil.which('orca'):
        try:
            p = subprocess.run(['orca', 'account', 'list', '--json'], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=5)
            data = json.loads(p.stdout) if p.returncode == 0 else {}
            accounts = data.get('result', {})
            for agent in candidates:
                row = accounts.get(agent)
                if (isinstance(row, dict) and row.get('accounts') == []
                        and isinstance(row.get('systemDefault'), dict)
                        and row['systemDefault'].get('hasAuth') is False):
                    out[agent] = {'available': False, 'why': 'Orca account unavailable'}
        except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
            pass
    for agent, reason in (fstate.read_json(path, {}) if path else {}).items():
        if agent in out:
            out[agent] = {'available': False, 'why': 'MODEL_UNAVAILABLE' + (': ' + reason if reason else '')}
    _cache[key] = out
    return out


def choose(agent, why, avail):
    if avail.get(agent, {}).get('available'):
        return agent, why
    other = next((a for a, state in avail.items() if state['available']), None)
    return (other, 'fallback: ' + str(agent) + ' unavailable') if other else (agent, why + '; WARNING no agents available')


def route(pipe, item, avail):
    kind = item.get('kind')
    routing = pipe.get('agent_routing', {})
    kind_agent = routing.get(kind if isinstance(kind, str) else None)
    agent = item.get('implementer') or kind_agent or routing.get('default') or pipe['default_implementer']
    why = ('explicit implementer' if item.get('implementer') else 'kind: ' + str(kind) if kind_agent
           else 'agent_routing.default' if routing.get('default') else 'default_implementer')
    return choose(agent, why, avail)


def paired(pipe, item, impl):
    reviewer = item.get("reviewer")
    return reviewer if reviewer and reviewer != impl else pipe["review_pairing"].get(impl)


def roles(pipe, item, avail, impl=None):
    """impl: the (agent, why) review and QA pair against - the recorded implementer, else the planned one; None
    forecasts it from availability (status, implement and lead dispatch before anything was recorded)."""
    impl = impl or route(pipe, item, avail)
    pair = paired(pipe, item, impl[0])
    review = choose(pair, 'review_pairing', avail)
    if review[0] == impl[0] and pair != impl[0] and not avail.get(pair, {}).get('available'):
        review = (review[0], 'SAME_MODEL (fallback: ' + str(pair) + ' unavailable)')
    qa = pipe.get('qa_prefer', pipe['review_pairing'].get(impl[0]))
    if qa == impl[0]:
        qa = pipe['review_pairing'].get(impl[0])
    return {'implement': impl, 'lead': choose(pipe.get('lead_agent', 'claude'), 'lead_agent', avail),
            'review': review, 'qa': choose(qa, 'qa_prefer / review_pairing', avail)}


def warnings(pipe, items):
    out = []
    for item in items:
        kind = item.get('kind')
        if kind is not None and kind not in KINDS:
            continue
        routing = pipe.get('agent_routing', {})
        expected = routing.get(kind) or routing.get('default') or pipe['default_implementer']
        if expected and item.get('implementer') and item['implementer'] != expected and not (item.get('reason') or '').strip():
            out.append(str(item.get('id', '?')) + ': implementer overrides ' + ('kind' if routing.get(kind) else 'default') + ' routing without reason')
    planned = {a: {'available': True} for a in pipe['agents']}
    if len(items) >= 3 and len({route(pipe, i, planned)[0] for i in items}) == 1:
        out.append('one-model plan: 3 or more tasks/subtasks use one model')
    return out


def prose_path(path):
    """Prose for tier S: a .md file anywhere, changelog.d/, or a skills/ path that is not a non-.md file (a skill
    directory holds .md files). docs/ alone is not prose: docs/schemas/*.json and docs/*.json are machine inputs."""
    if path.endswith('.md') or path.startswith('changelog.d/'):
        return True
    return path.startswith('skills/') and '.' not in path.rstrip('/').rsplit('/', 1)[-1]


def small_task(plan, task):
    """A small plan/task or prose-only ownership permits QA by the lead."""
    paths = task.get('paths') or []
    return (plan.get('tier') == 'S' or task.get('tier') == 'S' or bool(paths) and all(prose_path(p) for p in paths))


SUITE_CHECK = re.compile(r'(?:(?:env -u TMPDIR|bash)\s+)*(?:\./)?(tests/[\w.-]+\.sh)'
                         r'|(?:env -u TMPDIR\s+)*python3(?:\s+-B)?\s+(?:\./)?(tests/[\w.-]+\.py)')
# Suites run-all runs only with --release (its RELEASE_ONLY): never folded into the task tier command. A constant on
# purpose: --list-suites already omits them without --release, so this second guard needs no extra run-all call;
# tests/pipeline.test.sh fails when it differs from run-all's list.
RELEASE_ONLY = frozenset({'tests/installed-safety.sh'})
# any command separator, grouping, redirection or substitution the shell accepts, newlines included
COMPOUND = re.compile(r'[;&|<>()`\n\r]|\$\(')
DO_NOT_RUN = 'DO NOT RUN (a full run-all inside; full runs belong to integration QA; report it NOT_RUN): '


def suite_command(suite):
    """A suite run on its own, as run-all runs it: several suites need TMPDIR unset, the rest do not mind."""
    return 'env -u TMPDIR ' + ('python3 -B ' if suite.endswith('.py') else 'bash ') + suite


def runall_words(check):
    """The arguments of a check that is exactly one standalone run-all invocation (an optional `env [-u VAR]... [VAR=x]...`
    and `bash` prefix), else None. A compound command (&&, ||, ;, |, redirection, subshell, substitution) is None:
    it stays one complete extra command, never split or dropped."""
    if COMPOUND.search(check):
        return None
    try:
        words = shlex.split(check)
    except ValueError:
        return None
    i = 0
    if words[:1] == ['env']:
        i = 1
        while i < len(words):
            if words[i] == '-u' and i + 1 < len(words):
                i += 2
            elif re.fullmatch(r'[A-Za-z_]\w*=.*', words[i]):
                i += 1
            else:
                break
    if words[i:i + 1] == ['bash']:
        i += 1
    if i < len(words) and re.fullmatch(r'(?:\./)?tests/run-all\.sh', words[i]):
        return words[i + 1:]
    return None


def qa_checks(tasks, runall_suites=None, failed_suites=None):
    """Split suite invocations from extra commands; run-all is folded into the tier command.
    runall_suites: the suites `tests/run-all.sh --list-suites` prints in the task checkout. Only those are folded
    (run-all rejects any other suite name), except release-only suites; None (no such flag) folds nothing.
    failed_suites: the suites a previous QA recorded as failed; those run-all does not run become extra commands.
    Extras are `[task ids] command`, each command once and each recognised suite once (by suite path; the
    `env -u TMPDIR` form wins: several suites need TMPDIR unset). A compound check with a full run inside is marked
    DO_NOT_RUN: task QA never starts a full run (validate warns on it)."""
    known = set(runall_suites or ()) - RELEASE_ONLY
    suites, extra, by_suite, dropped = set(), {}, {}, False

    def add_extra(tid, command, suite=None):
        if suite:
            old = by_suite.setdefault(suite, command)
            if old != command and '-u TMPDIR' in command and '-u TMPDIR' not in old:
                by_suite[suite] = command  # the first form's position and task ids stay
                renamed = [(command if c == old else c, t) for c, t in extra.items()]
                extra.clear()
                extra.update(renamed)
            command = by_suite[suite]
        ids = extra.setdefault(command, [])
        if tid not in ids:
            ids.append(tid)
    for task in tasks:
        tid = str(task.get('id', '?'))
        for check in task.get('checks', []):
            words = runall_words(check)
            if words is not None:
                dropped |= not any(w == '--affected' or w.startswith('--only-suites') for w in words)
                for i, w in enumerate(words):  # suites a run-all check names join the one tier command
                    listed = w.split('=', 1)[1] if w.startswith('--only-suites=') else (
                        words[i + 1] if w == '--only-suites' and i + 1 < len(words) else '')
                    for x in (x.strip() for x in listed.split(',')):
                        if x in known:
                            suites.add(x)
                        elif x:
                            add_extra(tid, suite_command(x), x)
                continue
            # Only plain suite commands count: compound commands remain explicit extra checks.
            match = SUITE_CHECK.fullmatch(check.strip())
            suite = match and (match[1] or match[2])
            if suite and suite in known:
                suites.add(suite)
            elif COMPOUND.search(check) and full_run(check):
                add_extra(tid, DO_NOT_RUN + check)
            else:
                add_extra(tid, check, suite or None)
    ids = [str(t.get('id', '?')) for t in tasks]
    for x in failed_suites or []:
        if x in known:
            suites.add(x)
        elif x not in by_suite:
            for tid in ids:
                add_extra(tid, suite_command(x), x)
    return sorted(suites), [f"[{', '.join(t)}] {c}" for c, t in extra.items()], dropped


def full_run(check):
    """A check that starts a full run-all: one command of it (standalone or a part of a compound command) runs
    tests/run-all.sh without --affected or --only-suites."""
    for part in re.split(r'&&|\|\||[;|&()`\n\r]', check):
        words = [w.strip('\'"') for w in part.split()]  # quotes of `bash -c '...'` stay on the words
        if (any(re.fullmatch(r'(?:\./)?tests/run-all\.sh', w) for w in words)
                and not any(w == '--affected' or w.startswith('--only-suites') for w in words)):
            return True
    return False


def qa_warnings(task):
    out = []
    if any(full_run(c) for c in task.get('checks', [])):
        out.append(f"task {task.get('id')}: full run in checks; full runs belong to integration QA")
    for text in task.get('acceptance', []):
        scoped = '--affected' in text or '--only-suites' in text
        if not scoped and re.search(r'full.*run-all|run-all\.sh.*0 failed'
                                    r'|\b(?:full|whole|entire|complete)\s+(?:test\s+)?suites?\b|\ball\s+(?:the\s+)?suites\b',
                                    text, re.I):
            out.append(f"task {task.get('id')}: full run in acceptance; full runs belong to integration QA")
            break
    return out
