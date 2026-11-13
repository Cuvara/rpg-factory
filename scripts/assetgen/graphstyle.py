"""Graph style lint of asset-gen workflows (stdlib only at import; uiworkflow is imported inside template_violations).

The workflow style guide in short (rule ids in brackets):
  [title]          every API node has a title of its own (not empty, not its class name).
  [group]          every API node is in exactly one group.
  [vocabulary]     group titles come from STAGES: Prompt, References, Generate, Models, Refine (local), Post-process,
                   Preview, Output. Models holds the local loaders (checkpoint, LoRA, ControlNet, IPAdapter, upscale
                   model) that feed the Refine (local) sampler.
  [order]          groups run left to right in STAGES order, no title twice (any subsequence of STAGES).
  [note]           every group holds at least one Note or MarkdownNote that says what the stage does.
  [prompt]         the reviewed prompt is ONE PrimitiveStringMultiline linked directly into every positive text input:
                   NineRouterImage.user_prompt, and CLIPTextEncode.text / CLIPTextEncodeSDXL.text_g, text_l when the
                   encoder's CONDITIONING reaches a KSampler positive input (directly or through ControlNetApply*).
                   Two different prompt nodes feeding positive inputs are a violation whatever the node id order.
                   A negative-only encoder holds its own text, never the reviewed prompt node or {{prompt}}. In a
                   template that node's value is the reviewed prompt placeholder {{prompt}} (no other text), and only
                   one PrimitiveStringMultiline holds {{prompt}}.
  [one-image-node] the graph has exactly one NineRouterImage, or none when a local KSampler generates the image.
  [save-suffix]    every SaveImage.filename_prefix carries an inline suffix after the run prefix
                   ("{{filename_prefix}}-icon"; in a run's workflow.ui.json "assetgen/<run-id>-icon").
  [save-output]    every SaveImage sits in the Output group; intermediates use PreviewImage (any group).
  [load-image]     a template's LoadImage.image is exactly one {{placeholder}}, never a static file name.
  [unknown]        (UI form) a node type that data/known-nodes.json does not list.
  [layout]         a shape the rules cannot read (uiworkflow.to_ui error, malformed nodes, links or groups).

Profile rules (template form only, with a hardware argument; UNTESTED on RTX 5060: each is a static check of the graph
and its requires declaration against data/hardware.json planning thresholds; nothing is generated or measured). They
run under the effective profile (the profile argument, else the template's requires.profile) and only when it has a
GPU, except [profile]. Each message names the node(s) and says "under profile <id>".
  [profile]        a profile argument ranking below the template's requires.profile; names its local-model nodes.
  [vram]           requires.peak_vram_gb above the profile's min_vram_gb; names the checkpoint loader(s).
  [checkpoints]    two CheckpointLoaderSimple with different ckpt_name, unless requires.offload is true.
  [controlnet]     more than one ControlNetApply* on a KSampler's positive/negative conditioning path.
  [batch]          a batch_size that is not 1 (a placeholder passes when its default and every option are 1).
  [tiled-vae]      a VAEDecode whose latent may be above 1024 px on a side (EmptyLatentImage, the NineRouterImage
                   size, an upscale model upstream); use VAEDecodeTiled.
  [flux]           a Flux model file name in a model-file input (name ending in _name: ckpt_name, lora_name, ...) of a
                   local-model or pack node, or in requires.models[].name (never prompt text): any Flux under
                   local-4gb, unquantized Flux (no fp8, gguf, q4-q8, nf4 marker) under local-8gb.

Two forms are checked:
  template_violations(data, known, profile=None, hardware=None) -> ["<rule>: <message>", ...] for a parsed (merged)
      template; groups and notes come from its ui block, the left-to-right order from uiworkflow.to_ui's layout. The
      prompt source's value must be the {{prompt}} placeholder: literal text or another placeholder ({{model}}) is a
      prompt violation naming the source and the text input's node. hardware is lint.hardware()[0] ({profile id:
      {"vram", "ram", "gpu", "packs"}} in rank order); None (the default) runs no profile rule.
  ui_violations(ui_workflow, known, prefix=None) -> the same for a ComfyUI frontend workflow (a run's workflow.ui.json);
      group membership is geometric (the node's rect, title bar included, inside the group's bounding). Every API
      node obeys the title and group rules, the style-lock reference nodes render adds too (render titles them and
      lays them into a References group); there is no exemption by file name. load-image is not checked (render
      fills it). The prompt source's value is the filled prompt and is not checked here: gen-run-provenance compares
      workflow.json prompts with prompt.md. save-suffix compares against the run prefix: the argument (callers pass
      the trusted assetgen/<run-id> of the run context: graph-lint --run, the gen-run-workflow-style check), else
      assetgen/<extra.assetgen.run_id>; with neither, each SaveImage is a save-suffix violation saying the run prefix
      is unknown (never a silent skip). No profile rule runs on this form.
  template_row / ui_row wrap them as one validation row {"path", "check": CHECK, "state", "reasons"}. A legacy
      template (no ui block, or a ui without groups) is WARN, never FAIL.
Messages name a node as `node <id> (<class_type> "<title>")` and a group as `group "<title>"`. Callers pass parsed
data; `known` is the "nodes" object of data/known-nodes.json. The only file read is data/known-nodes.json's
local_model_nodes and pack nodes, once, when a profile rule runs.
"""

