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

from . import util

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
    expected = int(a.get("expected", len(ev["clients"]))) + int(a.get("plus_bots", 0) and (ev["scenario"].get("bots") or {}).get("players", 0))
    rows = _status_in_window(ev)
    if not rows:
        return _inconclusive("no /status samples inside the scenario window", source="/status")
    vals = [r.get("players_online") for r in rows]
    mode = a.get("mode", "max")
    measured = max(vals) if mode == "max" else vals[-1]
    return _result(PASS if measured == expected else FAIL, measured, expected,
                   source="gameserver /status players_online", sampling=f"1 Hz, {len(rows)} samples, {mode}",
                   rationale="every client must be a live player on the server",
                   artifacts=[str(ev["run_dir"] / "server" / "status.ndjson")])


def check_redis(ev, a):
    r = ev["redis"]
    if not r:
        return _inconclusive("redis.json missing", source="redis (docker exec rpgs-redis)")
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
    rows, failures, checked = [], 0, 0
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
                continue
            checked += 1
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            dist = math.hypot(dx, dy)
            want = (s["x"], s["y"])
            wn = math.hypot(*want) or 1.0
            cos = (dx * want[0] + dy * want[1]) / (dist * wn) if dist > 1e-6 else 0.0
            expected = speed * (s["t1"] - s["t0"] - settle)
            ok = cos >= min_cos and dist >= min_fraction * expected
            failures += 0 if ok else 1
            rows.append({"client": c["index"], "step": [s["t0"], s["t1"]], "dir": [s["x"], s["y"]],
                         "moved": round(dist, 3), "expected_at_speed": round(expected, 3), "cos": round(cos, 3),
                         "moves_read": reads, "ok": ok})
    if checked == 0:
        return _inconclusive("no move segment had server samples on both ends", source="/debug/entities + plan.json")
    return _result(PASS if failures == 0 else FAIL, f"{checked - failures}/{checked} segments",
                   {"min_cos": min_cos, "min_distance_fraction": min_fraction},
                   source="plan.json move steps vs server /debug/entities trajectory of the client's own player",
                   sampling=f"server positions at {ev['scenario'].get('server_sample_hz')} Hz",
                   rationale="input issued must be input consumed: the server entity moves in the scripted direction "
                             "at a plausible fraction of its speed (obstacles and stops excepted by the threshold)",
                   detail={"segments": rows})


def _divergence(ev, a, *, local: bool):
    lag = float(a.get("window_before_s", 0.6 if not local else 0.3))
    lead = float(a.get("window_after_s", 0.15 if not local else 0.6))
    types = set(a.get("types", ["mob", "player"]))
    rendered, received = [], []
    worst = []
    for c in ev["clients"]:
        for s in c["samples"]:
            st = s.get("st")
            if st is None or st < float(a.get("skip_first_s", 2.0)):
                continue
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
                rendered.append(d)
                if len(row) >= 7:
                    dr = _dist_to_path(t, st - lag, st + lead, row[5], row[6])
                    if dr is not None:
                        received.append(dr)
                if d > float(a.get("max", 1.0)):
                    worst.append({"client": c["index"], "st": round(st, 3), "id": eid, "type": etype,
                                  "rendered_err": round(d, 3)})
    return rendered, received, worst


def check_position_divergence(ev, a):
    local = bool(a.get("local", False))
    rendered, received, worst = _divergence(ev, a, local=local)
    if len(rendered) < int(a.get("min_samples", 50)):
        return _inconclusive(f"{len(rendered)} comparable samples (< {a.get('min_samples', 50)})",
                             source="client samples.ndjson vs server /debug/entities")
    p95, mx = util.percentile(rendered, 95), max(rendered)
    rp95 = util.percentile(received, 95) if received else None
    ok = p95 <= float(a.get("p95", 0.35)) and mx <= float(a.get("max", 1.0))
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
    return _result(PASS if ok else FAIL,
                   {"p50": round(util.percentile(rendered, 50), 4), "p95": round(p95, 4), "max": round(mx, 4),
                    "received_p95": None if rp95 is None else round(rp95, 4), "samples": len(rendered)},
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
    counts = {"local_major": 0, "local_minor": 0, "remote_major": 0, "remote_minor": 0, "server_teleport": 0}
    by_type = {}
    for c in ev["clients"]:
        js = [e for e in c["events"] if e.get("event") == "render_jump" and (e.get("st") or -1) >= skip]
        per_client[c["index"]] = len(js)
        for e in js:
            # A step the SERVER also made (respawn, teleport, portal) is the game, not a render
            # defect: the server path covered >= 80% of the rendered step around that instant.
            server_step = _server_displacement(ev, e.get("id"), e.get("st"))
            # ...and the server's own move was faster than any entity can walk in that window
            # (0.8 s at max_speed, +20%): only then is it a teleport rather than ordinary motion.
            walkable = float(ev["scenario"].get("jump", {}).get("max_speed", 6.0)) * 0.8 * 1.2
            respawned = _server_respawned(ev, e.get("id"), e.get("st"))
            if respawned or (server_step is not None and server_step >= 0.8 * (e.get("step") or 0)
                             and server_step > walkable):
                counts["server_teleport"] = counts.get("server_teleport", 0) + 1
                events.append({"client": c["index"], "class": "server_teleport", "server_step": round(server_step, 3),
                               **{k: e.get(k) for k in ("st", "id", "type", "local", "step", "allowed", "dt_ms")}})
                continue
            key = ("local" if e.get("local") else "remote") + ("_major" if (e.get("step") or 0) >= major_step else "_minor")
            counts[key] += 1
            by_type[e.get("type")] = by_type.get(e.get("type"), 0) + 1
            events.append({"client": c["index"], "class": key,
                           **{k: e.get(k) for k in ("st", "id", "type", "local", "step", "allowed", "dt_ms")}})
    if not any(c["summary"] for c in ev["clients"]):
        return _inconclusive("no client summary", source="client events.ndjson render_jump")
    minutes = max(1e-6, float(ev["scenario"].get("duration_s", 60)) / 60.0)
    n = max(1, len(ev["clients"]))
    rate = {k: round(v / minutes / n, 3) for k, v in counts.items() if k != "server_teleport"}
    ok = (counts["local_major"] <= int(a.get("max_local", 0)) and
          rate["remote_major"] <= float(a.get("max_remote_per_client_min", 2.0)) and
          rate["local_minor"] <= float(a.get("max_local_minor_per_client_min", 30.0)) and
          rate["remote_minor"] <= float(a.get("max_remote_minor_per_client_min", 30.0)))
    attributed = []
    for e in sorted(events, key=lambda x: -(x.get("step") or 0))[:30]:
        t = ev["traj"].get(e["id"])
        if not t or e.get("st") is None:
            continue
        p0, p1 = _pos_at(t, e["st"] - 0.25), _pos_at(t, e["st"] + 0.05)
        server_step = None if p0 is None or p1 is None else round(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 3)
        attributed.append({**e, "server_step_0p3s": server_step})
    return _result(PASS if ok else FAIL,
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


def _server_respawned(ev, eid, st, before=0.6, after=0.3) -> bool:
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


def _server_displacement(ev, eid, st, before=0.6, after=0.2):
    """Largest distance the server moved the entity between any two samples in [st-before, st+after]."""
    t = ev["traj"].get(eid)
    if not t or st is None:
        return None
    pts = [(x, y) for s2, x, y in zip(t["st"], t["x"], t["y"]) if st - before <= s2 <= st + after]
    if len(pts) < 2:
        return None
    best = 0.0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            best = max(best, math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]))
    return best


