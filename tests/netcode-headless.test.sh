#!/usr/bin/env bash
# netcode-headless.sh: which rpg-mmo-server it reads the pinned Shared.GameLogic tag from.
# A Netcode worktree outside the workspace has no sibling server repo; --server and
# RPG_FACTORY_WORKSPACE must find it. Fixture repos only (--resolve-server builds nothing).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
chk() { if [ "$2" = "$3" ]; then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1: expected '$2' got '$3'"; fi; }

netcode() { # dir - a Netcode checkout pinning sgl-v9.9.9
  mkdir -p "$1/Tests~/Headless"; : > "$1/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"
  printf '{"name":"com.cuvara.netcode","x-manualDependencies":{"com.rpgmmo.shared-gamelogic":"https://x/rpg-mmo-server.git?path=p#sgl-v9.9.9"}}' > "$1/package.json"
}
server() { # dir [tag]
  mkdir -p "$1"; git -C "$1" init -q; echo a > "$1/a"; git -C "$1" add a
  git -C "$1" -c user.email=t@t -c user.name=t commit -qm a; [ -n "${2:-}" ] && git -C "$1" tag "$2"; return 0
}
resolve() { bash "$ROOT/scripts/checks/netcode-headless.sh" --resolve-server "$@" 2>&1; }

WS="$TMP/ws"; server "$WS/rpg-mmo-server" sgl-v9.9.9; netcode "$WS/Netcode"
chk "sibling of the Netcode dir (workspace layout)" "server: $WS/rpg-mmo-server tag: sgl-v9.9.9" "$(resolve --netcode "$WS/Netcode")"

WT="$TMP/elsewhere/wt-netcode"; netcode "$WT"      # a worktree outside the workspace
chk "worktree outside the workspace -> RPG_FACTORY_WORKSPACE" "server: $WS/rpg-mmo-server tag: sgl-v9.9.9" \
    "$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT")"

server "$TMP/elsewhere/rpg-mmo-server"             # a sibling without the tag is skipped
chk "sibling without the tag falls through to the workspace" "server: $WS/rpg-mmo-server tag: sgl-v9.9.9" \
    "$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT")"

OTHER="$TMP/other-server"; server "$OTHER" sgl-v9.9.9
chk "--server wins" "server: $OTHER tag: sgl-v9.9.9" "$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT" --server "$OTHER")"

out=$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT" --server "$TMP/elsewhere/rpg-mmo-server"); rc=$?
chk "--server without the tag is an error, not a fallback" "2 blocked" "$rc $(grep -o 'blocked' <<<"$out")"

out=$(RPG_FACTORY_WORKSPACE="$TMP/none" resolve --netcode "$WT"); rc=$?
chk "no server anywhere -> NOT-RUN(blocked)" "2 blocked" "$rc $(grep -o 'blocked' <<<"$out")"

echo "netcode-headless: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
