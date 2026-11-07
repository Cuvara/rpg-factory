"""Offline lint of asset-gen data and rendered workflows.

Checks: schema id and required fields per kind, typed template params, {{placeholder}} use, node types, input
names, required inputs, link targets and types, combo values against data/known-nodes.json (a snapshot; the live
check is comfy-mcp validate_workflow), extends targets, and that no file carries a URL, host address or credential.
Every file gets one result {path, check: "assetgen-lint", state: PASS|WARN|FAIL, reasons}.
"""
import json
import os
import re

import layers
import runfiles

KNOWN = os.path.join(layers.HERE, "data", "known-nodes.json")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
PARAM_TYPES = {"string", "int", "number", "bool", "enum"}
# a URL scheme, an IPv4 address, a local host name, a credential-shaped key or value
FORBIDDEN = [
    (re.compile(r"\b[a-z][a-z0-9+.-]*:/{2}", re.I), "URL"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "IP address"),
    (re.compile(r"\blocalhost\b", re.I), "host name"),
    (re.compile(r"\"(api[_-]?key|authorization|access[_-]?token|secret|password|base_url|headers?)\"\s*:", re.I), "credential or endpoint key"),
    (re.compile(r"\bBearer\s+\S", re.I), "bearer credential"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"), "API key value"),
]


def known_nodes():
    with open(KNOWN, encoding="utf-8") as f:
        return json.load(f)["nodes"]


def domains():
    try:
        with open(os.path.join(layers.PLUGIN_ROOT, "registry.json"), encoding="utf-8") as f:
            return set(json.load(f).get("domains", {}))
    except (OSError, ValueError):
        return None


def secrets(text):
    return ["contains a %s (%s); templates must not carry endpoints or credentials" % (what, m.group(0)[:40])
            for rx, what in FORBIDDEN for m in [rx.search(text)] if m]


def is_link(v):
    """[node_id, output_index] with an int index (bool is not an index); the bounds are checked against the node."""
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int) and not isinstance(v[1], bool)


def check_graph(graph, params=None):
    """(errors, warnings) for an API-format graph. params: template param declarations (template mode, where
    {{placeholders}} are allowed); None = a rendered workflow (no placeholder may remain)."""
    nodes, errs, warns = known_nodes(), [], []
    if not isinstance(graph, dict) or not graph:
        return ["workflow must be a non-empty object of nodes"], []
    for nid, node in graph.items():
        if not nid.isdigit():
            errs.append("node id %r: must be digits (workflow.ui.json, the ComfyUI frontend workflow, needs numeric ids)" % nid)
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str) or not isinstance(node.get("inputs"), dict):
            errs.append("node %s: needs class_type and an inputs object" % nid)
            continue
        ctype, spec = node["class_type"], nodes.get(node["class_type"])
        if spec is None:
            errs.append("node %s: unknown node type %s (not in data/known-nodes.json; live check: comfy-mcp validate_workflow)" % (nid, ctype))
            continue
        for name, decl in spec["inputs"].items():
            if decl.get("required") and name not in node["inputs"]:
                errs.append("node %s (%s): required input %s missing" % (nid, ctype, name))
        for name, value in node["inputs"].items():
            decl = spec["inputs"].get(name)
            if decl is None:
                errs.append("node %s (%s): unknown input %s" % (nid, ctype, name))
                continue
            if is_link(value):
                src = graph.get(value[0])
                src_spec = nodes.get(src.get("class_type")) if isinstance(src, dict) else None
                if src is None:
                    errs.append("node %s.%s: link to missing node %s" % (nid, name, value[0]))
                elif src_spec is not None:
                    outs = src_spec["outputs"]
                    if not 0 <= value[1] < len(outs):
                        errs.append("node %s.%s: node %s has no output %d" % (nid, name, value[0], value[1]))
                    elif decl["type"] not in ("*", outs[value[1]]):
                        errs.append("node %s.%s: expects %s, linked output is %s" % (nid, name, decl["type"], outs[value[1]]))
                continue
            if decl["type"] in ("IMAGE", "MASK"):
                errs.append("node %s.%s: %s input must be a link [node_id, output_index]" % (nid, name, decl["type"]))
                continue
            text = value if isinstance(value, str) else None
            names = PLACEHOLDER.findall(text) if text else []
            if names:
                if params is None:
                    errs.append("node %s.%s: unfilled placeholder %s" % (nid, name, ", ".join(names)))
                    continue
                for p in names:
                    pdecl = params.get(p) if isinstance(params.get(p), dict) else {}
                    if p not in params:
                        errs.append("node %s.%s: placeholder {{%s}} is not a declared param" % (nid, name, p))
                    elif decl["type"] == "COMBO" and text.strip() == "{{%s}}" % p:
                        opts = pdecl.get("options")
                        bad = [o for o in (opts if isinstance(opts, list) else []) if o not in decl["options"]]
                        if pdecl.get("type") != "enum" or not isinstance(opts, list) or bad:
                            errs.append("param %s feeds combo %s.%s: must be an enum within %s" % (p, ctype, name, decl["options"]))
                    note = spec.get("warn_values", {}).get(name, {}).get(str(pdecl.get("default")))
                    if note:
                        warns.append("param %s default %s is %s" % (p, pdecl.get("default"), note))
                continue
            if decl["type"] == "COMBO" and value not in decl["options"]:
                errs.append("node %s.%s: %r is not one of %s" % (nid, name, value, decl["options"]))
            note = spec.get("warn_values", {}).get(name, {}).get(value) if isinstance(value, str) else None
            if note:
                warns.append("node %s.%s: %s is %s" % (nid, name, value, note))
    return errs, warns


