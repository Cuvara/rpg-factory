---
name: wire-contract
description: Use when changing anything that must stay byte- or value-compatible between the Go gateway, the C# game server, the Netcode package and the Unity client - a network message or protobuf field in wire.proto, the legacy JSON encoding, the wire protocol version, the JoinToken/JWT claims, or the Redis servers:id registry hash shared by C# and Go. Cross-repo driver that orders the server leg, the Netcode resync leg and the client pin leg, and collects the contract evidence. Not for server-only gameplay logic that does not touch the wire (server-realtime) or package-internal changes that keep the wire format (unity-package).
argument-hint: "[describe the wire change]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/wire-parity.sh:*)
---

# Wire contract - server → Netcode → client

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

## Applies when / Not when

- **Applies:** add/rename/remove a message or field; change `MsgType`, envelope, framing or sealed-frame layout; change
  the legacy JSON field names; bump `WireProtocolVersion`; change JoinToken/JWT claims; change the `servers:id:{id}`
  hash fields. The snapshot shows contract `wire-generated`, `protocol-version`, `join-token` or
  `redis-server-registry` with this skill as **lead**. (Nakama RPC payloads: contract `nakama-rpc`, led by `server-services`.)
- **Not:** server logic behind an unchanged message (`server-realtime` / `server-services`); Netcode internals with
  identical bytes on the wire (`unity-package`); a client pin move for an already released Netcode (`pin-bump`).

## Scope

This skill **drives**; legs implement. It edits only `server.proto` (the `.proto` + running its generator) - no file that a leg owns.

