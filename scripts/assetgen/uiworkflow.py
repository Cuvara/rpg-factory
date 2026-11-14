"""ComfyUI frontend (LiteGraph) workflow of a rendered API-format graph (stdlib only).

to_ui(graph, known, extra=None, ui=None) -> the UI-format workflow {"last_node_id", "last_link_id", "nodes", "links", "groups",
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
An optional template ui block supplies groups, notes (ui_only Note nodes), node colors and row hints; it never
  changes the API graph or workflow.json. Groups are laid out by stage with bounds around members and notes.
  A stage fed by a link that skips stages stays on its source's row and skipped stages move down; x never changes
  (the [order] rule sorts groups by x). Lanes are per stage: links inside a stage or into a later column of a
  multi-column stage are not routed.
Raises ValueError for invalid UI metadata or a graph it cannot lay out (non-digit id, unknown node type, a widget value after a missing one).
"""

import re
from collections import deque

WIDGET_TYPES = {"STRING", "COMBO", "INT", "FLOAT", "BOOLEAN"}
DEFAULT_SIZE = [360, 300]
COLUMN, ROW, MARGIN = 440, 380, 60
COLUMN_GAP, PAD, NODE_TITLE, GROUP_TITLE = 80, 30, 30, 40
PALETTE = {
    "red": ("#322", "#533", "#A88"), "brown": ("#332922", "#593930", "#b06634"),
    "green": ("#232", "#353", "#8A8"), "blue": ("#223", "#335", "#88A"),
    "pale_blue": ("#2a363b", "#3f5159", "#3f789e"), "cyan": ("#233", "#355", "#8AA"),
    "purple": ("#323", "#535", "#a1309b"), "yellow": ("#432", "#653", "#b58b2a"),
    "black": ("#222", "#000", "#444"),
}
HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


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


