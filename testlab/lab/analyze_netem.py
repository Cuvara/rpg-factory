"""S18 packet impairment checks: they read netem.ndjson (lab/netem.py) next to the usual client and server evidence.

Imported at the bottom of lab/analyze.py, which registers them in CHECKS; the helpers they share
(_result, _inconclusive, check_cross_client_convergence, ...) live there.

Phases, in scenario time (see _netem_windows):
    baseline  = [skip_first_s, impaired_start]   impaired_start is the scrape taken BEFORE the first tc command
    impaired  = [apply_done, impaired_end]       apply_done is the instant the last tc command returned
    recovery  = [remove_done, end of scenario]   remove_done is when the verified removal returned
The seconds the tc commands take (WSL round trips) belong to no judged window.
"""

from __future__ import annotations

import math

from . import analyze as A
from . import util

PASS, FAIL, INCONCLUSIVE = A.PASS, A.FAIL, A.INCONCLUSIVE
NETEM_PACKET_SIGMAS = 3.0


def _netem_view(ev):
    """The impairment timeline from netem.ndjson, or (None, INCONCLUSIVE result)."""
    recs = ev.get("netem") or []
    if not recs:
        return None, A._inconclusive("no netem.ndjson (the impairment step did not run)", source="netem.ndjson")
    scrapes = {}
    for r in recs:
        if r.get("record") == "scrape" and r.get("label") != "tick":
            scrapes[r["label"]] = r
    first = lambda kind: next((r for r in recs if r.get("record") == kind), None)  # noqa: E731
    removes = [r for r in recs if r.get("record") == "remove"]
    return {"recs": recs, "plan": first("plan"), "scrapes": scrapes, "apply": first("apply"),
            "planned_remove": next((r for r in removes if r.get("reason") == "planned"), None),
            "removes": removes, "stats": first("stats"), "final": first("final_cleanup"),
            "errors": [r for r in recs if r.get("record") == "error"]}, None


def _netem_windows(view, ev, a=None):
    """{'baseline', 'impaired', 'recovery'} -> (lo, hi) in scenario time, or None when the step did not get
    far enough to define them."""
    a = a or {}
    sc, apply_, planned = view["scrapes"], view["apply"], view["planned_remove"]
    if not (apply_ and apply_.get("ok") and planned and "impaired_start" in sc and "impaired_end" in sc):
        return None
    if None in (apply_.get("st"), planned.get("st"), sc["impaired_start"].get("st"), sc["impaired_end"].get("st")):
        return None
    skip = float(a.get("skip_first_s", 2.0))
    end = float(ev["scenario"].get("duration_s", 0))
    return {"baseline": (skip, sc["impaired_start"]["st"]),
            "impaired": (apply_["st"], sc["impaired_end"]["st"]),
            "recovery": (planned["st"], end)}


def _settled(windows, a):
    """The windows with the recovery start moved by recovery_settle_s (default 2 s)."""
    out = dict(windows)
    out["recovery"] = (windows["recovery"][0] + float(a.get("recovery_settle_s", 2.0)), windows["recovery"][1])
    return out


def _series_total(rec, name):
    vals = [v for k, v in (rec.get("metrics") or {}).items() if k == name or k.startswith(name + "{")]
    return sum(vals) if vals else None


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def _client_times(c, full_only=False):
    """Snapshot receive times of a client in scenario time; None without a clock origin."""
    start = (c["summary"] or {}).get("start_realtime")
    if start is None:
        return None
    return [x["t"] - start for x in c["snapshots"] if x.get("t") is not None and (not full_only or x.get("full"))]


