"""Graph style lint of asset-gen workflows (stdlib only at import; uiworkflow is imported inside template_violations).

The workflow style guide in short (rule ids in brackets):
  [title]          every API node has a title of its own (not empty, not its class name).
  [group]          every API node is in exactly one group.
  [vocabulary]     group titles come from STAGES: Prompt, References, Generate, Post-process, Preview, Output.
  [order]          groups run left to right in STAGES order, no title twice (any subsequence of STAGES).
  [note]           every group holds at least one Note or MarkdownNote that says what the stage does.
  [prompt]         NineRouterImage.user_prompt is linked directly from a PrimitiveStringMultiline (the reviewed prompt);
                   in a template that node's value is the reviewed prompt placeholder {{prompt}} (no other text).
  [one-image-node] the graph has exactly one NineRouterImage.
  [save-suffix]    every SaveImage.filename_prefix carries an inline suffix after the run prefix
                   ("{{filename_prefix}}-icon"; in a run's workflow.ui.json "assetgen/<run-id>-icon").
  [save-output]    every SaveImage sits in the Output group; intermediates use PreviewImage (any group).
  [load-image]     a template's LoadImage.image is exactly one {{placeholder}}, never a static file name.
  [unknown]        (UI form) a node type that data/known-nodes.json does not list.
  [layout]         a shape the rules cannot read (uiworkflow.to_ui error, malformed nodes, links or groups).

Two forms are checked:
  template_violations(data, known) -> ["<rule>: <message>", ...] for a parsed (merged) template; groups and notes come
      from its ui block, the left-to-right order from uiworkflow.to_ui's layout. The prompt source's value must be
      the {{prompt}} placeholder: literal text or another placeholder ({{model}}) is a prompt violation naming the
      source and the NineRouterImage node.
  ui_violations(ui_workflow, known, prefix=None) -> the same for a ComfyUI frontend workflow (a run's workflow.ui.json);
      group membership is geometric (the node's rect, title bar included, inside the group's bounding). Every API
      node obeys the title and group rules, the style-lock reference nodes render adds too (render titles them and
      lays them into a References group); there is no exemption by file name. load-image is not checked (render
      fills it). The prompt source's value is the filled prompt and is not checked here: gen-run-provenance compares
      workflow.json prompts with prompt.md. save-suffix compares against the run prefix: the argument (callers pass
      the trusted assetgen/<run-id> of the run context: graph-lint --run, the gen-run-workflow-style check), else
      assetgen/<extra.assetgen.run_id>; with neither, each SaveImage is a save-suffix violation saying the run prefix
      is unknown (never a silent skip).
  template_row / ui_row wrap them as one validation row {"path", "check": CHECK, "state", "reasons"}. A legacy
      template (no ui block, or a ui without groups) is WARN, never FAIL.
Messages name a node as `node <id> (<class_type> "<title>")` and a group as `group "<title>"`. Nothing here reads
files: callers pass parsed data; `known` is the "nodes" object of data/known-nodes.json.
"""

import re

STAGES = ("Prompt", "References", "Generate", "Post-process", "Preview", "Output")
CHECK = "assetgen-graph-style"
NOTE_TYPES = ("Note", "MarkdownNote")

WIDGET_TYPES = {"STRING", "COMBO", "INT", "FLOAT", "BOOLEAN"}
NODE_TITLE = 30
IMAGE_NODE, PROMPT_NODE = "NineRouterImage", "PrimitiveStringMultiline"
RUN_PREFIX = "assetgen/"
PREFIX_PARAM = "{{filename_prefix}}"
PROMPT_PARAM = "{{prompt}}"
REVIEWED_PROMPT = re.compile(r"\{\{\s*prompt\s*\}\}")
ANY_PLACEHOLDER = re.compile(r"\{\{[^{}]*\}\}")
ONE_PLACEHOLDER = re.compile(r"\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}")
LEGACY = "legacy template without a ui block: the graph style is not enforced (see the staged templates)"


