#!/usr/bin/env bash
# Platform defaults and environment overrides shared by shell and Python.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
HELPER="$ROOT/scripts/lib/workspace.sh"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

# Source in isolation so an inherited workspace does not affect the checks.
out=$(unset RPG_FACTORY_WORKSPACE; set -euo pipefail; . "$HELPER"; [ "${RPG_FACTORY_WORKSPACE+x}" != x ])
[ "$?" -eq 0 ] && [ -z "$out" ] && ok "source is silent and safe with an unset workspace under strict mode" || no "source with unset workspace"
out=$(RPG_FACTORY_WORKSPACE='kept value'; . "$HELPER"; [ "$RPG_FACTORY_WORKSPACE" = 'kept value' ])
[ "$?" -eq 0 ] && [ -z "$out" ] && ok "source leaves an existing workspace unchanged and is silent" || no "source with existing workspace"

shell_default() (
  unset RPG_FACTORY_WORKSPACE
  # Keep the platform in a separate variable: uname receives -s from the helper.
  _PLATFORM=$1
  uname() { printf '%s\n' "$_PLATFORM"; }
  . "$HELPER"
  rpgf_default_workspace
)
for platform in MINGW64_NT MSYS_NT CYGWIN_NT Linux Darwin; do
  case "$platform" in MINGW*|MSYS*|CYGWIN*) expected=/c/Workspaces/UnityIndie ;; *) expected=/mnt/c/Workspaces/UnityIndie ;; esac
  got=$(shell_default "$platform")
  [ "$got" = "$expected" ] && ok "shell default $platform" || no "shell default $platform: $got"
done
for platform in MINGW64_NT Linux; do
  got=$(unset RPG_FACTORY_WORKSPACE; RPG_FACTORY_WORKSPACE=''; uname() { printf '%s\n' "$platform"; }; . "$HELPER"; rpgf_default_workspace)
  [ "$got" = "$(shell_default "$platform")" ] && ok "shell empty value falls back on $platform" || no "shell empty value on $platform: $got"
  got=$(RPG_FACTORY_WORKSPACE='custom workspace'; uname() { printf '%s\n' "$platform"; }; . "$HELPER"; rpgf_default_workspace)
  [ "$got" = 'custom workspace' ] && ok "shell explicit value wins on $platform" || no "shell explicit value on $platform: $got"
done

