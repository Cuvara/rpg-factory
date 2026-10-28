# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- testlab `failure-summary.json`: every run that is not a clean PASS writes a machine-readable triage next to
  `report.md` at the end of `analyze` (`lab/failsum.py`): verdict, earliest event (scenario time and wall-clock UTC),
  per failing/invalid check the earliest event, evidence files with line pointers, suspected layer
  (environment / harness / server / netcode / client / unknown) by documented rules, confidence, host guard events within
  +-10 s, and a next action. Derived output only: it never changes the verdict or a check result, and a build error is
  recorded in the file. `check_render_jumps` leaves its counted jumps in `ev["_failsum"]` for it (not part of the result).
  Rules and tables: `testlab/docs/FAILURE-SUMMARY.md`; tests on scrubbed excerpts of runs k4n5, ibz3, 9tgw, 3ng5:
  `testlab/tests/test_failsum.py`.
- testlab host guard: optional 1 s per-process CPU sampler (`hostprocs.ps1`, top 10) for S09-class runs, written to
  `host/procs.ndjson` with its own measured cost in `host/procs-summary.json` (about 0.2 % of the host). Evidence only:
  the `host_guard` detail gains a `proc_sampler` summary (INFO); it is not a guard. A scenario can turn it off with
  `proc_sampler: false`. Added so the 40-140 ms client stalls of run ibz3 (F28) can be attributed to a process.

### Changed

- testlab `host_guard` G3 is relative to the preflight-measured resident AnyDesk baseline: it fires above
  min(1.0 %, max(0.5 %, baseline max x 2 + 0.3 %)) for 2 consecutive samples (policy, unvalidated). The 1.0 % cap keeps a
  session-like burst (>= 1.36 % seen in F28) firing however noisy the preflight was; a preflight resident max at or above
  the cap fails P2 and the run does not start (RV-F29 B2). After the reboot the idle resident
  `front` process runs 0.18 % mean / 0.33 % max (0.03 % in F19), which the fixed 0.5 % limit flagged. The baseline is recorded
  in `host/preflight.json` (`anydesk_baseline`) and in the guard stats. G1 and G2 are unchanged and still detect sessions;
  ibz3 stays INVALID on G1 (three real outgoing sessions).

- skills: refresh TickLoop citations after the server TickSleeper pacing change, and describe
  the Windows high-resolution timer path accurately.

### Fixed

- testlab `render_jumps`: a LOCAL snap at a server-confirmed respawn of the same player is explained by the respawn and
  counted as `local_respawn`, bound tightly (RV-F29 B1): the snapshot carrying the new position has a world tick inside
  [HP 0 probe tick, max-HP probe tick + 2], the received step is >= half the rendered step and points where the rendered
  snap went (cos >= 0.7), and one respawn explains one snap. Run ibz3 st 911.107 (rendered 1.088, received 0.8407, 3.4 %
  short of the old 0.8 x rule) failed a real respawn. A later unrelated snap, a second snap, another player's respawn
  and a local major without that evidence still FAIL.
- testlab `entity_lifecycle`: the id-reuse tolerance is per entity type. A projectile uses its content (or measured)
  speed x 0.15 s + 0.2 instead of the player `max_speed`, so a first draw one snapshot ahead after a client stall no longer
  fails (ibz3 proj-17, 1.33 u from spawn vs 1.1). The stale-buffer detection is kept: a first draw at or near the previous
  incarnation's last position still FAILs.
- testlab: S01 no longer FAILs `kcp` (3 `dead_link` closes) and `redis` (6-9 session keys for 3 users) because the WSL
  distro stopped under the run (runs 6qgq, ii3h, jmag, hj3f, imed; native and docker alike). WSL terminates a distro with no
  open `wsl.exe` session; dockerd and the scratch stack died with it mid-run (gateway "shutting down gateway", Redis
  reloading its AOF) and every harness call into WSL stalled for the reboot. The run loop then overran the scenario end:
  `metrics-end` was scraped after the clients quit (their teardown `dead_link` closes counted inside the window), and
  the sessions of the killed gateway stayed in Redis for SessionTTL (1 h). No product bug: the server, Netcode and client
  behaved the same in the passing runs. `run`/`suite`/`sweep` now hold one `wsl.exe` keep-alive session from the first
  stack action to after the teardown (`stack.WslKeepAlive`, recorded in run.json as `wsl_keepalive`); a fresh world starts
  with no `session:*` keys in the scratch Redis (`stack.clear_session_keys`, count in `stale_session_keys_cleared`); and
  a `kcp` or `redis` check whose evidence was taken after the window (timeline `metrics_end_late` / `redis_late`) is
  INCONCLUSIVE, not a FAIL or a false PASS. No threshold or assertion was changed.
- testlab host guard: G1 no longer reports false historical sessions ("active at window start") after the AnyDesk
  log rotates. The tailer re-read the file from 0 and re-emitted its Accepts; each duplicate queued a phantom
  session that a later close ended, shifting every pairing (run 9tgw: sessions 'ended' 13:16:14Z hours late). Events
  are now de-duplicated in the tailer and in `sessions_from_events`, and every open-ended session counts as active at
  the start only with a live backend process sample at or after the window start (matching PID when known). A real
  session in the window still fires G1, G2 and G3.
- testlab: a native game server that cannot be stopped at teardown no longer leaves a green exit and a running
  stack: `stack.down` still brings the scratch backing stack down, then raises, and `_with_stack_teardown` turns an
  exit of 0 or 4 into 3 (a run's own 1 or 2 is kept) and keeps the error in `<runs>/stack/teardown-failure.json`.
- testlab: native `--build-server` builds the Nakama plugin for the version of the resolved scratch compose Nakama
  image (what `.env.scratch` decides) and not for the scenario env or a fixed 3.40.0, so the plugin ABI matches the
  running Nakama; an unreadable image fails the build instead of guessing.
- testlab: native mode with `--build-server` no longer runs `stack.sh --scratch up` (its `up` ends in `dc up -d`
  for the whole project and started the container `gameserver-dotnet` before the native server replaced it).
  The Nakama plugin and the gateway image are built directly (the two builds of `stack.sh do_up`; the game server
  image is not built), then only the backing services are started. Regression tests prove no native path, with
  `build` true or false, runs the full-stack `up`. A native server that is still alive after `kill_tree` and the
  15 s wait now keeps its state and fails the stop with an error (the next run is refused until the process is
  gone) instead of dropping its pid record.

### Added

- testlab: `--server-mode native` runs the game server as a Windows process built with the Windows dotnet, so its
  `Stopwatch` is the QueryPerformanceCounter the players use and not the WSL VM's clock (F23 finding B, F24B, soak
  `3ng5`). The server is built from the configured checkout (`aot` when the MSVC linker exists, else self-contained
  ReadyToRun `r2r`; recorded as `server.native` with SDK, source sha and exe/dll hashes), takes the environment of the
  scratch compose service (`docker compose config`, with only the container-network addresses rewritten to the
  published localhost ports) and registers `127.0.0.1:<game port>` in the scratch Redis. The scratch stack runs
  without its `gameserver-dotnet` service (a leftover container and its registry entry are removed), the status
  endpoints are addressed as `localhost` (a Windows `HttpListener` answers 400 to `Host: 127.0.0.1`), CPU/memory come
  from a process sampler and the server console is kept as `server/gameserver.log`. Provenance gains
  `server.runtime` (`docker` or `windows-native`) and `image_id = native:<exe sha256>`; the report and
  `results.json` state the runtime. S18 (netem) is refused in native mode. Docker mode is unchanged.
- testlab: host guard G6 detects sustained server clock-rate steps against the harness monotonic clock and marks
  the run INVALID while preserving any FAIL evidence. The policy thresholds are documented as unvalidated and
  cite the F23 9mre soak evidence. The rate is measured over sliding windows of at least 2 s and needs three
  consecutive same-sign windows, so polling jitter and a single late poll do not fire it. Stalls are excluded with
  a 3 s margin (the achieved-rate meter lags by its 2 s window) and a 35 % plausibility cap. The five 9mre
  episodes are documented: two attributed, one start-up, two unexplained.

### Fixed

- testlab: the host guard kept sampling only until the players exited, not until the measurement window end
  (scenario end + `finish_grace_s`), so every full-length soak ended with a 20 s blind gap and G5 INVALID. The runner
  now holds the guard until a sample at or after the window end exists (`HostGuard.hold_until`); a sampler that does
  not deliver is still reported by G5, and the window is unchanged.

## [1.1.0] - 2026-10-24

Feature release. Adds `testlab/`, autonomous multiplayer gameplay tests with real rendered Unity clients (scenarios
S01-S18 on an isolated scratch stack, delivery analysis, malformed input, churn and packet impairment), and one
parallel-work policy (`skills/factory-core/references/parallel-work.md`: the main session is Lead/Integrator, one
worktree per task, QA and review on stable candidate commits, Orca as the preferred coordinator). The check runner
now fails closed: pollution is attributed per check, a timeout kills the check's whole process tree and FAILs when
that cannot be confirmed, wire-parity and Netcode headless test the candidate checkout and print its SHA, TRX results
need a Completed/Passed outcome with executed tests and no failures, and checks receive the workspace and checkout
as Git Bash or WSL paths. The snapshot routes only the files a task writes (`--paths`); uncommitted changes are
shown as the user's baseline. Also: truthful evidence scope, skill `allowed-tools` lint, guards for linked worktrees
outside the workspace, a Windows lock retry budget for state files and refreshed skill citations. Update the plugin
(`claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory`) and start a new
session. Evidence recorded by 1.0.5 re-grades once as STALE (`check scope changed`).

### Changed

- `testlab` AnyDesk trace tailing now detects replacement by file identity and a prefix fingerprint, rereads rotations from byte zero even when the replacement is equal to or larger than the previous offset, and records unavailable log identity as G5 blind evidence.
- Refreshed Netcode client guidance for v0.49.0: KcpCrypto reuses per-session crypto state, subscribers are isolated, and snapshot speed distinguishes absent (`NaN`) from present zero; documented the server unknown-type counter, kick-reason drain, and readiness/release runbooks.
- Clarified that `factory-status` derives client and package-CI pin versions from repository state instead of storing moving pin versions in registry prose.
- Updated drifted client, server, and Netcode skill citations to match their integration branches, including client `origin/develop` at `45634b1`.
- `testlab analyze --delivery` now fits server/client clock mapping independently in 10 second windows using one minimum-delay sample per 1 second bin. It reports relative excess above each window's minimum envelope and the empirical p95 fit error bound; absolute one-way delay remains explicitly unavailable, and poor fits yield no delay values or PATH attribution.

### Added

