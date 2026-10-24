"""Unit tests for S18 packet impairment: the tc command builder, the namespace guards, the cleanup contract
(with a fake shell, never a real tc) and the six analyzer checks against synthetic evidence.

    python3 -B testlab/tests/test_netem.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_lab import _ev  # noqa: E402

from lab import analyze, analyze_netem, config, netem, provenance, scenarios, stack  # noqa: E402

PROFILE = {"loss_pct": 5, "delay_ms": 40, "jitter_ms": 20, "reorder_pct": 1}


class ClauseAndCommandTests(unittest.TestCase):
    def test_the_clause_has_delay_jitter_loss_and_reorder(self):
        self.assertEqual(netem.netem_clause(PROFILE), "delay 40ms 20ms loss 5% reorder 1%")
        self.assertEqual(netem.netem_clause({"loss_pct": 2.5}), "loss 2.5%")

    def test_an_empty_profile_or_reorder_without_delay_is_refused(self):
        with self.assertRaises(netem.NetemError):
            netem.netem_clause({})
        with self.assertRaises(netem.NetemError):
            netem.netem_clause({"reorder_pct": 1})

    def test_in_ns_never_reaches_the_host_namespace(self):
        self.assertEqual(netem.in_ns(4242, "tc qdisc show"), "sudo -n nsenter -t 4242 -n tc qdisc show")
        for bad in (0, 1, -5):
            with self.assertRaises(netem.NetemError):
                netem.in_ns(bad, "tc qdisc show")

    def test_both_directions_shape_only_udp_on_the_game_port(self):
        cmds = netem.apply_commands("eth0", PROFILE)
        filters = [c for c in cmds if c.startswith("tc filter")]
        self.assertEqual(len(filters), 2)
        for f in filters:
            self.assertIn("match ip protocol 17 0xff", f)
            self.assertIn(f"{netem.GAME_PORT} 0xffff", f)
        self.assertIn("match ip sport 9000", filters[0])
        self.assertIn("match ip dport 9000", filters[1])
        # nothing is attached as a bare root netem on eth0: TCP (status, metrics, gateway) stays unshaped
        self.assertFalse(any(c.startswith("tc qdisc add dev eth0 root netem") for c in cmds))
        self.assertTrue(any("root handle 1: prio" in c for c in cmds))
        # the netem qdiscs carry the profile
        self.assertEqual(sum("netem delay 40ms 20ms loss 5% reorder 1%" in c for c in cmds), 2)

    def test_one_direction_builds_only_that_direction(self):
        egress = netem.apply_commands("eth0", PROFILE, ("egress",))
        self.assertFalse(any("ifb" in c or "ingress" in c for c in egress))
        ingress = netem.apply_commands("eth0", PROFILE, ("ingress",))
        self.assertFalse(any("root handle 1: prio" in c for c in ingress))
        self.assertTrue(any(c.startswith("ip link add ifb0") for c in ingress))

    def test_every_command_names_a_device_of_the_container(self):
        for c in netem.apply_commands("eth0", PROFILE) + netem.remove_commands("eth0"):
            self.assertRegex(c, r"dev (eth0|ifb0)|link (add|set|del) ifb0")

    def test_the_removal_covers_what_the_apply_created(self):
        rm = netem.remove_commands("eth0")
        self.assertEqual(rm, ["tc qdisc del dev eth0 root", "tc qdisc del dev eth0 ingress", "ip link del ifb0"])


class ParsingTests(unittest.TestCase):
    def test_qdisc_json_is_parsed(self):
        doc = json.dumps([{"kind": "netem", "handle": "30:", "parent": "1:3", "packets": 60, "bytes": 9, "drops": 5, "overlimits": 0},
                          {"kind": "noqueue"}])
        qs = netem.parse_qdiscs(doc)
        self.assertEqual(qs[0]["drops"], 5)
        self.assertEqual(qs[1]["packets"], 0)
        self.assertEqual(netem.parse_qdiscs("not json"), [])

    def test_leftover_names_what_remains(self):
        self.assertEqual(netem.leftover([{"kind": "noqueue"}], False), [])
        left = netem.leftover([{"kind": "prio", "handle": "1:"}, {"kind": "netem", "handle": "30:"}], True)
        self.assertEqual(left, ["qdisc prio 1:", "qdisc netem 30:", "device ifb0"])

    def test_default_route_device(self):
        self.assertEqual(netem.parse_default_dev("default via 172.20.0.1 dev eth0 \n172.20.0.0/16 dev eth0"), "eth0")
        self.assertIsNone(netem.parse_default_dev(""))


class FakeShaper(netem.Shaper):
    """The Shaper with the shell replaced: records every command and answers from a small model of a netns."""

    def __init__(self, cfg, *, fail_on=None, running=True, same_netns=False, leave_behind=False):
        super().__init__(cfg)
        self.sh_calls, self.fail_on, self.running = [], fail_on, running
        self.same_netns, self.leave_behind = same_netns, leave_behind
        self.state = {"qdiscs": [], "ifb": False}

    def _sh(self, cmd, timeout=30):
        self.sh_calls.append(cmd)
        if cmd.startswith("docker inspect"):
            return (0, "true 4242") if self.running else (0, "false 0")
        if cmd.startswith("nohup setsid"):
            return 0, "9001"
        if cmd == "sudo -n true":
            return 0, ""
        if "readlink /proc/1/ns/net" in cmd and "sudo" not in cmd:
            return 0, "net:[1]"
        if "readlink /proc/4242/ns/net" in cmd:
            return 0, "net:[1]" if self.same_netns else "net:[2]"
        if cmd.startswith("grep -q"):
            return 0, ""
        assert cmd.startswith("sudo -n nsenter -t 4242 -n "), cmd   # nothing else may run tc or ip
        inner = cmd[len("sudo -n nsenter -t 4242 -n "):]
        if self.fail_on and self.fail_on in inner and " del " not in inner:
            return 2, "RTNETLINK answers: Operation not permitted"
        if inner.startswith("ip -o route show default"):
            return 0, "default via 172.20.0.1 dev eth0"
        if inner.startswith("ip link add ifb0"):
            self.state["ifb"] = True
        elif inner.startswith("ip link del ifb0"):
            self.state["ifb"] = self.leave_behind
        elif inner.startswith("ip link show ifb0"):
            return (0, "ifb0") if self.state["ifb"] else (1, "does not exist")
        elif inner.startswith("tc qdisc add dev eth0 root"):
            self.state["qdiscs"].append({"kind": "prio", "handle": "1:"})
        elif inner.startswith("tc qdisc add dev eth0 parent"):
            self.state["qdiscs"].append({"kind": "netem", "handle": "30:"})
        elif inner.startswith("tc qdisc add dev eth0 handle ffff: ingress"):
            self.state["qdiscs"].append({"kind": "ingress", "handle": "ffff:"})
        elif inner.startswith("tc qdisc del dev eth0"):
            if not self.leave_behind:
                self.state["qdiscs"] = []
        elif inner.startswith("tc -s -j qdisc show dev eth0") or inner.startswith("tc -j qdisc show dev eth0"):
            return 0, json.dumps(self.state["qdiscs"] or [{"kind": "noqueue"}])
        elif inner.startswith("tc -s -j qdisc show dev ifb0"):
            return 0, json.dumps([{"kind": "netem", "packets": 20, "drops": 2}])
        return 0, ""

    def ran(self):
        return [c[len("sudo -n nsenter -t 4242 -n "):] for c in self.sh_calls if c.startswith("sudo -n nsenter")]


def _cfg(prefix="rpgs-"):
    return config.LabConfig(workspace=Path("."), runs_root=Path("."), container_prefix=prefix,
                            gameserver_container=prefix + "gameserver", redis_container=prefix + "redis")


class ShaperTests(unittest.TestCase):
    def test_only_the_scratch_container_is_ever_addressed(self):
        with self.assertRaises(stack.StackError):
            netem.Shaper(_cfg("rpg-"))   # the developer's own stack
        netem.Shaper(_cfg())

    def test_apply_runs_every_command_in_the_container_namespace_and_arms_a_watchdog(self):
        sh = FakeShaper(_cfg())
        rec = sh.apply(PROFILE, expect_s=100)
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["watchdog"]["pid"], 9001)
        self.assertEqual(rec["watchdog"]["after_s"], 100 + int(netem.WATCHDOG_SLACK_S))
        self.assertEqual(sh.ran()[0], "ip -o route show default")
        self.assertEqual(sum(c.startswith("tc qdisc add") for c in sh.ran()), 4)
        self.assertEqual(rec["qdiscs"]["ingress"][0]["kind"], "netem")
        # the watchdog script re-checks the namespace before it deletes anything
        wd = next(c for c in sh.sh_calls if c.startswith("nohup setsid"))
        self.assertIn('readlink /proc/4242/ns/net)" = "net:[2]"', wd)

    def test_a_failed_command_stops_the_apply_and_rolls_back(self):
        sh = FakeShaper(_cfg(), fail_on="parent 1:3")
        rec = sh.apply(PROFILE)
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["commands"][-1]["rc"], 2)
        self.assertTrue(rec["rolled_back"]["verified"])
        self.assertEqual(sh.state, {"qdiscs": [], "ifb": False})
        self.assertNotIn("watchdog", rec)

    def test_a_namespace_equal_to_the_hosts_is_never_shaped(self):
        sh = FakeShaper(_cfg(), same_netns=True)
        with self.assertRaises(netem.NetemError):
            sh.apply(PROFILE)
        with self.assertRaises(netem.NetemError):
            sh.preflight()
        self.assertFalse(any(c.startswith("tc qdisc add") for c in sh.ran()))

    def test_a_stopped_container_is_refused_for_apply_and_clean_for_cleanup(self):
        sh = FakeShaper(_cfg(), running=False)
        with self.assertRaises(netem.NetemError):
            sh.apply(PROFILE)
        self.assertEqual(sh.clean(), {"container_running": False, "verified": True, "leftover": []})

    def test_remove_is_verified_and_reports_a_leftover(self):
        sh = FakeShaper(_cfg())
        sh.apply(PROFILE)
        rec = sh.remove(4242, "eth0")
        self.assertTrue(rec["verified"])
        stuck = FakeShaper(_cfg(), leave_behind=True)
        stuck.apply(PROFILE)
        rec = stuck.remove(4242, "eth0")
        self.assertFalse(rec["verified"])
        self.assertIn("device ifb0", rec["leftover"])

    def test_preflight_cleans_a_leftover_of_a_dead_run(self):
        sh = FakeShaper(_cfg())
        sh.apply(PROFILE)
        rec = sh.preflight()
        self.assertTrue(rec["leftover_before"])
        self.assertTrue(rec["leftover_cleaned"])

    def test_stats_read_both_netem_qdiscs(self):
        sh = FakeShaper(_cfg())
        sh.apply(PROFILE)
        st = sh.stats(4242, "eth0")
        self.assertEqual(st["ingress"]["drops"], 2)
        self.assertEqual(st["egress"]["kind"], "netem")


class FakeProbe:
    """Scenario time that advances 10 s per read, so the step's waits end at once."""

    def __init__(self):
        self.t = 0.0

    def scenario_time(self, _mono):
        self.t += 10.0
        return self.t


