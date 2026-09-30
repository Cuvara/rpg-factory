# Validation

Factory Core **discovers** what must be validated (registry + context script). The agent,
or the skill that owns the task, **executes** it and reports evidence. Core never marks a
check as passed on its own.

## Deriving the check list

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh" --repo server --paths backend/gateway/redirect.go
bash "${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh" --repo server --json --paths ... | jq '.repos[0].checks'
```

Use `--paths` with the files *you* changed. Without it the script resolves the whole working
tree, which includes the user's pre-existing changes. The list covers touched modules and
their dependents. Deduplicate identical commands. Run each in `<repo>/<cwd>`.

## Factory check scripts (read-only against product repos)

| Script | Answers |
|---|---|
| `scripts/checks/pin-status.py [--remote] [--json]` | every client git-URL pin: manifest == lock, tag exists upstream, newer tags, `.sample-source` agreement |
| `scripts/checks/pin-plan.py <package> <tag> [--client-ref REF]` | exact manifest/lock edits (hash = tag commit), upstream dependency changes, DOTS Sample recopy files |
| `scripts/checks/wire-parity.sh` | Netcode `Wire.cs` byte-identical to the server binding; protocol version equal in C#, Go, Netcode |
| `scripts/checks/netcode-headless.sh` | runs Netcode's headless dotnet tests from a temp copy (Netcode has no .gitignore) and prints .trx counters |
| `scripts/checks/package-ready.py <pkg-dir>` | release readiness of a package repo -> "READY to tag vX.Y.Z" or the exact reasons |
| `scripts/checks/unity-package-pins.py <client>` | local mirror of client CI 02-package-pins step 1 + no `file:` pins |

Product-repo scripts are run with `PYTHONDONTWRITEBYTECODE=1` (UnityDots tracks `__pycache__`).

## Tiers

- **fast** - vet / test / build / cheap static checks. Always run. A missing tool is
  `not-run:tool-missing` and blocks a "done" claim.
- **extended** - integration E2E, AOT publish, proto regeneration, golden-vector regeneration.
  Required when the `trigger` applies. Ask before running; if the user declines or is not
  asked, report `not-run:needs-confirmation` and say which trigger applied.
- **external** - Unity Test Runner, GitHub CI, Docker stack, deploy pipeline. Ask, or report
  `not-run:external` with what is needed (Editor open, PR opened, stack up).

## Result states

| State | Meaning |
|---|---|
| `passed` | Ran, evidence matches the registry `evidence` field (counts where available) |
| `failed` | Ran and failed, or ran and produced no evidence (for example 0 tests executed) |
| `skipped` | Deliberately not run for a stated reason the user accepted |
| `not-required` | No check registered for the affected modules |
| `not-run:needs-confirmation` | Extended check whose trigger applied; awaiting the user |
| `not-run:external` | Needs an environment outside this shell |
| `not-run:tool-missing` | Required tool not resolved in the snapshot toolchain |

## Evidence per tool

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
  they are not passes.
- **dotnet build**: `Build succeeded` and `0 Error(s)`. Report the warning count if non-zero.
- **check_metas.py / unity-package-pins.py / bash -n / jq empty**: exit 0 plus the script's
  own summary line (for example `OK: 6 git-URL dependencies ...`).
- **Unity Test Runner** (via Unity MCP when `unity-mcp` is reachable): total / passed /
  failed / skipped per EditMode and PlayMode. Zero executed means `failed`.
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
    (Linux) is not reproduced locally, so report it `not-run:external`.
  - The Go integration suite starts the C# server itself and needs a dotnet it can call.
    If that fails in WSL, report `failed` with the error. Don't reclassify it as skipped.
- **go**: `go.mod` requires 1.26.x. `GOTOOLCHAIN=auto` fetches it or uses the cached
  toolchain, so a lower local `go` is fine.
- **protoc**: CI pins protoc 29.3 and protoc-gen-go v1.36.6. The snapshot shows local vs
  expected. Regenerating with a different version rewrites version headers. Either install
  the pinned version, or leave regeneration to CI and report `not-run:tool-missing`.

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
