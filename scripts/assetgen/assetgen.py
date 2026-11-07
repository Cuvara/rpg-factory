#!/usr/bin/env python3
"""asset-gen engine: purposes x styles x ComfyUI workflow templates -> a reviewed, QA'd, recorded generation run.

Usage:
  assetgen.py list [--kind purpose|style|template] [--authoring DIR] [--json]
  assetgen.py show ID [--kind K] [--authoring DIR] [--json]
  assetgen.py resolve --purpose P [--style S] [--template T] [--family F] [--style-override REASON] [--authoring DIR]
                      [--out FILE] [--verbose] [--json]
  assetgen.py render (--run RUN | --spec FILE --prompt-file FILE --out FILE) [--param NAME=VALUE]... [--authoring DIR]
  assetgen.py lint [PATH...] [--authoring DIR] [--json]
  assetgen.py review-cmd --phase prompt|image --run RUN [--codex BIN] [--no-write] [--authoring DIR] [--json]
  assetgen.py embed --run RUN [--authoring DIR] [--json]
  assetgen.py qa --run RUN [--authoring DIR] [--json]
  assetgen.py manifest --run RUN [--title T] [--prompt-author A] [--generated-by G] [--authoring DIR] [--json]
  assetgen.py publish --run RUN --comfy-url URL [--authoring DIR] [--json]
  assetgen.py promote-anchor --run RUN --output N|PATH --family F --dimensions a,b --strength S [--id ID]
                             [--authoring DIR] [--json]
  assetgen.py reject --type asset|direction --reason R [--text T] [--family F] [--run RUN --output N|PATH]
                     [--style S --authoring DIR] [--any-version] [--id ID] [--json]
  assetgen.py drift --authoring DIR [--json]

RUN is a run directory or a run id (<slug>-NNN): a value that is not an existing directory resolves to
<authoring>/assetgen/runs/<id>, with --authoring when given, else the top level of the git repository of the current
directory (resolve_run); when neither exists the error names the tried paths (exit 2).
resolve prints a short summary (purpose, style and template, params, hints, style lock, references, rejections,
warnings); --verbose adds the source of every param, hint and field, --json prints the whole spec.

Data layers (scripts/assetgen/layers.py): core purposes/styles/workflow templates under templates/assetgen/, a game
layer under <authoring>/assetgen/{purposes,styles,templates}/ that overrides (same id) or extends (deep merge, the
game wins) core ids. resolve --verbose prints the merged spec with the source file of every field and each param.
Param precedence, low to high: template default < style params < purpose params < render --param. The review prompts
list the params render used (rendered_params: read back from workflow.json, so a render --param shows; spec.json
params before the first render).
Hint precedence (data/precedence.json): a purpose's constraints.<field> (lighting, background, framing) replaces the
style hint of that name; resolve records spec.hints and marks the overridden style hint, review prompts use spec.hints.

Style lock (scripts/assetgen/stylelock.py): resolve picks the family (--family, else the purpose's default_family) and
the style (stylelock.choose: <authoring>/assetgen/project.json, its allowed_styles and families; a style outside them
or a deprecated style is refused unless --style-override REASON, recorded as spec.style_lock.override and in run.md;
without project.json the purpose default_style as before) and records spec.style_lock = {project, family,
family_source, style: {style_id, version, sha256}, override, max_references, references: the selected anchors (valid
active anchors of that style version, deterministic order, capped) with reason[] per pick, rejections: the relevant
ones}. render wires each selected anchor as a LoadImage (anchor-<id>.png) and a chain of ImageBatch nodes into
NineRouterImage.reference_images (an image-edit reference stays first). promote-anchor writes a proposed anchor from a
manifested run output (a person approves it); reject records a rejected asset or direction; drift lists gen-runs,
anchors and rejections recorded on an older style version or another style hash.

Run directory (<authoring>/assetgen/runs/<run-id>/, run-id = <slug>-NNN, e.g. iron-sword-icon-001):
  spec.json           resolve --out: resolved spec (purpose, style, template with sha256 content hashes, params)
  prompt.md           the final prompt text only (written by the prompt author; sent verbatim, reviewed verbatim)
  spec.json           resolve --out <run>/spec.json also sets the filename_prefix param to assetgen/<run-id>
                      (runfiles.run_filename_prefix): the one value render, the review prompts and run.md record
  workflow.json       render: ComfyUI API-format graph {"<id>": {"class_type", "inputs"}}, links [node_id, index];
                      runnable as is by comfy-mcp run_workflow. The prompt is the value of a PrimitiveStringMultiline
                      node titled "Prompt (Claude, Codex review <state>)" (state of review-prompt.json for this
                      prompt and spec: PASS, FAIL, STALE when its prompt_sha256 or requirements_sha256 differs,
                      INVALID or NOT_RUN; a verdict by another reviewer reads "review <by> <state>", its PASS as
                      WARN, e.g. "review SAME_MODEL:claude WARN") linked into NineRouterImage.user_prompt.
                      render --run refuses a spec.json whose filename_prefix is not assetgen/<run-id> and a
                      --param filename_prefix
  workflow.ui.json    render: the same graph as a ComfyUI frontend (LiteGraph) workflow, run id in extra.assetgen
                      (uiworkflow.py); written next to workflow.json (render --out X.json: X.ui.json)
  outputs/*.png       comfy-mcp fetch_outputs out_dir; embed then adds a `workflow` tEXt chunk (workflow.ui.json,
                      compact JSON) before IEND of each PNG that has none (prompt chunk kept, idempotent), so the
                      file QA and the reviews hash is the embedded one and dragging it into ComfyUI restores the graph
  references/<name>   image-edit: the original of each LoadImage reference (uploaded with comfy-mcp upload_file)
  references/anchor-<id>.png  render --run: a copy of each style-lock anchor spec.style_lock.references selected
                      (refused when the anchor's image no longer has the sha256 resolve selected); the agent uploads
                      every references/* file with comfy-mcp upload_file under its name before running
  review-prompt.json  Codex verdict {"state": "PASS|FAIL", "findings": [...], "by": "codex", "prompt_sha256": "...",
                      "requirements_sha256": "..."} (review-cmd prompt); the two hashes are the binding review-cmd
                      hands the reviewer to copy back: the prompt, and runfiles.requirements_sha256 of the purpose,
                      style and template content hashes and the resolved params
  review/tile-2x2.png review-cmd image, purposes with a tileable QA check: the output repeated 2x2 (seam preview,
                      passed with -i after the outputs; tile-2x2-<stem>.png per output when there are several).
                      Derived from the output pixels, never an output and never in the binding
  review-image.json   the same for the images (review-cmd image); its requirements_sha256 also covers the generation
                      inputs of workflow.json (runfiles.generation_inputs), and the binding adds "outputs": [{"path", "sha256"}] (runfiles.py; the
                      quality plugin FAILs a stale or unbound verdict once the run is proposed). With spec.style_lock
                      review-cmd also attaches the selected anchors (-i references/anchor-<id>.png after the outputs and
                      tiles; a missing or changed copy is refused), adds the rubric items "The image matches the attached
                      anchors ..." (when anchors are selected) and "Not repeated: <reason> - <text>" per relevant
                      rejection, and the binding adds "style" (the style ref) and "anchors" [{"anchor_id", "sha256"}].
                      The prompt review lists the direction rejections under "Must avoid". The image review states
                      qa.json's verdict as context only: size, alpha, corners, tileable and blank belong to QA, and
                      the reviewer is told not to re-grade them
  review-image-claude.json  Claude's own visual review, written by the agent: the same schema and binding (the
                      "binding" of review-cmd --phase image --json, judged against its "rubric") with "by": "claude". manifest records it as
                      spec.claude_image_review; the plugin WARNs when it is missing, unbound or stale. It never replaces
                      the independent review-image.json
  qa.json             qa: rpg-factory.validation/1 results per output, bound to the purpose content hash and the
                      requested size it graded with (purpose_sha256, requested_size). With spec.style_lock each output
                      also gets the style consistency rows style-palette, style-tone, style-edges, style-canvas
                      (qa.py, consistency.py): never required checks, WARN and NOT_AVAILABLE keep the qa state, a style
                      FAIL row (severity fail in the style data) fails it
  run.md              manifest: ---json front matter, kind gen-run, domain assetgen (see manifest())

Failed attempts: a run whose generation, QA or review failed for good keeps its directory without run.md; the next
attempt is <slug>-NNN+1 (fresh resolve, prompt, reviews). manifest of a run lists the lower-numbered sibling dirs of
its series (same slug) that have no run.md in spec.trace.failed_attempts.

Read-only except: resolve/render --out, render --run (workflow.json, workflow.ui.json, references/anchor-*.png), embed
(outputs/*.png), qa (qa.json), manifest (run.md) and review-cmd --phase image of a tileable purpose (review/tile-2x2.png)
in the given run dir, and promote-anchor (assetgen/styles/<style>/anchors/<id>.json + .png, status proposed only) and
reject (assetgen/styles/<style>/rejections/<id>.json) in the authoring repo; drift is read-only. review-cmd only prints a `codex exec --sandbox read-only` command with absolute paths (it works from any cwd);
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
import shutil
import subprocess
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
import stylelock  # noqa: E402
import uiworkflow  # noqa: E402

RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*-[0-9]{3}$")
REVIEW_FILES = {"prompt": "review-prompt.json", "image": "review-image.json"}
CLAUDE_REVIEW = "review-image-claude.json"  # Claude's own visual review: recorded, never replaces review-image.json
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


# -- resolve ---------------------------------------------------------------------------------------------------

def resolve_spec(purpose, style, template, authoring, family=None, override=None):
    """layers.resolve with the style lock: stylelock.choose picks the family and style (project.json, refusals and
    the override), then spec.style_lock records the project, family, style ref, override, the selected anchors and
    the relevant rejections."""
    choice = stylelock.choose(layers.load("purpose", purpose, authoring), authoring, family, style, override)
    spec = layers.resolve(purpose, choice["style_id"], template, authoring)
    ref = stylelock.style_ref(spec["style"])
    cap = stylelock.max_references(spec["purpose"]["data"], spec["template"]["data"])
    picks = stylelock.select_references(stylelock.valid_anchors(authoring, ref["style_id"]), ref, choice["family"],
                                        spec["purpose"]["data"].get("dimensions"), cap) if authoring else []
    rejections = stylelock.relevant_rejections(stylelock.load_rejections(authoring, ref["style_id"]), ref,
                                               choice["family"]) if authoring else []
    spec["style_lock"] = {"project": choice["project"], "family": choice["family"], "family_source": choice["family_source"],
                          "style": ref, "override": choice["override"], "max_references": cap, "references": picks,
                          "rejections": rejections}
    return spec


def style_lock_lines(lock):
    """Text lines of spec.style_lock (resolve output)."""
    st = lock["style"]
    lines = ["style lock: style %s v%s (sha256 %s), family %s%s, project %s" % (
        st["style_id"], st["version"] if st["version"] is not None else "-", st["sha256"][:12], lock["family"] or "-",
        " [%s]" % lock["family_source"] if lock["family_source"] else "", (lock["project"] or {}).get("path") or "none")]
    if lock["override"]:
        lines.append("style override: " + lock["override"])
    lines += ["reference %s  [%s]" % (r["anchor_id"], "; ".join(r["reason"])) for r in lock["references"]]         or ["references: none (max %d)" % lock["max_references"]]
    lines += ["rejection %s %s %s%s" % (r["id"], r["type"], r["reason"], ": " + r["text"] if r.get("text") else "") for r in lock["rejections"]]
    return lines


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


def prompt_review_state(run_dir, spec, prompt):
    """(state, by) of review-prompt.json for this prompt and spec: PASS/FAIL when bound to both (prompt_sha256 and
    requirements_sha256, as review-cmd --phase prompt hands them out), STALE when either differs or is missing; a PASS
    by a reviewer that is not Codex (a SAME_MODEL fallback) is WARN, as the quality plugin grades it. by is "codex"
    while no verdict exists (the title names the reviewer the run expects)."""
    v = runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["prompt"]), "prompt")
    if v["state"] not in ("PASS", "FAIL"):
        return v["state"], "codex"
    if (v["prompt_sha256"] != hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            or v["requirements_sha256"] != runfiles.requirements_sha256(spec, None)):
        return "STALE", v["by"]
    if v["state"] == "PASS" and not is_codex(v["by"]):
        return "WARN", v["by"]
    return v["state"], v["by"]


def is_codex(by):
    return re.split(r"[-_/.:@ ]", str(by or "").strip().lower(), maxsplit=1)[0] == "codex"


def review_title(title, state, by):
    """A node title with <state> filled; a verdict by another reviewer than Codex (or by none) never reads "Codex review"."""
    if not is_codex(by):
        title = title.replace("Codex review <state>", "review %s <state>" % (by or "without reviewer"))
    return title.replace("<state>", state)


def render(spec, prompt, overrides, run_id=None, review_state="NOT_RUN", reviewer="codex"):
    """(workflow, errors). Strict: undeclared params, missing required params and leftover placeholders are errors.
    run_id (render --run): spec.json must carry filename_prefix assetgen/<run_id> (bind_run) and --param may not
    change it. review_state replaces <state> in node titles (the prompt node's title); reviewer (the verdict's by)
    replaces "Codex review" there when it is not Codex (review_title)."""
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
    errors = wire_references(workflow, runfiles.style_lock_references(spec))
    if errors:
        return None, errors
    for node in workflow.values():
        meta = node.get("_meta") if isinstance(node, dict) else None
        if isinstance(meta, dict) and isinstance(meta.get("title"), str):
            meta["title"] = review_title(meta["title"], review_state, reviewer)
    e, _ = lint.check_graph(workflow, None)
    return workflow, e


def wire_references(workflow, picks):
    """Adds the selected style-lock anchors to workflow in place: one LoadImage per pick (image anchor-<id>.png) and
    a chain of ImageBatch nodes feeding NineRouterImage.reference_images. An existing reference_images link (image-edit)
    stays the first image. New node ids are the next free integers. Returns errors ([] when nothing to wire)."""
    if not picks:
        return []
    targets = [n for n in workflow.values() if isinstance(n, dict) and n.get("class_type") == "NineRouterImage"]
    if len(targets) != 1:
        return ["style lock: the template needs exactly one NineRouterImage node to take reference images, found %d" % len(targets)]
    inputs = targets[0]["inputs"]
    next_id = [max([int(k) for k in workflow if str(k).isdigit()] or [0])]

    def add(node):
        next_id[0] += 1
        workflow[str(next_id[0])] = node
        return [str(next_id[0]), 0]
    images = [inputs["reference_images"]] if lint.is_link(inputs.get("reference_images")) else []
    for pick in picks:
        aid = pick.get("anchor_id")
        if not isinstance(aid, str) or not stylelock.ID.match(aid):
            return ["style lock: reference %r has no valid anchor_id: resolve again" % (aid,)]
        images.append(add({"class_type": "LoadImage", "inputs": {"image": "anchor-%s.png" % aid},
                           "_meta": {"title": "Anchor %s (%s)" % (aid, pick.get("strength"))}}))
    link = images[0]
    for i, image in enumerate(images[1:], 1):
        link = add({"class_type": "ImageBatch", "inputs": {"image1": link, "image2": image},
                    "_meta": {"title": "Reference batch %d" % i}})
    inputs["reference_images"] = link
    return []


def copy_anchors(run_dir, spec):
    """render --run: copies each selected anchor PNG to <run>/references/anchor-<id>.png. Errors when an anchor is gone
    or its image no longer has the sha256 resolve selected (nothing is copied then)."""
    picks = runfiles.style_lock_references(spec)
    if not picks:
        return []
    runs = os.path.dirname(os.path.abspath(os.path.normpath(run_dir)))
    # the run's own authoring repo (<authoring>/assetgen/runs/<run-id>) wins over the path resolve recorded
    authoring = os.path.dirname(os.path.dirname(runs)) if os.path.basename(runs) == "runs" \
        and os.path.basename(os.path.dirname(runs)) == "assetgen" else spec.get("authoring")
    style_id = ((spec.get("style_lock") or {}).get("style") or {}).get("style_id")
    if not authoring or not os.path.isdir(authoring) or not isinstance(style_id, str):
        return ["style lock: spec.json names anchors but no authoring repo or style: resolve again with --authoring"]
    records = {r["id"]: r for r in stylelock.load_anchors(authoring, style_id)}
    plan, errors = [], []
    for pick in picks:
        rec = records.get(pick.get("anchor_id"))
        src = os.path.join(os.path.dirname(rec["path"]), rec["data"].get("image") or "") if rec else None
        if not src or not os.path.isfile(src):
            errors.append("style lock: anchor %s of style %s is missing: resolve again" % (pick.get("anchor_id"), style_id))
        elif qa.sha256(src) != pick.get("sha256"):
            errors.append("style lock: anchor %s image changed since resolve (sha256 differs): resolve again" % pick.get("anchor_id"))
        else:
            plan.append((src, os.path.join(run_dir, "references", "anchor-%s.png" % pick["anchor_id"])))
    if errors:
        return errors
    for src, dst in plan:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    return []


def ui_path(out):
    return (out[:-5] if out.endswith(".json") else out) + ".ui.json"


def generation_inputs(run_dir, spec):
    wf = os.path.join(run_dir, "workflow.json")
    return runfiles.generation_inputs(read_json(wf, "workflow") if os.path.isfile(wf) else None, spec,
                                      lambda name: os.path.join(run_dir, "references", name))


def requested_size(run_dir, spec):
    wf = os.path.join(run_dir, "workflow.json")
    return runfiles.requested_size(read_json(wf, "workflow") if os.path.isfile(wf) else None, spec)


def rendered_params(run_dir, spec):
    """(params, source) of the params render used: spec.json params with each template param the template workflow
    places read back from workflow.json (a whole "{{name}}" value as is, a placeholder inside a string by matching the
    template string), so a render --param shows. source names workflow.json, or spec.json before the first render.
    The prompt is not a param here."""
    params = dict(spec.get("params") or {}) if isinstance(spec.get("params"), dict) else {}
    wf_path = os.path.join(run_dir, "workflow.json")
    workflow = read_json(wf_path, "workflow") if os.path.isfile(wf_path) else None
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
            whole = lint.PLACEHOLDER.fullmatch(t.strip())
            if whole:
                found.setdefault(whole.group(1), r)
                return
            names = lint.PLACEHOLDER.findall(t)
            if names and isinstance(r, str):
                pattern = "".join("(.*?)" if i % 2 else re.escape(part)
                                  for i, part in enumerate(lint.PLACEHOLDER.split(t)))
                m = re.fullmatch(pattern, r, re.S)
                for name, value in zip(names, m.groups() if m else ()):
                    found.setdefault(name, value)
    walk(data["workflow"], workflow)
    for name, value in found.items():
        if name == "prompt" or name not in declared:
            continue
        try:
            params[name] = typed(name, declared[name], value)
        except (ValueError, TypeError):
            params[name] = value
    return params, "workflow.json"


def workflow_model(run_dir, spec):
    wf = os.path.join(run_dir, "workflow.json")
    if os.path.isfile(wf):
        for node in read_json(wf, "workflow").values():
            if isinstance(node, dict) and node.get("class_type") == "NineRouterImage":
                return node.get("inputs", {}).get("model")
    return spec.get("params", {}).get("model")


# -- review-cmd ------------------------------------------------------------------------------------------------

ANCHOR_RUBRIC = "The image matches the attached anchors in palette, lighting, line, detail density and rendering."


def rejection_item(r):
    """The image rubric item of one relevant rejection of spec.style_lock."""
    text = r.get("text")
    if not text:
        run = r.get("run") if isinstance(r.get("run"), dict) else {}
        text = "the rejected asset %s %s" % (run.get("run_id") or "-", run.get("output") or "-")
    return "Not repeated: %s - %s" % (r.get("reason"), text)


def style_lock_rejections(spec):
    lock = spec.get("style_lock") if isinstance(spec.get("style_lock"), dict) else {}
    rej = lock.get("rejections")
    return [r for r in rej if isinstance(r, dict)] if isinstance(rej, list) else []


def review_rubric(spec, phase):
    """The rubric of a review: the purpose's prompt_rubric or image_rubric; with spec.style_lock the image phase adds
    the anchor item (when anchors are selected) and one item per relevant rejection. Claude's own visual review
    (review-image-claude.json) uses the same items (review-cmd --json prints them as rubric)."""
    rubric = list(spec["purpose"]["data"].get("prompt_rubric" if phase == "prompt" else "image_rubric", []))
    if phase == "image":
        if runfiles.style_lock_references(spec):
            rubric.append(ANCHOR_RUBRIC)
        rubric += [rejection_item(r) for r in style_lock_rejections(spec)]
    return rubric


DETERMINISTIC = "size, alpha, corners, tileable, blank"


def review_prompt_text(phase, spec, prompt, images, qa_report, binding, sizes=(), tiles=(), anchors=(), params=None):
    """params: (values, source) of rendered_params; spec.json params when None."""
    p, s = spec["purpose"], spec["style"]
    values, source = params if params is not None else (spec.get("params", {}), "spec.json")
    rubric = review_rubric(spec, phase)
    forbidden = s["data"].get("forbidden") if isinstance(s["data"].get("forbidden"), list) else []
    lines = [
        "You are the independent %s reviewer of an asset-gen run (purpose %s, style %s, template %s)."
        % (phase, p["id"], s["id"], spec["template"]["id"]),
        "Do not modify any file. Judge only against the rubric and the requirements below.",
        "", "Purpose: %s - %s" % (p["data"].get("title", ""), p["data"].get("description", "")),
        "Style: %s. Prefix: %s Suffix: %s" % (s["data"].get("title", ""), s["data"].get("prefix", ""), s["data"].get("suffix", "")),
        "Style avoid: %s" % ", ".join(s["data"].get("avoid", [])),
        "Style forbidden (never in the prompt or the image): %s" % (", ".join(
            x for x in forbidden if isinstance(x, str)) or "none"),
        "Style outline: %s" % (stylelock.hint_text(s["data"].get("outline")) or "none"),
        "Style shape language: %s" % (stylelock.hint_text(s["data"].get("shape_language")) or "none"),
        "Hints (the purpose wins for technical constraints): %s" % ("; ".join(
            "%s: %s" % (k, h["text"]) for k, h in sorted(effective_hints(spec).items())) or "none"),
        "Requested params (%s): %s" % (source, ", ".join("%s=%s" % (k, v) for k, v in sorted(values.items()))),
    ]
    guide = p["data"].get("prompt", {})
    if phase == "prompt":
        lines += ["Prompt guidance: " + " ".join(guide.get("guidance", [])),
                  "Must include: " + ", ".join(guide.get("must_include", [])),
                  "Must avoid: " + ", ".join(list(guide.get("avoid", [])) + [
                      "%s (rejected direction %s)" % (r.get("text"), r.get("id")) for r in style_lock_rejections(spec)
                      if r.get("type") == "direction" and r.get("text")])]
    lines += ["", "Rubric:"] + ["%d. %s" % (i + 1, r) for i, r in enumerate(rubric)]
    lines += ["", "Prompt under review:" if phase == "prompt" else "Prompt that produced the images:", prompt]
    if phase == "image":
        lines += ["", "Attached images (one per -i): " + ", ".join(list(images) + [t for t, _ in tiles] + [a for a, _ in anchors])]
        lines += ["True pixel size (PNG header) of %s: %s" % (i, z) for i, z in zip(images, sizes)]
        lines += ["%s is not an output: review-cmd tiled %s 2x2 so you can judge its seams" % (t, src) for t, src in tiles]
        lines += ["%s is not an output: style anchor %s (%s; %s) of style %s, approved by a person; judge the outputs "
                  "against it" % (a, pick.get("anchor_id"), pick.get("strength"), ", ".join(pick.get("dimensions") or []) or "-",
                                  ((spec.get("style_lock") or {}).get("style") or {}).get("style_id")) for a, pick in anchors]
        if qa_report:
            lines += ["Deterministic QA: %s (%s); context only, qa.json is graded separately" % (qa_report.get("state"), "; ".join(
                "%s %s %s" % (r["state"], r["output"], r["check"]) for r in qa_report.get("results", []) if r["state"] != "PASS") or "all checks PASS")]
        else:
            lines += ["Deterministic QA: NOT_RUN; it is graded separately (qa.json)"]
        lines += ["Deterministic checks (%s) belong to QA only: do not re-grade them. The pixel sizes and the QA verdict "
                  "above are context; never fail a rubric item, or report a finding, for a size or another deterministic "
                  "check unless that rubric item asks for it. Grade each rubric item only on what it asks." % DETERMINISTIC]
    bound = ", ".join("%s: %s" % (json.dumps(k), json.dumps(v, sort_keys=True)) for k, v in sorted(binding.items()))
    lines += ["", "Answer with exactly one JSON object and nothing else:",
              '{"state": "PASS" or "FAIL", "findings": [{"rubric": <item number>, "severity": "blocker|major|minor", '
              '"text": "<finding>"}], "by": "codex", ' + bound + "}",
              "state is FAIL when any rubric item is not met with a blocker or major finding.",
              "Copy these binding fields unchanged into your answer; they name what you reviewed: " + bound]
    text = "\n".join(lines)
    return "\n".join(l if l.strip() != HEREDOC else l + "." for l in text.splitlines())


def effective_hints(spec):
    """spec.hints (resolve); a spec written before hints existed is resolved from its recorded purpose and style."""
    if isinstance(spec.get("hints"), dict):
        return spec["hints"]
    return layers.resolve_hints({"data": spec["purpose"]["data"], "sources": {}}, {"data": spec["style"]["data"], "sources": {}})


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


def review_anchors(run_dir, spec):
    """[(references/anchor-<id>.png, pick)] of the anchors spec.style_lock selected, in selection order. Exits 1 when
    a run copy is missing or no longer has the sha256 resolve selected (render --run copies them)."""
    out = []
    for pick in runfiles.style_lock_references(spec):
        rel = pick.get("image") if isinstance(pick.get("image"), str) else "references/anchor-%s.png" % pick.get("anchor_id")
        path = os.path.join(run_dir, *rel.split("/"))
        if not os.path.isfile(path):
            fail("%s is missing: run scripts/assetgen/assetgen.py render --run %s (it copies the selected anchors)"
                 % (rel, run_dir.replace(os.sep, "/")))
        if qa.sha256(path) != pick.get("sha256"):
            fail("%s is not the anchor resolve selected (sha256 differs): resolve and render again" % rel)
        out.append((rel, pick))
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
    anchors = review_anchors(run_dir, spec) if phase == "image" else []
    lock = spec.get("style_lock")
    if phase == "image" and isinstance(lock, dict):
        binding["style"] = lock.get("style")
        binding["anchors"] = [{"anchor_id": pick.get("anchor_id"), "sha256": pick.get("sha256")} for _, pick in anchors]
    stdin = review_prompt_text(phase, spec, prompt, rel, qa_report, binding, sizes, tiles, anchors,
                               rendered_params(run_dir, spec))
    verdict = os.path.join(run_dir, REVIEW_FILES[phase]).replace(os.sep, "/")
    argv = [codex, "exec", "--sandbox", "read-only", "-C", run_dir.replace(os.sep, "/")]
    for i in images + [os.path.join(run_dir, *t.split("/")) for t, _ in tiles + anchors]:
        argv += ["-i", i.replace(os.sep, "/")]
    argv += ["-o", verdict, "-"]
    shell = "%s <<'%s'\n%s\n%s" % (shlex.join(argv), HEREDOC, stdin, HEREDOC)
    return {"schema": "rpg-factory.assetgen-review-cmd/1", "phase": phase, "argv": argv, "stdin": stdin,
            "verdict": verdict, "binding": binding, "shell": shell, "tiles": [t for t, _ in tiles],
            "anchors": [a for a, _ in anchors], "rubric": review_rubric(spec, phase)}


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


def failed_attempts(run_dir):
    """Run ids of the earlier attempts of this run's series (<slug>-NNN, lower NNN) whose directory has no run.md."""
    name = os.path.basename(os.path.normpath(run_dir))
    slug, num = name.rsplit("-", 1)
    parent = os.path.dirname(os.path.abspath(os.path.normpath(run_dir)))
    out = []
    for other in sorted(os.listdir(parent)):
        o_slug, _, o_num = other.rpartition("-")
        if RUN_ID.match(other) and o_slug == slug and int(o_num) < int(num)                 and os.path.isdir(os.path.join(parent, other)) and not os.path.isfile(os.path.join(parent, other, "run.md")):
            out.append(other)
    return out


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
            "params": rendered_params(run_dir, spec)[0],
            "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt_author": prompt_author,
            "prompt_review": runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["prompt"]), "prompt"),
            "generation": {"generated_by": generated_by, "tool": "comfyui", "model": model,
                           "workflow": "workflow.json" if os.path.isfile(os.path.join(run_dir, "workflow.json")) else None},
            "outputs": outputs, "qa": qa_block,
            "image_review": runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["image"]), "image"),
            "claude_image_review": runfiles.read_verdict(os.path.join(run_dir, CLAUDE_REVIEW), "image"),
            "trace": {"failed_attempts": failed_attempts(run_dir)},
        },
    }
    if isinstance(spec.get("style_lock"), dict):  # a spec from before the style lock keeps its run.md shape
        front["spec"]["style_lock"] = spec["style_lock"]
    return front, bool(old.get("status")) and not same_outputs and old.get("status") != "proposed"


