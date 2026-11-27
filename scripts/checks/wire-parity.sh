#!/usr/bin/env bash
# wire-parity.sh — read-only evidence for the wire-generated and protocol-version contracts.
#
#  1. Netcode Runtime/Protocol/Generated/Wire.cs must match the server's
#     C# binding in the local working tree, ignoring carriage returns (line endings).
#     Netcode CI's `wire` job checks against rpg-mmo-server develop.
#  2. The wire protocol version constant must agree in all three places:
#     C# WireProtocol.ProtocolVersion, Go messages.WireProtocolVersion, Netcode WireProtocolVersion.Current.
#
# Usage: wire-parity.sh [--workspace DIR] [--server DIR] [--netcode DIR]
# Exit 0 = both hold; 1 = a mismatch (printed); 2 = a file is missing.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/../lib/workspace.sh"
ws="$(rpgf_default_workspace)"
server=""
netcode=""
while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) ws="$2"; shift 2 ;;
    --server) server="$2"; shift 2 ;;
    --netcode) netcode="$2"; shift 2 ;;
    *) echo "ERROR: unknown argument $1"; exit 2 ;;
  esac
done
if [ -z "$server" ]; then
  if [ "${RPG_FACTORY_REPO_KEY:-}" = server ] && [ -n "${RPG_FACTORY_REPO_DIR:-}" ]; then server="$RPG_FACTORY_REPO_DIR"
  else server="$ws/rpg-mmo-server"; fi
fi
if [ -z "$netcode" ]; then
  if [ "${RPG_FACTORY_REPO_KEY:-}" = netcode ] && [ -n "${RPG_FACTORY_REPO_DIR:-}" ]; then netcode="$RPG_FACTORY_REPO_DIR"
  else netcode="$ws/Netcode"; fi
fi
for label in server Netcode; do
  dir="$server"
  [ "$label" = Netcode ] && dir="$netcode"
  is_root=false
  if [ -n "$dir" ] && [ "$(git -C "$dir" rev-parse --is-inside-work-tree 2>/dev/null)" = true ] && [ -z "$(git -C "$dir" rev-parse --show-prefix 2>/dev/null)" ]; then is_root=true; fi
  $is_root || { echo "ERROR: $label target is not a git work-tree root: ${dir:-<unresolved>}"; exit 2; }
  printf '%s tree: %s @ %s\n' "$label" "$(git -C "$dir" rev-parse --show-toplevel)" "$(git -C "$dir" rev-parse HEAD)"
done

server_cs="$server/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"
netcode_cs="$netcode/Runtime/Protocol/Generated/Wire.cs"
cs_ver_file="$server/backend/gameserver-dotnet/GameServer/Net/WireProtocol.cs"
go_ver_file="$server/backend/shared/messages/messages.go"
nc_ver_file="$netcode/Runtime/Protocol/WireProtocolVersion.cs"

for f in "$server_cs" "$netcode_cs" "$cs_ver_file" "$go_ver_file" "$nc_ver_file"; do
  [ -f "$f" ] || { echo "ERROR: missing $f"; exit 2; }
done

rc=0
server_sha=$(tr -d '\r' < "$server_cs" | sha256sum | cut -c1-12)
netcode_sha=$(tr -d '\r' < "$netcode_cs" | sha256sum | cut -c1-12)
if cmp -s <(tr -d '\r' < "$server_cs") <(tr -d '\r' < "$netcode_cs"); then
  echo "OK: Wire.cs byte-identical ignoring CR ($(tr -d '\r' < "$server_cs" | wc -c) bytes, sha256 $server_sha)"
else
  echo "FAIL: Netcode Wire.cs differs from server GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs (server sha256 $server_sha, netcode sha256 $netcode_sha)"
  echo "      fix: copy the server file over the Netcode file (no edits); Netcode CI job 'wire' enforces this"
  rc=1
fi

cs_ver=$(grep -oP 'const uint ProtocolVersion\s*=\s*\K[0-9]+' "$cs_ver_file" | head -1)
go_ver=$(grep -oP 'const WireProtocolVersion uint32\s*=\s*\K[0-9]+' "$go_ver_file" | head -1)
nc_ver=$(grep -oP 'const uint Current\s*=\s*\K[0-9]+' "$nc_ver_file" | head -1)
if [ -z "$cs_ver" ] || [ -z "$go_ver" ] || [ -z "$nc_ver" ]; then
  echo "FAIL: could not read a protocol version constant (C#='$cs_ver' Go='$go_ver' Netcode='$nc_ver') - pattern drifted, update wire-parity.sh"
  rc=1
elif [ "$cs_ver" = "$go_ver" ] && [ "$go_ver" = "$nc_ver" ]; then
  echo "OK: wire protocol version = $cs_ver in C# server, Go shared/messages, Netcode"
else
  echo "FAIL: protocol version disagrees - C# server $cs_ver, Go $go_ver, Netcode $nc_ver"
  rc=1
fi
exit $rc
