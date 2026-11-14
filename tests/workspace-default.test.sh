#!/usr/bin/env bash
# Platform defaults and environment overrides shared by shell and Python.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
HELPER="$ROOT/scripts/lib/workspace.sh"
. "$ROOT/scripts/lib/compat.sh"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

# Source in isolation so an inherited workspace does not affect the checks.
out=$(unset RPG_FACTORY_WORKSPACE; set -euo pipefail; . "$HELPER"; [ "${RPG_FACTORY_WORKSPACE+x}" != x ])
[ "$?" -eq 0 ] && [ -z "$out" ] && ok "source is silent and safe with an unset workspace under strict mode" || no "source with unset workspace"
out=$(RPG_FACTORY_WORKSPACE='kept value'; . "$HELPER"; [ "$RPG_FACTORY_WORKSPACE" = 'kept value' ])
[ "$?" -eq 0 ] && [ -z "$out" ] && ok "source leaves an existing workspace unchanged and is silent" || no "source with existing workspace"

T=$(mktemp -d) || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/outside" "$T/ws" "$T/nocyg" "$T/cyg"
# Deterministic cygpath choices for the CYGWIN cases: "hidden" runs with a PATH that has no cygpath
# (Git for Windows ships a real one), "stub" puts a recognisable stub first on PATH.
cat > "$T/cyg/cygpath" <<'STUB'
#!/usr/bin/env bash
[ "$1" = -u ] || exit 2
p=$2
printf '/stub-cygdrive/%s%s\n' "$(printf '%s' "${p:0:1}" | tr '[:upper:]' '[:lower:]')" "${p:2}"
STUB
chmod +x "$T/cyg/cygpath"
# Mode: hidden (no cygpath), stub (the stub above); anything else leaves PATH alone.
use_cygpath_mode() {
  case "$1" in
    hidden) PATH="$T/nocyg" ;;
    stub) PATH="$T/cyg:$PATH" ;;
  esac
  hash -r
}

shell_default() (
  unset RPG_FACTORY_WORKSPACE
  # Keep the platform in a separate variable: uname receives -s from the helper.
  _PLATFORM=$1
  uname() { printf '%s\n' "$_PLATFORM"; }
  use_cygpath_mode "${2-}"
  . "$HELPER"
  rpgf_default_workspace
)
for platform in MINGW64_NT MSYS_NT Linux Darwin; do
  case "$platform" in MINGW*|MSYS*) expected=/c/Workspaces/UnityIndie ;; *) expected=/mnt/c/Workspaces/UnityIndie ;; esac
  got=$(shell_default "$platform")
  [ "$got" = "$expected" ] && ok "shell default $platform" || no "shell default $platform: $got"
done
got=$(shell_default CYGWIN_NT hidden)
[ "$got" = /cygdrive/c/Workspaces/UnityIndie ] && ok 'shell default CYGWIN without cygpath is the cygdrive form' || no "shell default CYGWIN without cygpath: $got"
got=$(shell_default CYGWIN_NT stub)
[ "$got" = /stub-cygdrive/c/Workspaces/UnityIndie ] && ok 'shell default CYGWIN with cygpath is the cygpath answer' || no "shell default CYGWIN with cygpath: $got"
for platform in MINGW64_NT Linux; do
  got=$(unset RPG_FACTORY_WORKSPACE; RPG_FACTORY_WORKSPACE=''; uname() { printf '%s\n' "$platform"; }; . "$HELPER"; rpgf_default_workspace)
  [ "$got" = "$(shell_default "$platform")" ] && ok "shell empty value falls back on $platform" || no "shell empty value on $platform: $got"
  got=$(RPG_FACTORY_WORKSPACE='custom workspace'; uname() { printf '%s\n' "$platform"; }; . "$HELPER"; rpgf_default_workspace)
  [ "$got" = 'custom workspace' ] && ok "shell explicit value wins on $platform" || no "shell explicit value on $platform: $got"
done

