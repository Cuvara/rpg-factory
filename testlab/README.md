# rpg-factory testlab

Autonomous multiplayer gameplay tests with **real, rendered Unity clients**. One command:
- starts an isolated backend;
- launches several players with distinct identities;
- drives them through a scripted scenario with no keyboard, mouse or window focus;
- records what each client rendered and what the server said was true;
- grades the run PASS, FAIL or INCONCLUSIVE from that evidence.

Nobody has to watch the windows.

```
python3 testlab/testlab.py run S01            # 3-client smoke test (about 40 s)
python3 testlab/testlab.py suite full         # S01 S02 S03 S04 S05 S06 S08 S10 (about 12 min)
python3 testlab/testlab.py sweep S07 --levels 0,25,50,100,150,200   # load sweep
python3 testlab/testlab.py run S09 --duration 3600                  # 1-hour soak
```

Exit codes: `0` PASS, `1` FAIL, `2` INCONCLUSIVE or INVALID, `3` harness or usage error, `4` PASS_WITH_WARNINGS.

**PASS_WITH_WARNINGS** is the outcome when every assertion passed but an `informational` one would have failed (today the S07/S07P memory slope, informational because the bot ramp allocates by design). It is never a clean PASS. The report lists it, and host load, under **Qualified by** next to the verdict: host-wide stalls seen in the run, or CPU load of 50 % or more at start or end. Host qualifications do not change the outcome (the timing checks a stall explains are already INCONCLUSIVE); they say the timing came from a busy host.

`run`, `suite` and `sweep` stop the scratch stack when they finish: on success, failure, harness error and Ctrl-C. Pass `--keep-stack` to leave it running for the next invocation. Players are stopped at the end of every run in all of these cases.

### Where each command works

| Command | Windows Git Bash (or PowerShell, cmd) with Windows Python | WSL Ubuntu with Linux Python |
|---|---|---|
| `run`, `suite`, `sweep`, `stack`, `clean`, `build-client`, `build-loadtest` | yes | no: the players are Windows processes and process control uses `tasklist`/`taskkill` |
| `analyze`, `analyze --delivery`, `replay-trace`, `leak-check`, `list` | yes | yes (give `/mnt/c/...` paths) |
| `python3 -B testlab/tests/test_lab.py`, `test_netem.py`, `test_native.py`, `test_failsum.py` | yes | yes (`test_native.py` skips its Windows-only case) |

In Git Bash, `python3` must be the Windows Python (`python3.exe`). Git Bash rewrites `/c/...` arguments for Windows programs; the CLI also converts them itself, so they work with `MSYS_NO_PATHCONV=1` too. WSL commands are run from Python through `wsl.exe -d Ubuntu --exec bash -c` with path conversion disabled.

## What runs where

| Part | Repo | Path |
|---|---|---|
| Orchestrator, scenarios, analysis, reports | rpg-factory | `testlab/` |
| Input seam (`IGameplayInputSource`), production code | IndieRPGMMOAdventure | `Assets/Scripts/DI/GameplayInput.cs` |
| Test runtime (scripted input, recorder, screenshots, overlay) | IndieRPGMMOAdventure | `Assets/TestLab/Runtime/` (asmdef `NDC.TestLab`) |
| Test scene builder / validator | IndieRPGMMOAdventure | `Assets/TestLab/Editor/TestLabSceneBuilder.cs` |
| Test scene | IndieRPGMMOAdventure | `Assets/Scenes/Tests/MultiplayerCombatTest.unity` |
| Per-build scripting defines | IndieRPGMMOAdventure | `PlayerBuilder -extraDefines` |
| Authoritative positions | rpg-mmo-server | `GAMESERVER_DEBUG_ENTITIES=on` serves `/debug/entities` |
| Deterministic enemy spawns | rpg-mmo-server | `GAMESERVER_ENEMY_SEED` |
| Isolated stack | rpg-mmo-server | `backend/deploy/stack.sh --scratch` with `STACK_SCRATCH_EXTRA_ENV` |
| Raw wire client (S16, S17): gateway auth, enter world, KCP join, hand-built frames | rpg-factory | `testlab/lab/rawclient.py`, steps in `testlab/lab/rawprobe.py` |
| Packet impairment (S18): tc netem in the scratch game server container's network namespace | rpg-factory | `testlab/lab/netem.py`, checks in `testlab/lab/analyze_netem.py` |
| Native Windows game server (`--server-mode native`): build, compose-derived environment, child process, sampler | rpg-factory | `testlab/lab/native.py`, bring-up in `testlab/lab/stack.py` |

## Prerequisites

- Windows host (the players are Windows processes) and Python 3.10 or newer. The orchestrator uses only the standard library.
- WSL Ubuntu with a native `dockerd`. The lab never starts Docker Desktop. WSL stops a distro that has no open `wsl.exe` session (dockerd and the scratch stack go with it), so `run`, `suite` and `sweep` hold a keep-alive `wsl.exe` session for the whole invocation (`run.json` `wsl_keepalive`); without it a run can lose its gateway and Redis mid-scenario. A fresh world also starts with no `session:*` keys in the scratch Redis. S18 (packet impairment) also needs passwordless `sudo` for `nsenter` and `tc` in WSL, and the kernel modules `sch_netem`, `ifb` and `act_mirred` (the WSL2 kernel ships them); its preflight says which is missing before any player starts.
- Unity **6000.3.9f1**, to build the player (`build-client`).
- Go, to build the load generator (`build-loadtest`; only S07 needs it).
- An `rpg-mmo-server` checkout whose `stack.sh` has `STACK_SCRATCH_EXTRA_ENV`, and whose compose file forwards `GAMESERVER_DEBUG_ENTITIES`, `GAMESERVER_ENEMY_SEED` and `GATEWAY_CONN_RATE_PER_MIN`. The preflight refuses an older one by name.

Configuration (all optional) lives in `<runs_root>/testlab.config.json`. `runs_root` defaults to `<workspace>/.testlab-runs`. Example:

```json
{ "server_repo": "C:/Workspaces/UnityIndie/rpg-mmo-server",
  "client_project": "C:/Workspaces/UnityIndie/IndieRPGMMOAdventure" }
```

The same keys can be given as CLI flags (`--server-repo`, `--project`, `--player`, `--runs-root`). The scratch-stack ports and the Unity path are also keys (`lab/config.py`).

## First run

```
python3 testlab/testlab.py build-client      # scene build -> scene validate -> player (CUVARA_TESTLAB)
python3 testlab/testlab.py build-loadtest    # only for S07
python3 testlab/testlab.py run S01
```

`build-client` runs Unity batch steps in the configured project:
1. Only with `--rebuild-scene`: `TestLabSceneBuilder.Build` regenerates the test scene from `MainScene`. Regeneration is not byte-deterministic, so by default the committed scene is used.
2. `TestLabSceneBuilder.Validate` fails on missing scripts, a missing `MainSceneScope` or `DotsWorldBridge`, or a missing arena.
3. `PlayerBuilder.Build` builds the player with `-bootScene Assets/Scenes/Tests/MultiplayerCombatTest.unity -extraDefines CUVARA_TESTLAB`.

It writes `testlab-build.json` next to the player: the client commit, uncommitted changes, defines, and every package embedded under `Packages/`. Its `netcode` block names the Netcode commit the build compiled: the HEAD of an embedded git clone, or the `packages-lock.json` hash of the manifest pin. An embedded copy without `.git` has no commit to name; such a build must carry `VERIFY-PROVENANCE.txt` (`netcode <sha> client <sha>`, written by the verification build script) or its runs grade provenance INCONCLUSIVE. The run's provenance record reads both files.

## Test code in production builds (`leak-check`)

```
python3 testlab/testlab.py leak-check <player exe | build dir | StandaloneWindows64 | _Data | Managed>
python3 testlab/testlab.py leak-check <testlab build> --expect-testlab
```

It inspects a built player without running it: every `Managed/*.dll`, `ScriptingAssemblies.json` and `RuntimeInitializeOnLoads.json` (Mono), or `GameAssembly.dll` and `global-metadata.dat` (IL2CPP). A finding is an `NDC.TestLab*` assembly, the `CUVARA_TESTLAB` define string, or a TestLab runtime type name (`TestLabRunner`, `ScriptedInputSource`, `DeliveryRecorder`, ...), in UTF-8 or UTF-16. The verdict is `CLEAN`, `TESTLAB_PRESENT` or `ERROR` (no player found, never clean). Exit `0` when the build matches the expectation (clean, or with `--expect-testlab` present), `1` when it does not, `3` on error. It does not build anything.

