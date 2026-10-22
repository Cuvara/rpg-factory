#!/usr/bin/env bash
# release-check.py on a throwaway plugin repo with a local bare "origin" (no network): the pre-tag gate and
# --verify-tag. Never touches this checkout's tags or remotes.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
RC="$ROOT/scripts/release-check.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
R="$TMP/repo"; O="$TMP/origin.git"
gc() { git -C "$R" -c user.email=t@t -c user.name=t "$@"; }
pass=0; fail=0
# expect <name> <rc> <grep-regex|-> <args...>: exit code and (optionally) a line of the combined output
expect() {
  local name="$1" want="$2" pat="$3"; shift 3
  local out rc; out=$(python3 -B "$RC" --repo "$R" "$@" 2>&1); rc=$?
  if [ "$rc" = "$want" ] && { [ "$pat" = - ] || grep -qE -- "$pat" <<<"$out"; }; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, want $want, pattern '$pat')"; sed 's/^/      /' <<<"$out"; fi
}

mkdir -p "$R/.claude-plugin"
echo "2.1.0" > "$R/VERSION"
echo '{"name":"rpg-factory","version":"2.1.0"}' > "$R/.claude-plugin/plugin.json"
echo '{"name":"rpg-factory","plugins":[{"name":"rpg-factory","source":"./","version":"2.1.0"}]}' > "$R/.claude-plugin/marketplace.json"
printf '# rpg-factory\n\nVersion 2.1.0 (see `VERSION`). Tags and releases ...\n' > "$R/README.md"
printf '# Changelog\n\n## [Unreleased]\n\n## [2.1.0] - 2026-10-22\n\n### Fixed\n- **Thing.** Fixed it.\n\n## [2.0.0] - 2026-10-01\n\n- Old.\n' > "$R/CHANGELOG.md"
git init -q -b main "$R"; gc add -A; gc commit -qm "chore(release): 2.1.0"
git init -q --bare "$O"; gc remote add origin "$O"; gc push -q origin main 2>/dev/null; gc fetch -q origin

echo "-- before tagging"
expect "ready: merge commit on main == origin/main, clean, no tag (offline)" 0 "release-check v2.1.0: PASS" --no-remote
expect "ready: also against origin (local bare remote, ls-remote)" 0 "OK +HEAD == main on origin"
notes=$(python3 -B "$RC" --repo "$R" --no-remote --notes 2>/dev/null); rc=$?
if [ $rc -eq 0 ] && [ "$(head -1 <<<"$notes")" = "### Fixed" ] && grep -q '^- \*\*Thing.\*\* Fixed it.$' <<<"$notes" && ! grep -qE '^(OK|FAIL|release-check)|2\.0\.0|Old' <<<"$notes"; then
  pass=$((pass + 1)); echo "PASS  --notes prints only the 2.1.0 section body on stdout"
else fail=$((fail + 1)); echo "FAIL  --notes (rc=$rc): $notes"; fi
gc checkout -q --detach; expect "detached at the merge commit is main" 0 - --no-remote; gc checkout -q main

cp "$R/README.md" "$TMP/readme"; sed -i 's/^Version 2.1.0/Version 2.0.9/' "$R/README.md"; gc commit -qam readme; gc push -q origin main 2>/dev/null; gc fetch -q origin
expect "README version differs" 1 "FAIL +version 2.1.0: .*README=2.0.9" --no-remote
cp "$TMP/readme" "$R/README.md"; echo '{"name":"rpg-factory","version":"2.1.1"}' > "$R/.claude-plugin/plugin.json"; gc commit -qam pj; gc push -q origin main 2>/dev/null; gc fetch -q origin
expect "plugin.json version differs" 1 "plugin.json=2.1.1" --no-remote
echo '{"name":"rpg-factory","version":"2.1.0"}' > "$R/.claude-plugin/plugin.json"
sed -i 's/^## \[Unreleased\]$/## [Unreleased]\n\n### Added\n- pending/' "$R/CHANGELOG.md"; gc commit -qam cl; gc push -q origin main 2>/dev/null; gc fetch -q origin
expect "Unreleased is not empty" 1 "FAIL +CHANGELOG ## \[Unreleased\] is present and empty" --no-remote
sed -i '/^### Added$/d; /^- pending$/d' "$R/CHANGELOG.md"; sed -i 's/^## \[2.1.0\]/## [2.0.5]/' "$R/CHANGELOG.md"; gc commit -qam cl2; gc push -q origin main 2>/dev/null; gc fetch -q origin
expect "no ## [2.1.0] section" 1 "FAIL +CHANGELOG has a non-empty ## \[2.1.0\] section" --no-remote
sed -i 's/^## \[2.0.5\]/## [2.1.0]/' "$R/CHANGELOG.md"; gc commit -qam cl3; gc push -q origin main 2>/dev/null; gc fetch -q origin
expect "fixed again" 0 - --no-remote

echo x > "$R/stray.txt"; expect "untracked file: tree not clean" 1 "FAIL +working tree clean" --no-remote; rm "$R/stray.txt"
echo y >> "$R/README.md"; expect "modified file: tree not clean" 1 "FAIL +working tree clean" --no-remote; gc checkout -q -- README.md
gc checkout -q -b feat/x; expect "feature branch is not main" 1 "FAIL +HEAD is main" --no-remote; gc checkout -q main; gc branch -q -D feat/x
gc commit -q --allow-empty -m local; expect "HEAD ahead of origin/main" 1 "FAIL +HEAD == origin/main" --no-remote; gc reset -q --hard origin/main

gc tag v2.1.0; expect "tag exists locally" 1 "FAIL +tag v2.1.0 does not exist locally" --no-remote
gc push -q origin v2.1.0 2>/dev/null; gc tag -d v2.1.0 >/dev/null
expect "tag only on origin: caught by the remote check" 1 "FAIL +tag v2.1.0 does not exist on origin"
expect "tag only on origin: offline check cannot see it" 0 - --no-remote
git -C "$O" tag -d v2.1.0 >/dev/null
gc remote remove origin; expect "remote checks without an origin fail (use --no-remote)" 1 "FAIL +remote checks need a remote named origin"
gc remote add origin "$O"; gc fetch -q origin

echo "-- after tagging (--verify-tag)"
expect "no tag yet" 1 "FAIL +tag v2.1.0 exists locally" --verify-tag --no-remote
gc tag v2.1.0; expect "lightweight tag is not annotated" 1 "FAIL +tag v2.1.0 is annotated" --verify-tag --no-remote; gc tag -d v2.1.0 >/dev/null
gc tag -a v2.1.0 -m "release 2.1.0"; expect "wrong tag message" 1 "FAIL +tag message is 'rpg-factory 2.1.0'" --verify-tag --no-remote; gc tag -d v2.1.0 >/dev/null
gc tag -a v2.1.0 -m "rpg-factory 2.1.0"
expect "annotated, right message, at HEAD (not pushed yet: a note)" 0 "note +tag v2.1.0 is not on origin yet" --verify-tag
gc push -q origin v2.1.0 2>/dev/null; expect "pushed: same tag object on origin" 0 "OK +origin has the same tag object" --verify-tag
gc commit -q --allow-empty -m after; expect "tag does not point to HEAD" 1 "FAIL +tag v2.1.0 points to HEAD" --verify-tag --no-remote; gc reset -q --hard v2.1.0

total=$((pass + fail)); echo "release-check tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