import json
import os
import re

STAGES = ("Prompt", "References", "Generate", "Models", "Refine (local)", "Post-process", "Preview", "Output")
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
SAMPLER, CHECKPOINT, CONTROLNET_APPLY = "KSampler", "CheckpointLoaderSimple", "ControlNetApply"
# the text inputs that carry a prompt; NineRouterImage.user_prompt is always positive, an encoder's text is positive
# when its CONDITIONING reaches a KSampler positive input
TEXT_INPUTS = {IMAGE_NODE: ("user_prompt",), "CLIPTextEncode": ("text",), "CLIPTextEncodeSDXL": ("text_g", "text_l")}
TILE_LIMIT = 1024
SIZE = re.compile(r"\s*(\d+)\s*[xX]\s*(\d+)\s*")  # NineRouterImage size "WxH"
# Flux under a profile (hardware.json excludes): local-4gb refuses Flux of any precision, local-8gb refuses Flux fp16
# (only a quantized file name passes); other profiles have no Flux rule
FLUX_RULE = {"local-4gb": "any", "local-8gb": "quantized"}
FLUX = re.compile(r"flux", re.I)
QUANTIZED = re.compile(r"fp8|gguf|q4|q5|q6|q8|nf4", re.I)
MODEL_INPUT = "_name"  # a model-file input: ckpt_name, lora_name, control_net_name, model_name, unet_name, clip_name
REGISTRY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "known-nodes.json")
_LOCAL = []


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
    out += _fan_out(nodes)
    sampler = any(nodes[nid]["type"] == SAMPLER for nid in ids)
    if len(image_nodes) > 1 or (not image_nodes and not sampler):
        out.append("one-image-node: the graph has %d %s nodes%s; it needs exactly one%s"
                   % (len(image_nodes), IMAGE_NODE, " (%s)" % ", ".join(image_nodes) if image_nodes else "",
                      "" if image_nodes else ", or a local %s" % SAMPLER))
    return out


def _consumers(nodes):
    """{(source id, output slot): [(consumer id, input name)]} over the links of nodes."""
    out = {}
    for nid in sorted(nodes, key=_sort_key):
        for name, value in nodes[nid]["inputs"].items():
            if _is_link(value) and value[0] in nodes:
                out.setdefault((value[0], value[1]), []).append((nid, name))
    return out


def _reaches(nodes, consumers, nid):
    """The KSampler inputs ("positive", "negative") the CONDITIONING output of encoder nid reaches, directly or through
    ControlNetApply* nodes (their positive/conditioning input leaves on output 0, their negative on output 1)."""
    found, seen, todo = set(), set(), [(nid, 0)]
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        seen.add(key)
        for dst, name in consumers.get(key, []):
            ctype = nodes[dst]["type"]
            if ctype == SAMPLER and name in ("positive", "negative"):
                found.add(name)
            elif ctype.startswith(CONTROLNET_APPLY) and name in ("positive", "conditioning", "negative"):
                todo.append((dst, 1 if name == "negative" else 0))
    return found


