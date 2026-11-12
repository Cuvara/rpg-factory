#!/usr/bin/env bash
# registry.json is built from registry/ fragments (scripts/build-registry.py, scripts/lib/registry_src.py):
# the committed file equals the build, merge rules refuse duplicates and stray keys, entries sit in the fragment their
# domain or repo names, the scaffolder writes fragments, and two branches adding entries to different domains merge
# without touching the same fragment (registry.json itself is rebuilt).
# Usage: tests/registry-fragments.test.sh   (standalone; throwaway plugin copies; no network)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/      /'; return 0; }
# copy <dir>: registry.json, its fragments and the two scripts (enough for build-registry)
copy() { rm -rf "$1"; mkdir -p "$1/scripts/lib"; cp -R "$ROOT/registry" "$ROOT/registry.json" "$1/"
  cp "$ROOT/scripts/build-registry.py" "$1/scripts/"; cp "$ROOT/scripts/lib/registry_src.py" "$1/scripts/lib/"; }
br() { out=$(python3 -B "$1/scripts/build-registry.py" "${@:2}" 2>&1); rc=$?; }
expect() {  # expect <label> <rc> <regex> <dir> <args...>
  local label="$1" want="$2" re="$3"; shift 3; br "$@"
  if [ "$rc" -eq "$want" ] && grep -qE -- "$re" <<<"$out"; then ok "$label"; else no "$label" "rc=$rc (want $want): $out"; fi
}
jqi() { local f="$1"; shift; jq "$@" "$f" > "$f.tmp" && mv "$f.tmp" "$f"; }

echo "-- this repository"
expect "registry.json is the build of registry/" 0 "^OK +registry.json == build" "$ROOT" --check
n=$(find "$ROOT/registry" -name '*.json' | wc -l)
[ "$n" -ge 7 ] && ok "fragments present ($n)" || no "fragments present" "$n"
grep -qE '^registry\.json .*linguist-generated' "$ROOT/.gitattributes" 2>/dev/null && ok ".gitattributes marks registry.json generated" \
  || no ".gitattributes marks registry.json linguist-generated"

CO="$ROOT/.github/CODEOWNERS"
if [ -f "$CO" ]; then
  stale=$(sed -n 's#^/\([^ *]*[^ */]\)/\{0,1\}[[:space:]].*#\1#p' "$CO" | while read -r p; do [ -e "$ROOT/$p" ] || echo "$p"; done)
  [ -z "$stale" ] && ok "CODEOWNERS: every literal path exists" || no "CODEOWNERS names missing paths" "$stale"
  miss=$(jq -r '.domains | keys[] | select(. != "engineering")' "$ROOT/registry.json" | while read -r d; do
    grep -q "^/registry/domains/$d\.json " "$CO" || echo "$d"; done)
  [ -z "$miss" ] && ok "CODEOWNERS: every domain fragment has an owner" || no "CODEOWNERS lacks domain fragments" "$miss"
else no "CODEOWNERS present" ".github/CODEOWNERS missing"; fi

echo "-- build and check"
D="$TMP/a"; copy "$D"
jqi "$D/registry.json" '.facts += []' ; printf ' ' >> "$D/registry.json"
expect "a hand-edited registry.json fails --check" 1 "is not the build of registry/" "$D" --check
expect "build rewrites registry.json" 0 "wrote registry.json" "$D"
expect "then --check passes" 0 "^OK" "$D" --check
copy "$D"; jqi "$D/registry/domains/ui.json" '.skills["ui-ux"] = {"kind":"repo","domain":"ui","repos":["authoring"],"order":1}' \
  && jqi "$D/registry/domains/vfx.json" '.skills["ui-ux"] = {"kind":"repo","domain":"ui","repos":["authoring"],"order":1}'
