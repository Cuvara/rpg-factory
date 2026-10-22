"""Snapshot delivery-path analysis (rpg-mmo-server#473): where a late snapshot lost its time.

Inputs (both optional; whatever is absent makes the answers that need it UNKNOWN, never PASS):
- C1, the server trace `server/snapshot-trace.csv` (GAMESERVER_SNAPSHOT_TRACE). One row per
  snapshot written to one connection:
  `conn_id,user_id,world_tick,gather_us,enqueue_us,write_start_us,write_end_us,bytes,queue_depth,
  dropped_oldest_total,kcp_wait_snd,kcp_snd_wnd,kcp_rmt_wnd,kcp_retrans_total,kcp_rto_ms`.
  `*_us` are monotonic microseconds since server start; -1 means not available.
- C2, the client trace in `client-N/` (TestLab `DeliveryRecorder`; empty field = unknown):
  `delivery.csv` `world_tick,recv_us,applied_us,bytes,full,entities,frame`, one row per received
  snapshot (`recv_us`: when its frame left the transport; `applied_us`: when it was merged; both
  LabClock microseconds since player start, on the same axis as the `t` columns), and `render.csv`
  `frame,t_us,render_tick,clock_newest_tick,newest_tick,newest_recv_us,snapshot_age_ms` (schema
  rpg.testlab.delivery.v1) plus `clock_source` (v2), one row per rendered frame; columns are read by
  header name, so both schemas parse. v1 players left render_tick empty (no clock was readable). Recorders that predate C2 write only snapshots.ndjson `t` (main-thread
  receive time, seconds since player start) and frames.csv `frame,t,dt_ms,scenario_t`. The receive
  time then falls back to `applied_us` or `t`, and the answers that need a true receive time
  (PATH) are UNKNOWN.

Server and client are joined on (user_id, world_tick). The two clocks differ in offset AND rate: the
server runs in the WSL VM, whose monotonic clock was measured 7.3 percent slow against Windows
(.testlab-runs/t06/clock-drift-check.txt: WSL uptime / Windows elapsed = 0.927). So per client the
harness fits recv = a + rate x write_end through the least-delayed snapshot of each time bin (the
floor of the delay, where queueing is smallest; fit_clock). With a good fit, one-way delay is the
residual above that line (offset and rate removed), and every server-side duration a class rule
compares with a client gap (write gap, queue delay) is converted to client time by `rate`. With a
poor or impossible fit, one-way delay is reported as unavailable, never as a number, and server
durations are compared uncorrected (flagged in the output).

Every client receive gap longer than `gap_ms` is classified, first match wins:
- QUEUE: the snapshot waited in the server's send queue (enqueue -> write_start) for at least
  `explain_fraction` of the gap.
- SERVER_LATE: the server's own write gap between the two snapshots is that large (the tick or the
  gather produced them late, not the queue).
- CLIENT: a client frame stall of that size overlaps the gap (the client was not reading). Checked
  before KCP because a client that stops reading also fills the server's KCP send window.
- KCP: written on time, but kcp_wait_snd grew or kcp_retrans_total rose over the gap.
- PATH: written on time, no KCP sign, client not stalled: the network or the host's UDP path held
  it. Needs a true receive time (C2 recv_us).
- UNKNOWN: the evidence for the class is missing (no server trace, tick not in the trace, -1
  fields, no C2 receive time).
Each gap is also ALL-CLIENTS when every other client with snapshots over the same ticks had a gap
over them too, SINGLE-CLIENT when another client received those ticks without one, and UNKNOWN when
there is no other client to compare with.
"""

from __future__ import annotations

import csv
from bisect import bisect_right
from pathlib import Path

from . import util

SCHEMA = "rpg.testlab.delivery.v1"
TRACE_FILE = "snapshot-trace.csv"
C1_COLUMNS = ("conn_id", "user_id", "world_tick", "gather_us", "enqueue_us", "write_start_us", "write_end_us",
              "bytes", "queue_depth", "dropped_oldest_total", "kcp_wait_snd", "kcp_snd_wnd", "kcp_rmt_wnd",
              "kcp_retrans_total", "kcp_rto_ms")
