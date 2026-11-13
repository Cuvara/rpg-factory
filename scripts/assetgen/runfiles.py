"""Run-directory evidence rules shared by the asset-gen engine and the gen-run quality plugin (stdlib only; imports
nothing from the engine, so scripts/checks/domains/assetgen.py can load it by file path).

read_verdict(path, phase) -> {by, state, findings, prompt_sha256, requirements_sha256, outputs}
  A review file (review-prompt.json, review-image.json) holds one JSON verdict object, possibly inside other text
  (codex exec -o writes the last message). state NOT_RUN when the file is absent, INVALID when no object with state
  PASS or FAIL is found. The binding fields are what review-cmd told the reviewer to copy back unchanged: the
  sha256 of the prompt it reviewed and the requirements_sha256 it judged against (both phases) and, for the image
  phase, [{path, sha256}] of the images it saw. A verdict without them, or with other values than the run's
  current prompt, requirements and outputs, is unbound or stale. With the style lock the image binding also names
  "style" (the style ref) and "anchors" ([{anchor_id, sha256}] of the anchors attached); an image verdict that carries
  them keeps them ({"style": dict or None, "anchors": [...]}), a verdict without them has neither key (older runs keep
  their shape).
requirements_sha256(spec, generation=None) -> sha256 of the canonical JSON (sorted keys, compact separators) of
  {purpose, style, template: their content sha256, params: spec params, generation: generation}. generation
  is None for the prompt review and generation_inputs(workflow, spec) for the image review. A review binding passes
  the spec with the rendered params (rendered_params: what the review prompt shows), so a render --param that changes
  a param after a review makes it stale. Works on spec.json (resolved refs carry sha256) and on run.md's spec block
  (manifest copies the refs and the rendered params); malformed input still gives a hash. A review made before the purpose (rubric, qa, ...), the style, the template, the resolved
  params or the rendered generation inputs changed is stale. Only when the spec carries style_lock (resolve with the
  style lock) does the object also hold {"style_lock": style_lock_binding(spec)}: the style ref, the family, the anchor
  hashes and the relevant rejections (id and content hash), so a review made before the family or the rejection set
  changed is stale too; a spec or run.md written before the style lock hashes exactly as it did.
generation_inputs(workflow, spec, locate=None) -> the effective inputs the images were generated with: the whole
  workflow.json graph when a NineRouterImage or KSampler is present, prompts included (a workflow re-rendered with
  another prompt is stale; the plugin also checks
  that the 9router prompt inputs equal the recorded prompt), so every render --param override is bound, plus {"references": {name: sha256}} for every LoadImage input; locate(name) gives the
  path of the run's copy references/<name> (None or a missing file -> null); style-lock anchors are LoadImage inputs
  anchor-<id>.png, so their copies are bound by content. With spec.style_lock it also holds {"anchors": [{anchor_id,
  sha256}]} of the selected references (absent otherwise). Without a workflow: the spec params.
rendered_params(workflow, spec) -> (params, source): spec.json params with each template param read back from the
  rendered workflow.json (source "workflow.json"; "spec.json" without a workflow). manifest records them as run.md
  spec.params, the review prompts show them, and the review bindings and the plugin hash them.
typed_param(name, decl, value) -> value coerced to its template param type (ValueError naming the param).
style_lock_binding(spec) -> {"style", "family", "references": [anchor sha256...], "rejections": [{id, sha256}]} of
  spec.style_lock (sha256 of a rejection: canonical JSON of its spec.style_lock entry), or None for a spec without it.
style_lock_references(spec) -> the selected anchor picks of spec.style_lock ([] without it).
workflow_prompts(workflow) -> 9router prompts followed by linked primitive CLIP texts, excluding negative-only nodes.
local_generation(workflow, spec, hashes=None) -> local model, LoRA and sampler provenance and requires hash, or None
  without local nodes. Local generation is UNTESTED on RTX 5060.
run_filename_prefix(run_id) -> assetgen/<run_id>, the SaveImage filename_prefix every record of the run carries.
reference_names(workflow) -> the LoadImage input names of a workflow (image-edit references).
required_checks(purpose_qa) -> the QA check names every output must carry for that purpose qa block (qa.py runs
  exactly these; the plugin requires a PASS row for each): png-edge-fringe comes last, only for qa.alpha required.
  Malformed input never raises.
qa_errors(purpose_qa) -> what is malformed in a purpose qa block ([] when valid). lint reports these, qa.py grades a
  run whose purpose qa block is malformed FAIL instead of guessing, and the plugin fails such a run.
requested_size(workflow, spec) -> the size the run asked for: the size input of the template's primary_node
  (NineRouterImage; a KSampler gives <w>x<h> of its EmptyLatentImage), else of the NineRouterImage with the lowest node
  id (never dict order), else the resolved spec's size param, else "auto". qa.json records it next to the purpose
  content hash it graded with (purpose_sha256), so a QA report made before the size or the purpose qa block changed is stale.
qa_style_binding(spec, locate) -> what the style consistency rows of qa.py evaluate besides the purpose and the output
  bytes, or None for a spec without style_lock (no style rows): {"style": spec.style_lock.style (the style ref: id,
  version, sha256), "style_sha256": sha256 of the canonical JSON of the effective style data spec.style.data (what
  consistency.py reads; {} when it is not an object), "family": spec.style_lock.family (None when not a string),
  "anchors": [{anchor_id, path, sha256}] of the selected anchors in selection order, path = the pick's image
  (references/anchor-<id>.png) and sha256 = the bytes of locate(path), the run copy qa.py reads for style-tone (null
  when it is missing)}. qa.json records it as style_binding and the plugin recomputes it from spec.json and the run's
  files, so a QA report graded before the style data or version, the family or an anchor copy changed is stale.
"""
import hashlib
import json
import os
import re

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SIZE_RE = re.compile(r"^[1-9]\d*x[1-9]\d*$")  # positive dimensions only
SIZE_MODES = {"exact", "min", "aspect", "orientation", "area", "any"}
ORIENTATIONS = {"landscape", "portrait", "square", "auto"}
ALPHA_MODES = {"required", "forbidden", "any"}
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def required_checks(purpose_qa):
    qa = purpose_qa if isinstance(purpose_qa, dict) else {}
    checks = ["png-valid", "png-size", "png-alpha"]
    if qa.get("transparent_corners"):
        checks.append("png-corners")
    if qa.get("tileable"):
        checks.append("png-tileable")
    if qa.get("not_blank") is not None:
        checks.append("png-not-blank")
    if qa.get("alpha") == "required":
        checks.append("png-edge-fringe")
    return checks


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def qa_errors(qa):
    if not isinstance(qa, dict):
        return ["qa must be an object"]
    errs = []
    size = qa.get("size", {"mode": "any"})
    if not isinstance(size, dict):
        errs.append("qa.size must be an object")
    else:
        if size.get("mode", "any") not in SIZE_MODES:
            errs.append("qa.size.mode must be one of %s" % sorted(SIZE_MODES))
        expect = size.get("expect", "auto")
        if not (expect == "auto" or (isinstance(expect, str) and SIZE_RE.match(expect))):
            errs.append("qa.size.expect must be WIDTHxHEIGHT or auto")
        if "aspect_tolerance" in size and not (_number(size["aspect_tolerance"]) and 0 <= size["aspect_tolerance"] < 1):
            errs.append("qa.size.aspect_tolerance must be a number between 0 and 1")
        if "min_side" in size and not (_number(size["min_side"]) and size["min_side"] >= 0):
            errs.append("qa.size.min_side must be a number >= 0")
        if "min_area" in size and not (_number(size["min_area"]) and 0 < size["min_area"] <= 1):
            errs.append("qa.size.min_area must be a number above 0 and at most 1 (share of the expected pixel count)")
        if "min_pixels" in size and not (_number(size["min_pixels"]) and size["min_pixels"] >= 1):
            errs.append("qa.size.min_pixels must be a number >= 1 (absolute pixel count)")
        if size.get("orientation", "auto") not in ORIENTATIONS:
            errs.append("qa.size.orientation must be one of %s" % sorted(ORIENTATIONS))
        if "square_tolerance" in size and not (_number(size["square_tolerance"]) and 0 <= size["square_tolerance"] < 1):
            errs.append("qa.size.square_tolerance must be a number between 0 and 1")
        if "allow_swap" in size and not isinstance(size["allow_swap"], bool):
            errs.append("qa.size.allow_swap must be true or false")
    if qa.get("alpha", "any") not in ALPHA_MODES:
        errs.append("qa.alpha must be one of %s" % sorted(ALPHA_MODES))
    if not isinstance(qa.get("transparent_corners", False), bool):
        errs.append("qa.transparent_corners must be true or false")
    tile = qa.get("tileable")
    if tile is not None and not (isinstance(tile, dict) and _number(tile.get("max_seam_error"))
                                 and 0 < tile["max_seam_error"] < 1):
        errs.append("qa.tileable.max_seam_error must be a number between 0 and 1")
    blank = qa.get("not_blank")
    if blank is not None:
        if not isinstance(blank, dict):
            errs.append("qa.not_blank must be an object")
        else:
            if "min_stddev" in blank and not (_number(blank["min_stddev"]) and blank["min_stddev"] >= 0):
                errs.append("qa.not_blank.min_stddev must be a number >= 0")
            if "min_coverage" in blank and not (_number(blank["min_coverage"]) and 0 <= blank["min_coverage"] <= 1):
                errs.append("qa.not_blank.min_coverage must be a number between 0 and 1")
    if qa.get("alpha") == "forbidden" and qa.get("transparent_corners"):
        errs.append("qa.transparent_corners contradicts qa.alpha forbidden")
    return errs


