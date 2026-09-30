# Wire contract chain

Facts were checked against the repos on 2026-09-30.

## Contract ends

| Contract | End | Path |
|---|---|---|
| wire-generated | source | `rpg-mmo-server/backend/shared/proto/wire.proto` |
| | Go binding | `backend/shared/proto/gen/wire.pb.go` (`generate.sh`) |
| | C# server binding | `backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs` (`generate.sh`) |
| | Netcode copy | `Netcode/Runtime/Protocol/Generated/Wire.cs`, byte-identical. Netcode CI job `wire` runs `cmp` against server **develop** |
| protocol-version | C# | `GameServer/Net/WireProtocol.cs` `ProtocolVersion = 2` (line 106) |
| | Go | `backend/shared/messages/messages.go` `WireProtocolVersion uint32 = 2` (line 234) |
| | Netcode | `Runtime/Protocol/WireProtocolVersion.cs` `Current = 2` (line 54) |
| | Gateway policy | `backend/gateway/cmd/gateway/main.go` `--min-protocol-version` (default 0). Tests: `gateway/server/protocol_version_test.go` |
| redis-server-registry | C# writer | `GameServer/Registry/RedisServerRegistry.cs` |
| | Go reader | `backend/shared/storage/redisstore/registry.go` |

Legacy JSON:
- Go: `shared/messages/codec.go` sniffs a leading `{`. Struct tags are in `messages.go`.
- C#: `GameServer/Net/WireJson.cs` and `WireProtocol.cs`.
- Netcode: `Runtime/Json/` and `Runtime/Codec/EncodingSniffer.cs`.
- Client: `Tools/WireConformance` asserts that the JSON codec output matches the Go tags. It compiles the embedded package clone.

## Co-change set (history)

Across 23 server commits that touched `shared/proto` or `shared/messages` (17 of them touched `wire.proto`), these files changed alongside:

| File | Commits |
|---|---|
| `shared/CHANGELOG.md` | 22 |
| `messages.go` | 20 |
| `gameserver-dotnet/CHANGELOG.md` | 19 |
| `GameServer/Net` (incl. generated) | 18 |
| `wire.pb.go` | 17 (always together with `wire.proto`) |
| `messages/proto.go` | 15 |
| `GameServer/Server` | 14 |
| `docs/API.md` | 12 |
| gateway CHANGELOG | 10 |
| `gateway/server` | 9 |
| `GameServer/Snapshot` | 9 |
| `Tests/Snapshot` | 9 |
| `Tests/Net` | 9 |
| `gateway/transfer` | 7 |
| `integration_test/dotnet_interop_test.go` | 5 |
| SGL Components/Systems | 5 |

Worked example, `action_seq`, 2026-09-18:

- **Server `2b1418c`** (20 files):
  - `wire.proto`, `wire.pb.go`, `Generated/.../Wire.cs`, `WireJson.cs`
  - `Input/InputHandler.cs`, `World/{ActionTransitions,Components,EcsWorld,EntityView}.cs`, `Snapshot/SnapshotDeltaState.cs`, `Server/GameServer.cs`
  - SGL `Systems/ActionStateLogic.cs`
  - tests in `Input/`, `Snapshot/`, `World/`
  - `docs/API.md`, and the `shared` and `gameserver-dotnet` CHANGELOGs
- **Netcode `649f078`** (the same day, 2 files): `Runtime/Protocol/Generated/Wire.cs` (a byte copy) and `CHANGELOG.md`.
- **Released:** first in Netcode **v0.41.0** (verified with `git tag --contains 649f078`), merged via `77d16a2` (#156); the client then pinned it (`pin-bump`).

Other chains that followed the same order:

| Change | Server | Netcode | Client |
|---|---|---|---|
| Sealed framing (ADR-22) | `ede9708`, `8c4bd3b`, `f0582b1` (09-10) | `6d65c49`, `78458e4`, `c77d962` | `dc51807` |
| Identity (ADR-25) | `f0ea8cc` (09-13) | `43a78c9` (v0.38.0) | `30fa10f` |
| Party entry (ADR-26) | `76d0ecb` (09-12) | `162b1c4` | `62d395a` |

## Order and CI timing

1. The server PR goes to `develop`. `ci.yml` checks that `proto-generated` is up to date and runs the integration suite on PRs (run 36089393362 had 25 PASS). `ci-dotnet.yml` builds, tests and runs AOT + native interop.
2. The Netcode PR's `wire` job compares `Wire.cs` with the server's **develop** branch, so it only passes after step 1 is merged. It is unpinned, so it can also start failing later when the server changes.
3. The lead tags Netcode `vX.Y.Z`. `release.yml` requires the tag to equal `package.json` and a `## [X.Y.Z]` CHANGELOG section.
4. The client pin-bump PR runs `02-package-pins`, and `01-ci` runs the Unity tests.

## Compatibility

- Protobuf: unknown fields are skipped, so an **additive** field or message is compatible both ways; reusing or
  renumbering a field number is never compatible (reserve removed numbers in `wire.proto`).
- Legacy JSON (ADR-9): absent fields decode to defaults; a renamed JSON key is breaking for JSON peers.
- Version gate: `--min-protocol-version` exists on the gateway (`gateway/cmd/gateway/main.go`) and the game server
  (`GAMESERVER_MIN_PROTOCOL_VERSION`), both default 0 (unversioned clients admitted). Raise it only after
  `gateway_unversioned_handshakes_total` stays flat at zero and every released client advertises the new version;
  it is a production decision (human gate).
- Players run old builds for days: the server must accept the previous protocol version until the client pin that
  carries the new one has shipped. `factory-status.py` shows where the rollout stands; a stage marked incomplete
  means some peers still run the old side.

## Security-sensitive wire changes

Read these before touching sealed frames, handshakes or identity:

- `backend/docs/SEALED-FRAMING.md` §1–8
- `backend/docs/ROADMAP-SECURITY.md`
- ADR-8 (PSK), ADR-21 (transport confidentiality), ADR-22 (ChaCha20-Poly1305 + X25519 sealed framing), ADR-23 (gateway TLS), ADR-24 (Nakama TLS) and ADR-25 (Ed25519 game server identity), all in `backend/docs/ARCHITECTURE-DECISIONS.md`

Sealed hellos are Protobuf only (Netcode `c77d962`).

## Known drift

- `Netcode/Documentation~/NETCODE.md` (around line 359) says CI does not diff `Wire.cs`. That is stale; the `wire` job does.
- The Netcode and UnityDots CIs bootstrap their own SGL tag, which can lag the client (`factory-status.py`).
- `IndieRPGMMOAdventure/Tools/WireConformance` compiles `Packages/com.cuvara.netcode`, the gitignored embedded clone, which can be older than the pin (`pin-status.py` shows the pin).
