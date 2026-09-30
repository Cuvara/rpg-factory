#!/usr/bin/env bash
# wire-parity.sh — read-only evidence for the wire-generated and protocol-version contracts.
#
#  1. Netcode Runtime/Protocol/Generated/Wire.cs must be byte-identical to the server's
#     committed C# binding (the same comparison Netcode CI's `wire` job makes against
#     rpg-mmo-server develop; this compares against the LOCAL server checkout instead).
#  2. The wire protocol version constant must agree in all three places:
#     C# WireProtocol.ProtocolVersion, Go messages.WireProtocolVersion, Netcode WireProtocolVersion.Current.
#
# Usage: wire-parity.sh [--workspace DIR]
# Exit 0 = both hold; 1 = a mismatch (printed); 2 = a file is missing.
set -uo pipefail

ws="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
[ "${1:-}" = "--workspace" ] && ws="$2"

server_cs="$ws/rpg-mmo-server/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"
netcode_cs="$ws/Netcode/Runtime/Protocol/Generated/Wire.cs"
cs_ver_file="$ws/rpg-mmo-server/backend/gameserver-dotnet/GameServer/Net/WireProtocol.cs"
go_ver_file="$ws/rpg-mmo-server/backend/shared/messages/messages.go"
nc_ver_file="$ws/Netcode/Runtime/Protocol/WireProtocolVersion.cs"

for f in "$server_cs" "$netcode_cs" "$cs_ver_file" "$go_ver_file" "$nc_ver_file"; do
  [ -f "$f" ] || { echo "ERROR: missing $f"; exit 2; }
done

rc=0
if cmp -s "$server_cs" "$netcode_cs"; then
  echo "OK: Wire.cs byte-identical ($(wc -c < "$server_cs") bytes, sha256 $(sha256sum "$server_cs" | cut -c1-12))"
else
  echo "FAIL: Netcode Wire.cs differs from server GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"
  echo "      server  sha256 $(sha256sum "$server_cs" | cut -c1-12)  netcode sha256 $(sha256sum "$netcode_cs" | cut -c1-12)"
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
