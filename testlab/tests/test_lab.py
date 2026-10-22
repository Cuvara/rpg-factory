"""Unit tests for the testlab's pure parts: scenario validation, plan expansion, path handling and
every analysis check against synthetic evidence. No stack, no Unity, no network.

    python3 -B testlab/tests/test_lab.py
"""

from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import analyze, scenarios, util  # noqa: E402


def _scenario(**kw):
    sc = copy.deepcopy(scenarios.DEFAULTS)
    sc.update({"schema": "rpg.testlab.scenario.v1", "id": "T", "version": 1, "title": "t",
               "assertions": [{"id": "a", "check": "clients_in_world"}], "_path": "t.json"})
    sc.update(kw)
    return sc


def _ev(clients=1, duration=10.0, entities=None, status=None, metrics_start=None, metrics_end=None, **sc_kw):
    sc = _scenario(clients=clients, duration_s=duration, **sc_kw)
    ents = entities or []
    ev = {
        "run_dir": Path("."),
        "meta": {},
        "scenario": sc,
        "clients": [{"index": i, "dir": Path(f"client-{i}"), "status": {}, "summary": None, "summaries": [],
                     "events": [], "samples": [], "snapshots": [], "inputs": [], "plan": {}, "logs": {},
                     "history": {}, "frames": []} for i in range(clients)],
        "server": {"entities": ents, "status": status or [], "container": [],
                   "metrics_start": metrics_start or {}, "metrics_end": metrics_end or {}},
        "redis": {},
        "bots": None,
    }
    ev["traj"] = analyze.trajectories(ents)
    return ev


class ScenarioTests(unittest.TestCase):
    def test_every_shipped_scenario_loads_and_expands(self):
        for sid in scenarios.list_ids():
            sc = scenarios.load(sid)
            for i in range(sc["clients"]):
                plan = scenarios.client_plan(sc, i, "run")
                self.assertEqual(plan["schema"], "rpg.testlab.plan.v1")
                self.assertEqual(plan["map"], sc["map"])
                for step in plan["steps"]:
                    self.assertLess(step["t0"], step["t1"])

    def test_unknown_mode_and_missing_assertions_are_refused(self):
        bad = _scenario(client_defaults={"steps": [{"t0": 0, "t1": 1, "mode": "teleport"}], "actions": []})
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(bad)
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(_scenario(assertions=[]))

    def test_per_client_override_replaces_only_the_named_block(self):
        sc = _scenario(clients=2, client_defaults={"steps": [{"t0": 0, "t1": 1, "mode": "idle"}],
                                                   "actions": [{"t0": 0, "t1": 1, "kind": "jump"}]},
                       per_client=[{"steps": [{"t0": 0, "t1": 2, "mode": "move", "x": 1, "y": 0}]}])
        p0, p1 = scenarios.client_plan(sc, 0, "r"), scenarios.client_plan(sc, 1, "r")
        self.assertEqual(p0["steps"][0]["mode"], "move")
        self.assertEqual(p0["actions"][0]["kind"], "jump")
        self.assertEqual(p1["steps"][0]["mode"], "idle")


class UtilTests(unittest.TestCase):
    def test_path_conversion_both_directions(self):
        self.assertEqual(util.to_wsl_path(r"C:\Workspaces\UnityIndie\x"), "/mnt/c/Workspaces/UnityIndie/x")
        self.assertEqual(util.to_wsl_path("/mnt/c/a"), "/mnt/c/a")
        self.assertEqual(util.to_windows_path("/c/Workspaces/a"), "C:\\Workspaces\\a")
        self.assertEqual(util.to_windows_path("/mnt/d/x/y"), "D:\\x\\y")

    def test_percentile_nearest_rank(self):
        self.assertEqual(util.percentile(range(1, 101), 95), 95)
        self.assertIsNone(util.percentile([], 50))

    def test_atomic_json_and_ndjson_tolerate_a_cut_last_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            util.write_json(p, {"x": 1})
            self.assertEqual(util.read_json(p), {"x": 1})
            n = Path(d) / "b.ndjson"
            n.write_text('{"a":1}\n{"a":2}\n{"a":', encoding="utf-8")
            self.assertEqual([r["a"] for r in util.read_ndjson(n)], [1, 2])