PROMPT_NODES = ("NineRouterImage", "NineRouterChat")
TEXT_NODES = ("PrimitiveStringMultiline", "PrimitiveString")  # a prompt node: its "value" is the text it outputs
GENERATION_NODES = ("NineRouterImage", "KSampler")
CLIP_TEXT_INPUTS = {"CLIPTextEncode": ("text",), "CLIPTextEncodeSDXL": ("text_g", "text_l")}
MODEL_LOADERS = {"CheckpointLoaderSimple": ("ckpt_name", "checkpoints"),
                 "LoraLoader": ("lora_name", "loras"), "ControlNetLoader": ("control_net_name", "controlnet"),
                 "UpscaleModelLoader": ("model_name", "upscale_models")}
PRESET_LOADERS = {"IPAdapterUnifiedLoader": ("preset", "ipadapter")}
LOCAL_NODES = ("KSampler",) + tuple(MODEL_LOADERS) + tuple(PRESET_LOADERS)
RUN_PREFIX = "assetgen/"


def run_filename_prefix(run_id):
    """The one filename_prefix of a run: resolve writes it into <run>/spec.json, render, the review prompts and run.md
    read it from there."""
    return RUN_PREFIX + run_id


def workflow_prompts(workflow):
    """The user_prompt inputs of the 9router nodes of a workflow (what was actually sent); a link to a prompt node
    gives its value. Also include linked primitive CLIP texts except negative-only encoders."""
    if not isinstance(workflow, dict):
        return []
    out = []
    for n in workflow.values():
        if not (isinstance(n, dict) and n.get("class_type") in PROMPT_NODES and isinstance(n.get("inputs"), dict)):
            continue
        v = n["inputs"].get("user_prompt")
        src = workflow.get(v[0]) if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) else None
        if isinstance(src, dict) and src.get("class_type") in TEXT_NODES and isinstance(src.get("inputs"), dict):
            v = src["inputs"].get("value")
        out.append(v)
    polarities, visited, pending = {}, set(), []
    for n in workflow.values():
        if isinstance(n, dict) and n.get("class_type") == "KSampler" and isinstance(n.get("inputs"), dict):
            pending.extend((n["inputs"].get(p), p) for p in ("positive", "negative"))
    while pending:
        link, polarity = pending.pop()
        if not (isinstance(link, list) and len(link) == 2 and isinstance(link[0], str)):
            continue
        nid, index = link
        if (nid, polarity) in visited:
            continue
        visited.add((nid, polarity))
        node = workflow.get(nid)
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type")
        if isinstance(cls, str) and cls in CLIP_TEXT_INPUTS:
            polarities.setdefault(nid, set()).add(polarity)
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "positive" in inputs and "negative" in inputs and type(index) is int and index in (0, 1):
            pending.append((inputs["positive" if index == 0 else "negative"], polarity))
        else:
            pending.extend((v, polarity) for v in inputs.values())
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        cls, inputs = node.get("class_type"), node.get("inputs")
        if not isinstance(cls, str) or cls not in CLIP_TEXT_INPUTS or not isinstance(inputs, dict):
            continue
        if polarities.get(nid) == {"negative"}:
            continue
        for key in CLIP_TEXT_INPUTS[cls]:
            link = inputs.get(key)
            src = workflow.get(link[0]) if isinstance(link, list) and len(link) == 2 and isinstance(link[0], str) else None
            if isinstance(src, dict) and src.get("class_type") in TEXT_NODES and isinstance(src.get("inputs"), dict):
                out.append(src["inputs"].get("value"))
    return out