def check_netem_applied(ev, a):
    """The impairment was on the game path, shown three independent ways: (1) every tc command of the apply
    returned 0; (2) the kernel's counters of the two netem qdiscs saw at least min_packets (default 300)
    datagrams and dropped a share within sigmas (default 3) binomial standard deviations of the configured
    loss; (3) the clients' own round-trip time rose by at least rtt_rise_ratio (default 0.5) of the delay added
    to a round trip (delay x directions applied)."""
    view, err = _netem_view(ev)
    if err:
        return err
    apply_, plan = view["apply"], view["plan"] or {}
    art = [str(ev["run_dir"] / "netem.ndjson")]
    if apply_ is None or not apply_.get("ok"):
        failed = [c for c in (apply_ or {}).get("commands", []) if c.get("rc") != 0]
        return A._result(FAIL, {"apply": "failed" if apply_ else "never ran", "failed_commands": failed[:3],
                                "errors": view["errors"][:2]}, {"apply": "ok"},
                         source="netem.ndjson apply record", sampling="once",
                         rationale="without the impairment the scenario measures nothing", artifacts=art)
    profile = plan.get("profile") or apply_.get("profile") or {}
    loss = float(profile.get("loss_pct", 0)) / 100.0
    stats = view["stats"] or {}
    sigmas = float(a.get("sigmas", NETEM_PACKET_SIGMAS))
    min_packets = int(a.get("min_packets", 300))
    per, problems, missing = {}, [], []
    for direction in apply_.get("directions", []):
        q = stats.get(direction)
        if not q:
            missing.append(f"no tc counters for {direction}")
            continue
        n = q["packets"] + q["drops"]
        est = q["drops"] / n if n else None
        per[direction] = {"datagrams": n, "dropped": q["drops"], "loss_pct": None if est is None else round(100 * est, 2)}
        if n < min_packets:
            problems.append(f"{direction}: {n} datagrams passed the qdisc (need {min_packets})")
        elif loss > 0:
            sd = math.sqrt(loss * (1 - loss) / n)
            per[direction]["allowed_loss_pct"] = [round(100 * (loss - sigmas * sd), 2), round(100 * (loss + sigmas * sd), 2)]
            if abs(est - loss) > sigmas * sd:
                problems.append(f"{direction}: measured loss {100 * est:.2f} % is outside {sigmas:g} sigma of {100 * loss:g} %")
    w = _netem_windows(view, ev, a)
    delay = float(profile.get("delay_ms", 0))
    dirs = len(apply_.get("directions", [])) or 1
    rtt = None
    if w and delay > 0:
        (blo, bhi), (ilo, ihi) = w["baseline"], w["impaired"]
        rows, need = [], float(a.get("rtt_rise_ratio", 0.5)) * delay * dirs
        for c in ev["clients"]:
            b = [s.get("rtt_ms") for s in c["samples"] if s.get("st") is not None and blo <= s["st"] <= bhi]
            i = [s.get("rtt_ms") for s in c["samples"] if s.get("st") is not None and ilo <= s["st"] <= ihi]
            if len(b) < 20 or len(i) < 20:
                missing.append(f"client {c['index']}: too few rtt samples")
                continue
            mb, mi = _median(b), _median(i)
            rows.append({"client": c["index"], "baseline_median_ms": mb, "impaired_median_ms": mi, "rise_ms": mi - mb})
            if mi - mb < need:
                problems.append(f"client {c['index']}: rtt rose {mi - mb:.0f} ms, need {need:.0f}")
        rtt = {"clients": rows, "required_rise_ms": need}
    per["rtt"] = rtt
    thr = {"sigmas": sigmas, "min_packets": min_packets, "rtt_rise_ratio": float(a.get("rtt_rise_ratio", 0.5))}
    src = "netem.ndjson apply record and tc counters; client samples.ndjson rtt_ms"
    if problems:
        return A._result(FAIL, per, thr, source=src, sampling="tc counters at the end of the impaired phase; 20 Hz samples",
                         detail={"problems": problems}, artifacts=art)
    if missing or not w:
        return A._inconclusive("; ".join(missing) or "phase windows undefined", source=src)
    return A._result(PASS, per, thr, source=src, sampling="tc counters at the end of the impaired phase; 20 Hz samples",
                     rationale="the retransmit and gap assertions only mean something if the impairment was on the game "
                               "path; the qdisc counters and the clients' round-trip time say so independently of the server",
                     artifacts=art)


