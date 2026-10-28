"""Cut the small, scrubbed failure-summary fixtures out of full testlab runs.

    python3 -B testlab/tests/fixtures/failsum/extract.py <run_dir> <name>

Writes testlab/tests/fixtures/failsum/<name>/ with only what lab/failsum.py reads for the run's
failing checks: the reportable assertions of results.json (long lists capped, run paths made relative),
the scheduled start, each client's start_realtime, the events / snapshots rows the locators point at,
the host guard events around the first guard evidence and the failing kcp counters. Ids that identify a
user or account (UUIDs) are replaced by stable fake ones. The run directory is only read.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
CAP = 20


def fake(m):
    h = hashlib.md5(m.group(0).encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def scrub(text: str, run_dir: Path) -> str:
    for variant in (str(run_dir), str(run_dir).replace("\\", "\\\\"), run_dir.as_posix()):
        text = text.replace(variant, ".")
    return UUID.sub(fake, text)


def rows(path: Path):
    if not path.exists():
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            try:
                yield n, line, json.loads(line)
            except ValueError:
                continue


def cap(v):
    if isinstance(v, list):
        return [cap(x) for x in v[:CAP]]
    if isinstance(v, dict):
        return {k: cap(x) for k, x in v.items()}
    return v


def main(run_dir: Path, name: str) -> None:
    out = HERE / name
    out.mkdir(parents=True, exist_ok=True)

    def put(rel: str, text: str) -> None:
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(scrub(text, run_dir))

    res = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    reportable = [a for a in res["assertions"] if a["status"] in ("FAIL", "INVALID", "INCONCLUSIVE")
                  or (a["status"] == "INFO" and (a.get("detail") or {}).get("would_be") == "FAIL")]
    keep = [{k: cap(a.get(k)) for k in ("id", "check", "title", "status", "measured", "threshold", "detail", "artifacts")}
            for a in reportable]
    put("results.json", json.dumps({"outcome": res["outcome"], "harness_error": res.get("harness_error"),
                                    "assertions": keep}, indent=1))
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    put("run.json", json.dumps({"run_id": run.get("run_id"),
                                "host_guard": {"start_wall_epoch": (run.get("host_guard") or {}).get("start_wall_epoch")},
                                "timeline": [t for t in run.get("timeline") or [] if t.get("event") == "start_scheduled"]}, indent=1))
    sc = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    put("scenario.json", json.dumps({"id": sc.get("id"), "clients": sc.get("clients"), "duration_s": sc.get("duration_s"),
                                     "assertions": []}, indent=1))

    # Per client: start_realtime, the events rows the locators use, the snapshot rows around the first gap / render ticks.
    limit = 0.25
    ticks = [w["render_tick"] for a in keep if a["check"] == "cross_client_convergence" for w in a["detail"].get("worst", [])]
    jump_sts = []
    if any(a["check"] == "render_jumps" for a in keep):
        # The counted jumps come from the check itself (it leaves them in ev["_failsum"]); run only that check.
        sys.path.insert(0, str(HERE.parents[2]))
        from lab import analyze
        full = analyze.load_evidence(run_dir)
        spec = next(a for a in full["scenario"]["assertions"] if a["check"] == "render_jumps")
        analyze.check_render_jumps(full, spec)
        side = full["_failsum"]["render_jumps"]
        side["events"] = sorted((e for e in side["events"] if e.get("class") in side["breaching"]), key=lambda e: e.get("st") or 0)[:CAP]
        put("counted_jumps.json", json.dumps(side, indent=1))
        jump_sts = [e["st"] for e in side["events"] if e.get("st") is not None]
    for i in range(int(sc.get("clients", 0))):
        cd = run_dir / f"client-{i}"
        if not cd.exists():
            continue
        summ = json.loads((cd / "summary.json").read_text(encoding="utf-8")) if (cd / "summary.json").exists() else {}
        put(f"client-{i}/summary.json", json.dumps({"start_realtime": summ.get("start_realtime")}))
        ev_out, got_offset = [], False
        for n, line, r in rows(cd / "events.ndjson"):
            if not got_offset and (r.get("st") or -1) >= 0 and r.get("t") is not None:
                ev_out.append(line)
                got_offset = True
            elif r.get("event") == "render_jump" and any(abs((r.get("st") or -1e9) - s) < 1e-4 for s in jump_sts):
                ev_out.append(line)
        put(f"client-{i}/events.ndjson", "".join(l if l.endswith("\n") else l + "\n" for l in ev_out))
        snaps = list(rows(cd / "snapshots.ndjson"))
        start = summ.get("start_realtime")
        keep_idx = set(range(0, min(5, len(snaps))))
        prev = None
        for k, (n, line, r) in enumerate(snaps):
            if prev is not None and start is not None and r.get("t") is not None and r["t"] >= start and r["t"] - prev > limit:
                keep_idx.update(range(max(0, k - 3), min(len(snaps), k + 3)))
                break
            prev = r.get("t")
        for tk in ticks:
            best = min(range(len(snaps)), key=lambda k: abs((snaps[k][2].get("tick") or 0) - tk), default=None)
            if best is not None:
                keep_idx.update(range(max(0, best - 1), min(len(snaps), best + 2)))
        put(f"client-{i}/snapshots.ndjson", "".join(snaps[k][1] if snaps[k][1].endswith("\n") else snaps[k][1] + "\n"
                                                    for k in sorted(keep_idx)))

    # Host guard: every AnyDesk event from a minute before the scheduled start (the sessions around the failures), and
    # the guard samples over the G3 limit, reduced to their time and AnyDesk CPU.
    hg = next((a for a in res["assertions"] if a["check"] == "host_guard"), None)
    if hg and (run_dir / "host" / "guard.ndjson").exists():
        start = (run.get("host_guard") or {}).get("start_wall_epoch") or 0
        events = [line for _, line, r in rows(run_dir / "host" / "anydesk-events.ndjson")
                  if r.get("epoch") is not None and r["epoch"] >= start - 60]
        put("host/anydesk-events.ndjson", "".join(l.rstrip("\r\n") + "\n" for l in events))
        limit = next((f.get("threshold_pct") for f in (hg.get("detail") or {}).get("fired", []) if f.get("id") == "G3"), None) or 0.5
        slim = [json.dumps({"ts": r.get("ts"), "epoch": r.get("epoch"), "ad_cpu": r.get("ad_cpu")})
                for _, _, r in rows(run_dir / "host" / "guard.ndjson") if float(r.get("ad_cpu") or 0) >= limit]
        slim = slim[:300] or [json.dumps({"ts": None, "epoch": start, "ad_cpu": 0})]
        put("host/guard.ndjson", "".join(l + "\n" for l in slim))

    # kcp: only the failing counter lines of the end scrape.
    if any(a["check"] == "kcp_health" for a in keep):
        lines = [l for l in (run_dir / "server" / "metrics-end.txt").read_text(encoding="utf-8").splitlines()
                 if l.startswith("gameserver_kcp_")]
        put("server/metrics-end.txt", "\n".join(lines) + "\n")
    print(f"written: {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), sys.argv[2])
