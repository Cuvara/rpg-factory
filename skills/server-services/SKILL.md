---
name: server-services
description: Use when changing the backend services around the realtime tier in rpg-mmo-server - the Go gateway (auth, map/dungeon assignment, join tokens, server registry, event relay), the Nakama Go plugin (auth hooks, economy, party RPCs), non-proto code in backend/shared (Redis store, codec helpers, config, jwt), or game-state persistence and its numbered SQL migrations. Not for the C# simulation/tick/netcode server, Shared.GameLogic or content data (server-realtime), proto or cross-language contract changes (wire-contract), or deploy manifests, compose and monitoring (server-ops).
argument-hint: "[service task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Server services (gateway, nakama, shared, persistence)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

These services sit around the game server: they authenticate, place a player on a server, and
persist state. None of them carries gameplay traffic. Most defects here are contract drift
between two processes that never talk directly, so the work is mostly about both sides.

## Applies when / Not when

Applies: `backend/gateway/**`, `backend/nakama/**`, `backend/shared/**` except `proto/`,
`backend/gameserver-dotnet/GameServer/Persistence/**` and its tests
(`GameServer.Tests/Persistence/`), `backend/deploy/db/migrations/gamestate/*.sql`,
`backend/deploy/db/init-gamestate.sql`, Go-side `backend/integration_test/` cases for these flows.

Not when: tick loop, simulation, AOI, snapshot, C# net code, `Shared.GameLogic`, `backend/content/`
-> `server-realtime`; so is a `PlayerSpawn.cs` change that alters spawn or movement behaviour
(it needs their live socket-path test). `shared/proto/`, a `shared/messages` wire type, the `servers:id:{id}` hash,
or join-token claims -> `wire-contract` leads and this skill runs the server-services leg. A Nakama
RPC name/payload (contract `nakama-rpc`) is driven by THIS skill; its client end (`PartyService.cs`,
`NakamaAuthProvider.cs`) is a `client-integration` follow-up and `NakamaClient.cs` a `server-realtime` co-edit. `backend/deploy/` except the migration files,
DB backup/restore scripts, compose, k8s/Agones, monitoring -> `server-ops`.

## Scope

Repo `server`. Modules: `server.gateway`, `server.nakama`, `server.shared`, `server.persistence`,
`server.db` (migration files only; backup/restore is `server-ops`), `server.integration-test`
(shared with `server-realtime`). Facts per module:
`jq '.modules[] | select(.id=="server.gateway")' "${CLAUDE_PLUGIN_ROOT}/registry.json"`.
Architecture map and cross-process contracts: `references/service-map.md`. Migration procedure:
`references/migrations.md`.

## Workflow delta

1. **Read the ADR first** for any boundary (`backend/docs/ARCHITECTURE-DECISIONS.md`): ADR-1 (one
   writer per datum), ADR-2 (one server per `map_id`), ADR-3 (redirect only), ADR-4 (Redis roles),
   ADR-5 (Streams), ADR-6 (<=30 s loss), ADR-20 (kick by jti), ADR-24 (Nakama TLS), ADR-26 (dungeons).
2. **List the other side** of every contract the change touches (`references/service-map.md`
   table). `nakama-rpc`: this skill drives - list the gateway, game-server and client ends and hand the
   client end to `client-integration` as a follow-up. `shared/messages` wire types, `servers:id`,
   join-token claims: stop and route to `wire-contract`.
3. **Implement** in the module, following its registry `rules` (Go standards from `backend/TEAM.md`
   are in `server.shared`'s rules). How the Go code is wired (no `go.work`, storage seams, Nakama
   idioms, test doubles): invoke `rpg-factory:go-backend`. Before changing an exported `shared`
   symbol or storage interface, take its callers with `lsp-go`; build every dependent module.
4. **Migrations:** follow `references/migrations.md` exactly - new numbered file in both places,
   never an edit to a shipped one.
5. **Docs:** new RPC or message handling -> module `docs/API.md`; design change -> dated
   `docs/DESIGN.md` note; operational change -> `docs/RUNBOOK.md` (nakama) or
   `backend/deploy/docs/DATABASE.md` (migrations). CHANGELOG `[Unreleased]` per module.
6. **Nakama plugin:** a change under `backend/nakama/` or `backend/shared/` is only live after the
   plugin is rebuilt against the pinned Nakama image (`backend/deploy/nakama-plugin.Dockerfile`);
   `modules/nakama.so` is a gitignored build output, not a committed artifact.

## Rules

- Gateway is a redirector: `handleMessage` accepts only `MsgAuth`, `MsgEnterWorld`,
  `MsgDisconnect` (+ `MsgPing`/`MsgPong`). Never forward gameplay (`backend/gateway/CLAUDE.md`, ADR-3).
- Never allocate a second server for a `map_id`; full map -> `no server available for map`
  (ADR-2, `backend/gateway/CLAUDE.md` Map Assignment).
- Cross-server events: Redis Streams (consumer group + ACK) only; no pub/sub without an ADR
  (ADR-5, `backend/shared/CLAUDE.md`).
- `shared` imports nothing from nakama/gateway/gameserver.
- The Nakama plugin makes no outbound network calls; callers come in over `runtime.http_key`
  (`backend/TEAM.md` Communication Channels).
- Economy writes are atomic DB transactions with an idempotency guard; client-facing RPCs are
  rate limited (`backend/nakama/CLAUDE.md` Key Design Constraints). Anything of value is granted
  through Nakama at grant time, never left to the 30 s save sweep (ADR-6).
