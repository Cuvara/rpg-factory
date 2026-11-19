#!/usr/bin/env python3
"""Stdlib UI -> API converter (as comfy-9router run_sample.py, object_info from data/known-nodes.json): widgets_values in
input order, then each linked socket; the result must equal workflow.json.

Usage: ui2api.py KNOWN-NODES.json WORKFLOW.ui.json WORKFLOW.json  (prints ok; an AssertionError or ValueError otherwise)
convert() is the same check for callers that run it in-process (tests/fixtures/assetgen/loops.py).
"""
import json
import sys

WIDGETS = ("STRING", "INT", "FLOAT", "BOOLEAN", "COMBO")


def convert(known_path, ui_path, api_path):
    known = json.load(open(known_path, encoding="utf-8"))["nodes"]
    ui = json.load(open(ui_path, encoding="utf-8"))
    api = json.load(open(api_path, encoding="utf-8"))
    by_id = {n["id"]: n for n in ui["nodes"]}
    links = {l[0]: l for l in ui["links"]}
    assert len(links) == len(ui["links"]) and ui["last_link_id"] == max(links, default=0) and ui["last_node_id"] == max(by_id)
    assert sorted(n["order"] for n in ui["nodes"]) == list(range(len(ui["nodes"])))
    graph = {}
    for node in ui["nodes"]:
        spec = known[node["type"]]
        assert len(node["pos"]) == 2 and len(node["size"]) == 2 and node["title"]
        if spec.get("ui_only"):
            continue
        values, inputs = iter(node["widgets_values"]), {}
        for name, decl in spec["inputs"].items():
            if decl["type"] in WIDGETS:
                try:
                    inputs[name] = next(values)
                except StopIteration:
                    if decl.get("required"):
                        raise ValueError("missing widget %s.%s" % (node["type"], name))
        for i, socket in enumerate(node.get("inputs", [])):
            if socket.get("link") is None:
                continue
            link = links[socket["link"]]
            assert link[3] == node["id"] and link[4] == i, link
            src = by_id[link[1]]
            assert src["outputs"][link[2]]["type"] == link[5] and link[0] in src["outputs"][link[2]]["links"], link
            inputs[socket["name"]] = [str(link[1]), link[2]]
        graph[str(node["id"])] = {"class_type": node["type"], "inputs": inputs, "_meta": {"title": node["title"]}}
    for nid in api:
        api[nid].setdefault("_meta", {"title": api[nid]["class_type"]})
    assert graph == api, json.dumps({"ui->api": graph, "workflow.json": api}, indent=1, sort_keys=True)
    return "ok"


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2], sys.argv[3]))
