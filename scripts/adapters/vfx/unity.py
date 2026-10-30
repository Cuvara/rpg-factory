#!/usr/bin/env python3
"""Read-only Unity prefab text adapter. Never launches the Editor."""
import argparse
import json
import re
import sys
from pathlib import Path


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
    meta = Path(str(path) + ".meta")
    guid = None
    if meta.exists():
        match = re.search(r"^guid:\s*([0-9a-f]+)\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M)
        guid = match.group(1) if match else None
    reasons = [] if fields else ["Prefab parsed but no supported ParticleSystem fields were found"]
    state = "PASS" if fields else "HUMAN_REQUIRED"
    if budget and fields:
        try:
            if int(fields["max_particles"]) > float(budget["max_particles"]):
                state = "FAIL"; reasons.append("prefab maximum particles exceed spec budget")
        except (KeyError, TypeError, ValueError):
            state = "HUMAN_REQUIRED"; reasons.append("complete particle budget unavailable for comparison")
    return {"state": state, "asset": str(path), "guid": guid or (re.search(r"^guid:\s*([0-9a-f]+)\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M).group(1) if meta.exists() and re.search(r"^guid:\s*([0-9a-f]+)\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M) else None), "fields": fields, "reasons": reasons}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(); parser.add_argument("project"); parser.add_argument("asset", nargs="?", default=""); parser.add_argument("--guid"); parser.add_argument("--budget-json"); args = parser.parse_args()
    budget = json.loads(Path(args.budget_json).read_text(encoding="utf-8")) if args.budget_json else None
    result = inspect(args.project, args.asset, args.guid, budget); print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "PASS" else 1


if __name__ == "__main__": sys.exit(main())
