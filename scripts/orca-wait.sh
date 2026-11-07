#!/usr/bin/env bash
# One consuming waiter per Run. Real deliveries remain unacknowledged for the caller.
set -uo pipefail
run= timeout=60000 types=worker_done,escalation,question
while [ "$#" -gt 0 ]; do
  case "$1" in
    --run|--timeout-ms|--types)
      [ "$#" -ge 2 ] || { echo "ERROR: $1 needs a value" >&2; exit 2; }
      case "$1" in --run) run=$2 ;; --timeout-ms) timeout=$2 ;; --types) types=$2 ;; esac
      shift 2 ;;
    *) echo "Usage: orca-wait.sh --run ID [--timeout-ms N] [--types T]" >&2; exit 2 ;;
  esac
done
[[ -n "$run" && "$timeout" =~ ^[1-9][0-9]*$ && -n "$types" ]] || {
  echo "ERROR: --run and a positive --timeout-ms are required" >&2; exit 2;
}
command -v orca >/dev/null 2>&1 || { echo "NOT_AVAILABLE: orca is not on PATH" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
state=$(python3 -B - "$ROOT" "$run" <<'PY'
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'scripts'))
from lib.fstate import persistent, session_key
print(os.path.join(persistent(), 'orca-wait', session_key(sys.argv[2]) + '.lock'))
PY
) || exit 2
state=${state//$'\r'/}
mkdir -p "$(dirname "$state")" || exit 2
# Serialize acquisition and stale takeover with a short-lived mkdir guard. A
# competing acquisition never deletes another waiter's newly acquired lock.
guard="$state.acquire"
guard_owned=0 locked=0 child=
cleanup() {
  if [ -n "$child" ]; then kill "$child" 2>/dev/null || :; wait "$child" 2>/dev/null || :; fi
  if [ "$locked" -eq 1 ]; then rm -f "$state"; fi
  if [ "$guard_owned" -eq 1 ]; then rmdir "$guard" 2>/dev/null || :; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for ((attempt=0; attempt<100; attempt++)); do
  if mkdir "$guard" 2>/dev/null; then guard_owned=1; break; fi
  sleep 0.05
done
if [ "$guard_owned" -eq 0 ]; then
  echo "ERROR: waiter acquisition busy: $guard (inspect interrupted acquisition)" >&2; exit 3
fi
if [ -f "$state" ]; then
  holder=$(cat "$state")
  if [[ "$holder" =~ ^[1-9][0-9]*$ ]] && kill -0 "$holder" 2>/dev/null; then
    echo "ERROR: waiter for run $run already held by pid $holder" >&2; exit 3
  fi
fi
printf '%s\n' "$$" > "$state" || exit 2
locked=1
rmdir "$guard" || exit 2
guard_owned=0

# Keep output bounded without truncating JSON: reject oversized deliveries so
# the caller can inspect the original inbox safely. Payloads are never eval'd.
response="$state.$$.response"
trap 'rm -f "$response"; cleanup' EXIT
ack=
while :; do
  args=(orchestration check --run "$run" --json)
  if [ -n "$ack" ]; then
    args+=(--ack "$ack")
  else
    args+=(--wait --types "$types" --timeout-ms "$timeout")
  fi
  orca "${args[@]}" > "$response" &
  child=$!
  wait "$child"; status=$?; child=
  [ "$status" -eq 0 ] || { echo "ERROR: orca check exited $status" >&2; exit "$status"; }
  parsed=$(python3 -B - "$response" <<'PY'
import json, sys
try:
    with open(sys.argv[1], 'rb') as f:
        raw = f.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('delivery exceeds 1 MiB; inspect inbox directly')
    obj = json.loads(raw)
    if obj.get('ok') is False:
        raise ValueError('orca returned an unsuccessful receipt')
    batch = obj.get('result', obj)
    if any(batch.get(k) for k in ('cancelled', 'connectionLost')):
        raise ValueError('wait cancelled or connection lost')
    messages = batch.get('messages', [])
    if not isinstance(messages, list):
        raise ValueError('messages must be a list')
    if messages and all(m.get('type') == 'heartbeat' for m in messages):
        delivery = batch.get('deliveryId')
        if not isinstance(delivery, str) or not delivery or '\n' in delivery or '\r' in delivery:
            raise ValueError('heartbeat batch has no valid deliveryId')
        print('ack\t' + delivery)
    elif messages:
        print('real')
    else:
        print('wait')
except (OSError, ValueError, TypeError, AttributeError) as e:
    print('ERROR: invalid orca receipt: ' + str(e), file=sys.stderr)
    sys.exit(2)
PY
  ) || exit 2
  parsed=${parsed//$'\r'/}
  case "$parsed" in
    real) cat "$response"; exit 0 ;;
    ack$'\t'*) ack=${parsed#*$'\t'} ;;
    wait) ack= ;;
    *) echo "ERROR: unrecognized receipt classification" >&2; exit 2 ;;
  esac
done
