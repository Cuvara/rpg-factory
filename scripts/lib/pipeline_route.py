"""Model routing and best-effort per-run availability for the delivery pipeline."""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
import codexconfig
import fstate

with (Path(__file__).resolve().parents[2] / 'docs/schemas/pipeline-plan.schema.json').open(encoding='utf-8') as _schema:
    KINDS = tuple(json.load(_schema)['properties']['tasks']['items']['properties']['kind']['enum'])


def _safe(x):
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(x))


# The Codex gateway wraps an upstream error in its own status: `unexpected status 503 Service Unavailable: [codex/<model>]
# [429]: The usage limit has been reached`. Case-sensitive and anchored at the status text (the HTTP reason phrase is
# title case), so a test name, a log line or a count that holds these numbers does not match.
_GATEWAY_PREFIX = r'(?:(?:stream )?[Ee]rror:\s*)?'
_GATEWAY_WRAP = _GATEWAY_PREFIX + r'unexpected status (\d{3})(?: [A-Z][a-z]+)*:'
_GATEWAY_TAG = re.compile(r'(?:' + _GATEWAY_WRAP + r'\s*|' + _GATEWAY_PREFIX + r')(\[codex/[^\]\s]+\]\s*)?\[(\d{3})\]:?\s*(.*)')
_GATEWAY_STATUS = re.compile(_GATEWAY_WRAP)


def _unavailable_code(code):
    return code == 401 or 500 <= code <= 599


def gateway_detail(status):
    """The MODEL_UNAVAILABLE detail of a model gateway error, the upstream code first, or None."""
    tagged = _GATEWAY_TAG.match(status)
    if tagged:
        codex, code, body = tagged.group(2), int(tagged.group(3)), tagged.group(4)
        if code == 429 and (codex or re.search(r'\busage limit\b', body, re.IGNORECASE)):
            return 'usage limit (429)'
        if code == 400 and re.search(r'\bmodel_not_found\b', body):
            return 'model not found'
        if codex and _unavailable_code(code):
            return 'gateway error (' + str(code) + ')'
    wrapped = _GATEWAY_STATUS.match(status)
    return 'gateway error (' + wrapped.group(1) + ')' if wrapped and _unavailable_code(int(wrapped.group(1))) else None


def stall_reason(text):
    """Return a reason for factory-pipeline.py agents --down, if the tail indicates a stall."""
    lines = text.splitlines() if isinstance(text, str) else [line for item in text for line in item.splitlines()]
    lines = [line for line in lines if line.strip()][-12:]
    for line in lines:
        agent = re.match(r'[ \u00a0]{0,2}(?:[\u25a0\u26a0\u2022\u25e6\u273b\u2722\u00b7*\u23fa] +)?(\S.*)', line)
        claude = re.match(r'[ \u00a0]{0,4}(?:\u23bf[ \u00a0]+)?(\S.*)', line)
        status = agent.group(1) if agent else ''
        error = claude.group(1) if claude else ''
        usage = (r"(?:you(?:'ve| have) hit your usage limit\b|"
                 r'stream error\b.*(?:\b429\b|too many requests))')
        claude_usage = (r'(?:api error\s*:\s*429\b|api error\b.*(?:rate_limit|overloaded)|'
                        r'claude usage limit reached\b|'
                        r'(?:usage|5-hour) limit reached\b.*\b(?:reset|resets|try again)\b)')
        gateway = gateway_detail(status)
        api = re.match(r'api error\s*:\s*(401|5\d\d)\b', error, re.IGNORECASE)
        if re.match(usage, status, re.IGNORECASE) or re.match(claude_usage, error, re.IGNORECASE):
            status = status if re.match(usage, status, re.IGNORECASE) else error
            detail = 'usage limit' + (' (429)' if re.search(r'\b429\b', status) else '')
        elif re.match(r'(?:reconnecting(?:\.\.\.|\u2026|\s+\d+/\d+)|stream disconnected before completion\b)', status, re.IGNORECASE):
            detail = 'reconnecting'
        elif gateway:
            detail = gateway
        elif api:
            detail = 'gateway error (' + api.group(1) + ')'
        else:
            continue
        return 'MODEL_UNAVAILABLE: ' + detail + ' - ' + line.strip()[:120]
    return None


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