def _is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int) and not isinstance(v[1], bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sort_key(nid):
    return (0, int(nid), "") if nid.isdigit() else (1, 0, nid)


def _name(nodes, nid):
    node = nodes[nid]
    return 'node %s (%s "%s")' % (nid, node["type"], node["title"])


def _group(title):
    return 'group "%s"' % title


def _check(nodes, groups):
    """Shared rules over the normalized form.
    nodes: {id: {"type", "title", "inputs", "groups": [group titles] or None (no rect: cannot judge)}} (API nodes)
    groups: [{"title", "x", "notes": int}]."""
    out = []
    ids = sorted(nodes, key=_sort_key)
    for nid in ids:
        node = nodes[nid]
        if not node["title"].strip():
            out.append("title: %s has no title" % _name(nodes, nid))
        elif node["title"] == node["type"]:
            out.append("title: %s has its class name as title; name what it does" % _name(nodes, nid))
    for nid in ids:
        member = nodes[nid]["groups"]
        if member is None:
            continue
        if not member:
            out.append("group: %s is in no group" % _name(nodes, nid))
        elif len(member) > 1:
            out.append("group: %s is in %d groups: %s" % (_name(nodes, nid), len(member), ", ".join(_group(t) for t in member)))
    for g in groups:
        if g["title"] not in STAGES:
            out.append("vocabulary: %s is not one of %s" % (_group(g["title"]), ", ".join(STAGES)))
    seen, last = set(), None
    for g in sorted(groups, key=lambda g: g["x"]):
        title = g["title"]
        if title not in STAGES:
            continue
        if title in seen:
            out.append("order: %s appears more than once" % _group(title))
            continue
        seen.add(title)
        if last is not None and STAGES.index(title) < STAGES.index(last):
            out.append("order: %s is right of %s; groups run %s from left to right"
                       % (_group(title), _group(last), ", ".join(STAGES)))
        else:
            last = title
    for g in groups:
        if not g["notes"]:
            out.append("note: %s has no Note or MarkdownNote" % _group(g["title"]))
    image_nodes = [nid for nid in ids if nodes[nid]["type"] == IMAGE_NODE]
    for nid in image_nodes:
        value = nodes[nid]["inputs"].get("user_prompt")
        fix = "link it directly from a %s" % PROMPT_NODE
        if value is None:
            out.append("prompt: %s user_prompt is missing; %s" % (_name(nodes, nid), fix))
        elif not _is_link(value):
            out.append("prompt: %s user_prompt is a literal value, not a link; %s" % (_name(nodes, nid), fix))
        elif value[0] not in nodes:
            out.append("prompt: %s user_prompt links to node %s, which is not an API node of the graph; %s"
                       % (_name(nodes, nid), value[0], fix))
        elif nodes[value[0]]["type"] != PROMPT_NODE:
            out.append("prompt: %s user_prompt is linked from %s, not a %s; %s"
                       % (_name(nodes, nid), _name(nodes, value[0]), PROMPT_NODE, fix))
    if len(image_nodes) != 1:
        out.append("one-image-node: the graph has %d %s nodes%s; it needs exactly one"
                   % (len(image_nodes), IMAGE_NODE, " (%s)" % ", ".join(image_nodes) if image_nodes else ""))
    return out


def _save_output(nodes):
    return ["save-output: %s is not in %s; intermediates use PreviewImage, the saved image sits in Output"
            % (_name(nodes, nid), _group("Output"))
            for nid in sorted(nodes, key=_sort_key)
            if nodes[nid]["type"] == "SaveImage" and nodes[nid]["groups"] is not None
            and "Output" not in nodes[nid]["groups"]]


def template_violations(data, known):
    """Violations of a parsed (merged) template {"workflow", "ui"?, "output_node", ...}; never raises for data problems."""
    if not isinstance(data, dict):
        return ["layout: the template is not an object"]
    graph = data.get("workflow")
    if not isinstance(graph, dict) or not graph:
        return ["layout: workflow must be a non-empty object of nodes"]
    for nid, node in graph.items():
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str) or not isinstance(node.get("inputs"), dict):
            return ["layout: node %s needs class_type and an inputs object" % nid]
    ui = data.get("ui")
    import uiworkflow
    try:
        laid = uiworkflow.to_ui(graph, known, None, ui)
    except ValueError as exc:
        return ["layout: %s" % exc]
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        return ["layout: the workflow cannot be laid out (%s: %s)" % (type(exc).__name__, exc)]
    ui_groups = ui.get("groups", []) if isinstance(ui, dict) else []
    ui_notes = ui.get("notes", []) if isinstance(ui, dict) else []
    membership = {}
    for g in ui_groups:
        for nid in g["nodes"]:
            membership.setdefault(nid, []).append(g["title"])
    nodes = {}
    for nid, node in graph.items():
        if known[node["class_type"]].get("ui_only"):
            continue
        meta = node.get("_meta")
        title = meta.get("title") if isinstance(meta, dict) else None
        nodes[nid] = {"type": node["class_type"], "title": title if isinstance(title, str) else "",
                      "inputs": node["inputs"], "groups": membership.get(nid, [])}
    xs = {g["title"]: g["bounding"][0] for g in laid["groups"]}
    groups = [{"title": g["title"], "x": xs.get(g["title"], 0),
               "notes": sum(1 for n in ui_notes if n["group"] == g["title"])} for g in ui_groups]
    out = _check(nodes, groups)
    for nid in sorted(nodes, key=_sort_key):
        link = nodes[nid]["inputs"].get("user_prompt") if nodes[nid]["type"] == IMAGE_NODE else None
        if not (_is_link(link) and link[0] in nodes and nodes[link[0]]["type"] == PROMPT_NODE):
            continue  # a missing, literal or wrongly sourced user_prompt is already a prompt violation of _check
        value = nodes[link[0]]["inputs"].get("value")
        if not (isinstance(value, str) and REVIEWED_PROMPT.fullmatch(value)):
            out.append("prompt: %s user_prompt is linked from %s whose value %s is not the reviewed prompt placeholder "
                       "%s; render fills it from prompt.md" % (_name(nodes, nid), _name(nodes, link[0]), _show(value),
                                                              PROMPT_PARAM))
    for nid in sorted(nodes, key=_sort_key):
        if nodes[nid]["type"] != "SaveImage":
            continue
        value = nodes[nid]["inputs"].get("filename_prefix")
        rest = value[len(PREFIX_PARAM):] if isinstance(value, str) and value.startswith(PREFIX_PARAM) else None
        if not rest or ANY_PLACEHOLDER.search(rest):
            out.append('save-suffix: %s filename_prefix %s is not "%s" plus an inline suffix (e.g. "%s-icon")'
                       % (_name(nodes, nid), _show(value), PREFIX_PARAM, PREFIX_PARAM))
    out += _save_output(nodes)
    output = data.get("output_node")
    if isinstance(output, str) and output in nodes and nodes[output]["type"] != "SaveImage":
        out.append("save-output: output_node %s is not a SaveImage in %s" % (_name(nodes, output), _group("Output")))
    for nid in sorted(nodes, key=_sort_key):
        if nodes[nid]["type"] != "LoadImage":
            continue
        value = nodes[nid]["inputs"].get("image")
        if not isinstance(value, str) or not ONE_PLACEHOLDER.fullmatch(value):
            out.append("load-image: %s image %s is not one {{placeholder}}; a template never names a static file"
                       % (_name(nodes, nid), _show(value)))
    return out


