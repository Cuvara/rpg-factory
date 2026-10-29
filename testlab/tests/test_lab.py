"""Unit tests for the testlab's pure parts: scenario validation, plan expansion, path handling and
every analysis check against synthetic evidence. No stack, no Unity, no network.

    python3 -B testlab/tests/test_lab.py
"""

from __future__ import annotations

import copy
import gzip
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
        # + provenance (no record: INCONCLUSIVE), host_quiet and host_guard (INFO), appended to every evaluation
        self.assertEqual([r["status"] for r in out],
                         [analyze.INCONCLUSIVE, analyze.INCONCLUSIVE, analyze.INCONCLUSIVE, analyze.INFO, analyze.INFO])
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

    def test_kcp_and_redis_are_inconclusive_when_their_evidence_was_taken_after_the_window(self):
        # Run 20261026T143656Z-S01-ii3h: the loop stalled in a slow WSL call past the scenario end, the clients had
        # quit, and metrics-end (scraped in the cleanup) counted the 3 dead_link closes of the teardown.
        start = {'gameserver_kcp_datagrams_dropped_total{reason="no_session"}': 0.0,
                 'gameserver_kcp_sessions_closed_total{reason="dead_link"}': 0.0}
        end = {'gameserver_kcp_datagrams_dropped_total{reason="no_session"}': 0.0,
               'gameserver_kcp_sessions_closed_total{reason="dead_link"}': 3.0}
        ev = _ev(metrics_start=start, metrics_end=end)
        self.assertEqual(analyze.check_kcp_health(ev, {})["status"], analyze.FAIL)      # on time: a real close fails
        ev["meta"]["timeline"] = [{"event": "metrics_end_late", "mono": 1.0}]
        res = analyze.check_kcp_health(ev, {})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)
        self.assertIn("after the clients quit", str(res))
        ev["redis"] = {"session_keys": 6, "map_members": ["gs"]}
        self.assertEqual(analyze.check_redis(ev, {})["status"], analyze.FAIL)           # on time: stale keys still fail
        ev["meta"]["timeline"] = [{"event": "redis_late", "mono": 1.0}]
        self.assertEqual(analyze.check_redis(ev, {})["status"], analyze.INCONCLUSIVE)

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

    INFO_ONLY = {"host_quiet", "host_guard", "bots_joined"}  # environment / not-applicable reports, never decide a run

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
        self.assertEqual([r["check"] for r in out], ["bots_joined", "provenance", "host_quiet", "host_guard"])
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

    def test_clear_session_keys_deletes_only_session_keys_of_the_scratch_redis(self):
        from unittest import mock
        from lab import stack
        calls = []

        def fake(cfg, args):
            calls.append(args)
            if "--scan" in args:
                return ["session:aaaa-1", "session:bbbb-2", "session:x; rm -rf /", "servers:id:gs", "session:"]
            return []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stack, "redis_cli", side_effect=fake):
            self.assertEqual(stack.clear_session_keys(self._cfg(d)), 2)
        self.assertEqual(calls[1], "del session:aaaa-1 session:bbbb-2")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stack.util, "wsl") as wsl:
            cfg = self._cfg(d, redis_container="rpg-redis")
            with self.assertRaises(stack.StackError):
                stack.clear_session_keys(cfg)          # the normal backend's Redis is never touched
            wsl.assert_not_called()

    def test_wsl_keepalive_holds_a_wsl_session_and_ends_it(self):
        from unittest import mock
        from lab import stack
        proc = mock.Mock(pid=4242, returncode=None)
        proc.poll.return_value = None
        with mock.patch("subprocess.Popen", return_value=proc) as popen, mock.patch.object(stack.time, "sleep"),                 mock.patch.object(stack.util, "kill_tree") as kill:
            keep = stack.WslKeepAlive("Ubuntu").start()
            self.assertTrue(keep.held)
            self.assertEqual(popen.call_args.args[0], ["wsl.exe", "-d", "Ubuntu", "--exec", "sleep", "infinity"])
            keep.stop()
            kill.assert_called_once_with(4242)
            self.assertFalse(keep.held)

    def test_wsl_keepalive_that_cannot_start_is_recorded_and_never_raises(self):
        from unittest import mock
        from lab import stack
        with mock.patch("subprocess.Popen", side_effect=FileNotFoundError("wsl.exe")), mock.patch.object(stack.util, "eprint"):
            keep = stack.WslKeepAlive("Ubuntu").start()
        self.assertFalse(keep.held)
        self.assertIn("FileNotFoundError", keep.error)
        keep.stop()
        dead = mock.Mock(returncode=1)
        dead.poll.return_value = 1
        with mock.patch("subprocess.Popen", return_value=dead), mock.patch.object(stack.time, "sleep"),                 mock.patch.object(stack.util, "eprint"):
            keep = stack.WslKeepAlive("Ubuntu").start()
        self.assertFalse(keep.held)
        self.assertIn("exited at once", keep.error)

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

        class FakeGuard:
            """No PowerShell in the runner tests: the guard is covered by HostGuardTests."""
            interval_s, baseline_pids = 5.0, []
            paths = type("P", (), {"as_dict": staticmethod(lambda: {})})()

            calls = []

            def __init__(self, out_dir):
                self.out = out_dir

            def start(self):
                pass

            def hold_until(self, epoch):
                FakeGuard.calls.append(("hold_until", epoch))
                return True

            def stop(self):
                FakeGuard.calls.append(("stop", None))
                return {"samples": 0}

        self.guard_calls = FakeGuard.calls = []

        patches = [
            mock.patch.object(runner, "_host_load", return_value={"cpu_load_pct": 1.0, "free_mem_mb": 1}),
            mock.patch.object(clients, "clean_orphans", return_value=[]),
            mock.patch.object(stack, "preflight", return_value={"conflicts": []}),
            mock.patch.object(stack, "ensure", return_value={"actions": []}),
            mock.patch.object(stack, "clear_session_keys", return_value=0),
            mock.patch.object(provenance, "docker_image_id", return_value="sha256:" + "0" * 64),
            mock.patch.object(stack, "image_revision", return_value=None),
            mock.patch.object(stack, "check_nakama_module"),
            mock.patch.object(runner, "ServerProbe", FakeProbe),
            mock.patch.object(runner.hostguard, "HostGuard", FakeGuard),
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

    def test_the_guard_samples_to_the_window_end_before_it_stops(self):
        from unittest import mock
        from lab import clients, runner
        with tempfile.TemporaryDirectory() as d:
            cfg, stopped = self._patched_run(d, None)

            class Done:
                pid = 4242

                def poll(self):
                    return 0

                def wait(self, timeout=None):
                    return 0

            def launch(cfg_, sc, p, plan, control):
                p.proc, p.pid = Done(), 4242
                p.history.append({"event": "launch", "pid": 4242})

            with mock.patch.object(clients, "launch", side_effect=launch), \
                    mock.patch.object(runner, "_take_redis"):
                runner.run(cfg, "S01", overrides={"duration_s": 1, "finish_grace_s": 30}, quiet=True)
            meta = self._run_json(cfg)
            self.assertIsNone(meta["harness_error"])
            end = meta["host_guard"]["window_epoch"][1]
            # The players exit at scenario end, 30 s before the window ends: stop() must wait for the guard.
            self.assertEqual([c[0] for c in self.guard_calls], ["hold_until", "stop"])
            self.assertEqual(self.guard_calls[0][1], end)

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


def _c1_row(uid, tick, write_us, *, enqueue_lag=1000, queue_depth=0, dropped=0, wait_snd=0, retrans=0, conn=None):
    gather = write_us - enqueue_lag - 500
    return (f"{conn or 'conn-' + uid},{uid},{tick},{gather},{write_us - enqueue_lag},{write_us},{write_us + 200},900,"
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
        self.reconnects = {}  # client -> dict(idx, ms, cause, events, conn)

    def delay(self, idx, stage, ms, client=None, **kw):
        self.delays[(client, idx)] = {"stage": stage, "ms": ms, **kw}
        return self

    def reconnect(self, idx, ms, client=0, cause="TransportError", events=True, conn=True):
        """Client `client` loses its session after snapshot idx - 1 and is back on a new connection
        (conn_id ...-b, KCP counters from 0) ms later, from snapshot idx on. Before it the old
        connection retransmitted 7 segments per snapshot (e26z: +700 over the dead link). events:
        write the client's net_state Ended / reconnected events and the player.log cause line; conn:
        give the new session its own conn_id."""
        self.reconnects[client] = {"idx": idx, "ms": ms, "cause": cause, "events": events, "conn": conn}
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
            rc = self.reconnects.get(ci)
            events = []
            for k in range(self.snaps):
                tick = 1000 + k * SNAP_TICKS
                conn = None
                if rc and k == rc["idx"]:
                    server_shift += rc["ms"] * 1000
                    retrans = 0
                if rc and k < rc["idx"]:
                    retrans += 7
                if rc and k >= rc["idx"] and rc["conn"]:
                    conn = f"conn-{uid}-b"
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
                server.append(_c1_row(uid, tick, write, enqueue_lag=lag, wait_snd=wait, retrans=retrans, conn=conn))
                jitter = self.bin_jitter_ms * 1000 * ((tick * TICK_US // 3_000_000) % 2)
                recv = offset_us + int(tick * TICK_US * (1 + self.drift)) + 30_000 + jitter + (
                    extra if stage in ("server", "queue", "kcp", "path", "client") else 0) + (
                    rc["ms"] * 1000 if rc and k >= rc["idx"] else 0)
                if rc and rc["events"] and k == rc["idx"]:
                    events += [{"t": (recv - 400_000) / 1e6, "st": 1.0, "event": "entities_reset", "count": 9},
                               {"t": (recv - 400_000) / 1e6, "st": 1.0, "event": "net_state", "state": "Ended"},
                               {"t": (recv - 50_000) / 1e6, "st": 1.0, "event": "reconnected", "generation": 2}]
                deliv.append(f"{tick},{recv if self.c2 else ''},{recv + 400},900,0,6,{k}")
                ndjson.append(json.dumps({"t": (recv + 400) / 1e6, "tick": tick}))
                render.append(f"{k},{offset_us + tick * TICK_US + 38_000},{tick - 6},{tick},{tick},{recv},8.0")
                if stage == "client":
                    frames.append(f"{k},{recv / 1e6:.6f},{extra / 1000 + 5:.3f},1")
            if events:
                _write(self.run / f"client-{ci}" / "events.ndjson", "".join(json.dumps(e) + "\n" for e in events))
                _write(self.run / f"client-{ci}" / "player.log",
                       f"[Net] game session closed: {rc['cause']}\n[Net] session ended with {rc['cause']}\n")
            _write(self.run / f"client-{ci}" / "delivery.csv", "\n".join(deliv) + "\n")
            _write(self.run / f"client-{ci}" / "snapshots.ndjson", "\n".join(ndjson) + "\n")
            _write(self.run / f"client-{ci}" / "frames.csv", "\n".join(frames) + "\n")
            _write(self.run / f"client-{ci}" / "render.csv", "\n".join(render) + "\n")
        if self.c1:
            _write(self.run / "server" / "snapshot-trace.csv", "\n".join(server) + "\n")
        return self.run


class DeliveryTests(unittest.TestCase):
    def test_a_gap_across_a_reconnect_is_reconnect_never_server_late(self):
        """T58 (e26z): the server stopped writing to the dead connection and wrote the next snapshot to
        the new one 3 s later; joined by user id that read as SERVER_LATE with retrans_delta -700. A
        gap spanning a session change is RECONNECT, with the cause, by the conn_id change alone or by
        the client's session events alone; the bucket's retransmissions are summed per connection."""
        from lab import delivery
        for label, kw in (("conn and events", {}), ("conn only", {"events": False}),
                          ("events only", {"conn": False})):
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                fx = DeliveryFixture(Path(d)).reconnect(100, 3000, client=0, cause="HeartbeatTimeout", **kw)
                doc = delivery.analyze(fx.build())
                g = self._only_gap(doc)
                self.assertEqual(g["class"], "RECONNECT", g)
                self.assertNotIn("retrans_delta", g["evidence"])
                self.assertEqual(doc["classes"]["SERVER_LATE"], 0)
                self.assertEqual(doc["classes"]["RECONNECT"], 1)
                if kw.get("events", True):
                    self.assertEqual(g["evidence"]["cause"], "HeartbeatTimeout")
                    self.assertIn("after HeartbeatTimeout", g["reason"])
                    self.assertEqual(doc["clients"]["0"]["sessions"][0]["cause"], "HeartbeatTimeout")
                if kw.get("conn", True):
                    self.assertEqual((g["evidence"]["conn_a"], g["evidence"]["conn_b"]), ("conn-user-0", "conn-user-0-b"))
                retrans = [b["kcp_retrans_delta"] for b in doc["clients"]["0"]["buckets"]
                           if b["kcp_retrans_delta"] is not None]
                self.assertTrue(retrans and min(retrans) >= 0, retrans)
                self.assertFalse(doc["clients"]["1"]["gaps"])

    def test_a_late_server_write_on_one_connection_is_still_server_late(self):
        with tempfile.TemporaryDirectory() as d:
            from lab import delivery
            doc = delivery.analyze(DeliveryFixture(Path(d)).delay(100, "server", 3000, client=0).build())
            self.assertEqual(self._only_gap(doc)["class"], "SERVER_LATE")
            self.assertEqual(doc["clients"]["0"]["sessions"], [])

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
                self.assertGreater(c["clock_fit"]["accepted_windows"], 0, c["clock_fit"])
                self.assertLessEqual(c["clock_fit"]["max_error_bound_ms"], 10.0)
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
            self.assertEqual(doc["clients"]["0"]["server_durations"], "client time (window-rate-corrected)")

    def test_a_poor_clock_fit_reports_relative_excess_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            doc = self._analyze(DeliveryFixture(Path(d), clients=1, snaps=900, bin_jitter_ms=200))
            c = doc["clients"]["0"]
            self.assertEqual(c["clock_fit"]["accepted_windows"], 0)
            self.assertIsNone(c["clock_fit"]["max_error_bound_ms"])
            self.assertIn("relative excess unavailable", c["one_way_delay"])
            self.assertTrue(all(b["one_way_rel_ms"]["p50"] is None for b in c["buckets"]))
            self.assertTrue(c["gaps"])
            self.assertTrue(all(g["class"] == "UNKNOWN" for g in c["gaps"]))

    def test_windowed_fit_tracks_wandering_seven_to_nine_percent_rate(self):
        from lab import delivery
        pairs = []
        for window, rate in enumerate((1.07, 1.09, 1.075, 1.085)):
            start = window * 10_000_000
            for second in range(10):
                for sample in range(20):
                    x = start + second * 1_000_000 + sample * 50_000
                    queue_us = (sample * 137 + second * 211) % 1800
                    pairs.append((x, int(3_000_000 + rate * x + queue_us)))
        fit = delivery.fit_windowed_clock(pairs)
        accepted = [w for w in fit["windows"].values() if w["ok"]]
        self.assertEqual(len(accepted), 4, fit)
        self.assertEqual([round(w["rate"], 3) for w in accepted], [1.07, 1.09, 1.075, 1.085])
        self.assertTrue(all(w["error_bound_us"] <= 10_000 for w in accepted))
        excess, bound, _ = delivery._window_excess(fit, 10_500_000,
                                                   int(3_000_000 + 1.09 * 10_500_000 + 30_000))
        self.assertGreaterEqual(excess, 28_000)
        self.assertLessEqual(bound, 10_000)

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

    def test_an_id_added_after_a_session_change_is_not_a_reuse(self):
        """T58: a reconnect ends the session with entities_reset; every entity of the new session's
        first snapshot is new to the view, wherever it stands, so an id removed before the reset is not
        judged as reused after it. The same add without the reset still fails (e26z: all 80 failures
        were in the catch-up frame of a frame freeze, before the session ended)."""
        removed = {"event": "entity_removed", "t": 104.0, "id": "m"}
        reset = {"event": "entities_reset", "t": 105.0, "count": 1}
        again = dict(self.ADD, t=106.0, tick=500, x=8.0, y=8.0, rx=1.0, ry=1.0)
        res = analyze.check_entity_lifecycle(
            self._ev([self.ADD, removed, reset, again], drawn_until=104.1, reuse_at=106.0), {})
        self.assertEqual((res["status"], res["measured"]["reused_ids_checked"]), (analyze.PASS, 0))
        res = analyze.check_entity_lifecycle(self._ev([self.ADD, removed, again], drawn_until=104.1, reuse_at=106.0), {})
        self.assertEqual((res["status"], res["measured"]["reused_drawn_elsewhere"]), (analyze.FAIL, 1))

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
                c["events"] = [{"event": "entity_added", "id": "u2", "st": -1},
                               {"event": "entity_removed", "id": "u2", "st": gone_at + 0.1}]
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

    def test_a_viewer_that_never_removed_the_leaver_still_fails(self):
        """P5-S08G-LEAVE: a viewer that held the leaver at quit and never saw it removed is a ghost."""
        ev = self._ev(gone_at=15.4)
        ev["clients"][1]["events"] = [{"event": "entity_added", "id": "u2", "st": -1}]
        res = analyze.check_graceful_leave(ev, {})
        self.assertEqual(res["status"], analyze.FAIL, res)
        self.assertIsNone(res["measured"][0]["others_removed_after_s"][1])

    def test_a_viewer_that_had_already_lost_the_leaver_is_not_judged_as_a_ghost_holder(self):
        """P5-S08G-LEAVE: the leaver walked out of viewer 1's area of interest (removal at 11.9 s) before
        it quit at 15 s; viewer 1 has nothing to remove, which is a scenario-geometry gap, not a leak."""
        ev = self._ev(gone_at=15.4)
        ev["clients"][1]["events"] = [{"event": "entity_added", "id": "u2", "st": -1},
                                      {"event": "entity_removed", "id": "u2", "st": 11.9}]
        res = analyze.check_graceful_leave(ev, {})
        # viewer 0 did hold it and got the removal, so the leave is judged; viewer 1 is only listed.
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual(res["measured"][0]["not_in_view_at_quit"], [1])
        # ...and a viewer that did hold it and missed the removal still fails alongside it.
        ev["clients"][0]["events"] = [{"event": "entity_added", "id": "u2", "st": -1}]
        self.assertEqual(analyze.check_graceful_leave(ev, {})["status"], analyze.FAIL)

    def test_viewers_without_lifecycle_events_for_the_leaver_are_inconclusive(self):
        """RV-P5-1: absence of client evidence must never turn into a PASS."""
        ev = self._ev(gone_at=15.4, others_removed=False)
        res = analyze.check_graceful_leave(ev, {})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE, res)
        self.assertEqual(res["measured"][0]["no_lifecycle_events"], [0, 1])

    def test_all_viewers_out_of_view_at_the_quit_are_inconclusive(self):
        ev = self._ev(gone_at=15.4)
        for c in ev["clients"][:2]:
            c["events"] = [{"event": "entity_added", "id": "u2", "st": -1},
                           {"event": "entity_removed", "id": "u2", "st": 11.9}]
        res = analyze.check_graceful_leave(ev, {})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE, res)
        self.assertEqual(res["measured"][0]["not_in_view_at_quit"], [0, 1])

    def test_one_viewer_in_view_that_got_the_removal_passes_beside_an_unjudged_one(self):
        ev = self._ev(gone_at=15.4)
        ev["clients"][1]["events"] = []
        res = analyze.check_graceful_leave(ev, {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual(list(res["measured"][0]["others_removed_after_s"]), [0])

    def test_one_viewer_in_view_that_missed_the_removal_fails_beside_a_good_one(self):
        ev = self._ev(gone_at=15.4)
        ev["clients"][1]["events"] = [{"event": "entity_added", "id": "u2", "st": -1}]
        self.assertEqual(analyze.check_graceful_leave(ev, {})["status"], analyze.FAIL)

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

    def test_s08g_leaver_stays_inside_every_viewers_area_of_interest(self):
        """P5-S08G-LEAVE: the leaver once walked 10 s, ending at x~50 (AOI radius 50) and just outside a
        stationary viewer's interest, so that viewer had nothing to remove. At the 6 units/s speed cap
        it must end well inside the radius, from spawn offsets of a few units."""
        sc = scenarios.load("S08G")
        walk = sc["per_client"][2]["steps"][0]
        reach = (walk["t1"] - walk["t0"]) * 6.0
        self.assertLessEqual(reach + 10.0, 50.0 - 2.0)


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
        cls, _, _ = delivery.classify_gap(gap, srv, [], "recv_us", explain_fraction=0.5, slack_us=50_000,
                                          after_rows=0, relative_excess={"a_ms": 0.0, "b_ms": 400.0,
                                                                         "error_ms": 3.0})
        self.assertEqual(cls, "PATH")  # local fit supports receive-side excess


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

    # Reporting added after the frozen reference (M4: H2 skipped client gaps, H3 INFO tiers, H5 hop sizes). Additive and never
    # graded; every other field, verdicts included, must still equal the reference.
    ADDED_MEASURED = {"skipped_ticks_backwards", "skipped_client_gap_samples", "host_stalls_info_30ms", "single_process_freezes_1s"}
    ADDED_DETAIL = {"skipped_client_gaps", "info_stalls_30ms", "single_process_freezes", "hop_sizes_by_boundary"}

    def _results(self, mod, run):
        ev = mod.load_evidence(run)
        out = {}
        for r in mod.evaluate(ev):
            m = r.get("measured")
            if isinstance(m, dict):
                m = {k: v for k, v in m.items() if k not in self.ADDED_MEASURED}
            d = r.get("detail")
            if isinstance(d, dict):
                d = {k: v for k, v in d.items() if k not in self.ADDED_DETAIL}
            out[r["id"]] = (r["status"], m, r.get("threshold"), d)
        return out

    def test_results_equal_the_pre_streaming_analysis(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import reference_analyze_171c573 as old
        import synthetic_soak
        with tempfile.TemporaryDirectory() as d:
            run = synthetic_soak.write(Path(d), 820, 8)
            new_r, old_r = self._results(analyze, run), self._results(old, run)
            # host_guard is newer than the frozen reference; it has nothing to grade without guard evidence
            self.assertEqual(set(new_r) - set(old_r), {"host_guard"})
            self.assertEqual(new_r.pop("host_guard")[0], analyze.INFO)
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
            self.assertEqual(list(reversed(util.LazyNdjson(Path(d) / "missing.ndjson"))), [])

    def test_reversed_rows_equal_the_forward_rows_reversed(self):
        """R5-1: reversed() reads the file backwards in blocks. Tiny blocks put block edges inside
        lines and inside multi-byte characters; blank lines, CRLF, a null row and a cut-short last
        line are parsed or skipped exactly as the forward reader does."""
        text = ('{"a": 1, "s": "é€ὠ0"}\r\n\n{"a": 2}\nnull\n  \n{"broken"\n'
                + "".join(f'{{"a": {i}, "pad": "{"x" * (i % 13)}"}}\n' for i in range(3, 200)) + '{"a": 2')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ndjson"
            p.write_bytes(text.encode("utf-8"))
            forward = util.read_ndjson(p)
            self.assertEqual(len(forward), 200)
            for block in (1, 2, 3, 7, 64, 1 << 16):
                self.assertEqual(list(util.iter_ndjson_reversed(p, block_size=block)), forward[::-1], block)
            self.assertEqual(list(reversed(util.LazyNdjson(p))), forward[::-1])
            p.write_bytes(b"")
            self.assertEqual(list(reversed(util.LazyNdjson(p))), [])

    def test_last_match_on_a_large_stream_stays_bounded(self):
        """R5-1: a last-match search through reversed() (analyze._user_ids on events.ndjson)
        no longer loads the whole stream: the tracemalloc peak stays far under the file size even when
        the only match is the first row, and the result equals the full-list search's."""
        import tracemalloc
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.ndjson"
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write('{"event": "in_world", "user_id": "u-first"}\n')
                for i in range(120_000):
                    fh.write(f'{{"event": "entity_removed", "id": "e{i}", "st": {i * 0.01:.2f}}}\n')
            size = p.stat().st_size
            lazy = util.LazyNdjson(p)

            def last_in_world(rows):
                return next((e.get("user_id") for e in rows
                             if e.get("event") == "in_world" and e.get("user_id")), None)

            expected = last_in_world(reversed(util.read_ndjson(p)))
            tracemalloc.start()
            got = last_in_world(reversed(lazy))
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            self.assertEqual((got, expected), ("u-first", "u-first"))
            self.assertLess(peak, size / 10, f"peak {peak} B for a {size} B stream")
            ev = {"meta": {}, "clients": [{"index": 0, "summary": {}, "status": {}, "events": lazy}]}
            tracemalloc.start()
            ids = analyze._user_ids(ev)
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            self.assertEqual(ids, ["u-first"])
            self.assertLess(peak, size / 10, f"_user_ids peak {peak} B for a {size} B stream")

    def test_server_status_is_streamed_and_its_last_match_bounded(self):
        """R5-1: server status.ndjson (~30 MB in a 1 h soak) is a LazyNdjson, and _status_map_bounds
        finds the last row with map_bounds without loading the file."""
        import tracemalloc
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run"
            (run / "server").mkdir(parents=True)
            p = run / "server" / "status.ndjson"
            mb = {"min_x": -5, "min_y": -6, "max_x": 7, "max_y": 8, "source": "content"}
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({"_st": 0.0, "map_id": "map_01", "map_bounds": mb}) + "\n")
                for i in range(40_000):
                    fh.write(json.dumps({"_st": i + 1.0, "players_online": 3, "tick_rate": 60,
                                         "pad": "x" * 100}) + "\n")
            size = p.stat().st_size
            ev = analyze.load_evidence(run)
            self.assertTrue(isinstance(ev["server"]["status"], util.LazyNdjson), type(ev["server"]["status"]).__name__)
            expected = analyze._status_map_bounds({"server": {"status": util.read_ndjson(p)}})
            tracemalloc.start()
            got = analyze._status_map_bounds(ev)
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            self.assertEqual(got, expected)
            self.assertEqual(got["bounds"], {"minX": -5, "minY": -6, "maxX": 7, "maxY": 8})
            self.assertLess(peak, size / 10, f"peak {peak} B for a {size} B stream")


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



def _ev_line(c, a=0, b=0, c2=0, x=0.0, y=0.0, z=0.0, w=0.0, f=0, t=0.0):
    """One line in Netcode's PredictorTraceEvent.AppendJson form (8986908)."""
    return (f'{{"c":{c},"a":{a},"b":{b},"c2":{c2},"x":{x!r},"y":{y!r},"z":{z!r},"w":{w!r},'
            f'"u":0,"v":0,"f":{f},"t":{t!r}}}')


class PredictorTraceFixture:
    """A client-0 directory with a trace.ndjson as the TestLab recorder writes it: header, session,
    frame markers at 60 Hz on the realtime axis (scenario st = t - 100), a reconcile per frame, and
    scripted stalls in events.ndjson."""

    OFF = 100.0

    def __init__(self, root: Path):
        self.dir = root / "client-0"
        self.dir.mkdir(parents=True)
        self.lines = [json.dumps({"kind": "header", "schema": "rpg.testlab.predictor-trace.v1", "map": "dev_arena",
                                  "settings_read": True, "tick_rate": 60, "speed": 5.0,
                                  "bounds": [-50.0, -50.0, 50.0, 50.0], "tick_rate_is_fallback": False,
                                  "motor_3d": True}),
                      json.dumps({"kind": "session", "map": "dev_arena", "protocol": 3, "server_tick_rate": 60,
                                  "motor_3d": True, "predictor_tick_rate": 60})]
        self.events = [{"t": self.OFF + 1.0, "st": 1.0, "event": "in_world", "user_id": "u0"}]
        self.frame = 0
        self.snaps = 0

    def frames(self, st0: float, st1: float, corrections=None):
        """Frames from st0 to st1 (scenario s), each with input, steering, a reconcile and an advance;
        corrections maps a scenario time to (LastCorrection, snap) for the first frame at or after it."""
        corrections = dict(corrections or {})
        st = st0
        while st < st1:
            self.frame += 1
            t = self.OFF + st
            self.lines.append(json.dumps({"frame": self.frame, "t": t, "udt": 1 / 60, "dt": 1 / 60}))
            self.lines.append(_ev_line(5, a=self.frame, x=1.0))
            self.lines.append(_ev_line(66, a=self.frame, t=t))
            self.lines.append(_ev_line(64, a=self.frame, b=self.frame - 2, t=t))
            corr = 0.0
            for k in sorted(corrections):
                if k <= st:
                    corr, snap = corrections.pop(k)
                    self.snaps += 1 if snap else 0
                    break
            self.lines.append(_ev_line(6, a=self.frame - 2, b=self.frame, c2=self.frame - 2, x=st, y=0.0))
            self.lines.append(_ev_line(32, a=self.frame, b=0, c2=0, x=corr, y=st, z=0.0, w=float(self.snaps)))
            self.lines.append(_ev_line(65))
            self.lines.append(_ev_line(7, x=1 / 60))
            st = round(st + 1 / 60, 6)
        return self

    def stall(self, st: float, ms: int):
        t = self.OFF + st
        self.events.append({"t": t, "st": st, "event": "stall", "ms": ms, "actual_ms": ms,
                            "start": t, "end": t + ms / 1000.0})
        return self

    def build(self, tail: str = "") -> Path:
        _write(self.dir / "trace.ndjson", "\n".join(self.lines) + "\n" + tail)
        _write(self.dir / "events.ndjson", "".join(json.dumps(e) + "\n" for e in self.events))
        calls = sum(1 for ln in self.lines if ln.startswith('{"c"'))
        _write(self.dir / "summary.json", json.dumps({"trace": {"enabled": True, "file": "trace.ndjson",
                                                                "events": calls, "frames": self.frame,
                                                                "predictor_attached": True,
                                                                "steering_attached": True}}))
        _write(self.dir / "plan.json", json.dumps({"predictor_trace": True}))
        return self.dir


class PredictorTraceTests(unittest.TestCase):
    """T56: S13 records the Netcode predictor call trace on the stalled client (plan predictor_trace,
    client-0/trace.ndjson), provenance requires it there only, and `testlab.py replay-trace` validates
    it and lists the corrections the live predictor recorded per stall."""

    def _stalled(self, root: Path, tail: str = "") -> Path:
        # 500 ms stall at st 10: a 1.3 u catch-up correction and a 1.0 u second one; 2000 ms at st 25:
        # one 1.25 u; and a 0.2 u correction at st 5 outside every stall.
        fx = PredictorTraceFixture(root).stall(10.0, 500).stall(25.0, 2000)
        fx.frames(4.9, 5.1, {5.0: (0.2, False)})
        fx.frames(9.9, 10.7, {10.5: (1.3, True), 10.6: (1.0, True)})
        fx.frames(24.9, 27.2, {27.0: (1.25, True)})
        return fx.build(tail)

    def test_s13_traces_client_0_only_and_provenance_requires_it_there(self):
        from lab import provenance
        sc = scenarios.load("S13")
        self.assertEqual(scenarios.traced_clients(sc), [0])
        self.assertEqual([scenarios.client_plan(sc, i, "r")["predictor_trace"] for i in range(3)], [True, False, False])
        inv = provenance.expected_inventory(sc)
        self.assertIn("client-0/trace.ndjson", inv)
        self.assertNotIn("client-1/trace.ndjson", inv)
        s01 = scenarios.load("S01")
        self.assertEqual(scenarios.traced_clients(s01), [])
        self.assertFalse(scenarios.client_plan(s01, 0, "r")["predictor_trace"])
        self.assertFalse([p for p in provenance.expected_inventory(s01) if p.endswith("trace.ndjson")])
        on_all = _scenario(clients=2, client_defaults={"steps": [], "actions": [], "predictor_trace": True})
        self.assertEqual(scenarios.traced_clients(on_all), [0, 1])
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(_scenario(clients=1, per_client=[{"predictor_trace": "yes"}]))

    def test_a_valid_trace_gives_its_corrections_per_stall(self):
        from lab import predtrace
        with tempfile.TemporaryDirectory() as d:
            doc = predtrace.summarise(self._stalled(Path(d)))
            self.assertTrue(doc["valid"], doc["problems"])
            self.assertEqual(doc["warnings"], [])
            self.assertEqual(doc["header"]["map"], "dev_arena")
            self.assertEqual(doc["sessions"][0]["protocol"], 3)
            self.assertEqual(doc["counts"]["reconciles"], doc["counts"]["results"])
            s500, s2000 = doc["stalls"]
            self.assertEqual((s500["ms"], s500["st"], s500["count"], s500["snaps"], s500["max"]), (500, 10.0, 2, 2, 1.3))
            self.assertEqual([c["correction"] for c in s500["corrections"]], [1.3, 1.0])
            self.assertAlmostEqual(s500["corrections"][1]["st"], 10.6, delta=1 / 60)
            self.assertEqual((s2000["count"], s2000["max"]), (1, 1.25))
            self.assertEqual((doc["outside_stalls"]["count"], doc["outside_stalls"]["max"]), (1, 0.2))
            self.assertIn("stall 500 ms at st 10.0: 2 correction(s), 2 snap(s), max 1.3", predtrace.render(doc))

    def test_broken_traces_are_invalid_with_the_reason(self):
        from lab import predtrace
        cases = {
            "no header": (lambda ls: ls[1:], "line 1 is not the header"),
            "settings unknown": (lambda ls: [ls[0].replace('"settings_read": true', '"settings_read": false')] + ls[1:],
                                 "settings_read is false"),
            "reconcile without result": (lambda ls: [x for x in ls if not x.startswith('{"c":32')],
                                         "Reconcile followed by SteeringOnSnapshotEnd"),
            "result without reconcile": (lambda ls: [x for x in ls if not x.startswith('{"c":6,')],
                                         "ReconcileResult without a Reconcile"),
            "frames backwards": (lambda ls: ls[:2] + ls[2:][::-1], "frames must increase"),
            "steering not closed": (lambda ls: [x for x in ls if not x.startswith('{"c":65')],
                                    "SteeringOnSnapshotBegin inside"),
            "unknown call": (lambda ls: ls + [_ev_line(99)], "unknown call code 99"),
            "damaged middle line": (lambda ls: ls[:5] + ['{"c":5,'] + ls[5:], "not a JSON object"),
        }
        for name, (mutate, reason) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                fx = PredictorTraceFixture(Path(d)).stall(10.0, 500)
                fx.frames(9.9, 10.2, {10.0: (1.3, True)})
                fx.lines = mutate(fx.lines)
                doc = predtrace.summarise(fx.build())
                self.assertFalse(doc["valid"], name)
                self.assertTrue(any(reason in p for p in doc["problems"]), (name, doc["problems"]))
        with tempfile.TemporaryDirectory() as d:
            doc = predtrace.summarise(Path(d))
            self.assertFalse(doc["valid"])
            self.assertIn("no trace.ndjson", doc["problems"][0])

    def test_a_cut_short_last_line_and_a_late_attach_are_warnings(self):
        from lab import predtrace
        with tempfile.TemporaryDirectory() as d:
            fx = PredictorTraceFixture(Path(d)).stall(10.0, 500)
            fx.frames(9.9, 10.2, {10.0: (1.3, True)})
            fx.events.append({"t": 101.0, "st": 1.0, "event": "trace_attached", "target": "steering",
                              "snapshots_before": 3})
            doc = predtrace.summarise(fx.build(tail='{"c":7,"a":0'))
            self.assertTrue(doc["valid"], doc["problems"])
            self.assertTrue(any("cut-short last line" in w for w in doc["warnings"]), doc["warnings"])
            self.assertTrue(any("after 3 snapshot(s) (steering)" in w for w in doc["warnings"]), doc["warnings"])

    def test_replay_trace_command_exit_codes_and_output(self):
        import contextlib
        import io
        import testlab as cli
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run"
            self._stalled(run)
            (run / "client-1").mkdir()
            _write(run / "client-1" / "plan.json", json.dumps({"predictor_trace": False}))
            out = Path(d) / "out"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cli.main(["replay-trace", str(run), "--out", str(out)]), 0)
            self.assertIn("VALID", buf.getvalue())
            doc = json.loads((out / "trace-summary.json").read_text(encoding="utf-8"))
            self.assertEqual([c["client"] for c in doc["clients"]], [0])
            self.assertFalse((run / "trace-summary.json").exists())
            self.assertFalse((run / "client-0" / "trace-summary.json").exists())
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["replay-trace", str(run), "--client", "1"]), 1)
                lines = (run / "client-0" / "trace.ndjson").read_text(encoding="utf-8").splitlines()
                _write(run / "client-0" / "trace.ndjson", "\n".join(lines[1:]) + "\n")
                self.assertEqual(cli.main(["replay-trace", str(run)]), 1)
                empty = Path(d) / "empty"
                (empty / "client-0").mkdir(parents=True)
                self.assertEqual(cli.main(["replay-trace", str(empty)]), 2)
                self.assertEqual(cli.main(["replay-trace", str(Path(d) / "none")]), 3)

# =========================================================================== S16 malformed input / S17 churn

import hashlib  # noqa: E402
import hmac  # noqa: E402
import socket  # noqa: E402
import struct  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from lab import provenance, rawclient, rawprobe  # noqa: E402


class FakeLink:
    """A link whose incoming bytes the test feeds, for the framed reader."""

    def __init__(self):
        self.inbox, self.sent, self.closed = [], [], False
        self._cv = threading.Condition()

    def feed(self, data: bytes):
        with self._cv:
            self.inbox.append(data)
            self._cv.notify_all()

    def write(self, data):
        self.sent.append(bytes(data))

    def read_some(self, timeout):
        with self._cv:
            if not self.inbox and not self.closed:
                self._cv.wait(min(timeout, 0.05))
            if self.inbox:
                return self.inbox.pop(0)
            return None if self.closed else b""

    def close(self):
        self.closed = True
        with self._cv:
            self._cv.notify_all()


class RawClientTests(unittest.TestCase):
    def test_jwt_is_hs256_with_the_claims_the_services_read(self):
        tok = rawclient.sign_jwt("u1", "secret", server_id="gs-1", ttl_s=30)
        head, body, sig = tok.split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        import base64
        claims = json.loads(base64.urlsafe_b64decode(pad(body)))
        self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(head))), {"alg": "HS256", "typ": "JWT"})
        self.assertEqual((claims["sub"], claims["sid"]), ("u1", "gs-1"))
        self.assertEqual(claims["exp"] - claims["iat"], 30)
        self.assertTrue(claims["jti"])
        want = hmac.new(b"secret", f"{head}.{body}".encode(), hashlib.sha256).digest()
        self.assertEqual(base64.urlsafe_b64decode(pad(sig)), want)
        plain = rawclient.sign_jwt("u1", "secret")
        self.assertNotIn("sid", json.loads(base64.urlsafe_b64decode(pad(plain.split(".")[1]))))

    def test_frames_are_length_prefixed_json_envelopes_and_noise_is_reproducible(self):
        body = rawclient.json_body(7, {"tick": 1})
        self.assertEqual(json.loads(body), {"type": 7, "payload": {"tick": 1}})
        f = rawclient.frame(body)
        self.assertEqual(struct.unpack(">I", f[:4])[0], len(body))
        self.assertEqual(rawclient.random_bytes(16, 3), rawclient.random_bytes(16, 3))
        self.assertNotEqual(rawclient.random_bytes(16, 3), rawclient.random_bytes(16, 4))

    def test_the_reader_reassembles_split_frames_and_answers_pings(self):
        link = FakeLink()
        w = rawclient.Wire(link, "t")
        try:
            snap = rawclient.frame(rawclient.json_body(rawclient.MSG_SNAPSHOT, {"tick": 1, "entities": []}))
            link.feed(snap[:5])
            link.feed(snap[5:])
            ping = rawclient.frame(rawclient.json_body(rawclient.MSG_PING, {"timestamp": 1234}))
            link.feed(ping)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not (w.snapshot_times and link.sent):
                time.sleep(0.02)
            self.assertEqual(len(w.snapshot_times), 1)
            pong = json.loads(link.sent[0][4:])
            self.assertEqual((pong["type"], pong["payload"]["timestamp"]), (rawclient.MSG_PONG, 1234))
        finally:
            w.stop()

    def test_a_silent_peer_does_not_answer_pings_and_a_bad_length_is_recorded(self):
        link = FakeLink()
        w = rawclient.Wire(link, "t", answer_pings=False)
        try:
            link.feed(rawclient.frame(rawclient.json_body(rawclient.MSG_PING, {"timestamp": 1})))
            link.feed(struct.pack(">I", rawclient.MAX_FRAME + 1))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and w.bad_frame is None:
                time.sleep(0.02)
            self.assertEqual(link.sent, [])
            self.assertIn("length", w.bad_frame)
        finally:
            w.stop()

    def test_kcp_link_acks_what_it_receives_delivers_the_stream_and_retransmits_until_acked(self):
        hdr = rawclient._KCP_HDR
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        srv.settimeout(3)
        link = rawclient.KcpLink("127.0.0.1", srv.getsockname()[1], conv=77)
        try:
            link.write(b"hello")
            data, peer = srv.recvfrom(2048)
            conv, cmd, frg, _wnd, _ts, sn, una, ln = hdr.unpack_from(data)
            self.assertEqual((conv, cmd, frg, sn, ln), (77, 81, 0, 0, 5))
            self.assertEqual(data[hdr.size:hdr.size + 5], b"hello")
            again, _ = srv.recvfrom(2048)  # not acked: sent again
            self.assertEqual(hdr.unpack_from(again)[5], 0)
            srv.sendto(hdr.pack(77, 82, 0, 128, 0, 0, 1, 0), peer)  # ACK sn 0
            srv.sendto(hdr.pack(77, 81, 0, 128, 5, 0, 0, 3) + b"abc", peer)  # PUSH sn 0 from the server
            got = b""
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not got:
                got = link.read_some(0.2) or b""
            self.assertEqual(got, b"abc")
            seen_ack = False
            srv.settimeout(1)
            for _ in range(20):
                try:
                    d2, _ = srv.recvfrom(2048)
                except socket.timeout:
                    break
                if hdr.unpack_from(d2)[1] == 82:
                    seen_ack = True
                    break
            self.assertTrue(seen_ack, "the PUSH from the server was never acknowledged")
        finally:
            link.close()
            srv.close()

    def test_close_sends_nothing(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        srv.settimeout(0.5)
        link = rawclient.KcpLink("127.0.0.1", srv.getsockname()[1])
        link.close()
        with self.assertRaises(socket.timeout):
            srv.recvfrom(2048)
        srv.close()
        with self.assertRaises(rawclient.RawClientError):
            link.write(b"x")


class RawProbeHelperTests(unittest.TestCase):
    def test_metrics_parse_and_the_moved_filter(self):
        text = ('# TYPE x\ngameserver_connections{map_id="m"} 3\n'
                'gameserver_inputs_rejected_total{map_id="m",reason="invalid_direction"} 2\n'
                'gameserver_achieved_tick_hz{map_id="m"} 59.9\nother_metric 1\n')
        m = rawprobe.parse_metrics(text)
        self.assertEqual(len(m), 3)
        after = dict(m)
        after['gameserver_connections{map_id="m"}'] = 2
        after['gameserver_inputs_rejected_total{map_id="m",reason="invalid_direction"}'] = 5
        after['gameserver_achieved_tick_hz{map_id="m"}'] = 60.1
        moved = rawprobe.moved(m, after)
        self.assertEqual(moved, {'gameserver_connections{map_id="m"}': -1.0,
                                 'gameserver_inputs_rejected_total{map_id="m",reason="invalid_direction"}': 3.0})

    def test_evidence_lines_are_appended_and_a_failing_step_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            ev = rawprobe.Evidence(Path(d))
            ev.write({"record": "a", "n": 1})
            ev.write({"record": "b"})
            lines = (Path(d) / rawprobe.EVIDENCE).read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(x)["record"] for x in lines], ["a", "b"])
            old = rawprobe.STEPS.get("raw_churn")
            def boom(*a, **k):
                raise RuntimeError("step broke")
            rawprobe.STEPS["raw_churn"] = boom
            try:
                t = rawprobe.start("raw_churn", None, {}, {}, Path(d), None, print, threading.Event())
                t.join(5)
            finally:
                rawprobe.STEPS["raw_churn"] = old
            last = json.loads((Path(d) / rawprobe.EVIDENCE).read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(last["record"], "error")
            self.assertIn("step broke", last["error"])

    def test_every_sender_kind_is_known_and_the_scenario_validates_them(self):
        for kind in ("oversize_length", "length_ffffffff", "zero_length", "truncated_frame", "unknown_type",
                     "type_out_of_range", "garbage_envelope", "garbage_payload", "move_out_of_range",
                     "attack_out_of_range", "ability_cooldown"):
            self.assertIn(kind, rawprobe.SENDERS)
        bad = _scenario(disruptions=[{"at_s": 1, "kind": "raw_malformed", "cases": [{"id": "x", "kind": "nope"}]}])
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(bad)
        dup = _scenario(disruptions=[{"at_s": 1, "kind": "raw_malformed", "cases": [
            {"id": "x", "kind": "zero_length"}, {"id": "x", "kind": "zero_length"}]}])
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(dup)
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.validate(_scenario(disruptions=[{"at_s": 1, "kind": "raw_churn", "cycles": 1}]))
        scenarios.validate(_scenario(disruptions=[{"at_s": 1, "kind": "raw_churn", "cycles": 10}]))

    def test_garbage_senders_write_what_they_say(self):
        class Game:
            def __init__(self):
                self.sent, self.answer_pings = [], True

            def send(self, data):
                self.sent.append(data)

            def send_msg(self, t, p=None):
                self.sent.append(rawclient.frame(rawclient.json_body(t, p)))

        class P:
            user_id = "u"
            game = Game()
        ctx = {"seed": 5}
        rawprobe._send_oversize(P, ctx)
        rawprobe._send_length_ffffffff(P, ctx)
        rawprobe._send_zero_length(P, ctx)
        rawprobe._send_truncated(P, ctx)
        rawprobe._send_garbage_envelope(P, ctx)
        rawprobe._send_garbage_payload(P, ctx)
        s = P.game.sent
        self.assertEqual(struct.unpack(">I", s[0])[0], rawclient.MAX_FRAME + 1)
        self.assertEqual(s[1], b"\xff\xff\xff\xff")
        self.assertEqual(s[2], b"\x00\x00\x00\x00")
        self.assertEqual(struct.unpack(">I", s[3][:4])[0], 64)
        self.assertEqual(len(s[3]) - 4, 10)          # shorter than its length prefix
        self.assertFalse(P.game.answer_pings)         # the truncated peer goes silent
        self.assertEqual(s[4][4:5], b"\x0a")
        self.assertEqual(s[5][4:8], b"\x08\x07\x12\x10")
        self.assertEqual(s[4], rawprobe._send_garbage_envelope(P, ctx) and P.game.sent[-1])  # reproducible


def _case(cid, *, closes, closed_after=0.01, pre=2, snaps=0, moved=None, join=True, detail=None, sent_st=20.0,
          target_after=None, user=None, mid=None, post=None):
    mid = pre + 1 if mid is None else mid
    post = (pre if closes else pre + 1) if post is None else post
    base = lambda c: {"connections": c, "players_online": c, "metrics": {}, "entities": {}}  # noqa: E731
    p = base(post)
    p["metrics"] = {k: v for k, v in (moved or {}).items()}
    m = base(mid)
    m["metrics"] = {k: 0.0 for k in (moved or {})}
    return {"record": "case", "id": cid, "kind": cid, "user_id": user or f"raw-{cid}", "join": {"ok": join},
            "pre": base(pre), "mid": m, "post": p, "sent_st": sent_st,
            "closed_after_s": closed_after if closes else None, "snapshots_after_send": snaps,
            "detail": detail or {"sent": "x"}, "entity_before": {"x": 0, "y": 0, "speed": 5.0},
            "moved": {}}


RJ = 'gameserver_inputs_rejected_total{map_id="map_01",reason="%s"}'


def _rejected(rec, reason, n=3.0):
    """The rejection counter of `reason` rising by n between the read with the offender in and the final read."""
    rec["post"]["metrics"] = {RJ % reason: float(n)}
    rec["mid"]["metrics"] = {RJ % reason: 0.0}
    return rec


def _malformed_ev(cases, consts=None):
    ev = _ev(clients=2, duration=100)
    ev["rawprobe"] = list(cases) + [{"record": "end", "constants": consts or {"attack_range": {"value": 3.0}}}]
    return ev


MAL = {"cases": {"zero": {"expect": "closes", "within_s": 3.0}, "unk": {"expect": "stays_open"}}}
# the same, with the signal a stays_open case needs: a rejection counter that rises
MALR = {"cases": {"zero": {"expect": "closes", "within_s": 3.0},
                  "unk": {"expect": "stays_open", "rejections": {"attack_other": 1}}}}


class MalformedInputTests(unittest.TestCase):
    def test_a_refused_or_closing_case_passes(self):
        unk = _case("unk", closes=False, snaps=40)
        unk["post"]["metrics"] = {RJ % "attack_other": 1.0}
        unk["mid"]["metrics"] = {RJ % "attack_other": 0.0}
        ev = _malformed_ev([_case("zero", closes=True), unk])
        res = analyze.check_malformed_input(ev, MALR)
        self.assertEqual(res["status"], analyze.PASS, res)

    def test_a_case_that_stays_open_without_a_server_signal_is_inconclusive_never_pass(self):
        # RV-F8A-1: type 99 has no counter; staying connected is not an observation of a rejection.
        ev = _malformed_ev([_case("zero", closes=True), _case("unk", closes=False, snaps=40)])
        res = analyze.check_malformed_input(ev, MAL)
        self.assertEqual(res["status"], analyze.INCONCLUSIVE, res)
        self.assertIn("signal_missing", res["measured"]["unk"])
        self.assertEqual(res["detail"]["not_judged"], ["unk"])
        # the same case closing the session is a failure, signal or not
        ev = _malformed_ev([_case("zero", closes=True), _case("unk", closes=True)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.FAIL)
        # and a counter that rises is the signal
        up = _case("unk", closes=False, snaps=40)
        up["post"]["metrics"] = {RJ % "attack_other": 1.0}
        up["mid"]["metrics"] = {RJ % "attack_other": 0.0}
        rule = {"cases": {"unk": {"expect": "stays_open", "rejections": {"attack_other": 1}}}}
        self.assertEqual(analyze.check_malformed_input(_malformed_ev([up]), rule)["status"], analyze.PASS)

    def test_s16_unknown_type_is_judged_on_the_messages_rejected_counter(self):
        # rpg-mmo-server #490: gameserver_messages_rejected_total{reason="unknown_type"} counts an undefined type
        rule = next(a for a in scenarios.load("S16")["assertions"] if a["check"] == "malformed_input")["cases"]["unknown_type"]
        self.assertEqual(rule["expect"], "stays_open")
        self.assertEqual(rule["rejections_counter"], "gameserver_messages_rejected_total")
        self.assertEqual(rule["rejections"], {"unknown_type": 1})

    def test_a_named_counter_that_rises_passes_one_that_does_not_fails_and_a_missing_series_is_inconclusive(self):
        MR = 'gameserver_messages_rejected_total{map_id="map_01",reason="unknown_type"}'
        rule = {"cases": {"unk": {"expect": "stays_open", "rejections_counter": "gameserver_messages_rejected_total",
                                  "rejections": {"unknown_type": 1}}}}

        def case(post, mid=0.0):
            c = _case("unk", closes=False, snaps=40)
            c["post"]["metrics"] = {MR: post} if post is not None else {}
            c["mid"]["metrics"] = {MR: mid} if post is not None else {}
            return c

        self.assertEqual(analyze.check_malformed_input(_malformed_ev([case(1.0)]), rule)["status"], analyze.PASS)
        res = analyze.check_malformed_input(_malformed_ev([case(0.0)]), rule)
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertIn("gameserver_messages_rejected_total", " ".join(res["measured"]["unk"]["problems"]))
        # the counter's reason series is not the inputs counter's: a rising inputs counter does not count
        wrong = _case("unk", closes=False, snaps=40)
        wrong["post"]["metrics"], wrong["mid"]["metrics"] = {RJ % "unknown_type": 1.0}, {RJ % "unknown_type": 0.0}
        self.assertEqual(analyze.check_malformed_input(_malformed_ev([wrong]), rule)["status"], analyze.INCONCLUSIVE)
        # a server without the counter (no series at all) cannot tell: INCONCLUSIVE, not FAIL
        res = analyze.check_malformed_input(_malformed_ev([case(None)]), rule)
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)
        self.assertIn("does not export", res["measured"]["unk"]["signal_missing"])

    def test_a_session_that_stays_open_or_closes_late_fails(self):
        ev = _malformed_ev([_case("zero", closes=False, snaps=40), _case("unk", closes=False, snaps=40)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.FAIL)
        ev = _malformed_ev([_case("zero", closes=True, closed_after=9.0), _case("unk", closes=False, snaps=40)])
        res = analyze.check_malformed_input(ev, MAL)
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertIn("zero", res["detail"]["failed"])

    def test_another_session_lost_is_a_failure(self):
        # connections ended at 1 although two rendered clients were in: the bad frame took a neighbour with it
        ev = _malformed_ev([_case("zero", closes=True, post=1), _case("unk", closes=False, snaps=40)])
        res = analyze.check_malformed_input(ev, MAL)
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertIn("another session", " ".join(res["measured"]["zero"]["problems"]))

    def test_an_input_that_should_only_be_refused_must_not_close_and_must_keep_snapshots(self):
        ev = _malformed_ev([_case("zero", closes=True), _case("unk", closes=True)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.FAIL)
        ev = _malformed_ev([_case("zero", closes=True), _case("unk", closes=False, snaps=1)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.FAIL)

    def test_missing_failed_or_unjoined_cases_are_inconclusive_never_pass(self):
        self.assertEqual(analyze.check_malformed_input(_ev(clients=2), MAL)["status"], analyze.INCONCLUSIVE)
        ev = _malformed_ev([_case("zero", closes=True)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.INCONCLUSIVE)
        ev = _malformed_ev([_case("zero", closes=True, join=False), _case("unk", closes=False, snaps=40)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.INCONCLUSIVE)
        broken = _case("zero", closes=True)
        broken["error"] = "boom"
        ev = _malformed_ev([broken, _case("unk", closes=False, snaps=40)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.INCONCLUSIVE)

    def test_a_failure_wins_over_a_case_that_could_not_be_judged(self):
        ev = _malformed_ev([_case("zero", closes=False, snaps=40)])
        self.assertEqual(analyze.check_malformed_input(ev, MAL)["status"], analyze.FAIL)

    def test_rejection_counters_must_rise_and_zero_ones_must_not(self):
        rule = {"cases": {"mv": {"expect": "stays_open", "rejections": {"invalid_direction": 3}}}}
        up = _case("mv", closes=False, snaps=40, moved={RJ % "invalid_direction": 3.0})
        up["post"]["metrics"] = {RJ % "invalid_direction": 3.0}
        up["mid"]["metrics"] = {RJ % "invalid_direction": 0.0}
        self.assertEqual(analyze.check_malformed_input(_malformed_ev([up]), rule)["status"], analyze.PASS)
        low = _case("mv", closes=False, snaps=40)
        low["post"]["metrics"] = {RJ % "invalid_direction": 1.0}
        low["mid"]["metrics"] = {RJ % "invalid_direction": 0.0}
        self.assertEqual(analyze.check_malformed_input(_malformed_ev([low]), rule)["status"], analyze.FAIL)
        none = _case("mv", closes=False, snaps=40)
        self.assertEqual(analyze.check_malformed_input(_malformed_ev([none]), rule)["status"], analyze.FAIL)
        zero_rule = {"cases": {"mv": {"expect": "stays_open", "zero": ["invalid_direction"]}}}
        self.assertEqual(analyze.check_malformed_input(_malformed_ev([up]), zero_rule)["status"], analyze.FAIL)

    def test_no_teleport_the_server_position_stays_within_speed_times_elapsed(self):
        rule = {"cases": {"mv": {"expect": "stays_open", "max_displacement": True, "rejections": {"invalid_direction": 3}}}}
        rec = _rejected(_case("mv", closes=False, snaps=40, sent_st=20.0, user="raw-mv"), "invalid_direction")
        walk = [_row(20.0 + k * 0.2, [["raw-mv", "player", 0.0 + k * 0.2, 0, 100, 100, 0, 5.0]]) for k in range(20)]
        ev = _malformed_ev([rec])
        ev["server"]["entities"] = walk
        ev["traj"] = analyze.trajectories(walk)
        self.assertEqual(analyze.check_malformed_input(ev, rule)["status"], analyze.PASS)
        jump = walk[:5] + [_row(21.0, [["raw-mv", "player", 400.0, 0, 100, 100, 0, 5.0]])] + walk[6:]
        ev = _malformed_ev([rec])
        ev["server"]["entities"] = jump
        ev["traj"] = analyze.trajectories(jump)
        res = analyze.check_malformed_input(ev, rule)
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertIn("moved", " ".join(res["measured"]["mv"]["problems"]))
        ev["traj"] = {}
        self.assertEqual(analyze.check_malformed_input(ev, rule)["status"], analyze.INCONCLUSIVE)

    def test_attack_out_of_range_needs_a_far_target_and_no_hp_loss(self):
        rule = {"cases": {"atk": {"expect": "stays_open", "beyond_attack_range": True, "target_hp_unchanged": True,
                                  "rejections": {"attack_out_of_range": 1}}}}
        rec = _rejected(_case("atk", closes=False, snaps=40, sent_st=20.0,
                              detail={"sent": "x", "target": "enemy-1", "target_distance": 10.5, "target_hp": 16}),
                        "attack_out_of_range")
        hp = lambda v: [_row(20.0 + k * 0.2, [["enemy-1", "mob", 5, 5, v(k), 16, 0, 2.5]]) for k in range(40)]  # noqa: E731
        ev = _malformed_ev([rec])
        ev["server"]["entities"] = hp(lambda k: 16)
        ev["traj"] = analyze.trajectories(ev["server"]["entities"])
        self.assertEqual(analyze.check_malformed_input(ev, rule)["status"], analyze.PASS)
        ev["server"]["entities"] = hp(lambda k: 16 if k < 10 else 6)
        ev["traj"] = analyze.trajectories(ev["server"]["entities"])
        self.assertEqual(analyze.check_malformed_input(ev, rule)["status"], analyze.FAIL)
        near = _rejected(_case("atk", closes=False, snaps=40, detail={"sent": "x", "target": "enemy-1", "target_distance": 2.0,
                                                                      "target_hp": 16}), "attack_out_of_range")
        ev = _malformed_ev([near])
        ev["server"]["entities"] = hp(lambda k: 16)
        ev["traj"] = analyze.trajectories(ev["server"]["entities"])
        self.assertEqual(analyze.check_malformed_input(ev, rule)["status"], analyze.FAIL)

    def test_s16_asserts_every_case_it_runs_and_the_truncated_bound_is_the_heartbeat_derivation(self):
        sc = scenarios.load("S16")
        run = {c["id"] for d in sc["disruptions"] for c in d["cases"]}
        judged = next(a for a in sc["assertions"] if a["check"] == "malformed_input")["cases"]
        self.assertEqual(run, set(judged))
        # PingInterval 10 s, PongTimeout 30 s: the close lands on the 4th tick, 40 s after the connection starts.
        self.assertGreaterEqual(judged["truncated_frame"]["within_s"], 40.0)
        window = next(c for d in sc["disruptions"] for c in d["cases"] if c["id"] == "truncated_frame")["window_s"]
        self.assertGreater(window, judged["truncated_frame"]["within_s"])
        self.assertEqual(sc["clients"], 2)
        checks = {a["check"] for a in sc["assertions"]}
        self.assertTrue({"server_alive", "server_tick", "client_sessions", "snapshot_cadence"} <= checks)
        self.assertEqual(next(a for a in sc["assertions"] if a["check"] == "snapshot_cadence")["max_gap_ms"], 250)


class ServerAliveTests(unittest.TestCase):
    def _ev(self, uptimes, failed=0, step=1.0):
        st = [{"_st": i * step, "uptime_seconds": u} for i, u in enumerate(uptimes)]
        ev = _ev(clients=1, status=st)
        ev["meta"] = {"probe_counts": {"status_failed": failed}}
        return ev

    def test_a_steady_server_passes(self):
        self.assertEqual(analyze.check_server_alive(self._ev(list(range(30))), {})["status"], analyze.PASS)

    def test_a_restart_a_gap_or_a_failed_probe_fails(self):
        self.assertEqual(analyze.check_server_alive(self._ev([1, 2, 3, 4, 5, 1, 2, 3]), {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_server_alive(self._ev(list(range(30)), failed=1), {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_server_alive(self._ev(list(range(30)), step=9.0), {})["status"], analyze.FAIL)

    def test_too_little_evidence_is_inconclusive(self):
        self.assertEqual(analyze.check_server_alive(self._ev([1, 2]), {})["status"], analyze.INCONCLUSIVE)
        ev = self._ev(list(range(30)))
        ev["meta"] = {}
        self.assertEqual(analyze.check_server_alive(ev, {})["status"], analyze.INCONCLUSIVE)


class ClientSessionsTests(unittest.TestCase):
    def _ev(self, extra=None):
        ev = _ev(clients=2, duration=60)
        for c in ev["clients"]:
            c["events"] = [{"event": "net_state", "state": "InWorld", "st": -1}, {"event": "in_world", "st": -1}]
        if extra:
            ev["clients"][1]["events"].append(extra)
        return ev

    def test_no_change_after_the_start_passes(self):
        self.assertEqual(analyze.check_client_sessions(self._ev(), {})["status"], analyze.PASS)

    def test_a_state_change_or_a_disconnect_inside_the_window_fails(self):
        for extra in ({"event": "net_state", "state": "Reconnecting", "st": 30.0},
                      {"event": "disconnected", "st": 31.0}, {"event": "entities_reset", "st": 12.0}):
            self.assertEqual(analyze.check_client_sessions(self._ev(extra), {})["status"], analyze.FAIL, extra)

    def test_changes_outside_the_window_or_a_client_never_seen_in_world(self):
        late = {"event": "net_state", "state": "Ended", "st": 61.0}
        self.assertEqual(analyze.check_client_sessions(self._ev(late), {})["status"], analyze.PASS)
        ev = self._ev()
        ev["clients"][0]["events"] = []
        self.assertEqual(analyze.check_client_sessions(ev, {})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_client_sessions(_ev(clients=0), {})["status"], analyze.INCONCLUSIVE)


# ---- churn

DROP_U, LEAVE_U = "churn-d", "churn-l"


def _cycles(n=10, t0=8.0, connected=4.0, drop_down=3.0, leave_down=6.0, join_ok=True, join_s=0.03):
    out, t = [], t0
    for k in range(n):
        kind = "drop" if k % 2 == 0 else "leave"
        out.append({"record": "cycle", "n": k + 1, "kind": kind, "user_id": DROP_U if kind == "drop" else LEAVE_U,
                    "join_st": t, "join": {"ok": join_ok, "join_s": join_s, "error": None if join_ok else "refused"},
                    "snapshots": 50, "end_st": t + connected})
        t += connected + (drop_down if kind == "drop" else leave_down)
    return out


def _churn_ev(*, cycles=None, duration=185.0, drop_gone_after=60.0, leave_gone_after=0.5, ghost=None, rendered_extra=None,
              redis_after=None, players_online=2, rendered_draw=2, removed_events=True, lingering_leaver=False,
              shown=True):
    """Two rendered clients (a, b) and the churn step; server samples at 5 Hz, clients at 20 Hz."""
    cyc = cycles if cycles is not None else _cycles()
    ev = _ev(clients=2, duration=duration)
    for i, c in enumerate(ev["clients"]):
        c["summary"] = {"user_id": "ab"[i], "outcome": "completed"}
        c["events"] = []
        c["samples"] = []
    present = lambda uid, t: any(c["kind"] == ("drop" if uid == DROP_U else "leave") and c["user_id"] == uid  # noqa: E731
                                 for c in cyc if c["join_st"] <= t)
    last_drop_end = max(c["end_st"] for c in cyc if c["kind"] == "drop")
    rows = []
    for k in range(int(duration * 5)):
        t = k * 0.2
        ents = [["a", "player", 0, 0, 100, 100, 0, 5], ["b", "player", 1, 0, 100, 100, 0, 5]]
        for c in cyc:
            if c["kind"] == "leave" and c["join_st"] <= t < c["end_st"] + (duration if lingering_leaver else leave_gone_after):
                ents.append([LEAVE_U, "player", 3, 0, 100, 100, 0, 5])
            if c["kind"] == "drop" and c["join_st"] <= t:
                # a dropped player is held until the server notices and the hold runs out
                if t < last_drop_end + drop_gone_after:
                    ents.append([DROP_U, "player", 2, 0, 100, 100, 0, 5])
        if ghost and ghost[0] <= t <= ghost[1]:
            ents.append(["ghost-1", "player", 9, 9, 100, 100, 0, 5])
        rows.append(_row(t, list({e[0]: e for e in ents}.values())))
    ev["server"]["entities"] = rows
    ev["traj"] = analyze.trajectories(rows)
    status = []
    for k in range(int(duration)):
        n = 2 + (1 if any(c["join_st"] <= k < c["end_st"] for c in cyc) else 0)
        status.append({"_st": float(k), "players_online": n if k < last_drop_end + 5 else players_online,
                       "connections": n if k < last_drop_end + 5 else players_online})
    ev["server"]["status"] = status
    for c in ev["clients"]:
        c["samples"] = [{"st": k * 0.05, "ents": [["x%d" % j, "player", 0, 0, 0, 0, 0] for j in range(rendered_draw)]}
                        for k in range(int(duration * 20))]
        for cy in cyc:
            if cy["kind"] == "leave":
                if shown:
                    c["events"].append({"event": "entity_added", "id": LEAVE_U, "st": cy["join_st"] + 0.1})
                if removed_events:
                    c["events"].append({"event": "entity_removed", "id": LEAVE_U, "st": cy["end_st"] + 0.3})
    ev["rawprobe"] = [{"record": "start", "step": "raw_churn", "users": {"drop": DROP_U, "leave": LEAVE_U}}] + cyc + [
        {"record": "redis", "label": "before", "session_keys": ["session:a", "session:b"], "registry_keys": ["servers:id:gs"],
         "map_members": ["gs"]},
        {"record": "redis", "label": "after", **(redis_after or {"session_keys": ["session:a", "session:b"],
                                                               "registry_keys": ["servers:id:gs"], "map_members": ["gs"]})}]
    return ev


class ChurnTests(unittest.TestCase):
    def test_cycles_all_joined(self):
        ev = _churn_ev()
        res = analyze.check_churn_cycles(ev, {"cycles": 10})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual([r["kind"] for r in res["measured"][:3]], ["drop", "leave", "drop"])

    def test_a_refused_or_slow_join_fails_and_a_short_run_is_inconclusive(self):
        self.assertEqual(analyze.check_churn_cycles(_churn_ev(cycles=_cycles(join_ok=False)), {"cycles": 10})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_churn_cycles(_churn_ev(cycles=_cycles(join_s=9.0)), {"cycles": 10})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_churn_cycles(_churn_ev(cycles=_cycles(n=4)), {"cycles": 10})["status"], analyze.INCONCLUSIVE)
        self.assertEqual(analyze.check_churn_cycles(_ev(clients=2), {"cycles": 10})["status"], analyze.INCONCLUSIVE)

    def test_no_ghosts_when_everyone_is_gone_in_time(self):
        res = analyze.check_churn_ghosts(_churn_ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res["detail"])
        self.assertEqual(res["detail"]["unknown_player_ids"], [])

    def test_an_entity_nobody_owns_is_a_ghost(self):
        res = analyze.check_churn_ghosts(_churn_ev(ghost=(50.0, 60.0)), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["detail"]["unknown_player_ids"], ["ghost-1"])

    def test_a_leaver_that_lingers_fails(self):
        res = analyze.check_churn_ghosts(_churn_ev(lingering_leaver=True), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("graceful leave" in p for p in res["detail"]["problems"]))

    def test_a_dropped_player_that_never_expires_fails(self):
        res = analyze.check_churn_ghosts(_churn_ev(drop_gone_after=120.0), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("silently dropped" in p for p in res["detail"]["problems"]))

    def test_rendered_clients_that_keep_drawing_a_removed_player_fail(self):
        self.assertEqual(analyze.check_churn_ghosts(_churn_ev(rendered_draw=3), {})["status"], analyze.FAIL)
        res = analyze.check_churn_ghosts(_churn_ev(removed_events=False), {})
        self.assertEqual(res["status"], analyze.FAIL)

    def test_a_removal_is_not_judged_for_a_client_that_was_never_shown_the_leaver(self):
        # S17 v1 lesson: a rendered client that walked out of the area of interest has no entity_added and no
        # entity_removed; judging it would blame the server for what the client never saw.
        res = analyze.check_churn_ghosts(_churn_ev(shown=False, removed_events=False), {})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)
        self.assertFalse(any("did not drop" in p for p in res["detail"]["problems"]))

    def test_a_scenario_that_ends_before_the_bound_is_inconclusive(self):
        res = analyze.check_churn_ghosts(_churn_ev(duration=100.0), {})
        self.assertEqual(res["status"], analyze.INCONCLUSIVE)

    def test_player_count_returns_to_the_baseline(self):
        self.assertEqual(analyze.check_player_count_baseline(_churn_ev(), {})["status"], analyze.PASS)
        res = analyze.check_player_count_baseline(_churn_ev(players_online=3), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(res["measured"]["off_baseline"])

    def test_player_count_peak_above_the_two_churn_users_fails(self):
        ev = _churn_ev()
        ev["server"]["status"][20]["players_online"] = 6
        self.assertEqual(analyze.check_player_count_baseline(ev, {"max_extra": 2})["status"], analyze.FAIL)

    def test_redis_keys_are_compared_by_name(self):
        self.assertEqual(analyze.check_redis_leak(_churn_ev(), {})["status"], analyze.PASS)
        leak = {"session_keys": ["session:a", "session:b", "session:churn-d"], "registry_keys": ["servers:id:gs"], "map_members": ["gs"]}
        res = analyze.check_redis_leak(_churn_ev(redis_after=leak), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertEqual(res["detail"]["session_keys"]["leaked"], ["session:churn-d"])
        swapped = {"session_keys": ["session:a", "session:c"], "registry_keys": ["servers:id:gs"], "map_members": ["gs"]}
        self.assertEqual(analyze.check_redis_leak(_churn_ev(redis_after=swapped), {})["status"], analyze.FAIL)

    def test_redis_baseline_without_the_rendered_sessions_or_a_missing_point_is_inconclusive(self):
        ev = _churn_ev()
        ev["rawprobe"] = [r for r in ev["rawprobe"] if r.get("label") != "after"]
        self.assertEqual(analyze.check_redis_leak(ev, {})["status"], analyze.INCONCLUSIVE)
        ev = _churn_ev()
        next(r for r in ev["rawprobe"] if r.get("label") == "before")["session_keys"] = []
        self.assertEqual(analyze.check_redis_leak(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_s17_fits_its_own_timeline_and_asserts_the_whole_list(self):
        sc = scenarios.load("S17")
        d = next(x for x in sc["disruptions"] if x["kind"] == "raw_churn")
        cyc = d["cycles"]
        drops, leaves = (cyc + 1) // 2, cyc // 2
        busy = cyc * d["connected_s"] + drops * d["drop_down_s"] + leaves * d["leave_down_s"]
        ghosts = next(a for a in sc["assertions"] if a["check"] == "churn_ghosts")
        # the wait outlasts the longest server hold, and the run leaves a quiet window after it
        self.assertGreaterEqual(d["settle_s"], ghosts["drop_gone_within_s"] - 10.0)
        self.assertGreaterEqual(sc["duration_s"], d["at_s"] + busy + ghosts["drop_gone_within_s"] + 5.0)
        # 30 s EntityHoldTTL + 10 s ping + 30 s pong timeout + 5 s slack
        self.assertGreaterEqual(ghosts["drop_gone_within_s"], 75.0)
        checks = {a["check"] for a in sc["assertions"]}
        self.assertTrue({"churn_cycles", "churn_ghosts", "player_count_baseline", "redis_leak", "entity_lifecycle",
                         "client_sessions", "snapshot_cadence", "server_alive"} <= checks)
        self.assertEqual(sc["clients"], 2)

    def test_provenance_requires_the_raw_probe_file_only_for_raw_scenarios(self):
        self.assertIn("rawprobe.ndjson", provenance.expected_inventory(scenarios.load("S16")))
        self.assertIn("rawprobe.ndjson", provenance.expected_inventory(scenarios.load("S17")))
        self.assertNotIn("rawprobe.ndjson", provenance.expected_inventory(scenarios.load("S15")))
        self.assertIn("rawprobe.ndjson", provenance.MANIFEST_FILES)


class HostGuardTests(unittest.TestCase):
    """The host guard (lab/hostguard.py): AnyDesk log parsing, guards G1-G5, the INVALID verdict and the
    preflight. Pure parts on real log lines (fixtures/ad_trace_sessions.txt, ids scrubbed)."""

    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ad_trace_sessions.txt"
    CLOCK_RATE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "clock-rate-status.json.gz"

    @staticmethod
    def _t(stamp):
        import datetime as dt
        return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()

    def _events(self):
        from lab import hostguard
        return hostguard.parse_ad_trace(self.FIXTURE.read_bytes())

    @staticmethod
    def _idle(start, end, step=5.0, pid_base=1000, **extra):
        """Samples of a host with the three AnyDesk residents idle."""
        out, t = [], start
        while t <= end:
            out.append({"epoch": t, "ts": f"t{t:.0f}", "cpu": 15.0, "ad_cpu": 0.03,
                        "ad": [{"pid": pid_base + i, "role": "resident", "cpu": 0.01} for i in range(3)],
                        "groups": {"build": 0.2, "av": 0.0, "agents": 0.5, "node": 0.0}, "own_cpu": 0.03, **extra})
            t += step
        return out

    def _guard_ev(self, samples, events, window, required=False, preflight=None):
        ev = _ev()
        ev["scenario"]["requires_clean_host"] = required
        ev["meta"] = {"host_guard": {"window_epoch": list(window), "start_wall_epoch": window[0] + 30,
                                     "required": required}}
        ev["hostguard"] = {"samples": samples, "events": events, "summary": None, "preflight": preflight}
        return ev

    # (a) the real excerpt
    def test_a_real_ad_trace_excerpt_parses_into_the_expected_sessions(self):
        import re
        from lab import hostguard
        data = self.FIXTURE.read_bytes()
        events, off = hostguard.parse_ad_trace(data)
        self.assertEqual(off, len(data))                       # every line was complete
        self.assertEqual(hostguard.parse_ad_trace(data, off), ([], off))
        sessions = hostguard.sessions_from_events(events)
        started = [x for x in sessions if x["start"] is not None]
        orphan = [x for x in sessions if x["start"] is None]
        self.assertEqual((len(started), len(orphan)), (16, 1))   # 16 Accepts; one session began before the log did
        self.assertTrue(all(x["end"] is not None for x in sessions))
        first = started[0]
        self.assertEqual(first["backend_pid"], 18720)
        self.assertAlmostEqual(first["start"], self._t("2026-10-23 16:05:43") + 0.440, places=3)
        self.assertAlmostEqual(first["end"] - first["start"], 59.717, places=3)   # 16:05:43.440 -> 16:06:43.157
        by_pid = {x["backend_pid"]: x for x in started}
        self.assertEqual(by_pid[77944]["end_reason"], "net_closed")             # the 05:17Z session ended on a socket close
        self.assertEqual(by_pid[18720]["end_reason"], "session_closed")
        # scrubbed: no peer id, address, fingerprint or relay name in the fixture, none copied into an event
        text = data.decode("utf-8")
        self.assertIsNone(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text))
        self.assertNotIn("FPR", text)
        self.assertEqual(set(re.findall(r"\b\d{9,}\b", text)), {"0000000001"})
        self.assertNotIn("0000000001", json.dumps(events))
        self.assertTrue(all(set(e) <= {"type", "ts", "epoch", "proc", "pid", "source", "fiber", "backend_pid"} for e in events))

    # (b) residents only
    def test_b_residents_only_and_idle_cpu_is_info_and_does_not_block_pass(self):
        from lab import hostguard
        w = (self._t("2026-10-24 18:00:00"), self._t("2026-10-24 18:30:00"))
        res = hostguard.evaluate(self._idle(w[0] - 60, w[1] + 5), [], w, baseline_pids=[1000, 1001, 1002])
        self.assertEqual(res["fired"], [])
        self.assertLess(res["stats"]["guard_own_cpu_pct"]["max"], 1.0)
        out = analyze.check_host_guard(self._guard_ev(self._idle(w[0] - 60, w[1] + 5), [], w), {})
        self.assertEqual(out["status"], analyze.INFO)
        self.assertEqual(analyze.overall([{"status": analyze.PASS}, out]), analyze.PASS)

    # (c) a session inside the window
    def test_c_session_in_window_is_invalid_even_when_every_other_check_passes(self):
        events, _ = self._events()
        w = (self._t("2026-10-23 16:05:13"), self._t("2026-10-23 16:20:00"))
        out = analyze.check_host_guard(self._guard_ev(self._idle(w[0], w[1]), events, w), {})
        self.assertEqual(out["status"], analyze.INVALID)
        self.assertEqual(out["detail"]["fired"][0]["id"], "G1")
        self.assertIn("G1", out["measured"]["fired"])
        results = [{"id": "a", "check": "x", "status": analyze.PASS}, {"id": "b", "check": "y", "status": analyze.PASS}, {**out, "check": "host_guard"}]
        self.assertEqual(analyze.overall(results), analyze.INVALID)
        self.assertNotEqual(analyze.overall(results), analyze.PASS)

    # (d) started before the window and still active at its start
    def test_d_session_active_at_window_start_fires_g1(self):
        from lab import hostguard
        events, _ = self._events()
        cut = self._t("2026-10-23 16:05:50")
        events = [e for e in events if e["epoch"] <= cut]       # the log shows the session open, nothing after
        w = (self._t("2026-10-23 16:06:00"), self._t("2026-10-23 16:30:00"))
        samples = self._idle(w[0], w[1], pid_base=18000)
        for sample in samples:
            sample["ad"] = sample["ad"] + [{"pid": 18720, "role": "backend", "cpu": 0.2}]
        res = hostguard.evaluate(samples, events, w, baseline_pids=[18000, 18001, 18002])
        g1 = next(f for f in res["fired"] if f["id"] == "G1")
        self.assertTrue(any("active at window start" in x for x in g1["evidence"]), g1)
        out = analyze.check_host_guard(self._guard_ev(samples, events, w), {})
        self.assertEqual(out["status"], analyze.INVALID)

    # (e) ended well before the window
    def test_e_session_that_ended_over_30_s_before_the_window_does_not_fire(self):
        from lab import hostguard
        events, _ = self._events()
        w = (self._t("2026-10-23 16:07:20"), self._t("2026-10-23 16:08:30"))   # session ended 16:06:43; next accept 16:09:24
        res = hostguard.evaluate(self._idle(w[0], w[1]), events, w, baseline_pids=[1000, 1001, 1002])
        self.assertEqual(res["fired"], [])
        self.assertEqual(hostguard.WINDOW_PRE_S, 30.0)


    # (e2) a log re-read after rotation must not shift the session pairing (run 9tgw)
    ROTATED_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ad_events_rotated_reread.ndjson.gz"

    def _rotated_events(self):
        with gzip.open(self.ROTATED_FIXTURE, "rt", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _rotated_samples(self, w):
        """Idle residents; the real session's backend (pid 111932) lives 13:14:49-13:16:14 at 5.9 % of host."""
        samples = self._idle(w[0], w[1], pid_base=18000)
        lo, hi = self._t("2026-10-25 13:14:49"), self._t("2026-10-25 13:16:14")
        for s in samples:
            if lo <= s["epoch"] <= hi:
                s["ad"] = s["ad"] + [{"pid": 111932, "role": "backend", "cpu": 5.9}]
                s["ad_cpu"] = 5.9
        return samples

    def test_e2_rotation_reread_does_not_create_a_false_historical_g1(self):
        from lab import hostguard
        events = self._rotated_events()
        self.assertEqual(sum(1 for e in events if e["type"] == "log_rotated"), 1)
        self.assertGreater(sum(1 for e in events if e["type"] == "accept"), len({e["epoch"] for e in events if e["type"] == "accept"}))
        sessions = hostguard.sessions_from_events(events)
        self.assertEqual([x for x in sessions if x["start"] is not None and x["end"] is None], [])
        real = [x for x in sessions if x["backend_pid"] == 111932]
        self.assertEqual(len(real), 1)
        self.assertAlmostEqual(real[0]["start"], self._t("2026-10-25 13:14:43") + 0.649, places=3)
        self.assertAlmostEqual(real[0]["end"], self._t("2026-10-25 13:16:14") + 0.190, places=3)
        for x in sessions:                      # every session ends after it starts and within an hour
            if x["start"] is not None and x["end"] is not None:
                self.assertTrue(0 <= x["end"] - x["start"] < 3600, x)
        w = (self._t("2026-10-25 13:07:13"), self._t("2026-10-25 14:08:03"))
        res = hostguard.evaluate(self._rotated_samples(w), events, w, baseline_pids=[18000, 18001, 18002])
        ids = [f["id"] for f in res["fired"]]
        self.assertEqual(ids, ["G1", "G2", "G3"])
        g1 = next(f for f in res["fired"] if f["id"] == "G1")
        self.assertFalse(any("active at window start" in x for x in g1["evidence"]), g1)
        self.assertTrue(any("2026-10-25T13:14:4" in x for x in g1["evidence"]), g1)
        self.assertTrue(any("--backend pid 111932" in x for x in g1["evidence"]), g1)
        self.assertFalse(any("2026-10-25T02:38:15" in x or "03:24:59" in x for x in g1["evidence"]), g1)

    def test_e3_open_ended_old_session_needs_a_live_backend(self):
        from lab import hostguard
        events = [e for e in self._rotated_events() if e.get("epoch", 0) <= self._t("2026-10-25 03:25:10")]
        w = (self._t("2026-10-25 13:07:13"), self._t("2026-10-25 13:30:00"))
        idle = hostguard.evaluate(self._idle(w[0], w[1], pid_base=18000), events, w, baseline_pids=[18000, 18001, 18002])
        self.assertEqual(idle["fired"], [])               # an accept with no end seen hours ago, nothing alive
        samples = self._idle(w[0], w[1], pid_base=18000)
        for s in samples:
            s["ad"] = s["ad"] + [{"pid": 60100, "role": "backend", "cpu": 0.2}]
        live = hostguard.evaluate(samples, events, w, baseline_pids=[18000, 18001, 18002])
        g1 = next(f for f in live["fired"] if f["id"] == "G1")
        self.assertTrue(any("active at window start" in x for x in g1["evidence"]), g1)

    def test_e3a_recent_open_session_needs_a_live_backend(self):
        from lab import hostguard
        window_start = self._t("2026-10-25 13:07:13")
        accept = window_start - 90.0
        events = [{"type": "accept", "epoch": accept, "ts": hostguard.iso_utc(accept), "proc": "ad",
                   "pid": 50000, "source": "ad_trace"}]
        w = (window_start, self._t("2026-10-25 13:30:00"))
        idle = self._idle(w[0], w[1], pid_base=18000)

        no_backend = hostguard.evaluate(idle, events, w, baseline_pids=[18000, 18001, 18002])
        self.assertEqual(no_backend["fired"], [])

        samples = self._idle(w[0], w[1], pid_base=18000)
        for sample in samples:
            sample["ad"] = sample["ad"] + [{"pid": 60100, "role": "backend", "cpu": 0.2}]
        live_backend = hostguard.evaluate(samples, events, w, baseline_pids=[18000, 18001, 18002])
        g1 = next(f for f in live_backend["fired"] if f["id"] == "G1")
        self.assertTrue(any("active at window start" in x for x in g1["evidence"]), g1)

    def test_e4_replayed_events_are_dropped_once(self):
        from lab import hostguard
        events, _ = self._events()
        self.assertEqual(hostguard.sessions_from_events(events + events), hostguard.sessions_from_events(events))

    # (f) a new AnyDesk pid with no readable log
    def test_f_new_anydesk_pid_fires_g2_without_a_log(self):
        from lab import hostguard
        w = (self._t("2026-10-24 18:00:00"), self._t("2026-10-24 18:10:00"))
        samples = self._idle(w[0] - 30, w[1])
        for sm in samples:
            if sm["epoch"] >= w[0] + 100:
                sm["ad"] = sm["ad"] + [{"pid": 4242, "role": "other", "cpu": 0.0}]
        res = hostguard.evaluate(samples, [], w, baseline_pids=[1000, 1001, 1002])
        self.assertEqual([f["id"] for f in res["fired"]], ["G2"])
        self.assertIn("4242", res["fired"][0]["evidence"][0])
        # a session backend is both a session (G1) and a new process (G2), log or no log
        for sm in samples:
            for q in sm["ad"]:
                if q["pid"] == 4242:
                    q["role"] = "backend"
        self.assertEqual([f["id"] for f in hostguard.evaluate(samples, [], w, baseline_pids=[1000, 1001, 1002])["fired"]], ["G1", "G2"])

    # (g) truncated and rotated logs
    def test_g_truncated_rotated_and_partial_logs(self):
        from lab import hostguard
        data = self.FIXTURE.read_bytes()
        events_all, _ = hostguard.parse_ad_trace(data)
        # a last line still being written is left for the next call, and read exactly once afterwards
        cut = data.index(b"Backend PID: 18720") + 8
        part, off = hostguard.parse_ad_trace(data[:cut])
        self.assertTrue(off < cut and data[off - 1:off] == b"\n")
        rest, off2 = hostguard.parse_ad_trace(data, off)
        self.assertEqual(len(part) + len(rest), len(events_all))
        self.assertEqual(off2, len(data))
        # truncation (rotation): a file shorter than the offset restarts at 0 and says so
        small, off3 = hostguard.parse_ad_trace(data[:200], len(data))
        self.assertEqual(small[0]["type"], "log_rotated")
        self.assertLessEqual(off3, 200)
        # CRLF and LF read the same
        lf, _ = hostguard.parse_ad_trace(data.replace(b"\r\n", b"\n"))
        self.assertEqual([e["type"] for e in lf], [e["type"] for e in events_all])
        # the tailer, on a real file: prime, append, rotate; never raises
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "ad.trace"
            log.write_bytes(data)
            g = hostguard.HostGuard(Path(d) / "host", paths=hostguard.AnyDeskPaths(log, None))
            g.out.mkdir()
            state = {"off": None}
            g._poll_ad(state)
            n = g.events
            self.assertGreater(n, 100)
            log.write_bytes(data[:300])                       # rotated
            g._poll_ad(state)
            self.assertIn("log_rotated", [r["type"] for r in util.read_ndjson(g.out / "anydesk-events.ndjson")])
            self.assertEqual(g.errors, [])

    def test_ad_trace_replacement_at_or_above_offset_replays_prefix(self):
        from lab import hostguard
        session = (b"info 2026-10-24 18:01:02.123 lsvc 14696 17760 12 anynet.any_socket - "
                   b"Session started\n")
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "ad.trace"
            old = b"old-prefix-" + b"o" * (2 << 20) + b"\n"
            log.write_bytes(old)
            g = hostguard.HostGuard(Path(d) / "host", paths=hostguard.AnyDeskPaths(log, None))
            g.out.mkdir()
            state = {"off": None}
            g._poll_ad(state)
            old_offset = state["off"]
            self.assertGreater(old_offset, len(session))

            for target_size in (len(old), len(old) + 1000):
                prefix = b"new-prefix-" + str(target_size).encode() + b"\n" + session
                replacement = prefix + b"n" * (target_size - len(prefix))
                log.write_bytes(replacement)
                before = g.events
                g._poll_ad(state)
                rows = util.read_ndjson(g.out / "anydesk-events.ndjson")
                self.assertGreater(g.events, before)
                self.assertTrue(any(r["type"] == "session_started" for r in rows), target_size)
                self.assertEqual(g.errors, [])

    def test_unavailable_ad_file_identity_emits_blind_evidence_for_g5(self):
        from unittest import mock
        from lab import hostguard
        w = (self._t("2026-10-24 18:00:00"), self._t("2026-10-24 18:10:00"))
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "ad.trace"
            log.write_bytes(b"log\n")
            g = hostguard.HostGuard(Path(d) / "host", paths=hostguard.AnyDeskPaths(log, None))
            g.out.mkdir()
            with mock.patch.object(hostguard, "_ad_file_identity", return_value=None), \
                 mock.patch.object(hostguard.time, "time", return_value=w[0] + 1):
                g._poll_ad({"off": None})
            events = util.read_ndjson(g.out / "anydesk-events.ndjson")
            result = hostguard.evaluate(self._idle(w[0], w[1]), events, w)
            self.assertIn("G5", [f["id"] for f in result["fired"]])
            self.assertTrue(any("identity unavailable" in x for f in result["fired"] for x in f["evidence"]))

    # (h) a blind guard
    def test_h_sampler_gap_over_three_intervals_fires_g5(self):
        from lab import hostguard
        w = (self._t("2026-10-24 18:00:00"), self._t("2026-10-24 18:10:00"))
        base = [1000, 1001, 1002]
        samples = [x for x in self._idle(w[0] - 10, w[1] + 10) if not (w[0] + 100 < x["epoch"] < w[0] + 125)]   # 25 s gap
        gap = hostguard.evaluate(samples, [], w, baseline_pids=base)
        self.assertEqual([f["id"] for f in gap["fired"]], ["G5"])
        ok = [x for x in self._idle(w[0] - 10, w[1] + 10) if not (w[0] + 100 < x["epoch"] < w[0] + 114)]          # 3 missed intervals
        self.assertEqual(hostguard.evaluate(ok, [], w, baseline_pids=base)["fired"], [])
        # a guard that died at the start or never produced a sample is blind too
        self.assertEqual([f["id"] for f in hostguard.evaluate([], [], w)["fired"]], ["G5"])
        early_end = self._idle(w[0] - 10, w[0] + 60)
        self.assertEqual([f["id"] for f in hostguard.evaluate(early_end, [], w, baseline_pids=base)["fired"]], ["G5"])

    def test_h2_hold_until_waits_for_a_sample_past_the_window_end(self):
        from unittest import mock
        from lab import hostguard
        with tempfile.TemporaryDirectory() as d:
            g = hostguard.HostGuard(Path(d) / "host", interval_s=5.0, paths=hostguard.AnyDeskPaths(None, None))
            g.proc = mock.Mock()
            g.proc.poll.return_value = None
            now = [1000.0]
            sleeps, produce = [], [True]

            def sleep(s):
                sleeps.append(s)
                now[0] += s
                if produce and now[0] >= 1012.0:           # the sampler's next row, 2 s after the window end
                    g.last_epoch = now[0]

            with mock.patch.object(hostguard.time, "time", side_effect=lambda: now[0]),                     mock.patch.object(hostguard.time, "sleep", side_effect=sleep):
                g.last_epoch = 995.0                       # the last row is 15 s before the window end
                self.assertTrue(g.hold_until(1010.0))
                self.assertGreaterEqual(now[0], 1012.0)
                # a sampler that never answers: gives up after one interval + slack, never claims a sample
                g.last_epoch, now[0] = 995.0, 1000.0
                produce.clear()
                self.assertFalse(g.hold_until(1010.0))
                self.assertLess(now[0], 1010.0 + 5.0 + hostguard.HOLD_SLACK_S + 1.0)
                # a dead sampler returns at once
                g.proc.poll.return_value = 1
                now[0] = 1000.0
                self.assertFalse(g.hold_until(1010.0))
                self.assertEqual(now[0], 1000.0)

    def test_g6_9mre_status_series_fires_and_flat_i9fl_e26z_do_not(self):
        from lab import hostguard
        with gzip.open(self.CLOCK_RATE_FIXTURE, "rt", encoding="utf-8") as fh:
            series = json.load(fh)["series"]
        nine = hostguard.evaluate_clock_rate(series["20261024T194653Z-S09-9mre"])
        g6 = next((f for f in nine["fired"] if f["id"] == "G6"), None)
        self.assertIsNotNone(g6)
        # F4: two episodes are F23 Finding B (564, 2990); 2 is start-up; 2288 and 2431 are unexplained (60 ticks/s regime)
        self.assertEqual(g6["episodes"], 5)
        starts = [float(e.split("scenario st ")[1].split("..")[0]) for e in g6["evidence"]]
        self.assertEqual([round(x) for x in starts], [2, 564, 2288, 2431, 2990])
        self.assertGreater(nine["stats"]["valid_intervals"], 3000)
        self.assertAlmostEqual(nine["stats"]["median_ticks_per_harness_s"], 55.0, delta=1.0)
        for run_id in ("20261023T071851Z-S09-i9fl", "20261023T040945Z-S09-e26z"):
            with self.subTest(run_id=run_id):
                self.assertEqual(hostguard.evaluate_clock_rate(series[run_id])["fired"], [])

    def test_g6_does_not_fire_for_a_server_tick_slowdown(self):
        from lab import hostguard
        rows = []
        tick = 0
        for second in range(12):
            if second:
                tick += 25 if 4 <= second <= 7 else 55
            healthy = not 4 <= second <= 7
            rows.append({"_mono": 1000.0 + second, "_st": float(second), "current_tick": tick,
                         "sim_critical_hz": 60, "achieved_tick_hz": 60 if healthy else 30})
        self.assertEqual(hostguard.evaluate_clock_rate(rows)["fired"], [])
        tick_check = analyze.check_server_tick(_ev(duration=12, status=rows), {})
        self.assertEqual(tick_check["status"], analyze.FAIL)

    @staticmethod
    def _g6_series(seconds, tick_at, achieved_at, mono_error=None):
        rows = []
        for s in range(seconds + 1):
            err = mono_error(s) if mono_error else 0.0
            # the poll loop runs slightly slower than 1 Hz
            rows.append({"_mono": 1000.0 + s * 1.001 + err, "_st": float(s), "current_tick": round(tick_at(float(s))),
                         "sim_critical_hz": 60, "achieved_tick_hz": achieved_at(float(s))})
        return rows

    def test_g6_never_fires_on_a_stall_seen_through_the_lagging_meter(self):
        from lab import hostguard

        def run(stall_start, rate, phase):
            def tick_at(t):                              # 55 ticks/s skew, `rate` ticks/s inside the 15 s stall
                end = stall_start + 15.0
                inside = max(0.0, min(t, end) - stall_start)
                return 55.0 * (t - inside) + rate * inside

            def achieved_at(t):                          # last completed 2 s window, published at its end
                window_end = ((t - phase) // 2.0) * 2.0 + phase
                rate_in_window = (tick_at(window_end) - tick_at(window_end - 2.0)) / 2.0
                return rate_in_window * (60.0 / 55.0)
            return self._g6_series(40, tick_at, achieved_at)

        for rate in (45.0, 30.0, 10.0, 1.0, 0.0):
            for start in range(0, 20, 2):                 # stall start phase x meter window phase
                for phase in range(0, 20, 2):
                    with self.subTest(rate=rate, start=start, phase=phase):
                        rows = run(11.0 + start * 0.05, rate, phase * 0.1)
                        self.assertEqual(hostguard.evaluate_clock_rate(rows)["fired"], [])

    def test_g6_ignores_polling_jitter_and_a_single_latency_spike(self):
        from lab import hostguard
        flat = lambda t: 55.0 * t
        healthy = lambda t: 60
        # +70 ms on every other poll for 40 s: the true rate never moved
        alternating = self._g6_series(40, flat, healthy, lambda s: 0.07 if s % 2 else 0.0)
        self.assertEqual(hostguard.evaluate_clock_rate(alternating)["fired"], [])
        # seeded random +-70 ms
        import random
        rng = random.Random(7)
        noise = [rng.uniform(-0.07, 0.07) for _ in range(41)]
        self.assertEqual(hostguard.evaluate_clock_rate(self._g6_series(40, flat, healthy, lambda s: noise[s]))["fired"], [])
        # one poll answered 0.4 s late
        spike = self._g6_series(40, flat, healthy, lambda s: 0.4 if s == 20 else 0.0)
        self.assertEqual(hostguard.evaluate_clock_rate(spike)["fired"], [])

    def test_g6_fires_for_a_sustained_clock_step_and_not_for_a_one_second_blip(self):
        from lab import hostguard
        step = lambda t0, t1: (lambda t: 55.0 * t + 10.0 * max(0.0, min(t, t1) - t0))   # 65 ticks/s between t0 and t1
        healthy = lambda t: 60
        six = hostguard.evaluate_clock_rate(self._g6_series(40, step(15.0, 21.0), healthy))
        self.assertEqual([f["id"] for f in six["fired"]], ["G6"])
        self.assertEqual(six["fired"][0]["episodes"], 1)
        self.assertEqual(hostguard.evaluate_clock_rate(self._g6_series(40, step(15.0, 16.0), healthy))["fired"], [])
        # a 20 % step is still a clock step, not a stall
        down = lambda t: 55.0 * t - 11.0 * max(0.0, min(t, 21.0) - 15.0)
        self.assertEqual([f["id"] for f in hostguard.evaluate_clock_rate(self._g6_series(40, down, healthy))["fired"]], ["G6"])

    def test_g6_makes_host_guard_invalid_and_keeps_server_fail_evidence(self):
        from lab import hostguard
        with gzip.open(self.CLOCK_RATE_FIXTURE, "rt", encoding="utf-8") as fh:
            rows = json.load(fh)["series"]["20261024T194653Z-S09-9mre"]
        w = (self._t("2026-10-24 18:00:00"), self._t("2026-10-24 19:00:00"))
        ev = self._guard_ev(self._idle(w[0] - 5, w[1] + 5), [], w)
        ev["scenario"]["duration_s"] = 3600
        ev["server"]["status"] = rows
        out = analyze.check_host_guard(ev, {})
        self.assertEqual(out["status"], analyze.INVALID)
        self.assertIn("G6", out["measured"]["fired"])
        self.assertEqual(analyze.overall([{"status": analyze.FAIL, "id": "server_tick"},
                                          {**out, "check": "host_guard"}]), analyze.INVALID)
        self.assertEqual(analyze.qualifications([{"status": analyze.FAIL, "id": "server_tick"},
                                                 {**out, "check": "host_guard"}])[-1]["id"], "kept_failures")

    # (i) the verdict order
    def test_i_invalid_beats_fail_beats_inconclusive_and_is_never_pass(self):
        import itertools
        order = lambda *st: analyze.overall([{"status": x} for x in st])
        self.assertEqual(order("PASS", "INCONCLUSIVE"), analyze.INCONCLUSIVE)
        self.assertEqual(order("INCONCLUSIVE", "FAIL"), analyze.FAIL)
        self.assertEqual(order("FAIL", "INVALID", "INCONCLUSIVE"), analyze.INVALID)
        self.assertEqual(order("PASS", "INVALID"), analyze.INVALID)
        # property: PASS needs every status to be PASS or INFO; a harness error is never PASS either
        for n in (1, 2, 3, 4):
            for combo in itertools.product(("PASS", "FAIL", "INCONCLUSIVE", "INFO", "INVALID"), repeat=n):
                got = analyze.overall([{"status": x} for x in combo])
                if any(x in ("FAIL", "INCONCLUSIVE", "INVALID") for x in combo):
                    self.assertNotIn(got, (analyze.PASS, analyze.PASS_WITH_WARNINGS), combo)
                if "INVALID" in combo:
                    self.assertEqual(got, analyze.INVALID, combo)
                self.assertNotEqual(analyze.overall([{"status": x} for x in combo], harness_error="boom"), analyze.PASS)

    # (j) preflight refuses
    def test_j_failed_preflight_refuses_to_start_the_run(self):
        from unittest import mock
        from lab import clients, hostguard, runner, stack
        busy = {"result": {"worktrees": [{"displayName": "other-agent", "path": "/x", "worktreeId": "w1",
                                           "agents": [{"state": "working"}]},
                                          {"displayName": "soak-runner", "path": "/y", "worktreeId": "w2",
                                           "agents": [{"state": "working"}]}]}}
        backend = [{"pid": 7, "ppid": 1, "cmdline": "AnyDesk.exe --backend", "role": "backend"}]
        residents = [{"pid": 1, "ppid": 0, "cmdline": '"C:\\x\\AnyDesk.exe"', "role": "resident"},
                     {"pid": 2, "ppid": 1, "cmdline": "AnyDesk.exe --local-service", "role": "resident"}]
        quiet_rows = [{"epoch": 1.0, "first": True, "ad_cpu": 0.0, "cpu": 14.0, "groups": {"build": 0.0, "av": 0.0}}] + \
                     [{"epoch": 1.0 + 5 * i, "ad_cpu": 0.03, "cpu": 14.0, "groups": {"build": 0.3, "av": 0.0}} for i in range(1, 25)]
        none = hostguard.AnyDeskPaths(None, None)

        def pf(procs, ps, announced="18:30Z 90min", rows=quiet_rows, uptime=3600.0, allow=()):
            return hostguard.preflight(sampler=lambda s: rows, processes=lambda: procs, orca_ps=lambda: ps,
                                       wsl_uptime=lambda: uptime, announced=announced, paths=none, allow_agents=allow)
        clean = pf(residents, {"result": {"worktrees": []}})
        self.assertTrue(clean["ok"], clean["rows"])                      # residents are allowed
        self.assertEqual([r["id"] for r in clean["rows"]], ["P1", "P2", "P3", "P4", "P5", "P6", "P7"])
        bad = pf(backend, busy, announced=None, uptime=30.0)
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["failed"], ["P1", "P3", "P6", "P7"])
        self.assertEqual(pf(residents, busy, allow=("other-agent", "soak-runner"))["failed"], [])
        self.assertEqual(pf(residents, busy, allow=("soak-runner",))["failed"], ["P3"])
        self.assertEqual(pf(residents, None)["failed"], ["P3"])           # cannot see the agents: not clean
        hot = [dict(r, cpu=60.0) for r in quiet_rows]
        self.assertIn("P5", pf(residents, {"result": {"worktrees": []}}, rows=hot)["failed"])
        self.assertIn("P2", pf(residents, {"result": {"worktrees": []}}, rows=[dict(r, ad_cpu=0.9) for r in quiet_rows])["failed"])
        with self.assertRaisesRegex(RuntimeError, "host preflight failed: P1, P3, P6, P7"):
            hostguard.enforce(bad)
        # P1 also reads the logs: a session event in the last two minutes fails it
        import time as _t
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "ad.trace"
            now = _t.time()
            stamp = _t.strftime("%Y-%m-%d %H:%M:%S", _t.gmtime(now - 20)) + ".100"
            log.write_text(f"   info {stamp}       lsvc  14696  17760   12                anynet.any_socket - Accept request from 0000000001 (via relay).\n", encoding="utf-8")
            r = hostguard.preflight(sampler=lambda s: quiet_rows, processes=lambda: residents, orca_ps=lambda: {"result": {"worktrees": []}},
                                    wsl_uptime=lambda: 3600.0, announced="x", paths=hostguard.AnyDeskPaths(log, None), now=now)
            self.assertEqual(r["failed"], ["P1"])

        # the runner: nothing of the stack is touched when the preflight fails
        t = CleanupTests()
        with tempfile.TemporaryDirectory() as d:
            cfg, stopped = t._patched_run(d, None)
            cfg.explicit |= {"player_exe", "server_repo"}      # H6: a soak names its player and server checkout
            ensure = stack.ensure
            with mock.patch.object(runner.hostguard, "preflight", return_value=bad):
                res = runner.run(cfg, "S09", quiet=True)
            self.assertEqual(res["outcome"], analyze.INCONCLUSIVE)
            self.assertIn("host preflight failed: P1, P3, P6, P7", res["harness_error"])
            ensure.assert_not_called()
            self.assertEqual(stopped, [])
            meta = t._run_json(cfg)
            self.assertEqual(meta["host_guard"]["preflight"]["failed"], ["P1", "P3", "P6", "P7"])
            self.assertTrue((cfg.runs_root / "runs" / meta["run_id"] / "host" / "preflight.json").exists())
            t.doCleanups()

    # --- the rest of the rules and plumbing
    def test_g3_and_g4_need_consecutive_samples(self):
        from lab import hostguard
        w = (1000.0, 1300.0)
        base = [1000, 1001, 1002]

        def mk(patch):
            rows = self._idle(900, 1400)
            for r in rows:
                if w[0] <= r["epoch"] <= w[1]:
                    patch(r)
            return hostguard.evaluate(rows, [], w, baseline_pids=base)["fired"]
        burst = lambda lo, hi: (lambda r: r.update(ad_cpu=0.6) if lo <= r["epoch"] <= hi else None)
        self.assertEqual([f["id"] for f in mk(burst(1100, 1100))], [])
        self.assertEqual([f["id"] for f in mk(burst(1100, 1105))], ["G3"])
        build = lambda lo, hi, key="build", v=6.0: (lambda r: r["groups"].update({key: v}) if lo <= r["epoch"] <= hi else None)
        self.assertEqual([f["id"] for f in mk(build(1100, 1105))], [])
        self.assertEqual([f["id"] for f in mk(build(1100, 1110))], ["G4"])
        self.assertEqual(mk(build(1100, 1110, "av"))[0]["group"], "av")
        self.assertEqual([f["id"] for f in mk(build(1100, 1110, v=5.0))], [])      # the limit is exclusive
        # agents and node are recorded, never invalidating
        self.assertEqual(mk(build(1100, 1200, "agents", 30.0)), [])

    def test_connection_trace_entry_in_the_window_fires_g1_when_the_log_is_unreadable(self):
        from lab import hostguard
        text = "Incoming 2026-10-24, 18:12 Token 1673959972\r\nOutgoing 2026-10-24, 09:00 Token 1\r\n".encode("utf-16-le")
        entries = hostguard.parse_connection_trace(text)
        self.assertEqual([(e["direction"], e["ts"]) for e in entries],
                         [("Incoming", "2026-10-24T18:12:00.000Z"), ("Outgoing", "2026-10-24T09:00:00.000Z")])
        self.assertNotIn("1673959972", json.dumps(entries))
        w = (self._t("2026-10-24 18:12:40"), self._t("2026-10-24 18:40:00"))    # minute resolution: the entry may overlap
        res = hostguard.evaluate(self._idle(w[0], w[1]), entries, w, baseline_pids=[1000, 1001, 1002])
        self.assertEqual([f["id"] for f in res["fired"]], ["G1"])
        w = (self._t("2026-10-24 18:13:30"), self._t("2026-10-24 18:40:00"))
        self.assertEqual(hostguard.evaluate(self._idle(w[0], w[1]), entries, w, baseline_pids=[1000, 1001, 1002])["fired"], [])

    def test_command_lines_are_classified_and_paths_discovered(self):
        from lab import hostguard
        c = hostguard.classify_cmdline
        self.assertEqual(c('"C:\\Users\\x\\Downloads\\AnyDesk.exe" --local-service'), "resident")
        self.assertEqual(c('"C:\\Users\\x\\Downloads\\AnyDesk.exe" --local-control'), "resident")
        self.assertEqual(c('"C:\\Users\\x\\Downloads\\AnyDesk.exe"'), "resident")
        self.assertEqual(c('"C:\\Users\\x\\Downloads\\AnyDesk.exe" --backend'), "backend")
        self.assertEqual(c('"C:\\Users\\x\\Downloads\\AnyDesk.exe" --update'), "other")
        self.assertEqual(c(None), "other")
        with tempfile.TemporaryDirectory() as d:
            ad = Path(d) / "AppData" / "AnyDesk"
            pd = Path(d) / "ProgramData" / "AnyDesk"
            _write(pd / "ad_svc.trace", "x")
            p = hostguard.AnyDeskPaths.discover({"APPDATA": str(Path(d) / "AppData"), "PROGRAMDATA": str(Path(d) / "ProgramData")})
            self.assertEqual((p.ad_trace, p.connection_trace), (pd / "ad_svc.trace", None))   # only the service log exists
            _write(ad / "ad.trace", "x")
            _write(ad / "connection_trace.txt", "x")
            p = hostguard.AnyDeskPaths.discover({"APPDATA": str(Path(d) / "AppData"), "PROGRAMDATA": str(Path(d) / "ProgramData")})
            self.assertEqual((p.ad_trace, p.connection_trace), (ad / "ad.trace", ad / "connection_trace.txt"))
            self.assertEqual(hostguard.AnyDeskPaths.discover({}).ad_trace, None)           # neither is required

    def test_host_guard_check_needs_evidence_only_when_a_clean_host_is_required(self):
        w = (1000.0, 1300.0)
        none = self._guard_ev([], [], w)
        none["meta"] = {}
        self.assertEqual(analyze.check_host_guard(none, {})["status"], analyze.INFO)
        self.assertEqual(analyze.check_host_guard(dict(none, scenario=dict(none["scenario"], requires_clean_host=True)), {})["status"],
                         analyze.INCONCLUSIVE)
        silent = self._guard_ev([], [], w, required=True)           # guard started but never produced a sample
        self.assertEqual(analyze.check_host_guard(silent, {})["status"], analyze.INCONCLUSIVE)

    def test_invalid_is_reported_with_its_guards_and_exits_non_zero(self):
        from lab import report
        self.assertEqual(report.EXIT_CODES[analyze.INVALID], 2)
        events, _ = self._events()
        w = (self._t("2026-10-23 16:05:13"), self._t("2026-10-23 16:20:00"))
        ev = self._guard_ev(self._idle(w[0], w[1]), events, w)
        ev["scenario"]["assertions"] = [{"id": "c", "check": "bots_joined"}]
        results = analyze.evaluate(ev)
        results.append({"id": "m", "check": "memory_growth", "status": analyze.FAIL, "title": ""})
        outcome = analyze.overall(results)
        self.assertEqual(outcome, analyze.INVALID)
        quals = analyze.qualifications(results, ev["meta"])
        self.assertTrue(any(q.get("id") == "G1" for q in quals))
        self.assertTrue(any(q.get("id") == "kept_failures" and "m" in q["text"] for q in quals))
        with tempfile.TemporaryDirectory() as d:
            doc = report.write(Path(d), ev, results, outcome, None, out_dir=Path(d) / "out")
            self.assertEqual((doc["outcome"], doc["exit_code"]), (analyze.INVALID, 2))
            md = (Path(d) / "out" / "report.md").read_text(encoding="utf-8")
            self.assertIn("**Outcome: INVALID**", md)
            self.assertIn("not a verdict on the candidate", md)
        import testlab as cli
        self.assertEqual(cli._worst(["INVALID"]), 2)
        self.assertEqual(cli._worst(["INVALID", "FAIL"]), 1)
        self.assertEqual(cli._worst(["PASS", "INVALID"]), 2)

    def test_long_single_process_frames_name_the_nearest_guard_event(self):
        events, _ = self._events()
        start = self._t("2026-10-23 16:05:00")
        ev = self._guard_ev([], events, (start - 30, start + 600))
        ev["meta"]["host_guard"]["start_wall_epoch"] = start
        ev["clients"][0]["frames"] = [(46.0, 4700.0), (200.0, 1200.0), (10.0, 50.0)]
        rows = analyze._long_frames_with_guard_events(ev)
        self.assertEqual([r["st"] for r in rows], [46.0, 200.0])
        near = rows[0]["nearest_guard_event"]                                      # a session began 16:05:43, capture 16:05:45.8
        self.assertEqual(near["type"], "session_started")
        self.assertLess(abs(near["offset_s"]), 1.0)
        self.assertIsNone(rows[1]["nearest_guard_event"])

    def test_s09_requires_a_clean_host_and_the_thresholds_are_unchanged(self):
        from lab import provenance
        sc = scenarios.load("S09")
        self.assertTrue(sc["requires_clean_host"])
        self.assertEqual(sc["version"], 5)
        self.assertIn("host/guard.ndjson", provenance.expected_inventory(sc))
        self.assertNotIn("host/guard.ndjson", provenance.expected_inventory(scenarios.load("S01")))
        limits = {a["check"]: {k: v for k, v in a.items() if k not in ("id", "check", "title")} for a in sc["assertions"]}
        self.assertEqual(limits["memory_growth"]["max_server_mib_per_min"], 2.0)
        self.assertEqual(limits["entity_stability"], {"skip_first_s": 60, "max_growth_ratio": 0.1})

    @unittest.skipUnless(util.IS_WINDOWS, "the sampler is PowerShell on Windows")
    def test_live_guard_samples_the_host_read_only_and_its_own_cpu_is_small(self):
        import time as _t
        from lab import hostguard
        with tempfile.TemporaryDirectory() as d:
            g = hostguard.HostGuard(Path(d) / "host", interval_s=2.0)
            g.start()
            deadline = _t.time() + 45                         # PowerShell start-up is slow on a loaded host
            while g.samples < 3 and _t.time() < deadline:
                _t.sleep(0.5)
            summary = g.stop()
            rows = util.read_ndjson(Path(d) / "host" / "guard.ndjson")
            self.assertGreaterEqual(len(rows), 3, summary)
            self.assertTrue(all("epoch" in r and "mono" in r and "groups" in r for r in rows))
            self.assertTrue(rows[0].get("first"))
            for r in rows:
                for q in r.get("ad", []):
                    self.assertIn(q["role"], ("resident", "backend", "other", "unknown"))
            self.assertLess(summary["sampler_cpu_pct_of_host"]["mean"], 1.0)        # at 2 s cadence; 5 s is ~0.03 %
            self.assertLess(summary["python_threads_cpu_pct_of_host"], 1.0)
            self.assertTrue((Path(d) / "host" / "guard-summary.json").exists())
            self.assertIsNotNone(g.proc.poll())                                      # the sampler is stopped


class F29LocalRespawnTests(unittest.TestCase):
    """render_jumps: a local snap at a server-confirmed respawn of the SAME player (F28 section 3.1,
    run 20261027T150400Z-S09-ibz3, st 911.107)."""

    PID = "ac61"
    DEATH = [(6, 0), (3, 0), (3, 0), (0, 1), (100, 0), (100, 0)]
    TIMES = [910.47, 910.68, 910.87, 911.075, 911.306, 911.48]

    def _ev(self, hps, other=None, received_dx=0.8407, snap_tick=55365, extra=(), pid=None):
        """Server probe at 5 Hz around st 911 for the local player (hp, dead flag per row; the probe
        ticks are 55327..55388 as in ibz3); the client received the entity moving by (-0.38, 0.75) =
        0.84 units (direction of the rendered snap) in the sample at world tick `snap_tick`; the
        rendered local step was 1.0882. `extra` is more (st, world_tick, rx, ry, dx, dy) samples."""
        pid = pid or self.PID
        ents = []
        ticks = [55327, 55339, 55351, 55363, 55376, 55388]
        for t, tk, (hp, dead) in zip(self.TIMES, ticks, hps):
            row = [[pid, "player", 0.0, 0.0, hp, 100, dead, 5]]
            if other is not None:
                ohp, odead = other[t]
                row.append(["q", "player", 3.0, 3.0, ohp, 100, odead, 5])
            ents.append({"st": t, "tick": tk, "ents": row})
        ev = _ev(entities=ents, duration=1200)
        c = ev["clients"][0]
        c["summary"] = {"outcome": "completed"}
        k = received_dx / 0.8407

        def smp(st, wt, rx, ry, dx, dy):
            return {"st": st, "world_tick": wt, "ents": [[pid, "player", 1, rx, ry, dx, dy]]}
        c["samples"] = [smp(911.06, 55361, 0.55, -2.01, 0.0, 0.0),
                        smp(911.11, snap_tick, 0.16, -1.24, -0.38 * k, 0.75 * k)] + [smp(*x) for x in extra]
        c["events"] = [{"event": "render_jump", "st": 911.107, "id": pid, "type": "player", "local": True,
                        "step": 1.0882, "allowed": 0.331}]
        return ev

    def _second_snap(self, ev, st=911.36, tick=55379, dx=0.6):
        """A second local snap event with its own received step, as the F29B repro of RV-F29 B1."""
        c = ev["clients"][0]
        c["samples"] += [{"st": st - 0.05, "world_tick": tick - 4, "ents": [[self.PID, "player", 1, 0.5, -1.0, 0.0, 0.0]]},
                         {"st": st, "world_tick": tick, "ents": [[self.PID, "player", 1, 1.1, -1.0, -dx * 0.5, dx * 0.8]]}]
        c["events"].append({"event": "render_jump", "st": st, "id": self.PID, "type": "player", "local": True,
                            "step": 1.088, "allowed": 0.331})
        return ev

    def test_the_ibz3_respawn_snap_is_explained_by_the_respawn(self):
        res = analyze.check_render_jumps(self._ev(self.DEATH), {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"], res["measured"]["server_teleport"]),
                         (analyze.PASS, 0, 1), res)
        self.assertEqual(res["measured"].get("local_respawn"), 1)

    def test_a_local_major_without_respawn_evidence_still_fails(self):
        alive = [(100, 0)] * 6
        res = analyze.check_render_jumps(self._ev(alive), {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)
        low = [(6, 0), (3, 0), (3, 0), (3, 0), (100, 0), (100, 0)]     # HP never reached 0: not a death
        self.assertEqual(analyze.check_render_jumps(self._ev(low), {"max_local": 0})["status"], analyze.FAIL)

    def test_the_respawn_of_another_entity_explains_nothing(self):
        alive = [(100, 0)] * 6
        died = dict(zip(self.TIMES, self.DEATH))
        res = analyze.check_render_jumps(self._ev(alive, other=died), {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)

    def test_a_respawn_without_an_authoritative_position_jump_does_not_explain_the_snap(self):
        res = analyze.check_render_jumps(self._ev(self.DEATH, received_dx=0.05), {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)

    def test_a_remote_snap_is_not_helped_by_the_new_rule(self):
        ev = self._ev(self.DEATH)
        ev["clients"][0]["events"][0]["local"] = False
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual(res["measured"]["remote_major"], 1)

    def test_a_later_unrelated_snap_after_the_respawn_fails(self):
        # RV-F29 B1: the respawn is real but the snap is 0.25 s later (world tick 55400, after the max-HP
        # probe at 55376 + slack); HP 0 -> max is in the +-window, an authoritative step is there, yet it is not this snap.
        ev = self._ev(self.DEATH, snap_tick=55400)
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)
        self.assertIsNone(res["measured"].get("local_respawn"))

    def test_a_snap_before_the_respawn_probe_window_fails(self):
        res = analyze.check_render_jumps(self._ev(self.DEATH, snap_tick=55340), {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)

    def test_a_second_snap_in_the_window_fails_one_respawn_explains_one_snap(self):
        ev = self._second_snap(self._ev(self.DEATH), tick=55374)       # inside the tick window, same respawn
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"], res["measured"]["local_respawn"]),
                         (analyze.FAIL, 1, 1), res)

    def test_a_snap_pointing_the_other_way_is_not_the_respawn(self):
        ev = self._ev(self.DEATH)
        ev["clients"][0]["samples"][1]["ents"][0][3:5] = [0.55 + 0.38, -2.01 - 0.75]     # rendered went the opposite way
        res = analyze.check_render_jumps(ev, {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)

    def test_another_players_respawn_does_not_excuse_the_snap_even_with_a_perfect_snap(self):
        died = dict(zip(self.TIMES, self.DEATH))
        res = analyze.check_render_jumps(self._ev([(100, 0)] * 6, other=died), {"max_local": 0})
        self.assertEqual((res["status"], res["measured"]["local_major"]), (analyze.FAIL, 1), res)


class F29ProjectileReuseTests(unittest.TestCase):
    """entity_lifecycle: per-type reuse tolerance (F28 section 3.3, proj-17 in the same run)."""

    def _ev(self, etype, spawn, drawn, prev_end, speed_rows=True):
        """Entity 'e' drawn at prev_end until t=104, removed, re-added at t=106 and first drawn at `drawn`."""
        ents = []
        if speed_rows:
            ents = [_row(float(i), [["e", etype, spawn[0], spawn[1], 1, 1, 0, 19.8 if etype == "projectile" else 5]])
                    for i in range(3)]
        ev = _ev(clients=1, duration=20, entities=ents)
        c = ev["clients"][0]
        samples = []
        for k in range(200):
            t = 100.0 + k * 0.05
            ents_ = []
            if t < 104.1:
                ents_.append(["e", etype, 0, prev_end[0], prev_end[1], prev_end[0], prev_end[1]])
            elif t >= 106.0:
                ents_.append(["e", etype, 0, drawn[0], drawn[1], drawn[0], drawn[1]])
            samples.append(_sample(t, ents_))
        add = {"event": "entity_added", "t": 100.0, "id": "e", "type": etype, "tick": 10, "x": 0.0, "y": 0.0,
               "rx": 0.0, "ry": 0.0}
        removed = {"event": "entity_removed", "t": 104.0, "id": "e"}
        readd = {"event": "entity_added", "t": 106.0, "id": "e", "type": etype, "tick": 500, "x": spawn[0], "y": spawn[1],
                 "rx": drawn[0], "ry": drawn[1]}
        c["samples"], c["events"] = samples, [add, removed, readd]
        return ev

    def test_a_projectile_one_snapshot_ahead_of_its_spawn_passes(self):
        # ibz3 proj-17: first drawn 1.333 from the snapshot position it was added at and 2.696 from where
        # the previous incarnation ended; the player tolerance (1.1) failed it, the projectile's (3.17) does not.
        ev = self._ev("projectile", (-10.336, -9.412), (-11.402, -8.612), (-9.0, -7.0))
        res = analyze.check_entity_lifecycle(ev, {})
        self.assertEqual((res["status"], res["measured"]["reused_drawn_elsewhere"]), (analyze.PASS, 0), res)
        self.assertAlmostEqual(res["threshold"]["reuse_tolerance_by_type"]["projectile"], 19.8 * 0.15 + 0.2, delta=0.5)

    def test_the_same_distance_fails_for_a_player_sized_entity(self):
        ev = self._ev("mob", (-10.336, -9.412), (-11.402, -8.612), (-9.0, -7.0))
        res = analyze.check_entity_lifecycle(ev, {})
        self.assertEqual((res["status"], res["measured"]["reused_drawn_elsewhere"]), (analyze.FAIL, 1), res)

    def test_a_projectile_first_drawn_where_the_previous_one_ended_still_fails(self):
        # stale buffer: 1.33 from the spawn (inside the projectile tolerance) but 0.1 from the previous end
        ev = self._ev("projectile", (-10.336, -9.412), (-11.402, -8.612), (-11.45, -8.65))
        res = analyze.check_entity_lifecycle(ev, {})
        self.assertEqual((res["status"], res["measured"]["reused_drawn_elsewhere"]), (analyze.FAIL, 1), res)

    def test_a_projectile_beyond_its_own_tolerance_fails(self):
        ev = self._ev("projectile", (0.0, 0.0), (6.0, 0.0), (20.0, 20.0))
        self.assertEqual(analyze.check_entity_lifecycle(ev, {})["status"], analyze.FAIL)

    def test_without_a_known_projectile_speed_the_player_tolerance_applies(self):
        ev = self._ev("projectile", (-10.336, -9.412), (-11.402, -8.612), (-9.0, -7.0), speed_rows=False)
        self.assertEqual(analyze.check_entity_lifecycle(ev, {})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_entity_lifecycle(ev, {"projectile_speed": 19.8})["status"], analyze.PASS)


class F29G3BaselineTests(unittest.TestCase):
    """G3 relative to the preflight-measured resident baseline (F28 section 4)."""

    W = (1000.0, 1300.0)
    BASE = {"mean_pct": 0.179, "max_pct": 0.328}     # ibz3 host/preflight.json P2

    def _samples(self, front):
        """Three idle residents; `front(epoch)` is the AnyDesk total in % of the host."""
        out, t = [], 900.0
        while t <= 1400.0:
            out.append({"epoch": t, "ts": f"t{t:.0f}", "cpu": 15.0, "ad_cpu": front(t),
                        "ad": [{"pid": 1 + i, "role": "resident", "cpu": 0.0} for i in range(3)],
                        "groups": {"build": 0.2, "av": 0.0}, "own_cpu": 0.03})
            t += 5.0
        return out

    def _fired(self, front, base):
        from lab import hostguard
        return [f["id"] for f in hostguard.evaluate(self._samples(front), [], self.W, baseline_pids=[1, 2, 3],
                                                    ad_baseline=base)["fired"]]

    def test_threshold_is_relative_to_the_baseline_with_the_old_floor(self):
        from lab import hostguard
        self.assertEqual(hostguard.g3_threshold(None), 0.5)
        self.assertEqual(hostguard.g3_threshold(0.05), 0.5)                      # F19 baseline: the floor wins
        self.assertAlmostEqual(hostguard.g3_threshold(0.328), 0.956, places=3)   # ibz3 baseline

    def test_ibz3_idle_front_process_samples_do_not_fire_but_a_session_burst_does(self):
        idle = lambda t: 0.76 if 1100 <= t <= 1150 else 0.4        # F28: idle front process 0.4-0.76 %
        self.assertEqual(self._fired(idle, None), ["G3"])           # the fixed 0.5 % limit fired on idle
        self.assertEqual(self._fired(idle, self.BASE), [])
        burst = lambda t: 1.6 if 1100 <= t <= 1105 else 0.2
        self.assertEqual(self._fired(burst, self.BASE), ["G3"])
        one = lambda t: 1.6 if t == 1100 else 0.2
        self.assertEqual(self._fired(one, self.BASE), [])           # still two consecutive samples

    def test_threshold_is_capped_so_a_noisy_preflight_cannot_hide_a_session_burst(self):
        from lab import hostguard
        self.assertEqual(hostguard.G3_THRESHOLD_CAP_PCT, 1.0)
        self.assertEqual(hostguard.g3_threshold(1.0), 1.0)           # uncapped: 2.3 %
        self.assertEqual(hostguard.g3_threshold(5.0), 1.0)
        self.assertAlmostEqual(hostguard.g3_threshold(0.328), 0.956, places=3)   # below the cap: unchanged
        noisy = {"mean_pct": 0.3, "max_pct": 0.95}                   # passes P2; uncapped limit would be 2.2 %
        burst = lambda t: 1.4 if 1100 <= t <= 1105 else 0.2          # F28 saw >= 1.36 % in a session
        self.assertEqual(self._fired(burst, noisy), ["G3"])

    def test_p2_fails_when_the_baseline_max_reaches_the_cap(self):
        from lab import hostguard
        none = hostguard.AnyDeskPaths(None, None)

        def p2(spike):
            rows = [{"epoch": 1.0, "first": True, "ad_cpu": 0.0, "cpu": 14.0, "groups": {"build": 0.0, "av": 0.0}}] +                    [{"epoch": 1.0 + 5 * i, "ad_cpu": spike if i == 7 else 0.1, "cpu": 14.0, "groups": {"build": 0.3, "av": 0.0}}
                    for i in range(1, 25)]
            pf = hostguard.preflight(sampler=lambda s: rows, processes=lambda: [], orca_ps=lambda: {"result": {"worktrees": []}},
                                     wsl_uptime=lambda: 3600.0, announced="x", paths=none)
            return pf, next(r for r in pf["rows"] if r["id"] == "P2")
        pf, row = p2(0.9)
        self.assertEqual(row["status"], "PASS", row)
        pf, row = p2(1.2)                                            # mean ~0.15 % passes the old P2; the max does not
        self.assertEqual((row["status"], "P2" in pf["failed"], pf["ok"]), ("FAIL", True, False), row)

    def test_the_g3_stats_record_the_baseline_and_the_label(self):
        from lab import hostguard
        res = hostguard.evaluate(self._samples(lambda t: 0.2), [], self.W, baseline_pids=[1, 2, 3], ad_baseline=self.BASE)
        self.assertEqual(res["stats"]["g3"]["baseline"], self.BASE)
        self.assertEqual(res["stats"]["g3"]["label"], "policy, unvalidated")
        self.assertIn("policy, unvalidated", hostguard.RULES["G3"])

    def test_preflight_records_the_baseline_and_the_guard_check_reads_it(self):
        from lab import hostguard
        none = hostguard.AnyDeskPaths(None, None)
        rows = [{"epoch": 1.0, "first": True, "ad_cpu": 0.0, "cpu": 14.0, "groups": {"build": 0.0, "av": 0.0}}] + \
               [{"epoch": 1.0 + 5 * i, "ad_cpu": 0.3 if i == 7 else 0.15, "cpu": 14.0, "groups": {"build": 0.3, "av": 0.0}}
                for i in range(1, 25)]
        pf = hostguard.preflight(sampler=lambda s: rows, processes=lambda: [], orca_ps=lambda: {"result": {"worktrees": []}},
                                 wsl_uptime=lambda: 3600.0, announced="x", paths=none)
        b = pf["anydesk_baseline"]
        self.assertEqual((b["max_pct"], b["samples"], b["label"]), (0.3, 24, "policy, unvalidated"))
        self.assertAlmostEqual(b["g3_threshold_pct"], 0.9, places=3)
        self.assertEqual(hostguard.g3_baseline(pf)["max_pct"], 0.3)
        legacy = {"rows": [{"id": "P2", "measured": {"mean_pct": 0.179, "max_pct": 0.328}}]}   # written before F29
        self.assertEqual(hostguard.g3_baseline(legacy)["max_pct"], 0.328)
        self.assertIsNone(hostguard.g3_baseline({"rows": []}))
        ev = HostGuardTests()._guard_ev(self._samples(lambda t: 0.76), [], self.W, preflight=pf)
        ev["meta"]["host_guard"]["baseline_pids"] = [1, 2, 3]
        out = analyze.check_host_guard(ev, {})
        self.assertEqual(out["status"], analyze.INFO, out["measured"])
        self.assertAlmostEqual(out["detail"]["stats"]["g3"]["threshold_pct"], 0.9, places=3)


class F29ProcSamplerTests(unittest.TestCase):
    """The optional 1 s process sampler is evidence only."""

    ROWS = [{"epoch": 100.0 + i, "top": [{"pid": 7, "name": "python", "cpu": 12.0 if i == 3 else 1.0},
                                           {"pid": 8, "name": "claude", "cpu": 0.5}], "sweep_ms": 40.0, "own_cpu": 0.2}
            for i in range(6)]

    def test_report_ranks_processes_and_names_the_hottest_seconds(self):
        from lab import hostguard
        rep = hostguard.procs_report(self.ROWS)
        self.assertEqual(rep["samples"], 6)
        self.assertEqual(rep["processes"][0]["name"], "python")
        self.assertEqual(rep["processes"][0]["max_pct"], 12.0)
        self.assertEqual(rep["processes"][0]["seconds_above_5_pct"], 1)
        self.assertEqual(rep["hottest_seconds"][0], {"epoch": 103.0, "name": "python", "cpu_pct": 12.0})

    def test_it_is_info_detail_and_never_a_guard(self):
        w = (1000.0, 1300.0)
        ev = HostGuardTests()._guard_ev(HostGuardTests._idle(900, 1400, pid_base=1), [], w)
        ev["meta"]["host_guard"]["baseline_pids"] = [1, 2, 3]
        ev["hostguard"]["procs"] = list(self.ROWS)
        ev["hostguard"]["procs_summary"] = {"sampler_cpu_pct_of_host": {"mean": 0.2, "max": 0.46}}
        out = analyze.check_host_guard(ev, {})
        self.assertEqual(out["status"], analyze.INFO)
        self.assertEqual(out["detail"]["proc_sampler"]["processes"][0]["name"], "python")
        self.assertEqual(out["detail"]["proc_sampler"]["cost"]["sampler_cpu_pct_of_host"]["max"], 0.46)
        ev["hostguard"]["procs"] = []
        self.assertNotIn("proc_sampler", analyze.check_host_guard(ev, {})["detail"])

    def test_the_sampler_script_is_read_only(self):
        from lab import hostguard
        text = hostguard.PROCS_PS1.read_text(encoding="utf-8")
        for verb in ("Stop-Process", "Start-Process", "Set-", "Remove-", "New-Item", "Out-File", "Add-Content"):
            self.assertNotIn(verb, text)
        self.assertIn("Get-Process", text)


if __name__ == "__main__":
    unittest.main()
