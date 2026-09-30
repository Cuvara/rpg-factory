---
name: measure
description: Use when a task has to produce or change a number someone will rely on - a load or capacity run, a protobuf/JSON encoding sweep, a tick/AOI/allocation micro-benchmark, a device frame-time run, a multi-client "A sees B" verification, or re-baselining CORE-BASELINE-V1.md after a pin moved. Drives the legs across rpg-mmo-server and IndieRPGMMOAdventure and enforces expected value, control arm, run id and attribution. Not for ordinary unit/CI test runs (factory-core validation), not for changing server or client code to go faster (the repo skill owns that; this skill measures before and after), and not for quoting capacity from old docs.
argument-hint: "[what to measure, and the claim it should support]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# Measure - benchmarks, sweeps, baselines, multi-client proof

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** any result that will be written into a doc, PR, CHANGELOG, baseline table or
  decision: bandwidth, tick time, RAM/CPU, join success, snapshot cadence, frame time, "N clients
  see each other", before/after of an optimisation.
- **Not when:** pass/fail tests (Core's validation tiers), code changes themselves (hand to
  `server-realtime`, `server-services`, `client-integration`, `unity-package`), deploy work (`server-ops`).

## Scope

Cross-repo driver. Modules: `server.loadtest`, `server.measurement-docs` (`backend/docs/BENCHMARK.md`, `backend/docs/MEASUREMENT.md`,
`backend/docs/CORE-BASELINE-V1.md`, `backend/loadtest/results/`), `client.tools` (multi-client scripts); updates client
`docs/DEVICE-BENCHMARK.md` as an obligation; reads
`server.gameserver-dotnet` bench tests without editing them. Code edits discovered necessary go to
the owning repo skill as a leg. Get paths/checks per module from the registry:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo server --paths backend/loadtest/
bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo client --paths Tools/
```

## Workflow delta

1. **Write the measurement record first** (`references/measurement-record.md`): claim, object
   measured, expected value **with units** and why, control arm, absolute bound, run id, results path.
   No record, no run.
2. **Pick the leg and its instrument** (`references/legs.md`). Prefer one binary with a runtime flag
   over two builds (MEASUREMENT.md section 4). Micro-benches (`GameServer.Tests/Bench`) are local and
   cheap; load/sweep/multi-client legs are heavy and gated.
3. **Establish the control** on the same host, same session, same generator binary. A control from
   another day, commit or host load is labelled as such, not used as a control (MEASUREMENT.md 4).
4. **Pre-flight the environment**: nothing else deploying (`encoding-sweep.sh` checks `cd.yml`; do the
   same by hand for other legs), server fresh and `gameserver_entities == 0`, rates read from `/status`.
5. **Run** under the gate, writing to a new results dir `<date>-<branch>-<shortsha>[-<topic>]` under
   `backend/loadtest/results/`, raw JSON/logs kept.
6. **Read validity before value.** INVALID levels are excluded, not failed; DEGRADED is a result
   (`backend/loadtest/README.md` "Verdict"). Prove zeros can be non-zero.
7. **Attribute** every delta: who pays (server tick, server egress, client CPU/GC, generator) and where
   it appears (metric, histogram, column).
8. **Write back** through the owning doc only with the run named: `backend/docs/BENCHMARK.md` part/section, results
   README, `CORE-BASELINE-V1.md` row. Re-baseline per its section 6 when a pin moves; stop at
   "ready to tag core-baseline-vX" (tags are the lead's).

## Ownership

`measure` is the lead for measurement **harnesses** as well as write-ups: `GameServer.Tests/Bench/`
(module `server.bench`, server-realtime co-leads), `backend/loadtest/`, the measurement docs, client `Tools/`;
it co-leads Netcode's `PredictionLatencyMeasurement.cs` (`netcode.measurement`). A harness change still runs the
game server's build/test checks; a number quoted from a harness always follows the workflow below.

## Rules

- ADR-7: never quote a player-count ceiling. The generator shares the host with the server, so tick
  figures are lower bounds of unknown tightness; bandwidth reproduces (0.3%) and is the column to size
  on (`backend/deploy/CLAUDE.md` section 8, `results/2026-09-18-develop-3378bc9/README.md`).
- A control arm **and** an absolute bound, never one alone (MEASUREMENT.md "What a valid control still
  cannot see").
- Tick budget = `1/SIM_CRITICAL_HZ`, snapshot period = `1/SIM_WORLD_HZ`; results before the 2026-09-18
  rate fields were judged against one 66.67 ms constant and their tick verdicts are not comparable.
- Host wall clock runs 10-17% fast on this box (#153): rates come from monotonic clocks /
  `achieved_tick_hz`, never wall-clock deltas (BENCHMARK.md "The host clock").
- k3d serverlb is in the gameplay data path (#143): a k3d-cluster number is not a server number.
- Gateway admits `GATEWAY_CONN_RATE_PER_MIN` (default 10/min per IP): full-path runs above 10 players
  measure the limiter. Capacity runs use `-join direct` against a dedicated server.
- `-encoding` defaults to `proto`; name the arm in every result.
- Never change what a published number means without updating every document that quotes it
  (MEASUREMENT.md section 7).

## Generated & protected paths

- `backend/loadtest/results/**`: append-only evidence. Never edit or delete a committed run; add a new dir.
- `backend/deploy/.env`: secrets source used by BENCHMARK.md section 10 - **gate**; ask the user to export
  `JWT_SECRET` / `JOIN_TOKEN_SECRET` rather than reading the file.
- `CORE-BASELINE-V1.md` version table: changes only with a named run and a moved pin.

## Validation delta

Fast: `bash -n` on `backend/loadtest/scripts/*.sh`;
`python3 -B scripts/encoding-report.py results/encoding` renders tables (cwd `backend/loadtest`).
Bench micro-tests: `BENCH_TICK=1` / `BENCH_AOI=1` / `MEASURE_TIERING=1` gate them; under WSL pass
`WSLENV=<VAR>` to `dotnet.exe` or every bench **skips** and the run exits 0 - a skip is not a result.
External: load/sweep legs (stack up), multi-client (Windows player + stack), device runs (phone),
reported HUMAN_REQUIRED (external) with the exact command when not run.

## Human gates

- Starting/stopping stacks or bench containers (`make flow-up`, `stack.sh up`, `docker run ... rpg-gs-bench`,
  `docker restart`); `bench.sh`, `encoding-sweep.sh`, `./loadtest` against anything.
- Any load against a shared/staging/production target or the dev k3d cluster.
- `Tools/run-clients.sh` / `Tools/verify-multiclient.sh` (launch many Windows processes; `--kill` runs
  `taskkill.exe`), Unity player builds, device runs.
- Reading `.env` or cluster secrets (`kubectl get secret ...` for the Nakama key).
- Committing results/doc changes; `core-baseline-*` tags (lead only).

## Review checklist

- [ ] Record written before the run; expected value had units and a reason.
- [ ] Control arm differs in exactly one thing; absolute bound stated and checked.
- [ ] Validity gate read; INVALID levels excluded and listed; zero readings proven able to move.
- [ ] Run id + results path cited next to every number; generator host load noted.
- [ ] No ceiling quoted; tick numbers labelled as host-bound lower bounds.
- [ ] Docs that quote the changed number updated in the same change.

## Report additions

A **Measurements** table after Validation, one row per quoted number:
`claim | object | expected (units) | control | measured | run id / path | validity | attribution`.
Plus the contract-evidence table when the leg spans repos (e.g. server run + client verify).