def _codex_provider(login):
    """Return the active authenticated provider's name, without exposing credentials."""
    try:
        data = codexconfig.config()
        profile = data.get('profiles', {}).get(data.get('profile'), {})
        name = profile.get('model_provider', data.get('model_provider'))
        if not isinstance(name, str) or not name:
            return None
        provider = data.get('model_providers', {}).get(name, {})
        headers = provider.get('http_headers', {})
        header = isinstance(headers, dict) and any(k.lower() == 'authorization' for k in headers)
        env_key = provider.get('env_key')
        if header or isinstance(env_key, str) and bool(os.environ.get(env_key)) or provider.get('requires_openai_auth') is True and login:
            return name
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def available(pipe, plan):
    """plan None (the planner): no per-run marks."""
    path = marks_path(plan) if plan is not None else None
    # content, not mtime: two writes within the timer resolution (Windows) share an mtime
    stamp = open(path, 'rb').read() if path and os.path.exists(path) else None
    try:
        # a digest, so the memo never holds the config's header or key values
        config_digest = hashlib.sha256((Path(codexconfig.home()) / 'config.toml').read_bytes()).digest()
    except OSError:
        config_digest = None
    key = (id(pipe), plan.get('id') if plan is not None else None, os.environ.get('RPG_FACTORY_AGENTS'),
           os.environ.get('PATH'), os.environ.get('CODEX_HOME'), os.environ.get('HOME'),
           os.environ.get('USERPROFILE'), stamp, config_digest, frozenset(k for k, v in os.environ.items() if v))
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
    codex_orca = False
    orca_reason = 'Orca not running'
    if chosen is None and any(k.startswith('ORCA_') for k in os.environ) and shutil.which('orca'):
        orca_reason = 'no Orca account'
        try:
            p = subprocess.run(['orca', 'account', 'list', '--json'], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=5)
            data = json.loads(p.stdout) if p.returncode == 0 else {}
            accounts = data.get('result', {})
            for agent in candidates:
                row = accounts.get(agent)
                if agent == 'codex':
                    codex_orca = (isinstance(row, dict) and
                                  (bool(row.get('accounts')) or
                                   isinstance(row.get('systemDefault'), dict) and
                                   row['systemDefault'].get('hasAuth') is True))
                    continue
                if (isinstance(row, dict) and row.get('accounts') == []
                        and isinstance(row.get('systemDefault'), dict)
                        and row['systemDefault'].get('hasAuth') is False):
                    out[agent] = {'available': False, 'why': 'Orca account unavailable'}
        except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
            pass
    if chosen is None and out.get('codex', {}).get('available'):
        codex_bin = pipe['agents']['codex']['bin']
        source = 'orca account' if codex_orca else None
        if not source:
            try:
                login = subprocess.run([shutil.which(codex_bin), 'login', 'status'], capture_output=True,
                                       stdin=subprocess.DEVNULL, timeout=5).returncode == 0
            except (OSError, TypeError, subprocess.TimeoutExpired):
                login = False
            provider = _codex_provider(login) if not login else None
            source = 'codex login' if login else 'api provider ' + provider if provider else None
        out['codex'] = {'available': bool(source), 'why': codex_bin + ' on PATH; ' +
                        (source or orca_reason + ', codex login missing, no authenticated api provider')}
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
    """Prose for tiers XS and S: a .md file anywhere, changelog.d/, or a skills/ path that is not a non-.md file (a skill
    directory holds .md files). docs/ alone is not prose: docs/schemas/*.json and docs/*.json are machine inputs."""
    if path.endswith('.md') or path.startswith('changelog.d/'):
        return True
    return path.startswith('skills/') and '.' not in path.rstrip('/').rsplit('/', 1)[-1]


def xs_plan(plan, task=None):
    """Tier XS: the plan's tier or the task's (the run lead implements it, no task lead or task worktree)."""
    return plan.get('tier') == 'XS' or bool(task) and task.get('tier') == 'XS'