def text_inputs(nodes):
    """[(node id, input name, positive)] of every prompt text input: NineRouterImage.user_prompt (always positive),
    CLIPTextEncode.text and CLIPTextEncodeSDXL.text_g/text_l (positive when the encoder reaches a KSampler positive
    input). nodes: the normalized {id: {"type", "title", "inputs", ...}} form."""
    consumers, out = _consumers(nodes), []
    for nid in sorted(nodes, key=_sort_key):
        names = TEXT_INPUTS.get(nodes[nid]["type"])
        if not names:
            continue
        positive = nodes[nid]["type"] == IMAGE_NODE or "positive" in _reaches(nodes, consumers, nid)
        out += [(nid, name, positive) for name in names]
    return out


def _source(nodes, value):
    """The PrimitiveStringMultiline id a text input value links from, else None."""
    if _is_link(value) and value[0] in nodes and nodes[value[0]]["type"] == PROMPT_NODE:
        return value[0]
    return None


def _holds_prompt(nodes, nid):
    value = nodes[nid]["inputs"].get("value")
    return isinstance(value, str) and bool(REVIEWED_PROMPT.search(value))


def _fan_out(nodes):
    """prompt violations of the fan-out: every positive text input (NineRouterImage.user_prompt included) is a direct
    link from the one reviewed prompt node; a negative-only text input never uses it nor holds the {{prompt}}
    placeholder. The missing/literal/wrong-class messages of NineRouterImage.user_prompt stay in _check. When two
    different PrimitiveStringMultiline nodes feed positive text inputs (whatever the node id order), every input not
    linked from the reviewed one is a "second prompt node" violation; the reviewed one is the source holding {{prompt}}
    (template form), else the source feeding the most positive inputs, else the lowest id. A graph without a CLIP
    encoder gets nothing here (API-only graphs keep their messages)."""
    inputs = text_inputs(nodes)
    if all(nodes[nid]["type"] == IMAGE_NODE for nid, _, _ in inputs):
        return []
    sources = [_source(nodes, nodes[nid]["inputs"].get(name)) for nid, name, positive in inputs if positive]
    linked = [s for s in sources if s is not None]
    reviewed = min(set(linked), key=lambda s: (not _holds_prompt(nodes, s), -linked.count(s), _sort_key(s)),
                   default=None)
    fix = ("link it directly from the reviewed prompt %s" % _name(nodes, reviewed) if reviewed is not None
           else "link it directly from a %s" % PROMPT_NODE)
    out = []
    for nid, name, positive in inputs:
        value = nodes[nid]["inputs"].get(name)
        if nodes[nid]["type"] == IMAGE_NODE:
            src = _source(nodes, value)
            if src is not None and src != reviewed:
                out.append("prompt: %s %s is linked from %s, a second prompt node; the reviewed prompt is one %s, %s, "
                           "feeding every positive text input" % (_name(nodes, nid), name, _name(nodes, src),
                                                                 PROMPT_NODE, _name(nodes, reviewed)))
            continue
        if not positive:
            src = value[0] if _is_link(value) else None
            if src is not None and src in nodes and (src in sources or (nodes[src]["type"] == PROMPT_NODE
                                                                        and _holds_prompt(nodes, src))):
                out.append("prompt: %s %s feeds only negative conditioning but is linked from the reviewed prompt %s; "
                           "give the negative its own text" % (_name(nodes, nid), name, _name(nodes, src)))
            elif isinstance(value, str) and REVIEWED_PROMPT.search(value):
                out.append("prompt: %s %s feeds only negative conditioning but holds the reviewed prompt placeholder "
                           "%s; give the negative its own text" % (_name(nodes, nid), name, PROMPT_PARAM))
            continue
        if value is None:
            out.append("prompt: %s %s is missing; %s" % (_name(nodes, nid), name, fix))
        elif not _is_link(value):
            out.append("prompt: %s %s is a literal value, not a link; %s" % (_name(nodes, nid), name, fix))
        elif value[0] not in nodes:
            out.append("prompt: %s %s links to node %s, which is not an API node of the graph; %s"
                       % (_name(nodes, nid), name, value[0], fix))
        elif nodes[value[0]]["type"] != PROMPT_NODE:
            out.append("prompt: %s %s is linked from %s, not a %s; %s"
                       % (_name(nodes, nid), name, _name(nodes, value[0]), PROMPT_NODE, fix))
        elif value[0] != reviewed:
            out.append("prompt: %s %s is linked from %s, a second prompt node; the reviewed prompt is one %s, %s, "
                       "feeding every positive text input" % (_name(nodes, nid), name, _name(nodes, value[0]),
                                                             PROMPT_NODE, _name(nodes, reviewed)))
    return out


