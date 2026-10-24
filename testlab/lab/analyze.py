"""Evidence -> assertions -> PASS / FAIL / INCONCLUSIVE.

Raw observations (what the clients and the server recorded) are loaded once into an evidence
dict; each check is a pure function of that evidence and the assertion's parameters, and returns
what it measured, where the number came from, at what sampling, the threshold and why, the
result and the artifacts to open. Missing required evidence is INCONCLUSIVE, never PASS.

Statuses: PASS, FAIL, INCONCLUSIVE, INFO (reported, never decides the run).
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right
from pathlib import Path

from . import provenance, util

PASS, FAIL, INCONCLUSIVE, INFO = "PASS", "FAIL", "INCONCLUSIVE", "INFO"
# Run outcome only: every assertion passed, but an informational one would have failed (e.g. the
# S07/S07P memory slope). Never a clean PASS; exit code 4.
PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
# A host is reported as loaded at this CPU load (policy, unvalidated; testlab/docs/THRESHOLDS.md).
HOST_LOAD_WARN_PCT = 50.0


# --------------------------------------------------------------------------- evidence loading

def load_evidence(run_dir: Path) -> dict:
    meta = util.read_json(run_dir / "run.json", default={}) or {}
    sc = util.read_json(run_dir / "scenario.json", default={}) or {}
    clients = []
    for i in range(int(sc.get("clients", 0))):
        d = run_dir / f"client-{i}"
        logs = sorted(d.glob("player*.log"))
        clients.append({
            "index": i,
            "dir": d,
            "status": util.read_json(d / "status.json", default={}) or {},
            "summary": util.read_json(d / "summary.json", default=None),
            "summaries": [util.read_json(p, default=None) for p in sorted(d.glob("summary*.json"))],
            # Streamed, never held: a 1 h soak's samples and events are gigabytes as Python objects.
            "events": util.LazyNdjson(d / "events.ndjson"),
            "samples": util.LazyNdjson(d / "samples.ndjson"),
            "snapshots": util.read_ndjson(d / "snapshots.ndjson"),
            "inputs": util.LazyNdjson(d / "inputs.ndjson"),
            "plan": util.read_json(d / "plan.json", default={}) or {},
            "logs": {p.name: p.read_text(encoding="utf-8", errors="replace") for p in logs},
            "frames": _read_frames(d / "frames.csv"),
            # C2 files are read by the checks that need them (render.csv has a row per frame).
            "delivery_csv": d / "delivery.csv",
            "render_csv": d / "render.csv",
            "history": (meta.get("clients") or {}).get(str(i), {}),
        })
    server_dir = run_dir / "server"
    entities = util.LazyNdjson(server_dir / "entities.ndjson")
    ev = {
        "run_dir": run_dir,
        "meta": meta,
        "scenario": sc,
        "clients": clients,
        "server": {
            "entities": entities,
            # Streamed too: a 1 h soak's status.ndjson is ~30 MB (uc3e), read by a few passes only.
            "status": util.LazyNdjson(server_dir / "status.ndjson"),
            "container": util.read_ndjson(server_dir / "container.ndjson"),
            "metrics_start": parse_prometheus((server_dir / "metrics-start.txt")),
            "metrics_end": parse_prometheus((server_dir / "metrics-end.txt")),
        },
        "redis": util.read_json(run_dir / "redis.json", default={}) or {},
        "bots": util.read_json(run_dir / "bots" / "loadtest.json", default=None),
        # What each scripted disruption did (runner._disrupt): debug_kill HTTP status, outcome, tick.
        "disruptions": util.read_ndjson(run_dir / "disruptions.ndjson"),
        # What the raw-client steps (S16 malformed input, S17 churn) recorded: rawprobe.ndjson.
        "rawprobe": util.read_ndjson(run_dir / "rawprobe.ndjson"),
        # What the packet-impairment step (S18) recorded: netem.ndjson.
        "netem": util.read_ndjson(run_dir / "netem.ndjson"),
    }
    ev["traj"] = trajectories(entities)
    return ev


class FrameSeries:
    """(scenario_t, dt_ms) per frame in two float arrays (16 bytes a frame, not a tuple each)."""

    def __init__(self):
        from array import array
        self.st, self.dt = array("d"), array("d")

    def append(self, item) -> None:
        self.st.append(item[0])
        self.dt.append(item[1])

    def __iter__(self):
        return zip(self.st, self.dt)

    def __len__(self) -> int:
        return len(self.st)

    def __bool__(self) -> bool:
        return len(self.st) > 0


def _read_frames(path: Path) -> "FrameSeries":
    """(scenario_t, dt_ms) for frames inside the scenario window (scenario_t >= 0)."""
    out = FrameSeries()
    try:
        with open(path, encoding="utf-8") as fh:
            next(fh, None)
            for line in fh:
                parts = line.strip().split(",")
                if len(parts) < 4 or parts[3] in ("", "null"):
                    continue
                try:
                    st, dt = float(parts[3]), float(parts[2])
                except ValueError:
                    continue
                if st >= 0:
                    out.append((st, dt))
    except FileNotFoundError:
        pass
    return out


def host_stalls(ev: dict, min_ms: float = 250.0, window_s: float = 0.25) -> list:
    """Frames of >= min_ms that END within window_s of each other in at least two separate client
    processes: the whole host stalled (another process, the OS, I/O), not one client. Returns
    [(start_st, end_st, clients)]."""
    long_frames = []
    for c in ev["clients"]:
        for st, dt in c.get("frames", []):
            if dt >= min_ms:
                long_frames.append((st, dt, c["index"]))
    long_frames.sort()
    stalls = []
    for st, dt, idx in long_frames:
        peers = {i for s2, d2, i in long_frames if abs(s2 - st) <= window_s}
        if len(peers) >= 2:
            stalls.append((st - dt / 1000.0, st, sorted(peers)))
    return stalls


def _in_stall(stalls, t0: float, t1: float, slack: float = 0.3, after: float | None = None) -> bool:
    """Overlap with a host-wide stall, widened by `slack` before it and `after` (default `slack`)
    after it. A stall's consequences land after it ends: inputs that could not be sent past the
    server's silence timeout are reconciled when the next acknowledgements arrive."""
    tail = slack if after is None else after
    return any(a - slack <= t1 and t0 <= b + tail for a, b, _ in stalls)


def parse_prometheus(path: Path) -> dict:
    out = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eEInfNa]+)", line)
        if m:
            try:
                out[m.group(1) + (m.group(2) or "")] = float(m.group(3))
            except ValueError:
                pass
    return out


def trajectories(entities) -> dict:
    """{id: {"type": t, "st": [...], "x": [...], "y": [...], "hp": [...], "max_hp": .., "speed": ..}}
    st, x and y are float arrays (8 bytes a value); one pass over the rows."""
    from array import array
    traj = {}
    for row in entities:
        st = row.get("st")
        if st is None:
            continue
        for e in row["ents"]:
            eid, etype, x, y, hp, max_hp, dead, speed = (e + [None] * 8)[:8]
            t = traj.get(eid)
            if t is None:
                t = traj[eid] = {"type": etype, "st": array("d"), "x": array("d"), "y": array("d"), "hp": [],
                                 "dead": [], "max_hp": max_hp, "speed": speed}
            t["st"].append(st)
            t["x"].append(x)
            t["y"].append(y)
            t["hp"].append(hp)
            t["dead"].append(dead)
    return traj


# --------------------------------------------------------------------------- helpers

def _window(ev: dict) -> tuple[float, float]:
    return 0.0, float(ev["scenario"].get("duration_s", 0))


def _result(status, measured=None, threshold=None, *, source, sampling, rationale="", detail=None, artifacts=None):
    return {"status": status, "measured": measured, "threshold": threshold, "source": source,
            "sampling": sampling, "rationale": rationale, "detail": detail or {}, "artifacts": artifacts or []}


def _inconclusive(why, *, source, sampling="n/a", artifacts=None):
    return _result(INCONCLUSIVE, None, None, source=source, sampling=sampling, detail={"why": why}, artifacts=artifacts)


def _user_ids(ev) -> list:
    """Each client's user id: summary.json, else status.json, else the last `in_world` event, else the
    id the orchestrator saw at join (run.json clients.N.first_user_id). A client that left with the
    quit action writes summary/status AFTER NetworkClient.Disconnect(), when NetworkClient.UserId
    (Netcode Runtime/Client/NetworkClient.cs:215, derived from the released session) is already
    empty - the S08G runs 20261022T194023Z-S08G-zvjy and 20261022T194902Z-S08G-zc4m."""
    ids = []
    clients_meta = (ev.get("meta") or {}).get("clients") or {}
    for c in ev["clients"]:
        uid = (c["summary"] or {}).get("user_id") or c["status"].get("user_id")
        if not uid:
            uid = next((e.get("user_id") for e in reversed(c["events"])
                        if e.get("event") == "in_world" and e.get("user_id")), None)
        if not uid:
            uid = (clients_meta.get(str(c["index"])) or {}).get("first_user_id")
        ids.append(uid or None)
    return ids


def _metric_sum(metrics: dict, name: str, label_filter: str = "") -> float | None:
    vals = [v for k, v in metrics.items() if (k == name or k.startswith(name + "{")) and label_filter in k]
    return sum(vals) if vals else None


def _delta(ev, name, label_filter=""):
    a = _metric_sum(ev["server"]["metrics_start"], name, label_filter)
    b = _metric_sum(ev["server"]["metrics_end"], name, label_filter)
    if a is None or b is None:
        return None
    return b - a


def _status_in_window(ev):
    lo, hi = _window(ev)
    return [s for s in ev["server"]["status"] if s.get("_st") is not None and lo <= s["_st"] <= hi]


def _pos_at(t: dict, st: float):
    """Server position of a trajectory at scenario time st, linearly interpolated; None outside."""
    times = t["st"]
    if not times or st < times[0] or st > times[-1]:
        return None
    i = bisect_left(times, st)
    if i < len(times) and times[i] == st:
        return t["x"][i], t["y"][i]
    a, b = i - 1, i
    if a < 0 or b >= len(times):
        return None
    f = (st - times[a]) / (times[b] - times[a]) if times[b] > times[a] else 0.0
    return t["x"][a] + f * (t["x"][b] - t["x"][a]), t["y"][a] + f * (t["y"][b] - t["y"][a])


def _dist_to_path(t: dict, st_lo: float, st_hi: float, px: float, py: float):
    """Shortest distance from (px, py) to the server's polyline between st_lo and st_hi."""
    times = t["st"]
    i0 = max(0, bisect_left(times, st_lo) - 1)
    i1 = min(len(times), bisect_right(times, st_hi) + 1)
    if i1 - i0 < 1:
        return None
    # Same arithmetic as _seg_dist, inlined over one slice of the trajectory (hot path: once per
    # rendered entity per sample, millions of times on a soak).
    xs, ys = t["x"][i0:i1], t["y"][i0:i1]
    best = None
    hypot = math.hypot
    ax, ay = xs[0], ys[0]
    for k in range(1, len(xs)):
        bx, by = xs[k], ys[k]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L <= 1e-12:
            d = hypot(px - ax, py - ay)
        else:
            f = ((px - ax) * dx + (py - ay) * dy) / L
            f = 0.0 if f < 0.0 else 1.0 if f > 1.0 else f
            d = hypot(px - (ax + f * dx), py - (ay + f * dy))
        if best is None or d < best:
            best = d
        ax, ay = bx, by
    d = hypot(px - ax, py - ay)
    return d if best is None or d < best else best


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L <= 1e-12:
        return math.hypot(px - ax, py - ay)
    f = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + f * dx), py - (ay + f * dy))


def _client_files(c, *names):
    return [str(c["dir"] / n) for n in names]


# --------------------------------------------------------------------------- checks

def check_clients_in_world(ev, a):
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client events.ndjson")
    missing = [c["index"] for c in ev["clients"]
               if not any(e.get("event") == "in_world" for e in c["events"])]
    n = len(ev["clients"])
    detail = {"missing": missing}
    after = a.get("reentered_after_s")
    if after is not None:
        # After a disruption (S11 server restart): each client must be back in the world, i.e. a
        # net_state InWorld event at or after scenario time `after`.
        not_back = [c["index"] for c in ev["clients"]
                    if not any(e.get("event") == "net_state" and e.get("state") == "InWorld"
                               and (e.get("st") if e.get("st") is not None else -1) >= float(after) for e in c["events"])]
        detail["not_back_in_world_after_s"] = {"after_s": float(after), "clients": not_back}
        missing = sorted(set(missing) | set(not_back))
    return _result(PASS if not missing and n else FAIL, n - len(missing), n,
                   source="client events.ndjson 'in_world' / net_state InWorld (NetworkClientState.InWorld)",
                   sampling="per client",
                   rationale="every launched client must complete auth, gateway redirect and KCP join"
                             + (" and re-join after the disruption" if after is not None else ""),
                   detail=detail, artifacts=[str(c["dir"] / "events.ndjson") for c in ev["clients"]])


def check_distinct_user_ids(ev, a):
    ids = _user_ids(ev)
    known = [i for i in ids if i]
    if len(known) < len(ids):
        return _inconclusive(f"user id unknown for {len(ids) - len(known)} client(s)", source="client status/summary")
    if len(known) < 2:
        return _inconclusive(f"{len(known)} client identity(ies): distinctness needs at least two",
                             source="client status/summary")
    ok = len(set(known)) == len(known)
    return _result(PASS if ok else FAIL, len(set(known)), len(known), source="client summary.json user_id (Nakama)",
                   sampling="per client", rationale="a shared identity makes logins evict each other",
                   detail={"user_ids": ids})


def check_same_game_server(ev, a):
    addrs = {}
    for c in ev["clients"]:
        text = "\n".join(c["logs"].values())
        m = re.findall(r"assigned to (\S+)", text)
        addrs[c["index"]] = m[-1] if m else None
    known = {v for v in addrs.values() if v}
    if len(known) == 0 or None in addrs.values():
        return _inconclusive("no 'assigned to <addr>' line in some player log", source="player.log (GatewayClient)")
    return _result(PASS if len(known) == 1 else FAIL, sorted(known), "1 address",
                   source="player.log 'assigned to' (GatewayClient)", sampling="per client",
                   rationale="ADR-2: one live server per map; clients on different servers never see each other",
                   detail={"by_client": addrs})


def check_players_online(ev, a):
    if not ev["clients"] and "expected" not in a:
        return _inconclusive("no clients in this run", source="/status")
    expected = int(a.get("expected", len(ev["clients"]))) + int(a.get("plus_bots", 0) and (ev["scenario"].get("bots") or {}).get("players", 0))
    rows = _status_in_window(ev)
    vals = [r.get("players_online") for r in rows if r.get("players_online") is not None]
    if not vals:
        return _inconclusive("no /status players_online sample inside the scenario window", source="/status")
    mode = a.get("mode", "max")
    measured = max(vals) if mode == "max" else vals[-1]
    return _result(PASS if measured == expected else FAIL, measured, expected,
                   source="gameserver /status players_online", sampling=f"1 Hz, {len(rows)} samples, {mode}",
                   rationale="every client must be a live player on the server",
                   artifacts=[str(ev["run_dir"] / "server" / "status.ndjson")])


def check_redis(ev, a):
    r = ev["redis"]
    if not r or r.get("session_keys") is None:
        return _inconclusive("redis.json missing or without a session count", source="redis (docker exec rpgs-redis)")
    if not ev["clients"] and "sessions" not in a:
        return _inconclusive("no clients in this run", source="redis (docker exec rpgs-redis)")
    sessions = r.get("session_keys")
    members = r.get("map_members") or []
    exp_sessions = int(a.get("sessions", len(ev["clients"])))
    ok = sessions == exp_sessions and len(members) == 1
    return _result(PASS if ok else FAIL, {"session_keys": sessions, "map_members": len(members)},
                   {"session_keys": exp_sessions, "map_members": 1},
                   source="redis SCAN session:* and SMEMBERS servers:map:<map> (taken while clients were in world)",
                   sampling="once, mid-run", rationale="gateway holds one session per user; ADR-2 one server per map",
                   detail=r, artifacts=[str(ev["run_dir"] / "redis.json")])


def check_clients_completed(ev, a):
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client summary.json")
    # A scenario may expect another outcome for a client, e.g. "left" for one that quits (S08G).
    want = {str(k): v for k, v in (a.get("expected_outcomes") or {}).items()}
    bad = {c["index"]: (c["summary"] or {}).get("outcome") for c in ev["clients"]
           if (c["summary"] or {}).get("outcome") != want.get(str(c["index"]), "completed")}
    return _result(PASS if not bad else FAIL, len(ev["clients"]) - len(bad), len(ev["clients"]),
                   source="client summary.json outcome", sampling="per client",
                   rationale="a client that crashed, aborted or errored did not run the scenario",
                   detail={"not_completed": bad},
                   artifacts=[str(c["dir"] / "summary.json") for c in ev["clients"]])


_LOG_ERROR = re.compile(r"(FATAL|NullReferenceException|IndexOutOfRangeException|InvalidOperationException|"
                        r"\[TestLab\].*error|Unhandled|Exception:)")


def check_client_log_clean(ev, a):
    allow = [re.compile(p) for p in a.get("allow", [])]
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="player.log")
    no_log = [c["index"] for c in ev["clients"] if not any(t.strip() for t in c["logs"].values())]
    if no_log:
        return _inconclusive(f"no player log for client(s) {no_log}: a log that was never written has no "
                             "exceptions to find", source="player.log")
    hits = {}
    for c in ev["clients"]:
        lines = []
        for name, text in c["logs"].items():
            for line in text.splitlines():
                if _LOG_ERROR.search(line) and not any(p.search(line) for p in allow):
                    lines.append(f"{name}: {line.strip()[:240]}")
        if lines:
            hits[c["index"]] = lines[:20]
    total = sum(len(v) for v in hits.values())
    return _result(PASS if total == 0 else FAIL, total, 0, source="player.log", sampling="whole log",
                   rationale="exceptions in the player are defects even when the scenario completes",
                   detail={"lines": hits}, artifacts=[str(c["dir"]) for c in ev["clients"]])


def check_inputs_consumed(ev, a):
    """Each scripted 'move' segment must move that client's server entity the planned way."""
    ids = _user_ids(ev)
    min_cos = float(a.get("min_cos", 0.9))
    min_fraction = float(a.get("min_distance_fraction", 0.5))
    settle = float(a.get("settle_s", 0.5))
    rows, failures, checked, unverified = [], 0, 0, 0
    for c in ev["clients"]:
        uid = ids[c["index"]]
        t = ev["traj"].get(uid) if uid else None
        moves = [s for s in c["plan"].get("steps", []) if s["mode"] == "move" and s["t1"] - s["t0"] >= 1.5]
        if not moves:
            continue
        if t is None:
            rows.append({"client": c["index"], "result": "no server trajectory"})
            failures += 1
            continue
        speed = t.get("speed") or 5.0
        reads = (c["summary"] or {}).get("input", {}).get("moves_read", 0)
        for s in moves:
            p0, p1 = _pos_at(t, s["t0"] + settle), _pos_at(t, s["t1"])
            if p0 is None or p1 is None:
                rows.append({"client": c["index"], "step": [s["t0"], s["t1"]], "result": "no samples"})
                unverified += 1
                continue
            # The displacement the INPUT produced: summed over the samples in the segment, leaving
            # out any step where the server respawned the player (HP from below half to full, or a
            # move no input can make). A respawn puts the player back at the spawn point, which is
            # not the input failing to move it.
            dx, dy, walked_s, respawns = _input_displacement(t, s["t0"] + settle, s["t1"], speed)
            if walked_s < 0.5 * (s["t1"] - s["t0"] - settle):
                rows.append({"client": c["index"], "step": [s["t0"], s["t1"]], "respawns": respawns,
                             "result": "respawned for most of the segment"})
                unverified += 1
                continue
            checked += 1
            dist = math.hypot(dx, dy)
            want = (s["x"], s["y"])
            wn = math.hypot(*want) or 1.0
            cos = (dx * want[0] + dy * want[1]) / (dist * wn) if dist > 1e-6 else 0.0
            expected = speed * walked_s
            ok = cos >= min_cos and dist >= min_fraction * expected
            failures += 0 if ok else 1
            rows.append({"client": c["index"], "step": [s["t0"], s["t1"]], "dir": [s["x"], s["y"]],
                         "moved": round(dist, 3), "expected_at_speed": round(expected, 3), "cos": round(cos, 3),
                         "respawns": respawns, "moves_read": reads, "ok": ok})
    if checked == 0:
        return _inconclusive("no move segment had server samples on both ends", source="/debug/entities + plan.json")
    status = FAIL if failures else (INCONCLUSIVE if unverified else PASS)
    return _result(status, f"{checked - failures}/{checked} segments ({unverified} unverified)",
                   {"min_cos": min_cos, "min_distance_fraction": min_fraction},
                   source="plan.json move steps vs server /debug/entities trajectory of the client's own player",
                   sampling=f"server positions at {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="input issued must be input consumed: the server entity moves in the scripted direction "
                             "at a plausible fraction of its speed (obstacles and stops excepted by the threshold)",
                   detail={"segments": rows})


