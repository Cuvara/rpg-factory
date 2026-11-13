"""Offline lint of asset-gen data and rendered workflows.

Checks: schema id and required fields per kind, typed template params, {{placeholder}} use, node types (a ui_only
node such as Note is never part of workflow), input names, required inputs, link targets and types, combo values
against data/known-nodes.json (a snapshot; the live check is comfy-mcp validate_workflow), extends targets, and that
no file carries a URL, host address or credential.
Purpose constraints are checked against data/precedence.json. A core file is linted as core data only (no game
layer merged in), so a bad game value is reported on the game file that holds it.
Style lock (stylelock.py): style version, status and structured fields, purpose default_family/dimensions/
max_references, <authoring>/assetgen/project.json (styles it names, version match), anchors (structure, image file
and hash, an active anchor needs a person's approval and an approved source gen-run) and rejections. With an
authoring repo and no project.json, lint adds a WARN row for assetgen/project.json (style lock off). An active game
style without a usable structured style field (palette.colors, tone, canvas, outline.edge_darkness; absent, empty or
malformed per consistency.field_states, the parsing the style checks use) is a WARN: no style-* QA row can grade.
Every file gets one result {path, check: "assetgen-lint", state: PASS|WARN|FAIL, reasons}.
lint_rows adds one {path, check: "assetgen-graph-style", ...} row per template (a core or game layer template, merged
as lint_data merges it, or a standalone file with the template schema): the workflow style guide (graphstyle.py:
titles, one stage group per node, the group vocabulary and order, a Note per group, the reviewed prompt linked
directly into the one NineRouterImage, SaveImage only in Output with a filename suffix, no static LoadImage file).
A legacy template without a ui block is a WARN, never a FAIL. An unreadable file or a layer load error gets no extra
row (its assetgen-lint row already FAILs).
Local models (UNTESTED on RTX 5060: the block is a declaration compared with planning thresholds, never a measured
number): a template's optional requires block {profile, peak_vram_gb, ram_gb, packs, models[{kind, name, size_gb}]}
is checked against data/hardware.json (profile id, the profile's VRAM and RAM ceilings and pack ids, model kinds, a
model name that is a file name; no link, path or credential). A node of a known-nodes pack needs its pack id in
requires.packs, and a local_model_nodes or pack node needs the block and a profile with a GPU (hardware.json
requires.gpu true; api-only has none and stays valid for an API-only graph). No requires and no such node: nothing
changes.
"""
import json
import math
import os
import re

import consistency
import graphstyle
import layers
import runfiles
import stylelock

KNOWN = os.path.join(layers.HERE, "data", "known-nodes.json")
PLACEHOLDER = runfiles.PLACEHOLDER
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
HARDWARE = os.path.join(layers.HERE, "data", "hardware.json")
REQUIRES_KEYS = ("profile", "peak_vram_gb", "ram_gb", "packs", "models")
MODEL_KEYS = ("kind", "name", "size_gb")
EXTRA_MODEL_KINDS = ("loras", "vae")  # model folders a template may name that no hardware profile lists


def known_registry():
    """The whole data/known-nodes.json: nodes, packs {pack id: {nodes, ...}} and local_model_nodes."""
    with open(KNOWN, encoding="utf-8") as f:
        return json.load(f)


def known_nodes():
    return known_registry()["nodes"]


