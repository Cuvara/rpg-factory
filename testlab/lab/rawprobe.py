"""Harness steps that drive raw clients (lab/rawclient.py) next to the rendered players.

Two steps, started by a scenario disruption and run on a background thread so the rendered clients
and the server probe keep sampling on the scenario clock:

- `raw_malformed` (S16): per case, one fresh session joins, sends one kind of malformed input, and the
  step watches the server (/status at 4 Hz, /metrics before and after, /debug/entities) for what
  happened to that session and to the rest of the server.
- `raw_churn` (S17): repeated cycles of (a) drop (both sockets closed, no MsgDisconnect) and rejoin,
  and (b) a graceful leave (MsgDisconnect) and rejoin, then a wait that outlasts the longest server
  hold, with Redis key names recorded before the first cycle and after the wait.

The step only RECORDS (`rawprobe.ndjson`: one JSON object per line, "record" says what). It decides
nothing: every verdict is the analyzer's (`malformed_input`, `churn_*` and `redis_leak` in
lab/analyze.py), with thresholds in the scenario and in docs/THRESHOLDS.md.
"""

from __future__ import annotations

import json
import math
import re
import struct
import threading
import time
from pathlib import Path

from . import rawclient as rc
from . import stack, util
from .config import LabConfig

EVIDENCE = "rawprobe.ndjson"

# Series that move on every scrape (rates, byte counters, GC): left out of "counters that moved".
_NOISE = re.compile(r"(achieved_tick_hz|tick_duration|bytes_total|snapshots_|gc_|process_|datagrams_received|"
                    r"tick_processed|sim_group|entities\{|receive_busy|player_saves|events_published|"
                    r"segments_retransmitted|kcp_wait|achieved)")

# /status fields kept in every poll.
_STATUS_KEYS = ("players_online", "connections", "uptime_seconds", "current_tick", "tick_rate")


