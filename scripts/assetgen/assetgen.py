#!/usr/bin/env python3
"""asset-gen engine: purposes x styles x ComfyUI workflow templates -> a reviewed, QA'd, recorded generation run.

Usage:
  assetgen.py list [--kind purpose|style|template] [--authoring DIR] [--json]
  assetgen.py show ID [--kind K] [--authoring DIR] [--json]
  assetgen.py resolve --purpose P [--style S] [--template T] [--authoring DIR] [--out FILE] [--json]
  assetgen.py render (--run DIR | --spec FILE --prompt-file FILE --out FILE) [--param NAME=VALUE]...
  assetgen.py lint [PATH...] [--authoring DIR] [--json]
  assetgen.py review-cmd --phase prompt|image --run DIR [--codex BIN] [--no-write] [--json]
  assetgen.py embed --run DIR [--json]
  assetgen.py qa --run DIR [--json]
  assetgen.py manifest --run DIR [--title T] [--prompt-author A] [--generated-by G] [--json]
  assetgen.py publish --run DIR --comfy-url URL [--json]

Data layers (scripts/assetgen/layers.py): core purposes/styles/workflow templates under templates/assetgen/, a game
layer under <authoring>/assetgen/{purposes,styles,templates}/ that overrides (same id) or extends (deep merge, the
game wins) core ids. resolve prints the merged spec with the source file of every field and each param.
Param precedence, low to high: template default < style params < purpose params < render --param.

Run directory (<authoring>/assetgen/runs/<run-id>/, run-id = <slug>-NNN, e.g. iron-sword-icon-001):
  spec.json           resolve --out: resolved spec (purpose, style, template with sha256 content hashes, params)
  prompt.md           the final prompt text only (written by the prompt author; sent verbatim, reviewed verbatim)
  spec.json           resolve --out <run>/spec.json also sets the filename_prefix param to assetgen/<run-id>
                      (runfiles.run_filename_prefix): the one value render, the review prompts and run.md record
  workflow.json       render: ComfyUI API-format graph {"<id>": {"class_type", "inputs"}}, links [node_id, index];
                      runnable as is by comfy-mcp run_workflow. The prompt is the value of a PrimitiveStringMultiline
                      node titled "Prompt (Claude, Codex review <state>)" (state of review-prompt.json for this
                      prompt: PASS, FAIL, STALE, INVALID or NOT_RUN) linked into NineRouterImage.user_prompt.
                      render --run refuses a spec.json whose filename_prefix is not assetgen/<run-id> and a
                      --param filename_prefix
  workflow.ui.json    render: the same graph as a ComfyUI frontend (LiteGraph) workflow, run id in extra.assetgen
                      (uiworkflow.py); written next to workflow.json (render --out X.json: X.ui.json)
  outputs/*.png       comfy-mcp fetch_outputs out_dir; embed then adds a `workflow` tEXt chunk (workflow.ui.json,
                      compact JSON) before IEND of each PNG that has none (prompt chunk kept, idempotent), so the
                      file QA and the reviews hash is the embedded one and dragging it into ComfyUI restores the graph
  references/<name>   image-edit: the original of each LoadImage reference (uploaded with comfy-mcp upload_file)
  review-prompt.json  Codex verdict {"state": "PASS|FAIL", "findings": [...], "by": "codex", "prompt_sha256": "...",
                      "requirements_sha256": "..."} (review-cmd prompt); the two hashes are the binding review-cmd
                      hands the reviewer to copy back: the prompt, and runfiles.requirements_sha256 of the purpose,
                      style and template content hashes and the resolved params
  review/tile-2x2.png review-cmd image, purposes with a tileable QA check: the output repeated 2x2 (seam preview,
                      passed with -i after the outputs; tile-2x2-<stem>.png per output when there are several).
                      Derived from the output pixels, never an output and never in the binding
  review-image.json   the same for the images (review-cmd image); its requirements_sha256 also covers the generation
                      inputs of workflow.json (runfiles.generation_inputs), and the binding adds "outputs": [{"path", "sha256"}] (runfiles.py; the
                      quality plugin FAILs a stale or unbound verdict once the run is proposed)
  qa.json             qa: rpg-factory.validation/1 results per output, bound to the purpose content hash and the
                      requested size it graded with (purpose_sha256, requested_size)
  run.md              manifest: ---json front matter, kind gen-run, domain assetgen (see manifest())

Read-only except: resolve/render --out, render --run (workflow.json, workflow.ui.json), embed (outputs/*.png), qa
(qa.json), manifest (run.md) and review-cmd --phase image of a tileable purpose (review/tile-2x2.png) in the given run
dir. review-cmd only prints a `codex exec --sandbox read-only` command with absolute paths (it works from any cwd);
--no-write (factory-cmd always passes it) never builds the tile: it uses review/tile-2x2.png only when it holds
the current pixels, else exits 2. The only network call is publish: it POSTs workflow.ui.json to ComfyUI's userdata
API (/api/userdata/workflows%2Fassetgen%2F<run-id>.json?overwrite=true) so the run shows in the ComfyUI Workflows
sidebar under assetgen; it writes nothing locally (unreachable ComfyUI: NOT_AVAILABLE, exit 3). This script never
runs agents or ComfyUI. Model ids, sizes and other values live in template params data, not here.
Exit codes: 0 ok/PASS, 1 FAIL or error, 2 usage, 3 NOT_AVAILABLE (qa, publish). Options are never abbreviated (--ou
is not --out): allow_abbrev=False on every parser.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layers  # noqa: E402
import lint  # noqa: E402
import png  # noqa: E402
import qa  # noqa: E402
import runfiles  # noqa: E402
import uiworkflow  # noqa: E402

RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*-[0-9]{3}$")
REVIEW_FILES = {"prompt": "review-prompt.json", "image": "review-image.json"}
HEREDOC = "ASSETGEN_REVIEW"


def fail(msg, code=1):
    print("assetgen: " + msg, file=sys.stderr)
    sys.exit(code)


def emit(obj, as_json, text):
    print(json.dumps(obj, indent=1, sort_keys=True) if as_json else text)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")


def read_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        fail("cannot read %s %s: %s" % (what, path, exc))


def load_spec(path):
    spec = read_json(path, "spec")
    if spec.get("schema") != "rpg-factory.assetgen-spec/1":
        fail("%s is not a resolved spec (run resolve --out)" % path)
    return spec


def read_prompt(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError as exc:
        fail("cannot read prompt %s: %s" % (path, exc))
    if not text:
        fail("prompt %s is empty" % path)
    return text


# -- render ----------------------------------------------------------------------------------------------------

def typed(name, decl, value):
    """value coerced to the param type; raises ValueError naming the param."""
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


def fill(node, values):
    if isinstance(node, dict):
        return {k: fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, values) for v in node]
    if isinstance(node, str):
        whole = lint.PLACEHOLDER.fullmatch(node.strip())
        if whole and whole.group(1) in values:
            return values[whole.group(1)]
        return lint.PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), node)
    return node


def bind_run(spec, run_id):
    """spec with the run's filename_prefix (resolve --out <run>/spec.json), when the template declares the param."""
    if "filename_prefix" in spec["template"]["data"].get("params", {}):
        spec["params"]["filename_prefix"] = runfiles.run_filename_prefix(run_id)
        spec["param_sources"]["filename_prefix"] = "run id " + run_id
    return spec


