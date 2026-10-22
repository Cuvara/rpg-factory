#!/usr/bin/env bash
# install-status.py: both load modes. cache (GitHub-style marketplace: sessions run the version-keyed
# copy; same-version update is a no-op) and directory (sessions run the marketplace directory in
# place; only the install record goes stale). Fake HOME; never touches the real ~/.claude.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
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
state() { HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r .state; }
pass=0; fail=0
chk() { if [ "$2" = "$3" ]; then pass=$((pass + 1)); echo "PASS  $1 -> $3"; else fail=$((fail + 1)); echo "FAIL  $1 expected $2 got $3"; fi; }

install 0.3.0 "$(git -C "$SRC" rev-parse HEAD)"
chk "installed copy == source HEAD" CURRENT "$(state)"
out=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$CACHE" python3 -B "$SRC/scripts/install-status.py" --session --source "$SRC")
chk "session hook silent when current" "" "$out"

echo "b" > "$SRC/file.txt"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v2
chk "new commit, same version (update would be a no-op)" CONTENT_MISMATCH "$(state)"
out=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$CACHE" python3 -B "$SRC/scripts/install-status.py" --session --source "$SRC" | jq -r '.hookSpecificOutput.additionalContext')
case "$out" in *CONTENT_MISMATCH*uninstall*) pass=$((pass + 1)); echo "PASS  session hook warns and names the reinstall fix";; *) fail=$((fail + 1)); echo "FAIL  session warning: $out";; esac

echo '{"name":"rpg-factory","version":"0.3.1"}' > "$SRC/.claude-plugin/plugin.json"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v3
chk "source version bumped, install older" STALE "$(state)"

install 0.3.1 "$(git -C "$SRC" rev-parse HEAD)"
chk "reinstalled" CURRENT "$(state)"
r=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$H/.claude/plugins/cache/rpg-factory/rpg-factory/0.2.0" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r .state)
chk "session still runs the previous cache copy" RESTART_REQUIRED "$r"

echo '{"version":2,"plugins":{}}' > "$H/.claude/plugins/installed_plugins.json"
chk "not installed" NOT_INSTALLED "$(state)"
HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --source "$SRC" >/dev/null; rc=$?
chk "exit code when not current" 1 "$rc"

echo "-- directory marketplace (sessions load the source in place)"
MKT=directory; install 0.3.1 "$(git -C "$SRC" rev-parse HEAD)"
chk "[dir] record == source" CURRENT "$(state)"
k=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$SRC" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r '.runtime.kind')
chk "[dir] session runs the marketplace dir in place" "installed: directory marketplace, in place" "$k"
echo "c" > "$SRC/file.txt"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v4
chk "[dir] new commit, same version: still CURRENT (content loads in place)" CURRENT "$(state)"
echo '{"name":"rpg-factory","version":"0.3.2"}' > "$SRC/.claude-plugin/plugin.json"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v5
chk "[dir] version bumped, record not updated -> STALE (record)" STALE "$(state)"
r=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$H/.claude/plugins/cache/rpg-factory/rpg-factory/0.3.0" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r '.runtime.kind')
chk "[dir] a session on a cache copy is flagged" "stale cache copy" "$r"

echo "-- runtime copy differs from the source (Windows backslash paths, other versions)"
install 0.3.2 "$(git -C "$SRC" rev-parse HEAD)"
chk "[dir] record == source again" CURRENT "$(state)"
OLD="$H/.claude/plugins/cache/rpg-factory/rpg-factory/0.2.9"; mkdir -p "$OLD/.claude-plugin"
echo '{"name":"rpg-factory","version":"0.2.9"}' > "$OLD/.claude-plugin/plugin.json"
BS="${OLD//\//\\}"  # C:\Users\...\.claude\plugins\cache\... as Claude Code sets it on Windows
r=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$BS" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC")
chk "[dir] backslash CLAUDE_PLUGIN_ROOT in the cache is a stale cache copy" "stale cache copy" "$(jq -r .runtime.kind <<<"$r")"
chk "[dir] backslash old cache copy is not CURRENT" RESTART_REQUIRED "$(jq -r .state <<<"$r")"
r=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$OLD" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r .state)
chk "[dir] forward-slash old cache copy is not CURRENT" RESTART_REQUIRED "$r"
OTHER="$TMP/other"; mkdir -p "$OTHER/.claude-plugin"; echo '{"name":"rpg-factory","version":"0.1.0"}' > "$OTHER/.claude-plugin/plugin.json"
r=$(HOME="$H" USERPROFILE="$H" CLAUDE_PLUGIN_ROOT="$OTHER" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" | jq -r .state)
chk "[dir] runtime version != source version (other checkout) is not CURRENT" RESTART_REQUIRED "$r"

echo "-- release note: directory mode runs unreleased commits under the release label (informational)"
git -C "$SRC" tag v0.3.2
r=$(HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC")
chk "[dir] HEAD == tag v0.3.2: no note" "CURRENT 0" "$(jq -r '"\(.state) \(.notes | length)"' <<<"$r")"
echo "d" > "$SRC/file.txt"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v6
echo "e" > "$SRC/file.txt"; git -C "$SRC" -c user.email=t@t -c user.name=t commit -qam v7
r=$(HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC")
chk "[dir] 2 commits past the tag: state unchanged" CURRENT "$(jq -r .state <<<"$r")"
chk "[dir] 2 commits past the tag: note names them" "source 0.3.2 + 2 commits past v0.3.2" "$(jq -r '.notes[0] | split(":")[0]' <<<"$r")"
out=$(HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --source "$SRC")
case "$out" in *"note: source 0.3.2 + 2 commits past v0.3.2"*) pass=$((pass + 1)); echo "PASS  text output (doctor) prints the release note";;
  *) fail=$((fail + 1)); echo "FAIL  text output lacks the release note: $out";; esac
out=$(HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --session --source "$SRC")
chk "[dir] session hook stays silent when CURRENT (the note is not an advisory)" "" "$out"

echo "-- malformed plugin records: --session never tracebacks, never fails the session"
for case in 'known_marketplaces.json=[]' 'installed_plugins.json={"plugins":[]}' 'installed_plugins.json={"plugins":{"rpg-factory@rpg-factory":"x"}}' \
            'installed_plugins.json=[1]' 'known_marketplaces.json={"rpg-factory":{"source":"directory"}}' 'known_marketplaces.json={"rpg-factory":{"source":{"source":"directory","path":5}}}' \
            'installed_plugins.json={"plugins":{"rpg-factory@rpg-factory":[{"installPath":7}]}}' 'installed_plugins.json=not json'; do
  install 0.3.2 "$(git -C "$SRC" rev-parse HEAD)"
  printf '%s\n' "${case#*=}" > "$H/.claude/plugins/${case%%=*}"
  err=$(HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --session --source "$SRC" 2>&1 >/dev/null); rc=$?
  chk "--session with $case: exit 0, no traceback" "0 " "$rc $(grep -c Traceback <<<"$err" | sed 's/^0$//')"
  err=$(HOME="$H" USERPROFILE="$H" python3 -B "$SRC/scripts/install-status.py" --json --source "$SRC" 2>&1 >/dev/null)
  chk "--json with $case: no traceback" "" "$(grep Traceback <<<"$err")"
done

total=$((pass + fail)); echo "install-status tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
