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
  G3 AnyDesk CPU above min(1.0 %, max(0.5 %, 2 x the preflight resident max + 0.3 %)) of the host for 2 consecutive samples
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
import statistics
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

from . import util

SCHEMA = "rpg.testlab.hostguard.v1"
PS1 = Path(__file__).with_name("hostguard.ps1")
PROCS_PS1 = Path(__file__).with_name("hostprocs.ps1")

# --- policy, unvalidated (calibrated on one 16 min baseline, F19 section 3.6) -------------------------
INTERVAL_S = 5.0                 # in-run sampling cadence
WINDOW_PRE_S = 30.0              # window starts this long before start_scheduled
ANYDESK_IDLE_MAX_PCT = 0.5       # G3 floor / P2: 4x the F19 idle maximum (0.13 %), half the lightest session (~1 %)
G3_BASELINE_FACTOR = 2.0         # F29: G3 fires above baseline_max x 2 + 0.3 %, never below the 0.5 % floor
G3_BASELINE_MARGIN_PCT = 0.3     # (F19 idle 0.03 % mean; F28 idle front process 0.18 % mean, 0.33 % max, bursts to 1.98 %)
G3_THRESHOLD_CAP_PCT = 1.0       # F29B: G3 never fires above this, so a session burst (>= 1.36 % seen in F28) always can;
#                                  a preflight resident max at or above the cap fails P2 (the run does not start)
G3_CONSECUTIVE = 2
PROC_SAMPLE_INTERVAL_S = 1.0     # F29: optional per-process sampler, S09-class runs only (evidence, never a guard)
PROC_SAMPLE_TOP_N = 10
G4_BUILD_PCT = 5.0               # any build-tool group, % of the whole host
G4_AV_PCT = 5.0                  # MsMpEng
G4_CONSECUTIVE = 3
G5_MISSED_INTERVALS = 3
G6_RATE_DEVIATION_PCT = 5.0
G6_SUSTAINED_S = 2.0
G6_ACHIEVED_TICK_MIN_RATIO = 0.98
G6_METER_WINDOW_S = 2.0          # AchievedRateMeter publishes the rate of the last completed 2 s window (it lags a stall)
G6_SAMPLE_S = 1.0                # one /status sample period
G6_STALL_DEVIATION_PCT = 35.0    # a host clock step is about +-20 %; an interval this far off is a stall, not a correction
G6_MIN_WINDOWS = 3               # consecutive same-sign sliding windows that must all exceed the limit
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
    "G3": (f"AnyDesk CPU above min({G3_THRESHOLD_CAP_PCT} %, max({ANYDESK_IDLE_MAX_PCT} %, preflight resident max x "
           f"{G3_BASELINE_FACTOR:g} + {G3_BASELINE_MARGIN_PCT} %)) of the host for {G3_CONSECUTIVE} consecutive samples "
           "(policy, unvalidated: F19 0.03 % idle, F28 0.18 % mean / 1.98 % max idle front process)"),
    "G4": f"build tools > {G4_BUILD_PCT} % or MsMpEng > {G4_AV_PCT} % of the host for {G4_CONSECUTIVE} consecutive samples",
    "G5": f"guard blind: more than {G5_MISSED_INTERVALS} consecutive intervals without a sample",
    "G6": (f"server clock-rate step: current_tick per harness second, over sliding windows of at least "
          f"{G6_SUSTAINED_S:.0f} s, differs by more than {G6_RATE_DEVIATION_PCT:.1f}% from the run median "
          f"in {G6_MIN_WINDOWS} consecutive windows of the same sign, "
          f"while achieved_tick_hz stays within {100 * (1 - G6_ACHIEVED_TICK_MIN_RATIO):.0f}% of target"),
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


def _event_key(e: dict) -> tuple:
    return (e["type"], e.get("epoch"), e.get("proc"), e.get("pid"), e.get("fiber"), e.get("backend_pid"))