def check_netem_cleanup(ev, a):
    """The scratch game server ends the run unshaped: the planned removal was verified (no netem, prio or ingress
    qdisc, no ifb device left) at most max_late_s (default 10) after the impaired phase was due to end, and the
    runner's own final cleanup verified it again."""
    view, err = _netem_view(ev)
    if err:
        return err
    final, planned, plan = view["final"], view["planned_remove"], view["plan"] or {}
    if final is None:
        return A._inconclusive("no final_cleanup record (the run ended before the runner's cleanup)", source="netem.ndjson")
    due = None
    if plan and "impaired_start" in view["scrapes"] and view["scrapes"]["impaired_start"].get("st") is not None:
        due = view["scrapes"]["impaired_start"]["st"] + float(plan.get("impaired_s", 0))
    late = None if not (planned and due is not None and planned.get("st") is not None) else round(planned["st"] - due, 2)
    max_late = float(a.get("max_late_s", 10.0))
    applied = bool((view["apply"] or {}).get("ok"))
    problems = []
    if applied and not (planned and planned.get("verified")):
        problems.append("the planned removal was not verified" + ("" if planned else " (it never ran)"))
    if not final.get("verified"):
        problems.append(f"the final cleanup did not verify: leftover {final.get('leftover')} {final.get('error', '')}".strip())
    if late is not None and late > max_late:
        problems.append(f"removal finished {late} s after the impaired phase was due to end (limit {max_late:g} s)")
    return A._result(FAIL if problems else PASS,
                     {"applied": applied, "planned_removal_verified": bool(planned and planned.get("verified")),
                      "final_cleanup_verified": bool(final.get("verified")), "removal_late_s": late,
                      "final_leftover": final.get("leftover")},
                     {"verified": True, "max_late_s": max_late}, source="netem.ndjson remove and final_cleanup records",
                     sampling="tc qdisc show + ip link show after the removal",
                     rationale="a qdisc left on the scratch game server would impair every later run; removal is checked, "
                               "not assumed", detail={"problems": problems}, artifacts=[str(ev["run_dir"] / "netem.ndjson")])


def _rate(rec_a, rec_b, name):
    """(delta, per second) of a counter between two scrapes; None when either is missing."""
    if not rec_a or not rec_b or rec_a.get("st") is None or rec_b.get("st") is None or rec_b["st"] <= rec_a["st"]:
        return None
    va, vb = _series_total(rec_a, name), _series_total(rec_b, name)
    if va is None or vb is None:
        return None
    return vb - va, (vb - va) / (rec_b["st"] - rec_a["st"])


