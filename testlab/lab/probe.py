"""Server-side evidence, sampled while a scenario runs: authoritative entity positions
(/debug/entities), /status, /metrics (start and end), and container CPU/memory.

Each sample carries the orchestrator's monotonic time and the scenario clock (`st`), so client and
server traces line up on one clock without trusting either process's wall clock.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from . import stack, util
from .config import LabConfig


class ServerProbe:
    def __init__(self, cfg: LabConfig, out_dir: Path, entity_hz: float, status_hz: float = 1.0,
                 stats_every_s: float = 5.0):
        self.cfg = cfg
        self.out = out_dir
        self.out.mkdir(parents=True, exist_ok=True)
        self.entity_period = 1.0 / max(0.5, entity_hz)
        self.status_period = 1.0 / max(0.2, status_hz)
        self.stats_every = stats_every_s
        self.start_mono: float | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.counts = {"entities": 0, "entities_failed": 0, "status": 0, "status_failed": 0, "stats": 0}

    def scenario_time(self, mono: float) -> float | None:
        return None if self.start_mono is None else mono - self.start_mono

    def start(self) -> None:
        # `docker stats` through wsl.exe takes 1-2 s, so it runs on its own thread and never
        # delays the entity samples the movement checks interpolate between.
        for target, name in ((self._run_http, "server-probe"), (self._run_stats, "server-stats")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=10)

    def scrape_metrics(self, name: str) -> None:
        status, body = util.http_get(self.cfg.metrics_url, timeout=5)
        (self.out / f"metrics-{name}.txt").write_bytes(body if status == 200 else b"")

    def _run_http(self) -> None:
        with open(self.out / "entities.ndjson", "w", encoding="utf-8", newline="\n") as ent_fh, \
                open(self.out / "status.ndjson", "w", encoding="utf-8", newline="\n") as st_fh:
            next_ent = next_status = util.mono()
            while not self._stop.is_set():
                now = util.mono()
                if now >= next_ent:
                    next_ent = now + self.entity_period
                    doc = util.http_json(self.cfg.debug_entities_url, timeout=2)
                    t = util.mono()
                    if doc is None:
                        self.counts["entities_failed"] += 1
                    else:
                        self.counts["entities"] += 1
                        ents = [[e["id"], e["type"], round(e["x"], 4), round(e["y"], 4), e["hp"], e.get("max_hp"),
                                 1 if e.get("dead") else 0, e.get("speed")] for e in doc.get("entities", [])]
                        ent_fh.write(json.dumps({"mono": t, "st": self.scenario_time(t), "tick": doc.get("tick"),
                                                 "server_s": doc.get("monotonic_s"), "ents": ents},
                                                separators=(",", ":")) + "\n")
                        ent_fh.flush()
                if now >= next_status:
                    next_status = now + self.status_period
                    doc = util.http_json(self.cfg.status_url, timeout=2)
                    t = util.mono()
                    if doc is None:
                        self.counts["status_failed"] += 1
                    else:
                        self.counts["status"] += 1
                        doc["_mono"] = t
                        doc["_st"] = self.scenario_time(t)
                        st_fh.write(json.dumps(doc, separators=(",", ":")) + "\n")
                        st_fh.flush()
                self._stop.wait(0.01)

    def _run_stats(self) -> None:
        with open(self.out / "container.ndjson", "w", encoding="utf-8", newline="\n") as fh:
            while not self._stop.is_set():
                s = stack.server_stats(self.cfg)
                if s is not None:
                    self.counts["stats"] += 1
                    t = util.mono()
                    s.update({"mono": t, "st": self.scenario_time(t)})
                    fh.write(json.dumps(s) + "\n")
                    fh.flush()
                self._stop.wait(self.stats_every)