class StepTests(unittest.TestCase):
    def _run(self, shaper, stop=None):
        d = {"baseline_s": 30, "impaired_s": 60, "recovery_s": 30, "profile": PROFILE}
        with tempfile.TemporaryDirectory() as tmp:
            logs = []
            netem.scrape = lambda cfg: {"ok": True, "metrics": {"gameserver_kcp_segments_retransmitted_total": 1.0}}
            netem.run_step(_cfg(), {}, d, Path(tmp), FakeProbe(), logs.append, stop or threading.Event(), shaper=shaper)
            return [json.loads(l) for l in (Path(tmp) / netem.EVIDENCE).read_text().splitlines()], logs

    def test_a_normal_run_records_the_phases_and_removes_once(self):
        sh = FakeShaper(_cfg())
        recs, _ = self._run(sh)
        kinds = [r["record"] for r in recs]
        self.assertEqual(kinds[0], "plan")
        for label in ("baseline_start", "impaired_start", "impaired_end", "recovery_start", "recovery_end"):
            self.assertTrue(any(r.get("label") == label for r in recs), label)
        planned = [r for r in recs if r["record"] == "remove"]
        self.assertEqual([r["reason"] for r in planned], ["planned"])
        self.assertTrue(planned[0]["verified"])
        self.assertEqual(sh.state, {"qdiscs": [], "ifb": False})

    def test_an_error_after_the_apply_still_removes(self):
        sh = FakeShaper(_cfg())
        original = sh.stats
        sh.stats = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        recs, _ = self._run(sh)
        sh.stats = original
        self.assertTrue(any(r["record"] == "error" and "boom" in r["error"] for r in recs))
        cleanup = [r for r in recs if r["record"] == "remove"]
        self.assertEqual(cleanup[-1]["reason"], "cleanup")
        self.assertTrue(cleanup[-1]["verified"])
        self.assertEqual(sh.state, {"qdiscs": [], "ifb": False})

    def test_a_stop_before_the_apply_never_shapes(self):
        sh = FakeShaper(_cfg())
        stop = threading.Event()
        stop.set()
        recs, _ = self._run(sh, stop)
        self.assertFalse(any(c.startswith("tc qdisc add") for c in sh.ran()))
        self.assertFalse(any(r["record"] == "apply" for r in recs))

    def test_a_failed_apply_is_recorded_and_not_left_behind(self):
        sh = FakeShaper(_cfg(), fail_on="ingress")
        recs, _ = self._run(sh)
        apply_ = next(r for r in recs if r["record"] == "apply")
        self.assertFalse(apply_["ok"])
        self.assertEqual(sh.state, {"qdiscs": [], "ifb": False})

    def test_final_cleanup_never_raises(self):
        sh = FakeShaper(_cfg())
        orig = netem.Shaper
        try:
            class Boom(netem.Shaper):
                def clean(self):
                    raise RuntimeError("wsl gone")
            netem.Shaper = Boom
            with tempfile.TemporaryDirectory() as tmp:
                rec = netem.final_cleanup(_cfg(), Path(tmp), lambda m: None)
                self.assertFalse(rec["verified"])
                self.assertIn("wsl gone", rec["error"])
                self.assertEqual(json.loads((Path(tmp) / netem.EVIDENCE).read_text())["record"], "final_cleanup")
        finally:
            netem.Shaper = orig
        del sh


