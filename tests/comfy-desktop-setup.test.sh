#!/usr/bin/env bash
# scripts/comfy-desktop-setup.py (Comfy Desktop + 9router node + comfy-mcp setup) and the vendored 9router node
# (templates/assetgen/comfy-node/): the node's signature equals scripts/assetgen/data/known-nodes.json and it reads its
# gateway and credential only from the Codex provider config at run time (stub numpy/torch/PIL, loopback fake gateway);
# the script against a temp fake Comfy Desktop data dir, a fake ComfyUI on a loopback port and fake claude/codex CLIs:
# --check writes nothing (exit 1 on a missing provider, 3 on gaps), cloud-only is ACTION, --apply copies the node, registers
# both CLIs with the port read from comfy-procs/port-locks, is idempotent, replaces a registration on a changed port, a
# not-yet-loaded node is ACTION (restart), --generate-test posts the low-quality graph with the template's model, and
# no output ever carries the key. No network, no real ComfyUI, no real CLI.
# Usage: tests/comfy-desktop-setup.test.sh   (standalone; own temp dir)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1
SRV=""; trap '[ -n "$SRV" ] && kill "$SRV" 2>/dev/null; rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | head -20 | sed 's/^/      /'; return 0; }
PY="$(python3 -c 'import sys; print(sys.executable.replace(chr(92), "/"))')"
FX="$ROOT/tests/fixtures/comfy-desktop-setup"
SETUP="$ROOT/scripts/comfy-desktop-setup.py"
KEY="test-placeholder-not-a-key"

echo "-- vendored node"
python3 -B "$FX/node-check.py" "$ROOT" "$TMP" > "$TMP/node.out" 2>&1
while IFS= read -r l; do
  case "$l" in "ok "*) ok "node: ${l#ok }" ;; *) no "node: ${l#not ok }" "$(cat "$TMP/node.out")" ;; esac
done < "$TMP/node.out"
[ "$(grep -c '^ok ' "$TMP/node.out")" -eq 9 ] && ok "node: all 9 checks ran" || no "node: expected 9 ok lines" "$(cat "$TMP/node.out")"

echo "-- fake Desktop data dir, ComfyUI and CLIs"
D="$TMP/desktop"; INST="$TMP/installs/9router"; CN="$INST/ComfyUI/custom_nodes"
mkdir -p "$D/comfy-procs" "$D/port-locks" "$CN"
printf 'nonode' > "$TMP/mode"; : > "$TMP/http.log"
python3 -B "$FX/fake-comfy.py" "$TMP/port" "$TMP/mode" "$TMP/http.log" & SRV=$!
for _ in $(seq 1 50); do [ -s "$TMP/port" ] && break; sleep 0.1; done
PORT="$(cat "$TMP/port")"
cloud='{"id":"inst-cloud","name":"Comfy Cloud","sourceId":"cloud","remoteUrl":"x"}'
loc="{\"id\":\"inst-1\",\"name\":\"9router\",\"sourceId\":\"standalone\",\"installPath\":\"$INST\",\"status\":\"installed\"}"
printf '[%s]' "$cloud" > "$D/installations.json"
GOOD="$TMP/codex.toml"; BAD="$TMP/codex-bad.toml"
printf '[model_providers.9router]\nbase_url = "gw-placeholder"\nhttp_headers = { Authorization = "%s" }\n' "$KEY" > "$GOOD"
printf '[model_providers.other]\nname = "x"\n' > "$BAD"
export FAKE_CLI_LOG="$TMP/cli.log" FAKE_CLI_STATE_CLAUDE="$TMP/st-claude.json" FAKE_CLI_STATE_CODEX="$TMP/st-codex.json"
export COMFY_SETUP_CLAUDE_CMD="'$PY' '$FX/fake-cli.py' claude" COMFY_SETUP_CODEX_CMD="'$PY' '$FX/fake-cli.py' codex"
: > "$FAKE_CLI_LOG"
VENV="$TMP/venv"; mkdir -p "$VENV/Scripts" "$VENV/bin"; : > "$VENV/Scripts/comfy-mcp.exe"; : > "$VENV/bin/comfy-mcp"
S() { python3 -B "$SETUP" --desktop-dir "$D" --venv "$VENV" --codex-config "$GOOD" "$@"; }
snap() { find "$TMP/installs" "$VENV" "$D" -type f -exec sha256sum {} + 2>/dev/null | sort; }

