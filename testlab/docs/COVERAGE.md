# Testlab coverage map

What the testlab proves today for each readiness area of the MMO core loop, through which
scenario and which check, and what it does not prove. Scenario files: `testlab/scenarios/`.
Checks: `testlab/lab/analyze.py` (`CHECKS`). `provenance` and `host_quiet` are appended to every
run and are not repeated below.

Status: **COVERED** - a scenario drives the behaviour and a check fails when it breaks.
**PARTIAL** - some of it is checked, or only incidentally (the check passes without exercising the
behaviour). **GAP** - nothing fails when it breaks.

Gaps are split by what closing them needs. **Factory-only** gaps need a scenario or a check in
this repo and nothing else. **Client hook** gaps need a change in the TestLab runtime of
IndieRPGMMOAdventure (`Assets/TestLab/Runtime/`). That work belongs to the Unity writer, so it is
listed here for the Lead and not implemented. **Server hook** gaps need a change in rpg-mmo-server.

## Map

| Area | Status | Scenario(s) | Check(s) | What is not proven |
|---|---|---|---|---|
| Tick-rate handling | PARTIAL | S01, S02, S04, S05, S07, S09 | `server_tick` (achieved rate, tick p99 vs 1/SIM_CRITICAL_HZ), `snapshot_cadence` (rate vs SIM_WORLD_HZ) | No scenario runs the server at a non-default rate. Nothing checks that the client adopts the advertised tick rate (client d4ac616, Netcode#183) |
| Reconciliation / replay | PARTIAL | S03, S06, S10 | `position_divergence` local (predicted player vs server path), `render_jumps` local_major / local_minor | Prediction counters (`snaps`, `reconciles`, `max_correction`) are recorded in summary.json, but no check bounds them. Nothing injects latency, loss or reordering, so replay runs only on a loopback path |
| Snaps after stalls | PARTIAL | every scenario, incidentally | `host_stalls` makes stall-explained gaps and jumps INCONCLUSIVE; `snapshot_cadence`, `render_jumps` | Nothing causes a stall on purpose. Recovery after a stall is graded only when the host happens to stall |
| Interpolation at rest | COVERED | S02 (idle clients), S05 | `position_divergence` remote mobs, `render_jumps` remote, `enemy_render_speed` | - |
| Interpolation in motion | COVERED | S03, S06 (known schedules, negative coordinates), S10 | `position_divergence` remote players and mobs (layer attribution), `render_jumps`, `enemy_render_speed` | - |
| Interpolation after respawn | PARTIAL | S02, S05, S09, incidentally | `render_jumps` sets server teleports (respawns) aside, using the client's received stream | No scenario forces a player death. A respawn is graded only when enemies kill a player by chance |
| Snapshot ordering and freshness | PARTIAL | S01, S02, S03, S06, S07, S09 | `snapshot_cadence` (receive gaps), `snapshot_update_gap` (server per-entity gap), `analyze --delivery` (diagnostic: gap classes, one-way delay, render age) | No check that world ticks arrive in order and without regressions per client. Render age (`snapshot_age_ms`) is not graded |
| Entity spawn / despawn / ID reuse | PARTIAL | S02, S09 | `entity_stability` (count drift), `spawn_overlap` (player placement) | No check that a despawned entity disappears on every client, or that a reused id is not drawn with the previous entity's state |
| Join | COVERED | S01 (all), every scenario | `clients_in_world`, `distinct_user_ids`, `same_game_server`, `players_online`, `redis` | - |
| Disconnect / reconnect | COVERED | S08 | `reconnect` (same user, one entity, no duplicate session), `players_online`, `redis`, `kcp_health` | A graceful disconnect (quit, not kill) inside the window is not a scenario |
| Resync after a server restart | GAP | none | none | The `restart_gameserver` disruption exists, but no scenario uses it |
| Multi-client convergence | PARTIAL | S03, S06, S10 | every client's rendered remote players vs the server path (`position_divergence`), `same_game_server` | Convergence is shown through the server as the shared reference. Nothing compares client A's view of B with B's own view at the same tick |
| Player spawn distribution | COVERED | S01, S04, S05, S10 | `spawn_overlap` (first appearance and respawn, nearest other player >= 0.5) | - |
| Player respawn | PARTIAL | S04, S05, incidentally | `spawn_overlap` counts respawns it sees | No deterministic death, so respawn placement and timing are judged only when a death happens |
| Enemy target acquisition | COVERED | S02, S05, S10 | `enemy_pursuit` (isolated far enemies head for the nearest live player), `enemy_crowding` (target share, INFO) | - |
| Enemy separation | COVERED | S02, S05, S10 | `enemy_crowding` with `overlap_is_failure` | - |
| Enemy bounded movement | PARTIAL | S02, S05, S10 | `enemy_server_speed`, `enemy_render_speed`, `enemy_pursuit` settled speed | No check that enemies stay inside the map bounds or out of obstacles. `trajectory_bound` covers players only |
| Enemy budget and overload | PARTIAL | S07 / S07P with `sweep`, S09 | `server_tick`, `kcp_health`, `snapshot_cadence`, `snapshot_update_gap` (shed ratio reported), `bots_joined`, `memory_growth` (INFO) | Nothing checks that the enemy count stays at or below the budget (rpg-mmo-server#468). Shedding under overload is reported, not graded |
| Combat authority | PARTIAL | S04 | `combat_effect` (scripted casts through the real cast path damage enemies on the server) | Only the positive path. Nothing proves that the server refuses an out-of-range cast, a cast faster than its cooldown, or damage the client claims |

## Gaps for the Lead

### Factory-only (no client or server change)

| # | Gap | What to add |
|---|---|---|
| F1 | Resync after a server restart | Scenario with the `restart_gameserver` disruption, plus `clients_in_world` after it, `players_online`, `snapshot_cadence` outside a grace window, and `position_divergence` after it |
| F2 | Snapshot ordering | Check `snapshot_order`: per client, received world ticks never go backwards inside one session (`snapshots.ndjson` / C2 `delivery.csv` already carry the tick) |
| F3 | Render freshness | Check on C2 `render.csv` `snapshot_age_ms` (p99 and max per client), once the Unity writer's recorder ships it. The threshold is the user's decision |
| F4 | Enemy map bounds | Check that every enemy position in `/debug/entities` stays inside the map bounds from `backend/content/maps/<map>.json` |
| F5 | Enemy budget | Scenario with a set `GAMESERVER_ENEMY_*` budget, and a check that the live enemy count in `/debug/entities` never exceeds it. The budget value is the user's decision |
| F6 | Non-default tick rate | Scenario with `server_env` at a different SIM rate, plus the existing local divergence and jump checks |
| F7 | Network impairment | Harness support for `tc netem` on the scratch UDP port in WSL (delay, loss, reorder). It is lab infrastructure on shared host networking, so it needs the LAB SLOT and the user's approval |
| F8 | Server delivery trace | rpg-mmo-server must forward `GAMESERVER_SNAPSHOT_TRACE` in `backend/deploy/docker-compose.yml` (like `GAMESERVER_DEBUG_ENTITIES`) and implement contract C1. Until then `--snapshot-trace` refuses to start (see Server hooks) |

### Client hooks (Unity writer; exact hook)

| # | Gap | Hook needed in `Assets/TestLab/Runtime/` |
|---|---|---|
| C1 | Client adopts the server tick rate | `samples.ndjson` `pred` block and `summary.json` `prediction`: add `tick_hz`, the rate the predictor runs at, read from the predictor after join |
| C2 | Snaps after stalls on purpose | Plan action `{"kind": "stall", "t0": ..., "t1": ..., "ms": N}` in `TestLabPlan` / `TestLabInputPlanner`: block the main thread for N ms once (`Thread.Sleep`), with an `events.ndjson` `stall` event (start, end, ms) |
| C3 | Entity despawn / ID reuse | `events.ndjson` `entity_added` / `entity_removed` with `id`, `type`, world tick and the first rendered position (from the snapshot's added and removed lists) |
| C4 | Cross-client convergence at one tick | `samples.ndjson` rows already carry `world_tick`. Add the snapshot tick the rendered position was interpolated from (`render_tick` per sample, as in C2 `render.csv`), so two clients' views can be compared at the same server tick |
| C5 | Combat authority, negative path | Plan actions `cast_at_point` (`x`, `y`, beyond range) and `cast_spam` (interval below the cooldown), each logging the request in `inputs.ndjson`. The server side needs rejection counters (see Server hooks) |
| C6 | Graceful disconnect | Plan action `quit` at `t0` that leaves through the normal disconnect path, not a process kill, and writes `summary.json` |

### Server hooks (rpg-mmo-server)

| # | Gap | Hook |
|---|---|---|
| S1 | Deterministic death and respawn | A debug-only endpoint on the scratch server (`GAMESERVER_DEBUG_ENTITIES=on` builds only) that sets a player's HP to 0, so a scenario can force a respawn at a known time |
| S2 | Combat authority | `/metrics` counters for rejected casts by reason (range, cooldown, dead caster) |
| S3 | Delivery trace (C1) | `GAMESERVER_SNAPSHOT_TRACE` writer and the compose passthrough (F8) |
