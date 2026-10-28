"""failure-summary.json: a derived, machine-readable triage of a run that is not a clean PASS.

Derived output only. It reads the evidence and the check results `analyze` already produced and
never changes either: the verdict, every check status and results.json are decided before this
module runs, and `write` swallows its own errors (a broken summary is reported inside the summary,
never as a different verdict). The rules below are the documented ones in testlab/docs/FAILURE-SUMMARY.md;
change them in both places and bump RULES_VERSION.

Per failing / invalid check the summary gives the earliest event it can locate (scenario time and
wall-clock UTC), the evidence files with line pointers, the suspected layer, a confidence, the host
guard events within +-GUARD_WINDOW_S of that event, and the next action from NEXT_ACTIONS.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import analyze, util

SCHEMA = "rpg.testlab.failure-summary.v1"
RULES_VERSION = 1
FILE_NAME = "failure-summary.json"
GUARD_WINDOW_S = 10.0
# scenario time -> wall time is the scheduled start plus st, accurate to about 5 s (the guard sampling
# interval; analyze._long_frames_with_guard_events uses the same mapping).
MAX_EVIDENCE = 8

LAYERS = ("environment", "harness", "server", "netcode", "client", "unknown")

# --------------------------------------------------------------------------- rule tables (documented)

# L4: the default layer of a check, a prior about where its failures originate. Used only when no
# direct evidence (L1-L3) decides the layer, and then the confidence is at most "medium".
LAYER_BY_CHECK = {
    "host_guard": "environment", "host_quiet": "environment",
    "provenance": "harness", "clients_completed": "harness", "clients_in_world": "harness",
    "distinct_user_ids": "harness", "same_game_server": "harness", "bots_joined": "harness",
    "netem_applied": "harness", "netem_cleanup": "harness",
    "server_tick": "server", "server_alive": "server", "server_config": "server", "kcp_health": "server",
    "snapshot_cadence": "server", "snapshot_update_gap": "server", "snapshot_order": "server",
    "tick_adoption": "server", "enemy_bounds": "server", "enemy_budget": "server", "enemy_crowding": "server",
    "enemy_pursuit": "server", "enemy_server_speed": "server", "spawn_overlap": "server",
    "players_online": "server", "player_count_baseline": "server", "redis": "server", "redis_leak": "server",
    "input_rejections": "server", "malformed_input": "server", "inputs_consumed": "server",
    "debug_kill_respawn": "server", "cast_damage_bound": "server", "combat_effect": "server",
    "trajectory_bound": "server", "entity_stability": "server", "graceful_leave": "server",
    "reconnect": "server", "churn_cycles": "server", "churn_ghosts": "server",
    "render_jumps": "netcode", "entity_lifecycle": "netcode", "cross_client_convergence": "netcode",
    "prediction_bound": "netcode", "render_freshness": "netcode", "stall_recovery": "netcode",
    "enemy_render_speed": "netcode", "position_divergence": "netcode", "client_sessions": "netcode",
    "netem_snapshots": "netcode", "netem_convergence": "netcode", "netem_prediction": "netcode",
    "netem_retransmits": "netcode",
    "frame_time": "client", "memory_growth": "client", "client_log_clean": "client",
}

# The next action: the check's own entry first, then its layer's. Diagnostics and corrective
# actions to take by hand; nothing here is run automatically.
NEXT_ACTIONS_BY_CHECK = {
    "kcp_health": "Open server/metrics-start.txt and metrics-end.txt for the reason= counters, then the server log "
                  "(server/gameserver.log) around the first session close; rerun the scenario to see whether it repeats.",
    "snapshot_cadence": "Run `testlab.py analyze --delivery <run>` to place the gap in the snapshot delivery path "
                        "(server enqueue, KCP write, client receive) before changing any code.",
    "snapshot_update_gap": "Run `testlab.py analyze --delivery <run>`; compare server/snapshot-trace.csv with the client delivery.csv.",
    "render_jumps": "Open the render_jump rows in the cited events.ndjson and the same instant in samples.ndjson; "
                    "run `testlab.py replay-trace <run>` if a predictor trace exists, to split prediction from interpolation.",
    "entity_lifecycle": "Open the cited events.ndjson rows (entity_added/entity_removed) and the rendered samples at that time; "
                        "check id reuse and AOI re-entry in the Netcode view lifecycle.",
    "cross_client_convergence": "Compare the two clients' samples.ndjson at the cited render tick; check whether the entity "
                                "was in both clients' snapshots (client snapshots.ndjson) before blaming interpolation.",
    "prediction_bound": "Run `testlab.py replay-trace <run>` and compare the correction sizes with the stalls in events.ndjson.",
    "frame_time": "Open frames.csv at the cited time and the host/procs.ndjson process samples for the same seconds.",
    "provenance": "Fix the provenance gap named in the check detail (commit, image, player build) and rerun; the evidence cannot grade a candidate.",
}
NEXT_ACTIONS_BY_LAYER = {
    "environment": "Rerun on a quiet host (no remote-desktop session, no foreign build or antivirus load); the evidence "
                   "of this run is not a verdict on the candidate.",
    "harness": "Read orchestrator.log and harness-error.txt, fix the harness or the run setup, then rerun.",
    "server": "Open the cited server files, then the server log around the earliest event; reproduce with a rerun "
              "before changing server code.",
    "netcode": "Open the cited client files around the earliest event; reproduce with a rerun and a predictor trace "
               "before changing Netcode.",
    "client": "Open the cited client files around the earliest event; reproduce with a rerun before changing the client.",
    "unknown": "No rule places this failure. Open the cited artifacts and the check detail in results.json by hand.",
}

CONFIDENCE_RULES = {
    "high": "the layer comes from direct evidence (L1 INVALID/host check, L2 harness error, L3 a guard event within "
            "+-10 s) and the earliest event is located",
    "medium": "the earliest event is located and a host guard recorded the run with no guard event within +-10 s, "
              "but the layer is the default prior of the check (L4)",
    "low": "the earliest event is not located, or no guard evidence exists, or the layer is unknown, or the run is "
           "INVALID and the failure is not near a guard event",
}
LAYER_RULES = {
    "L1": "the check is INVALID or is host_guard / host_quiet: environment",
    "L2": "the run has a harness error, the check raised or is unknown, or it is a harness check (provenance, "
          "clients_*, ...): harness",
    "L3": "a host guard event or a host-wide stall lies within +-10 s of the earliest event: environment "
          "(the default layer is kept as `alternative_layer`)",
    "L4": "the default layer of the check (LAYER_BY_CHECK)",
    "L5": "the check is not in the table: unknown",
}


# --------------------------------------------------------------------------- time

def _parse_utc(text: str) -> float | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z?$", text.strip())
    if not m:
        return None
    base = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return base + (float(m.group(2)) if m.group(2) else 0.0)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(round(epoch % 1 * 1000)) % 1000:03d}Z"


def start_epoch(ev: dict) -> float | None:
    """Wall-clock epoch of scenario time 0: the host guard's scheduled start, else the run's start_scheduled event."""
    meta = ev.get("meta") or {}
    s = (meta.get("host_guard") or {}).get("start_wall_epoch")
    if s is not None:
        return float(s)
    for t in meta.get("timeline") or []:
        if t.get("event") == "start_scheduled" and t.get("start_wall_utc"):
            return _parse_utc(t["start_wall_utc"])
    return None


# --------------------------------------------------------------------------- file helpers

def _rel(ev: dict, path) -> str:
    """A path as it reads from the run directory, with forward slashes (artifacts are stored with the
    separators of the host that ran the lab)."""
    text = str(path).replace("\\", "/")
    run = os.path.abspath(str(ev["run_dir"])).replace("\\", "/").rstrip("/") + "/"
    if re.match(r"^([A-Za-z]:)?/", text):
        if text.startswith(run):
            return text[len(run):]
        return text
    absolute = os.path.abspath(text).replace("\\", "/")
    if absolute.startswith(run):
        return absolute[len(run):]
    return text[2:] if text.startswith("./") else text


def _lines(path: Path):
    """(line_number, text) of a text file, streamed; nothing when it does not exist."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                yield n, line
    except OSError:
        return


