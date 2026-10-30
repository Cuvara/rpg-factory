#!/usr/bin/env python3
"""Create the registry-routed authoring layout and deterministic scenario seeds."""
import json
import sys
from pathlib import Path


def main():
    root, workspace, seed = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    for module in registry.get("modules", []):
        if module.get("repo") == "authoring":
            for route in module.get("paths", []):
                folder = workspace / route
                folder.mkdir(parents=True, exist_ok=True)
                if "approvals" not in Path(route).parts:
                    (folder / ".gitkeep").touch()
    def from_template(relative, artifact_id, title, spec=None):
        template = root / "templates" / relative
        raw = template.read_text(encoding="utf-8")
        value = json.loads(raw.split("---json\n", 1)[1].split("\n---", 1)[0])
        value["id"], value["title"], value["status"] = artifact_id, title, "draft"
        if spec is not None:
            value["spec"].update(spec)
        return value

    seeds = {
        "feature-spec": ("design/features/FD-inventory-001.artifact.json", from_template("design/feature-spec.md", "FD-inventory-001", "Inventory feature", {"summary": "Manage carried items", "requirements": [{"id": "REQ1", "description": "Show item slots"}]})),
        "approved-feature": ("design/features/FD-approved-001.artifact.json", from_template("design/feature-spec.md", "FD-approved-001", "Feature brief: craft a field tool", {"summary": "Craft a field tool", "requirements": [{"id": "REQ1", "description": "Show recipe and result"}]})),
        "field-tool-system": ("design/systems/GS-field-tool-001.artifact.json", from_template("design/gameplay-system.md", "GS-field-tool-001", "Field tool crafting system", {"core_loop": "Select a recipe, provide ingredients, and receive a crafted tool", "mechanics": ["Show recipe and result"]})),
        "design-event": ("design/features/GS-craft-complete-001.artifact.json", from_template("design/gameplay-system.md", "GS-craft-complete-001", "Craft completion gameplay system", {"system_type": "combat", "core_loop": "Crafting completes and presents a result", "mechanics": ["Emit a completion event"], "progression": ["TBD"], "combat_interaction": ["TBD"], "economy": {"currencies": ["TBD"], "sources": ["TBD"], "sinks": ["TBD"]}, "difficulty_balancing": ["TBD"], "meta_progression": ["TBD"]})),
        "asset-3d": ("art3d/assets/ARTD-workstation-001.artifact.json", from_template("art3d/asset-3d.md", "ARTD-workstation-001", "Workstation asset")),
    }
    if seed == "stale-pair":
        seeds["stale-upstream"] = ("design/features/GS-stale-001.artifact.json", from_template("design/gameplay-system.md", "GS-stale-001", "Changed crafting gameplay system", {"system_type": "combat", "core_loop": "Changed event"}))
        stale_vfx = from_template("vfx/vfx-spec.md", "VFX-craft-complete-001", "Crafting completion effect", {"purpose": "TBD: crafting completion effect", "triggers": ["GS-stale-001"]})
        stale_vfx["upstream"] = [{"id": "GS-stale-001", "rev": "0000000000000000000000000000000000000000"}]
        seeds["stale-downstream"] = ("vfx/specs/VFX-craft-complete-001.artifact.json", stale_vfx)
    if seed == "asset-3d-vfx":
        selected = ("asset-3d", "design-event")
    elif seed == "stale-pair":
        selected = ("stale-upstream", "stale-downstream")
    elif seed == "approved-feature":
        selected = ("approved-feature", "field-tool-system")
    else:
        selected = (seed,) if seed in seeds else ()
    for key in selected:
        rel, value = seeds[key]
        if value.get("status") == "approved":
            value["status"] = "draft"
        (workspace / rel).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