def parse_metrics(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("gameserver_"):
            m = re.match(r"^(\S+?)\s+([-+0-9.eEInfNa]+)$", line)
            if m:
                try:
                    out[m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
    return out


def moved(before: dict, after: dict) -> dict:
    """Series whose value changed, without the always-moving ones; {series: delta}."""
    out = {}
    for k in set(before) | set(after):
        d = after.get(k, 0.0) - before.get(k, 0.0)
        if d and not _NOISE.search(k):
            out[k] = round(d, 6)
    return dict(sorted(out.items()))


class Evidence:
    """Append-only rawprobe.ndjson, safe from several threads."""

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / EVIDENCE
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")


class Observer:
    """Reads the scratch server the way the probe does, stamped with the scenario clock."""

    def __init__(self, cfg: LabConfig, probe):
        self.cfg, self.probe = cfg, probe

    def st(self) -> float | None:
        return self.probe.scenario_time(util.mono()) if self.probe is not None else None

    def poll(self) -> dict:
        """One /status sample (cheap, 4 Hz during a case)."""
        doc = util.http_json(self.cfg.status_url, timeout=2) or {}
        return {"st": self.st(), "ok": bool(doc), **{k: doc.get(k) for k in _STATUS_KEYS}}

    def full(self) -> dict:
        """/status, every gameserver_ series and the player entity ids and positions."""
        s = self.poll()
        code, body = util.http_get(self.cfg.metrics_url, timeout=4)
        s["metrics"] = parse_metrics(body.decode("utf-8", "replace")) if code == 200 else {}
        ents = util.http_json(self.cfg.debug_entities_url, timeout=2) or {}
        s["entities"] = {e["id"]: e for e in ents.get("entities", [])}
        s["players"] = sorted(i for i, e in s["entities"].items() if e.get("type") == "player")
        return s


def _lab(cfg: LabConfig, sc: dict) -> dict:
    sec = stack.lab_secrets(cfg)
    return {"gateway": (cfg.gateway_host, cfg.gateway_port), "jwt_secret": sec["JWT_SECRET"],
            "join_secret": sec["JOIN_TOKEN_SECRET"], "map_id": sc["map"], "server_id": f"gs-dotnet-{sc['map']}",
            "game_addr": stack.advertised_game_addr(cfg, sc["map"])}


def _source_const(cfg: LabConfig, rel: str, name: str) -> dict:
    """A numeric constant read from the server source (`public const <type> Name = 3.0f;`)."""
    path = cfg.server_repo / rel
    try:
        m = re.search(rf"\b{name}\s*=\s*([-0-9.]+)f?\s*;", path.read_text(encoding="utf-8"))
        return {"value": float(m.group(1)), "source": f"{rel} {name}"} if m else {"value": None, "source": f"{rel}: {name} not found"}
    except OSError as exc:
        return {"value": None, "source": f"{rel}: {exc}"}


def _first_projectile_ability(cfg: LabConfig) -> dict | None:
    try:
        doc = json.loads((cfg.server_repo / "backend/content/abilities.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for ab in doc.get("abilities", []):
        if ab.get("delivery") == "projectile" and ab.get("projectile"):
            return {"id": ab.get("id"), "name": ab.get("name"), "cooldown_ticks": ab.get("cooldownTicks"),
                    "source": "backend/content/abilities.json (first projectile ability)"}
    return None


# --------------------------------------------------------------------------- S16: malformed input

def _send_oversize(p, ctx):
    p.game.send(struct.pack(">I", rc.MAX_FRAME + 1))
    return {"sent": "length prefix 1048577 (MaxMessageSize + 1), no body"}


def _send_length_ffffffff(p, ctx):
    p.game.send(struct.pack(">I", 0xFFFFFFFF))
    return {"sent": "length prefix 0xFFFFFFFF (negative as a signed 32-bit length), no body"}


def _send_zero_length(p, ctx):
    p.game.send(struct.pack(">I", 0))
    return {"sent": "length prefix 0"}


def _send_truncated(p, ctx):
    p.game.answer_pings = False  # a reply would complete the frame; the point is a peer that stops mid-frame
    p.game.send(struct.pack(">I", 64) + b'{"type":7,')
    return {"sent": "length prefix 64, then 10 of the 64 body bytes, then silence (heartbeats not answered)"}


def _send_unknown_type(p, ctx):
    p.game.send_msg(99, {"x": 1})
    for _ in range(5):
        time.sleep(0.2)
        p.send_input(0.0, 0.0)
    return {"sent": "valid JSON envelope of type 99 (not a defined message), then 5 valid inputs"}


def _send_type_out_of_range(p, ctx):
    p.game.send(rc.frame(b'{"type":300,"payload":{}}'))
    return {"sent": "JSON envelope with type 300 (does not fit the one-byte type)"}


def _send_garbage_envelope(p, ctx):
    p.game.send(rc.frame(b"\x0a" + rc.random_bytes(47, ctx["seed"])))
    return {"sent": "48 seeded noise bytes starting 0x0a (sniffed as protobuf, not a valid Envelope)"}


def _send_garbage_payload(p, ctx):
    p.game.send(rc.frame(b"\x08\x07\x12\x10" + rc.random_bytes(16, ctx["seed"] + 1)))
    return {"sent": "valid protobuf Envelope of type 7 (Input) whose 16-byte payload is seeded noise"}


def _send_move_out_of_range(p, ctx):
    sent = []
    for mag in (1.6, 50.0, 1e6):  # GameConstants.MaxInputMagnitude is 1.5
        p.send_input(mag, 0.0)
        sent.append(mag)
        time.sleep(0.4)  # a world tick apart: inputs inside one drain coalesce, only the last is judged
    return {"sent": f"{len(sent)} movement inputs of magnitude {sent} (one per 0.4 s)", "inputs": len(sent)}


def _send_attack_out_of_range(p, ctx):
    ents = ctx["entities"]
    me = ents.get(p.user_id)
    mobs = [e for e in ents.values() if e.get("type") == "mob" and not e.get("dead")]
    if me is None or not mobs:
        return {"sent": None, "error": "no player entity or no live enemy to aim at"}
    far = max(mobs, key=lambda e: math.hypot(e["x"] - me["x"], e["y"] - me["y"]))
    dist = math.hypot(far["x"] - me["x"], far["y"] - me["y"])
    for _ in range(4):
        p.send_input(0.0, 0.0, attack_target_id=far["id"])
        time.sleep(0.4)
    return {"sent": f"4 attack inputs on {far['id']} at distance {dist:.1f}", "target": far["id"],
            "target_distance": round(dist, 2), "target_hp": far.get("hp"), "inputs": 4}


def _send_ability_cooldown(p, ctx):
    ab = ctx["ability"]
    if not ab or ab.get("id") is None:
        return {"sent": None, "error": "no projectile ability in content"}
    for _ in range(20):
        p.send_input(0.0, 0.0, ability_id=int(ab["id"]), aim_x=1.0, aim_y=0.0)
        time.sleep(0.1)
    return {"sent": f"20 casts of ability {ab['id']} ({ab.get('name')}) at 100 ms, cooldown {ab.get('cooldown_ticks')} ticks",
            "inputs": 20}


SENDERS = {
    "oversize_length": _send_oversize, "length_ffffffff": _send_length_ffffffff, "zero_length": _send_zero_length,
    "truncated_frame": _send_truncated, "unknown_type": _send_unknown_type, "type_out_of_range": _send_type_out_of_range,
    "garbage_envelope": _send_garbage_envelope, "garbage_payload": _send_garbage_payload,
    "move_out_of_range": _send_move_out_of_range, "attack_out_of_range": _send_attack_out_of_range,
    "ability_cooldown": _send_ability_cooldown,
}


def run_malformed(cfg: LabConfig, sc: dict, d: dict, run_dir: Path, probe, log, stop: threading.Event) -> None:
    ev, obs = Evidence(run_dir), Observer(cfg, probe)
    tag = Path(run_dir).name[-9:].replace("-", "")
    ev.write({"record": "start", "step": "raw_malformed", "st": obs.st(), "cases": [c["id"] for c in d["cases"]]})
    try:
        lab = _lab(cfg, sc)
    except Exception as exc:  # no advertised address: nothing can be judged
        ev.write({"record": "error", "step": "raw_malformed", "error": f"{type(exc).__name__}: {exc}"})
        return
    consts = {"attack_range": _source_const(cfg, "backend/gameserver-dotnet/Shared.GameLogic/Components/GameConstants.cs", "AttackRange"),
              "max_input_magnitude": _source_const(cfg, "backend/gameserver-dotnet/Shared.GameLogic/Components/GameConstants.cs", "MaxInputMagnitude"),
              "ability": _first_projectile_ability(cfg)}
    for i, spec in enumerate(d["cases"]):
        if stop.is_set():
            break
        rec = {"record": "case", "id": spec["id"], "kind": spec["kind"], "user_id": f"lab-raw-{tag}-{spec['id']}"}
        try:
            _run_case(cfg, lab, obs, spec, rec, consts, i + int(sc.get("seed", 0)) * 100)
        except Exception as exc:  # recorded, never raised: the other cases and the rendered run go on
            rec["error"] = f"{type(exc).__name__}: {exc}"
        ev.write(rec)
        log(f"raw_malformed: {spec['id']}: " + ("error " + rec["error"] if rec.get("error") else
            f"closed_after_s={rec.get('closed_after_s')} snapshots_after={rec.get('snapshots_after_send')}"))
        stop.wait(float(d.get("gap_s", 1.0)))
    ev.write({"record": "end", "step": "raw_malformed", "st": obs.st(), "constants": consts})


def _run_case(cfg, lab, obs: Observer, spec: dict, rec: dict, consts: dict, seed: int) -> None:
    window = float(spec.get("window_s", 4.0))
    rec["pre"] = obs.full()
    p = rc.RawPlayer(lab, rec["user_id"], spec.get("mode", "gateway"))
    try:
        res = p.connect()
        rec["join"] = res
        if not res["ok"]:
            return
        deadline = util.mono() + 5
        while util.mono() < deadline and rec["user_id"] not in obs.full()["players"]:
            time.sleep(0.2)
        time.sleep(1.5)  # snapshots flowing
        mid = obs.full()
        rec["mid"] = mid
        ctx = {"entities": mid["entities"], "ability": consts["ability"], "seed": seed}
        me = mid["entities"].get(rec["user_id"])
        rec["entity_before"] = {"x": me["x"], "y": me["y"], "speed": me.get("speed")} if me else None
        snaps0 = p.snapshots()
        rec["sent_st"] = obs.st()
        t_send = util.mono()
        rec["detail"] = SENDERS[spec["kind"]](p, ctx)
        rec["send_returned_s"] = round(util.mono() - t_send, 3)
        # Watch: closed once the server's connection count falls below what it was with this session in.
        samples, closed_after = [], None
        end = t_send + window
        while util.mono() < end:
            s = obs.poll()
            samples.append({k: s[k] for k in ("st", "connections", "players_online", "uptime_seconds", "ok")})
            if closed_after is None and s.get("connections") is not None and mid.get("connections") is not None \
                    and s["connections"] < mid["connections"]:
                closed_after = round(util.mono() - t_send, 3)
                if spec.get("stop_when_closed", True):
                    break
            time.sleep(0.25)
        rec["samples"] = samples
        rec["closed_after_s"] = closed_after
        rec["snapshots_after_send"] = p.snapshots() - snaps0
        time.sleep(2.0)  # let gauges and counters settle before the final read
        rec["post"] = obs.full()
        post_me = rec["post"]["entities"].get(rec["user_id"])
        rec["entity_after"] = {"x": post_me["x"], "y": post_me["y"]} if post_me else None
        tgt = (rec["detail"] or {}).get("target")
        if tgt:
            rec["target_hp_after"] = (rec["post"]["entities"].get(tgt) or {}).get("hp")
        rec["moved"] = moved(mid["metrics"], rec["post"]["metrics"])
        rec["moved_since_pre"] = moved(rec["pre"]["metrics"], rec["post"]["metrics"])
        rec["peer_frames"] = {str(k): v for k, v in sorted(p.game.type_counts.items())}
        rec["client_bad_frame"] = p.game.bad_frame
    finally:
        p.leave()  # the polite way out, so no silent session lingers into the next case
    time.sleep(1.0)
    rec["after_cleanup"] = obs.poll()


# --------------------------------------------------------------------------- S17: churn

def _redis_state(cfg: LabConfig, map_id: str) -> dict:
    return {"session_keys": sorted(stack.redis_cli(cfg, '--scan --pattern "session:*"')),
            "registry_keys": sorted(stack.redis_cli(cfg, '--scan --pattern "servers:id:*"')),
            "map_members": sorted(stack.redis_map_members(cfg, map_id))}


def run_churn(cfg: LabConfig, sc: dict, d: dict, run_dir: Path, probe, log, stop: threading.Event) -> None:
    ev, obs = Evidence(run_dir), Observer(cfg, probe)
    tag = Path(run_dir).name[-9:].replace("-", "")
    cycles = int(d.get("cycles", 10))
    connected_s = float(d.get("connected_s", 4.0))
    down = {"drop": float(d.get("drop_down_s", 3.0)), "leave": float(d.get("leave_down_s", 6.0))}
    users = {"drop": f"lab-churn-d-{tag}", "leave": f"lab-churn-l-{tag}"}
    ev.write({"record": "start", "step": "raw_churn", "st": obs.st(), "cycles": cycles, "users": users,
              "connected_s": connected_s, "down_s": down, "settle_s": float(d.get("settle_s", 80.0))})
    try:
        lab = _lab(cfg, sc)
        base = obs.full()
        ev.write({"record": "redis", "label": "before", "st": obs.st(), **_redis_state(cfg, sc["map"]),
                  "players_online": base.get("players_online"), "connections": base.get("connections"),
                  "players": base["players"]})
    except Exception as exc:
        ev.write({"record": "error", "step": "raw_churn", "error": f"{type(exc).__name__}: {exc}"})
        return
    for k in range(cycles):
        if stop.is_set():
            break
        kind = "drop" if k % 2 == 0 else "leave"
        rec = {"record": "cycle", "n": k + 1, "kind": kind, "user_id": users[kind]}
        p = rc.RawPlayer(lab, users[kind], "gateway")
        try:
            rec["join_st"] = obs.st()
            rec["join"] = p.connect()
            if rec["join"]["ok"]:
                end = util.mono() + connected_s
                i = 0
                while util.mono() < end and not stop.is_set():
                    ang = i * 0.3
                    p.send_input(math.cos(ang), math.sin(ang))
                    i += 1
                    time.sleep(0.1)
                rec["snapshots"] = p.snapshots()
                rec["end_st"] = obs.st()
                (p.drop if kind == "drop" else p.leave)()
                rec["pre_close_poll"] = obs.poll()
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            p.drop()
        ev.write(rec)
        log(f"raw_churn: cycle {k + 1}/{cycles} {kind}: join_ok={rec.get('join', {}).get('ok')} "
            f"{rec.get('error') or ''}")
        if k + 1 < cycles:
            stop.wait(down[kind])
    ev.write({"record": "marker", "label": "cycles_done", "st": obs.st()})
    stop.wait(float(d.get("settle_s", 80.0)))
    after = obs.full()
    ev.write({"record": "redis", "label": "after", "st": obs.st(), **_redis_state(cfg, sc["map"]),
              "players_online": after.get("players_online"), "connections": after.get("connections"),
              "players": after["players"], "metrics_moved": moved((base or {}).get("metrics", {}), after["metrics"])})
    ev.write({"record": "end", "step": "raw_churn", "st": obs.st()})


STEPS = {"raw_malformed": run_malformed, "raw_churn": run_churn}


def start(kind: str, cfg: LabConfig, sc: dict, d: dict, run_dir: Path, probe, log, stop: threading.Event) -> threading.Thread:
    """Run one step on a daemon thread. Whatever it raises is recorded as an `error` record."""
    def body():
        try:
            STEPS[kind](cfg, sc, d, run_dir, probe, log, stop)
        except Exception as exc:
            Evidence(run_dir).write({"record": "error", "step": kind, "error": f"{type(exc).__name__}: {exc}"})
    t = threading.Thread(target=body, name=f"rawprobe-{kind}", daemon=True)
    t.start()
    return t
