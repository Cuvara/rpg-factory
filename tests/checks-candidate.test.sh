#!/usr/bin/env bash
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
export TMPDIR="$tmp" RPG_FACTORY_STATE_DIR="$tmp/state"
trap 'rm -rf "$tmp"' EXIT
checks=0; passed=0; failed=0
headless_script="${HEADLESS_SCRIPT:-$root/scripts/checks/netcode-headless.sh}"
case_run() { name="$1"; shift; checks=$((checks+1)); if "$@"; then passed=$((passed+1)); echo "PASS: $name"; else failed=$((failed+1)); echo "FAIL: $name"; fi; }
expect_fail() { "$@" >/dev/null 2>&1; [ "$?" -ne 0 ]; }
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
mkdir -p "$tmp/ws"; cp -r "$server" "$tmp/ws/rpg-mmo-server"
git -C "$net" worktree add -qb candidate "$tmp/net candidate"
printf 'wire-worktree\n' > "$tmp/net candidate/Runtime/Protocol/Generated/Wire.cs"
candidate_wire() { ! bash "$root/scripts/checks/wire-parity.sh" --server "$server" --netcode "$tmp/net candidate" --workspace "$tmp/ws" >"$tmp/parity.log" 2>&1 && grep -q 'FAIL: Netcode Wire.cs differs' "$tmp/parity.log" && grep -q "$(git -C "$tmp/net candidate" rev-parse HEAD)" "$tmp/parity.log"; }
case_run 'explicit candidate mismatch reports tree SHA' candidate_wire
main_wire() { bash "$root/scripts/checks/wire-parity.sh" --server "$server" --netcode "$net" --workspace "$tmp/ws" >"$tmp/main.log" && grep -q '^OK: Wire.cs' "$tmp/main.log"; }
case_run 'main Netcode tree passes' main_wire
env_netcode() { ! RPG_FACTORY_REPO_KEY=netcode RPG_FACTORY_REPO_DIR="$tmp/net candidate" RPG_FACTORY_WORKSPACE="$tmp/ws" bash "$root/scripts/checks/wire-parity.sh" >"$tmp/env-net.log" 2>&1 && grep -q 'FAIL: Netcode Wire.cs differs' "$tmp/env-net.log" && grep -F "Netcode tree: $(git -C "$tmp/net candidate" rev-parse --show-toplevel)" "$tmp/env-net.log" && grep -q "$(git -C "$tmp/net candidate" rev-parse HEAD)" "$tmp/env-net.log"; }
case_run 'netcode env target is checked and identified' env_netcode
workspace_defaults() { env -u RPG_FACTORY_REPO_KEY -u RPG_FACTORY_REPO_DIR RPG_FACTORY_WORKSPACE="$tmp/ws" bash "$root/scripts/checks/wire-parity.sh" >"$tmp/workspace.log" 2>&1 && grep -F 'Netcode tree: '"$(git -C "$net" rev-parse --show-toplevel)" "$tmp/workspace.log" && grep -F 'server tree: '"$(git -C "$tmp/ws/rpg-mmo-server" rev-parse --show-toplevel)" "$tmp/workspace.log"; }
case_run 'no env resolves both workspace siblings' workspace_defaults
git -C "$server" worktree add -qb candidate "$tmp/server candidate"
server_env() { RPG_FACTORY_REPO_KEY=server RPG_FACTORY_REPO_DIR="$tmp/server candidate" RPG_FACTORY_WORKSPACE="$tmp/ws" bash "$root/scripts/checks/wire-parity.sh" --netcode "$net" >"$tmp/env-server.log" 2>&1 && grep -F "server tree: $(git -C "$tmp/server candidate" rev-parse --show-toplevel)" "$tmp/env-server.log"; }
case_run 'server env target is used' server_env
missing_target() { expect_fail bash "$root/scripts/checks/wire-parity.sh" --server "$tmp/missing" --netcode "$net"; }
case_run 'missing target fails closed' missing_target
mkdir -p "$tmp/not-git"; nongit_target() { expect_fail bash "$root/scripts/checks/wire-parity.sh" --server "$tmp/not-git" --netcode "$net"; }
case_run 'non-git target fails closed' nongit_target
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
  fixture) mkdir -p results; cp "$TRX_FILE" results/results.trx; exit 0 ;;
esac
EOF
chmod +x "$tmp/bin/dotnet"; export PATH="$tmp/bin:$PATH" RPG_FACTORY_REPO_DIR="$tmp/headless" RPG_FACTORY_WORKSPACE="$tmp/ws"
for mode in crash nonzero failed; do
  headless_fail() { DOTNET_MODE="$mode" bash "$headless_script" >"$tmp/$mode.log" 2>&1; }
  case_run "headless rejects $mode" expect_fail headless_fail
done
headless_cwd_fallback() { (cd "$tmp/headless" && env -u RPG_FACTORY_REPO_DIR -u RPG_FACTORY_REPO_KEY RPG_FACTORY_WORKSPACE="$tmp/ws" DOTNET_MODE=crash bash "$headless_script") >"$tmp/cwd-fallback.log" 2>&1; rc=$?; grep -F "source: $(git -C "$tmp/headless" rev-parse --show-toplevel) @" "$tmp/cwd-fallback.log"; [ "$rc" -ne 0 ]; }
case_run 'headless standalone cwd fallback resolves Netcode checkout' headless_cwd_fallback
headless_fixture() { TRX_FILE="$1" DOTNET_MODE=fixture bash "$headless_script" >"$tmp/fixture.log" 2>&1; }
case_run 'headless accepts real-shape Completed zero-failure TRX' headless_fixture "$root/tests/fixtures/completed-pass.trx"
case_run 'headless rejects real Failed TRX sample' expect_fail headless_fixture "$root/tests/fixtures/failed.trx"
sed 's/ outcome="Completed"//' "$root/tests/fixtures/completed-pass.trx" > "$tmp/missing-outcome.trx"
case_run 'headless rejects missing outcome' expect_fail headless_fixture "$tmp/missing-outcome.trx"
for counter in failed error aborted; do
  sed "s/$counter=\"0\"/$counter=\"1\"/" "$root/tests/fixtures/completed-pass.trx" > "$tmp/$counter.trx"
  case_run "headless rejects nonzero $counter" expect_fail headless_fixture "$tmp/$counter.trx"
done
sed 's/executed="397"/executed="0"/' "$root/tests/fixtures/completed-pass.trx" > "$tmp/no-executed.trx"
case_run 'headless rejects zero executed' expect_fail headless_fixture "$tmp/no-executed.trx"
printf '<TestRun><ResultSummary outcome="Completed"><Counters' > "$tmp/malformed.trx"
case_run 'headless rejects malformed XML' expect_fail headless_fixture "$tmp/malformed.trx"
echo "checks-candidate: $checks checks, $passed passed, $failed failed"
[ "$failed" -eq 0 ]
