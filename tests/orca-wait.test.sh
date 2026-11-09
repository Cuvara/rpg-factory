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
if [ "${2:-}" = worker-list ] || [ "${2:-}" = worker-read ]; then
  printf '%s\n' "$*" >> "$FAKE_DIR/workers-argv"
  if [ "${FAKE_WORKER_FAIL:-}" = yes ]; then exit 1; fi
  if [ "$2" = worker-list ]; then
    if [ "${FAKE_PAGES:-}" = yes ] && [[ " $* " == *' --cursor page2 '* ]]; then
      cat "$FAKE_DIR/worker-list-page2"
    else cat "$FAKE_DIR/worker-list"; fi
  elif [ "${FAKE_READ_FAIL:-}" = yes ] && [[ " $* " == *' --dispatch ctx-bad '* ]]; then
    exit 1
  elif [ "${FAKE_CHANGING:-}" = yes ]; then
    printf '{"ok":true,"result":{"terminal":{"tail":"%s"}}}\n' "$(cat "$FAKE_DIR/step")"
  else
    cat "$FAKE_DIR/worker-read"
  fi
  exit 0
fi
printf '%s\n' "$*" >> "$FAKE_DIR/argv"
if [[ " $* " == *' --wait '* ]]; then
  echo '{"_keepalive":true,"elapsedMs":15000}' >&2
  echo '{"_keepalive":true,"elapsedMs":30000}' >&2
fi
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
if [ "${FAKE_MODE:-sequence}" = polling ]; then
  sleep 0.05
  if [ "$n" -ge "${FAKE_DELIVER_AT:-20}" ]; then
    echo '{"ok":true,"result":{"deliveryId":"done","messages":[{"type":"worker_done"}]}}'
  else
    echo '{"ok":true,"result":{"messages":[]}}'
  fi
  exit 0
fi
case "$n" in
  1) echo '{"ok":true,"result":{"deliveryId":"hb-42","messages":[{"type":"heartbeat"}]}}' ;;
  2) echo '{"ok":true,"result":{"deliveryId":null,"messages":[],"count":0}}' ;;
  3) echo '{"ok":true,"result":{"deliveryId":null,"messages":[],"timedOut":true}}' ;;
  4) echo '{"ok":true,"result":{"deliveryId":"done-99","messages":[{"type":"worker_done","body":"complete"}]}}' ;;
  *) echo 'unexpected check' >&2; exit 9 ;;
esac
SH
chmod +x "$TMP/bin/orca"
printf '@bash "%%~dp0orca" %%*\r\n' > "$TMP/bin/orca.cmd"
echo '{"ok":true,"result":{"workers":[]}}' > "$TMP/worker-list"
export PATH="$(path_entry "$TMP/bin"):$PATH"
python3 -B - "$ROOT" <<'PY'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'lib'))
from pipeline_route import stall_reason
positive = ['\u25a0 Reconnecting... 2/5', '\u26a0 stream error: exceeded retry limit, last status: 429 Too Many Requests',
            "\u25a0 You've hit your usage limit. Try again in 2 hours.", 'You have hit your usage limit',
            'API Error: 429 {"type":"error","error":{"type":"rate_limit_error"}}',
            'Claude usage limit reached. Your limit will resets at 3pm',
            'Reconnecting\u2026', 'Reconnecting 2/5', '  \u23bf  API Error: 429 {"type":"error"}',
            '\u2022 Reconnecting... 2/5 (12s \u2022 esc to interrupt)',
            '\u25a0 stream disconnected before completion: error sending request']
negative = ["positive = ['HTTP 429', ...", '   140  if quota exceeded then',
            'grep -n "usage limit reached" log', 'Error: 429 tests passed', 'status: 429 of 512 done',
            '  Reconnecting to database...', 'run-all: 512 checks, 429 passed, 0 failed',
            'commit 4291abc feat', '\u2193 429 tokens', '  \u23bf  \u25a0 Reconnecting... 2/5',
            '| Reconnecting...', '\u2502 Reconnecting...', '\u2514 Reconnecting...', '> Reconnecting...',
            '+ Reconnecting...', '- Reconnecting...', 'Error: 429 Too Many Requests',
            "    '  \u25a0 Reconnecting... 2/5' MODEL_UNAVAILABLE: reconnecting - ...",
            "  \u2514 '| Reconnecting...' MODEL_UNAVAILABLE", '    Reconnecting... 2/5',
            'Reconnecting...\n' + '\n'.join(['working'] * 12)]
assert all(stall_reason(s) and stall_reason([s]) for s in positive)
assert all(stall_reason(s) is None and stall_reason([s]) is None for s in negative)
PY
[ "$?" -eq 0 ] && ok "stall reason recognizes provider errors without healthy text false positives" || no "stall reason cases"
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
[ ! -s "$TMP/err" ] && ok "wait keepalives on stderr do not leak into delivery or diagnostics" || no "wait keepalives leaked"
[ ! -e "$TMP/state/orca-wait/sequence.lock" ] && ok "lock removed on exit" || no "lock leaked"
[ -z "$(find "$TMP/state/orca-wait" -name '*.response*' -print)" ] && ok "response and stderr files removed on exit" || no "response files leaked"

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