# The conversion is evaluated at call time and leaves other path forms alone.
# CYGWIN runs twice: without cygpath (cygdrive form) and with a stub (the cygpath answer for '<D>:/rest').
for variant in MINGW64_NT MSYS_NT CYGWIN_NT:hidden CYGWIN_NT:stub Linux Darwin; do
  platform=${variant%%:*}
  mode=""; [ "$variant" = "$platform" ] || mode=${variant#*:}
  for path in /mnt/c/Workspaces/UnityIndie /mnt/d/Other/WS /mnt/c /c/x C:/x relative/path; do
    expected=$path
    case "$platform:$path" in
      MINGW*:/mnt/*|MSYS*:/mnt/*) expected="/${path#/mnt/}" ;;
      CYGWIN*:/mnt/*)
        drive_rest=${path#/mnt/}
        case "$mode" in
          stub) expected="/stub-cygdrive/${drive_rest:0:1}${drive_rest:1}"; [ "${#drive_rest}" -gt 1 ] || expected="$expected/" ;;
          *) expected="/cygdrive/$drive_rest" ;;
        esac ;;
    esac
    got=$(uname() { printf '%s\n' "$platform"; }; use_cygpath_mode "$mode"; . "$HELPER"; rpgf_platform_path "$path")
    [ "$got" = "$expected" ] && ok "platform path $variant $path" || no "platform path $variant $path: $got"
  done
done

# Construct every on-disk registry path as a directory; the check requires existence only.
jq -r '(.repos | to_entries[] | .value.path as $p | $p, ((.value.instructions // [])[] | $p + "/" + .)),
  (.repos as $r | .modules[] | $r[.repo].path as $p | (.paths[], (.claude_md // empty), (.changelog // empty), (.docs // [])[], (.generated // [])[]) | $p + "/" + .),
  .workspace.root_markers[],
  (.repos as $r | (.contracts // [])[] | ([.source] + (.copies // []) + (.upstream // []) + (.watchers // []))[] | $r[.repo].path + "/" + .path)' "$ROOT/registry.json" > "$T/paths"
while IFS= read -r rel; do
  rel=${rel%%#*}; case "$rel" in ''|*'*'*) continue ;; esac
  mkdir -p "$T/ws/$rel"
done < "$T/paths"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    ws_drive=$(cd "$T/ws" && pwd -W)
    registry_ws="/mnt/$(printf '%s' "${ws_drive:0:1}" | tr '[:upper:]' '[:lower:]')${ws_drive:2}"
    stub_platform=MINGW64_NT ;;
  *) registry_ws=$(cd "$T/ws" && pwd); stub_platform=Linux ;;
esac
printf '%s' "$registry_ws" > "$T/registry-ws"
jq --rawfile w "$T/registry-ws" 'setpath(["workspace", "root_default"]; $w)' "$ROOT/registry.json" > "$T/registry.json"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "%s"\n' "$stub_platform" > "$T/bin/uname"
chmod +x "$T/bin/uname"
reg_out=$(unset RPG_FACTORY_WORKSPACE; PATH="$T/bin:$PATH" bash "$ROOT/scripts/check-registry.sh" --registry "$T/registry.json" 2>&1)
case "$reg_out" in *'referenced paths exist'*) ok 'registry default resolves to existing workspace paths' ;; *) no "registry default workspace: $reg_out" ;; esac

# The Netcode checkout is a throwaway fixture (cwd's git toplevel holding the headless csproj) whose
# package.json pins a Shared.GameLogic tag no server repo has, so the check ends NOT-RUN(blocked) and names
# the platform's default workspace server path. No real Netcode or rpg-mmo-server checkout is needed.
fx="$T/fx/Netcode"
mkdir -p "$fx/Tests~/Headless"
git init -q "$fx" >/dev/null 2>&1
: > "$fx/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"
printf '%s\n' '{"x-manualDependencies": {"com.rpgmmo.shared-gamelogic": "https://example.invalid/rpg-mmo-server.git?path=/Shared.GameLogic#sgl-v0.0.0-rpgf-fixture-missing"}}' > "$fx/package.json"
for platform in Linux MINGW64_NT; do
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "%s"\n' "$platform" > "$T/bin/uname"
  case "$platform" in Linux) expected=/mnt/c/Workspaces/UnityIndie/rpg-mmo-server ;; *) expected=/c/Workspaces/UnityIndie/rpg-mmo-server ;; esac
  headless_out=$(cd "$fx" && unset RPG_FACTORY_WORKSPACE RPG_FACTORY_REPO_DIR RPG_FACTORY_REPO_KEY && PATH="$T/bin:$PATH" bash "$ROOT/scripts/checks/netcode-headless.sh" --resolve-server 2>&1)
  case "$headless_out" in
    *'<unresolved>'*) no "headless default $platform unresolved" ;;
    NOT-RUN\(blocked\):*sgl-v0.0.0-rpgf-fixture-missing*"$expected"*) ok "headless default $platform" ;;
    *) no "headless default $platform: $headless_out" ;;
  esac
done

# Return each forbidden literal occurrence, retaining file and line for diagnostics.
workspace_literal_violations() {
  local root=$1 file line text
  while IFS=: read -r file line text; do
    case "$file" in
      scripts/lib/workspace.sh|scripts/lib/workspace.py|scripts/README.md|tests/workspace-default.test.sh|tests/fixtures/*) continue ;;
      tests/routing.test.sh) case "$text" in *rpgf_default_workspace*) continue ;; esac ;;
    esac
    printf '%s:%s:%s\n' "$file" "$line" "$text"
  done < <(cd "$root" && grep -rInF '/mnt/c/Workspaces/UnityIndie' scripts tests 2>/dev/null || true)
}
mkdir -p "$T/guard/scripts" "$T/guard/tests"
printf '%s\n' '/mnt/c/Workspaces/UnityIndie' > "$T/guard/scripts/offender.sh"
violations=$(workspace_literal_violations "$T/guard")
case "$violations" in *scripts/offender.sh*) ok 'literal guard detects an offending script' ;; *) no 'literal guard missed an offending script' ;; esac
violations=$(workspace_literal_violations "$ROOT")
[ -z "$violations" ] && ok 'workspace literal guard is clean' || no "workspace literal guard: $violations"

# jq readers must map on the same line; Python readers must use the shared helper.
reader_violations() {
  local root=$1 file line text
  while IFS=: read -r file line text; do
    case "$file" in tests/fixtures/*) [ "$file" = tests/fixtures/check-registry-p4.sh ] || continue ;; esac
    case "$text" in *rpgf_platform_path*) continue ;; esac
    printf '%s:%s:%s\n' "$file" "$line" "$text"
  done < <(cd "$root" && grep -rInE 'jq.*\.workspace\.root_default' scripts tests 2>/dev/null || true)
  while IFS=: read -r file line text; do
    case "$file" in scripts/lib/workspace.py|scripts/lib/fstate.py) continue ;; esac
    printf '%s:%s:%s\n' "$file" "$line" "$text"
  done < <(cd "$root" && grep -rIn --include='*.py' 'root_default' scripts 2>/dev/null || true)
  while IFS=: read -r file line text; do
    case "$file" in scripts/lib/*) continue ;; esac
    printf '%s:%s:%s\n' "$file" "$line" "$text"
  done < <(cd "$root" && grep -rInE --include='*.py' 'default_workspace\(\)' scripts 2>/dev/null || true)
}
# Negative self-test: a raw reader is reported, a converted one is not.
mkdir -p "$T/rguard/scripts" "$T/rguard/tests"
printf '%s\n' 'root=$(jq -r .workspace.root_default registry.json)' > "$T/rguard/scripts/raw.sh"
printf '%s\n' 'root=$(rpgf_platform_path "$(jq -r .workspace.root_default registry.json)")' > "$T/rguard/scripts/ok.sh"
printf '%s\n' "root = registry['workspace']['root_default']" > "$T/rguard/scripts/raw.py"
violations=$(reader_violations "$T/rguard")
case "$violations" in *scripts/raw.sh*) ok 'reader guard detects a raw jq reader' ;; *) no 'reader guard missed a raw jq reader' ;; esac
case "$violations" in *scripts/ok.sh*) no 'reader guard flags a converted jq reader' ;; *) ok 'reader guard accepts a converted jq reader' ;; esac
case "$violations" in *scripts/raw.py*) ok 'reader guard detects a raw Python reader' ;; *) no 'reader guard missed a raw Python reader' ;; esac
violations=$(reader_violations "$ROOT")
[ -z "$violations" ] && ok 'workspace reader guard is clean' || no "workspace reader guard: $violations"

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
    CYGWIN) shell=$(shell_default CYGWIN_NT hidden); python=${python_nt-} ;;
    LINUX) shell=$(shell_default Linux); python=${python_posix-} ;;
  esac
  case "$shell" in /c/*) shell="C:/${shell#/c/}" ;; /cygdrive/c/*) shell="C:/${shell#/cygdrive/c/}" ;; esac
  case "$python" in /c/*) python="C:/${python#/c/}" ;; esac
  [ "$shell" = "$python" ] && ok "shell and Python parity $platform" || no "shell and Python parity $platform"
done

echo "workspace default tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
