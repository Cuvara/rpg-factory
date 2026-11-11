#!/usr/bin/env bash
# One consuming waiter per Run. Orca 1.4.250+ marks every batch a check returns as handled and sends no deliveryId, so a
# printed delivery is already read (`orca orchestration inbox` finds it again). An older Orca sends a deliveryId: a
# heartbeat-only batch is acked here and a real delivery stays unacknowledged for the caller.
# The default types include status because task leads report with --type status. --types is only the wake condition and
# a delivery is the whole FIFO batch, so heartbeats always wake the wait: consumed here, they never pile up for a later one.
# Frozen stalls are advisory: a worker may be inside a long quiet command.
# Exit codes: 0 real delivery; 2 usage / NOT_AVAILABLE / invalid receipt or state;
# 3 lock held / acquisition busy; 4 orca failure; 5 stalled worker; 6 parent process gone (orphan, lock released);
# 130 INT; 143 TERM.
set -uo pipefail
run= timeout=60000 types=worker_done,escalation,question,status stall_poll=180000 stall_ms=900000
while [ "$#" -gt 0 ]; do
  case "$1" in
    --run|--timeout-ms|--types|--stall-poll-ms|--stall-ms)
      [ "$#" -ge 2 ] || { echo "ERROR: $1 needs a value" >&2; exit 2; }
      case "$1" in --run) run=$2 ;; --timeout-ms) timeout=$2 ;; --types) types=$2 ;; --stall-poll-ms) stall_poll=$2 ;; --stall-ms) stall_ms=$2 ;; esac
      shift 2 ;;
    *) echo "Usage: orca-wait.sh --run ID [--timeout-ms N] [--types T] [--stall-poll-ms N] [--stall-ms N]" >&2; exit 2 ;;
  esac
