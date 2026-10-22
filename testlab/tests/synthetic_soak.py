"""A synthetic soak run directory for memory and equivalence tests of the analysis (no stack, no
Unity): N client samples at 20 Hz with E remote mobs each, matching server /debug/entities rows,
entity add/remove events, frames and status. Deterministic.

    python3 -B testlab/tests/synthetic_soak.py <dir> <samples> <entities>   # write one, print sizes
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ASSERTIONS = [
    {"id": "render_jumps", "check": "render_jumps", "max_local": 0, "max_remote_per_client_min": 2.0},
    {"id": "entity_lifecycle", "check": "entity_lifecycle"},
    {"id": "cross_client_convergence", "check": "cross_client_convergence"},
    {"id": "snapshot_order", "check": "snapshot_order"},
    {"id": "entities", "check": "entity_stability"},
    {"id": "enemy_render_speed", "check": "enemy_render_speed", "speed": 2.5},
    {"id": "tick_adoption", "check": "tick_adoption"},
    {"id": "remote_mob_divergence", "check": "position_divergence", "types": ["mob"], "p95": 0.35, "max": 1.0},
]


def write(root: Path, samples: int, ents: int, clients: int = 3) -> Path:
    run = Path(root) / "20260101T000000Z-SYN-memo"
    duration = samples / 20.0
    sc = {"schema": "rpg.testlab.scenario.v1", "id": "SYN", "version": 1, "title": "synthetic soak", "clients": clients,
          "map": "map_01", "seed": 1, "duration_s": duration, "start_delay_s": 3, "sample_hz": 20,
          "server_sample_hz": 5, "fresh_server": True, "screenshots_s": [], "anomaly_screenshots": 0, "overlay": False,
          "jump": {"max_speed": 6.0, "factor": 3.0, "slack": 0.25}, "client_defaults": {"steps": [], "actions": []},
          "per_client": [], "bots": None, "disruptions": [], "assertions": ASSERTIONS, "join_timeout_s": 120,
          "_path": "syn.json"}
    run.mkdir(parents=True, exist_ok=True)
    (run / "scenario.json").write_text(json.dumps(sc), encoding="utf-8")
    (run / "run.json").write_text(json.dumps({"run_id": run.name}), encoding="utf-8")

    def pos(eid: int, st: float):
        # mob eid walks a circle of radius 5 around its own centre at 0.5 rad/s
        a = 0.5 * st + eid
        return 10 * (eid % 7) + 5 * math.cos(a), 10 * (eid // 7) + 5 * math.sin(a)

    def alive(eid: int, st: float) -> bool:
        # every mob is away (despawned) for 3 s out of every 40 s, phase-shifted per id
        return ((st + eid * 1.7) % 40.0) >= 3.0

    server = run / "server"
    server.mkdir(exist_ok=True)
    with open(server / "entities.ndjson", "w", encoding="utf-8", newline="\n") as fh:
        for k in range(int(duration * 5) + 1):
            st = k * 0.2
            rows = [[f"enemy-{e}", "mob", round(pos(e, st)[0], 4), round(pos(e, st)[1], 4), 16, 16, 0, 2.5]
                    for e in range(ents) if alive(e, st)]
            fh.write(json.dumps({"mono": 1000 + st, "st": st, "tick": int(st * 60), "ents": rows}) + "\n")
    with open(server / "status.ndjson", "w", encoding="utf-8", newline="\n") as fh:
        for k in range(int(duration) + 1):
            fh.write(json.dumps({"_st": float(k), "tick_rate": 60, "sim_world_hz": 15, "sim_critical_hz": 60}) + "\n")
    for i in range(clients):
        d = run / f"client-{i}"
        d.mkdir(exist_ok=True)
        start = 100.0 + 0.37 * i
        (d / "summary.json").write_text(json.dumps({"user_id": f"u{i}", "outcome": "completed", "start_realtime": start,
                                                    "scenario_seconds": duration,
                                                    "prediction": {"present": True, "snaps": 0, "tick_hz": 60}}),
                                        encoding="utf-8")
        (d / "status.json").write_text(json.dumps({"user_id": f"u{i}", "phase": "done"}), encoding="utf-8")
        events = [{"t": start - 1, "st": -1, "event": "in_world", "user_id": f"u{i}"}]
        present = {}
        with open(d / "samples.ndjson", "w", encoding="utf-8", newline="\n") as fh, \
                open(d / "frames.csv", "w", encoding="utf-8", newline="\n") as ff, \
                open(d / "snapshots.ndjson", "w", encoding="utf-8", newline="\n") as fs:
            ff.write("frame,t,dt_ms,scenario_t\n")
            for k in range(samples):
                st = k / 20.0
                t = start + st
                frame = 1000 + 3 * k
                tick = 60 * st
                rows = []
                for e in range(ents):
                    eid = f"enemy-{e}"
                    is_alive = alive(e, st - 0.1)  # the client draws 100 ms behind
                    if is_alive and not present.get(eid):
                        x, y = pos(e, st - 0.1)
                        events.append({"t": t, "st": st, "event": "entity_added", "id": eid, "type": "mob",
                                       "tick": int(tick), "x": x, "y": y, "rx": x, "ry": y, "frame": frame})
                        present[eid] = True
                    elif not is_alive and present.get(eid):
                        events.append({"t": t - 0.02, "st": st - 0.02, "event": "entity_removed", "id": eid,
                                       "type": "mob", "tick": int(tick), "rendered": True, "reason": "removed"})
                        present[eid] = False
                    if is_alive:
                        x, y = pos(e, st - 0.1)
                        rows.append([eid, "mob", 0, round(x, 4), round(y, 4), round(x, 4), round(y, 4)])
                fh.write(json.dumps({"t": t, "st": st, "frame": frame, "world_tick": int(tick) + 6,
                                     "render_tick": tick - 6.0, "render_clock": "binder",
                                     "pred": {"snaps": 0, "tick_hz": 60}, "ents": rows, "n": len(rows)}) + "\n")
                for f in range(3):
                    ff.write(f"{frame + f},{t + f / 60:.6f},16.7,{st + f / 60:.6f}\n")
                if k % 4 == 0 or k % 4 == 2:
                    fs.write(json.dumps({"t": t, "tick": int(tick) + 6 + (k % 4), "full": False, "n": len(rows)}) + "\n")
        with open(d / "events.ndjson", "w", encoding="utf-8", newline="\n") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")
    return run


if __name__ == "__main__":
    r = write(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
    total = sum(p.stat().st_size for p in r.rglob("*") if p.is_file())
    print(r, f"{total / 1e6:.1f} MB")