def reference_names(workflow):
    if not isinstance(workflow, dict):
        return []
    names = [(n.get("inputs") or {}).get("image") for n in workflow.values()
             if isinstance(n, dict) and n.get("class_type") == "LoadImage" and isinstance(n.get("inputs"), dict)]
    return sorted({x for x in names if isinstance(x, str)})


def _file_sha256(path):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def generation_inputs(workflow, spec, locate=None):
    if isinstance(workflow, dict) and any(isinstance(n, dict) and n.get("class_type") in GENERATION_NODES
                                          for n in workflow.values()):
        graph = {}
        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = dict(node["inputs"]) if isinstance(node.get("inputs"), dict) else {}
            graph[str(nid)] = {"class_type": node.get("class_type"), "inputs": inputs}
        refs = {}
        for name in reference_names(workflow):
            try:
                refs[name] = _file_sha256(locate(os.path.basename(name)) if locate else None)
            except (OSError, TypeError, ValueError):
                refs[name] = None
        out = {"graph": graph, "references": refs}
        lock = style_lock_binding(spec)
        if lock is not None:
            out["anchors"] = [{"anchor_id": r.get("anchor_id"), "sha256": r.get("sha256")} for r in style_lock_references(spec)]
        return out
    params = spec.get("params") if isinstance(spec, dict) else None
    return params if isinstance(params, dict) else {}


