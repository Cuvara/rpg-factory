"""Scenario definitions (testlab/scenarios/*.json) and their expansion into per-client plans.

A scenario is data: who connects, what the server is configured with, what each client does and
when, and which assertions decide the result. Adding a scenario is adding a JSON file; the
orchestration code does not change. Schema: testlab/README.md "Scenario format".
"""

from __future__ import annotations

import copy
from pathlib import Path

from . import SCHEMA_PLAN, SCHEMA_SCENARIO, util

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"

_STEP_MODES = {"idle", "move", "circle", "toward_point", "toward_nearest_enemy", "away_from_nearest_enemy", "toward_client"}
_ACTION_KINDS = {"cast_nearest_enemy", "cast_forward", "jump",
                 # Coverage hooks C2/C5/C6 (client docs/TESTLAB.md "Coverage hooks"): one-shot at t0.
                 "cast_at_point", "cast_spam", "stall", "quit", "reconnect"}
_ONE_SHOT = {"stall", "quit", "reconnect"}
_DISRUPTIONS = {"kill_client", "restart_gameserver", "debug_kill",
                # Raw-client steps (lab/rawprobe.py): S16 malformed input, S17 churn.
                "raw_malformed", "raw_churn"}

DEFAULTS = {
    "clients": 3,
    "map": "map_01",
    "seed": 1,
    "duration_s": 30,
    "start_delay_s": 3,
    "sample_hz": 20,
    "server_sample_hz": 5,
    "fresh_server": True,
    "screenshots_s": [],
    "anomaly_screenshots": 3,
    "overlay": True,
    "jump": {"max_speed": 6.0, "factor": 3.0, "slack": 0.25},
    "client_defaults": {"steps": [], "actions": []},
    "per_client": [],
    "bots": None,
    "disruptions": [],
    "assertions": [],
    "join_timeout_s": 120,
    # Ask the game server for its per-snapshot delivery trace (GAMESERVER_SNAPSHOT_TRACE, contract
    # C1); the harness copies it to server/snapshot-trace.csv for `analyze --delivery`.
    "snapshot_trace": False,
    # Repeat each client's steps and actions every N seconds until duration_s (soaks run longer than
    # the scripted cycle). None: the plan runs once and the client idles after its last step.
    "repeat_cycle_s": None,
}


class ScenarioError(ValueError):
    pass


def list_ids() -> list[str]:
    return sorted(p.stem.split("-", 1)[0] for p in SCENARIO_DIR.glob("*.json"))


def find(name: str) -> Path:
    p = Path(name)
    if p.suffix == ".json" and p.exists():
        return p
    # Exact id (the part of the file name before the first '-'): "S07" must not also match "S07P".
    matches = sorted(q for q in SCENARIO_DIR.glob("*.json") if q.stem.split("-", 1)[0] == name)
    if len(matches) != 1:
        raise ScenarioError(f"scenario '{name}': {len(matches)} matches in {SCENARIO_DIR}")
    return matches[0]


def load(name: str, overrides: dict | None = None) -> dict:
    path = find(name)
    raw = util.read_json(path)
    if raw is None:
        raise ScenarioError(f"{path}: not valid JSON")
    sc = copy.deepcopy(DEFAULTS)
    sc.update(raw)
    for k, v in (overrides or {}).items():
        if v is not None:
            sc[k] = v
    sc["_path"] = str(path)
    validate(sc)
    return sc


def validate(sc: dict) -> None:
    if sc.get("schema") != SCHEMA_SCENARIO:
        raise ScenarioError(f"{sc.get('_path')}: schema must be {SCHEMA_SCENARIO}")
    for key in ("id", "version", "title"):
        if not sc.get(key):
            raise ScenarioError(f"{sc.get('_path')}: '{key}' is required")
    if int(sc["clients"]) < 1:
        raise ScenarioError("clients must be >= 1")
    for block in [sc["client_defaults"], *sc["per_client"]]:
        if "predictor_trace" in (block or {}) and not isinstance(block["predictor_trace"], bool):
            raise ScenarioError(f"{sc['id']}: predictor_trace must be true or false: {block['predictor_trace']!r}")
        for step in (block or {}).get("steps", []):
            if step.get("mode") not in _STEP_MODES:
                raise ScenarioError(f"{sc['id']}: unknown step mode {step.get('mode')}")
            if float(step.get("t1", 0)) <= float(step.get("t0", 0)):
                raise ScenarioError(f"{sc['id']}: step t1 must be after t0: {step}")
        for action in (block or {}).get("actions", []):
            if action.get("kind") not in _ACTION_KINDS:
                raise ScenarioError(f"{sc['id']}: unknown action kind {action.get('kind')}")
            if action["kind"] == "stall" and int(action.get("ms", 0)) <= 0:
                raise ScenarioError(f"{sc['id']}: a stall needs ms > 0: {action}")
    for d in sc["disruptions"]:
        if d.get("kind") not in _DISRUPTIONS:
            raise ScenarioError(f"{sc['id']}: unknown disruption {d.get('kind')}")
        if d["kind"] in ("kill_client", "debug_kill") and not 0 <= int(d.get("client", -1)) < int(sc["clients"]):
            raise ScenarioError(f"{sc['id']}: disruption {d['kind']} needs a client index: {d}")
        if d["kind"] == "raw_malformed":
            from . import rawprobe
            cases = d.get("cases") or []
            ids = [c.get("id") for c in cases]
            if not cases or len(ids) != len(set(ids)) or not all(ids):
                raise ScenarioError(f"{sc['id']}: raw_malformed needs cases with unique ids")
            unknown = [c.get("kind") for c in cases if c.get("kind") not in rawprobe.SENDERS]
            if unknown:
                raise ScenarioError(f"{sc['id']}: unknown raw_malformed case kind {unknown}")
        if d["kind"] == "raw_churn" and int(d.get("cycles", 10)) < 2:
            raise ScenarioError(f"{sc['id']}: raw_churn needs at least 2 cycles (one drop, one leave)")
    if not sc["assertions"]:
        raise ScenarioError(f"{sc['id']}: a scenario without assertions cannot pass or fail")
    ids = [a.get("id") for a in sc["assertions"]]
    if len(ids) != len(set(ids)):
        raise ScenarioError(f"{sc['id']}: duplicate assertion ids")


