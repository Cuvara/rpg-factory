"""S18 packet impairment: tc netem on the scratch game server's UDP path, inside the container's own
network namespace, with guaranteed removal.

Why this mechanism (least invasive of the three considered):

- nsenter + tc on the scratch container's netns (CHOSEN). Nothing in the stack changes: no compose
  override, no extra capability on the game server container, no image change, no new process on the
  data path. The qdiscs live in the container's namespace, so they are invisible to the host and to every
  other container, and they disappear with the container if the harness ever dies. Needs passwordless
  `sudo nsenter` and `tc` in WSL (preflight checks it and fails the run before any player starts).
- A scratch-only compose override with NET_ADMIN was rejected: it recreates the stack differently from
  every other scenario (a different container for one scenario), and gives the game server process a
  capability it does not have in production.
- A UDP impairment proxy was rejected: the address clients dial is the one the server registers in Redis
  (`servers:id:*` addr) and the gateway hands out in the join token, so a proxy means changing what the
  stack advertises, and then the scenario no longer exercises the registered path. It would also add a
  user-space hop whose own jitter is mixed into the measurement.

What is shaped: UDP with port 9000 (the game port inside the container) and nothing else. /status, /metrics
and the gateway, Redis and Nakama TCP connections of the container are never delayed or dropped.

- server -> client (egress of eth0): `prio` root, band 3 holds the netem, a u32 filter on UDP source port 9000
  sends only the game datagrams to it (snapshots, KCP acks).
- client -> server (ingress of eth0): an `ingress` qdisc whose u32 filter on UDP destination port 9000 redirects
  to a per-container `ifb0` device (created inside the same netns) that carries the same netem (inputs, acks).

The step only RECORDS (`netem.ndjson`): the plan, the apply and remove commands with their output, the tc
packet and drop counters, and a metrics scrape every few seconds. Every verdict is the analyzer's
(`netem_applied`, `netem_cleanup`, `netem_retransmits`, ... in lab/analyze.py).

Cleanup contract: the qdiscs are removed in a `finally`, again by the runner's own `finally`, and a watchdog
process started inside WSL at apply time removes them after the planned duration + slack even if the harness
process is killed. Removal is VERIFIED (no netem/prio/ingress qdisc on the interface, no ifb0 device) and the
verdict is recorded; an unverified removal FAILs the run.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from . import stack, util
from .config import LabConfig

EVIDENCE = "netem.ndjson"
GAME_PORT = 9000          # the UDP port the game server listens on INSIDE the container (compose 9000/udp)
IFB = "ifb0"
SHAPED_KINDS = ("netem", "prio", "ingress")   # qdisc kinds this module creates; none may be left behind
WATCHDOG_SLACK_S = 45.0
SCRAPE_EVERY_S = 5.0

# Series recorded at every scrape (a subset: the evidence is read for rises, not for everything).
SCRAPED = ("gameserver_kcp_segments_retransmitted_total", "gameserver_kcp_datagrams_received_total",
           "gameserver_kcp_sessions_closed_total", "gameserver_kcp_sessions_rejected_total",
           "gameserver_kcp_datagrams_dropped_total", "gameserver_kcp_sessions", "gameserver_players_online")


class NetemError(RuntimeError):
    pass


def netem_clause(p: dict) -> str:
    """The netem arguments for a profile: delay with jitter (uniform, so +/- jitter is literal), loss and
    reorder. `reorder` needs a delay, which every profile has."""
    delay, jitter = float(p.get("delay_ms", 0)), float(p.get("jitter_ms", 0))
    parts = []
    if delay or jitter:
        parts.append(f"delay {delay:g}ms {jitter:g}ms")
    if float(p.get("loss_pct", 0)) > 0:
        parts.append(f"loss {float(p['loss_pct']):g}%")
    if float(p.get("reorder_pct", 0)) > 0:
        if not (delay or jitter):
            raise NetemError("reorder needs a delay in the profile")
        parts.append(f"reorder {float(p['reorder_pct']):g}%")
    if not parts:
        raise NetemError("an empty profile impairs nothing")
    return " ".join(parts)


def in_ns(pid: int, cmd: str) -> str:
    """The ONLY way this module runs tc/ip: inside the network namespace of one process. Refuses a
    process that is not a positive pid, so the host namespace is never reached through a bad lookup."""
    pid = int(pid)
    if pid <= 1:
        raise NetemError(f"refusing to enter the network namespace of pid {pid}")
    return f"sudo -n nsenter -t {pid} -n {cmd}"


def apply_commands(dev: str, profile: dict, directions=("egress", "ingress")) -> list[str]:
    """tc/ip commands (without the nsenter prefix) that impair the game port, in order."""
    clause = netem_clause(profile)
    cmds = []
    if "ingress" in directions:
        cmds += [f"ip link add {IFB} type ifb", f"ip link set {IFB} up"]
    if "egress" in directions:
        cmds += [f"tc qdisc add dev {dev} root handle 1: prio bands 3 priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
                 f"tc qdisc add dev {dev} parent 1:3 handle 30: netem {clause}",
                 f"tc filter add dev {dev} parent 1: protocol ip prio 1 u32 match ip protocol 17 0xff "
                 f"match ip sport {GAME_PORT} 0xffff flowid 1:3"]
    if "ingress" in directions:
        cmds += [f"tc qdisc add dev {dev} handle ffff: ingress",
                 f"tc filter add dev {dev} parent ffff: protocol ip prio 1 u32 match ip protocol 17 0xff "
                 f"match ip dport {GAME_PORT} 0xffff action mirred egress redirect dev {IFB}",
                 f"tc qdisc add dev {IFB} root netem {clause}"]
    return cmds


def remove_commands(dev: str) -> list[str]:
    return [f"tc qdisc del dev {dev} root", f"tc qdisc del dev {dev} ingress", f"ip link del {IFB}"]


# --------------------------------------------------------------------------- pure parsing (unit-tested)

def parse_qdiscs(text: str) -> list[dict]:
    """`tc -s -j qdisc show dev X` -> [{kind, handle, parent, packets, bytes, drops, overlimits}]."""
    try:
        doc = json.loads(text or "[]")
    except ValueError:
        return []
    out = []
    for q in doc if isinstance(doc, list) else []:
        out.append({"kind": q.get("kind"), "handle": q.get("handle"), "parent": q.get("parent"),
                    "packets": int(q.get("packets") or 0), "bytes": int(q.get("bytes") or 0),
                    "drops": int(q.get("drops") or 0), "overlimits": int(q.get("overlimits") or 0)})
    return out


def leftover(qdiscs: list[dict], ifb_present: bool) -> list[str]:
    """What of this module's setup is still there (empty = clean)."""
    left = [f"qdisc {q['kind']} {q.get('handle') or ''}".strip() for q in qdiscs if q.get("kind") in SHAPED_KINDS]
    if ifb_present:
        left.append(f"device {IFB}")
    return left