def style_lock_references(spec):
    lock = spec.get("style_lock") if isinstance(spec, dict) else None
    refs = lock.get("references") if isinstance(lock, dict) else None
    return [r for r in refs if isinstance(r, dict)] if isinstance(refs, list) else []


def _canonical_sha256(obj):
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def local_record_key(row):
    """Return the cache key for a model or LoRA row, if its name and kind are strings."""
    if not isinstance(row, dict) or not isinstance(row.get("name"), str):
        return None
    kind = row.get("kind", "loras")
    return kind + "/" + row["name"] if isinstance(kind, str) else None


def local_generation(workflow, spec, hashes=None):
    """Record local loaders and sampling settings; no local nodes means no record."""
    if not isinstance(workflow, dict):
        return None
    nodes = [(str(nid), node) for nid, node in workflow.items()
             if isinstance(node, dict) and node.get("class_type") in LOCAL_NODES]
    if not nodes:
        return None
    def node_order(item):
        nid = item[0]
        if nid.isascii() and nid.isdigit():
            number = nid.lstrip("0") or "0"
            return (0, len(number), number, nid)
        return (1, 0, nid, nid)
    nodes.sort(key=node_order)
    hashes = hashes if isinstance(hashes, dict) else {}
    spec = spec if isinstance(spec, dict) else {}
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    data = template.get("data") if isinstance(template.get("data"), dict) else {}
    template_graph = data.get("workflow") if isinstance(data.get("workflow"), dict) else {}
    try:
        requires = _canonical_sha256(data["requires"]) if "requires" in data else None
    except (TypeError, ValueError, RecursionError):
        requires = None
    result = {"models": [], "loras": [], "samplers": [], "requires_sha256": requires}

    def digest(kind, name, preset=False):
        value = hashes.get(kind + "/" + name) if isinstance(name, str) and not preset else None
        return value if isinstance(value, str) and SHA256.fullmatch(value) else None

    def seed_param(nid):
        node = template_graph.get(nid)
        inputs = node.get("inputs") if isinstance(node, dict) else None
        value = inputs.get("seed") if isinstance(inputs, dict) else None
        if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
            source = template_graph.get(value[0])
            source_inputs = source.get("inputs") if isinstance(source, dict) else None
            value = source_inputs.get("value") if isinstance(source_inputs, dict) else None
        match = PLACEHOLDER.fullmatch(value.strip()) if isinstance(value, str) else None
        return match.group(1) if match else None

    for nid, node in nodes:
        cls = node["class_type"]
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if cls == "KSampler":
            row = {"node": nid, "class_type": cls, "seed": inputs.get("seed"), "seed_param": seed_param(nid)}
            row.update({key: inputs.get(key) for key in ("sampler_name", "scheduler", "steps", "cfg", "denoise")})
            result["samplers"].append(row)
        elif cls == "LoraLoader":
            name = inputs.get("lora_name")
            sha = digest("loras", name)
            result["loras"].append({"node": nid, "name": name, "strength_model": inputs.get("strength_model"),
                                    "strength_clip": inputs.get("strength_clip"), "sha256": sha,
                                    "verified": sha is not None})
        else:
            preset = cls in PRESET_LOADERS
            key, kind = (PRESET_LOADERS if preset else MODEL_LOADERS)[cls]
            name = inputs.get(key)
            sha = digest(kind, name, preset)
            result["models"].append({"node": nid, "class_type": cls, "kind": kind, "name": name,
                                     "sha256": sha, "verified": sha is not None})
    return result