def prompt_review_state(run_dir, prompt):
    """State of review-prompt.json for this prompt: PASS/FAIL when bound to it, STALE when bound to another prompt."""
    v = runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["prompt"]), "prompt")
    if v["state"] in ("PASS", "FAIL") and v["prompt_sha256"] != hashlib.sha256(prompt.encode("utf-8")).hexdigest():
        return "STALE"
    return v["state"]


def render(spec, prompt, overrides, run_id=None, review_state="NOT_RUN"):
    """(workflow, errors). Strict: undeclared params, missing required params and leftover placeholders are errors.
    run_id (render --run): spec.json must carry filename_prefix assetgen/<run_id> (bind_run) and --param may not
    change it. review_state replaces <state> in node titles (the prompt node's title)."""
    tmpl = spec["template"]["data"]
    declared = tmpl.get("params", {})
    values, errors = dict(spec.get("params", {})), []
    values["prompt"] = prompt
    if run_id and "filename_prefix" in declared and values.get("filename_prefix") != runfiles.run_filename_prefix(run_id):
        errors.append("spec.json records filename_prefix %r, run %s needs %r: resolve again with --out <run>/spec.json"
                      % (values.get("filename_prefix"), run_id, runfiles.run_filename_prefix(run_id)))
    for item in overrides:
        name, sep, value = item.partition("=")
        if not sep:
            errors.append("--param %r: expected NAME=VALUE" % item)
        elif name == "prompt":
            errors.append("--param prompt: the prompt comes from the prompt file only")
        elif name == "filename_prefix" and run_id:
            errors.append("--param filename_prefix: a run's prefix is %s, recorded in spec.json" % runfiles.run_filename_prefix(run_id))
        else:
            values[name] = value
    for name in sorted(values):
        if name not in declared:
            errors.append("param %s is not declared by template %s" % (name, spec["template"]["id"]))
            continue
        try:
            values[name] = typed(name, declared[name], values[name])
        except ValueError as exc:
            errors.append(str(exc))
    errors += ["param %s is required and has no value" % n for n, d in declared.items() if d.get("required") and n not in values]
    if errors:
        return None, errors
    workflow = fill(tmpl.get("workflow", {}), values)
    for node in workflow.values():
        meta = node.get("_meta") if isinstance(node, dict) else None
        if isinstance(meta, dict) and isinstance(meta.get("title"), str):
            meta["title"] = meta["title"].replace("<state>", review_state)
    e, _ = lint.check_graph(workflow, None)
    return workflow, e