def above_xs(rule, paths, changed_lines=0):
    """Why a change is above tier XS (registry pipeline.tiers.XS): a path that is not prose, more files than max_files,
    more changed lines than max_changed_lines (0 when unknown). Empty when it fits."""
    paths = [str(p).replace('\\', '/') for p in paths]
    why = []
    if rule.get('prose_only', True):
        other = [p for p in paths if not prose_path(p)]
        if other:
            why.append('not prose: ' + ', '.join(other[:5]) + (' ...' if len(other) > 5 else ''))
    if 'max_files' in rule and len(paths) > rule['max_files']:
        why.append(f"{len(paths)} files > {rule['max_files']}")
    if 'max_changed_lines' in rule and changed_lines > rule['max_changed_lines']:
        why.append(f"{changed_lines} changed lines > {rule['max_changed_lines']}")
    return why


def small_task(plan, task):
    """A small plan/task (tier XS or S) or prose-only ownership permits QA by the lead."""
    paths = task.get('paths') or []
    return (plan.get('tier') == 'S' or task.get('tier') == 'S' or xs_plan(plan, task)
            or bool(paths) and all(prose_path(p) for p in paths))


SUITE_CHECK = re.compile(r'(?:(?:env -u TMPDIR|bash)\s+)*(?:\./)?(tests/[\w.-]+\.sh)'
                         r'|(?:env -u TMPDIR\s+)*python3(?:\s+-B)?\s+(?:\./)?(tests/[\w.-]+\.py)')
# Suites run-all runs only with --release (its RELEASE_ONLY): never folded into the task tier command. A constant on
# purpose: --list-suites already omits them without --release, so this second guard needs no extra run-all call;
# tests/pipeline.test.sh fails when it differs from run-all's list.
RELEASE_ONLY = frozenset({'tests/installed-safety.sh'})
# what full_run() splits words on (shlex punctuation_chars), newlines included
SHELL_PUNCT = '();<>|&`\n\r'
RUNALL_WORD = re.compile(r'(?:\./)?tests/run-all\.sh')
# The only run-all check task QA folds into the tier command: a plain standalone command, an optional `env -u TMPDIR`
# and `bash` prefix, then plain flag tokens. No quote, backslash, `#`, `$`, backtick, operator, redirection or newline:
# anything else that mentions run-all is DO_NOT_RUN, so no shell-parsing edge case can hide a full run.
RUNALL_PLAIN = re.compile(r'(?:env -u TMPDIR[ \t]+)?(?:bash[ \t]+)?(?:\./)?tests/run-all\.sh((?:[ \t]+[A-Za-z0-9=,./:-]+)*)')
DO_NOT_RUN = ('DO NOT RUN (run-all inside a check that is not one plain scoped run-all over known suites; full runs '
              'belong to integration QA; report it NOT_RUN): ')
# run-all flags (tests/run-all.sh's argument loop) a plain scoped check may carry; --release and --list-suites are no
# task QA. RUNALL_VALUE_FLAGS take the next word as their value.
RUNALL_FLAGS = frozenset({'--no-workspace', '--no-claude', '--reuse', '--no-wait', '--no-reuse'})
RUNALL_VALUE_FLAGS = frozenset({'--only-suites', '--base', '-j', '--jobs'})
SUITE_PATH = re.compile(r'tests/[\w.-]+\.(?:sh|py)')
# a suite path verdict --failed-suites accepts without run-all's list (run-all itself excluded: RUNALL_WORD)
FAILED_SUITE_PATH = re.compile(r'(?:tests|testlab|scripts)/(?:[\w.-]+/)*[\w.-]+\.(?:sh|py)')
DO_NOT_RUN_FAILED = ('DO NOT RUN (a recorded failed suite that is run-all itself or no suite path; full runs belong '
                     'to integration QA; report it NOT_RUN): ')


def failed_suite_ok(name):
    """A failed suite a re-QA may run on its own: a suite path, never run-all (that would be a full run)."""
    return (bool(FAILED_SUITE_PATH.fullmatch(name)) and '..' not in name.split('/') and not mentions_runall(name))


