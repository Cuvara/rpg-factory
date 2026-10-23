#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
export TMPDIR="$tmp" RPG_FACTORY_STATE_DIR="$tmp/state"
trap 'rm -rf "$tmp"' EXIT
server="$tmp/server with space"; net="$tmp/ws/Netcode"; mkdir -p "$server/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1" "$server/backend/gameserver-dotnet/GameServer/Net" "$server/backend/shared/messages" "$net/Runtime/Protocol/Generated"
init_repo() { git -C "$1" init -q; git -C "$1" config user.email test@example.com; git -C "$1" config user.name test; }
init_repo "$server"; init_repo "$net"
printf 'wire-main\n' > "$server/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"
printf 'wire-main\n' > "$net/Runtime/Protocol/Generated/Wire.cs"
printf 'const uint ProtocolVersion = 1;\n' > "$server/backend/gameserver-dotnet/GameServer/Net/WireProtocol.cs"
printf 'const WireProtocolVersion uint32 = 1\n' > "$server/backend/shared/messages/messages.go"
printf 'const uint Current = 1;\n' > "$net/Runtime/Protocol/WireProtocolVersion.cs"
git -C "$server" add .; git -C "$server" commit -qm fixture
git -C "$net" add .; git -C "$net" commit -qm fixture
git -C "$net" worktree add -qb candidate "$tmp/net candidate"
printf 'wire-worktree\n' > "$tmp/net candidate/Runtime/Protocol/Generated/Wire.cs"
if bash "$root/scripts/checks/wire-parity.sh" --server "$server" --netcode "$tmp/net candidate" --workspace "$tmp/ws" >"$tmp/parity.log" 2>&1; then echo 'expected candidate mismatch'; exit 1; fi
grep -q 'FAIL: Netcode Wire.cs differs' "$tmp/parity.log"; grep -q "$(git -C "$tmp/net candidate" rev-parse HEAD)" "$tmp/parity.log"
bash "$root/scripts/checks/wire-parity.sh" --server "$server" --netcode "$net" --workspace "$tmp/ws" >"$tmp/main.log"; grep -q '^OK: Wire.cs' "$tmp/main.log"
if bash "$root/scripts/checks/wire-parity.sh" --server "$tmp/missing" --netcode "$net" >"$tmp/missing.log" 2>&1; then echo 'missing target passed'; exit 1; fi
mkdir -p "$tmp/not-git"; if bash "$root/scripts/checks/wire-parity.sh" --server "$tmp/not-git" --netcode "$net" >"$tmp/notgit.log" 2>&1; then echo 'non-git target passed'; exit 1; fi
mkdir -p "$tmp/headless/Tests~/Headless" "$tmp/headless/Runtime" "$tmp/headless/Tests"; touch "$tmp/headless/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"; init_repo "$tmp/headless"; git -C "$tmp/headless" add .; git -C "$tmp/headless" commit -qm fixture
mkdir -p "$tmp/bin"
cat > "$tmp/bin/dotnet" <<'EOF'
#!/usr/bin/env bash
case "${DOTNET_MODE:-crash}" in
  crash) exit 139 ;;
  nonzero) exit 1 ;;
  failed) mkdir -p results; cat > results/results.trx <<'TRX'
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010"><ResultSummary outcome="Failed"><Counters total="1" executed="1" passed="0" failed="1" notExecuted="0" /></ResultSummary></TestRun>
TRX
    exit 0 ;;
esac
EOF
chmod +x "$tmp/bin/dotnet"; export PATH="$tmp/bin:$PATH" RPG_FACTORY_REPO_DIR="$tmp/headless" RPG_FACTORY_WORKSPACE="$tmp/ws"
for mode in crash nonzero failed; do if DOTNET_MODE="$mode" bash "$root/scripts/checks/netcode-headless.sh" >"$tmp/$mode.log" 2>&1; then echo "headless $mode passed"; exit 1; fi; done
echo 'PASS: candidate identity, path spaces, fail-closed targets, headless failures'