- One writer per datum (ADR-1): sessions = gateway, `player_states` = game server, meta = Nakama
  API only; a second writer needs an ADR. New Redis keys take a role prefix from
  `shared/constants/keys.go` and a TTL or trim bound: under `noeviction` a full Redis fails writes (ADR-4).
- Nakama ABI: plugin toolchain and `nakama-common` match the pinned Nakama release
  (`backend/deploy/docs/RUNBOOK-local-dev.md`; mechanics in `rpg-factory:go-backend`).
- Never edit an applied migration; never add anything to `init-gamestate.sql` beyond what
  `001_init.sql` describes (`backend/deploy/docs/DATABASE.md`).
- Migrations are expand/contract: CD migrates before the new binary starts.
- Phase: plumbing only - no reward amounts, prices, drop tables or party rules invented here
  (`backend/TEAM.md` Current phase). Ask.

## Generated & protected paths

| Path | Rule |
|---|---|
| `backend/shared/proto/gen/`, `GameServer/Net/Generated/` | `shared/proto/generate.sh` - `wire-contract` only |
| `GameServer/Persistence/Migrations/NNN_*.sql` once shipped | immutable (checksum) |
| `backend/deploy/db/migrations/gamestate/*.sql` | copy of the embedded file, normalised-equal |
| `backend/deploy/db/init-gamestate.sql` | must equal `001_init.sql` (normalised) |
| `backend/deploy/modules/nakama.so` | build output (`make plugin` / `stack.sh up`), gitignored |

## Validation delta

Fast Go checks come from the registry via Core; to iterate on one test use the commands in
`rpg-factory:go-backend` (its testing reference). This skill adds:

- **Persistence / migrations** - fast, from `backend/gameserver-dotnet`:
  `{dotnet} test GameServer.Tests/GameServer.Tests.csproj -c Release --filter "FullyQualifiedName~GameServer.Tests.Persistence.MigratorTests" --logger "trx;LogFileName=test-results.trx"`.
  Expected total: fact `migrator-tests-count`; without Docker the Docker-backed ones skip (`docker unavailable`). Passed only if
  `EmbeddedMigrations_AreDiscoveredAndWellFormed`, `EmbeddedMigrations_MatchDeployCopies`,
  `InitGamestateSql_MatchesFirstMigration`, `Normalize_IgnoresCommentsAndWhitespace_ButNotStatements`
  all passed - a skip of either sync test means the repo tree was not found, report FAIL.
  Then Core's full `dotnet-test` for `server.gameserver-dotnet` still applies.
- **integration-e2e** (extended, ask): trigger = join token, redirect, registry, party check,
  kick, session or Streams behaviour changed. Always `-tags integration -v`; count `--- PASS`
  and list every `--- SKIP`. A skipped `TestDotnetInterop_*`, `selfreg` or `sealed_session` test
  (`dotnet not found`, e.g. WSL with only `dotnet.exe`) is NOT evidence for a change on a
  Go<->C# contract: report it NOT_RUN, never PASS, even though `go test` printed `ok`.
- **nakama-plugin-image** (external): `make plugin` in `backend/deploy` or `./stack.sh up`; evidence
  is the Nakama log line `rpg-mmo nakama module loaded in <n>ms` (`main.go`), not a build exit.
- **ci**: `ci.yml` (Go modules + integration on every PR) and `ci-dotnet.yml` for persistence.

## Human gates

- Any `--migrate-only` run or `psql` against a non-throwaway database.
- Writing to `schema_migrations` by hand (DATABASE.md runbook D forbids it except one known row).
- Changing a join-token claim or the `servers:id` hash -> stop, hand to `wire-contract`. Changing a
  Nakama RPC name/payload -> this skill drives `nakama-rpc`; tell the user which client/game-server
  callers must follow. Tags stay with the lead.
- Starting/restarting the Docker stack or Nakama container the user is running.

## Review checklist

- Other side of each contract updated in the same commit, or the task routed to `wire-contract`.
- No gameplay forwarding path added to the gateway; no second server per map.
- New RPC: registered in `main.go` `InitModule`, rate limited, documented in `docs/API.md`.
- Migration: new number, both copies, no edit to a shipped file, backward compatible.
- Tests are table-driven and count > 0; Redis/Postgres-dependent C# tests use `[SkippableFact]`.

## Report additions

- Contracts touched and the file of each side (or "none").
- Migration table: version, name, both paths, MigratorTests counts.
- Whether the Nakama plugin was rebuilt/loaded, or HUMAN_REQUIRED (external).
- Interop evidence: `--- PASS` / `--- SKIP` counts of the integration run, or NOT_RUN with reason.

## Tools

- `go`: build, vet and test inside each touched module and every `shared` dependent. Fallback: CI `ci.yml`.
- `lsp-go`: `blast_radius` / `find_references` / `find_callers` (MCP server `lsp`) at step 3 before an exported symbol or storage interface changes. Fallback: `grep -rn` across `backend/` + `go vet`/`go build` of every dependent module.
- `pg-aiguide`: `search_docs` at step 4 for migration SQL: lock levels, `CREATE INDEX CONCURRENTLY`, adding columns with defaults. Fallback: the PostgreSQL docs for the server's version; state the lock taken in the report.
- `context-mode`: run Go/.NET test suites and integration logs through `ctx_execute`, keep only pass/fail/skip lines. Fallback: `grep` for the summary lines.
- `codex`: optional second review of a migration or contract change before reporting. Fallback: the Review checklist alone.
- `docker`: plugin build (`make plugin`), Docker-backed MigratorTests and the e2e stack. Fallback: HUMAN_REQUIRED / CI, reported as not run locally.