| Leg | Repo | Leg skill | Owns |
|---|---|---|---|
| 0 driver | `server` | **this skill** (module `server.proto`) | the `wire.proto` edit and running `generate.sh` (both generated trees) |
| 1 server | `server` | `server-services` (Go: `shared/messages`, gateway, `redisstore`) + `server-realtime` (C#: `GameServer/Net`, handlers, snapshot, SGL) | hand-written Go/C# on both sides, interop test, `backend/gameserver-dotnet/docs/API.md` |
| 2 netcode | `netcode` | `unity-package` | byte copy of `Wire.cs`, `WireProtocolVersion`, codecs/JSON, headless tests, CHANGELOG |
| gate | - | **the lead** | tags `vX.Y.Z` in Netcode (and `sgl-vX.Y.Z` if Shared.GameLogic moved) |
| 3 client | `client` | `pin-bump` (+ `client-integration` for fallout) | manifest + lock + DOTS Sample |

`redis-server-registry` (C# `RedisServerRegistry.cs` + Go `redisstore/registry.go`) and `join-token` (Go `transfer/join_token.go` + `shared/jwt/` + C# `JwtValidator.cs`) have only leg 1 - both languages in the same commit.

## Workflow (driver)

1. **Contract plan (M).** Name the change per contract end (`references/chain.md` §Co-change set). Decide:
   - **Compatibility**: additive field (old peers ignore it) vs breaking (removal/renumber/semantics) - breaking
     needs a `WireProtocolVersion` bump in all three constants and a gateway `--min-protocol-version` rollout plan.
   - **Legacy JSON**: does the field also exist in the JSON encoding (Go struct tags in `shared/messages`, C# `WireJson.cs`, Netcode `Runtime/Json`)? ADR-9 keeps JSON accepted.
   - **Ordering**: server leg must land on `develop` before the Netcode leg can pass Netcode CI job `wire` (it diffs
     against server **develop**).
2. **Leg 1 - server.** Invoke `server-services` and/or `server-realtime` with the per-end list. Evidence required:
   `generate.sh` run with protoc 29.3 + protoc-gen-go v1.36.6 (snapshot toolchain row; a mismatch = `not-run:tool-missing`,
   propose letting CI regenerate only if the user agrees), both generated trees in the diff, Go + C# fast tier,
   `backend/gameserver-dotnet/docs/API.md` (the normative wire reference) updated, CHANGELOGs (`backend/shared`, `backend/gameserver-dotnet`, gateway if touched), and the
   extended integration suite (`TestDotnetInterop*`) - ask before running.
3. **Leg 2 - netcode.** Invoke `unity-package`: copy the server's generated C# **byte-for-byte**
   (`backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs` → `Netcode/Runtime/Protocol/Generated/Wire.cs`),
   update codecs/JSON/version, headless tests, CHANGELOG, then `package-ready.py` for "ready to tag".
   Evidence: `bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/wire-parity.sh` → both `OK` lines.
4. **Gate - tag (H).** Stop. Report "ready to tag Netcode vX.Y.Z" with the evidence table. The lead tags; the
   guard denies agent tagging. Resume only when the user says the tag exists.
5. **Leg 3 - client.** Invoke `pin-bump` for `com.cuvara.netcode vX.Y.Z` (and SGL if it moved). Client fallout
   (DI, session, HUD) → `client-integration`.
6. **Report.** Core template + one validation table per repo + the contract evidence table below.

A task may stop after any leg (e.g. "server side only"); the report must then list the remaining legs as open, and
the contract as **not yet consistent** if `wire-parity.sh` fails.

## Rules

- `wire.proto` is the only source (`backend/shared/proto/wire.proto`); never hand-edit generated files anywhere.
- Frames: 4-byte big-endian length prefix + Protobuf; legacy JSON told apart by the first byte (ADR-9). Fields `snake_case`.
- Both server languages change in the same commit (TEAM.md cross-team contracts); Netcode follows in its own repo/PR.
- Protocol version constants: C# `WireProtocol.ProtocolVersion`, Go `messages.WireProtocolVersion`, Netcode
  `WireProtocolVersion.Current` - equal, always (`wire-parity.sh`). Gateway `--min-protocol-version` defaults to 0;
  raising it locks out unversioned clients - a production decision (human).
- Sealed framing / identity changes follow `backend/docs/SEALED-FRAMING.md` and ADR-22/ADR-25 (`references/chain.md` §Security).

## Generated & protected paths

`backend/shared/proto/gen/`, `backend/gameserver-dotnet/GameServer/Net/Generated/` (generator `generate.sh`), `Netcode/Runtime/Protocol/Generated/Wire.cs` (byte copy), Netcode `Runtime/Plugins/` (vendored Google.Protobuf 3.29.3 - must match the protoc major the server uses).

## Validation delta

| Tier | Check | Evidence |
|---|---|---|
| fast | `wire-parity.sh` after leg 2 (also before leg 1 as a baseline) | `OK: Wire.cs byte-identical`, `OK: wire protocol version = N` |
| extended | server `go test -tags integration ./...` in `backend/integration_test` | `--- PASS: TestDotnetInterop*` count > 0 |
| extended | server `generate.sh` + diff of both generated trees | diff limited to the intended messages |
| external | server CI `ci.yml` (proto-generated, integration - runs on PRs), `ci-dotnet.yml`; Netcode CI `wire`, `headless`, Unity jobs; client CI after the pin | each job listed and passing |
| external | client `Tools/WireConformance` (compiles the embedded, possibly stale, Netcode clone) | exit 0 + which Netcode version it compiled |

## Human gates

`tag` (Netcode vX.Y.Z, sgl-vX.Y.Z), `publish` (pushes/PRs per leg), production `--min-protocol-version` changes.

## Review checklist

- [ ] Field numbers never reused; removals reserved in `wire.proto`.
- [ ] Go (`shared/messages` + generated), C# (handlers, `WireJson.cs`), Netcode (codec/JSON) all handle the new field.
- [ ] Protocol version bumped iff breaking; all three constants equal.
- [ ] `backend/gameserver-dotnet/docs/API.md` (normative wire reference) and CHANGELOGs in every touched module/repo.
- [ ] Interop evidence (TestDotnetInterop) or an explicit `not-run:needs-confirmation`.
- [ ] Legs not done are listed as open; no tag was created by an agent.

## Report additions

**Contract evidence** table: contract id, each end (repo:path), state (changed / byte-identical / pending leg),
evidence (command + result). Then one Core validation table **per repo** in leg order.
