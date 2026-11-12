#!/usr/bin/env python3
"""asset-gen engine: purposes x styles x ComfyUI workflow templates -> a reviewed, QA'd, recorded generation run.

Usage:
  assetgen.py list [--kind purpose|style|template] [--authoring DIR] [--json]
  assetgen.py show ID [--kind K] [--authoring DIR] [--json]
  assetgen.py resolve --purpose P [--style S] [--template T] [--family F] [--style-override REASON] [--authoring DIR]
                      [--max-outputs N] [--out FILE] [--verbose] [--json]
  assetgen.py render (--run RUN | --spec FILE --prompt-file FILE --out FILE) [--param NAME=VALUE]... [--authoring DIR]
  assetgen.py lint [PATH...] [--authoring DIR] [--json]
  assetgen.py graph-lint [PATH...] [--run RUN] [--authoring DIR] [--json]
  assetgen.py review-cmd --phase prompt|image --run RUN [--codex BIN] [--no-write] [--authoring DIR] [--json]
  assetgen.py embed --run RUN [--authoring DIR] [--json]
  assetgen.py defringe --run RUN [--alpha-floor N] [--force] [--authoring DIR] [--json]
  assetgen.py qa --run RUN [--authoring DIR] [--json]
  assetgen.py finalize --run RUN [--force] [--authoring DIR] [--json]
  assetgen.py budget --run RUN [--authoring DIR] [--json]
  assetgen.py manifest --run RUN [--title T] [--prompt-author A] [--generated-by G] [--authoring DIR] [--json]
  assetgen.py publish --run RUN --comfy-url URL [--authoring DIR] [--json]
  assetgen.py promote-anchor --run RUN --output N|PATH --family F --dimensions a,b --strength S [--id ID]
                             [--authoring DIR] [--json]
  assetgen.py reject --type asset|direction --reason R [--text T] [--family F] [--run RUN --output N|PATH]
                     [--style S --authoring DIR] [--any-version] [--id ID] [--json]
  assetgen.py drift --authoring DIR [--json]
  assetgen.py approve-record --run RUN --by NAME [--note TEXT] [--authoring DIR] [--json]

RUN is a run directory or a run id (<slug>-NNN): a value that is not an existing directory resolves to
<authoring>/assetgen/runs/<id>, with --authoring when given, else the top level of the git repository of the current
directory (resolve_run); when neither exists the error names the tried paths (exit 2).
resolve prints a short summary (purpose, style and template, params, hints, style lock, references, rejections,
warnings: a selected anchor of another family than the run's, or the anchors anchor_family_fallback: false left out,
also recorded as spec.warnings); --verbose adds the source of every param, hint and field, --json prints the whole spec.

Workflow style guide (scripts/assetgen/graphstyle.py): every API node has a title and sits in exactly one group;
group titles come from Prompt, References, Generate, Post-process, Preview, Output, left to right in that order, each
with a Note; the reviewed prompt is linked directly from PrimitiveStringMultiline to NineRouterImage.user_prompt (in a
template that node holds {{prompt}}); exactly one NineRouterImage; every SaveImage sits in Output with an inline
filename suffix (intermediates use PreviewImage); no static LoadImage file name. lint adds one assetgen-graph-style row
per template (a legacy template without a ui block WARNs). graph-lint checks only that: each PATH is a template (layer
or standalone) or a ComfyUI frontend workflow (a JSON object with a "nodes" list, e.g. a run's workflow.ui.json);
--run RUN adds <run>/workflow.ui.json with SaveImage suffixes checked against assetgen/<run directory name> (a frontend
PATH uses its extra.assetgen.run_id; without one each SaveImage FAILs as unchecked); neither: every core and game
template. Exit 1 when a row FAILs, 0 otherwise (WARN included),
2 for usage (a PATH missing, not JSON or neither kind, a --run without workflow.ui.json).

Data layers (scripts/assetgen/layers.py): core purposes/styles/workflow templates under templates/assetgen/, a game
layer under <authoring>/assetgen/{purposes,styles,templates}/ that overrides (same id) or extends (deep merge, the
game wins) core ids. resolve --verbose prints the merged spec with the source file of every field and each param.
Param precedence, low to high: template default < style params < purpose params < render --param. The review prompts
list the params render used (rendered_params: read back from workflow.json, so a render --param shows; spec.json
params before the first render), and each review is bound to exactly those params.
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
anchors and rejections recorded on an older style version or another style hash, and with project.json those under a
style id that is neither the project style nor a family style (style-id-mismatch, naming the project style).

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
                      (uiworkflow.py); optional template ui supplies groups, ui_only Note nodes, node colors and row
                      hints, never included in workflow.json; written next to workflow.json (render --out X.json: X.ui.json)
  outputs/*.png       comfy-mcp fetch_outputs out_dir; for a purpose with alpha defringe rewrites them (below); embed
                      then adds a `workflow` tEXt chunk (workflow.ui.json, compact JSON) before IEND of each PNG (prompt
                      chunk kept; a PNG whose chunk is the current workflow.ui.json is kept byte for byte, a stale
                      chunk from an older render is replaced), so the file QA and the reviews hash is the embedded one
                      and dragging it into ComfyUI restores the graph
  outputs-raw/<name>  defringe: the original of each output it rewrote (kept; never an output, never in a binding)
  defringe.json       defringe: {"schema": "rpg-factory.assetgen-defringe/1", "params": {"alpha_floor", "rings",
                      "opaque"}, "outputs": [{"output", "raw", "before_sha256", "after_sha256", "after_pixels_sha256",
                      "stats"}]}
                      (imaging.defringe: opaque neighbour colour bled into the pixels with 0 < alpha < 224, alpha kept
                      except --alpha-floor N sets alpha below N to 0; text chunks carried over; a grayscale output
                      stays grayscale, as gray+alpha, with its GRAY iCCP; an iCCP profile of the other colour space
                      than the written colour type is dropped, in the review previews too). Run it after
                      fetch_outputs and before embed, qa and the reviews; run again, it starts from outputs-raw/, so
                      the result depends only on the originals and the params. It refuses an approved run.md, and
                      outputs that qa.json or an image review already bind unless --force (they are stale then and
                      must be re-run). manifest adds a "- Defringe:" line to the run.md body (STALE when an output's
                      pixels are no longer the ones defringe wrote; embed keeps them)
  references/<name>   image-edit: the original of each LoadImage reference (uploaded with comfy-mcp upload_file)
  references/anchor-<id>.png  render --run: a copy of each style-lock anchor spec.style_lock.references selected
                      (refused when the anchor's image no longer has the sha256 resolve selected); the agent uploads
                      every references/* file with comfy-mcp upload_file under its name before running
  review-prompt.json  Codex verdict {"state": "PASS|FAIL", "findings": [...], "by": "codex", "prompt_sha256": "...",
                      "requirements_sha256": "..."} (review-cmd prompt); the two hashes are the binding review-cmd
                      hands the reviewer to copy back: the prompt, and runfiles.requirements_sha256 of the purpose,
                      style and template content hashes and the rendered params the review prompt shows
                      (rendered_params: workflow.json after render, spec.json before), so a render --param that
                      changes a param after the review makes it STALE (the same params again keep it bound)
  review/tile-2x2.png review-cmd image, purposes with a tileable QA check: the output repeated 2x2 (seam preview,
                      passed with -i after the outputs; tile-2x2-<stem>.png per output when there are several).
                      Derived from the output pixels, never an output and never in the binding
  review/composite-dark.png, review/composite-light.png  review-cmd image: each output with transparent pixels
                      composited on #202020 and on #e0e0e0 (imaging.composite; composite-<stem>-dark.png etc. when
                      there are several outputs), attached with -i after the outputs and tiles, listed as "composites"
                      in --json, and the rubric gains the item "The edges of every output with alpha are clean on both
                      the dark and the light composite ...". Derived, never an output and never in the binding
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
                      requested size it graded with (purpose_sha256, requested_size) and to the style inputs of its style rows
                      (style_binding: runfiles.qa_style_binding, null without spec.style_lock). With spec.style_lock each output
                      also gets the style consistency rows style-palette, style-tone, style-edges, style-canvas
                      (qa.py, consistency.py): never required checks, WARN and NOT_AVAILABLE keep the qa state, a style
                      FAIL row (severity fail in the style data) fails it
  run.md              manifest: ---json front matter, kind gen-run, domain assetgen (see manifest()). A re-run keeps
                      an approved status while nothing the approval binds changed (approval.keep_status: the same
                      run.md bytes, so the record's rev still matches), else resets to proposed and names the change
  approvals/AGEN-<run-id>/assetgen-approval-<rev>.json  (authoring repo) approve-record --by NAME: a person's approval
                      (approval.approve_record: refuses an agent or model name and names the run records as agents or
                      reviewers; sets run.md status approved; rev = the git blob id of that run.md). An agent runs it
                      only on the person's explicit word; the person commits run.md and the record in one SSH-signed
                      commit whose signer principal is NAME (until then: present but not committed/signed)

finalize (scripts/assetgen/finalize.py): run it after fetch_outputs. It runs defringe (only for a purpose with qa.alpha
required), embed and qa in that fixed order, so embed can never be skipped before qa, and stops at the first FAIL naming
the step. Exit codes follow qa: 0 PASS, 1 FAIL, 3 NOT_AVAILABLE. It refuses (exit 1, nothing written) a run without
spec.json, outputs/*.png or a readable workflow.ui.json, and an approved run (rewriting approved bytes would fail
gen-run-outputs). A second finalize on an unchanged run is idempotent: defringe is skipped while defringe.json's
after_pixels_sha256 still equals every output that needs it (or no output needs it), embed keeps every output, qa is
rewritten. Outputs that qa.json or an image review already bind and that still need defringe stop it with FAIL at
defringe (defringe's own refusal) unless --force; --force is passed to defringe only. It prints which image reviews
(review-image.json, review-image-claude.json) it made stale ("stale now (re-run them): ..."; qa.json is rewritten, so
never listed). --json: one object, schema rpg-factory.assetgen-finalize/1 (steps, stale, state, exit, budget).

Spend guard (scripts/assetgen/budget.py): resolve records spec.budget = {"max_outputs": N} (--max-outputs N, default
4; not a whole number >= 1: exit 2). budget --run prints used (the run's outputs/*.png + the failed attempts of its
series), allowed and remaining; it exits 1 only when used exceeds allowed or spec.budget is malformed. A spec.json
without budget (resolved before the spend guard) is unlimited, never a failure. The limit is advisory: the engine cannot
stop comfy-mcp, so the asset-gen skill runs budget before each run_workflow. finalize prints the budget line before its
summary line (--json: key "budget") and keeps its own exit code.

Failed attempts: a run whose generation, QA or review failed for good keeps its directory without run.md; the next
attempt is <slug>-NNN+1 (fresh resolve, prompt, reviews). manifest of a run lists the lower-numbered sibling dirs of
its series (same slug) that have no run.md in spec.trace.failed_attempts.

Read-only verbs: list, show, resolve (without --out), lint, drift and review-cmd --no-write (factory-cmd forwards only
these), graph-lint and budget. The others write: resolve/render --out, render --run (workflow.json, workflow.ui.json,
references/anchor-*.png), defringe (outputs/*.png, outputs-raw/, defringe.json), embed (outputs/*.png), qa (qa.json),
finalize (all of those), manifest (run.md) and
review-cmd --phase image (review/tile-2x2.png of a tileable purpose, review/composite-*.png of an output with alpha) in
the given run dir, approve-record (run.md and <authoring>/approvals/AGEN-<run-id>/), promote-anchor
(assetgen/styles/<style>/anchors/<id>.json + .png, status proposed only) and reject
(assetgen/styles/<style>/rejections/<id>.json) in the authoring repo. review-cmd only prints a `codex exec --sandbox
read-only` command with absolute paths (it works from any cwd); --no-write (factory-cmd always passes it) never builds
a tile or composite: it uses each only when it holds the current pixels, else exits 2. The only network call is publish: it POSTs workflow.ui.json to ComfyUI's userdata
API (/api/userdata/workflows%2Fassetgen%2F<run-id>.json?overwrite=true) so the run shows in the ComfyUI Workflows
sidebar under assetgen; it writes nothing locally (unreachable ComfyUI: NOT_AVAILABLE, exit 3). This script never
runs agents or ComfyUI. Model ids, sizes and other values live in template params data, not here.
Exit codes: 0 ok/PASS, 1 FAIL or error, 2 usage, 3 NOT_AVAILABLE (qa, finalize, publish). Options are never abbreviated (--ou
is not --out): allow_abbrev=False on every parser.
"""
import argparse
import contextlib
import glob
import hashlib
import io
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
import approval  # noqa: E402
import budget  # noqa: E402
import finalize  # noqa: E402
import graphstyle  # noqa: E402
import imaging  # noqa: E402
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
    the relevant rejections. stylelock.family_fallback (purpose, else project.json anchor_family_fallback) decides
    whether anchors of another family may fill the selection; spec.warnings names each such pick (and the anchors a
    false fallback left out)."""
    choice = stylelock.choose(layers.load("purpose", purpose, authoring), authoring, family, style, override)
    spec = layers.resolve(purpose, choice["style_id"], template, authoring)
    ref = stylelock.style_ref(spec["style"])
    cap = stylelock.max_references(spec["purpose"]["data"], spec["template"]["data"])
    picks, warnings = stylelock.select_with_warnings(
        stylelock.valid_anchors(authoring, ref["style_id"]), ref, choice["family"], spec["purpose"]["data"].get("dimensions"),
        cap, stylelock.family_fallback(spec["purpose"]["data"], authoring)) if authoring else ([], [])
    rejections = stylelock.relevant_rejections(stylelock.load_rejections(authoring, ref["style_id"]), ref,
                                               choice["family"]) if authoring else []
    spec["style_lock"] = {"project": choice["project"], "family": choice["family"], "family_source": choice["family_source"],
                          "style": ref, "override": choice["override"], "max_references": cap, "references": picks,
                          "rejections": rejections}
    spec["warnings"] = warnings  # cross-family anchor picks (resolve prints them; not part of the style lock record)
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

typed = runfiles.typed_param  # value coerced to the param type; raises ValueError naming the param


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


def prompt_review_state(run_dir, spec, prompt, params=None):
    """(state, by) of review-prompt.json for this prompt and spec: PASS/FAIL when bound to both (prompt_sha256 and
    requirements_sha256, as review-cmd --phase prompt hands them out), STALE when either differs or is missing; a PASS
    by a reviewer that is not Codex (a SAME_MODEL fallback) is WARN, as the quality plugin grades it. by is "codex"
    while no verdict exists (the title names the reviewer the run expects). params: the rendered params the binding is
    checked against (render passes those of the workflow it is about to write); rendered_params of the run when None."""
    v = runfiles.read_verdict(os.path.join(run_dir, REVIEW_FILES["prompt"]), "prompt")
    if v["state"] not in ("PASS", "FAIL"):
        return v["state"], "codex"
    if (v["prompt_sha256"] != hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            or v["requirements_sha256"] != review_requirements_sha256(run_dir, spec, "prompt", params)):
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
    """(params, source) of the params render used (runfiles.rendered_params of the run's workflow.json): spec.json
    params with each template param read back from workflow.json, so a render --param shows; source names
    workflow.json, or spec.json before the first render. These are the params a review is shown and bound to."""
    wf_path = os.path.join(run_dir, "workflow.json")
    return runfiles.rendered_params(read_json(wf_path, "workflow") if os.path.isfile(wf_path) else None, spec)


def review_requirements_sha256(run_dir, spec, phase, params=None):
    """requirements_sha256 a review of phase is bound to: over the rendered params (what the review prompt shows;
    params, else rendered_params of the run), so a render --param that changes a param after a review makes it stale;
    the image phase also hashes the generation inputs."""
    bound = dict(spec, params=rendered_params(run_dir, spec)[0] if params is None else params)
    return runfiles.requirements_sha256(bound, generation_inputs(run_dir, spec) if phase == "image" else None)


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


def review_rubric(spec, phase, composites=False):
    """The rubric of a review: the purpose's prompt_rubric or image_rubric; with spec.style_lock the image phase adds
    the anchor item (when anchors are selected) and one item per relevant rejection; composites (an output with alpha,
    review/composite-*.png attached) adds the edge item. Claude's own visual review (review-image-claude.json) uses the
    same items (review-cmd --json prints them as rubric)."""
    rubric = list(spec["purpose"]["data"].get("prompt_rubric" if phase == "prompt" else "image_rubric", []))
    if phase == "image":
        if runfiles.style_lock_references(spec):
            rubric.append(ANCHOR_RUBRIC)
        rubric += [rejection_item(r) for r in style_lock_rejections(spec)]
        if composites:
            rubric.append(EDGE_RUBRIC)
    return rubric


DETERMINISTIC = "size, alpha, corners, tileable, blank"


def review_prompt_text(phase, spec, prompt, images, qa_report, binding, sizes=(), tiles=(), anchors=(), params=None,
                       composites=()):
    """params: (values, source) of rendered_params; spec.json params when None. composites: [(path, source output,
    background)] of review_composites."""
    p, s = spec["purpose"], spec["style"]
    values, source = params if params is not None else (spec.get("params", {}), "spec.json")
    rubric = review_rubric(spec, phase, bool(composites))
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
        lines += ["", "Attached images (one per -i): " + ", ".join(list(images) + [t for t, _ in tiles] + [c for c, _, _ in composites]
                                                                  + [a for a, _ in anchors])]
        lines += ["True pixel size (PNG header) of %s: %s" % (i, z) for i, z in zip(images, sizes)]
        lines += ["%s is not an output: review-cmd tiled %s 2x2 so you can judge its seams" % (t, src) for t, src in tiles]
        lines += ["%s is not an output: review-cmd composited %s on a %s background (#%02x%02x%02x) so you can judge its "
                  "edges; judge them on both the dark and the light composite" % ((c, src, bg) + imaging.SOLID[bg])
                  for c, src, bg in composites]
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


def composite_name(images, image, background):
    """review/composite-<background>.png for a single output, review/composite-<stem>-<background>.png for several."""
    if len(images) == 1:
        return "review/composite-%s.png" % background
    return "review/composite-%s-%s.png" % (os.path.splitext(os.path.basename(image))[0], background)


def depth_refusal(data, done):
    """None for an 8-bit PNG (IHDR bit depth 8; palette included), else the reason it is refused: defringe and the
    review previews handle only 8-bit inputs, what the image service produces (16-bit and 1/2/4-bit are not)."""
    depth = png.header(data)[2]
    return None if depth == 8 else "bit depth %d not supported: only 8-bit PNGs are %s" % (depth, done)


def source_preview(path):
    """(decoded image, output bytes, gray) of an output for its review previews; gray: a grayscale output (colour
    type 0 or 4), whose previews are built gray too (png.tile_2x2, imaging.composite with gray=True). A PNG that is
    not 8-bit raises png.Unsupported (depth_refusal): it gets no preview, the image still goes to the reviewer."""
    with open(path, "rb") as f:
        data = f.read()
    refusal = depth_refusal(data, "previewed")
    if refusal:
        raise png.Unsupported(refusal)
    img = png.decode(path)
    return img, data, png.gray_type(png.header(data)[3])


def tagged_preview(preview, source):
    """The preview bytes with the source output's PREVIEW_KEEP colour chunks right after IHDR (colour_chunks rules for
    the preview's own colour type: an iCCP profile of the other colour space is dropped), so the preview displays its
    pixel values as the output does. An untagged output gives none: its previews stay untagged, byte for byte."""
    colour = [(t, b) for t, b in colour_chunks(source, png.header(preview)[3]) if t in PREVIEW_KEEP]
    return after_ihdr(preview, colour) if colour else preview


def derived_preview(run_dir, name, data, write):
    """Writes a review preview (review/*.png, derived from output pixels, never an output). write=False builds nothing:
    the file must already hold exactly these bytes, else exit 2."""
    target = os.path.join(run_dir, *name.split("/"))
    if write:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        return
    try:
        with open(target, "rb") as f:
            current = f.read() == data
    except OSError:
        current = False
    if not current:
        fail("%s is missing or stale and --no-write builds nothing: run scripts/assetgen/assetgen.py review-cmd "
             "--phase image --run %s directly (the asset-gen skill)" % (name, run_dir.replace(os.sep, "/")), 2)


def review_tiles(run_dir, images, rel, write):
    """[(tile path relative to the run, source output)] of the 2x2 seam previews, each with the output's colour chunks
    (source_preview). write=False builds nothing: it uses a tile only when its bytes are what review-cmd would build
    now, else exits 2."""
    out = []
    for path, src, name in zip(images, rel, tile_names(images)):
        try:
            img, source, gray = source_preview(path)
            data = tagged_preview(png.tile_2x2(img, gray), source)
        except (OSError, png.Invalid, png.Unsupported) as exc:
            print("assetgen: no tiled preview of %s: %s" % (src, exc), file=sys.stderr)
            continue
        derived_preview(run_dir, name, data, write)
        out.append((name, src))
    return out


COMPOSITE_BACKGROUNDS = ("dark", "light")
EDGE_RUBRIC = ("The edges of every output with alpha are clean on both the dark and the light composite: no coloured "
               "fringe, halo, speckle or matte line around the subject.")


def review_composites(run_dir, images, rel, write):
    """[(composite path relative to the run, source output, background)] of every output with transparent pixels,
    composited on the dark and on the light background (imaging.composite) so a reviewer sees its edges. The blend
    runs on the stored (encoded) values, and the backgrounds are given in that same encoded space; each composite
    carries the output's colour chunks (source_preview), so body, background and fringe display as they would over
    that background in the output's own colour interpretation. write=False as review_tiles."""
    out = []
    for path, src in zip(images, rel):
        try:
            img, source, gray = source_preview(path)
        except (OSError, png.Invalid, png.Unsupported) as exc:
            print("assetgen: no composite preview of %s: %s" % (src, exc), file=sys.stderr)
            continue
        if not img.has_alpha or min(img.rgba[3::4]) == 255:
            continue
        for bg in COMPOSITE_BACKGROUNDS:
            name = composite_name(images, path, bg)
            derived_preview(run_dir, name, tagged_preview(imaging.composite(img, bg, gray), source), write)
            out.append((name, src, bg))
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
               "requirements_sha256": review_requirements_sha256(run_dir, spec, phase)}
    if phase == "image":
        binding["outputs"] = [{"path": r, "sha256": qa.sha256(i)} for r, i in zip(rel, images)]
    sizes, tiles, composites = [], [], []
    if phase == "image":
        requested = requested_size(run_dir, spec)
        sizes = [pixel_size(i, requested) for i in images]
        purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
        data = purpose.get("data") if isinstance(purpose.get("data"), dict) else {}
        if "png-tileable" in runfiles.required_checks(data.get("qa")):
            tiles = review_tiles(run_dir, images, rel, write)
        composites = review_composites(run_dir, images, rel, write)
    anchors = review_anchors(run_dir, spec) if phase == "image" else []
    lock = spec.get("style_lock")
    if phase == "image" and isinstance(lock, dict):
        binding["style"] = lock.get("style")
        binding["anchors"] = [{"anchor_id": pick.get("anchor_id"), "sha256": pick.get("sha256")} for _, pick in anchors]
    stdin = review_prompt_text(phase, spec, prompt, rel, qa_report, binding, sizes, tiles, anchors,
                               rendered_params(run_dir, spec), composites)
    verdict = os.path.join(run_dir, REVIEW_FILES[phase]).replace(os.sep, "/")
    argv = [codex, "exec", "--sandbox", "read-only", "-C", run_dir.replace(os.sep, "/")]
    for i in images + [os.path.join(run_dir, *t.split("/")) for t in [t for t, _ in tiles] + [c for c, _, _ in composites]
                       + [a for a, _ in anchors]]:
        argv += ["-i", i.replace(os.sep, "/")]
    argv += ["-o", verdict, "-"]
    shell = "%s <<'%s'\n%s\n%s" % (shlex.join(argv), HEREDOC, stdin, HEREDOC)
    return {"schema": "rpg-factory.assetgen-review-cmd/1", "phase": phase, "argv": argv, "stdin": stdin,
            "verdict": verdict, "binding": binding, "shell": shell, "tiles": [t for t, _ in tiles],
            "composites": [c for c, _, _ in composites], "anchors": [a for a, _ in anchors],
            "rubric": review_rubric(spec, phase, bool(composites))}


# -- embed -----------------------------------------------------------------------------------------------------

def read_ui(run_dir):
    path = os.path.join(run_dir, "workflow.ui.json")
    ui = read_json(path, "UI workflow (run render --run first)")
    if not isinstance(ui, dict) or not isinstance(ui.get("nodes"), list):
        fail("%s is not a ComfyUI frontend workflow (run render --run again)" % path.replace(os.sep, "/"))
    return path, ui


def text_chunks(data, keyword=None):
    """The (type, body) text chunks (tEXt, zTXt, iTXt) of PNG bytes in file order; only those named keyword when given."""
    key = keyword.encode("latin-1") if keyword is not None else None
    return [(t, b) for t, b in png.chunks(data) if t in png.TEXT_CHUNKS and (key is None or b.split(b"\0", 1)[0] == key)]


def rebuild(data, keep, extra=()):
    """PNG bytes with only the chunks keep(type, body) accepts and the extra (type, body) chunks right before IEND;
    every kept chunk and anything after IEND stay byte for byte."""
    out, pos = [data[:8]], 8
    for ctype, body in png.chunks(data):
        size = 12 + len(body)
        if ctype == b"IEND":
            out += [png.chunk(t, b) for t, b in extra]
        if ctype == b"IEND" or keep(ctype, body):
            out.append(data[pos:pos + size])
        pos += size
    out.append(data[pos:])
    return b"".join(out)


def write_atomic(path, data, suffix):
    tmp = path + suffix
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def embed(run_dir):
    """Rows {output, state: embedded|replaced|kept|FAIL, reason}: the UI workflow as a `workflow` tEXt chunk of each
    output. A PNG whose workflow chunk is exactly the current workflow.ui.json is kept byte for byte; one whose chunk
    differs (an older render) gets it replaced (every other chunk kept)."""
    _, ui = read_ui(run_dir)
    text = json.dumps(ui, separators=(",", ":"), ensure_ascii=True)
    want = [(b"tEXt", b"workflow\0" + text.encode("latin-1"))]
    images = sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))
    if not images:
        fail("no outputs/*.png in %s to embed the workflow in" % run_dir.replace(os.sep, "/"))
    rows = []
    for path in images:
        name = "outputs/" + os.path.basename(path)
        with open(path, "rb") as f:
            data = f.read()
        try:
            have = text_chunks(data, "workflow")
            if have == want:
                rows.append({"output": name, "state": "kept", "reason": "already carries the current workflow chunk"})
                continue
            new = rebuild(data, lambda t, b: not (t in png.TEXT_CHUNKS and b.split(b"\0", 1)[0] == b"workflow"))
            new = png.add_text(new, "workflow", text)
        except png.Invalid as exc:
            rows.append({"output": name, "state": "FAIL", "reason": str(exc)})
            continue
        write_atomic(path, new, ".embed.tmp")
        if have:
            rows.append({"output": name, "state": "replaced", "reason": "stale workflow chunk replaced by the current "
                         "workflow.ui.json (%d bytes)" % len(text)})
        else:
            rows.append({"output": name, "state": "embedded", "reason": "workflow chunk of %d bytes added" % len(text)})
    return rows


# -- defringe --------------------------------------------------------------------------------------------------

DEFRINGE_FILE = "defringe.json"
RAW_DIR = "outputs-raw"
DEFRINGE_RINGS = 8
# Ancillary chunks that stay valid for the rewritten 8-bit RGBA or gray+alpha image (colour management, HDR metadata,
# pixel size); defringe carries them right after IHDR, except an iCCP that does not fit the written colour type
# (colour_chunks). Chunks bound to the old pixel format (sBIT, PLTE, tRNS, bKGD, hIST, sPLT)
# and every other chunk are dropped.
DEFRINGE_KEEP = (b"cHRM", b"gAMA", b"iCCP", b"sRGB", b"cICP", b"mDCv", b"cLLI", b"pHYs")
# Chunks that say how a preview's pixel values are to be displayed: DEFRINGE_KEEP minus pHYs (a preview is looked at,
# never placed, so its physical pixel size is irrelevant).
PREVIEW_KEEP = tuple(t for t in DEFRINGE_KEEP if t != b"pHYs")


def icc_fits(body, color_type):
    """False when the iCCP profile's colour space (png.icc_space) is readable and is not the one the PNG spec requires
    for color_type: GRAY for gray (0, 4), RGB for colour (2, 3, 6). An unreadable profile is kept as it was."""
    space = png.icc_space(body)
    return space is None or space == (b"GRAY" if png.gray_type(color_type) else b"RGB ")


def colour_chunks(data, color_type=None):
    """The DEFRINGE_KEEP (type, body) chunks of PNG bytes found before the first IDAT, in file order, the first of each
    type only; iCCP wins over sRGB when an (invalid) input has both, so the output never carries both. color_type: the
    colour type of the PNG that will carry them; an iCCP whose profile does not fit it (icc_fits: a GRAY profile on
    RGB(A), an RGB one on gray) is dropped, and then the input's sRGB, if any, is kept."""
    found, seen = [], set()
    for ctype, body in png.chunks(data):
        if ctype == b"IDAT":
            break
        if ctype in DEFRINGE_KEEP and ctype not in seen:
            seen.add(ctype)
            found.append((ctype, body))
    if color_type is not None:
        found = [(t, b) for t, b in found if t != b"iCCP" or icc_fits(b, color_type)]
    icc = any(t == b"iCCP" for t, _ in found)
    return [(t, b) for t, b in found if not (t == b"sRGB" and icc)]


def after_ihdr(data, extra):
    """PNG bytes with the extra (type, body) chunks right after IHDR (which png.chunks has validated)."""
    first = next(iter(png.chunks(data)))
    if first[0] != b"IHDR":
        raise png.Invalid("first chunk is not IHDR")
    pos = 8 + 12 + len(first[1])
    return data[:pos] + b"".join(png.chunk(t, b) for t, b in extra) + data[pos:]


def bound_records(run_dir, outputs):
    """The run records that bind any of these output hashes ({path: sha256}): qa.json and the image reviews."""
    names = []
    for name in ("qa.json", REVIEW_FILES["image"], CLAUDE_REVIEW):
        path = os.path.join(run_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        recorded = data.get("outputs") if isinstance(data, dict) else None
        if any(isinstance(o, dict) and outputs.get(o.get("path")) == o.get("sha256") for o in recorded or []):
            names.append(name)
    return names


def pixels_sha256(path):
    """sha256 of the decoded RGBA pixels (and size) of a PNG, None when unreadable: unchanged by embed, which only
    adds a text chunk."""
    try:
        img = png.decode(path)
    except (png.Invalid, png.Unsupported, OSError):
        return None
    return hashlib.sha256(b"%dx%d:" % (img.width, img.height) + img.rgba).hexdigest()


def defringe(run_dir, alpha_floor=None, force=False):
    """(rows, bound): rows {output, state: defringed|skipped|FAIL, reason, ...} of imaging.defringe on every output
    with transparent pixels, in place; bound names the records (qa.json, image reviews) --force made stale. The
    original goes to outputs-raw/<name> first; defringe.json records the params and each output's before/after sha256
    (file bytes), its after_pixels_sha256 (decoded pixels: embed after defringe keeps them) and stats. Running it again
    on outputs it wrote (same pixels) starts from the kept originals, so the result depends only on the originals and
    the params. Text chunks (prompt, workflow) are carried over before IEND, and the colour-management and other safe
    ancillary chunks (cHRM, gAMA, iCCP or sRGB - never both -, cICP, mDCv, cLLI, pHYs) right after IHDR, so the opaque
    body keeps its colour (an iCCP whose profile does not fit the written colour type is dropped, colour_chunks); a
    grayscale output (colour type 0 or 4) stays grayscale, written as gray+alpha; chunks bound to the old pixel format (sBIT, PLTE, tRNS, bKGD, hIST, sPLT) are dropped. Only 8-bit PNGs are defringed
    (depth_refusal): any other bit depth is skipped with the reason and left byte-identical, no outputs-raw copy (skipped,
    not FAIL: the file is valid and untouched, and qa still grades its edges). Refuses an approved run, and outputs
    that qa.json or an image review already bind unless force (those records must be re-run afterwards)."""
    images = sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))
    if not images:
        fail("no outputs/*.png in %s to defringe" % run_dir.replace(os.sep, "/"))
    front = existing_front(os.path.join(run_dir, "run.md"))
    if isinstance(front, dict) and front.get("status") == "approved":
        fail("run.md is approved: defringe would change the approved outputs; start a new attempt <slug>-NNN+1 instead")
    current = {"outputs/" + os.path.basename(p): qa.sha256(p) for p in images}
    bound = bound_records(run_dir, current)
    if bound and not force:
        fail("%s already bind(s) the current outputs: defringe changes them, so they would be stale. Run defringe after "
             "fetch_outputs and before qa and the image reviews, or pass --force and then re-run embed, qa, review-cmd "
             "--phase image (Codex) and Claude's image review (%s)" % (", ".join(bound), CLAUDE_REVIEW))
    record_path = os.path.join(run_dir, DEFRINGE_FILE)
    old = {}
    if os.path.isfile(record_path):
        rec = read_json(record_path, "defringe record")
        old = {o.get("output"): o for o in rec.get("outputs") or [] if isinstance(o, dict)} if isinstance(rec, dict) else {}
    rows = []
    for path in images:
        name = "outputs/" + os.path.basename(path)
        raw = os.path.join(run_dir, RAW_DIR, os.path.basename(path))
        prev = old.get(name) or {}
        again = (os.path.isfile(raw) and qa.sha256(raw) == prev.get("before_sha256")
                 and prev.get("after_pixels_sha256") == pixels_sha256(path))
        src = raw if again else path
        with open(src, "rb") as f:
            data = f.read()
        try:
            refusal = depth_refusal(data, "defringed")
            if refusal:
                rows.append({"output": name, "state": "skipped", "reason": refusal})
                continue
            img = png.decode(src)
            chunks = text_chunks(data)
            gray = png.gray_type(png.header(data)[3])
        except (png.Invalid, png.Unsupported) as exc:
            rows.append({"output": name, "state": "FAIL", "reason": str(exc)})
            continue
        if not img.has_alpha or min(img.rgba[3::4]) == 255:
            rows.append({"output": name, "state": "skipped", "reason": "no transparent pixels: nothing to defringe"})
            continue
        new, stats = imaging.defringe(img, alpha_floor, DEFRINGE_RINGS, gray)
        new = rebuild(after_ihdr(new, colour_chunks(data, png.header(new)[3])), lambda t, b: True, chunks)
        if not again:
            os.makedirs(os.path.dirname(raw), exist_ok=True)
            shutil.copyfile(path, raw)
        write_atomic(path, new, ".defringe.tmp")
        rows.append({"output": name, "state": "defringed", "raw": RAW_DIR + "/" + os.path.basename(path),
                     "before_sha256": hashlib.sha256(data).hexdigest(), "after_sha256": hashlib.sha256(new).hexdigest(),
                     "after_pixels_sha256": pixels_sha256(path),
                     "stats": stats, "reason": "%d of %d soft pixels recoloured (%d unreached), %d floored to alpha 0%s" % (
                         stats["recoloured"], stats["soft"], stats["unreached"], stats["floored"],
                         ", from the kept original" if again else "")})
    done = [r for r in rows if r["state"] == "defringed"]
    if done:
        write_json(record_path, {"schema": "rpg-factory.assetgen-defringe/1", "run": os.path.basename(os.path.normpath(run_dir)),
                                 "params": {"alpha_floor": alpha_floor, "rings": DEFRINGE_RINGS, "opaque": imaging.OPAQUE},
                                 "outputs": [{k: r[k] for k in ("output", "raw", "before_sha256", "after_sha256",
                                                                "after_pixels_sha256", "stats")}
                                             for r in done]})
    return rows, bound


def defringe_line(run_dir, outputs):
    """The run.md body line of defringe.json (None without it): what it did, and STALE when an output's pixels are no
    longer the ones defringe wrote (after_pixels_sha256; embed keeps them)."""
    path = os.path.join(run_dir, DEFRINGE_FILE)
    if not os.path.isfile(path):
        return None
    rec = read_json(path, "defringe record")
    done = [o for o in rec.get("outputs") or [] if isinstance(o, dict)] if isinstance(rec, dict) else []
    recorded = {o["path"] for o in outputs}
    stale = [str(o.get("output")) for o in done if o.get("output") not in recorded or pixels_sha256(
        os.path.join(run_dir, *str(o.get("output")).split("/"))) != o.get("after_pixels_sha256")]
    params = rec.get("params") if isinstance(rec, dict) and isinstance(rec.get("params"), dict) else {}
    floor = params.get("alpha_floor")
    return "- Defringe: %d output(s), alpha floor %s, originals in %s/ (%s)%s" % (
        len(done), floor if floor is not None else "none", RAW_DIR, DEFRINGE_FILE,
        "; STALE, the outputs changed since: " + ", ".join(stale) if stale else "")


# -- qa --------------------------------------------------------------------------------------------------------

def qa_run(run_dir):
    """(report, text, code) of the qa verb: grades every output of the run, writes qa.json (rpg-factory.validation/1),
    text is the verb's human output, code 0 PASS, 1 FAIL, 3 NOT_AVAILABLE. qa and finalize both call it."""
    spec = load_spec(os.path.join(run_dir, "spec.json"))
    size = requested_size(run_dir, spec)
    results, outputs = qa.run_qa(run_dir, spec, size)
    purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
    state = qa.overall(results)
    counts = {s: sum(1 for r in results if r["state"] == s) for s in ("PASS", "WARN", "FAIL", "NOT_AVAILABLE")}
    report = {"schema": "rpg-factory.validation/1", "tool": "assetgen-qa", "run": os.path.basename(os.path.normpath(run_dir)),
              "purpose": purpose.get("id"), "purpose_sha256": layers.content_hash(purpose.get("data")), "requested_size": size,
              "style_binding": runfiles.qa_style_binding(spec, lambda rel: os.path.join(run_dir, *rel.split("/"))),
              "state": state, "results": results, "outputs": outputs, "summary": counts}
    write_json(os.path.join(run_dir, "qa.json"), report)
    text = ("\n".join("%s %s %s: %s" % (r["state"], r["output"], r["check"], "; ".join(r["reasons"])) for r in results)
            + "\nassetgen qa: %s (%d PASS, %s%d FAIL, %d NOT_AVAILABLE)" % (
                state, counts["PASS"], "%d WARN, " % counts["WARN"] if counts["WARN"] else "", counts["FAIL"], counts["NOT_AVAILABLE"]))
    return report, text, {"PASS": 0, "FAIL": 1}.get(state, 3)


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


def run_budget(run_dir, spec):
    """budget.state of a run: its outputs plus the failed attempts of its series (none for a dir not <slug>-NNN)."""
    name = os.path.basename(os.path.normpath(run_dir))
    return budget.state(run_dir, spec, failed_attempts(run_dir) if RUN_ID.match(name) else [])


def finalize_with_budget(run_dir, force, as_json):
    """finalize.run plus the budget state (text: a line before the summary line; --json: key "budget"). The exit code
    stays finalize's; a refusal (SystemExit from its precheck) prints what it printed and is re-raised unchanged."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = finalize.run(sys.modules[__name__], run_dir, force, as_json)
    except BaseException:
        sys.stdout.write(buf.getvalue())
        sys.stdout.flush()
        raise
    out = buf.getvalue()
    st = run_budget(run_dir, load_spec(os.path.join(run_dir, "spec.json")))
    if as_json:
        obj = json.loads(out)
        obj["budget"] = st
        print(json.dumps(obj, indent=1, sort_keys=True))
    else:
        lines = out.rstrip("\n").split("\n")
        lines.insert(len(lines) - 1, budget.line(st))
        print("\n".join(lines))
    return code


def manifest(run_dir, title=None, prompt_author="claude", generated_by="claude"):
    """(front matter, reset, changes): the gen-run front matter; reset when an earlier status other than proposed
    went back to proposed, changes the bound fields that made an approved run proposed (approval.bound_changes).
    The status follows approval.keep_status: an approved run stays approved while nothing its approval binds changed
    and the new run.md is byte for byte the approved one (so the approval record's rev still matches); any other
    change (another --title or --prompt-author too) makes it proposed and names the changed fields."""
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
    front = {
        "id": "AGEN-" + name, "kind": "gen-run", "domain": "assetgen", "schema_version": 2, "status": "proposed",
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
    front["status"] = approval.keep_status(old, front)
    changes = []
    if front["status"] == "approved":
        # the approval record binds the run.md blob: any other byte (another --title or --prompt-author, a body line)
        # would leave an approved run.md that no approval binds, so it goes back to proposed and names the fields
        with open(os.path.join(run_dir, "run.md"), encoding="utf-8", newline="") as f:
            if f.read() != manifest_text(front, run_dir, run_md_newline(run_dir)):
                front["status"] = "proposed"
                changes = unbound_changes(old, front) or ["run.md body"]
    reset = bool(old.get("status")) and old.get("status") != "proposed" and front["status"] == "proposed"
    if reset and old.get("status") == "approved" and not changes:
        changes = approval.bound_changes(old, front)
    return front, reset, changes


def unbound_changes(old, new):
    """The front-matter fields (spec.<key> inside spec) that differ between two run.md fronts, status left out."""
    out = [k for k in sorted(set(old) | set(new)) if k not in ("status", "spec") and old.get(k) != new.get(k)]
    o, n = old.get("spec") or {}, new.get("spec") or {}
    return out + ["spec." + k for k in sorted(set(o) | set(n)) if o.get(k) != n.get(k)]


def run_md_newline(run_dir):
    """The line ending of an existing run.md (CRLF when its first line ends in CRLF, else LF): a re-run manifest
    keeps it, so an unchanged approved run.md stays byte-identical (its approval record binds that blob)."""
    try:
        with open(os.path.join(run_dir, "run.md"), "rb") as f:
            first = f.readline()
    except OSError:
        return "\n"
    return "\r\n" if first.endswith(b"\r\n") else "\n"


def manifest_text(front, run_dir=None, newline="\n"):
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
    fringe = defringe_line(run_dir, s["outputs"]) if run_dir else None
    if fringe:
        body.append(fringe)
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
    text = "---json\n%s\n---\n%s\n" % (json.dumps(front, indent=2, ensure_ascii=True), "\n".join(body))
    return text.replace("\n", newline) if newline != "\n" else text


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
    """One line per drift item; a style-id-mismatch line names the project style (and the version state of its own
    style, when it is also behind)."""
    rows = []
    for i in report["items"]:
        st, cur = i["style"], i["current"]
        now = "v%s %s" % (cur["version"], (cur["sha256"] or "")[:12]) if cur else "missing"
        line = "%s %s %s (%s): recorded %s v%s %s, current %s" % (
            i["state"], i["kind"], i["id"], i["path"], st["style_id"], st.get("version") if st.get("version") is not None else "-",
            (st.get("sha256") or "-")[:12], now)
        if i["state"] == "style-id-mismatch":
            line += ", project style %s%s" % (i.get("project_style"), ", also %s" % i["version_state"] if i.get("version_state") else "")
        rows.append(line)
    return "\n".join(rows + ["assetgen drift: %d item(s) behind the current style or outside the project's styles"
                             % len(report["items"])])


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
                         + ["warning: " + w for w in spec.get("warnings") or []]
                         + ["%s  [%s]" % (k, v) for k, v in sorted(spec["sources"].items())])
    lock = spec["style_lock"]
    lines = head + ["params: " + (", ".join("%s=%s" % (k, v) for k, v in sorted(spec["params"].items())) or "none"),
                    "hints: " + (", ".join("%s (%s%s)" % (k, h.get("from") or "-", ", overrides the style" if "overrides" in h else "")
                                           for k, h in sorted(spec["hints"].items())) or "none"),
                    style_lock_lines(lock)[0]]
    lines.append("references: " + (", ".join(r["anchor_id"] for r in lock["references"]) or "none")
                 + " (max %d)" % lock["max_references"])
    lines.append("rejections: " + (", ".join("%s (%s %s)" % (r["id"], r["type"], r["reason"]) for r in lock["rejections"]) or "none"))
    warnings = list(spec.get("warnings") or [])
    if lock["override"]:
        warnings.append("style override: " + lock["override"])
    if spec.get("authoring") and not lock["project"]:
        warnings.append("no assetgen/project.json: the style is not locked by a project")
    if "filename_prefix" in spec["params"] and not str(spec["param_sources"].get("filename_prefix", "")).startswith("run id "):
        warnings.append("filename_prefix %s is not bound to a run: resolve --out <authoring>/assetgen/runs/<run-id>/spec.json"
                        % spec["params"]["filename_prefix"])
    lines += ["warning: " + w for w in warnings]
    if isinstance(spec.get("budget"), dict) and "max_outputs" in spec["budget"]:
        lines.append("budget: at most %s outputs per run series (advisory; assetgen.py budget --run)"
                     % spec["budget"]["max_outputs"])
    lines.append("(sources of every param, hint and field: --verbose or --json)")
    return "\n".join(lines)


def validation_report(results, tool, verb, as_json):
    """Print rpg-factory.validation/1 rows (lint, graph-lint) and return the exit code: 1 when a row FAILs, else 0."""
    counts = {s: sum(1 for r in results if r["state"] == s) for s in ("PASS", "WARN", "FAIL")}
    emit({"schema": "rpg-factory.validation/1", "tool": tool, "results": results, "summary": counts}, as_json,
         "\n".join("%s %s%s" % (r["state"], r["path"], (": " + "; ".join(r["reasons"])) if r["reasons"] else "") for r in results)
         + "\nassetgen %s: %d PASS, %d WARN, %d FAIL" % (verb, counts["PASS"], counts["WARN"], counts["FAIL"]))
    return 1 if counts["FAIL"] else 0


def read_graph_json(path, what):
    """Parsed JSON of a graph-lint input; exits 2 (usage) when it is missing or not readable JSON."""
    if not os.path.isfile(path):
        fail("graph-lint: %s %s is not a file" % (what, path), 2)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        fail("graph-lint: %s %s is not readable JSON (%s)" % (what, path, exc), 2)


def graph_lint_rows(paths, run, authoring):
    """assetgen-graph-style rows of graph-lint: each PATH (a template file or a ComfyUI frontend workflow), the run's
    workflow.ui.json, or with neither every core and game template. Exits 2 for a PATH that is missing, not JSON or
    neither kind, and for a --run without workflow.ui.json. The --run row checks SaveImage suffixes against the run's
    own prefix (runfiles.run_filename_prefix of the run directory name), not the file's extra.assetgen.run_id."""
    known, rows = lint.known_nodes(), []

    def template(path):
        data, err = lint.template_data(path, authoring)
        shown = lint.display(path, authoring)
        if err is not None:  # a layer template that does not load: no graph to lint
            return {"path": shown, "check": graphstyle.CHECK, "state": "FAIL", "reasons": ["layout: " + err]}
        return graphstyle.template_row(data, known, shown) if isinstance(data, dict) else None

    def frontend(path, raw, prefix=None):
        if isinstance(raw, dict) and isinstance(raw.get("nodes"), list):
            return graphstyle.ui_row(raw, known, lint.display(path, authoring), prefix)
        return None

    for path in paths:
        raw = read_graph_json(path, "PATH")
        row = template(path) or frontend(path, raw)
        if row is None:
            fail("graph-lint: %s is neither a workflow template nor a ComfyUI frontend workflow (a JSON object with a "
                 "\"nodes\" list)" % path, 2)
        rows.append(row)
    if run:
        path = os.path.join(run, "workflow.ui.json")
        prefix = runfiles.run_filename_prefix(os.path.basename(os.path.normpath(run)))
        row = frontend(path, read_graph_json(path, "--run workflow.ui.json"), prefix)
        if row is None:
            fail("graph-lint: %s is not a ComfyUI frontend workflow (a JSON object with a \"nodes\" list)" % path, 2)
        rows.append(row)
    if not paths and not run:
        files = layers.layer_files("template", authoring)
        rows += [row for row in (template(p) for p in list(files["core"].values()) + list(files["game"].values()))
                 if row is not None]
    return rows


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
    c.add_argument("--max-outputs", metavar="N", help="advisory limit of generations per run series, recorded as "
                   "spec.budget.max_outputs (default %d)" % budget.DEFAULT_MAX_OUTPUTS)
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
    c = sp("graph-lint"); c.add_argument("paths", nargs="*"); run_arg(c, False); c.add_argument("--json", action="store_true")
    c = sp("review-cmd"); c.add_argument("--phase", choices=["prompt", "image"], required=True); run_arg(c)
    c.add_argument("--codex", default="codex"); c.add_argument("--no-write", action="store_true"); c.add_argument("--json", action="store_true")
    c = sp("embed"); run_arg(c); c.add_argument("--json", action="store_true")
    c = sp("defringe"); run_arg(c); c.add_argument("--alpha-floor", type=int, metavar="N",
                                                   help="also set every alpha below N (0..%d) to 0" % imaging.OPAQUE)
    c.add_argument("--force", action="store_true", help="defringe outputs that qa.json or an image review already bind "
                   "(they are stale afterwards: re-run them)")
    c.add_argument("--json", action="store_true")
    c = sp("approve-record"); run_arg(c); c.add_argument("--by", metavar="NAME", help="the person who approves the run")
    c.add_argument("--note"); c.add_argument("--json", action="store_true")
    c = sp("publish"); run_arg(c); c.add_argument("--comfy-url", required=True)
    c.add_argument("--json", action="store_true")
    c = sp("qa"); run_arg(c); c.add_argument("--json", action="store_true")
    c = sp("budget"); run_arg(c); c.add_argument("--json", action="store_true")
    c = sp("finalize"); run_arg(c)
    c.add_argument("--force", action="store_true", help="let defringe rewrite outputs that qa.json or an image review "
                   "already bind (they are stale afterwards: re-run them)")
    c.add_argument("--json", action="store_true")
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
            max_outputs = budget.DEFAULT_MAX_OUTPUTS
            if a.max_outputs is not None:
                try:
                    max_outputs = budget.parse_max(a.max_outputs)
                except ValueError as exc:
                    fail("--max-outputs %s: %s" % (a.max_outputs, exc), 2)
            spec = resolve_spec(a.purpose, a.style, a.template, authoring, a.family, a.style_override)
            spec["budget"] = {"max_outputs": max_outputs}
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
            workflow, errors = render(spec, prompt, a.param, run_id)
            if not errors and a.run:  # the title states the review against the params this workflow renders
                state, reviewer = prompt_review_state(a.run, spec, prompt, runfiles.rendered_params(workflow, spec)[0])
                workflow, errors = render(spec, prompt, a.param, run_id, state, reviewer)
            if not errors and a.run:
                errors = copy_anchors(a.run, spec)
            ui = None
            if not errors:
                try:
                    ui = uiworkflow.to_ui(workflow, lint.known_nodes(),
                                          {"assetgen": {"run_id": run_id, "workflow": os.path.basename(out)}},
                                          spec["template"]["data"].get("ui"))
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
            results = [row for p in (a.paths or lint.default_paths(authoring)) for row in lint.lint_rows(p, authoring)]
            return validation_report(results, "assetgen-lint", "lint", a.json)
        if a.cmd == "graph-lint":
            return validation_report(graph_lint_rows(a.paths, a.run, authoring), "assetgen-graph-lint", "graph-lint", a.json)
        if a.cmd == "review-cmd":
            cmd = review_cmd(a.run, a.phase, a.codex, not a.no_write)
            emit(cmd, a.json, cmd["shell"])
            return 0
        if a.cmd == "embed":
            rows = embed(a.run)
            counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("embedded", "replaced", "kept", "FAIL")}
            emit({"schema": "rpg-factory.assetgen-embed/1", "run": os.path.basename(os.path.normpath(a.run)), "results": rows,
                  "summary": counts}, a.json, "\n".join("%s %s: %s" % (r["state"], r["output"], r["reason"]) for r in rows)
                 + "\nassetgen embed: %(embedded)d embedded, %(replaced)d replaced, %(kept)d kept, %(FAIL)d FAIL" % counts)
            return 1 if counts["FAIL"] else 0
        if a.cmd == "defringe":
            if a.alpha_floor is not None and not 0 <= a.alpha_floor <= imaging.OPAQUE:
                fail("--alpha-floor must be from 0 to %d" % imaging.OPAQUE, 2)
            rows, stale = defringe(a.run, a.alpha_floor, a.force)
            counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("defringed", "skipped", "FAIL")}
            tail = ("\nstale now (re-run them): " + ", ".join(stale)) if stale else ""
            emit({"schema": "rpg-factory.assetgen-defringe-run/1", "run": os.path.basename(os.path.normpath(a.run)),
                  "results": rows, "summary": counts, "stale": stale}, a.json,
                 "\n".join("%s %s: %s" % (r["state"], r["output"], r["reason"]) for r in rows)
                 + "\nassetgen defringe: %(defringed)d defringed, %(skipped)d skipped, %(FAIL)d FAIL" % counts
                 + (" (originals in %s/, record %s); next: embed, qa" % (RAW_DIR, DEFRINGE_FILE)
                    + (", review-cmd --phase image (Codex) and Claude's image review (%s)" % CLAUDE_REVIEW if stale else "")
                    if counts["defringed"] else "")
                 + tail)
            return 1 if counts["FAIL"] else 0
        if a.cmd == "approve-record":
            if not a.by or not a.by.strip():
                fail("approve-record needs --by NAME: the person who approves the run (an agent runs it only on that "
                     "person's explicit word)", 2)
            res = approval.approve_record(a.run, a.by, a.note)
            rel = os.path.relpath(res["approval"], os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(a.run)))))
            res = dict(res, run_md=res["run_md"].replace(os.sep, "/"), approval=res["approval"].replace(os.sep, "/"))
            emit(res, a.json, "\n".join([
                "wrote %s: status approved" % res["run_md"],
                "wrote %s: %s by %s, rev %s" % (rel.replace(os.sep, "/"), approval.GATE, res["record"]["by"], res["rev"]),
                "next: %s commits run.md and this record together in one SSH-signed commit (git commit -S) whose signer "
                "principal is %s; until then the checks report the approval as present but not committed/signed"
                % (res["record"]["by"], res["record"]["by"]),
                "do not edit run.md or the record before that commit: the record binds the blob %s of run.md" % res["rev"]]))
            return 0
        if a.cmd == "publish":
            res = publish(a.run, a.comfy_url)
            emit(res, a.json, "assetgen publish: %s %s (%s)" % (res["state"], res["workflow"], res["reason"]))
            return {"PASS": 0, "FAIL": 1}.get(res["state"], 3)
        if a.cmd == "qa":
            report, text, code = qa_run(a.run)
            emit(report, a.json, text)
            return code
        if a.cmd == "budget":
            if not os.path.isfile(os.path.join(a.run, "spec.json")):
                fail("budget needs <run>/spec.json (resolve --out first)")
            st = run_budget(a.run, load_spec(os.path.join(a.run, "spec.json")))
            emit(st, a.json, budget.line(st))
            return st["exit"]
        if a.cmd == "finalize":
            return finalize_with_budget(a.run, a.force, a.json)
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
            front, reset, changes = manifest(a.run, a.title, a.prompt_author, a.generated_by)
            newline = run_md_newline(a.run)
            with open(os.path.join(a.run, "run.md"), "w", encoding="utf-8", newline="") as f:
                f.write(manifest_text(front, a.run, newline))
            note = (" (approval no longer binds, changed: %s; status reset to proposed)" % ", ".join(changes) if changes
                    else " (outputs changed: status reset to proposed)" if reset else "")
            emit(front, a.json, "wrote %s/run.md: %s %s%s" % (a.run.replace(os.sep, "/"), front["id"], front["status"], note))
            return 0
    except layers.SpecError as exc:
        fail(str(exc))
    return 2


if __name__ == "__main__":
    sys.exit(main())