def ui_path(out):
    return (out[:-5] if out.endswith(".json") else out) + ".ui.json"


def generation_inputs(run_dir, spec):
    wf = os.path.join(run_dir, "workflow.json")
    return runfiles.generation_inputs(read_json(wf, "workflow") if os.path.isfile(wf) else None, spec,
                                      lambda name: os.path.join(run_dir, "references", name))


def requested_size(run_dir, spec):
    wf = os.path.join(run_dir, "workflow.json")
    return runfiles.requested_size(read_json(wf, "workflow") if os.path.isfile(wf) else None, spec)


def workflow_model(run_dir, spec):
    wf = os.path.join(run_dir, "workflow.json")
    if os.path.isfile(wf):
        for node in read_json(wf, "workflow").values():
            if isinstance(node, dict) and node.get("class_type") == "NineRouterImage":
                return node.get("inputs", {}).get("model")
    return spec.get("params", {}).get("model")


# -- review-cmd ------------------------------------------------------------------------------------------------

def review_prompt_text(phase, spec, prompt, images, qa_report, binding, sizes=(), tiles=()):
    p, s = spec["purpose"], spec["style"]
    rubric = p["data"].get("prompt_rubric" if phase == "prompt" else "image_rubric", [])
    lines = [
        "You are the independent %s reviewer of an asset-gen run (purpose %s, style %s, template %s)."
        % (phase, p["id"], s["id"], spec["template"]["id"]),
        "Do not modify any file. Judge only against the rubric and the requirements below.",
        "", "Purpose: %s - %s" % (p["data"].get("title", ""), p["data"].get("description", "")),
        "Style: %s. Prefix: %s Suffix: %s" % (s["data"].get("title", ""), s["data"].get("prefix", ""), s["data"].get("suffix", "")),
        "Style avoid: %s" % ", ".join(s["data"].get("avoid", [])),
        "Requested params: %s" % ", ".join("%s=%s" % (k, v) for k, v in sorted(spec.get("params", {}).items())),
    ]
    guide = p["data"].get("prompt", {})
    if phase == "prompt":
        lines += ["Prompt guidance: " + " ".join(guide.get("guidance", [])),
                  "Must include: " + ", ".join(guide.get("must_include", [])),
                  "Must avoid: " + ", ".join(guide.get("avoid", []))]
    lines += ["", "Rubric:"] + ["%d. %s" % (i + 1, r) for i, r in enumerate(rubric)]
    lines += ["", "Prompt under review:" if phase == "prompt" else "Prompt that produced the images:", prompt]
    if phase == "image":
        lines += ["", "Attached images (one per -i): " + ", ".join(list(images) + [t for t, _ in tiles])]
        lines += ["True pixel size (PNG header) of %s: %s" % (i, z) for i, z in zip(images, sizes)]
        lines += ["%s is not an output: review-cmd tiled %s 2x2 so you can judge its seams" % (t, src) for t, src in tiles]
        if qa_report:
            lines += ["Deterministic QA: %s (%s)" % (qa_report.get("state"), "; ".join(
                "%s %s %s" % (r["state"], r["output"], r["check"]) for r in qa_report.get("results", []) if r["state"] != "PASS") or "all checks PASS")]
    bound = ", ".join("%s: %s" % (json.dumps(k), json.dumps(v, sort_keys=True)) for k, v in sorted(binding.items()))
    lines += ["", "Answer with exactly one JSON object and nothing else:",
              '{"state": "PASS" or "FAIL", "findings": [{"rubric": <item number>, "severity": "blocker|major|minor", '
              '"text": "<finding>"}], "by": "codex", ' + bound + "}",
              "state is FAIL when any rubric item is not met with a blocker or major finding.",
              "Copy these binding fields unchanged into your answer; they name what you reviewed: " + bound]
    text = "\n".join(lines)
    return "\n".join(l if l.strip() != HEREDOC else l + "." for l in text.splitlines())


