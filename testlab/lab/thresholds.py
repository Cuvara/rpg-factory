"""Every limit the test lab grades against, with where it comes from: testlab/docs/THRESHOLDS.md.

The document is generated from this module and the scenario files (`testlab.py thresholds --write`),
and a unit test fails when it is out of date, so a new or changed limit cannot go undocumented.
A source is either a derivation (configuration, content, a measurement with its run ids) or
"policy, unvalidated": a reviewable choice nobody has measured against.
"""

from __future__ import annotations

import json

from . import hostguard, scenarios

POLICY = "policy, unvalidated"

# (check, parameter) -> source. Parameters a scenario sets; defaults are in CHECK_DEFAULTS.
SOURCES = {
    ("position_divergence", "p95"): f"{POLICY} (remote 0.35, local 0.5)",
    ("position_divergence", "max"): f"{POLICY} (remote 1.0, local 1.5)",
    ("position_divergence", "skip_first_s"): "S11: end of the restart grace window (scenario timing)",
    ("render_jumps", "max_local"): f"{POLICY}: any local major jump is a defect",
    ("render_jumps", "max_remote_per_client_min"): f"{POLICY} (2.0); S14: 0, the only teleports are the scripted respawns",
    ("render_jumps", "skip_first_s"): "S11: end of the restart grace window",
    ("snapshot_cadence", "max_gap_ms"): POLICY,
    ("snapshot_cadence", "expected_hz"): "S12: the configured SIM_WORLD_HZ (15)",
    ("snapshot_cadence", "exclude_s"): "scenario timing: S11 restart grace 20-40 s (estimate, " + POLICY + "); "
                                       "S13 stall + 1 s (500 ms) and + 1 s (2000 ms)",
    ("snapshot_update_gap", "max_gap_ms"): POLICY,
    ("frame_time", "p95_ms"): f"{POLICY}: 33.4 ms = 30 fps on a shared host",
    ("frame_time", "p99_ms"): POLICY,
    ("kcp_health", "max_sessions_closed"): "S08: 2 = the killed client's session plus its relaunch; S08G: 1 = the "
                                           "graceful leave; S18: 0, packet loss must not end a session",
    ("kcp_health", "max_dropped"): "S18: null = inbound datagram drops are reported, not judged (the impairment drops "
                                   "datagrams on purpose; sessions closed and rejected are still judged)",
    ("memory_growth", "max_server_mib_per_min"): f"{POLICY} (S09 2.0; S07/S07P 20, informational: the bot ramp "
                                                 "allocates by design)",
    ("entity_stability", "max_growth_ratio"): POLICY,
    ("entity_stability", "skip_first_s"): f"{POLICY}: population fill-up",
    ("enemy_crowding", "overlap_radius"): "half of the server's enemy separation radius (enemy_ai separation=0.8)",
    ("enemy_crowding", "max_overlap_ratio"): POLICY,
    ("enemy_crowding", "max_share_when_spread"): f"{POLICY}; INFO unless share_is_failure (rpg-mmo-server#469)",
    ("enemy_crowding", "spread_distance"): POLICY,
    ("enemy_crowding", "skip_first_s"): f"{POLICY}: first wave settling",
    ("enemy_crowding", "overlap_is_failure"): "scenario decision: separation is on (#469)",
    ("enemy_crowding", "require_spread"): "scenario decision: S05 moves players apart on purpose",
    ("enemy_pursuit", "min_pursuit_ratio"): POLICY,
    ("enemy_pursuit", "max_settled_speed"): POLICY,
    ("enemy_server_speed", "speed"): "server default GAMESERVER_ENEMY_SPEED (/status enemy_ai speed=2.5)",
    ("enemy_render_speed", "speed"): "server default GAMESERVER_ENEMY_SPEED (/status enemy_ai speed=2.5)",
    ("spawn_overlap", "min_distance"): f"{POLICY} (rpg-mmo-server#469 report)",
    ("inputs_consumed", "min_cos"): POLICY,
    ("inputs_consumed", "min_distance_fraction"): f"{POLICY}: obstacles and stops excepted",
    ("trajectory_bound", "max"): "dev_arena north wall at y 19..20 (content/maps/dev_arena.json)",
    ("trajectory_bound", "reach_at_least"): f"{POLICY}: close enough to the wall to prove contact",
    ("trajectory_bound", "t0"): "scenario timing", ("trajectory_bound", "t1"): "scenario timing",
    ("combat_effect", "min_damaged"): POLICY,
    ("graceful_leave", "leave_timeout_s"): f"{POLICY}: far below the 60 s KCP idle timeout (KcpTuning.IdleTimeoutMs)",
    ("prediction_bound", "max_unexplained"): "S14: 0, enemies are off so only the scripted respawns may snap",
    ("prediction_bound", "expected_explained"): "S14: one per scripted kill",
    ("clients_in_world", "reentered_after_s"): "S11: the restart instant",
    ("cross_client_convergence", "skip_first_s"): "S11: end of the restart grace window",
    ("tick_adoption", "exclude_s"): "S11: restart grace window",
    ("render_freshness", "exclude_s"): "S11: restart grace window",
    ("players_online", "expected"): "S08G: one client left",
    # S16 malformed input / S17 churn (rawprobe.ndjson). malformed_input rules are looked up per case
    # first ("<case>.<param>"), then by parameter.
    ("server_alive", "max_failed_probes"): "definition: every /status probe of the run is answered",
    ("server_alive", "max_gap_s"): f"{POLICY}: 5 probe periods of the 1 Hz /status sampler",
    ("malformed_input", "expect"): "contract: WireProtocol.DecodeAsync / DecodeBody throw on a bad length or body "
                                   "(the read loop ends and the connection closes); OnMessageReceived ignores an "
                                   "undefined type; InputHandler refuses what ValidationLogic forbids",
    ("malformed_input", "within_s"): f"{POLICY}: a close from the read loop is immediate (<= 0.02 s in the first "
                                     "S16 runs); 3 s is 12 polls of the 4 Hz /status reader",
    ("malformed_input", "truncated_frame.within_s"): "Connection.HeartbeatLoopAsync: PingInterval 10 s, closes at the "
                                                     "first tick where the last pong is older than PongTimeout 30 s = "
                                                     "tick 4 = 40 s after the connection starts (the frame is sent "
                                                     "after the join, so <= 40 s after the send), + 5 s slack",
    ("malformed_input", "min_snapshots"): f"{POLICY}: a stays_open offender must keep receiving; 5 snapshots is a third "
                                          "of a second at the 15 Hz world rate",
    ("malformed_input", "rejections"): "move_out_of_range: 3 inputs of magnitude 1.6, 50 and 1e6, spaced 0.4 s (inputs "
                                       "inside one drain coalesce and only the last is judged), each above "
                                       "GameConstants.MaxInputMagnitude 1.5; attack_out_of_range and ability_cooldown: "
                                       "at least one refusal of the reason",
    ("malformed_input", "unknown_type.rejections"): "rpg-mmo-server #490 (76aa973): gameserver_messages_rejected_total{reason=unknown_type} "
                                                    "counts a well-formed message whose type is undefined; the scenario sends one",
    ("malformed_input", "max_displacement"): "definition: a server position never moves faster than the entity's speed "
                                             "(+ 0.5 slack); a teleport is not expressible, positions are server-side",
    ("malformed_input", "beyond_attack_range"): "definition: target farther than GameConstants.AttackRange (read from source)",
    ("malformed_input", "target_hp_unchanged"): "definition: a refused attack does no damage",
    ("churn_cycles", "cycles"): "scenario decision: about 10 cycles (5 drops, 5 graceful leaves)",
    ("churn_cycles", "max_join_s"): f"{POLICY}: a join is one gateway round trip plus the KCP handshake (about 0.03 s on "
                                    "the scratch stack)",
    ("churn_ghosts", "leave_within_s"): f"{POLICY}: the graceful_leave bound (5 s), far below the 60 s KCP idle timeout",
    ("churn_ghosts", "drop_gone_within_s"): "Connection.HeartbeatLoopAsync: PingInterval 10 s + PongTimeout 30 s to notice "
                                            "a silent peer, + constants.EntityHoldTTL 30 s (map hold), + 5 s slack",
    ("player_count_baseline", "max_extra"): "definition: the two churn users are the only extra players",
    ("player_count_baseline", "leave_within_s"): "same instant as churn_ghosts (quiet window start)",
    ("player_count_baseline", "drop_gone_within_s"): "same instant as churn_ghosts (quiet window start)",
    ("players_online", "mode"): "scenario decision: the end of the run",
    # S18 packet impairment (netem.ndjson). The profile itself is in the "Impairment profiles" section.
    ("netem_cleanup", "max_late_s"): f"{POLICY}: the removal is 3 tc commands plus a verification, 1-2 s each through WSL; "
                                     "10 s is several times that",
    ("netem_retransmits", "min_rise"): "derivation: 15 Hz snapshots x 2 clients x 60 s = 1800 server->client segments x 5 % "
                                       "loss = about 90 resent; 30 is a third of that, and a quiet host adds about 0.2/s "
                                       "when clean (F8A control run, 22 in 125 s), i.e. 12 per 60 s, so 30 is not reachable "
                                       "by host noise alone",
    ("netem_retransmits", "rate_ratio"): f"{POLICY}: the impaired rate must be a multiple of the clean one, so a noisy host "
                                         "cannot fake the effect",
    ("netem_retransmits", "baseline_floor_per_s"): f"{POLICY}: a zero-retransmit baseline would make any rate pass the ratio; "
                                                   "0.1/s is half the clean-run noise seen in F8A",
    ("netem_retransmits", "recovery_max_ratio"): f"{POLICY}: after the removal the rate must fall to at most half the impaired "
                                                 "rate (the removal returned and the backlog drained)",
    ("netem_snapshots", "max_gap_ms"): f"baseline and recovery: the lab-wide snapshot_cadence limit ({POLICY})",
    ("netem_snapshots", "impaired_max_gap_ms"): "derivation, not a measurement: a lost KCP segment is resent after RTO "
                                                "(srtt 80 ms + 4 x rttvar about 100 ms = about 180 ms), a second loss of the "
                                                "same segment after 1.5 x RTO (270 ms), a third after 2.25 x RTO (405 ms): "
                                                "three consecutive losses = 855 ms + 40 ms one-way + sampling = about 0.9 s, "
                                                "probability 1.25e-4 per segment; 1000 ms is also the longest freeze "
                                                "this lab will call recoverable",
    ("netem_snapshots", "impaired_p99_gap_ms"): "derivation: 5 % loss is above 1 %, so the 99th-percentile gap lies in the "
                                                "single-loss class: RTO about 180 ms + 40 ms one-way + jitter 20 ms = about "
                                                "240 ms; 400 ms keeps the double-loss tail (0.25 % of segments) out of it",
    ("netem_snapshots", "rate_tolerance"): f"same as snapshot_cadence ({POLICY}); CORE-BASELINE-V1.md measured "
                                           "snapshotsApplied unchanged (14.8/s) at 40 ms +/- 60 ms",
    ("netem_snapshots", "recovery_settle_s"): f"{POLICY}: the netem queue holds at most delay + jitter = 60 ms and the removal "
                                              "flushes it; 2 s covers one RTO round of the KCP backlog",
    ("netem_prediction", "max_snaps_per_min"): "the lab's prediction_bound (4.0): measured fixed builds <= 2.0, pre-fix >= 7.5; "
                                               "not widened for impairment",
    ("netem_prediction", "max_correction"): f"{POLICY}: the local position_divergence max of S03/S06/S10 (1.5); the largest "
                                            "correction seen clean is 0.17 (S16 82bn)",
    ("netem_prediction", "max_keyframe_ratio"): f"{POLICY}: a resync storm would be many times the periodic keyframe rate; "
                                                "2x the clean rate of the same run",
    ("netem_prediction", "recovery_settle_s"): "same as netem_snapshots",
    ("netem_convergence", "converge_within_s"): f"{POLICY}: expected well under 3 s (interpolation cover 150 ms, KCP backlog a "
                                                "few RTOs, smoothing); 10 s is three times that",
    ("netem_convergence", "p95"): f"inherited from remote position_divergence ({POLICY})",
    ("netem_convergence", "max"): f"inherited from remote position_divergence ({POLICY})",
}
NETEM_PROFILE_SOURCE = (
    "delay 40 ms: the one-way latency CORE-BASELINE-V1.md measured a real Unity client at (section \"The client survives a "
    "worse link than most players will have\"); jitter +/- 20 ms: inside the +/- 60 ms the client held there (resyncs, "
    "rejected, dropped and clamped all 0) and the +/- 25 ms where tiered replication still held its cover, so a pass is "
    "expected, not a stretch; loss 5 %: above the 1-2 % of a typical mobile link and below the 10 % where a reliable "
    "transport mostly stalls; CORE-BASELINE-V1.md has no loss measurement at all (this is the first), so it is "
    f"{POLICY}; reorder 1 %: the value of the brief, on top of the reordering that uniform jitter above the 67 ms "
    "snapshot spacing already causes. Phases: 30 s baseline and 30 s recovery as briefed; 60 s impaired so about 900 "
    "snapshot segments per client meet 5 % loss (about 45 losses, enough for the loss share to be tested at 3 sigma)")

