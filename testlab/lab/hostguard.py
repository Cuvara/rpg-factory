"""Host guard: records what else the host is doing during a soak and marks a contaminated run INVALID.

Why: a freeze in a rendered player is only evidence about the game if nothing else on the host caused
it. Remote-desktop sessions (AnyDesk), builds and other agents' work do. Evidence and design:
reports/remediation/F19-SOAK-VALIDITY.md (sections 3-5). Residents of AnyDesk (the always-running
`AnyDesk.exe`, `--local-service`, `--local-control`) are allowed and never stopped; the session is the
extra `AnyDesk.exe --backend` process and the session events in AnyDesk's own log.

Everything here is passive and read-only, with no elevation: the AnyDesk logs are only read, the
sampler (`hostguard.ps1`) only reads process and counter data, and nothing is started, stopped or
changed on the host. The parsing and the rules are pure functions on text and rows, testable without
Windows; only `anydesk_processes`, `HostGuard` and `preflight` touch the machine.

Rules (policy, unvalidated; limits in testlab/docs/THRESHOLDS.md), evaluated inside the measurement
window [start_scheduled - 30 s, scenario end + finish_grace_s]:
  G1 AnyDesk session start, event or `--backend` process, or one still active at window start
  G2 an AnyDesk process that was not in the baseline set
  G3 AnyDesk CPU >= 0.5 % of the host for 2 consecutive samples
  G4 a build tool or MsMpEng group above its CPU limit for >= 3 consecutive samples
  G5 the guard was blind (more than 3 consecutive intervals without a sample)
A fired rule makes the `host_guard` check INVALID; it can never turn a FAIL or INCONCLUSIVE into PASS.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

from . import util

SCHEMA = "rpg.testlab.hostguard.v1"
PS1 = Path(__file__).with_name("hostguard.ps1")

# --- policy, unvalidated (calibrated on one 16 min baseline, F19 section 3.6) -------------------------
INTERVAL_S = 5.0                 # in-run sampling cadence
WINDOW_PRE_S = 30.0              # window starts this long before start_scheduled
ANYDESK_IDLE_MAX_PCT = 0.5       # G3 / P2: 4x the observed idle maximum (0.13 %), half the lightest session (~1 %)
G3_CONSECUTIVE = 2
G4_BUILD_PCT = 5.0               # any build-tool group, % of the whole host
G4_AV_PCT = 5.0                  # MsMpEng
G4_CONSECUTIVE = 3
G5_MISSED_INTERVALS = 3
HOLD_SLACK_S = 5.0          # extra time hold_until() waits for the sample that closes the window
PRE_QUIET_S = 120.0              # P1: no session event or connection entry this long before the start
PRE_SAMPLE_S = 120.0             # preflight sample length (P2, P4, P5)
P4_FOREIGN_PCT = 2.0             # sustained foreign load over the preflight sample
P5_REFUSE_PCT = 50.0
P5_SHARED_PCT = 30.0
P6_WSL_UPTIME_S = 600.0
SESSION_TYPES = ("accept", "auth", "backend_pid", "session_started", "capture_start",
                 "session_closed", "net_closed", "capture_stopped")
RULES = {
    "G1": "AnyDesk session started in the window, or still active at its start",
    "G2": "AnyDesk process not in the baseline set",
    "G3": f"AnyDesk CPU >= {ANYDESK_IDLE_MAX_PCT} % of the host for {G3_CONSECUTIVE} consecutive samples",
    "G4": f"build tools > {G4_BUILD_PCT} % or MsMpEng > {G4_AV_PCT} % of the host for {G4_CONSECUTIVE} consecutive samples",
    "G5": f"guard blind: more than {G5_MISSED_INTERVALS} consecutive intervals without a sample",
}

_AD_IDENTITY_PREFIX_BYTES = 256


def _ad_file_identity(path: Path) -> tuple | None:
    """Return a stable-enough file identity, or None when continuity cannot be proven."""
    try:
        st = path.stat()
        ino = getattr(st, "st_ino", 0)
        if not ino:
            return None
        with open(path, "rb") as fh:
            prefix = fh.read(_AD_IDENTITY_PREFIX_BYTES)
        # Windows exposes ctime as creation time; on POSIX it changes on writes, so inode is
        # the identity there. The prefix catches replacement on filesystems without useful ids.
        created = getattr(st, "st_ctime_ns", None) if os.name == "nt" else None
        return (getattr(st, "st_dev", None), ino, created, hashlib.sha256(prefix).digest())
    except (OSError, PermissionError):
        return None


# ----------------------------------------------------------------------------- AnyDesk: processes and logs

def classify_cmdline(cmdline: str | None) -> str:
    """resident | backend | other for one `AnyDesk.exe` command line. The backend is the session."""
    cl = cmdline or ""
    if "--backend" in cl:
        return "backend"
    if "--local-service" in cl or "--local-control" in cl:
        return "resident"
    if re.fullmatch(r'\s*"?[^"]*AnyDesk\.exe"?\s*', cl, re.I):
        return "resident"      # the tray/main process runs without arguments
    return "other"


def anydesk_processes() -> list[dict]:
    """AnyDesk.exe processes now: pid, ppid, cmdline, role. One filtered Win32_Process query, read-only."""
    if not util.IS_WINDOWS:
        return []
    cmd = ["powershell", "-NoProfile", "-Command",
           "Get-CimInstance -ClassName Win32_Process -Filter \"Name='AnyDesk.exe'\" | "
           "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30).stdout.strip()
        rows = json.loads(out) if out else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if isinstance(rows, dict):
        rows = [rows]
    return [{"pid": r.get("ProcessId"), "ppid": r.get("ParentProcessId"), "cmdline": r.get("CommandLine"),
             "role": classify_cmdline(r.get("CommandLine"))} for r in rows]


class AnyDeskPaths:
    """Where AnyDesk keeps its logs on this host. The portable exe logs under %AppData%\\AnyDesk; an
    installed service logs under %ProgramData%\\AnyDesk (ad_svc.trace). Neither is required."""

    def __init__(self, ad_trace: Path | None, connection_trace: Path | None):
        self.ad_trace = ad_trace
        self.connection_trace = connection_trace

    @classmethod
    def discover(cls, env: dict | None = None) -> "AnyDeskPaths":
        env = os.environ if env is None else env
        trace = conn = None
        appdata, progdata = env.get("APPDATA"), env.get("PROGRAMDATA")
        for base, names in ((appdata, ("ad.trace",)), (progdata, ("ad_svc.trace", "ad.trace"))):
            for name in names:
                p = Path(base) / "AnyDesk" / name if base else None
                if trace is None and p is not None and p.is_file():
                    trace = p
        for base in (appdata, progdata):
            p = Path(base) / "AnyDesk" / "connection_trace.txt" if base else None
            if conn is None and p is not None and p.is_file():
                conn = p
        return cls(trace, conn)

    def as_dict(self) -> dict:
        return {"ad_trace": str(self.ad_trace) if self.ad_trace else None,
                "connection_trace": str(self.connection_trace) if self.connection_trace else None}


_LINE = re.compile(r"^\s*(?P<level>\w+)\s+(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+(?P<proc>\w+)\s+(?P<pid>\d+)\s+"
                   r"(?P<tid>\d+)\s+(?:(?P<fiber>\d+)\s+)?(?P<module>[\w.]+)\s+-\s+(?P<text>.*?)\s*$")


def _ts_epoch(ts: str) -> float:
    return dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=dt.timezone.utc).timestamp()


def iso_utc(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _classify_text(module: str, text: str) -> str | None:
    if text.startswith("Accept request from"):
        return "accept"
    if text.startswith("Authenticated with") or re.match(r"\d+: Authenticated with", text):
        return "auth"
    if text.startswith("Backend PID:"):
        return "backend_pid"
    if text.startswith("Session started"):
        return "session_started"
    if text.startswith("Starting capture"):
        return "capture_start"
    if text.startswith("Session closed"):
        return "session_closed"
    if text.startswith("Net socket closed"):
        return "net_closed"
    if text.startswith("Stopped") and "capture" in module:
        return "capture_stopped"
    return None


def parse_ad_trace(data: bytes | str, since_offset: int = 0) -> tuple[list[dict], int]:
    """Session events in `data` (the file content) from byte offset `since_offset`, and the offset to
    resume from. Tolerant of CRLF, of a last line still being written (it is left for the next call),
    and of truncation or rotation: a file shorter than the offset restarts at 0 and the result starts
    with a `log_rotated` event. Peer ids and addresses are never copied into an event."""
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    events: list[dict] = []
    start = since_offset
    if len(raw) < since_offset:
        start = 0
        events.append({"type": "log_rotated", "source": "ad_trace"})
    end = raw.rfind(b"\n") + 1            # only complete lines; 0 when there is none
    if end <= start:
        return events, (start if end == 0 else max(start, end))
    for line in raw[start:end].decode("utf-8", errors="replace").splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        kind = _classify_text(m["module"], m["text"])
        if kind is None:
            continue
        ev = {"type": kind, "ts": iso_utc(_ts_epoch(m["ts"])), "epoch": _ts_epoch(m["ts"]), "proc": m["proc"],
              "pid": int(m["pid"]), "source": "ad_trace"}
        if m["fiber"]:
            ev["fiber"] = int(m["fiber"])
        if kind == "backend_pid":
            ev["backend_pid"] = int(re.search(r"\d+", m["text"])[0])
        events.append(ev)
    return events, end


def sessions_from_events(events: list[dict]) -> list[dict]:
    """Sessions from log events: {start, end, backend_pid, end_reason}. `start` is None for a session
    that was already running when the log begins. An Accept binds to the next session fiber that
    shows up; later events of that fiber (and of the backend pid) belong to the same session."""
    rows = sorted((e for e in events if e.get("epoch") is not None and e["type"] in SESSION_TYPES),
                  key=lambda e: e["epoch"])
    sessions: list[dict] = []
    pending: list[dict] = []
    by_fiber: dict[int, dict] = {}
    by_backend: dict[int, dict] = {}
    for e in rows:
        t = e["type"]
        if t == "accept":
            s = {"start": e["epoch"], "end": None, "backend_pid": None, "end_reason": None}
            sessions.append(s)
            pending.append(s)
            continue
        if e.get("proc") == "lsvc" and e.get("fiber") is not None and t in ("auth", "backend_pid", "session_closed", "net_closed"):
            s = by_fiber.get(e["fiber"])
            if s is None:
                s = pending.pop(0) if pending else {"start": None, "end": None, "backend_pid": None, "end_reason": None}
                if s not in sessions:
                    sessions.append(s)
                by_fiber[e["fiber"]] = s
            if t == "backend_pid":
                s["backend_pid"] = e["backend_pid"]
                by_backend[e["backend_pid"]] = s
            elif t in ("session_closed", "net_closed") and s["end"] is None:
                s["end"], s["end_reason"] = e["epoch"], t
            continue
        if e.get("proc") == "back" and t == "capture_stopped":
            s = by_backend.get(e["pid"])
            if s is not None and s["end"] is None:
                s["end"], s["end_reason"] = e["epoch"], t
    return sessions


def parse_connection_trace(data: bytes | str) -> list[dict]:
    """Entries of connection_trace.txt (UTF-16LE, UTC, minute resolution): direction, minute, auth.
    The peer id is dropped."""
    text = data.decode("utf-16-le", "replace") if isinstance(data, bytes) else data
    out = []
    for line in text.splitlines():
        m = re.search(r"(Incoming|Outgoing)\s+(\d{4}-\d\d-\d\d),\s+(\d\d:\d\d)\s+(\S+)", re.sub(r"\s+", " ", line))
        if m:
            epoch = dt.datetime.strptime(f"{m[2]} {m[3]}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp()
            out.append({"type": "connection_entry", "ts": iso_utc(epoch), "epoch": epoch, "direction": m[1],
                        "auth": m[4], "source": "connection_trace"})
    return out


# ----------------------------------------------------------------------------- rules

def _in(epoch: float | None, window: tuple[float, float]) -> bool:
    return epoch is not None and window[0] <= epoch <= window[1]


def _consecutive(flags: list[bool], n: int) -> int | None:
    """Index where a run of `n` True values ends, or None."""
    run = 0
    for i, f in enumerate(flags):
        run = run + 1 if f else 0
        if run >= n:
            return i
    return None


def evaluate(samples: list[dict], events: list[dict], window: tuple[float, float] | None, *,
             baseline_pids=(), interval_s: float = INTERVAL_S, preflight_pids=()) -> dict:
    """Guards G1-G5 against the window. `samples` are the guard's rows (epoch, ad[], ad_cpu, groups),
    `events` the AnyDesk log events and connection entries. Returns {"fired": [...], "stats": {...}}.
    Pure: no I/O. `baseline_pids` / `preflight_pids` are AnyDesk pids that existed before the run."""
    fired: list[dict] = []
    if window is None:
        return {"fired": fired, "window": None, "stats": {"samples": len(samples), "note": "no measurement window"}}
    rows = sorted((s for s in samples if s.get("epoch") is not None), key=lambda s: s["epoch"])
    inside = [s for s in rows if _in(s["epoch"], window)]
    pre = [s for s in rows if s["epoch"] < window[0]]

    # G1: session events, a session active at the start, a backend process, a connection entry.
    g1: list[str] = []
    for s in sessions_from_events(events):
        if s["start"] is not None and s["start"] < window[0] and (s["end"] is None or s["end"] >= window[0]):
            g1.append(f"session active at window start (began {iso_utc(s['start'])}, ended {iso_utc(s['end']) if s['end'] else 'not seen'})")
    for e in events:
        if e["type"] in SESSION_TYPES and _in(e.get("epoch"), window):
            g1.append(f"{e['type']} at {e['ts']}")
        elif e["type"] == "connection_entry" and e["epoch"] <= window[1] and e["epoch"] + 60.0 > window[0]:
            g1.append(f"connection entry {e['direction']} {e['ts']} (minute resolution)")
    for s in inside:
        for p in s.get("ad") or []:
            if p.get("role") == "backend":
                g1.append(f"--backend pid {p.get('pid')} in sample {s.get('ts')}")
                break
    if g1:
        fired.append({"id": "G1", "rule": RULES["G1"], "count": len(g1), "evidence": g1[:12]})

    # G2: a pid that was not there before the run.
    base = set(baseline_pids) | set(preflight_pids)
    if not base:
        base = {p["pid"] for s in pre for p in (s.get("ad") or [])}
    if not base and inside:
        base = {p["pid"] for p in (inside[0].get("ad") or []) if p.get("role") != "backend"}
    g2 = []
    for s in inside:
        for p in s.get("ad") or []:
            if p.get("pid") not in base and p["pid"] not in {x[0] for x in g2}:
                g2.append((p["pid"], f"pid {p['pid']} ({p.get('role')}) first seen {s.get('ts')}"))
    if g2:
        fired.append({"id": "G2", "rule": RULES["G2"], "count": len(g2), "evidence": [x[1] for x in g2[:12]]})

    # G3: AnyDesk CPU burst.
    flags = [float(s.get("ad_cpu") or 0.0) >= ANYDESK_IDLE_MAX_PCT for s in inside]
    at = _consecutive(flags, G3_CONSECUTIVE)
    if at is not None:
        fired.append({"id": "G3", "rule": RULES["G3"], "count": sum(flags),
                      "evidence": [f"{s.get('ts')} AnyDesk {s.get('ad_cpu')} % of host" for s, f in zip(inside, flags) if f][:12]})

    # G4: foreign build or antivirus load.
    for grp, limit, label in (("build", G4_BUILD_PCT, "build tools"), ("av", G4_AV_PCT, "MsMpEng")):
        flags = [float((s.get("groups") or {}).get(grp) or 0.0) > limit for s in inside]
        if _consecutive(flags, G4_CONSECUTIVE) is not None:
            fired.append({"id": "G4", "rule": RULES["G4"], "group": grp, "count": sum(flags),
                          "evidence": [f"{s.get('ts')} {label} {(s.get('groups') or {}).get(grp)} % of host"
                                       for s, f in zip(inside, flags) if f][:12]})

    # G5: blind. Gaps between samples, and the edges of the window.
    limit = interval_s * (G5_MISSED_INTERVALS + 1) + 1.0     # 3 missed intervals are tolerated, plus 1 s of jitter
    gaps = []
    points = [window[0]] + [s["epoch"] for s in inside] + [window[1]]
    for a, b in zip(points, points[1:]):
        if b - a > limit:
            gaps.append(f"no sample between {iso_utc(a)} and {iso_utc(b)} ({b - a:.0f} s)")
    if gaps:
        fired.append({"id": "G5", "rule": RULES["G5"], "count": len(gaps), "evidence": gaps[:12]})
    blind_logs = [e for e in events if e.get("type") == "log_blind" and _in(e.get("epoch"), window)]
    if blind_logs:
        fired.append({"id": "G5", "rule": RULES["G5"], "count": len(blind_logs),
                      "evidence": [f"AnyDesk log identity unavailable at {e['ts']}" for e in blind_logs[:12]]})

    ad_cpu = [float(s.get("ad_cpu") or 0.0) for s in inside]
    own = [float(s["own_cpu"]) for s in rows if s.get("own_cpu") is not None and not s.get("first")]
    cpu = [float(s["cpu"]) for s in inside if s.get("cpu") is not None]
    stats = {"samples": len(rows), "samples_in_window": len(inside),
             "anydesk_cpu_pct": {"mean": round(sum(ad_cpu) / len(ad_cpu), 3) if ad_cpu else None, "max": max(ad_cpu) if ad_cpu else None},
             "host_cpu_pct": {"mean": round(sum(cpu) / len(cpu), 2) if cpu else None, "max": max(cpu) if cpu else None},
             "guard_own_cpu_pct": {"mean": round(sum(own) / len(own), 4) if own else None, "max": max(own) if own else None},
             "new_processes_per_interval_max": max([s.get("newproc") or 0 for s in inside[1:]] or [0])}
    return {"fired": fired, "window": [iso_utc(window[0]), iso_utc(window[1])], "stats": stats}


def nearest_event(events: list[dict], epoch: float, within_s: float = 10.0) -> dict | None:
    """The guard event closest in time to `epoch` within +-`within_s`, for attributing a freeze."""
    best = None
    for e in events:
        if e.get("epoch") is None or e["type"] not in SESSION_TYPES + ("connection_entry",):
            continue
        d = abs(e["epoch"] - epoch)
        if d <= within_s and (best is None or d < best[0]):
            best = (d, e)
    return None if best is None else {"type": best[1]["type"], "ts": best[1]["ts"], "offset_s": round(best[1]["epoch"] - epoch, 2)}


# ----------------------------------------------------------------------------- the running guard

class HostGuard:
    """Runs hostguard.ps1 beside a run and tails the AnyDesk logs. Writes `<out>/guard.ndjson` (one row
    per interval, plus the harness `mono` clock), `<out>/anydesk-events.ndjson` and `guard-summary.json`
    (the guard's own CPU). `stop()` is safe to call twice and never raises."""

    def __init__(self, out_dir: Path, *, interval_s: float = INTERVAL_S, paths: AnyDeskPaths | None = None):
        self.out = Path(out_dir)
        self.interval_s = interval_s
        self.paths = paths or AnyDeskPaths.discover()
        self.proc: subprocess.Popen | None = None
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.samples = 0
        self.events = 0
        self.errors: list[str] = []
        self.py_cpu_s = 0.0
        self.started_epoch: float | None = None
        self.last_epoch: float | None = None     # epoch of the newest sample the reader appended
        self.baseline_pids: list[int] = []

    def start(self) -> None:
        if not util.IS_WINDOWS:
            raise RuntimeError("host guard needs Windows (hostguard.ps1)")
        self.out.mkdir(parents=True, exist_ok=True)
        self.baseline_pids = [p["pid"] for p in anydesk_processes() if p["pid"]]
        self.started_epoch = time.time()
        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
             "-IntervalS", str(self.interval_s), "-ParentPid", str(os.getpid())],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self._threads = [threading.Thread(target=self._read_samples, name="hostguard-samples", daemon=True),
                         threading.Thread(target=self._tail_logs, name="hostguard-logs", daemon=True)]
        for t in self._threads:
            t.start()

    def _append(self, name: str, row: dict) -> None:
        with self._lock, open(self.out / name, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    def _read_samples(self) -> None:
        first = True
        cpu0 = time.thread_time()
        try:
            for line in self.proc.stdout:
                if self._stop.is_set():
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                row["mono"] = util.mono()
                if first:
                    row["first"] = True       # CPU deltas and the new-process count of a first row are not rates
                    first = False
                self.samples += 1
                self._append("guard.ndjson", row)
                if isinstance(row.get("epoch"), (int, float)):
                    self.last_epoch = float(row["epoch"])
        except Exception as exc:              # the guard must never take the run down
            self.errors.append(f"samples: {type(exc).__name__}: {exc}")
        finally:
            self.py_cpu_s += time.thread_time() - cpu0

    def _tail_logs(self) -> None:
        cpu0 = time.thread_time()
        ad_state = {"off": None}
        conn_seen: Counter = Counter()
        conn_stamp = None
        try:
            while not self._stop.is_set():
                try:
                    self._poll_ad(ad_state)
                    conn_stamp = self._poll_conn(conn_seen, conn_stamp)
                except Exception as exc:
                    self.errors.append(f"logs: {type(exc).__name__}: {exc}")
                self._stop.wait(self.interval_s)
        finally:
            self.py_cpu_s += time.thread_time() - cpu0

    def _emit(self, events: list[dict]) -> None:
        for e in events:
            e["mono"] = util.mono()
            self._append("anydesk-events.ndjson", e)
            self.events += 1

    def _poll_ad(self, holder: dict) -> None:
        p = self.paths.ad_trace
        identity = _ad_file_identity(p) if p is not None else None
        if identity is None:
            now = time.time()
            self._emit([{"type": "log_blind", "source": "ad_trace", "ts": iso_utc(now), "epoch": now}])
            holder["identity"] = None
            holder["off"] = None
            return
        try:
            size = p.stat().st_size
            off = holder["off"]
            if holder.get("identity") is not None and identity != holder["identity"]:
                off = 0
                self._emit([{"type": "log_rotated", "source": "ad_trace"}])
            if off is None:                   # first look: prime with the last MiB so an open session is known
                off = max(0, size - (1 << 20))
            if size < off:                    # truncated: start again and say so
                off = 0
                self._emit([{"type": "log_rotated", "source": "ad_trace"}])
            with open(p, "rb") as fh:
                fh.seek(off)
                chunk = fh.read(size - off)
            if off > 0 and holder["off"] is None:  # primed mid-file: drop the partial first line
                nl = chunk.find(b"\n")
                chunk, off = (chunk[nl + 1:], off + nl + 1) if nl >= 0 else (b"", off)
            events, used = parse_ad_trace(chunk, 0)
            holder["off"] = off + used
            holder["identity"] = identity
            self._emit(events)
        except OSError:
            now = time.time()
            holder["identity"] = None
            holder["off"] = None
            self._emit([{"type": "log_blind", "source": "ad_trace", "ts": iso_utc(now), "epoch": now}])

    def _poll_conn(self, seen: Counter, stamp) -> tuple | None:
        p = self.paths.connection_trace
        if p is None or not p.is_file():
            return stamp
        st = p.stat()
        cur = (st.st_mtime_ns, st.st_size)
        if cur == stamp:
            return stamp
        horizon = (self.started_epoch or time.time()) - 600.0
        entries = [e for e in parse_connection_trace(p.read_bytes()) if e["epoch"] >= horizon]
        now: Counter = Counter((e["ts"], e["direction"], e["auth"]) for e in entries)
        new = []
        for e in entries:
            key = (e["ts"], e["direction"], e["auth"])
            if now[key] > seen[key]:
                seen[key] += 1
                new.append(e)
        self._emit(new)
        return cur

    def hold_until(self, epoch: float, *, slack_s: float | None = None) -> bool:
        """Keep sampling until a sample at or after `epoch` (the end of the measurement window) is on disk.
        Returns False when it gave up: the sampler died, or no such sample arrived within one interval plus
        `slack_s` after `epoch`. A missing sample then stays visible to G5; this never fabricates one."""
        limit = epoch + self.interval_s + (HOLD_SLACK_S if slack_s is None else slack_s)
        while True:
            if self.last_epoch is not None and self.last_epoch >= epoch:
                return True
            now = time.time()
            if now >= limit or self.proc is None or self.proc.poll() is not None:
                return False
            time.sleep(min(0.5, max(0.05, limit - now)))

    def stop(self) -> dict:
        """Stop the sampler, join the readers and write guard-summary.json. Returns the summary."""
        self._stop.set()
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        for t in self._threads:
            t.join(timeout=10)
        if self.proc is not None and self.proc.stdout is not None:
            try:
                self.proc.stdout.close()
            except OSError:
                pass
        summary = self.summary()
        try:
            util.write_json(self.out / "guard-summary.json", summary)
        except OSError as exc:
            summary["write_error"] = str(exc)
        return summary

    def summary(self) -> dict:
        rows = util.read_ndjson(self.out / "guard.ndjson") if (self.out / "guard.ndjson").exists() else []
        own = [float(r["own_cpu"]) for r in rows if r.get("own_cpu") is not None and not r.get("first")]
        elapsed = (time.time() - self.started_epoch) if self.started_epoch else None
        ncpu = os.cpu_count() or 1
        py_pct = round(self.py_cpu_s / elapsed * 100.0 / ncpu, 4) if elapsed else None
        return {"schema": SCHEMA, "interval_s": self.interval_s, "samples": self.samples, "events": self.events,
                "errors": self.errors[:10], "paths": self.paths.as_dict(), "baseline_pids": self.baseline_pids,
                "sampler_cpu_pct_of_host": {"mean": round(sum(own) / len(own), 4) if own else None, "max": max(own) if own else None},
                "python_threads_cpu_pct_of_host": py_pct,
                "note": "the sampler's CPU is its own process; the WMI provider that answers the AnyDesk command-line "
                        "query runs in a system process and is not included"}


# ----------------------------------------------------------------------------- preflight

def _row(pid: str, ok: bool, detail: str, measured=None, note: str | None = None) -> dict:
    return {"id": pid, "status": "PASS" if ok else "FAIL", "detail": detail, "measured": measured, **({"note": note} if note else {})}


def working_agents(ps_json: dict | None, allow=()) -> list[str]:
    """Names of Orca worktrees with an agent in the `working` state, except those in `allow`
    (display names or paths: the soak runner and the Lead). Input is `orca worktree ps --json`."""
    out = []
    for w in ((ps_json or {}).get("result") or {}).get("worktrees") or []:
        names = {str(w.get("displayName")), str(w.get("path")), str(w.get("worktreeId"))}
        if any((a.get("state") == "working") for a in (w.get("agents") or [])) and not (names & set(allow)):
            out.append(str(w.get("displayName") or w.get("path")))
    return out


def _orca_ps() -> dict | None:
    try:
        r = subprocess.run(["orca", "worktree", "ps", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return json.loads(r.stdout or "")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None


def _wsl_uptime(distro: str = "Ubuntu") -> float | None:
    """Uptime of the WSL VM in seconds, 0.0 when the distro is not running, None when unreadable. The
    distro is listed first (`wsl -l --running`) so that a stopped one is never started by the probe."""
    def text(raw: bytes) -> str:
        return raw.decode("utf-16-le", "ignore") if b"\x00" in raw else raw.decode("utf-8", "replace")
    try:
        running = text(subprocess.run(["wsl.exe", "-l", "--running", "-q"], capture_output=True, timeout=60).stdout)
        if distro.lower() not in running.lower():
            return 0.0
        r = subprocess.run(["wsl.exe", "-d", distro, "--exec", "cat", "/proc/uptime"], capture_output=True, timeout=60)
        return float(text(r.stdout).split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def sample_host(seconds: float) -> list[dict]:
    """Run the sampler for `seconds` and return its rows (used by the preflight)."""
    if not util.IS_WINDOWS:
        return []
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
                        "-IntervalS", str(INTERVAL_S), "-DurationS", str(seconds)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=seconds + 120)
    rows = []
    for line in p.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def preflight(*, window_min: float = 90.0, announced: str | None = None, sample_s: float = PRE_SAMPLE_S,
              allow_agents=(), paths: AnyDeskPaths | None = None, now: float | None = None,
              sampler=sample_host, processes=anydesk_processes, orca_ps=_orca_ps, wsl_uptime=_wsl_uptime,
              include_p7: bool = True) -> dict:
    """P1-P6 over a `sample_s` sample (and P7 when `include_p7`). Every input is injectable. The result
    is {"ok": bool, "rows": [...], "failed": [ids], "anydesk_pids": [...]}; the runner refuses to start
    when `ok` is false."""
    paths = paths or AnyDeskPaths.discover()
    now = time.time() if now is None else now
    samples = sampler(sample_s)
    procs = processes()
    rows: list[dict] = []

    # P1: no session now or starting. Residents are allowed.
    backends = [p for p in procs if p["role"] == "backend"]
    events: list[dict] = []
    if paths.ad_trace and paths.ad_trace.is_file():
        data = paths.ad_trace.read_bytes()
        events, _ = parse_ad_trace(data[-(1 << 20):].split(b"\n", 1)[-1] if len(data) > (1 << 20) else data, 0)
    if paths.connection_trace and paths.connection_trace.is_file():
        events += parse_connection_trace(paths.connection_trace.read_bytes())
    recent = [e for e in events if e["type"] in SESSION_TYPES + ("connection_entry",)
              and e["epoch"] + (60.0 if e["type"] == "connection_entry" else 0.0) >= now - PRE_QUIET_S]
    open_sessions = [s for s in sessions_from_events(events) if s["start"] is not None and s["end"] is None]
    p1_bad = [f"--backend pid {p['pid']}" for p in backends] + [f"{e['type']} at {e['ts']}" for e in recent[:5]] \
        + [f"session open since {iso_utc(s['start'])}" for s in open_sessions]
    rows.append(_row("P1", not p1_bad, "no --backend process and no session event in the last "
                     f"{PRE_QUIET_S:.0f} s (residents allowed)" if not p1_bad else "; ".join(p1_bad),
                     {"residents": sum(1 for p in procs if p["role"] == "resident"), "backends": len(backends)}))

    body = [s for s in samples if not s.get("first")] or samples
    ad = [float(s.get("ad_cpu") or 0.0) for s in body]
    ad_mean = sum(ad) / len(ad) if ad else None
    rows.append(_row("P2", ad_mean is not None and ad_mean < ANYDESK_IDLE_MAX_PCT,
                     f"AnyDesk mean CPU < {ANYDESK_IDLE_MAX_PCT} % of host over {len(body)} samples" if ad_mean is not None
                     else "no sample (sampler unavailable)", {"mean_pct": None if ad_mean is None else round(ad_mean, 3),
                                                              "max_pct": max(ad) if ad else None}))

    # P3: no other agent working.
    ps = orca_ps()
    if ps is None:
        rows.append(_row("P3", False, "orca worktree ps unavailable: cannot show that no other agent is working"))
    else:
        busy = working_agents(ps, allow_agents)
        rows.append(_row("P3", not busy, "no other agent in the working state" if not busy else "working: " + ", ".join(busy),
                         {"working": busy}))

    # P4: no sustained heavy foreign process.
    b = [float((s.get("groups") or {}).get("build") or 0.0) for s in body]
    a = [float((s.get("groups") or {}).get("av") or 0.0) for s in body]
    b_mean, a_mean = (sum(b) / len(b) if b else None), (sum(a) / len(a) if a else None)
    p4_ok = b_mean is not None and b_mean <= P4_FOREIGN_PCT and a_mean is not None and a_mean < G4_AV_PCT
    rows.append(_row("P4", p4_ok, f"build tools mean <= {P4_FOREIGN_PCT} %, MsMpEng mean < {G4_AV_PCT} % of host" if p4_ok else
                     "foreign load too high or no sample", {"build_mean_pct": None if b_mean is None else round(b_mean, 3),
                                                            "av_mean_pct": None if a_mean is None else round(a_mean, 3)}))

    # P5: host not saturated; recorded always.
    cpu = [float(s["cpu"]) for s in body if s.get("cpu") is not None]
    cpu_mean = sum(cpu) / len(cpu) if cpu else None
    shared = cpu_mean is not None and cpu_mean > P5_SHARED_PCT
    rows.append(_row("P5", cpu_mean is not None and cpu_mean <= P5_REFUSE_PCT,
                     f"host CPU mean <= {P5_REFUSE_PCT} %" if cpu_mean is not None else "no CPU sample",
                     {"mean_pct": None if cpu_mean is None else round(cpu_mean, 2), "shared_host": shared},
                     note=f"shared-host: mean above {P5_SHARED_PCT} %" if shared else None))

    up = wsl_uptime()
    rows.append(_row("P6", up is not None and up >= P6_WSL_UPTIME_S,
                     "WSL distro not running (the probe never starts it)" if up == 0.0 else
                     f"WSL uptime >= {P6_WSL_UPTIME_S:.0f} s" if up is not None else "WSL uptime unreadable", {"uptime_s": up}))
    if include_p7:
        rows.append(_row("P7", bool(announced), f"window announced: {announced}" if announced else
                         "the user has not named the start time and length (--window-announced \"18:30Z 90min\")",
                         {"window_min": window_min}))
    failed = [r["id"] for r in rows if r["status"] != "PASS"]
    return {"schema": SCHEMA, "ok": not failed, "failed": failed, "rows": rows, "window_min": window_min,
            "sample_s": sample_s, "samples": len(samples), "anydesk_pids": [p["pid"] for p in procs if p["pid"]],
            "paths": paths.as_dict(), "checked_epoch": now}


def enforce(result: dict) -> None:
    """Raise the harness error that refuses to start a run on a failed preflight."""
    if not result.get("ok"):
        raise RuntimeError("host preflight failed: " + ", ".join(result.get("failed") or ["unknown"]))