def _json_lines(path: Path, needle: str | None = None):
    for n, line in _lines(path):
        if needle is not None and needle not in line:
            continue
        try:
            yield n, json.loads(line)
        except ValueError:
            continue


def _client_dir(ev: dict, index) -> Path:
    for c in ev.get("clients") or []:
        if c["index"] == index:
            return Path(c["dir"])
    return Path(ev["run_dir"]) / f"client-{index}"


def _t_offset(ev: dict, index) -> float | None:
    """Process time minus scenario time of a client, from its first events row that carries both."""
    for _, row in _json_lines(_client_dir(ev, index) / "events.ndjson"):
        if row.get("st") is not None and row.get("st") >= 0 and row.get("t") is not None:
            return float(row["t"]) - float(row["st"])
    return None


def _cand(ev, st, path, line=None, find=None, what="", client=None) -> dict:
    return {"st": None if st is None else round(float(st), 3), "file": _rel(ev, path) if path else None,
            "line": line, "find": find, "what": what, "client": client}


# --------------------------------------------------------------------------- earliest-event locators
# Each returns candidate events [{st, file, line, find, what, client}], any order; the earliest by st
# is the check's earliest event. A locator that cannot place the failure in time returns candidates
# with st None (evidence only) or [].

def _loc_render_jumps(ev, res):
    """The counted jumps of the classes that breach their limit (the side channel of check_render_jumps, set when
    the analysis ran in this process). Without it only `detail.largest` is left, which holds the biggest steps
    (mostly server teleports): then the earliest counted jump is not located rather than guessed."""
    side = (ev.get("_failsum") or {}).get("render_jumps")
    if side is not None:
        breaching = set(side.get("breaching") or [])
        counted = [e for e in side.get("events") or [] if e.get("class") in breaching and e.get("st") is not None]
    else:
        counted = [e for e in (res.get("detail") or {}).get("largest") or []
                   if e.get("class") not in (None, "server_teleport") and e.get("st") is not None]
    out = []
    for e in counted:
        path = Path(_client_dir(ev, e["client"])) / "events.ndjson"
        line = next((n for n, row in _json_lines(path, '"render_jump"')
                     if row.get("event") == "render_jump" and abs((row.get("st") or -1e9) - e["st"]) < 1e-4), None)
        out.append(_cand(ev, e["st"], path, line, None,
                         f"render_jump {e.get('class')} step {e.get('step')} (allowed {e.get('allowed')}) of "
                         f"{'local player' if e.get('local') else e.get('type')} {e.get('id')}", e["client"]))
    if not out:
        for c in ev["clients"]:
            out.append(_cand(ev, None, Path(c["dir"]) / "events.ndjson", what="render_jump rows (the counted jump is not located)",
                             client=c["index"]))
    return out


