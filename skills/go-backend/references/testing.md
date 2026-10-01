# Go testing in rpg-mmo-server

Verified 2026-10-01 against rpg-mmo-server `develop`. Paths relative to the repo root.
Which checks a change needs and what counts as evidence is decided by the calling skill and the
registry; this file is only the mechanics.

## Running exactly what you mean

Always from the module directory (no `go.work`; see SKILL.md Architecture).

| Goal | Command |
|---|---|
| One test | `cd backend/gateway && go test ./registry -run '^TestRegistryService_FindServerSelection$' -race -count=1 -v` |
| One subtest | `-run '^TestName$/^case name$'` (spaces in `t.Run` names become `_`) |
| A package | `go test ./transfer -race -count=1` |
| Like CI, one module | `go vet ./... && go test ./... -race` (`.github/workflows/_go-module.yml:116-123`) |
| Integration, one test | `cd backend/integration_test && go test -tags integration -run '^TestDotnetInterop_FullFlow$' -race -count=1 -v -timeout 300s .` |
| Integration, like CI | `go vet -tags integration ./... && go test ./... -tags integration -v -race -timeout 300s` (`.github/workflows/ci.yml:191-192`) |

- `-count=1` defeats the test cache; a cached `ok ... (cached)` is not a fresh run.
- `-race` needs cgo; CI always runs it, so run it locally before calling a concurrency change done.
- After changing an exported `shared` API: `go build ./... && go vet ./...` in `gateway`, `nakama`,
  `integration_test` (with `-tags integration`), `loadtest`, `smoketest` and
  `backend/deploy/k8s/verify/probe` - each has `replace github.com/duycuong/rpg-mmo/shared`.
- `GOTOOLCHAIN=auto` (the default) may download the toolchain named by the module's `go`
  directive on first use; the first run is slow, not hung.

## Reading the result

- Count outcomes from `-v` output: `grep -cE '^\s*--- PASS'`, `grep -E '^\s*--- (FAIL|SKIP)'`.
  The package line `ok` is printed even when every test in it skipped.
- `[no test files]` in `integration_test` means `-tags integration` was missing - zero tests ran
  (`.github/workflows/ci.yml:185-188`).
- The interop tests skip with `dotnet not found` (`backend/integration_test/dotnet_interop_test.go:128,379`,
  `selfreg_flow_test.go:55`, `sealed_session_e2e_test.go:146`). They look for `dotnet` on `PATH`
  then `~/.dotnet/dotnet`; a WSL shell that only has the Windows `dotnet.exe` finds neither. Fix
  by installing the Linux SDK under `~/.dotnet`, or set `GAMESERVER_NATIVE_BIN` to a published
  NativeAOT game server (`dotnet_interop_test.go:98-117`). Any `--- SKIP` among
  `TestDotnetInterop_*` means the Go<->C# path was not exercised.

## Test doubles already in the repo

| Double | Use | Example |
|---|---|---|
| `miniredis.RunT(t)` | real Redis protocol, in process, cleaned up with the test | `backend/gateway/registry/lookup_test.go:17-27`, `backend/shared/storage/redisstore/redisstore_test.go` |
| Memory + Redis table | run one contract test against both `storage` implementations | `newStores` in `lookup_test.go:17-27` returns `{"memory", "redis"}` |
| `storage.NewMemory*` | in-process stores for gateway tests | `backend/shared/storage/memory.go` |
| `httptest.NewServer` | fake Nakama `party_get` / Agones allocator over HTTP | `backend/gateway/transfer/party_http_test.go:71`, `backend/gateway/registry/agones_allocator_test.go` |
| Embedded-nil Nakama | `struct{ runtime.NakamaModule; *mockStore }` - unimplemented calls panic | `backend/nakama/auth/mock_test.go:70-78` |
| Narrow interface | take `profileStore` instead of the whole module, assert `runtime.NakamaModule` satisfies it | `backend/nakama/auth/profile.go:35`, `profile_test.go:269` |
| Injected time | `Bucket.AllowAt(now)` instead of sleeping | `backend/shared/ratelimit/ratelimit.go:72-76` |

Tests are table-driven with `t.Run(tt.name, ...)` (e.g. `agones_allocator_test.go:97`).

## What a local run cannot show

- The Nakama plugin loading in the real server: only a pluginbuilder build plus the Nakama log
  line proves it (`backend/deploy/nakama-plugin.Dockerfile`, `backend/deploy/Makefile` `plugin`).
- golangci-lint findings: no config exists; `go vet` is the only lint CI runs.
