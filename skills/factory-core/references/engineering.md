# Engineering reference

This reference owns Engineering-specific repository knowledge used by Factory Core.

## Evidence per tool (what the parsers check; use it for manual external evidence too)

- **go test -v**: count lines `--- PASS:`, `--- FAIL:`, `--- SKIP:` (subtests included) and
  packages `ok` / `FAIL` / `[no test files]`. Report `discovered = pass + fail + skip`.
  `go test ./... 2>&1 | tee /tmp/x.log; grep -c -- '--- PASS' /tmp/x.log`.
  In `integration_test` **always pass `-tags integration`**: without it the package compiles
  to zero tests and exits 0.
- **go vet / go build**: exit code 0 and no output lines. There are no test counts; do not
  invent them.
- **dotnet test**: per test project, the summary `Failed: F, Passed: P, Skipped: S, Total: T`.
  Then `python3 .github/scripts/verify-test-counters.py "backend/gameserver-dotnet/**/test-results.trx"`
  (run from the repo root). It fails a run that selected nothing or skipped everything.
  `[SkippableFact]` tests skip without Docker/Postgres/Redis. Report skips with their reason;
  they are not passes (the `dotnet-test` parser counts them separately).
- **dotnet build**: `Build succeeded` and `0 Error(s)`. Report the warning count if non-zero.
- **check_metas.py / unity-package-pins.py / bash -n / jq empty**: exit 0 plus the script's
  own summary line (for example `OK: 6 git-URL dependencies ...`).
- **Unity Test Runner** (via Unity MCP when `unity-mcp` is reachable): total / passed /
  failed / skipped per EditMode and PlayMode. Zero executed means FAIL.
- **CI**: `gh pr checks <n>`. Count the jobs that passed against the jobs expected. A PR with
  a merge conflict lists **no** checks, and an absent check is not a pass. For log-level
  proof: `gh run view <id> --log | grep -c -- '--- PASS'`.

## Environment notes (WSL)

- **dotnet**: WSL often has no Linux `dotnet`. The snapshot resolves `{dotnet}` to
  `dotnet.exe`, which builds and tests fine on `/mnt/c` paths. Caveats:
  - Environment variables do not cross into Windows processes unless listed in `WSLENV`.
    Use `GOLDEN_REGEN=1 WSLENV=GOLDEN_REGEN dotnet.exe test --filter Regenerate` (verified:
    without WSLENV the variable does not reach the Windows process; the registry command sets it).
  - AOT publish through `dotnet.exe` produces a Windows binary. The CI native interop check
    (Linux) is not reproduced locally, so it is HUMAN_REQUIRED (CI).
  - The Go integration suite starts the C# server itself and needs a dotnet it can call.
    If that fails in WSL it is FAIL with the error. Don't reclassify it as skipped.
- **go**: `go.mod` requires 1.26.x. `GOTOOLCHAIN=auto` fetches it or uses the cached
  toolchain, so a lower local `go` is fine.
- **protoc**: CI pins protoc and protoc-gen-go (registry facts `protoc-ci-pin`, `protoc-gen-go-ci-pin`). The snapshot shows local vs
  expected. Regenerating with a different version rewrites version headers. Either install
  the pinned version, or leave regeneration to CI and report NOT_AVAILABLE.

## CI coverage facts (verified 2026-09-30)

- `ci.yml` runs on **every PR** to main/master/develop/staging with no paths filter:
  proto drift, every Go module, **and the cross-language `integration_test` suite**. PR run
  36089393362 executed 25 `--- PASS` lines, including `TestDotnetInterop_FullFlow` (json and
  proto). The comments in `ci-dotnet.yml` and `backend/deploy/docs/CICD.md` ("runs solely in
  cd.yml on push") are stale. Trust the workflow file and the run log.
- `ci-dotnet.yml` also runs on every PR: build, test, test counters, AOT publish, and native
  `TestDotnetInterop` against the published binary.
- Client: `01-ci.yml` (Unity tests via unity-build-workflows@v6) ignores docs-only paths.
  `02-package-pins.yml` runs on manifest/lock/DOTS Sample changes. `uxml-codegen-drift.yml`
  runs on `*.uxml`, `*.uxml.g.cs` and lock changes.
- A PR's CI proves what it ran on the PR head. It proves nothing about uncommitted local
  state.

## Engineering git rules moved from git-safety.md

3. **Branch.** Default and protected branches are per repo in `registry.json` `repos.<key>`
   (server/client/Netcode: develop; UnityDots/UIToolkit: main). Commits go to `<type>/<area>/<topic>`
   branches created from an up-to-date default branch (`feat/gateway/redirect-ttl`). A cross-repo
   task uses the **same topic** in every repo (`feat/wire/party` in server, Netcode, client) so
   `factory-status.py` links the legs and can resume them.

7. **Generated files only via their generator:**

   | Generated | Generator |
   |---|---|
   | `backend/shared/proto/gen/`, `backend/gameserver-dotnet/GameServer/Net/Generated/` | `backend/shared/proto/generate.sh` (protoc + protoc-gen-go at the CI pins - registry facts) |
   | `Shared.GameLogic/GoldenVectors/*.json` | `GOLDEN_REGEN=1 dotnet test --filter Regenerate` |
   | `Assets/Samples/Netcode/DOTS Sample/` | recopy from com.cuvara.netcode `Samples~/DOTSSample` + `.sample-source` |
   | `Assets/Samples/Cuvara */<version>/` | Unity Package Manager sample import |
   | `**/*.uxml.g.cs` | com.cuvara.uitoolkit UXML codegen |
   | `*.meta`, root `*.csproj` / `*.sln` (client) | Unity Editor |


8. **Never edit** the `Packages/com.gdk.*` submodules, the `unity-build-workflows`
   submodule content, or the gitignored embedded `Packages/com.cuvara.*` clones from the
   client repo. Changes go to their own repos.