def check_netem_retransmits(ev, a):
    """KCP segment retransmissions on the server rise during the impairment (proof that it hit the transport) and
    fall back after it: impaired rise >= min_rise (default 30 segments); impaired rate >= rate_ratio (default 5)
    x the baseline rate, the baseline floored at baseline_floor_per_s (default 0.1); recovery rate <=
    recovery_max_ratio (default 0.5) x the impaired rate. gameserver_kcp_segments_retransmitted_total, scraped at
    the phase boundaries (netem.ndjson)."""
    view, err = _netem_view(ev)
    if err:
        return err
    s, name = view["scrapes"], "gameserver_kcp_segments_retransmitted_total"
    base, imp, rec = (_rate(s.get(x), s.get(y), name) for x, y in
                      (("baseline_start", "impaired_start"), ("impaired_start", "impaired_end"),
                       ("recovery_start", "recovery_end")))
    if base is None or imp is None or rec is None:
        return A._inconclusive("a phase scrape or the retransmit series is missing", source="netem.ndjson scrapes")
    min_rise, ratio = float(a.get("min_rise", 30)), float(a.get("rate_ratio", 5.0))
    floor, rec_max = float(a.get("baseline_floor_per_s", 0.1)), float(a.get("recovery_max_ratio", 0.5))
    problems = []
    if imp[0] < min_rise:
        problems.append(f"impaired rise {imp[0]:g} < {min_rise:g}")
    if imp[1] < ratio * max(base[1], floor):
        problems.append(f"impaired rate {imp[1]:.2f}/s < {ratio:g} x baseline {max(base[1], floor):.2f}/s")
    if rec[1] > rec_max * imp[1]:
        problems.append(f"recovery rate {rec[1]:.2f}/s > {rec_max:g} x impaired {imp[1]:.2f}/s")
    return A._result(FAIL if problems else PASS,
                     {k: {"rise": v[0], "per_s": round(v[1], 3)} for k, v in (("baseline", base), ("impaired", imp), ("recovery", rec))},
                     {"min_rise": min_rise, "rate_ratio": ratio, "baseline_floor_per_s": floor, "recovery_max_ratio": rec_max},
                     source="/metrics gameserver_kcp_segments_retransmitted_total at the phase boundaries (netem.ndjson)",
                     sampling="scrape at baseline start, impaired start/end, recovery start/end",
                     rationale="a lost segment is sent again by KCP; retransmissions rising only while the impairment is on "
                               "show it reached the transport and that the transport recovered",
                     detail={"problems": problems}, artifacts=[str(ev["run_dir"] / "netem.ndjson")])


def check_netem_snapshots(ev, a):
    """Per client and phase, snapshots keep arriving: no gap between two snapshots wholly inside the phase longer
    than the phase limit (baseline and recovery max_gap_ms, default 250, the lab-wide cadence limit; impaired
    impaired_max_gap_ms, default 1000); the impaired 99th-percentile gap <= impaired_p99_gap_ms (default 400);
    the receive rate within rate_tolerance (default 0.2) of the world rate in every phase. Recovery is judged
    from recovery_settle_s (default 2) after the removal returned."""
    view, err = _netem_view(ev)
    if err:
        return err
    w = _netem_windows(view, ev, a)
    if not w:
        return A._inconclusive("the impairment was not applied and removed: no phase windows", source="netem.ndjson")
    rows = A._status_in_window(ev)
    hz = float(a.get("expected_hz", (rows[-1].get("sim_world_hz") if rows else None) or 15))
    limits = {"baseline": float(a.get("max_gap_ms", 250)), "impaired": float(a.get("impaired_max_gap_ms", 1000)),
              "recovery": float(a.get("max_gap_ms", 250))}
    p99_lim, tol = float(a.get("impaired_p99_gap_ms", 400)), float(a.get("rate_tolerance", 0.2))
    per, problems, missing = {}, [], []
    for c in ev["clients"]:
        ts = _client_times(c)
        if not ts:
            missing.append(f"client {c['index']}: no snapshots or start_realtime")
            continue
        per[c["index"]] = {}
        for phase, (lo, hi) in _settled(w, a).items():
            inside = [t for t in ts if lo <= t <= hi]
            if len(inside) < 10 or hi <= lo:
                missing.append(f"client {c['index']} {phase}: {len(inside)} snapshots")
                continue
            gaps = [(y - x) * 1000 for x, y in zip(inside, inside[1:])]
            rate, mx, p99 = len(inside) / (hi - lo), max(gaps), util.percentile(gaps, 99)
            per[c["index"]][phase] = {"snapshots": len(inside), "rate_hz": round(rate, 2), "max_gap_ms": round(mx, 1),
                                      "p99_gap_ms": round(p99, 1)}
            if mx > limits[phase]:
                problems.append(f"client {c['index']} {phase}: max gap {mx:.0f} ms > {limits[phase]:g}")
            if phase == "impaired" and p99 > p99_lim:
                problems.append(f"client {c['index']} impaired: p99 gap {p99:.0f} ms > {p99_lim:g}")
            if abs(rate - hz) > hz * tol:
                problems.append(f"client {c['index']} {phase}: rate {rate:.1f} Hz outside {hz:g} Hz +/- {100 * tol:g} %")
    thr = {"max_gap_ms": limits, "impaired_p99_gap_ms": p99_lim, "rate_hz": hz, "rate_tolerance": tol,
           "recovery_settle_s": float(a.get("recovery_settle_s", 2.0))}
    src = "client snapshots.ndjson receive times (NetworkClient.SnapshotReceived), phases from netem.ndjson"
    arts = [str(c["dir"] / "snapshots.ndjson") for c in ev["clients"]]
    if problems:
        return A._result(FAIL, per, thr, source=src, sampling="every snapshot", detail={"problems": problems}, artifacts=arts,
                         rationale="loss shows as longer gaps (KCP is reliable and ordered); see THRESHOLDS.md")
    if missing:
        return A._inconclusive("; ".join(missing), source=src)
    return A._result(PASS, per, thr, source=src, sampling="every snapshot", artifacts=arts,
                     rationale="KCP is reliable and ordered: a lost segment holds back everything behind it until it is "
                               "resent, so loss shows as longer gaps, not missing snapshots; the impaired limits are the "
                               "recovery time of consecutive losses (THRESHOLDS.md)")