# --------------------------------------------------------------------------- analyzer

START = 8.0     # client realtime of scenario time 0
APPLY_START, APPLY_DONE, IMPAIRED_END, REMOVE_DONE, DURATION = 30.0, 33.0, 90.0, 93.0, 120.0


def _scrape(label, st, retx):
    return {"record": "scrape", "label": label, "st": st, "ok": True,
            "metrics": {'gameserver_kcp_segments_retransmitted_total{map_id="map_01"}': retx}}


def _netem_records(*, retx=(0.0, 0.0, 160.0, 160.0, 160.0), egress=(3422, 189), ingress=(3396, 147), applied=True,
                   removed=True, final=True, remove_st=REMOVE_DONE, final_leftover=()):
    base0, base1, imp1, rec0, rec1 = retx
    recs = [{"record": "plan", "profile": PROFILE, "impaired_s": 60, "baseline_s": 30, "recovery_s": 30},
            _scrape("baseline_start", 1.0, base0), _scrape("impaired_start", APPLY_START, base1)]
    recs.append({"record": "apply", "st": APPLY_DONE, "ok": applied, "profile": PROFILE, "directions": ["egress", "ingress"],
                 "commands": [] if applied else [{"cmd": "tc qdisc add", "rc": 2, "out": "denied"}]})
    recs += [_scrape("impaired_end", IMPAIRED_END, imp1),
             {"record": "stats", "label": "impaired_end", "st": IMPAIRED_END,
              "egress": {"packets": egress[0] - egress[1], "drops": egress[1]},
              "ingress": {"packets": ingress[0] - ingress[1], "drops": ingress[1]}}]
    if removed is not None:
        recs.append({"record": "remove", "st": remove_st, "reason": "planned", "verified": bool(removed), "leftover": []})
    recs += [_scrape("recovery_start", REMOVE_DONE, rec0), _scrape("recovery_end", 119.0, rec1)]
    if final:
        recs.append({"record": "final_cleanup", "verified": not final_leftover, "leftover": list(final_leftover)})
    return recs