def _input_displacement(t, t0, t1, speed):
    """Sum of the server's per-sample displacement of an entity over [t0, t1], skipping steps
    that are respawns (HP from below half to full) or faster than 2x its speed. Returns
    (dx, dy, seconds covered, respawns skipped)."""
    max_hp = t.get("max_hp") or 0
    pts = [(st, x, y, hp) for st, x, y, hp in zip(t["st"], t["x"], t["y"], t["hp"]) if t0 <= st <= t1]
    dx = dy = covered = 0.0
    respawns = 0
    for (s0, x0, y0, h0), (s1, x1, y1, h1) in zip(pts, pts[1:]):
        step = math.hypot(x1 - x0, y1 - y0)
        respawned = max_hp > 0 and h0 is not None and h1 is not None and h0 < 0.5 * max_hp and h1 >= max_hp
        if respawned or step > 2.0 * speed * max(s1 - s0, 1e-3) + 0.2:
            respawns += 1
            continue
        dx += x1 - x0
        dy += y1 - y0
        covered += s1 - s0
    return dx, dy, covered, respawns


def _divergence(ev, a, *, local: bool):
    lag = float(a.get("window_before_s", 0.6 if not local else 0.3))
    lead = float(a.get("window_after_s", 0.15 if not local else 0.6))
    types = set(a.get("types", ["mob", "player"]))
    rendered, received, stalled = util.Distribution(), util.Distribution(), util.Distribution()
    import heapq
    worst, seq = [], 0  # the 15 largest (stable for ties), not every row over the limit
    stalls = host_stalls(ev)
    excluded_catchup = 0
    for c in ev["clients"]:
        # Remote entities drawn in a scripted stall's catch-up window are not judged (Lead rule S13):
        # the world moved while the process was frozen. Local positions are never excluded.
        catchup = [] if local else [(w[0], w[1]) for w in stall_windows(c, float(ev["scenario"].get("duration_s", 0)))]
        for s in c["samples"]:
            st = s.get("st")
            if st is None or st < float(a.get("skip_first_s", 2.0)):
                continue
            if catchup and any(lo <= st < hi for lo, hi in catchup):
                excluded_catchup += 1
                continue
            in_stall = _in_stall(stalls, st, st, slack=0.5)
            for row in s.get("ents", []):
                eid, etype, is_local = row[0], row[1], row[2] == 1
                if is_local != local or etype not in types:
                    continue
                t = ev["traj"].get(eid)
                if t is None:
                    continue
                d = _dist_to_path(t, st - lag, st + lead, row[3], row[4])
                if d is None:
                    continue
                if in_stall:
                    stalled.add(d)
                    continue
                rendered.add(d)
                if len(row) >= 7:
                    dr = _dist_to_path(t, st - lag, st + lead, row[5], row[6])
                    if dr is not None:
                        received.add(dr)
                if d > float(a.get("max", 1.0)):
                    item = (round(d, 3), -seq, {"client": c["index"], "st": round(st, 3), "id": eid, "type": etype,
                                                "rendered_err": round(d, 3)})
                    seq += 1
                    if len(worst) < 15:
                        heapq.heappush(worst, item)
                    elif item[:2] > worst[0][:2]:
                        heapq.heapreplace(worst, item)
    worst = [w[2] for w in sorted(worst, key=lambda w: (-w[0], -w[1]))]
    return rendered, received, worst, stalled, excluded_catchup


def check_position_divergence(ev, a):
    local = bool(a.get("local", False))
    rendered, received, worst, stalled, excluded_catchup = _divergence(ev, a, local=local)
    if len(rendered) < int(a.get("min_samples", 50)):
        return _inconclusive(f"{len(rendered)} comparable samples (< {a.get('min_samples', 50)})",
                             source="client samples.ndjson vs server /debug/entities")
    p95, mx = rendered.percentile(95), rendered.max()
    rp95 = received.percentile(95) if received else None
    ok = p95 <= float(a.get("p95", 0.35)) and mx <= float(a.get("max", 1.0))
    stall_would_fail = bool(stalled) and stalled.max() > float(a.get("max", 1.0))
    worst = [w for w in worst if not _in_stall(host_stalls(ev), w["st"], w["st"], slack=0.5)]
    # Attribution: a client that RECEIVED positions on the server's path but RENDERED them off it
    # has an interpolation/presentation problem; one that received them off-path has a
    # snapshot/transport problem (or the server path itself is what moved).
    if ok:
        layer = "none"
    elif rp95 is not None and rp95 <= float(a.get("p95", 0.35)):
        layer = "client interpolation / prediction / presentation (received positions are on the server path)"
    else:
        layer = "snapshot or transport (received positions already off the server path)"
    worst.sort(key=lambda w: -w["rendered_err"])
    return _result(FAIL if not ok else (INCONCLUSIVE if stall_would_fail else PASS),
                   {"p50": round(rendered.percentile(50), 4), "p95": round(p95, 4), "max": round(mx, 4),
                    "received_p95": None if rp95 is None else round(rp95, 4), "samples": len(rendered),
                    "in_host_stall": len(stalled),
                    "max_in_host_stall": round(stalled.max(), 4) if stalled else None,
                    **({"excluded_stall_catchup_samples": excluded_catchup} if excluded_catchup else {})},
                   {"p95": a.get("p95", 0.35), "max": a.get("max", 1.0)},
                   source=("rendered LocalTransform of the " + ("local predicted player" if local else "remote entities") +
                           " vs the server's authoritative polyline in a time window around the sample"),
                   sampling=f"client {ev['scenario'].get('sample_hz')} Hz, server {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="distance from what the player sees to where the server says the entity was, allowing "
                             "the interpolation delay (window) so legitimate lag is not counted as error",
                   detail={"layer": layer, "worst": worst[:15]},
                   artifacts=[str(c["dir"] / "samples.ndjson") for c in ev["clients"]] +
                             [str(ev["run_dir"] / "server" / "entities.ndjson")])


def check_render_jumps(ev, a):
    """Rendered discontinuities, split by size: a MAJOR jump (>= major_step units in one frame) is a
    teleport/rubber-band any player sees; a MINOR one is a correction applied in a single frame
    (a hitch). Both are counted; the thresholds are separate."""
    major_step = float(a.get("major_step", 1.0))
    skip = float(a.get("skip_first_s", 2.0))
    per_client, events = {}, []
    counts = {"local_major": 0, "local_minor": 0, "remote_major": 0, "remote_minor": 0, "server_teleport": 0,
              "host_stall": 0}
    all_stall_events = []
    by_type = {}
    for c in ev["clients"]:
        js = [e for e in c["events"] if e.get("event") == "render_jump" and (e.get("st") or -1) >= skip]
        per_client[c["index"]] = len(js)
        near = {"samples": _samples_near(c, [e.get("st") for e in js], before=0.25, after=0.15)}
        windows = stall_windows(c, float(ev["scenario"].get("duration_s", 0)))
        allowance = [1] * len(windows)
        stalls = host_stalls(ev)
        stall_events = all_stall_events
        for e in js:
            if e.get("type") in set(a.get("ignore_types", ["projectile"])):
                counts["ignored_type"] = counts.get("ignored_type", 0) + 1
                continue
            est = e.get("st")
            if windows and est is not None:
                # Lead rule S13: on the stalled client, a REMOTE jump inside the stall's catch-up
                # window is the world catching up (not judged); ONE local major correction per stall
                # is allowed (Netcode D1 contract), a second one counts.
                if not e.get("local") and any(w[0] <= est < w[1] for w in windows):
                    counts["stall_catchup"] = counts.get("stall_catchup", 0) + 1
                    continue
                if e.get("local") and (e.get("step") or 0) >= major_step:
                    k = next((i for i, w in enumerate(windows) if w[0] <= est <= w[2] and allowance[i]), None)
                    if k is not None:
                        allowance[k] = 0
                        counts["stall_local_correction"] = counts.get("stall_local_correction", 0) + 1
                        continue
            if e.get("st") is not None and _in_stall(stalls, e["st"], e["st"], slack=0.3, after=1.0):
                counts["host_stall"] = counts.get("host_stall", 0) + 1
                stall_events.append(e)
                continue
            # A step the SERVER also made (respawn, teleport, portal) is the game, not a render
            # defect: the server path covered >= 80% of the rendered step around that instant.
            server_step = _server_displacement(ev, e.get("id"), e.get("st"))
            # ...and the server's own move was faster than any entity can walk in that window
            # (0.8 s at max_speed, +20%): only then is it a teleport rather than ordinary motion.
            walkable = float(ev["scenario"].get("jump", {}).get("max_speed", 6.0)) * 0.8 * 1.2
            respawned = _server_respawned(ev, e.get("id"), e.get("st"))
            received_step = _received_step(near, e.get("id"), e.get("st"),
                                           max_speed=float(ev["scenario"].get("jump", {}).get("max_speed", 6.0)))
            explained = server_step is not None and server_step >= 0.8 * (e.get("step") or 0)
            # The client's own received stream (20 Hz) resolves a teleport the 5 Hz server
            # probe aliases: the server put the entity elsewhere in ONE snapshot.
            received_teleport = received_step is not None and received_step >= 0.8 * (e.get("step") or 0)
            if received_teleport or (explained and (respawned or server_step > walkable)):
                counts["server_teleport"] = counts.get("server_teleport", 0) + 1
                events.append({"client": c["index"], "class": "server_teleport", "server_step": round(server_step, 3),
                               **{k: e.get(k) for k in ("st", "id", "type", "local", "step", "allowed", "dt_ms")}})
                continue
            key = ("local" if e.get("local") else "remote") + ("_major" if (e.get("step") or 0) >= major_step else "_minor")
            counts[key] += 1
            by_type[e.get("type")] = by_type.get(e.get("type"), 0) + 1
            events.append({"client": c["index"], "class": key,
                           **{k: e.get(k) for k in ("st", "id", "type", "local", "step", "allowed", "dt_ms")}})
    missing = [c["index"] for c in ev["clients"] if not c["summary"] or not c["events"]]
    if not ev["clients"] or missing:
        return _inconclusive(f"no summary or events.ndjson for client(s) {missing or 'all'}: jumps that were never "
                             "recorded are not absent", source="client events.ndjson render_jump")
    minutes = max(1e-6, float(ev["scenario"].get("duration_s", 60)) / 60.0)
    n = max(1, len(ev["clients"]))
    rate = {k: round(v / minutes / n, 3) for k, v in counts.items()
            if k not in ("server_teleport", "host_stall", "ignored_type", "stall_catchup", "stall_local_correction")}
    def passes(c):
        r = {k: c[k] / minutes / n for k in ("remote_major", "local_minor", "remote_minor")}
        return (c["local_major"] <= int(a.get("max_local", 0)) and
                r["remote_major"] <= float(a.get("max_remote_per_client_min", 2.0)) and
                r["local_minor"] <= float(a.get("max_local_minor_per_client_min", 30.0)) and
                r["remote_minor"] <= float(a.get("max_remote_minor_per_client_min", 30.0)))

    ok = passes(counts)
    # Would the jumps set aside as host stalls have failed it? Then the evidence cannot decide:
    # INCONCLUSIVE (rerun on a quiet host), never PASS.
    with_stalls = dict(counts)
    for e in all_stall_events:
        key = ("local" if e.get("local") else "remote") + ("_major" if (e.get("step") or 0) >= major_step else "_minor")
        with_stalls[key] += 1
    hidden_by_stall = ok and not passes(with_stalls)
    attributed = []
    for e in sorted(events, key=lambda x: -(x.get("step") or 0))[:30]:
        t = ev["traj"].get(e["id"])
        if not t or e.get("st") is None:
            continue
        p0, p1 = _pos_at(t, e["st"] - 0.25), _pos_at(t, e["st"] + 0.05)
        server_step = None if p0 is None or p1 is None else round(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 3)
        attributed.append({**e, "server_step_0p3s": server_step})
    return _result(FAIL if not ok else (INCONCLUSIVE if hidden_by_stall else PASS),
                   {**counts, "per_client_min": rate, "by_type": by_type},
                   {"local_major": a.get("max_local", 0), "remote_major_per_client_min": a.get("max_remote_per_client_min", 2.0),
                    "local_minor_per_client_min": a.get("max_local_minor_per_client_min", 30.0),
                    "remote_minor_per_client_min": a.get("max_remote_minor_per_client_min", 30.0), "major_step": major_step},
                   source="client per-frame rendered step vs max_speed x dt x factor + slack (RenderJumpDetector)",
                   sampling="every rendered frame, every replicated entity",
                   rationale="a rendered step larger than any legitimate speed is a discontinuity the player sees; "
                             ">= major_step is a teleport/rubber-band, smaller is a one-frame correction hitch",
                   detail={"per_client": per_client, "largest": attributed},
                   artifacts=[str(c["dir"] / "events.ndjson") for c in ev["clients"]] +
                             [str(c["dir"] / "shots") for c in ev["clients"]])


def stall_windows(c: dict, duration: float, local_window_s: float = 5.0) -> list:
    """Scripted stalls of one client (C2 hook, events.ndjson `stall`) on its scenario clock, as
    (start_st, catchup_end_st, local_end_st); a time t is in the catch-up window when
    start_st <= t < catchup_end_st.

    The catch-up frame is the frame AFTER the frame whose dt contains the stall, and catchup_end_st is
    the start of the frame after it: events and samples are stamped a little later than the frame's
    own frames.csv time, inside the same frame.
    Unity's frame dt reports the previous frame, and the binder state captured in frame N-1 is drawn
    in frame N (client docs/TESTLAB.md, render.csv "Which render clock"), so that frame is where the
    world that moved while the process was frozen is first drawn. local_end_st bounds the local
    corrections attributed to the stall: start + local_window_s, the next stall or the end of the run
    (Lead rule for S13, 2026-10-23)."""
    out = []
    stalls = sorted((e for e in c["events"] if e.get("event") == "stall" and e.get("t") is not None
                     and e.get("st") is not None and e.get("start") is not None and e.get("end") is not None),
                    key=lambda e: e["start"])
    frames = c.get("frames")
    sts = list(frames.st) if isinstance(frames, FrameSeries) else [f[0] for f in (frames or [])]
    dts = list(frames.dt) if isinstance(frames, FrameSeries) else [f[1] for f in (frames or [])]
    for k, e in enumerate(stalls):
        off = e["t"] - e["st"]
        start, end = e["start"] - off, e["end"] - off
        need = 0.5 * float(e.get("actual_ms") or e.get("ms") or 0)
        catchup = end
        i = bisect_left(sts, start)
        while i < len(sts):
            if dts[i] >= need:
                # frames i (dt holds the stall), i + 1 (the catch-up frame); the window ends where
                # frame i + 2 starts.
                if i + 2 < len(sts):
                    catchup = sts[i + 2]
                elif i + 1 < len(sts):
                    catchup = sts[i + 1] + dts[i + 1] / 1000.0
                break
            i += 1
        nxt = stalls[k + 1]["start"] - (stalls[k + 1]["t"] - stalls[k + 1]["st"]) if k + 1 < len(stalls) else float("inf")
        out.append((start, max(catchup, end), min(start + local_window_s, nxt, duration)))
    return out


def _samples_near(c: dict, times, before: float, after: float) -> list:
    """The client's samples (in file order) whose scenario time lies within [t - before, t + after] of
    any of `times`: one streaming pass instead of re-reading the file for every jump."""
    merged = []
    for lo, hi in sorted((t - before, t + after) for t in times if t is not None):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    if not merged:
        return []
    starts = [m[0] for m in merged]
    out = []
    for smp in c["samples"]:
        st = smp.get("st")
        if st is None:
            continue
        j = bisect_right(starts, st) - 1
        if j >= 0 and st <= merged[j][1]:
            out.append(smp)
    return out


def _received_step(client: dict, eid: str, st: float, before=0.25, after=0.15, max_speed=6.0, tick_hz=60.0):
    """Largest jump in the position this client RECEIVED for the entity (the snapshot stream,
    sampled at the plan's sample_hz) between consecutive samples in [st-before, st+after] that no
    entity could have WALKED in the server time between them (the samples' world_tick delta,
    at 1.5x max_speed plus 0.2 units). Unlike the 5 Hz server probe this sees a teleport the
    server made between two of its samples; the server-tick bound keeps a late snapshot burst
    (a long but legitimate step after a delivery gap) from passing as one. None when no
    consecutive pair exceeded the bound."""
    prev = None
    best = None
    for s in client.get("samples", []):
        t = s.get("st")
        if t is None or t < st - before:
            continue
        if t > st + after:
            break
        row = next((r for r in s.get("ents", []) if r[0] == eid and len(r) >= 7), None)
        if row is None:
            continue
        wt = s.get("world_tick")
        if prev is not None:
            d = math.hypot(row[5] - prev[0], row[6] - prev[1])
            dticks = (wt - prev[2]) if (wt is not None and prev[2] is not None) else None
            if dticks is not None and dticks >= 0:
                walk = max_speed * 1.5 * max(dticks, 1) / tick_hz + 0.2
                if d > walk and (best is None or d > best):
                    best = d
        prev = (row[5], row[6], wt)
    return best


def _server_respawned(ev, eid, st, before=0.4, after=0.3) -> bool:
    """The server respawned the entity around st: its HP went from below half to full (a respawn
    puts a player back at the spawn point, which is a teleport whatever the distance)."""
    t = ev["traj"].get(eid)
    if not t or st is None:
        return False
    max_hp = t.get("max_hp") or 0
    if max_hp <= 0:
        return False
    window = [hp for s2, hp in zip(t["st"], t["hp"]) if st - before <= s2 <= st + after and hp is not None]
    for i in range(1, len(window)):
        if window[i - 1] < 0.5 * max_hp and window[i] >= max_hp:
            return True
    return False


def _server_displacement(ev, eid, st, before=0.4, after=0.2):
    """Largest distance the server moved the entity between two CONSECUTIVE samples in
    [st-before, st+after] - a single server step, not the sum of ordinary motion."""
    t = ev["traj"].get(eid)
    if not t or st is None:
        return None
    pts = [(x, y) for s2, x, y in zip(t["st"], t["x"], t["y"]) if st - before <= s2 <= st + after]
    if len(pts) < 2:
        return None
    return max(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))


def check_snapshot_cadence(ev, a):
    hz = None
    rows = _status_in_window(ev)
    if rows:
        hz = rows[-1].get("sim_world_hz")
    hz = float(a.get("expected_hz", hz or 15))
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client snapshots.ndjson")
    per = {}
    bad = 0
    host_explained = 0
    stalls = host_stalls(ev)
    for c in ev["clients"]:
        s = c["summary"] or {}
        snaps = [x for x in c["snapshots"] if x.get("t") is not None]
        start = s.get("start_realtime")
        dur = float(ev["scenario"].get("duration_s", 0))
        if start is None or not snaps:
            per[c["index"]] = "no data"
            bad += 1
            continue
        # Windows a scenario expects an interruption in (e.g. a server restart and its grace
        # period, S11) are left out: gaps touching them are not judged, nor counted in the rate.
        excl = [(start + float(w[0]), start + float(w[1])) for w in a.get("exclude_s", [])]
        inside = [x["t"] for x in snaps if start <= x["t"] <= start + dur]
        gaps = [b - a2 for a2, b in zip(inside, inside[1:]) if not any(e0 <= b and a2 <= e1 for e0, e1 in excl)]
        kept = [t for t in inside if not any(e0 <= t <= e1 for e0, e1 in excl)]
        judged_s = dur - sum(min(e1, start + dur) - max(e0, start) for e0, e1 in excl if e1 > start and e0 < start + dur)
        rate = len(kept) / judged_s if judged_s > 0 else 0
        max_gap = max(gaps) * 1000 if gaps else None
        p99_gap = util.percentile([g * 1000 for g in gaps], 99) if gaps else None
        ok = (abs(rate - hz) <= hz * float(a.get("rate_tolerance", 0.2)) and max_gap is not None and
              max_gap <= float(a.get("max_gap_ms", 250)))
        if not ok and max_gap is not None:
            # Every over-limit gap overlaps a host-wide stall: the evidence cannot say anything
            # about the netcode, so this client's row is inconclusive rather than failed.
            limit = float(a.get("max_gap_ms", 250)) / 1000.0
            over = [(a2 - start, b - start) for a2, b in zip(inside, inside[1:]) if b - a2 > limit
                    and not any(e0 <= b and a2 <= e1 for e0, e1 in excl)]
            if over and all(_in_stall(stalls, g0, g1) for g0, g1 in over) and \
                    abs(rate - hz) <= hz * float(a.get("rate_tolerance", 0.2)):
                host_explained += 1
                per[c["index"]] = {"rate_hz": round(rate, 2), "max_gap_ms": round(max_gap, 1),
                                   "ok": "host stall", "gaps_in_host_stall": len(over)}
                continue
        bad += 0 if ok else 1
        per[c["index"]] = {"rate_hz": round(rate, 2), "p99_gap_ms": p99_gap and round(p99_gap, 1),
                           "max_gap_ms": max_gap and round(max_gap, 1), "ok": ok}
    status = FAIL if bad else (INCONCLUSIVE if host_explained else PASS)
    return _result(status, per,
                   {"rate_hz": hz, "rate_tolerance": a.get("rate_tolerance", 0.2), "max_gap_ms": a.get("max_gap_ms", 250)},
                   source="client snapshots.ndjson receive times (NetworkClient.SnapshotReceived, monotonic)",
                   sampling="every snapshot", rationale="snapshots ship at SIM_WORLD_HZ; a long gap is a visible freeze "
                                                       "followed by a catch-up jump",
                   artifacts=[str(c["dir"] / "snapshots.ndjson") for c in ev["clients"]])