## Design (architecture decision record)

**Decision 1 - drive the production input path, not the transform.** `DotsWorldBridge` and `GameplayPanelDriver` read every control through `GameplayInput.Source` (`IGameplayInputSource`). In a normal build this is `DeviceGameplayInputSource`, with the same device reads as before. The testlab installs `ScriptedInputSource`. Everything downstream stays on the production path: the send schedule, `SendInput`, `LocalMovePredictor.RecordInput`, clock steering and projectile prediction. Rejected alternatives:
- OS key injection. The Input System drops input to an unfocused window, and the lab must not need focus.
- A second `SendInput` caller. It would make the recorded and sent input streams diverge.
- Transform writes. These would bypass exactly what is under test.

**Decision 2 - the runtime ships only in testlab builds.** `NDC.TestLab` has `defineConstraints: ["CUVARA_TESTLAB || UNITY_INCLUDE_TESTS"]`. It compiles in the Editor, so EditMode tests cover it, and in players built with `-extraDefines CUVARA_TESTLAB`. It is absent from a normal player; `leak-check` verifies a given build (`control-no-define` is `CLEAN`, the testlab builds are `TESTLAB_PRESENT`). Even inside a testlab build it does nothing unless the player is started with `-testlab-plan`.

**Decision 3 - the test scene is generated, not edited.** `MultiplayerCombatTest.unity` is MainScene plus a script-free `TestLabArena`: a 5-unit ground grid and a mirror of the server collision boxes, shown only for the map that defines them. Spawn points, obstacles and enemy density are server-authoritative. A scenario sets them through the server configuration (map id, `GAMESERVER_ENEMY_*`, seed), so the scene cannot drift from the game.

**Decision 4 - evidence from both sides, compared without trusting either clock.**
- Each client records the following, on the monotonic clock plus a shared scenario clock: inputs, snapshot arrivals, received and rendered positions of every entity at 20 Hz, per-frame rendered-step jumps, frame times, prediction counters and screenshots.
- The orchestrator records authoritative positions (`/debug/entities`, 5 Hz), `/status` (1 Hz), `/metrics` (scenario start and end) and container CPU/memory, stamped with the same scenario clock.
- The shared clock is a wall-clock start instant written into `control.json` once every client is in the world. Each process maps it onto its monotonic clock once.
- No check uses wall-clock deltas; this host's clock runs fast (rpg-mmo-server#153).

**Decision 5 - isolation.** Only the scratch compose project is touched (`rpg-mmo-scratch`, containers `rpgs-*`, ports 9000/9300/9501/8350, image tags `:scratch`).
- It uses `docker-compose.yml` only. The default stack's override, which published the default stack's ports, is no longer auto-loaded in scratch mode.
- The lab generates its own JWT and join-token secrets under `runs_root/stack/` and never reads the developer's `.env`.
- Players are started directly from Python. Their PIDs are recorded and are the only processes the lab kills; a PID is killed only while it is still the player executable.
- A developer's own stack and clients keep running throughout.

**Decision 6 - assertions are data, results are three-valued.** A scenario lists its assertions; each one names a check in `lab/analyze.py`. Every check returns:
- what it measured;
- its source and sampling;
- the threshold and the rationale;
- its artifacts.

Missing evidence is INCONCLUSIVE, never PASS. A check that raises is INCONCLUSIVE. INFO is reported but never decides the run.

## Scenarios