def manifest_text(front):
    s = front["spec"]
    body = ["# " + front["title"], "",
            "- Purpose: `%s` (%s), style `%s`, template `%s`" % (s["purpose"]["id"], s["purpose"]["layer"], s["style"]["id"], s["template"]["id"]),
            "- Prompt review: %s by %s" % (s["prompt_review"]["state"], s["prompt_review"]["by"] or "-"),
            "- Generation: %s, model `%s`" % (s["generation"]["tool"], s["generation"]["model"] or "-"),
            "- QA: %s" % s["qa"]["state"],
            "- Image review: %s by %s" % (s["image_review"]["state"], s["image_review"]["by"] or "-"),
            "- Claude visual review: %s by %s%s" % (s["claude_image_review"]["state"], s["claude_image_review"]["by"] or "-",
                                                     ", %d finding(s)" % s["claude_image_review"]["findings"] if s["claude_image_review"]["findings"] else ""),
            "- Failed attempts: %s" % (", ".join(s["trace"]["failed_attempts"]) or "none")]
    lock = s.get("style_lock")
    if isinstance(lock, dict):
        st = lock.get("style") or {}
        body.append("- Style lock: style `%s` v%s, family %s, project %s, references: %s" % (
            st.get("style_id"), st.get("version") if st.get("version") is not None else "-", lock.get("family") or "-",
            (lock.get("project") or {}).get("path") or "none",
            ", ".join("`%s`" % r.get("anchor_id") for r in lock.get("references") or [] if isinstance(r, dict)) or "none"))
        if lock.get("override"):
            body.append("- Style override: %s" % lock["override"])
    body += ["- Status: %s (approval is human-only)" % front["status"], "", "## Prompt", "", s["prompt"], "", "## Outputs", ""]
    body += ["![%s](%s)" % (o["path"], o["path"]) for o in s["outputs"]] or ["(none)"]
    return "---json\n%s\n---\n%s\n" % (json.dumps(front, indent=2, ensure_ascii=True), "\n".join(body))