def _netem_ev(*, gap_impaired=None, gap_baseline=None, rate_hz=15.0, rtt_rise=80.0, snaps_at=(), corr_impaired=0.2,
              keyframes_impaired=0.5, recovery_offset_until=None, impaired_offset=0.0, **rec_kw):
    """Two clients over 120 s of scenario time: snapshots at rate_hz, 20 Hz samples with rtt, prediction counters and a
    remote entity drawn by both clients, plus the netem.ndjson of a clean S18 run."""
    ev = _ev(clients=2, duration=DURATION, status=[{"_st": 1.0, "tick_rate": 60, "sim_world_hz": 15}])
    ev["scenario"]["disruptions"] = [{"at_s": 1, "kind": "netem", "profile": PROFILE}]
    for c in ev["clients"]:
        c["summary"] = {"start_realtime": START, "user_id": f"u{c['index']}"}
        snaps, t = [], 0.0
        while t < DURATION:
            snaps.append({"t": START + t, "tick": int(t * 60), "full": int(t * rate_hz) % 30 == 0 and c.get("_kf", True)})
            step = 1.0 / rate_hz
            if gap_impaired and APPLY_DONE + 5 <= t < APPLY_DONE + 5 + step:
                step = gap_impaired
            if gap_baseline and 10.0 <= t < 10.0 + step:
                step = gap_baseline
            t += step
        if keyframes_impaired > 1:
            extra = [{"t": START + APPLY_DONE + 1 + k * 0.5, "tick": 0, "full": True} for k in range(int(keyframes_impaired))]
            snaps = sorted(snaps + extra, key=lambda s: s["t"])
        c["snapshots"] = snaps
        samples, snapped = [], 0
        for k in range(int(DURATION * 20)):
            st = k * 0.05
            impaired = APPLY_DONE <= st <= IMPAIRED_END
            if any(abs(st - s) < 0.025 for s in snaps_at):
                snapped += 1
            x = st * 2.0
            if impaired:
                x += impaired_offset * (c["index"])
            if recovery_offset_until is not None and REMOVE_DONE <= st < recovery_offset_until and c["index"] == 1:
                x += 0.6
            samples.append({"st": st, "world_tick": int(st * 60), "render_tick": st * 60, "rtt_ms": 4.0 + (rtt_rise if impaired else 0),
                            "pred": {"snaps": snapped, "corr": corr_impaired if impaired else 0.05},
                            "ents": [["e", "mob", 0, x, 0.0, x, 0.0]]})
        c["samples"] = samples
    ev["netem"] = _netem_records(**rec_kw)
    return ev