S --check --json > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 3 ] && jq -e '.steps[] | select(.step=="instance" and .state=="ACTION" and (.detail | test("Comfy Cloud")))' "$TMP/o" >/dev/null \
  && ok "only Comfy Cloud: instance ACTION (New Instance), exit 3" || no "cloud only rc=$rc" "$(cat "$TMP/o")"

printf '[%s,%s]' "$cloud" "$loc" > "$D/installations.json"
printf '{"installationId":"inst-1","port":%s}' "$PORT" > "$D/comfy-procs/inst-1.json"
s0=$(snap)
S --check --codex-config "$BAD" --json > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && jq -e '.steps[] | select(.step=="provider" and .state=="FAIL" and (.hint | test("model_providers.9router")))' "$TMP/o" >/dev/null \
  && ok "no provider section: FAIL (exit 1) naming what to add" || no "bad provider rc=$rc" "$(cat "$TMP/o")"
S --check > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 3 ] && grep -q "^node  *MISSING" "$TMP/o" && grep -q "^port  *OK  *$PORT" "$TMP/o" && grep -q "^node-live  *ACTION" "$TMP/o" \
  && grep -q "^mcp-claude  *MISSING" "$TMP/o" && grep -q "^mcp-codex  *MISSING" "$TMP/o" \
  && ok "--check: node and registrations MISSING, port read from comfy-procs, node not live ACTION, exit 3" || no "check rc=$rc" "$(cat "$TMP/o")"
[ "$(snap)" = "$s0" ] && ok "--check changed nothing (no files, no CLI call but get)" || no "--check wrote" "$(diff <(echo "$s0") <(snap))"
if grep -qv "mcp get" "$FAKE_CLI_LOG"; then no "--check called a CLI other than mcp get" "$(cat "$FAKE_CLI_LOG")"; else ok "--check only ran mcp get"; fi
S --generate-test > "$TMP/o" 2>&1; [ $? -eq 2 ] && ok "--generate-test without --apply is a usage error (exit 2)" || no "generate-test usage" "$(cat "$TMP/o")"

S --apply --json > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 3 ] && jq -e '[.steps[] | select(.step=="node-live" and .state=="ACTION" and (.hint | test("Stop, then Launch")))] | length == 1' "$TMP/o" >/dev/null \
  && cmp -s <(tr -d '\r' < "$ROOT/templates/assetgen/comfy-node/comfyui_9router/__init__.py") <(tr -d '\r' < "$CN/comfyui_9router/__init__.py") \
  && ok "--apply: node copied identical to the vendored copy; node not loaded yet is ACTION (Stop + Launch), exit 3" || no "apply rc=$rc" "$(cat "$TMP/o")"
grep -q "^claude mcp add comfy-mcp --scope user -e COMFY_LOCAL_URL=http://127.0.0.1:$PORT -- " "$FAKE_CLI_LOG" \
  && grep -q "^codex mcp add comfy-mcp --env COMFY_LOCAL_URL=http://127.0.0.1:$PORT -- " "$FAKE_CLI_LOG" \
  && ok "--apply registered comfy-mcp for Claude (user scope) and Codex with the running port" || no "registration" "$(cat "$FAKE_CLI_LOG")"

printf 'node' > "$TMP/mode"
S --apply > "$TMP/o" 2>&1; rc=$?; n_add=$(grep -c "mcp add" "$FAKE_CLI_LOG")
[ $rc -eq 0 ] && tail -1 "$TMP/o" | grep -q READY && [ "$n_add" -eq 2 ] && ok "second --apply with the node loaded: READY (exit 0), nothing added again (idempotent)" || no "idempotent rc=$rc adds=$n_add" "$(cat "$TMP/o")"
S --check > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "--check on a finished setup: exit 0" || no "check after apply rc=$rc" "$(cat "$TMP/o")"