done
[[ -n "$run" && "$timeout" =~ ^[1-9][0-9]*$ && -n "$types" && "$stall_poll" =~ ^[0-9]+$ && "$stall_ms" =~ ^[0-9]+$ ]] || {
  echo "ERROR: --run and a positive --timeout-ms are required; --stall-poll-ms and --stall-ms must be nonnegative integers" >&2; exit 2;
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
guard_mutex="$guard.reclaim"
guard_stale_s=60
guard_owned=0 mutex_owned=0 locked=0 child=
# bash fixes $PPID at start, so it keeps naming the parent after a reap. 1 is init or a parent outside this shell's
# process table (a native Windows program): nothing to watch.
parent=$PPID
pid_alive() { [[ "$1" =~ ^[1-9][0-9]*$ ]] && kill -0 "$1" 2>/dev/null; }
parent_gone() { [ "$parent" -gt 1 ] && ! kill -0 "$parent" 2>/dev/null; }
release_guard() { rm -f "$guard/owner"; rmdir "$guard"; }
cleanup() {
  if [ -n "$child" ]; then kill "$child" 2>/dev/null || :; wait "$child" 2>/dev/null || :; fi
  if [ "$locked" -eq 1 ]; then rm -f "$state"; fi
  if [ "$mutex_owned" -eq 1 ]; then rm -f "$guard_mutex"; fi
  if [ "$guard_owned" -eq 1 ]; then release_guard 2>/dev/null || :; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# The owner file is created exclusively: an acquirer paused between mkdir and this write whose guard was reclaimed (and
# perhaps recreated) fails here and retries, so two waiters never both own the guard.
claim_guard() {
  mkdir "$guard" 2>/dev/null || return 1
  (set -o noclobber; printf '%s\n' "$$" > "$guard/owner") 2>/dev/null || return 1
  guard_owned=1
}
# Stale: no live pid recorded and untouched for guard_stale_s. A recorded live pid is never stale, whatever its age.
# $1 the path to age, $2 the file holding the owner pid.
is_stale() {
  local owner age
  owner=$(cat "$2" 2>/dev/null)
  if pid_alive "$owner"; then return 1; fi
  age=$(python3 -B -c 'import os, sys, time; print(int(time.time() - os.stat(sys.argv[1]).st_mtime))' "$1" 2>/dev/null) || return 1
  age=${age//$'\r'/}
  [[ "$age" =~ ^[0-9]+$ ]] && [ "$age" -ge "$guard_stale_s" ]
}
# A SIGKILL between claiming and releasing leaves the guard behind. The mutex stops two waiters from acting on one
# staleness decision, and the decision is repeated under it, so a guard that was replaced meanwhile is left alone. A
# reclaimer killed here leaves only its own mutex, which ages out the same way.
reclaim_guard() {
  [ -d "$guard" ] && is_stale "$guard" "$guard/owner" || return 0
  if is_stale "$guard_mutex" "$guard_mutex"; then rm -f "$guard_mutex"; fi
  (set -o noclobber; printf '%s\n' "$$" > "$guard_mutex") 2>/dev/null || return 0
  mutex_owned=1
  if is_stale "$guard" "$guard/owner"; then
    if release_guard 2>/dev/null; then echo "WARN: reclaimed stale acquisition guard: $guard" >&2; fi
  fi
  rm -f "$guard_mutex"
  mutex_owned=0
}
for ((attempt=0; attempt<100; attempt++)); do
  if claim_guard; then break; fi
  if [ $((attempt % 20)) -eq 0 ]; then reclaim_guard; fi
  sleep 0.05
done
if [ "$guard_owned" -eq 0 ]; then
  owner=$(cat "$guard/owner" 2>/dev/null)
  echo "ERROR: waiter acquisition busy: $guard (owner pid ${owner:-unknown}; a guard with no live owner is reclaimed after ${guard_stale_s}s)" >&2; exit 3
fi
if [ -f "$state" ]; then
  holder= holder_parent=
  read -r holder holder_parent < "$state" || :
  if pid_alive "$holder"; then
    # Named, never killed: the run cannot prove it started that process, and the holder exits by itself at its next loop.
    if [[ "$holder_parent" =~ ^[0-9]+$ ]] && [ "$holder_parent" -gt 1 ] && ! kill -0 "$holder_parent" 2>/dev/null; then
      echo "ERROR: waiter for run $run already held by pid $holder (orphan: parent gone, was pid $holder_parent; it exits at its next poll and releases the lock, retry then)" >&2; exit 3
    fi
    echo "ERROR: waiter for run $run already held by pid $holder" >&2; exit 3
  fi
fi
printf '%s %s\n' "$$" "$parent" > "$state" || exit 2
locked=1
release_guard || exit 2
guard_owned=0

# Keep output bounded without truncating JSON: reject oversized deliveries so
# the caller can inspect the original inbox safely. Payloads are never eval'd.
response="$state.$$.response"
stderr="$response.stderr"
trap 'rm -f "$response" "$stderr"; cleanup' EXIT
# The tail of a failed check is for the error: Orca's --wait keepalive lines (old alias _heartbeat) would crowd it out.
failure_tail() { grep -avE '^[[:space:]]*\{"_(keepalive|heartbeat)"' "$1" | tail -n 15 >&2; }
wake_types=$types
case ",$types," in *,heartbeat,*) ;; *) wake_types=$types,heartbeat ;; esac
ack=
wait_timeout=$timeout
if [ "$stall_poll" -gt 0 ] && [ "$stall_poll" -lt "$timeout" ]; then wait_timeout=$stall_poll; fi
while :; do
  if parent_gone; then
    echo "ERROR: waiter parent pid $parent is gone; exiting 6 and releasing the lock for run $run" >&2
    exit 6
  fi
  args=(orchestration check --run "$run" --json)
  if [ -n "$ack" ]; then
    args+=(--ack "$ack")
  else
    args+=(--wait --types "$wake_types" --timeout-ms "$wait_timeout")
  fi
  orca "${args[@]}" > "$response" 2> "$stderr" &
  child=$!
  wait "$child"; status=$?; child=
  if [ "$status" -ne 0 ]; then
    echo "ERROR: orca check exited $status" >&2
    failure_tail "$stderr"
    failure_tail "$response"
    exit 4
  fi
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
        if delivery is None or delivery == '':
            print('wait')  # Orca 1.4.250+ sends no deliveryId: the check already marked the batch handled
        elif not isinstance(delivery, str) or '\n' in delivery or '\r' in delivery:
            raise ValueError('heartbeat batch has an invalid deliveryId')
        else:
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
    wait)
      if [ -z "$ack" ] && [ "$stall_poll" -gt 0 ]; then
        python3 -B - "$ROOT" "$run" "$state.workers.json" "$stall_poll" "$stall_ms" <<'PY' &
import hashlib, json, os, shlex, shutil, subprocess, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root, run, path, interval, threshold = sys.argv[1:]
sys.path[:0] = [os.path.join(root, 'scripts'), os.path.join(root, 'scripts', 'lib')]
from lib import fstate
from lib.pipeline_route import stall_reason

now = time.time() * 1000
state = {}

def call(args):
    proc = subprocess.run([shutil.which('orca') or 'orca', 'orchestration'] + args, capture_output=True,
                          encoding='utf-8', errors='replace', timeout=20)
    if proc.returncode:
        raise ValueError(args[0] + ' exited ' + str(proc.returncode))
    doc = json.loads(proc.stdout)
    if not isinstance(doc, dict) or doc.get('ok') is False or not isinstance(doc.get('result'), dict):
        raise ValueError(args[0] + ' returned an invalid receipt')
    return doc['result']

