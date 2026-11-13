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

# Pass the actual shell results to Python for parity checks without OS argument conversion.
export RPGF_TEST_MINGW="$(shell_default MINGW64_NT)" RPGF_TEST_MSYS="$(shell_default MSYS_NT)"
export RPGF_TEST_CYGWIN="$(shell_default CYGWIN_NT)" RPGF_TEST_LINUX="$(shell_default Linux)"
export RPGF_TEST_ROOT="$ROOT"
python_out=$(python3 -B - <<'PY'
import json
import os
import sys

root = os.environ['RPGF_TEST_ROOT']
sys.path.insert(0, os.path.join(root, 'scripts', 'lib'))
import workspace

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

for platform, nt in (('MINGW', True), ('MSYS', True), ('CYGWIN', True), ('LINUX', False)):
    shell = os.environ['RPGF_TEST_' + platform]
    if shell.startswith('/c/'):
        shell = 'C:/' + shell[3:]
    check('shell and Python parity ' + platform, shell == workspace.default_workspace({}, nt))
PY
)
python_status=$?
while IFS= read -r line; do
  case "$line" in
    'PASS  '*) ok "${line#PASS  }" ;;
    'FAIL  '*) no "${line#FAIL  }" ;;
    *) no "unexpected Python output: $line" ;;
  esac
done <<< "$python_out"
[ "$python_status" -eq 0 ] || no "Python checks exited $python_status"

echo "workspace default tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
