#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP=$(mktemp_win) || exit 1
export RPG_FACTORY_STATE_DIR="$TMP/state" TMPDIR="$TMP" FAKE_DIR="$TMP"
waiter=
cleanup() {
  if [ -n "$waiter" ]; then kill "$waiter" 2>/dev/null || :; wait "$waiter" 2>/dev/null || :; fi
  rm -rf "$TMP"
}
trap cleanup EXIT
pass=0 fail=0
ok() { pass=$((pass+1)); echo "PASS  $1"; }
no() { fail=$((fail+1)); echo "FAIL  $1"; }
mkdir -p "$TMP/bin"
cat > "$TMP/bin/orca" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DIR/argv"
if [ "${FAKE_MODE:-sequence}" = failure ]; then
  echo 'fake orca stdout diagnostic'
  echo 'fake orca stderr diagnostic' >&2
  exit "${FAKE_EXIT:-2}"
fi
if [ "${FAKE_MODE:-sequence}" = hold ]; then
  touch "$FAKE_DIR/ready"
  while [ ! -f "$FAKE_DIR/release" ]; do sleep 0.05; done
  printf '{"ok":true,"result":{"deliveryId":"done","messages":[{"type":"status"}]}}\n'
  exit 0
fi
n=0
[ ! -f "$FAKE_DIR/step" ] || read -r n < "$FAKE_DIR/step"
n=$((n+1)); echo "$n" > "$FAKE_DIR/step"
case "$n" in
  1) echo '{"ok":true,"result":{"deliveryId":"hb-42","messages":[{"type":"heartbeat"}]}}' ;;
  2) echo '{"ok":true,"result":{"deliveryId":null,"messages":[],"count":0}}' ;;
  3) echo '{"ok":true,"result":{"deliveryId":null,"messages":[],"timedOut":true}}' ;;
  4) echo '{"ok":true,"result":{"deliveryId":"done-99","messages":[{"type":"worker_done","body":"complete"}]}}' ;;
  *) echo 'unexpected check' >&2; exit 9 ;;
esac
SH
chmod +x "$TMP/bin/orca"
export PATH="$(path_entry "$TMP/bin"):$PATH"
bash "$ROOT/scripts/orca-wait.sh" --run sequence --timeout-ms 25 --types worker_done,status > "$TMP/out" 2> "$TMP/err"
status=$?
[ "$status" -eq 0 ] && ok "heartbeat, timeout, real delivery exits 0" || no "sequence exits 0"
grep -q -- '--ack hb-42' "$TMP/argv" && ok "heartbeat delivery acknowledged" || no "heartbeat ack missing"
! grep -q -- '--ack done-99' "$TMP/argv" && ok "real delivery left unacknowledged" || no "real delivery acked"
[ "$(wc -l < "$TMP/argv")" -eq 4 ] && ok "ack response processed and timeout continued" || no "incorrect check count"
grep -q -- '--wait --types worker_done,status --timeout-ms 25' "$TMP/argv" && ok "wait options forwarded" || no "wait options missing"
python3 -B - "$TMP/out" <<'PY'
import json, sys
o = json.load(open(sys.argv[1]))
assert o['result']['deliveryId'] == 'done-99'
PY
[ "$?" -eq 0 ] && ok "only real JSON printed" || no "real JSON output incorrect"
[ ! -e "$TMP/state/orca-wait/sequence.lock" ] && ok "lock removed on exit" || no "lock leaked"

export FAKE_MODE=hold
bash "$ROOT/scripts/orca-wait.sh" --run held > "$TMP/held.out" 2> "$TMP/held.err" &
waiter=$!
for ((i=0; i<200; i++)); do [ ! -f "$TMP/ready" ] || break; sleep 0.05; done
bash "$ROOT/scripts/orca-wait.sh" --run held > "$TMP/second.out" 2>&1
status=$?
[ "$status" -eq 3 ] && grep -q "pid $waiter" "$TMP/second.out" && ok "second waiter refused with holder pid" || no "second waiter not refused"
kill -TERM "$waiter"
wait "$waiter"; status=$?; waiter=
[ "$status" -eq 143 ] && [ ! -e "$TMP/state/orca-wait/held.lock" ] && ok "TERM removes lock and stops wait" || no "TERM cleanup failed"
# Release any descendants of the fake CLI on shells without process-group kill.
touch "$TMP/release"
unset FAKE_MODE

# Use a positively dead Bash child pid, rather than assuming an arbitrary pid is absent.
sleep 0 & dead=$!; wait "$dead"
printf '%s\n' "$dead" > "$TMP/state/orca-wait/stale.lock"
rm -f "$TMP/step"
bash "$ROOT/scripts/orca-wait.sh" --run stale > "$TMP/stale.out" 2> "$TMP/stale.err"
status=$?
[ "$status" -eq 0 ] && [ ! -e "$TMP/state/orca-wait/stale.lock" ] && ok "dead holder taken over and cleaned" || no "stale takeover failed"

# CLI failures must not collide with the waiter's own usage and lock codes.
for orca_code in 2 3 9; do
  FAKE_MODE=failure FAKE_EXIT="$orca_code" bash "$ROOT/scripts/orca-wait.sh" --run failure > "$TMP/failure.out" 2> "$TMP/failure.err"
  status=$?
  if [ "$status" -eq 4 ] && grep -q "orca check exited $orca_code" "$TMP/failure.err" \
    && grep -q 'fake orca stdout diagnostic' "$TMP/failure.err" \
    && grep -q 'fake orca stderr diagnostic' "$TMP/failure.err" \
    && [ ! -e "$TMP/state/orca-wait/failure.lock" ]; then
    ok "orca failure $orca_code exits 4 with diagnostics and cleans lock"
  else no "orca failure $orca_code not diagnosed or cleaned"; fi
done

# An empty PATH proves absence even on hosts with Orca installed.
mkdir -p "$TMP/empty"
bash_bin=$(command -v bash)
PATH="$(path_entry "$TMP/empty")" "$bash_bin" "$ROOT/scripts/orca-wait.sh" --run missing > "$TMP/missing.out" 2>&1
status=$?
[ "$status" -eq 2 ] && grep -q 'NOT_AVAILABLE' "$TMP/missing.out" && ok "missing orca exits 2 with NOT_AVAILABLE" || no "missing orca not diagnosed"

echo "orca-wait: $((pass+fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
