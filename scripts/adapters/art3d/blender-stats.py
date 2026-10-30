"""Run inside Blender to emit stable scene statistics as JSON."""
import json
import sys
from pathlib import Path


def main():
    import bpy
    args = sys.argv[sys.argv.index("--") + 1:]
    output = args[0]
    source = args[1] if len(args) > 1 else ""
    if source.lower().endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=source)
    elif source.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=source)
    rows = []
    for obj in bpy.context.scene.objects:
        row = {"name": obj.name, "type": obj.type}
        if obj.type == "MESH":
            mesh = obj.data
            row.update({"triangles": sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons), "uv_sets": len(mesh.uv_layers), "materials": [m.name for m in mesh.materials if m]})
        rows.append(row)
    scene = bpy.context.scene
    export_settings = dict(scene.get("rpg_factory_export_settings", {}))
    sidecar = Path(source + ".rpgfactory.json") if source else None
    if sidecar and sidecar.is_file():
        with sidecar.open(encoding="utf-8") as stream:
            export_settings = json.load(stream).get("export_settings", {})
    materials = sorted({name for row in rows if row["type"] == "MESH" for name in row["materials"]})
    data = {"objects": rows, "meshes": sum(x["type"] == "MESH" for x in rows), "armatures": sum(x["type"] == "ARMATURE" for x in rows), "actions": sorted(a.name for a in bpy.data.actions), "materials": materials, "export_settings": export_settings}
    with open(output, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, sort_keys=True)


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