def suite_command(suite):
    """A suite run on its own, as run-all runs it: several suites need TMPDIR unset, the rest do not mind."""
    return 'env -u TMPDIR ' + ('python3 -B ' if suite.endswith('.py') else 'bash ') + suite


def strip_comments(check):
    """The check without its shell comments: an unquoted, unescaped `#` that starts a word comments out the rest of its
    line, never the newline (command boundaries survive). None on unbalanced quotes or a trailing backslash (unsure)."""
    out, quote, i, n = [], None, 0, len(check)
    while i < n:
        c = check[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == '\\':
            if i + 1 >= n:
                return None
            out.append(check[i:i + 2])
            i += 2
            continue
        elif quote == '"':
            quote = None if c == '"' else quote
        elif c in '\'"':
            quote = c
        elif c == '#' and (not out or len(out[-1]) == 1 and (out[-1].isspace() or out[-1] in SHELL_PUNCT)):
            # an escaped space or operator (`\ #`) is part of a word: the `#` after it starts no comment
            while i < n and check[i] not in '\n\r':
                i += 1
            continue
        out.append(c)
        i += 1
    return None if quote else ''.join(out)


def runall_args(words):
    """run-all's own argument loop over the words after tests/run-all.sh (tests/run-all.sh's `case "$1"`): a flag that
    takes a value consumes the next word, as there. Returns (affected, only-suites value or None, unknown words); a
    word run-all ignores (`--only-suitesXYZ`, `--affected=1`) is unknown, and a value that is itself a flag (`--base
    --affected`) is unknown too: run-all would take it as the value, never as the flag."""
    affected, only, unknown, i = False, None, [], 0
    while i < len(words):
        w = words[i]
        if w in RUNALL_VALUE_FLAGS:
            value = words[i + 1] if i + 1 < len(words) else ''
            if not value or value.startswith('-'):
                unknown.append(w)
            elif w == '--only-suites':
                only = value
            i += 2
            continue
        if w.startswith('--only-suites='):
            if w[len('--only-suites='):]:
                only = w[len('--only-suites='):]
            else:
                unknown.append(w)
        elif w == '--affected':
            affected = True
        elif not (w in RUNALL_FLAGS or re.fullmatch(r'-j[0-9]+|--jobs=[0-9]+', w)):
            unknown.append(w)
        i += 1
    return affected, only, unknown


def runall_words(check):
    """The --only-suites entries of a check that is exactly one plain, scoped run-all invocation (RUNALL_PLAIN, only
    flags run-all knows, with --affected or a non-empty --only-suites list), else None. An empty list: --affected
    alone."""
    match = RUNALL_PLAIN.fullmatch(check.strip(' \t'))
    if not match:
        return None
    affected, only, unknown = runall_args(match[1].split())
    entries = [x for x in (only or '').split(',') if x]
    if unknown or only is not None and not entries or not (affected or entries):
        return None
    return entries


def mentions_runall(check):
    """Any mention of run-all.sh, quotes and backslashes ignored (`run-a"ll".sh`, `run-all\\.sh`)."""
    return bool(re.search(r'run-all\.sh', re.sub(r'[\'"\\]', '', check)))


def qa_checks(tasks, runall_suites=None, failed_suites=None):
    """Split suite invocations from extra commands; run-all is folded into the tier command.
    runall_suites: the suites `tests/run-all.sh --list-suites` prints in the task checkout. Only those are folded
    (run-all rejects any other suite name), except release-only suites; None (no such flag) folds nothing.
    failed_suites: the suites a previous QA recorded as failed; those run-all does not run become extra commands,
    except run-all itself or a name that is no suite path (failed_suite_ok): DO_NOT_RUN_FAILED, never runnable.
    Extras are `[task ids] command`, each command once and each recognised suite once (by suite path; the
    `env -u TMPDIR` form wins: several suites need TMPDIR unset). Only a plain scoped run-all (runall_words) is folded;
    any other check that mentions run-all (a full run, compound, wrapped, quoted, escaped or commented) is marked
    DO_NOT_RUN: task QA never starts a full run and parses no shell. The third value (a full run-all check folded
    away) is always False now: such a check is marked DO_NOT_RUN instead."""
    known = set(runall_suites or ()) - RELEASE_ONLY
    suites, extra, by_suite = set(), {}, {}

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
            entries = runall_words(check)
            # every entry must be a suite run-all lists (when the list is known) or at least a suite path, never
            # run-all itself (`--only-suites tests/run-all.sh` must not become a runnable full run): else the whole
            # check is DO NOT RUN and no command is generated from any of its entries
            if entries is not None and all(
                    not mentions_runall(x) and (x in known if runall_suites is not None else SUITE_PATH.fullmatch(x))
                    for x in entries):
                for x in entries:  # suites a run-all check names join the one tier command
                    if x in known:
                        suites.add(x)
                    else:
                        add_extra(tid, suite_command(x), x)
                continue
            if mentions_runall(check):  # not one plain scoped run-all: never runnable, whatever the shell makes of it
                add_extra(tid, DO_NOT_RUN + check)
                continue
            # Only plain suite commands count: compound commands remain explicit extra checks.
            match = SUITE_CHECK.fullmatch(check.strip())
            suite = match and (match[1] or match[2])
            if suite and suite in known:
                suites.add(suite)
            else:
                add_extra(tid, check, suite or None)
    ids = [str(t.get('id', '?')) for t in tasks]
    for x in failed_suites or []:
        if x in known and not mentions_runall(x):
            suites.add(x)
        elif not failed_suite_ok(x):  # run-all itself or no suite path: never a runnable command
            for tid in ids:
                add_extra(tid, DO_NOT_RUN_FAILED + x)
        elif x not in by_suite:
            for tid in ids:
                add_extra(tid, suite_command(x), x)
    return sorted(suites), [f"[{', '.join(t)}] {c}" for c, t in extra.items()], False


def full_run(check):
    """A check that starts a full run-all: one command of it (standalone or a part of a compound command) runs
    tests/run-all.sh without --affected or --only-suites. Shell operators and redirections split words even without
    spaces (`tests/run-all.sh>qa.log`, `2>&1`, `|tee`); a redirection target is no argument; a quoted word (`bash -c
    '...'`) or an assignment value is checked as a command of its own. A comment ends at its line end: the next line
    stays a command of its own. Unbalanced quotes (anything unparsable): any run-all inside is full."""
    stripped = strip_comments(check)
    if stripped is None:
        return bool(re.search(r'tests/run-all\.sh', check))
    lexer = shlex.shlex(stripped, posix=True, punctuation_chars=SHELL_PUNCT)
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = ' \t', True, ''
    try:
        tokens = list(lexer)
    except ValueError:
        return bool(re.search(r'tests/run-all\.sh', check))
    commands, words, skip = [], [], False
    for token in tokens:
        if token and all(c in SHELL_PUNCT for c in token):
            skip = '<' in token or '>' in token  # `>`, `>>`, `>&`, `&>`, `<`: the redirection target follows
            if re.sub(r'[<>]&?|&>', '', token):
                commands.append(words)  # a separator, a pipe or a grouping ends the command
                words = []
            continue
        if skip:  # a redirection target (or the descriptor of `2>&1`) is no argument
            skip = False
            continue
        words.append(token)
        inner = token.split('=', 1)[1] if re.match(r'[A-Za-z_]\w*=', token) else token
        if inner != token or any(c.isspace() or c in SHELL_PUNCT for c in token):
            if inner and full_run(inner):
                return True
    commands.append(words)
    for ws in commands:
        at = next((i for i, w in enumerate(ws) if RUNALL_WORD.fullmatch(w)), None)
        if at is not None:
            affected, only, _ = runall_args(ws[at + 1:])
            if not (affected or any((only or '').split(','))):
                return True
    return False


def qa_warnings(task):
    out = []
    if any(SUITE_CHECK.search(c) or mentions_runall(c) or
           re.search(r'\b(?:dotnet test|go test|pytest|npm test|cargo test)\b', c)
           for c in task.get('checks', [])):
        out.append(f"task {task.get('id')}: checks contain test suites; implementers run syntax checks only, verify runs suites")
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
