"""Per-frame GC / main-thread / memory columns of a client's frames.csv (client TestLab, UCF F-21).

frames.csv is `frame,t,dt_ms,scenario_t` in older runs and gains `gc_alloc_b,gc_count,main_ms,used_mb`
(appended, by name) in newer ones. Everything here is tolerant: a run without the columns yields no result
and the analysis of that run is unchanged. Nothing in this module grades anything; it never changes a
verdict or a threshold.

`gc_count` is cumulative `GC.CollectionCount(0)`; a step between two rows is a gen0 collection in that frame.
A stall frame "coincided with a GC" when a collection happened in the frame itself or the one before it.
"""
from __future__ import annotations

from array import array
from pathlib import Path

NEW_COLUMNS = ("gc_alloc_b", "gc_count", "main_ms", "used_mb")
# Same size as analyze.host_stalls' default: a frame this long is a stall worth attributing.
STALL_MS = 250.0
MAX_STALLS = 20


def _num(text):
    if text is None or text in ("", "null"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cell(parts, i):
    return _num(parts[i]) if i is not None and i < len(parts) else None


def _pct(sorted_vals, q: float):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def read_client(path: Path) -> dict | None:
    """Summary of one frames.csv, or None when the file is missing or has none of the new columns."""
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return None
    with fh:
        header = (fh.readline() or "").strip().split(",")
        if "gc_alloc_b" not in header and "gc_count" not in header:
            return None
        col = {name: i for i, name in enumerate(header)}
        i_dt, i_st = col.get("dt_ms"), col.get("scenario_t")
        if i_dt is None or i_st is None:
            return None
        i_alloc, i_cnt, i_main = col.get("gc_alloc_b"), col.get("gc_count"), col.get("main_ms")
        alloc = array("d")
        stalls, collections = [], 0
        prev_cnt, prev_delta = None, 0
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) <= max(i_dt, i_st):
                continue
            st, dt = _num(parts[i_st]), _num(parts[i_dt])
            cnt = _cell(parts, i_cnt)
            delta = 0
            if cnt is not None:
                if prev_cnt is not None and cnt > prev_cnt:
                    delta = int(cnt - prev_cnt)
                prev_cnt = cnt
            before, prev_delta = prev_delta, delta
            if st is None or dt is None or st < 0:
                continue
            collections += delta
            a = _cell(parts, i_alloc)
            if a is not None:
                alloc.append(a)
            if dt >= STALL_MS and len(stalls) < MAX_STALLS:
                stalls.append({"st": round(st, 2), "dt_ms": round(dt, 1), "gc_alloc_b": None if a is None else int(a),
                               "main_ms": _cell(parts, i_main), "gc_collections": delta + before,
                               "gc_known": cnt is not None})
    s = sorted(alloc)
    return {"frames_with_alloc": len(s),
            "gc_alloc_b": {"p50": _pct(s, 0.50), "p95": _pct(s, 0.95), "max": s[-1] if s else None},
            "gc_collections": collections, "stall_frames": stalls,
            "stalls_with_gc": sum(1 for x in stalls if x["gc_collections"] > 0)}


def summarize(ev: dict) -> dict | None:
    """{client_index: read_client(...)} for clients that have the columns, or None when no client does."""
    out = {}
    for c in ev.get("clients") or []:
        r = read_client(Path(c["dir"]) / "frames.csv")
        if r is not None:
            out[c["index"]] = r
    return out or None


def stall_note(ev: dict, near_st: float | None = None, window_s: float = 1.0) -> str | None:
    """A sentence for a failure summary when a stall frame coincided with a gen0 GC collection, else None.
    With near_st only stall frames within window_s of that scenario time count (the earliest event)."""
    summary = summarize(ev)
    if not summary:
        return None
    hits = [(idx, x) for idx, r in sorted(summary.items()) for x in r["stall_frames"]
            if x["gc_collections"] > 0 and (near_st is None or abs(x["st"] - near_st) <= window_s)]
    if not hits:
        return None
    idx, x = hits[0]
    return (f"stall frame coincided with gen0 GC: client {idx} frame of {x['dt_ms']} ms at scenario {x['st']} s "
            f"saw {x['gc_collections']} collection(s)"
            + (f", {x['gc_alloc_b']} bytes allocated" if x["gc_alloc_b"] is not None else "")
            + (f" ({len(hits)} such frames in all)" if len(hits) > 1 else ""))


def markdown(summary: dict) -> list[str]:
    """The report.md section "Frame budget" (lines, without a trailing blank line)."""
    def fmt(v):
        return "-" if v is None else str(int(v))

    lines = ["## Frame budget", "",
             f"GC allocation per frame and stall frames (>= {int(STALL_MS)} ms) against gen0 collections, "
             "from the appended `frames.csv` columns.", "",
             "| client | frames | GC alloc p50 / p95 / max (B) | gen0 collections | stall frames | stalls with a GC |",
             "|---|---|---|---|---|---|"]
    for idx, r in sorted(summary.items()):
        g = r["gc_alloc_b"]
        lines.append(f"| {idx} | {r['frames_with_alloc']} | {fmt(g['p50'])} / {fmt(g['p95'])} / {fmt(g['max'])} | "
                     f"{r['gc_collections']} | {len(r['stall_frames'])} | {r['stalls_with_gc']} |")
    shown = [(i, x) for i, r in sorted(summary.items()) for x in r["stall_frames"]]
    if shown:
        lines += ["", "| client | scenario s | frame ms | main thread ms | GC alloc B | gen0 collections (frame + previous) |",
                  "|---|---|---|---|---|---|"]
        for i, x in shown[:MAX_STALLS]:
            lines.append(f"| {i} | {x['st']} | {x['dt_ms']} | {'-' if x['main_ms'] is None else x['main_ms']} | "
                         f"{fmt(x['gc_alloc_b'])} | {x['gc_collections'] if x['gc_known'] else '-'} |")
    return lines