def style_lock_binding(spec):
    lock = spec.get("style_lock") if isinstance(spec, dict) else None
    if not isinstance(lock, dict):
        return None
    rej = lock.get("rejections")
    rejections = [{"id": r.get("id"), "sha256": _canonical_sha256(r)} for r in rej if isinstance(r, dict)]         if isinstance(rej, list) else []
    return {"style": lock.get("style"), "family": lock.get("family"),
            "references": [r.get("sha256") for r in style_lock_references(spec)], "rejections": rejections}


def qa_style_binding(spec, locate):
    lock = spec.get("style_lock") if isinstance(spec, dict) else None
    if not isinstance(lock, dict):
        return None
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    data = style.get("data") if isinstance(style.get("data"), dict) else {}
    anchors = []
    for pick in style_lock_references(spec):
        image = pick.get("image") if isinstance(pick.get("image"), str) and pick.get("image") else None
        try:
            digest = _file_sha256(locate(image)) if image else None
        except (OSError, TypeError, ValueError):
            digest = None
        anchors.append({"anchor_id": pick.get("anchor_id"), "path": image, "sha256": digest})
    return {"style": lock.get("style"), "style_sha256": _canonical_sha256(data),
            "family": lock.get("family") if isinstance(lock.get("family"), str) else None, "anchors": anchors}


def typed_param(name, decl, value):
    """value coerced to the param type of its template declaration; raises ValueError naming the param."""
    t = decl.get("type")
    if t == "int" and not isinstance(value, int):
        value = int(value)
    elif t == "number" and not isinstance(value, (int, float)):
        value = float(value)
    elif t == "bool" and not isinstance(value, bool):
        if str(value).lower() not in ("true", "false"):
            raise ValueError("param %s: expected true or false, got %r" % (name, value))
        value = str(value).lower() == "true"
    elif t in ("string", "enum"):
        value = str(value)
    if t == "enum" and value not in decl.get("options", []):
        raise ValueError("param %s: %r is not one of %s" % (name, value, decl.get("options")))
    return value


def rendered_params(workflow, spec):
    """(params, source): the resolved spec params with each template param the template workflow places read back from
    workflow (a whole "{{name}}" value as is, a placeholder inside a string by matching the template string), so a
    render --param shows. source is "workflow.json", or "spec.json" without a workflow. The prompt is not a param here."""
    spec = spec if isinstance(spec, dict) else {}
    params = dict(spec["params"]) if isinstance(spec.get("params"), dict) else {}
    tmpl = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    data = tmpl.get("data") if isinstance(tmpl.get("data"), dict) else {}
    if not isinstance(workflow, dict) or not isinstance(data.get("workflow"), dict):
        return params, "spec.json"
    declared = data.get("params") if isinstance(data.get("params"), dict) else {}
    found = {}

    def walk(t, r):
        if isinstance(t, dict) and isinstance(r, dict):
            for k, v in t.items():
                if k in r:
                    walk(v, r[k])
        elif isinstance(t, list) and isinstance(r, list) and len(t) == len(r):
            for a, b in zip(t, r):
                walk(a, b)
        elif isinstance(t, str):
            whole = PLACEHOLDER.fullmatch(t.strip())
            if whole:
                found.setdefault(whole.group(1), r)
                return
            names = PLACEHOLDER.findall(t)
            if names and isinstance(r, str):
                pattern = "".join("(.*?)" if i % 2 else re.escape(part)
                                  for i, part in enumerate(PLACEHOLDER.split(t)))
                m = re.fullmatch(pattern, r, re.S)
                for name, value in zip(names, m.groups() if m else ()):
                    found.setdefault(name, value)
    walk(data["workflow"], workflow)
    for name, value in found.items():
        if name == "prompt" or not isinstance(declared.get(name), dict):
            continue
        try:
            params[name] = typed_param(name, declared[name], value)
        except (ValueError, TypeError):
            params[name] = value
    return params, "workflow.json"


