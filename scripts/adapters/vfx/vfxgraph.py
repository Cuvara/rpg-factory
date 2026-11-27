#!/usr/bin/env python3
"""Read-only VFX Graph (.vfx) text adapter. Never launches the Editor.

Reads a text-serialized VFX Graph asset (Unity YAML) and its .meta: the asset GUID, the particle
systems with their capacities and the GUIDs the graph references (textures, meshes, Shader Graphs,
subgraphs). With --stats it also reads the capture statistics of the effect (stats.json,
cuvara.vfx-capture/1, written by the com.cuvara.vfx capture verb) and checks that they belong to
this asset: same effect path, same per-system capacities and the SHA-256 of the
<Name>.vfxrecipe.json next to the .vfx. With --budget-json it compares the asset and the capture
with a spec budget (max_particles, max_systems, max_alive).

Same interface and states as the Shuriken prefab adapter (unity.py): PASS, FAIL, HUMAN_REQUIRED,
NOT_AVAILABLE. Appearance is never judged here: a person reviews the capture.
"""
import argparse
import hashlib
import json
import math
import numbers
import re
import sys
from pathlib import Path

CAPTURE_SCHEMA = "cuvara.vfx-capture/1"
# class id of VisualEffectResource in Unity YAML
RESOURCE_CLASS = "2058629511"
# VFXDataParticle.dataType
DATA_TYPES = {0: "Particle", 1: "ParticleStrip"}
# GUIDs of Unity's built-in resources (default meshes, textures, shaders)
BUILTIN_GUIDS = {"0000000000000000e000000000000000", "0000000000000000f000000000000000"}
TEXTURE_TYPES = {"Texture", "Texture2D", "Texture2DArray", "Texture3D", "Cubemap", "CubemapArray", "RenderTexture"}

DOC_RE = re.compile(r"^--- !u!(\d+) &(-?\d+)[^\n]*$", re.M)
GUID_RE = re.compile(r"^guid:\s*([0-9a-f]{32})\s*$", re.M)
REF_RE = re.compile(r"\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-f]{32}),\s*type:\s*\d+\}")
SERIALIZED_REF_RE = re.compile(r'"guid"\s*:\s*"([0-9a-f]{32})"')
TOP_KEY_RE = re.compile(r"^  (\w+):")
SERIALIZABLE_TYPE_RE = re.compile(r"m_SerializableType:\s*([\w.]+)")


def _valid_budget(value, integer=False):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    if not math.isfinite(value) or value < 0:
        return False
    return not integer or isinstance(value, numbers.Integral)


