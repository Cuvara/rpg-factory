#!/usr/bin/env bash
# A repo entry without a remote (absent or null, e.g. the optional authoring repo) must not crash
# factory-status (/rpg-factory:status) or degrade the git guard.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp_win)" || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
mkdir -p "$TMP/plugin"
jq '.repos |= with_entries(.value.remote = null)' "$ROOT/registry.json" > "$TMP/plugin/registry.json"
export RPG_FACTORY_STATE_DIR="$TMP/state"
out=$(CLAUDE_PLUGIN_ROOT="$TMP/plugin" python3 -B "$ROOT/scripts/factory-status.py" 2>&1); rc=$?
[ "$rc" -eq 0 ] && ! grep -q Traceback <<<"$out" && ok "factory-status with remote null" || { no "factory-status with remote null (rc=$rc)"; grep -m3 -E 'Error|Traceback' <<<"$out"; }
payload='{"tool_name":"Bash","tool_input":{"command":"gh release create v9.9.9 --repo Cuvara/rpg-factory"},"session_id":"t"}'
out=$(CLAUDE_PLUGIN_ROOT="$TMP/plugin" python3 -B "$ROOT/scripts/git-guard.py" <<<"$payload" 2>&1); rc=$?
[ "$rc" -eq 0 ] && ! grep -q Traceback <<<"$out" && grep -q 'advisory (high)' <<<"$out" && ok "git-guard keeps its release advisory with remote null" \
  || { no "git-guard with remote null (rc=$rc)"; head -3 <<<"$out"; }
echo "registry-nulls: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
