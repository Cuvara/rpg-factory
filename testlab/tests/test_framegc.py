"""lab/framegc.py: the appended frames.csv GC columns (client TestLab, UCF F-21) in the analysis.

    python3 -B testlab/tests/test_framegc.py

An old run (frames.csv with four columns) must analyze exactly as before: same frame series, same
results.json, same report.md, no "Frame budget" section. A new run adds that section, a `frame_gc` key in
results.json, and a note in failure-summary.json when a stall frame coincided with a gen0 collection.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import analyze, failsum, framegc, report, util  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "failsum" / "3ng5"
OLD_HEADER = "frame,t,dt_ms,scenario_t"
# The header and row layout FrameCsv.cs (client) writes.
NEW_HEADER = "frame,t,dt_ms,scenario_t,gc_alloc_b,gc_count,main_ms,used_mb"


def _old_rows():
    # frame 0 is before the scenario window; frame 4 is a 300 ms stall.
    return [(0, 99.0, 16.7, -0.5), (1, 100.0, 16.6, 0.0), (2, 100.02, 16.7, 0.02), (3, 100.04, 16.7, 0.04),
            (4, 100.34, 300.0, 0.34), (5, 100.36, 16.7, 0.36)]


def _write_frames(path: Path, new: bool, collect_at=4) -> None:
    lines = [NEW_HEADER if new else OLD_HEADER]
    count = 7
    for frame, t, dt, st in _old_rows():
        row = f"{frame},{t},{dt},{st}"
        if new:
            if frame == collect_at:
                count += 1
            row += f",{2048 if frame != 4 else 900000},{count},{'' if frame == 0 else dt - 1},{120.5}"
        lines.append(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _copy_run(td: Path, new: bool, collect_at=4) -> Path:
    run = td / ("new" if new else "old") / "run"
    shutil.copytree(FIXTURE, run)
    for d in run.glob("client-*"):
        _write_frames(d / "frames.csv", new, collect_at)
    return run


def _analyze(run: Path, out: Path):
    ev = analyze.load_evidence(run)
    stored = json.loads((FIXTURE / "results.json").read_text(encoding="utf-8"))
    with mock.patch.object(util, "utc_stamp", return_value="2026-01-01T00:00:00Z"):
        report.write(run, ev, stored["assertions"], stored["outcome"], None, out_dir=out)
    return ev, out


class OldRunTests(unittest.TestCase):
    def test_old_columns_give_no_summary(self):
        with tempfile.TemporaryDirectory() as td:
            run = _copy_run(Path(td), new=False)
            self.assertIsNone(framegc.summarize({"clients": [{"index": 0, "dir": run / "client-0"}]}))
            self.assertIsNone(framegc.read_client(run / "client-0" / "missing.csv"))

    def test_old_run_and_new_run_analyze_the_same_except_the_new_section(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ev_old, out_old = _analyze(_copy_run(td, False), td / "out-old")
            ev_new, out_new = _analyze(_copy_run(td, True), td / "out-new")
            for a, b in zip(ev_old["clients"], ev_new["clients"]):
                self.assertEqual(list(a["frames"]), list(b["frames"]), "frame series must not depend on the new columns")
                self.assertEqual(len(a["frames"]), 5)
            md_old = (out_old / "report.md").read_text(encoding="utf-8")
            md_new = (out_new / "report.md").read_text(encoding="utf-8")
            self.assertNotIn("## Frame budget", md_old)
            self.assertIn("## Frame budget", md_new)
            start = md_new.index("## Frame budget")
            end = md_new.index("Raw evidence:")
            stripped = (md_new[:start] + md_new[end:]).replace("\n\n\n", "\n\n")
            self.assertEqual(md_old.replace(str(td / "old"), "T"), stripped.replace(str(td / "new"), "T"))
            res_old = json.loads((out_old / "results.json").read_text(encoding="utf-8"))
            res_new = json.loads((out_new / "results.json").read_text(encoding="utf-8"))
            self.assertNotIn("frame_gc", res_old)
            self.assertEqual(sorted(res_new["frame_gc"]), ["0", "1", "2"])
            res_new.pop("frame_gc")
            for r in (res_old, res_new):
                for k in ("analysis", "player"):
                    r.pop(k, None)
            self.assertEqual(res_old["assertions"], res_new["assertions"])
            self.assertEqual(res_old["outcome"], res_new["outcome"])


class NewColumnsTests(unittest.TestCase):
    def test_summary_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            run = _copy_run(Path(td), new=True)
            r = framegc.read_client(run / "client-0" / "frames.csv")
        self.assertEqual(r["frames_with_alloc"], 5)  # frame 0 is before the window
        self.assertEqual(r["gc_alloc_b"], {"p50": 2048.0, "p95": 900000.0, "max": 900000.0})
        self.assertEqual(r["gc_collections"], 1)
        self.assertEqual(len(r["stall_frames"]), 1)
        stall = r["stall_frames"][0]
        self.assertEqual((stall["st"], stall["dt_ms"], stall["gc_alloc_b"], stall["gc_collections"]), (0.34, 300.0, 900000, 1))
        self.assertEqual(r["stalls_with_gc"], 1)

    def test_collection_in_the_frame_before_the_stall_counts(self):
        with tempfile.TemporaryDirectory() as td:
            run = _copy_run(Path(td), new=True, collect_at=3)
            r = framegc.read_client(run / "client-0" / "frames.csv")
        self.assertEqual(r["stalls_with_gc"], 1)

    def test_stall_without_a_collection_gives_no_note(self):
        with tempfile.TemporaryDirectory() as td:
            run = _copy_run(Path(td), new=True, collect_at=99)
            ev = {"clients": [{"index": 0, "dir": run / "client-0"}]}
            self.assertIsNone(framegc.stall_note(ev))

    def test_empty_cells_are_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "frames.csv"
            p.write_text(NEW_HEADER + "\n1,1.0,16.6,0.5,,,,\n2,1.1,300,0.6,,,,\nbad\n", encoding="utf-8")
            r = framegc.read_client(p)
        self.assertEqual((r["frames_with_alloc"], r["gc_collections"], r["stalls_with_gc"]), (0, 0, 0))
        self.assertFalse(r["stall_frames"][0]["gc_known"])

    def test_failure_summary_note_for_frame_time(self):
        with tempfile.TemporaryDirectory() as td:
            run = _copy_run(Path(td), new=True)
            ev = analyze.load_evidence(run)
            result = {"id": "frame_time", "check": "frame_time", "status": analyze.FAIL, "detail": {}, "artifacts": []}
            doc = failsum.build(run, ev, [result], analyze.FAIL, None)
            note = doc["failures"][0]["notes"][0]
            self.assertIn("stall frame coincided with gen0 GC", note)
            plain = _copy_run(Path(td) / "p", new=False)
            doc = failsum.build(plain, analyze.load_evidence(plain), [result], analyze.FAIL, None)
            self.assertNotIn("notes", doc["failures"][0])


if __name__ == "__main__":
    unittest.main()