def pixel_size(path, requested):
    try:
        with open(path, "rb") as f:
            w, h = png.header(f.read())[:2]
    except (OSError, png.Invalid) as exc:
        return "unreadable (%s)" % exc
    return "%dx%d (requested %s)" % (w, h, requested)


def tile_names(images):
    if len(images) == 1:
        return ["review/tile-2x2.png"]
    return ["review/tile-2x2-%s.png" % os.path.splitext(os.path.basename(i))[0] for i in images]


def review_tiles(run_dir, images, rel, write):
    """[(tile path relative to the run, source output)] of the 2x2 seam previews. write=False builds nothing: it uses a
    tile only when its bytes are what review-cmd would build now, else exits 2."""
    out = []
    for path, src, name in zip(images, rel, tile_names(images)):
        try:
            data = png.tile_2x2(png.decode(path))
        except (png.Invalid, png.Unsupported) as exc:
            print("assetgen: no tiled preview of %s: %s" % (src, exc), file=sys.stderr)
            continue
        target = os.path.join(run_dir, *name.split("/"))
        if write:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(data)
        else:
            try:
                with open(target, "rb") as f:
                    current = f.read() == data
            except OSError:
                current = False
            if not current:
                fail("%s is missing or stale and --no-write builds nothing: run scripts/assetgen/assetgen.py review-cmd "
                     "--phase image --run %s directly (the asset-gen skill)" % (name, run_dir.replace(os.sep, "/")), 2)
        out.append((name, src))
    return out


def review_cmd(run_dir, phase, codex, write=True):
    run_dir = os.path.abspath(run_dir)  # the printed command works from any cwd
    spec = load_spec(os.path.join(run_dir, "spec.json"))
    prompt = read_prompt(os.path.join(run_dir, "prompt.md"))
    images = []
    if phase == "image":
        images = sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))
        if not images:
            fail("no outputs/*.png in %s for the image review" % run_dir)
    qa_path = os.path.join(run_dir, "qa.json")
    qa_report = read_json(qa_path, "qa") if phase == "image" and os.path.isfile(qa_path) else None
    rel = [os.path.relpath(i, run_dir).replace(os.sep, "/") for i in images]
    binding = {"prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
               "requirements_sha256": runfiles.requirements_sha256(spec, generation_inputs(run_dir, spec) if phase == "image" else None)}
    if phase == "image":
        binding["outputs"] = [{"path": r, "sha256": qa.sha256(i)} for r, i in zip(rel, images)]
    sizes, tiles = [], []
    if phase == "image":
        requested = requested_size(run_dir, spec)
        sizes = [pixel_size(i, requested) for i in images]
        purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
        data = purpose.get("data") if isinstance(purpose.get("data"), dict) else {}
        if "png-tileable" in runfiles.required_checks(data.get("qa")):
            tiles = review_tiles(run_dir, images, rel, write)
    stdin = review_prompt_text(phase, spec, prompt, rel, qa_report, binding, sizes, tiles)
    verdict = os.path.join(run_dir, REVIEW_FILES[phase]).replace(os.sep, "/")
    argv = [codex, "exec", "--sandbox", "read-only", "-C", run_dir.replace(os.sep, "/")]
    for i in images + [os.path.join(run_dir, *t.split("/")) for t, _ in tiles]:
        argv += ["-i", i.replace(os.sep, "/")]
    argv += ["-o", verdict, "-"]
    shell = "%s <<'%s'\n%s\n%s" % (shlex.join(argv), HEREDOC, stdin, HEREDOC)
    return {"schema": "rpg-factory.assetgen-review-cmd/1", "phase": phase, "argv": argv, "stdin": stdin,
            "verdict": verdict, "binding": binding, "shell": shell, "tiles": [t for t, _ in tiles]}


