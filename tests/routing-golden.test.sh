#!/usr/bin/env bash
# Engineering routing contract is frozen: every task scenario of tests/routing.test.sh, resolved on a
# throwaway stand-in workspace, must give the same lead / co-leads / legs / follow-ups / tech / ambiguous,
# touched modules and check ids as tests/fixtures/routing-golden.json (recorded before domain metadata).
# Added fields (e.g. routing.domain) are ignored by construction; anything else that moves is a FAIL.
#
# Usage: tests/routing-golden.test.sh [--update]   (--update rewrites the golden file; review the diff)
# --update keeps the host-dependent scenarios this host cannot evaluate (see merge_golden); the merge and the
# comparison are functions with a self-test on small fixtures that never touches the real golden file.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GOLDEN="$ROOT/tests/fixtures/routing-golden.json"
ROUTING_TEST="$ROOT/tests/routing.test.sh"
TMP="$(mktemp_win)" || exit 1; trap 'rm -rf "$TMP"' EXIT
SW="$TMP/ws"

# "absolute path (...)" scenarios depend on the host's path forms (C:/, /c/, /mnt/c/ exist only on Windows);
# tests/routing.test.sh asserts their lead on every platform, so they are kept out of the cross-platform comparison
PLATFORM='with_entries(select(.key | startswith("absolute path (") | not))'

# host_dependent_names <routing.test.sh>: the names of the host-dependent scenarios the suite declares (one per line).
# A scenario deleted from the suite is not listed, so --update drops it like any other removed scenario.
host_dependent_names() {
  grep -o 'assert "absolute path ([^"]*"' "$1" 2>/dev/null | sed 's/^assert "//; s/"$//' | tr -d '\r'
}

# merge_golden <current.json> <golden.json> <declared-names-file>: the file --update writes. Everything this run
# recorded, plus the golden's declared host-dependent scenarios this run did not record (this host cannot evaluate
# them: the cygpath and /mnt/c/ forms exist only on Windows). The current run wins when it recorded a scenario; an
# ordinary scenario missing from the current run, or a host-dependent name no longer declared, is dropped.
merge_golden() {
  local old="$2"
  [ -f "$old" ] || { old="$TMP/empty-golden.json"; echo '{}' > "$old"; }
  jq -S -n --slurpfile cur "$1" --slurpfile old "$old" --argjson decl "$(jq -Rn '[inputs | select(length > 0)]' < "$3")" \
    '($old[0] | with_entries(select(.key as $k | $decl | index($k) != null))) + $cur[0]'
}

# golden_diff <golden.json> <current.json> <diff-out>: 0 when the cross-platform contract is identical
# (host-dependent scenarios are ignored on both sides)
golden_diff() {
  jq -S "$PLATFORM" "$1" > "$3.golden" && jq -S "$PLATFORM" "$2" > "$3.current" &&
    diff -u "$3.golden" "$3.current" > "$3"
}

selftest_pass=0; selftest_fail=0
st() { # st <name> <command...>: PASS when the command succeeds
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then selftest_pass=$((selftest_pass + 1)); echo "PASS  $name"
  else selftest_fail=$((selftest_fail + 1)); echo "FAIL  $name"; fi
}
st_not() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then selftest_fail=$((selftest_fail + 1)); echo "FAIL  $name"; else selftest_pass=$((selftest_pass + 1)); echo "PASS  $name"; fi; }
selftest() {
  local d="$TMP/selftest"; mkdir -p "$d"
  cat > "$d/routing.sh" <<'EOS'
assert "ordinary scenario" server "x" a
  assert "absolute path (cygpath form) routes" server "x" a
    assert "absolute path (WSL form) routes" server "x" a
# assert "not an absolute path scenario" server "x" a
EOS
  printf '%s\n' 'absolute path (cygpath form) routes' 'absolute path (WSL form) routes' > "$d/declared.txt"
  st "declared host-dependent names are read from the suite source" \
    test "$(host_dependent_names "$d/routing.sh" | tr '\n' '|')" = 'absolute path (cygpath form) routes|absolute path (WSL form) routes|'
  st "the real routing suite still declares its host-dependent scenarios (WSL and cygpath forms included)" \
    bash -c "$(declare -f host_dependent_names); n=\$(host_dependent_names '$ROUTING_TEST'); echo \"\$n\" | grep -q 'WSL /mnt/c/ form' && echo \"\$n\" | grep -q 'git-bash /c/ form'"
  echo '{"kept":[{"v":"new"}],"absolute path (cygpath form) routes":[{"v":"new"}]}' > "$d/cur.json"
  cat > "$d/old.json" <<'EOS'
{"kept":[{"v":"old"}],"gone":[{"v":"old"}],
 "absolute path (cygpath form) routes":[{"v":"old"}],
 "absolute path (WSL form) routes":[{"v":"old"}],
 "absolute path (deleted from the suite)":[{"v":"old"}]}
EOS
  merge_golden "$d/cur.json" "$d/old.json" "$d/declared.txt" > "$d/merged.json"
  st "update: a host-dependent scenario missing from the current run survives" jq -e '.["absolute path (WSL form) routes"] == [{"v":"old"}]' "$d/merged.json"
  st "update: a host-dependent scenario recorded by this run takes the new record" jq -e '.["absolute path (cygpath form) routes"] == [{"v":"new"}]' "$d/merged.json"
  st "update: an ordinary scenario is rewritten from the current run" jq -e '.kept == [{"v":"new"}]' "$d/merged.json"
  st "update: an ordinary removed scenario is dropped" jq -e 'has("gone") | not' "$d/merged.json"
  st "update: a host-dependent scenario no longer in the suite is dropped" jq -e 'has("absolute path (deleted from the suite)") | not' "$d/merged.json"
  merge_golden "$d/cur.json" "$d/missing.json" "$d/declared.txt" > "$d/fresh.json"
  st "update: without a golden file the merge is the current run" jq -e '. == {"kept":[{"v":"new"}],"absolute path (cygpath form) routes":[{"v":"new"}]}' "$d/fresh.json"
  echo '{"a":[{"lead":"x"}]}' > "$d/g.json"; echo '{"a":[{"lead":"x"}],"absolute path (WSL form) routes":[{"lead":"y"}]}' > "$d/c-same.json"
  echo '{"a":[{"lead":"z"}]}' > "$d/c-moved.json"; echo '{"a":[{"lead":"x"}],"extra":[{"lead":"x"}]}' > "$d/c-added.json"
  st "compare: an identical contract passes, host-dependent scenarios ignored" golden_diff "$d/g.json" "$d/c-same.json" "$d/diff1"
  st_not "compare: a moved lead fails" golden_diff "$d/g.json" "$d/c-moved.json" "$d/diff2"
  st_not "compare: an added scenario fails" golden_diff "$d/g.json" "$d/c-added.json" "$d/diff3"
}