def to_ui(graph, known, extra=None, ui=None):
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
        node_ui = spec.get("ui", {})
        nodes[nid] = {
            "id": int(nid), "type": node["class_type"], "title": (node.get("_meta") or {}).get("title") or node["class_type"],
            "pos": [MARGIN + COLUMN * depth[nid], MARGIN + ROW * row], "size": list(node_ui.get("size", DEFAULT_SIZE)),
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
    groups, notes = _layout(graph, known, nodes, depth, ui) if ui is not None else ([], [])
    return {"last_node_id": max([int(n) for n in ids] + [n["id"] for n in notes]), "last_link_id": len(links),
            "nodes": [nodes[n] for n in ids] + notes, "links": links, "groups": groups, "config": {},
            "extra": dict({"ds": {"scale": 1.0, "offset": [0, 0]}}, **(extra or {})), "version": 0.4}


def _hex(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _layout(graph, known, nodes, depth, ui):
    """Validate template UI metadata and lay out groups without changing graph data."""
    if not isinstance(ui, dict):
        raise ValueError("ui must be an object")
    unknown = set(ui) - {"groups", "notes", "colors", "rows"}
    if unknown:
        raise ValueError("ui: unknown key %s" % sorted(unknown, key=str)[0])
    groups, notes = ui.get("groups", []), ui.get("notes", [])
    colors, hints = ui.get("colors", {}), ui.get("rows", {})
    if not isinstance(groups, list) or not isinstance(notes, list):
        raise ValueError("ui groups and notes must be lists")
    if not isinstance(colors, dict) or not isinstance(hints, dict):
        raise ValueError("ui colors and rows must be objects")
    membership, titles, group_colors = {}, {}, []
    for i, group in enumerate(groups):
        if not isinstance(group, dict) or set(group) - {"title", "color", "nodes"}:
            raise ValueError("ui group must contain title, nodes and optional color")
        title, members = group.get("title"), group.get("nodes")
        if not isinstance(title, str) or not title.strip() or title in titles:
            raise ValueError("ui group: empty or duplicate title %r" % title)
        titles[title] = i
        if not isinstance(members, list) or not members:
            raise ValueError("ui group %s: nodes must be a non-empty list" % title)
        for nid in members:
            if not isinstance(nid, str) or nid not in graph:
                raise ValueError("ui group %s: unknown node id %r" % (title, nid))
            if nid in membership:
                raise ValueError("ui node %s in two groups or repeated" % nid)
            membership[nid] = i
        color = group.get("color", "#3f789e")
        if isinstance(color, str) and color in PALETTE:
            color = PALETTE[color][2]
        if not _hex(color):
            raise ValueError("ui group %s: bad color %r" % (title, color))
        group_colors.append(color)
    for nid, color in colors.items():
        if not isinstance(nid, str) or nid not in graph:
            raise ValueError("ui colors: unknown node id %r" % nid)
        if isinstance(color, str) and color in PALETTE:
            color = dict(zip(("color", "bgcolor"), PALETTE[color][:2]))
        if not isinstance(color, dict) or set(color) != {"color", "bgcolor"} or not all(_hex(v) for v in color.values()):
            raise ValueError("ui node %s: bad color" % nid)
        nodes[nid].update(color)
    for nid, hint in hints.items():
        if not isinstance(nid, str) or nid not in graph:
            raise ValueError("ui rows: unknown node id %r" % nid)
        if isinstance(hint, bool) or not isinstance(hint, int) or hint < 0:
            raise ValueError("ui node %s: bad row" % nid)
    grouped_notes = [[] for _ in groups]
    note_nodes = []
    next_id = max((int(n) for n in graph), default=0)
    for note in notes:
        if not isinstance(note, dict) or set(note) != {"text", "group"}:
            raise ValueError("ui note must contain text and group")
        title, value = note["group"], note["text"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("ui note: empty text")
        if not isinstance(title, str) or title not in titles:
            raise ValueError("ui note: unknown group %r" % title)
        if "Note" not in known:
            raise ValueError("ui note: unknown node type Note")
        next_id += 1
        node = {"id": next_id, "type": "Note", "title": "Note", "pos": [0, 0],
                "size": list(known["Note"].get("ui", {}).get("size", DEFAULT_SIZE)),
                "flags": {}, "order": len(nodes) + len(note_nodes), "mode": 0, "inputs": [], "outputs": [],
                "properties": {}, "widgets_values": [value], "color": "#432", "bgcolor": "#653"}
        note_nodes.append(node)
        grouped_notes[titles[title]].append(node)
    if not groups:
        return [], note_nodes

    upstream = {nid: [v[0] for v in node["inputs"].values() if _is_link(v) and v[0] in graph]
                for nid, node in graph.items()}
    downstream = {nid: [] for nid in graph}
    for nid, producers in upstream.items():
        for producer in producers:
            downstream[producer].append(nid)

    def nearest(start, edges, choose):
        seen, queue = {start}, deque([(start, 0)])
        found, distance = [], None
        while queue:
            nid, d = queue.popleft()
            if distance is not None and d > distance:
                break
            if nid in membership:
                found.append(membership[nid])
                distance = d
            else:
                for neighbor in edges[nid]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        queue.append((neighbor, d + 1))
        return choose(found) if found else None

    stages = {}
    for nid in graph:
        stage = membership.get(nid)
        if stage is None:
            stage = nearest(nid, downstream, min)
        if stage is None:
            stage = nearest(nid, upstream, max)
        stages[nid] = stage if stage is not None else 0
    columns = {}
    for nid in graph:
        columns.setdefault((stages[nid], depth[nid]), []).append(nid)
    leftmost = {i: min(depth[n] for n in group["nodes"]) for i, group in enumerate(groups)}
    x, previous_stage = MARGIN + PAD, None
    stage_bottom = {}
    for (stage, level), members in sorted(columns.items()):
        if previous_stage is not None and stage != previous_stage:
            x += 2 * PAD
        previous_stage = stage
        group_members = [n for n in members if n in membership]
        group_members.sort(key=lambda n: (0, hints[n], int(n)) if n in hints else (1, 0, int(n)))
        column_notes = grouped_notes[stage] if stage < len(groups) and leftmost[stage] == level else []
        width = max(nodes[n]["size"][0] for n in members)
        width = max([width] + [n["size"][0] for n in column_notes])
        y = MARGIN + PAD + GROUP_TITLE + NODE_TITLE
        for node in [nodes[n] for n in group_members] + column_notes:
            node["pos"] = [x, y]
            y += node["size"][1] + NODE_TITLE + COLUMN_GAP
        stage_bottom[stage] = max(stage_bottom.get(stage, 0), y)
        for nid in members:
            if nid not in membership:
                nodes[nid]["pos"][0] = x
        x += width + COLUMN_GAP
    for (stage, level), members in sorted(columns.items()):
        y = stage_bottom[stage] + PAD + GROUP_TITLE
        for nid in sorted((n for n in members if n not in membership),
                          key=lambda n: (0, hints[n], int(n)) if n in hints else (1, 0, int(n))):
            nodes[nid]["pos"][1] = y
            y += nodes[nid]["size"][1] + NODE_TITLE + COLUMN_GAP

    stage_order = sorted({stage for stage, _ in columns})
    pos = {stage: i for i, stage in enumerate(stage_order)}
    stage_links = [(stages[src], stages[dst], src) for dst, producers in upstream.items() for src in producers
                   if stages[src] != stages[dst] and pos[stages[src]] < pos[stages[dst]]]
    skips = [(a, b, src) for a, b, src in stage_links if pos[b] - pos[a] > 1]
    lanes = {}
    for stage in stage_order:
        forbidden = {lanes[a] for a, b, _ in skips if pos[a] < pos[stage] < pos[b]}
        incoming_skips = sorted(((a, src) for a, b, src in skips if b == stage),
                                key=lambda link: (pos[link[0]], int(link[1])))
        if incoming_skips:
            lanes[stage] = lanes[incoming_skips[0][0]]
        else:
            incoming = [(a, src) for a, b, src in stage_links if b == stage]
            preferred = lanes[max(incoming, key=lambda link: (pos[link[0]], -int(link[1])))[0]] if incoming else 0
            lane = preferred
            if lane in forbidden:
                lane = 0
                while lane in forbidden:
                    lane += 1
            lanes[stage] = lane

    lane_contents = {}
    for nid, stage in stages.items():
        lane_contents.setdefault(lanes[stage], []).append(nodes[nid])
    for stage, stage_notes in enumerate(grouped_notes):
        if stage in lanes:
            lane_contents[lanes[stage]].extend(stage_notes)
    bottom = None
    for lane in sorted(lane_contents):
        contents = lane_contents[lane]
        offset = 0 if bottom is None else bottom + COLUMN_GAP - MARGIN
        for node in contents:
            node["pos"][1] += offset
        bottom = max(node["pos"][1] + node["size"][1] + PAD for node in contents)
    result = []
    for i, group in enumerate(groups):
        contents = [nodes[n] for n in group["nodes"]] + grouped_notes[i]
        x1 = min(n["pos"][0] for n in contents) - PAD
        y1 = min(n["pos"][1] - NODE_TITLE for n in contents) - PAD - GROUP_TITLE
        x2 = max(n["pos"][0] + n["size"][0] for n in contents) + PAD
        y2 = max(n["pos"][1] + n["size"][1] for n in contents) + PAD
        result.append({"id": i + 1, "title": group["title"], "bounding": [x1, y1, x2 - x1, y2 - y1],
                       "color": group_colors[i], "font_size": 24, "flags": {}})
    return result, note_nodes