CLASSES = ("SERVER_LATE", "QUEUE", "KCP", "PATH", "CLIENT", "UNKNOWN")
SCOPES = ("ALL-CLIENTS", "SINGLE-CLIENT", "UNKNOWN")


# --------------------------------------------------------------------------- parsing

def _int(v):
    """Integer field; None for absent, empty, unparsable or -1 (the contract's 'not available')."""
    if v is None:
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return None if n == -1 else n


def read_server_trace(path: Path) -> dict | None:
    """{user_id: {world_tick: row}}, or None when the file does not exist. Unknown columns are kept
    out, absent ones read as None; rows without a user or a tick are dropped."""
    try:
        fh = open(path, encoding="utf-8", newline="")
    except OSError:
        return None
    by_user: dict = {}
    with fh:
        for raw in csv.DictReader(fh):
            uid = (raw.get("user_id") or "").strip()
            tick = _int(raw.get("world_tick"))
            if not uid or tick is None:
                continue
            row = {k: _int(raw.get(k)) for k in C1_COLUMNS if k not in ("user_id", "conn_id")}
            row["conn_id"] = (raw.get("conn_id") or "").strip()
            by_user.setdefault(uid, {})[tick] = row
    return by_user


def _csv_rows(path: Path) -> list | None:
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return None


def _opt(v):
    """C2 optional field: empty or negative is unknown (None)."""
    n = _int(v)
    return None if n is None or n < 0 else n


def client_snapshots(client_dir: Path) -> tuple[list, str]:
    """[(tick, recv_us, applied_us, bytes)] in receive order, and the source of the receive time:
    'recv_us' (C2, every row has it), 'applied_us' (C2 without the transport tap), or 't'
    (pre-C2 snapshots.ndjson, main-thread receive time)."""
    rows = _csv_rows(client_dir / "delivery.csv")
    if rows:
        parsed = [(_int(r.get("world_tick")), _opt(r.get("recv_us")), _opt(r.get("applied_us")), _opt(r.get("bytes")))
                  for r in rows]
        parsed = [p for p in parsed if p[0] is not None]
        if parsed and all(p[1] is not None for p in parsed):
            return [(t, rv, ap, b) for t, rv, ap, b in parsed], "recv_us"
        with_applied = [(t, ap, ap, b) for t, rv, ap, b in parsed if ap is not None]
        if with_applied:
            return with_applied, "applied_us"
    out = []
    for r in util.read_ndjson(client_dir / "snapshots.ndjson"):
        tick = r.get("world_tick", r.get("tick"))
        if tick is None or r.get("t") is None:
            continue
        out.append((int(tick), int(round(float(r["t"]) * 1e6)), None, None))
    return out, "t"