def _show(value):
    if isinstance(value, str):
        return '"%s"' % value
    return "(%s)" % ("missing" if value is None else "a link" if _is_link(value) else type(value).__name__)


def _rect(node):
    pos, size = node.get("pos"), node.get("size")
    if not (isinstance(pos, list) and len(pos) >= 2 and isinstance(size, list) and len(size) >= 2
            and all(_is_num(v) for v in pos[:2] + size[:2])):
        return None
    return [pos[0], pos[1] - NODE_TITLE, size[0], size[1] + NODE_TITLE]


def _inside(rect, box):
    return (rect[0] >= box[0] and rect[1] >= box[1]
            and rect[0] + rect[2] <= box[0] + box[2] and rect[1] + rect[3] <= box[1] + box[3])


def ui_violations(ui_workflow, known, prefix=None):
    """Violations of a ComfyUI frontend workflow (workflow.ui.json); malformed shapes give layout violations."""
    if not isinstance(ui_workflow, dict) or not isinstance(ui_workflow.get("nodes"), list):
        return ["layout: a ComfyUI frontend workflow needs a nodes list"]
    out = []
    links = {}
    raw_links = ui_workflow.get("links", [])
    if not isinstance(raw_links, list):
        out.append("layout: links must be a list")
        raw_links = []
    for i, link in enumerate(raw_links):
        if isinstance(link, list) and len(link) >= 5 and all(_is_num(v) and int(v) == v for v in link[:5]):
            links[int(link[0])] = (str(int(link[1])), int(link[2]))
        else:
            out.append("layout: link entry %d is malformed (expected [id, from_node, from_slot, to_node, to_slot, type])" % i)
    boxes = []
    raw_groups = ui_workflow.get("groups", [])
    if not isinstance(raw_groups, list):
        out.append("layout: groups must be a list")
        raw_groups = []
    for i, g in enumerate(raw_groups):
        box = g.get("bounding") if isinstance(g, dict) else None
        if not isinstance(g, dict) or not isinstance(g.get("title"), str) or not (
                isinstance(box, list) and len(box) == 4 and all(_is_num(v) for v in box)):
            out.append("layout: group entry %d needs a title and a bounding [x, y, w, h]" % i)
            continue
        boxes.append({"title": g["title"], "box": box, "x": box[0], "notes": 0})
    nodes = {}
    for i, node in enumerate(ui_workflow["nodes"]):
        nid = node.get("id") if isinstance(node, dict) else None
        if isinstance(nid, bool) or not (isinstance(nid, int) or (isinstance(nid, str) and nid.isdigit())) \
                or not isinstance(node.get("type"), str):
            out.append("layout: node entry %d needs a numeric id and a type" % i)
            continue
        nid, ntype = str(int(nid)), node["type"]
        title = node.get("title") if isinstance(node.get("title"), str) else ""
        spec = known.get(ntype)
        if not isinstance(spec, dict):
            out.append('unknown: node %s (%s "%s") is not in data/known-nodes.json' % (nid, ntype, title))
            continue
        rect = _rect(node)
        if spec.get("ui_only"):
            if ntype in NOTE_TYPES and rect is not None:
                for b in boxes:
                    if _inside(rect, b["box"]):
                        b["notes"] += 1
            continue
        if nid in nodes:
            out.append("layout: node id %s is used twice" % nid)
            continue
        if rect is None:
            out.append('layout: node %s (%s "%s") needs pos [x, y] and size [w, h]' % (nid, ntype, title))
        widgets = node.get("widgets_values", [])
        if not isinstance(widgets, list):
            out.append('layout: node %s (%s "%s") widgets_values must be a list' % (nid, ntype, title))
            widgets = []
        inputs, k = {}, 0
        for name, decl in spec.get("inputs", {}).items():
            if decl.get("type") in WIDGET_TYPES:
                if k < len(widgets):
                    inputs[name] = widgets[k]
                k += 1
        sockets = node.get("inputs", [])
        for socket in sockets if isinstance(sockets, list) else []:
            if not isinstance(socket, dict) or socket.get("link") is None:
                continue
            link = socket["link"]
            if not _is_num(link) or int(link) not in links or not isinstance(socket.get("name"), str):
                out.append('layout: node %s (%s "%s") input %s: link %r is not in the links table'
                           % (nid, ntype, title, socket.get("name"), link))
                continue
            src, slot = links[int(link)]
            inputs[socket["name"]] = [src, slot]
        member = None if rect is None else [b["title"] for b in boxes if _inside(rect, b["box"])]
        nodes[nid] = {"type": ntype, "title": title, "inputs": inputs, "groups": member}
    out += _check(nodes, boxes)
    if prefix is None:
        extra = ui_workflow.get("extra")
        meta = extra.get("assetgen") if isinstance(extra, dict) else None
        run_id = meta.get("run_id") if isinstance(meta, dict) else None
        if isinstance(run_id, str) and run_id:
            prefix = RUN_PREFIX + run_id
    for nid in sorted(nodes, key=_sort_key):
        if nodes[nid]["type"] != "SaveImage":
            continue
        value = nodes[nid]["inputs"].get("filename_prefix")
        if prefix is None:
            out.append("save-suffix: %s filename_prefix %s cannot be checked: the run prefix is unknown (no "
                       "extra.assetgen.run_id; pass the run)" % (_name(nodes, nid), _show(value)))
        elif not (isinstance(value, str) and value.startswith(prefix) and len(value) > len(prefix)):
            out.append('save-suffix: %s filename_prefix %s is not "%s" plus an inline suffix (e.g. "%s-icon")'
                       % (_name(nodes, nid), _show(value), prefix, prefix))
    out += _save_output(nodes)
    return out


def template_row(data, known, shown):
    """One row for a template: legacy (no ui block or no groups) WARN, else FAIL on violations, PASS without."""
    violations = template_violations(data, known)
    ui = data.get("ui") if isinstance(data, dict) else None
    if ui is None or (isinstance(ui, dict) and not ui.get("groups")):
        return {"path": shown, "check": CHECK, "state": "WARN", "reasons": [LEGACY] + violations}
    return {"path": shown, "check": CHECK, "state": "FAIL" if violations else "PASS", "reasons": violations}


def ui_row(ui_workflow, known, shown, prefix=None):
    """One row for a ComfyUI frontend workflow: FAIL on violations, PASS without."""
    violations = ui_violations(ui_workflow, known, prefix)
    return {"path": shown, "check": CHECK, "state": "FAIL" if violations else "PASS", "reasons": violations}
