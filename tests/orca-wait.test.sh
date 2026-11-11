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
  for ((k=0; k<20; k++)); do echo '{"_keepalive":true,"elapsedMs":45000}' >&2; done
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
if [ "${FAKE_MODE:-sequence}" = script ]; then
  line=$(sed -n "${n}p" "$FAKE_DIR/script")
  [ -n "$line" ] || { echo 'script: unexpected check' >&2; exit 9; }
  printf '%s\n' "$line"
  exit 0
fi
# Orca 1.4.250: --types is only the wake condition, a delivery is the whole FIFO batch with no deliveryId and is handled.
if [ "${FAKE_MODE:-sequence}" = inbox ]; then
  [ "$n" -ne "${FAKE_ARRIVE_AT:-0}" ] || echo "${FAKE_ARRIVE_TYPE:-status}" >> "$FAKE_DIR/inbox"
  [ "$n" -le "${FAKE_INBOX_MAX:-20}" ] || { echo 'inbox: too many checks' >&2; exit 9; }
  wake= prev=
  for a in "$@"; do [ "$prev" != --types ] || wake=$a; prev=$a; done
  woken=no batch=
  while read -r t; do
    case ",$wake," in *,"$t",*) woken=yes ;; esac
    batch+="${batch:+,}{\"type\":\"$t\"}"
  done < "$FAKE_DIR/inbox"
  if [ "$woken" = yes ]; then
    : > "$FAKE_DIR/inbox"
    printf '{"ok":true,"result":{"messages":[%s]}}\n' "$batch"
  else
    echo '{"ok":true,"result":{"messages":[],"timedOut":true}}'
  fi
  exit 0
fi
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
            'Reconnecting\u2026', 'Reconnecting 2/5', '  \u23bf \u00a0API Error: 429 {"type":"error"}',
            '  \u23bf \u00a0Claude usage limit reached. resets 3pm',
            '  \u23bf  API Error: 429 {"type":"error"}',
            '\u00a0 \u23bf \u00a0API Error: 429 {"type":"error"}',
            '\u00a0 \u25a0 Reconnecting... 2/5',
            '\u2022 Reconnecting... 2/5 (12s \u2022 esc to interrupt)',
            '\u25a0 stream disconnected before completion: error sending request',
            '[codex/gpt-6.1-terra] [401]: Unauthorized', '  \u23bf  API Error: 500 {"type":"api_error"}',
            '\u25a0 unexpected status 401 Unauthorized: invalid token']
gateway = {'\u25a0 unexpected status 503 Service Unavailable: [codex/gpt-6.1-terra] [429]: The usage limit has been reached': 'usage limit (429)',
           '[codex/gpt-6.1-terra] [429]: The usage limit has been reached': 'usage limit (429)',
           '\u25a0 unexpected status 503 Service Unavailable: [codex/gpt-6.1-terra] [400]: bad model model_not_found': 'model not found',
           '[400] The requested model does not exist: model_not_found': 'model not found',
           '[codex/gpt-6.1-terra] [503]: upstream down': 'gateway error (503)',
           '\u26a0 stream error: unexpected status 502 Bad Gateway: upstream': 'gateway error (502)',
           'API Error: 401 {"type":"authentication_error"}': 'gateway error (401)'}
for text, detail in gateway.items():
    assert stall_reason(text).startswith('MODEL_UNAVAILABLE: ' + detail + ' - '), text