def requirements_sha256(spec, generation=None):
    spec = spec if isinstance(spec, dict) else {}

    def ref(key):
        r = spec.get(key)
        return r.get("sha256") if isinstance(r, dict) else None
    params = spec.get("params")
    obj = {"purpose": ref("purpose"), "style": ref("style"), "template": ref("template"),
           "params": params if isinstance(params, dict) else {}, "generation": generation}
    lock = style_lock_binding(spec)
    if lock is not None:  # only with the style lock: older specs keep their hash
        obj["style_lock"] = lock
    return _canonical_sha256(obj)


def requested_size(workflow, spec):
    spec = spec if isinstance(spec, dict) else {}
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    data = template.get("data") if isinstance(template.get("data"), dict) else {}
    primary = data.get("primary_node")
    node = None
    if isinstance(workflow, dict):
        if isinstance(primary, str) and isinstance(workflow.get(primary), dict):
            node = workflow[primary]
        else:
            candidates = [(nid, n) for nid, n in workflow.items()
                          if isinstance(n, dict) and n.get("class_type") == "NineRouterImage"]
            if candidates:
                def order(item):
                    nid = str(item[0])
                    if nid.isdigit():
                        try:
                            return (0, int(nid))
                        except ValueError:
                            pass
                    return (1, nid)
                node = min(candidates, key=order)[1]
        if isinstance(node, dict):
            inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
            if node.get("class_type") == "NineRouterImage":
                return inputs.get("size", "auto")
            if node.get("class_type") == "KSampler":
                link = inputs.get("latent_image")
                source = workflow.get(link[0]) if (isinstance(link, list) and len(link) == 2
                                                   and isinstance(link[0], str)) else None
                latent = source.get("inputs") if isinstance(source, dict) else None
                if (isinstance(source, dict) and source.get("class_type") == "EmptyLatentImage"
                        and isinstance(latent, dict) and type(latent.get("width")) is int
                        and type(latent.get("height")) is int and latent["width"] > 0 and latent["height"] > 0):
                    return "%dx%d" % (latent["width"], latent["height"])
    params = spec.get("params")
    return params.get("size", "auto") if isinstance(params, dict) else "auto"


def _outputs(value):
    if not isinstance(value, list):
        return []
    rows = [{"path": o.get("path"), "sha256": o.get("sha256")} for o in value if isinstance(o, dict)]
    return sorted((o for o in rows if isinstance(o["path"], str) and isinstance(o["sha256"], str)), key=lambda o: o["path"])


def _empty(state):
    return {"by": None, "state": state, "findings": 0, "prompt_sha256": None, "requirements_sha256": None, "outputs": []}


def read_verdict(path, phase):
    if not os.path.isfile(path):
        return _empty("NOT_RUN")
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    obj = None
    for candidate in [text] + re.findall(r"\{.*\}", text, re.S):
        try:
            obj = json.loads(candidate)
            break
        except ValueError:
            continue
    if not isinstance(obj, dict) or obj.get("state") not in ("PASS", "FAIL"):
        return _empty("INVALID")

    def digest(key):
        v = obj.get(key)
        return v if isinstance(v, str) and SHA256.match(v) else None
    findings = obj.get("findings")
    out = {"by": obj.get("by") if isinstance(obj.get("by"), str) and obj.get("by") else None, "state": obj["state"],
           "findings": len(findings) if isinstance(findings, list) else 0,
           "prompt_sha256": digest("prompt_sha256"), "requirements_sha256": digest("requirements_sha256"),
           "outputs": _outputs(obj.get("outputs")) if phase == "image" else []}
    if phase == "image" and ("style" in obj or "anchors" in obj):
        out["style"] = obj.get("style") if isinstance(obj.get("style"), dict) else None
        out["anchors"] = _anchors(obj.get("anchors"))
    return out


def _anchors(value):
    if not isinstance(value, list):
        return []
    return [{"anchor_id": a.get("anchor_id"), "sha256": a.get("sha256")} for a in value
            if isinstance(a, dict) and isinstance(a.get("anchor_id"), str) and isinstance(a.get("sha256"), str)]