# -- embed -----------------------------------------------------------------------------------------------------

def read_ui(run_dir):
    path = os.path.join(run_dir, "workflow.ui.json")
    ui = read_json(path, "UI workflow (run render --run first)")
    if not isinstance(ui, dict) or not isinstance(ui.get("nodes"), list):
        fail("%s is not a ComfyUI frontend workflow (run render --run again)" % path.replace(os.sep, "/"))
    return path, ui


def embed(run_dir):
    """Rows {output, state: embedded|kept|FAIL, reason}: the UI workflow as a `workflow` tEXt chunk of each output."""
    _, ui = read_ui(run_dir)
    text = json.dumps(ui, separators=(",", ":"), ensure_ascii=True)
    images = sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))
    if not images:
        fail("no outputs/*.png in %s to embed the workflow in" % run_dir.replace(os.sep, "/"))
    rows = []
    for path in images:
        name = "outputs/" + os.path.basename(path)
        with open(path, "rb") as f:
            data = f.read()
        try:
            if "workflow" in png.text_keywords(data):
                rows.append({"output": name, "state": "kept", "reason": "already carries a workflow chunk"})
                continue
            new = png.add_text(data, "workflow", text)
        except png.Invalid as exc:
            rows.append({"output": name, "state": "FAIL", "reason": str(exc)})
            continue
        tmp = path + ".embed.tmp"
        with open(tmp, "wb") as f:
            f.write(new)
        os.replace(tmp, path)
        rows.append({"output": name, "state": "embedded", "reason": "workflow chunk of %d bytes added" % len(text)})
    return rows


# -- publish ---------------------------------------------------------------------------------------------------

