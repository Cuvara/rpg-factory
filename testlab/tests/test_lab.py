"""Unit tests for the testlab's pure parts: scenario validation, plan expansion, path handling and
every analysis check against synthetic evidence. No stack, no Unity, no network.

    python3 -B testlab/tests/test_lab.py
"""

from __future__ import annotations

import copy
import json
import math
import os
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


class WriteJsonTests(unittest.TestCase):
    def test_write_json_retries_a_replace_the_target_is_locked_for(self):
        import tempfile
        from unittest import mock
        from lab import util
        real = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(5, "Access is denied")
            return real(src, dst)

        with tempfile.TemporaryDirectory() as d, mock.patch.object(util.os, "replace", flaky):
            target = Path(d) / "control.json"
            util.write_json(target, {"ok": 1})
            self.assertEqual(json.loads(target.read_text()), {"ok": 1})
            self.assertEqual(calls["n"], 3)


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
    def test_distinct_user_ids_needs_at_least_two_clients(self):
        self.assertEqual(analyze.check_distinct_user_ids(_ev(clients=0), {})["status"], analyze.INCONCLUSIVE)
        one = _ev(clients=1)
        one["clients"][0]["summary"] = {"user_id": "u0"}
        self.assertEqual(analyze.check_distinct_user_ids(one, {})["status"], analyze.INCONCLUSIVE)
        two = _ev(clients=2)
        for i, c in enumerate(two["clients"]):
            c["summary"] = {"user_id": f"u{i}"}
        self.assertEqual(analyze.check_distinct_user_ids(two, {})["status"], analyze.PASS)

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
        # + provenance (no record: INCONCLUSIVE) and host_quiet (INFO), appended to every evaluation
        self.assertEqual([r["status"] for r in out],
                         [analyze.INCONCLUSIVE, analyze.INCONCLUSIVE, analyze.INCONCLUSIVE, analyze.INFO])
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
            c["events"] = [{"event": "in_world", "st": -1.0}]
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


# =========================================================================== harness reliability

def _all_assertions():
    """One assertion per registered check, with the parameters a check cannot run without."""
    extra = {"trajectory_bound": {"client": 0, "axis": "y", "max": 1.0}}
    return [{"id": f"a_{name}", "check": name, **extra.get(name, {})} for name in sorted(analyze.CHECKS)]