class NetemAppliedTests(unittest.TestCase):
    def test_the_impairment_shown_by_the_qdisc_and_the_clients_passes(self):
        res = analyze_netem.check_netem_applied(_netem_ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertEqual(res["measured"]["egress"]["dropped"], 189)

    def test_a_loss_share_far_from_the_configured_one_fails(self):
        for egress in ((3422, 20), (3422, 600)):
            res = analyze_netem.check_netem_applied(_netem_ev(egress=egress), {})
            self.assertEqual(res["status"], analyze.FAIL, egress)
            self.assertTrue(any("loss" in p for p in res["detail"]["problems"]))

    def test_too_few_datagrams_through_the_qdisc_fails(self):
        self.assertEqual(analyze_netem.check_netem_applied(_netem_ev(ingress=(100, 5)), {})["status"], analyze.FAIL)

    def test_no_round_trip_rise_means_the_path_was_not_shaped(self):
        res = analyze_netem.check_netem_applied(_netem_ev(rtt_rise=5.0), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("rtt" in p for p in res["detail"]["problems"]))

    def test_a_failed_apply_fails_and_a_missing_file_is_inconclusive(self):
        self.assertEqual(analyze_netem.check_netem_applied(_netem_ev(applied=False), {})["status"], analyze.FAIL)
        ev = _netem_ev()
        ev["netem"] = []
        self.assertEqual(analyze_netem.check_netem_applied(ev, {})["status"], analyze.INCONCLUSIVE)

    def test_missing_counters_are_inconclusive_not_a_pass(self):
        ev = _netem_ev()
        next(r for r in ev["netem"] if r["record"] == "stats").pop("ingress")
        self.assertEqual(analyze_netem.check_netem_applied(ev, {})["status"], analyze.INCONCLUSIVE)


class NetemCleanupTests(unittest.TestCase):
    def test_a_verified_removal_twice_passes(self):
        res = analyze_netem.check_netem_cleanup(_netem_ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertLessEqual(res["measured"]["removal_late_s"], 10)

    def test_an_unverified_planned_removal_or_final_cleanup_fails(self):
        self.assertEqual(analyze_netem.check_netem_cleanup(_netem_ev(removed=False), {})["status"], analyze.FAIL)
        res = analyze_netem.check_netem_cleanup(_netem_ev(final_leftover=("device ifb0",)), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertIn("ifb0", " ".join(res["detail"]["problems"]))

    def test_a_late_removal_fails(self):
        self.assertEqual(analyze_netem.check_netem_cleanup(_netem_ev(remove_st=120.0), {"max_late_s": 10}) ["status"], analyze.FAIL)

    def test_no_final_cleanup_record_is_inconclusive(self):
        self.assertEqual(analyze_netem.check_netem_cleanup(_netem_ev(final=False), {})["status"], analyze.INCONCLUSIVE)

    def test_an_apply_that_failed_still_needs_a_clean_final_state(self):
        res = analyze_netem.check_netem_cleanup(_netem_ev(applied=False, removed=None), {})
        self.assertEqual(res["status"], analyze.PASS)
        res = analyze_netem.check_netem_cleanup(_netem_ev(applied=False, removed=None, final_leftover=("qdisc netem 30:",)), {})
        self.assertEqual(res["status"], analyze.FAIL)


class NetemRetransmitTests(unittest.TestCase):
    def test_a_rise_only_while_impaired_passes(self):
        res = analyze_netem.check_netem_retransmits(_netem_ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertAlmostEqual(res["measured"]["impaired"]["per_s"], 160 / 60.0, places=2)

    def test_no_rise_means_the_impairment_did_not_reach_the_transport(self):
        res = analyze_netem.check_netem_retransmits(_netem_ev(retx=(0.0, 0.0, 5.0, 5.0, 5.0)), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("rise" in p for p in res["detail"]["problems"]))

    def test_a_noisy_baseline_cannot_fake_the_effect(self):
        # 100 retransmits in the 29 s baseline (3.4/s) and 160 impaired (2.7/s): not 5x the clean rate
        res = analyze_netem.check_netem_retransmits(_netem_ev(retx=(0.0, 100.0, 260.0, 260.0, 260.0)), {})
        self.assertEqual(res["status"], analyze.FAIL)

    def test_retransmits_that_do_not_fall_after_the_removal_fail(self):
        res = analyze_netem.check_netem_retransmits(_netem_ev(retx=(0.0, 0.0, 160.0, 160.0, 260.0)), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("recovery" in p for p in res["detail"]["problems"]))

    def test_a_missing_series_is_inconclusive(self):
        ev = _netem_ev()
        for r in ev["netem"]:
            r.pop("metrics", None)
        self.assertEqual(analyze_netem.check_netem_retransmits(ev, {})["status"], analyze.INCONCLUSIVE)


class NetemSnapshotTests(unittest.TestCase):
    A = {"max_gap_ms": 250, "impaired_max_gap_ms": 1000, "impaired_p99_gap_ms": 400}

    def test_clean_cadence_in_every_phase_passes(self):
        res = analyze_netem.check_netem_snapshots(_netem_ev(), self.A)
        self.assertEqual(res["status"], analyze.PASS, res["detail"])
        self.assertEqual(set(res["measured"][0]), {"baseline", "impaired", "recovery"})

    def test_a_loss_recovery_gap_below_the_impaired_limit_passes_but_fails_in_the_baseline(self):
        res = analyze_netem.check_netem_snapshots(_netem_ev(gap_impaired=0.45), self.A)
        self.assertEqual(res["status"], analyze.PASS, res["detail"])
        res = analyze_netem.check_netem_snapshots(_netem_ev(gap_baseline=0.45), self.A)
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("baseline" in p for p in res["detail"]["problems"]))

    def test_a_freeze_over_the_impaired_limit_fails(self):
        res = analyze_netem.check_netem_snapshots(_netem_ev(gap_impaired=1.6), self.A)
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("impaired: max gap" in p for p in res["detail"]["problems"]))

    def test_a_collapsed_rate_fails(self):
        self.assertEqual(analyze_netem.check_netem_snapshots(_netem_ev(rate_hz=9.0), self.A)["status"], analyze.FAIL)

    def test_without_phase_windows_it_is_inconclusive(self):
        self.assertEqual(analyze_netem.check_netem_snapshots(_netem_ev(applied=False), self.A)["status"], analyze.INCONCLUSIVE)


class NetemPredictionTests(unittest.TestCase):
    def test_bounded_prediction_passes_with_the_numbers_per_phase(self):
        res = analyze_netem.check_netem_prediction(_netem_ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res["detail"])
        self.assertEqual(res["measured"][0]["impaired"]["unexplained_snaps"], 0)

    def test_hard_snaps_in_the_impaired_phase_over_the_bound_fail(self):
        res = analyze_netem.check_netem_prediction(_netem_ev(snaps_at=(40, 45, 50, 55, 60, 65)), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("hard snaps" in p for p in res["detail"]["problems"]))

    def test_a_snap_inside_the_bound_passes(self):
        self.assertEqual(analyze_netem.check_netem_prediction(_netem_ev(snaps_at=(40, 45)), {})["status"], analyze.PASS)

    def test_an_oversized_correction_fails(self):
        res = analyze_netem.check_netem_prediction(_netem_ev(corr_impaired=2.5), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("correction" in p for p in res["detail"]["problems"]))

    def test_a_keyframe_storm_in_the_impaired_phase_fails(self):
        res = analyze_netem.check_netem_prediction(_netem_ev(keyframes_impaired=120), {})
        self.assertEqual(res["status"], analyze.FAIL)
        self.assertTrue(any("keyframes" in p for p in res["detail"]["problems"]))

    def test_no_per_sample_counters_is_inconclusive(self):
        ev = _netem_ev()
        for c in ev["clients"]:
            for s in c["samples"]:
                s.pop("pred")
        self.assertEqual(analyze_netem.check_netem_prediction(ev, {})["status"], analyze.INCONCLUSIVE)


class NetemConvergenceTests(unittest.TestCase):
    def test_clients_that_agree_after_the_impairment_pass(self):
        res = analyze_netem.check_netem_convergence(_netem_ev(), {"converge_within_s": 10})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertIn("impaired", res["detail"])
        self.assertEqual(res["threshold"]["converge_within_s"], 10)

    def test_disagreement_only_while_impaired_is_reported_not_judged(self):
        res = analyze_netem.check_netem_convergence(_netem_ev(impaired_offset=0.8), {"converge_within_s": 10})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertGreater(res["detail"]["impaired"]["max"], 0.5)

    def test_disagreement_that_outlasts_the_window_fails(self):
        res = analyze_netem.check_netem_convergence(_netem_ev(recovery_offset_until=REMOVE_DONE + 14.0), {"converge_within_s": 10})
        self.assertEqual(res["status"], analyze.FAIL, res)

    def test_disagreement_that_ends_inside_the_window_passes(self):
        res = analyze_netem.check_netem_convergence(_netem_ev(recovery_offset_until=REMOVE_DONE + 6.0), {"converge_within_s": 10})
        self.assertEqual(res["status"], analyze.PASS, res)

    def test_without_phase_windows_it_is_inconclusive(self):
        self.assertEqual(analyze_netem.check_netem_convergence(_netem_ev(applied=False), {})["status"], analyze.INCONCLUSIVE)


class KcpHealthNullDropTests(unittest.TestCase):
    def _ev(self, dropped, closed):
        return _ev(metrics_start={"gameserver_kcp_datagrams_dropped_total": 0.0, "gameserver_kcp_sessions_closed_total": 0.0},
                   metrics_end={"gameserver_kcp_datagrams_dropped_total": dropped, "gameserver_kcp_sessions_closed_total": closed})

    def test_null_max_dropped_reports_drops_without_judging_them(self):
        res = analyze.check_kcp_health(self._ev(40.0, 0.0), {"max_dropped": None, "max_sessions_closed": 0})
        self.assertEqual(res["status"], analyze.PASS)
        self.assertEqual(res["measured"]["dropped"], 40.0)

    def test_a_closed_session_still_fails_and_the_default_still_judges_drops(self):
        self.assertEqual(analyze.check_kcp_health(self._ev(0.0, 1.0), {"max_dropped": None, "max_sessions_closed": 0})["status"], analyze.FAIL)
        self.assertEqual(analyze.check_kcp_health(self._ev(3.0, 0.0), {})["status"], analyze.FAIL)


class ScenarioTests(unittest.TestCase):
    def test_s18_is_valid_and_graded_by_the_netem_checks(self):
        sc = scenarios.load("S18")
        d = next(x for x in sc["disruptions"] if x["kind"] == "netem")
        base, imp, rec = netem.default_phases(d)
        self.assertEqual((base, imp, rec), (30.0, 60.0, 30.0))
        self.assertLessEqual(base + imp + rec, sc["duration_s"])
        checks = {a["check"] for a in sc["assertions"]}
        self.assertTrue({"netem_applied", "netem_cleanup", "netem_retransmits", "netem_snapshots", "netem_prediction",
                         "netem_convergence", "client_sessions", "kcp_health", "server_alive"} <= checks)
        self.assertIn("S18", json.loads((Path(scenarios.__file__).resolve().parent.parent / "suites.json").read_text())["robustness"])
        # the profile of the brief
        self.assertEqual(d["profile"], PROFILE)

    def test_every_check_of_s18_exists(self):
        for a in scenarios.load("S18")["assertions"]:
            self.assertIn(a["check"], analyze.CHECKS)

    def test_netem_ndjson_is_required_evidence_only_for_netem_scenarios(self):
        self.assertIn("netem.ndjson", provenance.expected_inventory(scenarios.load("S18")))
        self.assertNotIn("netem.ndjson", provenance.expected_inventory(scenarios.load("S17")))
        self.assertIn("netem.ndjson", provenance.MANIFEST_FILES)

    def test_validation_rejects_a_bad_profile_or_phases(self):
        base = scenarios.load("S18")
        for mutate in (lambda d: d.update(profile={}), lambda d: d.update(profile={"loss_pct": 90, "delay_ms": 1}),
                       lambda d: d.update(profile={"loss_pct": 5, "bogus": 1}), lambda d: d.update(impaired_s=200),
                       lambda d: d.update(directions=["sideways"])):
            sc = copy.deepcopy(base)
            mutate(next(x for x in sc["disruptions"] if x["kind"] == "netem"))
            with self.assertRaises(scenarios.ScenarioError):
                scenarios.validate(sc)

    def test_the_runner_cleans_up_in_its_own_finally(self):
        src = (Path(netem.__file__).parent / "runner.py").read_text(encoding="utf-8")
        self.assertIn("netem.final_cleanup(cfg, run_dir, log)", src)
        self.assertIn("netem.Shaper(cfg).preflight()", src)


if __name__ == "__main__":
    unittest.main()
