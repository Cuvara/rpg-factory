"""The client's predictor call trace (client-N/trace.ndjson, plan `predictor_trace`; Netcode >= 8986908):
validation and a per-stall summary of the corrections it records.

The trace is what Netcode's `PredictorTraceReplayer` replays headless (Netcode owns the replayer and
its file-driven entry point; the recipe is in testlab/README.md "Predictor call trace"). This module
does not replay anything: it checks the file is complete and well ordered, so a replay can start
from it, and reports the corrections the live predictor itself recorded (`ReconcileResult`).

Line kinds (client docs/TESTLAB.md "Predictor call trace"): one `{"kind":"header"}` first, a
`{"kind":"session"}` per join, a frame marker `{"frame":N,"t":..,"udt":..,"dt":..}` before each frame's
calls, and one `{"c":<PredictorCall>,...}` per traced call. Frame `t` is realtime seconds, the same axis
as the `t` of events.ndjson (and the `start`/`end` of a stall event).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import util

SCHEMA = "rpg.testlab.predictor-trace.v1"
FILE_NAME = "trace.ndjson"

# Netcode Runtime/Prediction/PredictorTrace.cs `PredictorCall` (8986908).
CALLS = {
    1: "UseServerProtocol", 2: "UseServerTickRate", 3: "SetMapGeometry", 4: "SetMotorParams",
    5: "RecordInput", 6: "Reconcile", 7: "Advance", 8: "SetServerSpeed", 9: "SeedBaseTick",
    10: "SteerToServerTick", 11: "SkipReconcileForBunchedSnapshot", 12: "SetClockRateScale", 13: "Reset",
    14: "SetHoldTicks", 32: "ReconcileResult", 64: "SteeringOnSnapshotBegin", 65: "SteeringOnSnapshotEnd",
    66: "SteeringNoteInputSent", 67: "SteeringSampleTickRate", 68: "SteeringRoundTripMs", 69: "SteeringReset",
}
RECONCILE, RESULT, RESET = 6, 32, 13
RECORD_INPUT = 5
STEER_BEGIN, STEER_END = 64, 65
STEERING_TIMED = (64, 66, 67)  # steering calls whose `t` is the steering clock (seconds)


def traced_clients(run_dir: Path) -> list[int]:
    """Client indices whose plan asked for the trace or whose directory holds one."""
    out = []
    for d in sorted(Path(run_dir).glob("client-*")):
        try:
            i = int(d.name.split("-", 1)[1])
        except ValueError:
            continue
        plan = util.read_json(d / "plan.json", default={}) or {}
        if plan.get("predictor_trace") or (d / FILE_NAME).exists():
            out.append(i)
    return sorted(out)


def _clock_offset(events) -> float | None:
    """realtime t minus scenario st, from the first event that has both."""
    for e in events:
        if e.get("t") is not None and e.get("st") is not None:
            return float(e["t"]) - float(e["st"])
    return None


def _stalls(events) -> list[dict]:
    rows = sorted((e for e in events if e.get("event") == "stall" and e.get("start") is not None
                   and e.get("end") is not None), key=lambda e: e["start"])
    return [{"start": float(e["start"]), "end": float(e["end"]),
             "ms": e.get("actual_ms") or e.get("ms")} for e in rows]


def summarise(client_dir: Path, *, min_correction: float = 0.05, local_window_s: float = 5.0,
              max_listed: int = 20) -> dict:
    """Validate client_dir/trace.ndjson and summarise its recorded corrections.

    `problems` make the trace unusable for an exact replay (no header or settings, unknown call, a
    reconcile without its result, broken steering nesting, frames or steering times going backwards,
    an unreadable line before the last). `warnings` do not (a cut-short last line, a late attach,
    input ticks going backwards without a Reset, counts that differ from summary.json).
    Corrections are `ReconcileResult` events with LastCorrection >= min_correction; each is placed in
    the frame whose marker precedes it and attributed to a scripted stall when it falls within
    [stall start, min(start + local_window_s, next stall start)) on the realtime axis."""
    client_dir = Path(client_dir)
    path = client_dir / FILE_NAME
    out = {"client_dir": str(client_dir), "file": str(path), "valid": False, "problems": [], "warnings": [],
           "header": None, "sessions": [], "counts": {}, "stalls": [], "outside_stalls": {},
           "min_correction": min_correction, "local_window_s": local_window_s}
    problems, warnings = out["problems"], out["warnings"]
    if not path.exists():
        problems.append(f"no {FILE_NAME} in {client_dir} (plan predictor_trace off, or a client without the trace)")
        return out

    events = util.LazyNdjson(client_dir / "events.ndjson")
    off = _clock_offset(events)
    stalls = _stalls(events)
    for e in events:
        if e.get("event") == "trace_attached" and int(e.get("snapshots_before") or 0) > 0:
            warnings.append(f"trace attached after {e.get('snapshots_before')} snapshot(s) "
                            f"({e.get('target') or 'sink'}): the replay starts mid-session")

    by_call: dict[str, int] = {}
    lines = frames = calls = before_first_frame = 0
    frame_no, frame_t = None, None
    pending_reconcile = None  # line number of a Reconcile still waiting for its ReconcileResult
    in_steering = None
    last_steer_t = None
    last_input_tick = None
    prev_snaps = None
    corrections = []
    bad_lines = []
    last_line = 0
    try:
        fh = open(path, "rb")
    except OSError as exc:
        problems.append(f"{path}: {exc}")
        return out
    with fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            last_line = lineno
            lines += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad_lines.append(lineno)
                continue
            if not isinstance(row, dict):
                bad_lines.append(lineno)
                continue
            if lines == 1:
                if row.get("kind") != "header":
                    problems.append("line 1 is not the header ({\"kind\":\"header\"})")
                else:
                    out["header"] = row
                    if row.get("schema") != SCHEMA:
                        problems.append(f"header schema {row.get('schema')!r}, expected {SCHEMA}")
                    if not row.get("settings_read"):
                        problems.append("header settings_read is false: the predictor's PredictionSettings "
                                        "are unknown, so a replay cannot be built exactly")
                    if not row.get("map"):
                        problems.append("header has no map id (the replay needs the map's geometry)")
                    if row.get("tick_rate_is_fallback"):
                        warnings.append("header tick_rate_is_fallback: the predictor started on the "
                                        "fallback rate (the trace records the adoption, if any)")
                continue
            kind = row.get("kind")
            if kind == "header":
                problems.append(f"line {lineno}: a second header")
                continue
            if kind == "session":
                out["sessions"].append(row)
                continue
            if "frame" in row and "c" not in row:
                frames += 1
                f, t = row.get("frame"), row.get("t")
                if not isinstance(f, int) or not isinstance(t, (int, float)):
                    problems.append(f"line {lineno}: frame marker without an integer frame and a time")
                    continue
                if frame_no is not None and f <= frame_no:
                    problems.append(f"line {lineno}: frame {f} after frame {frame_no} (frames must increase)")
                if frame_t is not None and t < frame_t:
                    problems.append(f"line {lineno}: frame {f} time {t} before the previous frame's {frame_t}")
                if pending_reconcile is not None:
                    problems.append(f"line {pending_reconcile}: Reconcile without its ReconcileResult "
                                    f"before frame {f}")
                    pending_reconcile = None
                frame_no, frame_t = f, t
                continue
            if "c" not in row:
                warnings.append(f"line {lineno}: unknown line kind, ignored")
                continue
            code = row.get("c")
            name = CALLS.get(code)
            if name is None:
                problems.append(f"line {lineno}: unknown call code {code!r}")
                continue
            calls += 1
            by_call[name] = by_call.get(name, 0) + 1
            if frame_no is None:
                before_first_frame += 1
            if pending_reconcile is not None and code != RESULT:
                problems.append(f"line {pending_reconcile}: Reconcile followed by {name} (line {lineno}), "
                                f"not by its ReconcileResult")
                pending_reconcile = None
            if code == RECONCILE:
                pending_reconcile = lineno
            elif code == RESULT:
                if pending_reconcile is None:
                    problems.append(f"line {lineno}: ReconcileResult without a Reconcile")
                pending_reconcile = None
                corr, snaps = float(row.get("x") or 0.0), row.get("w")
                snapped = prev_snaps is not None and snaps is not None and snaps > prev_snaps
                if snaps is not None:
                    prev_snaps = snaps
                if corr >= min_correction or snapped:
                    corrections.append({"line": lineno, "frame": frame_no, "t": frame_t,
                                        "st": round(frame_t - off, 4) if frame_t is not None and off is not None else None,
                                        "correction": round(corr, 4), "snap": snapped,
                                        "base_tick": row.get("a"), "tick_error": row.get("b"),
                                        "stall_resyncs": row.get("c2")})
            elif code == STEER_BEGIN:
                if in_steering is not None:
                    problems.append(f"line {lineno}: SteeringOnSnapshotBegin inside the one from line {in_steering}")
                in_steering = lineno
            elif code == STEER_END:
                if in_steering is None:
                    problems.append(f"line {lineno}: SteeringOnSnapshotEnd without a Begin")
                in_steering = None
            elif code == RECORD_INPUT:
                tick = row.get("a")
                if last_input_tick is not None and tick is not None and tick < last_input_tick:
                    warnings.append(f"line {lineno}: input tick {tick} after {last_input_tick} without a Reset")
                last_input_tick = tick
            elif code == RESET:
                last_input_tick = None
            if code in STEERING_TIMED:
                t = row.get("t")
                if last_steer_t is not None and t is not None and t < last_steer_t:
                    problems.append(f"line {lineno}: steering time {t} before {last_steer_t}")
                if t is not None:
                    last_steer_t = t

    # A writer killed mid-line leaves the last line cut short; anywhere else a bad line is damage.
    for ln in bad_lines:
        if ln == last_line:
            warnings.append(f"line {ln}: cut-short last line, ignored")
        else:
            problems.append(f"line {ln}: not a JSON object")
    if pending_reconcile is not None:
        warnings.append(f"line {pending_reconcile}: the trace ends between a Reconcile and its result")
    if in_steering is not None:
        warnings.append(f"line {in_steering}: the trace ends inside a steering OnSnapshot")
    if lines == 0:
        problems.append(f"{FILE_NAME} is empty")
    elif frames == 0:
        problems.append("no frame markers: the frame boundaries and Advance deltas cannot be checked")
    if calls == 0 and lines:
        problems.append("no traced calls (the predictor sink was never attached?)")

    summary = (util.read_json(client_dir / "summary.json", default=None) or {}).get("trace") or {}
    if summary.get("enabled"):
        for key, have in (("events", calls), ("frames", frames)):
            if summary.get(key) is not None and int(summary[key]) != have:
                warnings.append(f"summary.json trace.{key} {summary[key]} but the file holds {have}")
        for key, what in (("predictor_attached", "predictor"), ("steering_attached", "steering")):
            if summary.get(key) is False:
                warnings.append(f"summary.json: the {what} sink never attached (its calls are missing)")

    out["counts"] = {"lines": lines, "frames": frames, "calls": calls, "calls_before_first_frame": before_first_frame,
                     "reconciles": by_call.get("Reconcile", 0), "results": by_call.get("ReconcileResult", 0),
                     "corrections": len(corrections), "by_call": dict(sorted(by_call.items()))}
    windows = []
    for k, s in enumerate(stalls):
        nxt = stalls[k + 1]["start"] if k + 1 < len(stalls) else float("inf")
        windows.append((s["start"], min(s["start"] + local_window_s, nxt)))
    used = set()
    for s, (lo, hi) in zip(stalls, windows):
        inside = [c for c in corrections if c["t"] is not None and lo <= c["t"] < hi]
        used.update(id(c) for c in inside)
        out["stalls"].append({
            "start": s["start"], "end": s["end"], "ms": s["ms"],
            "st": round(s["start"] - off, 4) if off is not None else None, "window_end": hi,
            "count": len(inside), "snaps": sum(1 for c in inside if c["snap"]),
            "max": max((c["correction"] for c in inside), default=0.0),
            "corrections": inside[:max_listed]})
    rest = [c for c in corrections if id(c) not in used]
    out["outside_stalls"] = {"count": len(rest), "snaps": sum(1 for c in rest if c["snap"]),
                             "max": max((c["correction"] for c in rest), default=0.0), "corrections": rest[:max_listed]}
    if not stalls:
        warnings.append("no scripted stall in events.ndjson: every correction is listed outside stalls")
    out["valid"] = not problems
    return out


def render(doc: dict) -> str:
    """A short text report of summarise()'s result."""
    h = doc.get("header") or {}
    c = doc.get("counts") or {}
    lines = [f"{doc['file']}: {'VALID' if doc['valid'] else 'INVALID'}"]
    if h:
        lines.append(f"  header: map {h.get('map')}, tick_rate {h.get('tick_rate')}, speed {h.get('speed')}, "
                     f"bounds {h.get('bounds')}, motor_3d {h.get('motor_3d')}")
    for s in doc.get("sessions") or []:
        lines.append(f"  session: map {s.get('map')}, protocol {s.get('protocol')}, server_tick_rate "
                     f"{s.get('server_tick_rate')}, predictor_tick_rate {s.get('predictor_tick_rate')}, "
                     f"motor_3d {s.get('motor_3d')}")
    if c:
        lines.append(f"  {c['lines']} lines, {c['frames']} frames, {c['calls']} calls "
                     f"({c['reconciles']} reconciles, {c['results']} results), {c['corrections']} corrections "
                     f">= {doc['min_correction']} u or snaps")
    for p in doc["problems"]:
        lines.append(f"  PROBLEM: {p}")
    for w in doc["warnings"]:
        lines.append(f"  warning: {w}")

    def corr(x):
        return (f"      frame {x['frame']} st {x['st']} correction {x['correction']}"
                f"{' SNAP' if x['snap'] else ''} tick_error {x['tick_error']} stall_resyncs {x['stall_resyncs']}")

    for s in doc.get("stalls") or []:
        lines.append(f"  stall {s['ms']} ms at st {s['st']}: {s['count']} correction(s), {s['snaps']} snap(s), "
                     f"max {s['max']} (window {doc['local_window_s']} s)")
        lines += [corr(x) for x in s["corrections"]]
    o = doc.get("outside_stalls") or {}
    if o:
        lines.append(f"  outside stalls: {o['count']} correction(s), {o['snaps']} snap(s), max {o['max']}")
        lines += [corr(x) for x in o["corrections"]]
    return "\n".join(lines)