def template_errors(data, ident):
    errs, warns = [], []
    params = data.get("params")
    if not isinstance(params, dict) or "prompt" not in params:
        return ["template %s: params must be an object declaring at least prompt" % ident], []
    for name, d in params.items():
        if not isinstance(d, dict) or d.get("type") not in PARAM_TYPES:
            errs.append("param %s: type must be one of %s" % (name, sorted(PARAM_TYPES)))
            continue
        if not d.get("required") and "default" not in d:
            errs.append("param %s: needs a default or required: true" % name)
        opts = d.get("options")
        if d["type"] == "enum" and (not isinstance(opts, list) or not opts or ("default" in d and d["default"] not in opts)):
            errs.append("param %s: enum needs options containing its default" % name)
    graph = data.get("workflow")
    e, w = check_graph(graph, params)
    errs += e
    warns += w
    used = set(PLACEHOLDER.findall(json.dumps(graph)))
    warns += ["param %s is declared but never used in the workflow" % n for n in params if n not in used]
    out = data.get("output_node")
    if not isinstance(graph, dict) or not isinstance(out, str) or out not in graph:
        errs.append("output_node %r is not a node of the workflow" % out)
    elif not isinstance(graph[out], dict) or not known_nodes().get(graph[out].get("class_type"), {}).get("output_node"):
        errs.append("output_node %s is not an output node (SaveImage)" % out)
    return errs, warns


def purpose_errors(data, ident, authoring):
    errs = []
    doms = domains()
    if doms is not None and (not isinstance(data.get("handoff_domain"), str) or data.get("handoff_domain") not in doms):
        errs.append("handoff_domain %r is not a registry domain (%s)" % (data.get("handoff_domain"), ", ".join(sorted(doms))))
    for key in ("prompt_rubric", "image_rubric"):
        v = data.get(key)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
            errs.append("%s must be a non-empty list of strings" % key)
    guide = data.get("prompt", {})
    if not isinstance(guide, dict):
        errs.append("prompt must be an object")
    else:
        for key in ("guidance", "must_include", "avoid"):
            v = guide.get(key, [])
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errs.append("prompt.%s must be a list of strings" % key)
    params = data.get("params", {})
    if not isinstance(params, dict):
        errs.append("params must be an object")
        params = {}
    for key in ("default_template", "default_style"):
        if data.get(key) is not None and not isinstance(data.get(key), str):
            errs.append("%s must be a string" % key)
    try:
        tmpl_id = data.get("default_template") if isinstance(data.get("default_template"), str) else ""
        tmpl = layers.load("template", tmpl_id, authoring)
        declared = tmpl["data"].get("params", {})
        declared = declared if isinstance(declared, dict) else {}
        for name, value in params.items():
            d = declared.get(name)
            if not isinstance(d, dict):
                errs.append("params.%s is not declared by template %s" % (name, tmpl["id"]))
            elif d.get("type") == "enum" and value not in (d.get("options") if isinstance(d.get("options"), list) else []):
                errs.append("params.%s=%r is not one of %s" % (name, value, d.get("options")))
    except layers.SpecError as exc:
        errs.append("default_template: %s" % exc)
    if isinstance(data.get("default_style"), str) and data["default_style"]:
        try:
            layers.load("style", data["default_style"], authoring)
        except layers.SpecError as exc:
            errs.append("default_style: %s" % exc)
    return errs + runfiles.qa_errors(data.get("qa"))