def check_frame_time(ev, a):
    per, bad, missing = {}, 0, 0
    for c in ev["clients"]:
        f = (c["summary"] or {}).get("frames")
        if not f or not f.get("count"):
            missing += 1
            continue
        ok = (f.get("p95_ms") or 1e9) <= float(a.get("p95_ms", 33.4)) and (f.get("p99_ms") or 1e9) <= float(a.get("p99_ms", 50))
        bad += 0 if ok else 1
        per[c["index"]] = {k: f.get(k) for k in ("count", "p50_ms", "p95_ms", "p99_ms", "max_ms", "long_frames")}
    if not ev["clients"] or missing == len(ev["clients"]):
        return _inconclusive("no frame statistics", source="client summary.json frames")
    status = FAIL if bad else (INCONCLUSIVE if missing else PASS)
    return _result(status, per, {"p95_ms": a.get("p95_ms", 33.4), "p99_ms": a.get("p99_ms", 50)},
                   source="client unscaled frame delta (every frame of the scenario window)", sampling="every frame",
                   rationale="all clients render on one host here, so this is a lower bound of a single-client frame "
                             "budget; it still catches a client-side frame-time regression or hitch",
                   artifacts=[str(c["dir"] / "frames.csv") for c in ev["clients"]])


def check_server_tick(ev, a):
    rows = _status_in_window(ev)
    if not rows:
        return _inconclusive("no /status samples", source="/status achieved_tick_hz")
    if not any(r.get("achieved_tick_hz") is not None for r in rows):
        return _inconclusive("no achieved_tick_hz in the /status samples", source="/status achieved_tick_hz")
    crit = rows[-1].get("sim_critical_hz") or 60
    min_hz = min(r.get("achieved_tick_hz") or 0 for r in rows)
    budget_ms = 1000.0 / crit
    p99_ms = tick_p99_ms(ev)
    over = _delta(ev, "gameserver_tick_overruns_total")
    ok = min_hz >= crit * float(a.get("min_rate_ratio", 0.98)) and (p99_ms is None or p99_ms <= budget_ms * float(a.get("p99_budget_ratio", 1.0)))
    status = PASS if ok else FAIL
    if p99_ms is None and ok:
        status = INCONCLUSIVE if a.get("require_p99", True) else PASS
    return _result(status, {"min_achieved_hz": round(min_hz, 2), "tick_p99_ms_bucket_upper": p99_ms, "overruns_delta": over},
                   {"min_rate": crit * float(a.get("min_rate_ratio", 0.98)), "p99_ms": round(budget_ms, 2)},
                   source="/status achieved_tick_hz; /metrics gameserver_tick_duration_seconds histogram delta",
                   sampling="status 1 Hz; histogram start->end of run",
                   rationale="tick budget = 1/SIM_CRITICAL_HZ; the load generator shares this host, so tick numbers "
                             "are lower bounds of unknown tightness (ADR-7)",
                   artifacts=[str(ev["run_dir"] / "server" / f) for f in ("status.ndjson", "metrics-start.txt", "metrics-end.txt")])


def tick_p99_ms(ev):
    """p99 as the upper bound of the histogram bucket holding the 99th percentile (delta over the run)."""
    a, b = ev["server"]["metrics_start"], ev["server"]["metrics_end"]
    buckets = {}
    for k, v in b.items():
        if k.startswith("gameserver_tick_duration_seconds_bucket{"):
            m = re.search(r'le="([^"]+)"', k)
            if m:
                le = float("inf") if m.group(1) == "+Inf" else float(m.group(1))
                buckets[le] = buckets.get(le, 0) + v - a.get(k, 0.0)
    if not buckets:
        return None
    total = buckets.get(float("inf"))
    if not total:
        return None
    for le in sorted(buckets):
        if buckets[le] >= 0.99 * total:
            return None if math.isinf(le) else le * 1000.0
    return None


def check_kcp_health(ev, a):
    by_reason = {k.split("reason=")[1].strip('"}'): v - ev["server"]["metrics_start"].get(k, 0.0)
                 for k, v in ev["server"]["metrics_end"].items()
                 if k.startswith(("gameserver_kcp_datagrams_dropped_total{", "gameserver_kcp_sessions_closed_total{"))
                 and "reason=" in k and v - ev["server"]["metrics_start"].get(k, 0.0) > 0}
    dropped = _delta(ev, "gameserver_kcp_datagrams_dropped_total")
    closed = _delta(ev, "gameserver_kcp_sessions_closed_total")
    rejected = _delta(ev, "gameserver_kcp_sessions_rejected_total")
    if dropped is None or closed is None:
        return _inconclusive("metrics scrape missing", source="/metrics kcp counters")
    # `"max_dropped": null` leaves inbound drops unjudged (reported): S18 loses datagrams on purpose.
    max_dropped = a.get("max_dropped", 0)
    ok = (max_dropped is None or dropped <= float(max_dropped)) and closed <= float(a.get("max_sessions_closed", 0))         and (rejected or 0) == 0
    return _result(PASS if ok else FAIL, {"dropped": dropped, "sessions_closed": closed, "sessions_rejected": rejected},
                   {"dropped": max_dropped, "sessions_closed": a.get("max_sessions_closed", 0), "rejected": 0},
                   source="/metrics gameserver_kcp_* counters, delta scenario start -> scenario end (clients still in world)",
                   sampling="2 scrapes", detail={"by_reason": by_reason},
                   rationale="drops and closed sessions inside the scenario window are lost gameplay traffic or "
                             "disconnects; teardown after the window is excluded (metrics-after.txt)",
                   artifacts=[str(ev["run_dir"] / "server")])


def check_snapshot_update_gap(ev, a):
    rows = _status_in_window(ev)
    if not rows:
        return _inconclusive("no /status samples", source="/status snapshot_max_update_gap_ms")
    vals = [r.get("snapshot_max_update_gap_ms") for r in rows if r.get("snapshot_max_update_gap_ms") is not None]
    shed = _delta(ev, "gameserver_snapshots_entities_shed_total")
    gathered = _delta(ev, "gameserver_snapshots_entities_gathered_total")
    if not vals or len(vals) < len(rows):
        return _inconclusive(f"field present in {len(vals)} of {len(rows)} /status samples",
                             source="/status snapshot_max_update_gap_ms")
    expected = float(ev["scenario"].get("duration_s", 0)) * 0.8  # 1 Hz probe; 80% coverage
    if len(rows) < expected:
        return _inconclusive(f"only {len(rows)} /status samples for a {ev['scenario'].get('duration_s')} s window",
                             source="/status snapshot_max_update_gap_ms")
    mx = max(vals)
    ok = mx <= float(a.get("max_gap_ms", 200))
    return _result(PASS if ok else FAIL, {"max_update_gap_ms": mx, "shed": shed, "gathered": gathered,
                                          "shed_ratio": None if not gathered else round((shed or 0) / gathered, 5)},
                   {"max_update_gap_ms": a.get("max_gap_ms", 200)},
                   source="/status snapshot_max_update_gap_ms (worst per-entity replication gap); /metrics shed counters",
                   sampling="1 Hz", rationale="an entity left out of snapshots for long freezes then jumps on screen")


def _alive_enemies(row):
    return [e for e in row["ents"] if e[1] == "mob" and not e[6] and (e[4] or 0) > 0]


def _players(row):
    return [e for e in row["ents"] if e[1] == "player" and not e[6]]


