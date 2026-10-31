"""lab/failsum.py (failure-summary.json) on small scrubbed excerpts of real runs, plus its rules.

    python3 -B testlab/tests/test_failsum.py

Fixtures (tests/fixtures/failsum, cut from the full runs by extract.py): k4n5, ibz3 and 9tgw are INVALID
soaks (an AnyDesk session ran during the window), 3ng5 is a FAIL on a recorded host. The summary is derived
output: it never changes the results it reads.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import analyze, failsum, report  # noqa: E402
from test_lab import _ev  # noqa: E402
from test_framegc import NewColumnsTests, OldRunTests  # noqa: E402,F401  (run with this suite: tests/run-all.sh lists test_failsum.py)

ROOT = Path(__file__).resolve().parent / "fixtures" / "failsum"


class FixtureTests(unittest.TestCase):
    def _build(self, name):
        d = ROOT / name
        ev = analyze.load_evidence(d)
        counted = d / "counted_jumps.json"
        if counted.exists():  # what check_render_jumps leaves in ev["_failsum"] when the analysis ran in-process
            ev["_failsum"] = {"render_jumps": json.loads(counted.read_text(encoding="utf-8"))}
        stored = json.loads((d / "results.json").read_text(encoding="utf-8"))
        before = copy.deepcopy(stored["assertions"])
        doc = failsum.build(d, ev, stored["assertions"], stored["outcome"], stored.get("harness_error"))
        self.assertEqual(stored["assertions"], before, "the summary must not edit the results it reads")
        return doc, {f["id"]: f for f in doc["failures"]}

    def test_k4n5_places_every_failure_and_blames_the_host_session(self):
        doc, f = self._build("k4n5")
        self.assertEqual(doc["verdict"], "INVALID")
        self.assertEqual(doc["scenario_start_utc"], "2026-10-28T07:33:37.798Z")
        self.assertEqual(sorted(f), ["cross_client_convergence", "entity_lifecycle", "host_guard", "kcp", "snapshots"])
        # The run's earliest event is the first AnyDesk session evidence inside the window.
        self.assertEqual(doc["earliest_event"]["check"], "host_guard")
        self.assertEqual(doc["earliest_event"]["wall_utc"], "2026-10-28T07:35:22.016Z")
        self.assertAlmostEqual(doc["earliest_event"]["scenario_s"], 104.218, places=2)
        self.assertEqual((f["host_guard"]["suspected_layer"], f["host_guard"]["layer_rule"], f["host_guard"]["confidence"]),
                         ("environment", "L1", "high"))
        # First snapshot gap over 250 ms in the window: 4.76 s, in client 2, during the second AnyDesk session.
        snap = f["snapshots"]
        self.assertEqual(snap["earliest_event"]["client"], 2)
        self.assertAlmostEqual(snap["earliest_event"]["scenario_s"], 1215.312, places=2)
        self.assertEqual(snap["earliest_event"]["wall_utc"], "2026-10-28T07:53:53.110Z")
        self.assertIn("4758.7 ms", snap["earliest_event"]["what"])
        self.assertEqual((snap["suspected_layer"], snap["layer_rule"], snap["alternative_layer"], snap["confidence"]),
                         ("environment", "L3", "server", "high"))
        self.assertTrue(any(g["kind"] == "session_active" for g in snap["guard_events_within_10s"]))
        self.assertEqual(snap["evidence"][0]["file"], "client-2/snapshots.ndjson")
        self.assertIsInstance(snap["evidence"][0]["line"], int)
        # Process time of the lifecycle row maps to scenario time through the client's first st-stamped event.
        life = f["entity_lifecycle"]
        self.assertEqual((life["earliest_event"]["client"], life["suspected_layer"], life["alternative_layer"]),
                         (2, "environment", "netcode"))
        self.assertAlmostEqual(life["earliest_event"]["scenario_s"], 1220.076, places=2)
        # The worst convergence pair: render tick mapped to scenario time through client 0's snapshot ticks.
        conv = f["cross_client_convergence"]
        self.assertAlmostEqual(conv["earliest_event"]["scenario_s"], 1226.05, places=2)
        self.assertEqual(conv["evidence"][0]["file"], "client-0/snapshots.ndjson")

    def test_k4n5_kcp_counters_have_no_time_so_the_event_is_unlocated(self):
        _, f = self._build("k4n5")
        kcp = f["kcp"]
        self.assertIsNone(kcp["earliest_event"])
        self.assertEqual((kcp["suspected_layer"], kcp["layer_rule"], kcp["confidence"]), ("server", "L4", "low"))
        lines = [(e["file"], e["line"]) for e in kcp["evidence"] if e["line"]]
        self.assertTrue(lines and all(file == "server/metrics-end.txt" for file, _ in lines))
        text = (ROOT / "k4n5" / "server" / "metrics-end.txt").read_text(encoding="utf-8").splitlines()
        self.assertTrue(all("gameserver_kcp_" in text[n - 1] for _, n in lines))
        self.assertIn("metrics-end.txt", kcp["next_action"])

    def test_ibz3_render_jumps_not_counted_by_the_current_analyzer_stay_unlocated(self):
        """The stored FAIL is from an older analyzer (a local respawn snap counted as local_major); the current check
        counts none, so there is no counted jump to point at and the summary says so instead of guessing."""
        doc, f = self._build("ibz3")
        self.assertEqual(doc["verdict"], "INVALID")
        self.assertIsNone(f["render_jumps"]["earliest_event"])
        self.assertEqual((f["render_jumps"]["suspected_layer"], f["render_jumps"]["confidence"]), ("netcode", "low"))
        life = f["entity_lifecycle"]
        self.assertEqual(life["earliest_event"]["client"], 1)
        self.assertAlmostEqual(life["earliest_event"]["scenario_s"], 1062.972, places=2)
        # INVALID run, no guard event near this failure: the layer is the check's default prior, confidence low.
        self.assertEqual((life["suspected_layer"], life["layer_rule"], life["confidence"]), ("netcode", "L4", "low"))
        self.assertEqual(doc["earliest_event"]["check"], "host_guard")
        self.assertEqual(doc["earliest_event"]["wall_utc"], "2026-10-27T15:07:31.161Z")

    def test_9tgw_invalid_only_by_the_guard(self):
        doc, f = self._build("9tgw")
        self.assertEqual(list(f), ["host_guard"])
        self.assertEqual(doc["earliest_event"]["wall_utc"], "2026-10-25T13:14:49.175Z")
        self.assertAlmostEqual(doc["earliest_event"]["scenario_s"], 426.115, places=2)
        self.assertIn("G2", doc["earliest_event"]["what"])
        self.assertEqual(f["host_guard"]["suspected_layer"], "environment")
        self.assertIn("quiet host", f["host_guard"]["next_action"])

    def test_3ng5_fail_on_a_recorded_host_is_netcode_with_medium_confidence(self):
        doc, f = self._build("3ng5")
        self.assertEqual(doc["verdict"], "FAIL")
        jump = f["render_jumps"]
        self.assertEqual(jump["earliest_event"]["client"], 0)
        self.assertAlmostEqual(jump["earliest_event"]["scenario_s"], 3039.49, places=2)
        self.assertEqual(jump["earliest_event"]["wall_utc"], "2026-10-25T00:59:03.510Z")
        self.assertIn("local_major", jump["earliest_event"]["what"])
        self.assertEqual((jump["suspected_layer"], jump["layer_rule"], jump["confidence"], jump["guard_events_within_10s"]),
                         ("netcode", "L4", "medium", []))
        self.assertEqual(jump["evidence"][0]["file"], "client-0/events.ndjson")
        self.assertIsInstance(jump["evidence"][0]["line"], int)
        self.assertIn("replay-trace", jump["next_action"])

    def test_written_file_is_json_with_the_exit_code_and_the_rules(self):
        d = ROOT / "9tgw"
        ev = analyze.load_evidence(d)
        stored = json.loads((d / "results.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            path = failsum.write(d, ev, stored["assertions"], stored["outcome"], None, td)
            doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((doc["schema"], doc["verdict"], doc["exit_code"], doc["derived_only"]),
                         (failsum.SCHEMA, "INVALID", 2, True))
        self.assertEqual(set(doc["rules"]), {"layers", "confidence", "guard_window_s", "doc"})


class RuleTests(unittest.TestCase):
    def test_pass_has_no_summary_and_a_stale_one_is_removed(self):
        results = [{"id": "a", "check": "clients_in_world", "status": "PASS", "detail": {}}]
        self.assertIsNone(failsum.build(".", _ev(), results, analyze.PASS, None))
        with tempfile.TemporaryDirectory() as td:
            stale = Path(td) / failsum.FILE_NAME
            stale.write_text(json.dumps({"schema": failsum.SCHEMA}), encoding="utf-8")
            self.assertIsNone(failsum.write(".", _ev(), results, analyze.PASS, None, td))
            self.assertFalse(stale.exists())
            stale.write_text("{}", encoding="utf-8")  # not ours: left alone
            failsum.write(".", _ev(), results, analyze.PASS, None, td)
            self.assertTrue(stale.exists())

    def test_pass_with_warnings_reports_the_informational_breach(self):
        results = [{"id": "mem", "check": "memory_growth", "status": "INFO", "detail": {"would_be": "FAIL"},
                    "measured": 1, "threshold": 0},
                   {"id": "ok", "check": "clients_in_world", "status": "PASS", "detail": {}}]
        doc = failsum.build(".", _ev(), results, analyze.PASS_WITH_WARNINGS, None)
        self.assertEqual([f["id"] for f in doc["failures"]], ["mem"])
        self.assertTrue(doc["failures"][0]["informational_breach"])
        self.assertEqual(doc["failures"][0]["suspected_layer"], "client")

    def test_harness_error_and_broken_checks_are_the_harness_layer(self):
        results = [{"id": "x", "check": "kcp_health", "status": "INCONCLUSIVE", "detail": {"why": "check raised KeyError: 'a'"}}]
        doc = failsum.build(".", _ev(), results, analyze.INCONCLUSIVE, "stack did not start")
        self.assertEqual([(f["id"], f["suspected_layer"]) for f in doc["failures"]],
                         [("harness_error", "harness"), ("x", "harness")])
        self.assertEqual(doc["failures"][1]["layer_rule"], "L2")

    def test_unknown_check_is_unknown_layer_with_low_confidence(self):
        doc = failsum.build(".", _ev(), [{"id": "z", "check": "no_such_check", "status": "FAIL", "detail": {}}],
                            analyze.FAIL, None)
        f = doc["failures"][0]
        self.assertEqual((f["suspected_layer"], f["layer_rule"], f["confidence"]), ("unknown", "L5", "low"))
        self.assertIsNone(f["earliest_event"])

    def test_every_registered_check_has_a_default_layer(self):
        self.assertEqual(sorted(set(analyze.CHECKS) - set(failsum.LAYER_BY_CHECK)), [])
        self.assertTrue(set(failsum.LAYER_BY_CHECK.values()) <= set(failsum.LAYERS))
        self.assertEqual(set(failsum.NEXT_ACTIONS_BY_LAYER), set(failsum.LAYERS))

    def test_a_broken_builder_never_raises_and_the_error_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            failsum.write(".", {"no": "run_dir"}, [{"id": "a", "check": "kcp_health", "status": "FAIL"}],
                          analyze.FAIL, None, td)
            doc = json.loads(Path(td, failsum.FILE_NAME).read_text(encoding="utf-8"))
            self.assertEqual(doc["verdict"], "FAIL")
            self.assertIn("error", doc)

    def test_non_oserror_summary_write_failures_keep_verdict_and_exit_code(self):
        results = [{"id": "bad", "check": "kcp_health", "status": "FAIL", "detail": {}}]
        for error_type in (ValueError, TypeError):
            with self.subTest(error_type=error_type.__name__), tempfile.TemporaryDirectory() as td:
                with mock.patch.object(failsum.util, "write_json", side_effect=error_type("serializer failed")):
                    path = failsum.write(".", _ev(), results, analyze.FAIL, None, td)
                self.assertIsNotNone(path)
                doc = json.loads(Path(td, failsum.FILE_NAME).read_text(encoding="utf-8"))
                self.assertEqual((doc["verdict"], doc["exit_code"]),
                                 (analyze.FAIL, report.EXIT_CODES[analyze.FAIL]))
                self.assertEqual(doc["error"], f"{error_type.__name__}: serializer failed")


if __name__ == "__main__":
    unittest.main()