negative = ['run-all: 503 checks, 401 passed, 0 failed', 'Error: 503 tests passed', 'status: 503 of 512 done',
            'unexpected status 200 OK: fine', 'unexpected status 404 Not Found: x', 'unexpected status 503 in test fixture: x',
            '  [codex/review] notes', 'grep -n "[codex/x] [429]: limit" log', '| [codex/x] [429]: The usage limit',
            '- [400] model_not_found', 'assert "[400] model_not_found" in out', '[400] bad request', '[codex/gpt] [200]: ok',
            '    [codex/gpt] [429]: The usage limit has been reached', '[429]: retry budget left', '[500] tests passed',
            '[codex/gpt] [400]: invalid request', 'Tests: 401 of 500 API Error: 500 cases',
"positive = ['HTTP 429', ...", '   140  if quota exceeded then',
            'grep -n "usage limit reached" log', 'Error: 429 tests passed', 'status: 429 of 512 done',
            '  Reconnecting to database...', 'run-all: 512 checks, 429 passed, 0 failed',
            'commit 4291abc feat', '\u2193 429 tokens', '  \u23bf  \u25a0 Reconnecting... 2/5',
            '| Reconnecting...', '\u2502 Reconnecting...', '\u2514 Reconnecting...', '> Reconnecting...',
            '+ Reconnecting...', '- Reconnecting...', 'Error: 429 Too Many Requests',
            "    '  \u25a0 Reconnecting... 2/5' MODEL_UNAVAILABLE: reconnecting - ...",
            "  \u2514 '| Reconnecting...' MODEL_UNAVAILABLE", '    Reconnecting... 2/5',
            '\u00a0    \u23bf \u00a0API Error: 429', '\u00a0  \u25a0 Reconnecting... 2/5',
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
grep -q -- '--wait --types worker_done,status,heartbeat --timeout-ms 25' "$TMP/argv" && ok "wait options forwarded, heartbeats wake" || no "wait options missing"
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
[ "$status" -eq 3 ] && grep -q "pid $waiter" "$TMP/second.out" && ! grep -q 'parent gone' "$TMP/second.out" && ok "second waiter refused with holder pid" || no "second waiter not refused"
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
    && ! grep -q _keepalive "$TMP/failure.err" \
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

# plugin-flow-4's lost reports: task leads send --type status, a waiter that does not wake on it times out forever.
echo status > "$TMP/inbox"; rm -f "$TMP/step" "$TMP/argv"
FAKE_MODE=inbox bash "$ROOT/scripts/orca-wait.sh" --run status-wake --timeout-ms 25 --stall-poll-ms 0 > "$TMP/inbox.out" 2> "$TMP/inbox.err"
status=$?
[ "$status" -eq 0 ] && grep -q '"status"' "$TMP/inbox.out" && grep -q -- '--types worker_done,escalation,question,status,heartbeat ' "$TMP/argv" \
  && ok "a status message wakes the default waiter" || no "default waiter missed a status message"
echo status > "$TMP/inbox"; rm -f "$TMP/step"
FAKE_MODE=inbox FAKE_INBOX_MAX=3 bash "$ROOT/scripts/orca-wait.sh" --run status-filtered --types worker_done --timeout-ms 25 --stall-poll-ms 0 > "$TMP/inbox.out" 2> "$TMP/inbox.err"
status=$?
[ "$status" -eq 4 ] && [ ! -s "$TMP/inbox.out" ] && ok "control: a waiter filter without status does not wake on it" || no "fake inbox ignores the wake types"

printf 'heartbeat\nheartbeat\n' > "$TMP/inbox"; rm -f "$TMP/step"
FAKE_MODE=inbox FAKE_ARRIVE_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run hb-drain --timeout-ms 25 --stall-poll-ms 0 > "$TMP/inbox.out" 2> "$TMP/inbox.err"
status=$?
[ "$status" -eq 0 ] && grep -q '"status"' "$TMP/inbox.out" && ! grep -q heartbeat "$TMP/inbox.out" \
  && ok "heartbeats are consumed across waits, not piled onto the next delivery" || no "heartbeats piled up"

# Heartbeat-only batches: Orca 1.4.250 sends no deliveryId and has already handled them; an older Orca is acked.
cat > "$TMP/script" <<'JSON'
{"ok":true,"result":{"messages":[{"type":"heartbeat"}]}}
{"ok":true,"result":{"deliveryId":null,"messages":[{"type":"heartbeat"}]}}
{"ok":true,"result":{"deliveryId":"hb-7","messages":[{"type":"heartbeat"}]}}
{"ok":true,"result":{"deliveryId":null,"messages":[],"count":0}}
{"ok":true,"result":{"messages":[{"type":"status","body":"task done"}]}}
JSON
rm -f "$TMP/step" "$TMP/argv"
FAKE_MODE=script bash "$ROOT/scripts/orca-wait.sh" --run hb-noid --timeout-ms 25 --stall-poll-ms 0 > "$TMP/hb.out" 2> "$TMP/hb.err"
status=$?
[ "$status" -eq 0 ] && grep -q 'task done' "$TMP/hb.out" && [ "$(wc -l < "$TMP/argv")" -eq 5 ] && [ "$(grep -c -- '--ack' "$TMP/argv")" -eq 1 ] && grep -q -- '--ack hb-7' "$TMP/argv" \
  && ok "heartbeat batch without deliveryId keeps waiting, one with it is acked" || no "heartbeat batch handling"

echo '{"ok":true,"result":{"deliveryId":7,"messages":[{"type":"heartbeat"}]}}' > "$TMP/script"; rm -f "$TMP/step"
FAKE_MODE=script bash "$ROOT/scripts/orca-wait.sh" --run hb-bad --timeout-ms 25 --stall-poll-ms 0 > "$TMP/hb.out" 2> "$TMP/hb.err"
status=$?
[ "$status" -eq 2 ] && grep -q 'invalid deliveryId' "$TMP/hb.err" && ok "malformed deliveryId exits 2" || no "malformed deliveryId accepted"

# A batch mixing heartbeats with a real message is a real delivery, with or without a deliveryId, and is never acked.
echo '{"ok":true,"result":{"messages":[{"type":"heartbeat"},{"type":"status","body":"mixed"},{"type":"heartbeat"}]}}' > "$TMP/script"; rm -f "$TMP/step" "$TMP/argv"
FAKE_MODE=script bash "$ROOT/scripts/orca-wait.sh" --run mixed --timeout-ms 25 --stall-poll-ms 0 > "$TMP/hb.out" 2> "$TMP/hb.err"
status=$?
[ "$status" -eq 0 ] && grep -q mixed "$TMP/hb.out" && [ "$(wc -l < "$TMP/argv")" -eq 1 ] && ok "mixed batch without deliveryId delivered" || no "mixed batch without deliveryId"
echo '{"ok":true,"result":{"deliveryId":"mix-7","messages":[{"type":"heartbeat"},{"type":"worker_done"}]}}' > "$TMP/script"; rm -f "$TMP/step" "$TMP/argv"
FAKE_MODE=script bash "$ROOT/scripts/orca-wait.sh" --run mixed --timeout-ms 25 --stall-poll-ms 0 > "$TMP/hb.out" 2> "$TMP/hb.err"
status=$?
[ "$status" -eq 0 ] && grep -q mix-7 "$TMP/hb.out" && ! grep -q -- '--ack' "$TMP/argv" && ok "mixed batch with deliveryId left unacknowledged" || no "mixed batch acked"

# set -m: a plain background job starts with SIGINT ignored, which bash cannot trap.
rm -f "$TMP/ready" "$TMP/release"
export FAKE_MODE=hold
set -m
bash "$ROOT/scripts/orca-wait.sh" --run interrupted > "$TMP/int.out" 2> "$TMP/int.err" &
waiter=$!
set +m
for ((i=0; i<200; i++)); do [ ! -f "$TMP/ready" ] || break; sleep 0.05; done
kill -INT "$waiter"
wait "$waiter"; status=$?; waiter=
[ "$status" -eq 130 ] && [ ! -e "$TMP/state/orca-wait/interrupted.lock" ] && [ ! -s "$TMP/int.out" ] && ok "INT exits 130 and releases the lock" || no "INT cleanup failed (status $status)"
touch "$TMP/release"
unset FAKE_MODE

# The parent is killed outright, as when Claude Code reaps the waiter's shell.
rm -f "$TMP/step" "$TMP/orphan.pid"
FAKE_MODE=polling FAKE_DELIVER_AT=100000 bash -c 'bash "$1" --run orphan --timeout-ms 50 --stall-poll-ms 0 > "$2" 2> "$3" & echo $! > "$4"; wait' _ \
  "$ROOT/scripts/orca-wait.sh" "$TMP/orphan.out" "$TMP/orphan.err" "$TMP/orphan.pid" &
orphan_parent=$!
for ((i=0; i<200; i++)); do [ ! -s "$TMP/state/orca-wait/orphan.lock" ] || break; sleep 0.05; done
waiter=$(cat "$TMP/orphan.pid" 2>/dev/null)
read -r lock_pid lock_parent < "$TMP/state/orca-wait/orphan.lock"
[ "$lock_pid" = "$waiter" ] && [ "$lock_parent" = "$orphan_parent" ] && ok "lock records the holder and its parent" || no "lock content: $lock_pid $lock_parent"
kill -KILL "$orphan_parent"
wait "$orphan_parent" 2>/dev/null
for ((i=0; i<300; i++)); do kill -0 "$waiter" 2>/dev/null || break; sleep 0.05; done
if ! kill -0 "$waiter" 2>/dev/null && [ ! -e "$TMP/state/orca-wait/orphan.lock" ] && grep -q "parent pid $orphan_parent is gone; exiting 6" "$TMP/orphan.err"; then
  ok "a waiter whose parent died exits 6 and releases the lock"
  waiter=
else no "orphaned waiter kept running or kept its lock"; fi

# An orphan blocked in check --wait that then gets a real delivery: stdout is a dead pipe and Orca already marked the batch
# handled, so the delivery is saved next to the lock and named on stderr (exit 6).
rm -f "$TMP/ready" "$TMP/release" "$TMP/orphan.pid"
FAKE_MODE=hold bash -c 'bash "$1" --run orphan-real --timeout-ms 60000 --stall-poll-ms 0 > "$2" 2> "$3" & echo $! > "$4"; wait' _ \
  "$ROOT/scripts/orca-wait.sh" "$TMP/orphan-real.out" "$TMP/orphan-real.err" "$TMP/orphan-real.pid" &
orphan_parent=$!
for ((i=0; i<200; i++)); do [ ! -f "$TMP/ready" ] || break; sleep 0.05; done
waiter=$(cat "$TMP/orphan-real.pid" 2>/dev/null)
kill -KILL "$orphan_parent"
wait "$orphan_parent" 2>/dev/null
touch "$TMP/release"
for ((i=0; i<300; i++)); do kill -0 "$waiter" 2>/dev/null || break; sleep 0.05; done
saved=$(ls "$TMP/state/orca-wait/"orphan-real.lock.orphan.*.json 2>/dev/null | head -n 1)
if ! kill -0 "$waiter" 2>/dev/null && [ ! -e "$TMP/state/orca-wait/orphan-real.lock" ] && [ -n "$saved" ] \
  && grep -q '"deliveryId":"done"' "$saved" && grep -q "delivery for run orphan-real saved to .*orphan-real.lock.orphan" "$TMP/orphan-real.err" \
  && grep -q 'exiting 6' "$TMP/orphan-real.err" && [ ! -s "$TMP/orphan-real.out" ]; then
  ok "an orphan that receives a real delivery saves it under the state dir and exits 6"
  waiter=
else no "orphan delivery not saved (saved: ${saved:-none}; stderr: $(tr '\n' ' ' < "$TMP/orphan-real.err" 2>/dev/null))"; fi
rm -f "$TMP/ready" "$TMP/release"

sleep 120 & live=$!
sleep 0 & dead=$!; wait "$dead"
printf '%s %s\n' "$live" "$dead" > "$TMP/state/orca-wait/orphaned.lock"
bash "$ROOT/scripts/orca-wait.sh" --run orphaned > "$TMP/orphaned.out" 2>&1
status=$?
if [ "$status" -eq 3 ] && grep -q "pid $live" "$TMP/orphaned.out" && grep -q 'parent gone' "$TMP/orphaned.out" \
  && kill -0 "$live" 2>/dev/null && [ "$(cat "$TMP/state/orca-wait/orphaned.lock")" = "$live $dead" ]; then
  ok "next waiter names the orphan holder and never kills it"
else no "orphan holder not named or was killed"; fi

# A stale guard: the acquirer was SIGKILLed after recording its pid, or before it could.
age_path() { python3 -B -c 'import os, sys, time; t = time.time() - 3600; os.utime(sys.argv[1], (t, t))' "$1"; }
for owner in "$dead" ''; do
  g="$TMP/state/orca-wait/guard-stale.lock.acquire"
  mkdir "$g"
  [ -z "$owner" ] || echo "$owner" > "$g/owner"
  age_path "$g"
  rm -f "$TMP/step"
  bash "$ROOT/scripts/orca-wait.sh" --run guard-stale --timeout-ms 25 --stall-poll-ms 0 > "$TMP/guard.out" 2> "$TMP/guard.err"
  status=$?
  [ "$status" -eq 0 ] && [ ! -e "$g" ] && [ ! -e "$g.reclaim" ] && grep -q 'reclaimed stale acquisition guard' "$TMP/guard.err" \
    && ok "stale guard reclaimed by age (owner '${owner:+dead}')" || no "stale guard not reclaimed (status $status)"
done

# Never reclaimed: an old guard whose recorded owner is alive, and a young guard with no owner yet.
live_guard="$TMP/state/orca-wait/guard-live.lock.acquire"
young_guard="$TMP/state/orca-wait/guard-young.lock.acquire"
mkdir "$live_guard" "$young_guard"
echo "$live" > "$live_guard/owner"
age_path "$live_guard"
bash "$ROOT/scripts/orca-wait.sh" --run guard-live > "$TMP/guard-live.out" 2>&1 & first=$!
bash "$ROOT/scripts/orca-wait.sh" --run guard-young > "$TMP/guard-young.out" 2>&1 & second=$!
wait "$first"; live_status=$?
wait "$second"; young_status=$?
if [ "$live_status" -eq 3 ] && grep -q 'acquisition busy' "$TMP/guard-live.out" && grep -q "owner pid $live" "$TMP/guard-live.out" \
  && [ "$(cat "$live_guard/owner")" = "$live" ]; then
  ok "an old guard with a live owner is never reclaimed"
else no "live guard reclaimed (status $live_status)"; fi
[ "$young_status" -eq 3 ] && [ -d "$young_guard" ] && ok "a young guard with no owner is not reclaimed" || no "young guard reclaimed (status $young_status)"
kill "$live" 2>/dev/null; wait "$live" 2>/dev/null

echo '{"ok":true,"result":{"workers":[{"dispatchId":"ctx-test","dispatchStatus":"dispatched","projection":{"provider":{"id":"codex"}}}]}}' > "$TMP/worker-list"
export FAKE_MODE=polling
for tail in 'API Error: 429 Too Many Requests' '■ Reconnecting... 2/5'; do
  rm -f "$TMP/step" "$TMP/workers-argv"
  printf '{"ok":true,"result":{"terminal":{"tail":"%s"}}}\n' "$tail" > "$TMP/worker-read"
  PYTHONIOENCODING=cp1252 bash "$ROOT/scripts/orca-wait.sh" --run "limit-${tail%% *}" --timeout-ms 100 --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
  status=$?
  if [ "$status" -eq 5 ] && grep -q $'STALL\tctx-test\tcodex\tMODEL_UNAVAILABLE:' "$TMP/poll.out" && grep -q 'NEXT.*python3 -B scripts/factory-pipeline.py agents <plan> --down codex --reason' "$TMP/poll.out"; then
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

# A gateway 503 body has its own reason: reported once, and not confused with reconnecting or the usage limit.
rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"unexpected status 503 Service Unavailable: [codex/gpt] [400]: no such model_not_found"}}}' > "$TMP/worker-read"
bash "$ROOT/scripts/orca-wait.sh" --run gateway --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q $'STALL\tctx-test\tcodex\tMODEL_UNAVAILABLE: model not found' "$TMP/poll.out" && grep -q -- '--down codex --reason .*model not found' "$TMP/poll.out" \
  && ok "gateway model_not_found reported as model not found" || no "gateway model_not_found report"
rm -f "$TMP/step"
FAKE_DELIVER_AT=2 bash "$ROOT/scripts/orca-wait.sh" --run gateway --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 0 ] && ! grep -q STALL "$TMP/poll.out" && ok "gateway reason reported once" || no "gateway reason repeated"
rm -f "$TMP/step"
echo '{"ok":true,"result":{"terminal":{"tail":"[codex/gpt] [429]: The usage limit has been reached"}}}' > "$TMP/worker-read"
bash "$ROOT/scripts/orca-wait.sh" --run gateway --stall-poll-ms 10 > "$TMP/poll.out" 2> "$TMP/poll.err"
status=$?
[ "$status" -eq 5 ] && grep -q 'MODEL_UNAVAILABLE: usage limit (429)' "$TMP/poll.out" && ok "gateway usage limit is a separate reason" || no "gateway usage limit report"

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