def parse_default_dev(text: str) -> str | None:
    m = re.search(r"^default\b.*?\bdev\s+(\S+)", text or "", re.M)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- talking to WSL

class Shaper:
    """Runs the commands for the scratch game server container; nothing else is ever addressed."""

    def __init__(self, cfg: LabConfig):
        self.cfg = cfg
        stack.assert_scratch_name(cfg, cfg.gameserver_container)

    def _sh(self, cmd: str, timeout: float = 30):
        res = util.wsl(self.cfg.wsl_distro, cmd, timeout=timeout)
        return res.returncode, (res.stdout + res.stderr).strip()

    def pid(self) -> int | None:
        rc, out = self._sh(f"docker inspect -f '{{{{.State.Running}}}} {{{{.State.Pid}}}}' {self.cfg.gameserver_container}")
        m = re.fullmatch(r"true (\d+)", out.strip()) if rc == 0 else None
        return int(m.group(1)) if m and int(m.group(1)) > 1 else None

    def netns(self, pid: int) -> str:
        rc, out = self._sh(f"sudo -n readlink /proc/{int(pid)}/ns/net")
        return out if rc == 0 else ""

    def host_netns(self) -> str:
        rc, out = self._sh("readlink /proc/1/ns/net")
        return out if rc == 0 else ""

    def dev(self, pid: int) -> str:
        rc, out = self._sh(in_ns(pid, "ip -o route show default"))
        dev = parse_default_dev(out) if rc == 0 else None
        if not dev:
            raise NetemError(f"no default route device in the container namespace: {out[:200]}")
        return dev

    def run(self, pid: int, cmd: str) -> dict:
        rc, out = self._sh(in_ns(pid, cmd))
        return {"cmd": cmd, "rc": rc, "out": out[:400]}

    def qdiscs(self, pid: int, dev: str, stats: bool = True) -> list[dict]:
        rc, out = self._sh(in_ns(pid, f"tc {'-s ' if stats else ''}-j qdisc show dev {dev}"))
        return parse_qdiscs(out) if rc == 0 else []

    def ifb_present(self, pid: int) -> bool:
        rc, _ = self._sh(in_ns(pid, f"ip link show {IFB}"))
        return rc == 0

    # ---- the operations

    def preflight(self) -> dict:
        """Everything the step needs, checked before any player starts. Raises NetemError with the reason."""
        pid = self.pid()
        if pid is None:
            raise NetemError(f"{self.cfg.gameserver_container} is not running: nothing to shape")
        rc, out = self._sh("sudo -n true")
        if rc != 0:
            raise NetemError("passwordless sudo is not available in WSL (needed for nsenter + tc): " + out[:200])
        ns, host = self.netns(pid), self.host_netns()
        if not ns or ns == host:
            raise NetemError(f"the container's network namespace ({ns or 'unreadable'}) is the host's: refusing to shape")
        dev = self.dev(pid)
        left = leftover(self.qdiscs(pid, dev, stats=False), self.ifb_present(pid))
        rec = {"pid": pid, "netns": ns, "host_netns": host, "dev": dev, "leftover_before": left}
        if left:
            self.remove(pid, dev)   # a previous run that died; the namespace is ours (scratch container)
            rec["leftover_cleaned"] = not leftover(self.qdiscs(pid, dev, stats=False), self.ifb_present(pid))
        return rec

    def apply(self, profile: dict, directions=("egress", "ingress"), expect_s: float = 120.0) -> dict:
        pid = self.pid()
        if pid is None:
            raise NetemError("the game server container is not running")
        ns = self.netns(pid)
        if not ns or ns == self.host_netns():
            raise NetemError("refusing to shape: the container namespace is unreadable or the host's")
        dev = self.dev(pid)
        results, ok = [], True
        for cmd in apply_commands(dev, profile, directions):
            r = self.run(pid, cmd)
            results.append(r)
            if r["rc"] != 0:
                ok = False
                break
        rec = {"pid": pid, "netns": ns, "dev": dev, "ok": ok, "commands": results, "profile": profile,
               "directions": list(directions)}
        if ok:
            rec["watchdog"] = self.arm_watchdog(pid, ns, dev, expect_s + WATCHDOG_SLACK_S)
            rec["qdiscs"] = {"egress": self.qdiscs(pid, dev), "ingress": self.qdiscs(pid, IFB)}
        else:
            rec["rolled_back"] = self.remove(pid, dev)
        return rec

    def stats(self, pid: int, dev: str) -> dict:
        """Packet and drop counters of the two netem qdiscs (egress on dev, ingress on ifb0)."""
        def netem_of(qs):
            return next((q for q in qs if q["kind"] == "netem"), None)
        return {"egress": netem_of(self.qdiscs(pid, dev)), "ingress": netem_of(self.qdiscs(pid, IFB))}

    def remove(self, pid: int, dev: str) -> dict:
        """Delete everything this module created and VERIFY it. Safe to call when nothing is there."""
        results = [self.run(pid, c) for c in remove_commands(dev)]
        left = leftover(self.qdiscs(pid, dev, stats=False), self.ifb_present(pid))
        return {"commands": results, "leftover": left, "verified": not left}

    def clean(self) -> dict:
        """Idempotent full cleanup by container name: resolves the pid afresh. A container that is not
        running has no namespace and so no qdisc."""
        pid = self.pid()
        if pid is None:
            return {"container_running": False, "verified": True, "leftover": []}
        dev = self.dev(pid)
        rec = self.remove(pid, dev)
        rec.update({"container_running": True, "pid": pid, "dev": dev})
        self.disarm_watchdog()
        return rec

    # ---- watchdog: removes the shaping after the planned time even if this process is killed

    def arm_watchdog(self, pid: int, ns: str, dev: str, after_s: float) -> dict:
        tag = f"netem-watchdog-{pid}-{int(time.time())}"
        # Acts only if the namespace of that pid is still the one recorded (pid reuse after a container
        # restart must never send tc into another namespace).
        guard = f'[ "$(readlink /proc/{pid}/ns/net)" = "{ns}" ]'
        dels = "; ".join(in_ns(pid, c) + " >/dev/null 2>&1" for c in remove_commands(dev))
        script = f": {tag}; sleep {int(after_s)}; if {guard}; then {dels}; fi"
        rc, out = self._sh(f"nohup setsid bash -c '{script}' >/dev/null 2>&1 & echo $!")
        last = out.split()[-1] if out.split() else ""
        wd = {"tag": tag, "after_s": int(after_s), "pid": int(last) if rc == 0 and last.isdigit() else None}
        self._watchdog = wd
        return wd

    def disarm_watchdog(self) -> None:
        wd = getattr(self, "_watchdog", None)
        if wd and wd.get("pid"):
            # only a process whose command line is our script
            self._sh(f"grep -q '{wd['tag']}' /proc/{wd['pid']}/cmdline 2>/dev/null && kill {wd['pid']}; true")
        self._watchdog = None