def check_netem_prediction(ev, a):
    """Prediction stays bounded under impairment. Per client and phase (recovery from recovery_settle_s): hard
    snaps of the local player (rises of pred.snaps) that no server teleport explains <= max_snaps_per_min
    (default 4.0, the lab's prediction_bound) per minute of the phase; the largest per-sample correction
    (pred.corr) <= max_correction (default 1.5); impaired phase only: keyframes (full snapshots) per minute <=
    max_keyframe_ratio (default 2.0) x the baseline rate."""
    view, err = _netem_view(ev)
    if err:
        return err
    w = _netem_windows(view, ev, a)
    if not w:
        return A._inconclusive("the impairment was not applied and removed: no phase windows", source="netem.ndjson")
    bound = float(a.get("max_snaps_per_min", A.PREDICTION_UNEXPLAINED_BOUND))
    max_corr, kf_ratio = float(a.get("max_correction", 1.5)), float(a.get("max_keyframe_ratio", 2.0))
    max_speed = float(ev["scenario"].get("jump", {}).get("max_speed", 6.0))
    win_ticks = int(a.get("match_window_ticks", 60))
    ids = A._user_ids(ev)
    per, problems, missing = {}, [], []
    for c in ev["clients"]:
        samples = [s for s in c["samples"] if s.get("st") is not None]
        if not any((s.get("pred") or {}).get("snaps") is not None for s in samples):
            missing.append(f"client {c['index']}: no per-sample pred.snaps")
            continue
        kf_times = _client_times(c, full_only=True)
        if kf_times is None:
            missing.append(f"client {c['index']}: no start_realtime")
            continue
        tps = A._server_teleports(ev, ids[c["index"]], max_speed) if ids[c["index"]] else []
        rises, prev = [], None
        for s in samples:
            snaps = (s.get("pred") or {}).get("snaps")
            if snaps is None:
                continue
            tick = s.get("world_tick")
            if prev is not None and int(snaps) > prev[1]:
                explained = tick is not None and any(lo - win_ticks <= tick and prev[0] <= hi + win_ticks for lo, hi in tps)
                rises.append((s["st"], int(snaps) - prev[1], explained))
            prev = (tick if tick is not None else 0, int(snaps))
        per[c["index"]], base_kf = {}, None
        for phase, (lo, hi) in _settled(w, a).items():
            if hi <= lo:
                missing.append(f"client {c['index']} {phase}: empty window")
                continue
            mins = (hi - lo) / 60.0
            snaps = sum(n for st, n, ex in rises if lo <= st <= hi and not ex)
            corr = max([abs(float((s.get("pred") or {}).get("corr") or 0)) for s in samples if lo <= s["st"] <= hi] or [0.0])
            kf_rate = sum(1 for t in kf_times if lo <= t <= hi) / mins
            base_kf = kf_rate if phase == "baseline" else base_kf
            per[c["index"]][phase] = {"unexplained_snaps": snaps, "snaps_per_min": round(snaps / mins, 2),
                                      "max_correction": round(corr, 3), "keyframes_per_min": round(kf_rate, 1)}
            if snaps / mins > bound:
                problems.append(f"client {c['index']} {phase}: {snaps / mins:.1f} hard snaps/min > {bound:g}")
            if corr > max_corr:
                problems.append(f"client {c['index']} {phase}: correction {corr:.2f} > {max_corr:g}")
            if phase == "impaired" and base_kf and kf_rate > kf_ratio * base_kf:
                problems.append(f"client {c['index']} impaired: {kf_rate:.1f} keyframes/min > {kf_ratio:g} x baseline {base_kf:.1f}")
    thr = {"max_snaps_per_min": bound, "max_correction": max_corr, "max_keyframe_ratio": kf_ratio}
    src = ("client samples.ndjson pred.snaps / pred.corr / world_tick, snapshots.ndjson full flag, server /debug/entities "
           "teleports; phases from netem.ndjson")
    arts = [str(c["dir"] / "samples.ndjson") for c in ev["clients"]]
    rationale = ("late and resent inputs must be absorbed by reconciliation smoothing, not by hard snaps of the player's own "
                 "avatar; the player records no separate resync counter, so a hard snap and a resent keyframe are the "
                 "observable resyncs")
    if problems:
        return A._result(FAIL, per, thr, source=src, sampling="20 Hz client samples, 5 Hz server samples",
                         detail={"problems": problems}, artifacts=arts, rationale=rationale)
    if missing:
        return A._inconclusive("; ".join(missing), source=src)
    return A._result(PASS, per, thr, source=src, sampling="20 Hz client samples, 5 Hz server samples", artifacts=arts,
                     rationale=rationale)