def _save_output(nodes):
    return ["save-output: %s is not in %s; intermediates use PreviewImage, the saved image sits in Output"
            % (_name(nodes, nid), _group("Output"))
            for nid in sorted(nodes, key=_sort_key)
            if nodes[nid]["type"] == "SaveImage" and nodes[nid]["groups"] is not None
            and "Output" not in nodes[nid]["groups"]]


def template_violations(data, known, profile=None, hardware=None):
    """Violations of a parsed (merged) template {"workflow", "ui"?, "output_node", ...}; never raises for data problems.
    hardware: {profile id: {"vram", "ram", "gpu", "packs"}} in rank order (lint.hardware()[0]) turns on the profile
    rules under the effective profile (profile, else the template's requires.profile); None = no profile rule."""
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
    for nid, name, positive in text_inputs(nodes):
        link = nodes[nid]["inputs"].get(name)
        if not positive or _source(nodes, link) is None:
            continue  # a missing, literal or wrongly sourced positive text input is already a prompt violation of _check
        value = nodes[link[0]]["inputs"].get("value")
        if not (isinstance(value, str) and REVIEWED_PROMPT.fullmatch(value)):
            out.append("prompt: %s %s is linked from %s whose value %s is not the reviewed prompt placeholder "
                       "%s; render fills it from prompt.md" % (_name(nodes, nid), name, _name(nodes, link[0]),
                                                              _show(value), PROMPT_PARAM))
    holders = [nid for nid in sorted(nodes, key=_sort_key) if nodes[nid]["type"] == PROMPT_NODE
               and isinstance(nodes[nid]["inputs"].get("value"), str)
               and REVIEWED_PROMPT.search(nodes[nid]["inputs"]["value"])]
    if len(holders) > 1:
        out.append("prompt: %d %s nodes hold the reviewed prompt placeholder %s (%s); exactly one node is the reviewed "
                   "prompt" % (len(holders), PROMPT_NODE, PROMPT_PARAM, ", ".join(_name(nodes, n) for n in holders)))
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
    if isinstance(hardware, dict):
        out += _profile_rules(data, nodes, known, profile, hardware)
    return out


def _local_types():
    """(local_model_nodes, pack node types) of data/known-nodes.json, read once; empty sets when it cannot be read
    (lint's own known-nodes checks FAIL then)."""
    if not _LOCAL:
        try:
            with open(REGISTRY, encoding="utf-8") as f:
                registry = json.load(f)
            local = {t for t in registry.get("local_model_nodes", []) if isinstance(t, str)}
            packs = {t for spec in registry.get("packs", {}).values() for t in spec.get("nodes", []) if isinstance(t, str)}
        except (OSError, ValueError, AttributeError, TypeError):
            local, packs = set(), set()
        _LOCAL.append((local, packs))
    return _LOCAL[0]


def _candidates(value, params):
    """The values an input may take: a literal is itself; one {{param}} placeholder is that param's default and enum
    options (nothing when the param is not declared); a link or any other string with a placeholder is []."""
    if _is_link(value):
        return []
    if isinstance(value, str) and ANY_PLACEHOLDER.search(value):
        if not ONE_PLACEHOLDER.fullmatch(value):
            return []
        decl = params.get(value.strip()[2:-2].strip()) if isinstance(params, dict) else None
        if not isinstance(decl, dict):
            return []
        out = [decl["default"]] if "default" in decl else []
        return out + (list(decl["options"]) if isinstance(decl.get("options"), list) else [])
    return [value]