| Id | What it proves |
|---|---|
| S01 | Bootstrap: 3 clients, distinct users, one game server (ADR-2), sessions, snapshot cadence, KCP, tick rate |
| S02 | Idle stability while the enemy population fills: render vs server divergence, jumps, enemy speed, crowd shape |
| S03 | Movement and collision on `dev_arena` (enemies off): every scripted segment reaches the server, local and remote divergence, north-wall collision |
| S04 | Combat through the real projectile cast path: enemies damaged on the server |
| S05 | Enemy targeting and crowding: together, spread, retreat, approach, target switch |
| S06 | Replication and interpolation under known schedules, including negative coordinates |
| S07 | Load: rendered clients plus `backend/loadtest` bots; run with `sweep` |
| S08 | Reconnect: a client process is killed and relaunched on the same device |
| S09 | Soak: memory slope, entity drift, accumulated errors (default 300 s); the 300 s cycle repeats for the whole `--duration` (`repeat_cycle_s`). Soaks before S09 v4 (eeoa, sfj5, y6vg) ran it once: 5 min active, then idle |
| S10 | Regression replay of the 2026-10-21 report, with before/after reference numbers |
| S11 | Resync after a game-server restart (`restart_gameserver` at 20 s, grace window 20-40 s): clients back InWorld, ticks restart only in a new session, cadence and rendering judged outside the grace window |
| S12 | S03's movement with the server at 30 Hz critical / 15 Hz world (`SIM_CRITICAL_HZ`, `SIM_WORLD_HZ`): the client must adopt the advertised tick rate; `server_config` proves the rates were in force |
| S13 | Client stall recovery: client 0's main thread stops 500 ms at 10 s and 2000 ms at 25 s (plan action `stall`); graded by `stall_recovery`, `prediction_bound` and `render_jumps` local |
| S08G | Graceful disconnect: client 2 walks 6 s (about 30 units, inside every viewer's 50-unit AOI) and leaves at 15 s with plan action `quit` (`NetworkClient.Disconnect()`); `graceful_leave`, outcome `left`, 2 players online at the end |
| S14 | Deterministic death and respawn: client 1 killed at 12 s and 27 s with disruption `debug_kill` (POST /debug/kill); enemy phase on with no population and attacks off. Graded: respawn, spawn placement, client 1 snaps only at its respawns, remote clients without jump or overshoot, no duplicate entity |
| S15 | Combat authority, negative path: client 0 `cast_spam` every 100 ms (below the ability cooldown) and `cast_at_point` beyond the projectile range; `input_rejections` (`ability_on_cooldown`) and `cast_damage_bound` |
| S16 | Malformed input: two rendered clients play while a raw-client step sends, one fresh session per case, a length prefix over the 1 MiB limit (two values), a zero length, a truncated frame then silence, an undefined and an out-of-range message type, a garbage protobuf envelope, a valid Input envelope with a garbage payload, out-of-range movement vectors, attacks beyond the attack range and casts inside the cooldown. Graded: `server_alive`, `server_tick`, `malformed_input` (each case refused or closing only its own session, with the server counters that moved), `client_sessions`, `snapshot_cadence` |
| S17 | Churn: a raw-client step runs 10 cycles of drop (both sockets closed, no `MsgDisconnect`) plus rejoin and graceful leave plus rejoin through the real join path, then waits out the longest server hold. Graded: `churn_cycles`, `churn_ghosts` (no entity nobody owns; leaver gone within 5 s for the server and the rendered clients; dropped player gone by 75 s; quiet-window entity counts), `player_count_baseline`, `redis_leak` (key names before and after), `entity_lifecycle`, `client_sessions` |

## Readiness checks with derived bounds

- `snapshot_order`: per client, received world ticks never go backwards and never repeat inside one session. A session starts at each `net_state` InWorld event, so a reconnect to a restarted server may restart the ticks. It reads `snapshots.ndjson` and, when present, C2 `delivery.csv`.
- `enemy_bounds`: every live enemy in `/debug/entities` stays inside `bounds` of `backend/content/maps/<map>.json`, read at the server commit of the run (`git show`). The map id comes from the stack's `GAMESERVER_MAP_ID`, checked against the scenario and the server's redis registration (`/status` has no map id). A map without a file is INCONCLUSIVE: the server's flat fallback bounds are not reported. Enemies inside a blocking box (top more than 0.4 above the ground, `content/README.md`) are INFO unless `obstacles_are_failure`.
- `enemy_budget`: live enemies (`/status enemies_alive`, `/debug/entities`) never exceed the hard budget the server reports in force (`/status enemy_ai` `budget=N`, `GAMESERVER_ENEMY_BUDGET`). The lab sets no budget. `budget_reached` says whether the run pushed the population that far.
- `render_freshness` (C2 `render.csv`, schema `rpg.testlab.delivery.v2`): per frame, how far the render clock that drew it ran past the newest tick it had consumed, **overrun_ms = max(0, render_tick - clock_newest_tick) / tick_hz x 1000; p99 <= MaxExtrapolation = 50 ms** (Netcode `InterpolationConfig.Default`, which the client's `DotsWorldBridge` uses). Normally the clock runs TargetDelay (100 ms) behind the newest tick, so the overrun is 0; past MaxExtrapolation the interpolator holds remote entities still, a freeze the player saw. `tick_hz` is `/status tick_rate`. The clock is WorldViewBinder's (`clock_source: binder`) or the ECS one (`ecs`). Schema v1 players wrote an empty `render_tick` (the ECS clock is never fed on the untimed `SetState` path), so v1 evidence is INCONCLUSIVE. `snapshot_age_ms` (receive age of the newest snapshot) is reported alongside. Frames inside host-wide stalls are set aside.
- `prediction_bound`: **at most 4 unexplained hard prediction snaps per client-minute.** A teleport must snap: every idle snap on the fixed builds is a server respawn of that player (T17-NET-IDLESNAP). So each rise of `pred.snaps` in `samples.ndjson` is matched by world tick (window 60 ticks) to a respawn (dead to alive, or HP below half to full) or a non-walkable step of the same player in `/debug/entities`; matched snaps are reported as explained, the rest are graded. Derived from every stored run of 2026-10-21/22: the fixed builds leave at most 2.0 unexplained per client-minute (S07 `20261022T091437Z-S07-c5hc`), every pre-fix run has a client at 7.5 or more (S10 `20261022T054359Z-S10-g0tz`); 4 is twice the first and about half the second (`.testlab-runs/reanalysis/T16-FAC-V2/prediction-bound-derivation.log`). `max_correction` is reported, not judged. Windows shorter than 20 s, or snaps without per-sample counters, are INCONCLUSIVE.
- `server_config`: the `SIM_*` rates a scenario sets (or an `expect` map of `/status` fields) are what `/status` reports in every sample. Otherwise INCONCLUSIVE: the run did not test the configuration it names.
- `snapshot_cadence` and `render_freshness` accept `exclude_s: [[t0, t1], ...]` (scenario seconds) for an interruption a scenario causes on purpose. `clients_in_world` accepts `reentered_after_s`.
- `tick_adoption` (client hook C1): every sample's predictor `pred.tick_hz` and `summary.json` `prediction.tick_hz` equal `/status tick_rate`, the rate the server advertises in `JoinTokenResponse.tick_rate`.
- `entity_lifecycle` (hook C3): an entity in `entity_removed` at time t is in no rendered sample after t + TargetDelay + MaxExtrapolation (150 ms) + one sample period, unless its id is added again; a reused id's first rendered position (`entity_added` `rx`, `ry`) is within max_speed x 150 ms + 0.2 of its own first snapshot position, not where the previous entity was. INCONCLUSIVE without a removal.
- `cross_client_convergence` (hook C4): for every pair of clients, A's rendered position of a remote entity at render tick T against B's, interpolated between B's two samples around T. p95 <= 0.35, max <= 1.0: the thresholds of the remote `position_divergence` assertions. Pairs across a server teleport are skipped, and so are the samples of a client that is not a valid observer (M4/H2): from 0.5 s before to 2 s after a net_state other than InWorld (Ended, Reconnecting, ...), a gap of 1 s or more in its sample stream, or a frame of 1 s or more. The skipped spans are listed per client under `detail.skipped_client_gaps` (class `CLIENT` or `RECONNECT`, samples skipped). Convergence errors outside those spans still FAIL.
- `stall_recovery` (hook C2): after each `stall` event, the stalled client's local player is back on the server path: local divergence p95 <= 0.5 (the S03/S10/S12 local bound) over [end + 1 s, end + 4 s]. The 1 s recovery allowance is a test parameter. Hard snaps during each stall are reported.
- `graceful_leave` (hook C6): a client that ran `quit` ends with outcome `left` and a `disconnected` event, and its player is gone from `/debug/entities` (and from the other clients, with C3) within 5 s. A viewer that had already dropped the leaver out of its area of interest before the quit is reported as `not_in_view_at_quit` and a viewer with no lifecycle event for the leaver as `no_lifecycle_events`; neither is judged, and with no judged viewer left the check is INCONCLUSIVE, never PASS (a judged viewer that missed the removal FAILs); S08G keeps the leaver inside every viewer's 50-unit AOI so all viewers are judged. That is a test bound far under the 60 s KCP idle timeout (`KcpTuning.IdleTimeoutMs`) that cleans up a silent client.
- Plan actions `stall` (`ms`), `quit`, `reconnect`, `cast_at_point` (`x`, `y`) and `cast_spam` (`interval_ms`) are accepted and expanded (client `docs/TESTLAB.md` "Coverage hooks"); one-shot actions need only `t0`. `clients_completed` takes `expected_outcomes` (e.g. `{"2": "left"}`).
- `repeat_cycle_s` (scenario): each client's steps and actions repeat every N seconds until `duration_s`; the first cycle is unchanged.
- Preflight: without `--build-server`, a server worktree with no `backend/deploy/modules/nakama.so` (the Nakama plugin that `--build-server` builds) fails fast instead of timing out every join.
- Disruption `debug_kill` (`at_s`, `client`): POST `/debug/kill` `{"id": <user id>}` on the scratch server (rpg-mmo-server hook S1, `GAMESERVER_DEBUG_ENTITIES=on`). Every disruption is recorded in `disruptions.ndjson` with its scenario time; a kill records the HTTP status, outcome, server tick and `hp_before`. An assertion with `requires_debug_kill: true` is INCONCLUSIVE when no kill ran or one was not confirmed (anything but HTTP 200 `killed`).
- `debug_kill_respawn`: each confirmed kill is followed within 2 s by /status `player_respawns` +1 and the player alive at full HP (the respawn runs within one world interval; /status is probed at 1 Hz).
- `input_rejections`: `gameserver_inputs_rejected_total{reason}` deltas (hook S2): `expect_positive` reasons rose, `expect_zero` reasons did not. A server without a reason's series is INCONCLUSIVE.
- `cast_damage_bound`: in each `cast_spam` / `cast_at_point` window of the one casting client, enemy HP lost <= (floor(window / cooldown) + 1) x the ability's damage power, and for `cast_at_point` no enemy farther than range + radius + 1 from the caster loses HP. Ability = the content's first projectile ability (what the client casts), read from `content/abilities.json` at the run's server commit. Projectiles have no aim-range check (`AbilityLogic.ValidateCast`), so a beyond-range aim is accepted and must expire at its range.
- `enemy_bounds` reads `/status` `map_bounds` first (hook S4; source `map_file` or `configured_size`) and falls back to the map file; with neither it is INCONCLUSIVE.
- `prediction_bound` also takes `max_unexplained` (absolute, per client) and `expected_explained` (`{client: n}`); `entity_lifecycle` takes `require_removal: false` and fails on a sample that draws one id twice.

## Raw-client scenarios (S16 malformed input, S17 churn)

A Unity player cannot send what the protocol forbids, and starting a player takes seconds, so these two scenarios add a Python
wire client next to the rendered ones (`lab/rawclient.py`). It speaks the real join path: gateway TCP (`MsgAuth` with a gateway
JWT signed with the lab's `JWT_SECRET`, `MsgEnterWorld`), then KCP over UDP to the game server (`MsgJoinToken`). The KCP layer is
a minimal sender and receiver of kcp-go's segment format (in-order delivery, ACKs, retransmission with back-off; no congestion
control, FEC or encryption: the scratch stack sets no `TRANSPORT_KEY` and `GAMESERVER_SEALED=off`). Frames are JSON envelopes,
which the server sniffs per frame, so a broken protobuf body can follow a JSON join. The step (`lab/rawprobe.py`) is a scenario
disruption (`raw_malformed` with a `cases` list, `raw_churn` with `cycles`, `connected_s`, `drop_down_s`, `leave_down_s`,
`settle_s`) that runs on its own thread so the rendered clients and the server probe keep sampling on the scenario clock.

- The step only records (`rawprobe.ndjson`, one JSON object per line, part of the provenance manifest). Every verdict is made by
  the analyzer from that file and the server probe, with thresholds in the scenario and in `docs/THRESHOLDS.md`.
- `malformed_input`: per case, `connections` from `/status` before the offender joins, with it, and 2 s after; `closes` (within
  `within_s`, ends at the value before the join: only the offender went) or `stays_open` (ends one above, still receives
  snapshots); `rejections` ({reason: minimum} on `gameserver_inputs_rejected_total{reason}` between the read with the offender in
  and the final read); `max_displacement` (server position never moves faster than speed x elapsed + 0.5: positions are never
  client-supplied, so a "teleport" is only expressible as a movement vector); `beyond_attack_range` and `target_hp_unchanged`
  (an attack at an enemy farther than `GameConstants.AttackRange`, read from the server source, costs it nothing). The report
  lists, per case, every `gameserver_*` series that moved, so it shows which counter (if any) saw a bad frame. A `stays_open`
  case without a `rejections` rule is INCONCLUSIVE (`signal_missing`): the session surviving does not show the server refused or
  ignored the input. `rejections_counter` names another counter than the default `gameserver_inputs_rejected_total`. The
  undefined-type case (`unknown_type`, type 99) uses `gameserver_messages_rejected_total{reason="unknown_type"}` (rpg-mmo-server #490,
  `76aa973`: the message is ignored and the session stays open); a server without that series leaves the case INCONCLUSIVE, not FAIL.
  Before #490 the server had no counter or log line for it, and S16 graded INCONCLUSIVE.
- `server_alive`: every `/status` probe answered, `uptime_seconds` never goes backwards, no gap over `max_gap_s`.
- `client_sessions`: a rendered client logs no `net_state` change, `disconnected`, `entities_reset` or `reconnected` inside the
  scenario window.
- `churn_cycles`, `churn_ghosts`, `player_count_baseline`, `redis_leak`: see the S17 row above; the 75 s bound for a silent drop is
  PingInterval 10 s + PongTimeout 30 s (the longest the heartbeat takes to notice a silent peer) + the 30 s map hold
  (`EntityHoldTTL`) + 5 s slack. Redis session (`session:*`), registry (`servers:id:*`) and map-member (`servers:map:<map>`) key
  names are read from the scratch Redis only.
- Limits: a raw client is not a real client. It does not predict, interpolate or render, it answers heartbeats only while its
  script says so, and it cannot reach the sealed handshake (JSON clients cannot be sealed). The truncated-frame case takes about
  40 s (the heartbeat timeout), so S16 runs about 2 minutes; S17 about 3.5 minutes, most of it the wait for the hold to expire.

## Packet impairment (S18)

S18 puts loss, delay, jitter and reordering on the game server's UDP path for 60 s between a 30 s clean baseline and a 30 s recovery,
with two rendered clients moving the whole time, and grades what the transport and the netcode do about it.

**Mechanism and why** (`lab/netem.py` docstring has the long form). `nsenter -t <pid of rpgs-gameserver> -n tc ...` from WSL, inside the
scratch game server container's own network namespace. Nothing else changes: no compose override, no extra capability on the game server,
no image change, no process on the data path, no host-wide qdisc. The qdiscs vanish with the container if the harness dies. Rejected:
a scratch-only compose override with `NET_ADMIN` (a different container for one scenario, and a capability the production server does not
have) and a UDP proxy in the harness (the address clients dial is what the server registers in Redis and the gateway hands out, so a proxy
means changing what the stack advertises, and its own jitter would be measured). The cost: it needs passwordless `sudo` in WSL.

**What is shaped.** UDP port 9000 (the game port inside the container) and nothing else; `/status`, `/metrics` and every TCP connection of the
container are untouched. Server to client: `prio` root on `eth0` with the netem in band 3 and a u32 filter on UDP source port 9000. Client to
server: an `ingress` qdisc on `eth0` whose u32 filter on UDP destination port 9000 redirects to a per-container `ifb0` carrying the same netem.
The profile applies per direction (a round trip sees twice the delay and about twice the loss).

**Profile** (scenario disruption `netem`: `profile` {`loss_pct`, `delay_ms`, `jitter_ms`, `reorder_pct`}, `baseline_s`, `impaired_s`,
`recovery_s`, `directions`): 5 % loss, 40 ms +/- 20 ms (uniform) and 1 % reorder. The values and their sources are in
[`docs/THRESHOLDS.md`](docs/THRESHOLDS.md) "Impairment profiles": 40 ms is the one-way latency `CORE-BASELINE-V1.md` measured a real client
at, +/- 20 ms is inside the +/- 60 ms that client held (so a pass is expected), 5 % loss has no baseline measurement at all (policy, unvalidated).

**Cleanup contract.** The step removes the qdiscs and the `ifb0` device in a `finally`; the runner calls `netem.final_cleanup` in its own
`finally` (even when the step never ran); a watchdog (a detached long-running `wsl.exe` child that sleeps, then deletes; a process started inside WSL from a
short call does not survive the call) removes them after the planned time + 45 s, only if the namespace of that pid is still the recorded one; the preflight removes the leftover of a dead run before the players start. Every removal is
verified (`tc -j qdisc show`: no `netem`, `prio` or `ingress` qdisc; `ip link show ifb0`: absent) and the verdict is recorded; `netem_cleanup`
FAILs on an unverified one.

**Checks** (thresholds and derivations in `docs/THRESHOLDS.md`; phases from `netem.ndjson`, in scenario time: baseline up to the scrape before
the first tc command, impaired from the instant the last tc command returned to the scrape before the removal, recovery from the instant the
verified removal returned; the seconds the tc commands take are in no judged window):

- `netem_applied`: the impairment was on the path, three independent ways: every tc command returned 0; the kernel's own netem counters (packets
  passed and dropped, per direction) show a loss share within 3 binomial standard deviations of the configured loss over at least 300 datagrams;
  the clients' round-trip time rose by at least half the delay added to a round trip.
- `netem_cleanup`: the planned removal and the runner's final cleanup were both verified, the first at most 10 s after the impaired phase was due to end.
- `netem_retransmits`: `gameserver_kcp_segments_retransmitted_total` rose by at least 30 during the impairment, at at least 5 times the baseline rate
  (floored at 0.1/s), and fell to at most half the impaired rate afterwards. Scraped at each phase boundary, and every 5 s in between (`netem.ndjson`).
- `kcp_health` (`max_dropped: null`, `max_sessions_closed: 0`) and `client_sessions`: no KCP session closed or rejected, no rendered client saw a
  session change. Inbound datagram drops are reported, not judged (the impairment drops datagrams on purpose).
- `netem_snapshots`: per client and phase, the largest gap between two snapshots, the impaired p99 gap and the receive rate (clean limit 250 ms before and
  after, impaired limit 1000 ms and p99 400 ms; derivation: KCP is reliable and ordered, so loss costs time, not snapshots).
- `netem_prediction`: per client and phase, unexplained hard snaps of the local player (`pred.snaps`) per minute against the lab's `prediction_bound`
  (4.0), the largest per-sample correction (`pred.corr`) against 1.5, and, impaired only, keyframes (full snapshots) per minute against twice the
  baseline rate. **The lab player records no separate "hard resync" counter**: a hard snap and a resent keyframe are the observable resyncs; a
  session reset would show as a `client_sessions` failure.
- `netem_convergence`: `cross_client_convergence` over [removal + 10 s, end of scenario] (p95 0.35, max 1.0); the baseline and impaired phases are
  measured the same way and reported in the detail, not judged.

Limits: one profile at one severity, UDP port 9000 on IPv4 only; the netem queue is the default 1000 packets; loss is random and uncorrelated (a
burst-loss profile is a different test); the client's own kernel and the Windows to WSL localhost forwarding are not shaped; the server's
`gameserver_kcp_segments_retransmitted_total` counts only the server's resends (the clients' resends of inputs are not exported); it takes
about 2.7 minutes per run, and runs on the scratch stack only.