expect "a key defined in two fragments fails" 1 "skills.ui-ux is already defined in registry/domains/ui.json" "$D"
copy "$D"; jqi "$D/registry/domains/vfx.json" '.schema_version = 9'
expect "a scalar outside core.json fails" 1 "'schema_version' must be an object or array here" "$D"
copy "$D"; jqi "$D/registry/domains/vfx.json" '.brand_new = []'
expect "a top-level key not declared in core.json fails" 1 "top-level key 'brand_new' is not declared" "$D"
copy "$D"; m=$(jq -c '.modules[0]' "$D/registry/engineering/server.json"); jqi "$D/registry/engineering/server.json" '.modules |= .[1:]'
jqi "$D/registry/engineering/client.json" --argjson m "$m" '.modules += [$m]'
expect "a server module in client.json is misplaced" 1 "registry/engineering/client.json: modules '.*' belongs in registry/engineering/server.json" "$D" --check
copy "$D"; s=$(jq -c '.skills["vfx"]' "$D/registry/domains/vfx.json"); jqi "$D/registry/domains/vfx.json" 'del(.skills["vfx"])'
jqi "$D/registry/core.json" --argjson s "$s" '.skills["vfx"] = $s'
expect "a domain skill in core.json is misplaced" 1 "registry/core.json: skills 'vfx' belongs in registry/domains/vfx.json" "$D" --check
copy "$D"; printf '{' > "$D/registry/domains/ui.json"
expect "an unreadable fragment fails" 1 "registry/domains/ui.json: not readable JSON" "$D"
copy "$D"; rm "$D/registry/core.json"
expect "without core.json the build fails" 1 "registry/core.json missing" "$D"

echo "-- split round trip"
copy "$D"; cp "$D/registry.json" "$TMP/before.json"
expect "--split rewrites the same fragments" 0 "wrote [0-9]+ fragment" "$D" --split
cmp -s <(tr -d '\r' < "$D/registry.json") <(tr -d '\r' < "$TMP/before.json") && ok "split + build reproduces registry.json ignoring CR" || no "split round trip changed registry.json"
[ -z "$(diff -r --strip-trailing-cr "$ROOT/registry" "$D/registry")" ] && ok "split reproduces the committed fragments" || no "split differs" "$(diff -r --strip-trailing-cr "$ROOT/registry" "$D/registry" | head -5)"

echo "-- scaffolder writes fragments"
P="$TMP/plugin"; mkdir -p "$P"; cp -R "$ROOT/." "$P/"; rm -rf "$P/.git"
out=$(CLAUDE_PLUGIN_ROOT="$P" python3 -B "$P/scripts/new-skill.py" --name ui-motion --kind tech --domain ui --summary "How UI motion works." \
  --repos client --used-by client-integration 2>&1); rc=$?
[ "$rc" -eq 0 ] && jq -e '.skills["ui-motion"].domain == "ui"' "$P/registry/domains/ui.json" >/dev/null \
  && ! jq -e '.skills["ui-motion"]' "$P/registry/core.json" "$P/registry/engineering/skills.json" >/dev/null 2>&1 \
  && ok "new-skill --domain ui lands in registry/domains/ui.json" || no "new-skill fragment placement" "rc=$rc $out"
expect "after new-skill registry.json is the build" 0 "^OK" "$P" --check

echo "-- parallel branches merge through fragments"
G="$TMP/git"; copy "$G"; cp "$ROOT/.gitattributes" "$G/" 2>/dev/null
gg() { git -C "$G" -c user.email=t@t -c user.name=t "$@"; }
git init -q -b main "$G"; gg add -A; gg commit -qm base
gg switch -q -c ui-work; jqi "$G/registry/domains/ui.json" '.contracts += [{"id":"ui-extra","domain":"ui","driver":"ui-ux","kind":"handoff","summary":"x","source":{"repo":"authoring","path":"ui/specs/"},"copies":[]}]'
python3 -B "$G/scripts/build-registry.py" >/dev/null; gg commit -qam ui
gg switch -q main; jqi "$G/registry/domains/vfx.json" '.contracts += [{"id":"vfx-extra","domain":"vfx","driver":"vfx","kind":"handoff","summary":"y","source":{"repo":"authoring","path":"vfx/specs/"},"copies":[]}]'
python3 -B "$G/scripts/build-registry.py" >/dev/null; gg commit -qam vfx
gg merge -q --no-edit ui-work >/dev/null 2>&1; conflicted=$(gg diff --name-only --diff-filter=U | tr '\n' ' ')
case "$conflicted" in *registry/*) no "fragments conflicted" "$conflicted";; *) ok "the fragments merge cleanly (conflicted: ${conflicted:-none})";; esac
# entries are grouped by fragment in the generated file, so it usually merges too; if not, rebuilding resolves it
if [ -n "$conflicted" ]; then python3 -B "$G/scripts/build-registry.py" >/dev/null; gg add registry.json; gg commit -qm merged --no-edit 2>/dev/null; fi
jq -e '[.contracts[].id] | index("ui-extra") and index("vfx-extra")' "$G/registry.json" >/dev/null \
  && ok "rebuilding resolves it: both contracts present" || no "rebuilt registry lacks a contract"
expect "merged tree: registry.json is the build" 0 "^OK" "$G" --check

echo "registry fragments tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
