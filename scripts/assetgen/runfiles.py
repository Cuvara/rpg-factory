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
  workflow.json graph, prompts included (a workflow re-rendered with another prompt is stale; the plugin also checks
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
workflow_prompts(workflow) -> the prompts the 9router nodes send: their user_prompt, or the value of the prompt node
  (PrimitiveStringMultiline) it links to.
run_filename_prefix(run_id) -> assetgen/<run_id>, the SaveImage filename_prefix every record of the run carries.
reference_names(workflow) -> the LoadImage input names of a workflow (image-edit references).
required_checks(purpose_qa) -> the QA check names every output must carry for that purpose qa block (qa.py runs
  exactly these; the plugin requires a PASS row for each). Malformed input never raises.
qa_errors(purpose_qa) -> what is malformed in a purpose qa block ([] when valid). lint reports these, qa.py grades a
  run whose purpose qa block is malformed FAIL instead of guessing, and the plugin fails such a run.
requested_size(workflow, spec) -> the size the run asked for: the NineRouterImage size input of workflow.json, else
  the resolved spec's size param, else "auto". qa.json records it next to the purpose content hash it graded with
  (purpose_sha256), so a QA report made before the size or the purpose qa block changed is stale.
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
RUN_PREFIX = "assetgen/"


def run_filename_prefix(run_id):
    """The one filename_prefix of a run: resolve writes it into <run>/spec.json, render, the review prompts and run.md
    read it from there."""
    return RUN_PREFIX + run_id


def workflow_prompts(workflow):
    """The user_prompt inputs of the 9router nodes of a workflow (what was actually sent); a link to a prompt node
    (TEXT_NODES) gives that node's value, any other link stays as the link."""
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
    if isinstance(workflow, dict) and any(isinstance(n, dict) and n.get("class_type") == "NineRouterImage"
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


def style_lock_binding(spec):
    lock = spec.get("style_lock") if isinstance(spec, dict) else None
    if not isinstance(lock, dict):
        return None
    rej = lock.get("rejections")
    rejections = [{"id": r.get("id"), "sha256": _canonical_sha256(r)} for r in rej if isinstance(r, dict)]         if isinstance(rej, list) else []
    return {"style": lock.get("style"), "family": lock.get("family"),
            "references": [r.get("sha256") for r in style_lock_references(spec)], "rejections": rejections}


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
    if isinstance(workflow, dict):
        for node in workflow.values():
            if isinstance(node, dict) and node.get("class_type") == "NineRouterImage":
                inputs = node.get("inputs")
                return inputs.get("size", "auto") if isinstance(inputs, dict) else "auto"
    params = spec.get("params") if isinstance(spec, dict) else None
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
