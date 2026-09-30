#!/usr/bin/env bash
# install-status.py: both load modes. cache (GitHub-style marketplace: sessions run the version-keyed
# copy; same-version update is a no-op) and directory (sessions run the marketplace directory in
# place; only the install record goes stale). Fake HOME; never touches the real ~/.claude.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
SRC="$TMP/src"; mkdir -p "$SRC/.claude-plugin" "$SRC/scripts"
cp "$ROOT/scripts/install-status.py" "$SRC/scripts/"
echo '{"name":"rpg-factory","version":"0.3.0"}' > "$SRC/.claude-plugin/plugin.json"; echo "a" > "$SRC/file.txt"
git -C "$SRC" init -q; git -C "$SRC" add -A; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qm v1
H="$TMP/home"; mkdir -p "$H/.claude/plugins/cache/rpg-factory/rpg-factory"
CACHE="$H/.claude/plugins/cache/rpg-factory/rpg-factory/0.3.0"
MKT=github
install() { # version commit
  rm -rf "$CACHE"; mkdir -p "$(dirname "$CACHE")"; cp -r "$SRC" "$CACHE"; rm -rf "$CACHE/.git"
  jq -n --arg p "$CACHE" --arg v "$1" --arg c "$2" '{version:2, plugins:{"rpg-factory@rpg-factory":[{scope:"user", installPath:$p, version:$v, gitCommitSha:$c}]}}' > "$H/.claude/plugins/installed_plugins.json"
  if [ "$MKT" = directory ]; then jq -n --arg s "$SRC" '{"rpg-factory":{source:{source:"directory", path:$s}, installLocation:$s}}'
  else jq -n '{"rpg-factory":{source:{source:"github", repo:"Cuvara/rpg-factory"}}}'; fi > "$H/.claude/plugins/known_marketplaces.json"
}
state() { HOME="$H" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r .state; }
pass=0; fail=0
chk() { if [ "$2" = "$3" ]; then pass=$((pass + 1)); echo "PASS  $1 -> $3"; else fail=$((fail + 1)); echo "FAIL  $1 expected $2 got $3"; fi; }

install 0.3.0 "$(git -C "$SRC" rev-parse HEAD)"
chk "installed copy == source HEAD" CURRENT "$(state)"
out=$(HOME="$H" CLAUDE_PLUGIN_ROOT="$CACHE" python3 -B "$SRC/scripts/install-status.py" --session --source "$SRC")
chk "session hook silent when current" "" "$out"

echo "b" > "$SRC/file.txt"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v2
chk "new commit, same version (update would be a no-op)" CONTENT_MISMATCH "$(state)"
out=$(HOME="$H" CLAUDE_PLUGIN_ROOT="$CACHE" python3 -B "$SRC/scripts/install-status.py" --session --source "$SRC" | jq -r '.hookSpecificOutput.additionalContext')
case "$out" in *CONTENT_MISMATCH*uninstall*) pass=$((pass + 1)); echo "PASS  session hook warns and names the reinstall fix";; *) fail=$((fail + 1)); echo "FAIL  session warning: $out";; esac

echo '{"name":"rpg-factory","version":"0.3.1"}' > "$SRC/.claude-plugin/plugin.json"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v3
chk "source version bumped, install older" STALE "$(state)"

install 0.3.1 "$(git -C "$SRC" rev-parse HEAD)"
chk "reinstalled" CURRENT "$(state)"
r=$(HOME="$H" CLAUDE_PLUGIN_ROOT="$H/.claude/plugins/cache/rpg-factory/rpg-factory/0.2.0" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r .state)
chk "session still runs the previous cache copy" RESTART_REQUIRED "$r"

echo '{"version":2,"plugins":{}}' > "$H/.claude/plugins/installed_plugins.json"
chk "not installed" NOT_INSTALLED "$(state)"
HOME="$H" python3 -B "$SRC/scripts/install-status.py" --source "$SRC" >/dev/null; rc=$?
chk "exit code when not current" 1 "$rc"

echo "-- directory marketplace (sessions load the source in place)"
MKT=directory; install 0.3.1 "$(git -C "$SRC" rev-parse HEAD)"
chk "[dir] record == source" CURRENT "$(state)"
k=$(HOME="$H" CLAUDE_PLUGIN_ROOT="$SRC" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r '.runtime.kind')
chk "[dir] session runs the marketplace dir in place" "installed (directory marketplace, in place)" "$k"
echo "c" > "$SRC/file.txt"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v4
chk "[dir] new commit, same version: still CURRENT (content loads in place)" CURRENT "$(state)"
echo '{"name":"rpg-factory","version":"0.3.2"}' > "$SRC/.claude-plugin/plugin.json"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v5
chk "[dir] version bumped, record not updated -> STALE (record)" STALE "$(state)"
r=$(HOME="$H" CLAUDE_PLUGIN_ROOT="$H/.claude/plugins/cache/rpg-factory/rpg-factory/0.3.0" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r '.runtime.kind')
chk "[dir] a session on a cache copy is flagged" "stale cache copy" "$r"

total=$((pass + fail)); echo "install-status tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
