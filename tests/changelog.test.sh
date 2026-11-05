#!/usr/bin/env bash
# scripts/changelog.py on throwaway trees: fragment validation, the [Unreleased]-must-stay-empty rule, preview order
# and the release assembly (section written under [Unreleased], fragments removed, refusals leave files untouched).
# Usage: tests/changelog.test.sh   (standalone; own temp dir; no network)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
CL="$ROOT/scripts/changelog.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/      /'; return 0; }
# expect <label> <rc> <regex|-> <args...>: runs changelog.py --root $R and greps stdout+stderr
expect() {
  local label="$1" want="$2" re="$3"; shift 3
  out=$(python3 -B "$CL" --root "$R" "$@" 2>&1); rc=$?
  if [ "$rc" -eq "$want" ] && { [ "$re" = - ] || grep -qE -- "$re" <<<"$out"; }; then ok "$label"
  else no "$label" "rc=$rc (want $want) out: $out"; fi
}
fresh() {
  R="$TMP/$1"; mkdir -p "$R/changelog.d"; printf '# fragments\n' > "$R/changelog.d/README.md"
  printf '# Changelog\n\nIntro.\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- First.\n' > "$R/CHANGELOG.md"
}

echo "-- check"
fresh empty
expect "no fragments, empty [Unreleased]: OK" 0 "0 fragment\(s\), 0 problem" check
printf '### Fixed\n\n- **Guard.** A fix.\n' > "$R/changelog.d/b-fix.md"
printf '### Added\n\n- **Thing.** New.\n  continued line.\n\n### Fixed\n\n- **Other.** Fix two.\n' > "$R/changelog.d/a-feature.md"
expect "two valid fragments: OK" 0 "2 fragment\(s\), 0 problem" check
cp -r "$R" "$TMP/valid"
printf '### Improved\n\n- x\n' > "$R/changelog.d/bad-cat.md"
expect "unknown category fails" 1 "bad-cat.md: line 1: unknown category '### Improved'" check
rm "$R/changelog.d/bad-cat.md"; printf 'Loose text.\n\n### Added\n\n- x\n' > "$R/changelog.d/loose.md"
expect "text before the first heading fails" 1 "loose.md: line 1: text before the first" check
rm "$R/changelog.d/loose.md"; printf '### Added\n\n' > "$R/changelog.d/empty-cat.md"
expect "category without entries fails" 1 "empty-cat.md: '### Added' has no entries" check
rm "$R/changelog.d/empty-cat.md"; printf '## [9.9.9]\n\n### Added\n\n- x\n' > "$R/changelog.d/version-head.md"
expect "a version heading in a fragment fails" 1 "only '### <Category>' headings" check
rm "$R/changelog.d/version-head.md"; printf '### Added\n\n- x\n\n### Added\n\n- y\n' > "$R/changelog.d/dup.md"
expect "a category twice in one fragment fails" 1 "'### Added' appears twice" check
rm "$R/changelog.d/dup.md"; : > "$R/changelog.d/blank.md"
expect "an empty fragment fails" 1 "blank.md: no '### <Category>' section" check
rm "$R/changelog.d/blank.md"; printf 'notes' > "$R/changelog.d/notes.txt"
expect "non-.md files are ignored" 0 "2 fragment\(s\), 0 problem" check
sed -i 's/^## \[Unreleased\]$/## [Unreleased]\n\n### Fixed\n\n- direct edit/' "$R/CHANGELOG.md"
expect "an entry written straight into [Unreleased] fails" 1 "\[Unreleased\] has entries: put them in changelog.d" check
fresh noheading; sed -i '/^## \[Unreleased\]$/d' "$R/CHANGELOG.md"
expect "a CHANGELOG without [Unreleased] fails" 1 "no '## \[Unreleased\]' heading" check

echo "-- preview"
R="$TMP/valid"
expect "preview merges by category in Keep a Changelog order" 0 - preview
want=$'### Added\n\n- **Thing.** New.\n  continued line.\n\n### Fixed\n\n- **Other.** Fix two.\n- **Guard.** A fix.'
[ "$out" = "$want" ] && ok "preview text: Added before Fixed; fragments in file-name order" || no "preview text" "$out"

echo "-- release"
cp "$R/CHANGELOG.md" "$TMP/before.md"
expect "release refuses a bad version" 2 "X.Y.Z" release 1.1
expect "release refuses an existing version section" 1 "already has '## \[1.0.0\]'" release 1.0.0
cmp -s "$R/CHANGELOG.md" "$TMP/before.md" && [ "$(ls "$R/changelog.d" | wc -l)" -eq 3 ] \
  && ok "refused releases leave CHANGELOG.md and the fragments untouched" || no "refused release changed files"
expect "release 1.1.0 with a summary" 0 "wrote ## \[1.1.0\] - 2026-11-05" release 1.1.0 --date 2026-11-05 --summary "Feature release: things."
want=$'# Changelog\n\nIntro.\n\n## [Unreleased]\n\n## [1.1.0] - 2026-11-05\n\nFeature release: things.\n\n### Added\n\n- **Thing.** New.\n  continued line.\n\n### Fixed\n\n- **Other.** Fix two.\n- **Guard.** A fix.\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- First.'
[ "$(cat "$R/CHANGELOG.md")" = "$want" ] && ok "release writes the section under an empty [Unreleased], before 1.0.0" \
  || no "released CHANGELOG.md" "$(cat "$R/CHANGELOG.md")"
[ "$(cd "$R/changelog.d" && ls)" = "README.md" ] && ok "release removes the fragments, keeps README.md" || no "fragments left" "$(ls "$R/changelog.d")"
expect "after release check passes again" 0 "0 fragment\(s\), 0 problem" check
expect "nothing to release without fragments or summary" 1 "nothing to release" release 1.2.0
fresh bad; printf '### Nope\n\n- x\n' > "$R/changelog.d/x.md"; cp "$R/CHANGELOG.md" "$TMP/bad-before.md"
expect "release refuses invalid fragments" 1 "unknown category" release 1.1.0
cmp -s "$R/CHANGELOG.md" "$TMP/bad-before.md" && [ -f "$R/changelog.d/x.md" ] && ok "invalid fragments: nothing written" || no "invalid fragments changed files"

echo "-- this repository"
R="$ROOT"; expect "repo fragments valid and CHANGELOG.md [Unreleased] empty" 0 "0 problem" check

echo "changelog tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
