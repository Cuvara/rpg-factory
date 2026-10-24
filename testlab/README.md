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

Exit codes: `0` PASS, `1` FAIL, `2` INCONCLUSIVE, `3` harness or usage error, `4` PASS_WITH_WARNINGS.

**PASS_WITH_WARNINGS** is the outcome when every assertion passed but an `informational` one would have failed (today the S07/S07P memory slope, informational because the bot ramp allocates by design). It is never a clean PASS. The report lists it, and host load, under **Qualified by** next to the verdict: host-wide stalls seen in the run, or CPU load of 50 % or more at start or end. Host qualifications do not change the outcome (the timing checks a stall explains are already INCONCLUSIVE); they say the timing came from a busy host.

`run`, `suite` and `sweep` stop the scratch stack when they finish: on success, failure, harness error and Ctrl-C. Pass `--keep-stack` to leave it running for the next invocation. Players are stopped at the end of every run in all of these cases.

### Where each command works

| Command | Windows Git Bash (or PowerShell, cmd) with Windows Python | WSL Ubuntu with Linux Python |
|---|---|---|
| `run`, `suite`, `sweep`, `stack`, `clean`, `build-client`, `build-loadtest` | yes | no: the players are Windows processes and process control uses `tasklist`/`taskkill` |
| `analyze`, `analyze --delivery`, `replay-trace`, `leak-check`, `list` | yes | yes (give `/mnt/c/...` paths) |
| `python3 -B testlab/tests/test_lab.py`, `python3 -B testlab/tests/test_netem.py` | yes | yes |

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

## Prerequisites

- Windows host (the players are Windows processes) and Python 3.10 or newer. The orchestrator uses only the standard library.
- WSL Ubuntu with a native `dockerd`. The lab never starts Docker Desktop.
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
| S08G | Graceful disconnect: client 2 leaves at 15 s with plan action `quit` (`NetworkClient.Disconnect()`); `graceful_leave`, outcome `left`, 2 players online at the end |
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
- `cross_client_convergence` (hook C4): for every pair of clients, A's rendered position of a remote entity at render tick T against B's, interpolated between B's two samples around T. p95 <= 0.35, max <= 1.0: the thresholds of the remote `position_divergence` assertions. Pairs across a server teleport are skipped.
- `stall_recovery` (hook C2): after each `stall` event, the stalled client's local player is back on the server path: local divergence p95 <= 0.5 (the S03/S10/S12 local bound) over [end + 1 s, end + 4 s]. The 1 s recovery allowance is a test parameter. Hard snaps during each stall are reported.
- `graceful_leave` (hook C6): a client that ran `quit` ends with outcome `left` and a `disconnected` event, and its player is gone from `/debug/entities` (and from the other clients, with C3) within 5 s. That is a test bound far under the 60 s KCP idle timeout (`KcpTuning.IdleTimeoutMs`) that cleans up a silent client.
- Plan actions `stall` (`ms`), `quit`, `reconnect`, `cast_at_point` (`x`, `y`) and `cast_spam` (`interval_ms`) are accepted and expanded (client `docs/TESTLAB.md` "Coverage hooks"); one-shot actions need only `t0`. `clients_completed` takes `expected_outcomes` (e.g. `{"2": "left"}`).
- `repeat_cycle_s` (scenario): each client's steps and actions repeat every N seconds until `duration_s`; the first cycle is unchanged.
- Preflight: without `--build-server`, a server worktree with no `backend/deploy/modules/nakama.so` (the Nakama plugin `stack.sh up` builds) fails fast instead of timing out every join.
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
  ignored the input. The undefined-type case (`unknown_type`, type 99) is that case today: the server has no counter or log line for
  it (`GameServer.cs` `OnMessageReceived` default arm logs at Debug, `Program.cs` sets the console minimum level to Information), so S16
  grades INCONCLUSIVE until the server counts it.
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
| `run.json` | repos and commits, player fingerprint, stack actions, timeline, client launches, and the `provenance` record (below) |
| `scenario.json` | the scenario exactly as run (defaults applied) |
| `client-N/` | `plan.json`, `status.json`, `summary.json`, `events.ndjson` (incl. `render_jump`), `inputs.ndjson`, `snapshots.ndjson`, `samples.ndjson`, `frames.csv`, `player.log`, `shots/*.png`; with a C2 recorder also `delivery.csv` and `render.csv`; with `predictor_trace` also `trace.ndjson` |
| `rawprobe.ndjson` | S16/S17 only: what the raw-client step did and saw (cases with server reads, churn cycles, Redis key names before and after) |
| `server/` | `entities.ndjson` (authoritative positions), `status.ndjson`, `container.ndjson`, `metrics-{start,end,after}.txt`; with `snapshot_trace` also `snapshot-trace.csv` |
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
