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

Exit codes: `0` PASS, `1` FAIL, `2` INCONCLUSIVE, `3` harness or usage error.

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

`build-client` runs three Unity batch steps in the configured project:
1. `TestLabSceneBuilder.Build` regenerates the test scene from `MainScene`.
2. `TestLabSceneBuilder.Validate` fails on missing scripts, a missing `MainSceneScope` or `DotsWorldBridge`, or a missing arena.
3. `PlayerBuilder.Build` builds the player with `-bootScene Assets/Scenes/Tests/MultiplayerCombatTest.unity -extraDefines CUVARA_TESTLAB`.

It writes `testlab-build.json` next to the player: the client commit, uncommitted changes, defines, and every package embedded under `Packages/`. Every report shows this provenance.

## Design (architecture decision record)

**Decision 1 - drive the production input path, not the transform.** `DotsWorldBridge` and `GameplayPanelDriver` read every control through `GameplayInput.Source` (`IGameplayInputSource`). In a normal build this is `DeviceGameplayInputSource`, with the same device reads as before. The testlab installs `ScriptedInputSource`. Everything downstream stays on the production path: the send schedule, `SendInput`, `LocalMovePredictor.RecordInput`, clock steering and projectile prediction. Rejected alternatives:
- OS key injection. The Input System drops input to an unfocused window, and the lab must not need focus.
- A second `SendInput` caller. It would make the recorded and sent input streams diverge.
- Transform writes. These would bypass exactly what is under test.

**Decision 2 - the runtime ships only in testlab builds.** `NDC.TestLab` has `defineConstraints: ["CUVARA_TESTLAB || UNITY_INCLUDE_TESTS"]`. It compiles in the Editor, so EditMode tests cover it, and in players built with `-extraDefines CUVARA_TESTLAB`. It is absent from a normal player (verified by building both; see the client CHANGELOG). Even inside a testlab build it does nothing unless the player is started with `-testlab-plan`.

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
| S09 | Soak: memory slope, entity drift, accumulated errors (default 300 s) |
| S10 | Regression replay of the 2026-10-21 report, with before/after reference numbers |

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
| `run.json` | repos and commits, player fingerprint, stack actions, timeline, client launches |
| `scenario.json` | the scenario exactly as run (defaults applied) |
| `client-N/` | `plan.json`, `status.json`, `summary.json`, `events.ndjson` (incl. `render_jump`), `inputs.ndjson`, `snapshots.ndjson`, `samples.ndjson`, `frames.csv`, `player.log`, `shots/*.png` |
| `server/` | `entities.ndjson` (authoritative positions), `status.ndjson`, `container.ndjson`, `metrics-{start,end,after}.txt` |
| `redis.json`, `orchestrator.log`, `stack-up.log`, `harness-error.txt` | |

`python3 testlab/testlab.py analyze <run_dir>` re-grades stored evidence. Use it after a check changes, or to review a run without re-running it.

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

## Limits (stated, not hidden)

- **Capacity numbers are host-bound.** Players, bots and the server share one machine (ADR-7). S07 reports the first failing level on this host, not a server ceiling.
- **Frame times** come from three rendered players on one GPU. Use them for regressions, not as a device budget.
- **GC allocation per frame** needs a development build. Release testlab players report `gc.valid: false`.
- **Obstacles** exist only on maps with a geometry file. Today that is `dev_arena`; `map_01` is flat.
- **Image analysis** is not used to judge motion. Screenshots are supporting evidence; motion claims come from the per-frame and 20 Hz traces.
- **The scenario clock** is shared through the host wall clock once per run. Clients on different hosts would need clock offset measurement, which the lab does not do.