# On Git Bash ROOT is in drive form, safe from MSYS path conversion.
export RPGF_TEST_ROOT="$ROOT"
python_out=$(python3 -B - <<'PY'
import json
import os
import sys
import tempfile

root = os.environ['RPGF_TEST_ROOT']
sys.path.insert(0, os.path.join(root, 'scripts', 'lib'))
import workspace
import fstate

def check(name, condition):
    print(('PASS  ' if condition else 'FAIL  ') + name)

for nt, expected in ((False, '/mnt/c/Workspaces/UnityIndie'), (True, 'C:/Workspaces/UnityIndie')):
    for env, label in (({}, 'missing'), ({'RPG_FACTORY_WORKSPACE': ''}, 'empty'),
                       ({'RPG_FACTORY_WORKSPACE': 'custom workspace'}, 'explicit')):
        want = 'custom workspace' if label == 'explicit' else expected
        check(f'Python {label} value nt={nt}', workspace.default_workspace(env, nt) == want)

os.environ['RPG_FACTORY_WORKSPACE'] = 'from environment'
check('Python env=None reads os.environ', workspace.default_workspace() == 'from environment')
os.environ['RPG_FACTORY_WORKSPACE'] = ''
check('Python env=None falls back for empty environment value',
      workspace.default_workspace(nt=False) == workspace.WSL_WORKSPACE_DEFAULT)
with open(os.path.join(root, 'registry.json'), encoding='utf-8') as registry:
    check('WSL constant matches registry', workspace.WSL_WORKSPACE_DEFAULT == json.load(registry)['workspace']['root_default'])

root_env = 'RPGF_TEST_WORKSPACE_DEFAULT_UNIQUE'
test_registry = {'workspace': {'root_env': root_env, 'root_default': '/mnt/d/Other/WS'}}
for nt, expected in ((True, 'D:/Other/WS'), (False, '/mnt/d/Other/WS')):
    check(f'Python registry default nt={nt}',
          workspace.default_workspace({}, nt, test_registry) == expected)
    check(f'Python registry empty value nt={nt}',
          workspace.default_workspace({root_env: ''}, nt, test_registry) == expected)
    check(f'Python registry environment wins nt={nt}',
          workspace.default_workspace({root_env: 'registry override'}, nt, test_registry) == 'registry override')

previous_env = os.environ.pop(root_env, None)
previous_cwd = os.getcwd()
temp_dir = tempfile.TemporaryDirectory()
try:
    temp = temp_dir.name
    start = os.path.join(temp, 'start')
    other = os.path.join(temp, 'other')
    os.makedirs(start)
    os.makedirs(other)
    open(os.path.join(other, 'marker'), 'w').close()
    if os.name == 'nt':
        default = os.path.join(temp, 'default').replace('\\', '/')
        os.makedirs(default)
        wsl_default = '/mnt/' + default[0].lower() + default[2:]
    else:
        os.chdir(temp)
        default = 'C:/ws'
        os.makedirs(default)
        wsl_default = '/mnt/c/ws'
    open(os.path.join(default, 'marker'), 'w').close()
    find_registry = {'workspace': {'root_env': root_env, 'root_default': wsl_default,
                                   'root_markers': ['marker']}}
    check('find_workspace converts the WSL-form registry default with nt=True',
          workspace.find_workspace(start, find_registry, use_default=True, nt=True) == default)
    check('find_workspace leaves the WSL-form default unconverted with nt=False',
          not os.path.exists(wsl_default) and
          workspace.find_workspace(start, find_registry, use_default=True, nt=False) is None)
    check('find_workspace prefers the workspace containing start',
          workspace.find_workspace(other, find_registry, use_default=True, nt=True) == os.path.abspath(other))
    os.environ[root_env] = other
    check('find_workspace prefers the exported workspace over the default',
          workspace.find_workspace(start, find_registry, use_default=True, nt=True) == os.path.abspath(other))
    state_registry = {'workspace': {'root_env': root_env,
                                    'root_default': '/mnt/c/Workspaces/UnityIndie'}}
    check('fstate uses an existing exported workspace', fstate.workspace(state_registry, nt=True) == other)
    del os.environ[root_env]
    check('fstate converts the registry default with nt=True',
          fstate.workspace(state_registry, nt=True) == 'C:/Workspaces/UnityIndie')
finally:
    os.chdir(previous_cwd)
    temp_dir.cleanup()
    if previous_env is None:
        os.environ.pop(root_env, None)
    else:
        os.environ[root_env] = previous_env

print('DEFAULT_NT ' + workspace.default_workspace({}, True))
print('DEFAULT_POSIX ' + workspace.default_workspace({}, False))
PY
)
python_status=$?
while IFS= read -r line; do
  line=${line%$'\r'}
  case "$line" in
    'PASS  '*) ok "${line#PASS  }" ;;
    'FAIL  '*) no "${line#FAIL  }" ;;
    'DEFAULT_NT '*) python_nt=${line#DEFAULT_NT } ;;
    'DEFAULT_POSIX '*) python_posix=${line#DEFAULT_POSIX } ;;
    *) no "unexpected Python output: $line" ;;
  esac
done <<< "$python_out"
[ "$python_status" -eq 0 ] || no "Python checks exited $python_status"
for platform in MINGW MSYS CYGWIN LINUX; do
  case "$platform" in
    MINGW) shell=$(shell_default MINGW64_NT); python=${python_nt-} ;;
    MSYS) shell=$(shell_default MSYS_NT); python=${python_nt-} ;;
    CYGWIN) shell=$(shell_default CYGWIN_NT); python=${python_nt-} ;;
    LINUX) shell=$(shell_default Linux); python=${python_posix-} ;;
  esac
  case "$shell" in /c/*) shell="C:/${shell#/c/}" ;; esac
  case "$python" in /c/*) python="C:/${python#/c/}" ;; esac
  [ "$shell" = "$python" ] && ok "shell and Python parity $platform" || no "shell and Python parity $platform"
done

echo "workspace default tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