# -- style lock records: promote-anchor, reject ----------------------------------------------------------------

def run_authoring(run_dir):
    """(authoring repo, run id) of <authoring>/assetgen/runs/<run-id>; fails for any other layout."""
    full = os.path.abspath(os.path.normpath(run_dir))
    runs = os.path.dirname(full)
    if not RUN_ID.match(os.path.basename(full)) or os.path.basename(runs) != "runs" \
            or os.path.basename(os.path.dirname(runs)) != "assetgen":
        fail("--run %s must be <authoring>/assetgen/runs/<slug>-NNN" % run_dir.replace(os.sep, "/"))
    return os.path.dirname(os.path.dirname(runs)), os.path.basename(full)


def run_output(run_dir, output):
    """The recorded output of a manifested run: (spec, {"path", "sha256"}, absolute path). output is a 1-based index
    into run.md spec.outputs or its path (outputs/<name> or <name>). Fails when the file's sha256 is not the one
    run.md records, or qa.json records another sha256 for it."""
    front = existing_front(os.path.join(run_dir, "run.md"))
    if not isinstance(front, dict) or not isinstance(front.get("spec"), dict):
        fail("%s has no run.md front matter: run manifest first" % run_dir.replace(os.sep, "/"))
    recorded = [o for o in front["spec"].get("outputs") or [] if isinstance(o, dict) and isinstance(o.get("path"), str)]
    if str(output).isdigit():
        n = int(output)
        if not 1 <= n <= len(recorded):
            fail("--output %s: run.md records %d output(s)" % (output, len(recorded)))
        pick = recorded[n - 1]
    else:
        name = str(output).replace(os.sep, "/")
        name = name if name.startswith("outputs/") else "outputs/" + os.path.basename(name)
        match = [o for o in recorded if o["path"] == name]
        if not match:
            fail("--output %s is not an output recorded in run.md (%s)" % (output, ", ".join(o["path"] for o in recorded) or "none"))
        pick = match[0]
    path = os.path.join(run_dir, *pick["path"].split("/"))
    actual = qa.sha256(path) if os.path.isfile(path) else None
    if actual != pick.get("sha256"):
        fail("%s does not match run.md (recorded sha256 %s, file %s): run qa and manifest again"
             % (pick["path"], pick.get("sha256"), actual or "missing"))
    qa_path = os.path.join(run_dir, "qa.json")
    if os.path.isfile(qa_path):
        graded = {o.get("path"): o.get("sha256") for o in read_json(qa_path, "qa").get("outputs") or [] if isinstance(o, dict)}
        if graded.get(pick["path"]) != actual:
            fail("%s does not match qa.json (graded sha256 %s): run qa and manifest again" % (pick["path"], graded.get(pick["path"])))
    return front["spec"], {"path": pick["path"], "sha256": actual}, path