def _row(st, ents):
    return {"st": st, "tick": int(st * 60), "ents": ents}


class ConfigTests(unittest.TestCase):
    def test_a_build_directory_resolves_to_its_player_exe(self):
        import tempfile
        from lab import config
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "StandaloneWindows64" / "IndieRPGMMOAdventure.exe"
            exe.parent.mkdir()
            exe.write_bytes(b"")
            self.assertEqual(config.LabConfig(workspace=Path(d), player_exe=Path(d)).player_exe, exe)
            self.assertEqual(config.LabConfig(workspace=Path(d), player_exe=exe.parent).player_exe, exe)


class AnalysisTests(unittest.TestCase):
    def test_missing_evidence_is_inconclusive_never_pass(self):
        ev = _ev()
        for check in ("players_online", "server_tick", "kcp_health", "enemy_crowding", "frame_time",
                      "position_divergence", "memory_growth", "snapshot_update_gap", "inputs_consumed"):
            res = analyze.CHECKS[check](ev, {})
            self.assertNotEqual(res["status"], analyze.PASS, check)

    def test_unknown_check_and_raising_check_are_inconclusive(self):
        ev = _ev()
        ev["scenario"]["assertions"] = [{"id": "x", "check": "nope"}, {"id": "y", "check": "reconnect", "client": 9}]
        out = analyze.evaluate(ev)
        self.assertEqual([r["status"] for r in out], [analyze.INCONCLUSIVE, analyze.INCONCLUSIVE, analyze.INFO])  # + host_quiet
        self.assertEqual(analyze.overall(out), analyze.INCONCLUSIVE)

    def test_overall_fail_dominates_and_info_never_decides(self):
        self.assertEqual(analyze.overall([{"status": "PASS"}, {"status": "INFO"}]), "PASS")
        self.assertEqual(analyze.overall([{"status": "PASS"}, {"status": "FAIL"}, {"status": "INCONCLUSIVE"}]), "FAIL")
        self.assertEqual(analyze.overall([{"status": "PASS"}], harness_error="boom"), "INCONCLUSIVE")

    def test_kcp_counts_only_the_scenario_window(self):
        start = {'gameserver_kcp_datagrams_dropped_total{reason="no_session"}': 0.0,
                 'gameserver_kcp_sessions_closed_total{reason="dead_link"}': 0.0}
        end = {'gameserver_kcp_datagrams_dropped_total{reason="no_session"}': 4.0,
               'gameserver_kcp_sessions_closed_total{reason="dead_link"}': 0.0}
        res = analyze.check_kcp_health(_ev(metrics_start=start, metrics_end=end), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["detail"]["by_reason"], {"no_session": 4.0})

    def test_position_divergence_allows_the_interpolation_window_and_attributes_the_layer(self):
        # Server: entity m walks +x at 2.5 u/s, sampled at 5 Hz.
        ents = [_row(i * 0.2, [["m", "mob", 2.5 * i * 0.2, 0.0, 16, 16, 0, 2.5]]) for i in range(60)]
        ev = _ev(entities=ents, duration=12)
        # Client renders it 100 ms late (on the path), and once 2 units off the path while it
        # RECEIVED the right position: interpolation layer.
        samples = []
        for k in range(200):
            st = 2.0 + k * 0.05
            rx = 2.5 * (st - 0.1)
            ry = 2.0 if k == 100 else 0.0
            samples.append({"st": st, "ents": [["m", "mob", 0, rx, ry, 2.5 * st, 0.0]]})
        ev["clients"][0]["samples"] = samples
        res = analyze.check_position_divergence(ev, {"types": ["mob"], "p95": 0.35, "max": 1.0, "min_samples": 10})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertLess(res["measured"]["p95"], 0.05)
        self.assertIn("interpolation", res["detail"]["layer"])
        ev["clients"][0]["samples"][100]["ents"][0][4] = 0.0
        self.assertEqual(analyze.check_position_divergence(ev, {"types": ["mob"], "min_samples": 10})["status"], analyze.PASS)

    def test_render_jumps_separate_server_teleports_from_render_defects(self):
        # Server: player p stands at -15 then is teleported (respawn) to 0 at st=5.
        ents = [_row(i * 0.2, [["p", "player", -15.0 if i * 0.2 < 5 else 0.0, 0.0, 100, 100, 0, 5]]) for i in range(50)]
        ev = _ev(entities=ents, duration=10)
        ev["clients"][0]["summary"] = {"outcome": "completed"}
        ev["clients"][0]["events"] = [
            {"event": "render_jump", "st": 5.05, "id": "p", "type": "player", "local": False, "step": 15.0},  # respawn
            {"event": "render_jump", "st": 7.0, "id": "p", "type": "player", "local": False, "step": 5.0},   # render only
            {"event": "render_jump", "st": 8.0, "id": "p", "type": "player", "local": True, "step": 0.4},    # hitch
        ]
        res = analyze.check_render_jumps(ev, {"max_local": 0, "max_remote_per_client_min": 2.0})
        m = res["measured"]
        self.assertEqual((m["server_teleport"], m["remote_major"], m["local_minor"]), (1, 1, 1))
        self.assertEqual(res["status"], analyze.FAIL)  # 1 remote major in 10 s = 6/min > 2

    def test_a_short_respawn_counts_as_a_server_teleport(self):
        # Player dies at (3, 1) with 3 HP and respawns at (0.3, 0.3) with full HP at st=5.
        ents = [_row(i * 0.2, [["p", "player", 3.0 if i * 0.2 < 5 else 0.3, 1.0 if i * 0.2 < 5 else 0.3,
                                3 if i * 0.2 < 5 else 100, 100, 0, 5]]) for i in range(50)]
        ev = _ev(entities=ents, duration=10)
        ev["clients"][0]["summary"] = {"outcome": "completed"}
        ev["clients"][0]["events"] = [
            {"event": "render_jump", "st": 5.1, "id": "p", "type": "player", "local": True, "step": 3.1}]
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual(res["measured"]["server_teleport"], 1)
        self.assertEqual(res["status"], analyze.PASS)

    def test_review_findings_are_not_false_passes(self):
        # Zero clients: never "all completed".
        self.assertEqual(analyze.check_clients_completed(_ev(clients=0), {})["status"], analyze.INCONCLUSIVE)
        # A move step with no server samples is not silently skipped.
        ents = [_row(i * 0.2, [["u", "player", 5.0 * max(0, i * 0.2 - 1), 0.0, 100, 100, 0, 5.0]]) for i in range(30)]
        ev = _ev(entities=ents, duration=20)
        ev["clients"][0]["summary"] = {"user_id": "u", "input": {"moves_read": 9}}
        ev["clients"][0]["plan"] = {"steps": [{"t0": 1, "t1": 4, "mode": "move", "x": 1, "y": 0},
                                              {"t0": 10, "t1": 14, "mode": "move", "x": 1, "y": 0}]}
        self.assertEqual(analyze.check_inputs_consumed(ev, {})["status"], analyze.INCONCLUSIVE)
        # A respawn does not excuse a rendered jump the server's motion does not explain.
        ents = [_row(i * 0.2, [["p", "player", 3.0 if i * 0.2 < 5 else 2.5, 1.0, 3 if i * 0.2 < 5 else 100, 100, 0, 5]])
                for i in range(50)]
        ev = _ev(entities=ents, duration=10)
        ev["clients"][0]["summary"] = {"outcome": "completed"}
        ev["clients"][0]["events"] = [
            {"event": "render_jump", "st": 5.1, "id": "p", "type": "player", "local": True, "step": 6.0}]
        self.assertEqual(analyze.check_render_jumps(ev, {"max_local": 0})["measured"]["local_major"], 1)

    def test_crowding_without_a_spread_interval_is_inconclusive_when_required(self):
        def sample(st):
            ents = [[f"p{i}", "player", x, 0.0, 100, 100, 0, 5] for i, x in enumerate([0, 0.5, 1.0])]
            ents += [[f"m{j}", "mob", 0.5, 0.01 * j, 16, 16, 0, 2.5] for j in range(20)]
            return _row(st, ents)
        ev = _ev(entities=[sample(6 + i * 0.2) for i in range(30)], duration=20)
        self.assertEqual(analyze.check_enemy_crowding(ev, {"spread_distance": 10, "require_spread": True})["status"],
                         analyze.INCONCLUSIVE)

    def test_a_gap_explained_by_a_host_wide_stall_is_inconclusive_not_fail(self):
        ev = _ev(clients=2, duration=10, status=[{"_st": 5, "sim_world_hz": 15}])
        for c in ev["clients"]:
            c["summary"] = {"start_realtime": 100.0}
            c["snapshots"] = [{"t": 100.0 + k / 15.0} for k in range(150) if not 70 <= k < 82]
            c["frames"] = [(k / 60.0, 16.7) for k in range(600)] + [(5.45, 800.0)]
        res = analyze.check_snapshot_cadence(ev, {"max_gap_ms": 250})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)
        ev["clients"][1]["frames"] = [(k / 60.0, 16.7) for k in range(600)]  # only one process stalled
        self.assertEqual(analyze.check_snapshot_cadence(ev, {"max_gap_ms": 250})["status"], analyze.FAIL)

    def test_jumps_hidden_only_by_a_host_stall_make_the_result_inconclusive(self):
        ents = [_row(i * 0.2, [["p", "player", 0.0, 0.0, 100, 100, 0, 5]]) for i in range(50)]
        ev = _ev(clients=2, entities=ents, duration=10)
        for c in ev["clients"]:
            c["summary"] = {"outcome": "completed"}
            c["frames"] = [(5.0, 800.0)]
        ev["clients"][0]["events"] = [
            {"event": "render_jump", "st": 5.1, "id": "p", "type": "player", "local": True, "step": 3.0}]
        self.assertEqual(analyze.check_render_jumps(ev, {"max_local": 0})["status"], analyze.INCONCLUSIVE)
        ev["clients"][1]["frames"] = []  # not host-wide any more: a real local snap
        self.assertEqual(analyze.check_render_jumps(ev, {"max_local": 0})["status"], analyze.FAIL)

    def test_projectiles_are_not_judged_as_walking_entities(self):
        ev = _ev(duration=10)
        ev["clients"][0]["summary"] = {"outcome": "completed"}
        ev["clients"][0]["events"] = [
            {"event": "render_jump", "st": 5.0, "id": "pr", "type": "projectile", "local": True, "step": 3.0}]
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual(res["status"], analyze.PASS)
        self.assertEqual(res["measured"]["ignored_type"], 1)

    def test_reconnect_reads_the_last_sample_inside_the_window(self):
        rows = [_row(st, [[f"p{i}", "player", 0.0, 0.0, 100, 100, 0, 5] for i in range(3)]) for st in (1.0, 5.0, 9.5)]
        rows.append(_row(11.0, [["p0", "player", 0.0, 0.0, 100, 100, 0, 5]]))  # teardown, after the window
        ev = _ev(clients=3, entities=rows, duration=10, status=[{"_st": 9.0, "players_online": 3}])
        for i, c in enumerate(ev["clients"]):
            c["summary"] = {"user_id": f"p{i}"}
        ev["clients"][2]["history"] = {"first_user_id": "p2", "history": [{"event": "launch"}, {"event": "launch"}]}
        res = analyze.check_reconnect(ev, {"client": 2})
        self.assertEqual(res["measured"]["player_entities_final"], 3)
        self.assertEqual(res["status"], analyze.PASS)

    def test_a_respawn_the_server_probe_aliased_is_seen_in_the_received_stream(self):
        # Server probe at 5 Hz misses the instant; the client received -1.17 -> 0 in one snapshot.
        ents = [_row(15.0, [["p", "player", 0.0, 0.0, 1, 100, 0, 5]]),
                _row(15.22, [["p", "player", -0.83, 0.0, 1, 100, 0, 5]]),
                _row(15.42, [["p", "player", -0.25, 0.0, 100, 100, 0, 5]])]
        ev = _ev(entities=ents, duration=20)
        c = ev["clients"][0]
        c["summary"] = {"outcome": "completed"}
        c["samples"] = [{"st": 15.31, "world_tick": 900, "ents": [["p", "player", 1, -1.28, 0.0, -1.167, 0.0]]},
                        {"st": 15.366, "world_tick": 904, "ents": [["p", "player", 1, -0.35, 0.0, 0.0, 0.0]]}]
        c["events"] = [{"event": "render_jump", "st": 15.362, "id": "p", "type": "player", "local": True, "step": 1.14}]
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual(res["measured"]["server_teleport"], 1)
        self.assertEqual(res["status"], analyze.PASS)

    def test_a_late_snapshot_burst_is_not_a_server_teleport(self):
        # The client received 1.0 units in one step, but 12 server ticks (200 ms) passed between
        # the two snapshots: walkable, so a 1.1-unit local render jump is the client's defect.
        ev = _ev(entities=[_row(15.0 + 0.2 * k, [["p", "player", 1.0 * k, 0.0, 100, 100, 0, 5]]) for k in range(3)],
                 duration=20)
        c = ev["clients"][0]
        c["summary"] = {"outcome": "completed"}
        c["samples"] = [{"st": 15.31, "world_tick": 900, "ents": [["p", "player", 1, 0.0, 0.0, 0.0, 0.0]]},
                        {"st": 15.366, "world_tick": 912, "ents": [["p", "player", 1, 1.0, 0.0, 1.0, 0.0]]}]
        c["events"] = [{"event": "render_jump", "st": 15.362, "id": "p", "type": "player", "local": True, "step": 1.1}]
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual(res["measured"]["server_teleport"], 0)
        self.assertEqual(res["measured"]["local_major"], 1)
        self.assertEqual(res["status"], analyze.FAIL)

    def test_replication_gap_with_missing_samples_is_inconclusive(self):
        rows = [{"_st": float(i), "snapshot_max_update_gap_ms": 100} for i in range(10)]
        rows[3].pop("snapshot_max_update_gap_ms")
        ev = _ev(duration=10, status=rows)
        self.assertEqual(analyze.check_snapshot_update_gap(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_crowding_concentration_is_a_defect_only_when_players_are_spread(self):
        def sample(st, players):
            ents = [[f"p{i}", "player", x, 0.0, 100, 100, 0, 5] for i, x in enumerate(players)]
            ents += [[f"m{j}", "mob", players[0] + 0.5, 0.01 * j, 16, 16, 0, 2.5] for j in range(20)]
            return _row(st, ents)
        together = _ev(entities=[sample(6 + i * 0.2, [0, 0.5, 1.0]) for i in range(30)], duration=20)
        res = analyze.check_enemy_crowding(together, {"spread_distance": 10})
        self.assertNotEqual(res["status"], analyze.FAIL, "a pile on players standing together is the AI design")
        spread = _ev(entities=[sample(6 + i * 0.2, [0, 15, -15]) for i in range(30)], duration=20)
        res = analyze.check_enemy_crowding(spread, {"spread_distance": 10, "max_share_when_spread": 0.9})
        self.assertEqual(res["status"], analyze.INFO, "concentration alone follows the nearest-player rule")
        res = analyze.check_enemy_crowding(spread, {"spread_distance": 10, "max_share_when_spread": 0.9,
                                                    "share_is_failure": True})
        self.assertEqual(res["status"], analyze.FAIL)

    def test_pursuit_passes_when_far_enemies_close_on_the_nearest_player(self):
        def sample(st, sign):
            ents = [["a", "player", 0.0, 0.0, 100, 100, 0, 5], ["b", "player", 40.0, 0.0, 100, 100, 0, 5]]
            # m0 near a walks to a; m1 near b walks to b (or away from it when sign is -1).
            ents += [["m0", "mob", -10.0 + 2.5 * st, 0.0, 16, 16, 0, 2.5],
                     ["m1", "mob", 50.0 - sign * 2.5 * st, 0.0, 16, 16, 0, 2.5]]
            return _row(st, ents)
        ok = _ev(entities=[sample(i * 0.1, 1) for i in range(30)], duration=3)
        res = analyze.check_enemy_pursuit(ok, {"skip_first_s": 0, "min_far_steps": 10})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertGreater(res["measured"]["far_steps"], 0)
        bad = _ev(entities=[sample(i * 0.1, -1) for i in range(30)], duration=3)
        res = analyze.check_enemy_pursuit(bad, {"skip_first_s": 0, "min_far_steps": 10})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(0.4 < res["measured"]["pursuit_ratio"] < 0.6, res["measured"])  # m0 closes, m1 flees

    def test_pursuit_settled_jitter_is_relative_to_the_target(self):
        def sample(st, jitter):
            dx = (0.1 if int(st * 10) % 2 else -0.1) if jitter else 0.0
            ents = [["a", "player", st, 0.0, 100, 100, 0, 5],
                    ["m0", "mob", st + 1.0 + dx, 0.0, 16, 16, 0, 2.5],
                    ["m1", "mob", -10.0 + 2.5 * st, 5.0, 16, 16, 0, 2.5]]
            return _row(st, ents)
        still = analyze.check_enemy_pursuit(_ev(entities=[sample(i * 0.1, False) for i in range(30)], duration=3),
                                            {"skip_first_s": 0, "max_settled_speed": 0.3,
                                             "min_far_steps": 10, "min_settled_samples": 10})
        self.assertEqual(still["measured"]["settled_rel_speed_p95"], 0.0, "following a walking player is not jitter")
        self.assertEqual(still["status"], analyze.PASS)
        shaky = analyze.check_enemy_pursuit(_ev(entities=[sample(i * 0.1, True) for i in range(30)], duration=3),
                                            {"skip_first_s": 0, "max_settled_speed": 0.3,
                                             "min_far_steps": 10, "min_settled_samples": 10})
        self.assertEqual(shaky["status"], analyze.FAIL)

    def test_pursuit_does_not_judge_enemies_moved_inside_a_crowd(self):
        # Two enemies 0.5 apart, far from the player, sliding sideways: separation and queueing,
        # not targeting. Reported as crowd steps; with no isolated step the rule is unjudged.
        rows = [_row(i * 0.1, [["a", "player", 0.0, 0.0, 100, 100, 0, 5],
                               ["m0", "mob", -10.0, 0.2 * i, 16, 16, 0, 2.5],
                               ["m1", "mob", -10.0, 0.5 + 0.2 * i, 16, 16, 0, 2.5]]) for i in range(80)]
        res = analyze.check_enemy_pursuit(_ev(entities=rows, duration=8), {"skip_first_s": 0, "min_far_steps": 10})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)

    def test_pursuit_with_too_few_far_steps_is_inconclusive(self):
        rows = [_row(i * 0.1, [["a", "player", 0.0, 0.0, 100, 100, 0, 5],
                               ["m", "mob", -10.0 + 0.25 * i, 0.0, 16, 16, 0, 2.5]]) for i in range(5)]
        self.assertEqual(analyze.check_enemy_pursuit(_ev(entities=rows, duration=1), {"skip_first_s": 0})["status"],
                         analyze.INCONCLUSIVE)

    def test_pursuit_without_far_motion_is_inconclusive(self):
        rows = [_row(i * 0.1, [["a", "player", 0.0, 0.0, 100, 100, 0, 5], ["m", "mob", 1.0, 0.0, 16, 16, 0, 2.5]])
                for i in range(20)]
        self.assertEqual(analyze.check_enemy_pursuit(_ev(entities=rows, duration=2), {"skip_first_s": 0})["status"],
                         analyze.INCONCLUSIVE)

    def test_spawn_overlap_flags_players_starting_on_the_same_point(self):
        def run(second_at):
            rows = [_row(0.0, [["a", "player", 0.0, 0.0, 100, 100, 0, 5]])]
            rows += [_row(0.1 * k, [["a", "player", 0.0, 0.0, 100, 100, 0, 5],
                                    ["b", "player", second_at, 0.0, 100, 100, 0, 5]]) for k in range(1, 5)]
            return analyze.check_spawn_overlap(_ev(entities=rows, duration=1), {"min_distance": 0.5, "min_judged": 1})
        self.assertEqual(run(0.0)["status"], analyze.FAIL)
        self.assertEqual(run(0.0)["measured"]["overlapping"], 1)
        self.assertEqual(run(2.0)["status"], analyze.PASS)

    def test_spawn_overlap_counts_a_respawn_onto_another_player(self):
        rows = [_row(0.0, [["a", "player", 0.0, 0.0, 100, 100, 0, 5], ["b", "player", 9.0, 0.0, 100, 100, 0, 5]]),
                _row(0.1, [["a", "player", 0.0, 0.0, 100, 100, 0, 5], ["b", "player", 9.0, 0.0, 0, 100, 1, 5]]),
                _row(0.2, [["a", "player", 0.0, 0.0, 100, 100, 0, 5], ["b", "player", 0.1, 0.0, 100, 100, 0, 5]])]
        res = analyze.check_spawn_overlap(_ev(entities=rows, duration=1), {"min_distance": 0.5, "min_judged": 1})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["detail"]["overlapping"][0]["id"], "b")
        # Three placements judged (a and b joining together, b respawning) meet the default minimum.
        self.assertEqual(analyze.check_spawn_overlap(_ev(entities=rows, duration=1), {})["measured"]["judged"], 3)

    def test_spawn_overlap_with_one_player_is_inconclusive(self):
        rows = [_row(0.1 * k, [["a", "player", 0.0, 0.0, 100, 100, 0, 5]]) for k in range(5)]
        self.assertEqual(analyze.check_spawn_overlap(_ev(entities=rows, duration=1), {})["status"], analyze.INCONCLUSIVE)

    def test_inputs_consumed_skips_a_respawn_inside_the_segment(self):
        # Walking +x at 5 u/s from t=1; killed and put back at the spawn point at t=2.5; walks on.
        def x_at(st):
            if st < 1:
                return 0.0
            return 5.0 * (st - 1) if st < 2.5 else 5.0 * (st - 2.5)
        def hp_at(st):
            return 10 if 2.0 <= st < 2.5 else 100
        ents = [_row(i * 0.2, [["u", "player", x_at(i * 0.2), 0.0, hp_at(i * 0.2), 100, 0, 5.0]]) for i in range(30)]
        ev = _ev(entities=ents, duration=6)
        ev["clients"][0]["summary"] = {"user_id": "u", "input": {"moves_read": 50}}
        ev["clients"][0]["plan"] = {"steps": [{"t0": 1, "t1": 5, "mode": "move", "x": 1, "y": 0}]}
        res = analyze.check_inputs_consumed(ev, {})
        self.assertEqual(res["status"], analyze.PASS, res["detail"])
        self.assertEqual(res["detail"]["segments"][0]["respawns"], 1)
        # A player that never moves still fails, respawn or not.
        still = [_row(i * 0.2, [["u", "player", 0.0, 0.0, hp_at(i * 0.2), 100, 0, 5.0]]) for i in range(30)]
        ev2 = _ev(entities=still, duration=6)
        ev2["clients"][0]["summary"] = ev["clients"][0]["summary"]
        ev2["clients"][0]["plan"] = ev["clients"][0]["plan"]
        self.assertEqual(analyze.check_inputs_consumed(ev2, {})["status"], analyze.FAIL)

    def test_inputs_consumed_compares_direction_and_distance(self):
        ents = [_row(i * 0.2, [["u", "player", 5.0 * max(0, i * 0.2 - 1), 0.0, 100, 100, 0, 5.0]]) for i in range(30)]
        ev = _ev(entities=ents, duration=6)
        ev["clients"][0]["summary"] = {"user_id": "u", "input": {"moves_read": 50}}
        ev["clients"][0]["plan"] = {"steps": [{"t0": 1, "t1": 4, "mode": "move", "x": 1, "y": 0}]}
        self.assertEqual(analyze.check_inputs_consumed(ev, {})["status"], analyze.PASS)
        ev["clients"][0]["plan"] = {"steps": [{"t0": 1, "t1": 4, "mode": "move", "x": -1, "y": 0}]}
        self.assertEqual(analyze.check_inputs_consumed(ev, {})["status"], analyze.FAIL)

    def test_tick_p99_reads_the_histogram_delta(self):
        start = {'gameserver_tick_duration_seconds_bucket{le="0.001"}': 100.0,
                 'gameserver_tick_duration_seconds_bucket{le="0.01"}': 100.0,
                 'gameserver_tick_duration_seconds_bucket{le="+Inf"}': 100.0}
        end = {'gameserver_tick_duration_seconds_bucket{le="0.001"}': 1080.0,
               'gameserver_tick_duration_seconds_bucket{le="0.01"}': 1100.0,
               'gameserver_tick_duration_seconds_bucket{le="+Inf"}': 1100.0}
        ev = _ev(metrics_start=start, metrics_end=end)
        self.assertEqual(analyze.tick_p99_ms(ev), 10.0)

    def test_prometheus_parser(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.txt"
            p.write_text('# HELP x\nfoo_total{a="b"} 3\nbar 1.5e2\n', encoding="utf-8")
            self.assertEqual(analyze.parse_prometheus(p), {'foo_total{a="b"}': 3.0, "bar": 150.0})


if __name__ == "__main__":
    unittest.main()