What each readiness area is covered by, and the gaps (with the client and server hooks they need): [`docs/COVERAGE.md`](docs/COVERAGE.md).

Every limit and grace window, with its derivation or marked "policy, unvalidated": [`docs/THRESHOLDS.md`](docs/THRESHOLDS.md) (generated: `testlab.py thresholds --write`).

## Adding a scenario

Copy a file in `scenarios/` and change these fields:
- `id`, `version` (bump when you change what it does), `title` and `description`.
- `clients`, `map`, `seed`, `server_env`, `duration_s` and `screenshots_s`.
- `client_defaults` / `per_client` steps and actions:
  - steps: `idle`, `move`, `circle`, `toward_point`, `toward_nearest_enemy`, `away_from_nearest_enemy`, `toward_client`;
  - actions: `cast_nearest_enemy`, `cast_forward`, `jump`.
- `disruptions` (`kill_client` with `relaunch_after_s`, `restart_gameserver`) and `bots` (S07).
- `assertions`: the check name plus its thresholds; see each `check_*` docstring in `lab/analyze.py`.

`tests/test_lab.py` loads every scenario, so a malformed one fails `tests/run-all.sh`.

## Artifacts (`<runs_root>/runs/<run_id>/`)

| File | Contents |
|---|---|
| `report.md`, `results.json` | outcome, per-assertion measurement, threshold, source, artifacts; build provenance |
| `failure-summary.json` | only when the run is not a clean PASS: earliest event, per failing check evidence pointers, suspected layer, confidence, guard events within 10 s, next action ([`docs/FAILURE-SUMMARY.md`](docs/FAILURE-SUMMARY.md)); derived, never changes the verdict |
| `run.json` | repos and commits, player fingerprint, stack actions, timeline, client launches, and the `provenance` record (below) |
| `scenario.json` | the scenario exactly as run (defaults applied) |
| `client-N/` | `plan.json`, `status.json`, `summary.json`, `events.ndjson` (incl. `render_jump`), `inputs.ndjson`, `snapshots.ndjson`, `samples.ndjson`, `frames.csv`, `player.log`, `shots/*.png`; with a C2 recorder also `delivery.csv` and `render.csv`; with `predictor_trace` also `trace.ndjson` |
| `rawprobe.ndjson` | S16/S17 only: what the raw-client step did and saw (cases with server reads, churn cycles, Redis key names before and after) |
| `server/` | `entities.ndjson` (authoritative positions), `status.ndjson`, `container.ndjson`, `metrics-{start,end,after}.txt`; with `snapshot_trace` also `snapshot-trace.csv` |
| `host/` | the host guard: `guard.ndjson` (one row per 5 s: AnyDesk processes with CPU and role, host CPU/DPC/interrupt, foreign load by group, the guard's own CPU), `anydesk-events.ndjson` (session events from AnyDesk's own log, including the `Session count` lines), `ad-trace-excerpt.txt` (at guard stop: the session-relevant `ad.trace` lines from one hour before the guard started, peer text redacted; `ad.trace` rolls over within days, this copy does not), `guard-summary.json` (the guard's cost), and with a clean-host scenario `preflight.json` |
| `redis.json`, `orchestrator.log`, `stack-up.log`, `harness-error.txt` | |

`python3 testlab/testlab.py analyze <run_dir>` re-grades stored evidence. Use it after a check changes, or to review a run without re-running it. It writes `results.json` and `report.md` into the run directory; `--out DIR` writes them elsewhere and leaves the run directory untouched (use it on runs other people rely on).

## Provenance (every run, every analysis)

When a run ends, `run.json` gets a `provenance` record (`lab/provenance.py`):
- factory, server and client commits (the client commit the player was BUILT from, `testlab-build.json`), and whether each tree was dirty;
- the image id the scratch game server container ran (`docker inspect rpgs-gameserver`) and its `org.opencontainers.image.revision` label. With `--build-server` the harness passes the server checkout's HEAD as `STACK_GIT_REVISION`, which stack.sh (rpg-mmo-server 1dc89ed and later) stamps into the image; the `provenance` assertion is then INCONCLUSIVE when the label is missing or differs from the recorded server SHA. A server whose stack.sh predates the variable is recorded as `label unsupported`;
- the Netcode the player embedded: version and source hash from `testlab-build.json`, commit from `VERIFY-PROVENANCE.txt`;
- the player exe sha256 and one sha256 over every managed assembly;
- scenario id, version and the sha256 of `scenario.json` as run;
- host load at start and end (`host_quiet`; the stalls themselves are graded by the `host_quiet` assertion);
- start and end instants, and a manifest of every evidence file (`client-N/`, `server/`, `bots/`, `scenario.json`, `redis.json`) with its sha256.

Every evaluation appends the `provenance` assertion. It is PASS only when every field is present, the run id is the directory's own, the scenario and every evidence file still hash as recorded, and every client summary names this run. Anything else is INCONCLUSIVE, so a run copied under another id, re-used evidence, or a run without a record (runs before this change) cannot grade PASS. `results.json` carries an `analysis` block (run id, run directory, time, factory commit, provenance status).

The manifest covers every evidence file: `scenario.json`, `redis.json`, `disruptions.ndjson` and everything under `client-*/`, `server/` and `bots/`. Each scenario has an expected inventory (`provenance.expected_inventory`: the server probe files, each client's recorder outputs, plus `disruptions.ndjson`, `bots/loadtest.json` or `server/snapshot-trace.csv` when the scenario produces them, and `client-N/trace.ndjson` for each client whose plan has `predictor_trace`). An inventory file missing from the manifest, an evidence file not in it, or a hash mismatch makes `provenance` INCONCLUSIVE.

## Native game server (`--server-mode native`)

The scratch game server normally runs in a container inside the WSL2 VM. That VM's monotonic clock steps in rate against the Windows clock the players render with (F23 finding B, F24B; the `3ng5` soak): the same host measured `current_tick` per harness second at 55.2 in docker mode and 60.1 in native mode. `--server-mode native` (a flag of `run`, `suite`, `sweep` and `stack`; config key `server_mode`) runs the game server as a Windows process of the host instead, so its `Stopwatch` is the same QueryPerformanceCounter the players use. Redis, Postgres, Nakama and the gateway stay in the scratch compose project: none is tick-time critical, and the gateway never dials the game server (it hands the players the address in the registry).

```
python3 testlab/testlab.py run S01 --server-mode native            # build, start, run, stop
python3 testlab/testlab.py run S09 --duration 600 --server-mode native --native-build auto
```

What the lab does, and nothing else (`lab/native.py`, `lab/stack.py::ensure_native`):

| Step | How |
|---|---|
| Build | `dotnet publish` of `backend/gameserver-dotnet/GameServer` from the configured `server_repo`, `win-x64`, Release, self-contained, into `<runs_root>/native/build/<sha12>-<kind>/` with `--artifacts-path` under `<runs_root>/native/` (the checkout gets no `bin/obj`; no build node outlives the build, because guard G4 counts `dotnet`). Every run rebuilds (incremental, 2 s when nothing changed), so the binary is always the checkout's. |
| Build kind | `aot` is what the image runs (NativeAOT). It needs the MSVC linker (Visual Studio "Desktop development with C++"); `--native-build auto` (default) uses it when `vswhere` finds it and otherwise builds `r2r`: self-contained ReadyToRun with the JIT (`PublishAot=false`, Server GC as in the csproj). On this host there is no linker, so native runs are **r2r**; the report and provenance say which. |
| Settings | The environment the compose `gameserver-dotnet` service would get: `docker compose config --format json` on the generated `.env.scratch` (scenario settings, lab secrets, every `GAMESERVER_*` default). Only container-network values are rewritten: listen and advertised address `127.0.0.1:<published game port>`, `METRICS_ADDR` `:<status port>`, `REDIS_ADDR`/`GAME_DB_URL`/`NAKAMA_URL` to the published host ports (7379, 6433, 8350), `CONTENT_DIR` to the checkout's `backend/content`. A TLS Nakama hop is refused. |
| Stack | The scratch compose project is started **without** `gameserver-dotnet` (`up -d` with the other services). A leftover `rpgs-gameserver` container is removed and its `servers:id:` / `servers:map:` entry deleted before the native server starts, so the gateway can only hand out the native one. Switching back to docker mode stops the native process first. |
| Registry and gateway | The server registers itself in the scratch Redis as in docker mode; `servers:id:gs-dotnet-<map>` `addr` is `127.0.0.1:9300`, which is what the players and the load generator dial (the players are on this host). No `host.docker.internal` is needed in this direction: the server dials out to published ports on localhost, the gateway only reads Redis. |
| Endpoints | `/status`, `/metrics`, `/debug/entities`, `/debug/kill` on the same status port. A Windows `HttpListener` without an URL ACL (admin) answers only the `localhost` prefix (400 to `Host: 127.0.0.1`, measured), so the lab addresses them as `localhost` in native mode (`LabConfig.status_host`). Every analyzer check reads the same files. |
| Samples | `server/container.ndjson` holds the process's CPU % (of one core, as `docker stats`) and working set. The snapshot trace is a file under `<runs_root>/native/`, copied to `server/snapshot-trace.csv`. The server's console output since the run's start is `server/gameserver.log`. |
| Provenance | `server.runtime = windows-native`, `server.image_id = native:<sha256 of GameServer.exe>`, `server.native` (build kind, SDK, runtime, source sha, exe and dll hashes). `image_revision` is the commit the binary was built from; the `provenance` assertion is INCONCLUSIVE if it differs from the recorded server sha. The report header and `results.json` (`server_runtime`) state the runtime. |
| Lifetime | The pid is recorded in `<runs_root>/native/server.json`; `stack down` (and the end of an invocation without `--keep-stack`) stops it, only while the pid still runs that executable. |

**Not supported in native mode:** S18 (`netem` shapes the container's network namespace; the runner refuses it with a message). Thresholds and checks are unchanged. P6 (WSL uptime) still applies because the rest of the stack runs in WSL.

**What a native run is not.** It is not the NativeAOT image: an `r2r` build starts precompiled but tiered JIT recompiles hot methods, so allocation and warm-up differ from the image. The Windows timer granularity differs from Linux's: the tick loop sleeps `WaitOne(delay - 1)` then spins, and a Windows process that has not asked for a 1 ms timer (`timeBeginPeriod(1)`) wakes on the 15.625 ms system quantum. Measured on this host (S09, `server/snapshot-trace.csv`, 8 483 snapshot intervals of 4 ticks, nominal 66.67 ms): 98.4 % of the intervals are 62.5 ms (4 quanta) or 78.1 ms (5 quanta), standard deviation 6.9 ms; the container server's is 0.4 ms. The average tick rate is still 60 Hz, so G6, `tick` and the player checks pass; with an experimental `timeBeginPeriod(1)` in the tick loop (not committed) the same build had a standard deviation of 0.8 ms and 99.1 % of the intervals at 66.7 ms (evidence in `P1B-NATIVE-SERVER.md`). Treat snapshot-gap numbers of a native run as including up to about 15 ms of server pacing jitter. Compare native runs with native runs and docker runs with docker runs; the report says which. A native run on a shared host competes with the other processes for cores, which the VM did not (shared-host numbers are labelled so).

### Host requirements (native mode)

- Windows 10/11 x64 with the .NET 10 SDK (`dotnet --version` 10.x, the version the server's csproj targets) on `PATH`; the first build needs NuGet access (runtime pack and crossgen2 for `r2r`).
- For `aot` only: Visual Studio Build Tools with "Desktop development with C++" (the MSVC linker), as for any NativeAOT publish on Windows.
- The same scratch prerequisites as docker mode (WSL Ubuntu with `dockerd`; the images tagged `:scratch` built once with `--build-server`: the gateway image and the Nakama plugin are still needed, the game server image is not used).
- TCP ports 7379 (Redis), 6433 (Postgres game DB) and 8350 (Nakama) published by the scratch stack and reachable on `127.0.0.1` from Windows (WSL2 localhost forwarding, TCP). UDP 9300 and TCP 9501 must be free on the host: the server binds `127.0.0.1:9300` (KCP) and the status port, so there is no firewall prompt and nothing is exposed.
- No admin rights and no change to the WSL clock configuration. Only the process the lab started is ever stopped.

## Clean-host soak (S09, host guard)

A freeze in a rendered player is evidence about the game only if nothing else on the host caused it. An AnyDesk session start does: in the F19 study, 2 of the 4 session starts that fell inside soaks with a process sampler froze the players for about 5 s (`20261023T040945Z-S09-e26z`, `20261023T071851Z-S09-i9fl`), and the other 2 did not. So the rule is about sessions, not about the program being installed. **AnyDesk stays running; the harness never stops, kills or starts anything on the host.** Every read is passive and read-only, with no elevation.

**The rule.** No `AnyDesk.exe --backend` process (that process is the session) and no AnyDesk session event from 2 min before the first scheduled client until the run ends. The three resident AnyDesk processes (`AnyDesk.exe`, `--local-service`, `--local-control`) are allowed. This replaces the older "no `AnyDesk.exe` process" wording, which cannot be met while remote access is kept.

**Preflight** (`python3 testlab/testlab.py preflight-soak [--window-min 90] [--window-announced "18:30Z 90min"] [--allow-agent PATH|WORKTREE-ID|UNIQUE-NAME] [--allow-dispatch CTX-ID] [--json]`): a 2 min passive sample plus the AnyDesk, Orca and WSL state, one PASS/FAIL row each, exit 0 only when all pass. P3 records each agent's repo, display name, normalized and original paths, worktree id, agent type, terminal evidence, and an 80-character prompt prefix. A working agent with a live terminal is ACTIVE and blocks; a working state with zero live terminals and terminal verdict `none` or `dead` is reported as STALE and does not block. Missing evidence and malformed fields fail closed as ACTIVE. P3 lists every Orca Run, then queries every page of each Run's supervised workers (including context-only Dispatches absent from worktree ps). Every worker page must report the exact requested Run with scope source `flag`; a missing/mismatched scope or any unavailable run/worker page fails P3. `measured.run_coverage` records the worker count and page scopes per Run. A worker is SETTLED only when its worker and dispatch states belong to the settled state sets documented in `THRESHOLDS.md` and liveness is known safe: non-abandoned workers require `exited` or `unverifiable`, while abandoned workers require `exited`. Missing, malformed, or unknown liveness is ACTIVE-UNVERIFIED. A `working` agent with a live terminal still blocks through worktree ps even if its supervised dispatch is settled. If the complete per-run worker inventory is unavailable, P3 FAILs even when worktree ps succeeds. `--allow-agent` matches a normalized absolute path (slashes unified and case-folded on Windows) or exact non-empty worktree id; a unique display name is also supported. Other path forms, including WSL `/home/...` paths against Windows paths, do not match and remain uncovered (fail closed). `--allow-dispatch` must match exactly one worker record with a non-empty exact dispatch id. Unmatched and ambiguous entries fail P3; every matched worker record is recorded in `host/preflight.json` and run.json metadata. Set `ORCA_CLI_COMMAND` when the Orca CLI is not on PATH.

| Row | Needs |
|---|---|
| P1 | no `--backend` process, no session event or connection entry in the last 2 min (residents allowed) |
| P2 | AnyDesk residents idle: mean CPU under 0.5 % and max under 1.0 % (the G3 cap) of the host |
| P3 | no ACTIVE agent: `working` agents with a live terminal block; zero live terminals with `none`/`dead` is STALE. Settled worker state pairs follow `THRESHOLDS.md`; settled workers with live liveness and abandoned workers with liveness other than exited block as ACTIVE-UNVERIFIED outside worktree ps. Other settled workers are summarized in detail and retained fully in measured evidence. Malformed worker fields and unavailable worker-list fail closed. `--allow-agent` matches path/worktree identity, and repeatable `--allow-dispatch` matches exact dispatch ids; unmatched entries fail. Allow-list matches are recorded in preflight and run.json. |
| P4 | no sustained build tools (mean 2 % or less) or Defender scan (`MsMpEng` under 5 %) |
| P5 | host CPU mean 50 % or less; above 30 % it is flagged shared-host |
| P6 | the WSL distro is running with uptime of 10 min or more (the probe never starts it) |
| P7 | the user has named the window (`--window-announced`); a runbook step, not measured |

A scenario with `requires_clean_host` (S09) first refuses to start unless the player and the server checkout are named (M4/H6): `--player` and `--server-repo` (or the same keys in the config file) are required, the defaults are never used for a soak, and `--expect-player-sha` / `--expect-server-sha` (7 or more hex digits) refuse a build from another commit (the player's commit is `client_head` in `testlab-build.json`). The refusal exits with code 3 before a run directory, the stack or the WSL keep-alive exists; the accepted inputs are recorded in `run.json` under `soak_inputs`. It then runs P1-P6 automatically before anything starts and refuses to start on a FAIL (`harness_error`: `host preflight failed: P3`). `--require-clean-host` does the same for any scenario. The result is `host/preflight.json`.

**In-run guard.** `lab/hostguard.ps1` (a PowerShell child, started before the clients, stopped after them) samples every 5 s; `lab/hostguard.py` tails AnyDesk's `ad.trace` (and `connection_trace.txt`) for session events. The guard writes its own CPU cost to `host/guard-summary.json`. Guards are evaluated inside the window from `start_scheduled` minus 30 s to the scenario end plus `finish_grace_s`:

| Guard | Fires on |
|---|---|
| G1 | an AnyDesk session event or `--backend` process in the window, or a session still active at its start |
| G2 | an AnyDesk process that was not in the preflight / pre-window set (also catches a log that cannot be read) |
| G3 | AnyDesk CPU of min(1.0 %, max(0.5 %, resident max x 2 + 0.3 %)) of the host or more for 2 consecutive samples; the resident max is the preflight's 2-minute P2 maximum (`host/preflight.json` `anydesk_baseline`), 0.5 % without one. Policy, unvalidated (F19 0.03 % idle, F28 0.18 % mean / 1.98 % max idle front process) |
| G4 | build tools or `MsMpEng` above 5 % of the host for 3 consecutive samples |
| G5 | the guard was blind: more than 3 consecutive intervals without a sample |
| G6 | `current_tick` per harness second steps more than 5 % from its run median for more than 2 s while `achieved_tick_hz` remains within its normal 98 % bound |

A fired guard makes the `host_guard` assertion, and so the run, **INVALID**. INVALID is checked before FAIL and is never PASS: it cannot turn a FAIL or INCONCLUSIVE into a PASS, it is not a verdict on the candidate, and a FAIL in the table is kept as evidence (and named under **Qualified by**). It exits with code 2. No threshold or pass rule of any scenario changed. `host_quiet` additionally names the nearest guard event within 10 s of every single-process frame of 1 s or more, and carries two INFO tiers (M4/H3, never graded, never PRODUCT): host-wide stalls of 30 ms or more ending within 50 ms of each other in at least two client processes (`info_stalls_30ms`), and single-process freezes of 1 s or more outside a graded stall (`single_process_freezes`); the graded 250 ms rule is unchanged. `host_guard` lists the viewer (outgoing, `front` process) AnyDesk sessions with start, end and duration under `anydesk_outgoing_sessions` (M4/H1): the end is the first later `Session count: (total, incoming)` line with fewer outgoing sessions (total - incoming); a session without such a line is reported open, with its duration unknown. `render_jumps` reports `hop_sizes_by_boundary` (M4/H5): size min/p50/p95/max of the counted jumps per scripted step boundary, reported only. Other agents' shell and WSL bursts are recorded (`newproc`) but do not invalidate. Every limit above is **policy, unvalidated** (`docs/THRESHOLDS.md`), calibrated on one 16 min baseline.

G6 compares the server tick counter with the harness monotonic clock using 1 Hz `/status` samples. The rate is the net `current_tick` delta over the monotonic delta of a sliding window of at least 2 s (the fewest whole 1 s intervals spanning 2 s), so one late poll moves it by at most its lateness divided by 2 s and alternating jitter cancels. G6 fires on 3 consecutive windows of the same sign more than 5 % from the run median (a union span of at least 4 s) whose own net rate also exceeds 5 %. The "2 s" is therefore the window length, not a duration the step has to exceed.

A server stall or slowdown remains graded by the existing tick, snapshot and render checks as FAIL. Because `achieved_tick_hz` is the rate of the last completed 2 s window and lags a stall, G6 drops every interval with `achieved_tick_hz` below 98 % of the critical rate, with no tick progress, or more than 35 % off the median (a host clock step is about 20 %), and also every interval within 3 s (the 2 s meter window plus one sample) before or after one.

The provisional limits are tied to F23's `9mre` evidence. The detector reports five episodes there, not two: 564 s and 2990 s (about 65 instead of 55 ticks per harness second while the server reported ~60 achieved ticks/s) are F23 Finding B, the only ones attributed to a host clock correction; one at 2 s is start-up (58.8 ticks/s, 6.6 %); 2288 s (50 s) and 2431 s (42 s) run at 60 ticks/s with no 55 skew and are unexplained. The reference is the run median, so a run that spends more than half of its time in the other regime would flag the normal one; this is a policy limitation, not validated.

S09-class runs (`requires_clean_host`) also run `hostprocs.ps1`, a 1 s sampler of the top 10 processes by CPU (`host/procs.ndjson`, cost in `host/procs-summary.json`: about 0.2 % of the host, one 50 ms sweep a second on one core). It is evidence only: the `host_guard` detail carries a `proc_sampler` summary (INFO) and no guard reads it. It exists to match a 40-140 ms client stall to a process, which the 5 s guard cannot do.

The guard cannot see which part of a session start freezes a player, and an idle resident AnyDesk cannot be cleared by it; both stay open (F19 section 3.5). A run with no guard evidence (older runs) shows `host_guard` INFO; a clean-host scenario without it is INCONCLUSIVE.

## Snapshot delivery path (`analyze --delivery`, rpg-mmo-server#473)

```
python3 testlab/testlab.py run S09 --duration 3600 --snapshot-trace    # or "snapshot_trace": true in a scenario
python3 testlab/testlab.py analyze --delivery <run_dir> [--out DIR] [--gap-ms 250] [--bucket-s 300]
```

With `snapshot_trace` the stack sets `GAMESERVER_SNAPSHOT_TRACE=/tmp/testlab-snapshot-trace.csv` in the scratch game server, restarts it so the trace starts with the run, and copies the file to `server/snapshot-trace.csv` at the end. The compose file must forward `GAMESERVER_SNAPSHOT_TRACE`; the run refuses to start otherwise.

The analysis (`lab/delivery.py`) joins the server trace (contract C1) and the client trace (contract C2: `delivery.csv`, `render.csv`) on (user id, world tick). Per client and per 5-minute bucket it reports server send inter-gap, client receive inter-gap, windowed relative excess delay, fit error bound, queue depth and queue delay, dropped, KCP retransmissions, `kcp_wait_snd`, and render snapshot age. Absolute one-way delay is always unavailable because the minimum envelope includes unknown path delay. Every client receive gap over 250 ms is classified RECONNECT, SERVER_LATE, QUEUE, CLIENT, KCP, PATH or UNKNOWN, and ALL-CLIENTS or SINGLE-CLIENT; the rules are in the module docstring. A gap that spans a session change is RECONNECT, never SERVER_LATE: the server wrote its two ends to different connections (C1 `conn_id`), or the client ended a session and reconnected between them (`events.ndjson` `net_state` Ended / `entities_reset` and `reconnected`, the cause from `player.log` "game session closed: <cause>"); each client's `sessions` are listed. Per-connection counters (retransmissions, dropped) are summed per connection, because a new connection restarts them at 0. Missing inputs make the classes that need them UNKNOWN and the output INCOMPLETE (exit 2); a poor fit makes relative excess and PATH attribution unavailable. It is diagnostic: it never grades a run PASS. Without C2 the receive time falls back to the main-thread `t` of `snapshots.ndjson`, so a main-thread stall shows up as CLIENT.

**Scope and KCP window.** A gap is ALL-CLIENTS when every other client had a long gap over overlapping or touching tick ranges (one host freeze can leave one client's gap at ticks 182061-182065 and another's at 182065-182069). Independent window fits do not provide a shared absolute clock axis for cross-client receive-window mapping. The KCP class reads the server rows up to tick b and the 4 rows after it, where a retransmission burst lands.

**Clock rate.** The server runs in the WSL VM, whose monotonic clock was measured 7.3 % slow against Windows (`.testlab-runs/t06/clock-drift-check.txt`). The analyzer fits each 10 second window separately from one minimum-delay sample per 1 second bin. It reports excess above that fitted minimum envelope, plus the p95 absolute residual of the minima as an empirical fit error bound. A window needs at least five minima, a rate from 0.8 to 1.2, and error at most 10 ms; otherwise it produces no relative-delay numbers, and PATH gaps that need it are UNKNOWN. Accepted local rates convert server durations to client time. This follows the X13 10 second fit shape (2.16-3.85 ms residual p95 and 4.07-7.66 ms relative excess p95 in `20261023T071851Z-S09-i9fl` and `20261023T040945Z-S09-e26z`). The bound describes fit residual only; it cannot bound absolute one-way delay.

## Predictor call trace (`replay-trace`, Netcode >= 8986908)

```
python3 testlab/testlab.py run S13                                   # client 0 records client-0/trace.ndjson
python3 testlab/testlab.py replay-trace <run_dir> [--client N] [--out DIR] [--min-correction 0.05] [--window-s 5]
```

**Turning it on.** `"predictor_trace": true` in a scenario's `client_defaults` or in one `per_client` entry puts
`predictor_trace` into that client's plan (client `TestLabPlan.predictor_trace`, client docs/TESTLAB.md "Predictor
call trace"). The player then writes Netcode's call trace of `LocalMovePredictor` and `PredictionClockSteering`
to `trace.ndjson`: a header (the predictor's `PredictionSettings`, map id, motor), a session line per join, a
frame marker per frame (realtime `t`, `udt`, `dt`) and one line per call in Netcode's
`PredictorTraceEvent.AppendJson` form. S13 turns it on for client 0, the stalled client, only. A client with the
flag must leave `trace.ndjson` (expected inventory); with the flag off the player writes none. A player built
before the client hook ignores the flag, so its S13 run is INCONCLUSIVE on provenance.

**`replay-trace`** (`lab/predtrace.py`) does not replay. It checks that the trace can be replayed and lists
what the live predictor recorded, so the Netcode owner knows what a replay must reproduce:
- **Invalid** (exit 1): no header or `settings_read` false, a second header, an unknown call code, a `Reconcile`
  not followed by its `ReconcileResult`, a result without a reconcile, steering `OnSnapshot` begin/end not
  nested, frame numbers not increasing or frame times going back, steering times going back, a damaged line
  before the last, no frame markers or no calls.
- **Warnings** (still valid): a cut-short last line, a sink attached after snapshots (`events.ndjson`
  `trace_attached` with `snapshots_before` > 0), input ticks going back without a `Reset`, counts that differ from
  `summary.json` `trace`.
- **Corrections per stall:** every `ReconcileResult` with `LastCorrection` >= `--min-correction` or a new snap,
  placed in its frame (scenario time from the frame marker), attributed to a scripted stall when it falls within
  `--window-s` of the stall start (until the next stall), the rest listed as outside stalls.
- Exit 0 every trace valid, 1 one invalid, 2 no trace in the run, 3 usage. It prints a text summary;
  `--out DIR` also writes `trace-summary.json` there. It never writes into the run directory.

**The exact replay is Netcode's** (it owns `PredictorTraceReplayer` and its headless project; a file-driven
entry point is a Netcode follow-up). The recipe, from client docs/TESTLAB.md and Netcode
`Documentation~/PREDICTION.md` "Replaying a live session":
1. From the header: `new LocalMovePredictor(new PredictionSettings(tick_rate, speed, new MapBounds(minX, minY,
   maxX, maxY)))` (`bounds` is `[minX, minY, maxX, maxY]`).
2. The map geometry for `header.map`: the same JSON the client loads from `Resources/Maps/<map>.json` and the
   server from `backend/content/maps/<map>.json`, parsed as the client does (`MapGeometryJson.TryParse`,
   Unity-free) or as the server does. Set it as `PredictorTraceReplayer.Geometry`; the trace's
   `SetMapGeometry` call applies it.
3. `PredictorTraceEvent.TryParseJson` every line and `Apply` it in order (lines without `"c"` are skipped by the
   parser). `ReplaySteering = true` re-decides the steering instead of replaying its effects.
4. Compare each replayed reconcile's outcome with the recorded `ReconcileResult` (`x` LastCorrection, `y`/`z`
   the simulated position, `w` snaps, `a` base tick, `b` tick error, `c2` stall resyncs): equal before a fix,
   and after a fix the corrections `replay-trace` lists for the stall are the ones that must change.

## Failure triage

| Symptom | Look at | Typical cause |
|---|---|---|
| HARNESS ERROR `timeout ... all clients in world`, client log `connection was aborted` | `client-N/player.log`, gateway logs | gateway per-IP limit (`connection rate limited`); the scratch stack sets `GATEWAY_CONN_RATE_PER_MIN=0`, which needs the compose passthrough |
| `port conflict` in preflight | `stack.py preflight` | something other than `rpgs-*` holds 9000/9501/8350 |
| `render_jumps` local_major | `largest` in the detail, `client-N/samples.ndjson` (`pred` vs received), `shots/anomaly*.png` | prediction disagreeing with the server (e.g. the predictor-bounds bug, S10) |
| `render_jumps` server_teleport | nothing; informational | a respawn or teleport the server made |
| `spawn_overlap` FAIL | `detail.overlapping` (player, time, position, nearest other player) | a fresh or respawned player placed on another (rpg-mmo-server#469); `GAMESERVER_SPAWN_SCATTER=0` reproduces it |
| `enemy_crowding` overlap FAIL | `timeline` (`nn_p10`, `overlap_ratio`) | enemy separation off or not converging (`GAMESERVER_ENEMY_SEPARATION`, #469). Concentration on one player is INFO: it follows the nearest-player rule, which `enemy_pursuit` checks |
| `enemy_pursuit` FAIL | `detail.away` (enemy, target, heading) | an isolated enemy (no other within `crowd_radius`) far from every player not heading for the nearest one - crowd members moved by separation are reported as `crowd_steps`, not judged; `settled_rel_speed_p95` above its bound is a crowd that still jitters at its target |
| `position_divergence` with layer "interpolation" | the worst rows, `samples.ndjson` | the client received the right position and drew it elsewhere |
| `position_divergence` with layer "snapshot or transport" | `snapshots.ndjson` gaps, `/status` replication gap | the client never received the server's path |
| `kcp_health` dropped `no_session` | `metrics-after.txt` vs `metrics-end.txt` | a client quit inside the window |
| INCONCLUSIVE everywhere | `harness-error.txt`, `server/` empty | stack not ready, debug endpoint off, player without `NDC.TestLab.dll` |
| `provenance` INCONCLUSIVE | `detail.problems` | run predates provenance, evidence changed or copied after the run, build without `VERIFY-PROVENANCE.txt` for an embedded Netcode |
| `snapshot_cadence` FAIL, gaps grow over a soak | `analyze --delivery` classes and buckets | CLIENT: main-thread stalls (e.g. the overlay cost bug, run `20261022T112220Z-S09-eeoa`); the server classes need `--snapshot-trace` |

## Limits (stated, not hidden)

- **Raw clients are not clients.** S16 and S17 use a Python wire client (`lab/rawclient.py`) with JSON envelopes and a minimal KCP; they prove what the server does with a session, not what a client does with the server's answer.
- **No network impairment.** Every run uses the host's loopback path. Latency, loss and reordering (`tc netem` on the scratch UDP port, COVERAGE F7) would change shared WSL networking and need the user's approval, so reconciliation and delivery are not tested under them.
- **Capacity numbers are host-bound.** Players, bots and the server share one machine (ADR-7). S07 reports the first failing level on this host, not a server ceiling.
- **Frame times** come from three rendered players on one GPU. Use them for regressions, not as a device budget.
- **GC allocation per frame** needs a development build. Release testlab players report `gc.valid: false`.
- **Obstacles** exist only on maps with a geometry file. Today that is `dev_arena`; `map_01` is flat.
- **Image analysis** is not used to judge motion. Screenshots are supporting evidence; motion claims come from the per-frame and 20 Hz traces.
- **The scenario clock** is shared through the host wall clock once per run. Clients on different hosts would need clock offset measurement, which the lab does not do.