def read_frames(client_dir: Path) -> tuple[list, list]:
    """(frames, render): frames = [(start_us, end_us, dt_ms)] of every frame on the player clock
    (frames.csv, else consecutive render.csv t_us); render = C2 render.csv rows that carry a
    snapshot age: [(t_us, snapshot_age_ms, render_tick, newest_tick)]."""
    frames = []
    for raw in _csv_rows(client_dir / "frames.csv") or []:
        try:
            t, dt = float(raw["t"]), float(raw["dt_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        end = int(round(t * 1e6))
        frames.append((end - int(round(dt * 1000)), end, dt))
    render, prev = [], None
    from_render = not frames
    for raw in _csv_rows(client_dir / "render.csv") or []:
        t_us = _opt(raw.get("t_us"))
        if t_us is None:
            continue
        if from_render and prev is not None:
            frames.append((prev, t_us, (t_us - prev) / 1000.0))
        prev = t_us
        try:
            age = float(raw["snapshot_age_ms"]) if raw.get("snapshot_age_ms") not in (None, "") else None
        except ValueError:
            age = None
        if age is not None:
            rt = raw.get("render_tick")
            render.append((t_us, age, float(rt) if rt not in (None, "") else None, _opt(raw.get("newest_tick"))))
    return frames, render


# --------------------------------------------------------------------------- statistics

def _stats(values) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "p50": None, "p99": None, "max": None}
    return {"n": len(vals), "p50": round(util.percentile(vals, 50), 3), "p99": round(util.percentile(vals, 99), 3),
            "max": round(max(vals), 3)}


def _delta(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return (vals[-1] - vals[0]) if len(vals) >= 2 else None


def _overlaps(stalls, lo, hi, min_ms, slack_us):
    """Largest frame stall >= min_ms overlapping [lo, hi] (player clock, widened by slack)."""
    best = None
    for s0, s1, dt in stalls:
        if dt >= min_ms and s0 - slack_us <= hi and lo <= s1 + slack_us:
            best = dt if best is None or dt > best else best
    return best


# --------------------------------------------------------------------------- classification

def fit_clock(pairs: list, *, min_points: int = 5, bin_us: int = 1_000_000, tolerance_us: int = 50_000) -> dict:
    """Clock relation between the server (x: write time, server us) and one client (y: receive time,
    client us) from matched snapshots: least squares through the minimum-delay pair of each bin of
    `bin_us` server time (bin width grows so there are at most 60 bins). ok only with at least
    `min_points` bins and the 90th percentile of their residuals within `tolerance_us`."""
    if len(pairs) < min_points * 2:
        return {"ok": False, "reason": f"{len(pairs)} matched snapshots (need {min_points * 2})"}
    pairs = sorted(pairs)
    x0, span = pairs[0][0], pairs[-1][0] - pairs[0][0]
    width = max(bin_us, span // 60 + 1)
    best: dict = {}
    for x, y in pairs:
        k = (x - x0) // width
        if k not in best or y - x < best[k][1] - best[k][0]:
            best[k] = (x, y)
    pts = list(best.values())
    if len(pts) < min_points:
        return {"ok": False, "reason": f"{len(pts)} time bins of {width / 1e6:.1f} s (need {min_points})"}
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den == 0:
        return {"ok": False, "reason": "no spread in server time"}
    rate = sum((p[0] - mx) * (p[1] - my) for p in pts) / den
    offset = my - rate * mx
    res = sorted(abs(p[1] - (offset + rate * p[0])) for p in pts)
    p90 = res[min(len(res) - 1, int(0.9 * len(res)))]
    out = {"rate": rate, "skew_pct": round((rate - 1) * 100, 3), "offset_us": offset, "bins": n,
           "bin_s": round(width / 1e6, 2), "residual_p90_ms": round(p90 / 1000, 2)}
    if p90 > tolerance_us:
        return {**out, "ok": False, "reason": f"poor fit: residual p90 {p90 / 1000:.1f} ms > {tolerance_us / 1000:.0f} ms"}
    return {**out, "ok": True}


def classify_gap(gap: dict, srv: dict | None, stalls: list, recv_source: str, *, explain_fraction: float,
                 slack_us: int, rate: float = 1.0, srv_ticks: list | None = None,
                 after_rows: int = 4) -> tuple[str, str, dict]:
    """(class, reason, evidence) for one client receive gap between ticks a and b. `rate` converts
    server durations to client time (fit_clock); 1.0 when no fit is available."""
    a, b, gap_us = gap["tick_a"], gap["tick_b"], gap["gap_us"]
    large = explain_fraction * gap_us
    ev: dict = {}
    if srv is None:
        server = None
        reason_srv = "no server trace (C1) for this client"
    else:
        server = (srv.get(a), srv.get(b))
        reason_srv = None if all(server) else f"tick {a if server[0] is None else b} not in the server trace"
    queue_delay = write_gap = None
    ra = rb = None
    if server and all(server):
        ra, rb = server
        between = [r for t, r in srv.items() if a < t <= b]
        # KCP signs can land just after the late snapshot: a retransmission burst or a full send
        # window is written in the rows that follow tick b. Look `after_rows` server rows further.
        ticks = srv_ticks if srv_ticks is not None else sorted(srv)
        j = bisect_right(ticks, b)
        after = [srv[t] for t in ticks[j:j + after_rows]]
        kcp_rows = between + after
        delays = [(r["write_start_us"] - r["enqueue_us"]) * rate for r in between
                  if r.get("write_start_us") is not None and r.get("enqueue_us") is not None]
        queue_delay = max(delays) if delays else None
        if ra.get("write_start_us") is not None and rb.get("write_start_us") is not None:
            write_gap = (rb["write_start_us"] - ra["write_start_us"]) * rate
        ev.update({"server_write_gap_ms": None if write_gap is None else round(write_gap / 1000, 1),
                   "queue_delay_ms": None if queue_delay is None else round(queue_delay / 1000, 1),
                   "server_rows_between": len(between),
                   "queue_depth_b": rb.get("queue_depth"),
                   "dropped_delta": _sub(rb.get("dropped_oldest_total"), ra.get("dropped_oldest_total")),
                   "retrans_delta": _sub(max((r["kcp_retrans_total"] for r in kcp_rows
                                              if r.get("kcp_retrans_total") is not None), default=None),
                                         ra.get("kcp_retrans_total")),
                   "wait_snd_a": ra.get("kcp_wait_snd"),
                   "wait_snd_max": max((r["kcp_wait_snd"] for r in kcp_rows if r.get("kcp_wait_snd") is not None),
                                       default=None),
                   "kcp_rows_after_b": len(after)})
        if queue_delay is not None and queue_delay >= large:
            return "QUEUE", "the snapshot waited in the server send queue for most of the gap", ev
        if write_gap is not None and write_gap >= large:
            return "SERVER_LATE", "the server itself wrote the two snapshots this far apart", ev
    stall = _overlaps(stalls, gap["recv_a_us"], gap["recv_b_us"], large / 1000.0, slack_us)
    ev["client_stall_ms"] = None if stall is None else round(stall, 1)
    if stall is not None:
        return "CLIENT", "a client frame stall overlaps the gap", ev
    if reason_srv:
        return "UNKNOWN", reason_srv, ev
    if write_gap is None:
        return "UNKNOWN", "write_start_us not available in the server trace", ev
    retrans, wait_max, wait_a = ev.get("retrans_delta"), ev.get("wait_snd_max"), ev.get("wait_snd_a")
    if retrans is None and wait_max is None:
        return "UNKNOWN", "server wrote on time; KCP fields not available to tell KCP from PATH", ev
    if (retrans or 0) > 0 or (wait_max is not None and wait_a is not None and wait_max > wait_a):
        return "KCP", "written on time, KCP held it (send queue grew or segments were retransmitted)", ev
    if recv_source != "recv_us":
        return "UNKNOWN", "server wrote on time; PATH needs the client's receive time (C2 recv_us)", ev
    return "PATH", "written on time, no KCP sign, client not stalled: received late", ev


def _sub(x, y):
    return None if x is None or y is None else x - y


# --------------------------------------------------------------------------- analysis

def analyze(run_dir: Path, *, gap_ms: float = 250.0, bucket_s: float = 300.0, tick_hz: float | None = None,
            explain_fraction: float = 0.5, slack_ms: float = 50.0) -> dict:
    run_dir = Path(run_dir)
    meta = util.read_json(run_dir / "run.json", default={}) or {}
    sc = util.read_json(run_dir / "scenario.json", default={}) or {}
    trace_path = run_dir / "server" / TRACE_FILE
    trace = read_server_trace(trace_path)
    if tick_hz is None:
        status = util.read_ndjson(run_dir / "server" / "status.ndjson")
        tick_hz = float(next((s.get("sim_critical_hz") for s in reversed(status) if s.get("sim_critical_hz")), 60.0))
    bucket_ticks = bucket_s * tick_hz
    slack_us = int(slack_ms * 1000)

    clients = []
    for i in range(int(sc.get("clients", 0))):
        d = run_dir / f"client-{i}"
        summary = util.read_json(d / "summary.json", default=None) or {}
        status = util.read_json(d / "status.json", default={}) or {}
        snaps, source = client_snapshots(d)
        stalls, render = read_frames(d)
        clients.append({"index": i, "user_id": summary.get("user_id") or status.get("user_id"), "snaps": snaps,
                        "recv_source": source, "stalls": stalls, "render": render})
    all_ticks = [s[0] for c in clients for s in c["snaps"]]
    tick0 = min(all_ticks) if all_ticks else 0

    def bucket_of(tick):
        return int((tick - tick0) // bucket_ticks) if tick >= tick0 else 0

    # Gaps per client.
    for c in clients:
        gaps = []
        for (ta, ra, _, _), (tb, rb, _, _) in zip(c["snaps"], c["snaps"][1:]):
            gaps.append({"tick_a": ta, "tick_b": tb, "recv_a_us": ra, "recv_b_us": rb, "gap_us": rb - ra})
        c["gaps"] = gaps
        c["long"] = [g for g in gaps if g["gap_us"] > gap_ms * 1000]

    # Clock fits first: the scope of a gap compares clients on the server clock.
    for c in clients:
        srv = (trace or {}).get(c["user_id"]) if (trace is not None and c["user_id"]) else None
        c["clock"] = fit_clock(_matched(c, srv)) if srv else {"ok": False, "reason": "no server trace"}

    out_clients = {}
    totals = {k: 0 for k in CLASSES}
    scopes = {k: 0 for k in SCOPES}
    for c in clients:
        srv = (trace or {}).get(c["user_id"]) if (trace is not None and c["user_id"]) else None
        clock = c["clock"]
        rate = clock["rate"] if clock["ok"] else 1.0
        srv_ticks = sorted(srv) if srv else None
        classified = []
        for g in c["long"]:
            cls, why, evd = classify_gap(g, srv, c["stalls"], c["recv_source"],
                                         explain_fraction=explain_fraction, slack_us=slack_us, rate=rate,
                                         srv_ticks=srv_ticks)
            scope = _scope(g, c, clients, gap_ms, slack_us)
            totals[cls] += 1
            scopes[scope] += 1
            classified.append({"tick_a": g["tick_a"], "tick_b": g["tick_b"], "gap_ms": round(g["gap_us"] / 1000, 1),
                               "bucket": bucket_of(g["tick_a"]), "class": cls, "scope": scope, "reason": why,
                               "evidence": evd})
        out_clients[str(c["index"])] = {
            "user_id": c["user_id"], "snapshots": len(c["snaps"]), "recv_source": c["recv_source"],
            "server_rows": len(srv) if srv else 0, "frames": len(c["stalls"]), "render_rows": len(c["render"]),
            "clock_fit": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in clock.items()},
            "server_durations": "client time (rate-corrected)" if clock["ok"] else "server time (no clock fit)",
            "one_way_delay": "available" if clock["ok"] else f"unavailable: {clock['reason']}",
            "buckets": _buckets(c, srv, bucket_of, gap_ms, clock),
            "long_gaps": len(classified),
            "classes": {k: sum(1 for g in classified if g["class"] == k) for k in CLASSES},
            "scopes": {k: sum(1 for g in classified if g["scope"] == k) for k in SCOPES},
            "gaps": classified[:500],
        }

    inputs = {
        "server_trace": str(trace_path) if trace is not None else None,
        "server_trace_users": len(trace or {}),
        "c2_recv_us": all(c["recv_source"] == "recv_us" for c in clients) if clients else False,
        "c2_render": all(c["render"] for c in clients) if clients else False,
        "tick_hz": tick_hz, "bucket_s": bucket_s, "gap_ms": gap_ms, "explain_fraction": explain_fraction,
    }
    missing = []
    if trace is None:
        missing.append("server trace (C1) server/snapshot-trace.csv: SERVER_LATE, QUEUE and KCP cannot be decided")
    if not inputs["c2_recv_us"]:
        missing.append("client recv_us (C2 delivery.csv) for every snapshot: receive time falls back to "
                       "applied_us or the main-thread 't'; PATH cannot be decided")
    if not inputs["c2_render"]:
        missing.append("client render.csv snapshot_age_ms (C2): render age not reported")
    if not clients or not all_ticks:
        missing.append("no client snapshots")
    # Diagnostic, never a verdict: COMPLETE when every input is present, else INCOMPLETE.
    return {"schema": SCHEMA, "run_id": meta.get("run_id"), "run_dir": str(run_dir),
            "scenario": {"id": sc.get("id"), "version": sc.get("version")},
            "completeness": "COMPLETE" if not missing else "INCOMPLETE", "missing": missing, "inputs": inputs,
            "classes": totals, "scopes": scopes, "clients": out_clients}


def _to_server_us(clock, recv_us):
    return (recv_us - clock["offset_us"]) / clock["rate"]


def _scope(g, c, clients, gap_ms, slack_us=50_000):
    """ALL-CLIENTS when every other client that received snapshots across these ticks had a long gap
    at the same time; SINGLE-CLIENT when one of them did not. "Same time": the two receive windows
    overlap on the server clock (both clients' clock fits mapped, widened by slack_us), or their tick
    ranges overlap or touch - one host freeze can leave one client's gap at 182061-182065 and
    another's at 182065-182069 (T06, run 20261022T163744Z-S09-sfj5 s 3269)."""
    others = [o for o in clients if o is not c and o["snaps"]
              and o["snaps"][0][0] <= g["tick_a"] and o["snaps"][-1][0] >= g["tick_b"]]
    if not others:
        return "UNKNOWN"
    mine = c.get("clock") or {}
    window = ((_to_server_us(mine, g["recv_a_us"]), _to_server_us(mine, g["recv_b_us"]))
              if mine.get("ok") else None)
    for o in others:
        theirs = o.get("clock") or {}

        def same(og):
            if og["tick_a"] <= g["tick_b"] and g["tick_a"] <= og["tick_b"]:
                return True
            if window is None or not theirs.get("ok"):
                return False
            o0, o1 = _to_server_us(theirs, og["recv_a_us"]), _to_server_us(theirs, og["recv_b_us"])
            return o0 - slack_us <= window[1] and window[0] <= o1 + slack_us

        if not any(same(og) for og in o["long"]):
            return "SINGLE-CLIENT"
    return "ALL-CLIENTS"


def _matched(c, srv):
    """[(server write_end_us, client recv_us)] for the snapshots both sides recorded."""
    out = []
    for tick, recv, _, _ in c["snaps"]:
        r = (srv or {}).get(tick)
        sent = r and (r.get("write_end_us") if r.get("write_end_us") is not None else r.get("write_start_us"))
        if sent is not None:
            out.append((sent, recv))
    return out


def _buckets(c, srv, bucket_of, gap_ms, clock=None):
    clock = clock or {"ok": False}
    rate = clock["rate"] if clock.get("ok") else 1.0
    by: dict = {}
    for g in c["gaps"]:
        by.setdefault(bucket_of(g["tick_a"]), {"recv_gaps": [], "send_gaps": [], "owd": [], "rows": []})["recv_gaps"].append(
            g["gap_us"] / 1000.0)
    one_way = []
    if srv:
        rows = sorted(srv.items())
        for (ta, ra), (tb, rb) in zip(rows, rows[1:]):
            if ra.get("write_start_us") is not None and rb.get("write_start_us") is not None:
                by.setdefault(bucket_of(tb), {"recv_gaps": [], "send_gaps": [], "owd": [], "rows": []})["send_gaps"].append(
                    (rb["write_start_us"] - ra["write_start_us"]) * rate / 1000.0)
        for t, r in rows:
            by.setdefault(bucket_of(t), {"recv_gaps": [], "send_gaps": [], "owd": [], "rows": []})["rows"].append(r)
        if clock.get("ok"):
            # Residual above the fitted clock line: offset and rate removed (fit_clock).
            for tick, recv, _, _ in c["snaps"]:
                r = srv.get(tick)
                sent = r and (r.get("write_end_us") if r.get("write_end_us") is not None else r.get("write_start_us"))
                if sent is not None:
                    one_way.append((tick, recv - (clock["offset_us"] + clock["rate"] * sent)))
    for _, age, _, newest in c["render"]:
        if newest is not None:
            by.setdefault(bucket_of(newest), {"recv_gaps": [], "send_gaps": [], "owd": [], "rows": []}).setdefault(
                "ages", []).append(age)
    base = min((d for _, d in one_way), default=None)
    for tick, d in one_way:
        by.setdefault(bucket_of(tick), {"recv_gaps": [], "send_gaps": [], "owd": [], "rows": []})["owd"].append(
            (d - base) / 1000.0)
    out = []
    for k in sorted(by):
        b = by[k]
        rows = b["rows"]
        out.append({
            "bucket": k,
            "client_recv_gap_ms": _stats(b["recv_gaps"]),
            "client_gaps_over_limit": sum(1 for x in b["recv_gaps"] if x > gap_ms),
            "server_send_gap_ms": _stats(b["send_gaps"]),
            "one_way_rel_ms": _stats(b["owd"]),
            "queue_depth": _stats([r.get("queue_depth") for r in rows]),
            "queue_delay_ms": _stats([(r["write_start_us"] - r["enqueue_us"]) * rate / 1000.0 for r in rows
                                      if r.get("write_start_us") is not None and r.get("enqueue_us") is not None]),
            "dropped_delta": _delta(rows, "dropped_oldest_total"),
            "kcp_retrans_delta": _delta(rows, "kcp_retrans_total"),
            "kcp_wait_snd": _stats([r.get("kcp_wait_snd") for r in rows]),
            "snapshot_age_ms": _stats(b.get("ages", [])),
        })
    return out


# --------------------------------------------------------------------------- report

def markdown(doc: dict) -> str:
    lines = [f"# Snapshot delivery analysis - run {doc.get('run_id')}", "",
             f"Scenario `{doc['scenario'].get('id')}` v{doc['scenario'].get('version')}. "
             f"Inputs: **{doc['completeness']}**. Diagnostic only: this analysis never grades a run PASS.", ""]
    for m in doc["missing"]:
        lines.append(f"- missing: {m}")
    inp = doc["inputs"]
    lines += ["", f"Gap limit {inp['gap_ms']} ms, buckets of {inp['bucket_s']} s ({inp['tick_hz']} Hz ticks), "
              f"a cause explains a gap at >= {inp['explain_fraction']:.0%} of it.", "",
              "## Long gaps by class", "", "| Class | Gaps |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in doc["classes"].items()]
    lines += ["", "| Scope | Gaps |", "|---|---|"] + [f"| {k} | {v} |" for k, v in doc["scopes"].items()]
    for idx, c in doc["clients"].items():
        lines += ["", f"## Client {idx} (`{c['user_id']}`)", "",
                  f"{c['snapshots']} snapshots (receive time from `{c['recv_source']}`), {c['server_rows']} server rows, "
                  f"{c['long_gaps']} gaps over the limit.", "",
                  f"Clock fit (server write -> client receive): {_fit_text(c.get('clock_fit') or {})}. "
                  f"One-way delay {c.get('one_way_delay')}; server durations in {c.get('server_durations')}.", "",
                  "| Bucket | client recv gap p50/p99/max ms | gaps > limit | server send gap p50/p99/max ms | "
                  "one-way rel p50/p99/max ms | queue depth p50/max | queue delay p99 ms | dropped | retrans | wait_snd p50/max | "
                  "render age p50/p99/max ms |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in c["buckets"]:
            lines.append(f"| {b['bucket']} | {_t(b['client_recv_gap_ms'])} | {b['client_gaps_over_limit']} | "
                         f"{_t(b['server_send_gap_ms'])} | {_t(b['one_way_rel_ms'])} | "
                         f"{_v(b['queue_depth']['p50'])}/{_v(b['queue_depth']['max'])} | {_v(b['queue_delay_ms']['p99'])} | "
                         f"{_v(b['dropped_delta'])} | {_v(b['kcp_retrans_delta'])} | "
                         f"{_v(b['kcp_wait_snd']['p50'])}/{_v(b['kcp_wait_snd']['max'])} | {_t(b['snapshot_age_ms'])} |")
        if c["gaps"]:
            lines += ["", "| ticks | gap ms | class | scope | reason |", "|---|---|---|---|---|"]
            for g in sorted(c["gaps"], key=lambda x: -x["gap_ms"])[:20]:
                lines.append(f"| {g['tick_a']}-{g['tick_b']} | {g['gap_ms']} | {g['class']} | {g['scope']} | {g['reason']} |")
    return "\n".join(lines) + "\n"


def _fit_text(fit: dict) -> str:
    if not fit.get("ok"):
        return f"none ({fit.get('reason')})"
    return (f"rate {fit['rate']:.5f} (skew {fit['skew_pct']:+.3f} %), {fit['bins']} bins of {fit['bin_s']} s, "
            f"residual p90 {fit['residual_p90_ms']} ms")


def _v(x):
    return "-" if x is None else str(x)


def _t(s):
    return f"{_v(s['p50'])}/{_v(s['p99'])}/{_v(s['max'])}"


def write(doc: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j, m = out_dir / "delivery.json", out_dir / "delivery.md"
    util.write_json(j, doc)
    with open(m, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(markdown(doc))
    return j, m
