# Measurement legs

Verified 2026-09-30 against `rpg-mmo-server` @ `5023a3d` and `IndieRPGMMOAdventure` `develop`.
Every leg below except the micro-benches and the report renderer is a human gate.

## Server: load generator (`backend/loadtest`)

Build: `go build -o loadtest ./cmd/loadtest` (cwd `backend/loadtest`; BENCHMARK.md section 10).
Flags used by the recorded runs: `-sweep`, `-repeat`, `-cooldown`, `-join direct|gateway`,
`-encoding proto|json`, `-transport tcp`, `-movement cluster|spread|still`, `-baseline-entities`,
`-ramp`, `-warmup`, `-duration`, `-json <file>`, `-gameserver-addr`, `-server-id`,
`-join-token-secret`, `-gameserver-metrics`, `-gateway-metrics`, `-sealed`.
Flag reference: `backend/loadtest/README.md` "Key flags".

| Recipe | Source | Notes |
|---|---|---|
| Single level, full gateway path, stock dev stack | BENCHMARK.md 10 | `./loadtest -players 10 -duration 60s -baseline-entities 6 -movement still`. Stay <= 10 players (gateway conn-rate limit) |
| Capacity sweep, dedicated server, direct join | BENCHMARK.md 10 | `docker run -d --name rpg-gs-bench ... GAMESERVER_CAPACITY=2000 GAMESERVER_ENEMIES=false rpg-mmo/gameserver-dotnet:dev`, then `-join direct -sweep 50,100,150,200 -repeat 3` |
| Current control shape | `results/2026-09-18-develop-3378bc9/README.md` | Release build run directly (not containerised), `-cooldown 40s` (> 30 s entity hold) instead of a restart per level, `SIM 60/15/5`, both `cluster` and `spread` |
| One level + RAM/CPU sampling | `scripts/bench.sh <players> <duration> <movement> <outdir> [flags]` | needs `JWT_SECRET`; `LOADTEST_BIN` (default `./loadtest`), `DOCKER` (default `docker.exe`), `CONTAINERS` (default `rpg-gameserver rpg-gateway rpg-redis`). Writes `run-<players>-<movement>.{json,log}` and `stats-<players>-<movement>.txt` |
| Encoding A/B | `JWT_SECRET=... scripts/encoding-sweep.sh [players...]` | arms `baseline-json` (`BASELINE_IMAGE`), `new-json` and `new-proto` (`NEW_IMAGE`), same generator. Refuses while a `cd.yml` run is in flight (`SKIP_CD_CHECK=1` overrides). Starts/restarts containers |
| Render sweep tables | `python3 -B scripts/encoding-report.py [results/encoding]` | offline |

Secrets: the server refuses to start without `JOIN_TOKEN_SECRET`; pass it to both sides. BENCHMARK.md
greps them from `backend/deploy/.env` - that read is a gate; ask the user to export them.

Freshness: README "Benchmarking protocol" and BENCHMARK.md "Run protocol" say restart the server and
wait for `gameserver_entities` to read 0 before each level; the 2026-09-18 control used `-cooldown 40s`
against a fresh server instead. Either way, record the entity count at level start.

Results layout: dated dirs `<YYYY-MM-DD>-<branch>-<shortsha>[-topic]` (`2026-09-07-develop-c05f715`,
`2026-09-18-develop-3378bc9`, `2026-09-18-importance`), topic dirs (`encoding`, `encoding-rerun`,
`entity-type-enum`, `entity-id-interning`, `tick-variance`), and legacy flat `run-<N>-<movement>.json`.
New runs go in a new dated dir with a README stating the command, setup and which column to quote.

## Server: micro-benchmarks (`backend/gameserver-dotnet/GameServer.Tests/Bench`)

Skipped unless the env var is `1`; no timing assertions, the console output is the deliverable.

| Class | Gate |
|---|---|
| `TickBreakdownBench`, `TickAllocationBench`, `ImportanceIntervalBench`, `UnchangedFieldBytesBench`, `AoiComposeBench` | `BENCH_TICK=1` |
| `AoiIndexBench`, `AoiClusteredGateBench` | `BENCH_AOI=1` |
| `TieringRateMeasurement` | `MEASURE_TIERING=1` (several minutes) |

Shape (from the class docs): `BENCH_TICK=1 dotnet test --filter FullyQualifiedName~TickBreakdownBench
--logger "console;verbosity=detailed"`. Under WSL with `dotnet.exe`, add `WSLENV=BENCH_TICK` (or the
relevant var), otherwise the variable never reaches the Windows process and the bench reports skipped.
Evidence: the bench's printed table and `Skipped: 0` for the selected class. Clocks are `Stopwatch`
(monotonic) by design (`TickBreakdownBench` header).

## Client: multi-client verification (`IndieRPGMMOAdventure/Tools`)

Needs a Windows player built by `Assets/BuildScripts/Editor/PlayerBuilder.cs` (client `CLAUDE.md`
"Running several clients against one backend") and a running backend.

- `Tools/run-clients.sh --exe <player.exe> [--count N] [--gateway-host/--gateway-port] [--nakama-*]
  [--map ID] [--status-url URL] [--log-dir DIR] [--tile] [--kill]`: distinct device id, log file and
  window per instance; logs default to `/tmp/cuvara-clients`.
- `Tools/verify-multiclient.sh --exe <exe> --gateway-port P --nakama-port P --nakama-key KEY
  --status-url URL [--count N] [--kube-context CTX | --redis-container NAME] [--settle S] [--keep]`:
  asserts distinct Nakama users, all IN WORLD, no FATAL, `/status` players_online == N, same server
  address (ADR-2), N Redis session keys, one `servers:map:<map>` member; captures screenshots for the
  "N capsules visible" row a human must judge. Evidence line: `<P> passed, <F> failed, <S> not checked`;
  exit 0 only when every ASSERTED row passed. NOT CHECKED rows are reported, never counted as pass.
  `--kube-context` uses `kubectl exec` (gate); the Nakama key comes from a cluster secret (gate).

## Client: device benchmark (`docs/DEVICE-BENCHMARK.md`)

`BenchmarkRecorder` + `Assets/Scenes/DeviceBenchmark.unity`, config `DeviceBenchmarkConfig.asset`
(warm-up 10 s, settle 2 s, ramp 250 -> 500 -> 1000 entities x 30 s, ~100 s total). Desktop overrides:
`-benchWarmup`, `-benchSettle`, `-benchPhases 250:30,...`, `-benchNoQuit`; Android uses only the baked
asset. Development-build numbers are relative (run-to-run), not absolute; discard the first run after
install; 2-minute cooldown between runs; >10% p95 disagreement between repeats = throttling.
GPU time reads 0 unless Frame Timing Stats is enabled.