def client_plan(sc: dict, index: int, run_id: str) -> dict:
    """The plan.json one player receives (TestLabPlan on the C# side)."""
    block = copy.deepcopy(sc["client_defaults"])
    if index < len(sc["per_client"]):
        override = sc["per_client"][index] or {}
        for key in ("steps", "actions", "predictor_trace"):
            if key in override:
                block[key] = override[key]
    jump = sc["jump"]
    return {
        "schema": SCHEMA_PLAN,
        "run_id": run_id,
        "scenario_id": sc["id"],
        "client_index": index,
        "map": sc["map"],
        "duration_s": float(sc["duration_s"]),
        "sample_hz": float(sc["sample_hz"]),
        "jump_factor": float(jump["factor"]),
        "jump_slack": float(jump["slack"]),
        "max_speed": float(jump["max_speed"]),
        "screenshots_s": [float(t) for t in sc["screenshots_s"]],
        "anomaly_screenshots": int(sc["anomaly_screenshots"]),
        "overlay": bool(sc["overlay"]),
        "quit_on_done": True,
        # Netcode predictor call trace to trace.ndjson (client hook, Netcode >= 8986908); opt-in per client.
        "predictor_trace": bool(block.get("predictor_trace", False)),
        "steps": [_step(s) for s in _repeat(block.get("steps", []), sc)],
        "actions": [_action(a) for a in _repeat(block.get("actions", []), sc)],
    }


def traced_clients(sc: dict) -> list[int]:
    """Client indices whose plan turns the predictor call trace on (client_defaults or per_client)."""
    out = []
    for i in range(int(sc.get("clients", 0))):
        block = sc["client_defaults"] or {}
        if i < len(sc["per_client"]) and "predictor_trace" in (sc["per_client"][i] or {}):
            block = sc["per_client"][i]
        if block.get("predictor_trace"):
            out.append(i)
    return out


def _repeat(items: list, sc: dict) -> list:
    """The scripted cycle, then copies of it shifted by k x repeat_cycle_s while they start inside
    duration_s, each clipped to the duration. The first cycle is unchanged; nothing is random, so
    a soak of any length is reproducible."""
    cycle = sc.get("repeat_cycle_s")
    duration = float(sc["duration_s"])
    if not cycle or float(cycle) <= 0:
        return list(items)
    cycle = float(cycle)
    out, k = [], 0
    while k * cycle < duration:
        for it in items:
            t0 = float(it["t0"]) + k * cycle
            if t0 >= duration:
                continue
            c = dict(it)
            c["t0"] = t0
            if "t1" in it:
                c["t1"] = min(float(it["t1"]) + k * cycle, duration)
            out.append(c)
        k += 1
        if not items:
            break
    return out


def _step(s: dict) -> dict:
    out = {"t0": float(s["t0"]), "t1": float(s["t1"]), "mode": s["mode"],
           "x": float(s.get("x", 0)), "y": float(s.get("y", 0)), "rate": float(s.get("rate", 1)),
           "px": float(s.get("px", 0)), "py": float(s.get("py", 0)),
           "stop_distance": float(s.get("stop_distance", 0.5)), "target_client": int(s.get("target_client", -1))}
    return out


def _action(a: dict) -> dict:
    # One-shot actions (stall, quit, reconnect) fire at t0; the client ignores t1.
    t1 = a.get("t1", a["t0"] if a["kind"] in _ONE_SHOT else None)
    return {"t0": float(a["t0"]), "t1": float(t1), "kind": a["kind"],
            "interval_s": float(a.get("interval_s", 1)), "range": float(a.get("range", 12)),
            "x": float(a.get("x", 0)), "y": float(a.get("y", 0)),
            "interval_ms": float(a.get("interval_ms", 100)), "ms": int(a.get("ms", 250))}