def check_snapshot_cadence(ev, a):
    hz = None
    rows = _status_in_window(ev)
    if rows:
        hz = rows[-1].get("sim_world_hz")
    hz = float(a.get("expected_hz", hz or 15))
    per = {}
    bad = 0
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
        bad += 0 if ok else 1
        per[c["index"]] = {"rate_hz": round(rate, 2), "p99_gap_ms": p99_gap and round(p99_gap, 1),
                           "max_gap_ms": max_gap and round(max_gap, 1), "ok": ok}
    return _result(PASS if bad == 0 else FAIL, per,
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
    if missing == len(ev["clients"]):
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
    if not vals:
        return _inconclusive("field absent", source="/status snapshot_max_update_gap_ms")
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
    if max_share_spread is not None and max_share_spread > float(a.get("max_share_when_spread", 0.9)):
        findings.append(f"with players >= {a.get('spread_distance', 10)} apart, one player still drew "
                        f"{max_share_spread:.0%} of enemies")
        status = FAIL
    if overlap is not None and overlap > float(a.get("max_overlap_ratio", 0.5)):
        findings.append(f"median {overlap:.0%} of enemies overlap another enemy within {overlap_r} units")
        status = FAIL if a.get("overlap_is_failure", False) else (status if status == FAIL else INFO)
    measured = {"samples": len(per_sample), "median_overlap_ratio": overlap,
                "median_max_target_share": util.percentile([s["max_target_share"] for s in per_sample], 50),
                "max_target_share_when_spread": max_share_spread,
                "median_at_contact_ratio": util.percentile([s["at_contact_ratio"] for s in per_sample], 50),
                "median_nn": util.percentile([s["nn_median"] for s in per_sample if s["nn_median"] is not None], 50)}
    return _result(status, measured,
                   {"max_share_when_spread": a.get("max_share_when_spread", 0.9),
                    "max_overlap_ratio": a.get("max_overlap_ratio", 0.5),
                    "overlap_is_failure": a.get("overlap_is_failure", False)},
                   source="server /debug/entities; target derived with the server's own rule (nearest live player, "
                          "EnemyMoveSystem/PlayerTargetBuffer.TryNearest)",
                   sampling=f"{len(per_sample)} evenly spaced server samples",
                   rationale="concentration on one player is EXPECTED when players stand together (nearest-player rule); "
                             "it is a defect only when players are spread and one still draws nearly all. Overlap is a "
                             "design gap (no separation exists in EnemyAiSystems), reported as INFO unless the scenario "
                             "declares separation required",
                   detail={"findings": findings, "timeline": per_sample[:: max(1, len(per_sample) // 20)]},
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
    c = ev["clients"][k]
    hist = c["history"]
    launches = [h for h in hist.get("history", []) if h.get("event") == "launch"]
    first_uid = hist.get("first_user_id")
    final_uid = ids[k]
    last = ev["server"]["entities"][-1] if ev["server"]["entities"] else None
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
    "enemy_server_speed": check_enemy_server_speed,
    "enemy_render_speed": check_enemy_render_speed,
    "combat_effect": check_combat_effect,
    "reconnect": check_reconnect,
    "memory_growth": check_memory_growth,
    "entity_stability": check_entity_stability,
    "bots_joined": check_bots_joined,
}


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
