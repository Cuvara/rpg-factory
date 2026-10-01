---
name: go-backend
description: Use when writing, debugging or reviewing Go code in rpg-mmo-server's gateway, shared, Nakama plugin or Go integration_test modules and you need to know how that code actually works - module wiring without go.work, gateway entry points and options, the storage interfaces, Nakama runtime idioms, test doubles and how to run a single test. Not for deciding where a change goes or which rules, checks and gates apply (server-services, wire-contract), and not for the C# game server.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Go backend (gateway, shared, nakama, integration_test)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

This skill explains how the Go code works. Where a change belongs, its rules, checks and gates
come from the calling skill (`server-services`, `wire-contract`) and the registry. Package map and
cross-process contracts: the service map reference of `rpg-factory:server-services` - not repeated here.
Paths below are relative to the rpg-mmo-server root.

## Applies when / Not when

Applies: reading or changing Go under `backend/gateway`, `backend/shared`, `backend/nakama`,
`backend/integration_test` (and the other `shared` dependents when a `shared` API moves).
Not when: C# server or `Shared.GameLogic` code, Dockerfiles/compose/k8s as such, deciding scope.

## Scope

Repo `server`, used by `server-services` and `wire-contract`. Owns no module, contract or check.

## Architecture

- **No `go.work`.** Each module is its own build root, linked by `replace` directives:
  gateway `backend/gateway/go.mod:56`, nakama `backend/nakama/go.mod:12`, integration_test
  `backend/integration_test/go.mod:56-61` (shared, gateway and nakama). `loadtest`, `smoketest` and
  `backend/deploy/k8s/verify/probe` also replace `shared`. So: `cd` into the module before any
  `go` command, and a change to an exported `shared` symbol is only proven by building every
  dependent: `grep -l 'rpg-mmo/shared =>' backend/*/go.mod backend/deploy/k8s/verify/probe/go.mod`.
- **The `go` directive differs per module** (`grep -H '^go ' backend/*/go.mod`). With the default
  `GOTOOLCHAIN=auto` an older local `go` silently downloads the module's toolchain; `go version`
  run inside the module shows which one actually builds it.
- **Gateway:** `Gateway` struct (`backend/gateway/server/server.go:31`), built by
  `New(sessions, reg, jwtSecret, logger, opts...)` (`server.go:277`) with functional `Option`s
  (`server.go:113`, e.g. `WithDungeons` at `:131`), served by `Run` (`server.go:431`). Wiring of
  stores, allocator and options is all in `backend/gateway/cmd/gateway/main.go` (redis vs memory
  backend `:207-233`, `server.New` `:398`). Collaborators: `ClientConn`
  (`server/connection.go:30`), `registry.RegistryService` (`registry/registry.go:77`),
  `session.SessionManager` (`session/manager.go:38`), and the seams
  `transfer.PartyMembership` (`transfer/party.go:37`), `transfer.DungeonAllocator`
  (`transfer/dungeon.go:46`), `registry.KindAllocator` (`registry/agones_allocator.go:83`).