def _loc_snapshot_gaps(ev, res):
    """First snapshot gap over the limit, per client that failed."""
    limit = float((res.get("threshold") or {}).get("max_gap_ms", 250)) / 1000.0
    out = []
    for c in ev["clients"]:
        per = (res.get("measured") or {}).get(str(c["index"])) or (res.get("measured") or {}).get(c["index"])
        if isinstance(per, dict) and per.get("ok") is True:
            continue
        start = (c.get("summary") or {}).get("start_realtime")
        path = Path(c["dir"]) / "snapshots.ndjson"
        if start is None:
            out.append(_cand(ev, None, path, what="snapshot gap (client summary has no start_realtime)", client=c["index"]))
            continue
        prev = None
        for n, row in _json_lines(path):
            t = row.get("t")
            if t is None:
                continue
            if prev is not None and prev[1] >= start and t - prev[1] > limit:
                out.append(_cand(ev, prev[1] - start, path, prev[0],
                                 what=f"snapshot gap {round((t - prev[1]) * 1000, 1)} ms after tick {prev[2]} "
                                      f"(limit {round(limit * 1000)} ms)", client=c["index"]))
                break
            prev = (n, t, row.get("tick"))
    return out


def _loc_entity_lifecycle(ev, res):
    d = res.get("detail") or {}
    items = []
    for key, tkey in (("lingering", "removed_t"), ("reuse_drawn_elsewhere", "t"), ("duplicate_ids", "t")):
        for e in d.get(key) or []:
            if e.get(tkey) is not None and e.get("client") is not None:
                items.append((key, e, float(e[tkey])))
    out, offsets = [], {}
    for key, e, t in items:
        off = offsets.setdefault(e["client"], _t_offset(ev, e["client"]))
        st = None if off is None else t - off
        path = _client_dir(ev, e["client"]) / ("samples.ndjson" if key == "duplicate_ids" else "events.ndjson")
        out.append(_cand(ev, st, path, None, {"t": t, "id": e.get("id")},
                         f"{key} id {e.get('id')} (process time t={t})", e["client"]))
    return out