def check_enemy_crowding(ev, a):
    """Target distribution and separation of the enemy crowd, measured on the server."""
    lo, hi = _window(ev)
    lo += float(a.get("skip_first_s", 5))
    n_rows = sum(1 for r in ev["server"]["entities"] if r.get("st") is not None and lo <= r["st"] <= hi)
    if not n_rows:
        return _inconclusive("no server entity samples in window", source="/debug/entities")
    overlap_r = float(a.get("overlap_radius", 0.3))
    per_sample = []
    stride = max(1, n_rows // 60)
    picked = (r for i, r in enumerate(r for r in ev["server"]["entities"]
                                      if r.get("st") is not None and lo <= r["st"] <= hi) if i % stride == 0)
    for r in picked:
        enemies, players = _alive_enemies(r), _players(r)
        if not enemies or not players:
            continue
        share = {}
        contact = 0
        for e in enemies:
            best, bd = None, None
            for p in players:
                d = (e[2] - p[2]) ** 2 + (e[3] - p[3]) ** 2
                if bd is None or d < bd:
                    best, bd = p[0], d
            share[best] = share.get(best, 0) + 1
            contact += 1 if math.sqrt(bd) <= float(a.get("contact_radius", 1.3)) else 0
        nn = _nearest_neighbour(enemies)
        overlapped = sum(1 for d in nn if d < overlap_r)
        pd = [math.hypot(p[2] - q[2], p[3] - q[3]) for i, p in enumerate(players) for q in players[i + 1:]]
        per_sample.append({
            "st": round(r["st"], 2), "enemies": len(enemies), "players": len(players),
            "max_target_share": round(max(share.values()) / len(enemies), 3),
            "target_counts": sorted(share.values(), reverse=True),
            "min_player_distance": round(min(pd), 2) if pd else None,
            "nn_p10": round(util.percentile(nn, 10), 3) if nn else None,
            "nn_median": round(util.percentile(nn, 50), 3) if nn else None,
            "overlap_ratio": round(overlapped / len(enemies), 3),
            "at_contact_ratio": round(contact / len(enemies), 3),
        })
    if not per_sample:
        return _inconclusive("no sample with both enemies and players", source="/debug/entities")
    spread = [s for s in per_sample if s["min_player_distance"] is not None and s["min_player_distance"] >= float(a.get("spread_distance", 10))]
    max_share_spread = max((s["max_target_share"] for s in spread), default=None)
    overlap = util.percentile([s["overlap_ratio"] for s in per_sample], 50)
    findings = []
    status = PASS
    if max_share_spread is None and a.get("require_spread"):
        findings.append(f"players were never >= {a.get('spread_distance', 10)} apart: the spread criterion "
                        "was not exercised")
        status = INCONCLUSIVE
    if max_share_spread is not None and max_share_spread > float(a.get("max_share_when_spread", 0.9)):
        findings.append(f"with players >= {a.get('spread_distance', 10)} apart, one player still drew "
                        f"{max_share_spread:.0%} of enemies")
        # Concentration alone is not a defect under the nearest-player rule: enemies that chased
        # one player stay with it after the others walk away. Whether they follow the rule is
        # what enemy_pursuit checks. A scenario may still declare concentration a failure.
        if a.get("share_is_failure", False):
            status = FAIL
        elif status == PASS:
            status = INFO
    if overlap is not None and overlap > float(a.get("max_overlap_ratio", 0.5)):
        findings.append(f"median {overlap:.0%} of enemies overlap another enemy within {overlap_r} units")
        status = FAIL if a.get("overlap_is_failure", False) else (status if status in (FAIL, INCONCLUSIVE) else INFO)
    measured = {"samples": len(per_sample), "median_overlap_ratio": overlap,
                "median_max_target_share": util.percentile([s["max_target_share"] for s in per_sample], 50),
                "max_target_share_when_spread": max_share_spread,
                "median_at_contact_ratio": util.percentile([s["at_contact_ratio"] for s in per_sample], 50),
                "median_nn": util.percentile([s["nn_median"] for s in per_sample if s["nn_median"] is not None], 50)}
    return _result(status, measured,
                   {"max_share_when_spread": a.get("max_share_when_spread", 0.9),
                    "share_is_failure": a.get("share_is_failure", False),
                    "max_overlap_ratio": a.get("max_overlap_ratio", 0.5),
                    "overlap_is_failure": a.get("overlap_is_failure", False)},
                   source="server /debug/entities; target derived with the server's own rule (nearest live player, "
                          "EnemyMoveSystem/PlayerTargetBuffer.TryNearest)",
                   sampling=f"{len(per_sample)} evenly spaced server samples",
                   rationale="target distribution follows the nearest-live-player rule: concentration on one "
                             "player is reported (INFO) but is a failure only when the scenario sets share_is_failure, "
                             "because enemies that closed on one player stay with it after the others leave (product "
                             "decision recorded in rpg-mmo-server#469; rule conformance is enemy_pursuit). Overlap "
                             "fails when the scenario sets overlap_is_failure (server separation on, #469)",
                   detail={"findings": findings, "timeline": per_sample[:: max(1, len(per_sample) // 20)]},
                   artifacts=[str(ev["run_dir"] / "server" / "entities.ndjson")])


def _nearest_player(e, players):
    best, bd = None, None
    for p in players:
        d = math.hypot(e[2] - p[2], e[3] - p[3])
        if bd is None or d < bd:
            best, bd = p, d
    return best, bd


def check_enemy_pursuit(ev, a):
    """Enemies follow the server's targeting rule, and a settled crowd holds still.

    Pursuit: an enemy farther than `far_distance` from its nearest live player, that moved
    between two consecutive server samples, must have moved toward where that player stood
    (within `max_heading_deg` of the bearing). Heading, not distance: a player walking away at
    5 u/s outruns a 2.5 u/s chaser, so the distance grows while the pursuit is correct. Judged on
    ISOLATED enemies only (no other enemy within `crowd_radius`): inside a crowd, separation and
    queueing legitimately move an enemy sideways or back, which is not a targeting decision.
    Crowd steps are reported, not judged. Near the target,
    queueing, sliding and separation legitimately move an enemy sideways or back, so the rule is
    asserted only where none of them applies. Settled: enemies within `settle_distance` of their
    target in both samples; their speed relative to the target is the jitter a client sees.
    """
    lo, hi = _window(ev)
    lo += float(a.get("skip_first_s", 5))
    n_rows = sum(1 for r in ev["server"]["entities"] if r.get("st") is not None and lo <= r["st"] <= hi)
    if n_rows < 2:
        return _inconclusive("fewer than two server entity samples in window", source="/debug/entities")

    def _rows_in_window():
        return (r for r in ev["server"]["entities"] if r.get("st") is not None and lo <= r["st"] <= hi)

    def _consecutive(it):
        prev = None
        for r in it:
            if prev is not None:
                yield prev, r
            prev = r
    far = float(a.get("far_distance", 3.0))
    settle = float(a.get("settle_distance", 2.6))
    moving_eps = float(a.get("moving_epsilon", 0.02))
    cos_max = math.cos(math.radians(float(a.get("max_heading_deg", 45))))
    crowd_r = float(a.get("crowd_radius", 1.2))
    crowd_steps = crowd_heading = 0
    far_steps = approaching = 0
    away = []
    settled_rel = []
    for r0, r1 in _consecutive(_rows_in_window()):
        dt = r1["st"] - r0["st"]
        if not 0.03 <= dt <= 0.6:
            continue
        players0 = {p[0]: p for p in _players(r0)}
        players1 = {p[0]: p for p in _players(r1)}
        if not players0:
            continue
        e1 = {e[0]: e for e in _alive_enemies(r1)}
        alive0 = _alive_enemies(r0)
        for e in alive0:
            n = e1.get(e[0])
            if n is None:
                continue
            target, d0 = _nearest_player(e, players0.values())
            t1 = players1.get(target[0])
            if t1 is None:
                continue
            d1 = math.hypot(n[2] - t1[2], n[3] - t1[3])
            moved = math.hypot(n[2] - e[2], n[3] - e[3])
            if d0 > far and moved > moving_eps:
                cos = ((n[2] - e[2]) * (target[2] - e[2]) + (n[3] - e[3]) * (target[3] - e[3])) / (moved * d0)
                if any(o is not e and math.hypot(o[2] - e[2], o[3] - e[3]) < crowd_r for o in alive0):
                    crowd_steps += 1
                    crowd_heading += 1 if cos >= cos_max else 0
                    continue
                far_steps += 1
                if cos >= cos_max:
                    approaching += 1
                elif len(away) < 20:
                    away.append({"st": round(r0["st"], 2), "id": e[0], "target": target[0],
                                 "d0": round(d0, 3), "d1": round(d1, 3), "heading_deg": round(math.degrees(math.acos(max(-1.0, min(1.0, cos)))), 1)})
            if d0 <= settle and d1 <= settle:
                rel = math.hypot((n[2] - e[2]) - (t1[2] - target[2]), (n[3] - e[3]) - (t1[3] - target[3]))
                settled_rel.append(rel / dt)
    min_far = int(a.get("min_far_steps", 50))
    if far_steps < min_far:
        return _inconclusive(f"{far_steps} isolated enemy steps farther than {far} from a target (need {min_far})",
                             source="/debug/entities")
    min_settled = int(a.get("min_settled_samples", 50))
    if a.get("max_settled_speed") is not None and len(settled_rel) < min_settled:
        return _inconclusive(f"{len(settled_rel)} settled-enemy samples (need {min_settled}) for the settled bound",
                             source="/debug/entities")
    ratio = approaching / far_steps
    findings = []
    status = PASS
    if ratio < float(a.get("min_pursuit_ratio", 0.95)):
        findings.append(f"only {ratio:.1%} of {far_steps} isolated far enemy steps headed for the nearest live player")
        status = FAIL
    settled_p95 = round(util.percentile(settled_rel, 95), 3) if settled_rel else None
    if a.get("max_settled_speed") is not None and settled_p95 is not None \
            and settled_p95 > float(a["max_settled_speed"]):
        findings.append(f"settled enemies move at p95 {settled_p95} u/s relative to their target")
        status = FAIL
    return _result(status, {"far_steps": far_steps, "pursuit_ratio": round(ratio, 4),
                             "crowd_steps": crowd_steps,
                             "crowd_heading_ratio": round(crowd_heading / crowd_steps, 4) if crowd_steps else None,
                             "settled_samples": len(settled_rel), "settled_rel_speed_p95": settled_p95,
                             "settled_rel_speed_median": round(util.percentile(settled_rel, 50), 3) if settled_rel else None},
                   {"min_pursuit_ratio": a.get("min_pursuit_ratio", 0.95), "far_distance": far,
                    "max_heading_deg": a.get("max_heading_deg", 45), "crowd_radius": crowd_r,
                    "max_settled_speed": a.get("max_settled_speed")},
                   source="server /debug/entities, consecutive samples; target = nearest live player "
                          "(the server's rule, PlayerTargetBuffer.TryNearest)",
                   sampling=f"{n_rows} server samples",
                   rationale="an enemy far from every player has no crowd to queue in, so every step it takes must "
                             "close on its target; the settled speed is how much a crowd at its target still moves "
                             "(jitter), measured relative to the target so a walking player is not counted",
                   detail={"findings": findings, "away": away},
                   artifacts=[str(ev["run_dir"] / "server" / "entities.ndjson")])


def check_spawn_overlap(ev, a):
    """Fresh player placements (first appearance, respawn) do not land on another live player."""
    min_d = float(a.get("min_distance", 0.5))
    n_rows = 0
    seen = {}
    spawns = []
    for r in (r for r in ev["server"]["entities"] if r.get("st") is not None):
        n_rows += 1
        players = _players(r) + [e for e in r["ents"] if e[1] == "player" and e[6]]
        alive = [p for p in players if not p[6] and (p[4] or 0) > 0]
        for p in players:
            prev = seen.get(p[0])
            fresh = prev is None
            if prev is not None and (prev[6] or (prev[4] or 0) <= 0) and not p[6] and (p[4] or 0) > 0:
                fresh = True
            mx = p[5] or 0
            if prev is not None and mx > 0 and (prev[4] or 0) < 0.5 * mx and (p[4] or 0) >= mx:
                fresh = True
            seen[p[0]] = p
            if not fresh or p[6]:
                continue
            others = [q for q in alive if q[0] != p[0]]
            nearest = min((math.hypot(p[2] - q[2], p[3] - q[3]) for q in others), default=None)
            spawns.append({"st": round(r["st"], 2), "id": p[0], "x": round(p[2], 3), "y": round(p[3], 3),
                           "nearest_player": None if nearest is None else round(nearest, 3)})
    if not n_rows:
        return _inconclusive("no server entity samples", source="/debug/entities")
    judged = [s for s in spawns if s["nearest_player"] is not None]
    min_judged = int(a.get("min_judged", 2))
    if len(judged) < min_judged:
        return _inconclusive(f"{len(judged)} of {len(spawns)} placements had another live player to compare with "
                             f"(need {min_judged})", source="/debug/entities")
    bad = [s for s in judged if s["nearest_player"] < min_d]
    ok = len(bad) <= int(a.get("max_overlapping", 0))
    return _result(PASS if ok else FAIL,
                   {"spawns": len(spawns), "judged": len(judged), "unjudged": len(spawns) - len(judged),
                    "overlapping": len(bad),
                    "min_nearest": min(s["nearest_player"] for s in judged)},
                   {"min_distance": min_d, "max_overlapping": a.get("max_overlapping", 0)},
                   source="server /debug/entities: first appearance or respawn (dead -> alive, or HP from below half "
                          "to full) of each player, distance to every other live player in the same sample",
                   sampling=f"{n_rows} server samples",
                   rationale="every new or respawned player used to start on the same point (rpg-mmo-server#469); "
                             "GAMESERVER_SPAWN_SCATTER spreads them. A placement with no other live player in the "
                             "world cannot land on one: it is counted as unjudged, and PASS speaks for the judged "
                             "placements (at least min_judged of them)",
                   detail={"overlapping": bad[:20], "spawns": spawns[:40]},
                   artifacts=[str(ev["run_dir"] / "server" / "entities.ndjson")])


def _nearest_neighbour(points):
    out = []
    n = len(points)
    if n < 2:
        return out
    # Grid bucket so 2000 enemies stay cheap.
    cell = 1.0
    grid = {}
    for i, p in enumerate(points):
        grid.setdefault((int(p[2] // cell), int(p[3] // cell)), []).append(i)
    for i, p in enumerate(points):
        best = None
        cx, cy = int(p[2] // cell), int(p[3] // cell)
        for ring in range(0, 6):
            for gx in range(cx - ring, cx + ring + 1):
                for gy in range(cy - ring, cy + ring + 1):
                    if max(abs(gx - cx), abs(gy - cy)) != ring:
                        continue
                    for j in grid.get((gx, gy), ()):
                        if j == i:
                            continue
                        d = math.hypot(p[2] - points[j][2], p[3] - points[j][3])
                        best = d if best is None or d < best else best
            if best is not None and best <= ring * cell:
                break
        if best is not None:
            out.append(best)
    return out


def check_enemy_server_speed(ev, a):
    configured = float(a.get("speed", 2.5))
    tol = float(a.get("tolerance", 1.15))
    speeds = util.Distribution()
    worst = []
    for eid, t in ev["traj"].items():
        if t["type"] != "mob":
            continue
        for i in range(1, len(t["st"])):
            dt = t["st"][i] - t["st"][i - 1]
            if dt <= 0.05:
                continue
            v = math.hypot(t["x"][i] - t["x"][i - 1], t["y"][i] - t["y"][i - 1]) / dt
            speeds.add(v)
            if v > configured * tol:
                worst.append({"id": eid, "st": round(t["st"][i], 2), "speed": round(v, 3)})
                if len(worst) > 1000:
                    worst = sorted(worst, key=lambda w: -w["speed"])[:10]
    if not speeds:
        return _inconclusive("no enemy trajectories", source="/debug/entities")
    mx = speeds.max()
    # Probe sampling jitter (HTTP latency) inflates speeds measured over short intervals.
    ok = speeds.percentile(99) <= configured * tol
    return _result(PASS if ok else FAIL, {"p99": round(speeds.percentile(99), 3), "max": round(mx, 3), "n": len(speeds)},
                   {"p99_max": round(configured * tol, 3)}, source="server /debug/entities positions, consecutive samples",
                   sampling=f"{ev['scenario'].get('server_sample_hz')} Hz", rationale="server-side enemy speed must not "
                   "exceed GAMESERVER_ENEMY_SPEED; probe timing jitter is why p99, not max, decides",
                   detail={"worst": sorted(worst, key=lambda w: -w["speed"])[:10]})


def check_enemy_render_speed(ev, a):
    """'Enemies fly': rendered enemy speed seen by each client."""
    configured = float(a.get("speed", 2.5))
    tol = float(a.get("tolerance", 1.6))
    speeds, worst, n_fast = util.Distribution(), [], 0
    for c in ev["clients"]:
        last = {}
        for s in c["samples"]:
            st = s.get("st")
            if st is None or st < float(a.get("skip_first_s", 2.0)):
                continue
            for row in s.get("ents", []):
                if row[1] != "mob":
                    continue
                p = last.get(row[0])
                if p and 0.02 < st - p[0] < 0.2:
                    v = math.hypot(row[3] - p[1], row[4] - p[2]) / (st - p[0])
                    speeds.add(v)
                    if v > configured * tol:
                        n_fast += 1
                        worst.append({"client": c["index"], "id": row[0], "st": round(st, 2), "speed": round(v, 2)})
                        if len(worst) > 1000:
                            worst = sorted(worst, key=lambda w: -w["speed"])[:15]
                last[row[0]] = (st, row[3], row[4])
    if not speeds:
        return _inconclusive("no rendered enemy samples", source="client samples.ndjson")
    p99 = speeds.percentile(99)
    frac = n_fast / len(speeds)
    ok = p99 <= configured * tol and frac <= float(a.get("max_fast_fraction", 0.01))
    return _result(PASS if ok else FAIL, {"p50": round(speeds.percentile(50), 3), "p99": round(p99, 3),
                                          "max": round(speeds.max(), 3), "fast_fraction": round(frac, 4), "n": len(speeds)},
                   {"p99_max": configured * tol, "max_fast_fraction": a.get("max_fast_fraction", 0.01)},
                   source="client rendered enemy positions (LocalTransform) between consecutive samples",
                   sampling=f"client {ev['scenario'].get('sample_hz')} Hz",
                   rationale="what the player sees must not move enemies faster than the server does (\"enemies fly\")",
                   detail={"worst": sorted(worst, key=lambda w: -w["speed"])[:15]})


def check_combat_effect(ev, a):
    casts = sum(((c["summary"] or {}).get("input") or {}).get("casts_planned", 0) for c in ev["clients"])
    damaged, killed = set(), set()
    for eid, t in ev["traj"].items():
        if t["type"] != "mob":
            continue
        mh = t.get("max_hp") or 0
        if any((h or 0) < mh for h in t["hp"]):
            damaged.add(eid)
        if t["st"] and t["st"][-1] < float(ev["scenario"].get("duration_s", 0)) - 1 and (t["hp"][-1] or 0) < mh:
            killed.add(eid)
    kills_status = None
    rows = _status_in_window(ev)
    if len(rows) >= 2:
        kills_status = (rows[-1].get("attack_kills") or 0) - (rows[0].get("attack_kills") or 0)
    if casts == 0:
        return _result(FAIL, {"casts": 0}, {"casts": ">0"}, source="client summary input.casts_planned",
                       sampling="per client", rationale="the scenario issued no cast: the combat path was not exercised")
    ok = len(damaged) >= int(a.get("min_damaged", 1))
    return _result(PASS if ok else FAIL, {"casts": casts, "enemies_damaged": len(damaged), "enemies_damaged_then_gone": len(killed),
                                          "status_attack_kills_delta": kills_status},
                   {"min_damaged": a.get("min_damaged", 1)},
                   source="client casts (scripted, real projectile cast path) vs server enemy HP in /debug/entities",
                   sampling=f"server {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="casts sent through the production input path must damage enemies on the server")


def check_reconnect(ev, a):
    ids = _user_ids(ev)
    k = int(a.get("client", 0))
    if k >= len(ev["clients"]):
        return _inconclusive(f"client {k} is not in this run", source="run.json client history")
    c = ev["clients"][k]
    hist = c["history"]
    launches = [h for h in hist.get("history", []) if h.get("event") == "launch"]
    first_uid = hist.get("first_user_id")
    final_uid = ids[k]
    lo, hi = _window(ev)
    last = None
    for r in ev["server"]["entities"]:
        if r.get("st") is not None and lo <= r["st"] <= hi:
            last = r  # The last sample INSIDE the scenario window: after it, clients quit on purpose.
    players_final = len(_players(last)) if last else None
    rows = _status_in_window(ev)
    online_final = rows[-1].get("players_online") if rows else None
    n = len(ev["clients"])
    if len(launches) < 2:
        return _inconclusive("the client was not relaunched", source="run.json client history")
    ok = (first_uid == final_uid and players_final == n and online_final == n and
          (ev["redis"].get("session_keys") in (None, n)))
    return _result(PASS if ok else FAIL,
                   {"launches": len(launches), "user_id_before": first_uid, "user_id_after": final_uid,
                    "player_entities_final": players_final, "players_online_final": online_final,
                    "redis_sessions": ev["redis"].get("session_keys")},
                   {"same_user_id": True, "player_entities": n, "players_online": n},
                   source="client status/summary user ids, server /debug/entities and /status at the end, redis",
                   sampling="end of run", rationale="a reconnecting device must come back as the same user with one "
                   "entity, and the old session must not linger as a duplicate")


def check_memory_growth(ev, a):
    rows = [r for r in ev["server"]["container"] if r.get("st") is not None and r.get("mem_bytes")]
    if len(rows) < 3:
        return _inconclusive("fewer than 3 container samples", source="docker stats")
    xs = [r["st"] / 60.0 for r in rows]
    ys = [r["mem_bytes"] / (1024 * 1024) for r in rows]
    slope = _slope(xs, ys)
    client_mem = {c["index"]: ((c["summary"] or {}).get("gc") or {}).get("max_used_memory_bytes") for c in ev["clients"]}
    ok = slope <= float(a.get("max_server_mib_per_min", 2.0))
    return _result(PASS if ok else FAIL, {"server_mib_per_min": round(slope, 3), "server_mib_first": round(ys[0], 1),
                                          "server_mib_last": round(ys[-1], 1), "client_max_used_memory_bytes": client_mem},
                   {"max_server_mib_per_min": a.get("max_server_mib_per_min", 2.0)},
                   source="docker stats MemUsage of the scratch game server (5 s), least-squares slope",
                   sampling=f"{len(rows)} samples", rationale="steady memory growth under a repeating load is a leak")


def check_entity_stability(ev, a):
    from array import array
    counts = array("l", (len(r["ents"]) for r in ev["server"]["entities"]
                         if r.get("st") is not None and r["st"] >= float(a.get("skip_first_s", 10))))
    if len(counts) < 10:
        return _inconclusive("too few samples", source="/debug/entities")
    q = max(1, len(counts) // 4)
    first = sum(counts[:q]) / q
    lastq = sum(counts[-q:]) / q
    growth = (lastq - first) / max(1.0, first)
    ok = growth <= float(a.get("max_growth_ratio", 0.1))
    return _result(PASS if ok else FAIL, {"first_quarter_mean": round(first, 1), "last_quarter_mean": round(lastq, 1),
                                          "growth_ratio": round(growth, 4)},
                   {"max_growth_ratio": a.get("max_growth_ratio", 0.1)}, source="/debug/entities count",
                   sampling="first vs last quarter of the run", rationale="entity count must not drift under a steady scenario")


def _slope(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return 0.0 if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def check_bots_joined(ev, a):
    b = ev["bots"]
    want = (ev["scenario"].get("bots") or {}).get("players", 0)
    if not want:
        return _result(INFO, None, None, source="loadtest", sampling="n/a", detail={"why": "no bots in this scenario"})
    if not b:
        return _inconclusive("loadtest.json missing", source="loadtest -json")
    client = b.get("client", {})
    joined, failed = client.get("players_joined"), client.get("players_failed")
    ok = joined == want and not failed
    return _result(PASS if ok else FAIL, {"joined": joined, "failed": failed, "verdict": (b.get("verdict") or {}).get("status")},
                   {"joined": want, "failed": 0}, source="backend/loadtest -json client block",
                   sampling="whole run", rationale="headless bots provide the network load; a level where they did not "
                   "all join measured fewer players than it claims",
                   artifacts=[str(ev["run_dir"] / "bots")])


def check_trajectory_bound(ev, a):
    """A client's server position stays within a bound during a window (collision against a wall)."""
    ids = _user_ids(ev)
    k = int(a["client"])
    t = ev["traj"].get(ids[k]) if k < len(ids) and ids[k] else None
    if t is None:
        return _inconclusive("no server trajectory for the client", source="/debug/entities")
    lo, hi = float(a.get("t0", 0)), float(a.get("t1", ev["scenario"].get("duration_s", 0)))
    axis = a["axis"]
    vals = [v for st, v in zip(t["st"], t[axis]) if lo <= st <= hi]
    if not vals:
        return _inconclusive("no samples in window", source="/debug/entities")
    mx, mn = max(vals), min(vals)
    ok = (a.get("max") is None or mx <= float(a["max"])) and (a.get("min") is None or mn >= float(a["min"])) and          (a.get("reach_at_least") is None or mx >= float(a["reach_at_least"]))
    return _result(PASS if ok else FAIL, {"max": round(mx, 3), "min": round(mn, 3)},
                   {k2: a.get(k2) for k2 in ("max", "min", "reach_at_least")},
                   source=f"server /debug/entities {axis} of client {k}", sampling=f"window {lo}-{hi} s",
                   rationale=a.get("rationale", "server-side collision keeps the player inside the walls while the "
                                                "input keeps pushing into them"))


CHECKS = {
    "trajectory_bound": check_trajectory_bound,
    "clients_in_world": check_clients_in_world,
    "distinct_user_ids": check_distinct_user_ids,
    "same_game_server": check_same_game_server,
    "players_online": check_players_online,
    "redis": check_redis,
    "clients_completed": check_clients_completed,
    "client_log_clean": check_client_log_clean,
    "inputs_consumed": check_inputs_consumed,
    "position_divergence": check_position_divergence,
    "render_jumps": check_render_jumps,
    "snapshot_cadence": check_snapshot_cadence,
    "frame_time": check_frame_time,
    "server_tick": check_server_tick,
    "kcp_health": check_kcp_health,
    "snapshot_update_gap": check_snapshot_update_gap,
    "enemy_crowding": check_enemy_crowding,
    "enemy_pursuit": check_enemy_pursuit,
    "spawn_overlap": check_spawn_overlap,
    "enemy_server_speed": check_enemy_server_speed,
    "enemy_render_speed": check_enemy_render_speed,
    "combat_effect": check_combat_effect,
    "reconnect": check_reconnect,
    "memory_growth": check_memory_growth,
    "entity_stability": check_entity_stability,
    "bots_joined": check_bots_joined,
}


def check_host_quiet(ev, a):
    """INFO: host-wide stalls seen during the run (several client processes stalling at once)."""
    stalls = host_stalls(ev)
    quiet = (ev["meta"].get("provenance") or {}).get("host_quiet") or {}
    return _result(INFO, {"host_stalls": len(stalls),
                          "clients_with_frames": sum(1 for c in ev["clients"] if c.get("frames")),
                          "load_start": quiet.get("load_start") or ev["meta"].get("host_load_at_start"),
                          "load_end": quiet.get("load_end")},
                   None,
                   source="client frames.csv, frames >= 250 ms ending within 250 ms in >= 2 processes",
                   sampling="every frame", detail={"stalls": [(round(a, 2), round(b, 2), c) for a, b, c in stalls[:20]]},
                   rationale="a stall shared by separate processes is the host, not the game; checks it explains are "
                             "INCONCLUSIVE, and the run should be repeated on a quiet host")


CHECKS["host_quiet"] = check_host_quiet


def check_provenance(ev, a):
    """The run directory matches the provenance its run record carries (lab/provenance.py): every
    required field is present, the run id is the directory's, and the scenario, the evidence files
    and the client summaries are the ones written by this run. Any problem is INCONCLUSIVE, so a
    stale, copied or incomplete run can never grade PASS."""
    problems = provenance.verify(ev["run_dir"], ev["meta"], ev["scenario"], ev["clients"])
    prov = ev["meta"].get("provenance") or {}
    measured = {"run_id": prov.get("run_id"), "factory": (prov.get("factory") or {}).get("sha"),
                "server": (prov.get("server") or {}).get("sha"),
                "server_image": (prov.get("server") or {}).get("image_id"),
                "server_image_revision": ((prov.get("server") or {}).get("image_revision")
                                          if (prov.get("server") or {}).get("label_supported") is not False
                                          else "label unsupported"),
                "client": (prov.get("client") or {}).get("sha"), "netcode": (prov.get("netcode") or {}).get("sha"),
                "player_exe": ((prov.get("player") or {}).get("exe_sha256") or "")[:16] or None,
                "scenario": (prov.get("scenario") or {}).get("id"),
                "scenario_version": (prov.get("scenario") or {}).get("version"),
                "evidence_files": len(prov.get("manifest") or {})}
    return _result(INCONCLUSIVE if problems else PASS, measured, "complete and matching the run directory",
                   source="run.json provenance vs the files in the run directory", sampling="whole run",
                   rationale="evidence is only evidence for what it was recorded against; an analysis of a run whose "
                             "provenance is missing or does not match cannot vouch for any commit",
                   detail={"problems": problems}, artifacts=[str(ev["run_dir"] / "run.json")])


CHECKS["provenance"] = check_provenance

# Appended to every evaluation when the scenario does not list them.
ALWAYS = (("provenance", "run provenance (commits, image, player, scenario, evidence hashes)"),
          ("host_quiet", "host-wide stalls (environment)"))


def evaluate(ev: dict) -> list[dict]:
    out = []
    for a in ev["scenario"].get("assertions", []):
        fn = CHECKS.get(a.get("check"))
        if fn is None:
            out.append({"id": a.get("id"), "check": a.get("check"), **_inconclusive(
                f"unknown check '{a.get('check')}'", source="scenario")})
            continue
        failed_kills = _failed_debug_kills(ev) if a.get("requires_debug_kill") else []
        if a.get("requires_debug_kill") and (failed_kills or not _debug_kills(ev)):
            # The assertion depends on a scripted kill the server did not confirm: it cannot pass.
            out.append({"id": a["id"], "check": a["check"], "title": a.get("title", ""), **_inconclusive(
                "depends on debug_kill, which " + ("did not run" if not _debug_kills(ev) else
                                                   f"failed: {failed_kills}"), source="disruptions.ndjson")})
            continue
        try:
            res = fn(ev, a)
        except Exception as exc:  # a broken check is INCONCLUSIVE, never a silent PASS
            res = _inconclusive(f"check raised {type(exc).__name__}: {exc}", source=a.get("check"))
        if a.get("informational") and res["status"] in (PASS, FAIL):
            res["detail"]["would_be"] = res["status"]
            res["status"] = INFO
        out.append({"id": a["id"], "check": a["check"], "title": a.get("title", ""), **res})
    listed = {a.get("check") for a in ev["scenario"].get("assertions", [])}
    for check, title in ALWAYS:
        if check not in listed:
            out.append({"id": check, "check": check, "title": title, **CHECKS[check](ev, {})})
    return out


def overall(results: list[dict], harness_error: str | None = None) -> str:
    if harness_error:
        return INCONCLUSIVE
    statuses = [r["status"] for r in results]
    if FAIL in statuses:
        return FAIL
    if INCONCLUSIVE in statuses or not statuses:
        return INCONCLUSIVE
    if informational_breaches(results):
        return PASS_WITH_WARNINGS
    return PASS


def informational_breaches(results: list[dict]) -> list[dict]:
    """Informational assertions whose own verdict was FAIL (detail.would_be): reported as INFO, but
    they keep the run from a clean PASS."""
    return [r for r in results if r.get("status") == INFO and (r.get("detail") or {}).get("would_be") == FAIL]


def qualifications(results: list[dict], meta: dict | None = None) -> list[dict]:
    """What qualifies the verdict, for the top of the report: informational breaches, and host
    load - host-wide stalls seen in the run, or CPU load at start/end >= HOST_LOAD_WARN_PCT. Host
    qualifications do not change the outcome (the timing checks a stall explains are already
    INCONCLUSIVE); they say the run's timing numbers came from a busy host."""
    out = [{"kind": "informational_breach", "id": r.get("id"),
            "text": f"`{r.get('id')}` would be FAIL (informational): measured {r.get('measured')}, "
                    f"threshold {r.get('threshold')}"} for r in informational_breaches(results)]
    host = next((r for r in results if r.get("check") == "host_quiet"), None)
    m = (host or {}).get("measured") or {}
    if m.get("host_stalls"):
        out.append({"kind": "host", "text": f"{m['host_stalls']} host-wide stall(s) (frames >= 250 ms in two or more "
                                           "player processes at once): timing checks they explain are INCONCLUSIVE; "
                                           "rerun on a quiet host for representative timing"})
    for when in ("load_start", "load_end"):
        load = (m.get(when) or {}).get("cpu_load_pct") if isinstance(m.get(when), dict) else None
        if load is not None and float(load) >= HOST_LOAD_WARN_PCT:
            out.append({"kind": "host", "text": f"host CPU load {load:.0f} % at {when.split('_')[1]} "
                                               f"(>= {HOST_LOAD_WARN_PCT:.0f} %): other processes shared the host"})
    return out


# --------------------------------------------------------------------------- readiness checks (COVERAGE.md F2-F6)

def _csv_dicts(path):
    """Rows of a CSV file as dicts; [] when it does not exist."""
    import csv
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except (OSError, TypeError):
        return []


def _num_or_none(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _session_starts(c) -> list:
    """Player-clock seconds at which each session reached InWorld (net_state events). A client
    that only logged `in_world` has one session from the start."""
    starts = [e["t"] for e in c["events"] if e.get("event") == "net_state" and e.get("state") == "InWorld"
              and e.get("t") is not None]
    return sorted(starts)


def _order_stats(rows, starts):
    """rows: [(t_seconds, tick)] in receive order. Backward steps and duplicates per session."""
    backward, dups, sessions = [], 0, set()
    seen, newest, cur = set(), None, None
    for t, tick in rows:
        sess = bisect_right(starts, t) - 1 if starts else 0
        sessions.add(sess)
        if sess != cur:
            cur, seen, newest = sess, set(), None
        if tick in seen:
            dups += 1
        elif newest is not None and tick < newest:
            if len(backward) < 20:
                backward.append({"t": round(t, 3), "tick": tick, "after": newest, "session": sess})
            else:
                backward.append(None)
        seen.add(tick)
        newest = tick if newest is None else max(newest, tick)
    return {"rows": len(rows), "sessions": len(sessions), "backward": len(backward),
            "duplicates": dups, "examples": [b for b in backward if b][:10]}


def check_snapshot_order(ev, a):
    """Per client, received world ticks never go backwards inside one session, and no tick is
    received twice. A session starts at each net_state InWorld (join, reconnect); a new session
    may restart the tick sequence (a restarted server starts again from its first tick)."""
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client snapshots.ndjson")
    min_rows = int(a.get("min_snapshots", 10))
    per, missing, backward, dups = {}, [], 0, 0
    for c in ev["clients"]:
        starts = _session_starts(c)
        sources = {}
        rows = [(float(x["t"]), int(x["tick"])) for x in c["snapshots"]
                if x.get("t") is not None and x.get("tick") is not None]
        if rows:
            sources["snapshots.ndjson"] = _order_stats(rows, starts)
        drows = []
        for r in _csv_dicts(c.get("delivery_csv")):
            tick, t_us = _num_or_none(r.get("world_tick")), _num_or_none(r.get("applied_us"))
            if tick is not None and t_us is not None:
                drows.append((t_us / 1e6, int(tick)))
        if drows:
            sources["delivery.csv"] = _order_stats(drows, starts)
        if not sources or max(s["rows"] for s in sources.values()) < min_rows:
            missing.append(c["index"])
        per[c["index"]] = sources
        backward += max((s["backward"] for s in sources.values()), default=0)
        dups += max((s["duplicates"] for s in sources.values()), default=0)
    if missing:
        return _inconclusive(f"fewer than {min_rows} received snapshots for client(s) {missing}",
                             source="client snapshots.ndjson / delivery.csv")
    ok = backward <= int(a.get("max_backward", 0)) and dups <= int(a.get("max_duplicates", 0))
    return _result(PASS if ok else FAIL, {"backward": backward, "duplicates": dups},
                   {"max_backward": a.get("max_backward", 0), "max_duplicates": a.get("max_duplicates", 0)},
                   source="client snapshots.ndjson (tick, main-thread t) and C2 delivery.csv (world_tick, applied_us); "
                          "sessions from events.ndjson net_state InWorld",
                   sampling="every received snapshot",
                   rationale="the server's world tick only grows within one connection; a tick received out of order "
                             "or twice is applied out of order or twice (stale state, interpolation running backwards)",
                   detail={"per_client": per},
                   artifacts=[str(c["dir"] / "snapshots.ndjson") for c in ev["clients"]])


def _map_source(ev, a, map_id):
    """(map dict | None, source) for content/maps/<map_id>.json at the server commit the run used
    (`git show <sha>:...`), falling back to the server checkout's working tree."""
    import json as _json
    import subprocess
    meta = ev["meta"] or {}
    repo = a.get("server_repo") or (meta.get("config") or {}).get("server_repo")
    if not repo:
        return None, "no server_repo in run.json config"
    sha = ((meta.get("provenance") or {}).get("server") or {}).get("sha") or ((meta.get("repos") or {}).get("server") or {}).get("head")
    rel = f"backend/content/maps/{map_id}.json"
    if sha:
        try:
            res = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{rel}"], capture_output=True, timeout=30)
            if res.returncode == 0:
                return _json.loads(res.stdout.decode("utf-8")), f"{rel} at server {sha[:10]}"
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    path = Path(repo) / rel
    if path.exists():
        try:
            return _json.loads(path.read_text(encoding="utf-8")), f"{path} (working tree; commit {sha or 'unknown'} not readable)"
        except ValueError:
            return None, f"{path} is not valid JSON"
    return None, f"{rel} does not exist (server {str(sha)[:10] if sha else 'commit unknown'})"


def _run_map_id(ev):
    """The map the scratch server ran: GAMESERVER_MAP_ID the stack was started with (run.json
    stack.env), checked against the scenario and the server's own registration (redis
    servers:map:<map> members, taken mid-run). /status does not report a map id."""
    sc_map = ev["scenario"].get("map")
    env_map = (((ev["meta"] or {}).get("stack") or {}).get("env") or {}).get("GAMESERVER_MAP_ID")
    members = ev["redis"].get("map_members") or []
    problems = []
    if env_map and sc_map and env_map != sc_map:
        problems.append(f"stack GAMESERVER_MAP_ID {env_map} != scenario map {sc_map}")
    if ev["redis"] and not members:
        problems.append(f"no server registered under servers:map:{sc_map}")
    return env_map or sc_map, {"scenario": sc_map, "stack_env": env_map, "registered": members}, problems


def _status_map_bounds(ev):
    """/status map_id and map_bounds (rpg-mmo-server S4) from the last sample that has them, as
    {"map_id", "bounds": {minX, minY, maxX, maxY}, "source"}; None on a server without the hook."""
    for r in reversed(ev["server"]["status"]):
        mb = r.get("map_bounds")
        if isinstance(mb, dict) and all(k in mb for k in ("min_x", "min_y", "max_x", "max_y")):
            return {"map_id": r.get("map_id"), "source": mb.get("source"),
                    "bounds": {"minX": mb["min_x"], "minY": mb["min_y"], "maxX": mb["max_x"], "maxY": mb["max_y"]}}
    return None


def check_enemy_bounds(ev, a):
    """Every live enemy the server reports stays inside the map's bounds (content/maps/<map>.json).
    Enemy footprints inside a blocking box (top more than the 0.4 step height above the ground,
    content/README.md 'Map geometry') are reported; they fail only with obstacles_are_failure."""
    map_id, where, problems = _run_map_id(ev)
    reported = _status_map_bounds(ev)
    if reported is not None:
        # rpg-mmo-server hook S4: the bounds the running server clamps to, map file or configured size.
        if reported["map_id"] and map_id and reported["map_id"] != map_id:
            return _inconclusive(f"/status map_id {reported['map_id']} != configured {map_id}", source="/status")
        map_id = reported["map_id"] or map_id
        where["status_map_id"] = reported["map_id"]
        problems = [p for p in problems if not p.startswith("no server registered")]
        geo, src = {"bounds": reported["bounds"], "boxes": []}, f"/status map_bounds ({reported['source']})"
        file_geo, _ = _map_source(ev, a, map_id)
        if file_geo:
            geo["boxes"] = file_geo.get("boxes", [])  # obstacles are only in the map file
    if problems:
        return _inconclusive("; ".join(problems), source="run.json stack env, redis.json")
    if reported is None:
        geo, src = _map_source(ev, a, map_id)
    if geo is None:
        return _inconclusive(f"map {map_id}: {src}. Without a map file the server uses flat bounds from "
                             "--map-width/--map-height (GAMESERVER_MAP_WIDTH/HEIGHT or GameConstants defaults), and this "
                             "server's /status has no map_bounds (hook S4); bounds unknown", source="backend/content/maps")
    b = geo.get("bounds") or {}
    if not all(k in b for k in ("minX", "minY", "maxX", "maxY")):
        return _inconclusive(f"{src} has no complete bounds", source=src)
    eps = float(a.get("tolerance", 0.01))
    step = float(a.get("step_height", 0.4))
    blocking = [x for x in geo.get("boxes", []) if float(x.get("maxZ", 0)) > step]
    lo, hi = _window(ev)
    outside, inside_box, n = [], [], 0
    for r in ev["server"]["entities"]:
        if r.get("st") is None or not lo <= r["st"] <= hi:
            continue
        for e in _alive_enemies(r):
            n += 1
            x, y = e[2], e[3]
            if x < b["minX"] - eps or x > b["maxX"] + eps or y < b["minY"] - eps or y > b["maxY"] + eps:
                if len(outside) < 20:
                    outside.append({"st": round(r["st"], 2), "id": e[0], "x": x, "y": y})
                else:
                    outside.append(None)
            for box in blocking:
                if box["minX"] + eps < x < box["maxX"] - eps and box["minY"] + eps < y < box["maxY"] - eps:
                    if len(inside_box) < 20:
                        inside_box.append({"st": round(r["st"], 2), "id": e[0], "x": x, "y": y, "box": box})
                    else:
                        inside_box.append(None)
    if n < int(a.get("min_samples", 50)):
        return _inconclusive(f"{n} live-enemy positions in the window (need {a.get('min_samples', 50)})",
                             source="/debug/entities")
    status = FAIL if outside else PASS
    if inside_box and status == PASS:
        status = FAIL if a.get("obstacles_are_failure") else INFO
    return _result(status, {"enemy_positions": n, "outside_bounds": len(outside), "inside_blocking_box": len(inside_box)},
                   {"bounds": b, "tolerance": eps, "blocking_boxes": len(blocking),
                    "obstacles_are_failure": bool(a.get("obstacles_are_failure"))},
                   source=f"server /debug/entities enemy positions vs {src}",
                   sampling=f"{ev['scenario'].get('server_sample_hz')} Hz server samples",
                   rationale="the server clamps positions into the map bounds (content/README.md); an enemy outside them "
                             "is a movement or separation step that escaped the clamp. Boxes are reported, not judged by "
                             "default: whether enemies collide with static boxes is a gameplay rule"
                             + ("" if blocking else "; this map defines no blocking box"),
                   detail={"map": map_id, "map_evidence": where, "outside": [o for o in outside if o],
                           "inside_box": [o for o in inside_box if o]},
                   artifacts=[str(ev["run_dir"] / "server" / "entities.ndjson")])


_BUDGET = re.compile(r"\bbudget=(\d+)")


def check_enemy_budget(ev, a):
    """The live enemy count never exceeds the hard enemy budget the server reports in force
    (/status enemy_ai `budget=N`, GAMESERVER_ENEMY_BUDGET, rpg-mmo-server#468). The lab chooses no
    budget; it records the one the server ran with."""
    rows = _status_in_window(ev)
    if not rows:
        return _inconclusive("no /status samples inside the scenario window", source="/status enemy_ai")
    ai = [r.get("enemy_ai") for r in rows if r.get("enemy_ai") is not None]
    if not ai:
        return _inconclusive("/status has no enemy_ai field", source="/status enemy_ai")
    if all(x == "off" for x in ai):
        return _inconclusive("enemy AI is off in this run", source="/status enemy_ai")
    budgets = sorted({int(m.group(1)) for x in ai for m in [_BUDGET.search(x)] if m})
    if not budgets:
        return _inconclusive("/status enemy_ai does not report budget=N (server hook: echo GAMESERVER_ENEMY_BUDGET)",
                             source="/status enemy_ai")
    counted = [r for r in rows if r.get("enemies_alive") is not None]
    if len(counted) < int(a.get("min_samples", 10)):
        return _inconclusive(f"{len(counted)} /status samples with enemies_alive (need {a.get('min_samples', 10)})",
                             source="/status enemies_alive")
    over, over_cap = [], 0
    max_alive = 0
    for r in counted:
        m = _BUDGET.search(r.get("enemy_ai") or "")
        budget = int(m.group(1)) if m else budgets[-1]
        alive = int(r["enemies_alive"])
        max_alive = max(max_alive, alive)
        if alive > budget:
            over.append({"st": round(r["_st"], 1), "enemies_alive": alive, "budget": budget})
        if r.get("enemy_ai_max_now") is not None and alive > int(r["enemy_ai_max_now"]):
            over_cap += 1
    lo, hi = _window(ev)
    probe_max = max((len(_alive_enemies(r)) for r in ev["server"]["entities"]
                     if r.get("st") is not None and lo <= r["st"] <= hi), default=None)
    if probe_max is not None and probe_max > min(budgets):
        over.append({"source": "/debug/entities", "max_alive": probe_max, "budget": min(budgets)})
    return _result(FAIL if over else PASS,
                   {"max_enemies_alive": max_alive, "max_alive_debug_entities": probe_max, "budget": budgets,
                    "budget_reached": max_alive >= min(budgets), "samples_over_cap_now": over_cap},
                   {"max": "budget reported by /status enemy_ai"},
                   source="/status enemies_alive and enemy_ai budget=N; /debug/entities live mobs",
                   sampling=f"1 Hz /status ({len(counted)} samples), server entity samples",
                   rationale="the hard budget is the ceiling of the enemy population whatever the player count "
                             "(cap = min(MAX + MAX_PER_PLAYER x players, BUDGET)). budget_reached false means the run "
                             "never pushed the population to the budget, so PASS only says it was not exceeded. "
                             "Samples above enemy_ai_max_now are reported, not judged: that cap falls when players leave "
                             "and live enemies are not removed for it",
                   detail={"over": over[:20]},
                   artifacts=[str(ev["run_dir"] / "server" / "status.ndjson")])


# Netcode InterpolationConfig.Default (Runtime/Interpolation/InterpolationConfig.cs, the client's
# DotsWorldBridge uses Default): the render clock runs TargetDelay behind the newest received
# tick and may extrapolate MaxExtrapolation past it before remote entities hold still.
INTERP_TARGET_DELAY_MS = 100.0
INTERP_MAX_EXTRAPOLATION_MS = 50.0


def _tick_hz(ev, a) -> float | None:
    """Server base tick rate (world ticks advance at it): the assertion's, else /status."""
    if a.get("tick_hz"):
        return float(a["tick_hz"])
    rows = [r for r in ev["server"]["status"] if r.get("tick_rate") or r.get("sim_critical_hz")]
    return float(rows[-1].get("tick_rate") or rows[-1]["sim_critical_hz"]) if rows else None


def check_render_freshness(ev, a):
    """How far the render clock runs past the newest snapshot it has consumed, per rendered frame
    (C2 render.csv, schema rpg.testlab.delivery.v2: render_tick, clock_newest_tick, clock_source).

    overrun_ms = (render_tick - clock_newest_tick) / tick_hz * 1000, 0 when the clock is behind the
    newest tick (the normal case: TargetDelay behind). A positive overrun means the interpolator has
    no sample ahead and extrapolates; past MaxExtrapolation (50 ms, Netcode InterpolationConfig.Default,
    which the client uses) remote entities are held still: a visible freeze. p99 overrun <= 50 ms.
    snapshot_age_ms (receive age of the newest snapshot) is reported alongside. A v1 render.csv has
    an empty render_tick in this client (the ECS clock is never fed on the untimed SetState path), so
    v1 evidence is INCONCLUSIVE. Frames in host-wide stalls are set aside (INCONCLUSIVE when only they
    would fail it)."""
    import csv
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client render.csv")
    hz = _tick_hz(ev, a)
    if not hz:
        return _inconclusive("server tick rate unknown (/status tick_rate, sim_critical_hz)", source="/status")
    bound = float(a.get("max_extrapolation_ms", INTERP_MAX_EXTRAPOLATION_MS))
    dur = float(ev["scenario"].get("duration_s", 0))
    excl = [(float(w[0]), float(w[1])) for w in a.get("exclude_s", [])]
    stalls = host_stalls(ev)
    per, missing, worst_all, worst_quiet = {}, {}, [], []
    for c in ev["clients"]:
        start = (c["summary"] or {}).get("start_realtime")
        over, quiet, ages, sources, frames = [], [], [], {}, 0
        try:
            with open(c.get("render_csv") or "", encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    t_us = _num_or_none(r.get("t_us"))
                    if t_us is None or start is None:
                        continue
                    st = t_us / 1e6 - start
                    if not 0 <= st <= dur or any(e0 <= st <= e1 for e0, e1 in excl):
                        continue
                    frames += 1
                    age = _num_or_none(r.get("snapshot_age_ms"))
                    if age is not None:
                        ages.append(age)
                    rt, newest = _num_or_none(r.get("render_tick")), _num_or_none(r.get("clock_newest_tick"))
                    if rt is None or newest is None:
                        continue
                    src = r.get("clock_source") or "unnamed (v1)"
                    sources[src] = sources.get(src, 0) + 1
                    o = max(0.0, (rt - newest) / hz * 1000.0)
                    over.append(o)
                    if not _in_stall(stalls, st, st, slack=0.3, after=1.0):
                        quiet.append(o)
        except OSError:
            pass
        if not over:
            missing[c["index"]] = ("no render.csv" if frames == 0 else
                                   f"{frames} frames, none with a render_tick (v1 schema or no readable clock)")
            continue
        p99, p99q = util.percentile(over, 99), util.percentile(quiet, 99) if quiet else None
        per[c["index"]] = {"frames": len(over), "clock_source": sources, "overrun_p99_ms": round(p99, 1),
                           "overrun_max_ms": round(max(over), 1),
                           "overrun_p99_outside_host_stalls_ms": None if p99q is None else round(p99q, 1),
                           "frames_frozen": sum(1 for o in over if o > bound),
                           "snapshot_age_p50_ms": round(util.percentile(ages, 50), 1) if ages else None,
                           "snapshot_age_p99_ms": round(util.percentile(ages, 99), 1) if ages else None}
        worst_all.append(p99)
        worst_quiet.append(p99q if p99q is not None else p99)
    if missing:
        return _inconclusive(f"no render clock in C2 render.csv for client(s) {missing}", source="client render.csv")
    fails, fails_quiet = max(worst_all) > bound, max(worst_quiet) > bound
    status = FAIL if fails_quiet else (INCONCLUSIVE if fails else PASS)
    return _result(status, per, {"overrun_p99_ms": bound, "formula": "max(0, render_tick - clock_newest_tick) / tick_hz",
                                 "tick_hz": hz, "max_extrapolation_ms": bound},
                   source="C2 render.csv v2 render_tick and clock_newest_tick (WorldViewBinder clock)",
                   sampling="every rendered frame in the scenario window",
                   rationale="the render clock runs TargetDelay behind the newest snapshot; when snapshots stop it "
                             "catches up and extrapolates, and past MaxExtrapolation it holds remote entities still. "
                             "The overrun is read from the clock that drew the frame, so it is a freeze the player saw",
                   artifacts=[str(c["dir"] / "render.csv") for c in ev["clients"]])


# Derived from every stored run of 2026-10-21/22 (.testlab-runs/reanalysis/T16-FAC-V2/
# prediction-bound-derivation.log): with respawn snaps explained, the fixed builds
# (verify-netcode-77cbc97, 7e6c9d8, 5fa8f37) leave at most 2 unexplained snaps per client-minute
# (S07 20261022T091437Z-S07-c5hc client 2: 2 in 60 s, under bot load; both 1 h soaks: 0-3 per hour),
# while in every run of the pre-fix builds (testlab, testlab-before-fix) the worst client has at
# least 7.5 (S10 20261022T054359Z-S10-g0tz client 0: 5 in 40 s; typical 15-30).
PREDICTION_UNEXPLAINED_BOUND = 4.0
BOUND_JUSTIFICATION = ("Bound 4 unexplained snaps per client-minute: twice the worst fixed-build rate (2.0, S07 c5hc) "
                       "and about half the lowest pre-fix rate (7.5, S10 g0tz), from every stored run of 2026-10-21/22.")


def _server_teleports(ev, uid, max_speed):
    """[(tick_lo, tick_hi)] server-tick ranges in which the server moved player `uid` other than by
    walking: a respawn (dead -> alive, or HP from below half to full) or a step longer than it can
    walk between two probe samples (1.5 x max_speed + 0.2). Read from /debug/entities rows."""
    out, prev = [], None
    for r in ev["server"]["entities"]:
        tick, st = r.get("tick"), r.get("st")
        if tick is None or st is None:
            continue
        e = next((x for x in r["ents"] if x[0] == uid), None)
        if e is None:
            prev = None
            continue
        if prev is not None and tick > prev[0]:
            ptick, pst, px, py, php, pdead = prev
            mx = e[5] or 0
            respawn = (pdead and not e[6]) or (mx > 0 and php is not None and e[4] is not None
                                                and php < 0.5 * mx and e[4] >= mx)
            jump = math.hypot(e[2] - px, e[3] - py) > 1.5 * max_speed * max(st - pst, 1e-3) + 0.2
            if respawn or jump:
                out.append((ptick, tick))
        prev = (tick, st, e[2], e[3], e[4], e[6])
    return out


def _snap_steps(c):
    """[(world_tick_before, world_tick_at, n)] for each rise of the cumulative pred.snaps counter
    between two consecutive samples (world_tick = newest snapshot the client had then)."""
    out, prev = [], None
    for s in c["samples"]:
        p = s.get("pred") or {}
        if p.get("snaps") is None or s.get("world_tick") is None:
            continue
        cur = (s["world_tick"], int(p["snaps"]))
        if prev is not None and cur[1] > prev[1]:
            out.append((prev[0], cur[0], cur[1] - prev[1]))
        prev = cur
    return out


def check_prediction_bound(ev, a):
    """Local-prediction hard snaps that NO server teleport explains stay under a bound taken from
    measured runs.

    A teleport must snap: the server respawns a dead player 1-2.4 units away (PlayerRespawnSystem;
    rpg-mmo-server, T17-NET-IDLESNAP: every client snap in S02, S04 and both 1 h soaks of 2026-10-22
    matched one server respawn of that player). So each rise of the client's pred.snaps (20 Hz
    samples) is matched by world tick to a server-side respawn or non-walkable step of the same
    player (/debug/entities, 5 Hz) whose tick range, widened by match_window_ticks (default 60 =
    1 s at 60 Hz: probe spacing 12 ticks + snapshot latency), overlaps the snap's tick range. Matched
    snaps are 'explained'; the rest are prediction errors and are graded. Snaps after the last sample
    (summary count above the last sample) count as unexplained.

    Bound: see BOUND_JUSTIFICATION below (max_unexplained_per_client_min). max_correction is reported,
    not judged: it includes the teleports."""
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client summary.json prediction")
    bound = float(a.get("max_unexplained_per_client_min", PREDICTION_UNEXPLAINED_BOUND))
    min_s = float(a.get("min_seconds", 20.0))  # S03, the shortest moving scenario, is 22 s
    win = int(a.get("match_window_ticks", 60))
    max_speed = float(ev["scenario"].get("jump", {}).get("max_speed", 6.0))
    ids = _user_ids(ev)
    per, missing, over = {}, [], []
    for c in ev["clients"]:
        s = c["summary"] or {}
        p, secs = s.get("prediction") or {}, s.get("scenario_seconds")
        if not p.get("present") or p.get("snaps") is None or not secs or secs < min_s:
            missing.append(f"{c['index']}: no prediction counters over >= {min_s:.0f} s")
            continue
        steps = _snap_steps(c)
        located = any((x.get("pred") or {}).get("snaps") is not None and x.get("world_tick") is not None
                      for x in c["samples"])
        if p["snaps"] > 0 and not located:
            missing.append(f"{c['index']}: snaps not locatable (no per-sample pred.snaps / world_tick)")
            continue
        uid = ids[c["index"]]
        tps = _server_teleports(ev, uid, max_speed) if uid else []
        explained = 0
        for t0, t1, n in steps:
            if any(lo - win <= t1 and t0 <= hi + win for lo, hi in tps):
                explained += n
        unexplained = max(0, p["snaps"] - explained)
        rate = unexplained / (secs / 60.0)
        per[c["index"]] = {"snaps": p["snaps"], "explained_by_server_teleport": explained,
                           "unexplained": unexplained, "server_teleports": len(tps), "seconds": round(secs, 1),
                           "unexplained_per_min": round(rate, 2), "max_correction": p.get("max_correction")}
        if rate > bound or (a.get("max_unexplained") is not None and unexplained > int(a["max_unexplained"])):
            over.append(c["index"])
        want = (a.get("expected_explained") or {}).get(str(c["index"]))
        if want is not None and explained != int(want):
            per[c["index"]]["expected_explained"] = int(want)
            over.append(c["index"])
    if missing:
        return _inconclusive("; ".join(missing), source="client summary.json / samples.ndjson prediction")
    return _result(FAIL if over else PASS, per, {"max_unexplained_per_client_min": bound,
                                                 "max_unexplained": a.get("max_unexplained"),
                                                 "expected_explained": a.get("expected_explained"),
                                                 "match_window_ticks": win},
                   source="client samples.ndjson pred.snaps rises vs server /debug/entities respawns and teleports "
                          "of the same player, matched by world tick",
                   sampling="20 Hz client samples, 5 Hz server samples",
                   rationale="a hard snap the server did not cause is a prediction error the player sees as a jump; "
                             "snaps from respawns are correct and are reported, not judged. " + BOUND_JUSTIFICATION,
                   detail={"over": over})



_RATE_FIELDS = {"SIM_CRITICAL_HZ": "sim_critical_hz", "SIM_WORLD_HZ": "sim_world_hz",
                "SIM_BACKGROUND_HZ": "sim_background_hz"}


def check_server_config(ev, a):
    """The server ran with the settings the scenario asked for: each SIM_* rate in server_env (and
    any `expect` {status_field: value}) equals what /status reports in every sample. A scenario
    whose setting did not reach the server has not tested what it claims: INCONCLUSIVE."""
    want = {_RATE_FIELDS[k]: int(v) for k, v in (ev["scenario"].get("server_env") or {}).items() if k in _RATE_FIELDS}
    want.update(a.get("expect") or {})
    if not want:
        return _inconclusive("the scenario sets nothing this check can compare", source="scenario server_env")
    rows = _status_in_window(ev)
    if not rows:
        return _inconclusive("no /status samples inside the scenario window", source="/status")
    seen = {k: sorted({r.get(k) for r in rows}, key=str) for k in want}
    wrong = {k: seen[k] for k, v in want.items() if seen[k] != [v]}
    res = _result(PASS if not wrong else INCONCLUSIVE, seen, want, source="/status", sampling=f"{len(rows)} samples",
                  rationale="evidence about a configuration only counts when that configuration was in force",
                  detail={"mismatch": wrong})
    return res


CHECKS.update({
    "snapshot_order": check_snapshot_order,
    "enemy_bounds": check_enemy_bounds,
    "enemy_budget": check_enemy_budget,
    "render_freshness": check_render_freshness,
    "prediction_bound": check_prediction_bound,
    "server_config": check_server_config,
})


# --------------------------------------------------------------------------- client hooks C1-C6 (T16)

def _expected_tick_hz(ev):
    rows = _status_in_window(ev) or ev["server"]["status"]
    vals = sorted({float(r.get("tick_rate") or r.get("sim_critical_hz")) for r in rows
                   if r.get("tick_rate") or r.get("sim_critical_hz")})
    return vals


def check_tick_adoption(ev, a):
    """The client's predictor steps at the rate the server advertises (C1 hook: samples.ndjson
    pred.tick_hz, summary.json prediction.tick_hz) - JoinTokenResponse.tick_rate, which /status
    publishes as tick_rate (= SimulationRates.MovementHz). Every sample after the scenario start
    must match, so a reconnect that kept the old rate fails too (client fix 4544aab, Netcode#183)."""
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="samples.ndjson pred.tick_hz")
    want = _expected_tick_hz(ev)
    if not want:
        return _inconclusive("/status reports no tick_rate", source="/status tick_rate")
    if len(want) > 1:
        return _inconclusive(f"/status tick_rate changed during the run: {want}", source="/status tick_rate")
    hz = want[0]
    excl = [(float(w[0]), float(w[1])) for w in a.get("exclude_s", [])]
    per, missing, wrong = {}, [], 0
    for c in ev["clients"]:
        seen = {}
        for s in c["samples"]:
            st, p = s.get("st"), s.get("pred") or {}
            if st is None or st < 0 or p.get("tick_hz") is None or any(e0 <= st <= e1 for e0, e1 in excl):
                continue
            v = float(p["tick_hz"])
            seen[v] = seen.get(v, 0) + 1
        end = ((c["summary"] or {}).get("prediction") or {}).get("tick_hz")
        if not seen and end is None:
            missing.append(c["index"])
            continue
        bad = sum(n for v, n in seen.items() if abs(v - hz) > 1e-3) + (1 if end is not None and abs(float(end) - hz) > 1e-3 else 0)
        wrong += bad
        per[c["index"]] = {"samples": seen, "summary_tick_hz": end, "mismatches": bad}
    if missing:
        return _inconclusive(f"no predictor tick_hz from client(s) {missing} (player without hook C1, or no predictor)",
                         source="samples.ndjson pred.tick_hz")
    return _result(PASS if wrong == 0 else FAIL, per, {"tick_hz": hz},
                   source="client samples.ndjson pred.tick_hz and summary.json prediction.tick_hz vs /status tick_rate",
                   sampling="every client sample", detail={},
                   rationale="a predictor stepping at another rate than the server integrates at drifts from the "
                             "server path and is corrected again and again (rubber-banding)")


# Removed entities may still be drawn while the render clock (TargetDelay behind) has not passed
# their removal; TargetDelay + MaxExtrapolation is the longest that can legitimately take.
def check_entity_lifecycle(ev, a):
    """C3 hooks (events.ndjson entity_added / entity_removed / entities_reset) against the 20 Hz
    rendered samples:
    - despawn: an entity removed at time t (a despawn, or leaving the client's area of interest)
      is not in any rendered sample after t + TargetDelay + MaxExtrapolation (150 ms) + one sample
      period, unless its id was added again (AOI re-entry or reuse) - samples from the re-add frame
      on show the new entry;
    - id reuse: an id added again after a removal is first drawn at its own spawn position (the
      entity_added rx/ry within max_speed x 150 ms + 0.2 of its first snapshot's x/y), not where the
      previous entity was."""
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="events.ndjson entity_*")
    grace = (float(a.get("target_delay_ms", INTERP_TARGET_DELAY_MS)) +
             float(a.get("max_extrapolation_ms", INTERP_MAX_EXTRAPOLATION_MS))) / 1000.0
    sample_dt = 1.0 / max(1.0, float(ev["scenario"].get("sample_hz", 20)))
    max_speed = float(ev["scenario"].get("jump", {}).get("max_speed", 6.0))
    tol = max_speed * grace + 0.2
    lingering, reuse_bad, reuse_ok = [], [], 0
    removed_total, missing, duplicates = 0, [], []
    for c in ev["clients"]:
        # Compact, time-ordered entity events: (t, kind, id, frame, x, y, rx, ry).
        evs = sorted(((e["t"], e["event"], e.get("id"), e.get("frame"), e.get("x"), e.get("y"), e.get("rx"), e.get("ry"))
                      for e in c["events"] if e.get("event") in ("entity_added", "entity_removed", "entities_reset")
                      and e.get("t") is not None), key=lambda e: e[0])
        if not any(e[1] in ("entity_added", "entity_removed") for e in evs) or not c["samples"]:
            missing.append(c["index"])
            continue
        # For each event, the next entity_added of the same id or the next entities_reset after it
        # (one backward pass; the old forward scan was quadratic on a soak).
        nxt = [None] * len(evs)
        next_add, next_reset = {}, None
        for i in range(len(evs) - 1, -1, -1):
            t, kind, eid = evs[i][0], evs[i][1], evs[i][2]
            cand = next_add.get(eid)
            if next_reset is not None and (cand is None or next_reset < cand):
                cand = next_reset
            nxt[i] = cand
            if kind == "entity_added":
                next_add[eid] = i
            elif kind == "entities_reset":
                next_reset = i
        windows = {}      # id -> [lo, hi, re_frame, removal event index, resolved]
        queries = []      # (removal t, id, add event index): last drawn position before a reused id's removal
        removed_at = {}
        for i, (t, kind, eid, frame, x, y, rx, ry) in enumerate(evs):
            if kind == "entities_reset":
                removed_at.clear()
                continue
            if kind == "entity_removed":
                removed_total += 1
                removed_at[eid] = t
                j = nxt[i]
                hi = evs[j][0] if j is not None else float("inf")
                # The id may come back (AOI re-entry, or reuse). entity_added is written at the first
                # frame that draws it, and the 20 Hz sample of that same frame is stamped a little
                # earlier in the frame: a sample at or after the re-add frame shows the NEW entity.
                re_frame = evs[j][3] if j is not None and evs[j][1] == "entity_added" else None
                windows.setdefault(eid, []).append([t + grace + sample_dt, hi, re_frame, i, False])
            elif kind == "entity_added" and eid in removed_at and rx is not None:
                queries.append((removed_at[eid], eid, i))
                removed_at.pop(eid, None)
        queries.sort(key=lambda q: q[0])
        q_next, last_seen, prev_at = 0, {}, {}
        hits = {}
        for smp in c["samples"]:
            ids_ = [r[0] for r in smp.get("ents", [])]
            if len(ids_) != len(set(ids_)) and len(duplicates) < 20:
                duplicates.append({"client": c["index"], "t": smp.get("t"),
                                   "ids": sorted({i for i in ids_ if ids_.count(i) > 1})})
            t = smp.get("t")
            if t is None:
                continue
            # Positions "before the removal" are those of samples strictly earlier than it.
            while q_next < len(queries) and queries[q_next][0] <= t:
                rt, eid, i = queries[q_next]
                prev_at[i] = last_seen.get(eid)
                q_next += 1
            fr = smp.get("frame")
            for r in smp.get("ents", []):
                eid = r[0]
                last_seen[eid] = r
                for w in windows.get(eid, ()):
                    if not w[4] and w[0] < t < w[1] and not (w[2] is not None and fr is not None and fr >= w[2]):
                        w[4] = True
                        hits[w[3]] = (t, fr)
        while q_next < len(queries):
            rt, eid, i = queries[q_next]
            prev_at[i] = last_seen.get(eid)
            q_next += 1
        for i in sorted(hits):
            t_hit, fr = hits[i]
            lingering.append({"client": c["index"], "id": evs[i][2], "removed_t": round(evs[i][0], 3),
                              "still_drawn_t": round(t_hit, 3), "frame": fr})
        for rt, eid, i in sorted(queries, key=lambda q: q[2]):
            t, _, _, _, x, y, rx, ry = evs[i]
            prev = prev_at.get(i)
            d = math.hypot(rx - x, ry - y)
            row = {"client": c["index"], "id": eid, "t": round(t, 3), "first_drawn_from_spawn": round(d, 3),
                   "from_previous_entity": None if prev is None else round(math.hypot(rx - prev[3], ry - prev[4]), 3)}
            if d > tol:
                reuse_bad.append(row)
            else:
                reuse_ok += 1
    if missing:
        return _inconclusive(f"no entity_added/entity_removed events or samples for client(s) {missing} "
                             "(player without hook C3)", source="events.ndjson entity_*")
    if removed_total == 0 and a.get("require_removal", True):
        return _inconclusive("no entity was removed during the run: despawn not exercised", source="events.ndjson")
    return _result(FAIL if lingering or reuse_bad or duplicates else PASS,
                   {"removed": removed_total, "lingering": len(lingering), "reused_ids_checked": reuse_ok + len(reuse_bad),
                    "reused_drawn_elsewhere": len(reuse_bad), "samples_with_duplicate_ids": len(duplicates)},
                   {"despawn_grace_s": round(grace + sample_dt, 3), "reuse_tolerance": round(tol, 3)},
                   source="client events.ndjson entity_added/entity_removed (C3) vs samples.ndjson rendered entities",
                   sampling=f"rendered samples at {ev['scenario'].get('sample_hz')} Hz",
                   rationale="a removed entity left on screen is a ghost; a reused id drawn where the previous entity "
                             "was is a stale view entry interpolating between two different entities",
                   detail={"lingering": lingering[:20], "reuse_drawn_elsewhere": reuse_bad[:20],
                           "duplicate_ids": duplicates})


def _render_rows(c, skip, stalls, until=None):
    """(render_tick, id, x, y) of remote (not locally predicted) entities, in sample order, for
    scenario time in [skip, until]."""
    for smp in c["samples"]:
        rt, st = smp.get("render_tick"), smp.get("st")
        if rt is None or st is None or st < skip or (until is not None and st > until)                 or _in_stall(stalls, st, st, slack=0.5):
            continue
        for row in smp.get("ents", []):
            if row[2] == 1 or row[1] == "projectile":
                continue
            yield float(rt), row[0], row[3], row[4]


class _TrackWindow:
    """One client's rendered remote positions for a sliding render-tick window, filled from a
    stream: {id: ([ticks], [x], [y])}, ticks increasing per id. A row whose tick goes backwards
    (a reconnect to a restarted server) is skipped and counted."""

    def __init__(self, rows):
        self._rows = iter(rows)
        self._head = next(self._rows, None)
        self.tracks = {}
        self.last = None
        self.backwards = 0

    @property
    def done(self) -> bool:
        return self._head is None

    def first_tick(self):
        return None if self._head is None else self._head[0]

    def fill(self, until: float) -> None:
        while self._head is not None and self._head[0] < until:
            tick, eid, x, y = self._head
            if self.last is not None and tick < self.last:
                self.backwards += 1
            else:
                self.last = tick
                tr = self.tracks.get(eid)
                if tr is None:
                    tr = self.tracks[eid] = ([], [], [])
                tr[0].append(tick)
                tr[1].append(x)
                tr[2].append(y)
            self._head = next(self._rows, None)

    def prune(self, before: float) -> None:
        for tr in self.tracks.values():
            k = bisect_left(tr[0], before)
            if k:
                del tr[0][:k], tr[1][:k], tr[2][:k]


def _all_server_teleports(ev, max_speed):
    """{entity id: [(tick_lo, tick_hi)]} of every server-side respawn (dead -> alive, or HP from below
    half to full) or non-walkable step (1.5 x max_speed + 0.2 between probe samples), all entities in
    one pass over /debug/entities."""
    out, prev = {}, {}
    for r in ev["server"]["entities"]:
        tick, st = r.get("tick"), r.get("st")
        if tick is None or st is None:
            continue
        for e in r["ents"]:
            eid = e[0]
            p = prev.get(eid)
            if p is not None and tick > p[0]:
                mx = e[5] or 0
                respawn = (p[5] and not e[6]) or (mx > 0 and p[4] is not None and e[4] is not None
                                                  and p[4] < 0.5 * mx and e[4] >= mx)
                speed = float(e[7]) if len(e) > 7 and e[7] else max_speed
                if respawn or math.hypot(e[2] - p[2], e[3] - p[3]) > 1.5 * max(speed, max_speed) * max(st - p[1], 1e-3) + 0.2:
                    out.setdefault(eid, []).append((p[0], tick))
            prev[eid] = (tick, st, e[2], e[3], e[4], e[6])
    return out


def check_cross_client_convergence(ev, a):
    """Two clients drawing the same remote entity at the same server tick draw it in the same place
    (C4 hook: samples.ndjson render_tick, the tick the row's positions were drawn at). For every pair
    of clients, A's rendered position at render tick T is compared with B's interpolated between B's
    two samples around T. Thresholds are those of the remote position_divergence assertions (p95 0.35,
    max 1.0): two views of one interpolated stream must agree at least as well as each agrees with
    the server. Pairs across a server teleport (B's two samples further apart than an entity can walk)
    are skipped, and so is every pair within teleport_window_s (default 0.5 s: probe spacing 0.2 s
    plus the 0.2 s bracket plus the interpolation delay) of a server-side respawn or teleport of that
    entity (/debug/entities): around one, one client may already draw the new position while the
    other still draws the old one (T31 final soak 20261022T200348Z-S09-uc3e: the 15 worst pairs, max
    18.56, were 3-14 ticks before a player respawn)."""
    if len(ev["clients"]) < 2:
        return _inconclusive("needs at least two clients", source="samples.ndjson render_tick")
    hz = _tick_hz(ev, a)
    if not hz:
        return _inconclusive("server tick rate unknown", source="/status")
    stalls = host_stalls(ev)
    skip = float(a.get("skip_first_s", 2.0))
    until = a.get("until_s")
    wins = [_TrackWindow(_render_rows(c, skip, stalls, None if until is None else float(until))) for c in ev["clients"]]
    missing = [c["index"] for c, w in zip(ev["clients"], wins) if w.done]
    if missing:
        return _inconclusive(f"no samples with render_tick for client(s) {missing} (player without hook C4)",
                             source="samples.ndjson render_tick")
    max_gap = float(a.get("max_bracket_s", 0.2)) * hz
    max_speed = float(ev["scenario"].get("jump", {}).get("max_speed", 6.0))
    window = float(a.get("teleport_window_s", 0.5)) * hz
    teleports = {eid: sorted((lo - window, hi + window) for lo, hi in spans)
                 for eid, spans in _all_server_teleports(ev, max_speed).items()}
    dists, worst, near_teleport = util.Distribution(), [], 0
    # Pairs are formed window by window of render ticks (60 s at 60 Hz), each client's rows kept
    # only for the window plus the bracket margin: memory follows the window, not the run (T41).
    span = float(a.get("window_ticks", 3600))
    margin = max_gap + 1.0
    w0 = min(w.first_tick() for w in wins if not w.done)
    while True:
        w1 = w0 + span
        for w in wins:
            w.fill(w1 + margin)
        for i, wa in enumerate(wins):
            for j, wb in enumerate(wins):
                if i == j:
                    continue
                for eid, (ticks, xs, ys) in wa.tracks.items():
                    other = wb.tracks.get(eid)
                    if other is None:
                        continue
                    bt, bx, by = other
                    spans = teleports.get(eid, [])
                    starts = [lo for lo, _ in spans]
                    for k in range(bisect_left(ticks, w0), bisect_left(ticks, w1)):
                        tick = ticks[k]
                        if spans:
                            q = bisect_right(starts, tick) - 1
                            if q >= 0 and tick <= spans[q][1] or q + 1 < len(spans) and spans[q + 1][0] <= tick:
                                near_teleport += 1
                                continue
                        m = bisect_left(bt, tick)
                        if m == 0 or m >= len(bt) or bt[m] - bt[m - 1] > max_gap or bt[m] == bt[m - 1]:
                            continue
                        step = math.hypot(bx[m] - bx[m - 1], by[m] - by[m - 1])
                        if step > max_speed * 1.5 * (bt[m] - bt[m - 1]) / hz + 0.2:
                            continue
                        f = (tick - bt[m - 1]) / (bt[m] - bt[m - 1])
                        d = math.hypot(xs[k] - (bx[m - 1] + f * (bx[m] - bx[m - 1])),
                                       ys[k] - (by[m - 1] + f * (by[m] - by[m - 1])))
                        dists.add(d)
                        if d > float(a.get("max", 1.0)) and len(worst) < 15:
                            worst.append({"a": i, "b": j, "id": eid, "render_tick": tick, "dist": round(d, 3)})
        if all(w.done and (w.last is None or w.last < w1) for w in wins):
            break
        for w in wins:
            w.prune(w1 - margin)
        w0 = w1
    if len(dists) < int(a.get("min_pairs", 50)):
        return _inconclusive(f"{len(dists)} comparable pairs (need {a.get('min_pairs', 50)})", source="samples.ndjson")
    p95, mx = dists.percentile(95), dists.max()
    ok = p95 <= float(a.get("p95", 0.35)) and mx <= float(a.get("max", 1.0))
    return _result(PASS if ok else FAIL, {"pairs": len(dists), "p50": round(dists.percentile(50), 4),
                                          "p95": round(p95, 4), "max": round(mx, 4),
                                          "skipped_near_server_teleport": near_teleport,
                                          "skipped_ticks_backwards": sum(w.backwards for w in wins)},
                   {"p95": a.get("p95", 0.35), "max": a.get("max", 1.0),
                    "teleport_window_s": a.get("teleport_window_s", 0.5)},
                   source="samples.ndjson rendered remote positions keyed by render_tick (C4), client pairs",
                   sampling=f"client {ev['scenario'].get('sample_hz')} Hz",
                   rationale="clients interpolate the same server stream; at the same render tick they must draw an "
                             "entity in the same place, or players see each other's world differently",
                   detail={"worst": worst})


def check_stall_recovery(ev, a):
    """After a scripted client stall (C2 hook: plan action stall, events.ndjson stall with start/end
    and actual_ms), the stalled client's predicted player is back on the server path: local
    divergence p95 <= 0.5 (the local_divergence bound of S03/S10/S12) over [end + recover_s,
    end + recover_s + judge_s]. recover_s (default 1.0 s, 15 world snapshots) is the time allowed to
    reconcile; it is a test parameter, reported with the result. Hard snaps during each stall window
    are reported (pred.snaps delta)."""
    stalls = [(c, e) for c in ev["clients"] for e in c["events"] if e.get("event") == "stall"]
    if not stalls:
        return _inconclusive("no stall event in any client (plan without a stall action, or player without hook C2)",
                             source="events.ndjson stall")
    recover, judge = float(a.get("recover_s", 1.0)), float(a.get("judge_s", 3.0))
    bound = float(a.get("p95", 0.5))
    rows, failed, unjudged = [], 0, 0
    for c, e in stalls:
        if e.get("end") is None or e.get("actual_ms") is None or float(e["actual_ms"]) < 0.9 * float(e.get("ms", 0)):
            rows.append({"client": c["index"], "ms": e.get("ms"), "actual_ms": e.get("actual_ms"), "result": "did not stall as asked"})
            unjudged += 1
            continue
        lo, hi = float(e["end"]) + recover, float(e["end"]) + recover + judge
        errs, snaps_before, snaps_after = [], None, None
        for s in c["samples"]:
            t, p = s.get("t"), s.get("pred") or {}
            if t is None:
                continue
            if t <= float(e["start"]) and p.get("snaps") is not None:
                snaps_before = p["snaps"]
            if t <= hi and p.get("snaps") is not None:
                snaps_after = p["snaps"]
            if not lo <= t <= hi or s.get("st") is None:
                continue
            for row in s.get("ents", []):
                if row[2] != 1:
                    continue
                tr = ev["traj"].get(row[0])
                d = _dist_to_path(tr, s["st"] - 0.3, s["st"] + 0.6, row[3], row[4]) if tr else None
                if d is not None:
                    errs.append(d)
        if len(errs) < 10:
            rows.append({"client": c["index"], "ms": e.get("ms"), "result": f"{len(errs)} local samples after recovery"})
            unjudged += 1
            continue
        p95 = util.percentile(errs, 95)
        ok = p95 <= bound
        failed += 0 if ok else 1
        rows.append({"client": c["index"], "ms": e.get("ms"), "actual_ms": e.get("actual_ms"),
                     "local_p95_after": round(p95, 3), "samples": len(errs),
                     "snaps_during": None if snaps_before is None or snaps_after is None else snaps_after - snaps_before,
                     "ok": ok})
    status = FAIL if failed else (INCONCLUSIVE if unjudged else PASS)
    return _result(status, rows, {"local_p95": bound, "recover_s": recover, "judge_s": judge},
                   source="events.ndjson stall (C2) and samples.ndjson local rendered position vs server /debug/entities",
                   sampling=f"client {ev['scenario'].get('sample_hz')} Hz, server {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="a client that stops for a frame of half a second or two seconds must reconcile with the "
                             "server and stay there, not keep drifting or rubber-banding")


def check_graceful_leave(ev, a):
    """A client that leaves with the quit action (C6 hook: Disconnect(), not a process kill) ends
    with outcome `left` and a `disconnected` event, and its player entity leaves the server within
    leave_timeout_s (default 5 s, a test bound far under the 60 s KCP idle timeout,
    KcpTuning.IdleTimeoutMs, that cleans up a silent client): a polite leave must not wait for
    the timeout. Other clients with hook C3 must report its entity removed in the same bound."""
    leavers = [(c, e) for c in ev["clients"] for e in c["events"] if e.get("event") == "quit_requested"]
    if not leavers:
        return _inconclusive("no quit_requested event (plan without quit, or player without hook C6)",
                             source="events.ndjson quit_requested")
    ids = _user_ids(ev)
    timeout = float(a.get("leave_timeout_s", 5.0))
    rows, bad, unjudged = [], 0, 0
    for c, e in leavers:
        uid, st = ids[c["index"]], e.get("st")
        row = {"client": c["index"], "user_id": uid, "quit_st": st,
               "outcome": (c["summary"] or {}).get("outcome"),
               "disconnected": any(x.get("event") == "disconnected" for x in c["events"])}
        t = ev["traj"].get(uid) if uid else None
        after = [r["st"] for r in ev["server"]["entities"]
                 if r.get("st") is not None and st is not None and r["st"] > st + timeout
                 and any(x[0] == uid for x in r["ents"])]
        any_after = st is not None and any(r.get("st") is not None and r["st"] > st + timeout
                                           for r in ev["server"]["entities"])
        if t is None or st is None or not any_after:
            row["result"] = "no server samples to judge the removal"
            unjudged += 1
            rows.append(row)
            continue
        still = after
        last_seen = max((s for s in t["st"] if s >= st), default=None)
        row.update({"server_removed_after_s": None if last_seen is None else round(last_seen - st, 2),
                    "present_after_timeout": len(still)})
        seen_removed = {}
        for o in ev["clients"]:
            if o is c:
                continue
            rm = [x["st"] for x in o["events"] if x.get("event") == "entity_removed" and x.get("id") == uid
                  and x.get("st") is not None and x["st"] >= st]
            seen_removed[o["index"]] = round(min(rm) - st, 2) if rm else None
        row["others_removed_after_s"] = seen_removed
        late_others = [k for k, v in seen_removed.items() if v is None or v > timeout]
        has_c3 = any(x.get("event") == "entity_removed" for o in ev["clients"] if o is not c for x in o["events"])
        ok = row["outcome"] == "left" and row["disconnected"] and not still and (not has_c3 or not late_others)
        row["ok"] = ok
        bad += 0 if ok else 1
        rows.append(row)
    status = FAIL if bad else (INCONCLUSIVE if unjudged else PASS)
    # How the server saw the session end: a dead_link close means the polite disconnect frame never
    # arrived and the transport gave up on retransmissions (the entity then sits in the reconnect hold).
    dead_link = _delta(ev, "gameserver_kcp_sessions_closed_total", 'reason="dead_link"')
    diagnosis = {"kcp_sessions_closed_dead_link": dead_link}
    if dead_link:
        diagnosis["note"] = ("the server closed a session by dead_link during the run: the client's polite disconnect "
                             "frame did not reach it, so the leave was handled as a dropped connection (reconnect hold)")
    return _result(status, rows, {"leave_timeout_s": timeout, "outcome": "left"}, detail=diagnosis,
                   source="client events.ndjson quit_requested/disconnected, summary.json outcome, server /debug/entities, "
                          "other clients' entity_removed (C3), /metrics kcp sessions closed",
                   sampling=f"server {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="a player who leaves must disappear for everyone at once; one that lingers until the idle "
                             "timeout is a ghost the others can still see and hit")


CHECKS.update({
    "tick_adoption": check_tick_adoption,
    "entity_lifecycle": check_entity_lifecycle,
    "cross_client_convergence": check_cross_client_convergence,
    "stall_recovery": check_stall_recovery,
    "graceful_leave": check_graceful_leave,
})


# --------------------------------------------------------------------------- server hooks S1/S2 (T20)

def _debug_kills(ev):
    return [d for d in ev.get("disruptions", []) if d.get("kind") == "debug_kill"]


def _failed_debug_kills(ev):
    return [{"client": d.get("client"), "http_status": d.get("http_status"),
             "outcome": (d.get("response") or {}).get("outcome"), "error": d.get("error")}
            for d in _debug_kills(ev) if not d.get("ok")]


def check_debug_kill_respawn(ev, a):
    """Every scripted kill (disruption debug_kill: POST /debug/kill, rpg-mmo-server hook S1) was
    confirmed by the server (HTTP 200, outcome killed) and was followed by a respawn: /status
    player_respawns rises by one per kill within respawn_within_s (default 2 s: the respawn runs
    within one world interval, 67 ms at 15 Hz, per the hook's tests; /status is probed at 1 Hz and
    the request is queued to the tick), and the player is alive at full HP in /debug/entities
    after it. A kill that did not answer 200 is INCONCLUSIVE, never PASS."""
    kills = _debug_kills(ev)
    if not kills:
        return _inconclusive("no debug_kill disruption ran", source="disruptions.ndjson")
    failed = _failed_debug_kills(ev)
    if failed:
        return _inconclusive(f"debug_kill not confirmed by the server: {failed}", source="disruptions.ndjson")
    within = float(a.get("respawn_within_s", 2.0))
    status = [r for r in ev["server"]["status"] if r.get("_st") is not None and r.get("player_respawns") is not None]
    if not status:
        return _inconclusive("/status has no player_respawns", source="/status player_respawns")
    rows, bad = [], 0
    for d in kills:
        st, uid = d.get("st"), d.get("user_id")
        before = [r["player_respawns"] for r in status if r["_st"] <= st]
        after = [r["player_respawns"] for r in status if st < r["_st"] <= st + within]
        if st is None or not before or not after:
            return _inconclusive(f"no /status samples around the kill at st={st}", source="/status player_respawns")
        respawned = max(after) - before[-1]
        t = ev["traj"].get(uid) or {}
        mx = t.get("max_hp") or 0
        back = any(st < s2 <= st + within + 1.0 and not dd and mx and (hp or 0) >= mx
                   for s2, hp, dd in zip(t.get("st", []), t.get("hp", []), t.get("dead", [])))
        ok = respawned >= 1 and back
        bad += 0 if ok else 1
        rows.append({"client": d.get("client"), "st": None if st is None else round(st, 2), "server_tick": d.get("server_tick"),
                     "hp_before": (d.get("response") or {}).get("hp_before"), "respawns_counted": respawned,
                     "alive_full_hp_after": back, "ok": ok})
    return _result(FAIL if bad else PASS, rows, {"respawn_within_s": within},
                   source="disruptions.ndjson (POST /debug/kill), /status player_respawns, /debug/entities",
                   sampling="1 Hz /status, 5 Hz entities",
                   rationale="a player killed through the normal damage path must come back through the normal respawn "
                             "rule; a kill without a respawn leaves the player dead in the world",
                   artifacts=[str(ev["run_dir"] / "disruptions.ndjson")])


def _rejections_by_reason(metrics: dict) -> dict:
    out = {}
    for k, v in metrics.items():
        if k.startswith("gameserver_inputs_rejected_total{"):
            m = re.search(r'reason="([^"]+)"', k)
            if m:
                out[m.group(1)] = out.get(m.group(1), 0.0) + v
    return out


def check_input_rejections(ev, a):
    """Per-reason input rejections over the scenario window (gameserver_inputs_rejected_total{reason},
    rpg-mmo-server hook S2): each reason in expect_positive rose; each in expect_zero did not."""
    start = _rejections_by_reason(ev["server"]["metrics_start"])
    end = _rejections_by_reason(ev["server"]["metrics_end"])
    if not end:
        return _inconclusive("no gameserver_inputs_rejected_total series in the end scrape", source="/metrics")
    want_pos, want_zero = list(a.get("expect_positive", [])), list(a.get("expect_zero", []))
    unknown = [r for r in want_pos + want_zero if r not in end]
    if unknown:
        return _inconclusive(f"the server publishes no series for reason(s) {unknown} (a build without hook S2)",
                             source="/metrics")
    delta = {r: end[r] - start.get(r, 0.0) for r in end}
    bad = [r for r in want_pos if delta[r] <= 0] + [r for r in want_zero if delta[r] != 0]
    return _result(FAIL if bad else PASS, {r: delta[r] for r in sorted(delta) if delta[r] or r in want_pos + want_zero},
                   {"positive": want_pos, "zero": want_zero},
                   source="/metrics gameserver_inputs_rejected_total{map_id,reason}, scenario start -> end",
                   sampling="2 scrapes", detail={"failed": bad},
                   rationale="the server must refuse what its rules forbid, and say why",
                   artifacts=[str(ev["run_dir"] / "server")])


def _content_projectile_ability(ev, a):
    """The ability the client casts: the first `projectile` ability in content/abilities.json
    (client Catalog.FirstProjectileAbility), read at the run's server commit."""
    import json as _json
    import subprocess
    meta = ev["meta"] or {}
    repo = a.get("server_repo") or (meta.get("config") or {}).get("server_repo")
    sha = ((meta.get("provenance") or {}).get("server") or {}).get("sha") or ((meta.get("repos") or {}).get("server") or {}).get("head")
    rel = "backend/content/abilities.json"
    doc, src = None, None
    if repo and sha:
        try:
            res = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{rel}"], capture_output=True, timeout=30)
            if res.returncode == 0:
                doc, src = _json.loads(res.stdout.decode("utf-8")), f"{rel} at server {sha[:10]}"
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    if doc is None and repo and (Path(repo) / rel).exists():
        doc, src = _json.loads((Path(repo) / rel).read_text(encoding="utf-8")), f"{Path(repo) / rel} (working tree)"
    for ab in (doc or {}).get("abilities", []):
        if ab.get("delivery") == "projectile" and ab.get("projectile"):
            power = sum(float(e.get("power", 0)) for e in ab.get("effects", []) if e.get("kind") == "damage")
            return {"id": ab.get("id"), "name": ab.get("name"), "power": power, "cooldown_ticks": ab.get("cooldownTicks", 0),
                    "range": float(ab["projectile"]["range"]), "radius": float(ab["projectile"].get("radius", 0)),
                    "speed": float(ab["projectile"]["speed"]), "source": src}
    return None


def _hp_lost(t, lo, hi):
    loss, prev = 0.0, None
    for s2, hp in zip(t["st"], t["hp"]):
        if lo <= s2 <= hi and prev is not None and hp is not None and hp < prev:
            loss += prev - hp
        prev = hp if hp is not None else prev
    return loss


def check_cast_damage_bound(ev, a):
    """Rejected casts do no damage. For the casting client's cast_spam and cast_at_point windows,
    the HP enemies lose is at most (casts the cooldown lets through) x (the ability's damage power):
    floor(window / cooldown) + 1 accepted casts, cooldown = cooldownTicks / tick_rate, power = the
    sum of the ability's damage effects (defense only lowers it). Both numbers are read from
    content/abilities.json at the run's server commit. For cast_at_point windows, an enemy that was
    farther than the projectile's reach (range + radius + 1) from the caster for the whole window
    must lose no HP. Only one client may cast in the scenario, and enemy attacks must be off, so no
    other source changes enemy HP."""
    k = int(a.get("client", 0))
    if k >= len(ev["clients"]):
        return _inconclusive(f"client {k} is not in this run", source="plan.json")
    others = [c["index"] for c in ev["clients"] if c["index"] != k and any(
        str(x.get("kind", "")).startswith("cast") for x in c["plan"].get("actions", []))]
    if others:
        return _inconclusive(f"clients {others} also cast: damage cannot be attributed", source="plan.json")
    ab = _content_projectile_ability(ev, a)
    if ab is None:
        return _inconclusive("no projectile ability readable in content/abilities.json", source="content")
    hz = _tick_hz(ev, a)
    if not hz or not ab["cooldown_ticks"]:
        return _inconclusive("tick rate or cooldown unknown", source="/status tick_rate, content")
    cooldown_s = float(ab["cooldown_ticks"]) / hz
    c = ev["clients"][k]
    uid = _user_ids(ev)[k]
    caster = ev["traj"].get(uid) if uid else None
    mobs = {eid: t for eid, t in ev["traj"].items() if t["type"] == "mob"}
    windows = [x for x in c["plan"].get("actions", []) if x.get("kind") in ("cast_spam", "cast_at_point")]
    if not windows or not mobs or caster is None:
        return _inconclusive("no cast window, no enemies or no caster trajectory", source="plan.json, /debug/entities")
    reach = ab["range"] + ab["radius"] + float(a.get("reach_margin", 1.0))
    rows, bad, unexercised = [], 0, 0
    for w in windows:
        t0, t1 = float(w["t0"]), float(w["t1"])
        hi = t1 + ab["range"] / ab["speed"] + 0.5
        accepted = int((t1 - t0) // cooldown_s) + 1
        bound = accepted * ab["power"]
        loss = sum(_hp_lost(t, t0, hi) for t in mobs.values())
        row = {"kind": w["kind"], "window": [t0, t1], "max_accepted_casts": accepted, "hp_bound": bound,
               "enemy_hp_lost": round(loss, 2)}
        if w["kind"] == "cast_spam" and float(w.get("interval_ms", 100)) / 1000.0 >= cooldown_s:
            row["result"] = "interval not below the cooldown: cooldown not exercised"
            unexercised += 1
        elif w["kind"] == "cast_at_point":
            far = []
            for eid, t in mobs.items():
                ds = [math.hypot(x - p[0], y - p[1]) for s2, x, y in zip(t["st"], t["x"], t["y"]) if t0 <= s2 <= hi
                      for p in [_pos_at(caster, s2)] if p is not None]
                if ds and min(ds) > reach and _hp_lost(t, t0, hi) > 0:
                    far.append({"id": eid, "min_distance": round(min(ds), 2)})
            p0 = _pos_at(caster, t0)
            aim_d = None if p0 is None else math.hypot(float(w.get("x", 0)) - p0[0], float(w.get("y", 0)) - p0[1])
            row.update({"aim_distance": None if aim_d is None else round(aim_d, 2), "hit_beyond_reach": far})
            if far:
                bad += 1
            if aim_d is None or aim_d <= ab["range"]:
                row["note"] = "aim point not beyond the projectile range"
        if loss > bound + 1e-6:
            row["over_bound"] = True
            bad += 1
        if w["kind"] == "cast_spam" and loss == 0 and "result" not in row:
            row["result"] = "no enemy was hit: the bound was not exercised"
            unexercised += 1
        rows.append(row)
    status = FAIL if bad else (INCONCLUSIVE if unexercised else PASS)
    return _result(status, rows, {"ability": {k2: ab[k2] for k2 in ("id", "name", "power", "cooldown_ticks", "range",
                                                                    "radius", "speed")},
                                  "cooldown_s": round(cooldown_s, 3), "reach": reach},
                   source=f"plan.json cast windows, /debug/entities enemy HP and caster position, {ab['source']}",
                   sampling=f"server {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="a cast the server refuses (cooldown) must not damage anything, and a projectile must not "
                             "hit beyond the range the content gives it (projectiles have no aim-range check: the aim "
                             "only gives the direction, AbilityLogic.ValidateCast)")


CHECKS.update({
    "debug_kill_respawn": check_debug_kill_respawn,
    "input_rejections": check_input_rejections,
    "cast_damage_bound": check_cast_damage_bound,
})


# --------------------------------------------------------------------------- S16 / S17: raw clients

def _raw_records(ev, kind: str) -> list:
    return [r for r in ev.get("rawprobe", []) if r.get("record") == kind]


def _rendered_ids(ev) -> list:
    return [u for u in _user_ids(ev) if u]


def check_server_alive(ev, a):
    """The game server process stayed up and answered for the whole scenario: every /status probe was
    answered (max_failed_probes, default 0), /status `uptime_seconds` never went backwards (a restart
    resets it to 0) and no two consecutive answers were more than max_gap_s apart (default 5 s, 5 probe
    periods). Tick health is `server_tick`'s job."""
    rows = [(r["_st"], r.get("uptime_seconds")) for r in ev["server"]["status"] if r.get("_st") is not None]
    if len(rows) < 5:
        return _inconclusive("fewer than 5 /status samples", source="server/status.ndjson")
    rows.sort()
    restarts = [round(b[0], 1) for a_, b in zip(rows, rows[1:])
                if a_[1] is not None and b[1] is not None and b[1] < a_[1]]
    gaps = [b[0] - a_[0] for a_, b in zip(rows, rows[1:])]
    counts = (ev["meta"].get("probe_counts") or {})
    failed = counts.get("status_failed")
    if failed is None:
        return _inconclusive("run.json has no probe_counts: failed probes cannot be counted", source="run.json probe_counts")
    max_failed = int(a.get("max_failed_probes", 0))
    max_gap = float(a.get("max_gap_s", 5.0))
    ok = not restarts and max(gaps) <= max_gap and failed <= max_failed
    return _result(PASS if ok else FAIL,
                   {"status_samples": len(rows), "restarts_at_s": restarts, "max_gap_s": round(max(gaps), 2),
                    "failed_status_probes": failed},
                   {"restarts": 0, "max_gap_s": max_gap, "failed_status_probes": max_failed},
                   source="server/status.ndjson uptime_seconds and sample times, run.json probe_counts",
                   sampling="1 Hz /status",
                   rationale="a malformed client must never take the server down; a restart or an unanswering /status "
                             "is the server not being there",
                   artifacts=[str(ev["run_dir"] / "server" / "status.ndjson")])


def check_client_sessions(ev, a):
    """No rendered client's network session changed inside the scenario window: after the scenario clock
    starts a client logs no `net_state` change, `disconnected`, `entities_reset` or `reconnected` event
    (a session close is any of them)."""
    if not ev["clients"]:
        return _inconclusive("no clients in this run", source="client events.ndjson")
    dur = float(ev["scenario"].get("duration_s", 0))
    bad = {}
    never_in_world = [c["index"] for c in ev["clients"] if not any(
        e.get("event") == "in_world" or (e.get("event") == "net_state" and e.get("state") == "InWorld") for e in c["events"])]
    if never_in_world:
        return _inconclusive(f"clients {never_in_world} logged no in_world event: their session was never observed",
                             source="client events.ndjson")
    for c in ev["clients"]:
        seen = [{"event": e.get("event"), "state": e.get("state"), "st": round(e["st"], 2)}
                for e in c["events"] if e.get("st") is not None and 0 <= e["st"] <= dur
                and e.get("event") in ("net_state", "disconnected", "entities_reset", "reconnected")]
        if seen:
            bad[c["index"]] = seen[:10]
    return _result(FAIL if bad else PASS, {"clients_with_session_change": sorted(bad), "events": bad},
                   {"session_changes": 0},
                   source="client events.ndjson net_state / disconnected / entities_reset / reconnected, st in [0, duration]",
                   sampling="every event",
                   rationale="what one bad client sends must not end another player's session",
                   artifacts=[str(c["dir"] / "events.ndjson") for c in ev["clients"]])


def _delta_series(rec, name, reason):
    key = next((k for k in rec["post"]["metrics"] if k.startswith(name + "{") and f'reason="{reason}"' in k), None)
    if key is None:
        return None
    return rec["post"]["metrics"][key] - rec["mid"]["metrics"].get(key, 0.0)


def check_malformed_input(ev, a):
    """Each case of the raw-client step (rawprobe.ndjson, rawprobe.run_malformed): one fresh session sent one
    kind of malformed input while the rendered clients played.

    Per case, from the scenario's `cases` map:
    - expect `closes`: the server's connection count fell below its value with the offender in, within
      `within_s`, and ended at the value before the offender joined (the rendered clients' sessions are
      intact); expect `stays_open`: it did not fall, ended one above that value, and the offender kept
      receiving snapshots (at least `min_snapshots`, default 5).
    - `rejections`: {reason: minimum} for gameserver_inputs_rejected_total{reason} (or the counter named by
      `rejections_counter`, e.g. gameserver_messages_rejected_total for an undefined message type) between the
      read with the offender in and the final read; a `zero` list of reasons must not rise. A named counter
      with no series at all makes the case INCONCLUSIVE (the server predates it).
    - `max_displacement`: the offender's server position never moved more than speed x elapsed + 0.5 after the
      send (no teleport: positions are never client-supplied, so this is the speed bound).
    - `target_hp_unchanged` / `beyond_attack_range`: an attack at a far enemy cost it nothing and was aimed
      beyond GameConstants.AttackRange.
    A case that did not run, did not join or has no read is INCONCLUSIVE, never PASS. A `stays_open` case
    without a `rejections` rule is INCONCLUSIVE too (`signal_missing`): the session surviving does not show
    the server refused or ignored the input. An undefined message type is counted from rpg-mmo-server #490
    (gameserver_messages_rejected_total{reason="unknown_type"}); before it there was no counter or log line.
    Every case lists the server counters that moved, so the report shows which counter (if any) saw the bad frame."""
    cases = a.get("cases") or {}
    recs = {r["id"]: r for r in _raw_records(ev, "case")}
    end = next(iter(_raw_records(ev, "end")), {})
    consts = end.get("constants") or {}
    if not recs:
        return _inconclusive("no raw-client case record (the step did not run or wrote nothing)", source="rawprobe.ndjson")
    rows, bad, unjudged = {}, [], []
    for cid, rule in cases.items():
        rec = recs.get(cid)
        if rec is None or rec.get("error") or not (rec.get("join") or {}).get("ok") or not rec.get("post") or not rec.get("mid"):
            unjudged.append(cid)
            rows[cid] = {"result": "not judged", "why": (rec or {}).get("error") or (rec or {}).get("join") or "no record"}
            continue
        row = {"sent": (rec.get("detail") or {}).get("sent"), "closed_after_s": rec.get("closed_after_s"),
               "connections": {"before_join": rec["pre"].get("connections"), "with_offender": rec["mid"].get("connections"),
                               "end": rec["post"].get("connections")},
               "players_online": {"before_join": rec["pre"].get("players_online"), "end": rec["post"].get("players_online")},
               "snapshots_after_send": rec.get("snapshots_after_send"), "counters_moved": rec.get("moved")}
        problems = []
        pre_c, mid_c, end_c = rec["pre"].get("connections"), rec["mid"].get("connections"), rec["post"].get("connections")
        if None in (pre_c, mid_c, end_c):
            unjudged.append(cid)
            row["result"] = "not judged: no /status connections"
            rows[cid] = row
            continue
        if mid_c != pre_c + 1:
            problems.append(f"the offender did not show as one connection (before {pre_c}, with it {mid_c})")
        if rule.get("expect") == "closes":
            within = float(rule.get("within_s", 3.0))
            if rec.get("closed_after_s") is None or rec["closed_after_s"] > within:
                problems.append(f"session not closed within {within} s (closed_after_s={rec.get('closed_after_s')})")
            if end_c != pre_c:
                problems.append(f"connections ended at {end_c}, expected {pre_c}: another session was affected or the offender stayed")
        else:
            if rec.get("closed_after_s") is not None:
                problems.append(f"session closed after {rec['closed_after_s']} s but the input should only be refused")
            if end_c != pre_c + 1:
                problems.append(f"connections ended at {end_c}, expected {pre_c + 1}")
            if (rec.get("snapshots_after_send") or 0) < int(rule.get("min_snapshots", 5)):
                problems.append(f"offender received {rec.get('snapshots_after_send')} snapshots after the send")
            if not rule.get("rejections") and not problems:
                # The session survived, but nothing on the server says the input was refused or ignored rather
                # than accepted as a no-op (RV-F8A-1): staying connected is not an observation of a rejection.
                unjudged.append(cid)
                row["signal_missing"] = ("no server-side signal that the input was refused or ignored: a stays_open case "
                                         "needs a `rejections` rule (a counter that rises)")
        rej = {}
        counter = rule.get("rejections_counter", "gameserver_inputs_rejected_total")
        for reason, minimum in (rule.get("rejections") or {}).items():
            dv = _delta_series(rec, counter, reason)
            rej[reason] = dv
            if dv is None and counter != "gameserver_inputs_rejected_total":
                # A counter a server may predate (gameserver_messages_rejected_total, rpg-mmo-server #490): no series
                # at all is "this server cannot tell", not a failure of the case.
                unjudged.append(cid)
                row["signal_missing"] = f"no {counter}{{reason={reason}}} series: the server does not export this counter"
            elif dv is None:
                problems.append(f"no series for rejection reason {reason}")
            elif dv < float(minimum):
                problems.append(f"{counter}{{reason={reason}}} rose {dv}, expected >= {minimum}")
        for reason in rule.get("zero", []):
            dv = _delta_series(rec, "gameserver_inputs_rejected_total", reason)
            rej[reason] = dv
            if dv:
                problems.append(f"gameserver_inputs_rejected_total{{reason={reason}}} rose {dv}, expected 0")
        if rej:
            row["rejections_delta"] = rej
        if rule.get("max_displacement"):
            t = ev["traj"].get(rec["user_id"])
            st0 = rec.get("sent_st")
            speed = (rec.get("entity_before") or {}).get("speed")
            if t is None or st0 is None or not speed:
                unjudged.append(cid)
                row["displacement"] = "not judged: no trajectory or speed"
            else:
                p0 = _pos_at(t, st0) or (t["x"][0], t["y"][0])
                later = [(s2, math.hypot(x - p0[0], y - p0[1])) for s2, x, y in zip(t["st"], t["x"], t["y"]) if s2 >= st0]
                worst = max(later, key=lambda r: r[1] - speed * (r[0] - st0), default=None)
                if worst is None:
                    unjudged.append(cid)
                    row["displacement"] = "not judged: no samples after the send"
                else:
                    allowed = speed * (worst[0] - st0) + 0.5
                    row["displacement"] = {"worst_distance": round(worst[1], 2), "allowed": round(allowed, 2), "speed": speed}
                    if worst[1] > allowed:
                        problems.append(f"moved {worst[1]:.2f} in {worst[0] - st0:.2f} s, above speed x elapsed + 0.5 = {allowed:.2f}")
        if rule.get("beyond_attack_range"):
            rng = (consts.get("attack_range") or {}).get("value")
            dist = (rec.get("detail") or {}).get("target_distance")
            row["attack_range"] = rng
            row["target_distance"] = dist
            if rng is None or dist is None:
                unjudged.append(cid)
            elif dist <= rng:
                problems.append(f"target at {dist} is inside the attack range {rng}: the case did not test out-of-range")
        if rule.get("target_hp_unchanged"):
            # From the 5 Hz entity trajectory (the enemy may despawn before the final read), over the case.
            tgt = (rec.get("detail") or {}).get("target")
            t = ev["traj"].get(tgt) if tgt else None
            st0 = rec.get("sent_st")
            if t is None or st0 is None:
                unjudged.append(cid)
                row["target_hp"] = "not judged: the target is not in the entity samples"
            else:
                lost = _hp_lost(t, st0, st0 + float(rule.get("window_s", 6.0)))
                row["target_hp"] = {"target": tgt, "hp_lost_in_window": lost}
                if lost > 0:
                    problems.append(f"{tgt} lost {lost} HP to refused attacks")
        row["problems"] = problems
        row["result"] = "FAIL" if problems else ("not judged" if row.get("signal_missing") else "ok")
        if problems:
            bad.append(cid)
        rows[cid] = row
    status = FAIL if bad else (INCONCLUSIVE if unjudged else PASS)
    return _result(status, rows, {"cases": cases},
                   source="rawprobe.ndjson (raw-client step), gameserver /status connections, /metrics gameserver_* "
                          "(read with the offender in and 2 s after), /debug/entities",
                   sampling="/status 4 Hz during the case; /metrics and entities before join, with offender, at the end",
                   detail={"failed": bad, "not_judged": sorted(set(unjudged)), "constants": consts},
                   rationale="a client that sends what the protocol forbids must be refused or lose its own session, "
                             "and nobody else may notice",
                   artifacts=[str(ev["run_dir"] / "rawprobe.ndjson")])


def _churn_view(ev, a):
    """Cycle records and derived instants of the churn step, or an INCONCLUSIVE result."""
    cycles = _raw_records(ev, "cycle")
    start = next(iter(_raw_records(ev, "start")), None)
    if not cycles or not start:
        return None, _inconclusive("no churn cycle recorded (the step did not run)", source="rawprobe.ndjson")
    drops = [c for c in cycles if c["kind"] == "drop" and c.get("end_st") is not None]
    leaves = [c for c in cycles if c["kind"] == "leave" and c.get("end_st") is not None]
    gone = float(a.get("drop_gone_within_s", 75.0))
    last_end = max([c["end_st"] for c in cycles if c.get("end_st") is not None], default=None)
    last_drop = max([c["end_st"] for c in drops], default=None)
    quiet0 = None if last_end is None else max(last_end + float(a.get("leave_within_s", 5.0)),
                                                (last_drop + gone) if last_drop is not None else 0.0)
    return {"cycles": cycles, "start": start, "drops": drops, "leaves": leaves, "users": start.get("users") or {},
            "quiet_from": quiet0, "last_drop": last_drop, "gone_within_s": gone}, None


def check_churn_cycles(ev, a):
    """Every churn cycle joined: `cycles` cycles ran (default 10), each join answered ok within
    max_join_s (default 5 s). A cycle that could not join is a product or harness failure, reported with the
    join error; a step that recorded fewer cycles is INCONCLUSIVE."""
    view, bad = _churn_view(ev, a)
    if bad:
        return bad
    want = int(a.get("cycles", 10))
    cyc = view["cycles"]
    if len(cyc) < want:
        return _inconclusive(f"{len(cyc)} of {want} cycles recorded", source="rawprobe.ndjson")
    max_join = float(a.get("max_join_s", 5.0))
    rows, failed = [], []
    for c in cyc:
        j = c.get("join") or {}
        ok = bool(j.get("ok")) and (j.get("join_s") or 0) <= max_join and not c.get("error")
        rows.append({"n": c["n"], "kind": c["kind"], "join_ok": j.get("ok"), "join_s": j.get("join_s"),
                     "snapshots": c.get("snapshots"), "error": j.get("error") or c.get("error")})
        if not ok:
            failed.append(c["n"])
    return _result(FAIL if failed else PASS, rows, {"cycles": want, "max_join_s": max_join},
                   source="rawprobe.ndjson cycle records (gateway auth, enter world, KCP join)", sampling="per cycle",
                   detail={"failed_cycles": failed},
                   rationale="a player who dropped or left must be able to come back at once, every time",
                   artifacts=[str(ev["run_dir"] / "rawprobe.ndjson")])


def check_churn_ghosts(ev, a):
    """No ghost entities after churn. From /debug/entities (5 Hz) and the rendered clients:
    - no player entity other than the rendered clients' and the two churn users' ever exists;
    - after each graceful leave the leaver's entity is absent from `leave_within_s` (default 5 s, the
      graceful_leave bound) after the leave until the next join, and every rendered client logged
      entity_removed for it inside that bound (hook C3);
    - after the last silent drop the entity is gone by `drop_gone_within_s` (default 75 s = PingInterval 10 s
      + PongTimeout 30 s, the longest the server needs to notice a silent peer, + the 30 s map hold
      (constants.EntityHoldTTL), + 5 s sampling slack);
    - in the quiet window (from that instant to the end, first 2 s skipped) the server holds exactly the
      rendered clients' player entities and every rendered client draws exactly that many players (itself
      included: its samples list its own entity)."""
    view, bad = _churn_view(ev, a)
    if bad:
        return bad
    rendered = _rendered_ids(ev)
    users = view["users"]
    allowed = set(rendered) | set(users.values())
    ents = [(r["st"], {e[0] for e in r["ents"] if e[1] == "player"}) for r in ev["server"]["entities"] if r.get("st") is not None]
    if not ents or not ev["clients"]:
        return _inconclusive("no server entity samples or no rendered clients", source="server/entities.ndjson")
    dur = float(ev["scenario"].get("duration_s", 0))
    problems, unjudged, detail = [], [], {}
    unknown = sorted({i for _, ids in ents for i in ids} - allowed)
    detail["unknown_player_ids"] = unknown
    if unknown:
        problems.append(f"player entities nobody owns: {unknown}")
    leave_w = float(a.get("leave_within_s", 5.0))
    leave_rows = []
    by_n = {c["n"]: c for c in view["cycles"]}
    for c in view["leaves"]:
        uid = c["user_id"]
        nj = by_n.get(c["n"] + 1)
        hi = (nj["join_st"] - 0.4) if nj and nj.get("join_st") is not None else c["end_st"] + leave_w + 2.0
        lo = c["end_st"] + leave_w
        window = [ids for st, ids in ents if lo <= st <= hi]
        row = {"cycle": c["n"], "left_at_s": round(c["end_st"], 1), "judged_window": [round(lo, 1), round(hi, 1)],
               "samples": len(window)}
        if not window:
            row["result"] = "no server sample in the window"
            unjudged.append(f"leave cycle {c['n']}: no server sample in the window")
        elif any(uid in ids for ids in window):
            row["result"] = "FAIL: entity still present"
            problems.append(f"leave cycle {c['n']}: {uid} still in the world {leave_w} s after the graceful leave")
        removed, never_shown = {}, []
        for cl in ev["clients"]:
            shown = any(e.get("event") == "entity_added" and e.get("id") == uid and e.get("st") is not None
                        and c["join_st"] - 0.5 <= e["st"] <= c["end_st"] for e in cl["events"])
            rm = [e["st"] for e in cl["events"] if e.get("event") == "entity_removed" and e.get("id") == uid
                  and e.get("st") is not None and c["end_st"] <= e["st"] <= c["end_st"] + leave_w]
            removed[cl["index"]] = round(min(rm) - c["end_st"], 2) if rm else None
            if not shown:
                never_shown.append(cl["index"])
        row["removed_for_clients_after_s"] = removed
        if never_shown:
            # out of the area of interest (or no C3 events): there was nothing to remove, so nothing to judge
            row["never_shown_to_clients"] = never_shown
            unjudged.append(f"leave cycle {c['n']}: clients {never_shown} were never shown the leaver")
        late = [k for k, v in removed.items() if v is None and k not in never_shown]
        if late:
            problems.append(f"leave cycle {c['n']}: rendered clients {late} did not drop the leaver within {leave_w} s")
        leave_rows.append(row)
    detail["leave_cycles"] = leave_rows
    gone = view["gone_within_s"]
    if view["last_drop"] is not None:
        duid = users.get("drop")
        seen = [st for st, ids in ents if duid in ids and st >= view["last_drop"]]
        last_seen = max(seen) if seen else None
        detail["last_drop"] = {"dropped_at_s": round(view["last_drop"], 1), "bound_s": gone,
                               "last_seen_after_s": None if last_seen is None else round(last_seen - view["last_drop"], 1)}
        if ents[-1][0] < view["last_drop"] + gone:
            unjudged.append("scenario ends before the drop bound")
        elif last_seen is not None and last_seen - view["last_drop"] > gone:
            problems.append(f"silently dropped {duid} still in the world {last_seen - view['last_drop']:.1f} s after the drop (bound {gone})")
    q0 = view["quiet_from"]
    if q0 is None or dur - q0 < 5.0:
        unjudged.append("quiet window shorter than 5 s")
    else:
        q_ents = [ids for st, ids in ents if q0 + 2.0 <= st <= dur]
        extra = sorted({i for ids in q_ents for i in ids} - set(rendered))
        detail["quiet_window_s"] = [round(q0, 1), dur]
        detail["server_players_in_quiet_window"] = sorted({i for ids in q_ents for i in ids})
        if extra or any(set(ids) != set(rendered) for ids in q_ents):
            problems.append(f"server player entities in the quiet window differ from the rendered clients': extra {extra}")
        per_client = {}
        for cl in ev["clients"]:
            counts = [sum(1 for e in s.get("ents", []) if e[1] == "player") for s in cl["samples"]
                      if s.get("st") is not None and q0 + 2.0 <= s["st"] <= dur]
            per_client[cl["index"]] = {"samples": len(counts), "players_drawn": sorted(set(counts))}
            if not counts:
                unjudged.append(f"client {cl['index']} has no sample in the quiet window")
            elif set(counts) != {len(ev["clients"])}:
                problems.append(f"client {cl['index']} draws {sorted(set(counts))} players, expected {len(ev['clients'])}")
        detail["rendered_view"] = per_client
    status = FAIL if problems else (INCONCLUSIVE if unjudged else PASS)
    detail["problems"], detail["not_judged"] = problems, unjudged
    return _result(status, {"unknown_ids": len(unknown), "problems": len(problems)},
                   {"unknown_ids": 0, "leave_within_s": leave_w, "drop_gone_within_s": gone},
                   source="server/entities.ndjson (5 Hz), rendered clients' samples.ndjson and entity_removed events, "
                          "rawprobe.ndjson cycle times",
                   sampling="5 Hz server, 20 Hz clients", detail=detail,
                   rationale="a player who left or dropped must stop existing for everyone once the server's own "
                             "timeouts have run; a second entity for the same player, or one that never goes, is a ghost",
                   artifacts=[str(ev["run_dir"] / "rawprobe.ndjson"), str(ev["run_dir"] / "server" / "entities.ndjson")])


def check_player_count_baseline(ev, a):
    """The server's own player count follows the churn and returns to the baseline: /status `players_online`
    and `connections` never exceed baseline + `max_extra` (default 2, the two churn users) during the run,
    and equal the baseline (the rendered clients) at every sample of the quiet window (from the instant
    churn_ghosts derives, first 2 s skipped)."""
    view, bad = _churn_view(ev, a)
    if bad:
        return bad
    base = len(ev["clients"])
    if not base:
        return _inconclusive("no rendered clients", source="/status")
    rows = _status_in_window(ev)
    if not rows:
        return _inconclusive("no /status sample", source="/status")
    extra = int(a.get("max_extra", 2))
    peak = {"players_online": max(r.get("players_online") or 0 for r in rows),
            "connections": max(r.get("connections") or 0 for r in rows)}
    q0 = view["quiet_from"]
    dur = float(ev["scenario"].get("duration_s", 0))
    q = [r for r in rows if q0 is not None and q0 + 2.0 <= r["_st"] <= dur]
    if len(q) < 3:
        return _inconclusive("fewer than 3 /status samples in the quiet window", source="/status")
    off = [(round(r["_st"], 1), r.get("players_online"), r.get("connections")) for r in q
           if r.get("players_online") != base or r.get("connections") != base]
    ok = not off and peak["players_online"] <= base + extra and peak["connections"] <= base + extra
    return _result(PASS if ok else FAIL, {"peak": peak, "quiet_window_samples": len(q), "off_baseline": off[:10]},
                   {"baseline": base, "peak_max": base + extra},
                   source="gameserver /status players_online and connections", sampling="1 Hz",
                   rationale="players_online is balanced by join and leave; a double count (two connections for one player) "
                             "or a count that stays up after everyone is gone is a leaked session",
                   artifacts=[str(ev["run_dir"] / "server" / "status.ndjson")])


def check_redis_leak(ev, a):
    """Redis holds the same session keys (`session:*`), registry keys (`servers:id:*`) and map members
    (`servers:map:<map>`) after the churn and its wait as before the first cycle (names compared, not
    counts). Before is taken with only the rendered clients in the world, so it must hold their sessions:
    a baseline that does not is INCONCLUSIVE."""
    pts = {r.get("label"): r for r in _raw_records(ev, "redis")}
    if "before" not in pts or "after" not in pts:
        return _inconclusive("no before/after Redis record (the step did not finish)", source="rawprobe.ndjson")
    b, af = pts["before"], pts["after"]
    if len(b["session_keys"]) != len(ev["clients"]):
        return _inconclusive(f"baseline has {len(b['session_keys'])} session keys for {len(ev['clients'])} rendered clients",
                             source="redis SCAN session:*")
    diff = {k: {"leaked": sorted(set(af[k]) - set(b[k])), "lost": sorted(set(b[k]) - set(af[k]))}
            for k in ("session_keys", "registry_keys", "map_members")}
    bad = any(v["leaked"] or v["lost"] for v in diff.values())
    return _result(FAIL if bad else PASS,
                   {k: {"before": len(b[k]), "after": len(af[k])} for k in ("session_keys", "registry_keys", "map_members")},
                   "identical key sets", source="redis-cli --scan session:* and servers:id:*, SMEMBERS servers:map:<map> "
                                                "(docker exec rpgs-redis; scratch stack only)",
                   sampling="before the first cycle, after the wait", detail=diff,
                   rationale="a gateway session or registry entry that outlives its player is a leak that grows with every "
                             "join; the scratch stack is the only writer of these keys, so any difference is ours",
                   artifacts=[str(ev["run_dir"] / "rawprobe.ndjson")])


CHECKS.update({
    "server_alive": check_server_alive,
    "client_sessions": check_client_sessions,
    "malformed_input": check_malformed_input,
    "churn_cycles": check_churn_cycles,
    "churn_ghosts": check_churn_ghosts,
    "player_count_baseline": check_player_count_baseline,
    "redis_leak": check_redis_leak,
})


# S18 packet impairment checks register themselves in CHECKS (they use the helpers above).
from . import analyze_netem  # noqa: E402,F401
