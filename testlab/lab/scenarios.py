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
_ACTION_KINDS = {"cast_nearest_enemy", "cast_forward", "jump"}
_DISRUPTIONS = {"kill_client", "restart_gameserver"}

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
        for step in block.get("steps", []):
            if step.get("mode") not in _STEP_MODES:
                raise ScenarioError(f"{sc['id']}: unknown step mode {step.get('mode')}")
            if float(step.get("t1", 0)) <= float(step.get("t0", 0)):
                raise ScenarioError(f"{sc['id']}: step t1 must be after t0: {step}")
        for action in block.get("actions", []):
            if action.get("kind") not in _ACTION_KINDS:
                raise ScenarioError(f"{sc['id']}: unknown action kind {action.get('kind')}")
    for d in sc["disruptions"]:
        if d.get("kind") not in _DISRUPTIONS:
            raise ScenarioError(f"{sc['id']}: unknown disruption {d.get('kind')}")
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
        for key in ("steps", "actions"):
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
        "steps": [_step(s) for s in block.get("steps", [])],
        "actions": [_action(a) for a in block.get("actions", [])],
    }


def _step(s: dict) -> dict:
    out = {"t0": float(s["t0"]), "t1": float(s["t1"]), "mode": s["mode"],
           "x": float(s.get("x", 0)), "y": float(s.get("y", 0)), "rate": float(s.get("rate", 1)),
           "px": float(s.get("px", 0)), "py": float(s.get("py", 0)),
           "stop_distance": float(s.get("stop_distance", 0.5)), "target_client": int(s.get("target_client", -1))}
    return out


def _action(a: dict) -> dict:
    return {"t0": float(a["t0"]), "t1": float(a["t1"]), "kind": a["kind"],
            "interval_s": float(a.get("interval_s", 1)), "range": float(a.get("range", 12))}
