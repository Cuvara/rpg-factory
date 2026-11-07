"""ComfyUI frontend (LiteGraph) workflow of a rendered API-format graph (stdlib only).

to_ui(graph, known, extra=None) -> the UI-format workflow {"last_node_id", "last_link_id", "nodes", "links", "groups",
  "config", "extra", "version"} of the same graph, so the ComfyUI frontend can open it as a canvas tab:
  - one node per API node: id (the API id as an int; API ids must be digits), type, title (_meta.title, else the type),
    pos and size (a column per link depth, left to right), order (execution order), inputs and outputs, and
    widgets_values in the node's input order (data/known-nodes.json lists inputs in the order ComfyUI declares them:
    required, then optional);
  - a widget input (STRING, COMBO, INT, FLOAT, BOOLEAN) is a value in widgets_values; when it is linked, it also gets
    an input socket {"name", "type", "widget": {"name"}, "link"} and its widgets_values slot holds "";
  - every other input (IMAGE, MASK, *) is a socket, linked or not ("link": null);
  - a node's ui.extra_widgets (known-nodes, e.g. the LoadImage upload button) follow its own widget values;
  - links are [link_id, from_node, from_slot, to_node, to_slot, type], to_slot indexing the target's inputs list.
  Converting it back (widgets_values in input order, then each linked socket as [str(from_node), from_slot], _meta
  title from the node title) gives the API graph again; tests/assetgen.test.sh checks that round trip.
Raises ValueError for a graph it cannot lay out (non-digit id, unknown node type, a widget value after a missing one).
"""

WIDGET_TYPES = {"STRING", "COMBO", "INT", "FLOAT", "BOOLEAN"}
DEFAULT_SIZE = [360, 300]
COLUMN, ROW, MARGIN = 440, 380, 60


def _is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int) and not isinstance(v[1], bool)


def _depths(graph):
    """Longest link distance from a source node, per node id."""
    memo = {}

    def depth(nid, seen):
        if nid in memo:
            return memo[nid]
        if nid in seen:
            raise ValueError("node %s: link cycle" % nid)
        ups = [v[0] for v in graph[nid]["inputs"].values() if _is_link(v) and v[0] in graph]
        memo[nid] = 1 + max((depth(u, seen | {nid}) for u in ups), default=-1)
        return memo[nid]
    return {nid: depth(nid, frozenset()) for nid in graph}


def to_ui(graph, known, extra=None):
    for nid, node in graph.items():
        if not str(nid).isdigit():
            raise ValueError("node id %r: the ComfyUI frontend needs numeric node ids" % nid)
        if node.get("class_type") not in known:
            raise ValueError("node %s: unknown node type %s (not in data/known-nodes.json)" % (nid, node.get("class_type")))
    depth = _depths(graph)
    ids = sorted(graph, key=int)
    order = sorted(ids, key=lambda n: (depth[n], int(n)))
    rows = {}
    nodes, links = {}, []
    for nid in order:
        node, spec = graph[nid], known[graph[nid]["class_type"]]
        row = rows.get(depth[nid], 0)
        rows[depth[nid]] = row + 1
        ui = spec.get("ui", {})
        nodes[nid] = {
            "id": int(nid), "type": node["class_type"], "title": (node.get("_meta") or {}).get("title") or node["class_type"],
            "pos": [MARGIN + COLUMN * depth[nid], MARGIN + ROW * row], "size": list(ui.get("size", DEFAULT_SIZE)),
            "flags": {}, "order": order.index(nid), "mode": 0, "inputs": [],
            "outputs": [{"name": t, "type": t, "links": [], "slot_index": i} for i, t in enumerate(spec.get("outputs", []))],
            "properties": {"Node name for S&R": node["class_type"]}, "widgets_values": [],
        }
    for nid in ids:
        node, spec, ui_node = graph[nid], known[graph[nid]["class_type"]], nodes[nid]
        missing = None
        for name, decl in spec["inputs"].items():
            value, widget = node["inputs"].get(name), decl.get("type") in WIDGET_TYPES
            linked = _is_link(value)
            if widget:
                if name not in node["inputs"]:
                    missing = missing or name
                    continue
                if missing:
                    raise ValueError("node %s (%s): widget %s is set after missing widget %s" % (nid, node["class_type"], name, missing))
                ui_node["widgets_values"].append("" if linked else value)
            if widget and not linked:
                continue
            socket = {"name": name, "type": decl.get("type"), "link": None}
            if widget:
                socket["widget"] = {"name": name}
            if linked:
                src, slot = value
                link_id = len(links) + 1
                link_type = known[graph[src]["class_type"]]["outputs"][slot]
                links.append([link_id, int(src), slot, int(nid), len(ui_node["inputs"]), link_type])
                nodes[src]["outputs"][slot]["links"].append(link_id)
                socket["link"] = link_id
            ui_node["inputs"].append(socket)
        if not missing:
            ui_node["widgets_values"] += list(spec.get("ui", {}).get("extra_widgets", []))
    return {"last_node_id": max(int(n) for n in ids), "last_link_id": len(links),
            "nodes": [nodes[n] for n in ids], "links": links, "groups": [], "config": {},
            "extra": dict({"ds": {"scale": 1.0, "offset": [0, 0]}}, **(extra or {})), "version": 0.4}