def _distinct_events(rows: list[dict]) -> list[dict]:
    """Drop repeats of the same log line. A rotation (new file identity) makes the tailer read the file
    again from 0, so one Accept arrives twice; each copy would queue a phantom session that a later,
    unrelated close then ends, which shifted every pairing after it."""
    seen: set = set()
    out = []
    for e in rows:
        k = _event_key(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def sessions_from_events(events: list[dict]) -> list[dict]:
    """Sessions from log events: {start, end, backend_pid, end_reason}. `start` is None for a session
    that was already running when the log begins. An Accept binds to the next session fiber that
    shows up; later events of that fiber (and of the backend pid) belong to the same session."""
    rows = sorted((e for e in events if e.get("epoch") is not None and e["type"] in SESSION_TYPES),
                  key=lambda e: e["epoch"])
    rows = _distinct_events(rows)
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


def g3_threshold(baseline_max_pct: float | None) -> float:
    """AnyDesk CPU (% of host) above which G3 counts a sample. Relative to the resident baseline measured
    by the preflight (P2), with the original 0.5 % as the floor and G3_THRESHOLD_CAP_PCT as the ceiling; no baseline gives the floor."""
    if baseline_max_pct is None:
        return ANYDESK_IDLE_MAX_PCT
    return min(G3_THRESHOLD_CAP_PCT,
               max(ANYDESK_IDLE_MAX_PCT, float(baseline_max_pct) * G3_BASELINE_FACTOR + G3_BASELINE_MARGIN_PCT))


def g3_baseline(preflight: dict | None) -> dict | None:
    """The resident AnyDesk baseline a preflight recorded: {"mean_pct", "max_pct", ...}. Reads the
    `anydesk_baseline` block, or the P2 row's measured values of a preflight written before F29."""
    if not preflight:
        return None
    b = preflight.get("anydesk_baseline")
    if isinstance(b, dict) and b.get("max_pct") is not None:
        return b
    for r in preflight.get("rows") or []:
        m = r.get("measured") or {}
        if r.get("id") == "P2" and m.get("max_pct") is not None:
            return {"mean_pct": m.get("mean_pct"), "max_pct": m.get("max_pct"), "source": "P2 row"}
    return None


def evaluate(samples: list[dict], events: list[dict], window: tuple[float, float] | None, *,
             baseline_pids=(), interval_s: float = INTERVAL_S, preflight_pids=(),
             ad_baseline: dict | None = None) -> dict:
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
    backends_after = [p for r in rows if r["epoch"] >= window[0] for p in (r.get("ad") or []) if p.get("role") == "backend"]
    for s in sessions_from_events(events):
        if s["start"] is not None and s["start"] < window[0] and (s["end"] is None or s["end"] >= window[0]):
            if s["end"] is None:      # P1 still refuses a start within PRE_QUIET_S (120 s) of any session event, so a session must be absent before start.
                alive = any(p.get("pid") == s["backend_pid"] for p in backends_after) if s["backend_pid"] is not None                     else bool(backends_after)
                if not alive:
                    continue
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
    g3_limit = g3_threshold((ad_baseline or {}).get("max_pct"))
    flags = [float(s.get("ad_cpu") or 0.0) >= g3_limit for s in inside]
    at = _consecutive(flags, G3_CONSECUTIVE)
    if at is not None:
        fired.append({"id": "G3", "rule": RULES["G3"], "count": sum(flags), "threshold_pct": round(g3_limit, 3),
                      "evidence": [f"{s.get('ts')} AnyDesk {s.get('ad_cpu')} % of host (limit {g3_limit:.3f} %)"
                                   for s, f in zip(inside, flags) if f][:12]})

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
             "g3": {"threshold_pct": round(g3_limit, 3), "baseline": ad_baseline, "label": "policy, unvalidated"},
             "host_cpu_pct": {"mean": round(sum(cpu) / len(cpu), 2) if cpu else None, "max": max(cpu) if cpu else None},
             "guard_own_cpu_pct": {"mean": round(sum(own) / len(own), 4) if own else None, "max": max(own) if own else None},
             "new_processes_per_interval_max": max([s.get("newproc") or 0 for s in inside[1:]] or [0])}
    return {"fired": fired, "window": [iso_utc(window[0]), iso_utc(window[1])], "stats": stats}