try:
    state = fstate.read_json(path, {})
    if (not isinstance(state, dict) or not isinstance(state.get('last_poll', 0), (int, float))
            or not isinstance(state.get('workers', {}), dict)
            or any(not isinstance(v, dict) or not isinstance(v.get('since', now), (int, float))
                   for v in state.get('workers', {}).values())):
        state = {}
    if now - state.get('last_poll', 0) < int(interval):
        sys.exit(0)
    state['last_poll'] = now
    old = state.get('workers', {})
    workers, cursor = [], None
    while True:
        args = ['worker-list', '--run', run, '--terminal-state', 'active', '--json']
        if cursor:
            args += ['--cursor', cursor]
        result = call(args)
        rows = result.get('workers')
        if not isinstance(rows, list):
            raise ValueError('worker-list returned invalid workers')
        workers.extend(rows)
        page = result.get('page') or {}
        cursor = page.get('nextCursor') if page.get('hasMore') else None
        if not cursor:
            break
    current, stalls = {}, []
    for worker in workers:
        if not isinstance(worker, dict) or not isinstance(worker.get('dispatchId'), str):
            raise ValueError('worker-list returned invalid worker')
        dispatch = worker['dispatchId']
        if str(worker.get('dispatchStatus', '')).lower() in ('completed', 'failed', 'cancelled'):
            continue
        try:
            result = call(['worker-read', '--dispatch', dispatch, '--source', 'terminal', '--limit', '40', '--json'])
            tail = result.get('terminal', {}).get('tail')
            if not isinstance(tail, (str, list)) or (isinstance(tail, list) and not all(isinstance(x, str) for x in tail)):
                raise ValueError('worker-read returned invalid terminal tail')
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
            print('WARN: worker-read {}: {}'.format(dispatch, ' '.join(str(exc).split())), file=sys.stderr)
            if dispatch in old:
                current[dispatch] = old[dispatch]
            continue
        digest = hashlib.sha256(json.dumps(tail, ensure_ascii=True).encode()).hexdigest()
        prior = old.get(dispatch, {})
        since = prior.get('since', now) if isinstance(prior, dict) and prior.get('hash') == digest else now
        current[dispatch] = {'hash': digest, 'since': since}
        reason = stall_reason(tail)
        if not reason and now - since >= int(threshold):
            reason = 'frozen: output unchanged for ' + str(int((now - since) // 60000)) + ' min'
        reason_key = ('frozen' if reason and reason.startswith('frozen:') else
                      'usage limit' if reason and reason.startswith('MODEL_UNAVAILABLE: usage limit') else
                      'model not found' if reason and reason.startswith('MODEL_UNAVAILABLE: model not found') else
                      'gateway error' if reason and reason.startswith('MODEL_UNAVAILABLE: gateway error') else
                      'reconnecting' if reason else None)
        prior_reason = prior.get('reported') if isinstance(prior, dict) else None
        if reason_key == 'frozen' and isinstance(prior, dict) and prior.get('hash') != digest:
            prior_reason = None
        current[dispatch]['reported'] = reason_key
        if reason and reason_key != prior_reason:
            provider = (worker.get('projection') or {}).get('provider') or {}
            agent = provider.get('id') or 'unknown'
            stalls.append((dispatch, agent, ' '.join(reason.split())))
    state['workers'] = current
    for name in os.listdir(os.path.dirname(path)):
        candidate = os.path.join(os.path.dirname(path), name)
        if name.endswith('.workers.json') and candidate != path:
            try:
                if time.time() - os.stat(candidate).st_mtime > 7 * 86400:
                    os.remove(candidate)
            except OSError:
                pass
    fstate.write_json(path, state)
    for dispatch, agent, reason in stalls:
        print('STALL\t{}\t{}\t{}'.format(dispatch, agent, reason))
        if reason.startswith('MODEL_UNAVAILABLE: '):
            print('NEXT\tpython3 -B scripts/factory-pipeline.py agents <plan> --down {} --reason {}'.format(
                shlex.quote(agent), shlex.quote(reason[len('MODEL_UNAVAILABLE: '):])))
    if stalls:
        sys.exit(5)
except (OSError, UnicodeError, ValueError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
    try:
        fstate.write_json(path, state)
    except OSError:
        pass
    print('WARN: worker poll: ' + ' '.join(str(exc).split()), file=sys.stderr)
PY
        child=$!
        wait "$child"; poll_status=$?; child=
        [ "$poll_status" -ne 5 ] || exit 5
      fi
      ack= ;;
    *) echo "ERROR: unrecognized receipt classification" >&2; exit 2 ;;
  esac
done