def _names(nodes, ids, limit=None):
    shown = [_name(nodes, nid) for nid in ids]
    if limit is not None and len(shown) > limit:
        shown = shown[:limit] + ["..."]
    return ", ".join(shown)


def _above(nodes, known, params, link, seen):
    """True when the image or latent behind link may be above TILE_LIMIT px on a side (see the tiled-vae rule)."""
    if not _is_link(link) or link[0] not in nodes or link[0] in seen:
        return False
    nid = link[0]
    seen.add(nid)
    ctype, inputs = nodes[nid]["type"], nodes[nid]["inputs"]
    if ctype == "EmptyLatentImage":
        return any(_is_num(c) and c > TILE_LIMIT for k in ("width", "height") for c in _candidates(inputs.get(k), params))
    if ctype == SAMPLER:
        return _above(nodes, known, params, inputs.get("latent_image"), seen)
    if ctype == "VAEEncode":
        return _above(nodes, known, params, inputs.get("pixels"), seen)
    if ctype == IMAGE_NODE:
        for size in _candidates(inputs.get("size"), params):
            m = SIZE.fullmatch(size) if isinstance(size, str) else None
            if m and max(int(m.group(1)), int(m.group(2))) > TILE_LIMIT:
                return True
        return False
    if ctype == "ImageUpscaleWithModel":
        return True
    if ctype == "LoadImage":
        return False
    decls = known[ctype].get("inputs", {}) if isinstance(known.get(ctype), dict) else {}
    links = [v for name, v in inputs.items() if _is_link(v) and decls.get(name, {}).get("type") in ("IMAGE", "LATENT")]
    return len(links) == 1 and _above(nodes, known, params, links[0], seen)


def _conditioning_upstream(nodes, known, nid):
    """The ControlNetApply* node ids upstream of KSampler nid's positive and negative inputs, following CONDITIONING
    links (the path the conditioning takes; an input of unknown type is followed too)."""
    found, seen = [], set()
    todo = [nodes[nid]["inputs"].get(k) for k in ("positive", "negative")]
    while todo:
        link = todo.pop()
        if not _is_link(link) or link[0] not in nodes or link[0] in seen:
            continue
        src = link[0]
        seen.add(src)
        ctype = nodes[src]["type"]
        if ctype.startswith(CONTROLNET_APPLY):
            found.append(src)
        decls = known[ctype].get("inputs", {}) if isinstance(known.get(ctype), dict) else {}
        todo += [v for name, v in nodes[src]["inputs"].items()
                 if _is_link(v) and decls.get(name, {}).get("type", "CONDITIONING") == "CONDITIONING"]
    return sorted(found, key=_sort_key)