def _loc_convergence(ev, res):
    """Map the worst pair's render ticks to scenario time through client a's snapshots (tick -> receive time)."""
    out = []
    for w in (res.get("detail") or {}).get("worst") or []:
        c = next((c for c in ev["clients"] if c["index"] == w.get("a")), None)
        start = ((c or {}).get("summary") or {}).get("start_realtime")
        path = Path(c["dir"]) / "snapshots.ndjson" if c else None
        st = line = None
        if c and start is not None and w.get("render_tick") is not None:
            best = None
            for n, row in _json_lines(path):
                if row.get("tick") is None or row.get("t") is None:
                    continue
                dist = abs(row["tick"] - w["render_tick"])
                if best is None or dist < best[0]:
                    best = (dist, n, row["t"] - start)
            if best:
                st, line = best[2], best[1]
        out.append(_cand(ev, st, path, line, {"render_tick": w.get("render_tick")},
                         f"clients {w.get('a')}/{w.get('b')} drew {w.get('id')} {w.get('dist')} units apart at render tick "
                         f"{round(w.get('render_tick') or 0, 1)}", w.get("a")))
    return out


def _loc_kcp(ev, res):
    """The counters are two scrapes: no time, but the lines that carry the failing counters."""
    out = []
    path = Path(ev["run_dir"]) / "server" / "metrics-end.txt"
    for n, line in _lines(path):
        if line.startswith(("gameserver_kcp_datagrams_dropped_total", "gameserver_kcp_sessions_closed_total",
                            "gameserver_kcp_sessions_rejected_total")) and not line.rstrip().endswith(" 0"):
            out.append(_cand(ev, None, path, n, what=f"counter at scenario end: {line.strip()[:120]} "
                                                     "(two scrapes: no time of occurrence)"))
    return out


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")


def _loc_host_guard(ev, res):
    """Per fired guard, the first evidence stamp at or after the scenario start (a minute-resolution connection
    entry only when nothing else exists). Evidence from before the start means the condition was already
    active when the scenario began: scenario time 0."""
    out = []
    run = Path(ev["run_dir"])
    events_path = run / "host" / "anydesk-events.ndjson"
    s0 = start_epoch(ev)
    for f in (res.get("detail") or {}).get("fired") or []:
        precise = [(_parse_utc(m), e) for e in f.get("evidence") or [] if "minute resolution" not in e for m in _ISO.findall(e)]
        coarse = [(_parse_utc(m), e) for e in f.get("evidence") or [] if "minute resolution" in e for m in _ISO.findall(e)]
        pool = sorted((x for x in (precise or coarse) if x[0] is not None), key=lambda x: x[0])
        if not pool or s0 is None:
            out.append(_cand(ev, None, run / "host" / "guard.ndjson", what=f"guard {f.get('id')} fired: {f.get('rule', '')[:90]}"))
            continue
        inside = [x for x in pool if x[0] >= s0]
        first = inside[0][0] if inside else s0
        what = (f"guard {f.get('id')} first evidence {_iso(first)} ({f.get('count')} event(s)): {f.get('rule', '')[:80]}" if inside else
                f"guard {f.get('id')} already active at scenario start (evidence from {_iso(pool[-1][0])}): {f.get('rule', '')[:80]}")
        line = next((n for n, row in _json_lines(events_path)
                     if row.get("epoch") is not None and abs(row["epoch"] - first) < 0.01), None) if inside else None
        out.append(_cand(ev, first - s0, events_path if line else run / "host" / "guard.ndjson", line, {"ts": _iso(first)}, what))
    return out


def _loc_generic(ev, res):
    """Any dict in the detail that carries a scenario time (`st`)."""
    best = []

    def walk(v, depth=0):
        if depth > 4:
            return
        if isinstance(v, dict):
            if isinstance(v.get("st"), (int, float)):
                best.append(float(v["st"]))
            for x in v.values():
                walk(x, depth + 1)
        elif isinstance(v, list):
            for x in v[:200]:
                walk(x, depth + 1)

    walk(res.get("detail"))
    if not best:
        return []
    return [_cand(ev, min(best), None, None, None, "earliest scenario time found in the check detail")]


LOCATORS = {
    "render_jumps": _loc_render_jumps, "snapshot_cadence": _loc_snapshot_gaps, "entity_lifecycle": _loc_entity_lifecycle,
    "cross_client_convergence": _loc_convergence, "kcp_health": _loc_kcp, "host_guard": _loc_host_guard,
}


# --------------------------------------------------------------------------- guard events near an instant

