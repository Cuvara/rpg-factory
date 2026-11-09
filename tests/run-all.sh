#!/usr/bin/env bash
# run-all.sh — every local validation for the plugin. Read-only against the workspace.
# Prints one line per check and a final count; exits non-zero if anything failed.
# Dead parallel workers fail with buffered output; added branch/worktree config sections warn, other mutations fail.
#
# Usage: tests/run-all.sh [-j N] [--no-workspace] [--no-claude] [--release] [--affected [--base REF]]
#                         [--only-suites L] [--reuse] [--no-reuse] [--no-wait] [--list-suites]
#   -j N, --jobs N  run up to N independent suites at once (default 1). Lines print in the -j 1 order with the
#                   same count and exit code. Read-only live-workspace checks (runl, block) run one at a time
#                   next to the fixture suites; run1 suites (shared git config guard, installed plugin, claude
#                   validate) run alone. Ends with the wall time.
#   --affected      run only the suites the change touches (tests/affected.py: files changed since
#                   merge-base(REF|origin/main|main) plus untracked); the cheap inline checks (JSON parse,
#                   executable bits, manifest and wording greps, resolver and fixture checks) always run.
#                   For iteration and task QA; the full run (no --affected, no --only-suites) is integration
#                   QA's gate before a PR (once per batch, not each task's) and runs for --release.
#                   With --affected or --only-suites, a check that runs a script outside a suite line (the live
#                   blocks: scripts/checks/skill-citations.py, scripts/factory-context.sh, and in the live checks
#                   scripts/checks/pin-status.py, pin-plan.py, package-ready.py, netcode-headless.sh) is selected
#                   like a suite by that script path, else it counts as not affected.
#   --reuse         reuse a clean PASS full-run record for the same tree and coverage flags
#   --no-wait       exit 3 when another full run holds the machine-wide lock
#   --only-suites L run comma-separated suite paths, unioned with --affected (no full-run lock); a path may also
#                   be a gated script above (e.g. scripts/checks/netcode-headless.sh). A name that is not in
#                   --list-suites (no run line runs it, e.g. tests/handoff-e2e.test.sh) exits 2, naming each one;
#                   so does a release-only suite (tests/installed-safety.sh) without --release.
#   --list-suites   print every suite and gated script path the current flags can select (one per line, exactly
#                   the names --only-suites accepts, in run order; release-only suites only with --release) and
#                   exit 0; runs no check, takes no lock
#   --no-reuse      force suites to run instead of reusing matching input PASS records
#   --release       the installed plugin must equal the source (install-status CURRENT), the source
#                   must be committed, and tests/installed-safety.sh must pass against the installed hooks
#   --no-workspace  skip checks that need the RPG MMO workspace on disk
#   --no-claude     skip `claude plugin validate`
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/gitcfg-guard.sh"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
cd "$ROOT" || exit 1
RUNALL_SELF="$ROOT/tests/run-all.sh"   # the run lines --list-suites reads (stand-in plans set RUNALL_SUITES_FROM)
RELEASE_ONLY="tests/installed-safety.sh"   # run only with --release: --list-suites omits them, --only-suites rejects them without it
use_ws=true; use_claude=true; release=false; affected=false; base=""; jobs=1; reuse=false; no_wait=false; suite_reuse=true; only_suites=""
list_only=false
while [ $# -gt 0 ]; do
  case "$1" in --no-workspace) use_ws=false ;; --no-claude) use_claude=false ;; --release) release=true ;;
    --reuse) reuse=true ;; --no-wait) no_wait=true ;; --no-reuse) suite_reuse=false ;;
    --only-suites) only_suites="${2:-}"; [ -n "$only_suites" ] || { echo "run-all: --only-suites needs a list" >&2; exit 2; }; shift ;;
    --only-suites=*) only_suites="${1#--only-suites=}"; [ -n "$only_suites" ] || { echo "run-all: --only-suites needs a list" >&2; exit 2; } ;;
    --list-suites) list_only=true ;;
    --affected) affected=true ;; --base) base="${2:-}"; shift ;;
    -j|--jobs) jobs="${2:-}"; shift ;; -j*) jobs="${1#-j}" ;; --jobs=*) jobs="${1#--jobs=}" ;; esac
  shift
done
case "$jobs" in ''|*[!0-9]*|0*) echo "run-all: -j/--jobs needs a positive integer, got '$jobs'" >&2; exit 2 ;; esac
t_start=$(date +%s)
AFF=""
if $affected && ! $release; then
  AFF=$(mktemp_win)/changed.txt
  if python3 -B "${RUNALL_AFFECTED_PY:-tests/affected.py}" changed ${base:+"$base"} > "$AFF"; then echo "affected mode: $(wc -l < "$AFF" | tr -d ' ') changed file(s)"
  elif [ -n "$only_suites" ]; then echo "affected mode: no base, running only --only-suites $only_suites"; rm -rf "${AFF%/*}"; AFF=""
  else echo "affected mode: no base, running everything"; rm -rf "${AFF%/*}"; AFF=""; fi
fi