if [ "${1:-}" != "--update" ]; then
  selftest
  if [ "$selftest_fail" -gt 0 ]; then echo "routing-golden: $selftest_pass passed, $selftest_fail failed"; exit 1; fi
fi

while IFS= read -r p; do
  git init -q "$SW/$p" && git -C "$SW/$p" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
done < <(jq -r '.repos | to_entries[] | select(.value.optional != true) | .value.path' "$ROOT/registry.json")
while IFS= read -r m; do mkdir -p "$SW/$(dirname "$m")"; touch "$SW/$m"; done < <(jq -r '.workspace.root_markers[]' "$ROOT/registry.json")
OUT="$TMP/routing.jsonl"; : > "$OUT"
RPG_FACTORY_WORKSPACE="$SW" ROUTING_GOLDEN_OUT="$OUT" bash "$ROOT/tests/routing.test.sh" --no-history > "$TMP/routing.log" 2>&1
# canonical: one object keyed by scenario name (sorted keys); a name used twice keeps both in order
jq -S -s 'reduce .[] as $s ({}; .[$s.name] += [$s | del(.name)])' "$OUT" > "$TMP/all.json"
jq "$PLATFORM" "$TMP/all.json" > "$TMP/current.json"
n=$(jq 'length' "$TMP/current.json")
if [ "${1:-}" = "--update" ]; then
  host_dependent_names "$ROUTING_TEST" > "$TMP/declared.txt"
  merge_golden "$TMP/all.json" "$GOLDEN" "$TMP/declared.txt" > "$TMP/merged.json" || { echo "FAIL  could not merge the golden file"; exit 1; }
  cp "$TMP/merged.json" "$GOLDEN"
  echo "routing-golden: updated $n scenarios ($(jq 'length' "$TMP/merged.json") in the file, host-dependent ones this host cannot evaluate kept)"; exit 0
fi
[ -f "$GOLDEN" ] || { echo "FAIL  no golden file $GOLDEN"; exit 1; }
# every snapshot prints the Language line, without --full, with the registry report language
LANG_WANT="$(jq -r '.workspace.report_language // "the user'"'"'s language"' "$ROOT/registry.json")"
snap="$(RPG_FACTORY_WORKSPACE="$SW" bash "$ROOT/scripts/factory-context.sh" --repo all 2>&1)"
if grep -qxF "**Language:** write everything in English (files, plans, briefs, messages, commits, PR text); report to the owner in $LANG_WANT." <<<"${snap//$'
'/}"; then
  selftest_pass=$((selftest_pass + 1)); echo "PASS  snapshot without --full prints the Language line ($LANG_WANT)"
else
  selftest_fail=$((selftest_fail + 1)); echo "FAIL  snapshot without --full lacks the Language line"; grep -n 'Language' <<<"$snap" | head -3 | sed 's/^/      /'
fi
if [ "$n" -lt 40 ]; then echo "FAIL  only $n scenarios recorded (expected >= 40)"; tail -5 "$TMP/routing.log"; exit 1; fi
if golden_diff "$GOLDEN" "$TMP/current.json" "$TMP/diff.txt"; then
  echo "PASS  routing contract identical to the golden file ($n scenarios)"
  echo "routing-golden: $((selftest_pass + 1)) passed, $selftest_fail failed"; [ "$selftest_fail" -eq 0 ]; exit $?
fi
echo "FAIL  routing contract changed:"; head -60 "$TMP/diff.txt" | sed 's/^/      /'
echo "routing-golden: $selftest_pass passed, $((selftest_fail + 1)) failed"; exit 1
