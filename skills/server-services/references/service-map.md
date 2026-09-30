# Service map and cross-process contracts

Verified 2026-09-30 against rpg-mmo-server `develop`. Paths relative to `backend/`.

## Gateway (`gateway/`, module `github.com/duycuong/rpg-mmo/gateway`)

| Package | Files | Role |
|---|---|---|
| `cmd/gateway` | `main.go` | flags/env, wiring |
| `server` | `server.go`, `connection.go`, `kick.go`, `kick_consumer.go` | listener (TCP, KCP via `--transport=kcp`, TLS `WithTLS`), `handleMessage` (Ping/Pong/Auth/EnterWorld/Disconnect only), `handleAuth`, `handleEnterWorld` (returns `ServerAddr` + `JoinToken`), `assignDungeon`, duplicate-login kick (`events:gateway_kick`, Go mirror of C# `RedisKickConsumer`) |
| `transfer` | `join_token.go`, `map_assign.go`, `dungeon.go`, `party.go`, `session_key.go` | `GenerateJoinToken[Keyring]` / `ValidateJoinToken[Keyring]`; map assignment; dungeon allocation; `NakamaParty.IsMember` over `party_get` + `runtime.http_key` (optionally TLS-pinned, `NewNakamaPartyTLS`); `GenerateSessionKey` |
| `registry` | `registry.go`, `allocator.go`, `agones_allocator.go`, `watcher.go` | lookup on the Redis registry, Agones allocation then wait for self-registration (`--allocation-wait-timeout`) |
| `session` | `manager.go`, `jwt.go` | local JWT verify (shared secret, no Nakama round trip), `session:{user_id}` TTL |
| `events` | `relay.go` | Streams consumer; logs, cannot push to clients yet (no `MsgEvent`) |
| `metrics` | `metrics.go` | Prometheus |

Docs: `gateway/docs/{README,API,DESIGN}.md` (no RUNBOOK.md exists despite `gateway/CLAUDE.md`).
Note: `gateway/CLAUDE.md` "With Nakama: NONE at runtime" is stale - `transfer/party.go` calls
Nakama `party_get` for dungeon entry (ADR-26 decision 3).

## Nakama plugin (`nakama/`, module `github.com/duycuong/rpg-mmo/nakama`, depends on `shared`)

`main.go` `InitModule` registers, in order: RPC `gateway_token` (`auth/token.go`); hooks
`AfterAuthenticateDevice`, `AfterAuthenticateEmail`, `BeforeAuthenticateEmail`; economy RPCs
`reward_kill`, `reward_kills`, `submit_kill`, `get_leaderboard` (`economy/`); party RPCs
`party_create`, `party_join`, `party_leave`, `party_get` (`social/party.go`, storage-backed, cap 4,
not the Nakama socket Party API); then `economy.SetupLeaderboards`. Log on success:
`rpg-mmo nakama module loaded in <n>ms`.

Build: `-buildmode=plugin` inside `deploy/nakama-plugin.Dockerfile` (`make plugin` -> gitignored
`deploy/modules/nakama.so`; `make image` for k3s/CI; `cd.yml` job `build-plugin`). `stack.sh up`
rebuilds when any `*.go` under `nakama/` or `shared/` is newer than the `.so`
(`deploy/docs/RUNBOOK-local-dev.md`). Docs: `nakama/docs/{README,API,DESIGN,RUNBOOK}.md`.
`nakama/CLAUDE.md` "File Structure Target" is aspirational (no `leaderboard/`, `matchmaking/`,
`internal/` exist).

## Shared (`shared/`, non-proto)

`config/`, `constants/` (`keys.go`: `ServerRegistryKey = "servers:"`), `errors/`, `jwt/`, `logger/`,
`ratelimit/`, `sealed/` (`EncodeIdentityKey`/`DecodeIdentityKey`), `sessionkey/`, `transport/`,
`messages/` (`codec.go`, `messages.go`, `proto.go`, `facing.go`, `snapshot_state.go`,
`version.go`), `storage/` (`interfaces.go`, `memory.go`, `redisstore/{client,dungeon,registry,session,stream}.go`).
`messages/` and `proto/` are wire-contract territory when a wire type or protocol version changes.

## Cross-process contracts (other side must change in the same commit)

| Contract | This side | Other side | Driver |
|---|---|---|---|
| `servers:id:{server_id}` hash (`server_id, map_id, addr, transport, capacity, player_count, identity_key`) + `servers:map:{map_id}` set | `shared/storage/redisstore/registry.go` (`infoFromFields`) | `gameserver-dotnet/GameServer/Registry/RedisServerRegistry.cs` | wire-contract (`redis-server-registry`) |
| Join token HS256, claim `sid` (+ `jti` for kick, ADR-20) | `gateway/transfer/join_token.go`, `shared/jwt/` | `gameserver-dotnet/GameServer/Server/JwtValidator.cs` | contract `join-token` (driver wire-contract) |
| Gateway session JWT minted by Nakama | `nakama/auth/token.go` (`gateway_token`) | `gateway/session/jwt.go`; client `Assets/Scripts/Nakama/Auth/NakamaAuthProvider.cs` | contract `nakama-rpc` (driver server-services) |
| Party RPCs `party_*` + `{"party_id"}` payload | `nakama/social/party.go` | client `Assets/Scripts/Nakama/Social/PartyService.cs`; gateway `transfer/party.go` | contract `nakama-rpc` (driver server-services) |
| Reward RPC `reward_kills` over `runtime.http_key` in the query string | `nakama/economy/reward_batch.go` | `gameserver-dotnet/GameServer/Nakama/NakamaClient.cs` | server-services + server-realtime |
| Kick stream `events:gateway_kick` | `gateway/server/kick_consumer.go` | C# `GameServer/Events/RedisKickConsumer.cs` | wire-contract |
| Envelope / message types | `shared/messages/`, `shared/proto/wire.proto` | C# `GameServer/Net/`, netcode package | wire-contract (`wire-generated`, `protocol-version`) |

Sources: `backend/TEAM.md` Cross-Team Contracts; `nakama/main.go`; files named above.