# Parameters that are not limits (identifiers, switches, documentation).
NOT_LIMITS = {"local", "types", "client", "axis", "rationale", "expected_outcomes", "expect_positive",
              "expect_zero", "require_removal", "informational"}

# (check, parameter, default, source): the limits a check applies when the scenario does not set them.
CHECK_DEFAULTS = [
    ("snapshot_cadence", "rate_tolerance", 0.2, POLICY),
    ("snapshot_cadence", "max_gap_ms", 250, POLICY),
    ("server_tick", "min_rate_ratio", 0.98, POLICY),
    ("server_tick", "p99_budget_ratio", 1.0, "tick budget = 1 / SIM_CRITICAL_HZ (definition)"),
    ("kcp_health", "max_dropped", 0, f"{POLICY}: a drop inside the window is lost traffic"),
    ("position_divergence", "window_before_s / after_s", "0.6/0.15 remote, 0.3/0.6 local",
     f"{POLICY}: interpolation delay (TargetDelay 100 ms) plus probe spacing"),
    ("position_divergence", "min_samples", 50, POLICY),
    ("render_jumps", "major_step", 1.0, POLICY),
    ("render_jumps", "max_local_minor / remote_minor per client-min", 30.0, POLICY),
    ("render jump detector", "max_speed / factor / slack", "6.0 / 3.0 / 0.25",
     "max_speed above the player speed 5 u/s (client DotsWorldBridge); factor and slack " + POLICY),
    ("host_stalls", "frame / window", "250 ms / 250 ms in >= 2 processes", POLICY),
    ("qualifications", "HOST_LOAD_WARN_PCT", 50.0, POLICY),
    ("snapshot_order", "max_backward / max_duplicates", "0 / 0", "definition: the world tick only grows"),
    ("snapshot_order", "min_snapshots", 10, POLICY),
    ("enemy_bounds", "tolerance / step_height", "0.01 / 0.4", "float tolerance; step height from content/README.md"),
    ("enemy_bounds", "min_samples", 50, POLICY),
    ("enemy_budget", "budget", "server-reported", "/status enemy_ai budget=N (GAMESERVER_ENEMY_BUDGET)"),
    ("render_freshness", "overrun p99", "50 ms", "Netcode InterpolationConfig.Default MaxExtrapolation"),
    ("prediction_bound", "max_unexplained_per_client_min", 4.0,
     "measured: fixed builds <= 2.0, pre-fix >= 7.5 (.testlab-runs/reanalysis/T16-FAC-V2/prediction-bound-derivation.log)"),
    ("prediction_bound", "match_window_ticks / min_seconds", "60 / 20 s", POLICY),
    ("server_config", "rates", "exact", "definition"),
    ("tick_adoption", "tick_hz", "exact", "definition: /status tick_rate"),
    ("entity_lifecycle", "despawn grace", "150 ms + one sample", "TargetDelay + MaxExtrapolation (InterpolationConfig.Default)"),
    ("entity_lifecycle", "reuse tolerance", "max_speed x 0.15 + 0.2", "same grace; 0.2 " + POLICY),
    ("cross_client_convergence", "p95 / max / min_pairs", "0.35 / 1.0 / 50", "inherited from remote position_divergence"),
    ("cross_client_convergence", "teleport_window_s", 0.5, "probe spacing 0.2 s + bracket 0.2 s + interpolation delay "
                                                           "0.1 s around a server respawn or teleport"),
    ("stall_recovery", "recover_s / judge_s / p95", "1.0 / 3.0 / 0.5", f"{POLICY}; 0.5 inherited from local divergence"),
    ("stall catch-up (render_jumps, position_divergence)", "remote catch-up window",
     "stall start .. the frame after the frame whose dt contains the stall",
     "Lead rule for S13 (T41): the world moved while the process was frozen; Unity's dt reports the previous "
     "frame and the binder state of frame N-1 is drawn in frame N (client docs/TESTLAB.md). Stalled client "
     "only, remote entities only"),
    ("stall catch-up (render_jumps)", "local major corrections allowed per stall", "1 within 5 s",
     "Lead rule for S13 (T41), Netcode D1 contract: one correction after a stall; a second one FAILs. The 5 s "
     f"window is {POLICY}"),
    ("graceful_leave", "leave_timeout_s", 5.0, f"{POLICY}; below the 60 s KCP idle timeout"),
    ("malformed_input", "within_s (closes)", 3.0, f"{POLICY}: see the per-scenario rows"),
    ("malformed_input", "min_snapshots (stays_open)", 5, f"{POLICY}: a third of a second at 15 Hz"),
    ("malformed_input", "displacement slack", "speed x elapsed + 0.5", f"{POLICY}: 0.5 units covers the 5 Hz sampling"),
    ("server_alive", "max_failed_probes / max_gap_s", "0 / 5.0", "definition / " + POLICY),
    ("churn_cycles", "max_join_s", 5.0, POLICY),
    ("churn_ghosts", "leave_within_s / drop_gone_within_s", "5.0 / 75.0",
     "graceful_leave bound / PingInterval 10 + PongTimeout 30 + EntityHoldTTL 30 + 5 s slack"),
    ("churn_ghosts", "quiet window", "last end + bound .. end, first 2 s skipped", f"{POLICY}: 2 s = 10 samples at 5 Hz"),
    ("player_count_baseline", "max_extra", 2, "definition: two churn users"),
    ("debug_kill_respawn", "respawn_within_s", 2.0, "one world interval (67 ms) + 1 Hz /status probe + queue; rounded up"),
    ("cast_damage_bound", "cooldown / power / reach", "content", "content/abilities.json at the run's server commit"),
    ("cast_damage_bound", "reach_margin", 1.0, POLICY),
    ("netem_applied", "sigmas / min_packets / rtt_rise_ratio", "3 / 300 / 0.5",
     "3 binomial standard deviations (0.27 % false alarm per direction); 300 datagrams is 15 expected drops at 5 %; the "
     "clients' round-trip time must rise by half the delay added to a round trip (a smoothed, sampled estimate)"),
    ("netem_prediction", "match_window_ticks", 60, "same as prediction_bound"),
    ("delivery (analyze --delivery)", "gap_ms / explain_fraction / bucket_s", "250 / 0.5 / 300", POLICY),
    ("delivery windowed clock fit", "window / bins / rate / empirical error", "10 s / >= 5 minima per 1 s bin / 0.8-1.2 / p95 <= 10 ms", "X13 measured 10 s minima fits: residual p95 2.16-3.85 ms on i9fl/e26z; 10 ms is a conservative rejection ceiling; rate range is defensive policy, unvalidated"),
    ("delivery scope", "time-overlap slack", "50 ms", POLICY),
    ("host_guard (INVALID verdict)", "window", f"start_scheduled - {hostguard.WINDOW_PRE_S:.0f} s .. scenario end + finish_grace_s",
     f"{POLICY}: a session that began just before t0 and is still running counts (F19 section 4.3)"),
    ("host_guard G1", "AnyDesk session", "any session event, `--backend` process or session active at window start, in the window",
     f"{POLICY}: 2 of 4 session starts in soaks with a sampler froze the players (e26z, i9fl), so none can be excused; "
     "residents (`AnyDesk.exe`, `--local-service`, `--local-control`) are allowed"),
    ("host_guard G2", "new AnyDesk process", "pid not in the preflight / pre-window set", f"{POLICY}: catches a missing or rotated log"),
    ("host_guard G3", "AnyDesk CPU, consecutive samples",
     f">= {hostguard.ANYDESK_IDLE_MAX_PCT} % of host for {hostguard.G3_CONSECUTIVE}",
     f"{POLICY}: 4x the idle maximum 0.13 % and half the lightest session ~1 % (F19 baseline 16:27-16:43Z, 185 samples)"),
    ("host_guard G4", "foreign load, consecutive samples",
     f"build tools > {hostguard.G4_BUILD_PCT} %, MsMpEng > {hostguard.G4_AV_PCT} % of host for {hostguard.G4_CONSECUTIVE}",
     f"{POLICY}: provisional; T62 pre-soak load was 51 %, MsMpEng 105 CPU-s per 30 s"),
    ("host_guard G5", "blind guard", f"> {hostguard.G5_MISSED_INTERVALS} missed intervals of {hostguard.INTERVAL_S:.0f} s (+1 s)", POLICY),
    ("host_guard G6", "server clock-rate step",
     f"> {hostguard.G6_RATE_DEVIATION_PCT:.0f}% from run-median current_tick / harness-second for > {hostguard.G6_SUSTAINED_S:.0f} s; "
     f"achieved_tick_hz >= {hostguard.G6_ACHIEVED_TICK_MIN_RATIO:.2f} x target",
     f"{POLICY}: F23 9mre had two ~6 s episodes at 65 vs 55 ticks/harness-second while achieved_tick_hz stayed ~60; "
     "flat i9fl/e26z series are the comparison evidence"),
    ("preflight P1", "no session now", f"no `--backend`, no session event or connection entry in the last {hostguard.PRE_QUIET_S:.0f} s", POLICY),
    ("preflight P2", "AnyDesk residents idle", f"mean CPU < {hostguard.ANYDESK_IDLE_MAX_PCT} % of host over a {hostguard.PRE_SAMPLE_S:.0f} s sample",
     f"{POLICY}: observed idle mean 0.03 %, max 0.13 %"),
    ("preflight P3", "no other agent working", "0 `working` agents in `orca worktree ps` except the allowed ones", POLICY),
    ("preflight P4", "no heavy foreign process", f"build-tool mean <= {hostguard.P4_FOREIGN_PCT} %, MsMpEng mean < {hostguard.G4_AV_PCT} %", POLICY),
    ("preflight P5", "host CPU", f"refuse above {hostguard.P5_REFUSE_PCT} % mean, flag shared-host above {hostguard.P5_SHARED_PCT} %",
     f"{POLICY}: idle baseline mean 15.8 %, p95 33 %"),
    ("preflight P6", "WSL warm", f"uptime >= {hostguard.P6_WSL_UPTIME_S:.0f} s", f"{POLICY}: FINAL-SOAK-PREFLIGHT found WSL cold at 15 s"),
    ("preflight P7", "window announced", "the user named start time and length (`--window-announced`)", f"{POLICY}: runbook step, out of band"),
    ("delivery KCP class", "after_rows", 4, f"{POLICY}: rows after tick b where a retransmission burst lands "
                                            "(T06 sfj5 s 738: 3 -> 40 in the next rows)"),
]