def check_netem_convergence(ev, a):
    """Two clients draw each remote entity in the same place again within converge_within_s (default 10) of the
    impairment ending: cross_client_convergence over [removal + converge_within_s, end of scenario] with its usual
    limits (p95 0.35, max 1.0). Baseline and impaired phases are measured the same way and reported in detail,
    not judged: under loss the two views legitimately differ."""
    view, err = _netem_view(ev)
    if err:
        return err
    w = _netem_windows(view, ev, a)
    if not w:
        return A._inconclusive("the impairment was not applied and removed: no phase windows", source="netem.ndjson")
    n = float(a.get("converge_within_s", 10.0))
    base = {k: v for k, v in a.items() if k not in ("id", "check", "title", "converge_within_s", "skip_first_s", "until_s")}
    judged = A.check_cross_client_convergence(ev, {**base, "skip_first_s": w["recovery"][0] + n})
    detail = dict(judged.get("detail") or {})
    for phase in ("baseline", "impaired"):
        lo, hi = w[phase]
        r = A.check_cross_client_convergence(ev, {**base, "skip_first_s": lo, "until_s": hi})
        detail[phase] = r["measured"] if r["status"] in (PASS, FAIL) else {"status": r["status"], **(r.get("detail") or {})}
    judged["detail"] = detail
    judged["threshold"] = {**(judged.get("threshold") or {}), "converge_within_s": n}
    judged["rationale"] = (f"after the impairment ends the interpolation buffers refill (150 ms cover), the KCP backlog drains "
                           f"(a few RTOs) and prediction smoothing completes; the clients must draw the same world within "
                           f"{n:g} s. " + judged.get("rationale", ""))
    return judged


A.CHECKS.update({
    "netem_applied": check_netem_applied,
    "netem_cleanup": check_netem_cleanup,
    "netem_retransmits": check_netem_retransmits,
    "netem_snapshots": check_netem_snapshots,
    "netem_prediction": check_netem_prediction,
    "netem_convergence": check_netem_convergence,
})