def run_style_ref(spec):
    """The style ref a run was resolved with: spec.style_lock.style, else built from the recorded style (a run from
    before the style lock: id, the recorded style data's version when known, content hash)."""
    lock = spec.get("style_lock")
    if isinstance(lock, dict) and isinstance(lock.get("style"), dict):
        return dict(lock["style"])
    st = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    if not isinstance(st.get("id"), str):
        fail("the run records no style")
    return {"style_id": st["id"], "version": stylelock.style_version(st.get("data") or {}), "sha256": st.get("sha256")}


def inside(path, root):
    path, root = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    return os.path.commonpath([path, root]) == root


def split_list(text):
    return [x.strip() for x in str(text or "").split(",") if x.strip()]


def promote_anchor(run_dir, output, family, dimensions, strength, anchor_id=None):
    """Writes <authoring>/assetgen/styles/<style-id>/anchors/<id>.json (status proposed, approved_by null) and copies
    the output PNG next to it as <id>.png. Never writes an active anchor: a person approves it."""
    authoring, run_id = run_authoring(run_dir)
    spec, out, src = run_output(run_dir, output)
    if not out["path"].lower().endswith(".png"):
        fail("%s is not a PNG output" % out["path"])
    ref = run_style_ref(spec)
    recorded = [o.get("path") for o in spec.get("outputs") or [] if isinstance(o, dict)]
    aid = anchor_id or "%s-%d" % (run_id, recorded.index(out["path"]) + 1)
    data = {"schema": stylelock.ANCHOR_SCHEMA, "id": aid, "status": "proposed", "style": ref, "family": family,
            "dimensions": split_list(dimensions), "strength": strength, "image": aid + ".png", "image_sha256": out["sha256"],
            "source_run": {"run_id": run_id, "output": out["path"], "sha256": out["sha256"]},
            "approved_by": None, "approved_on": None}
    errs = stylelock.anchor_errors(data, ref.get("style_id"), aid)
    if errs:
        fail("anchor not written: " + "; ".join(errs))
    target_dir = os.path.join(stylelock.style_dir(authoring, ref["style_id"]), "anchors")
    if not inside(target_dir, authoring):
        fail("style directory %s is outside the authoring repo %s" % (target_dir, authoring))
    target = os.path.join(target_dir, aid + ".json")
    if os.path.exists(target) or os.path.exists(os.path.join(target_dir, aid + ".png")):
        fail("anchor %s already exists in %s: pass another --id" % (aid, target_dir.replace(os.sep, "/")))
    os.makedirs(target_dir, exist_ok=True)
    shutil.copyfile(src, os.path.join(target_dir, aid + ".png"))
    write_json(target, data)
    return dict(data, path=os.path.relpath(target, authoring).replace(os.sep, "/"))


