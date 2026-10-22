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
            "events": util.read_ndjson(d / "events.ndjson"),
            "samples": util.read_ndjson(d / "samples.ndjson"),
            "snapshots": util.read_ndjson(d / "snapshots.ndjson"),
            "inputs": util.read_ndjson(d / "inputs.ndjson"),
            "plan": util.read_json(d / "plan.json", default={}) or {},
            "logs": {p.name: p.read_text(encoding="utf-8", errors="replace") for p in logs},
            "frames": _read_frames(d / "frames.csv"),
            "history": (meta.get("clients") or {}).get(str(i), {}),
        })
    server_dir = run_dir / "server"
    entities = util.read_ndjson(server_dir / "entities.ndjson")
    ev = {
        "run_dir": run_dir,
        "meta": meta,
        "scenario": sc,
        "clients": clients,
        "server": {
            "entities": entities,
            "status": util.read_ndjson(server_dir / "status.ndjson"),
            "container": util.read_ndjson(server_dir / "container.ndjson"),
            "metrics_start": parse_prometheus((server_dir / "metrics-start.txt")),
            "metrics_end": parse_prometheus((server_dir / "metrics-end.txt")),
        },
        "redis": util.read_json(run_dir / "redis.json", default={}) or {},
        "bots": util.read_json(run_dir / "bots" / "loadtest.json", default=None),
    }
    ev["traj"] = trajectories(entities)
    return ev


def _read_frames(path: Path) -> list:
    """[(scenario_t, dt_ms)] for frames inside the scenario window (scenario_t >= 0)."""
    out = []
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


def trajectories(entities: list) -> dict:
    """{id: {"type": t, "st": [...], "x": [...], "y": [...], "hp": [...], "max_hp": .., "speed": ..}}"""
    traj = {}
    for row in entities:
        st = row.get("st")
        if st is None:
            continue
        for e in row["ents"]:
            eid, etype, x, y, hp, max_hp, dead, speed = (e + [None] * 8)[:8]
            t = traj.setdefault(eid, {"type": etype, "st": [], "x": [], "y": [], "hp": [], "dead": [],
                                       "max_hp": max_hp, "speed": speed})
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
    ids = []
    for c in ev["clients"]:
        uid = (c["summary"] or {}).get("user_id") or c["status"].get("user_id")
        ids.append(uid)
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
    best = None
    for i in range(i0, i1):
        if i + 1 < i1:
            d = _seg_dist(px, py, t["x"][i], t["y"][i], t["x"][i + 1], t["y"][i + 1])
        else:
            d = math.hypot(px - t["x"][i], py - t["y"][i])
        best = d if best is None or d < best else best
    return best


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
    return _result(PASS if not missing and n else FAIL, n - len(missing), n,
                   source="client events.ndjson 'in_world' (NetworkClientState.InWorld)", sampling="per client",
                   rationale="every launched client must complete auth, gateway redirect and KCP join",
                   detail={"missing": missing}, artifacts=[str(c["dir"] / "events.ndjson") for c in ev["clients"]])


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
    bad = {c["index"]: (c["summary"] or {}).get("outcome") for c in ev["clients"]
           if (c["summary"] or {}).get("outcome") != "completed"}
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
    rendered, received = [], []
    worst = []
    stalls = host_stalls(ev)
    stalled = []
    for c in ev["clients"]:
        for s in c["samples"]:
            st = s.get("st")
            if st is None or st < float(a.get("skip_first_s", 2.0)):
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
                    stalled.append(d)
                    continue
                rendered.append(d)
                if len(row) >= 7:
                    dr = _dist_to_path(t, st - lag, st + lead, row[5], row[6])
                    if dr is not None:
                        received.append(dr)
                if d > float(a.get("max", 1.0)):
                    worst.append({"client": c["index"], "st": round(st, 3), "id": eid, "type": etype,
                                  "rendered_err": round(d, 3)})
    return rendered, received, worst, stalled