def guard_events_near(ev: dict, epoch: float | None, within_s: float = GUARD_WINDOW_S) -> list[dict]:
    """Host guard events within +-within_s of a wall-clock instant, nearest first (offset_s is event minus instant):
    AnyDesk log events, an AnyDesk session that is active at the instant, and guard samples whose AnyDesk CPU
    is over the G3 limit that the host_guard check recorded."""
    if epoch is None:
        return []
    hg = ev.get("hostguard") or {}
    out = []
    open_since = None
    for e in sorted((e for e in hg.get("events") or [] if e.get("epoch") is not None), key=lambda e: e["epoch"]):
        if e["type"] == "session_started":
            open_since = e["epoch"]
        elif e["type"] == "session_closed":
            if open_since is not None and open_since <= epoch <= e["epoch"]:
                out.append({"source": "anydesk-events.ndjson", "kind": "session_active", "ts": _iso(open_since), "offset_s": 0.0})
            open_since = None
        if abs(e["epoch"] - epoch) <= within_s:
            out.append({"source": "anydesk-events.ndjson", "kind": e.get("type"), "ts": e.get("ts"),
                        "offset_s": round(e["epoch"] - epoch, 2)})
    if open_since is not None and open_since <= epoch:
        out.append({"source": "anydesk-events.ndjson", "kind": "session_active", "ts": _iso(open_since), "offset_s": 0.0})
    limit = None
    for r in ev.get("_results") or []:
        if r.get("check") == "host_guard":
            for f in (r.get("detail") or {}).get("fired") or []:
                if f.get("id") == "G3":
                    limit = f.get("threshold_pct")
    if limit is not None:
        for smp in hg.get("samples") or []:
            if smp.get("epoch") is not None and abs(smp["epoch"] - epoch) <= within_s and float(smp.get("ad_cpu") or 0.0) >= float(limit):
                out.append({"source": "guard.ndjson", "kind": f"AnyDesk CPU {smp.get('ad_cpu')} % of host (G3 limit {limit} %)",
                            "ts": smp.get("ts"), "offset_s": round(smp["epoch"] - epoch, 2)})
    out.sort(key=lambda e: abs(e["offset_s"]))
    seen, uniq = set(), []
    for e in out:
        k = (e["source"], e["ts"], e["kind"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq[:10]


def _in_host_stall(ev, st) -> bool:
    try:
        return st is not None and analyze._in_stall(analyze.host_stalls(ev), st, st, slack=GUARD_WINDOW_S, after=GUARD_WINDOW_S)
    except Exception:
        return False


# --------------------------------------------------------------------------- one failure

def _is_reportable(r: dict) -> bool:
    if r.get("status") in (analyze.FAIL, analyze.INVALID, analyze.INCONCLUSIVE):
        return True
    return r.get("status") == analyze.INFO and (r.get("detail") or {}).get("would_be") == analyze.FAIL


def _layer(check, status, harness_issue, near_guard, in_stall):
    base = LAYER_BY_CHECK.get(check)
    if status == analyze.INVALID or check in ("host_guard", "host_quiet"):
        return "environment", "L1", None
    if harness_issue:
        return "harness", "L2", base
    if near_guard or in_stall:
        return "environment", "L3", base
    if base:
        return base, "L4", None
    return "unknown", "L5", None


def _failure(ev, r, outcome, s0) -> dict:
    check = r.get("check")
    detail = r.get("detail") or {}
    why = detail.get("why") or ""
    harness_issue = (str(why).startswith(("check raised", "unknown check")) or LAYER_BY_CHECK.get(check) == "harness")
    cands = (LOCATORS.get(check) or _loc_generic)(ev, r)
    if not cands and check not in LOCATORS:
        cands = []
    located = sorted((c for c in cands if c["st"] is not None), key=lambda c: c["st"])
    earliest = located[0] if located else None
    wall = None if earliest is None or s0 is None else s0 + earliest["st"]
    near = guard_events_near(ev, wall)
    stall = _in_host_stall(ev, None if earliest is None else earliest["st"])
    layer, rule, alt = _layer(check, r.get("status"), harness_issue, bool(near), stall)
    guard_recorded = bool((ev.get("hostguard") or {}).get("samples"))
    if earliest is None or layer == "unknown":
        conf = "low"
    elif rule in ("L1", "L2", "L3"):
        conf = "high"
    elif guard_recorded and outcome != analyze.INVALID:
        conf = "medium"
    else:
        conf = "low"
    evidence = []
    for c in (located[:3] or cands[:3]):
        if c["file"]:
            evidence.append({"file": c["file"], "line": c["line"], "find": c["find"], "client": c["client"], "note": c["what"]})
    for a in (r.get("artifacts") or []):
        rel = _rel(ev, a)
        if len(evidence) >= MAX_EVIDENCE:
            break
        if not any(e["file"] == rel for e in evidence):
            evidence.append({"file": rel, "line": None, "find": None, "client": None, "note": "artifact named by the check"})
    return {
        "id": r.get("id"), "check": check, "status": r.get("status"),
        "informational_breach": r.get("status") == analyze.INFO,
        "measured": r.get("measured"), "threshold": r.get("threshold"),
        "earliest_event": None if earliest is None else {
            "scenario_s": earliest["st"], "wall_utc": None if wall is None else _iso(wall),
            "client": earliest["client"], "what": earliest["what"]},
        "event_candidates": len(cands),
        "evidence": evidence,
        "suspected_layer": layer, "layer_rule": rule, "alternative_layer": alt,
        "confidence": conf,
        "guard_events_within_10s": near, "in_host_stall_window": stall,
        "next_action": NEXT_ACTIONS_BY_CHECK.get(check) if layer == LAYER_BY_CHECK.get(check) and check in NEXT_ACTIONS_BY_CHECK
        else NEXT_ACTIONS_BY_LAYER[layer],
    }


# --------------------------------------------------------------------------- the summary

def build(run_dir, ev: dict, results: list[dict], outcome: str, harness_error: str | None) -> dict | None:
    """The summary of a run, or None for a clean PASS. Pure of the verdict: reads results, never edits them."""
    if outcome == analyze.PASS and not harness_error:
        return None
    ev = dict(ev)
    ev["_results"] = results
    s0 = start_epoch(ev)
    failures = []
    if harness_error:
        failures.append({
            "id": "harness_error", "check": "harness", "status": "ERROR", "informational_breach": False,
            "measured": None, "threshold": None, "earliest_event": None, "event_candidates": 0,
            "evidence": [{"file": "harness-error.txt", "line": None, "find": None, "client": None, "note": str(harness_error)[:300]},
                         {"file": "orchestrator.log", "line": None, "find": None, "client": None, "note": "run log"}],
            "suspected_layer": "harness", "layer_rule": "L2", "alternative_layer": None, "confidence": "low",
            "guard_events_within_10s": [], "in_host_stall_window": False,
            "next_action": NEXT_ACTIONS_BY_LAYER["harness"]})
    for r in results:
        if _is_reportable(r):
            failures.append(_failure(ev, r, outcome, s0))
    timed = [f for f in failures if f["earliest_event"]]
    first = min(timed, key=lambda f: f["earliest_event"]["scenario_s"]) if timed else None
    return {
        "schema": SCHEMA, "rules_version": RULES_VERSION, "derived_only": True,
        "note": "derived from results.json and the run evidence; it never changes the verdict or a check result",
        "run_id": (ev.get("meta") or {}).get("run_id"),
        "scenario": (ev.get("scenario") or {}).get("id"),
        "verdict": outcome, "exit_code": None,
        "scenario_start_utc": None if s0 is None else _iso(s0),
        "earliest_event": None if first is None else {**first["earliest_event"], "check": first["id"]},
        "failures": failures,
        "rules": {"layers": LAYER_RULES, "confidence": CONFIDENCE_RULES, "guard_window_s": GUARD_WINDOW_S,
                  "doc": "testlab/docs/FAILURE-SUMMARY.md"},
    }


def write(run_dir, ev, results, outcome, harness_error, out_dir) -> Path | None:
    """Write failure-summary.json beside report.md. Never raises and never touches the verdict: a failure to
    build the summary is recorded in the file. A clean PASS writes nothing (and removes a stale summary of an
    earlier analysis in the same directory)."""
    out_dir = Path(out_dir)
    path = out_dir / FILE_NAME
    try:
        doc = build(run_dir, ev, results, outcome, harness_error)
    except Exception as exc:  # derived output must not break the analysis
        doc = {"schema": SCHEMA, "rules_version": RULES_VERSION, "derived_only": True, "verdict": outcome,
               "error": f"{type(exc).__name__}: {exc}", "failures": []}
    try:
        if doc is None:
            if path.exists() and (util.read_json(path, default={}) or {}).get("schema") == SCHEMA:
                path.unlink()
            return None
        from .report import EXIT_CODES
        doc["exit_code"] = EXIT_CODES.get(outcome, 2)
        out_dir.mkdir(parents=True, exist_ok=True)
        util.write_json(path, doc)
        return path
    except OSError:
        return None