def next_rejection_id(folder, reason):
    """<reason>-NNN, the lowest free number in the rejections folder (deterministic, no clock)."""
    stem = reason.replace("_", "-")
    taken = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    n = 1
    while "%s-%03d.json" % (stem, n) in taken:
        n += 1
    return "%s-%03d" % (stem, n)


def reject(kind, reason, text=None, family=None, run_dir=None, output=None, style=None, authoring=None,
           any_version=False, rejection_id=None):
    """Writes <authoring>/assetgen/styles/<style-id>/rejections/<id>.json. An asset rejection names a run output (its
    style ref and family come from the run); a direction rejection names a style (--authoring and --style) and
    carries text. --any-version records version null (relevant to every version of the style). Data, not an approval."""
    run = None
    if kind == "asset":
        if not run_dir or output is None:
            fail("reject --type asset needs --run DIR and --output N|PATH", 2)
        auth, run_id = run_authoring(run_dir)
        if authoring and os.path.normcase(os.path.realpath(authoring)) != os.path.normcase(os.path.realpath(auth)):
            fail("--authoring %s is not the run's authoring repo %s" % (authoring, auth))
        authoring = auth
        spec, out, _ = run_output(run_dir, output)
        ref = run_style_ref(spec)
        if style and style != ref["style_id"]:
            fail("--style %s is not the run's style %s" % (style, ref["style_id"]))
        lock = spec.get("style_lock") if isinstance(spec.get("style_lock"), dict) else {}
        family = family or lock.get("family")
        run = {"run_id": run_id, "output": out["path"], "sha256": out["sha256"]}
    else:
        if run_dir or output is not None:
            fail("reject --type direction takes no --run or --output (use --type asset)", 2)
        if not authoring or not style:
            fail("reject --type direction needs --authoring DIR and --style S", 2)
        ref = stylelock.style_ref(layers.load("style", style, authoring))
    if any_version:
        ref["version"] = None
    data = {"schema": stylelock.REJECTION_SCHEMA, "id": None, "type": kind, "style": ref, "family": family or None,
            "reason": reason}
    if text:
        data["text"] = text
    if run:
        data["run"] = run
    folder = os.path.join(stylelock.style_dir(authoring, ref["style_id"]), "rejections")
    data["id"] = rejection_id or next_rejection_id(folder, str(reason))
    errs = stylelock.rejection_errors(data, ref["style_id"], data["id"])
    if errs:
        fail("rejection not written: " + "; ".join(errs))
    if not inside(folder, authoring):
        fail("style directory %s is outside the authoring repo %s" % (folder, authoring))
    target = os.path.join(folder, data["id"] + ".json")
    if os.path.exists(target):
        fail("rejection %s already exists in %s: pass another --id" % (data["id"], folder.replace(os.sep, "/")))
    write_json(target, data)
    return dict(data, path=os.path.relpath(target, authoring).replace(os.sep, "/"))