- **Storage seams:** `PlayerStore`, `SessionStore`, `ServerRegistry`, `DungeonIndex`,
  `EventStream` in `backend/shared/storage/interfaces.go:76-152`. Two implementations each:
  in-memory (`storage/memory.go`, also the gateway's `--backend=memory`) and Redis
  (`storage/redisstore/`). Compile-time assertions sit at `interfaces.go:14-19`.
- **Nakama plugin:** a `-buildmode=plugin` `.so`; entry `InitModule` (`backend/nakama/main.go:25`)
  registers RPCs and hooks. Handlers are plain functions
  `(ctx, runtime.Logger, *sql.DB, runtime.NakamaModule, payload)` (e.g.
  `economy/reward_batch.go:140`), so per-plugin state lives in package-level singletons.
- **Data ownership** (`backend/docs/ARCHITECTURE-DECISIONS.md`): ADR-1 - one writer per datum,
  `player_states` in Postgres is the only recoverable gameplay datum; sessions and registry are
  rebuilt, not restored. ADR-4 - one Redis, roles separated by key prefix
  (`backend/shared/constants/keys.go`) and `noeviction`. ADR-6 - up to 30 s of player state may be
  lost on a crash, which is acceptable only because anything of value goes through Nakama
  transactionally when granted.

## Idioms

- **Errors:** wrap with `%w`; absence is `storage.ErrNotFound` tested with `errors.Is`
  (`interfaces.go:11`, `gateway/registry/registry.go:238`, `registry/watcher.go:145`).
- **Logging:** gateway and shared use `log/slog` (`server.go:39`, `shared/logger/logger.go`);
  the Nakama plugin uses the printf-style `runtime.Logger` it is handed - no slog there.
- **Nakama errors:** `runtime.NewError(msg, grpcCode)` (`economy/reward_batch.go:158`).
- **Idempotent economy write:** the caller-supplied `BatchID` is the key
  (`reward_batch.go:63-66`); a receipt with create-only `Version: "*"` and the wallet update go
  in ONE `nk.MultiUpdate` (`reward_batch.go:42-45,185-200`), so a replay loses on the version
  check and rolls back the wallet too. Reuse this shape for any new grant.
- **Rate limiting:** `shared/ratelimit` token buckets; per-user limiter as a package singleton
  with `StartCleanup` (`backend/nakama/social/ratelimit.go:48-53`); per-IP/per-connection in the
  gateway (`server.go` `connLimiter`, `msgRate`).
- **Nil means off:** optional collaborators are nil-able and documented as such
  (`server.go:33-36`, `WithDungeons` treating one-without-the-other as off).
- **Narrow interfaces over Nakama:** declare the slice of `runtime.NakamaModule` you call
  (`nakama/auth/profile.go:35`) and assert it (`auth/profile_test.go:269`).

## Pitfalls

- **Skipped is not passed.** `backend/integration_test/dotnet_interop_test.go:123-130,376-379`
  (and `selfreg_flow_test.go:55`, `sealed_session_e2e_test.go:146`) `t.Skip` when neither
  `dotnet` on `PATH` nor `~/.dotnet/dotnet` exists. On WSL with only the Windows `dotnet.exe`
  they skip and `go test` still prints `ok`. Read `-v` output for `--- SKIP` (see
  `references/testing.md`). `GAMESERVER_NATIVE_BIN` runs them against a published AOT binary
  instead (`dotnet_interop_test.go:98-117`).
- **No build tag, no tests.** Every integration_test file is `//go:build integration`; without
  `-tags integration` the package reports `[no test files]` - CI says it once went green that way
  (`.github/workflows/ci.yml:185-192`).
- **Plugin ABI lock.** The `.so` must be built by `heroiclabs/nakama-pluginbuilder` at the SAME tag
  as the running `heroiclabs/nakama`, with the Go toolchain and `nakama-common` that release ships;
  mismatch fails at load with "plugin was built with a different version of package"
  (`backend/deploy/nakama-plugin.Dockerfile:15-21`, `backend/deploy/docs/RUNBOOK-local-dev.md`
  "Version pinning rule"). A local `go build` of `nakama/` proves compile only, and
  `GOTOOLCHAIN=auto` in the builder would reintroduce the mismatch.
- **Build context is `backend/`**, not `backend/nakama/`, because of the `replace => ../shared`
  (`nakama-plugin.Dockerfile:3-5,28-30`).
- **Lint:** `backend/TEAM.md:234` asks for golangci-lint, but there is no config and no CI step
  (registry known issue `golangci-lint-missing`); CI runs `go vet` (`.github/workflows/_go-module.yml:116-118`).
- **Panicking mocks are intentional:** the Nakama mock embeds a nil `runtime.NakamaModule`
  (`nakama/auth/mock_test.go:70-74`); a panic in a new test means your code called a method the
  mock does not implement - add it to the mock, do not recover.

## Testing

One test, from inside the module:
`cd backend/<module> && go test ./<pkg> -run '^TestName$' -race -count=1 -v`.
Subtests `-run '^TestName$/case'`; integration_test always adds `-tags integration`.
Doubles: `miniredis.RunT(t)` run against both store implementations
(`backend/gateway/registry/lookup_test.go:17-27`), `httptest.NewServer` for Nakama/Agones HTTP
(`gateway/transfer/party_http_test.go:71`), the embedded-nil Nakama mock. Full recipes, CI flag
parity and skip reading: `references/testing.md`.

## Tools

- `go`: every build, vet and test step, run inside the module directory. Fallback: CI `ci.yml`
  (one job per module) and say the result is CI-only.
- `lsp-go`: agent-lsp MCP server `lsp` over gopls: `blast_radius` on the file, then
  `find_references` / `find_callers` before changing an exported symbol or a `shared/storage`
  interface; it sees across `replace`d modules only when they are workspace folders. Fallback:
  `grep -rn` for the symbol across `backend/` plus `go vet ./...` and `go build ./...` in every
  dependent module listed above.
- `docker`: building the Nakama plugin with the pinned pluginbuilder (`make plugin` in
  `backend/deploy`) and the compose stack the e2e flows need. Fallback: HUMAN_REQUIRED or CI;
  report the plugin as compile-checked only.
- `context-mode`: run `go test -v` / `-race` suites and integration runs through
  `ctx_execute` and return only `--- FAIL`, `--- SKIP` and `ok`/`FAIL` lines. Fallback: pipe
  through `grep -E '^(--- |ok|FAIL|panic)'`.