def evaluate_clock_rate(status_rows: list[dict]) -> dict:
    """Detect G6 from 1 Hz server status samples without treating a server stall as a host clock step.

    current_tick gives a high-resolution server-clock measure; _mono is the harness monotonic clock.
    Stalls are excluded and the exclusion is dilated, because achieved_tick_hz lags a real stall:
      - an interval with achieved_tick_hz below 98% of sim_critical_hz, with no tick progress, or with a
        deviation above G6_STALL_DEVIATION_PCT from the median is a stall;
      - every interval within G6_METER_WINDOW_S + G6_SAMPLE_S (3 s) before or after a stall is dropped too.
    The rate is the net tick delta over the harness monotonic delta of a sliding window of at least
    G6_SUSTAINED_S (whole intervals), so one late poll cannot move it by more than its lateness / 2 s. An
    episode needs G6_MIN_WINDOWS consecutive windows of the same sign over the limit, and the net rate over
    their union must exceed the limit too. Server stalls remain graded by the server_tick/render checks.
    """
    raw = []
    rows = [r for r in status_rows if isinstance(r.get("_mono"), (int, float))]
    rows.sort(key=lambda r: r["_mono"])
    for before, after in zip(rows, rows[1:]):
        start, end = float(before["_mono"]), float(after["_mono"])
        elapsed = end - start
        if elapsed <= 0.0 or elapsed > 2.0:
            continue
        target = min(float(before.get("sim_critical_hz") or before.get("tick_rate") or 0.0),
                     float(after.get("sim_critical_hz") or after.get("tick_rate") or 0.0))
        achieved = min(float(before.get("achieved_tick_hz") or 0.0),
                       float(after.get("achieved_tick_hz") or 0.0))
        if target <= 0.0:
            continue
        try:
            ticks = float(after["current_tick"]) - float(before["current_tick"])
        except (KeyError, TypeError, ValueError):
            continue
        raw.append({"start": start, "end": end, "scenario_st": after.get("_st"), "ticks": ticks,
                    "rate": ticks / elapsed, "achieved": achieved, "target": target,
                    "stall": ticks <= 0.0 or achieved < target * G6_ACHIEVED_TICK_MIN_RATIO})

    pool = [x["rate"] for x in raw if not x["stall"]]
    median = statistics.median(pool) if pool else None
    if median and median > 0:
        for x in raw:
            if abs(x["rate"] / median - 1.0) * 100.0 > G6_STALL_DEVIATION_PCT:
                x["stall"] = True
    pad = G6_METER_WINDOW_S + G6_SAMPLE_S
    stalls = [(x["start"] - pad, x["end"] + pad) for x in raw if x["stall"]]
    intervals = [x for x in raw if not any(x["end"] > lo and x["start"] < hi for lo, hi in stalls)]
    rates = [x["rate"] for x in intervals]
    median = statistics.median(rates) if rates else None

    fired = []
    max_deviation = 0.0
    if median and median > 0:
        segments, current = [], []
        for x in intervals:
            if current and x["start"] - current[-1]["end"] > 0.25:
                segments.append(current)
                current = []
            current.append(x)
        if current:
            segments.append(current)
        episodes = []
        for seg in segments:
            flagged = []                                    # (first index, last index, sign) per sliding window
            for i in range(len(seg)):
                j = i
                while j < len(seg) and seg[j]["end"] - seg[i]["start"] < G6_SUSTAINED_S - 1e-6:
                    j += 1
                if j == len(seg):
                    break
                span = seg[j]["end"] - seg[i]["start"]
                deviation = (sum(x["ticks"] for x in seg[i:j + 1]) / span / median - 1.0) * 100.0
                max_deviation = max(max_deviation, abs(deviation))
                if abs(deviation) > G6_RATE_DEVIATION_PCT:
                    flagged.append((i, j, 1 if deviation > 0 else -1))
            group = []
            for w in flagged + [None]:
                if w is not None and group and w[2] == group[-1][2] and w[0] == group[-1][0] + 1:
                    group.append(w)
                    continue
                if len(group) >= G6_MIN_WINDOWS:
                    run = seg[group[0][0]:group[-1][1] + 1]
                    mean_rate = sum(x["ticks"] for x in run) / (run[-1]["end"] - run[0]["start"])
                    if abs(mean_rate / median - 1.0) * 100.0 > G6_RATE_DEVIATION_PCT:
                        episodes.append((run, mean_rate))
                group = [w] if w is not None else []
        episode_evidence = []
        for run, mean_rate in episodes:
            deviation = abs(mean_rate / median - 1.0) * 100.0
            start_st, end_st = run[0].get("scenario_st"), run[-1].get("scenario_st")
            scenario_window = (f"scenario st {float(start_st):.1f}..{float(end_st):.1f} s; "
                               if isinstance(start_st, (int, float)) and isinstance(end_st, (int, float)) else "")
            episode_evidence.append(f"{scenario_window}harness mono {run[0]['start']:.3f}..{run[-1]['end']:.3f}: "
                                    f"{mean_rate:.2f} ticks/s vs {median:.2f} median "
                                    f"({deviation:.1f}% deviation, "
                                    f"achieved_tick_hz >= {G6_ACHIEVED_TICK_MIN_RATIO:.2f} x target)")
        if episode_evidence:
            fired.append({"id": "G6", "rule": RULES["G6"], "count": sum(len(run) for run, _ in episodes),
                          "episodes": len(episodes), "evidence": episode_evidence[:12]})
    stats = {"source": "server/status.ndjson current_tick / harness _mono",
             "valid_intervals": len(intervals), "excluded_intervals": len(raw) - len(intervals),
             "median_ticks_per_harness_s": round(median, 3) if median else None,
             "max_window_deviation_pct": round(max_deviation, 2) if median else None,
             "rate_deviation_limit_pct": G6_RATE_DEVIATION_PCT, "sustained_limit_s": G6_SUSTAINED_S,
             "achieved_tick_min_ratio": G6_ACHIEVED_TICK_MIN_RATIO,
             "stall_exclusion_pad_s": pad, "stall_deviation_pct": G6_STALL_DEVIATION_PCT}
    return {"fired": fired, "stats": stats}


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
            rotated = False
            if holder.get("identity") is not None and identity != holder["identity"]:
                off, rotated = 0, True
                self._emit([{"type": "log_rotated", "source": "ad_trace"}])
            if off is None:                   # first look: prime with the last MiB so an open session is known
                off = max(0, size - (1 << 20))
            if size < off:                    # truncated: start again and say so
                off, rotated = 0, True
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
            if rotated:                       # the re-read starts at 0: drop what this run already wrote
                seen = holder.setdefault("keys", set())
                events = [e for e in events if _event_key(e) not in seen]
            holder.setdefault("keys", set()).update(_event_key(e) for e in events)
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


