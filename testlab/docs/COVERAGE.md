# Testlab coverage map

What the testlab proves today for each readiness area of the MMO core loop, through which
scenario and which check, and what it does not prove. Scenario files: `testlab/scenarios/`.
Checks: `testlab/lab/analyze.py` (`CHECKS`). `provenance` and `host_quiet` are appended to every
run and are not repeated below.

Status: **COVERED** - a scenario drives the behaviour and a check fails when it breaks.
**PARTIAL** - some of it is checked, or only incidentally (the check passes without exercising the
behaviour). **GAP** - nothing fails when it breaks. **(unrun)** - the scenario and checks exist and
are unit-tested, but no lab run has used them yet (S11 and S12 were added on 2026-10-22, T12).

Gaps are split by what closing them needs. **Factory-only** gaps need a scenario or a check in
this repo and nothing else. **Client hook** gaps need a change in the TestLab runtime of
IndieRPGMMOAdventure (`Assets/TestLab/Runtime/`). That work belongs to the Unity writer, so it is
listed here for the Lead and not implemented. **Server hook** gaps need a change in rpg-mmo-server.

## Map

| Area | Status | Scenario(s) | Check(s) | What is not proven |
|---|---|---|---|---|
| Tick-rate handling | COVERED (unrun) | S12 (30 Hz critical / 15 Hz world), S01, S02, S04, S05, S07, S09 | S12: `server_config` (the rates were in force), `server_tick` vs 30 Hz, local `position_divergence`, `render_jumps` local, `prediction_bound`, `snapshot_cadence` at 15 Hz; elsewhere `server_tick`, `snapshot_cadence` | The client's own tick rate is not recorded (hook C1); a wrong rate shows only through divergence, jumps and snaps |
| Reconciliation / replay | PARTIAL | S02-S06, S08-S10, S12 | `position_divergence` local (predicted player vs server path), `render_jumps` local_major / local_minor, `prediction_bound` (hard snaps per client-minute) | `max_correction` is reported, not judged (respawns dominate it). Nothing injects latency, loss or reordering (F7, out of scope), so replay runs only on a loopback path |
| Snaps after stalls | PARTIAL | every scenario, incidentally | `host_stalls` makes stall-explained gaps and jumps INCONCLUSIVE; `snapshot_cadence`, `render_jumps` | Nothing causes a stall on purpose. Recovery after a stall is graded only when the host happens to stall |
| Interpolation at rest | COVERED | S02 (idle clients), S05 | `position_divergence` remote mobs, `render_jumps` remote, `enemy_render_speed` | - |
| Interpolation in motion | COVERED | S03, S06 (known schedules, negative coordinates), S10 | `position_divergence` remote players and mobs (layer attribution), `render_jumps`, `enemy_render_speed` | - |
| Interpolation after respawn | PARTIAL | S02, S05, S09, incidentally | `render_jumps` sets server teleports (respawns) aside, using the client's received stream | No scenario forces a player death. A respawn is graded only when enemies kill a player by chance |
| Snapshot ordering and freshness | COVERED | S01-S12 (`snapshot_order`), S11, S12 (`render_freshness`) | `snapshot_order` (no backward or repeated tick within a session; snapshots.ndjson and C2 delivery.csv), `snapshot_cadence`, `snapshot_update_gap`, `render_freshness` (C2 render age p99 <= TargetDelay + MaxExtrapolation), `analyze --delivery` (diagnostic) | `render_freshness` needs a player with the C2 recorder; it is INCONCLUSIVE on every run before it |
| Entity spawn / despawn / ID reuse | PARTIAL | S02, S09 | `entity_stability` (count drift), `spawn_overlap` (player placement) | No check that a despawned entity disappears on every client, or that a reused id is not drawn with the previous entity's state |
| Join | COVERED | S01 (all), every scenario | `clients_in_world`, `distinct_user_ids`, `same_game_server`, `players_online`, `redis` | - |
| Disconnect / reconnect | COVERED | S08 | `reconnect` (same user, one entity, no duplicate session), `players_online`, `redis`, `kcp_health` | A graceful disconnect (quit, not kill) inside the window is not a scenario |
| Resync after a server restart | COVERED (unrun) | S11 | `clients_in_world` with `reentered_after_s`, `players_online` (last), `snapshot_cadence` outside the grace window, `snapshot_order` (a new session may restart ticks), `position_divergence` and `render_jumps` after the grace window | The 20 s grace window (20-40 s) is a first estimate: docker restart, boot, registration and reconnect; the first run measures it. Server-side counters reset with the restart, so `kcp_health` and `server_tick` are not graded in S11 |
| Multi-client convergence | PARTIAL | S03, S06, S10 | every client's rendered remote players vs the server path (`position_divergence`), `same_game_server` | Convergence is shown through the server as the shared reference. Nothing compares client A's view of B with B's own view at the same tick |
| Player spawn distribution | COVERED | S01, S04, S05, S10 | `spawn_overlap` (first appearance and respawn, nearest other player >= 0.5) | - |
| Player respawn | PARTIAL | S04, S05, incidentally | `spawn_overlap` counts respawns it sees | No deterministic death, so respawn placement and timing are judged only when a death happens |
| Enemy target acquisition | COVERED | S02, S05, S10 | `enemy_pursuit` (isolated far enemies head for the nearest live player), `enemy_crowding` (target share, INFO) | - |
| Enemy separation | COVERED | S02, S05, S10 | `enemy_crowding` with `overlap_is_failure` | - |
| Enemy bounded movement | PARTIAL | S11 (`enemy_bounds`, dev_arena), S02, S05, S10 | `enemy_bounds` (map bounds from content/maps/<map>.json at the run's server commit; blocking boxes reported), `enemy_server_speed`, `enemy_render_speed`, `enemy_pursuit` settled speed | Only maps with a file have known bounds: `map_01` (S02, S05, S10) has none, so `enemy_bounds` is INCONCLUSIVE there until /status reports the fallback bounds (server hook S4). Box penetration is INFO: whether enemies collide with boxes is a gameplay rule |
| Enemy budget and overload | PARTIAL | S02, S04, S05, S07 (`sweep`), S09, S10 | `enemy_budget` (live enemies <= the budget /status reports in force, `budget=300` at 11f0140), `server_tick`, `kcp_health`, `snapshot_cadence`, `snapshot_update_gap` (shed ratio reported), `bots_joined` | With 3 clients the cap is 30 + 45 x 3 = 165, so the budget is never reached (`budget_reached: false`); only an S07 sweep level with 6 or more players (clients + bots) pushes the population to it. Shedding under overload is reported, not graded |
| Combat authority | PARTIAL | S04 | `combat_effect` (scripted casts through the real cast path damage enemies on the server) | Only the positive path. Nothing proves that the server refuses an out-of-range cast, a cast faster than its cooldown, or damage the client claims |

## Gaps for the Lead

### Factory-only (no client or server change)

| # | Gap | State |
|---|---|---|
| F1 | Resync after a server restart | **Done (T12), unrun:** scenario S11 |
| F2 | Snapshot ordering | **Done (T12):** check `snapshot_order`, in every scenario. On the 2026-10-22 runs it finds 0 backward and 0 duplicate ticks |
| F3 | Render freshness | **Done (T12), unrun:** check `render_freshness` in S11 and S12. The bound is cited configuration, not a choice: TargetDelay + MaxExtrapolation of Netcode `InterpolationConfig.Default` (100 + 50 ms), which the client uses |
| F4 | Enemy map bounds | **Done (T12):** check `enemy_bounds` (S11). INCONCLUSIVE on map_01, which has no map file (server hook S4) |
| F5 | Enemy budget | **Done (T12):** check `enemy_budget` against the budget the server reports (`/status enemy_ai budget=N`); the lab sets no budget. Reaching the budget needs an S07 sweep level with 6 or more players |
| F6 | Non-default tick rate | **Done (T12), unrun:** scenario S12 (30/15 Hz) |
| F7 | Network impairment | **Out of scope, limitation:** `tc netem` on the scratch UDP port changes shared WSL networking and needs the user's approval. Until then, reconciliation and delivery are tested only on loopback |
| F8 | Server delivery trace | Open: rpg-mmo-server must forward `GAMESERVER_SNAPSHOT_TRACE` in `backend/deploy/docker-compose.yml` (like `GAMESERVER_DEBUG_ENTITIES`) and implement contract C1. Until then `--snapshot-trace` refuses to start (see Server hooks) |

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
| S4 | Map id and bounds in force | `/status` fields `map_id` and the bounds in force (from the map file, or the flat `--map-width`/`--map-height` fallback). Today the lab reads the map id from the stack settings and the redis registration, and has no bounds for maps without a file |