def _fmt(v) -> str:
    return json.dumps(v, separators=(", ", ": ")) if isinstance(v, (list, dict, bool)) else str(v)


def scenario_rows() -> list[tuple]:
    rows = []
    for sid in scenarios.list_ids():
        sc = scenarios.load(sid)
        for a in sc["assertions"]:
            for k, v in a.items():
                if k in ("id", "check", "title") or k in NOT_LIMITS or k.startswith("requires_"):
                    continue
                if a["check"] == "malformed_input" and k == "cases":
                    # one row per case parameter, with a per-case source where the case has its own derivation
                    for cid, rule in v.items():
                        for rk, rv in rule.items():
                            if rk in ("note", "rejections_counter"):
                                continue
                            src = SOURCES.get((a["check"], f"{cid}.{rk}")) or SOURCES.get((a["check"], rk), POLICY)
                            rows.append((sid, a["id"], a["check"], f"{cid}.{rk}", _fmt(rv), src))
                    continue
                rows.append((sid, a["id"], a["check"], k, _fmt(v), SOURCES.get((a["check"], k), POLICY)))
    return rows


def render() -> str:
    lines = [
        "# Test lab thresholds",
        "",
        "Generated by `python3 testlab/testlab.py thresholds --write` from `testlab/lab/thresholds.py` and the",
        "scenario files; `tests/test_lab.py` fails when this file is out of date. Every limit names its source:",
        f"a derivation (configuration, content, a measurement with its run ids) or **{POLICY}** - a reviewable",
        "choice nobody has measured against. Treat the policy limits as policy, not as validated targets.",
        "",
        "## Check defaults",
        "",
        "| Check | Parameter | Default | Source |",
        "|---|---|---|---|",
    ]
    lines += [f"| `{c}` | {p} | {_fmt(d)} | {s} |" for c, p, d, s in CHECK_DEFAULTS]
    lines += ["", "## Per scenario", "", "| Scenario | Assertion | Check | Parameter | Value | Source |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {sid} | `{aid}` | `{c}` | {k} | `{v}` | {s} |" for sid, aid, c, k, v, s in scenario_rows()]
    lines += ["", "## Scenario timing", "",
              "| Scenario | Duration s | Client / server sample Hz | Disruptions |", "|---|---|---|---|"]
    for sid in scenarios.list_ids():
        sc = scenarios.load(sid)
        dis = ", ".join(f"{d['kind']} at {d['at_s']} s" for d in sc["disruptions"]) or "-"
        lines.append(f"| {sid} | {sc['duration_s']} | {sc['sample_hz']} / {sc['server_sample_hz']} | {dis} |")
    lines += ["", "## Impairment profiles", "",
              "| Scenario | Phases (baseline / impaired / recovery s) | Per direction | Source |", "|---|---|---|---|"]
    for sid in scenarios.list_ids():
        for d in scenarios.load(sid)["disruptions"]:
            if d["kind"] == "netem":
                p = d["profile"]
                lines.append(f"| {sid} | {d.get('baseline_s')} / {d.get('impaired_s')} / {d.get('recovery_s')} | "
                             f"loss {p.get('loss_pct')} %, delay {p.get('delay_ms')} ms +/- {p.get('jitter_ms')} ms, "
                             f"reorder {p.get('reorder_pct')} % ({', '.join(d.get('directions') or [])}) | {NETEM_PROFILE_SOURCE} |")
    lines += ["", "Durations, kill and stall instants and the S11 grace window are scenario timing chosen by the "
              f"author ({POLICY}).", ""]
    return "\n".join(lines)
