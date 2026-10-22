# Testlab coverage map

What the testlab proves today for each readiness area of the MMO core loop, through which
scenario and which check, and what it does not prove. Scenario files: `testlab/scenarios/`.
Checks: `testlab/lab/analyze.py` (`CHECKS`). `provenance` and `host_quiet` are appended to every
run and are not repeated below.

Status: **COVERED** - a scenario drives the behaviour and a check fails when it breaks.
**PARTIAL** - some of it is checked, or only incidentally (the check passes without exercising the
behaviour). **GAP** - nothing fails when it breaks. **(unrun)** - the scenario and checks exist and
are unit-tested, but no lab run has used them yet (S11, S12 added 2026-10-22 in T12; S13, S08G and the
client-hook checks in T16; S14, S15 in T20).

Gaps are split by what closing them needs. **Factory-only** gaps need a scenario or a check in
this repo and nothing else. **Client hook** gaps need a change in the TestLab runtime of
IndieRPGMMOAdventure (`Assets/TestLab/Runtime/`). That work belongs to the Unity writer, so it is
listed here for the Lead and not implemented. **Server hook** gaps need a change in rpg-mmo-server.

## Map

| Area | Status | Scenario(s) | Check(s) | What is not proven |
|---|---|---|---|---|
| Tick-rate handling | COVERED (unrun) | S12 (30 Hz critical / 15 Hz world), S11, S13, S01, S02, S04, S05, S07, S09 | `tick_adoption` (every client sample's predictor `tick_hz`, hook C1, equals /status `tick_rate`; S11 also after the reconnect), S12: `server_config`, `server_tick` vs 30 Hz, local `position_divergence`, `render_jumps` local, `prediction_bound`, `snapshot_cadence` at 15 Hz | Needs a player with hook C1 (client 299b6c8); INCONCLUSIVE on earlier players |
| Reconciliation / replay | PARTIAL | S02-S06, S08-S10, S12 | `position_divergence` local (predicted player vs server path), `render_jumps` local_major / local_minor, `prediction_bound` (hard snaps no server respawn or teleport explains, per client-minute) | `max_correction` is reported, not judged (respawns dominate it). Nothing injects latency, loss or reordering (F7, out of scope), so replay runs only on a loopback path |
| Snaps after stalls | COVERED (unrun) | S13 (one client stalls 500 ms and 2000 ms, hook C2) | `stall_recovery` (local divergence p95 <= 0.5 from 1 s after each stall), `prediction_bound`, `render_jumps` local, `snapshot_cadence` outside the stalls; elsewhere `host_stalls` sets host-wide stalls aside | The 1 s recovery allowance is a test parameter, not a measured or product number |
| Interpolation at rest | COVERED | S02 (idle clients), S05 | `position_divergence` remote mobs, `render_jumps` remote, `enemy_render_speed` | - |
| Interpolation in motion | COVERED | S03, S06 (known schedules, negative coordinates), S10 | `position_divergence` remote players and mobs (layer attribution), `render_jumps`, `enemy_render_speed` | - |
| Interpolation after respawn | COVERED (unrun) | S14 (client 1 killed twice via /debug/kill), S02, S05, S09 incidentally | S14: `render_jumps` (remote major 0 beyond the server's own teleports), remote `position_divergence` (no overshoot), `prediction_bound` (client 1 snaps exactly at its 2 respawns) | Needs a server with hook S1 (rpg-mmo-server #475); without it the kill answers 404 and every dependent assertion is INCONCLUSIVE |
| Snapshot ordering and freshness | COVERED | every scenario (`snapshot_order`), S11, S12 (`render_freshness`) | `snapshot_order`, `snapshot_cadence`, `snapshot_update_gap`, `render_freshness` (C2 v2 render.csv: p99 of the render clock's overrun past the newest consumed tick <= MaxExtrapolation, 50 ms), `analyze --delivery` (diagnostic) | `render_freshness` needs C2 schema v2 (`rpg.testlab.delivery.v2`, client 299b6c8): v1 left `render_tick` empty, so v1 evidence is INCONCLUSIVE |
| Entity spawn / despawn / ID reuse | COVERED (unrun) | S04, S09, S08G (`entity_lifecycle`), S02, S09 | `entity_lifecycle` (hook C3: a removed entity is not drawn after removal + TargetDelay + MaxExtrapolation + one sample; a reused id is first drawn at its own spawn), `entity_stability`, `spawn_overlap` | Whether ids are reused at all depends on the server; a run without reuse checks only despawn (`reused_ids_checked: 0`) |
| Join | COVERED | S01 (all), every scenario | `clients_in_world`, `distinct_user_ids`, `same_game_server`, `players_online`, `redis` | - |
| Disconnect / reconnect | COVERED | S08 (crash + relaunch), S08G (graceful leave, unrun), S11 (server restart, unrun) | `reconnect`, `graceful_leave` (hook C6 quit: outcome left, server and other clients drop the player within 5 s, far under the 60 s KCP idle timeout), `players_online`, `redis`, `kcp_health` | In-process reconnect (`reconnect` action, hook C6) has no scenario yet |
| Resync after a server restart | COVERED (unrun) | S11 | `clients_in_world` with `reentered_after_s`, `players_online` (last), `snapshot_cadence` outside the grace window, `snapshot_order` (a new session may restart ticks), `position_divergence` and `render_jumps` after the grace window | The 20 s grace window (20-40 s) is a first estimate: docker restart, boot, registration and reconnect; the first run measures it. Server-side counters reset with the restart, so `kcp_health` and `server_tick` are not graded in S11 |
| Multi-client convergence | COVERED (unrun) | S06, S09, S11, S12 (`cross_client_convergence`), S03, S10 | `cross_client_convergence` (hook C4: two clients' rendered position of a remote entity at the same render tick, p95 <= 0.35, max <= 1.0), `position_divergence` against the server path, `same_game_server` | Needs a player with hook C4 |
| Player spawn distribution | COVERED | S01, S04, S05, S10 | `spawn_overlap` (first appearance and respawn, nearest other player >= 0.5) | - |
| Player respawn | COVERED (unrun) | S14 | `debug_kill_respawn` (each confirmed kill followed by /status player_respawns +1 and the player alive at full HP), `spawn_overlap` on the respawn placement, `entity_lifecycle` (no duplicate entity) | Respawn exists only with the enemy phase on: S14 keeps it on with no population and attacks off |
| Enemy target acquisition | COVERED | S02, S05, S10 | `enemy_pursuit` (isolated far enemies head for the nearest live player), `enemy_crowding` (target share, INFO) | - |
| Enemy separation | COVERED | S02, S05, S10 | `enemy_crowding` with `overlap_is_failure` | - |
| Enemy bounded movement | PARTIAL | S11 (`enemy_bounds`), S02, S05, S10 | `enemy_bounds` (bounds from /status `map_bounds`, hook S4, else content/maps/<map>.json; blocking boxes reported), `enemy_server_speed`, `enemy_render_speed`, `enemy_pursuit` settled speed | With hook S4, map_01 is judged too, but `enemy_bounds` is not yet in S02/S05/S10: it would be INCONCLUSIVE on a server without S4 |
| Enemy budget and overload | PARTIAL | S02, S04, S05, S07 (`sweep`), S09, S10 | `enemy_budget` (live enemies <= the budget /status reports in force, `budget=300` at 11f0140), `server_tick`, `kcp_health`, `snapshot_cadence`, `snapshot_update_gap` (shed ratio reported), `bots_joined` | With 3 clients the cap is 30 + 45 x 3 = 165, so the budget is never reached (`budget_reached: false`); only an S07 sweep level with 6 or more players (clients + bots) pushes the population to it. Shedding under overload is reported, not graded |
| Combat authority | COVERED (unrun) | S15, S04 | S15: `input_rejections` (`ability_on_cooldown` rises, hook S2), `cast_damage_bound` (enemy HP lost <= casts the cooldown allows x power; no hit beyond the projectile's reach), `combat_effect` positive control; S04 `combat_effect` | The client casts only the projectile ability, which has no aim-range check by design (`AbilityLogic.ValidateCast`): `ability_out_of_range` cannot be produced from the client's cast path, so range is judged by the projectile's reach instead. Entity- and ground-targeted abilities have no client cast path yet |

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

| # | Gap | State (hooks shipped in client 299b6c8, docs/TESTLAB.md "Coverage hooks") |
|---|---|---|
| C1 | Client adopts the server tick rate | **Done (client 299b6c8):** `pred.tick_hz` / `prediction.tick_hz`; graded by `tick_adoption` |
| C2 | Snaps after stalls on purpose | **Done:** plan action `stall` (`t0`, `ms`), event `stall`; scenario S13, check `stall_recovery` |
| C3 | Entity despawn / ID reuse | **Done:** `entity_added` / `entity_removed` / `entities_reset`; check `entity_lifecycle` |
| C4 | Cross-client convergence at one tick | **Done:** per-sample `render_tick` / `render_clock`; check `cross_client_convergence` |
| C5 | Combat authority, negative path | **Done:** `cast_at_point`, `cast_spam`; scenario S15, checks `input_rejections`, `cast_damage_bound` |
| C6 | Graceful disconnect | **Done:** plan action `quit` (and `reconnect`); scenario S08G, check `graceful_leave` |

### Server hooks (rpg-mmo-server)

| # | Gap | Hook |
|---|---|---|
| S1 | Deterministic death and respawn | **Done (rpg-mmo-server #475, c7ad277):** POST /debug/kill; harness disruption `debug_kill`, scenario S14 |
| S2 | Combat authority | **Done (#475):** `gameserver_inputs_rejected_total{map_id,reason}` with the combat reasons; check `input_rejections` |
| S3 | Delivery trace (C1) | `GAMESERVER_SNAPSHOT_TRACE` writer and the compose passthrough (F8) |
| S4 | Map id and bounds in force | **Done (#475):** /status `map_id`, `map_bounds`; `enemy_bounds` reads them first |