def check_position_divergence(ev, a):
    local = bool(a.get("local", False))
    rendered, received, worst, stalled = _divergence(ev, a, local=local)
    if len(rendered) < int(a.get("min_samples", 50)):
        return _inconclusive(f"{len(rendered)} comparable samples (< {a.get('min_samples', 50)})",
                             source="client samples.ndjson vs server /debug/entities")
    p95, mx = util.percentile(rendered, 95), max(rendered)
    rp95 = util.percentile(received, 95) if received else None
    ok = p95 <= float(a.get("p95", 0.35)) and mx <= float(a.get("max", 1.0))
    stall_would_fail = bool(stalled) and max(stalled) > float(a.get("max", 1.0))
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
                   {"p50": round(util.percentile(rendered, 50), 4), "p95": round(p95, 4), "max": round(mx, 4),
                    "received_p95": None if rp95 is None else round(rp95, 4), "samples": len(rendered),
                    "in_host_stall": len(stalled),
                    "max_in_host_stall": round(max(stalled), 4) if stalled else None},
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
        stalls = host_stalls(ev)
        stall_events = all_stall_events
        for e in js:
            if e.get("type") in set(a.get("ignore_types", ["projectile"])):
                counts["ignored_type"] = counts.get("ignored_type", 0) + 1
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
            received_step = _received_step(c, e.get("id"), e.get("st"),
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
            if k not in ("server_teleport", "host_stall", "ignored_type")}
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
        inside = [x["t"] for x in snaps if start <= x["t"] <= start + dur]
        gaps = [b - a2 for a2, b in zip(inside, inside[1:])]
        rate = len(inside) / dur if dur else 0
        max_gap = max(gaps) * 1000 if gaps else None
        p99_gap = util.percentile([g * 1000 for g in gaps], 99) if gaps else None
        ok = (abs(rate - hz) <= hz * float(a.get("rate_tolerance", 0.2)) and max_gap is not None and
              max_gap <= float(a.get("max_gap_ms", 250)))
        if not ok and max_gap is not None:
            # Every over-limit gap overlaps a host-wide stall: the evidence cannot say anything
            # about the netcode, so this client's row is inconclusive rather than failed.
            limit = float(a.get("max_gap_ms", 250)) / 1000.0
            over = [(a2 - start, b - start) for a2, b in zip(inside, inside[1:]) if b - a2 > limit]
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
    ok = dropped <= float(a.get("max_dropped", 0)) and closed <= float(a.get("max_sessions_closed", 0)) and (rejected or 0) == 0
    return _result(PASS if ok else FAIL, {"dropped": dropped, "sessions_closed": closed, "sessions_rejected": rejected},
                   {"dropped": a.get("max_dropped", 0), "sessions_closed": a.get("max_sessions_closed", 0), "rejected": 0},
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
    rows = [r for r in ev["server"]["entities"] if r.get("st") is not None and lo + float(a.get("skip_first_s", 5)) <= r["st"] <= hi]
    if not rows:
        return _inconclusive("no server entity samples in window", source="/debug/entities")
    overlap_r = float(a.get("overlap_radius", 0.3))
    per_sample = []
    for r in rows[:: max(1, len(rows) // 60)]:
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
    rows = [r for r in ev["server"]["entities"]
            if r.get("st") is not None and lo + float(a.get("skip_first_s", 5)) <= r["st"] <= hi]
    if len(rows) < 2:
        return _inconclusive("fewer than two server entity samples in window", source="/debug/entities")
    far = float(a.get("far_distance", 3.0))
    settle = float(a.get("settle_distance", 2.6))
    moving_eps = float(a.get("moving_epsilon", 0.02))
    cos_max = math.cos(math.radians(float(a.get("max_heading_deg", 45))))
    crowd_r = float(a.get("crowd_radius", 1.2))
    crowd_steps = crowd_heading = 0
    far_steps = approaching = 0
    away = []
    settled_rel = []
    for r0, r1 in zip(rows, rows[1:]):
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
                   sampling=f"{len(rows)} server samples",
                   rationale="an enemy far from every player has no crowd to queue in, so every step it takes must "
                             "close on its target; the settled speed is how much a crowd at its target still moves "
                             "(jitter), measured relative to the target so a walking player is not counted",
                   detail={"findings": findings, "away": away},
                   artifacts=[str(ev["run_dir"] / "server" / "entities.ndjson")])


def check_spawn_overlap(ev, a):
    """Fresh player placements (first appearance, respawn) do not land on another live player."""
    min_d = float(a.get("min_distance", 0.5))
    rows = [r for r in ev["server"]["entities"] if r.get("st") is not None]
    if not rows:
        return _inconclusive("no server entity samples", source="/debug/entities")
    seen = {}
    spawns = []
    for r in rows:
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
                   sampling=f"{len(rows)} server samples",
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
    speeds = []
    worst = []
    for eid, t in ev["traj"].items():
        if t["type"] != "mob":
            continue
        for i in range(1, len(t["st"])):
            dt = t["st"][i] - t["st"][i - 1]
            if dt <= 0.05:
                continue
            v = math.hypot(t["x"][i] - t["x"][i - 1], t["y"][i] - t["y"][i - 1]) / dt
            speeds.append(v)
            if v > configured * tol:
                worst.append({"id": eid, "st": round(t["st"][i], 2), "speed": round(v, 3)})
    if not speeds:
        return _inconclusive("no enemy trajectories", source="/debug/entities")
    mx = max(speeds)
    # Probe sampling jitter (HTTP latency) inflates speeds measured over short intervals.
    ok = util.percentile(speeds, 99) <= configured * tol
    return _result(PASS if ok else FAIL, {"p99": round(util.percentile(speeds, 99), 3), "max": round(mx, 3), "n": len(speeds)},
                   {"p99_max": round(configured * tol, 3)}, source="server /debug/entities positions, consecutive samples",
                   sampling=f"{ev['scenario'].get('server_sample_hz')} Hz", rationale="server-side enemy speed must not "
                   "exceed GAMESERVER_ENEMY_SPEED; probe timing jitter is why p99, not max, decides",
                   detail={"worst": sorted(worst, key=lambda w: -w["speed"])[:10]})


def check_enemy_render_speed(ev, a):
    """'Enemies fly': rendered enemy speed seen by each client."""
    configured = float(a.get("speed", 2.5))
    tol = float(a.get("tolerance", 1.6))
    speeds, worst = [], []
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
                    speeds.append(v)
                    if v > configured * tol:
                        worst.append({"client": c["index"], "id": row[0], "st": round(st, 2), "speed": round(v, 2)})
                last[row[0]] = (st, row[3], row[4])
    if not speeds:
        return _inconclusive("no rendered enemy samples", source="client samples.ndjson")
    p99 = util.percentile(speeds, 99)
    frac = len(worst) / len(speeds)
    ok = p99 <= configured * tol and frac <= float(a.get("max_fast_fraction", 0.01))
    return _result(PASS if ok else FAIL, {"p50": round(util.percentile(speeds, 50), 3), "p99": round(p99, 3),
                                          "max": round(max(speeds), 3), "fast_fraction": round(frac, 4), "n": len(speeds)},
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
    inside = [r for r in ev["server"]["entities"] if r.get("st") is not None and lo <= r["st"] <= hi]
    # The last sample INSIDE the scenario window: after it, clients are quitting on purpose.
    last = inside[-1] if inside else None
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
    rows = [r for r in ev["server"]["entities"] if r.get("st") is not None and r["st"] >= float(a.get("skip_first_s", 10))]
    if len(rows) < 10:
        return _inconclusive("too few samples", source="/debug/entities")
    q = max(1, len(rows) // 4)
    first = sum(len(r["ents"]) for r in rows[:q]) / q
    lastq = sum(len(r["ents"]) for r in rows[-q:]) / q
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
    return PASS
