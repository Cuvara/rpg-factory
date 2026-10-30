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
    seeds = {
        "feature-spec": ("design/features/FD-inventory-001.artifact.json", {"schema_version": 2, "id": "FD-inventory-001", "kind": "feature-spec", "domain": "design", "status": "approved", "title": "Inventory feature", "authors": [{"kind": "agent", "id": "dogfood-fixture"}], "sources": [], "upstream": [], "acceptance": [], "trace": [], "spec": {"summary": "Manage carried items", "requirements": ["show item slots"]}}),
        "approved-feature": ("design/features/FD-approved-001.artifact.json", {"schema_version": 2, "id": "FD-approved-001", "kind": "feature-spec", "domain": "design", "status": "approved", "title": "Approved crafting feature", "authors": [{"kind": "agent", "id": "dogfood-fixture"}], "sources": [], "upstream": [], "acceptance": [], "trace": [], "spec": {"summary": "Craft a field tool", "requirements": ["show recipe and result"]}}),
        "design-event": ("design/events/DE-craft-complete-001.artifact.json", {"schema_version": 2, "id": "DE-craft-complete-001", "kind": "design-event", "domain": "design", "status": "approved", "title": "Crafting complete", "authors": [{"kind": "agent", "id": "dogfood-fixture"}], "sources": [], "upstream": [], "acceptance": [], "trace": [], "spec": {"event": "crafting.complete"}}),
        "asset-3d": ("art3d/deliveries/A3-workstation-001.artifact.json", {"schema_version": 2, "id": "A3-workstation-001", "kind": "asset-3d", "domain": "art3d", "status": "approved", "title": "Workstation asset", "authors": [{"kind": "agent", "id": "dogfood-fixture"}], "sources": [], "upstream": [], "acceptance": [], "trace": [], "spec": {"format": "glb", "source": "fixture"}}),
    }
    if seed == "stale-pair":
        seeds["stale-upstream"] = ("design/events/DE-stale-001.artifact.json", {"schema_version": 2, "id": "DE-stale-001", "kind": "design-event", "domain": "design", "status": "approved", "title": "Changed crafting event", "authors": [{"kind": "agent", "id": "dogfood-fixture"}], "sources": [], "upstream": [], "acceptance": [], "trace": [], "spec": {"event": "crafting.complete", "revision_note": "changed"}})
        seeds["stale-downstream"] = ("vfx/specs/VFX-craft-complete-001.artifact.json", {"schema_version": 2, "id": "VFX-craft-complete-001", "kind": "vfx-spec", "domain": "vfx", "status": "draft", "title": "Crafting completion effect", "authors": [{"kind": "agent", "id": "dogfood-fixture"}], "sources": [], "upstream": [{"id": "DE-stale-001", "rev": "0000000000000000000000000000000000000000"}], "acceptance": [], "trace": [], "spec": {"duration": 1.0, "phases": [{"name": "burst", "duration": 1.0}], "platform_budgets": {"pc": {}, "console": {}, "mobile": {}, "web": {}}}})
    if seed in seeds:
        rel, value = seeds[seed]
        (workspace / rel).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
