#!/usr/bin/env bash
# scripts/ci-plan.py: the CI matrix. Selection is tests/affected.py's (never re-implemented here): one skill file gives
# exactly affected.py's suites; a registry, workflow or CI-plumbing change, a missing or unusable base, a schedule event
# and --full give every suite; every runnable suite is run or skipped with a reason; the OS list follows
# tests/ci-windows-suites.txt, which names only runnable suites; --summary and --github-output are written.
# Changed paths come from --changed-file stand-ins; the base cases use the real repository and explicit shas.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
PLAN="$ROOT/scripts/ci-plan.py"; AFF="$ROOT/tests/affected.py"; WIN="$ROOT/tests/ci-windows-suites.txt"
pass=0; fail=0
good() { pass=$((pass + 1)); echo "PASS  $1"; }
no()  { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -20 | sed 's/^/      /'; }
# pj FILE EXPR: evaluate a python expression over the JSON in FILE (as d) and print the result
pj() { python3 -B -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print(eval(sys.argv[2]))' "$1" "$2"; }
# changed FILE PATH...: a stand-in changed list
changed() { local f="$1"; shift; printf '%s\n' "$@" > "$f"; }

mapfile -t SUITES < <(bash "$ROOT/tests/run-all.sh" --list-suites --no-workspace --no-claude | tr -d '\r')
if [ "${#SUITES[@]}" -gt 10 ]; then good "run-all --list-suites --no-workspace --no-claude lists the runnable suites (${#SUITES[@]})"
else no "run-all --list-suites lists the runnable suites" "got ${#SUITES[@]}"; fi
if printf '%s\n' "${SUITES[@]}" | grep -qx tests/ci-plan.test.sh; then good "run-all --list-suites lists this suite"
else no "run-all --list-suites lists this suite (register it in tests/run-all.sh)"; fi

# 1. one skill file: exactly the suites affected.py select-many gives for it, not full
changed "$TMP/skill" skills/delivery/SKILL.md
python3 -B "$PLAN" --changed-file "$TMP/skill" --event pull_request > "$TMP/skill.json"; rc=$?
want=$(python3 -B "$AFF" select-many "$TMP/skill" "${SUITES[@]}" | tr -d '\r' | LC_ALL=C sort)
got=$(pj "$TMP/skill.json" '"\n".join(sorted(s["suite"] for s in d["suites"]))')
if [ "$rc" = 0 ] && [ "$(pj "$TMP/skill.json" 'd["full"]')" = False ] && [ -n "$want" ] && [ "$got" = "$want" ]; then
  good "one skill file plans exactly affected.py's suites, not full"
else no "one skill file plans exactly affected.py's suites, not full (rc=$rc)" "want [$want] got [$got]"; fi
if [ "$(pj "$TMP/skill.json" 'd["event"]')" = pull_request ] && [ "$(pj "$TMP/skill.json" 'd["changed_files"]')" = 1 ] \
   && [ "$(pj "$TMP/skill.json" 'd["base"]')" = None ]; then good "the plan echoes the event, the changed count and a null base"
else no "the plan echoes the event, the changed count and a null base"; fi

# 2. fail-safe full plans: every suite, cases ALL, a reason
full_case() { # name expected-reason-substring plan-args...
  local name="$1" reason="$2"; shift 2
  python3 -B "$PLAN" "$@" > "$TMP/f.json"; local rc=$?
  local n; n=$(pj "$TMP/f.json" 'len(d["suites"])') k=$(pj "$TMP/f.json" 'len(d["skipped"])') a=$(pj "$TMP/f.json" 'all(s["cases"] == "ALL" for s in d["suites"])')
  local r; r=$(pj "$TMP/f.json" 'd["reason"]')
  if [ "$rc" = 0 ] && [ "$(pj "$TMP/f.json" 'd["full"]')" = True ] && [ "$n" = "${#SUITES[@]}" ] && [ "$k" = 0 ] && [ "$a" = True ] \
     && [[ "$r" == *"$reason"* ]]; then good "$name"
  else no "$name (rc=$rc suites=$n skipped=$k all-ALL=$a)" "reason [$r] want [*$reason*]"; fi
}
changed "$TMP/reg" registry.json
full_case "a registry.json change plans every suite" "" --changed-file "$TMP/reg"
changed "$TMP/frag" registry/core.json
full_case "a registry fragment change plans every suite" "" --changed-file "$TMP/frag"
changed "$TMP/wf" .github/workflows/x.yml
full_case "a .github/workflows change plans every suite" ".github/workflows/x.yml" --changed-file "$TMP/wf"
changed "$TMP/act" .github/actions/setup/action.yml
full_case "a .github/actions change plans every suite" ".github/actions/setup/action.yml" --changed-file "$TMP/act"
for f in tests/run-all.sh tests/affected.py scripts/ci-plan.py tests/ci-windows-suites.txt; do
  changed "$TMP/plumb" "$f"
  full_case "a change to $f plans every suite" "$f" --changed-file "$TMP/plumb"
done
changed "$TMP/mixed" skills/delivery/SKILL.md .github/workflows/tests.yml
full_case "one workflow file among others still plans every suite" ".github/workflows/tests.yml" --changed-file "$TMP/mixed"
full_case "no base and no changed list plans every suite" "no base"
full_case "an empty --base plans every suite" "no base" --base ""
full_case "an all-zero base (a new branch's push before) plans every suite" "unusable base" --base 0000000000000000000000000000000000000000
full_case "an unknown sha plans every suite" "unusable base" --base 1234567890abcdef1234567890abcdef12345678
full_case "an unusable base beats a stand-in changed list" "unusable base" --base 0000000000000000000000000000000000000000 --changed-file "$TMP/skill"
full_case "--full plans every suite" "--full" --changed-file "$TMP/skill" --full
full_case "a schedule event plans every suite" "schedule" --changed-file "$TMP/skill" --event schedule

# 3. a usable base: the real repository and an explicit commit (the work tree against HEAD)
python3 -B "$PLAN" --base HEAD --event pull_request > "$TMP/head.json"; rc=$?
if [ "$rc" = 0 ] && [ "$(pj "$TMP/head.json" 'd["base"]')" = HEAD ] && [ "$(pj "$TMP/head.json" 'd["reason"] != "no base" and not d["reason"].startswith("unusable")')" = True ]; then
  good "a commit base is used (no base fail-safe)"
else no "a commit base is used (no base fail-safe) (rc=$rc)" "$(pj "$TMP/head.json" 'd["reason"]')"; fi
if [ "$(pj "$TMP/head.json" 'len(d["suites"]) + len(d["skipped"])')" = "${#SUITES[@]}" ]; then good "a commit base plan accounts for every suite"
else no "a commit base plan accounts for every suite"; fi
# a commit of another repository is no commit here
(cd "$TMP" && rm -rf repo && git init -q repo && cd repo && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m base) \
  && good "a temp git repo for the base case" || no "a temp git repo for the base case"
BASE_SHA=$(git -C "$TMP/repo" rev-parse HEAD)
full_case "a sha that exists only in another repo is unusable here" "unusable base" --base "$BASE_SHA"

# 4. a docs-only change plans few suites (a path no suite names)
changed "$TMP/docs" docs/zz-ci-plan-unnamed-note.md
python3 -B "$PLAN" --changed-file "$TMP/docs" > "$TMP/docs.json"
ran=$(pj "$TMP/docs.json" 'len(d["suites"])')
if [ "$(pj "$TMP/docs.json" 'd["full"]')" = False ] && [ "$((ran * 2))" -lt "${#SUITES[@]}" ]; then good "a docs-only change plans few suites ($ran of ${#SUITES[@]})"
else no "a docs-only change plans few suites ($ran of ${#SUITES[@]})"; fi
changed "$TMP/none" ""
python3 -B "$PLAN" --changed-file "$TMP/none" > "$TMP/none.json"
if [ "$(pj "$TMP/none.json" 'd["full"]')" = False ] && [ "$(pj "$TMP/none.json" 'd["changed_files"]')" = 0 ] \
   && [ "$(pj "$TMP/none.json" 'len(d["matrix"]["include"])')" = 0 ]; then good "an empty change plans no suite and is not full"
else no "an empty change plans no suite and is not full"; fi

# 5. every runnable suite is in exactly one of suites / skipped, with a reason for the skipped
for f in skill docs; do
  ok=$(python3 -B -c '
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); want = sys.argv[2:]
run = [s["suite"] for s in d["suites"]]; skip = [s["suite"] for s in d["skipped"]]
print(all(s["reason"] for s in d["skipped"]) and sorted(run + skip) == sorted(want) and not set(run) & set(skip) and run == [w for w in want if w in run])
' "$TMP/$f.json" "${SUITES[@]}")
  if [ "$ok" = True ]; then good "every listed suite is selected or skipped with a reason once, in list order ($f plan)"
  else no "every listed suite is selected or skipped with a reason once, in list order ($f plan)"; fi
done

# 6. the matrix: one entry per suite x os; windows only for suites named in tests/ci-windows-suites.txt
python3 -B "$PLAN" --full > "$TMP/all.json"
mapfile -t WINSUITES < <(sed 's/#.*//; s/[[:space:]]*$//; s/^[[:space:]]*//; /^$/d' "$WIN" | tr -d '\r')
ok=$(python3 -B -c '
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); win = set(sys.argv[2:])
by = {}
for e in d["matrix"]["include"]:
    by.setdefault(e["suite"], []).append(e["os"])
exp = lambda s: ["ubuntu-24.04", "windows-2025"] if s in win else ["ubuntu-24.04"]
print(all(by[s["suite"]] == exp(s["suite"]) == s["os"] for s in d["suites"]) and len(by) == len(d["suites"])
      and all(set(e) == {"suite", "cases", "os"} for e in d["matrix"]["include"]) and bool(win))
' "$TMP/all.json" "${WINSUITES[@]}")
if [ "$ok" = True ]; then good "a windows-listed suite has both OS entries, every other suite only ubuntu-24.04"
else no "a windows-listed suite has both OS entries, every other suite only ubuntu-24.04"; fi
if [ "${#WINSUITES[@]}" -gt 0 ] && [ -z "$(comm -23 <(printf '%s\n' "${WINSUITES[@]}" | LC_ALL=C sort -u) <(printf '%s\n' "${SUITES[@]}" | LC_ALL=C sort -u))" ]; then
  good "tests/ci-windows-suites.txt names only runnable suites (${#WINSUITES[@]})"
else no "tests/ci-windows-suites.txt names only runnable suites" "$(comm -23 <(printf '%s\n' "${WINSUITES[@]}" | LC_ALL=C sort -u) <(printf '%s\n' "${SUITES[@]}" | LC_ALL=C sort -u))"; fi
if printf '%s\n' "${WINSUITES[@]}" | grep -qx tests/git-guard.test.sh && ! printf '%s\n' "${WINSUITES[@]}" | grep -qx tests/skills-lint.sh; then
  good "the windows list holds the OS-sensitive seed and not the text lints"
else no "the windows list holds the OS-sensitive seed and not the text lints"; fi

# a windows-list line that is no runnable suite is an error (exit 2): a copy of the repo scripts with a bad list
CP="$TMP/copy"; mkdir -p "$CP/scripts/lib" "$CP/tests"
cp "$PLAN" "$CP/scripts/ci-plan.py"; cp "$ROOT/scripts/lib/shells.py" "$CP/scripts/lib/"
printf '%s\n' '#!/usr/bin/env bash' 'case "$1" in --list-suites) printf "%s\n" tests/a.test.sh tests/b.test.sh ;; esac' > "$CP/tests/run-all.sh"
printf '%s\n' '# a comment' 'tests/a.test.sh' '' 'tests/nope.test.sh   # no such suite' > "$CP/tests/ci-windows-suites.txt"
python3 -B "$CP/scripts/ci-plan.py" --full > "$TMP/bad.out" 2> "$TMP/bad.err"; rc=$?
if [ "$rc" = 2 ] && grep -q 'tests/nope.test.sh' "$TMP/bad.err"; then good "a windows-list line that is no runnable suite exits 2 naming it"
else no "a windows-list line that is no runnable suite exits 2 naming it (rc=$rc)" "$(cat "$TMP/bad.err")"; fi
printf '%s\n' '# only a comment' 'tests/b.test.sh   # trailing comment' > "$CP/tests/ci-windows-suites.txt"
python3 -B "$CP/scripts/ci-plan.py" --full > "$TMP/ok.json"; rc=$?
if [ "$rc" = 0 ] && [ "$(pj "$TMP/ok.json" '[s["os"] for s in d["suites"]]')" = "[['ubuntu-24.04'], ['ubuntu-24.04', 'windows-2025']]" ]; then
  good "comments and blank lines in the windows list are ignored (stand-in suites)"
else no "comments and blank lines in the windows list are ignored (rc=$rc)" "$(cat "$TMP/ok.json")"; fi
printf '%s\n' 'exit 1' > "$CP/tests/run-all.sh"
python3 -B "$CP/scripts/ci-plan.py" --full > /dev/null 2> "$TMP/bad.err"; rc=$?
if [ "$rc" = 2 ]; then good "a failing --list-suites exits 2"; else no "a failing --list-suites exits 2 (rc=$rc)"; fi

# 7. --summary and --github-output are written (appended)
rm -f "$TMP/sum.md" "$TMP/out.txt"
python3 -B "$PLAN" --changed-file "$TMP/skill" --summary "$TMP/sum.md" --github-output "$TMP/out.txt" > "$TMP/s.json"
n=$(pj "$TMP/s.json" 'len(d["matrix"]["include"])'); ran=$(pj "$TMP/s.json" 'len(d["suites"])')
if grep -q '^## CI plan: 1 changed file' "$TMP/sum.md" && grep -q '^| Suite | Run | Cases | OS / reason |' "$TMP/sum.md" \
   && [ "$(grep -cE '^\| [^|]+ \| (yes|no) \|' "$TMP/sum.md")" = "${#SUITES[@]}" ] && grep -q '| no | - | not affected |' "$TMP/sum.md"; then
  good "--summary writes a markdown table of every suite (run versus skipped)"
else no "--summary writes a markdown table of every suite" "$(head -8 "$TMP/sum.md")"; fi
first_skip=$(grep -n '| no | - |' "$TMP/sum.md" | head -1 | cut -d: -f1); last_run=$(grep -n '| yes |' "$TMP/sum.md" | tail -1 | cut -d: -f1)
if [ -n "$first_skip" ] && [ -n "$last_run" ] && [ "$last_run" -lt "$first_skip" ]; then good "--summary lists the run rows before the skipped rows"
else no "--summary lists the run rows before the skipped rows"; fi
if grep -q '^full=false$' "$TMP/out.txt" && grep -q '^changed=1$' "$TMP/out.txt" && grep -qx "count=$n" "$TMP/out.txt" \
   && [ "$(grep '^matrix=' "$TMP/out.txt" | sed 's/^matrix=//' | python3 -B -c 'import json,sys; print(len(json.load(sys.stdin)["include"]))')" = "$n" ] \
   && ! grep '^matrix=' "$TMP/out.txt" | grep -q ' '; then
  good "--github-output writes a compact matrix, count, full and changed"
else no "--github-output writes a compact matrix, count, full and changed" "$(cut -c1-120 "$TMP/out.txt")"; fi
python3 -B "$PLAN" --changed-file "$TMP/skill" --github-output "$TMP/out.txt" > /dev/null
if [ "$(grep -c '^count=' "$TMP/out.txt")" = 2 ]; then good "--github-output appends"; else no "--github-output appends"; fi
python3 -B "$PLAN" --full --github-output "$TMP/out2.txt" > /dev/null
if grep -q '^full=true$' "$TMP/out2.txt" && grep -qx "count=$(pj "$TMP/all.json" 'len(d["matrix"]["include"])')" "$TMP/out2.txt"; then good "a full plan writes full=true and every matrix entry"
else no "a full plan writes full=true and every matrix entry"; fi

# 8. no selection logic outside tests/affected.py: the plan names affected.py and no selection rule of its own
if grep -q 'affected.py' "$PLAN" && ! grep -qE 'fnmatch|GLOBAL|PIPELINE_SUITES|import_closure' "$PLAN"; then good "ci-plan.py selects through tests/affected.py only"
else no "ci-plan.py selects through tests/affected.py only"; fi
# usage error
python3 -B "$PLAN" --bogus > /dev/null 2>&1; rc=$?
if [ "$rc" = 2 ]; then good "an unknown option exits 2"; else no "an unknown option exits 2 (rc=$rc)"; fi

echo "ci-plan: $pass passed, $fail failed"
[ "$fail" = 0 ]