def publish(run_dir, comfy_url, timeout=15):
    """POST workflow.ui.json to ComfyUI's userdata API as workflows/assetgen/<run-id>.json (overwrite); writes nothing."""
    run_id = os.path.basename(os.path.normpath(run_dir))
    if not RUN_ID.match(run_id):
        fail("run dir name %r must be <slug>-NNN (lowercase, digits, dashes)" % run_id, 2)
    parts = urllib.parse.urlsplit(comfy_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        fail("--comfy-url must be the ComfyUI base address (http or https, host and port, no query)", 2)
    path, _ = read_ui(run_dir)
    with open(path, "rb") as f:
        body = f.read()
    target = "workflows/assetgen/%s.json" % run_id
    url = comfy_url.rstrip("/") + "/api/userdata/" + urllib.parse.quote(target, safe="") + "?overwrite=true"
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    result = {"schema": "rpg-factory.assetgen-publish/1", "run": run_id, "workflow": target, "comfy_url": comfy_url}
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as resp:
            result.update(state="PASS", http_status=resp.status,
                          reason="ComfyUI Workflows sidebar > assetgen > %s.json" % run_id)
    except urllib.error.HTTPError as exc:
        result.update(state="FAIL", http_status=exc.code, reason="ComfyUI refused the upload: HTTP %d %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError) as exc:
        result.update(state="NOT_AVAILABLE", http_status=None,
                      reason="ComfyUI is not reachable: %s" % getattr(exc, "reason", exc))
    return result


# -- manifest --------------------------------------------------------------------------------------------------

def existing_front(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        m = re.match(r"\A---json\s*\n(.*?)\n---", f.read(), re.S)
    try:
        return json.loads(m.group(1)) if m else None
    except ValueError:
        return None


def manifest(run_dir, title=None, prompt_author="claude", generated_by="claude"):
    """The gen-run front matter (and whether a previous status was reset)."""
    name = os.path.basename(os.path.normpath(run_dir))
    if not RUN_ID.match(name):
        fail("run dir name %r must be <slug>-NNN (lowercase, digits, dashes), e.g. iron-sword-icon-001" % name)
    spec = load_spec(os.path.join(run_dir, "spec.json"))
    prompt = read_prompt(os.path.join(run_dir, "prompt.md"))
    outputs = [{"path": "outputs/" + os.path.basename(p), "sha256": qa.sha256(p)}
               for p in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))]
    qa_path = os.path.join(run_dir, "qa.json")
    qa_report = read_json(qa_path, "qa") if os.path.isfile(qa_path) else None
    qa_block = {"state": qa_report.get("state"), "results": qa_report.get("results", [])} if qa_report else {"state": "NOT_RUN", "results": []}
    model = workflow_model(run_dir, spec)

    def ref(r):
        return {"id": r["id"], "layer": r["layer"], "files": r["files"], "sha256": r["sha256"]}
    old = existing_front(os.path.join(run_dir, "run.md")) or {}
    same_outputs = old.get("spec", {}).get("outputs") == outputs
    status = old.get("status") if old.get("status") and same_outputs else "proposed"
    front = {
        "id": "AGEN-" + name, "kind": "gen-run", "domain": "assetgen", "schema_version": 2, "status": status,
        "title": title or old.get("title") or "%s / %s generation run %s" % (spec["purpose"]["id"], spec["style"]["id"], name),
        "upstream": old.get("upstream", []), "sources": [o["path"] for o in outputs],
        "authors": old.get("authors") or [{"kind": "agent", "id": prompt_author}],
        "acceptance": old.get("acceptance") or [
            {"id": "AC-1", "text": "The prompt was reviewed by a model other than its author.", "verify": "review", "evidence": REVIEW_FILES["prompt"]},
            {"id": "AC-2", "text": "Deterministic image QA passes for every output.", "verify": "test", "evidence": "qa.json"},
            {"id": "AC-3", "text": "The images were reviewed against the purpose rubric.", "verify": "review", "evidence": REVIEW_FILES["image"]}],
        "trace": old.get("trace", []),
        "provenance": {"generated_by": generated_by, "tool": "comfyui", "model": model or ""},
        "spec": {
            "run_id": name, "purpose": ref(spec["purpose"]), "style": ref(spec["style"]), "template": ref(spec["template"]),
            "handoff_domain": spec["purpose"]["data"].get("handoff_domain"),
            "params": spec.get("params", {}),
            "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt_author": prompt_author,
            "prompt_review": runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["prompt"]), "prompt"),
            "generation": {"generated_by": generated_by, "tool": "comfyui", "model": model,
                           "workflow": "workflow.json" if os.path.isfile(os.path.join(run_dir, "workflow.json")) else None},
            "outputs": outputs, "qa": qa_block,
            "image_review": runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["image"]), "image"),
        },
    }
    return front, bool(old.get("status")) and not same_outputs and old.get("status") != "proposed"


def manifest_text(front):
    s = front["spec"]
    body = ["# " + front["title"], "",
            "- Purpose: `%s` (%s), style `%s`, template `%s`" % (s["purpose"]["id"], s["purpose"]["layer"], s["style"]["id"], s["template"]["id"]),
            "- Prompt review: %s by %s" % (s["prompt_review"]["state"], s["prompt_review"]["by"] or "-"),
            "- Generation: %s, model `%s`" % (s["generation"]["tool"], s["generation"]["model"] or "-"),
            "- QA: %s" % s["qa"]["state"],
            "- Image review: %s by %s" % (s["image_review"]["state"], s["image_review"]["by"] or "-"),
            "- Status: %s (approval is human-only)" % front["status"], "", "## Prompt", "", s["prompt"], "", "## Outputs", ""]
    body += ["![%s](%s)" % (o["path"], o["path"]) for o in s["outputs"]] or ["(none)"]
    return "---json\n%s\n---\n%s\n" % (json.dumps(front, indent=2, ensure_ascii=True), "\n".join(body))