echo '{"ok":true,"result":{"workers":[{"dispatchId":"ctx-test","dispatchStatus":"dispatched","projection":{"provider":{"id":"codex"}}}]}}' > "$TMP/worker-list"
export FAKE_MODE=polling
for tail in 'API Error: 429 Too Many Requests' '■ Reconnecting... 2/5'; do
  rm -f "$TMP/step" "$TMP/workers-argv"
  printf '{"ok":true,"result":{"terminal":{"tail":"%s"}}}\n' "$tail" > "$TMP/worker-read"
  PYTHONIOENCODING=cp1252 bash "$ROOT/scripts/orca-wait.sh" --run "limit-${tail%% *}" --timeout-ms 100 --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
  status=$?
  if [ "$status" -eq 5 ] && grep -q $'STALL\tctx-test\tcodex\tMODEL_UNAVAILABLE:' "$TMP/poll.out" && grep -q 'NEXT.*--down codex --reason' "$TMP/poll.out"; then
    ok "$tail reports model unavailable and exits 5"
  else no "$tail stall report"; fi
done
grep -q -- '--timeout-ms 10' "$TMP/argv" && ok "worker polling caps wait timeout" || no "wait timeout not capped"
[ -n "$(find "$TMP/state/orca-wait" -name 'limit-API*.workers.json' -print)" ] && ok "worker state persists after exit" || no "worker state missing"

rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"API Error: 429 Too Many Requests"}}}' > "$TMP/worker-read"
FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run limit-API --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && ! grep -q STALL "$TMP/poll.out" && ok "same stall reported only once" || no "same stall repeated"
rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"Reconnecting... 2/5"}}}' > "$TMP/worker-read"
bash "$ROOT/scripts/orca-wait.sh" --run limit-API --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q 'Reconnecting' "$TMP/poll.out" && ok "changed stall category reported" || no "changed stall category missed"
rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"Reconnecting... 3/5"}}}' > "$TMP/worker-read"
FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run limit-API --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && ! grep -q STALL "$TMP/poll.out" && ok "reconnect progress deduplicated" || no "reconnect repeated"

echo '{"ok":true,"result":{"workers":[{"dispatchId":"ctx-bad"}],"page":{"hasMore":true,"nextCursor":"page2"}}}' > "$TMP/worker-list"
echo '{"ok":true,"result":{"workers":[{"dispatchId":"ctx-test","projection":{"provider":{"id":"codex"}}}],"page":{"hasMore":false}}}' > "$TMP/worker-list-page2"
echo '{"ok":true,"result":{"terminal":{"tail":"Reconnecting... 2/5"}}}' > "$TMP/worker-read"
rm -f "$TMP/step" "$TMP/workers-argv"
FAKE_PAGES=yes FAKE_READ_FAIL=yes bash "$ROOT/scripts/orca-wait.sh" --run pages --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q 'ctx-test' "$TMP/poll.out" && grep -q 'WARN: worker-read ctx-bad' "$TMP/poll.err" && grep -q -- '--cursor page2' "$TMP/workers-argv" && ok "pagination and failed worker read preserve second worker stall" || no "pagination or per-worker failure"

echo '{"last_poll":"bad","workers":{"ctx-test":42}}' > "$TMP/state/orca-wait/malformed.lock.workers.json"
echo '{}' > "$TMP/state/orca-wait/expired.workers.json"
python3 -B - "$TMP/state/orca-wait/expired.workers.json" <<'PY'
import os, sys, time
old = time.time() - 8 * 86400
os.utime(sys.argv[1], (old, old))
PY
echo '{"ok":true,"result":{"workers":[{"dispatchId":"ctx-test"}]}}' > "$TMP/worker-list"
rm -f "$TMP/step"
bash "$ROOT/scripts/orca-wait.sh" --run malformed --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q STALL "$TMP/poll.out" && ! grep -q Traceback "$TMP/poll.err" && ok "malformed state recovers" || no "malformed state recovery"
[ ! -e "$TMP/state/orca-wait/expired.workers.json" ] && ok "old worker state pruned" || no "old worker state retained"

rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"working"}}}' > "$TMP/worker-read"
bash "$ROOT/scripts/orca-wait.sh" --run frozen --stall-poll-ms 10 --stall-ms 30 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q 'frozen: output unchanged' "$TMP/poll.out" && ok "unchanged worker stalls" || no "frozen worker not reported"
rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"working again"}}}' > "$TMP/worker-read"
bash "$ROOT/scripts/orca-wait.sh" --run frozen --stall-poll-ms 10 --stall-ms 30 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q 'frozen: output unchanged' "$TMP/poll.out" && ok "changed output can freeze again" || no "second freeze missed"

rm -f "$TMP/step"
FAKE_CHANGING=yes FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run changing --stall-poll-ms 10 --stall-ms 30 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && ! grep -q STALL "$TMP/poll.out" && ok "changing output does not stall" || no "changing output stalled"

echo '{"ok":true,"result":{"workers":[{"dispatchId":"ctx-test","dispatchStatus":"completed"}]}}' > "$TMP/worker-list"
rm -f "$TMP/step" "$TMP/workers-argv"
FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run completed --stall-poll-ms 10 --stall-ms 0 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && ! grep -q worker-read "$TMP/workers-argv" && ok "completed dispatch skipped" || no "completed dispatch read"

rm -f "$TMP/step"
FAKE_WORKER_FAIL=yes FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run poll-failure --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && grep -q 'WARN: worker poll:' "$TMP/poll.err" && grep -q worker_done "$TMP/poll.out" && ok "worker failure warns and preserves delivery" || no "worker failure interrupted delivery"

rm -f "$TMP/step" "$TMP/workers-argv"
FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run disabled --stall-poll-ms 0 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && [ ! -e "$TMP/workers-argv" ] && ok "disabled polling makes no worker calls" || no "disabled polling called workers"

echo "orca-wait: $((pass+fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
