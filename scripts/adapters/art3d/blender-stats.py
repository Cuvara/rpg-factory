"""Run inside Blender to emit stable scene statistics as JSON."""
import json
import sys


def main():
    import bpy
    args = sys.argv[sys.argv.index("--") + 1:]
    output = args[0]
    rows = []
    for obj in bpy.context.scene.objects:
        row = {"name": obj.name, "type": obj.type}
        if obj.type == "MESH":
            mesh = obj.data
            row.update({"triangles": sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons), "uv_sets": len(mesh.uv_layers), "materials": [m.name for m in mesh.materials if m]})
        rows.append(row)
    data = {"objects": rows, "meshes": sum(x["type"] == "MESH" for x in rows), "armatures": sum(x["type"] == "ARMATURE" for x in rows), "actions": sorted(a.name for a in bpy.data.actions), "materials": sorted(m.name for m in bpy.data.materials)}
    with open(output, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, sort_keys=True)


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