def _meta_guid(path):
    meta = Path(str(path) + ".meta")
    if not meta.is_file():
        return None
    match = GUID_RE.search(meta.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


def _documents(text):
    """Split Unity YAML into (class_id, file_id, body) tuples."""
    marks = list(DOC_RE.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        yield mark.group(1), mark.group(2), text[mark.end():end]


def _scalar(body, key):
    match = re.search(r"^  " + re.escape(key) + r":[ \t]*([^\n]*)$", body, re.M)
    return match.group(1).strip() if match else None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _add(refs, kind, guid):
    if guid in BUILTIN_GUIDS:
        refs["builtin"].add(guid)
    else:
        refs[kind].add(guid)


def parse_vfx(text):
    """Facts of a text-serialized .vfx: resource name, graph version, systems and references."""
    resource = None
    graph_version = None
    systems = []
    refs = {key: set() for key in ("textures", "meshes", "shaders", "subgraphs", "other", "builtin")}
    for class_id, file_id, body in _documents(text):
        if class_id == RESOURCE_CLASS:
            resource = _scalar(body, "m_Name") or ""
            continue
        version = _scalar(body, "m_GraphVersion")
        if version is not None and graph_version is None:
            graph_version = _int(version)
        # editor script references (m_Script) are VFX Graph's own classes, not asset dependencies
        top_key = None
        for line in body.splitlines():
            key_match = TOP_KEY_RE.match(line)
            if key_match:
                top_key = key_match.group(1)
            stripped = line.strip()
            if stripped.startswith("m_Script:"):
                continue
            for match in REF_RE.finditer(line):
                guid = match.group(2)
                if "shaderGraph:" in stripped:
                    _add(refs, "shaders", guid)
                elif stripped.startswith("m_Subgraph:") or (stripped.startswith("- ") and top_key == "m_SubgraphDependencies"):
                    _add(refs, "subgraphs", guid)
                else:
                    _add(refs, "other", guid)
        # object slot values are a JSON string next to their serializable type
        value_type = None
        for line in body.splitlines():
            type_match = SERIALIZABLE_TYPE_RE.search(line)
            if type_match:
                value_type = type_match.group(1).rsplit(".", 1)[-1]
                continue
            for guid in SERIALIZED_REF_RE.findall(line):
                if value_type in TEXTURE_TYPES:
                    _add(refs, "textures", guid)
                elif value_type == "Mesh":
                    _add(refs, "meshes", guid)
                elif value_type == "Shader":
                    _add(refs, "shaders", guid)
                else:
                    _add(refs, "other", guid)
        data_type = _int(_scalar(body, "dataType"))
        capacity = _int(_scalar(body, "capacity"))
        if data_type is not None and capacity is not None:
            title = _scalar(body, "title")
            system = {"file_id": file_id, "title": title or None,
                      "data_type": DATA_TYPES.get(data_type, "dataType " + str(data_type)), "capacity": capacity}
            if data_type == 1:
                system["strip_capacity"] = _int(_scalar(body, "stripCapacity"))
                system["particles_per_strip"] = _int(_scalar(body, "particlePerStripCount"))
            systems.append(system)
    # a GUID seen as a subgraph or shader is not also "other"
    refs["other"] -= refs["subgraphs"] | refs["shaders"] | refs["textures"] | refs["meshes"]
    return {"resource": resource, "graph_version": graph_version, "systems": systems,
            "references": {key: sorted(value) for key, value in refs.items()}}


def _resolve(project, asset, guid):
    if guid:
        matches = []
        for meta in project.rglob("*.vfx.meta"):
            try:
                if re.search(r"^guid:\s*" + re.escape(guid) + r"\s*$", meta.read_text(encoding="utf-8", errors="replace"), re.M):
                    matches.append(Path(str(meta)[:-5]))
            except OSError:
                continue
        if len(matches) == 1:
            return matches[0].resolve(), None
        if not matches:
            return None, {"state": "NOT_AVAILABLE", "reasons": ["VFX Graph asset GUID was not found in the supplied project"]}
        return None, {"state": "HUMAN_REQUIRED", "reasons": ["VFX Graph asset GUID is duplicated in the supplied project"]}
    requested = Path(asset)
    return ((project / requested).resolve() if not requested.is_absolute() else requested.resolve()), None


def _read_stats(stats_path):
    try:
        stats = json.loads(Path(stats_path).read_text(encoding="utf-8"))
    except OSError:
        return None, "stats file is unavailable"
    except ValueError:
        return None, "stats file is not valid JSON"
    if not isinstance(stats, dict):
        return None, "stats file is not a JSON object"
    if stats.get("schema") != CAPTURE_SCHEMA:
        return None, "stats schema is " + json.dumps(stats.get("schema")) + ", expected " + CAPTURE_SCHEMA
    return stats, None


def _stats_summary(stats):
    alive = stats.get("alive") if isinstance(stats.get("alive"), dict) else {}
    systems = stats.get("systems") if isinstance(stats.get("systems"), list) else []
    return {
        "schema": stats.get("schema"), "effect": stats.get("effect"), "recipe_sha256": stats.get("recipe_sha256"),
        "seed": stats.get("seed"), "camera": stats.get("camera"), "lighting": stats.get("lighting"),
        "unity": stats.get("unity"), "vfx_graph": stats.get("vfx_graph"),
        "duration_seconds": stats.get("duration_seconds"), "alive_peak": alive.get("peak"),
        "systems": [{"name": s.get("name"), "capacity": s.get("capacity"), "peak": s.get("peak")}
                    for s in systems if isinstance(s, dict)],
    }


def inspect(project, asset, guid=None, budget=None, stats_path=None):
    project = Path(project).resolve()
    if not project.is_dir():
        return {"state": "NOT_AVAILABLE", "reasons": ["Unity project root is unavailable"]}
    path, failure = _resolve(project, asset, guid)
    if failure:
        return failure
    if not path.is_relative_to(project) or not path.is_file():
        return {"state": "NOT_AVAILABLE", "reasons": ["Unity project or referenced .vfx asset is unavailable inside the supplied project root"]}
    if path.suffix != ".vfx":
        return {"state": "NOT_AVAILABLE", "asset": str(path), "reasons": ["asset is not a .vfx file; Shuriken prefabs use unity.py"]}
    raw = path.read_bytes()
    if not raw.startswith(b"%YAML"):
        return {"state": "NOT_AVAILABLE", "asset": str(path), "reasons": ["asset is not text-serialized Unity YAML (binary serialization cannot be read)"]}
    facts = parse_vfx(raw.decode("utf-8", errors="replace"))
    if facts["resource"] is None:
        return {"state": "NOT_AVAILABLE", "asset": str(path), "reasons": ["file holds no VisualEffectResource; it is not a VFX Graph asset"]}
    relative = path.relative_to(project).as_posix()
    recipe_file = path.with_name(path.stem + ".vfxrecipe.json")
    recipe = ({"path": recipe_file.relative_to(project).as_posix(), "sha256": hashlib.sha256(recipe_file.read_bytes()).hexdigest()}
              if recipe_file.is_file() else None)
    capacities = [s["capacity"] for s in facts["systems"]]
    fields = {}
    if capacities:
        fields["max_particles"] = str(sum(capacities))
        fields["particle_systems"] = len(capacities)
        fields["max_particles_per_system"] = capacities
    reasons = [] if fields else ["VFX Graph asset parsed but has no particle system with a capacity"]
    state = "PASS" if fields else "HUMAN_REQUIRED"
    comparisons = []

    def fail(reason):
        nonlocal state
        state = "FAIL"
        reasons.append(reason)

    def human(reason):
        nonlocal state
        if state != "FAIL":
            state = "HUMAN_REQUIRED"
        reasons.append(reason)

    stats = None
    if stats_path:
        loaded, error = _read_stats(stats_path)
        if error:
            fail(error)
        else:
            stats = _stats_summary(loaded)
            effect = stats["effect"] if isinstance(stats["effect"], str) else ""
            if effect.endswith(".vfx"):
                if effect != relative and not effect.endswith("/" + relative):
                    fail("stats were captured for " + effect + ", not " + relative)
                else:
                    comparisons.append("stats.effect")
                    stat_caps = sorted(s["capacity"] for s in stats["systems"] if isinstance(s["capacity"], int))
                    if stat_caps != sorted(capacities):
                        fail("capture system capacities " + json.dumps(stat_caps) + " differ from the asset's " + json.dumps(sorted(capacities)) + "; recapture")
                    else:
                        comparisons.append("stats.systems.capacity")
            else:
                human("stats were captured for a prefab (" + (effect or "unknown effect") + "); asset match needs a person")
            expected = recipe["sha256"] if recipe else None
            if stats["recipe_sha256"] != expected:
                fail("stats recipe_sha256 " + json.dumps(stats["recipe_sha256"]) + " differs from the recipe next to the asset " + json.dumps(expected) + "; recapture")
            else:
                comparisons.append("stats.recipe_sha256")
    if not isinstance(budget, dict):
        human("spec budget missing; asset cannot PASS without a budget comparison")
    elif fields:
        checks = (("max_particles", sum(capacities), "asset particle capacity exceeds spec budget"),
                  ("max_systems", len(capacities), "asset particle systems exceed spec budget"))
        if "max_particles" not in budget:
            human("spec budget is missing max_particles")
        for key, value, message in checks:
            if key not in budget:
                continue
            if not _valid_budget(budget[key], integer=True):
                fail(key + " budget must be a finite non-negative integer")
            elif value > budget[key]:
                fail(message)
            else:
                comparisons.append(key)
        if "max_alive" in budget:
            peak = stats["alive_peak"] if stats else None
            if not _valid_budget(budget["max_alive"], integer=True):
                fail("max_alive budget must be a finite non-negative integer")
            elif not isinstance(peak, int) or isinstance(peak, bool):
                human("max_alive needs capture stats with alive.peak")
            elif peak > budget["max_alive"]:
                fail("captured alive.peak exceeds spec budget")
            else:
                comparisons.append("max_alive")
    return {"state": state, "asset": str(path), "relative_path": relative, "guid": _meta_guid(path),
            "resource": facts["resource"], "graph_version": facts["graph_version"], "fields": fields,
            "systems": facts["systems"], "references": facts["references"], "recipe": recipe, "stats": stats,
            "comparisons": comparisons, "reasons": reasons}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Read a VFX Graph .vfx asset, its .meta and optional capture stats (text only).")
    parser.add_argument("project"); parser.add_argument("asset", nargs="?", default="")
    parser.add_argument("--guid"); parser.add_argument("--budget-json"); parser.add_argument("--stats")
    args = parser.parse_args()
    if not args.asset and not args.guid:
        parser.error("give an asset path or --guid")
    budget = json.loads(Path(args.budget_json).read_text(encoding="utf-8")) if args.budget_json else None
    result = inspect(args.project, args.asset, args.guid, budget, args.stats); print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "PASS" else 1


if __name__ == "__main__": sys.exit(main())
