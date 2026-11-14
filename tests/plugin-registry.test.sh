#!/usr/bin/env bash
# scripts/lib/plugin_registry.py: plugin root lookup and registry loading shared by the pin checks.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
. "$ROOT/scripts/lib/compat.sh"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

T=$(mktemp -d) || exit 1
trap 'rm -rf "$T"' EXIT
# Native Python on Windows cannot read an MSYS /tmp path: hand it the drive form.
native() { (cd "$1" && { pwd -W 2>/dev/null || pwd; }); }
mkdir -p "$T/fixture" "$T/e2e" "$T/ws/IndieRPGMMOAdventure/Packages" "$T/ws-empty"
FIXTURE=$(native "$T/fixture"); E2E=$(native "$T/e2e"); WS=$(native "$T/ws")
printf '{"marker": "fixture"}\n' > "$T/fixture/registry.json"
printf '{"workspace": {"root_env": "RPG_FIXTURE_WS", "root_default": "/nonexistent-fixture-ws"}}\n' > "$T/e2e/registry.json"
printf '{"dependencies": {}}\n' > "$T/ws/IndieRPGMMOAdventure/Packages/manifest.json"
printf '{"dependencies": {}}\n' > "$T/ws/IndieRPGMMOAdventure/Packages/packages-lock.json"

export RPGF_TEST_ROOT="$ROOT" RPGF_TEST_FIXTURE="$FIXTURE"
# Prints one line per probe: <name> <true|false>. The caller sets the environment.
probe() {
  python3 -B - <<'PY'
import json
import os
import sys

root = os.environ['RPGF_TEST_ROOT']
fixture = os.environ['RPGF_TEST_FIXTURE']
mode = os.environ['RPGF_TEST_MODE']
sys.path.insert(0, os.path.join(root, 'scripts', 'lib'))
import plugin_registry

def same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))

def checkout_registry():
    with open(os.path.join(root, 'registry.json'), encoding='utf-8') as f:
        return json.load(f)

if mode == 'checkout':
    print('root', str(same(plugin_registry.plugin_root(), root)).lower())
    print('registry', str(plugin_registry.load_registry() == checkout_registry()).lower())
elif mode == 'fixture':
    print('root', str(same(plugin_registry.plugin_root(), fixture)).lower())
    print('registry', str(plugin_registry.load_registry() == {'marker': 'fixture'}).lower())
elif mode == 'explicit':
    print('root', str(same(plugin_registry.plugin_root(), root)).lower())
    print('registry', str(plugin_registry.load_registry(fixture) == {'marker': 'fixture'}).lower())
PY
}
expect_probe() { # <label> <mode> [env assignments...]
  local label=$1 mode=$2 out line
  shift 2
  out=$(env "$@" RPGF_TEST_MODE="$mode" bash -c "$(declare -f probe); probe" 2>&1)
  for line in "root true" "registry true"; do
    case "$out" in
      *"$line"*) ok "$label: ${line% true}" ;;
      *) no "$label: ${line% true} (got: $(printf '%s' "$out" | tr '\n' ' '))" ;;
    esac
  done
}

expect_probe "CLAUDE_PLUGIN_ROOT unset falls back to the checkout" checkout -u CLAUDE_PLUGIN_ROOT -u PLUGIN_ROOT
expect_probe "CLAUDE_PLUGIN_ROOT empty falls back to the checkout" checkout -u PLUGIN_ROOT CLAUDE_PLUGIN_ROOT=
expect_probe "CLAUDE_PLUGIN_ROOT set wins" fixture -u PLUGIN_ROOT "CLAUDE_PLUGIN_ROOT=$FIXTURE"
expect_probe "load_registry(root) works with CLAUDE_PLUGIN_ROOT unset" explicit -u CLAUDE_PLUGIN_ROOT -u PLUGIN_ROOT
expect_probe "PLUGIN_ROOT alone is ignored" checkout -u CLAUDE_PLUGIN_ROOT "PLUGIN_ROOT=$FIXTURE"

# End to end: the pin checks read the registry through the helper and the registry's root_env variable.
# The same run with --workspace and the checkout registry must give the same exit code and output.
run_check() { # <env assignments...> -- <script> <args...>
  local envs=()
  while [ "$#" -gt 0 ] && [ "$1" != -- ]; do envs+=("$1"); shift; done
  shift
  env -u TMPDIR -u RPG_FACTORY_WORKSPACE "${envs[@]}" python3 -B "$ROOT/scripts/checks/$1" "${@:2}" 2>&1
  printf 'EXIT=%s\n' "$?"
}
compare() { # <label> <script> <args...>
  local label=$1 script=$2 routed direct
  shift 2
  routed=$(run_check "CLAUDE_PLUGIN_ROOT=$E2E" "RPG_FIXTURE_WS=$WS" -- "$script" "$@")
  direct=$(run_check -u CLAUDE_PLUGIN_ROOT -u PLUGIN_ROOT -- "$script" "$@" --workspace "$WS")
  # Strip carriage returns so Git Bash and Python line endings compare equal.
  routed=${routed//$'\r'/}; direct=${direct//$'\r'/}
  case "$direct" in
    *"Traceback"*|*"KeyError"*) no "$label: baseline run crashed: $direct"; return ;;
  esac
  [ "$routed" = "$direct" ] && ok "$label: registry-routed run matches the --workspace run" \
    || no "$label: routed run differs. routed: $routed | direct: $direct"
  case "$routed" in
    *"EXIT="[0-9]*) ok "$label: reports an exit code" ;;
    *) no "$label: no exit code captured" ;;
  esac
}
compare "pin-status.py" pin-status.py --json
compare "pin-plan.py" pin-plan.py com.cuvara.dots v1.0.0

echo "plugin registry tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