def is_number(v):
    """An int or a finite float (bool is not a number)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and (isinstance(v, int) or math.isfinite(v))


def hardware():
    """(profiles, kinds) of data/hardware.json: {profile id: {"vram": requires.min_vram_gb, "ram":
    requires.min_ram_gb, "gpu": requires.gpu (a bool), "packs": [pack id]}} and the model kinds any profile names
    (file order). ValueError with one message when the file is missing or malformed."""
    try:
        with open(HARDWARE, encoding="utf-8") as f:
            raw = json.load(f)
        profiles, kinds = {}, []
        for p in raw["profiles"]:
            entry = {"vram": p["requires"]["min_vram_gb"], "ram": p["requires"]["min_ram_gb"],
                     "gpu": p["requires"]["gpu"], "packs": [pack["id"] for pack in p["packs"]]}
            found = [m["kind"] for m in p["models"]]
            if (not isinstance(p["id"], str) or not is_number(entry["vram"]) or not is_number(entry["ram"])
                    or not isinstance(entry["gpu"], bool)
                    or not all(isinstance(x, str) for x in entry["packs"] + found)):
                raise ValueError("profile %r: id, pack ids and model kinds must be strings, min_vram_gb and min_ram_gb numbers, gpu a bool" % (p["id"],))
            profiles[p["id"]] = entry
            kinds += [k for k in found if k not in kinds]
        if not profiles:
            raise ValueError("no profiles")
        return profiles, kinds
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("data/hardware.json is missing or malformed (%s: %s): the requires block cannot be checked"
                         % (type(exc).__name__, str(exc).replace("\n", " ")))


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
        if spec.get("ui_only"):
            errs.append("node %s: %s is a UI-only node (frontend canvas only, no API form); it cannot be part of workflow" % (nid, ctype))
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


def requires_errors(data, graph):
    """(errors, warnings) of a template's optional requires block and of the graph rules tied to it. The block names
    what a local template needs: a data/hardware.json profile, the peak VRAM and the RAM it declares (never above the
    profile's min_vram_gb / min_ram_gb), the node packs its workflow uses and its model files (kind, file name, size).
    A node of a known-nodes pack needs that pack id in requires.packs; a local_model_nodes or pack node needs the
    block and a declared profile with a GPU (hardware.json requires.gpu true): one error per such node otherwise.
    A template without the block and without such a node gets no error and no warning."""
    registry = known_registry()
    pack_of = {name: pid for pid, spec in registry.get("packs", {}).items() for name in spec.get("nodes", [])}
    local = set(registry.get("local_model_nodes", []))
    typed = [(nid, node["class_type"]) for nid, node in (graph.items() if isinstance(graph, dict) else [])
             if isinstance(node, dict) and isinstance(node.get("class_type"), str)]
    if "requires" not in data:
        return ["node %s (%s) runs a local model: the template needs a requires block (%s)"
                % (nid, ctype, ", ".join(REQUIRES_KEYS)) for nid, ctype in typed if ctype in local or ctype in pack_of], []
    req = data["requires"]
    if not isinstance(req, dict):
        return ["requires must be an object (%s)" % ", ".join(REQUIRES_KEYS)], []
    try:
        profiles, kinds = hardware()
    except ValueError as exc:
        return [str(exc)], []
    errs = ["requires.%s: unknown key (a requires block holds only %s)" % (k, ", ".join(REQUIRES_KEYS))
            for k in req if k not in REQUIRES_KEYS]
    text = json.dumps(req)
    errs += ["requires contains a %s (%s); it names a profile, packs and model files, never a link, an endpoint or a credential"
             % (what, m.group(0)[:40]) for rx, what in FORBIDDEN for m in [rx.search(text)] if m]
    profile = req.get("profile")
    limits = profiles.get(profile) if isinstance(profile, str) else None
    if "profile" not in req:
        errs.append("requires.profile missing (one of %s; data/hardware.json)" % ", ".join(profiles))
    elif limits is None:
        errs.append("requires.profile %r is not a hardware profile (%s; data/hardware.json)" % (profile, ", ".join(profiles)))
    elif not limits["gpu"]:
        with_gpu = ", ".join(pid for pid, p in profiles.items() if p["gpu"]) or "hardware.json has none"
        errs += ["node %s (%s) runs a local model, but profile %s has no GPU (hardware.json requires.gpu false); declare a local profile (%s)"
                 % (nid, ctype, profile, with_gpu) for nid, ctype in typed if ctype in local or ctype in pack_of]
    for key, limit, field in (("peak_vram_gb", "vram", "min_vram_gb"), ("ram_gb", "ram", "min_ram_gb")):
        value = req.get(key)
        if not is_number(value) or value < 0:
            errs.append("requires.%s must be a number >= 0" % key if key in req else "requires.%s missing (a number >= 0)" % key)
        elif limits is not None and value > limits[limit]:
            errs.append("requires.%s %s is above %s %s of profile %s (data/hardware.json): the template would not fit the machine the profile describes"
                        % (key, value, field, limits[limit], profile))
    declared = req.get("packs", [])
    if not isinstance(declared, list) or not all(isinstance(p, str) for p in declared):
        errs.append("requires.packs must be a list of pack ids (strings)")
        declared = [p for p in declared if isinstance(p, str)] if isinstance(declared, list) else []
    declared_ids = list(dict.fromkeys(declared))
    errs += ["requires.packs lists %r more than once" % p for p in declared_ids if declared.count(p) > 1]
    if limits is not None:
        errs += ["requires.packs: %r is not a pack of profile %s (%s)" % (p, profile, ", ".join(limits["packs"]) or "it has no packs")
                 for p in declared_ids if p not in limits["packs"]]
    models = req.get("models", [])
    if not isinstance(models, list):
        errs.append("requires.models must be a list of {%s} objects" % ", ".join(MODEL_KEYS))
        models = []
    allowed = kinds + [k for k in EXTRA_MODEL_KINDS if k not in kinds]
    for i, model in enumerate(models):
        if not isinstance(model, dict) or sorted(model) != sorted(MODEL_KEYS):
            errs.append("requires.models[%d] must be an object with exactly %s" % (i, ", ".join(MODEL_KEYS)))
            continue
        if not isinstance(model["kind"], str) or model["kind"] not in allowed:
            errs.append("requires.models[%d].kind %r is not a model kind (%s)" % (i, model["kind"], ", ".join(allowed)))
        name = model["name"]
        if not isinstance(name, str) or not name.strip() or any(c in name for c in "/\\:"):
            errs.append("requires.models[%d].name must be a model file name; source links live in docs/hardware.md, never in templates" % i)
        if not is_number(model["size_gb"]) or model["size_gb"] <= 0:
            errs.append("requires.models[%d].size_gb must be a number > 0" % i)
    used = set()
    for nid, ctype in typed:
        pid = pack_of.get(ctype)
        if pid is None:
            continue
        used.add(pid)
        if pid not in declared_ids:
            errs.append("node %s uses %s from pack %s, not declared in requires.packs" % (nid, ctype, pid))
    warns = ["requires.packs declares %s, but no workflow node comes from that pack" % p for p in declared_ids if p not in used]
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
    e, w = requires_errors(data, graph)
    errs += e
    warns += w
    errs += [e for e in stylelock.purpose_errors(data) if e.startswith("max_references")]
    out = data.get("output_node")
    if not isinstance(graph, dict) or not isinstance(out, str) or out not in graph:
        errs.append("output_node %r is not a node of the workflow" % out)
    elif not isinstance(graph[out], dict) or not known_nodes().get(graph[out].get("class_type"), {}).get("output_node"):
        errs.append("output_node %s is not an output node (SaveImage)" % out)
    return errs, warns


def fit_errors(qa):
    if not isinstance(qa, dict) or not isinstance(qa.get("size"), dict):
        return []
    size = qa["size"]
    fit = size.get("fit", "none")
    if fit not in ("none", "pad"):
        return ["qa.size.fit must be one of ['none', 'pad']"]
    if fit != "pad":
        return []
    errs = []
    if qa.get("alpha") != "required":
        errs.append("qa.size.fit pad needs qa.alpha required (pad adds transparent pixels)")
    if size.get("mode") != "orientation":
        errs.append("qa.size.fit pad needs qa.size.mode orientation")
    if "orientation" in size and size["orientation"] != "auto":
        errs.append("qa.size.fit pad needs qa.size.orientation auto (the expected aspect comes from qa.size.expect)")
    if size.get("allow_swap") is True:
        errs.append("qa.size.fit pad needs qa.size.allow_swap false (pad would square a swapped output qa accepts)")
    return [err + "; or set qa.size.fit none" for err in errs]


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
    cons = data.get("constraints", {})
    if not isinstance(cons, dict):
        errs.append("constraints must be an object")
    else:
        rules = layers.precedence()
        for field, text in cons.items():
            if rules.get(field) != "purpose":
                errs.append("constraints.%s: not a technical constraint a purpose may set (%s; data/precedence.json)"
                            % (field, ", ".join(sorted(k for k, v in rules.items() if v == "purpose"))))
            elif not isinstance(text, str) or not text:
                errs.append("constraints.%s must be a non-empty string" % field)
    return errs + stylelock.purpose_errors(data) + runfiles.qa_errors(data.get("qa")) + fit_errors(data.get("qa"))


def style_errors(data):
    errs = [k + " must be a string" for k in ("prefix", "suffix") if not isinstance(data.get(k, ""), str)]
    if not isinstance(data.get("avoid", []), list):
        errs.append("avoid must be a list")
    if not isinstance(data.get("params", {}), dict):
        errs.append("params must be an object")
    return errs + stylelock.style_errors(data)


def style_warnings(data, layer):
    """An active game style (merged) none of whose structured fields a style check can grade with
    (consistency.usable_fields: absent, empty or malformed) gets no style QA: a WARN naming each field's state."""
    if not layer.startswith("game") or stylelock.style_status(data) != "active":
        return []
    states = consistency.field_states(data)
    if any(state == "ok" for state, _ in states.values()):
        return []
    why = "; ".join("%s %s (%s)" % (consistency.FIELDS[row], states[row][0], states[row][1]) for row in consistency.ROWS)
    return ["active game style has no usable structured style fields (palette.colors, tone, canvas, "
            "outline.edge_darkness): %s; no style-* QA row can grade an output, so qa checks nothing of the style; "
            "add a usable one" % why]


def anchor_lint(raw, style_id, ident, path, authoring):
    errs = stylelock.anchor_errors(raw, style_id, ident)
    if errs:
        return errs
    img = os.path.join(os.path.dirname(path), raw["image"])
    if not os.path.isfile(img):
        errs.append("image %s is missing next to the anchor" % raw["image"])
    elif stylelock._file_sha256(img) != raw["image_sha256"]:
        errs.append("image %s does not match image_sha256" % raw["image"])
    if raw["status"] == "active":
        ok, why = stylelock.anchor_validity({"errors": [], "data": raw}, authoring)
        if not ok:
            errs.append("active anchor: " + why)
    return errs


def classify(path, authoring):
    """(kind, id, layer) when path is a layer file (layer core or game), else (None, None, None)."""
    full = os.path.abspath(path)
    for kind, spec in layers.KINDS.items():
        dirs = [("core", os.path.join(layers.CORE_DIR, spec["core"]))]
        if authoring:
            dirs.append(("game", os.path.join(layers.game_dir(authoring), spec["game"])))
        for layer, d in dirs:
            if os.path.normcase(os.path.dirname(full)) == os.path.normcase(os.path.abspath(d)):
                return kind, os.path.basename(full)[:-5], layer
    return None, None, None


def display(path, authoring):
    full = os.path.abspath(path)
    for prefix, root in (("game:", os.path.abspath(authoring) if authoring else None), ("core:", layers.PLUGIN_ROOT)):
        if root and os.path.normcase(full).startswith(os.path.normcase(root) + os.sep):
            return prefix + os.path.relpath(full, root).replace(os.sep, "/")
    return path.replace(os.sep, "/")


def lint_data(path, raw, authoring):
    """(errors, warnings) of one parsed file; nested types are validated before use."""
    errs, warns = [], []
    lock, style_id, lock_id = stylelock.classify(path, authoring)
    if lock == "project":
        return stylelock.project_errors(raw, authoring), []
    if lock == "anchor":
        return anchor_lint(raw, style_id, lock_id, path, authoring), []
    if lock == "rejection":
        return stylelock.rejection_errors(raw, style_id, lock_id), []
    kind, ident, layer = classify(path, authoring)
    if kind:
        # a core file is linted as core data only: a bad game value that extends or overrides it is blamed on the
        # game file that holds it, never on the unchanged core file
        if layer == "core":
            authoring = None
        try:
            entry = layers.load(kind, ident, authoring, _layer=layer if layer == "core" else None)
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
            warns += style_warnings(data, entry["layer"])
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
    if stylelock.classify(path, authoring)[0] == "project" and not os.path.isfile(path):
        return {"path": shown, "check": "assetgen-lint", "state": "WARN",
                "reasons": ["no assetgen/project.json: style lock off (styles come from the purpose's default_style or --style)"]}
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


def template_data(path, authoring=None):
    """(data, error) of a template file for the graph style rows: a core or game layer template merged as lint_data
    merges it (a core file as core only), or a standalone file whose schema is the template schema. (None, None) for
    any other file or an unreadable one; (None, message) when a layer template does not load."""
    if stylelock.classify(path, authoring)[0]:
        return None, None
    kind, ident, layer = classify(path, authoring)
    if kind:
        if kind != "template":
            return None, None
        try:
            if layer == "core":
                return layers.load(kind, ident, None, _layer="core")["data"], None
            return layers.load(kind, ident, authoring)["data"], None
        except layers.SpecError as exc:
            return None, str(exc)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None, None
    if isinstance(raw, dict) and raw.get("schema") == layers.KINDS["template"]["schema"]:
        return raw, None
    return None, None


def lint_rows(path, authoring=None):
    """[lint_file(path)] plus one assetgen-graph-style row (graphstyle.template_row) when path is a template."""
    rows = [lint_file(path, authoring)]
    data, _ = template_data(path, authoring)
    if isinstance(data, dict):
        rows.append(graphstyle.template_row(data, known_nodes(), display(path, authoring)))
    return rows


def default_paths(authoring=None):
    out = []
    for kind in layers.KINDS:
        files = layers.layer_files(kind, authoring)
        out += list(files["core"].values()) + list(files["game"].values())
    if authoring:
        out.append(stylelock.project_path(authoring))
        out += [p for _, _, p in stylelock.anchor_files(authoring)]
    return out