class MissingEvidenceTests(unittest.TestCase):
    """Absent or empty evidence never grades PASS - for every check the lab has."""

    INFO_ONLY = {"host_quiet", "bots_joined"}  # environment / not-applicable reports, never decide a run

    def _statuses(self, ev):
        ev["scenario"]["assertions"] = _all_assertions()
        return {r["check"]: r["status"] for r in analyze.evaluate(ev)}

    def test_every_check_without_evidence_is_never_pass(self):
        for clients in (0, 1, 3):
            statuses = self._statuses(_ev(clients=clients))
            self.assertEqual(set(statuses), set(analyze.CHECKS))
            for check, status in statuses.items():
                allowed = {analyze.INFO} if check in self.INFO_ONLY else {analyze.INCONCLUSIVE, analyze.FAIL}
                self.assertIn(status, allowed, f"{check} with {clients} client(s) and no evidence: {status}")

    def test_files_that_exist_but_are_empty_are_missing_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "20260101T000000Z-T-abcd"
            for rel in ("client-0/summary.json", "client-0/events.ndjson", "client-0/snapshots.ndjson",
                        "client-0/samples.ndjson", "client-0/frames.csv", "client-0/player.log",
                        "server/entities.ndjson", "server/status.ndjson", "server/metrics-start.txt",
                        "server/metrics-end.txt", "redis.json"):
                (run / rel).parent.mkdir(parents=True, exist_ok=True)
                (run / rel).write_text("", encoding="utf-8")
            sc = _scenario(clients=1, assertions=_all_assertions())
            (run / "scenario.json").write_text(json.dumps(sc), encoding="utf-8")
            (run / "run.json").write_text(json.dumps({"run_id": run.name}), encoding="utf-8")
            ev = analyze.load_evidence(run)
            for r in analyze.evaluate(ev):
                if r["check"] not in self.INFO_ONLY:
                    self.assertNotEqual(r["status"], analyze.PASS, r["check"])

    def test_log_check_needs_a_log(self):
        ev = _ev(clients=2)
        self.assertEqual(analyze.check_client_log_clean(ev, {})["status"], analyze.INCONCLUSIVE)
        for c in ev["clients"]:
            c["logs"] = {"player.log": "[TestLab] in world\n"}
        self.assertEqual(analyze.check_client_log_clean(ev, {})["status"], analyze.PASS)
        self.assertEqual(analyze.check_client_log_clean(_ev(clients=0), {})["status"], analyze.INCONCLUSIVE)

    def test_cadence_with_no_clients_is_inconclusive(self):
        ev = _ev(clients=0, status=[{"_st": 1, "sim_world_hz": 15}])
        self.assertEqual(analyze.check_snapshot_cadence(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_render_jumps_need_every_clients_events(self):
        ev = _ev(clients=2)
        for c in ev["clients"]:
            c["summary"] = {"outcome": "completed"}
        ev["clients"][0]["events"] = [{"event": "in_world", "st": -1}]
        self.assertEqual(analyze.check_render_jumps(ev, {})["status"], analyze.INCONCLUSIVE)
        ev["clients"][1]["events"] = [{"event": "in_world", "st": -1}]
        self.assertEqual(analyze.check_render_jumps(ev, {})["status"], analyze.PASS)

    def test_zero_clients_cannot_satisfy_online_or_redis_counts(self):
        ev = _ev(clients=0, status=[{"_st": 1, "players_online": 0}])
        ev["redis"] = {"session_keys": 0, "map_members": ["gs"]}
        self.assertEqual(analyze.check_players_online(ev, {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_redis(ev, {})["status"], analyze.INCONCLUSIVE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _run_dir(root: Path, run_id="20260101T000000Z-T-abcd", *, netcode_embedded=True, netcode_sha="5fa8f37"):
    """A finished run directory with a complete provenance record."""
    from lab import provenance
    run = root / run_id
    sc = _scenario(clients=1)
    _write(run / "scenario.json", json.dumps(sc))
    _write(run / "client-0" / "summary.json", json.dumps({"run_id": run_id, "user_id": "u0"}))
    _write(run / "server" / "entities.ndjson", '{"st": 1, "ents": []}\n')
    prov = {
        "schema": provenance.SCHEMA, "run_id": run_id,
        "factory": {"sha": "f" * 40}, "server": {"sha": "s" * 40, "image_id": "sha256:" + "i" * 64},
        "client": {"sha": "c" * 40},
        "netcode": {"embedded": netcode_embedded, "sha": netcode_sha},
        "player": {"exe_sha256": "e" * 64, "managed_sha256": "m" * 64},
        "scenario": {"id": sc["id"], "version": sc["version"], "sha256": provenance.sha256_file(run / "scenario.json")},
        "host_quiet": {"load_start": {"cpu_load_pct": 5}, "load_end": {"cpu_load_pct": 6}},
        "started_utc": "20260101T000000Z", "ended_utc": "20260101T000100Z",
        "manifest": provenance.manifest(run),
    }
    _write(run / "run.json", json.dumps({"run_id": run_id, "provenance": prov}))
    return run


class ProvenanceTests(unittest.TestCase):
    def _status(self, run):
        return analyze.check_provenance(analyze.load_evidence(run), {})

    def test_complete_matching_record_passes(self):
        with tempfile.TemporaryDirectory() as d:
            res = self._status(_run_dir(Path(d)))
            self.assertEqual(res["status"], analyze.PASS, res["detail"])
            self.assertEqual(res["measured"]["evidence_files"], 3)

    def test_a_run_without_a_record_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            _write(run / "run.json", json.dumps({"run_id": run.name}))
            self.assertEqual(self._status(run)["status"], analyze.INCONCLUSIVE)

    def test_each_required_field_is_required(self):
        from lab import provenance
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            full = json.loads((run / "run.json").read_text(encoding="utf-8"))
            for path, _ in provenance.REQUIRED:
                meta = copy.deepcopy(full)
                cur = meta["provenance"]
                *parents, leaf = path.split(".")
                for p in parents:
                    cur = cur[p]
                cur[leaf] = None
                _write(run / "run.json", json.dumps(meta))
                res = self._status(run)
                self.assertEqual(res["status"], analyze.INCONCLUSIVE, path)
                self.assertTrue(any(path in p for p in res["detail"]["problems"]), (path, res["detail"]["problems"]))

    def test_embedded_netcode_must_name_its_commit(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._status(_run_dir(Path(d), netcode_sha=None))["status"], analyze.INCONCLUSIVE)
        with tempfile.TemporaryDirectory() as d:  # manifest pin, nothing embedded: no commit needed
            self.assertEqual(self._status(_run_dir(Path(d), netcode_embedded=False, netcode_sha=None))["status"],
                             analyze.PASS)

    def test_record_from_another_run_or_changed_evidence_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            moved = run.with_name("20260202T000000Z-T-wxyz")  # a run copied under another id
            run.rename(moved)
            problems = self._status(moved)["detail"]["problems"]
            self.assertTrue(any("does not match the run directory" in p for p in problems), problems)
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            _write(run / "server" / "entities.ndjson", '{"st": 2, "ents": []}\n')
            problems = self._status(run)["detail"]["problems"]
            self.assertTrue(any("server/entities.ndjson changed" in p for p in problems), problems)
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            (run / "server" / "entities.ndjson").unlink()
            problems = self._status(run)["detail"]["problems"]
            self.assertTrue(any("server/entities.ndjson is missing" in p for p in problems), problems)
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            sc = json.loads((run / "scenario.json").read_text(encoding="utf-8"))
            sc["version"] = 2
            _write(run / "scenario.json", json.dumps(sc))
            problems = self._status(run)["detail"]["problems"]
            self.assertTrue(any("scenario.json is T v2" in p for p in problems), problems)
            self.assertTrue(any("scenario.json changed" in p for p in problems), problems)

    def test_a_client_summary_from_another_run_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
            meta["provenance"]["manifest"] = {}  # isolate the run-id comparison from the hash check
            _write(run / "run.json", json.dumps(meta))
            _write(run / "client-0" / "summary.json", json.dumps({"run_id": "20251231T000000Z-T-old0"}))
            problems = self._status(run)["detail"]["problems"]
            self.assertTrue(any("belongs to run 20251231T000000Z-T-old0" in p for p in problems), problems)

    def test_provenance_is_appended_to_every_evaluation_and_blocks_pass(self):
        ev = _ev()
        ev["scenario"]["assertions"] = [{"id": "c", "check": "bots_joined"}]
        out = analyze.evaluate(ev)
        self.assertEqual([r["check"] for r in out], ["bots_joined", "provenance", "host_quiet"])
        self.assertEqual(analyze.overall(out), analyze.INCONCLUSIVE)

    def test_player_record_reads_the_build_provenance_files(self):
        from lab import provenance
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "verify-build"
            exe = root / "StandaloneWindows64" / "IndieRPGMMOAdventure.exe"
            _write(exe, "stub")
            _write(exe.parent / "IndieRPGMMOAdventure_Data" / "Managed" / "NDC.Scripts.dll", "code")
            _write(root / "VERIFY-PROVENANCE.txt", "netcode 5fa8f37fb74b963fb34582e0d44610f8c49f130f client 47ec933\n")
            _write(root / "testlab-build.json", json.dumps({"client_head": "47ec933", "embedded_packages": [
                {"name": "com.cuvara.netcode", "version": "0.48.0", "cs_sha256": "8036"}]}))
            rec = provenance.player_record(exe)
            self.assertEqual(rec["netcode"]["sha"], "5fa8f37fb74b963fb34582e0d44610f8c49f130f")
            self.assertTrue(rec["netcode"]["embedded"])
            self.assertEqual(rec["built_from_client"], "47ec933")
            self.assertEqual(len(rec["exe_sha256"]), 64)
            self.assertEqual(len(rec["managed_sha256"]), 64)
            _write(exe.parent / "IndieRPGMMOAdventure_Data" / "Managed" / "NDC.Scripts.dll", "other code")
            self.assertNotEqual(provenance.player_record(exe)["managed_sha256"], rec["managed_sha256"])

    def test_results_name_the_run_they_analyse(self):
        from lab import report
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            out = Path(d) / "elsewhere"
            ev = analyze.load_evidence(run)
            results = analyze.evaluate(ev)
            doc = report.write(run, ev, results, analyze.overall(results), None, out_dir=out)
            self.assertEqual(doc["analysis"]["run_id"], run.name)
            self.assertEqual(doc["analysis"]["run_dir_name"], run.name)
            self.assertEqual(doc["analysis"]["provenance"], analyze.PASS)
            self.assertTrue((out / "results.json").exists())
            self.assertFalse((run / "results.json").exists())  # --out never writes into the run dir


class ScratchIsolationTests(unittest.TestCase):
    def _cfg(self, d, **kw):
        from lab import config
        return config.LabConfig(workspace=Path(d), runs_root=Path(d), **kw)

    def test_container_filter_matches_only_scratch_containers(self):
        from unittest import mock
        from lab import stack
        listing = ("rpg-gameserver\tUp 2 hours\nrpg-redis\tUp 2 hours\nrpgs-gameserver\tUp 1 minute\n"
                   "rpgs-redis\tExited (0)\nrpg-nakama\tUp\nmy-rpgs-x\tUp\nrpgsx-y\tUp\n")
        done = __import__("subprocess").CompletedProcess([], 0, listing, "")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stack.util, "wsl", return_value=done):
            self.assertEqual(sorted(stack.scratch_containers(self._cfg(d))), ["rpgs-gameserver", "rpgs-redis"])
            # A misconfigured prefix cannot widen the filter to the default stack.
            for bad in ("rpg-", "rpg", ""):
                self.assertEqual(stack.scratch_containers(self._cfg(d, container_prefix=bad)), {}, bad)

    def test_actions_on_a_non_scratch_container_are_refused(self):
        from unittest import mock
        from lab import stack
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stack.util, "wsl") as wsl:
            cfg = self._cfg(d, gameserver_container="rpg-gameserver", redis_container="rpg-redis")
            for fn in (stack.restart_gameserver, stack.down, stack.docker_stats,
                       lambda c: stack.redis_cli(c, "ping"),
                       lambda c: stack.fetch_snapshot_trace(c, Path(d) / "t.csv")):
                with self.assertRaises(stack.StackError):
                    fn(cfg)
            wsl.assert_not_called()

    def test_snapshot_trace_sets_the_server_env_and_needs_the_compose_passthrough(self):
        from lab import stack
        self.assertNotIn("GAMESERVER_SNAPSHOT_TRACE", stack.env_for({"map": "map_01"}))
        env = stack.env_for({"map": "map_01", "snapshot_trace": True})
        self.assertEqual(env["GAMESERVER_SNAPSHOT_TRACE"], stack.SNAPSHOT_TRACE_PATH)
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d, server_repo=Path(d))
            compose = Path(d) / "backend" / "deploy" / "docker-compose.yml"
            _write(compose, "services:\n  gameserver:\n    environment:\n      GAMESERVER_DEBUG_ENTITIES: ${X:-}\n")
            self.assertFalse(stack.compose_forwards(cfg, "GAMESERVER_SNAPSHOT_TRACE"))
            _write(compose, compose.read_text() + "      GAMESERVER_SNAPSHOT_TRACE: ${GAMESERVER_SNAPSHOT_TRACE:-}\n")
            self.assertTrue(stack.compose_forwards(cfg, "GAMESERVER_SNAPSHOT_TRACE"))


class CleanupTests(unittest.TestCase):
    """Every run stops its players on success, failure, timeout and Ctrl-C; every invocation stops
    the scratch stack unless asked to keep it."""

    def _patched_run(self, d, wait_phase_effect):
        from unittest import mock
        from lab import clients, config, runner, stack, provenance
        exe = Path(d) / "build" / "StandaloneWindows64" / "IndieRPGMMOAdventure.exe"
        _write(exe, "stub")
        _write(exe.parent / "IndieRPGMMOAdventure_Data" / "Managed" / "NDC.TestLab.dll", "lab")
        cfg = config.LabConfig(workspace=Path(d), runs_root=Path(d) / "runs-root", player_exe=exe,
                               server_repo=Path(d) / "server", client_project=Path(d) / "client")
        stopped = []

        def fake_launch(cfg_, sc, p, plan, control):
            p.proc, p.pid = None, 4242
            p.history.append({"event": "launch", "pid": 4242})

        class FakeProbe:
            def __init__(self, cfg_, out, entity_hz):
                self.out, self.start_mono, self.counts = out, None, {"entities": 0}
                out.mkdir(parents=True, exist_ok=True)

            def scrape_metrics(self, name):
                (self.out / f"metrics-{name}.txt").write_text("", encoding="utf-8")

            def start(self):
                pass

            def stop(self):
                pass

        def fake_stop(players):
            stopped.extend(p.index for p in players)
            return ["stopped"]

        patches = [
            mock.patch.object(runner, "_host_load", return_value={"cpu_load_pct": 1.0, "free_mem_mb": 1}),
            mock.patch.object(clients, "clean_orphans", return_value=[]),
            mock.patch.object(stack, "preflight", return_value={"conflicts": []}),
            mock.patch.object(stack, "ensure", return_value={"actions": []}),
            mock.patch.object(provenance, "docker_image_id", return_value="sha256:" + "0" * 64),
            mock.patch.object(runner, "ServerProbe", FakeProbe),
            mock.patch.object(clients, "launch", side_effect=fake_launch),
            mock.patch.object(clients, "wait_phase", side_effect=wait_phase_effect),
            mock.patch.object(clients, "stop", side_effect=fake_stop),
            mock.patch.object(runner.time, "sleep"),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return cfg, stopped

    def _run_json(self, cfg):
        runs = list((cfg.runs_root / "runs").iterdir())
        self.assertEqual(len(runs), 1)
        return json.loads((runs[0] / "run.json").read_text(encoding="utf-8"))

    def test_ctrl_c_stops_players_records_the_run_and_reraises(self):
        from lab import runner
        with tempfile.TemporaryDirectory() as d:
            cfg, stopped = self._patched_run(d, KeyboardInterrupt)
            with self.assertRaises(KeyboardInterrupt):
                runner.run(cfg, "S01", quiet=True)
            self.assertEqual(stopped, [0, 1, 2])
            meta = self._run_json(cfg)
            self.assertIn("KeyboardInterrupt", meta["harness_error"])
            self.assertEqual(meta["provenance"]["run_id"], meta["run_id"])
            self.assertEqual(json.loads((cfg.runs_root / "active-pids.json").read_text()), {})

    def test_a_join_timeout_stops_players_and_is_never_pass(self):
        from lab import clients, runner
        with tempfile.TemporaryDirectory() as d:
            cfg, stopped = self._patched_run(d, clients.ClientError("timeout after 120s waiting for all clients"))
            res = runner.run(cfg, "S01", quiet=True)
            self.assertEqual(stopped, [0, 1, 2])
            self.assertEqual(res["outcome"], analyze.INCONCLUSIVE)
            self.assertIn("timeout", self._run_json(cfg)["harness_error"])

    def test_every_invocation_stops_the_scratch_stack(self):
        from unittest import mock
        import testlab as cli
        from lab import runner, stack
        for effect, keep in ((None, False), (KeyboardInterrupt, False), (RuntimeError("boom"), False), (None, True)):
            with mock.patch.object(stack, "down", return_value="down") as down, \
                    mock.patch.object(runner, "run", side_effect=effect,
                                      return_value={"outcome": "PASS", "assertions": [], "run_id": "r"}):
                args = cli.main.__globals__["argparse"].Namespace(
                    scenarios=["S01"], build_server=False, keep_clients=False, keep_stack=keep, duration=None,
                    clients=None, snapshot_trace=False, config=None, server_repo=None, player=None, project=None,
                    runs_root=None)
                if effect is None:
                    self.assertEqual(cli.cmd_run(args), 0)
                else:
                    with self.assertRaises(effect if isinstance(effect, type) else type(effect)):
                        cli.cmd_run(args)
                self.assertEqual(down.call_count, 0 if keep else 1, (effect, keep))

    def test_git_bash_paths_reach_windows_python_converted(self):
        import testlab as cli
        if util.IS_WINDOWS:
            self.assertEqual(str(cli._path("/c/Workspaces/x")), "C:\\Workspaces\\x")
        self.assertEqual(cli._path("relative/run"), Path("relative/run"))


class LeakCheckTests(unittest.TestCase):
    def _player(self, root: Path, files: dict) -> Path:
        exe = root / "StandaloneWindows64" / "Game.exe"
        _write(exe, "stub")
        for name, data in files.items():
            p = exe.parent / "Game_Data" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return root

    def test_a_production_build_is_clean(self):
        from lab import leakcheck
        with tempfile.TemporaryDirectory() as d:
            root = self._player(Path(d), {"Managed/NDC.Scripts.DI.dll": b"MZ GameplayInput DeviceGameplayInputSource",
                                          "ScriptingAssemblies.json": b'{"names":["NDC.Scripts.DI.dll"]}'})
            for target in (root, root / "StandaloneWindows64", root / "StandaloneWindows64" / "Game.exe",
                           root / "StandaloneWindows64" / "Game_Data" / "Managed"):
                res = leakcheck.inspect(target)
                self.assertEqual(res["verdict"], "CLEAN", target)
                self.assertEqual(res["backend"], "mono")

    def test_testlab_assembly_types_and_define_are_found(self):
        from lab import leakcheck
        cases = {
            "assembly file": {"Managed/NDC.TestLab.dll": b"MZ"},
            "type in another assembly": {"Managed/NDC.Scripts.DI.dll": b"MZ\x00ScriptedInputSource\x00"},
            "utf-16 user string": {"Managed/Assembly-CSharp.dll": "CUVARA_TESTLAB".encode("utf-16-le")},
            "assembly list": {"Managed/NDC.Scripts.dll": b"MZ", "ScriptingAssemblies.json": b'["NDC.TestLab.dll"]'},
            "il2cpp metadata": {"il2cpp_data/Metadata/global-metadata.dat": b"\x00TestLabRunner\x00"},
        }
        for label, files in cases.items():
            with tempfile.TemporaryDirectory() as d:
                res = leakcheck.inspect(self._player(Path(d), files))
                self.assertEqual(res["verdict"], "TESTLAB_PRESENT", label)

    def test_no_player_is_an_error_not_clean(self):
        from lab import leakcheck
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(leakcheck.inspect(Path(d))["verdict"], "ERROR")
            _write(Path(d) / "X_Data" / "readme.txt", "")
            self.assertEqual(leakcheck.inspect(Path(d))["verdict"], "ERROR")

    def test_cli_exit_codes(self):
        import testlab as cli
        with tempfile.TemporaryDirectory() as d:
            clean = self._player(Path(d) / "clean", {"Managed/NDC.Scripts.dll": b"MZ"})
            lab = self._player(Path(d) / "lab", {"Managed/NDC.TestLab.dll": b"MZ"})
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["leak-check", str(clean)]), 0)
                self.assertEqual(cli.main(["leak-check", str(lab)]), 1)
                self.assertEqual(cli.main(["leak-check", str(lab), "--expect-testlab"]), 0)
                self.assertEqual(cli.main(["leak-check", str(clean), "--expect-testlab"]), 1)
                self.assertEqual(cli.main(["leak-check", str(Path(d) / "none")]), 3)


# =========================================================================== delivery path (#473)

TICK_US = 1_000_000 // 60  # 60 Hz world ticks; snapshots every 4 ticks (15 Hz)
SNAP_TICKS = 4


def _c1_row(uid, tick, write_us, *, enqueue_lag=1000, queue_depth=0, dropped=0, wait_snd=0, retrans=0):
    gather = write_us - enqueue_lag - 500
    return (f"conn-{uid},{uid},{tick},{gather},{write_us - enqueue_lag},{write_us},{write_us + 200},900,"
            f"{queue_depth},{dropped},{wait_snd},128,128,{retrans},200")


class DeliveryFixture:
    """A synthetic run: N clients receiving snapshots every 4 ticks, with the server writing them on
    a 60 Hz clock; individual snapshots can be delayed at one stage of the path."""

    def __init__(self, root: Path, clients=2, snaps=200, c1=True, c2=True):
        self.run = root / "20260101T000000Z-T-dlvr"
        self.clients, self.snaps, self.c1, self.c2 = clients, snaps, c1, c2
        self.delays = {}  # (client or None, snap index) -> dict(stage=..., ms=...)

    def delay(self, idx, stage, ms, client=None, **kw):
        self.delays[(client, idx)] = {"stage": stage, "ms": ms, **kw}
        return self

    def _d(self, ci, idx):
        return self.delays.get((ci, idx)) or self.delays.get((None, idx))

    def build(self) -> Path:
        sc = _scenario(clients=self.clients)
        _write(self.run / "scenario.json", json.dumps(sc))
        _write(self.run / "run.json", json.dumps({"run_id": self.run.name}))
        server = ["conn_id,user_id,world_tick,gather_us,enqueue_us,write_start_us,write_end_us,bytes,queue_depth,"
                  "dropped_oldest_total,kcp_wait_snd,kcp_snd_wnd,kcp_rmt_wnd,kcp_retrans_total,kcp_rto_ms"]
        for ci in range(self.clients):
            uid = f"user-{ci}"
            _write(self.run / f"client-{ci}" / "summary.json", json.dumps({"user_id": uid}))
            deliv = ["world_tick,recv_us,applied_us,bytes,full,entities,frame"]
            render = ["frame,t_us,render_tick,clock_newest_tick,newest_tick,newest_recv_us,snapshot_age_ms"]
            frames = ["frame,t,dt_ms,scenario_t"]
            ndjson = []
            server_shift = client_shift = 0
            retrans = 0
            offset_us = 5_000_000 + ci * 777_000  # each player has its own clock origin
            for k in range(self.snaps):
                tick = 1000 + k * SNAP_TICKS
                d = self._d(ci, k)
                stage = d["stage"] if d else None
                extra = d["ms"] * 1000 if d else 0
                write = tick * TICK_US + server_shift + (extra if stage in ("server", "queue") else 0)
                if stage == "server":
                    server_shift += 0  # a one-off late write
                lag = 1000 + (extra if stage == "queue" else 0)
                if stage == "kcp":
                    retrans += 3
                wait = 40 if stage == "kcp" else 0
                server.append(_c1_row(uid, tick, write, enqueue_lag=lag, wait_snd=wait, retrans=retrans))
                recv = offset_us + tick * TICK_US + 30_000 + (extra if stage in ("server", "queue", "kcp", "path", "client") else 0)
                deliv.append(f"{tick},{recv if self.c2 else ''},{recv + 400},900,0,6,{k}")
                ndjson.append(json.dumps({"t": (recv + 400) / 1e6, "tick": tick}))
                render.append(f"{k},{offset_us + tick * TICK_US + 38_000},{tick - 6},{tick},{tick},{recv},8.0")
                if stage == "client":
                    frames.append(f"{k},{recv / 1e6:.6f},{extra / 1000 + 5:.3f},1")
            _write(self.run / f"client-{ci}" / "delivery.csv", "\n".join(deliv) + "\n")
            _write(self.run / f"client-{ci}" / "snapshots.ndjson", "\n".join(ndjson) + "\n")
            _write(self.run / f"client-{ci}" / "frames.csv", "\n".join(frames) + "\n")
            _write(self.run / f"client-{ci}" / "render.csv", "\n".join(render) + "\n")
        if self.c1:
            _write(self.run / "server" / "snapshot-trace.csv", "\n".join(server) + "\n")
        return self.run


class DeliveryTests(unittest.TestCase):
    def _analyze(self, fx):
        from lab import delivery
        return delivery.analyze(fx.build())

    def _only_gap(self, doc, client="0"):
        gaps = doc["clients"][client]["gaps"]
        self.assertEqual(len(gaps), 1, gaps)
        return gaps[0]

    def test_each_cause_gets_its_class(self):
        for stage, cls in (("server", "SERVER_LATE"), ("queue", "QUEUE"), ("kcp", "KCP"), ("path", "PATH"),
                           ("client", "CLIENT")):
            with tempfile.TemporaryDirectory() as d:
                doc = self._analyze(DeliveryFixture(Path(d)).delay(100, stage, 400, client=0))
                g = self._only_gap(doc)
                self.assertEqual(g["class"], cls, (stage, g))
                self.assertEqual(g["scope"], "SINGLE-CLIENT", stage)
                self.assertEqual(doc["completeness"], "COMPLETE")

    def test_a_gap_every_client_shares_is_all_clients(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self._analyze(DeliveryFixture(Path(d), clients=3).delay(100, "server", 400))
            for c in ("0", "1", "2"):
                g = self._only_gap(doc, c)
                self.assertEqual((g["class"], g["scope"]), ("SERVER_LATE", "ALL-CLIENTS"))

    def test_without_the_server_trace_server_classes_are_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self._analyze(DeliveryFixture(Path(d), c1=False).delay(100, "queue", 400, client=0))
            self.assertEqual(self._only_gap(doc)["class"], "UNKNOWN")
            self.assertEqual(doc["completeness"], "INCOMPLETE")
            self.assertTrue(any("server trace" in m for m in doc["missing"]))

    def test_without_c2_recv_us_path_is_unknown_never_pass(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self._analyze(DeliveryFixture(Path(d), c2=False).delay(100, "path", 400, client=0))
            g = self._only_gap(doc)
            self.assertEqual(g["class"], "UNKNOWN")
            self.assertIn("recv_us", g["reason"])
            self.assertEqual(doc["clients"]["0"]["recv_source"], "applied_us")
            self.assertEqual(doc["completeness"], "INCOMPLETE")

    def test_pre_c2_recorder_falls_back_to_main_thread_time(self):
        with tempfile.TemporaryDirectory() as d:
            fx = DeliveryFixture(Path(d)).delay(100, "client", 400, client=0)
            run = fx.build()
            for ci in range(2):
                (run / f"client-{ci}" / "delivery.csv").unlink()
            from lab import delivery
            doc = delivery.analyze(run)
            self.assertEqual(doc["clients"]["0"]["recv_source"], "t")
            self.assertEqual(self._only_gap(doc)["class"], "CLIENT")

    def test_minus_one_fields_are_unknown_not_zero(self):
        from lab import delivery
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.csv"
            _write(p, "conn_id,user_id,world_tick,gather_us,enqueue_us,write_start_us,write_end_us,bytes,queue_depth,"
                      "dropped_oldest_total,kcp_wait_snd,kcp_snd_wnd,kcp_rmt_wnd,kcp_retrans_total,kcp_rto_ms\n"
                      "c,u,10,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1\n")
            row = delivery.read_server_trace(p)["u"][10]
            self.assertTrue(all(v is None for k, v in row.items() if k not in ("conn_id", "world_tick")))
            self.assertIsNone(delivery.read_server_trace(Path(d) / "absent.csv"))
            gap = {"tick_a": 10, "tick_b": 14, "recv_a_us": 0, "recv_b_us": 400_000, "gap_us": 400_000}
            cls, why, _ = delivery.classify_gap(gap, {10: row, 14: row}, [], "recv_us", explain_fraction=0.5,
                                                slack_us=50_000)
            self.assertEqual(cls, "UNKNOWN", why)

    def test_buckets_report_send_and_receive_gaps_and_relative_one_way_delay(self):
        with tempfile.TemporaryDirectory() as d:
            # 5-minute buckets at 60 Hz ticks are 18000 ticks: 200 snapshots x 4 ticks fit in one.
            doc = self._analyze(DeliveryFixture(Path(d), clients=1).delay(100, "path", 400, client=0))
            b = doc["clients"]["0"]["buckets"][0]
            self.assertAlmostEqual(b["server_send_gap_ms"]["p50"], SNAP_TICKS * TICK_US / 1000, delta=0.1)
            self.assertAlmostEqual(b["client_recv_gap_ms"]["max"], SNAP_TICKS * TICK_US / 1000 + 400, delta=0.1)
            self.assertEqual(b["client_gaps_over_limit"], 1)
            # Each player's clock has a different origin; relative one-way delay removes it.
            self.assertEqual(b["one_way_rel_ms"]["p50"], 0.0)
            self.assertAlmostEqual(b["one_way_rel_ms"]["max"], 400.0, delta=0.1)
            self.assertEqual(self._only_gap(doc)["scope"], "UNKNOWN")  # no other client to compare with

    def test_cli_writes_delivery_files_where_asked(self):
        import contextlib
        import io
        import testlab as cli
        with tempfile.TemporaryDirectory() as d:
            run = DeliveryFixture(Path(d)).delay(10, "queue", 400, client=1).build()
            out = Path(d) / "out"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["analyze", "--delivery", str(run), "--out", str(out)]), 0)
            doc = json.loads((out / "delivery.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["classes"]["QUEUE"], 1)
            self.assertIn("QUEUE", (out / "delivery.md").read_text(encoding="utf-8"))
            self.assertFalse((run / "delivery.json").exists())


if __name__ == "__main__":
    unittest.main()
