"""Every limit the test lab grades against, with where it comes from: testlab/docs/THRESHOLDS.md.

The document is generated from this module and the scenario files (`testlab.py thresholds --write`),
and a unit test fails when it is out of date, so a new or changed limit cannot go undocumented.
A source is either a derivation (configuration, content, a measurement with its run ids) or
"policy, unvalidated": a reviewable choice nobody has measured against.
"""

from __future__ import annotations

import json

from . import scenarios

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
                                           "graceful leave",
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
    ("players_online", "mode"): "scenario decision: the end of the run",
}
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
    ("stall_recovery", "recover_s / judge_s / p95", "1.0 / 3.0 / 0.5", f"{POLICY}; 0.5 inherited from local divergence"),
    ("graceful_leave", "leave_timeout_s", 5.0, f"{POLICY}; below the 60 s KCP idle timeout"),
    ("debug_kill_respawn", "respawn_within_s", 2.0, "one world interval (67 ms) + 1 Hz /status probe + queue; rounded up"),
    ("cast_damage_bound", "cooldown / power / reach", "content", "content/abilities.json at the run's server commit"),
    ("cast_damage_bound", "reach_margin", 1.0, POLICY),
    ("delivery (analyze --delivery)", "gap_ms / explain_fraction / bucket_s", "250 / 0.5 / 300", POLICY),
    ("delivery clock fit", "bins / tolerance", ">= 5 bins / residual p90 <= 50 ms", POLICY),
    ("delivery scope", "time-overlap slack", "50 ms", POLICY),
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
    lines += ["", "Durations, kill and stall instants and the S11 grace window are scenario timing chosen by the "
              f"author ({POLICY}).", ""]
    return "\n".join(lines)
