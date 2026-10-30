"""Production checks for 3D art delivery artifacts."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path


def result(check, state, *reasons):
    return {"check": check, "state": state, "reasons": list(reasons)}


def gltf_data(path):
    raw = path.read_bytes()
    if path.suffix.lower() != ".glb":
        return json.loads(raw.decode("utf-8")), path.parent
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("invalid GLB header")
    magic, version, length = struct.unpack_from("<4sII", raw)
    if version != 2 or length != len(raw):
        raise ValueError("unsupported GLB version or invalid length")
    offset = 12
    while offset + 8 <= len(raw):
        size, kind = struct.unpack_from("<I4s", raw, offset)
        chunk = raw[offset + 8:offset + 8 + size]
        if kind == b"JSON":
            return json.loads(chunk.decode("utf-8")), path.parent
        offset += 8 + size
    raise ValueError("GLB has no JSON chunk")


def triangles(gltf, primitive):
    mode = primitive.get("mode", 4)
    if mode not in (4, 5, 6):
        return 0
    accessor = primitive.get("indices")
    if accessor is not None:
        acc = gltf.get("accessors", [])[accessor]
        count = acc.get("count", 0)
    else:
        position = primitive.get("attributes", {}).get("POSITION")
        count = gltf.get("accessors", [])[position].get("count", 0) if position is not None else 0
    if mode == 4:
        return count // 3
    return max(0, count - 2)


def gltf_check(path, spec):
    data, folder = gltf_data(path)
    return gltf_errors(data, folder, spec)


def gltf_errors(data, folder, spec):
    errors = []
    meshes = data.get("meshes", [])
    if not meshes:
        errors.append("asset contains no meshes")
    budgets = spec.get("polygon_budget_by_lod", {})
    lods = spec.get("lods", [])
    total = sum(triangles(data, p) for mesh in meshes for p in mesh.get("primitives", []))
    budget = budgets.get("default")
    for lod in lods:
        name = lod.get("name") if isinstance(lod, dict) else lod
        match = [m for m in meshes if name in m.get("name", "")]
        if not match:
            errors.append("required LOD missing: " + str(name)); continue
        limit = budgets.get(name, budget)
        count = sum(triangles(data, p) for m in match for p in m.get("primitives", []))
        if limit is not None and count > limit:
            errors.append(f"{name} triangle count {count} exceeds budget {limit}")
    if not lods and budget is not None and total > budget:
        errors.append(f"triangle count {total} exceeds budget {budget}")
    for mesh in meshes:
        if spec.get("naming_pattern") and not __import__("re").fullmatch(spec["naming_pattern"], mesh.get("name", "")):
            errors.append("mesh naming convention failed: " + mesh.get("name", "<unnamed>"))
        for primitive in mesh.get("primitives", []):
            if spec.get("uv_required") and "TEXCOORD_0" not in primitive.get("attributes", {}):
                errors.append("required UV set TEXCOORD_0 missing")
            material = primitive.get("material")
            if material is not None and material >= len(data.get("materials", [])):
                errors.append("primitive material index out of range")
    for image in data.get("images", []):
        uri = image.get("uri")
        if uri and not uri.startswith("data:") and not (folder / uri).is_file():
            errors.append("texture image missing: " + uri)
    if spec.get("materials_required") and not data.get("materials"):
        errors.append("materials required but none found")
    nodes = data.get("nodes", [])
    if spec.get("node_naming_pattern"):
        import re
        for node in nodes:
            if not re.fullmatch(spec["node_naming_pattern"], node.get("name", "")):
                errors.append("node naming convention failed: " + node.get("name", "<unnamed>"))
    if spec.get("root_required"):
        scenes = data.get("scenes", [])
        scene_index = data.get("scene", 0)
        if not scenes or not isinstance(scene_index, int) or not 0 <= scene_index < len(scenes):
            errors.append("scene/root structure missing")
        else:
            roots = scenes[scene_index].get("nodes", [])
            if not roots or any(not isinstance(i, int) or not 0 <= i < len(nodes) for i in roots):
                errors.append("scene/root structure missing or invalid")
    if spec.get("rig_required") and not data.get("skins"):
        errors.append("required skin/rig missing")
    if spec.get("animation_required") and not data.get("animations"):
        errors.append("required animations missing")
    declared = spec.get("export_settings", {})
    asset = data.get("asset", {})
    extras = data.get("extras", {})
    for key in ("scale", "units", "up_axis"):
        expected = declared.get(key)
        actual = extras.get(key, asset.get(key))
        if expected is not None and actual != expected:
            errors.append(f"export {key} mismatch: expected {expected}, got {actual}")
    return errors


def blender_check(path, ctx, spec):
    tool = ctx.tools("blender") if ctx.tools else None
    if not tool:
        return result("art3d-dcc-inspection", "NOT_AVAILABLE", "Blender not available; install Blender or provide glTF/GLB for automatic inspection")
    adapter = Path(__file__).resolve().parents[2] / "adapters" / "art3d" / "blender-stats.py"
    with tempfile.TemporaryDirectory(prefix="rpg-art3d-") as temp:
        output = Path(temp) / "stats.json"
        try:
            command = [tool["path"], "-b"]
            if path.suffix.lower() == ".blend": command.append(str(path))
            command.extend(["--python", str(adapter), "--", str(output), str(path)])
            proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=90)
        except subprocess.TimeoutExpired:
            return result("art3d-dcc-inspection", "HUMAN_REQUIRED", "Blender inspection exceeded 90 second timeout")
        if proc.returncode or not output.exists():
            return result("art3d-dcc-inspection", "HUMAN_REQUIRED", "Blender could not inspect file: " + (proc.stderr[-500:] or "adapter produced no output"))
        try:
            stats = json.loads(output.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            return result("art3d-dcc-inspection", "HUMAN_REQUIRED", "invalid Blender adapter output: " + str(exc))
        problems = []
        import re
        mesh_objects = [x for x in stats.get("objects", []) if x.get("type") == "MESH"]
        if not mesh_objects: problems.append("asset contains no meshes")
        budgets = spec.get("polygon_budget_by_lod", {})
        lods = spec.get("lods", [])
        total = sum(x.get("triangles", 0) for x in mesh_objects)
        if not lods and budgets.get("default") is not None and total > budgets["default"]:
            problems.append(f"triangle count {total} exceeds budget {budgets['default']}")
        for lod in lods:
            name = lod.get("name") if isinstance(lod, dict) else lod
            matches = [x for x in mesh_objects if name in x.get("name", "")]
            if not matches: problems.append("required LOD missing: " + str(name)); continue
            limit = budgets.get(name, budgets.get("default"))
            count = sum(x.get("triangles", 0) for x in matches)
            if limit is not None and count > limit: problems.append(f"{name} triangle count {count} exceeds budget {limit}")
        if spec.get("naming_pattern"):
            for obj in mesh_objects:
                if not re.fullmatch(spec["naming_pattern"], obj.get("name", "")): problems.append("mesh naming convention failed: " + obj.get("name", "<unnamed>"))
        if spec.get("node_naming_pattern"):
            for obj in stats.get("objects", []):
                if not re.fullmatch(spec["node_naming_pattern"], obj.get("name", "")): problems.append("node naming convention failed: " + obj.get("name", "<unnamed>"))
        if spec.get("materials_required") and not stats.get("materials"): problems.append("materials required but none found")
        if spec.get("uv_required") and any(not x.get("uv_sets") for x in stats.get("objects", []) if x.get("type") == "MESH"):
            problems.append("required UV set missing")
        if spec.get("rig_required") and not stats.get("armatures"):
            problems.append("required armature missing")
        if spec.get("animation_required") and not stats.get("actions"):
            problems.append("required animation action missing")
        actual = stats.get("export_settings", {})
        for key, expected in spec.get("export_settings", {}).items():
            if actual.get(key) != expected: problems.append(f"export {key} mismatch: expected {expected}, got {actual.get(key)}")
        if not stats: return result("art3d-dcc-inspection", "HUMAN_REQUIRED", "Blender adapter produced no scene statistics")
        return result("art3d-dcc-inspection", "FAIL" if problems else "PASS", *(problems or ["Blender scene statistics collected"]))


def check(artifact, ctx):
    kind = artifact.get("kind")
    if kind not in ("asset-3d", "art3d-asset"):
        return []
    spec = artifact.get("spec", {})
    errors = []
    file_path = spec.get("file", artifact.get("source_uri", ""))
    candidate = Path(ctx.repo) / file_path if file_path and not Path(file_path).is_absolute() else Path(file_path) if file_path else None
    if not candidate or not candidate.is_file():
        return [result("art3d-asset-file", "FAIL", "production asset file missing: " + str(file_path))]
    expected_hash = spec.get("hash", artifact.get("hash"))
    if expected_hash:
        import hashlib
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual.lower() != expected_hash.lower(): errors.append("asset SHA-256 does not match declared hash")
    fmt = spec.get("format", candidate.suffix.lstrip(".")).lower()
    suffix = candidate.suffix.lstrip(".").lower()
    if fmt != suffix: errors.append(f"declared format {fmt} does not match file extension {suffix}")
    required = spec.get("required_deliverables", [])
    for item in required:
        value = item.get("path") if isinstance(item, dict) else str(item)
        if not (Path(ctx.repo) / value).is_file(): errors.append("required deliverable missing: " + value)
    for category in ("collision", "textures"):
        for value in spec.get(category, []):
            if not (Path(ctx.repo) / value).is_file(): errors.append(f"required {category} deliverable missing: " + value)
    state = "PASS"
    dcc = None
    if suffix in ("gltf", "glb"):
        try: errors.extend(gltf_check(candidate, spec))
        except Exception as exc: errors.append("glTF parse/validation failed: " + str(exc))
    elif suffix in ("blend", "fbx", "obj"):
        dcc = blender_check(candidate, ctx, spec)
    else: errors.append("unsupported automatic inspection format: " + suffix)
    dcc_state = dcc.get("state") if dcc else None
    if dcc_state == "FAIL": errors.extend(dcc.get("reasons", []))
    production_state = "FAIL" if errors else (dcc_state if dcc_state in ("NOT_AVAILABLE", "HUMAN_REQUIRED", "FAIL") else "PASS")
    output = [result("art3d-asset-production", production_state, *errors)]
    if dcc: output.append(dcc)
    return output