- **testlab host guard** marks contaminated soaks INVALID (`feat(testlab)`): `lab/hostguard.py` + `hostguard.ps1` sample the host every 5 s
  (AnyDesk processes with role, host CPU/DPC/interrupt, build-tool and Defender load, the guard's own CPU) and tail AnyDesk's log for
  session events, all passive and read-only; AnyDesk is never stopped. Guards G1-G5 (session start or active session, new AnyDesk process,
  AnyDesk CPU burst, foreign build load, blind guard) inside `start_scheduled - 30 s .. end + finish_grace_s` make the new always-on
  `host_guard` assertion, and the run, **INVALID**: ordered before FAIL, never PASS, exit code 2, FAIL evidence kept and named. New
  `testlab.py preflight-soak` (P1-P7) and an automatic P1-P6 preflight for scenarios with `requires_clean_host` (S09 v5, which refuses to
  start on a FAIL; `--require-clean-host` for others). The rule becomes "no `AnyDesk.exe --backend` and no session event from T-2 min to
  the end; resident processes allowed". `host_quiet` names the nearest guard event for every single-process frame of 1 s or more.
  Limits are policy, unvalidated (`testlab/docs/THRESHOLDS.md`); no scenario threshold or pass rule changed. Tests: `HostGuardTests`
  (real scrubbed `ad.trace` fixture).

- **testlab S16 judges the undefined-message-type case** on `gameserver_messages_rejected_total{reason="unknown_type"}`
  (rpg-mmo-server #490, `76aa973`): the `malformed_input` rule gains `rejections_counter` (default `gameserver_inputs_rejected_total`), the
  `unknown_type` case asserts the counter rises by 1 and the session stays open, and a server without the series leaves the case
  INCONCLUSIVE (not FAIL). S16 version 2; S16 can now PASS (two live runs against server `7c412e4`, see `testlab/docs/COVERAGE.md`).

- **testlab scenario S18 (packet impairment)**: loss, delay, jitter and reordering on the game server's UDP path, with two rendered clients
  moving, a 30 s clean baseline, a 60 s impaired phase and a 30 s recovery.
  - `testlab/lab/netem.py` shapes with `nsenter` + `tc netem` inside the scratch game server container's own network namespace (UDP port 9000
    only, both directions: `prio` + netem on `eth0` egress, `ingress` redirect to a per-container `ifb0` carrying the same netem). No compose
    override, no capability added to the server, no host-wide qdisc, `/status` and every TCP connection unshaped. Removal is guaranteed and verified:
    `finally` in the step, the runner's own `finally`, a detached watchdog process that deletes the qdiscs after the planned time + 45 s, and a leftover sweep
    in the preflight. Needs passwordless `sudo` for `nsenter`/`tc` in WSL (the preflight says so before any player starts).
  - New checks in `testlab/lab/analyze_netem.py`: `netem_applied` (tc loss counters within 3 sigma of the configured loss, clients' round-trip
    time up), `netem_cleanup`, `netem_retransmits` (server KCP resends rise only while impaired), `netem_snapshots` (per-phase gap and rate limits),
    `netem_prediction` (hard snaps, corrections, keyframes per phase) and `netem_convergence` (clients draw the same positions again within 10 s of the removal).
  - `kcp_health` accepts `"max_dropped": null` (inbound drops reported, not judged); `cross_client_convergence` accepts `until_s`.
  - Thresholds, each with its derivation or marked "policy, unvalidated", and the impairment profile with its source (CORE-BASELINE-V1.md) are in
    `testlab/docs/THRESHOLDS.md`; the `robustness` suite includes S18; 63 unit tests in `testlab/tests/test_netem.py` (run by `tests/run-all.sh`).

- **testlab scenarios S16 (malformed input) and S17 (churn)** with a raw-client harness step.
  - `testlab/lab/rawclient.py` joins the scratch stack like a client (gateway auth, enter world, KCP join, JSON envelopes) and can send
    frames a real client never would; `testlab/lab/rawprobe.py` runs it from a scenario disruption (`raw_malformed`, `raw_churn`) on its
    own thread and records `rawprobe.ndjson` (part of the provenance manifest). The step records; the analyzer decides.
  - S16 sends 11 malformed cases (length prefixes over the 1 MiB limit, zero length, truncated frame, undefined and out-of-range type, garbage
    protobuf, out-of-range movement, attack out of range, cast inside the cooldown) while two rendered clients play. New checks:
    `malformed_input` (each case refused or closes only its own session, with the server counters that moved), `server_alive`,
    `client_sessions`. A `stays_open` case without a `rejections` rule grades INCONCLUSIVE (the session surviving does not show the
    input was refused). The undefined-type case was that case until rpg-mmo-server #490 added the counter (see the S16 entry below).
  - S17 runs 10 cycles of silent drop plus rejoin and graceful leave plus rejoin, then waits out the server's longest hold. New checks:
    `churn_cycles`, `churn_ghosts`, `player_count_baseline`, `redis_leak` (Redis session, registry and map-member key names before and after).
  - Thresholds and their derivations are in `testlab/docs/THRESHOLDS.md`; a new `robustness` suite runs both.
  - 43 unit tests in `testlab/tests/test_lab.py` (raw client against a UDP peer, step helpers, every check's pass and failure modes,
    scenario timelines); `testlab/README.md` and `testlab/docs/COVERAGE.md` document them.

- **`testlab/`: autonomous multiplayer gameplay tests with real, rendered Unity clients.**
  `python3 testlab/testlab.py run|suite|sweep|analyze|build-client|build-loadtest|stack|clean`.
  - It starts the isolated scratch stack (`stack.sh --scratch` + `STACK_SCRATCH_EXTRA_ENV`) and
    launches N players with distinct devices.
  - It drives them through scenario files (S01-S10: bootstrap, idle stability, movement and
    collision, combat, crowding, replication, load sweep, reconnect, soak, regression replay)
    through the client's `IGameplayInputSource` seam. No focus or keyboard is needed.
  - It records client traces and server-authoritative positions (`/debug/entities`) and grades
    every assertion PASS / FAIL / INCONCLUSIVE / INFO with source, sampling, threshold and
    artifacts. Missing evidence is never a PASS.
  - Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 harness error.
  - Design, commands, artifacts and triage: `testlab/README.md`.
  - `tests/run-all.sh` runs its unit tests (`testlab/tests/test_lab.py`) and loads every scenario.
  - Crowd checks for rpg-mmo-server#469: `spawn_overlap` (no fresh or respawned player starts
    within 0.5 units of another), `enemy_pursuit` (an enemy far from every player heads for the
    nearest one; settled-crowd speed relative to its target). `enemy_crowding` overlap is a failure
    where the scenario declares separation (S02, S05, S10). Concentration on one player is INFO
    unless a scenario sets `share_is_failure`, because it follows the nearest-player rule.
  - `render_jumps` classifies a jump as a server teleport when the client's own received stream
    shows the same step, and gives host stalls a 1 s tail window, so a respawn the server probe
    aliased is not counted against interpolation or prediction. A received step counts only when
    no entity could walk it in the server ticks between the two samples.
  - `enemy_pursuit` is judged on isolated enemies; crowd steps (separation, queueing) are reported.
    `inputs_consumed` leaves server respawns out of a move segment. Evidence minimums make sparse
    pursuit or spawn evidence INCONCLUSIVE.
  - `--player` accepts a build directory; sweep files are named by scenario id; the atomic JSON
    write retries while a player holds the file (Windows).
  - **Run provenance.** `run.json` records factory, server and client commits, the scratch server
    image id, the embedded Netcode commit (`VERIFY-PROVENANCE.txt`), player exe and managed-code
    hashes, scenario id, version and file hash, host load at start and end, start and end, and a
    sha256 manifest of the evidence files. Every evaluation appends a `provenance` assertion: a
    missing record, a missing field, a run id that is not the directory's, or evidence changed
    after the run is INCONCLUSIVE. Runs recorded before this change therefore re-grade
    INCONCLUSIVE instead of PASS. `results.json` names the run it analyses (`analysis` block);
    `analyze --out DIR` leaves the run directory untouched.
  - **Missing evidence is never PASS, for every check** (tested per check with absent and empty
    inputs). Fixed: `client_log_clean` passed with no player log, `snapshot_cadence` with no
    clients, `render_jumps` with a client's events missing, `players_online` and `redis` with
    zero clients.
  - **Cleanup.** `run`, `suite` and `sweep` stop the scratch stack when they finish, also on
    failure and Ctrl-C (`--keep-stack` keeps it). Ctrl-C stops the players, writes the run record
    and re-raises. Every docker action refuses a container outside `rpgs-*`, and a misconfigured
    `container_prefix` cannot widen the container filter to `rpg-*`.
  - **`leak-check <player>`** reports whether a built player contains TestLab code
    (`NDC.TestLab*` assembly, `CUVARA_TESTLAB`, TestLab type names) without building or running it.
  - **`analyze --delivery <run>`** (rpg-mmo-server#473): joins the server snapshot trace (C1,
    `--snapshot-trace` / `snapshot_trace: true` sets `GAMESERVER_SNAPSHOT_TRACE` and copies the
    file into `server/`) with the client trace (C2 `delivery.csv`, `render.csv`). It reports per
    client and 5-minute bucket the send and receive gaps, relative one-way delay, queue, drops,
    KCP retransmissions and send queue, and classifies every receive gap over 250 ms as
    SERVER_LATE, QUEUE, CLIENT, KCP, PATH or UNKNOWN and ALL-CLIENTS or SINGLE-CLIENT. It is
    diagnostic only.
  - `testlab/docs/COVERAGE.md`: readiness areas mapped to scenarios and checks, with the gaps.
  - **Factory-only coverage gaps closed (COVERAGE F1-F6).** New checks: `snapshot_order` (no
    backward or repeated world tick within a session), `enemy_bounds` (enemies inside the map
    file's bounds at the run's server commit), `enemy_budget` (live enemies within the budget
    the server reports), `render_freshness` (C2 snapshot age p99 within TargetDelay +
    MaxExtrapolation, 150 ms), `prediction_bound` (at most 6 hard snaps per client-minute,
    derived from the 2026-10-22 runs) and `server_config` (the scenario's `SIM_*` rates were in
    force). Each is INCONCLUSIVE on missing evidence. New scenarios S11 (resync after a
    game-server restart) and S12 (30/15 Hz tick rate). `snapshot_cadence` and
    `render_freshness` take `exclude_s` windows; `clients_in_world` takes `reentered_after_s`.
    S01-S10 gain `snapshot_order`, and `prediction_bound`/`enemy_budget` where they apply
    (versions bumped).
  - `build-client` writes a `netcode` block (embedded git HEAD or packages-lock hash) into
    `testlab-build.json`, so a build-client player's provenance names its Netcode commit.
  - **Client trace schema v2 and the client coverage hooks C1-C6** (client 299b6c8,
    `docs/TESTLAB.md`). `render_freshness` now grades the render clock that drew each frame
    (v2 `render_tick` / `clock_newest_tick`): p99 overrun past the newest consumed tick <=
    MaxExtrapolation (50 ms); v1 render.csv (empty `render_tick`) is INCONCLUSIVE. New checks
    `tick_adoption` (C1), `entity_lifecycle` (C3: no ghost after removal, reused ids drawn at
    their own spawn), `cross_client_convergence` (C4: same entity, same render tick, same place),
    `stall_recovery` (C2) and `graceful_leave` (C6); each INCONCLUSIVE without its hook's
    evidence. New scenarios S13 (client stall 500 ms and 2000 ms) and S08G (graceful leave);
    suite `readiness` (S11 S12 S13 S08G). Plan actions `stall`, `quit`, `reconnect`,
    `cast_at_point`, `cast_spam` are accepted; `clients_completed` takes `expected_outcomes`.
  - **`prediction_bound` grades only unexplained snaps.** Every snap is matched by world tick to
    a server respawn or teleport of the same player (/debug/entities); explained snaps are
    reported, the rest are graded at 4 per client-minute (fixed builds at most 2.0, pre-fix runs
    7.5 or more, derived from every stored run). It was 6 total snaps per client-minute, which
    counted correct respawn snaps as errors.
  - **Server hooks S1/S2/S4 (rpg-mmo-server #475).** Disruption `debug_kill` (POST /debug/kill,
    recorded with HTTP status and server tick in `disruptions.ndjson`; `requires_debug_kill`
    assertions are INCONCLUSIVE unless the kill was confirmed). Checks `debug_kill_respawn`,
    `input_rejections` (per-reason rejection deltas) and `cast_damage_bound` (refused casts do no
    damage; no hit beyond the projectile's reach; numbers read from content/abilities.json).
    `enemy_bounds` reads /status `map_bounds` first. Scenarios S14 (deterministic death and
    respawn) and S15 (combat negative path) join the `readiness` suite.
  - **Server image revision.** `--build-server` passes the server HEAD as `STACK_GIT_REVISION`
    (stack.sh stamps it into `org.opencontainers.image.revision`); provenance records the running
    image's label and is INCONCLUSIVE when it is missing or differs from the recorded server SHA.
    Server trees whose stack.sh predates the variable are recorded as `label unsupported`.
  - **Independent review R3 fixes.** Provenance hashes every evidence file (now including
    `disruptions.ndjson`) and checks each scenario's expected inventory: an omitted, unrecorded
    or changed file is INCONCLUSIVE. `analyze --delivery` fits each client's clock rate against
    the server's (the WSL VM clock runs about 7 % slow) and reports one-way delay as unavailable
    when the fit is poor. A run whose informational assertion would fail (S07/S07P memory) is
    PASS_WITH_WARNINGS (exit 4), never PASS; the report shows that and host load under
    "Qualified by". `testlab/docs/THRESHOLDS.md` (generated, kept current by a test) lists every
    limit with its source or "policy, unvalidated".
  - **Soak plan and classifier fixes (T06 findings).** S09 v4 repeats its 300 s movement and combat
    cycle for the whole `--duration` (`repeat_cycle_s`; earlier 1 h soaks were 5 min active, 55 min
    idle). `analyze --delivery`: a gap is ALL-CLIENTS when the other clients' gaps overlap in time
    on the server clock or in touching tick ranges; the KCP class also reads the 4 server rows after
    the late snapshot. On the 1 h soaks the clock fit stays poor (the WSL clock rate wanders
    1.073-1.090), so one-way delay is reported unavailable. Preflight fails fast when a server
    worktree has no `modules/nakama.so` and `--build-server` is not set.
  - **S08G analysis fixes (T34).** A client that left with `quit` writes `summary.json` after
    `Disconnect()`, with an empty user id; client user ids now fall back to the `in_world` event and
    run.json, so `graceful_leave` is judged instead of INCONCLUSIVE. `entity_lifecycle` no longer counts
    the sample of an entity's re-add frame (AOI re-entry) as a ghost of its earlier removal.
    `graceful_leave` names a dead_link session close (the polite disconnect frame never arrived).
  - `cross_client_convergence` skips pairs within 0.5 s of a server-side respawn or teleport of the
    compared entity (`teleport_window_s`): next to one, one client may already draw the new position.
    The final soak's maximum (18.56) was such a pair.
  - **Analysis memory bounded (T41).** A 1 h soak's analysis needed about 13 GB. Samples, events,
    inputs and server entity rows are now streamed from their files (`util.LazyNdjson`) instead of
    held as Python objects; trajectories and frames are float arrays; large value sets use
    `util.Distribution` (exact up to 1 M values, then 1e-6 bins); `cross_client_convergence` forms
    pairs per 60 s render-tick window; `entity_lifecycle` merges its windows with the sample stream
    (its quadratic next-event scan is gone). On a synthetic soak the peak drops from about 7x to
    2x the evidence size; results equal the pre-change analysis (frozen reference test).
  - **S13 stall catch-up rule (Lead decision).** On a client with a scripted stall, remote render
    jumps and remote divergence from the stall start through the frame after the frame whose dt
    contains the stall are not judged (the world moved while the process was frozen; one-frame
    binder drain lag); one local major correction per stall is allowed within 5 s, a second FAILs.
    Other clients and later frames are never excluded. COVERAGE.md statuses refreshed (T31 runs,
    hooks S1-S4 and the delivery trace done, graceful-leave fix upstream).
  - **Reverse scans stay bounded (review R5-1).** `reversed()` on a `util.LazyNdjson` read the whole
    file into a list; it now reads the file backwards in 64 KiB blocks (`util.iter_ndjson_reversed`,
    same rows and skips as the forward reader), so a last-match search (`_user_ids` on events,
    `_status_map_bounds`) holds one block and stops at the match. Server `status.ndjson` (~30 MB in a
    1 h soak) is streamed as well instead of held as a list.
  - **Session-aware delivery classes (T58).** `analyze --delivery` classifies a receive gap that spans
    a session change as RECONNECT (with the cause from player.log when known): a C1 `conn_id` change
    between its two snapshots, or a client `net_state` Ended / `reconnected` inside it. Joined by user id
    alone, the e26z post-reconnect gaps read as SERVER_LATE with retransmission deltas of -700..-1295.
    Bucket counter deltas (retransmissions, dropped) are summed per connection. entity_lifecycle and
    cross_client_convergence are unchanged: every e26z failure lies between a client's frame freeze and
    its reconnect (the backlog frame, and client 0's 31 s on a dead session), none after a session
    change, and the backlog-frame reuse is a real Netcode view defect (T57, Netcode 4520ccf). A test pins
    that an id added after `entities_reset` is not judged as a reuse.
  - **Predictor call trace (T56).** A scenario can turn on the client's Netcode predictor call trace per
    client (`"predictor_trace": true` in `client_defaults` or a `per_client` entry; plan `predictor_trace`;
    client d6c8839, Netcode >= 8986908). S13 (version 2) records it on client 0, the stalled client; the
    expected provenance inventory then requires `client-0/trace.ndjson`. New `testlab.py replay-trace <run>
    [--client N] [--out DIR]` (`lab/predtrace.py`) validates the trace (header and settings, frame markers in
    order, each `Reconcile` followed by its `ReconcileResult`, steering begin/end nesting, steering times) and
    lists the corrections the live predictor recorded per scripted stall. The exact replay stays with Netcode's
    `PredictorTraceReplayer`; the recipe is in testlab/README.md "Predictor call trace".
- `scripts/checks/netcode-headless.sh` finds the rpg-mmo-server holding the pinned Shared.GameLogic
  tag from a Netcode worktree too: `--server DIR`, else the Netcode dir's sibling, else
  `$RPG_FACTORY_WORKSPACE/rpg-mmo-server`; `--resolve-server` prints the choice
  (`tests/netcode-headless.test.sh`, in run-all).
- `netcode-headless.sh` fails when `dotnet test` fails or times out, whatever TRX it left
  (`NETCODE_HEADLESS_TIMEOUT`, default 900 s).
  - Paths given to the CLI in Git Bash form (`/c/...`) work with Windows Python. The README states
    which commands run in Git Bash and which also run in WSL, and that `build-client` regenerates
    the scene only with `--rebuild-scene`.
- `skills/measure/references/legs.md`: the testlab as the multi-client verification leg.
- **Parallel-work policy.** New `skills/factory-core/references/parallel-work.md` is the single policy for
  delegated work: the main session is the lead and integrator; one worktree per implementation task (Orca-managed
  or `isolation: "worktree"`, never a second clone); one Unity writer per client project; shared exclusive
  resources go to one task at a time and a task without one reports `NOT_RUN`; QA and review run in parallel on
  a recorded candidate commit; the lead re-verifies, integrates in dependency order and cleans up only its own
  worktrees, keeping task branches (`orca worktree rm` also deletes a merged checked-out branch, so it is only for
  disposable branches). Orca is the preferred coordinator (load `orca skills get orchestration`; never a decision gate for
  routine work) with Claude Code worktree agents as the fallback. Tags, releases, deploys and `human_gates` keep
  their rules; nothing new asks or blocks. factory-core `SKILL.md`, `git-safety.md` (rule 10 now points here,
  rule 5 names the lead's integration-branch merges), `report.md` (optional parallel-work ledger) and
  `.claude/CLAUDE.md` point to it without copying it.
- `tests/skills-lint.sh` checks the policy is linked, exists in one copy (by its signature phrases), contains no
  blocking wording (ask/prompt the user, wait for / get / require approval or confirmation, until the user,
  `permissionDecision`) and keeps the release and `human_gates` rules; `tests/parallel-policy.test.sh` proves those
  checks fail on a mutated plugin copy; `tests/orca-commands.test.sh` verifies every cited `orca` command against
  `orca --help` and every `--flag` cited with it against that command's `--help` (skipped when Orca is not
  installed, and in `--no-workspace` runs), including that `orca worktree rm` still deletes branches as the
  policy warns.
- `tests/skills-lint.sh` checks that a skill's `allowed-tools` covers every plugin script its `SKILL.md` or
  `references/` tell the agent to run (`${CLAUDE_PLUGIN_ROOT}/scripts/...` uses, and backticked bare script names in
  non-core skills; entry paths match as fnmatch patterns, a named interpreter must match the entry's);
  `tests/parallel-policy.test.sh` proves it fails on a mutated copy.

### Fixed

- Updated .NET game server skill citations to current `EcsWorld` definitions on server `origin/develop`.

- Enforced section citations for Markdown documentation in skills; line citations now fail the skill citation checker.
- **Task-scoped routing in the snapshot.** Without `--paths`, uncommitted changes are the user's baseline: the
  snapshot lists them with their modules but prints no Routing, `Next:`, gates or checks for them and says to route
  the task with `--paths <files the task will write>` (commits on a feature branch are still routed; JSON keeps the
  full resolution and adds `task_scope`). A module without skills prints an explicit `**Routing** no specialised
  lead - factory-core only; follow <CLAUDE.md>` line. An absolute `--paths` entry in a linked worktree of the repo
  maps to its repo-relative path; one in another repo or outside every repo gets a warning and is not routed as
  `<repo>.root` (exit 2 when no path is left). `--mode=plan`, `--lead=x` (any `--flag`) after `--paths` end the
  path list instead of being read as paths. `tests/routing.test.sh` covers each case on a throwaway workspace.
- **Runner timeout isolation.** Checks run in a Windows Job Object or process group with bounded cleanup verification; taskkill fallback verifies the captured process tree, and Git Bash is preferred on Windows while WSL bash receives validated workspace and repository environment values.

- Run wire parity and Netcode headless checks against the candidate checkout, report tested tree SHAs, and fail closed on unresolved trees or unsuccessful test hosts.
- Grade Netcode TRX results as successful only with a present Completed/Passed outcome, valid counters, executed tests, and zero failed, error, timeout, or aborted tests.
- Windows runner cleanup now treats inaccessible or otherwise unqueryable child processes as unknown and fails closed; TRX parser regression cases explicitly target their fixture checkout and assert the parser's diagnostic.
- Candidate check targets must be Git work-tree roots, preventing nested plain directories from inheriting a parent repository's SHA.
- Fingerprint dirty and untracked check outputs using a single stat's size, nanosecond mtime and mode (plus symlink target), avoiding reads of large untracked assets; pass Git Bash Windows paths as `C:/...` without requiring `cygpath` on Windows Python's PATH.
- Isolate each executed validation check's working-tree pollution, terminate its child process tree on timeout, and pass the resolved workspace and checkout through the check environment.
- The `unity-client-tech` `MainSessionDriver.Endpoint` citation now spans the whole adapter class (`MainSessionDriver.cs:237-364`); the old range began in `RunFlowAsync` and ended inside the class.
- **Windows lock retry budget for state files.** `fstate.read_json` and `write_text` retry a Windows sharing
  violation (`PermissionError`) for up to 2 s (backoff capped at 50 ms) instead of a fixed 8 / 5 attempts
  (~0.36 s / ~0.3 s), so a record held open under machine load no longer reads as missing (NOT_RUN) and a
  replace no longer fails; other platforms keep the short attempt count (`tests/session-state.test.sh`).
- Git and file guards: a linked worktree outside the workspace root (Orca worktrees, sibling dirs) whose main
  checkout lies in the workspace now gets that checkout's rules (tags, pushes, protected branches, secrets,
  generated paths), from its cwd or through `git -C`; before, every command there was silent. The worktree is
  found from its `.git` file (no extra git process); a main checkout outside the workspace stays silent.
- Git guard: `merge --ff-only` on a protected branch no longer warns (a fast-forward creates no commit), and
  `pull --rebase=false|no|off|0` (any case) is no longer treated as a rebase.
- `tests/skills-lint.sh`: the dev-tools and allowed-tools blocks fail closed - a crash of their Python check is a
  FAIL (it passed silently before), and skill files are read as UTF-8 (a non-ASCII reference crashed the check
  under a cp1252 locale). `tests/parallel-policy.test.sh` covers both. parallel-work.md says an
  `isolation: "worktree"` QA/review worker starts from the lead's HEAD and checks the candidate SHA first;
  the report template's dotnet row no longer asserts "0 failed".
- Skill `allowed-tools` now grant the scripts the skills run (netcode-client, pin-bump, server-ops, server-realtime,
  unity-package, wire-contract), so unattended runs no longer hit permission prompts.
- `git-safety.md` rule 5: PRs target the repo's default branch from `registry.json`, not always `develop`.
  `repos.md` and dotnet-gameserver describe the gameplay transport as KCP/UDP only (ADR-32). `report.md`'s template
  uses placeholders instead of asserting a `--status` result and example test counts. `parallel-work.md` section 6
  runs each QA and review worker in its own worktree at the candidate SHA. pin-chain.md and packages.md point to
  `pin-status.py` / `package-ready.py` instead of stale pin versions.
- **Truthful check evidence.** A check's identity scope now includes its own module's paths, so editing
  `backend/content/` makes a `content-loader-tests` PASS (run in `backend/gameserver-dotnet`) STALE; a record
  made under another scope is STALE (`check scope changed`), so pre-upgrade records re-grade once. `factory-status`
  grades evidence against the current registry definition (a changed `run` is STALE there too, like
  `run-checks --status`) and a record of a check no longer declared is STALE. Two modules sharing one command each
  get a record graded with their own definition and identity (both PASS right after the run). A check whose
  `needs` prerequisite did not PASS in this run (failed, skipped by `--only`, listed after it) is BLOCKED.
  `run-checks` exits 2 on an unknown `--tier`/`--only` name, a bad `--timeout`, a `--paths` entry outside the
  repo checkout and its linked worktrees (also `../` escapes and paths `factory-context.sh` rejects) and a path in
  another linked worktree of the repo (checks run in, and evidence describes, the checkout `run-checks` runs in:
  run it from that worktree), and prints `none registered` when no check is declared for the paths.
  `validation.md`, factory-core `SKILL.md` and the README describe the new `BLOCKED` meaning.

## [1.0.5] - 2026-10-22

Stability release after a full audit of 1.0.4 (hooks, session state, routing, install, release workflow). Hooks stay
advisory-only and never block; nothing asks for approval. Fixes: tag/push/destructive commands the guard missed
(git-bash `/c/` paths, shell blocks and functions, heredocs read by a shell, `gh --repo`), a missing or failing hook
script can no longer return Claude Code's blocking exit code, atomic and lossless session state and evidence under
concurrency, absolute `--paths` routing on Windows, stale-install detection, workspace worktrees in file-guard, and a
pre-tag `scripts/release-check.py`. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin
update rpg-factory@rpg-factory`) and start a new session. Evidence stored by 1.0.4 shows as NOT_RUN once (new
workspace key). No command-line or registry changes for users.

### Changed
- **Release policy wording matches practice.** The docs, skills, registry rule `no-tags`, snapshot header and guard
  advisories said agents never tag, while 1.0.4 was tagged and released by an agent on the user's explicit
  authorization. They now say: without explicit release authorization from the user in the current task, stop at
  READY_TO_TAG and the lead tags; with it, perform exactly the authorized merge, version, tag and release steps after
  the release checks pass on the tagged commit (never move, delete or reuse a tag). No behaviour change: the guard
  flags the same commands at the same advisory level, nothing blocks or asks. `run-all.sh` fails if the absolute
  "agents never tag" wording returns or a policy file drops the authorization rule.

### Fixed
- **Guard classification gaps.** `git-guard.py` stays advisory only (no permission decision, exit 0); these
  commands were missed or misread and now get the advisory they should:
  - Windows git-bash paths: `cd /c/...`, `git -C /c/...`, `/mnt/c/...` and such paths in the human-gate scan
    resolved to `C:\c\...` (no workspace, no advisory); they are mapped to drive paths first (`native_path`).
  - Shell reserved words hid git: `{ git tag v1; }`, `! git tag`, `if/then/else/elif`, `for/while/until ... do`,
    `f() { ...; }`, `function f { ... }`, PowerShell `if (...) { git tag v1 }` / `foreach (...) { ... }` (braces end
    a PowerShell command).
  - A heredoc read by a shell (`bash <<EOF`, `bash -s <<EOF`, `cat <<EOF | sh`) is analysed as commands; read by an
    interpreter (`python3 - <<PY`) and mentioning git/gh it is warn (opaque). Other heredocs (commit messages,
    `cat > file <<EOF`) stay data.
  - `gh --repo/-R/--hostname <x>` before the group or verb hid `release create`, `pr merge` and the `publish` gate.
  - Interpreter one-liners invoking `gh` (`python3 -c "...gh release create..."`, `node -e`) are warn like git.
  - Non-object JSON payloads (`[]`, `null`, `42`) crashed with a traceback (exit 1); stdin is read as UTF-8, so a
    non-ASCII cwd no longer breaks the workspace match on Windows.
  - `git tag --merged`, `--no-merged <c>`, `--no-contains <c>` and `--sort <full key>` / `--format '%(...)'` as
    separate words are listings (allow); a name after them, and the abbreviated `--sort -v:refname`, stay high.
  - Speed: read-only git subcommands (status, log, diff, ...) skip the per-repo git calls and the others are
    memoised per directory (30 x `git -C backend status`: ~1.36 s -> ~0.18 s on Windows); commands over 200 KB
    get one warn ("command too large to check") instead of minutes of parsing.
  - `factory-context.sh --mode <m>` run outside the workspace now records the mode (a stale read-only mode stayed),
    and the mode is only recorded when the script is actually run - `grep factory-context.sh --mode review` or
    `echo ... --mode plan` no longer switch it.
  - Wording: the module and `classify_gh` docstrings describe advisory levels high/warn, not deny/ask decisions.
- **Session state and evidence robustness.** Hooks stay advisory-only and never block; tests in
  `session-state.test.sh`, `run-checks.test.sh` and `factory-status.test.sh` cover each fix.
  - Evidence records and run records are written atomically (`fstate.write_json`, readers retry the Windows
    replace window); log and run-record names carry a pid + random suffix, so parallel or same-second runs never
    share or truncate a file. Only the newest 20 logs per check are kept (never the one the latest record names).
  - Valid JSON of the wrong shape in the evidence dir (`{"identity":"x"}`, `[1]`, no `state`) is treated as no
    evidence (NOT_RUN) instead of crashing `run-checks.py --status` and `factory-status.py`.
  - `run-checks.py --dry-run` writes nothing (no run record).
  - The auto-correction of an early tech skill to factory-core happens once per session even under parallel Skill
    calls (claimed by an exclusive `CORRECTED` file; the other calls get the lead-missing advisory).
  - The Skill hook's logs are one file per event (`SKILLS.d/`, `ADVISORIES.d/`): parallel appends lost lines on
    Windows. Legacy `SKILLS` / `ADVISORIES` files are still read. Read them with
    `factory_session.py --skills <session-id>` / `--advisories <session-id>` (used by git-guard.test.sh and dogfood.sh).
  - `MODE` is replaced atomically (no torn reads). A mode is recorded only when the command really runs
    `factory-context.sh` / `context.py` (`grep factory-context.sh --mode review` or `echo ...` no longer set it), and
    "do not implement" alone in Skill arguments is no longer a plan-mode declaration.
  - The hook prints its advisory / correction before logging; an unwritable log loses nothing the session sees,
    and with no usable session dir it advises without correcting.
  - Session ids go through one helper, `fstate.session_key()`: plain ids are unchanged, anything else (`..`, `.`,
    over 100 characters, characters a substitution would collide) becomes `s-<sha1>`.
  - A bare registry skill name (`go-backend` without `rpg-factory:`) is recorded and gated like the prefixed name.
  - `fstate.scratch()` skips a candidate whose `rpg-factory/` cannot be created; `persistent()` falls back to the
    platform temp dir (absolute on Windows too).
  - The evidence workspace key is the case-folded real path, and `run-checks.py` and `factory-status.py` resolve
    `RPG_FACTORY_WORKSPACE` the same way. Evidence stored under the old key shows as NOT_RUN once; rerun the checks.
- **Routing, install and docs.**
  - `factory-context.sh --paths` with an absolute (`C:\`, `C:/`, git-bash `/c/`, WSL `/mnt/c/`) or glob path
    routed nowhere on Windows (`relpath` returned backslashes, lead null). Paths are normalised to repo-relative
    forward slashes; another drive no longer raises. New routing scenarios (absolute forms, glob).
  - A missing hook script made python exit 2, Claude Code's blocking code. Every `hooks.json` command now ends
    with `; exit 0` (bash and PowerShell); stdout still passes through. run-all checks the wiring and runs each
    command against a missing and an exit-2 script.
  - `install-status.py` reported CURRENT for an old cache copy on Windows (backslash `CLAUDE_PLUGIN_ROOT` missed
    the `/.claude/plugins/cache/` test) and whenever the runtime version differed from the source; both are now
    RESTART_REQUIRED. `--session` never tracebacks on malformed `installed_plugins.json` /
    `known_marketplaces.json` and always exits 0. New informational note (doctor, `--json` `notes`) when the
    source HEAD is not the commit of tag `v<VERSION>` (`source 1.0.4 + N commits past v1.0.4`); no state change.
  - `file-guard.py`: linked worktrees of a workspace repo (`.wt-client-cleanup/`) get that repo's rules (via the
    git common dir); paths outside the workspace get no advisory even with `RPG_FACTORY_WORKSPACE` set; the mode
    advisory command is quoted with forward slashes; secret names match case-insensitively (`.ENV`).
  - `tests/dogfood.sh` looks for the session's `ADVISORIES` / `MODE` under both `fstate.scratch()` and
    `persistent()/tmp` (headless hooks on Windows Python 3.14 fall back to the latter).
  - Agent-facing wording said the hooks enforce or deny (snapshot mode line, `tag (deny)` in Human gates, pin-bump
    "denied by the guard", `.claude/CLAUDE.md`); it now says advisory (`tag (high)`), pin-bump names the explicit
    release authorization, README marks the pre-1.0.3 "denied" note historical and states the Windows scratch
    root, and the `--mode` / path forms are documented in the usage headers. run-all fails if
    `denied by the guard`, `hooks enforce` or `(deny)` returns in agent-facing text.
  - New `scripts/release-check.py` (read-only) gates a release before the tag (versions agree, CHANGELOG section,
    empty `[Unreleased]`, tag absent locally and on origin, HEAD == origin/main, clean tree; `--notes` prints the
    release notes) and verifies it afterwards (`--verify-tag`: annotated, `rpg-factory X.Y.Z`, at HEAD, VERSION).
    `tests/release-check.test.sh` (throwaway repo, local bare origin) runs in run-all; the order is in
    `.claude/CLAUDE.md` "Releases".

## [1.0.4] - 2026-10-22

Fix: tech skills stay behind their lead skills under the advisory-only hooks of 1.0.3, still without blocking or
asking. A tech skill requested before factory-core loads factory-core instead (auto-corrected); one requested
before its lead runs with an advisory. Update the plugin (`claude plugin marketplace update rpg-factory && claude
plugin update rpg-factory@rpg-factory`) and start a new session. No command-line or registry changes.

### Fixed
- **Skill order under advisory-only hooks (1.0.3 dogfood regression, `tech-go` and `tech-dots`).** With the
  Skill hook advisory-only, a model could load a tech skill before its lead; dogfood reported it as a failure
  and nothing showed whether the session corrected itself. The hook still never blocks or asks:
  - a tech skill requested **before factory-core** is auto-corrected: the call loads `rpg-factory:factory-core`
    instead (`updatedInput`; Claude Code honours it for the Skill tool - verified in a headless session, not
    documented for Skill), with an advisory naming the route command and the leads. Once per session (factory-core
    is then recorded), so it cannot repeat or loop. If a Claude Code version ignores `updatedInput`, the tech skill
    loads and the advisory still applies;
  - requested **after factory-core but before its lead**, it runs with an actionable advisory ("this call
    continues", the route command, the leads). No auto-correction there: two to four leads use each tech skill and
    only routing knows which applies.
  - every advisory is logged to the session's `ADVISORIES` file, and `SKILLS` records what actually loaded.
  - `tests/dogfood.sh` now grades what loaded (the "Launching skill" results, so an auto-corrected call counts as
    factory-core) and passes a tech-first session only with evidence: the hook's advisory for it, one of its leads
    loading afterwards, and a finished session. New scenario `tech-first` forces the auto-correction. The mode check
    reads the real session state path (`fstate.scratch()`, not `/tmp/rpg-factory`).
  - regression cases in `git-guard.test.sh` (early go-backend, early unity-dots, normal order, no second
    auto-correction, never a permission decision, the hook always exits 0) and `session-state.test.sh`.
- The README "Version" line still said 1.0.0 through 1.0.1-1.0.3; `run-all.sh`'s version check now covers it
  (VERSION == plugin.json == marketplace == CHANGELOG section == README).

## [1.0.3] - 2026-10-22

Hotfix: the hooks never ask for confirmation and never block; every former ask/deny rule reaches the agent
as an advisory. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and start a new session. Also ships the citation drift guard (PR #6, new optional
registry field `skills.<s>.cite_roots`) and the skill authoring workflow (PR #9). No command-line changes.

### Added
- **Skill authoring workflow.** Adding a skill meant about 25 hand edits across the registry, skills,
  tests, docs and evals, and several lists had already gone stale (unity-dots and netcode-client were missing
  from the factory-core tech list, the README diagram and tech table, and dogfood; go-backend and
  dotnet-gameserver had no eval grader).
  - `scripts/new-skill.py` scaffolds a lead or tech skill: `SKILL.md` with every section skills-lint
    requires and `SCAFFOLD:` markers, plus the registry entry (order after the existing skills of its kind,
    so it never outranks one in routing ties; module ownership or contract driver; `dev_tools.used_by`;
    `cite_roots`). It refuses anything it cannot validate and rewrites `registry.json` only when a JSON
    round trip reproduces it byte for byte.
  - `scripts/skill-touchpoints.py` (read-only, run by `skills-lint.sh --all`) checks that every skill is
    in the factory-core Skills section, the skill-contract diagram, the README diagram and tables,
    `.claude/CLAUDE.md` (names and counts), the plugin manifests' lead count, a routing scenario, a
    dogfood scenario and an eval grader - and that no `SCAFFOLD:` marker is left.
  - Repo-local skill `.claude/skills/skill-author/` (not a plugin skill): the order of work from the
    learning-loop gate to a green run-all.
  - The stale places were fixed; new dogfood scenarios `tech-dots`, `tech-netcode` and evals
    `go-single-test`, `dotnet-single-test`. The routing test's tech list and the Skill-hook test now come
    from the registry, so a new tech skill needs no edit there. `tests/new-skill.test.sh` (22 cases).
- **Citation drift guard (`scripts/checks/skill-citations.py`).** Skills cite product code by
  `path:line`; nothing checked those lines, and a smoke test after 1.0.0 found 9 of 12 sampled server
  citations pointing at the wrong code (e.g. `WriteLoopAsync` cited at `Connection.cs:841`, now 1019). The
  checker reads every line citation in `SKILL.md` and `references/*.md` (full paths, ranges, lists, bare
  `:N` continuations, bare basenames, `dots:`/`client:` and repo-name prefixes) and resolves it at each
  repo's integration branch (`origin/<default_branch>`, `--ref repo=REF` to override) - never the working
  tree. Each line citation needs an **anchor**, the symbol it shows written in backticks before it; the
  anchor must occur within the cited lines +/- 3, else `drift` (with `--suggest`, the corrected line).
  Lines past the end, missing or ambiguous files and line citations outside backticks fail too; a missing
  repo is SKIP. New registry field `skills.<s>.cite_roots` (schema + `check-registry.sh`) says where a
  skill's paths resolve. `skills-lint.sh` runs the repo-free part (`--offline`: backticked and anchored),
  `run-all.sh` the fixture suite `tests/skill-citations.test.sh` and the live check against the workspace.
  The rule is in `skill-contract.md` ("Line citations are checked against the code").

- `check-registry.sh` rejects duplicate keys in `registry.json`: they are valid JSON and jq and Python
  silently keep the last one (a duplicated `cite_roots` hid that another skill had none).

### Changed
- **Hooks are advisory only: they never ask the user and never block the agent.** Agents using the plugin
  still stopped for a human Yes/No: every guard rule returned a `permissionDecision` - `ask` (destructive git,
  any push, rebase, stash, human gates, file-guard rules) shows a confirmation prompt only a person can answer,
  and `deny` (tags and GitHub Releases, `gh repo delete/archive`, read-only execution modes, a tech skill before
  its lead) blocked the call. Now `git-guard.py`, `file-guard.py` and `factory_session.py --skill` never emit a
  `permissionDecision`. A match is returned as `additionalContext`
  `rpg-factory advisory (high|warn): <rule>` - `high` for the former deny class, `warn` for the former ask
  class - and the tool call proceeds through Claude Code's normal permission flow (the user's own settings
  are untouched). The classifiers and rule texts are unchanged; the policy in `git-safety.md` stays as
  guidance for the agent.
- Tests read the advisory level (`high` / `warn` / `allow`) instead of a decision, and every test command
  fails if any hook output contains `permissionDecision`. `tests/session-state.test.sh` adds direct probes
  (rebase, force push, tag, `gh repo delete`, `reset --hard`, multi-client, `kubectl`, a tech skill before its
  lead). `installed-safety.sh` still executes only commands with no advisory.
- `skill-contract.md` "New skill" names every required registry field (`order`, `used_by`, `cite_roots`).

### Fixed
- The skills' line citations, refreshed against the integration branches: drifted lines moved, every
  citation anchored, claims that no longer hold corrected.

## [1.0.2] - 2026-10-21

Fix: read-only inspection of a gated script (`sed -n`, `cat`, `grep`, `head`) no longer asks for a human
gate. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and start a new session. No command-line changes; the registry gains the optional
`human_gates[].read_only_exempt` field.

### Fixed
- **Human gates no longer ask for read-only inspection of a gated script.** The gate regexes match script
  names anywhere in a command, so `sed -n 300,340p Tools/verify-multiclient.sh` asked under `multi-client`
  exactly like running the script (same for `cat bench.sh`, `grep x backup.sh`, `head toggle-packages.sh`).
  New registry field `human_gates[].read_only_exempt` (schema): the git guard skips such a gate when the
  whole command is read-only (`factory_session.is_read_only`, the classifier the execution modes use). Set
  on every gate with a `match` except `secrets`, whose point is reading. Running, editing (`sed -i`),
  redirecting, or piping a gated script into a shell still asks.
- `is_read_only` accepts print-only `sed` (`N,Mp`, `/re/p`, `Nq`, with `-n`/`-e`/`-E`); `-i`, `-f`, the
  `e` and `w` commands, `s///` and multi-command scripts stay non-read-only. A read-only mode therefore
  allows `sed -n 10,40p file`.

## [1.0.1] - 2026-10-21

Hotfix: the tripwire and its workspace latch are removed. Update the plugin (`claude plugin marketplace
update rpg-factory && claude plugin update rpg-factory@rpg-factory`) and start a new session: hooks bind at
session start, so a running session keeps the old hooks until it is restarted. No registry schema or
command-line changes.

### Changed
- The execution-mode and tech-skill-order logic moved from `scripts/tripwire.py` to
  `scripts/factory_session.py` (Skill hook: `factory_session.py --skill`). Behaviour is unchanged.

### Removed
- **The tripwire and its latch, on purpose.** `tripwire.py` snapshotted every workspace repo around each
  non-read-only Bash/PowerShell call. Any ref or baseline-file change in that window, whoever made it,
  raised a STOP and latched the whole workspace for every session until the user ran `tripwire.py --ack`.
  In practice the Unity Editor saving `ProjectSettings/ProjectSettings.asset` latched it within minutes,
  during read-only commands, and blocked autonomous work in every session. Removed with it:
  - the SessionStart baseline scan, the `--pre` PreToolUse hook and the PostToolUse /
    PostToolUseFailure `--post` hooks;
  - the latch deny in `git-guard.py` (`latch_hits`) and `file-guard.py`, and the guard rule that denied
    `tripwire.py --ack` to the agent (`ack_hits`);
  - the file guard's "already dirty when the session started" ask, which read the tripwire baseline;
  - `fstate` latch, audit and activity paths and `ack_command()`; the doctor "Tripwire latches" section;
  - the STOP, ack and recovery instructions in `factory-core`, `git-safety.md`, `report.md` and the
    doctor command;
  - `tests/tripwire.test.sh`.

  State files left by older versions (`latch/`, `audit/`, `activity/` under the persistent state root, a
  session `LATCH`) are no longer read and can be deleted. `tests/session-state.test.sh` (new) checks that
  stale latch files block nothing (`git fetch --tags`, commits, writes), that no hook or script reads them,
  and keeps the state-path checks from the old suite. The git guard (tag deny, destructive-git asks, human
  gates), the file guard's other rules and the execution modes are unchanged.

## [1.0.0] - 2026-10-20

First stable release. Supported environments: Linux, WSL and Windows (Git for Windows bash with native
Windows Python). No registry schema, hook or command-line changes are required of users:
update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and restart the session. Legacy single-file latches from 0.5.0 and earlier are
still read and migrated on `--ack`.

### Added
- **Game rules live only in Shared.GameLogic (ADR-10).** Until now the rule existed only in the
  client's stale `unity-netcode` agent. Factory said nothing when a client or package change
  reimplemented movement, combat or validation logic that the server must agree with. New module rules
  cover `client.scripts`, `netcode.runtime` and `unitydots.runtime`: never copy a game rule. Stop the leg
  and hand the rule to `server-realtime`, then to `pin-bump`. A new rule on `server.gameserver-dotnet`
  says that logic the client must reproduce goes into `Shared.GameLogic`, not only into `GameServer/`.
  `client-integration` has a new workflow step and a new hand-off row, and `server-realtime` step 2 names
  the placement. `tests/routing.test.sh` asserts that each of the four snapshots carries the rule.
- **Tech skill `unity-dots`** (Entities/Burst/Jobs in UnityDots and the client): the ECS-vs-classic
  decision (ECS for many homogeneous per-frame entities; services, UI and request/response state stay
  VContainer + UI Toolkit), the group tree and bootstrap install, `SystemOrderVerifier`, the package ECB
  singleton, the measured `ParallelScheduling` thresholds, archetype-stable spawning, sync points,
  allocators, change filters and ECS tests, every claim cited. References `dots-patterns.md` and
  `ecs-review.md` (the review checklist). Used by unity-package, client-integration and measure.
- **Tech skill `netcode-client`** (com.cuvara.netcode on the client): TCP gateway hop vs KCP-only
  gameplay and its PlayerLoop pump, KcpCrypto (CRC, no integrity) vs the sealed session, codecs,
  snapshot interning and merge, the interpolation clock, movement prediction and reconciliation with
  clock steering, reconnect policy, per-packet allocations, the headless suite. Replaces the client's
  stale `unity-netcode` agent. Used by unity-package, wire-contract, client-integration and measure.
- `unity-client-tech` reference `ui-toolkit.md`: View/ViewModel/Presenter, one-way binding, the
  package list adapters and virtualization, screen flow and subscription lifecycle, the two ways game
  state reaches UI, VContainer scopes and lifetimes. ECS idioms moved to `unity-dots`.
- `measure` reference `client-profiling.md` (markers, Performance Testing, MCP `profiler-*` as point
  samples, no budget without a baseline) and `legs.md` sections for server profiling, the seeded
  network-adversity suites and soak (NOT_AVAILABLE until a harness exists).
- `server-realtime` reference `gameplay-systems.md`: where combat, abilities, statuses, inventory,
  loot and content live, the authority checklist for a new input or command, SGL determinism, and the
  known structural debt.
- **Fast check `sgl-determinism`** (`scripts/checks/sgl-determinism.py`, module
  `server.shared-gamelogic`): fails on any `Math`/`MathF` transcendental in Shared.GameLogic (ADR-10),
  ignoring comments and strings. Fixture tests in `run-all.sh`.
- Registry facts `entities-version`, `burst-version`, `collections-version`, `unity-physics-version`,
  `vcontainer-version`, `unitask-version`, `perf-testing-version`; dev tool `dotnet-diagnostics`
  (`dotnet-counters` / `dotnet-trace`, optional, fallback the server's OTel metrics).
- Evals `dots-spawn-system`, `prediction-reconcile-bug`, `claim-faster-frame`, `inventory-list-screen`,
  `new-command-authority`, `ecs-or-service`; routing scenarios for the new tech skills.
- **CI.** `.github/workflows/tests.yml` runs `tests/run-all.sh --no-workspace --no-claude` on every pull
  request and push to `main` (read-only token, pinned actions, log artifact, FAIL/SKIP summary). The
  runner has no RPG MMO workspace, so workspace checks show as SKIP there; `tests/run-all.sh` with the
  workspace is still required locally before a release.
- **Stash audit.** A visible `git stash` (the approved path) is appended to `audit/<workspace>.jsonl`
  with session, tool call id, command and the stash SHA before and after. It does not latch.

### Changed
- **A tech skill waits for its lead (Skill hook).** The release-gate dogfood `tech-go` failed 4/4 runs: asked
  how to run one gateway test, the model invoked `go-backend` right after `factory-core`, before routing and
  before `server-services`, so the answer skipped the lead's rules and gates. `tripwire.py --skill` now records
  each Factory skill a session runs and denies a `kind: tech` skill until one of its registry `used_by` skills
  ran, with a message naming the route command and those leads; it fails open without a registry. The
  `go-backend` description now has the same "how it works / not for scope" form as the other tech skills.
  `tests/dogfood.sh` counts only Skill calls that ran (a denied call is not an invocation); 12 cases in
  `git-guard.test.sh`.
- **`routing.tech` lists a tech skill only when the snapshot's repo is in its `repos`.** A measure run
  on the server no longer suggests `unity-dots`/`netcode-client`, and a client `Tools/` change no longer
  suggests `dotnet-gameserver` (`scripts/lib/resolve.jq`, skill-contract "Tech skills").
- factory-core step 11 (Review) applies the lead's checklist and the review file of every
  `routing.tech` skill after `/code-review`; the report template gains **Review** and **Lessons**.
- Skill contract: a **learning loop** (a verified failure lands in exactly one of: regression test,
  cited Pitfall, `known_issues`, `facts[]`), version-specific API advice names its fact, and every tech
  skill Pitfall cites a file or issue (`skills-lint.sh` enforces it).
- `known_issues` for the stale client/server CLAUDE.md text and the `unity-netcode` agent name the
  product-repo branches that fix them; remove each entry when its branch reaches the default branch.
- **Tripwire events instead of one latch file.** Each incident is `latch/<workspace>/<event-id>.json` with
  the command, session, tool call id, ref values before and after, and recovery hints (for a dropped
  stash: its SHA and `git stash apply <sha>`). A second incident no longer overwrites the first. `--ack`
  archives events to `acked/` (kept 30 days) instead of deleting them; `--ack <event-id>` acknowledges one,
  and an event created while an ack runs stays open. The latch stays global per workspace. A legacy
  `latch/<workspace>.json` still blocks and is migrated into `acked/` on ack.
- `--status` lists open events with ref values, recovery hints, recent audited stash operations and the
  exact ack command.
- While latched, read-only investigation is allowed: `git reflog` (not `expire`/`delete`/`drop`/`write`,
  which rewrite the history the recovery hints point at), `git stash show` and `git branch --list <pattern>`.
- Snapshots of calls without a `tool_use_id` are keyed by the command, so parallel calls do not share one.
  A second legacy latch is archived next to the first instead of overwriting it.
- git-safety: never stash/reset/clean to get a clean tree (export HEAD instead), never assume a stash is
  yours, one mutating command per worktree, and the recovery procedure after a STOP.

### Fixed
- **Windows (git-bash + native Windows Python) is a supported environment.** On Windows `tests/run-all.sh`
  failed 12 checks before any Factory change. Causes and fixes:
  - `jq -r` writes CRLF there, so `$(jq -r ...)` loops kept a carriage return (`skills/foo<CR>/SKILL.md` does
    not exist): 10 skills-lint failures. New `scripts/lib/compat.sh` (sourced by every test suite and
    `check-registry.sh`) strips it on MSYS/MINGW/CYGWIN only, and adds `mktemp_win`, `is_abs`, `fwd`,
    `path_entry` and `dir_readonly`/`dir_writable` (an ACL, since `chmod 555` does nothing on NTFS).
  - Test scripts passed MSYS paths (`/c/...`, `/tmp/...`) to native Python, which cannot resolve them
    (`No module named 'fstate'`, fixture workspaces never found). `ROOT` now comes from `pwd -W` and temp dirs
    from `mktemp_win` (`C:/...`). `install-status.test.sh` also sets `USERPROFILE`: Windows Python ignores `HOME`.
  - Tests compared native Python paths (`C:\x`) as strings with bash paths (`C:/x`); they now normalise.
  - **Output encoding.** Python entry points wrote cp1252 into pipes (the snapshot showed `?` for `·`,
    `pin-plan.py` crashed on `→`), and 16 `subprocess` calls decoded git and jq output as cp1252. Every
    entry point now writes UTF-8 and every `text=True` call decodes UTF-8 (`errors="replace"`).
  - **Tool lookup ignored `PATHEXT`.** `context.which` and `devtools.which` looked for `python3`, not
    `python3.exe`, so the snapshot said `python3 MISSING` and listed every Python-based fast check as MISSING
    (not run) on Windows. Both now try the `PATHEXT` extensions.
  - **Every check that calls a Factory script failed on Windows.** `{plugin_root}` was substituted as
    `C:\...\rpg-factory`, and `run-checks.py` runs each check through `bash -c`, which drops the backslashes
    (`can't open file '...WorkspacesUnityIndierpg-factory\scripts\checks\sgl-determinism.py'`). It is
    substituted with forward slashes; `run-checks.test.sh` runs a `{plugin_root}` check with a backslash root.
    The guard's mode denial printed the same broken form (`bash C:/x\scripts\factory-context.sh`); it now
    prints a quoted forward-slash path (`git-guard.test.sh` checks it with a backslash root).
  - Registry fact `netcode-vendored-protobuf` probed with `strings`, which git-bash lacks; the probe is
    Python now (same value, 3.29.3). `ci-integration-on-pull-request` opens `ci.yml` as UTF-8.
- **`netcode-headless.sh` compiled nothing since Netcode's prediction tests need Shared.GameLogic.** The temp
  copy had no sibling `rpg-mmo-server`, so `Vec2`/`MapBounds` were missing and no `.trx` was produced. The check
  now does what Netcode CI does: Shared.GameLogic at the tag `package.json` pins (`x-manualDependencies`), taken
  with `git archive` from the workspace server repo into the temp dir, passed as `-p:SglDir` (352/352 run).
  The path is converted for Windows `dotnet.exe`: `cygpath -m` in git-bash, `wslpath -m` in WSL.
- **`package-ready.py` crashed in WSL and read a failed `git status` as a clean tree.** Over `/mnt/c` a cold
  index made `git status` exceed the 30 s timeout (traceback, no verdict). git calls now allow 120 s; a git
  timeout or a failing `git status` exits 2 with "readiness unknown" instead of continuing as if the tree were
  clean (`run-all.sh` covers the non-repo case).
- **Per-project MCP servers were never found on Windows.** `~/.claude.json` keys projects as `C:/x/y`; the
  probe looked up `C:\x\y`, so a project-scoped server such as `ai-game-developer` showed as not configured.
  Keys are compared normalised.
- `run-all.sh`: when live `pin-status` fails and the client's pin files hold uncommitted user changes (the
  local `file:` toggle), the committed HEAD is verified through a read-only export and the live check is
  reported as SKIP with that result, never as PASS. New `tests/compat.test.sh` covers the helpers, UTF-8
  output under a cp1252 stdout, the `PATHEXT` lookup and (by AST) that every `text=True` call decodes UTF-8.
  README has a Windows section with requirements and troubleshooting. A clean tree that fails still fails. `py_compile` now
  covers `scripts/lib/*.py`, reads UTF-8 and treats `SyntaxWarning` as an error.
- `unity-client-tech` cited the client `CLAUDE.md` by line numbers, which had drifted by about 15 lines.
  The citations now use section names.
- **Tripwire false STOPs across sessions.** The pre-command snapshot was one `pre.json` per session,
  consumed by whichever PostToolUse came next. A call denied by the guard (PreToolUse ran, PostToolUse
  never does) left its snapshot behind, and the next read-only command (`tripwire.py --status`) compared
  against it and was blamed for every ref another session had changed in between. Parallel calls of one
  session overwrote each other's snapshot. Snapshots are now per tool call (`pre-<tool_use_id>.json`),
  read only by the same call, written atomically, and pruned after 2 h when a call never completes.
  Without a `tool_use_id`, a snapshot of a different command is discarded.
- **Concurrent sessions.** A ref change is explained when another session's (or a parallel call's)
  completed command saw that same ref reach that same value while its own visible git ran in that repo,
  and its subcommands could make that change: `commit`/`merge`/`reset`/... move only the branch it had
  checked out, `branch`/`switch`/`checkout -b` create branches, `fetch`/`push` move remote-tracking refs,
  `stash` moves `refs/stash`. A read-only `git log`, a different ref, a tag or an unfinished call never
  explains anything, so a hidden reset of `develop` still trips while another session commits elsewhere.
- **Failing commands were never checked.** A Bash call that exits non-zero fires `PostToolUseFailure`,
  not `PostToolUse`; the tripwire now runs `--post` on both (`hooks.json`).
- **A worktree ref change was reported twice** (once per checkout sharing the refs); it is now reported
  once, under the worktree the command ran in.
- Cache writes that fail (Windows: `os.replace` onto a file another hook has open) are retried, never
  leave temp files, and never cost the comparison.
- **The printed ack command did not work.** `os.path.join` produced `C:/.../rpg-factory\scripts\tripwire.py`;
  bash dropped the backslashes and the user's ack silently failed. Every message (STOP, guard denials,
  file guard, SessionStart, doctor) now prints `fstate.ack_command()`: quoted, forward slashes.
- **`--ack` reported success it had not checked** and always exited 0. It now re-reads the state and
  prints `latch is now CLEAR` (exit 0) or `still LATCHED: <ids>` / `NOT cleared: <reason>` (exit 1;
  2 = invalid id). Repeating it is safe; unknown ids are reported.

### Security
- The guard now denies `tripwire.py --ack` to the agent at all times, not only while latched, so an agent
  cannot dismiss an incident another session raised a moment earlier. It matches any Python invocation of
  the script (options before it, `py -3`, `python -c ... run_path`, the path behind a variable) and no
  longer denies `grep -- --ack tripwire.py`.
- **The git guard ignored a workspace when `RPG_FACTORY_WORKSPACE` named another one.** The env root was tried
  before the cwd, so a second checkout of the workspace (or a `cd` into it) counted as "outside the workspace"
  and `git tag`, `push --tags` and `reset --hard` there passed without a decision. The nearest workspace above
  the cwd now wins and the env root is the fallback; after a `cd` the new directory's workspace applies.
- **`git -C <workspace repo> ...` from outside the workspace was not checked** when `RPG_FACTORY_WORKSPACE`
  was unset (`git -C .../rpg-mmo-server tag v1` from another directory was allowed). The workspace is now
  resolved from the directory git works in. Cases in `git-guard.test.sh` and `installed-safety.sh`.
- **The guard went silent on Windows path and encoding differences.** It compared paths as strings, so a
  payload cwd `C:/ws/x` did not match the workspace found as `C:\ws` and every command there was skipped; and a
  non-ASCII branch name (a UTF-8 byte cp1252 cannot decode) raised inside the guard, which counts as "no
  opinion". Paths are compared normalised and git output is decoded as UTF-8. New `git-guard.test.sh` cases
  cover both, the env-root case and `cd` between workspaces.

## [0.5.0] - 2026-10-01

### Security
- **Unity batch-mode test runs were ungated.** Factory treats Unity tests as external
  (HUMAN_REQUIRED), but the new tech skill and the client's Unity MCP reference offered a batchmode
  `-runTests` run as the agent's fallback when the Editor is closed. Nothing gated it, and the run opens
  the user's project, which can rewrite `packages-lock.json` and settings and triggers a reimport. The
  `unity-batch` human gate now also matches `-runTests` and the `_SampleBuild` build entries
  (`PlayClientBuilder`, `SampleBuilder`), which the remap had brought under that gate without its
  regex. The skills now hand the user the batchmode command instead of running it.

### Added
- **Dev tools per skill.** New registry `dev_tools[]` records the MCP servers, plugins and binaries
  the skills use: `unity-mcp`, `lsp-go`, `lsp-csharp`, `pg-aiguide`, `context-mode`, `codex`,
  `dotnet`, `go`, `protoc` and `docker`. Each entry has `probes`, `used_by` skills, `required` and a
  `fallback`. `scripts/lib/devtools.py` probes them: PATH, registry tools, TCP services, MCP server
  names (from workspace/repo `.mcp.json` and `~/.claude.json`) and enabled plugins. Config files are
  parsed in memory, but only server and plugin names leave the module. Env, headers and URLs are
  never returned, printed or stored.
- The snapshot prints a **Services** line and, per repo, **Tools for this change** (OK / DOWN /
  MISSING, with the fallback) for the routed skills. `/rpg-factory:doctor` has a **Dev tools**
  section that also lists skills missing a required tool.
- `check-registry.sh` and the schema validate `dev_tools`: fields, probe syntax, known tools,
  services and skills, and a fallback for every tool. They also accept the new skill kind
  `tech`, which needs `used_by` (repo or cross-repo skills) and must not own a module or contract.
  Known issues `no-csharp-lsp`,
  `golangci-lint-missing` and `gameserver-claude-stale` were added, and `client-claude-stale` was
  extended.
- Tests:
  - `tests/devtools.test.sh` adds scenarios over the real registry in a controlled environment: all
    tools OK; Unity Editor closed (`unity-mcp` DOWN, not MISSING or OK); no C# LSP (`lsp-csharp`
    MISSING with its fallback, doctor still exits 0); a malformed config with a planted secret
    surfaces no content or traceback.
  - `tests/facts.test.sh` proves a stale registry value is caught by re-probing the repo.
  - `tests/routing.test.sh` checks that `--lead <tech skill>` is rejected.
  - `tests/dogfood.sh` adds `tech-dotnet`, `tech-go` and `tech-unity`: real sessions must invoke the
    repo skill and its tech skill, and apply the reported tool fallback.
- `tests/devtools.test.sh` covers the probes, the snapshot, doctor, planted secrets that must never
  be printed, and malformed registry entries.
- **Tech skills** (new skill kind `tech`) explain how a technology works in this workspace. Repo
  skills keep where a change goes and which rules apply. Tech skills own no module, so they are never
  lead, leg or follow-up. `resolve.jq` emits `routing.tech`: the tech skills used by a working skill
  (lead, co-lead or leg). The snapshot prints it in the routing line and the Next hint.
  - `dotnet-gameserver` (used by server-realtime, wire-contract and measure): tick order (the tick
    gathers and connection write tasks encode/send), rates, ECS world locking, zero-alloc idioms and
    what each guard covers, SGL compiler limits, the Net layer, xUnit idioms and filters, NativeAOT.
  - `go-backend` (used by server-services and wire-contract): six modules that `replace` shared
    without go.work, gateway entry points, storage seams, test doubles (`miniredis.RunT`, httptest,
    embedded `runtime.NakamaModule`), single-test commands, and when the dotnet interop tests skip.
  - `unity-client-tech` (used by client-integration, unity-package and pin-bump): Entities system
    install and world lifecycle, Task vs UniTask boundaries, main-thread rules, VContainer, asmdef and
    test-assembly rules, domain reload, WebGL limits, single tests through Unity MCP `tests-run`
    filters (with the Editor closed, the batchmode command is handed to the user).
- Every repo, cross-repo and tech skill has a `## Tools` section that names its `dev_tools` and the
  step each one is for. `tests/skills-lint.sh` enforces it in both directions: each `used_by` skill
  names the tool, and each tool a bullet leads with is registered for that skill. Tech skills need
  the sections Architecture / Idioms / Pitfalls / Testing / Tools, and every `used_by` skill names
  `rpg-factory:<tech>`.
- Routing properties P7 (a tech skill is never routed) and P8 (`routing.tech` only lists skills
  whose `used_by` is a working skill), plus 7 task scenarios in `tests/routing.test.sh`.
- Registry facts with probes: `sgl-langversion`, `sgl-target-frameworks`, `tick-rates-default`,
  `aoi-parallel-gather-min-viewers`, `nakama-version`, `enter-playmode-options`.

### Changed
- `server-realtime`, `server-services` and `client-integration` were deepened and point to their tech
  skill.
  - server-realtime names `SnapshotAllocationTests` (snapshot path only) and the single-test filter,
    and cites ADR-7/8/13/22/25.
  - server-services cites ADR-1/4/6 and adds an evidence rule: skipped interop tests are NOT_RUN,
    never PASS.
  - client-integration is trimmed to 149 lines, covers `_SampleBuild`, adds CI `01-ci-docs.yml`
    (its green result is not evidence) and `02-package-pins.yml`, and its Unity MCP reference gains
    the `tests-run` filters.
- `server-ops` is trimmed to about 150 lines and gains ADR-17 (one replica; `Recreate` on the
  `hostPort` workloads).
- Registry modules:
  - `Assets/_SampleBuild/` maps to `client.buildscripts`, which brings its build gates (it used to
    fall through to `client.unity-assets`).
  - `client.ui` now describes what it actually holds (the theme). The HUD UXML/USS live in
    `client.scripts`, which gains `docs/UI-ARCHITECTURE.md` and the `ci-uxml-drift` external check.
- Known issue `dotnet-wsl` is corrected: a Linux SDK may exist off PATH at `~/.dotnet/dotnet`, and the
  Go interop tests use it.

### Fixed
- **Tech skills were not loaded for "how does it work / how do I test it" questions.** A real session
  routed to `server-realtime` but never invoked `dotnet-gameserver`: the pointer sat only in the
  "place the code" step and said "read", not "invoke". The repo skill, `factory-core` and the
  snapshot's Next line now give one rule: the lead invokes the tech skill (Skill tool) before
  implementing, debugging or reviewing code, or answering how it works or how to test it, in every
  mode. A tech skill is supporting context, not a follow-up.
- **A session could use a tech skill as the owner.** In one of three real Go sessions the model
  invoked `go-backend` and `dotnet-gameserver` but never the routed lead or co-lead, so no rules, gates
  or validation were loaded. Every tech skill now opens with a "Supporting skill, never the owner:
  invoke the lead first" guard (lint-enforced). `tests/dogfood.sh` fails any session that invokes a
  tech skill before an owning skill.
- `/rpg-factory:status` answers dropped each Pending item's owning skill (`[unity-package]`), which is
  the point of the report. On this branch the installed and A/B sessions failed 3/3, against 2/2 on 0.4.0,
  although the status output was byte-identical. The command now says to keep the brackets as printed
  (3/3 after the fix).
- The `factory-core` Skills table let a session name the lead by lookup and stop. It is now marked
  orientation-only: run Route and invoke the lead before answering, with tech skills after the lead.
  Known residual: `netcode-change` still sometimes names the lead without invoking it, at the 0.4.0
  rate (0.4.0 passed 5 of 6 sessions, this release 6 of 7).
- `--explain` said a tech skill was "not selected - no touched path maps to its modules ()". It now
  reports `tech (supporting)` with the skill that uses it, or names its users when none works on the
  change.
- The git guard denied `git tag --sort=...` / `--format=...` (a read) as tag creation. Listing
  options in their `=` form are now a listing. A tag name after them, or a separated `--sort <value>`,
  is still denied.
- `go-backend`: only the `*_test.go` files of `integration_test` carry the build tag; the
  `mock_client.go` helper does not.
- `server-ops` reference: the Nakama plugin is built by `deploy/nakama-plugin.Dockerfile`.
  `docker/Dockerfile.nakama-plugin` is not referenced by anything.
- **The `services.unity-mcp` probe never ran.** Skills branch on "the snapshot shows `unity-mcp`
  reachable", but no script read `services`. The snapshot now probes each service over TCP
  (0.3 s timeout) and reports it in markdown and `--json`.

### Documentation
- README: plugin hooks bind at session start. A session running before rpg-factory was installed or
  enabled has no Factory hooks at all (compaction does not load them); start or resume a session, and
  check with `/rpg-factory:doctor`. Found in the post-release audit of the v0.4.0 tagging session;
  fresh, resumed and `--plugin-dir` sessions were verified to deny tag creation and enforce modes.

## [0.4.0] - 2026-09-30

### Security
- **GitHub mutations were unguarded.** `gh api graphql` could create tags (`createRef refs/tags/*`,
  `createRelease`), `gh repo delete` and branch-protection writes were allowed. The guard now applies a
  structural gh policy: the API method is derived the way gh does (`-X`, else POST when fields or
  `--input` are given); reads pass; tag/release creation (REST and GraphQL) and repository
  deletion/archival are denied; every other remote mutation (branch protection, rulesets, repo
  settings, secrets, variables, workflows, runs, PR/issue changes, GraphQL mutations or queries from a
  file) asks. `gh` commands naming a workspace repo are checked even outside the workspace. These
  changes are remote-only, so the tripwire cannot see them - the guard is the only control.
- Protected refs and remotes: `git pull` without `--ff-only` on a protected branch, renaming or
  deleting a protected branch, `fetch <src>:<dst>` into local branches (forced or not; into tag refs =
  deny), `remote add/set-url/remove/rename`, `config` writes to aliases / remote URLs / `insteadOf` /
  `hooksPath` / credential helpers, `symbolic-ref` writes, `submodule add/set-url` now ask.
- **File tools were unguarded.** New `scripts/file-guard.py` (PreToolUse
  `Write|Edit|MultiEdit|NotebookEdit|Read`): writes into embedded package clones, submodule content,
  registry generated paths, the user's baseline files or secrets ask; secret reads ask; writes while the
  tripwire is latched or while a read-only mode is declared are denied. MCP tools are not inspected
  (documented; the `unity-asset-edit` gate remains the control).
- **A tripwire STOP vanished with its session.** The latch is now also written per workspace in the
  persistent state root: a crashed or closed session leaves the next one latched, SessionStart says
  why, and only the user's `--ack` clears it (the ack now rebuilds the baseline immediately).

### Fixed
- **State paths could be relative.** With `TMPDIR` empty (as in some shells), relative or invalid, the
  tripwire and runner wrote `rpg-factory/<session>/` into the current directory. All state now resolves
  through `scripts/lib/fstate.py` (always absolute; scratch under a usable `$TMPDIR` or `/tmp`,
  persistent state under `$XDG_STATE_HOME/rpg-factory` / `~/.local/state/rpg-factory`);
  `netcode-headless.sh` rejects a relative/invalid `TMPDIR`. Read paths no longer create directories.
- **The first dirty file of each repo was not protected.** The tripwire baseline stripped the first
  porcelain line and lost the first character of its path (and mangled quoted paths); it now parses
  NUL-separated porcelain.
- `is_read_only` treated `2>/dev/null` / `2>&1` as writes.
- Command `!` lines must match their own `allowed-tools` pattern or Claude Code refuses them (found by
  installed dogfood; now linted). factory-core asks for Factory script paths exactly as printed
  (absolute): relative paths hit permission prompts, and allow-listing relative paths would auto-approve
  any repo's own `rpg-factory/scripts/`.
- CHANGELOG 0.3.0 said 16 human gates; the registry has 15.

### Added
- **Execution modes** `analyze`, `plan`, `implement`, `validate`, `review`, `resume`: declared with
  `factory-context.sh --mode <m>` (printed in the snapshot), recorded per session by the guard and
  enforced by both guards (analyze/plan/review read-only; validate only `run-checks.py`). factory-core
  owns the mode table; every skill honours it. A PreToolUse(Skill) hook also records an explicit mode
  from Factory skill arguments ("plan only", "mode: validate") - installed dogfood showed sessions that
  never ran the Route command. Evidence: in v0.3.0 dogfood every missed lead invocation came from a
  plan-only prompt.
- **Commands** `/rpg-factory:status`, `/rpg-factory:route`, `/rpg-factory:check`, `/rpg-factory:doctor`
  (one validating dispatcher, `scripts/factory-cmd.py`). No `ack` command: clearing a latch stays a
  user action.
- **Tree-bound evidence.** `run-checks.py` stores each executed check with the identity of the tree it
  ran on (HEAD + diff and untracked files in the check's directory and its module's same-repo
  dependencies + the check definition) and its full log; `--status` grades the declared checks against
  the current tree without running anything: **STALE** after any relevant change, **NOT_RUN** when never
  executed.
- `factory-status.py`: package-CI pins from contract watchers (the real UnityDots CI -> Netcode v0.41.0
  vs the client's v0.45.0 drift is now pending), remote-knowledge **freshness** per repo (never fetches;
  prints the `git fetch` when older than 24 h), uncommitted work per repo, embedded clones, and stored
  evidence graded against the current tree. Status scans run in parallel.
- Workspace model: registry `repos.<key>.embedded_clones` (the client's gitignored
  `Packages/com.cuvara.*`): tripwire fingerprints them and samples their dirty files before/after each
  command (the user's own concurrent edits are not flagged); a snapshot run inside one says so
  instead of silently showing the canonical repos.
- Registry: contract `transport-security` (driver server-ops; TLS / `GAMESERVER_SEALED` switches vs the
  server, Netcode, client-pin and smoketest/verify capabilities - history `ed090ab`, `437a3db`);
  `package-pins` watchers; modules `server.bench` (measure leads benchmark harnesses) and
  `netcode.measurement` (measure co-leads).
- Skills: server-ops rollout order for security switches; unity-package package-CI pins;
  client-integration Unity-MCP hand-off (`references/unity-mcp.md`); measure ownership; factory-core
  game-ai-workflows hand-off.
- Tests: guard 252 (GitHub, refs/remotes/config, modes), tripwire 40, file guard 29, commands 30,
  run-checks 35 (evidence), factory-status 22, worktree 13 (clones), routing 52 (transport-security,
  bench, follow-up noise), installed-safety 83; dogfood gains analyze/plan/validate-only and command
  scenarios (13 real sessions against the installed plugin).

### Changed
- Performance (same harness, /mnt/c): SessionStart baseline ~12 s (was ~14 s; repos and clones now scanned in
  parallel), read-only command hooks ~0.19 s (was ~0.18 s), state-changing ~0.8 s (was ~0.9 s; signatures and
  clone samples in parallel), factory-status ~4.3 s (was ~4.8 s; parallel scans, one git grep), file guard
  ~0.09 s per file-tool call (new). Plugin scripts append (not prepend) their paths to sys.path so stdlib
  imports never stat /mnt/c first.
- `git pull` on a protected branch now asks unless `--ff-only`.
- Routing: a cross-repo dependent adds only its module's primary owner as a follow-up (a secondary owner
  such as `measure` on `netcode.measurement` is not downstream work of a wire change). Replay of all 358
  post-split commits against v0.3.0: 0 lead changes; co-leads/follow-ups differ only where intended
  (measure on 26 Netcode measurement commits, transport-security on 5 TLS commits).

## [0.3.0] - 2026-09-30

### Fixed
- **Install state was invisible.** `claude plugin list` still reported 0.1.0 while the source was
  0.2.0, and nothing checked what sessions load. `scripts/install-status.py` reports the load mode
  and state (CURRENT / STALE / CONTENT_MISMATCH / RESTART_REQUIRED / NOT_INSTALLED); a SessionStart
  hook warns when not CURRENT and the snapshot header shows the runtime version and load path.
  Observed with Claude Code 2.1.280: a **directory** marketplace (this workspace) loads the plugin
  in place from the marketplace directory - the version-keyed cache copy is only used by other
  marketplace types, where `claude plugin update` is a no-op until the version changes. README
  "Updating" documents both; the v0.3 roadmap's premise that v0.2.0 sessions ran v0.1.0 content is
  not supported by this evidence (only the install record was stale).
- **Guard: `xargs` tag creation** (`echo v9 | xargs git tag`) was allowed because the peeled command
  looked like a tag listing; xargs input is now modelled as an extra argument (deny). Found by
  `tests/installed-safety.sh`; the tripwire had caught it after the fact.
- **Guard bypasses.** The guard now covers the PowerShell tool (matcher `Bash|PowerShell`,
  PowerShell tokenizer with backtick escapes and the `&` call operator) and expands commands before
  classifying: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`, `xargs`,
  `find -exec`), nested shells (`bash/sh -c`, `eval`, `cmd /c`, `powershell -c`), repo git aliases;
  `$VAR` / `$(...)` as the program and interpreter one-liners running git ask.
- Guard: `gh api .../git/refs|tags` and `gh release create` are denied; `merge`, `cherry-pick`,
  `revert`, `am`, `pull --rebase`, `reset <commit>` on protected branches ask; `checkout -B`,
  `switch -C`, `branch -f`, `update-ref`, `gc --prune`, `reflog expire`, `prune` ask. Worktrees use
  their main checkout's protected branches.
- Routing: `backend/content/` was mapped by two modules (winner depended on registry order).

### Added
- **Tripwire** (`scripts/tripwire.py`, SessionStart/PreToolUse/PostToolUse): detects git state
  changes the guard could not see (tags, pushes, branch/HEAD/stash moves without a visible git
  command in that repo, modified or deleted baseline files, moved user submodules, changed dirty
  files inside submodules). Emits "STOP - rpg-factory tripwire" and latches the session (the guard
  denies non-read-only commands) until `tripwire.py --ack`.
- **Deterministic routing**: one primary lead (cross-repo driver > repo-kind driver on a touched
  source > primary owner > secondary owner > `skills.<name>.order`), ordered co-leads, AMBIGUOUS,
  `--lead` override (validated) and `--explain`. `.meta` paths route like their asset; unmapped
  files route to per-repo fallback modules `<repo>.root`.
- **Worktree-aware context**: the snapshot resolves the repo or worktree from the current directory.
- **Check runner** `scripts/run-checks.py`: runs the registry checks for the touched modules and
  grades them PASS / FAIL / BLOCKED / NOT_AVAILABLE / HUMAN_REQUIRED / SKIPPED with per-check
  parsers (`go-test`, `dotnet-test`, `exit`, `regex:`), `needs` dependencies, extended-tier approval
  (`--approve`), pollution detection (before/after `git status`) and an evidence JSON.
- **Derived cross-repo status** `scripts/factory-status.py`: contract consistency, the wire rollout
  chain (server bindings → Netcode copy → Netcode release → client pin), package release state
  (released / unreleased changes / READY_TO_TAG), pins vs latest tags, CI SGL watchers,
  unity-build-workflows refs and gitlink (`--remote`), in-flight `<type>/<area>/<topic>` branches
  linked across repos, and pending items with their owning skill. No stored state.
- Registry schema v3: `skills.order`, fallback modules, check `parser` / `needs`, `facts[]` with
  read-only probe commands (re-verified by `tests/facts.test.sh`), 15 human gates (incl. `sgl-release`; this entry originally said 16).
- `VERSION` file; run-all checks VERSION == plugin.json == marketplace == CHANGELOG section.
- Tests: guard bypass matrix (145 cases incl. PowerShell and wrappers), tripwire simulations,
  routing properties over real history, worktree, check runner, factory-status rollout fixtures,
  install-status (both load modes), facts; `tests/installed-safety.sh` drives the installed hooks
  against a disposable workspace (63 cases incl. tripwire STOP and latch; part of
  `run-all --release`); `tests/dogfood.sh --installed` runs headless sessions against the installed
  plugin and asserts the loaded source/version/path and the invoked skills.
- `--paths` normalisation: repo-prefixed (`rpg-mmo-server/backend/...`), absolute, comma-joined and
  glob paths resolve to repo-relative files (they used to fall to the repo fallback and lose routing).
  factory-core routes by the files the task writes (a benchmark writes the harness/BENCHMARK.md).
- Cross-repo tasks have one lead: a downstream contract end (e.g. the client's `PartyService.cs` for
  `nakama-rpc`) prints a **Cross-repo** line naming the upstream driver; factory-core says so.
- Snapshot routing prints an explicit "Next: invoke the Skill tool with the lead" line (installed
  dogfood showed sessions naming the lead without invoking it).

### Changed
- Snapshot diet: compact output filtered to the touched repos, toolchain probed lazily
  (all repos 16.1 KB / 15.3 s → 3.3 KB / 4.9 s; one repo with `--paths` 13.9 KB → 2.4 KB).
- `factory-core`: Resume step (factory-status), routing with lead/co-leads, validation through the
  runner, tripwire STOP rule, same branch topic across repos, plugin boundary clause
  (game-ai-workflows, web-game-factory).
- `pin-bump`: also moves the unity-build-workflows toolkit (submodule gitlink and reusable-workflow
  `@vN` refs); submodule bumps route to it.
- `wire-contract`: resumes at the first incomplete rollout stage; compatibility, rollout order and
  rollback table; `--min-protocol-version` on gateway and game server.
- `client-integration`: package-version awareness (codes against the pinned tag) and hand-off table.
- `server-realtime` trimmed; volatile values in skills replaced by registry facts;
  `skills-lint` flags rule sentences copied from the registry and missing plugin boundaries.

## [0.2.0] - 2026-09-30

### Added
- Eight specialised skills on top of Factory Core: cross-repo drivers `wire-contract`, `pin-bump`,
  `measure`; repo skills `server-realtime`, `server-services`, `server-ops`, `unity-package`,
  `client-integration`. Each follows `references/skill-contract.md` (Core first, registry facts,
  validation delta, generated paths, human gates, review checklist, report additions).
- Registry schema v2: repos `netcode`, `unitydots`, `uitoolkit`; 52 modules (deploy split into
  k8s/compose/monitoring/db, plus persistence, content, measurement-docs, wire-conformance, and 17
  package modules); `skills`; 9 `contracts` (wire-generated, protocol-version, join-token,
  redis-server-registry, nakama-rpc, sgl-pin, package-pins, gamestate-migrations, server-knobs with a
  `co_edit` clause); 15 `human_gates`; module `skills`/`gates`; 26 verified `known_issues`.
- `factory-context.sh`: cross-repo dependents (advisory), suggested skills with roles
  (lead / leg / follow-up), touched contracts with other ends / upstream / watchers, human gates,
  known issues; all five repos in the default snapshot.
- Check scripts: `pin-status.py`, `pin-plan.py` (incl. `--client-ref` historical replay),
  `wire-parity.sh`, `netcode-headless.sh` (temp-copy test run), `package-ready.py`.
- Tests: `tests/routing.test.sh` (25 task scenarios + 13 real historical commits replayed
  read-only), `tests/skills-lint.sh` (skill contract), JSON Schema validation in
  `check-registry.sh`; `tests/dogfood.sh` (opt-in headless sessions asserting the invoked skills -
  8 scenarios verified with sonnet).
- Evals: routing cases for server-realtime, server-ops, unity-package, server-services, plus
  wire-contract / pin-bump graders.

### Changed
- Contributor instructions moved from `CLAUDE.md` to `.claude/CLAUDE.md` (a root CLAUDE.md is not
  plugin context and fails `claude plugin validate --strict`).
- Plugin/marketplace descriptions describe the full workflow set.
- Git guard hardened: one invalid `human_gates` regex no longer disables the whole guard (each gate
  and the git evaluation fail independently).
- Git guard: creating, deleting or pushing tags is now **denied** (agents never tag); commands
  matching registry `human_gates[].match` (kubectl/helm/ssh, workflow dispatch, secrets,
  toggle-packages.sh, local stack) now ask. Protected branches come from each repo's registry entry.
- `factory-core`: new Route step (invoke the suggested lead skill), skill map, updated references.
- `server.gameserver-dotnet` knob rule corrected: passthrough is enforced against compose and fleet
  manifests (ComposeEnvPassthroughTests / FleetEnvPassthroughTests), not `20-configmaps.yaml`.

## [0.1.0] - 2026-09-30

### Added
- Factory Core v1 plugin (`rpg-factory`) with single-plugin marketplace.
- `factory-core` skill: workflow (scope, baseline, branch, plan, implement, obligations,
  validate, verify, review, report), live snapshot injection, global rules from the registry,
  and references for repos, validation, git safety, report template and skill contract.
- `registry.json` (27 modules across rpg-mmo-server and IndieRPGMMOAdventure) with
  `docs/registry.schema.json`.
- `scripts/factory-context.sh`: read-only live snapshot (branch, working tree, branch diff,
  submodules, touched modules and dependents, checks by tier, obligations, toolchain with
  `dotnet` -> `dotnet.exe` fallback, Unity MCP reachability); `--paths` and `--json` modes.
- `scripts/git-guard.py` PreToolUse(Bash) hook asking before destructive or high-impact git.
- `scripts/check-registry.sh`, `scripts/checks/unity-package-pins.py`.
- `tests/run-all.sh`, `tests/git-guard.test.sh`, and three `claude plugin eval` smoke cases.
