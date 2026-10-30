#!/usr/bin/env python3
"""Read-only Unity prefab text adapter. Never launches the Editor."""
import argparse
import json
import math
import numbers
import re
import sys
from pathlib import Path


def _valid_budget(value, integer=False):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    if not math.isfinite(value) or value < 0:
        return False
    return not integer or isinstance(value, numbers.Integral)


def inspect(project, asset, guid=None, budget=None):
    project = Path(project).resolve()
    requested = Path(asset)
    path = (project / requested).resolve() if not requested.is_absolute() else requested.resolve()
    if guid:
        matches = []
        for meta in project.rglob("*.meta"):
            try:
                if re.search(r"^guid:\s*" + re.escape(guid) + r"\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M):
                    matches.append(Path(str(meta)[:-5]))
            except OSError:
                continue
        if len(matches) == 1: path = matches[0].resolve()
        elif not matches: return {"state": "NOT_AVAILABLE", "reasons": ["Unity GUID was not found in the supplied project"]}
        else: return {"state": "HUMAN_REQUIRED", "reasons": ["Unity GUID is duplicated in the supplied project"]}
    if not path.is_relative_to(project) or not path.is_file():
        return {"state": "NOT_AVAILABLE", "reasons": ["Unity project or referenced prefab is unavailable inside the supplied project root"]}
    text = path.read_text(encoding="utf-8", errors="replace")
    fields = {}
    patterns = {"max_particles": r"maxNumParticles:\s*(\d+)", "start_lifetime": r"startLifetime:\s*([\d.eE+-]+)", "looping": r"looping:\s*(\d+)", "duration": r"\bduration:\s*([\d.eE+-]+)"}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match: fields[key] = match.group(1)
    # every ParticleSystem in the prefab counts: the effect budget covers all of them
    per_system = [int(v) for v in re.findall(r"maxNumParticles:\s*(\d+)", text)]
    if per_system:
        fields["max_particles"] = str(sum(per_system))
        fields["particle_systems"] = len(per_system)
        fields["max_particles_per_system"] = per_system
    meta = Path(str(path) + ".meta")
    guid = None
    if meta.exists():
        match = re.search(r"^guid:\s*([0-9a-f]+)\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M)
        guid = match.group(1) if match else None
    reasons = [] if fields else ["Prefab parsed but no supported ParticleSystem fields were found"]
    state = "HUMAN_REQUIRED" if not fields else "PASS"
    comparisons = []
    if not isinstance(budget, dict):
        state = "HUMAN_REQUIRED"; reasons.append("spec budget missing; prefab cannot PASS without a budget comparison")
    elif fields:
        if "max_particles" not in fields:
            state = "HUMAN_REQUIRED"; reasons.append("prefab does not expose max_particles for comparison")
        elif "max_particles" not in budget:
            state = "HUMAN_REQUIRED"; reasons.append("spec budget is missing max_particles")
        elif not _valid_budget(budget["max_particles"], integer=True):
            state = "FAIL"; reasons.append("max_particles budget must be a finite non-negative integer")
        elif int(fields["max_particles"]) > budget["max_particles"]:
            state = "FAIL"; reasons.append("prefab maximum particles exceed spec budget")
        else:
            comparisons.append("max_particles")
        for key in ("start_lifetime", "looping", "duration"):
            if key in fields: reasons.append(key + " parsed but has no comparable spec budget")
        if any(key in fields for key in ("start_lifetime", "looping", "duration")):
            if state != "FAIL": state = "HUMAN_REQUIRED"
    return {"state": state, "asset": str(path), "guid": guid or (re.search(r"^guid:\s*([0-9a-f]+)\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M).group(1) if meta.exists() and re.search(r"^guid:\s*([0-9a-f]+)\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M) else None), "fields": fields, "comparisons": comparisons, "reasons": reasons}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(); parser.add_argument("project"); parser.add_argument("asset", nargs="?", default=""); parser.add_argument("--guid"); parser.add_argument("--budget-json"); args = parser.parse_args()
    budget = json.loads(Path(args.budget_json).read_text(encoding="utf-8")) if args.budget_json else None
    result = inspect(args.project, args.asset, args.guid, budget); print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "PASS" else 1


if __name__ == "__main__": sys.exit(main())