class ProcSampler:
    """Optional 1 s sampler of the top PROC_SAMPLE_TOP_N processes by CPU (hostprocs.ps1), for S09-class
    runs only. Writes `<out>/procs.ndjson`; `stop()` writes `procs-summary.json` with its own measured
    cost. EVIDENCE ONLY (analyze `host_procs`, INFO): no guard and no verdict reads it. It exists so a
    40-140 ms client stall that the 5 s guard cannot attribute (F28) can be matched to a process. It
    never raises into the run."""

    def __init__(self, out_dir: Path, *, interval_s: float = PROC_SAMPLE_INTERVAL_S, top_n: int = PROC_SAMPLE_TOP_N):
        self.out = Path(out_dir)
        self.interval_s = interval_s
        self.top_n = top_n
        self.proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self.samples = 0
        self.errors: list[str] = []
        self.py_cpu_s = 0.0
        self.started_epoch: float | None = None

    def start(self) -> None:
        if not util.IS_WINDOWS:
            raise RuntimeError("process sampler needs Windows (hostprocs.ps1)")
        self.out.mkdir(parents=True, exist_ok=True)
        self.started_epoch = time.time()
        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROCS_PS1),
             "-IntervalS", str(self.interval_s), "-TopN", str(self.top_n), "-ParentPid", str(os.getpid())],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self._thread = threading.Thread(target=self._read, name="hostprocs", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        cpu0 = time.thread_time()
        try:
            with open(self.out / "procs.ndjson", "a", encoding="utf-8", newline="\n") as fh:
                for line in self.proc.stdout:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    row["mono"] = util.mono()
                    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                    fh.flush()
                    self.samples += 1
        except Exception as exc:
            self.errors.append(f"procs: {type(exc).__name__}: {exc}")
        finally:
            self.py_cpu_s += time.thread_time() - cpu0

    def stop(self) -> dict:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self.proc is not None and self.proc.stdout is not None:
            try:
                self.proc.stdout.close()
            except OSError:
                pass
        summary = self.summary()
        try:
            util.write_json(self.out / "procs-summary.json", summary)
        except OSError as exc:
            summary["write_error"] = str(exc)
        return summary

    def summary(self) -> dict:
        path = self.out / "procs.ndjson"
        rows = util.read_ndjson(path) if path.exists() else []
        own = [float(r["own_cpu"]) for r in rows[2:] if r.get("own_cpu") is not None]
        sweep = [float(r["sweep_ms"]) for r in rows[2:] if r.get("sweep_ms") is not None]
        return {"schema": SCHEMA, "interval_s": self.interval_s, "top_n": self.top_n, "samples": self.samples,
                "errors": self.errors[:10],
                "sampler_cpu_pct_of_host": {"mean": round(sum(own) / len(own), 4) if own else None, "max": max(own) if own else None},
                "sweep_ms": {"mean": round(sum(sweep) / len(sweep), 1) if sweep else None, "max": max(sweep) if sweep else None},
                "note": "evidence only (INFO); cost is the sampler process, not the WMI provider or the Python reader"}


def procs_report(rows: list[dict], *, hot_pct: float = 5.0, top: int = 8) -> dict:
    """Pure summary of procs.ndjson rows for the INFO check: per process name the mean and max of the
    sampled CPU (% of host, only the seconds in which it was in the top N), the seconds above `hot_pct`,
    and the hottest seconds. Names, not pids, so a restarted process stays one line."""
    by: dict[str, dict] = {}
    seconds = []
    for r in rows:
        peak = None
        for p in r.get("top") or []:
            d = by.setdefault(str(p.get("name")), {"n": 0, "sum": 0.0, "max": 0.0, "hot_s": 0})
            c = float(p.get("cpu") or 0.0)
            d["n"] += 1
            d["sum"] += c
            d["max"] = max(d["max"], c)
            if c > hot_pct:
                d["hot_s"] += 1
            if peak is None or c > peak[1]:
                peak = (str(p.get("name")), c)
        if peak is not None and r.get("epoch") is not None:
            seconds.append({"epoch": r["epoch"], "name": peak[0], "cpu_pct": peak[1]})
    procs = sorted(({"name": k, "samples_in_top": v["n"], "mean_pct": round(v["sum"] / v["n"], 3), "max_pct": round(v["max"], 2),
                     f"seconds_above_{hot_pct:g}_pct": v["hot_s"]} for k, v in by.items()), key=lambda x: -x["max_pct"])
    return {"samples": len(rows), "processes": procs[:top], "hottest_seconds": sorted(seconds, key=lambda x: -x["cpu_pct"])[:top]}


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
    ad_base = None if not ad else {"mean_pct": round(ad_mean, 3), "max_pct": max(ad), "samples": len(ad),
                                   "sample_s": sample_s, "g3_threshold_pct": round(g3_threshold(max(ad)), 3),
                                   "label": "policy, unvalidated"}
    ad_max = max(ad) if ad else None
    p2_ok = ad_mean is not None and ad_mean < ANYDESK_IDLE_MAX_PCT and ad_max < G3_THRESHOLD_CAP_PCT
    rows.append(_row("P2", p2_ok,
                     f"AnyDesk mean CPU < {ANYDESK_IDLE_MAX_PCT} % and max < {G3_THRESHOLD_CAP_PCT} % (the G3 cap) of host "
                     f"over {len(body)} samples" if ad_mean is not None else "no sample (sampler unavailable)", {"mean_pct": None if ad_mean is None else round(ad_mean, 3),
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
            "anydesk_baseline": ad_base,
            "paths": paths.as_dict(), "checked_epoch": now}


def enforce(result: dict) -> None:
    """Raise the harness error that refuses to start a run on a failed preflight."""
    if not result.get("ok"):
        raise RuntimeError("host preflight failed: " + ", ".join(result.get("failed") or ["unknown"]))
