"""M4 harness defects H1-H7 (M1-FAILURE-MATRIX section 7c). Each test fails on the harness before the change.

    python3 -B testlab/tests/test_m4_harness.py

H1  viewer (outgoing) AnyDesk sessions get an end and a duration from the `Session count` lines
H2  cross_client_convergence leaves out samples of a client that is not InWorld, frozen or reconnecting - and still fails
    a convergence error outside such spans
H3  host_quiet INFO tiers (>= 30 ms in >= 2 processes within 50 ms; single-process freeze >= 1 s); the 250 ms grading is unchanged
H5  render_jumps reports the hop-size distribution per scripted boundary; grading unchanged
H6  soak-class runs refuse default player / server checkout and an unexpected SHA
H7  the guard copies the session-relevant ad.trace lines into host/ at stop
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import analyze, config, hostguard, scenarios, soakinputs  # noqa: E402
from test_lab import _ev, _sample  # noqa: E402


# ----------------------------------------------------------------------------------------------- H1, H7

def _line(ts, proc, pid, module, text, fiber=None):
    mid = f"{pid:>6}  17188  {fiber:>3}" if fiber is not None else f"{pid:>6}  17188"
    return f"   info {ts}      {proc:>5} {mid}                        {module} - {text}"


# ibz3, 2026-10-27: two consecutive viewer sessions of 15:00 each (front process), Session count lines in between.
TRACE = "\n".join([
    _line("2026-10-27 14:40:41.355", "lctrl", 16996, "ad_app.control", "Session count: (0, 0)."),
    _line("2026-10-27 14:41:55.881", "front", 16644, "app.session", "Session started"),
    _line("2026-10-27 14:41:55.883", "lctrl", 16996, "ad_app.control", "Session count: (1, 0)."),
    _line("2026-10-27 14:56:56.273", "lctrl", 16996, "ad_app.control", "Session count: (0, 0)."),
    _line("2026-10-27 14:56:58.992", "front", 16644, "app.session", "Session started"),
    _line("2026-10-27 14:56:58.994", "lctrl", 16996, "ad_app.control", "Session count: (1, 0)."),
    _line("2026-10-27 15:11:59.367", "lctrl", 16996, "ad_app.control", "Session count: (0, 0)."),
    _line("2026-10-27 15:20:00.100", "lsvc", 14696, "anynet.any_socket", "Accept request from 1234567890 (via relay).", 12),
    _line("2026-10-27 15:20:00.700", "lsvc", 14696, "app.session", "Authenticated with 1234567890 using token.", 827),
    _line("2026-10-27 15:20:01.000", "lsvc", 14696, "app.session", "Backend PID: 4242", 827),
    _line("2026-10-27 15:20:02.000", "lctrl", 16996, "ad_app.control", "Session count: (1, 1)."),
    _line("2026-10-27 15:25:02.000", "lctrl", 16996, "ad_app.control", "Session count: (0, 0)."),
    _line("2026-10-27 15:25:02.500", "lsvc", 14696, "app.service", "Heartbeat noise that is not a session line"),
]) + "\n"


class OutgoingSessionTests(unittest.TestCase):
    def test_viewer_session_ends_and_durations_come_from_the_session_count_lines(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        counts = [e for e in events if e["type"] == "session_count"]
        self.assertEqual([e["count"] for e in counts], [[0, 0], [1, 0], [0, 0], [1, 0], [0, 0], [1, 1], [0, 0]])
        rep = hostguard.outgoing_sessions(events)
        self.assertEqual([s["duration_s"] for s in rep["sessions"]], [900.4, 900.4])
        self.assertEqual([s["end_reason"] for s in rep["sessions"]], ["session_count", "session_count"])
        self.assertEqual(rep["sessions"][0]["end"], "2026-10-27T14:56:56.273Z")

    def test_an_incoming_session_is_not_a_viewer_session(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        rep = hostguard.outgoing_sessions(events)
        self.assertEqual(len(rep["sessions"]), 2)            # the (1, 1) session at 15:20 has no `front` start

    def test_a_viewer_session_without_an_end_line_stays_open_and_is_counted_to_the_window_end(self):
        events, _ = hostguard.parse_ad_trace("\n".join(TRACE.splitlines()[:3]) + "\n")
        t0 = events[1]["epoch"]
        rep = hostguard.outgoing_sessions(events, (t0 - 100.0, t0 + 400.0))
        s = rep["sessions"][0]
        self.assertEqual((s["end"], s["duration_s"], s["end_reason"], s.get("open_at_window_end")), (None, None, "not_seen", True))
        self.assertEqual(s["overlap_with_window_s"], 400.0)

    def test_window_fraction_is_the_measured_share_of_the_window(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        e0 = events[1]["epoch"]
        win = (e0 - 100.0, e0 - 100.0 + 2000.0)             # covers both 900 s sessions
        rep = hostguard.outgoing_sessions(events, win)
        self.assertAlmostEqual(rep["active_fraction_of_window"], 1800.8 / 2000.0, places=2)

    def test_session_count_never_counts_as_a_session_event_for_the_guards(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        self.assertNotIn("session_count", hostguard.SESSION_TYPES)
        win = (events[0]["epoch"] - 5.0, events[0]["epoch"] + 1.0)      # only the (0, 0) line is inside
        res = hostguard.evaluate([], [e for e in events if e["type"] == "session_count"], win)
        self.assertEqual([f["id"] for f in res["fired"]], [])

    def test_host_guard_check_reports_the_sessions_without_changing_the_grade(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        e0 = events[1]["epoch"]
        win = (e0 - 100.0, e0 + 2000.0)
        ev = _ev()
        ev["meta"] = {"host_guard": {"window_epoch": list(win), "start_wall_epoch": win[0] + 30, "required": False}}
        ev["hostguard"] = {"samples": [{"epoch": t, "ts": f"t{t:.0f}", "cpu": 10.0, "ad_cpu": 0.03,
                                        "ad": [{"pid": 1, "role": "resident", "cpu": 0.0}], "groups": {}}
                                       for t in range(int(win[0]), int(win[1]), 5)],
                           "events": events, "preflight": None, "summary": None, "procs": [], "procs_summary": None}
        res = analyze.check_host_guard(ev, {})
        sessions = res["detail"]["anydesk_outgoing_sessions"]["sessions"]
        self.assertEqual([s["duration_s"] for s in sessions], [900.4, 900.4])
        self.assertEqual(res["status"], analyze.INVALID)    # the grade is the G1 one it was before (a session in the window)


class AdTraceExcerptTests(unittest.TestCase):
    def test_excerpt_keeps_session_lines_and_redacts_the_peer(self):
        lines = hostguard.ad_trace_excerpt(TRACE, 0.0)
        text = "\n".join(lines)
        self.assertIn("Session count: (1, 0)", text)
        self.assertIn("Backend PID: 4242", text)
        self.assertNotIn("1234567890", text)
        self.assertIn("Accept request from <redacted>", text)
        self.assertIn("Authenticated with <redacted>", text)
        self.assertNotIn("Heartbeat noise", text)

    def test_excerpt_starts_at_the_requested_time(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        since = events[3]["epoch"]
        lines = hostguard.ad_trace_excerpt(TRACE, since)
        self.assertTrue(all("14:41" not in ln and "14:40" not in ln for ln in lines), lines)

    def test_guard_stop_copies_the_excerpt_into_the_host_directory(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "ad.trace"
            log.write_text(TRACE, encoding="utf-8")
            out = Path(d) / "host"
            out.mkdir()
            g = hostguard.HostGuard(out, paths=hostguard.AnyDeskPaths(log, None))
            g.started_epoch = hostguard.parse_ad_trace(TRACE)[0][-1]["epoch"] + 60.0      # an hour of lead covers all of TRACE
            summary = g.stop()
            ex = out / "ad-trace-excerpt.txt"
            self.assertTrue(ex.is_file())
            body = ex.read_text(encoding="utf-8")
            self.assertIn("Session count: (0, 0)", body)
            self.assertTrue(body.startswith("# rpg-factory testlab"))
            self.assertTrue(summary["ad_trace_excerpt"]["written"])
            self.assertEqual((out / "guard-summary.json").is_file(), True)

    def test_analysis_reads_the_excerpt_of_the_run_when_the_guard_events_have_no_session_end(self):
        events, _ = hostguard.parse_ad_trace(TRACE)
        legacy = [e for e in events if e["type"] != "session_count"]         # a run recorded before H1
        e0 = events[1]["epoch"]
        win = (e0 - 100.0, e0 + 2000.0)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "host").mkdir()
            (Path(d) / "host" / "ad-trace-excerpt.txt").write_text(TRACE, encoding="utf-8")
            ev = _ev()
            ev["run_dir"] = Path(d)
            ev["meta"] = {}
            ev["hostguard"] = {"events": legacy}
            rep = analyze._outgoing_sessions_report(ev, win)
        self.assertEqual([s["duration_s"] for s in rep["sessions"]], [900.4, 900.4])
        self.assertIn("ad-trace-excerpt", rep["source"])


# --------------------------------------------------------------------------------------------------- H2

class ConvergenceGapTests(unittest.TestCase):
    """Two clients draw one mob walking +x at 2 u/s as a function of the render tick. Client 0 freezes for 5 s at
    st 10-15 (no samples); when it resumes it draws the entity 1.5 u off for 0.7 s while it catches up (k4n5)."""

    def _ev(self, bad_at=None, reconnect=False):
        ev = _ev(clients=2, status=[{"_st": 1, "tick_rate": 60}], duration=40.0)
        for c in ev["clients"]:
            samples = []
            phase = 0.013 * c["index"]
            k = 0
            while True:
                st = 3.0 + phase + k * 0.05
                k += 1
                if st > 38.0:
                    break
                if c["index"] == 0 and 10.0 < st < 15.0:
                    continue                                     # the freeze: no sample
                tick = 1000 + st * 60
                x = st * 2.0
                if c["index"] == 0 and (15.0 <= st < 15.7 or (bad_at is not None and bad_at <= st < bad_at + 0.7)):
                    x += 1.5
                samples.append(_sample(st + 100.0, [["e", "mob", 0, x, 0.0, x, 0.0]], tick))
            c["samples"] = samples
            c["events"] = []
        if reconnect:
            ev["clients"][0]["events"] = [{"st": 15.0, "event": "net_state", "state": "Ended"},
                                          {"st": 15.05, "event": "net_state", "state": "Reconnecting"},
                                          {"st": 15.4, "event": "net_state", "state": "InWorld"}]
        return ev

    def test_a_frozen_client_catching_up_is_not_a_convergence_failure(self):
        res = analyze.check_cross_client_convergence(self._ev(), {})
        self.assertEqual(res["status"], analyze.PASS, res)
        self.assertGreater(res["measured"]["skipped_client_gap_samples"], 0)
        gap = res["detail"]["skipped_client_gaps"][0]
        self.assertEqual((gap["client"], gap["class"]), (0, "CLIENT"))
        self.assertLess(gap["from_st"], 10.1)
        self.assertGreater(gap["to_st"], 15.0)

    def test_the_same_error_outside_a_gap_still_fails(self):
        res = analyze.check_cross_client_convergence(self._ev(bad_at=25.0), {})
        self.assertEqual(res["status"], analyze.FAIL, res)
        self.assertGreaterEqual(res["measured"]["max"], 1.5)

    def test_net_state_spans_are_skipped_and_reported_as_reconnect(self):
        ev = self._ev(reconnect=True)
        spans = analyze.client_gap_spans(ev["clients"][0], 40.0)
        self.assertEqual([(round(a, 2), round(b, 2), why) for a, b, why in spans], [(14.5, 17.4, "RECONNECT")])

    def test_a_client_that_never_comes_back_is_skipped_to_the_end(self):
        c = {"events": [{"st": 20.0, "event": "net_state", "state": "Ended"}], "frames": []}
        self.assertEqual(analyze.client_gap_spans(c, 40.0), [(19.5, 42.0, "RECONNECT")])

    def test_a_long_client_frame_is_a_client_gap(self):
        c = {"events": [], "frames": [(30.0, 5000.0), (31.0, 16.0)]}
        self.assertEqual(analyze.client_gap_spans(c, 40.0), [(24.5, 32.0, "CLIENT")])


# --------------------------------------------------------------------------------------------------- H3

class HostQuietTierTests(unittest.TestCase):
    def _ev(self, frames):
        ev = _ev(clients=3)
        for c, fr in zip(ev["clients"], frames):
            c["frames"] = fr
        return ev

    def test_a_42_to_78_ms_stall_in_three_clients_is_an_info_host_stall_the_250_ms_rule_does_not_see(self):
        base = [(k / 60.0, 16.7) for k in range(600)]
        ev = self._ev([base + [(5.50, 42.0)], base + [(5.51, 60.0)], base + [(5.52, 78.0)]])
        res = analyze.check_host_quiet(ev, {})
        self.assertEqual(res["status"], analyze.INFO)
        self.assertEqual(res["measured"]["host_stalls"], 0)                    # the graded 250 ms rule: unchanged
        self.assertEqual(res["measured"]["host_stalls_info_30ms"], 1)
        top = res["detail"]["info_stalls_30ms"]["largest"][0]
        self.assertEqual((top["clients"], top["max_ms"]), ([0, 1, 2], 78.0))

    def test_one_process_alone_is_not_a_host_stall(self):
        base = [(k / 60.0, 16.7) for k in range(600)]
        res = analyze.check_host_quiet(self._ev([base + [(5.5, 80.0)], base, base]), {})
        self.assertEqual(res["measured"]["host_stalls_info_30ms"], 0)

    def test_stalls_more_than_50_ms_apart_do_not_pair(self):
        res = analyze.check_host_quiet(self._ev([[(5.50, 40.0)], [(5.60, 40.0)], []]), {})
        self.assertEqual(res["measured"]["host_stalls_info_30ms"], 0)

    def test_a_5_second_single_process_freeze_is_an_info_class(self):
        base = [(k / 60.0, 16.7) for k in range(100)]
        res = analyze.check_host_quiet(self._ev([base + [(50.0, 5000.0)], base, base]), {})
        self.assertEqual(res["status"], analyze.INFO)                          # never PRODUCT, never a failure
        self.assertEqual(res["measured"]["single_process_freezes_1s"], 1)
        self.assertEqual(res["detail"]["single_process_freezes"]["events"], [{"client": 0, "st": 50.0, "dt_ms": 5000.0}])

    def test_a_freeze_inside_a_graded_host_stall_is_not_double_counted(self):
        ev = self._ev([[(50.0, 1500.0)], [(50.0, 1500.0)], []])
        res = analyze.check_host_quiet(ev, {})
        self.assertGreater(res["measured"]["host_stalls"], 0)
        self.assertEqual(res["measured"]["single_process_freezes_1s"], 0)


# --------------------------------------------------------------------------------------------------- H5

class HopSizeTests(unittest.TestCase):
    SC = {"repeat_cycle_s": 300, "per_client": [{"steps": [{"t0": 2, "t1": 298, "mode": "circle"}]},
                                                {"steps": [{"t0": 2, "t1": 60}, {"t0": 60, "t1": 120}, {"t0": 240, "t1": 298}]}]}

    def test_sizes_are_grouped_by_the_nearest_scripted_boundary_modulo_the_cycle(self):
        ev = [{"st": 61.0, "step": 0.40, "allowed": 0.30}, {"st": 59.5, "step": 0.90, "allowed": 0.30},
              {"st": 361.0, "step": 0.50, "allowed": 0.31},          # 61 s into the second cycle
              {"st": 150.0, "step": 0.35, "allowed": 0.30, "local": True}]
        rep = analyze.hop_size_distribution(self.SC, ev)
        b = rep["boundaries"]
        self.assertEqual(b["t=60s (clients 1)"]["count"], 3)
        self.assertEqual(b["t=60s (clients 1)"]["size_max"], 0.9)
        self.assertEqual(b["none"]["local"], 1)
        self.assertEqual(rep["cycle_s"], 300.0)

    def test_render_jumps_reports_the_distribution_and_grading_is_unchanged(self):
        ev = _ev(clients=2, duration=300.0)
        ev["scenario"].update(self.SC)
        for c in ev["clients"]:
            c["summary"] = {"x": 1}
            c["events"] = [{"event": "render_jump", "st": 60.5, "id": "m", "type": "mob", "local": False, "step": 0.4,
                            "allowed": 0.3, "dt_ms": 16.0}]
        res = analyze.check_render_jumps(ev, {})
        self.assertEqual(res["measured"]["remote_minor"], 2)
        self.assertEqual(res["status"], analyze.PASS)                       # 2 over 5 client-minutes: under 30 per client-minute
        self.assertEqual(res["detail"]["hop_sizes_by_boundary"]["boundaries"]["t=60s (clients 1)"]["count"], 2)


# --------------------------------------------------------------------------------------------------- H6

class SoakInputsTests(unittest.TestCase):
    SOAK = {"id": "S09", "requires_clean_host": True}

    def _cfg(self, explicit=()):
        cfg = config.LabConfig(workspace=Path("W"), runs_root=Path("W/runs"), player_exe=Path("W/p/StandaloneWindows64/Game.exe"),
                               server_repo=Path("W/srv"), client_project=Path("W/cl"))
        cfg.explicit = set(explicit)
        return cfg

    def _check(self, cfg, sc=None, **kw):
        return soakinputs.check(cfg, sc or self.SOAK, server_head=lambda p: "aaaaaaa1111111", player_head=lambda p: "bbbbbbb2222222", **kw)

    def test_defaults_are_refused_for_a_soak(self):
        with self.assertRaisesRegex(soakinputs.SoakInputsError, r"no explicit --player.*no explicit --server-repo"):
            self._check(self._cfg())
        with self.assertRaisesRegex(soakinputs.SoakInputsError, "no explicit --server-repo"):
            self._check(self._cfg({"player_exe"}))
        with self.assertRaisesRegex(soakinputs.SoakInputsError, "no explicit --player"):
            self._check(self._cfg({"server_repo"}))

    def test_other_scenarios_keep_their_defaults(self):
        rec = self._check(self._cfg(), {"id": "S01"})
        self.assertFalse(rec["required"])

    def test_explicit_inputs_are_recorded_and_pass(self):
        rec = self._check(self._cfg({"player_exe", "server_repo"}))
        self.assertEqual((rec["explicit"], rec["server_sha"], rec["player_sha"]), (["player_exe", "server_repo"], "aaaaaaa1111111", "bbbbbbb2222222"))

    def test_expected_shas_must_match_by_prefix(self):
        cfg = self._cfg({"player_exe", "server_repo"})
        self._check(cfg, expect_player_sha="bbbbbbb2", expect_server_sha="AAAAAAA1")
        with self.assertRaisesRegex(soakinputs.SoakInputsError, "player built from bbbbbbb2222222, expected 908950f"):
            self._check(cfg, expect_player_sha="908950f")
        with self.assertRaisesRegex(soakinputs.SoakInputsError, "server checkout at aaaaaaa1111111, expected 11f0140"):
            self._check(cfg, expect_server_sha="11f0140")
        with self.assertRaisesRegex(soakinputs.SoakInputsError, "expected abc"):
            self._check(cfg, expect_server_sha="abc")                        # fewer than 7 digits never matches

    def test_an_unreadable_player_build_fails_an_expectation(self):
        cfg = self._cfg({"player_exe", "server_repo"})
        with self.assertRaisesRegex(soakinputs.SoakInputsError, "unknown commit"):
            soakinputs.check(cfg, self.SOAK, expect_player_sha="bbbbbbb", server_head=lambda p: "a" * 40, player_head=lambda p: None)

    def test_config_marks_cli_and_file_values_explicit_and_defaults_not(self):
        cfg = config.LabConfig(workspace=Path("W"))
        self.assertEqual(cfg.explicit, set())
        cfg.apply({"player_exe": Path("W/x.exe")})
        self.assertEqual(cfg.explicit, {"player_exe"})

    def test_the_cli_refuses_before_any_stack_is_touched(self):
        import testlab as cli
        args = SimpleNamespace(scenarios=["S09"], duration=None, clients=None, snapshot_trace=False,
                               expect_player_sha=None, expect_server_sha=None)
        code = cli._refuse_stale_soak_inputs(self._cfg(), ["S09"], args)
        self.assertEqual(code, 3)
        self.assertIsNone(cli._refuse_stale_soak_inputs(self._cfg(), ["S01"], args))

    def test_runner_refuses_before_creating_a_run_directory(self):
        from lab import runner
        with tempfile.TemporaryDirectory() as d:
            cfg = config.LabConfig(workspace=Path(d), runs_root=Path(d) / "runs-root")
            with self.assertRaises(soakinputs.SoakInputsError):
                runner.run(cfg, "S09", quiet=True)
            self.assertFalse((Path(d) / "runs-root" / "runs").exists())


if __name__ == "__main__":
    unittest.main()