def drift_text(report):
    rows = []
    for i in report["items"]:
        st, cur = i["style"], i["current"]
        now = "v%s %s" % (cur["version"], (cur["sha256"] or "")[:12]) if cur else "missing"
        rows.append("%s %s %s (%s): recorded %s v%s %s, current %s" % (
            i["state"], i["kind"], i["id"], i["path"], st["style_id"], st.get("version") if st.get("version") is not None else "-",
            (st.get("sha256") or "-")[:12], now))
    return "\n".join(rows + ["assetgen drift: %d item(s) behind the current style" % len(report["items"])])


# -- CLI -------------------------------------------------------------------------------------------------------

def git_toplevel():
    """The top level of the git repository of the current directory, or None."""
    try:
        res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    top = res.stdout.strip() if res.returncode == 0 else ""
    return top or None


def resolve_run(value, authoring):
    """--run: an existing directory as is, else a run id under <authoring>/assetgen/runs/ (--authoring, else the
    current git repository's top level). Exits 2 naming the tried paths when neither exists."""
    if os.path.isdir(value):
        return value
    tried = [value]
    if RUN_ID.match(value):
        root = authoring or git_toplevel()
        if root:
            candidate = os.path.join(root, "assetgen", "runs", value)
            if os.path.isdir(candidate):
                return candidate
            tried.append(candidate)
        else:
            tried.append("<authoring>/assetgen/runs/%s (no --authoring and the current directory is not in a git "
                         "repository)" % value)
    fail("--run %s: no run directory at %s (pass a run directory, or a run id <slug>-NNN with --authoring DIR or from "
         "inside the authoring repository)" % (value, " or ".join(t.replace(os.sep, "/") for t in tried)), 2)