def style_errors(data):
    errs = [k + " must be a string" for k in ("prefix", "suffix") if not isinstance(data.get(k, ""), str)]
    if not isinstance(data.get("avoid", []), list):
        errs.append("avoid must be a list")
    if not isinstance(data.get("params", {}), dict):
        errs.append("params must be an object")
    return errs


def classify(path, authoring):
    """(kind, id) when path is a layer file, else (None, None)."""
    full = os.path.abspath(path)
    for kind, spec in layers.KINDS.items():
        dirs = [os.path.join(layers.CORE_DIR, spec["core"])]
        if authoring:
            dirs.append(os.path.join(layers.game_dir(authoring), spec["game"]))
        if any(os.path.normcase(os.path.dirname(full)) == os.path.normcase(os.path.abspath(d)) for d in dirs):
            return kind, os.path.basename(full)[:-5]
    return None, None


def display(path, authoring):
    full = os.path.abspath(path)
    for prefix, root in (("game:", os.path.abspath(authoring) if authoring else None), ("core:", layers.PLUGIN_ROOT)):
        if root and os.path.normcase(full).startswith(os.path.normcase(root) + os.sep):
            return prefix + os.path.relpath(full, root).replace(os.sep, "/")
    return path.replace(os.sep, "/")


def lint_data(path, raw, authoring):
    """(errors, warnings) of one parsed file; nested types are validated before use."""
    errs, warns = [], []
    kind, ident = classify(path, authoring)
    if kind:
        try:
            entry = layers.load(kind, ident, authoring)
        except layers.SpecError as exc:
            return [str(exc)], []
        data = entry["data"]
        if "extends" in raw and entry["layer"] != "game-extends":
            errs.append("extends is only allowed in the game layer")
        if data.get("schema") != layers.KINDS[kind]["schema"]:
            errs.append("schema must be %s" % layers.KINDS[kind]["schema"])
        if not isinstance(data.get("title"), str) or not data.get("title"):
            errs.append("title is required")
        if kind == "template":
            e, w = template_errors(data, ident)
            errs, warns = errs + e, warns + w
        elif kind == "purpose":
            errs += purpose_errors(data, ident, authoring)
        else:
            errs += style_errors(data)
    elif isinstance(raw, dict) and raw.get("schema") == layers.KINDS["template"]["schema"]:
        errs, warns = template_errors(raw, os.path.basename(path))
    elif isinstance(raw, dict) and raw and all(isinstance(n, dict) and "class_type" in n for n in raw.values()):
        errs, warns = check_graph(raw, None)
    else:
        errs.append("not an asset-gen purpose, style, template or rendered workflow")
    return errs, warns


def lint_file(path, authoring=None):
    errs, warns = [], []
    shown = display(path, authoring)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        raw = json.loads(text)
    except (OSError, ValueError) as exc:
        return {"path": shown, "check": "assetgen-lint", "state": "FAIL", "reasons": ["unreadable JSON: %s" % exc]}
    errs += secrets(text)
    try:
        e, w = lint_data(path, raw, authoring)
        errs, warns = errs + e, warns + w
    except (AttributeError, TypeError, KeyError, IndexError, ValueError) as exc:  # a shape no rule names: FAIL, no traceback
        errs.append("malformed data (%s: %s)" % (type(exc).__name__, exc))
    state = "FAIL" if errs else ("WARN" if warns else "PASS")
    return {"path": shown, "check": "assetgen-lint", "state": state, "reasons": errs + warns}


def default_paths(authoring=None):
    out = []
    for kind in layers.KINDS:
        files = layers.layer_files(kind, authoring)
        out += list(files["core"].values()) + list(files["game"].values())
    return out