echo "-- port change, port-locks fallback, outdated node"
rm "$D/comfy-procs/inst-1.json"
printf '{"pid":1,"installationName":"9router"}' > "$D/port-locks/port-$PORT.json"
echo '{"url":"http://127.0.0.1:1","exe":"x"}' > "$FAKE_CLI_STATE_CLAUDE"
echo "stale" >> "$CN/comfyui_9router/__init__.py"
S --check > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 3 ] && grep -q "^port  *OK  *$PORT" "$TMP/o" && grep -q "^node  *OUTDATED" "$TMP/o" && grep -q "^mcp-claude  *OUTDATED" "$TMP/o" \
  && ok "port found through port-locks; changed node OUTDATED; stale registration port OUTDATED" || no "port-locks rc=$rc" "$(cat "$TMP/o")"
: > "$FAKE_CLI_LOG"; S --apply > "$TMP/o" 2>&1; rc=$?
grep -q "^claude mcp remove comfy-mcp --scope user" "$FAKE_CLI_LOG" && grep -q "^claude mcp add .*COMFY_LOCAL_URL=http://127.0.0.1:$PORT" "$FAKE_CLI_LOG" \
  && ! grep -q "^codex mcp remove" "$FAKE_CLI_LOG" && [ $rc -eq 0 ] \
  && ok "a changed port is remove + add for that CLI only; the outdated node is replaced" || no "re-register rc=$rc" "$(cat "$FAKE_CLI_LOG" "$TMP/o")"

echo "-- --generate-test and credentials"
: > "$TMP/http.log"; S --apply --generate-test --json > "$TMP/o" 2>&1; rc=$?
model=$(jq -r .params.model.default "$ROOT/templates/assetgen/workflows/image-generate.json")
[ $rc -eq 0 ] && jq -e '.steps[] | select(.step=="generate" and .state=="OK" and (.detail | test("8x6")))' "$TMP/o" >/dev/null \
  && jq -e -s --arg m "$model" '[.[] | select(.method=="POST" and .path=="/prompt")] | length == 1 and ((.[0].body.prompt | [.[]] | map(.class_type) | sort) == ["NineRouterImage","PrimitiveStringMultiline","SaveImage"])
       and ((.[0].body.prompt | [.[]] | map(select(.class_type=="NineRouterImage"))[0].inputs) | .quality == "low" and .model == $m)' "$TMP/http.log" >/dev/null \
  && ok "--generate-test: one POST /prompt (Primitive -> NineRouterImage low quality, the template's model -> SaveImage), result size read from the PNG" || no "generate rc=$rc" "$(cat "$TMP/o" "$TMP/http.log")"
if grep -rq "$KEY" "$TMP/o" "$TMP/http.log" "$FAKE_CLI_LOG" "$CN" "$D" 2>/dev/null; then no "the credential value leaked into output, requests, CLI calls or the instance"; else ok "the credential value appears in no output, request, CLI call or written file"; fi
[ "$(grep -c "$KEY" "$GOOD")" -eq 1 ] && ok "the provider config was left untouched" || no "provider config changed"

echo "-- venv apply fails cleanly offline"
rm -rf "$TMP/venv2"
PIP_INDEX_URL="http://127.0.0.1:9/simple" PIP_RETRIES=0 PIP_TIMEOUT=3 python3 -B "$SETUP" --desktop-dir "$D" --venv "$TMP/venv2" --codex-config "$GOOD" --targets none --apply > "$TMP/o" 2>&1; rc=$?
[ $rc -eq 1 ] && grep -q "^venv  *FAIL  *pip install comfy-mcp failed" "$TMP/o" && ok "venv created, pip install failure is FAIL (exit 1), no traceback" || no "venv offline rc=$rc" "$(cat "$TMP/o")"

echo "comfy-desktop-setup: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