def resolve_text(spec, verbose):
    """resolve's text output: a short summary; verbose adds the source of every param, hint and field."""
    head = ["purpose %s (%s), style %s (%s), template %s (%s)" % tuple(
        x for k in ("purpose", "style", "template") for x in (spec[k]["id"], spec[k]["layer"]))]
    if verbose:
        return "\n".join(head
                         + ["param %s = %s  [%s]" % (k, v, spec["param_sources"][k]) for k, v in sorted(spec["params"].items())]
                         + ["hint %s = %s  [%s%s]" % (k, h["text"], h["source"], "; style hint overridden by the purpose" if "overrides" in h else "")
                            for k, h in sorted(spec["hints"].items())]
                         + style_lock_lines(spec["style_lock"])
                         + ["%s  [%s]" % (k, v) for k, v in sorted(spec["sources"].items())])
    lock = spec["style_lock"]
    lines = head + ["params: " + (", ".join("%s=%s" % (k, v) for k, v in sorted(spec["params"].items())) or "none"),
                    "hints: " + (", ".join("%s (%s%s)" % (k, h.get("from") or "-", ", overrides the style" if "overrides" in h else "")
                                           for k, h in sorted(spec["hints"].items())) or "none"),
                    style_lock_lines(lock)[0]]
    lines.append("references: " + (", ".join(r["anchor_id"] for r in lock["references"]) or "none")
                 + " (max %d)" % lock["max_references"])
    lines.append("rejections: " + (", ".join("%s (%s %s)" % (r["id"], r["type"], r["reason"]) for r in lock["rejections"]) or "none"))
    warnings = []
    if lock["override"]:
        warnings.append("style override: " + lock["override"])
    if spec.get("authoring") and not lock["project"]:
        warnings.append("no assetgen/project.json: the style is not locked by a project")
    if "filename_prefix" in spec["params"] and not str(spec["param_sources"].get("filename_prefix", "")).startswith("run id "):
        warnings.append("filename_prefix %s is not bound to a run: resolve --out <authoring>/assetgen/runs/<run-id>/spec.json"
                        % spec["params"]["filename_prefix"])
    lines += ["warning: " + w for w in warnings]
    lines.append("(sources of every param, hint and field: --verbose or --json)")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="assetgen.py", description="asset-gen engine (see module docstring)", allow_abbrev=False)
    subs = ap.add_subparsers(dest="cmd", required=True)

    def sp(name):
        return subs.add_parser(name, allow_abbrev=False)  # every subparser refuses abbreviated options
    c = sp("list"); c.add_argument("--kind", choices=list(layers.KINDS)); c.add_argument("--authoring"); c.add_argument("--json", action="store_true")
    c = sp("show"); c.add_argument("id"); c.add_argument("--kind", choices=list(layers.KINDS)); c.add_argument("--authoring"); c.add_argument("--json", action="store_true")
    c = sp("resolve"); c.add_argument("--purpose", required=True); c.add_argument("--style"); c.add_argument("--template")
    c.add_argument("--family"); c.add_argument("--style-override", metavar="REASON")
    c.add_argument("--authoring"); c.add_argument("--out")
    c.add_argument("--verbose", action="store_true", help="also print the source of every param, hint and field")
    c.add_argument("--json", action="store_true")
    run_help = ("run directory, or run id <slug>-NNN resolved under <authoring>/assetgen/runs/ (--authoring, else the "
                "current git repository)")
    auth_help = "authoring repo a --run id resolves in (default: the current git repository)"

    def run_arg(c, required=True):
        c.add_argument("--run", required=required, metavar="RUN", help=run_help)
        c.add_argument("--authoring", help=auth_help)
    c = sp("render"); run_arg(c, False); c.add_argument("--spec"); c.add_argument("--prompt-file"); c.add_argument("--out")
    c.add_argument("--param", action="append", default=[])
    c = sp("lint"); c.add_argument("paths", nargs="*"); c.add_argument("--authoring"); c.add_argument("--json", action="store_true")
    c = sp("review-cmd"); c.add_argument("--phase", choices=["prompt", "image"], required=True); run_arg(c)
    c.add_argument("--codex", default="codex"); c.add_argument("--no-write", action="store_true"); c.add_argument("--json", action="store_true")
    c = sp("embed"); run_arg(c); c.add_argument("--json", action="store_true")
    c = sp("publish"); run_arg(c); c.add_argument("--comfy-url", required=True)
    c.add_argument("--json", action="store_true")
    c = sp("qa"); run_arg(c); c.add_argument("--json", action="store_true")
    c = sp("promote-anchor"); run_arg(c); c.add_argument("--output", required=True)
    c.add_argument("--family", required=True); c.add_argument("--dimensions", required=True)
    c.add_argument("--strength", required=True, choices=list(stylelock.STRENGTHS)); c.add_argument("--id"); c.add_argument("--json", action="store_true")
    c = sp("reject"); c.add_argument("--type", required=True, choices=list(stylelock.REJECTION_TYPES), dest="kind")
    c.add_argument("--reason", required=True, choices=list(stylelock.REASONS)); c.add_argument("--text"); c.add_argument("--family")
    c.add_argument("--run", metavar="RUN", help=run_help); c.add_argument("--output"); c.add_argument("--style")
    c.add_argument("--authoring", help="authoring repo (direction rejections; a --run id resolves in it)")
    c.add_argument("--any-version", action="store_true"); c.add_argument("--id"); c.add_argument("--json", action="store_true")
    c = sp("drift"); c.add_argument("--authoring", required=True); c.add_argument("--json", action="store_true")
    c = sp("manifest"); run_arg(c); c.add_argument("--title")
    c.add_argument("--prompt-author", default="claude"); c.add_argument("--generated-by", default="claude"); c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    authoring = getattr(a, "authoring", None)
    if authoring and not os.path.isdir(authoring):
        fail("--authoring %s is not a directory" % authoring, 2)
    if getattr(a, "run", None):
        a.run = resolve_run(a.run, authoring)
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
            if a.family is not None and not stylelock.ID.match(a.family):
                fail("--family %r must be a lowercase id (characters, environment, props, ui, vfx, ...)" % a.family, 2)
            spec = resolve_spec(a.purpose, a.style, a.template, authoring, a.family, a.style_override)
            run_dir = os.path.dirname(os.path.abspath(a.out)) if a.out else ""
            if a.out and os.path.basename(a.out) == "spec.json" and RUN_ID.match(os.path.basename(run_dir)):
                spec = bind_run(spec, os.path.basename(run_dir))
            if a.out:
                write_json(a.out, spec)
            emit(spec, a.json, resolve_text(spec, a.verbose))
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
            prompt, spec = read_prompt(prompt_path), load_spec(spec_path)
            state, reviewer = prompt_review_state(a.run, spec, prompt) if a.run else ("NOT_RUN", "codex")
            workflow, errors = render(spec, prompt, a.param, run_id, state, reviewer)
            if not errors and a.run:
                errors = copy_anchors(a.run, spec)
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
            counts = {s: sum(1 for r in results if r["state"] == s) for s in ("PASS", "WARN", "FAIL", "NOT_AVAILABLE")}
            report = {"schema": "rpg-factory.validation/1", "tool": "assetgen-qa", "run": os.path.basename(os.path.normpath(a.run)),
                      "purpose": purpose.get("id"), "purpose_sha256": layers.content_hash(purpose.get("data")), "requested_size": size, "state": state, "results": results, "outputs": outputs, "summary": counts}
            write_json(os.path.join(a.run, "qa.json"), report)
            emit(report, a.json, "\n".join("%s %s %s: %s" % (r["state"], r["output"], r["check"], "; ".join(r["reasons"])) for r in results)
                 + "\nassetgen qa: %s (%d PASS, %s%d FAIL, %d NOT_AVAILABLE)" % (
                     state, counts["PASS"], "%d WARN, " % counts["WARN"] if counts["WARN"] else "", counts["FAIL"], counts["NOT_AVAILABLE"]))
            return {"PASS": 0, "FAIL": 1}.get(state, 3)
        if a.cmd == "promote-anchor":
            rec = promote_anchor(a.run, a.output, a.family, a.dimensions, a.strength, a.id)
            emit(rec, a.json, "wrote %s: anchor %s proposed (a person approves it: status active, approved_by, approved_on)"
                 % (rec["path"], rec["id"]))
            return 0
        if a.cmd == "reject":
            rec = reject(a.kind, a.reason, a.text, a.family, a.run, a.output, a.style, authoring, a.any_version, a.id)
            emit(rec, a.json, "wrote %s: %s rejection %s (%s)" % (rec["path"], rec["type"], rec["id"], rec["reason"]))
            return 0
        if a.cmd == "drift":
            report = stylelock.drift(authoring)
            emit(report, a.json, drift_text(report))
            return 0
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