def _profile_rules(data, nodes, known, profile, hardware):
    """Profile rule violations of a template (UNTESTED on RTX 5060: static checks of the graph and its requires
    declaration against the hardware.json planning thresholds; nothing is generated or measured)."""
    req = data.get("requires") if isinstance(data.get("requires"), dict) else {}
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    declared = req.get("profile") if isinstance(req.get("profile"), str) and req.get("profile") in hardware else None
    if profile is not None and profile not in hardware:
        return []
    effective = profile if profile is not None else declared
    if effective is None:
        return []
    under = "under profile %s" % effective
    ids = sorted(nodes, key=_sort_key)
    local, packs = _local_types()
    local_ids = [nid for nid in ids if nodes[nid]["type"] in local or nodes[nid]["type"] in packs]
    ranks = list(hardware)
    out = []
    if profile is not None and declared is not None and ranks.index(declared) > ranks.index(profile):
        out.append("profile: the template requires profile %s (requires.profile), which ranks above profile %s%s; "
                   "it does not run %s"
                   % (declared, profile, "; its local-model nodes %s" % _names(nodes, local_ids, 3) if local_ids else "",
                      under))
    limits = hardware[effective]
    if not (isinstance(limits, dict) and limits.get("gpu") is True):
        return out
    loaders = [nid for nid in ids if nodes[nid]["type"] == CHECKPOINT]
    peak, vram = req.get("peak_vram_gb"), limits.get("vram")
    if _is_num(peak) and _is_num(vram) and peak > vram:
        named = loaders or local_ids
        out.append("vram: requires.peak_vram_gb %s is above the %s GiB VRAM (min_vram_gb) of profile %s%s; the template "
                   "does not fit %s" % (peak, vram, effective, " for %s" % _names(nodes, named, 3) if named else "", under))
    models = {json.dumps(nodes[nid]["inputs"].get("ckpt_name"), sort_keys=True) for nid in loaders}
    if len(models) > 1 and req.get("offload") is not True:
        out.append("checkpoints: %s load %d different checkpoints at once %s; keep one checkpoint or declare "
                   "requires.offload true (one is unloaded before the next loads)"
                   % (_names(nodes, loaders), len(models), under))
    for nid in ids:
        if nodes[nid]["type"] != SAMPLER:
            continue
        nets = _conditioning_upstream(nodes, known, nid)
        if len(nets) > 1:
            out.append("controlnet: %s gets %d ControlNets in one path (%s) %s; apply at most one ControlNet"
                       % (_name(nodes, nid), len(nets), _names(nodes, nets), under))
    for nid in ids:
        inputs = nodes[nid]["inputs"]
        if "batch_size" not in inputs:
            continue
        value = inputs["batch_size"]
        values = _candidates(value, params)
        if not (values and all(v == 1 and isinstance(v, int) and not isinstance(v, bool) for v in values)):
            out.append("batch: %s batch_size %s is not 1 %s; local generation runs batch 1"
                       % (_name(nodes, nid), value if _is_num(value) else _show(value), under))
    for nid in ids:
        if nodes[nid]["type"] == "VAEDecode" and _above(nodes, known, params, nodes[nid]["inputs"].get("samples"), set()):
            out.append("tiled-vae: %s may decode an image above %d px on a side %s; use VAEDecodeTiled"
                       % (_name(nodes, nid), TILE_LIMIT, under))
    rule = FLUX_RULE.get(effective)
    if rule:
        why = ("Flux of any precision is excluded" if rule == "any"
               else "Flux fp16 is excluded; only a quantized file (fp8, gguf, q4, q5, q6, q8, nf4) passes")

        def refused(name):
            return isinstance(name, str) and bool(FLUX.search(name)) and (rule == "any" or not QUANTIZED.search(name))
        for nid in local_ids:
            for name, value in sorted(nodes[nid]["inputs"].items()):
                if not name.endswith(MODEL_INPUT):
                    continue  # only model-file inputs (ckpt_name, lora_name, ...), never prompt text
                hit = next((v for v in ([value] + _candidates(value, params) if isinstance(value, str) else [])
                            if refused(v)), None)
                if hit is not None:
                    out.append('flux: %s %s "%s" is a Flux model %s; %s' % (_name(nodes, nid), name, hit, under, why))
        listed = req.get("models") if isinstance(req.get("models"), list) else []
        for i, model in enumerate(listed):
            name = model.get("name") if isinstance(model, dict) else None
            if refused(name):
                out.append('flux: requires.models[%d] "%s" is a Flux model %s; %s' % (i, name, under, why))
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


def template_row(data, known, shown, profile=None, hardware=None):
    """One row for a template: legacy (no ui block or no groups) WARN, else FAIL on violations, PASS without.
    profile, hardware: as template_violations (None = no profile rule)."""
    violations = template_violations(data, known, profile, hardware)
    ui = data.get("ui") if isinstance(data, dict) else None
    if ui is None or (isinstance(ui, dict) and not ui.get("groups")):
        return {"path": shown, "check": CHECK, "state": "WARN", "reasons": [LEGACY] + violations}
    return {"path": shown, "check": CHECK, "state": "FAIL" if violations else "PASS", "reasons": violations}


def ui_row(ui_workflow, known, shown, prefix=None):
    """One row for a ComfyUI frontend workflow: FAIL on violations, PASS without."""
    violations = ui_violations(ui_workflow, known, prefix)
    return {"path": shown, "check": CHECK, "state": "FAIL" if violations else "PASS", "reasons": violations}