# -- CLI -------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="assetgen.py", description="asset-gen engine (see module docstring)", allow_abbrev=False)
    subs = ap.add_subparsers(dest="cmd", required=True)

    def sp(name):
        return subs.add_parser(name, allow_abbrev=False)  # every subparser refuses abbreviated options
    c = sp("list"); c.add_argument("--kind", choices=list(layers.KINDS)); c.add_argument("--authoring"); c.add_argument("--json", action="store_true")
    c = sp("show"); c.add_argument("id"); c.add_argument("--kind", choices=list(layers.KINDS)); c.add_argument("--authoring"); c.add_argument("--json", action="store_true")
    c = sp("resolve"); c.add_argument("--purpose", required=True); c.add_argument("--style"); c.add_argument("--template")
    c.add_argument("--authoring"); c.add_argument("--out"); c.add_argument("--json", action="store_true")
    c = sp("render"); c.add_argument("--run"); c.add_argument("--spec"); c.add_argument("--prompt-file"); c.add_argument("--out")
    c.add_argument("--param", action="append", default=[])
    c = sp("lint"); c.add_argument("paths", nargs="*"); c.add_argument("--authoring"); c.add_argument("--json", action="store_true")
    c = sp("review-cmd"); c.add_argument("--phase", choices=["prompt", "image"], required=True); c.add_argument("--run", required=True)
    c.add_argument("--codex", default="codex"); c.add_argument("--no-write", action="store_true"); c.add_argument("--json", action="store_true")
    c = sp("embed"); c.add_argument("--run", required=True); c.add_argument("--json", action="store_true")
    c = sp("publish"); c.add_argument("--run", required=True); c.add_argument("--comfy-url", required=True)
    c.add_argument("--json", action="store_true")
    c = sp("qa"); c.add_argument("--run", required=True); c.add_argument("--json", action="store_true")
    c = sp("manifest"); c.add_argument("--run", required=True); c.add_argument("--title")
    c.add_argument("--prompt-author", default="claude"); c.add_argument("--generated-by", default="claude"); c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    authoring = getattr(a, "authoring", None)
    if authoring and not os.path.isdir(authoring):
        fail("--authoring %s is not a directory" % authoring, 2)
    try:
        if a.cmd == "list":
            items = layers.entries(a.kind, authoring)
            emit({"schema": "rpg-factory.assetgen-list/1", "entries": items}, a.json, "\n".join(
                "%-8s %-20s %-13s %s" % (e["kind"], e["id"], e["layer"], e.get("error") or e["title"]) for e in items))
            return 1 if any(e["layer"] == "error" for e in items) else 0
        if a.cmd == "show":
            e = layers.find(a.id, a.kind, authoring)
            emit(e, a.json, "%s %s (%s; %s)\n%s" % (e["kind"], e["id"], e["layer"], ", ".join(e["files"]), json.dumps(e["data"], indent=1)))
            return 0
        if a.cmd == "resolve":
            spec = layers.resolve(a.purpose, a.style, a.template, authoring)
            run_dir = os.path.dirname(os.path.abspath(a.out)) if a.out else ""
            if a.out and os.path.basename(a.out) == "spec.json" and RUN_ID.match(os.path.basename(run_dir)):
                spec = bind_run(spec, os.path.basename(run_dir))
            if a.out:
                write_json(a.out, spec)
            emit(spec, a.json, "\n".join(
                ["purpose %s (%s), style %s (%s), template %s (%s)" % tuple(x for k in ("purpose", "style", "template") for x in (spec[k]["id"], spec[k]["layer"]))]
                + ["param %s = %s  [%s]" % (k, v, spec["param_sources"][k]) for k, v in sorted(spec["params"].items())]
                + ["%s  [%s]" % (k, v) for k, v in sorted(spec["sources"].items())]))
            return 0
        if a.cmd == "render":
            if a.run:
                spec_path, prompt_path = os.path.join(a.run, "spec.json"), os.path.join(a.run, "prompt.md")
                out = a.out or os.path.join(a.run, "workflow.json")
            elif a.spec and a.prompt_file and a.out:
                spec_path, prompt_path, out = a.spec, a.prompt_file, a.out
            else:
                fail("render needs --run DIR or --spec, --prompt-file and --out", 2)
            run_id = os.path.basename(os.path.normpath(a.run)) if a.run else None
            prompt = read_prompt(prompt_path)
            state = prompt_review_state(a.run, prompt) if a.run else "NOT_RUN"
            workflow, errors = render(load_spec(spec_path), prompt, a.param, run_id, state)
            ui = None
            if not errors:
                try:
                    ui = uiworkflow.to_ui(workflow, lint.known_nodes(),
                                          {"assetgen": {"run_id": run_id, "workflow": os.path.basename(out)}})
                except ValueError as exc:
                    errors.append("workflow.ui.json: %s" % exc)
            if errors:
                print("\n".join("FAIL " + e for e in errors))
                return 1
            write_json(out, workflow)
            write_json(ui_path(out), ui)
            print("rendered %s (%d nodes) and %s" % (out, len(workflow), ui_path(out)))
            return 0
        if a.cmd == "lint":
            results = [lint.lint_file(p, authoring) for p in (a.paths or lint.default_paths(authoring))]
            counts = {s: sum(1 for r in results if r["state"] == s) for s in ("PASS", "WARN", "FAIL")}
            emit({"schema": "rpg-factory.validation/1", "tool": "assetgen-lint", "results": results, "summary": counts}, a.json,
                 "\n".join("%s %s%s" % (r["state"], r["path"], (": " + "; ".join(r["reasons"])) if r["reasons"] else "") for r in results)
                 + "\nassetgen lint: %(PASS)d PASS, %(WARN)d WARN, %(FAIL)d FAIL" % counts)
            return 1 if counts["FAIL"] else 0
        if a.cmd == "review-cmd":
            cmd = review_cmd(a.run, a.phase, a.codex, not a.no_write)
            emit(cmd, a.json, cmd["shell"])
            return 0
        if a.cmd == "embed":
            rows = embed(a.run)
            counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("embedded", "kept", "FAIL")}
            emit({"schema": "rpg-factory.assetgen-embed/1", "run": os.path.basename(os.path.normpath(a.run)), "results": rows,
                  "summary": counts}, a.json, "\n".join("%s %s: %s" % (r["state"], r["output"], r["reason"]) for r in rows)
                 + "\nassetgen embed: %(embedded)d embedded, %(kept)d kept, %(FAIL)d FAIL" % counts)
            return 1 if counts["FAIL"] else 0
        if a.cmd == "publish":
            res = publish(a.run, a.comfy_url)
            emit(res, a.json, "assetgen publish: %s %s (%s)" % (res["state"], res["workflow"], res["reason"]))
            return {"PASS": 0, "FAIL": 1}.get(res["state"], 3)
        if a.cmd == "qa":
            spec = load_spec(os.path.join(a.run, "spec.json"))
            size = requested_size(a.run, spec)
            results, outputs = qa.run_qa(a.run, spec, size)
            purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
            state = qa.overall(results)
            counts = {s: sum(1 for r in results if r["state"] == s) for s in ("PASS", "FAIL", "NOT_AVAILABLE")}
            report = {"schema": "rpg-factory.validation/1", "tool": "assetgen-qa", "run": os.path.basename(os.path.normpath(a.run)),
                      "purpose": purpose.get("id"), "purpose_sha256": layers.content_hash(purpose.get("data")), "requested_size": size, "state": state, "results": results, "outputs": outputs, "summary": counts}
            write_json(os.path.join(a.run, "qa.json"), report)
            emit(report, a.json, "\n".join("%s %s %s: %s" % (r["state"], r["output"], r["check"], "; ".join(r["reasons"])) for r in results)
                 + "\nassetgen qa: %s (%d PASS, %d FAIL, %d NOT_AVAILABLE)" % (state, counts["PASS"], counts["FAIL"], counts["NOT_AVAILABLE"]))
            return {"PASS": 0, "FAIL": 1}.get(state, 3)
        if a.cmd == "manifest":
            front, reset = manifest(a.run, a.title, a.prompt_author, a.generated_by)
            with open(os.path.join(a.run, "run.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(manifest_text(front))
            note = " (outputs changed: status reset to proposed)" if reset else ""
            emit(front, a.json, "wrote %s/run.md: %s %s%s" % (a.run.replace(os.sep, "/"), front["id"], front["status"], note))
            return 0
    except layers.SpecError as exc:
        fail(str(exc))
    return 2


if __name__ == "__main__":
    sys.exit(main())