# --------------------------------------------------------------------------- the harness step

class Evidence:
    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / EVIDENCE
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")


def default_phases(d: dict) -> tuple[float, float, float]:
    return float(d.get("baseline_s", 30.0)), float(d.get("impaired_s", 60.0)), float(d.get("recovery_s", 30.0))


def scrape(cfg: LabConfig) -> dict:
    from .rawprobe import parse_metrics
    code, body = util.http_get(cfg.metrics_url, timeout=4)
    series = parse_metrics(body.decode("utf-8", "replace")) if code == 200 else {}
    sel = {k: v for k, v in series.items() if k.startswith(SCRAPED)}
    return {"ok": code == 200, "metrics": sel}


def _st(probe) -> float | None:
    return probe.scenario_time(util.mono()) if probe is not None else None


def run_step(cfg: LabConfig, sc: dict, d: dict, run_dir: Path, probe, log, stop: threading.Event,
             shaper: Shaper | None = None) -> None:
    """Baseline scrape, wait, apply, wait, remove (verified), wait, final scrape. Always removes."""
    ev = Evidence(run_dir)
    shaper = shaper or Shaper(cfg)
    baseline_s, impaired_s, recovery_s = default_phases(d)
    profile = dict(d.get("profile") or {})
    directions = tuple(d.get("directions") or ("egress", "ingress"))
    pid = dev = None
    applied = removed = False

    def wait_until(st_target: float) -> None:
        nxt = 0.0
        while not stop.is_set():
            st = _st(probe)
            if st is not None and st >= st_target:
                return
            if util.mono() >= nxt:
                nxt = util.mono() + SCRAPE_EVERY_S
                ev.write({"record": "scrape", "label": "tick", "st": _st(probe), **scrape(cfg)})
            stop.wait(0.25)

    ev.write({"record": "plan", "profile": profile, "clause": netem_clause(profile), "directions": list(directions),
              "baseline_s": baseline_s, "impaired_s": impaired_s, "recovery_s": recovery_s,
              "game_port": GAME_PORT, "mechanism": "nsenter+tc in the scratch game server netns"})
    try:
        ev.write({"record": "scrape", "label": "baseline_start", "st": _st(probe), **scrape(cfg)})
        wait_until(baseline_s)
        if stop.is_set():
            return
        ev.write({"record": "scrape", "label": "impaired_start", "st": _st(probe), **scrape(cfg)})
        rec = shaper.apply(profile, directions, expect_s=impaired_s + recovery_s + 10.0)
        pid, dev = rec.get("pid"), rec.get("dev")
        applied = bool(rec.get("ok"))
        ev.write({"record": "apply", "st": _st(probe), **rec})
        log(f"netem: {'applied' if applied else 'APPLY FAILED'}: {netem_clause(profile)} on {dev} (pid {pid})")
        if not applied:
            return
        wait_until(baseline_s + impaired_s)
        ev.write({"record": "scrape", "label": "impaired_end", "st": _st(probe), **scrape(cfg)})
        ev.write({"record": "stats", "label": "impaired_end", "st": _st(probe), **shaper.stats(pid, dev)})
        rem = shaper.remove(pid, dev)
        removed = rem["verified"]
        ev.write({"record": "remove", "st": _st(probe), "reason": "planned", **rem})
        log(f"netem: removed, verified={removed}")
        ev.write({"record": "scrape", "label": "recovery_start", "st": _st(probe), **scrape(cfg)})
        wait_until(baseline_s + impaired_s + recovery_s - 1.0)
        ev.write({"record": "scrape", "label": "recovery_end", "st": _st(probe), **scrape(cfg)})
    except Exception as exc:
        ev.write({"record": "error", "st": _st(probe), "error": f"{type(exc).__name__}: {exc}"})
        log(f"netem: ERROR {type(exc).__name__}: {exc}")
    finally:
        # Whatever happened above, nothing may stay shaped.
        try:
            if not removed:
                ev.write({"record": "remove", "st": _st(probe), "reason": "cleanup", **shaper.clean()})
        except Exception as exc:
            ev.write({"record": "remove", "st": _st(probe), "reason": "cleanup", "verified": False,
                      "error": f"{type(exc).__name__}: {exc}"})
        shaper.disarm_watchdog()


def start(cfg, sc, d, run_dir, probe, log, stop) -> threading.Thread:
    t = threading.Thread(target=run_step, args=(cfg, sc, d, run_dir, probe, log, stop), name="netem", daemon=True)
    t.start()
    return t


def final_cleanup(cfg: LabConfig, run_dir: Path, log) -> dict:
    """The runner's own last word: clean by container name and record the verdict. Never raises."""
    try:
        rec = Shaper(cfg).clean()
    except Exception as exc:
        rec = {"verified": False, "error": f"{type(exc).__name__}: {exc}"}
    Evidence(run_dir).write({"record": "final_cleanup", **rec})
    log(f"netem: final cleanup verified={rec.get('verified')}")
    return rec