pass=0; fail=0; skip=0; naff=0; cleanup=(); failures=(); GITCFG_KEEP=""
STATE=""; LOCK=""; LOCK_TOKEN=""; TREE=""; HEAD_SHA=""; CLEAN_START=false
HASHES=(); HASH_SUITES=(); CACHE_PATHS=(); CACHE_BEFORE=""
_ok()   { pass=$((pass + 1)); echo "PASS  $1"; }
_bad()  { failures+=("$1"); fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/      /'; }
_skp()  { skip=$((skip + 1)); echo "SKIP  $1 ($2)"; }
_note() { echo "$1"; }
# Suites read /dev/null, never the caller's stdin. -j 1: every line prints when its check ends. -j N: suites are
# queued and started in the background (at most N at a time: live-lane suites first, one at a time, one slot for the
# earliest queued suite, then the SLOW ones, then the rest in order; output buffered in $QD). Every line - suite results and inline checks alike - waits
# in the queue until the lines before it are out, so the output order, the count and the exit code are those of -j 1.
QD=""; qn=0; qnext=0; nrun=0; nlive=0; nord=0; QK=(); QM=(); QX=(); QC=(); QS=(); QL=(); QA=(); QP=(); PEND=()
# the longest suites (Windows, -j 1), started early so none of them is the tail of the parallel phase
SLOW="tests/parallel-policy.test.sh tests/git-guard.test.sh tests/run-checks.test.sh tests/routing-golden.test.sh
      tests/check-registry.test.sh tests/checks-candidate.test.sh tests/factory-status.test.sh tests/new-skill.test.sh
      tests/devtools.test.sh tests/domains.test.sh tests/assetgen.test.sh testlab/tests/test_lab.py"
runall_cleanup() {
  local pid
  for pid in $(jobs -p); do kill "$pid" 2>/dev/null || :; done
  [ -z "$QD" ] || rm -rf "$QD"
  [ -z "$AFF" ] || rm -rf "${AFF%/*}"
  # every exit (also --list-suites, a --reuse hit, --no-wait, an unknown suite) removes the config copy, except after a
  # shared-config FAIL, whose message names the copy
  [ -z "${GITCFG_COPY:-}" ] || [ -n "$GITCFG_KEEP" ] || rm -f "$GITCFG_COPY"
  if [ -n "$LOCK_TOKEN" ] && [ "$(cat "$LOCK/owner" 2>/dev/null)" = "$LOCK_TOKEN" ]; then
    rm -f "$LOCK/owner" "$LOCK/pid" "$LOCK/checkout" "$LOCK/started" "$LOCK/winpid"
    rmdir "$LOCK" 2>/dev/null || :
  fi
}
[ "$jobs" -gt 1 ] && QD=$(mktemp_win)
trap runall_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
queue() { # kind message [detail]
  if [ -z "$QD" ]; then "_$1" "$2" "${3:-}"; return; fi
  QK[qn]=$1; QM[qn]=$2; QX[qn]=${3:-}; qn=$((qn + 1)); flush
}
ok()   { queue ok "$@"; }
bad()  { queue bad "$@"; }
skp()  { queue skp "$@"; }
note() { queue note "$1"; }
worker_result() { # synthesize a failure only for a started worker that exited without publishing its result
  local i=$1 pid=${QP[$1]:-}
  if [ ! -f "$QD/$i.res" ] && [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    # The worker publishes by rename: it may have finished between the first test and kill -0.
    [ -f "$QD/$i.res" ] && return 0
    printf '\nsuite worker died without a result (pid %s)\n' "$pid" >> "$QD/$i.out"
    printf '137 0\n' > "$QD/$i.res"
  fi
}
flush() { # print the queue up to the first suite still running
  local i st secs
  while [ "$qnext" -lt "$qn" ]; do
    i=$qnext
    if [ "${QK[i]}" = job ]; then
      worker_result "$i"
      [ -f "$QD/$i.res" ] || return 0
      read -r st secs < "$QD/$i.res"
      if [ "$st" = 137 ] && grep -q 'suite worker died without a result' "$QD/$i.out"; then _bad "${QM[i]} [${secs}s]" "$(cat "$QD/$i.out")"
      elif [ -n "${QX[i]}" ]; then "${QX[i]}" "$st" "$(cat "$QD/$i.out")" "${QM[i]}"
      elif [ "$st" = 0 ]; then suite_cache_pass "${QS[i]}" "$(cat "$QD/$i.out")"; _ok "${QM[i]} [${secs}s]"; else _bad "${QM[i]} [${secs}s]" "$(cat "$QD/$i.out")"; fi
      rm -f "$QD/$i.res" "$QD/$i.out"
    else "_${QK[i]}" "${QM[i]}" "${QX[i]}"; fi
    unset 'QK[i]' 'QM[i]' 'QX[i]' 'QC[i]' 'QS[i]' 'QL[i]' 'QA[i]' 'QP[i]'; qnext=$((i + 1))
  done
}
running() { # sets nrun (started, not ended), nlive (of them in the live lane), nord (started as the in-order one)
  local i; nrun=0; nlive=0; nord=0
  for ((i = qnext; i < qn; i++)); do
    [ "${QK[i]}" = job ] && worker_result "$i"
    [ -n "${QL[i]:-}" ] && [ ! -f "$QD/$i.res" ] && { nrun=$((nrun + 1)); [ -n "${QA[i]:-}" ] && nlive=$((nlive + 1))
      [ "${QL[i]}" = o ] && nord=$((nord + 1)); }
  done
}
start() { # queue index [o: the in-order pick]
  QL[$1]=${2:-1}
  ( t0=$(date +%s); eval "${QC[$1]}" > "$QD/$1.out" 2>&1 < /dev/null; rc=$?; t1=$(date +%s)
    echo "$rc $((t1 - t0))" > "$QD/$1.tmp" && mv "$QD/$1.tmp" "$QD/$1.res" ) &
  QP[$1]=$!
}
pump() { # start queued suites while fewer than $jobs run: a live-lane one when none runs, the earliest queued one when
  # none of those runs (keeps the output moving), else SLOW first, else in order
  local i k pick kind
  while [ ${#PEND[@]} -gt 0 ]; do
    running; [ "$nrun" -lt "$jobs" ] || return 0
    pick=""; kind=""
    [ "$nlive" -eq 0 ] && for i in "${!PEND[@]}"; do [ -n "${QA[${PEND[i]}]}" ] && { pick=$i; break; }; done
    [ -n "$pick" ] || [ "$nord" -gt 0 ] || for i in "${!PEND[@]}"; do [ -z "${QA[${PEND[i]}]}" ] && { pick=$i; kind=o; break; }; done
    [ -n "$pick" ] || for k in $SLOW; do for i in "${!PEND[@]}"; do [ "${QS[${PEND[i]}]}" = "$k" ] && { pick=$i; break 2; }; done; done
    [ -n "$pick" ] || for i in "${!PEND[@]}"; do [ -z "${QA[${PEND[i]}]}" ] && { pick=$i; break; }; done
    [ -n "$pick" ] || return 0   # only live-lane suites left and one is running
    start "${PEND[pick]}" "$kind"; unset 'PEND[pick]'
  done
}
drain() { [ -n "$QD" ] || return 0; while pump; flush; [ "$qnext" -lt "$qn" ]; do sleep 0.2; done; }
# suite_of <args>: sets $s to the test or script file a run line executes (the unit tests/affected.py selects on)
suite_of() { local a; s=""; for a in "$@"; do case "$a" in tests/*|testlab/*|scripts/*) s=$a; return ;; esac; done; }
# run <name> <cmd...>: a suite; with -j N it runs in the background.
# runl <name> <cmd...>: a read-only suite against the live workspace: in the background, but never two at once.
# run1 <name> <cmd...>: a suite that must run alone (shared git config, installed plugin, `claude plugin validate`):
#   every queued suite ends first.
# runp <name> <post> <cmd...>: like run, but <post> <rc> <output> grades the result (with _ok/_bad/_skp).
# block <fn>: inline checks in function <fn> as one live-lane suite; its PASS/FAIL/SKIP lines are counted (replay).
run()  { _run bg "" "" "$@"; }
runl() { _run bg "" live "$@"; }
runp() { local name="$1" post="$2"; shift 2; _run bg "$post" "" "$name" "$@"; }
run1() { drain; _run fg "" "" "$@"; }
# A block's checks read the live workspace: LIVE_BLOCK keeps every run line inside it out of suite reuse (-j 1 and -j N).
block() { if [ -z "$QD" ]; then local LIVE_BLOCK=1; "$1"; else _run bg replay live "$1" in_block "$1"; fi; }
in_block() { ( QD=""; IN_BLOCK=1; LIVE_BLOCK=1; "$1"; echo "<end of block>" ); }   # inside the job: the checks print at once
IN_BLOCK=""; LIVE_BLOCK=""
# not_affected: count a check the change does not touch (inside a block job, a marker line replay counts)
not_affected() { if [ -n "$IN_BLOCK" ]; then echo "<not affected>"; else skip=$((skip + 1)); naff=$((naff + 1)); fi; }
# gated <script>: guard for a check that runs <script> outside a run/runl line (block or inline). In a full run or
# --release it always runs; with --affected / --only-suites only when <script> is listed or affected.
gated() { suite_selected "$1" && return 0; not_affected; return 1; }
replay() { # rc output name: the lines a block printed, counted by their prefix
  local l done=""
  while IFS= read -r l; do
    case "$l" in "PASS  "*) pass=$((pass + 1)) ;; "FAIL  "*) fail=$((fail + 1)); failures+=("${l#FAIL  }") ;; "SKIP  "*) skip=$((skip + 1)) ;;
      "<not affected>") skip=$((skip + 1)); naff=$((naff + 1)); continue ;;
      "<end of block>") done=1; continue ;; esac
    printf '%s\n' "$l"
  done <<<"$2"
  [ -n "$done" ] || _bad "checks block $3 ended early (rc=$1)"
}
_run() {
  local mode="$1" post="$2" lane="$3" name="$4"; shift 4; local out s t0 t1 n rc
  suite_of "$@"
  if [ -n "$s" ] && ! suite_selected "$s"; then not_affected; return; fi
  # Postprocessors can turn rc=0 into SKIP/FAIL, so they always grade fresh output.
  local cache_suite="$s"
  case "$name" in 'bash -n:'*|'py_compile:'*|'json:'*|'jq compile:'*) cache_suite="" ;; esac
  # never reused: graded by a handler, live lane (runl, block), inside a block, or reading a workspace
  [ -z "$post$lane$LIVE_BLOCK" ] || cache_suite=""
  case " $* " in *" --no-history "*|*" RPG_FACTORY_WORKSPACE="*) cache_suite="" ;; esac
  if [ -z "$post" ] && suite_cache_hit "$cache_suite"; then ok "$name (reused $s inputs $suite_hash)"; return; fi
  if [ -z "$QD" ] || [ "$mode" = fg ]; then
    if [ -n "$post" ]; then out=$("$@" 2>&1 < /dev/null); rc=$?; "$post" "$rc" "$out"; return; fi
    t0=$(date +%s)
    if out=$("$@" 2>&1 < /dev/null); then t1=$(date +%s); suite_cache_pass "$cache_suite" "$out"; ok "$name [$((t1 - t0))s]"; else t1=$(date +%s); bad "$name [$((t1 - t0))s]" "$out"; fi
    return
  fi
  n=$qn; printf -v "QC[$n]" '%q ' "$@"; QK[n]=job; QM[n]=$name; QX[n]=$post; QS[n]=$cache_suite; QA[n]=$lane; PEND+=("$n"); qn=$((qn + 1))
  pump; flush
}
# Classify conservatively: existing bytes must stay intact, and insertions must be whole new sections.
gitcfg_classify() { # before after -> PASS|WARN|FAIL (unreadable files fail)
  python3 -B - "$1" "$2" <<'PY'
import difflib
import re
import sys
try:
    before, after = [open(p, 'rb').readlines() for p in sys.argv[1:]]
except OSError:
    print('FAIL')
    sys.exit(0)
if before == after:
    print('PASS')
    sys.exit(0)
header = re.compile(rb'^\s*\[([^\r\n]+)\]\s*(?:\r?\n)?$')
allowed = re.compile(rb'^(?:branch\s+"[^"\r\n]+"|worktree(?:\s+"[^"\r\n]+")?)$')
existing = {m[1] for line in before if (m := header.fullmatch(line))}
for tag, a, b, c, d in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
    if tag == 'equal':
        continue
    if tag != 'insert' or (a < len(before) and not header.fullmatch(before[a])):
        print('FAIL')
        break
    lines = after[c:d]
    if not lines or not header.fullmatch(lines[0]) or (a and not before[a-1].endswith(b'\n')):
        print('FAIL')
        break
    for line in lines:
        if line.lstrip().startswith(b'['):
            m = header.fullmatch(line)
            if not m or not allowed.fullmatch(m[1]) or m[1] in existing:
                print('FAIL')
                sys.exit(0)
            existing.add(m[1])
else:
    print('WARN')
PY
}
# Persistent state and reuse helpers are also exercised by the stand-in scheduler tests.
python_path_fast() {
  local py real
  py=$(command -v python3) || return 0
  case "$py" in *[Ww]indowsApps/*)
    real=$(python3 -c 'import sys,os; print(os.path.dirname(sys.executable))') || return 0
    real=${real%$'\r'}
    case "$real" in ''|*[Ww]indowsApps*) return 0 ;; esac
    if command -v cygpath >/dev/null 2>&1; then real=$(cygpath -u "$real") || return 0; fi
    [ -d "$real" ] || return 0
    PATH="$real:$PATH"; export PATH
    echo "run-all: using real Python directory $real"
  esac
}
list_suites() { # file: every suite or gated script a run/runl/runp/run1 line or a gated guard in <file> names, as
  # suite_of returns it (first tests/, testlab/ or scripts/ argument of the command); syntax checks and paths built
  # from variables (the bash -n / py_compile loops) are not suites
  python3 -B - "$1" <<'PY'
import re, shlex, sys
text = re.sub(r'\\\r?\n', ' ', open(sys.argv[1], encoding='utf-8').read())
lead = {'if', 'elif', 'then', 'else', 'do', 'while', 'until', '!', '{'}
syntax = ('bash -n:', 'py_compile:', 'json:', 'jq compile:')
punct = lambda t: bool(t) and all(c in '();<>|&' for c in t)
seen = []
for line in text.splitlines():
    if line.lstrip().startswith('#'):
        continue
    try:
        lx = shlex.shlex(line, posix=True, punctuation_chars=True)
        lx.whitespace_split = True
        toks = list(lx)
    except ValueError:
        continue
    for i, t in enumerate(toks):
        if t not in ('run', 'runl', 'runp', 'run1', 'gated') or not (i == 0 or punct(toks[i - 1]) or toks[i - 1] in lead):
            continue
        args = []
        for a in toks[i + 1:]:
            if punct(a):
                break
            args.append(a)
        if t == 'gated':
            cmd = args[:1]
        elif not args or args[0].startswith(syntax):
            continue
        else:
            cmd = args[2:] if t == 'runp' else args[1:]
        for a in cmd:
            if a.startswith(('tests/', 'testlab/', 'scripts/')):
                if '$' not in a and a not in seen:
                    seen.append(a)
                break
sys.stdout.buffer.write(''.join(s + '\n' for s in seen).encode())   # LF on Windows too: callers compare lines
PY
}
release_only() { case " $RELEASE_ONLY " in *" $1 "*) return 0 ;; esac; return 1; }
list_runnable() { # file: list_suites without the release-only suites unless --release (what the current flags can run)
  local listed s
  listed=$(list_suites "$1") || return 1
  while IFS= read -r s; do
    s=${s%$'\r'}; [ -n "$s" ] || continue
    $release || ! release_only "$s" || continue
    printf '%s\n' "$s"
  done <<<"$listed"
}
suite_selected() {
  local target=$1
  $release && return 0
  case ",$only_suites," in *",$target,"*) return 0 ;; esac
  if [ -n "$AFF" ]; then python3 -B "${RUNALL_AFFECTED_PY:-tests/affected.py}" select "$AFF" "$target"; return; fi
  [ -z "$only_suites" ]
}
suite_hash_for() {
  local i; suite_hash=""
  for i in "${!HASH_SUITES[@]}"; do
    [ "${HASH_SUITES[i]}" = "$1" ] && { suite_hash=${HASHES[i]}; break; }
  done
  [[ "$suite_hash" =~ ^[a-fA-F0-9]{16,128}$ ]]
}
suite_cache_file() {
  local key
  suite_hash_for "$1" || return 1
  key=$(printf '%s' "$1" | sha1sum); key=${key%% *}
  cache_file="$STATE/run-all/suites/$key/$suite_hash"
}
suite_cache_hit() {
  $suite_reuse && ! $release && [ -n "$STATE" ] && [ -n "$1" ] || return 1
  suite_cache_file "$1" && [ -f "$cache_file" ] && grep -qx PASS "$cache_file"
}
suite_cache_pass() { # suite output
  # Defer publishing until the input snapshot is confirmed unchanged at the end.
  $suite_reuse && ! $release && [ -n "$STATE" ] && [ -n "$1" ] || return 0
  # A suite that skipped cases (a tool, repo or platform missing) passed only in part: once the tool appears its
  # inputs are the same, so a record would reuse the partial pass. Such a suite runs again next time.
  suite_partial "${2:-}" && return 0
  suite_cache_file "$1" || return 0
  CACHE_PATHS+=("$cache_file")
}
# Only result lines count: a SKIP or NOT_AVAILABLE line (a tool, repo or platform missing). The words inside a PASS
# line (a case named "orca missing: NOT_AVAILABLE") are a case name, not a partial pass.
suite_partial() { grep -Eqi '^[[:space:]]*(SKIP|NOT_AVAILABLE)([[:space:]:(]|$)' <<<"$1"; }
input_snapshot() {
  # Includes dirty and untracked bytes, not just status letters or mtimes.
  python3 -B - <<'PY'
import hashlib, subprocess
h = hashlib.sha256()
for cmd in (["git", "ls-files", "-co", "--exclude-standard", "-z"],):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode: raise SystemExit(1)
    for raw in sorted(set(r.stdout.split(b'\0')) - {b''}):
        h.update(raw + b'\0')
        try:
            with open(raw, 'rb') as f: h.update(f.read())
        except OSError: h.update(b'<missing>')
print(h.hexdigest())
PY
}
lock_alive() {
  local pid winpid
  pid=$(cat "$LOCK/pid" 2>/dev/null)
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null && return 0
  winpid=$(cat "$LOCK/winpid" 2>/dev/null)
  if [[ "$winpid" =~ ^[0-9]+$ ]] && command -v tasklist.exe >/dev/null 2>&1; then
    tasklist.exe //FI "PID eq $winpid" //NH 2>/dev/null | grep -Eq "[[:space:]]$winpid[[:space:]]" && return 0
  fi
  return 1
}
dir_age() { python3 -c 'import os,sys,time; print(int(time.time()-os.stat(sys.argv[1]).st_mtime))' "$1" 2>/dev/null; }
reclaim_stale() { # a takeover that died inside its reclaim guard must not wedge the lock: remove a guard whose holder
  # is dead, or one older than 10 s (a takeover holds it for milliseconds)
  local r="$LOCK/reclaim" rpid age
  [ -d "$r" ] || return 0
  rpid=$(cat "$r/pid" 2>/dev/null)
  if [[ "$rpid" =~ ^[0-9]+$ ]] && kill -0 "$rpid" 2>/dev/null; then
    age=$(dir_age "$r") && [ "$age" -ge 10 ] || return 0
  elif [ -z "$rpid" ]; then
    # the pid is written right after mkdir: give a live holder time to write it
    age=$(dir_age "$r") && [ "$age" -ge 2 ] || return 0
  fi
  echo "run-all: removing stale reclaim guard of the full-run lock (${rpid:-no pid})"
  rm -f "$r/pid"; rmdir "$r" 2>/dev/null || :
}
# identity of a directory: a fresh lock created at the same path differs (inode, and creation time where the platform
# has one; mtime is no use, the reclaim mkdir itself changes it)
dir_ident() { python3 -c 'import os,sys; st=os.stat(sys.argv[1]); b=getattr(st,"st_birthtime_ns",None)
print(st.st_dev, st.st_ino, b if b is not None else (st.st_ctime_ns if os.name=="nt" else ""))' "$1" 2>/dev/null; }
lock_still_stale() { # stale-pid stale-ident: under the reclaim guard, the lock is still the stale one this process
  # judged. Another takeover may have removed it and a new holder created a fresh lock (pid not yet written) that this
  # guard now sits in: removing that would let two full runs start.
  [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$1" ] && [ -n "$2" ] && [ "$(dir_ident "$LOCK")" = "$2" ] && ! lock_alive
}
full_lock() {
  local owner waited=false age stale_pid stale_ident
  LOCK="$STATE/locks/run-all-full"; mkdir -p "${LOCK%/*}" || return 1
  until mkdir "$LOCK" 2>/dev/null; do
    # mkdir and metadata publication are separate: give a new holder time to publish.
    if [ ! -f "$LOCK/pid" ]; then
      age=$(dir_age "$LOCK") || continue
      [ "$age" -ge 10 ] || { $no_wait && { echo "waiting for full run unknown in $LOCK"; return 3; }; sleep 0.2; continue; }
    fi
    reclaim_stale
    stale_pid=$(cat "$LOCK/pid" 2>/dev/null); stale_ident=$(dir_ident "$LOCK")
    if ! lock_alive && mkdir "$LOCK/reclaim" 2>/dev/null; then
      printf '%s
' "$$" > "$LOCK/reclaim/pid"
      if lock_still_stale "$stale_pid" "$stale_ident"; then
        echo "run-all: taking over stale full-run lock ($(cat "$LOCK/pid" 2>/dev/null))"
        rm -f "$LOCK/owner" "$LOCK/pid" "$LOCK/checkout" "$LOCK/started" "$LOCK/winpid"
        rm -f "$LOCK/reclaim/pid"; rmdir "$LOCK/reclaim" "$LOCK" 2>/dev/null || :
      else rm -f "$LOCK/reclaim/pid"; rmdir "$LOCK/reclaim" 2>/dev/null || :; fi
      continue
    fi
    if ! $waited; then echo "waiting for full run $(cat "$LOCK/pid" 2>/dev/null) in $(cat "$LOCK/checkout" 2>/dev/null)"; waited=true; fi
    $no_wait && return 3
    sleep 0.2
  done
  LOCK_TOKEN="$$-$RANDOM-$(date +%s)"
  printf '%s\n' "$LOCK_TOKEN" > "$LOCK/owner"
  printf '%s\n' "$$" > "$LOCK/pid"
  printf '%s\n' "$ROOT" > "$LOCK/checkout"
  date -u +%FT%TZ > "$LOCK/started"
  ps -p $$ -o winpid= 2>/dev/null | tr -d ' ' > "$LOCK/winpid" || :
}
full_reuse() {
  $reuse && ! $release && $CLEAN_START && [ -n "$TREE" ] || return 1
  python3 -B - "$STATE/run-all/$TREE.json" "$TREE" "$use_ws" "$use_claude" <<'PY'
import json, sys
try:
    r = json.load(open(sys.argv[1], encoding='utf-8'))
    assert r['tree'] == sys.argv[2] and r['counts']['fail'] == 0 and r['counts']['pass'] > 0
    assert sys.argv[3] != 'true' or not r['flags']['no_workspace']
    assert sys.argv[4] != 'true' or not r['flags']['no_claude']
    print(f"reused full run at {r['head']} (tree {r['tree']}, {r['date']})")
except (OSError, ValueError, KeyError, TypeError, AssertionError):
    sys.exit(1)
PY
}
clean_tree() {
  local status
  status=$(git status --porcelain) || return 1
  [ -z "$status" ]
}
runall_prepare() {
  local suite hash candidate hash_output found; local -a suites=()
  python_path_fast
  STATE=$(python3 -B -c 'import sys; sys.path.insert(0, "scripts/lib"); import fstate; print(fstate.persistent())') || return 1
  STATE=$(fwd "${STATE%$'\r'}")
  TREE=$(git rev-parse 'HEAD^{tree}' 2>/dev/null) || TREE=""
  HEAD_SHA=$(git rev-parse HEAD 2>/dev/null) || HEAD_SHA=""
  [ -n "$TREE" ] && clean_tree && CLEAN_START=true
  full_run=false; if $release || { ! $affected && [ -z "$only_suites" ]; }; then full_run=true; fi
  if $full_run; then
    full_reuse && return 10
    full_lock || return $?
    # Another checkout may have produced this record while we waited.
    full_reuse && return 10
  fi
  # All file-backed commands, including syntax checks, are valid suite_of units.
  while IFS= read -r suite; do suites+=("$suite"); done < <(find tests scripts testlab -type f 2>/dev/null | sort)
  if [ -n "$only_suites" ]; then
    # only a name a run line runs (--list-suites): any other file would be accepted and silently never run
    local listed bad=false; local -a requested
    listed=$(list_suites "${RUNALL_SUITES_FROM:-$RUNALL_SELF}") || { echo "run-all: cannot list the suites" >&2; return 2; }
    IFS=, read -r -a requested <<<"$only_suites"
    for candidate in "${requested[@]}"; do
      found=false
      while IFS= read -r suite; do [ "${suite%$'\r'}" = "$candidate" ] && { found=true; break; }; done <<<"$listed"
      if $found && ! $release && release_only "$candidate"; then
        echo "run-all: release-only suite '$candidate' runs only with --release" >&2; bad=true; continue
      fi
      $found && continue
      echo "run-all: unknown suite '$candidate' (not a suite run-all runs; see --list-suites)" >&2; bad=true
    done
    $bad && return 2
  fi
  if $suite_reuse && ! $release; then
    hash_output=$(python3 -B "${RUNALL_AFFECTED_PY:-tests/affected.py}" hashes "${suites[@]}" 2>/dev/null) || hash_output=""
    while read -r suite hash; do
      suite=${suite%$'\r'}; hash=${hash%$'\r'}
      [ -n "$suite" ] || continue
      HASH_SUITES+=("$suite"); HASHES+=("${hash:--}")
    done <<<"$hash_output"
    CACHE_BEFORE=$(input_snapshot) || CACHE_BEFORE=""
  fi
  # M4/P0: no test may rewrite the shared git config of the repo this runs in (checked at the end). Taken after every
  # early exit and once the full-run lock is held: what other sessions change while this run waits is not this run's.
  gitcfg_snapshot "$ROOT"
}
runall_finish() {
  local path after
  if [ -n "$CACHE_BEFORE" ]; then
    after=$(input_snapshot) || after=""
    if [ "$after" = "$CACHE_BEFORE" ]; then
      for path in "${CACHE_PATHS[@]}"; do
        mkdir -p "${path%/*}" && printf 'PASS\n' > "$path.$$.tmp" && mv "$path.$$.tmp" "$path"
      done
    else echo 'run-all: inputs changed; suite PASS records not published'; fi
  fi
  $full_run && $CLEAN_START && [ -n "$TREE" ] && clean_tree \
    && [ "$(git rev-parse 'HEAD^{tree}')" = "$TREE" ] || return 0
  python3 -B - "$STATE" "$TREE" "$HEAD_SHA" "$pass" "$fail" "$skip" "$t_start" "$jobs" "$use_ws" "$use_claude" "${failures[@]}" <<'PY'
import datetime, json, os, sys, time
state, tree, head, passed, failed, skipped, start, jobs, ws, claude, *names = sys.argv[1:]
r = dict(tree=tree, head=head, counts=dict(pass_=int(passed), fail=int(failed), skip=int(skipped)),
         failed_checks=names, wall_time=int(time.time())-int(start), date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
         flags=dict(jobs=int(jobs), no_workspace=ws!='true', no_claude=claude!='true'))
r['counts']['pass'] = r['counts'].pop('pass_')
os.makedirs(os.path.join(state, 'run-all'), exist_ok=True)
p = os.path.join(state, 'run-all', tree+'.json'); tmp = p+f'.{os.getpid()}.tmp'
with open(tmp, 'w', encoding='utf-8') as f: json.dump(r, f)
os.replace(tmp, p)
PY
}

# sourced (tests/run-all-parallel.test.sh): scheduler and config classifier only, no checks
[ "${BASH_SOURCE[0]}" != "$0" ] && return 0
if $list_only; then list_runnable "${RUNALL_SUITES_FROM:-$RUNALL_SELF}"; exit; fi
runall_prepare; prep_rc=$?
[ "$prep_rc" -eq 10 ] && exit 0
[ "$prep_rc" -eq 0 ] || exit "$prep_rc"

# ---- syntax
# one jq process for every file (a job per file cost about 0.3 s each on Windows); on any error, one line per file
json_files=(); while IFS= read -r f; do json_files+=("$f"); done < <(find . -name '*.json' -not -path './.git/*' | sort)
json_count=${#json_files[@]}
if [ "$json_count" -gt 0 ] && jq empty "${json_files[@]}" >/dev/null 2>&1; then for f in "${json_files[@]}"; do ok "json: $f"; done
else for f in "${json_files[@]}"; do run "json: $f" jq empty "$f"; done; fi
[ "$json_count" -ge 4 ] && ok "json files found: $json_count" || bad "json files found: $json_count (expected >= 4)"
for f in scripts/*.sh scripts/checks/*.sh tests/*.sh; do run "bash -n: $f" bash -n "$f"; done
for f in scripts/*.py scripts/checks/*.py scripts/lib/*.py scripts/lib/guard/*.py testlab/*.py testlab/lab/*.py testlab/tests/*.py; do run "py_compile: $f" python3 -B -W error::SyntaxWarning -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1])" "$f"; done
run "jq compile: scripts/lib/resolve.jq" \
  jq -e --arg repo server --argjson files '[]' --argjson subst '{}' --argjson tools '{}' -f scripts/lib/resolve.jq registry.json
find scripts tests -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- executable bits (as recorded in git when available, else filesystem)
exec_files=(scripts/factory-context.sh scripts/check-registry.sh scripts/git-guard.py scripts/checks/*.py scripts/checks/*.sh tests/*.sh)
declare -A git_mode=()   # one git call for every file
while IFS=$'\t' read -r meta f; do git_mode[$f]=${meta%% *}; done < <(git ls-files -s -- "${exec_files[@]}" 2>/dev/null)
for f in "${exec_files[@]}"; do
  mode=${git_mode[$f]:-}
  if [ "$mode" = "100755" ] || { [ -z "$mode" ] && [ -x "$f" ]; }; then ok "executable: $f"
  else bad "executable: $f" "git mode=${mode:-untracked}"; fi
done

# ---- manifest consistency
name=$(jq -r .name .claude-plugin/plugin.json)
mname=$(jq -r '.plugins[0].name' .claude-plugin/marketplace.json)
msrc=$(jq -r '.plugins[0].source' .claude-plugin/marketplace.json)
[ "$name" = "rpg-factory" ] && [ "$mname" = "$name" ] && [ "$msrc" = "./" ] \
  && ok "manifest: plugin.json name == marketplace entry, source ./" \
  || bad "manifest consistency" "plugin=$name marketplace=$mname source=$msrc"
ver=$(jq -r .version .claude-plugin/plugin.json); mver=$(jq -r '.plugins[0].version // empty' .claude-plugin/marketplace.json)
fver=$(tr -d '[:space:]' < VERSION 2>/dev/null)
rver=$(sed -n 's/^Version \([0-9][0-9.]*\) (see `VERSION`).*/\1/p' README.md)
# Codex packaging, when present: .codex-plugin/plugin.json must carry the version; the Codex marketplace only if it has one
cver=$ver; [ -f .codex-plugin/plugin.json ] && cver=$(jq -r '.version // "none"' .codex-plugin/plugin.json 2>/dev/null || echo invalid)
cmver=""; [ -f .agents/plugins/marketplace.json ] && cmver=$(jq -r '[.version?, (.plugins[]? | select(.name == "rpg-factory") | .version?)]
  | map(select(. != null)) | unique | join(",")' .agents/plugins/marketplace.json 2>/dev/null || echo invalid)
{ [ "$ver" = "$fver" ] && [ -z "$mver" -o "$mver" = "$ver" ] && grep -q "^## \[$ver\]" CHANGELOG.md && [ "$rver" = "$ver" ] \
  && [ "$cver" = "$ver" ] && [ -z "$cmver" -o "$cmver" = "$ver" ]; } \
  && ok "version: VERSION == plugin.json == marketplace == CHANGELOG section == README == Codex manifest/marketplace when present ($ver)" \
  || bad "version consistency" "VERSION=$fver plugin=$ver marketplace=$mver README=${rver:-none} codex=$cver codex-marketplace=${cmver:-none} changelog section missing?"
# release policy wording: tags and releases are the lead's by default and the agent's only with explicit release
# authorization in the current task - no authoritative text may state the absolute "agents never tag" rule again
policy_files=(.claude/CLAUDE.md README.md registry.json skills/factory-core/SKILL.md skills/factory-core/references/git-safety.md
              skills/factory-core/references/skill-contract.md skills/unity-package/SKILL.md scripts/git-guard.py scripts/lib/gitguard.py scripts/lib/guard/*.py
              scripts/lib/context.py scripts/lib/procrun.py scripts/lib/snapshot_render.py
              .claude-plugin/plugin.json .claude-plugin/marketplace.json)
absolute=$(grep -nE -i "agents never tag|never create the tag|tags are never (done|created) by agents|never tag, never publish|; never tag\b" "${policy_files[@]}" 2>/dev/null)
missing=$(for f in .claude/CLAUDE.md README.md registry.json skills/factory-core/references/git-safety.md skills/factory-core/references/skill-contract.md skills/unity-package/SKILL.md; do
  grep -qiE "explicit(ly)? (release authorization|authoriz)" "$f" || echo "$f"; done)
[ -z "$absolute$missing" ] && ok "release policy: default READY_TO_TAG, tag/release only with explicit authorization (${#policy_files[@]} files)" \
  || bad "release policy wording" "absolute 'never tag' text: ${absolute:-none}; no authorization rule in: ${missing:-none}"
# since 1.0.3 the hooks are advisory only: agent-facing text must not claim they deny, block or enforce
advisory_files=(.claude/CLAUDE.md README.md scripts/lib/context.py scripts/lib/snapshot_render.py scripts/factory-context.sh commands/*.md skills/*/SKILL.md skills/*/references/*.md)
blocking=$(grep -nE -i "denied by the guard|hooks enforce|\(deny\)|enforced by (both|the) (guards?|hooks)" "${advisory_files[@]}" 2>/dev/null)
[ -z "$blocking" ] && ok "advisory wording: no 'denied by the guard' / 'hooks enforce' / '(deny)' in agent-facing text (${#advisory_files[@]} files)" \
  || bad "advisory wording (hooks never block since 1.0.3)" "$blocking"
[ -f "skills/factory-core/SKILL.md" ] && head -5 skills/factory-core/SKILL.md | grep -q '^name: factory-core$' \
  && ok "skill: factory-core frontmatter name" || bad "skill: factory-core frontmatter name"
for ref in $(grep -o 'references/[a-z-]*\.md' skills/factory-core/SKILL.md | sort -u); do
  [ -f "skills/factory-core/$ref" ] && ok "skill reference exists: $ref" || bad "skill reference missing: $ref"
done
jq -e '(.hooks.PreToolUse[0].matcher == "Bash|PowerShell")
        and ([.hooks.PreToolUse[0].hooks[].command] | any(test("git-guard.py")))
        and ([.hooks.PreToolUse[] | select(.matcher == "Skill") | .hooks[].command] | any(test("factory_session.py\" --skill")))
        and ([.hooks.SessionStart[0].hooks[].command] | any(test("install-status.py\" --session")))
        and ([.. | .command? // empty] | all(test("tripwire") | not))
        and ([.. | .command? // empty] | length >= 4 and all(endswith("; exit 0")))' hooks/hooks.json >/dev/null \
  && ok "hooks: guard on Bash|PowerShell, skill order on Skill, session install check, no tripwire, every command fail-safe (; exit 0)" || bad "hooks wiring"
# exit 2 is Claude Code's blocking code (python exits 2 on a missing script): a missing or crashing hook script
# must exit 0 and its stdout must still reach Claude Code
HT=$(mktemp_win); mkdir -p "$HT/missing/scripts" "$HT/broken/scripts"
for f in $(jq -r '[.. | .command? // empty | capture("scripts/(?<f>[a-z_-]+\\.py)").f] | unique[]' hooks/hooks.json); do
  printf 'import sys\nprint("{\\"marker\\": \\"%s\\"}")\nsys.exit(2)\n' "$f" > "$HT/broken/scripts/$f"
done
hfail=""
while IFS= read -r h; do
  out=$(CLAUDE_PLUGIN_ROOT="$HT/missing" bash -c "$h" </dev/null 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && [ -z "$out" ] || hfail+="missing script rc=$rc: $h"$'\n'
  out=$(CLAUDE_PLUGIN_ROOT="$HT/broken" bash -c "$h" </dev/null 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && grep -q '"marker"' <<<"$out" || hfail+="exit-2 script rc=$rc stdout='$out': $h"$'\n'
done < <(jq -r '.. | .command? // empty' hooks/hooks.json)
rm -rf "$HT"
[ -z "$hfail" ] && ok "hooks: a missing or exit-2 script never blocks (exit 0, stdout passes through)" || bad "hooks fail-safe" "$hfail"

# ---- testlab (pure parts: scenarios, plan expansion, analysis checks; no stack, no Unity)
run "testlab: unit tests" python3 -B testlab/tests/test_lab.py
run "testlab: packet impairment (S18) unit tests" python3 -B testlab/tests/test_netem.py
run "testlab: native game server mode unit tests" python3 -B testlab/tests/test_native.py
run "testlab: failure-summary unit tests" python3 -B testlab/tests/test_failsum.py
run "testlab: harness defects H1-H7 (M4) unit tests" python3 -B testlab/tests/test_m4_harness.py
run "testlab: frame GC columns (UCF F-21) unit tests" python3 -B testlab/tests/test_framegc.py
run "testlab: scenarios load" python3 -B testlab/testlab.py list
find testlab -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- registry
run "registry structure" scripts/check-registry.sh --structure-only
run "registry domain rules + optional repos" tests/check-registry.test.sh
if $use_ws; then runl "registry paths exist in workspace" scripts/check-registry.sh
else skp "registry paths exist in workspace" "--no-workspace"; fi

# ---- git guard, skill contract lint, routing (task + historical replay)
run "cross-platform helpers + UTF-8 output (Linux, WSL, Windows git-bash)" env -u TMPDIR tests/compat.test.sh
run "git-guard unit tests" tests/git-guard.test.sh
run "skills lint (contract)" tests/skills-lint.sh
run "line budget (gitguard.py, context.py, run-checks.py under 500 lines; self-test at 499/500)" tests/line-budget.test.sh
run "English-only fixture cases" env -u TMPDIR tests/english-only.test.sh
run "English-only enforcement (report available)" python3 -B scripts/checks/english-only.py --enforce
run "session state + tripwire removed (state paths, stale latch files inert)" env -u TMPDIR tests/session-state.test.sh
run "file guard (Write/Edit/MultiEdit/NotebookEdit/Read)" env -u TMPDIR tests/file-guard.test.sh
run "hook cost (no git guard on Read, bytecode in the state dir, gitlinks cache, python3 alias)" env -u TMPDIR tests/hook-perf.test.sh
run "slash commands (files, parsing, invocation)" env -u TMPDIR tests/commands.test.sh
run "UI component catalog + selection (UIToolkit git fixture, refs, NOT_AVAILABLE)" env -u TMPDIR tests/ui-catalog.test.sh
run "UI plan commands (intent, skills per verb, NOT_UI, NEEDS_CONTEXT, Figma URL)" env -u TMPDIR tests/ui-commands.test.sh
run "UI plan routing, golden matrix, component selection (fixture workspace)" env -u TMPDIR tests/ui-skill-routing.test.sh
run "UI skills content, docs, snapshot Next line for UI paths (fixture workspace)" env -u TMPDIR tests/ui-skills.test.sh
run "dev tools + services (probes, snapshot, doctor, no secrets, registry checks)" env -u TMPDIR tests/devtools.test.sh
run "Figma connector environment check (fixture Unity projects, no network)" env -u TMPDIR tests/ui-figma-env.test.sh
run "worktree-aware context" tests/worktree.test.sh
run "check runner state model" tests/run-checks.test.sh
run "artifact contract, lifecycle, trace and approval fixtures" tests/artifacts.test.sh
run "run-checks targets the invoking worktree, writes no pyc, guards the canonical checkout" tests/worktree-target.test.sh
run "candidate tree checks" tests/checks-candidate.test.sh
run "factory-status rollout / resume fixture" tests/factory-status.test.sh
run "install-status stale-install detection" tests/install-status.test.sh
run "release-check gate (throwaway repo, local bare origin)" env -u TMPDIR tests/release-check.test.sh
run "delivery pipeline (tier, plan, dispatch, verdicts, gate)" env -u TMPDIR tests/pipeline.test.sh
run "run-all --affected suite selection" tests/affected.test.sh
run "run-all -j scheduler (order, counts, concurrency cap, live lane, run1 alone)" tests/run-all-parallel.test.sh
run "changelog fragments (changelog.d, scripts/changelog.py; [Unreleased] stays empty)" tests/changelog.test.sh
run "registry fragments (registry/ -> registry.json build, placement, merge)" tests/registry-fragments.test.sh
# Codex packaging (.codex-plugin, .agents/plugins, hooks/codex-hooks.json, scripts/codex_hook.py)
codex_post() { # rc output
  local cxsum cxpass; cxsum=$(tail -1 <<<"$2"); cxpass=$(sed -n 's/.*, \([0-9]*\) passed,.*/\1/p' <<<"$cxsum")
  if [ "$1" -ne 0 ]; then _bad "Codex plugin: manifest, marketplace, hook config, adapter" "$2"
  elif [ "${cxpass:-0}" -eq 0 ]; then _skp "Codex plugin: manifest, marketplace, hook config, adapter" "${cxsum#codex-plugin tests: }: Codex packaging files absent"
  else _ok "Codex plugin: manifest, marketplace, hook config, adapter (${cxsum#codex-plugin tests: })"; fi
}
runp "Codex plugin" codex_post env -u TMPDIR tests/codex-plugin.test.sh
run "skill citation checker (fixture repos)" env -u TMPDIR tests/skill-citations.test.sh
run "engineering routing contract unchanged (golden, stand-in workspace)" env -u TMPDIR tests/routing-golden.test.sh
run "repos without a remote do not crash status or the git guard" env -u TMPDIR tests/registry-nulls.test.sh
  run "domain and artifact-kind routing (stand-in workspace)" env -u TMPDIR tests/domains-routing.test.sh
  run "Game Design domain: routing, feature-state ownership, standalone (no game-ai-workflows)" env -u TMPDIR tests/domains.test.sh
run "Game Design production workflow" tests/design-workflow.test.sh
run "dogfood write grader (offline, recorded transcripts)" tests/dogfood-grader.test.sh
run "UI/UX production workflow" tests/ui-workflow.test.sh
run "2D Art production workflow" tests/art2d-workflow.test.sh
run "3D Art production workflow" tests/art3d-workflow.test.sh
run "VFX production workflow" tests/vfx-workflow.test.sh
run "asset-gen engine, core templates, image QA, gen-run quality plugin (temp authoring repo, no network)" env -u TMPDIR tests/assetgen.test.sh
run "netcode-headless server resolution (fixture repos)" env -u TMPDIR tests/netcode-headless.test.sh
run "skill scaffolder + touchpoints (throwaway plugin copy)" env -u TMPDIR tests/new-skill.test.sh
run "parallel-work policy lint bites (throwaway plugin copy)" env -u TMPDIR tests/parallel-policy.test.sh
if ! $use_ws; then skp "orca commands cited in parallel-work.md" "--no-workspace"
elif ! command -v orca >/dev/null 2>&1; then skp "orca commands cited in parallel-work.md" "orca not on PATH"
else run "orca commands cited in parallel-work.md exist in orca --help" tests/orca-commands.test.sh; fi
# ---- live workspace (read-only): runl / block - with -j N in the background next to the fixture suites, one at a time
if $use_ws; then runl "routing properties over real history" python3 -B tests/routing-properties.test.py
else skp "routing properties over real history" "--no-workspace"; fi
if $use_ws; then runl "registry facts re-probed in the repos" tests/facts.test.sh
else skp "registry facts re-probed in the repos" "--no-workspace"; fi
live_citations() {  # MOVED (anchor unique elsewhere) is a warning here and a failure under --release
  local cit citrc l
  if $release; then run "skill line citations point at their symbols (integration branches, --strict)" python3 -B scripts/checks/skill-citations.py --strict
  else
    cit=$(python3 -B scripts/checks/skill-citations.py 2>&1); citrc=$?
    if [ $citrc -ne 0 ]; then bad "skill line citations point at their symbols (integration branches)" "$cit"
    else ok "skill line citations point at their symbols (integration branches)"
      while IFS= read -r l; do note "WARN  moved citation: ${l#MOVED }"; done < <(grep '^MOVED ' <<<"$cit")
      grep -q '^MOVED ' <<<"$cit" && note "WARN  rewrite moved citations: python3 -B scripts/checks/skill-citations.py --fix (fails under --release)"
    fi
  fi
}
if $use_ws; then gated scripts/checks/skill-citations.py && block live_citations
else skp "skill line citations against the repos" "--no-workspace"; fi
if $use_ws; then runl "routing + history replay" tests/routing.test.sh
else
  # task scenarios resolve --paths only, but factory-context still needs the workspace markers and a git
  # work tree per registry repo: a throwaway stand-in (empty repos), never the real workspace
  SW=$(mktemp_win)
  while IFS= read -r p; do
    git init -q "$SW/$p" && git -C "$SW/$p" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  done < <(jq -r '.repos[].path' registry.json)
  while IFS= read -r m; do mkdir -p "$SW/$(dirname "$m")"; touch "$SW/$m"; done < <(jq -r '.workspace.root_markers[]' registry.json)
  run "routing (task scenarios only, stand-in workspace)" env RPG_FACTORY_WORKSPACE="$SW" tests/routing.test.sh --no-history
  cleanup+=("$SW")  # removed after the last suite ended (with -j N this one may still be running)
fi

# ---- resolver behaviour (pure jq, no workspace needed)
resolve() { # repo files-json
  jq -c --arg repo "$1" --argjson files "$2" --argjson subst '{"{dotnet}":"dotnet.exe","{plugin_root}":"/p"}' \
    --argjson tools '{"go":"/usr/bin/go","dotnet":"/x/dotnet.exe","python3":"/usr/bin/python3","protoc":"/usr/bin/protoc","protoc-gen-go":"/x","jq":"/usr/bin/jq","docker":null}' \
    -f scripts/lib/resolve.jq registry.json
}
expect() { # name jq-predicate json
  if jq -e "$2" <<<"$3" >/dev/null 2>&1; then ok "resolve: $1"; else bad "resolve: $1" "$(jq -c '{touched,dependents,unmapped}' <<<"$3")"; fi
}
r=$(resolve server '[{"path":"backend/shared/proto/wire.proto","status":"--","source":"given"}]')
expect "wire.proto -> server.proto (longest prefix)" '.touched == ["server.proto"]' "$r"
expect "wire.proto dependents include C# server + integration" '(.dependents | index("server.gameserver-dotnet")) and (.dependents | index("server.integration-test"))' "$r"
expect "proto triggers proto-regen extended check" 'any(.checks[]; .id == "proto-regen" and .tier == "extended")' "$r"
r=$(resolve server '[{"path":"backend/gateway/internal/redirect.go","status":" M","source":"worktree"}]')
expect "gateway fast checks = vet+test+build" '[.checks[] | select(.tier=="fast" and .module=="server.gateway") | .id] == ["go-vet","go-test","go-build"]' "$r"
expect "gateway dependents = integration only" '.dependents == ["server.integration-test"]' "$r"
r=$(resolve server '[{"path":"backend/gameserver-dotnet/GameServer/Program.cs","status":" M","source":"worktree"}]')
expect "{dotnet} substituted" 'any(.checks[]; .run == "dotnet.exe build -c Release")' "$r"
r=$(resolve server '[{"path":"backend/gameserver-dotnet/GameServer/Net/Generated/Wire.cs","status":" M","source":"worktree"}]')
expect "generated path flagged" '.generated_hits | length == 1' "$r"
r=$(resolve client '[{"path":"Assets/Samples/Netcode/DOTS Sample/Scripts/A.cs","status":" M","source":"worktree"},{"path":"Assets/Samples/Cuvara UI Toolkit/","status":"??","source":"worktree"},{"path":"Packages/com.gdk.core","status":" M","source":"worktree"},{"path":"weird/file.txt","status":"??","source":"worktree"}]')
expect "DOTS Sample beats Assets/Samples" '.files[0].module == "client.dots-sample"' "$r"
expect "untracked sample dir -> samples-imported" '.files[1].module == "client.samples-imported"' "$r"
expect "submodule pointer -> gdk-submodules" '.files[2].module == "client.gdk-submodules"' "$r"
expect "unknown path -> repo-level (client.root), not unmapped" '.unmapped == [] and .repo_level == ["weird/file.txt"]' "$r"
expect "{plugin_root} substituted in package-pins" 'any(.checks[]; .run == "python3 -B /p/scripts/checks/unity-package-pins.py .")' "$r"
r=$(resolve server '[]')
expect "no files -> no checks" '.checks == [] and .touched == []' "$r"

# ---- live context script (read-only against the real workspace)
live_context() {
  local out out2 md
  # every registered repo is snapshotted, except optional repos that are absent on disk, which are reported
  if out=$(scripts/factory-context.sh --json 2>&1) && jq -e --slurpfile reg registry.json '
      ([.repos[].repo] + (.optional_repos_absent // [])) as $seen
      | ($seen | sort) == ($reg[0].repos | keys | sort)
        and all((.optional_repos_absent // [])[]; $reg[0].repos[.].optional == true)' <<<"$out" >/dev/null; then
    ok "factory-context --json: every registered repo (absent optional repos reported)"
    jq -e 'all(.repos[]; .error == null and (.branch | length) > 0)' <<<"$out" >/dev/null \
      && ok "factory-context: branch resolved for each repo" || bad "factory-context: branch per repo" "$out"
    out2=$(scripts/factory-context.sh --repo server --json --paths backend/gameserver-dotnet/GameServer/Program.cs 2>&1)
    jq -e 'any(.toolchain[]; .tool == "dotnet" and .resolved != null)' <<<"$out2" >/dev/null \
      && ok "factory-context: dotnet resolved lazily for a .NET change ($(jq -r '.toolchain[] | select(.tool=="dotnet") | .resolved' <<<"$out2"))" \
      || bad "factory-context: dotnet not resolved (dotnet / dotnet.exe)"
  else
    bad "factory-context --json" "$out"
  fi
  out=$(scripts/factory-context.sh --repo server --json --paths backend/gateway/x.go 2>&1)
  jq -e '.repos[0].touched == ["server.gateway"] and (.repos[0].files | length == 1)' <<<"$out" >/dev/null \
    && ok "factory-context --paths ignores working tree" || bad "factory-context --paths" "$out"
  scripts/factory-context.sh --paths x >/dev/null 2>&1; [ $? -eq 2 ] \
    && ok "factory-context --paths without --repo is rejected" || bad "factory-context --paths without --repo"
  md=$(scripts/factory-context.sh --repo client 2>&1)
  grep -q "^## client:" <<<"$md" && ok "factory-context markdown renders" || bad "factory-context markdown" "$md"
}
if $use_ws; then gated scripts/factory-context.sh && block live_context
else skp "factory-context live checks" "--no-workspace"; fi

# ---- sgl-determinism (ADR-10) against fixtures: banned calls fail, comments/strings/allowed MathF pass
dt=$(mktemp_win)
printf '%s\n' 'class A {' '  float F(float x) => MathF.Sqrt(x) + MathF.Abs(x); // MathF.Sin(x) in a comment' \
  '  string S = "Math.Pow(1, 2)";' '}' > "$dt/Ok.cs"
out=$(python3 -B scripts/checks/sgl-determinism.py "$dt" 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "^OK: sgl-determinism files=1 banned=0" <<<"$out" \
  && ok "sgl-determinism: allowed MathF, comments and strings pass" || bad "sgl-determinism allowed fixture" "$out"
printf '%s\n' 'class B {' '  float G(float x) => MathF.Atan2(x, 1f);' '  double H(double y) => System.Math.Pow(y, 2);' '}' > "$dt/Bad.cs"
out=$(python3 -B scripts/checks/sgl-determinism.py "$dt" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "Bad.cs:2: MathF.Atan2" <<<"$out" && grep -q "Bad.cs:3: Math.Pow" <<<"$out" \
  && ok "sgl-determinism: banned calls fail with path:line" || bad "sgl-determinism banned fixture" "$out"
rm -f "$dt"/*.cs
python3 -B scripts/checks/sgl-determinism.py "$dt" >/dev/null 2>&1; [ $? -eq 2 ] \
  && ok "sgl-determinism: empty directory is an error, not a pass" || bad "sgl-determinism empty dir"
rm -rf "$dt"

# ---- Factory check scripts against the live workspace (read-only)
live_checks() {
  local wsr cl pin_files out hout ph r p rc
  run "sgl-determinism on Shared.GameLogic" python3 -B scripts/checks/sgl-determinism.py \
    "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/rpg-mmo-server/backend/gameserver-dotnet/Shared.GameLogic"
  # pin-status reads the client's working tree. When the user has uncommitted pin files (the local file:
  # toggle is a human gate and their state), a live FAIL says nothing about this plugin: then verify the
  # committed HEAD through a read-only export and report SKIP with the reason - never PASS.
  wsr="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"; cl="$wsr/IndieRPGMMOAdventure"
  pin_files=(Packages/manifest.json Packages/packages-lock.json "Assets/Samples/Netcode/DOTS Sample/.sample-source")
  if ! gated scripts/checks/pin-status.py; then :
  elif out=$(python3 -B scripts/checks/pin-status.py 2>&1); then ok "pin-status (client pins vs upstream tags)"
  elif [ -n "$(git -C "$cl" status --porcelain -- "${pin_files[@]}" 2>/dev/null)" ]; then
    ph=$(mktemp_win); mkdir -p "$ph/ws/IndieRPGMMOAdventure"
    git -C "$cl" archive HEAD -- "${pin_files[@]}" | tar -x -C "$ph/ws/IndieRPGMMOAdventure"
    for r in Netcode UnityDots UIToolkit rpg-mmo-server; do
      [ -d "$wsr/$r/.git" ] && git clone -q --shared --no-checkout "$wsr/$r" "$ph/ws/$r"; done
    if hout=$(python3 -B scripts/checks/pin-status.py --workspace "$ph/ws" 2>&1); then
      skp "pin-status on the live tree" "client pin files have uncommitted user changes; committed HEAD: $(tail -1 <<<"$hout")"
    else bad "pin-status (committed HEAD, live tree also has user changes)" "$hout"; fi
    rm -rf "$ph"
  else bad "pin-status (client pins vs upstream tags)" "$out"; fi
  run "wire-parity (Wire.cs bytes + protocol version)" bash scripts/checks/wire-parity.sh
  if gated scripts/checks/pin-plan.py; then
    out=$(python3 -B scripts/checks/pin-plan.py com.cuvara.netcode v0.45.0 --client-ref 17b7737^ 2>&1)
    grep -q "hash=2eb6ddbc4e0c62544fa860b3a4f7e64071918f0b" <<<"$out" && grep -q "DOTSNetworkBridge.cs" <<<"$out" \
      && ok "pin-plan replays 17b7737 (lock hash + DOTS Sample file)" || bad "pin-plan replay of 17b7737" "$out"
    out=$(python3 -B scripts/checks/pin-plan.py com.cuvara.dots v99.0.0 2>&1); rc=$?
    [ $rc -eq 1 ] && grep -q "BLOCKED: tag v99.0.0 not found" <<<"$out" && ok "pin-plan blocks on a missing tag" || bad "pin-plan missing-tag gate" "$out"
  else not_affected   # two pin-plan checks: gated counted the first
  fi
  for p in Netcode UnityDots UIToolkit; do
    gated scripts/checks/package-ready.py || continue
    out=$(python3 -B scripts/checks/package-ready.py "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/$p" 2>&1); rc=$?
    { [ $rc -eq 0 ] && grep -q "READY to tag" <<<"$out"; } || { [ $rc -eq 1 ] && grep -q "NOT READY" <<<"$out"; } \
      && ok "package-ready $p -> $(grep -m1 -oE 'NOT READY|READY to tag v[0-9.]+' <<<"$out")" || bad "package-ready $p" "$out"
  done
  if ! gated scripts/checks/netcode-headless.sh; then :
  elif command -v dotnet >/dev/null 2>&1 || command -v dotnet.exe >/dev/null 2>&1; then
    out=$(bash scripts/checks/netcode-headless.sh 2>&1); rc=$?
    [ $rc -eq 0 ] && ok "netcode headless tests: $(sed -n 's/^headless tests: //p' <<<"$out")" || bad "netcode headless tests" "$(tail -5 <<<"$out")"
  else skp "netcode headless tests" "no dotnet/dotnet.exe"; fi
}
$use_ws && block live_checks

# ---- live derived status + install state
if $use_ws; then
  runl "factory-status on the real workspace (read-only)" python3 -B scripts/factory-status.py
fi
ist=$(python3 -B scripts/install-status.py --json 2>/dev/null | jq -r .state)
if $release; then
  [ "$ist" = "CURRENT" ] && ok "installed plugin == source (release gate)" || bad "installed plugin == source (release gate)" "$(python3 -B scripts/install-status.py)"
  [ -z "$(git status --porcelain)" ] && ok "source is committed (release gate)" || bad "source is committed (release gate)" "uncommitted changes"
  run1 "safety through the installed hooks (disposable workspace)" env -u TMPDIR tests/installed-safety.sh
else
  skp "installed plugin == source" "install state $ist; required only with --release"
fi

# ---- package pins checker behaviour
T=$(mktemp_win); mkdir -p "$T/Packages"
echo '{"dependencies":{"a":"https://x/a.git#v1","b":"1.0.0"}}' > "$T/Packages/manifest.json"
echo '{"dependencies":{"a":{"version":"https://x/a.git#v1"}}}' > "$T/Packages/packages-lock.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && ok "package-pins: agreeing pins pass" || bad "package-pins: agreeing pins pass"
echo '{"dependencies":{"a":{"version":"https://x/a.git#v0"}}}' > "$T/Packages/packages-lock.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: mismatch must fail" || ok "package-pins: mismatch fails"
echo '{"dependencies":{"a":"file:/mnt/c/x"}}' > "$T/Packages/manifest.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: file: must fail" || ok "package-pins: file: path fails"
echo '{"dependencies":{"b":"1.0.0"}}' > "$T/Packages/manifest.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: empty selection must fail" || ok "package-pins: zero git deps fails"
rm -rf "$T"

# ---- package-ready: when git cannot read the tree, readiness is unknown (exit 2), never READY
T=$(mktemp_win)
printf '{"name":"com.cuvara.netcode","version":"9.9.9"}\n' > "$T/package.json"; printf '## [9.9.9] - 2026-01-01\n' > "$T/CHANGELOG.md"
out=$(GIT_CEILING_DIRECTORIES="$T" python3 -B scripts/checks/package-ready.py "$T" 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q "readiness unknown" <<<"$out" && ! grep -q "READY to tag" <<<"$out" \
  && ok "package-ready: unreadable git tree is an error, not READY" || bad "package-ready on a non-repo (rc=$rc)" "$out"
rm -rf "$T"

# ---- alone (run1): the shared git config guard suite, then Claude Code's own validator
run1 "git environment isolation + shared-config guard (throwaway repos)" env -u TMPDIR tests/git-env-isolation.test.sh
if $use_claude && command -v claude >/dev/null 2>&1; then
  run1 "claude plugin validate --strict . (marketplace)" claude plugin validate --strict .
  run1 "claude plugin validate --strict .claude-plugin/plugin.json (plugin + skills)" claude plugin validate --strict .claude-plugin/plugin.json
else
  skp "claude plugin validate" "claude CLI unavailable or --no-claude"
fi

drain
[ -n "$QD" ] && rm -rf "$QD"
[ ${#cleanup[@]} -gt 0 ] && rm -rf "${cleanup[@]}"
find scripts tests testlab -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- the shared git config (common dir) must be byte-identical to what it was when the run started
if [ -n "${GITCFG_FILE:-}" ]; then
  if out=$(gitcfg_verify); then ok "shared git config unchanged during the run"
  elif [ -n "${GITCFG_COPY:-}" ] && [ "$(gitcfg_classify "$GITCFG_COPY" "$GITCFG_FILE")" = WARN ]; then
    note "WARN  shared git config: only other sessions' branch/worktree sections were added during the run"
    note "$(diff -u "$GITCFG_COPY" "$GITCFG_FILE" | sed 's/^/      /')"
  else GITCFG_KEEP=1; bad "shared git config changed during the run" "$out"; fi
else skp "shared git config unchanged during the run" "not inside a git repository"; fi

runall_finish
total=$((pass + fail + skip))
echo "----"
echo "wall time: $(( $(date +%s) - t_start ))s (-j $jobs)"
echo "run-all: $total checks, $pass passed, $fail failed, $skip skipped$( [ -n "$AFF$only_suites" ] && echo " ($naff not affected by the change)")"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
