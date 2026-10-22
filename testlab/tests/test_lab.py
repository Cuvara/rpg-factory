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


def _run_dir(root: Path, run_id="20260101T000000Z-T-abcd", *, netcode_embedded=True, netcode_sha="5fa8f37",
             scenario_kw=None):
    """A finished run directory with a complete provenance record."""
    from lab import provenance
    run = root / run_id
    sc = _scenario(clients=1, **(scenario_kw or {}))
    _write(run / "scenario.json", json.dumps(sc))
    # The full evidence inventory of a one-client run (provenance.expected_inventory).
    for rel in provenance.expected_inventory(sc)[1:]:  # [0] is scenario.json, written above
        _write(run / rel, "{}\n")
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

    def _problems(self, run):
        return self._status(run)["detail"]["problems"]

    def _manifest(self, run, edit):
        meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
        edit(meta["provenance"]["manifest"])
        _write(run / "run.json", json.dumps(meta))

    def test_disruptions_are_hashed_and_tampering_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d), scenario_kw={"disruptions": [{"at_s": 1, "kind": "debug_kill", "client": 0}]})
            self.assertIn("disruptions.ndjson", json.loads((run / "run.json").read_text())["provenance"]["manifest"])
            self.assertEqual(self._status(run)["status"], analyze.PASS)
            _write(run / "disruptions.ndjson", '{"kind": "debug_kill", "ok": true}\n')  # rewritten after the run
            self.assertTrue(any("disruptions.ndjson changed" in p for p in self._problems(run)))

    def test_an_omitted_manifest_entry_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            self._manifest(run, lambda m: m.pop("client-0/samples.ndjson"))
            problems = self._problems(run)
            self.assertTrue(any("client-0/samples.ndjson is not in the manifest (omitted" in p for p in problems), problems)
        with tempfile.TemporaryDirectory() as d:  # an inventory file never written at all
            run = _run_dir(Path(d))
            (run / "server" / "metrics-end.txt").unlink()
            self._manifest(run, lambda m: m.pop("server/metrics-end.txt"))
            self.assertEqual(self._status(run)["status"], analyze.INCONCLUSIVE)

    def test_a_scenario_with_disruptions_needs_their_record(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d), scenario_kw={"disruptions": [{"at_s": 1, "kind": "debug_kill", "client": 0}]})
            (run / "disruptions.ndjson").unlink()
            self._manifest(run, lambda m: m.pop("disruptions.ndjson"))
            self.assertTrue(any("disruptions.ndjson is not in the manifest" in p for p in self._problems(run)))

    def test_an_evidence_file_added_after_the_run_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            _write(run / "disruptions.ndjson", '{"kind": "debug_kill", "ok": true}\n')
            self.assertTrue(any("disruptions.ndjson is not in the manifest (added after the run)" in p
                                for p in self._problems(run)))

    def test_complete_matching_record_passes(self):
        with tempfile.TemporaryDirectory() as d:
            res = self._status(_run_dir(Path(d)))
            self.assertEqual(res["status"], analyze.PASS, res["detail"])
            self.assertEqual(res["measured"]["evidence_files"], 14)  # 2 root + 5 server + 7 client

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
            mock.patch.object(stack, "image_revision", return_value=None),
            mock.patch.object(stack, "check_nakama_module"),
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

    def __init__(self, root: Path, clients=2, snaps=200, c1=True, c2=True, drift=0.0, bin_jitter_ms=0):
        self.run = root / "20260101T000000Z-T-dlvr"
        self.clients, self.snaps, self.c1, self.c2 = clients, snaps, c1, c2
        # drift: client clock rate relative to the server's (0.08 = client runs 8 % fast);
        # bin_jitter_ms: extra delay that alternates every 3 s, so no clean delay floor exists.
        self.drift, self.bin_jitter_ms = drift, bin_jitter_ms
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
                jitter = self.bin_jitter_ms * 1000 * ((tick * TICK_US // 3_000_000) % 2)
                recv = offset_us + int(tick * TICK_US * (1 + self.drift)) + 30_000 + jitter + (
                    extra if stage in ("server", "queue", "kcp", "path", "client") else 0)
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

    def test_clock_rate_drift_is_fitted_and_removed(self):
        # The WSL VM clock was measured 7.3 % slow against Windows (t06): test 7 % and 9 % both ways.
        for drift in (0.07, 0.09, -0.07, -0.09):
            with tempfile.TemporaryDirectory() as d:
                doc = self._analyze(DeliveryFixture(Path(d), clients=1, snaps=900, drift=drift)
                                    .delay(450, "path", 400, client=0))
                c = doc["clients"]["0"]
                self.assertTrue(c["clock_fit"]["ok"], c["clock_fit"])
                self.assertAlmostEqual(c["clock_fit"]["rate"], 1 + drift, delta=0.001)
                owd = [b["one_way_rel_ms"] for b in c["buckets"] if b["one_way_rel_ms"]["n"]]
                # 60 s of snapshots: uncorrected, the relative delay would sweep |drift| x 60 s = 4.2-5.4 s.
                self.assertLess(max(o["p99"] for o in owd), 5.0, (drift, owd))
                self.assertAlmostEqual(max(o["max"] for o in owd), 400.0, delta=5.0)
                self.assertEqual(self._only_gap(doc)["class"], "PATH")

    def test_server_durations_are_converted_to_client_time(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self._analyze(DeliveryFixture(Path(d), clients=1, snaps=900, drift=0.08))
            b = doc["clients"]["0"]["buckets"][0]
            self.assertAlmostEqual(b["server_send_gap_ms"]["p50"], SNAP_TICKS * TICK_US / 1000 * 1.08, delta=0.2)
            self.assertEqual(doc["clients"]["0"]["server_durations"], "client time (rate-corrected)")

    def test_a_poor_clock_fit_reports_one_way_delay_as_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self._analyze(DeliveryFixture(Path(d), clients=1, snaps=900, bin_jitter_ms=200))
            c = doc["clients"]["0"]
            self.assertFalse(c["clock_fit"]["ok"])
            self.assertTrue(c["one_way_delay"].startswith("unavailable"))
            self.assertTrue(all(b["one_way_rel_ms"]["p50"] is None for b in c["buckets"]))

    def test_fit_clock_needs_enough_points(self):
        from lab import delivery
        self.assertFalse(delivery.fit_clock([(1, 2)] * 3)["ok"])
        pts = [(k * 100_000, 5_000_000 + int(k * 100_000 * 1.08)) for k in range(200)]
        fit = delivery.fit_clock(pts)
        self.assertTrue(fit["ok"])
        self.assertAlmostEqual(fit["rate"], 1.08, places=4)

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


# =========================================================================== readiness checks (COVERAGE F1-F6)

def _snap_rows(ticks, t0=10.0, dt=1 / 15):
    return [{"t": t0 + k * dt, "tick": tick} for k, tick in enumerate(ticks)]


class SnapshotOrderTests(unittest.TestCase):
    def _ev(self, *tick_lists, events=None):
        ev = _ev(clients=len(tick_lists))
        for c, ticks in zip(ev["clients"], tick_lists):
            c["snapshots"] = _snap_rows(ticks)
            c["events"] = list(events or [])
        return ev

    def test_increasing_ticks_pass(self):
        ev = self._ev(list(range(100, 200, 4)), list(range(100, 200, 4)))
        self.assertEqual(analyze.check_snapshot_order(ev, {})["status"], analyze.PASS)

    def test_a_backward_tick_or_a_duplicate_fails(self):
        ticks = list(range(100, 200, 4))
        back = ticks[:10] + [ticks[5]] + ticks[10:]
        res = analyze.check_snapshot_order(self._ev(back), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["measured"]["duplicates"], 1)  # tick seen before in this session
        older = ticks[:10] + [ticks[5] + 1] + ticks[10:]
        res = analyze.check_snapshot_order(self._ev(older), {})
        self.assertEqual((res["status"], res["measured"]["backward"]), (analyze.FAIL, 1))

    def test_a_new_session_may_restart_the_ticks(self):
        ticks = list(range(1000, 1100, 4)) + list(range(4, 100, 4))  # server restarted at row 25
        restart_t = 10.0 + 25 / 15 - 0.01
        events = [{"event": "net_state", "state": "InWorld", "t": 9.0},
                  {"event": "net_state", "state": "Connecting", "t": restart_t - 0.5},
                  {"event": "net_state", "state": "InWorld", "t": restart_t}]
        self.assertEqual(analyze.check_snapshot_order(self._ev(ticks, events=events), {})["status"], analyze.PASS)
        # The same restart without a new session is ticks running backwards.
        self.assertEqual(analyze.check_snapshot_order(self._ev(ticks, events=events[:1]), {})["status"], analyze.FAIL)

    def test_c2_delivery_csv_is_checked_too(self):
        with tempfile.TemporaryDirectory() as d:
            ev = self._ev(list(range(100, 200, 4)))
            p = Path(d) / "delivery.csv"
            _write(p, "world_tick,recv_us,applied_us,bytes,full,entities,frame\n"
                      "100,,10000000,,0,1,1\n104,,10066000,,0,1,2\n96,,10133000,,0,1,3\n" +
                      "".join(f"{108 + 4 * k},,{10200000 + 66000 * k},,0,1,{4 + k}\n" for k in range(10)))
            ev["clients"][0]["delivery_csv"] = p
            res = analyze.check_snapshot_order(ev, {})
            self.assertEqual(res["status"], analyze.FAIL)
            self.assertEqual(res["detail"]["per_client"][0]["delivery.csv"]["backward"], 1)

    def test_too_few_snapshots_is_inconclusive(self):
        self.assertEqual(analyze.check_snapshot_order(self._ev([1, 2, 3]), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_snapshot_order(_ev(clients=0), {})["status"], analyze.INCONCLUSIVE)


def _enemy_row(st, positions):
    return _row(st, [[f"e{i}", "mob", x, y, 10, 10, 0, 2.5] for i, (x, y) in enumerate(positions)])


class EnemyBoundsTests(unittest.TestCase):
    MAP = {"bounds": {"minX": -20, "minY": -20, "maxX": 20, "maxY": 20},
           "boxes": [{"minX": -4, "minY": 4, "minZ": 0, "maxX": -2, "maxY": 6, "maxZ": 0.3},
                     {"minX": 5, "minY": 5, "minZ": 0, "maxX": 8, "maxY": 8, "maxZ": 3}]}

    def _ev(self, d, positions, map_id="dev_arena", env_map="dev_arena"):
        _write(Path(d) / "backend" / "content" / "maps" / "dev_arena.json", json.dumps(self.MAP))
        ev = _ev(entities=[_enemy_row(1 + i * 0.2, positions) for i in range(30)], duration=10, map=map_id)
        ev["meta"] = {"config": {"server_repo": str(d)}, "stack": {"env": {"GAMESERVER_MAP_ID": env_map}}}
        ev["redis"] = {"session_keys": 1, "map_members": [f"gs-dotnet-{map_id}"]}
        return ev

    def test_inside_bounds_passes_outside_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(analyze.check_enemy_bounds(self._ev(d, [(0, 0), (19.9, -19.9)]), {})["status"], analyze.PASS)
            res = analyze.check_enemy_bounds(self._ev(d, [(0, 0), (20.5, 0)]), {})
            self.assertEqual(res["status"], analyze.FAIL)
            self.assertEqual(res["measured"]["outside_bounds"], 30)

    def test_blocking_boxes_are_reported_and_steps_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(analyze.check_enemy_bounds(self._ev(d, [(-3, 5), (0, 0)]), {})["status"], analyze.PASS)
            ev = self._ev(d, [(6, 6), (0, 0)])
            self.assertEqual(analyze.check_enemy_bounds(ev, {})["status"], analyze.INFO)
            self.assertEqual(analyze.check_enemy_bounds(ev, {"obstacles_are_failure": True})["status"], analyze.FAIL)

    def test_no_map_file_or_unclear_map_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            res = analyze.check_enemy_bounds(self._ev(d, [(0, 0)] * 3, map_id="map_01", env_map="map_01"), {})
            self.assertEqual(res["status"], analyze.INCONCLUSIVE)
            self.assertIn("does not exist", res["detail"]["why"])
            ev = self._ev(d, [(0, 0)] * 3, map_id="dev_arena", env_map="map_01")
            self.assertEqual(analyze.check_enemy_bounds(ev, {})["status"], analyze.INCONCLUSIVE)
            ev = self._ev(d, [(0, 0)])  # 30 positions < 50
            self.assertEqual(analyze.check_enemy_bounds(ev, {})["status"], analyze.INCONCLUSIVE)


class EnemyBudgetTests(unittest.TestCase):
    def _ev(self, alive, ai="chase=on max=30+45/player budget=10 seed=1", cap=10, ents=None):
        status = [{"_st": 1 + i, "enemy_ai": ai, "enemies_alive": n, "enemy_ai_max_now": cap} for i, n in enumerate(alive)]
        return _ev(duration=30, status=status, entities=ents or [])

    def test_at_most_the_reported_budget_passes(self):
        res = analyze.check_enemy_budget(self._ev([5] * 5 + [10] * 10), {})
        self.assertEqual(res["status"], analyze.PASS)
        self.assertEqual(res["measured"]["budget"], [10])
        self.assertTrue(res["measured"]["budget_reached"])

    def test_one_over_the_budget_fails(self):
        self.assertEqual(analyze.check_enemy_budget(self._ev([10] * 14 + [11]), {})["status"], analyze.FAIL)
        ents = [_enemy_row(1 + i, [(k, 0) for k in range(12)]) for i in range(3)]
        self.assertEqual(analyze.check_enemy_budget(self._ev([10] * 15, ents=ents), {})["status"], analyze.FAIL)

    def test_without_a_reported_budget_it_is_inconclusive(self):
        self.assertEqual(analyze.check_enemy_budget(self._ev([5] * 15, ai="chase=on max=30"), {})["status"],
                         analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_enemy_budget(self._ev([0] * 15, ai="off"), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_enemy_budget(self._ev([5] * 3), {})["status"], analyze.INCONCLUSIVE)


class RenderFreshnessTests(unittest.TestCase):
    """v2 render.csv: overrun = render_tick past clock_newest_tick, in ms at the server tick rate."""
    V2 = "frame,t_us,render_tick,clock_newest_tick,newest_tick,newest_recv_us,snapshot_age_ms,clock_source"

    def _ev(self, d, overruns_per_client, start=10.0, header=V2, hz=60):
        ev = _ev(clients=len(overruns_per_client), duration=10, status=[{"_st": 1, "tick_rate": hz}])
        for c, overruns in zip(ev["clients"], overruns_per_client):
            p = Path(d) / f"render-{c['index']}.csv"
            rows = [header]
            for k, o in enumerate(overruns):
                t_us = int((start + 0.5 + k * 0.016) * 1e6)
                newest = 1000 + k
                rt = "" if o is None else f"{newest + o / 1000.0 * hz:.3f}"
                cn = "" if o is None else str(newest)
                src = "" if o is None else "binder"
                cols = [str(k), str(t_us), rt, cn, str(newest), str(t_us - 30000), "30.0"]
                if "clock_source" in header:
                    cols.append(src)
                rows.append(",".join(cols))
            _write(p, "\n".join(rows) + "\n")
            c["render_csv"] = p
            c["summary"] = {"start_realtime": start}
        return ev

    def test_clock_behind_newest_passes_and_frozen_frames_fail(self):
        with tempfile.TemporaryDirectory() as d:
            # Normal: render clock TargetDelay (100 ms) behind the newest tick -> overrun 0.
            res = analyze.check_render_freshness(self._ev(d, [[-100] * 300] * 2), {})
            self.assertEqual(res["status"], analyze.PASS, res)
            self.assertEqual(res["threshold"]["overrun_p99_ms"], 50.0)
            self.assertEqual(res["measured"][0]["clock_source"], {"binder": 300})
            frozen = self._ev(d, [[-100] * 280 + [200] * 20, [-100] * 300])
            res = analyze.check_render_freshness(frozen, {})
            self.assertEqual(res["status"], analyze.FAIL)
            self.assertEqual(res["measured"][0]["frames_frozen"], 20)

    def test_overrun_is_converted_at_the_server_tick_rate(self):
        with tempfile.TemporaryDirectory() as d:
            ev = self._ev(d, [[40] * 300], hz=30)  # 40 ms at 30 Hz = 1.2 ticks
            self.assertAlmostEqual(analyze.check_render_freshness(ev, {})["measured"][0]["overrun_p99_ms"], 40.0, delta=0.1)

    def test_v1_render_csv_with_empty_render_tick_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            v1 = "frame,t_us,render_tick,clock_newest_tick,newest_tick,newest_recv_us,snapshot_age_ms"
            res = analyze.check_render_freshness(self._ev(d, [[None] * 300] * 2, header=v1), {})
            self.assertEqual(res["status"], analyze.INCONCLUSIVE)
            self.assertIn("v1 schema", res["detail"]["why"])

    def test_frozen_frames_only_inside_a_host_stall_are_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            ev = self._ev(d, [[-100] * 280 + [200] * 20] * 2)
            for c in ev["clients"]:
                c["frames"] = [(0.5 + 285 * 0.016, 800.0)]
            self.assertEqual(analyze.check_render_freshness(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_missing_c2_or_tick_rate_is_inconclusive(self):
        ev = _ev(clients=2, status=[{"_st": 1, "tick_rate": 60}])
        for c in ev["clients"]:
            c["summary"] = {"start_realtime": 1.0}
            c["render_csv"] = Path("does-not-exist.csv")
        self.assertEqual(analyze.check_render_freshness(ev, {})["status"], analyze.INCONCLUSIVE)
        with tempfile.TemporaryDirectory() as d:
            ev = self._ev(d, [[-100] * 300])
            ev["server"]["status"] = []
            self.assertEqual(analyze.check_render_freshness(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_delivery_parser_reads_v1_and_v2_render_csv(self):
        from lab import delivery
        with tempfile.TemporaryDirectory() as d:
            for header, extra in ((self.V2, ",binder"), (self.V2.rsplit(",", 1)[0], "")):
                _write(Path(d) / "render.csv", header + "\n" + f"1,1000000,99.5,104,104,980000,20.0{extra}\n"
                       + f"2,1016000,100.5,104,104,980000,36.0{extra}\n")
                frames, render = delivery.read_frames(Path(d))
                self.assertEqual(len(render), 2)
                self.assertEqual(render[0][2], 99.5)


class TickAdoptionTests(unittest.TestCase):
    def _ev(self, *rates, summary=None, status_hz=30):
        ev = _ev(clients=len(rates), status=[{"_st": 1, "tick_rate": status_hz}])
        for c, hz in zip(ev["clients"], rates):
            c["samples"] = [{"st": k * 0.5, "pred": {"tick_hz": hz}} for k in range(10)]
            c["summary"] = {"prediction": {"tick_hz": summary if summary is not None else hz}}
        return ev

    def test_predictor_at_the_advertised_rate_passes_any_other_fails(self):
        self.assertEqual(analyze.check_tick_adoption(self._ev(30, 30), {})["status"], analyze.PASS)
        self.assertEqual(analyze.check_tick_adoption(self._ev(30, 60), {})["status"], analyze.FAIL)
        ev = self._ev(30)
        ev["clients"][0]["samples"][7]["pred"]["tick_hz"] = 60  # a reconnect that kept the old rate
        self.assertEqual(analyze.check_tick_adoption(ev, {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_tick_adoption(ev, {"exclude_s": [[3, 4]]})["status"], analyze.PASS)

    def test_without_the_hook_or_the_server_rate_it_is_inconclusive(self):
        ev = _ev(clients=1, status=[{"_st": 1, "tick_rate": 60}])
        ev["clients"][0]["samples"] = [{"st": 1, "pred": {"snaps": 0}}]
        self.assertEqual(analyze.check_tick_adoption(ev, {})["status"], analyze.INCONCLUSIVE)
        ev = self._ev(30)
        ev["server"]["status"] = []
        self.assertEqual(analyze.check_tick_adoption(ev, {})["status"], analyze.INCONCLUSIVE)


def _sample(t, ents, render_tick=None, pred=None):
    s = {"t": t, "st": t - 100.0, "ents": ents}
    if render_tick is not None:
        s["render_tick"] = render_tick
    if pred is not None:
        s["pred"] = pred
    return s


class EntityLifecycleTests(unittest.TestCase):
    def _ev(self, events, drawn_until, reuse_at=None):
        """Entity 'm' drawn every 50 ms from t=100 until drawn_until (player clock)."""
        ev = _ev(clients=1, duration=20)
        c = ev["clients"][0]
        samples = []
        for k in range(200):
            t = 100.0 + k * 0.05
            ents = []
            if t < drawn_until or (reuse_at is not None and t >= reuse_at):
                ents.append(["m", "mob", 0, 1.0, 1.0, 1.0, 1.0])
            samples.append(_sample(t, ents))
        c["samples"], c["events"] = samples, events
        return ev

    ADD = {"event": "entity_added", "t": 100.0, "id": "m", "type": "mob", "tick": 10, "x": 1.0, "y": 1.0, "rx": 1.0, "ry": 1.0}

    def test_removed_entity_off_screen_within_the_grace_passes(self):
        ev = self._ev([self.ADD, {"event": "entity_removed", "t": 104.0, "id": "m", "rendered": True}], drawn_until=104.1)
        res = analyze.check_entity_lifecycle(ev, {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual(res["measured"]["removed"], 1)

    def test_a_removed_entity_still_drawn_is_a_ghost(self):
        ev = self._ev([self.ADD, {"event": "entity_removed", "t": 104.0, "id": "m"}], drawn_until=105.0)
        res = analyze.check_entity_lifecycle(ev, {})
        self.assertEqual((res["status"], res["measured"]["lingering"]), (analyze.FAIL, 1))

    def test_a_reused_id_must_start_at_its_own_spawn(self):
        removed = {"event": "entity_removed", "t": 104.0, "id": "m"}
        good = dict(self.ADD, t=106.0, tick=500, x=8.0, y=8.0, rx=8.1, ry=8.0)
        res = analyze.check_entity_lifecycle(self._ev([self.ADD, removed, good], drawn_until=104.1, reuse_at=106.0), {})
        self.assertEqual((res["status"], res["measured"]["reused_ids_checked"]), (analyze.PASS, 1))
        stale = dict(good, rx=1.0, ry=1.0)  # drawn where the previous entity was
        res = analyze.check_entity_lifecycle(self._ev([self.ADD, removed, stale], drawn_until=104.1, reuse_at=106.0), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["detail"]["reuse_drawn_elsewhere"][0]["from_previous_entity"], 0.0)

    def test_without_the_hook_or_a_removal_it_is_inconclusive(self):
        self.assertEqual(analyze.check_entity_lifecycle(self._ev([], drawn_until=200), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_entity_lifecycle(self._ev([self.ADD], drawn_until=200), {})["status"],
                         analyze.INCONCLUSIVE)


class CrossClientConvergenceTests(unittest.TestCase):
    def _ev(self, offset=0.0, render_tick=True):
        ev = _ev(clients=2, status=[{"_st": 1, "tick_rate": 60}])
        for c in ev["clients"]:
            samples = []
            phase = 0.013 * c["index"]  # the two clients sample at different instants
            for k in range(100):
                t = 103.0 + phase + k * 0.05
                tick = 1000 + (t - 103.0) * 60
                x = (tick - 1000) / 60 * 2.0  # 2 u/s along x, a function of the render tick
                if c["index"] == 1:
                    x += offset
                samples.append(_sample(t, [["e", "mob", 0, x, 0.0, x, 0.0]], tick if render_tick else None))
            c["samples"] = samples
        return ev

    def test_same_tick_same_place_passes(self):
        res = analyze.check_cross_client_convergence(self._ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertLess(res["measured"]["max"], 0.01)

    def test_a_client_drawing_elsewhere_fails(self):
        self.assertEqual(analyze.check_cross_client_convergence(self._ev(offset=0.6), {})["status"], analyze.FAIL)

    def test_without_render_tick_or_a_second_client_it_is_inconclusive(self):
        self.assertEqual(analyze.check_cross_client_convergence(self._ev(render_tick=False), {})["status"],
                         analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_cross_client_convergence(_ev(clients=1), {})["status"], analyze.INCONCLUSIVE)


class StallRecoveryTests(unittest.TestCase):
    def _ev(self, err_after, actual_ms=2000):
        # Server: player 'u' walks +x at 2 u/s; client 0 stalls 2 s at st 10-12 (t 110-112).
        ents = [_row(k * 0.2, [["u", "player", k * 0.2 * 2.0, 0.0, 100, 100, 0, 5]]) for k in range(150)]
        ev = _ev(clients=1, entities=ents, duration=30)
        c = ev["clients"][0]
        c["events"] = [{"event": "stall", "t": 110.0, "ms": 2000, "actual_ms": actual_ms, "start": 110.0, "end": 112.0}]
        samples = []
        for k in range(400):
            t = 100.0 + k * 0.05
            if 110.0 < t < 112.0:
                continue
            st = t - 100.0
            x, y = st * 2.0, (err_after if t > 112.0 else 0.0)  # off the path sideways
            samples.append(_sample(t, [["u", "player", 1, x, y, x, y]], pred={"snaps": 0 if t < 112 else 1}))
        c["samples"] = samples
        return ev

    def test_back_on_the_server_path_after_the_stall_passes(self):
        res = analyze.check_stall_recovery(self._ev(0.0), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual(res["measured"][0]["snaps_during"], 1)

    def test_still_off_the_path_after_recovery_fails(self):
        self.assertEqual(analyze.check_stall_recovery(self._ev(1.0), {})["status"], analyze.FAIL)

    def test_no_stall_or_a_short_stall_is_inconclusive(self):
        self.assertEqual(analyze.check_stall_recovery(_ev(clients=1), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_stall_recovery(self._ev(0.0, actual_ms=300), {})["status"], analyze.INCONCLUSIVE)


class GracefulLeaveTests(unittest.TestCase):
    def _ev(self, gone_at, outcome="left", others_removed=True):
        ents = [_row(k * 0.2, [["u0", "player", 0, 0, 100, 100, 0, 5], ["u1", "player", 1, 0, 100, 100, 0, 5]] +
                     ([["u2", "player", 2, 0, 100, 100, 0, 5]] if k * 0.2 < gone_at else [])) for k in range(150)]
        ev = _ev(clients=3, entities=ents, duration=30)
        for c in ev["clients"]:
            c["summary"] = {"user_id": f"u{c['index']}", "outcome": "completed"}
        leaver = ev["clients"][2]
        leaver["summary"]["outcome"] = outcome
        leaver["events"] = [{"event": "quit_requested", "st": 15.0}, {"event": "disconnected", "st": 15.05}]
        if others_removed:
            for c in ev["clients"][:2]:
                c["events"] = [{"event": "entity_removed", "id": "u2", "st": gone_at + 0.1}]
        return ev

    def test_a_polite_leave_removes_the_player_quickly(self):
        res = analyze.check_graceful_leave(self._ev(gone_at=15.4), {})
        self.assertEqual(res["status"], analyze.PASS, res)

    def test_lingering_until_the_idle_timeout_or_a_wrong_outcome_fails(self):
        self.assertEqual(analyze.check_graceful_leave(self._ev(gone_at=25.0), {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_graceful_leave(self._ev(gone_at=15.4, outcome="completed"), {})["status"],
                         analyze.FAIL)

    def test_without_a_quit_it_is_inconclusive(self):
        self.assertEqual(analyze.check_graceful_leave(_ev(clients=2), {})["status"], analyze.INCONCLUSIVE)

    def test_expected_outcomes_let_a_leaver_complete(self):
        ev = self._ev(gone_at=15.4)
        self.assertEqual(analyze.check_clients_completed(ev, {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_clients_completed(ev, {"expected_outcomes": {"2": "left"}})["status"], analyze.PASS)


class HookScenarioTests(unittest.TestCase):
    def test_one_shot_actions_expand_with_their_fields(self):
        plan = scenarios.client_plan(scenarios.load("S13"), 0, "r")
        stalls = [a for a in plan["actions"] if a["kind"] == "stall"]
        self.assertEqual([(a["t0"], a["t1"], a["ms"]) for a in stalls], [(10.0, 10.0, 500), (25.0, 25.0, 2000)])
        quit_ = [a for a in scenarios.client_plan(scenarios.load("S08G"), 2, "r")["actions"] if a["kind"] == "quit"]
        self.assertEqual(quit_[0]["t0"], 15.0)
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(_scenario(client_defaults={"steps": [], "actions": [{"t0": 1, "kind": "stall", "ms": 0}]}))

    def test_s13_judges_after_each_stall_and_excludes_them_from_cadence(self):
        sc = scenarios.load("S13")
        stalls = [a for a in sc["per_client"][0]["actions"] if a["kind"] == "stall"]
        windows = next(a for a in sc["assertions"] if a["check"] == "snapshot_cadence")["exclude_s"]
        for s, w in zip(stalls, windows):
            self.assertEqual(w[0], s["t0"])
            self.assertGreaterEqual(w[1], s["t0"] + s["ms"] / 1000.0)
        checks = {a["check"] for a in sc["assertions"]}
        self.assertTrue({"stall_recovery", "prediction_bound", "render_jumps"} <= checks)

    def test_s08g_expects_the_leaver_to_leave(self):
        sc = scenarios.load("S08G")
        by = {a["check"]: a for a in sc["assertions"]}
        self.assertEqual(by["clients_completed"]["expected_outcomes"], {"2": "left"})
        self.assertEqual(by["players_online"]["expected"], sc["clients"] - 1)
        self.assertNotIn("disruptions", {k for k, v in sc.items() if v})


class PredictionBoundTests(unittest.TestCase):
    """Snaps matched by world tick to server respawns/teleports of the same player are explained."""

    def _ev(self, snap_ticks, respawn_ticks=(), seconds=60.0, present=True, extra_summary_snaps=0):
        # Server: player 'u' sampled every 12 ticks (5 Hz at 60 Hz); dead one sample before each respawn tick.
        rows = []
        for k in range(int(seconds * 5) + 1):
            tick = 300 + k * 12
            dead = any(rt - 12 <= tick < rt for rt in respawn_ticks)
            moved = sum(1 for rt in respawn_ticks if tick >= rt) * 2.0  # respawn 2 units away
            rows.append({"st": k * 0.2, "tick": tick, "ents": [["u", "player", moved, 0.0, 0 if dead else 100, 100,
                                                                 1 if dead else 0, 5]]})
        ev = _ev(clients=1, entities=rows, duration=seconds)
        c = ev["clients"][0]
        samples, snaps = [], 0
        for k in range(int(seconds * 20)):
            tick = 300 + k * 3
            snaps += sum(1 for st in snap_ticks if tick - 3 < st <= tick)
            samples.append({"t": 100 + k * 0.05, "st": k * 0.05, "world_tick": tick, "pred": {"snaps": snaps}})
        c["samples"] = samples
        c["summary"] = {"user_id": "u", "scenario_seconds": seconds,
                        "prediction": {"present": present, "snaps": snaps + extra_summary_snaps, "max_correction": 2.0}}
        return ev

    def test_snaps_at_server_respawns_are_explained(self):
        respawns = [1500, 2600, 3700]
        res = analyze.check_prediction_bound(self._ev([r + 4 for r in respawns], respawns), {})  # S02 58sn pattern
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual((res["measured"][0]["explained_by_server_teleport"], res["measured"][0]["unexplained"]), (3, 0))

    def test_snaps_without_a_server_teleport_are_graded(self):
        snaps = [400 + 150 * k for k in range(20)]  # 20 unexplained in 60 s
        res = analyze.check_prediction_bound(self._ev(snaps), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["measured"][0]["unexplained"], 20)
        # A snap far from the respawn (outside the match window) is not explained by it.
        res = analyze.check_prediction_bound(self._ev([1500 + 200], [1500]), {})
        self.assertEqual(res["measured"][0]["explained_by_server_teleport"], 0)

    def test_bound_separates_the_measured_fixed_and_broken_rates(self):
        fixed = self._ev([400, 2000])  # 2 unexplained in 60 s: S07 c5hc client 2, the worst fixed build
        self.assertEqual(analyze.check_prediction_bound(fixed, {})["status"], analyze.PASS)
        broken = self._ev([400 + 300 * k for k in range(5)], seconds=40)  # 5 in 40 s = 7.5/min: S10 g0tz
        self.assertEqual(analyze.check_prediction_bound(broken, {})["status"], analyze.FAIL)

    def test_snaps_after_the_last_sample_count_as_unexplained(self):
        res = analyze.check_prediction_bound(self._ev([], extra_summary_snaps=2), {})
        self.assertEqual(res["measured"][0]["unexplained"], 2)

    def test_without_counters_samples_or_long_enough_window_it_is_inconclusive(self):
        self.assertEqual(analyze.check_prediction_bound(self._ev([], seconds=15), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_prediction_bound(self._ev([], present=False), {})["status"], analyze.INCONCLUSIVE)
        ev = self._ev([1000])
        ev["clients"][0]["samples"] = []
        self.assertEqual(analyze.check_prediction_bound(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_server_teleport_detection(self):
        ev = self._ev([], [1500])
        self.assertEqual(len(analyze._server_teleports(ev, "u", 6.0)), 1)
        rows = [{"st": k * 0.2, "tick": k * 12, "ents": [["u", "player", 0.0 if k < 5 else 9.0, 0, 100, 100, 0, 5]]}
                for k in range(10)]  # a 9-unit step in 0.2 s: not walkable
        self.assertEqual(analyze._server_teleports({"server": {"entities": rows}}, "u", 6.0), [(48, 60)])


class ServerConfigTests(unittest.TestCase):
    def test_rates_in_force_must_match_the_scenario(self):
        ev = _ev(duration=10, status=[{"_st": 1, "sim_critical_hz": 30, "sim_world_hz": 15}] * 3,
                 server_env={"SIM_CRITICAL_HZ": "30", "SIM_WORLD_HZ": "15"})
        self.assertEqual(analyze.check_server_config(ev, {})["status"], analyze.PASS)
        ev["server"]["status"][1] = {"_st": 2, "sim_critical_hz": 60, "sim_world_hz": 15}
        self.assertEqual(analyze.check_server_config(ev, {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_server_config(_ev(), {})["status"], analyze.INCONCLUSIVE)


class DisruptionWindowTests(unittest.TestCase):
    def test_cadence_leaves_out_an_expected_interruption(self):
        ev = _ev(clients=1, duration=60, status=[{"_st": 5, "sim_world_hz": 15}])
        c = ev["clients"][0]
        c["summary"] = {"start_realtime": 100.0}
        c["snapshots"] = [{"t": 100.0 + k / 15.0} for k in range(900) if not 20 * 15 <= k < 32 * 15]
        self.assertEqual(analyze.check_snapshot_cadence(ev, {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_snapshot_cadence(ev, {"exclude_s": [[20, 40]]})["status"], analyze.PASS)

    def test_clients_must_be_back_in_world_after_the_restart(self):
        ev = _ev(clients=2)
        for c in ev["clients"]:
            c["events"] = [{"event": "in_world", "st": -1}, {"event": "net_state", "state": "InWorld", "st": -1}]
        self.assertEqual(analyze.check_clients_in_world(ev, {})["status"], analyze.PASS)
        self.assertEqual(analyze.check_clients_in_world(ev, {"reentered_after_s": 20})["status"], analyze.FAIL)
        for c in ev["clients"]:
            c["events"].append({"event": "net_state", "state": "InWorld", "st": 27.5})
        self.assertEqual(analyze.check_clients_in_world(ev, {"reentered_after_s": 20})["status"], analyze.PASS)

    def test_s11_and_s12_are_consistent(self):
        s11 = scenarios.load("S11")
        restart = [d for d in s11["disruptions"] if d["kind"] == "restart_gameserver"]
        self.assertEqual(len(restart), 1)
        by_id = {a["id"]: a for a in s11["assertions"]}
        grace = by_id["snapshots"]["exclude_s"][0]
        self.assertEqual(grace[0], restart[0]["at_s"])
        for aid in ("local_divergence", "remote_player_divergence", "render_jumps"):
            self.assertEqual(by_id[aid]["skip_first_s"], grace[1], aid)
        self.assertEqual(by_id["in_world"]["reentered_after_s"], restart[0]["at_s"])
        s12 = scenarios.load("S12")
        crit, world = int(s12["server_env"]["SIM_CRITICAL_HZ"]), int(s12["server_env"]["SIM_WORLD_HZ"])
        # SimulationRates.TryCreate: every group divides the critical rate, none exceeds it, <= 240 Hz.
        self.assertTrue(crit <= 240 and world <= crit and crit % world == 0 and crit % 5 == 0)
        self.assertNotEqual(crit, 60)
        self.assertIn("server_config", {a["check"] for a in s12["assertions"]})


class NetcodeProvenanceTests(unittest.TestCase):
    def test_build_client_records_the_netcode_commit(self):
        import testlab as cli
        from lab import provenance
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d)
            _write(proj / "Packages" / "packages-lock.json", json.dumps({"dependencies": {"com.cuvara.netcode": {
                "version": "https://github.com/Cuvara/Netcode.git#v0.47.0", "source": "git",
                "hash": "1971df40301f69cf0731df6eb80151d58272ea75"}}}))
            rec = cli.netcode_provenance(proj)
            self.assertEqual((rec["embedded"], rec["sha"]), (False, "1971df40301f69cf0731df6eb80151d58272ea75"))
            nc = provenance.netcode_record({"embedded_packages": [], "netcode": rec}, None)
            self.assertEqual(nc["sha"], rec["sha"])
            # An embedded copy without .git cannot name its commit: provenance stays INCONCLUSIVE.
            _write(proj / "Packages" / "com.cuvara.netcode" / "package.json",
                   json.dumps({"name": "com.cuvara.netcode", "version": "0.48.0"}))
            rec = cli.netcode_provenance(proj)
            self.assertEqual((rec["embedded"], rec["sha"], rec["version"]), (True, None, "0.48.0"))
            with tempfile.TemporaryDirectory() as r:
                run = _run_dir(Path(r), netcode_sha=None)
                problems = analyze.check_provenance(analyze.load_evidence(run), {})["detail"]["problems"]
                self.assertTrue(any("netcode.sha missing" in p for p in problems), problems)


# =========================================================================== server hooks S1/S2/S4 (T20)

def _kill_record(st=12.0, ok=True, status=200, outcome="killed", client=1, uid="u1"):
    return {"kind": "debug_kill", "client": client, "st": st, "user_id": uid, "http_status": status, "ok": ok,
            "response": {"ok": ok, "outcome": outcome, "tick": 720, "hp_before": 100}, "server_tick": 720}


class DebugKillHarnessTests(unittest.TestCase):
    def test_debug_kill_posts_the_user_id_and_records_the_answer(self):
        from unittest import mock
        from lab import config, runner
        cfg = config.LabConfig(workspace=Path("."), runs_root=Path("."))
        player = mock.Mock()
        player.status.return_value = {"user_id": "u1"}
        with mock.patch.object(runner.util, "http_post_json", return_value=(200, {"outcome": "killed", "tick": 9})) as post:
            rec = runner.debug_kill(cfg, player)
        post.assert_called_once_with("http://127.0.0.1:9501/debug/kill", {"id": "u1"}, timeout=5)
        self.assertEqual((rec["ok"], rec["http_status"], rec["server_tick"]), (True, 200, 9))
        for status, body in ((404, {"outcome": "not_found"}), (409, {"outcome": "already_dead"}), (0, None)):
            with mock.patch.object(runner.util, "http_post_json", return_value=(status, body)):
                self.assertFalse(runner.debug_kill(cfg, player)["ok"], status)
        player.status.return_value = {}
        self.assertFalse(runner.debug_kill(cfg, player)["ok"])

    def test_disrupt_appends_the_record(self):
        from unittest import mock
        from lab import config, runner
        with tempfile.TemporaryDirectory() as d:
            cfg = config.LabConfig(workspace=Path(d), runs_root=Path(d))
            p = mock.Mock()
            p.status.return_value = {"user_id": "u1"}
            with mock.patch.object(runner.util, "http_post_json", return_value=(200, {"outcome": "killed", "tick": 9})):
                runner._disrupt(cfg, {}, {"at_s": 12, "kind": "debug_kill", "client": 0}, [p], [], None, lambda m: None,
                                Path(d))
            rows = util.read_ndjson(Path(d) / "disruptions.ndjson")
            self.assertEqual((rows[0]["kind"], rows[0]["ok"], rows[0]["at_s"]), ("debug_kill", True, 12))

    def test_scenario_disruption_needs_a_client(self):
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(_scenario(disruptions=[{"at_s": 1, "kind": "debug_kill"}]))
        scenarios.validate(_scenario(clients=2, disruptions=[{"at_s": 1, "kind": "debug_kill", "client": 1}]))


class DebugKillGatingTests(unittest.TestCase):
    def _ev(self, kills):
        ev = _ev(clients=1)
        ev["disruptions"] = kills
        ev["scenario"]["assertions"] = [{"id": "x", "check": "clients_in_world", "requires_debug_kill": True}]
        ev["clients"][0]["events"] = [{"event": "in_world"}]
        return ev

    def test_a_dependent_assertion_cannot_pass_without_a_confirmed_kill(self):
        self.assertEqual(analyze.evaluate(self._ev([]))[0]["status"], analyze.INCONCLUSIVE)
        failed = self._ev([_kill_record(ok=False, status=404, outcome="not_found")])
        res = analyze.evaluate(failed)[0]
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)
        self.assertIn("404", res["detail"]["why"])
        self.assertEqual(analyze.evaluate(self._ev([_kill_record()]))[0]["status"], analyze.PASS)


class DebugKillRespawnTests(unittest.TestCase):
    def _ev(self, respawned=True, kill=None, status_field=True):
        # Player u1 walks at x=10, dies at st 12.1, respawns at the spawn (0,0) at 12.2 when respawned.
        rows = []
        for k in range(100):
            st = k * 0.2
            dead = respawned is False and st >= 12.1
            x = 0.0 if (respawned and st >= 12.2) else 10.0
            rows.append(_row(st, [["u1", "player", x, 0.0, 0 if dead else 100, 100, 1 if dead else 0, 5]]))
        status = [{"_st": float(s), **({"player_respawns": 1 if (respawned and s >= 13) else 0} if status_field else {})}
                  for s in range(20)]
        ev = _ev(clients=2, entities=rows, status=status, duration=20)
        ev["disruptions"] = [kill or _kill_record()]
        return ev

    def test_kill_then_respawn_passes(self):
        res = analyze.check_debug_kill_respawn(self._ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual(res["measured"][0]["server_tick"], 720)

    def test_no_respawn_fails(self):
        self.assertEqual(analyze.check_debug_kill_respawn(self._ev(respawned=False), {})["status"], analyze.FAIL)

    def test_unconfirmed_kill_or_missing_counter_is_inconclusive(self):
        bad = _kill_record(ok=False, status=503, outcome="busy")
        self.assertEqual(analyze.check_debug_kill_respawn(self._ev(kill=bad), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_debug_kill_respawn(self._ev(status_field=False), {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_debug_kill_respawn(_ev(), {})["status"], analyze.INCONCLUSIVE)


class InputRejectionTests(unittest.TestCase):
    K = 'gameserver_inputs_rejected_total{map_id="map_01",reason="%s"}'

    def _ev(self, start, end):
        return _ev(metrics_start={self.K % r: v for r, v in start.items()},
                   metrics_end={self.K % r: v for r, v in end.items()})

    def test_expected_reasons_must_rise(self):
        ev = self._ev({"ability_on_cooldown": 2, "ability_out_of_range": 0}, {"ability_on_cooldown": 40, "ability_out_of_range": 0})
        self.assertEqual(analyze.check_input_rejections(ev, {"expect_positive": ["ability_on_cooldown"]})["status"], analyze.PASS)
        self.assertEqual(analyze.check_input_rejections(ev, {"expect_positive": ["ability_out_of_range"]})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_input_rejections(ev, {"expect_zero": ["ability_on_cooldown"]})["status"], analyze.FAIL)

    def test_a_server_without_the_series_is_inconclusive(self):
        self.assertEqual(analyze.check_input_rejections(_ev(), {"expect_positive": ["x"]})["status"], analyze.INCONCLUSIVE)
        ev = self._ev({"other": 0}, {"other": 1})
        self.assertEqual(analyze.check_input_rejections(ev, {"expect_positive": ["ability_on_cooldown"]})["status"],
                         analyze.INCONCLUSIVE)


ABILITIES = {"abilities": [
    {"id": 1, "name": "Bolt", "delivery": "entity", "range": 8, "effects": [{"kind": "damage", "power": 10}], "cooldownTicks": 30},
    {"id": 4, "name": "Fire Bolt", "delivery": "projectile", "effects": [{"kind": "damage", "power": 15}],
     "projectile": {"speed": 20, "radius": 0.3, "range": 25}, "cooldownTicks": 45}]}


class CastDamageBoundTests(unittest.TestCase):
    def _ev(self, d, hits_spam=5, far_hit=False, other_casts=False):
        _write(Path(d) / "backend" / "content" / "abilities.json", json.dumps(ABILITIES))
        rows = []
        hp_near, hp_far = 100, 100
        for k in range(200):
            st = k * 0.2
            if 5 <= st <= 15 and k % 5 == 0 and hits_spam > 0:
                hp_near -= 15
                hits_spam -= 1
            if far_hit and st == 22.0:
                hp_far -= 15
            rows.append(_row(st, [["u0", "player", 0.0, 0.0, 100, 100, 0, 5],
                                  ["near", "mob", 10.0, 0.0, max(hp_near, 0), 100, 0, 2.5],
                                  ["far", "mob", 40.0, 0.0, hp_far, 100, 0, 2.5]]))
        ev = _ev(clients=2, entities=rows, duration=40, status=[{"_st": 1, "tick_rate": 60}])
        ev["meta"] = {"config": {"server_repo": str(d)}}
        ev["clients"][0]["summary"] = {"user_id": "u0"}
        ev["clients"][0]["plan"] = {"actions": [
            {"t0": 5, "t1": 15, "kind": "cast_spam", "interval_ms": 100, "range": 25},
            {"t0": 20, "t1": 30, "kind": "cast_at_point", "interval_s": 1.0, "x": 60, "y": 0}]}
        if other_casts:
            ev["clients"][1]["plan"] = {"actions": [{"t0": 1, "t1": 2, "kind": "cast_forward"}]}
        return ev

    def test_damage_within_the_cooldown_bound_passes(self):
        with tempfile.TemporaryDirectory() as d:
            res = analyze.check_cast_damage_bound(self._ev(d), {})
            self.assertEqual(res["status"], analyze.PASS, res)
            self.assertEqual(res["threshold"]["ability"]["cooldown_ticks"], 45)  # read from content, not chosen
            self.assertEqual(res["measured"][0]["max_accepted_casts"], 14)     # 10 s / 0.75 s + 1

    def test_more_damage_than_the_cooldown_allows_fails(self):
        with tempfile.TemporaryDirectory() as d:
            ev = self._ev(d, hits_spam=6)
            ev["clients"][0]["plan"]["actions"][0]["t1"] = 7  # 2 s window: at most 3 casts = 45 HP
            self.assertEqual(analyze.check_cast_damage_bound(ev, {})["status"], analyze.FAIL)

    def test_a_hit_beyond_the_projectile_reach_fails(self):
        with tempfile.TemporaryDirectory() as d:
            res = analyze.check_cast_damage_bound(self._ev(d, far_hit=True), {})
            self.assertEqual(res["status"], analyze.FAIL)
            self.assertEqual(res["measured"][1]["hit_beyond_reach"][0]["id"], "far")

    def test_unattributable_or_unexercised_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(analyze.check_cast_damage_bound(self._ev(d, other_casts=True), {})["status"], analyze.INCONCLUSIVE)
            self.assertEqual(analyze.check_cast_damage_bound(self._ev(d, hits_spam=0), {})["status"], analyze.INCONCLUSIVE)
        ev = _ev(clients=1)
        self.assertEqual(analyze.check_cast_damage_bound(ev, {})["status"], analyze.INCONCLUSIVE)


class StatusMapBoundsTests(unittest.TestCase):
    def _ev(self, positions, status_map="map_01"):
        status = [{"_st": 1, "map_id": status_map,
                   "map_bounds": {"min_x": -50, "min_y": -50, "max_x": 50, "max_y": 50, "source": "configured_size"}}]
        ev = _ev(entities=[_enemy_row(1 + i * 0.2, positions) for i in range(30)], duration=10, map="map_01", status=status)
        ev["meta"] = {"stack": {"env": {"GAMESERVER_MAP_ID": "map_01"}}}
        return ev

    def test_status_bounds_judge_a_map_without_a_file(self):
        res = analyze.check_enemy_bounds(self._ev([(0, 0), (49, -49)]), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertIn("/status map_bounds (configured_size)", res["source"])
        self.assertEqual(analyze.check_enemy_bounds(self._ev([(0, 0), (51, 0)]), {})["status"], analyze.FAIL)

    def test_a_status_map_id_that_disagrees_is_inconclusive(self):
        self.assertEqual(analyze.check_enemy_bounds(self._ev([(0, 0)] * 2, status_map="dev_arena"), {})["status"],
                         analyze.INCONCLUSIVE)


class RespawnScenarioTests(unittest.TestCase):
    def test_s14_expects_one_explained_snap_per_kill(self):
        sc = scenarios.load("S14")
        kills = [d for d in sc["disruptions"] if d["kind"] == "debug_kill"]
        pb = next(a for a in sc["assertions"] if a["check"] == "prediction_bound")
        self.assertEqual(pb["expected_explained"][str(kills[0]["client"])], len(kills))
        self.assertEqual(pb["max_unexplained"], 0)
        self.assertEqual(sc["server_env"]["GAMESERVER_ENEMY_ATTACKS"], "false")
        dependent = [a for a in sc["assertions"] if a.get("requires_debug_kill")]
        self.assertGreaterEqual(len(dependent), 5)

    def test_s15_casts_from_one_client_only(self):
        sc = scenarios.load("S15")
        casters = [i for i, p in enumerate(sc["per_client"]) if p.get("actions")]
        self.assertEqual(casters, [0])
        kinds = {a["kind"] for a in sc["per_client"][0]["actions"]}
        self.assertEqual(kinds, {"cast_spam", "cast_at_point"})
        self.assertEqual(sc["server_env"]["GAMESERVER_ENEMY_ATTACKS"], "false")


class LifecycleDuplicateTests(unittest.TestCase):
    def test_duplicate_ids_in_one_sample_fail_even_without_removals(self):
        ev = _ev(clients=1)
        c = ev["clients"][0]
        c["events"] = [{"event": "entity_added", "t": 100.0, "id": "p", "x": 0, "y": 0, "rx": 0, "ry": 0}]
        c["samples"] = [_sample(100 + k * 0.05, [["p", "player", 0, 0, 0, 0, 0]]) for k in range(20)]
        self.assertEqual(analyze.check_entity_lifecycle(ev, {"require_removal": False})["status"], analyze.PASS)
        self.assertEqual(analyze.check_entity_lifecycle(ev, {})["status"], analyze.INCONCLUSIVE)
        c["samples"][5]["ents"].append(["p", "player", 0, 3, 0, 3, 0])
        self.assertEqual(analyze.check_entity_lifecycle(ev, {"require_removal": False})["status"], analyze.FAIL)

    def test_prediction_bound_expected_explained_and_absolute_limit(self):
        t = PredictionBoundTests()
        ev = t._ev([1504, 2604], [1500, 2600])
        self.assertEqual(analyze.check_prediction_bound(ev, {"expected_explained": {"0": 2}, "max_unexplained": 0})["status"],
                         analyze.PASS)
        self.assertEqual(analyze.check_prediction_bound(ev, {"expected_explained": {"0": 3}})["status"], analyze.FAIL)
        ev = t._ev([1504, 400], [1500])
        self.assertEqual(analyze.check_prediction_bound(ev, {"max_unexplained": 0})["status"], analyze.FAIL)


class ImageRevisionTests(unittest.TestCase):
    """--build-server stamps STACK_GIT_REVISION; provenance proves the container runs that source."""
    SHA = "a" * 40

    def _cfg(self, d, supported=True):
        from lab import config
        _write(Path(d) / "backend" / "deploy" / "stack.sh",
               "STACK_SCRATCH_EXTRA_ENV\n" + ("STACK_GIT_REVISION\n" if supported else ""))
        return config.LabConfig(workspace=Path(d), runs_root=Path(d), server_repo=Path(d))

    def _ensure_cmd(self, d, supported, build=True):
        from unittest import mock
        from lab import stack
        cfg = self._cfg(d, supported)
        done = __import__("subprocess").CompletedProcess([], 0, "", "")
        with mock.patch.object(stack, "health", return_value={"ok": False}), \
                mock.patch.object(stack, "wait_ready"), \
                mock.patch.object(stack, "server_head", return_value=self.SHA), \
                mock.patch.object(stack.util, "wsl", return_value=done) as wsl:
            rec = stack.ensure(cfg, {"A": "1"}, build=build, log_path=Path(d) / "up.log", force_restart_gameserver=False)
        return wsl.call_args_list[0][0][1], rec

    def test_build_stamps_the_server_head_when_stack_sh_supports_it(self):
        with tempfile.TemporaryDirectory() as d:
            cmd, rec = self._ensure_cmd(d, supported=True)
            self.assertIn(f"STACK_GIT_REVISION='{self.SHA}'", cmd)
            self.assertEqual(rec["stamped_revision"], self.SHA)
        with tempfile.TemporaryDirectory() as d:
            cmd, rec = self._ensure_cmd(d, supported=False)
            self.assertNotIn("STACK_GIT_REVISION", cmd)
        with tempfile.TemporaryDirectory() as d:
            cmd, _ = self._ensure_cmd(d, supported=True, build=False)
            self.assertNotIn("STACK_GIT_REVISION", cmd)

    def test_image_revision_reads_the_label(self):
        from unittest import mock
        from lab import stack
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            for out, want in ((self.SHA + "\n", self.SHA), ("<no value>\n", None), ("", None)):
                done = __import__("subprocess").CompletedProcess([], 0, out, "")
                with mock.patch.object(stack.util, "wsl", return_value=done) as wsl:
                    self.assertEqual(stack.image_revision(cfg), want)
                self.assertIn("org.opencontainers.image.revision", wsl.call_args[0][1])

    def _status(self, d, **server):
        run = _run_dir(Path(d))
        meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
        meta["provenance"]["server"].update(server)
        _write(run / "run.json", json.dumps(meta))
        return analyze.check_provenance(analyze.load_evidence(run), {})

    def test_provenance_requires_the_label_to_match_when_supported(self):
        sha = "s" * 40  # _run_dir's recorded server sha
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._status(d, label_supported=True, image_revision=sha)["status"], analyze.PASS)
        with tempfile.TemporaryDirectory() as d:
            res = self._status(d, label_supported=True, image_revision="b" * 40)
            self.assertEqual(res["status"], analyze.INCONCLUSIVE)
            self.assertTrue(any("does not run the recorded source" in p for p in res["detail"]["problems"]))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._status(d, label_supported=True, image_revision=None)["status"], analyze.INCONCLUSIVE)
        with tempfile.TemporaryDirectory() as d:
            res = self._status(d, label_supported=False, image_revision=None)
            self.assertEqual(res["status"], analyze.PASS)
            self.assertEqual(res["measured"]["server_image_revision"], "label unsupported")


class QualifiedVerdictTests(unittest.TestCase):
    """R3-3: an informational breach (S07/S07P memory) never yields a clean PASS; R3-6: host load is
    shown next to the verdict."""

    def _memory_ev(self, slope_mib_per_min):
        mem = next(a for a in scenarios.load("S07")["assertions"] if a["check"] == "memory_growth")
        self.assertTrue(mem.get("informational"))
        ev = _ev(clients=1)
        ev["server"]["container"] = [{"st": k * 5.0, "mem_bytes": int((100 + slope_mib_per_min * k * 5 / 60) * 1024 * 1024)}
                                     for k in range(12)]
        ev["scenario"]["assertions"] = [dict(mem)]
        return ev

    def test_s07_memory_breach_makes_the_run_pass_with_warnings(self):
        results = [r for r in analyze.evaluate(self._memory_ev(60.0)) if r["check"] == "memory_growth"]
        self.assertEqual(results[0]["status"], analyze.INFO)
        self.assertEqual(analyze.overall(results), analyze.PASS_WITH_WARNINGS)
        self.assertEqual(analyze.qualifications(results)[0]["kind"], "informational_breach")
        quiet = [r for r in analyze.evaluate(self._memory_ev(1.0)) if r["check"] == "memory_growth"]
        self.assertEqual(analyze.overall(quiet), analyze.PASS)
        self.assertEqual(analyze.overall(results + [{"status": analyze.FAIL}]), analyze.FAIL)
        self.assertEqual(analyze.overall(results + [{"status": analyze.INCONCLUSIVE}]), analyze.INCONCLUSIVE)

    def test_exit_codes_rank_warnings_below_fail_and_inconclusive(self):
        import testlab as cli
        from lab import report
        self.assertEqual(report.EXIT_CODES[analyze.PASS_WITH_WARNINGS], 4)
        self.assertEqual(cli._worst(["PASS", "PASS_WITH_WARNINGS"]), 4)
        self.assertEqual(cli._worst(["PASS_WITH_WARNINGS", "INCONCLUSIVE"]), 2)
        self.assertEqual(cli._worst(["PASS_WITH_WARNINGS", "FAIL"]), 1)
        self.assertEqual(cli._worst(["PASS"]), 0)

    def test_host_stalls_and_load_qualify_the_verdict_in_the_report(self):
        from lab import report
        ev = _ev(clients=2)
        for c in ev["clients"]:
            c["frames"] = [(5.0, 800.0)]  # one host-wide stall
        ev["meta"] = {"run_id": "r", "provenance": {"host_quiet": {"load_start": {"cpu_load_pct": 72.0},
                                                                   "load_end": {"cpu_load_pct": 10.0}}}}
        ev["scenario"]["assertions"] = []
        results = analyze.evaluate(ev)
        q = analyze.qualifications(results)
        self.assertEqual([x["kind"] for x in q], ["host", "host"])
        self.assertIn("host-wide stall(s)", q[0]["text"])
        self.assertIn("72 %", q[1]["text"])
        with tempfile.TemporaryDirectory() as d:
            ev["run_dir"] = Path(d)
            for c in ev["clients"]:
                c["dir"] = Path(d) / f"client-{c['index']}"
            doc = report.write(Path(d), ev, results, analyze.overall(results), None)
            self.assertEqual(len(doc["qualifications"]), 2)
            md = (Path(d) / "report.md").read_text(encoding="utf-8")
            self.assertLess(md.index("**Qualified by:**"), md.index("## Build and environment"))
        ev["clients"][1]["frames"] = []
        ev["meta"]["provenance"]["host_quiet"]["load_start"]["cpu_load_pct"] = 20.0
        self.assertEqual(analyze.qualifications(analyze.evaluate(ev)), [])


class ThresholdsDocTests(unittest.TestCase):
    def test_thresholds_md_is_generated_and_current(self):
        from lab import thresholds
        doc = Path(__file__).resolve().parents[1] / "docs" / "THRESHOLDS.md"
        self.assertEqual(doc.read_text(encoding="utf-8"), thresholds.render(),
                         "testlab/docs/THRESHOLDS.md is stale: run python3 testlab/testlab.py thresholds --write")

    def test_every_scenario_limit_is_listed_with_a_source(self):
        from lab import thresholds
        rows = thresholds.scenario_rows()
        listed = {(sid, aid) for sid, aid, *_ in rows}
        for sid in scenarios.list_ids():
            for a in scenarios.load(sid)["assertions"]:
                limits = [k for k in a if k not in ("id", "check", "title") and k not in thresholds.NOT_LIMITS
                          and not k.startswith("requires_")]
                if limits:
                    self.assertIn((sid, a["id"]), listed)
        self.assertTrue(all(r[5] for r in rows))


# =========================================================================== T28: soak cycle, classifier, preflight

class SoakCycleTests(unittest.TestCase):
    def _active(self, plan, t0, t1):
        return any(x["t0"] < t1 and x["t1"] > t0 for x in plan["steps"] + plan["actions"])

    def test_an_hour_of_s09_is_active_in_every_five_minute_bucket(self):
        sc = scenarios.load("S09", {"duration_s": 3600})
        for i in range(sc["clients"]):
            plan = scenarios.client_plan(sc, i, "r")
            for k in range(12):
                self.assertTrue(self._active(plan, k * 300, (k + 1) * 300), (i, k))
            self.assertTrue(all(x["t1"] <= 3600 for x in plan["steps"] + plan["actions"]))

    def test_the_first_cycle_is_unchanged(self):
        short = scenarios.load("S09")
        long_ = scenarios.load("S09", {"duration_s": 3600})
        for i in range(short["clients"]):
            a, b = scenarios.client_plan(short, i, "r"), scenarios.client_plan(long_, i, "r")
            for key in ("steps", "actions"):
                self.assertEqual(a[key], [x for x in b[key] if x["t0"] < 300], (i, key))

    def test_without_repeat_a_long_run_idles_after_the_script(self):
        sc = scenarios.load("S09", {"duration_s": 3600, "repeat_cycle_s": 0})
        plan = scenarios.client_plan(sc, 0, "r")
        self.assertFalse(self._active(plan, 300, 600))


class ScopeAndKcpWindowTests(unittest.TestCase):
    def test_a_gap_on_the_next_tick_pair_in_the_same_freeze_is_all_clients(self):
        # T06, sfj5 s 3269: c0 182061-182065, c1 182065-182069, both ~600 ms in one host freeze.
        from lab import delivery
        g0 = {"tick_a": 182061, "tick_b": 182065, "recv_a_us": 10_000_000, "recv_b_us": 10_600_000, "gap_us": 600_000}
        g1 = {"tick_a": 182065, "tick_b": 182069, "recv_a_us": 20_050_000, "recv_b_us": 20_640_000, "gap_us": 590_000}
        snaps = [(182000, 0, None, None), (182200, 0, None, None)]
        c0 = {"snaps": snaps, "long": [g0], "clock": {"ok": False}}
        c1 = {"snaps": snaps, "long": [g1], "clock": {"ok": False}}
        self.assertEqual(delivery._scope(g0, c0, [c0, c1], 250), "ALL-CLIENTS")  # ticks touch
        g1b = dict(g1, tick_a=182069, tick_b=182073)
        c1["long"] = [g1b]
        self.assertEqual(delivery._scope(g0, c0, [c0, c1], 250), "SINGLE-CLIENT")  # no clock: cannot tell
        # Same receive time on the server clock (each client's own offset), different tick pairs.
        c0["clock"] = {"ok": True, "offset_us": 5_000_000, "rate": 1.08}
        c1["clock"] = {"ok": True, "offset_us": 15_050_000, "rate": 1.08}
        self.assertEqual(delivery._scope(g0, c0, [c0, c1], 250), "ALL-CLIENTS")
        c1["clock"] = {"ok": True, "offset_us": 13_000_000, "rate": 1.08}  # 2 s apart on the server clock
        self.assertEqual(delivery._scope(g0, c0, [c0, c1], 250), "SINGLE-CLIENT")

    def test_kcp_signs_just_after_the_late_snapshot_are_seen(self):
        # T06 candidate s 738: written on time, retransmissions 3 -> 40 in the rows after tick b.
        from lab import delivery
        def row(tick, write, retrans):
            return {"gather_us": write - 1500, "enqueue_us": write - 1000, "write_start_us": write,
                    "write_end_us": write + 200, "queue_depth": 0, "dropped_oldest_total": 0, "kcp_wait_snd": 0,
                    "kcp_retrans_total": retrans}
        srv = {t: row(t, t * 16_667, 3 if t <= 108 else 40) for t in range(100, 130, 4)}
        gap = {"tick_a": 104, "tick_b": 108, "recv_a_us": 0, "recv_b_us": 400_000, "gap_us": 400_000}
        cls, _, ev = delivery.classify_gap(gap, srv, [], "recv_us", explain_fraction=0.5, slack_us=50_000)
        self.assertEqual(cls, "KCP")
        self.assertEqual(ev["retrans_delta"], 37)
        cls, _, _ = delivery.classify_gap(gap, srv, [], "recv_us", explain_fraction=0.5, slack_us=50_000, after_rows=0)
        self.assertEqual(cls, "PATH")  # the old window: up to tick b only


class NakamaPreflightTests(unittest.TestCase):
    def test_a_worktree_without_the_nakama_plugin_fails_fast_unless_building(self):
        from lab import config, stack
        with tempfile.TemporaryDirectory() as d:
            cfg = config.LabConfig(workspace=Path(d), runs_root=Path(d), server_repo=Path(d))
            with self.assertRaises(stack.StackError) as e:
                stack.check_nakama_module(cfg, build=False)
            self.assertIn("--build-server", str(e.exception))
            stack.check_nakama_module(cfg, build=True)  # building makes it
            _write(Path(d) / "backend" / "deploy" / "modules" / "nakama.so", "elf")
            stack.check_nakama_module(cfg, build=False)


class LeaverIdentityAndReentryTests(unittest.TestCase):
    """T34: S08G runs zvjy/zc4m - a leaver's summary has user_id "" (written after Disconnect), and
    an entity re-entering AOI was counted as a ghost by the sample of its own re-add frame."""

    def test_user_id_falls_back_to_the_join_event_and_run_record(self):
        ev = _ev(clients=2)
        ev["clients"][0]["summary"] = {"user_id": ""}
        ev["clients"][0]["status"] = {"user_id": ""}
        ev["clients"][0]["events"] = [{"event": "in_world", "user_id": "u-join"}]
        ev["clients"][1]["summary"] = {"user_id": ""}
        ev["meta"] = {"clients": {"1": {"first_user_id": "u-run"}}}
        self.assertEqual(analyze._user_ids(ev), ["u-join", "u-run"])

    def test_graceful_leave_is_judged_when_the_leaver_wrote_no_user_id(self):
        t = GracefulLeaveTests()
        ev = t._ev(gone_at=15.4)
        ev["clients"][2]["summary"]["user_id"] = ""
        ev["clients"][2]["events"].insert(0, {"event": "in_world", "user_id": "u2"})
        self.assertEqual(analyze.check_graceful_leave(ev, {})["status"], analyze.PASS)
        ev["clients"][2]["events"] = [e for e in ev["clients"][2]["events"] if e["event"] != "in_world"]
        self.assertEqual(analyze.check_graceful_leave(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_a_dead_link_close_is_named_in_the_leave_diagnosis(self):
        t = GracefulLeaveTests()
        ev = t._ev(gone_at=40)  # held until the end
        k = 'gameserver_kcp_sessions_closed_total{map_id="map_01",reason="dead_link"}'
        ev["server"]["metrics_start"], ev["server"]["metrics_end"] = {k: 0.0}, {k: 1.0}
        res = analyze.check_graceful_leave(ev, {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertIn("polite disconnect frame did not reach it", res["detail"]["note"])

    def _reentry(self, stale_frame):
        """enemy-96 leaves AOI at t=19.588 (frame 4900) and re-enters at t=22.130123 (frame 9681); the
        20 Hz sample of frame 9681 is stamped at t=22.130091, just before the entity_added event."""
        ev = _ev(clients=1, duration=20)
        c = ev["clients"][0]
        rows = []
        for k, (t, fr) in enumerate([(19.5, 4880), (19.8, 4950), (21.0, 7000), (22.130091, 9681), (22.18, 9706)]):
            drawn = t < 19.6 or fr >= 9681 or (stale_frame and fr == 7000)
            rows.append({"t": t, "st": t - 7.6, "frame": fr, "ents": [["enemy-96", "mob", 0, 1, 1, 1, 1]] if drawn else []})
        c["samples"] = rows
        c["events"] = [
            {"event": "entity_added", "t": 11.32, "id": "enemy-96", "x": 4.4, "y": 11.2, "rx": 4.4, "ry": 11.2, "frame": 4344},
            {"event": "entity_removed", "t": 19.588, "id": "enemy-96", "rendered": True, "reason": "removed"},
            {"event": "entity_added", "t": 22.130123, "id": "enemy-96", "x": 1, "y": 1, "rx": 1, "ry": 1, "frame": 9681}]
        return analyze.check_entity_lifecycle(ev, {})

    def test_the_re_add_frame_sample_is_not_a_ghost(self):
        res = self._reentry(stale_frame=False)
        self.assertEqual(res["status"], analyze.PASS, res["detail"])
        res = self._reentry(stale_frame=True)  # drawn at frame 7000, between removal and re-entry
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["detail"]["lingering"][0]["frame"], 7000)


class ConvergenceNearTeleportTests(unittest.TestCase):
    """T37: final soak 20261022T200348Z-S09-uc3e - the worst convergence pairs (max 18.56) were 3-14
    ticks before a player respawn: one client already drew the respawn position, the other not yet."""

    def _ev(self, a_early_ticks=25, offset=0.0, respawn=True):
        # Server: player p walks +x at 2 u/s; at tick 1500 it dies and respawns 18 units away.
        rows = []
        for k in range(120):
            tick = 1000 + k * 12
            x = (tick - 1000) / 60 * 2.0 + (18.0 if respawn and tick >= 1500 else 0.0)
            dead = respawn and 1488 <= tick < 1500
            rows.append({"st": k * 0.2, "tick": tick, "ents": [["p", "player", x, 0.0, 0 if dead else 100, 100,
                                                                1 if dead else 0, 5]]})
        ev = _ev(clients=2, entities=rows, duration=24, status=[{"_st": 1, "tick_rate": 60}])
        for c in ev["clients"]:
            samples = []
            for k in range(450):
                t = 103.0 + 0.013 * c["index"] + k * 0.05
                tick = 1000 + (t - 103.0) * 60
                # client 0 shows the respawn a_early_ticks before client 1 does
                jump_at = 1500 - (a_early_ticks if c["index"] == 0 else 0)
                x = (tick - 1000) / 60 * 2.0 + (18.0 if respawn and tick >= jump_at else 0.0)
                if c["index"] == 1:
                    x += offset
                samples.append(_sample(t, [["p", "player", 0, x, 0.0, x, 0.0]], tick))
            c["samples"] = samples
        return ev

    def test_pairs_next_to_a_server_respawn_are_skipped(self):
        res = analyze.check_cross_client_convergence(self._ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertGreater(res["measured"]["skipped_near_server_teleport"], 0)
        res = analyze.check_cross_client_convergence(self._ev(), {"teleport_window_s": 0})
        self.assertEqual(res["status"], analyze.FAIL)  # the old behaviour: an 18-unit "divergence"
        self.assertGreater(res["measured"]["max"], 15)

    def test_divergence_away_from_teleports_still_fails(self):
        res = analyze.check_cross_client_convergence(self._ev(a_early_ticks=0, offset=0.6, respawn=False), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["measured"]["skipped_near_server_teleport"], 0)

    def test_all_server_teleports_finds_respawns_and_jumps(self):
        spans = analyze._all_server_teleports(self._ev(), 6.0)
        self.assertEqual(spans["p"], [(1492, 1504)])  # last pre-respawn sample to the respawned sample


class BoundedMemoryAnalysisTests(unittest.TestCase):
    """T41: a 1 h soak's analysis took ~13 GB. Evidence files are streamed (util.LazyNdjson), large
    value sets kept in util.Distribution, convergence pairs formed per render-tick window and
    entity_lifecycle merged with the sample stream. Results must equal the pre-T41 analysis."""

    def _results(self, mod, run):
        ev = mod.load_evidence(run)
        out = {}
        for r in mod.evaluate(ev):
            m = r.get("measured")
            if isinstance(m, dict):
                m = {k: v for k, v in m.items() if k != "skipped_ticks_backwards"}
            out[r["id"]] = (r["status"], m, r.get("threshold"), r.get("detail"))
        return out

    def test_results_equal_the_pre_streaming_analysis(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import reference_analyze_171c573 as old
        import synthetic_soak
        with tempfile.TemporaryDirectory() as d:
            run = synthetic_soak.write(Path(d), 820, 8)
            new_r, old_r = self._results(analyze, run), self._results(old, run)
            self.assertEqual(set(new_r), set(old_r))
            for k in old_r:
                self.assertEqual(new_r[k], old_r[k], k)
            # the synthetic run exercises the heavy checks
            self.assertGreater(new_r["cross_client_convergence"][1]["pairs"], 1000)
            self.assertGreater(new_r["entity_lifecycle"][1]["removed"], 5)

    def test_peak_memory_stays_near_the_evidence_size(self):
        import tracemalloc
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import reference_analyze_171c573 as old
        import synthetic_soak

        def peak(mod, run):
            tracemalloc.start()
            mod.evaluate(mod.load_evidence(run))
            value = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            return value

        with tempfile.TemporaryDirectory() as d:
            run = synthetic_soak.write(Path(d), 600, 16)
            size = sum(p.stat().st_size for p in run.rglob("*") if p.is_file())
            new_peak, old_peak = peak(analyze, run), peak(old, run)
        # The pre-T41 analysis held every sample, event and entity row as Python objects: about 7x the
        # evidence size, growing with the run. The streamed one keeps compact arrays (trajectories,
        # frames, value sets up to 1 M) and per-window buffers. Fails if a check holds a whole file again.
        self.assertLess(new_peak, 3.0 * size, (new_peak, old_peak, size))
        self.assertLess(new_peak * 2.5, old_peak, (new_peak, old_peak, size))

    def test_distribution_is_exact_below_its_cap_and_close_above(self):
        import random
        rnd = random.Random(7)
        vals = [rnd.random() for _ in range(5000)]
        exact, binned = util.Distribution(), util.Distribution(exact_cap=100)
        for v in vals:
            exact.add(v)
            binned.add(v)
        for p in (50, 95, 99):
            self.assertEqual(exact.percentile(p), util.percentile(vals, p))
            self.assertAlmostEqual(binned.percentile(p), util.percentile(vals, p), delta=1e-6)
        self.assertEqual((len(binned), binned.max()), (5000, max(vals)))
        self.assertIsNone(util.Distribution().percentile(50))

    def test_lazy_ndjson_reads_on_every_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ndjson"
            _write(p, '{"a": 1}\n{"a": 2}\n{"a"')
            lazy = util.LazyNdjson(p)
            self.assertEqual([r["a"] for r in lazy], [1, 2])
            self.assertEqual((len(lazy), bool(lazy), [r["a"] for r in reversed(lazy)]), (2, True, [2, 1]))
            self.assertFalse(util.LazyNdjson(Path(d) / "missing.ndjson"))


class StallCatchupRuleTests(unittest.TestCase):
    """Lead rule for S13 (runs 20261022T221641Z-S13-7fud, 20261022T222006Z-S13-uwrf): on the stalled
    client, remote jumps/divergence inside the catch-up window (through the frame after the frame
    whose dt contains the stall) are not judged; one local major correction per stall is allowed."""

    def _ev(self, jumps):
        ev = _ev(clients=2, duration=40)
        c = ev["clients"][0]
        for x in ev["clients"]:
            x["summary"] = {"outcome": "completed"}
            x["events"] = [{"event": "in_world", "st": -1}]
        # uwrf client 0: 2 s stall; frames 27.0039 (1.3 ms), 27.0079 (dt 2006 ms = the stall), 27.0108, 27.0149
        frames = analyze.FrameSeries()
        for st, dt in [(26.99, 16.0), (27.0039, 1.3), (27.0079, 2006.2), (27.0108, 3.7), (27.0149, 4.7), (27.0163, 1.5)]:
            frames.append((st, dt))
        c["frames"] = frames
        c["events"] += [{"event": "stall", "t": 36.678162, "st": 27.000843, "ms": 2000, "start": 34.67739,
                         "end": 36.678089, "actual_ms": 2000.7}]
        c["events"] += [dict({"event": "render_jump", "type": "player"}, **j) for j in jumps]
        return ev

    def test_the_catch_up_window_ends_at_the_frame_after_the_stall_frame(self):
        w = analyze.stall_windows(self._ev([])["clients"][0], 40)
        self.assertEqual(len(w), 1)
        self.assertAlmostEqual(w[0][0], 25.0, delta=0.01)   # stall start on the scenario clock
        self.assertAlmostEqual(w[0][1], 27.0149, delta=1e-6)  # f20068 (after the dt-2006 frame) ends where f20069 starts
        self.assertAlmostEqual(w[0][2], 30.0, delta=0.01)   # +5 s for local corrections

    def test_remote_catch_up_is_excluded_and_one_local_correction_allowed(self):
        # uwrf: the events of frame 20068 are stamped at 27.01080, after the frame's own 27.01076
        jumps = [{"st": 27.0108015, "id": "r1", "local": False, "step": 7.5},
                 {"st": 27.0108015, "id": "me", "local": True, "step": 1.25}]
        res = analyze.check_render_jumps(self._ev(jumps), {"max_local": 0, "max_remote_per_client_min": 0})
        self.assertEqual(res["status"], analyze.PASS, res["measured"])
        self.assertEqual((res["measured"]["stall_catchup"], res["measured"]["stall_local_correction"]), (1, 1))

    def test_a_jump_on_the_second_frame_after_the_stall_still_fails(self):
        jumps = [{"st": 27.0149, "id": "r1", "local": False, "step": 7.5}]
        res = analyze.check_render_jumps(self._ev(jumps), {"max_local": 0, "max_remote_per_client_min": 0})
        self.assertEqual(res["status"], analyze.FAIL)

    def test_a_second_local_correction_fails(self):
        jumps = [{"st": 27.0108, "id": "me", "local": True, "step": 1.25},
                 {"st": 27.0667, "id": "me", "local": True, "step": 1.0}]  # uwrf
        res = analyze.check_render_jumps(self._ev(jumps), {"max_local": 0, "max_remote_per_client_min": 2.0})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["measured"]["local_major"], 1)

    def test_other_clients_are_never_excluded(self):
        ev = self._ev([])
        ev["clients"][1]["events"].append({"event": "render_jump", "type": "player", "st": 27.0108, "id": "r1",
                                           "local": False, "step": 7.5})
        res = analyze.check_render_jumps(ev, {"max_local": 0, "max_remote_per_client_min": 0})
        self.assertEqual(res["status"], analyze.FAIL)

    def test_remote_divergence_samples_in_the_catch_up_window_are_excluded(self):
        ents = [_row(k * 0.2, [["r1", "player", 0.0, 0.0, 100, 100, 0, 5]]) for k in range(200)]
        ev = self._ev([])
        ev["server"]["entities"], ev["traj"] = ents, analyze.trajectories(ents)
        for x in ev["clients"]:
            x["samples"] = [{"t": 100 + k * 0.05, "st": 3 + k * 0.05, "ents": [["r1", "player", 0, 0.0, 0.0, 0.0, 0.0]]}
                            for k in range(600)]
        ev["clients"][0]["samples"].append({"t": 0, "st": 27.004, "ents": [["r1", "player", 0, 6.265, 0.0, 0.0, 0.0]]})
        res = analyze.check_position_divergence(ev, {"types": ["player"], "p95": 0.35, "max": 1.0})
        self.assertEqual(res["status"], analyze.PASS, res["measured"])
        self.assertEqual(res["measured"]["excluded_stall_catchup_samples"] >= 1, True)
        ev["clients"][0]["samples"][-1]["st"] = 27.02  # after the catch-up frame: judged
        self.assertEqual(analyze.check_position_divergence(ev, {"types": ["player"], "p95": 0.35, "max": 1.0})["status"],
                         analyze.FAIL)


if __name__ == "__main__":
    unittest.main()
