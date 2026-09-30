# Validation

Factory Core **discovers** the checks (registry + context script) and **runs and grades** them
with `scripts/run-checks.py`. The runner's table and evidence JSON are the validation record;
the agent never writes a state itself.

## Running checks

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths backend/gateway/redirect.go
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths ... --dry-run      # list only
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths ... --approve integration-e2e
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths ... --json         # machine record
```

- Use `--paths` with the files *you* changed. Without it the runner resolves the whole working
  tree, which includes the user's pre-existing changes.
- The list covers touched modules and their dependents; identical commands run once (the second
  is SKIPPED as a duplicate).
- `--tier fast` (default) runs fast checks and reports extended/external ones as HUMAN_REQUIRED.
  `--approve <id>` runs a named extended check after the user agreed. `--only <id>` narrows.
- Each check is graded by its registry `parser` (`go-test`, `dotnet-test`, `exit`,
  `regex:<pattern>`); `needs` makes a check BLOCKED when a prerequisite failed.
- Before/after `git status` of the product repo is compared: a check that leaves files behind
  is FAIL (pollution), even if it passed.
- Every executed check is stored with the **identity of the tree it ran on** (HEAD, diff and untracked
  files in the check's directory, check definition) and its full log, under
  `~/.local/state/rpg-factory/evidence/`. Cite the log path; the table carries the summary.
- `run-checks.py ... --status` grades the declared checks against the current tree **without running
  anything**: the stored state when nothing changed, **STALE** after any change, **NOT_RUN** when never
  executed. Run it before reporting: a PASS from before your last edit is not evidence.
- Exit 1 when any fast check is not PASS or anything FAILed.

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

- **fast** - vet / test / build / cheap static checks. Always run by the runner.
- **extended** - integration E2E, AOT publish, proto regeneration, golden-vector regeneration.
  Required when the `trigger` applies. Ask the user, then `--approve <id>`; otherwise it stays
  HUMAN_REQUIRED and the report names the trigger.
- **external** - Unity Test Runner, GitHub CI, Docker stack, deploy pipeline. Always
  HUMAN_REQUIRED from the runner; report what is needed (Editor open, PR opened, stack up).

## Result states (run-checks.py)

| State | Meaning | Done? |
|---|---|---|
| `PASS` | Ran, exit 0, parser evidence found (tests executed > 0, expected line present), no pollution | yes |
| `FAIL` | Ran and failed; or exit 0 with no evidence (0 tests, all skipped); or left files in the repo | no |
| `BLOCKED` | A `needs` prerequisite failed, or the check's directory is missing | no |
| `NOT_AVAILABLE` | A required tool is not resolved on this machine | no - say so |
| `HUMAN_REQUIRED` | Extended check not approved, or an external environment | open item |
| `SKIPPED` | Excluded on purpose (`--only`, duplicate command) | n/a |
| `NOT_RUN` | (`--status`) declared for this change, never executed | no |
| `STALE` | (`--status`) executed, but the tree or the check changed since | no - rerun |

No registered check for the touched modules is reported as "none registered", not as PASS.

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
