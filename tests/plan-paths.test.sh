#!/usr/bin/env bash
# scripts/lib/plan_paths.py resolve_repo_path on Windows spellings: a workspace root from the environment, or an
# absolute repo path, written as Git Bash (/c/ws) or WSL (/mnt/c/ws) resolves to the native form; POSIX is unchanged.
# The Windows conversion is exercised on every platform through the nt parameter of workspace.native_path: the
# patched converter maps the drive C: onto a drive directory inside a temp dir, so the same assertions hold on
# Linux CI and on Windows. The plan-paths case of tests/parallel-policy.test.sh keeps the base semantics.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -15 | sed 's/^/      /'; }

out=$(python3 -B - "$ROOT" "$TMP" <<'PY'
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'lib'))  # as factory-pipeline.py imports lib modules
import plan_paths
import workspace
from plan_paths import resolve_repo_path

tmp = Path(sys.argv[2]).resolve()
drive = tmp / 'drive-c'                      # stands for C:/ when the converter runs as on Windows
plan = tmp / 'plans' / 'nested' / 'plan.json'
variable = 'RPG_FACTORY_WORKSPACE'
registry = {'workspace': {'root_env': variable, 'root_markers': ['marker'], 'root_default': str(tmp / 'missing')}}


def windows_native(p):
    """workspace.native_path as on Windows, with the drive C: mapped into the temp dir."""
    r = workspace.native_path(p, nt=True)
    return str(drive) + r[2:] if r.startswith('C:/') else r


def posix_native(p):
    return workspace.native_path(p, nt=False)


def expect(label, value, wanted):
    assert value == wanted, (label, value, wanted)
    print(label)


# the converter itself: both spellings give C:/..., anything else is untouched, POSIX never converts
for spelling in ('/c/ws/repo', '/mnt/c/ws/repo', '/C/ws/repo'):
    expect('native_path nt ' + spelling, workspace.native_path(spelling, nt=True), 'C:/ws/repo')
    expect('native_path posix ' + spelling, workspace.native_path(spelling, nt=False), spelling)
expect('native_path nt leaves a relative path', workspace.native_path('repo/x', nt=True), 'repo/x')

ws = drive / 'ws'                            # the workspace: markers present
(ws / 'marker').mkdir(parents=True)
bare = drive / 'bare'                        # a converted root without the markers
bare.mkdir()
anc = tmp / 'anc'                            # the plan's own ancestor workspace, found when the env root has no markers
(anc / 'marker').mkdir(parents=True)
anc_plan = anc / 'plans' / 'plan.json'

with patch.object(plan_paths, 'native_path', windows_native):
    for label, env in (('Git Bash', '/c/ws'), ('WSL', '/mnt/c/ws')):
        with patch.dict(os.environ, {variable: env}):
            for prefix in ('${' + variable + '}', '$' + variable):
                expect(f'{label} root, prefix {prefix}', resolve_repo_path(prefix + '/repo', plan, registry),
                       (os.path.abspath(str(ws / 'repo')), None))
            expect(f'{label} root alone', resolve_repo_path('$' + variable, plan, registry),
                   (os.path.abspath(str(ws)), None))
            assert os.environ[variable] == env, 'environment restored'
            print(f'{label} root leaves the environment as it was')
    with patch.dict(os.environ, {variable: '/c/ws'}):
        # precedence: the converted env root with every marker beats the plan's own ancestors
        expect('converted env root beats the ancestors', resolve_repo_path('$' + variable + '/r', anc_plan, registry),
               (os.path.abspath(str(ws / 'r')), None))
    with patch.dict(os.environ, {variable: '/c/bare'}):
        # a converted root without the markers falls through to the ancestors of the plan
        expect('marker-less converted root falls through to the ancestors',
               resolve_repo_path('$' + variable + '/r', anc_plan, registry), (os.path.abspath(str(anc / 'r')), None))
        result, reason = resolve_repo_path('$' + variable + '/r', plan, registry)
        assert result is None and variable in reason, (result, reason)
        print('marker-less converted root with no ancestor names the variable')
    with patch.dict(os.environ, {variable: '/c/bare'}):
        registry['workspace']['root_default'] = str(ws)
        expect('marker-less converted root falls through to the registry default',
               resolve_repo_path('$' + variable + '/r', plan, registry), (os.path.abspath(str(ws / 'r')), None))
        registry['workspace']['root_default'] = str(tmp / 'missing')
    # an absolute repo path in either spelling
    for spelling in ('/c/ws/repo', '/mnt/c/ws/repo'):
        expect('absolute repo path ' + spelling, resolve_repo_path(spelling, plan, registry),
               (os.path.abspath(str(ws / 'repo')), None))
    expect('relative repo path stays plan-relative', resolve_repo_path('../../repo', plan, registry),
           (str(tmp / 'repo'), None))

# POSIX (the converter is the identity): nothing is rewritten, the same inputs resolve as before
with patch.object(plan_paths, 'native_path', posix_native):
    plain = tmp / 'posix-ws'
    (plain / 'marker').mkdir(parents=True)
    with patch.dict(os.environ, {variable: str(plain)}):
        expect('posix env root', resolve_repo_path('$' + variable + '/repo', plan, registry),
               (os.path.abspath(str(plain / 'repo')), None))
    for spelling in ('/c/ws/repo', '/mnt/c/ws/repo'):
        expect('posix keeps ' + spelling, resolve_repo_path(spelling, plan, registry),
               (os.path.abspath(os.path.join(str(plan.parent), spelling)), None))
    with patch.dict(os.environ, {variable: '/mnt/c/ws'}):
        result, reason = resolve_repo_path('$' + variable + '/repo', plan, registry)
        assert result is None and variable in reason, (result, reason)
        print('posix unconverted /mnt/c root without markers is not found')
        assert os.environ[variable] == '/mnt/c/ws'
PY
); rc=$?
if [ "$rc" -eq 0 ]; then
  while IFS= read -r label; do ok "plan_paths: $label"; done <<<"$out"
else no "plan_paths windows spellings (rc=$rc)" "$out"; fi

echo "plan-paths: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
