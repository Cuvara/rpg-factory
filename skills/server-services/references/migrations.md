# Game-state persistence and migrations

Verified 2026-09-30. Sources: `backend/deploy/docs/DATABASE.md`,
`backend/gameserver-dotnet/GameServer/Persistence/Migrator.cs`,
`backend/gameserver-dotnet/GameServer/GameServer.csproj`,
`backend/gameserver-dotnet/GameServer.Tests/Persistence/MigratorTests.cs`.

## Two databases, one of them ours

| Instance | Container / port | Schema owner |
|---|---|---|
| Meta | `rpg-postgres` :5432 | Nakama (`nakama migrate up`). Never hand-edit, never migrate. |
| Game state | `rpg-postgres-game` :5433, db `gamestate`, user `game` | us - numbered migrations |

## Files

| File | Role |
|---|---|
| `GameServer/Persistence/Migrations/NNN_<desc>.sql` | canonical; embedded by the glob `<EmbeddedResource Include="Persistence\Migrations\*.sql" />` (no csproj edit needed); resource names `GameServer.Persistence.Migrations.<file>.sql` |
| `backend/deploy/db/migrations/gamestate/NNN_<desc>.sql` | ops copy for `psql` during incidents |
| `backend/deploy/db/init-gamestate.sql` | first-boot seed (`/docker-entrypoint-initdb.d/`); must equal `001_init.sql`; add nothing |

Persistence code beside it: `AsyncSaver.cs` (`IPlayerStore`, `MemoryPlayerStore`, `AsyncSaver`
batch saves, degraded mode), `PostgresPlayerStore.cs`, `PlayerSpawn.cs`, `Migrator.cs`.
Without `GAME_DB_URL` the game server uses the memory store.

## How the runner behaves (`Migrator`)

- Loads embedded scripts, parses `<number>_<description>` (throws on a bad name or a duplicate
  version), sorts ascending.
- `schema_migrations(version, name, checksum 'sha256:...', applied_at)`; one transaction per
  migration with its row; advisory lock serialises concurrent runners.
- `ComputeChecksum(sql)` = sha256 over `Normalize(sql)`: whole-line `--` comments dropped,
  whitespace runs collapsed. Comment/whitespace edits are safe; statement edits are drift.
- `VerifyChecksums` throws `MigrationDriftException` ("was modified after it was applied")
  on mismatch; a DB version unknown to the binary only warns (rollback allowed).
- Runs in CD job `db-migrate` (`--migrate-only`, after a backup) and on every server boot.
  Exit codes: 0 ok, 1 failure/drift, 2 no DSN.

## Adding a migration (the only allowed change)

1. Next free number: `ls GameServer/Persistence/Migrations/`.
2. Write `GameServer/Persistence/Migrations/NNN_<description>.sql`, backward compatible
   (expand/contract: add nullable, backfill, drop in a later deploy) because CD migrates before
   the new binary starts.
3. Copy it verbatim to `backend/deploy/db/migrations/gamestate/NNN_<description>.sql`.
4. Do not touch `init-gamestate.sql` or any shipped `NNN` file.
5. Update `backend/deploy/docs/DATABASE.md` only if procedure changes; CHANGELOG entries in
   `backend/gameserver-dotnet/CHANGELOG.md` and `backend/deploy/CHANGELOG.md`.
6. Run the MigratorTests filter (SKILL.md Validation delta). With Docker available the 8
   Postgres-backed tests also run against an ephemeral container (`EphemeralPostgres.cs`); ask
   before relying on Docker.

A migration that failed during deploy never recorded a checksum, so it may be fixed in the same
numbered file (DATABASE.md runbook C). A migration that ran anywhere is fixed only by a new one
(runbook D). Hand-patching `schema_migrations` is a human gate.

## What the tests pin

| Test | Kind | Proves |
|---|---|---|
| `EmbeddedMigrations_AreDiscoveredAndWellFormed` | Fact | unique ascending versions, `001_init` present, `sha256:` checksums |
| `EmbeddedMigrations_MatchDeployCopies` | SkippableFact (skips only outside the repo tree) | same file set both sides, normalised-equal |
| `InitGamestateSql_MatchesFirstMigration` | SkippableFact (same) | seed == `001_init.sql` normalised |
| `Normalize_IgnoresCommentsAndWhitespace_ButNotStatements` | Fact | normaliser semantics |
| 8 DB tests (fresh apply, no-op rerun, pending only, drift, comment-only edit, rollback, concurrency, DB ahead) | SkippableFact (skip: docker unavailable) | runner behaviour on real Postgres |
