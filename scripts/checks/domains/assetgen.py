#!/usr/bin/env python3
"""Asset generation (assetgen) domain quality rules for gen-run records; read-only, no network, no ComfyUI.

A gen-run is <authoring>/assetgen/runs/<run_id>/run.md, written by scripts/assetgen/assetgen.py manifest. Checks:

  gen-run-location     run.md sits at assetgen/runs/<run_id>/run.md and the id is AGEN-<run_id>
  gen-run-prompt-review / gen-run-image-review
                       state PASS, by a model other than the prompt author (model family: the part of the name
                       before the first - _ / . : @ or space, so claude-sonnet counts as claude). A same-model review
                       is allowed only as an explicit fallback: by = "SAME_MODEL:<model>" grades WARN (the human
                       approver weighs it); an unmarked same-model review FAILS, and a marker naming another model
                       than the author FAILS (it is not a fallback). The review file itself is the evidence, not the
                       run.md summary: review-<phase>.json must exist, run.md's <phase>_review must equal what
                       scripts/assetgen/runfiles.py reads from it (else FAIL: re-run manifest), and its binding must
                       name the current bytes: prompt_sha256 = spec.prompt_sha256, requirements_sha256 =
                       runfiles.requirements_sha256 of the run.md spec (purpose, style and template content hashes,
                       the rendered params - runfiles.rendered_params of workflow.json over spec.json, what the review
                       prompt showed - or run.md's spec.params without spec.json; for the image review also
                       the generation inputs of workflow.json) and, for the
                       image review, outputs = the recorded outputs (review-cmd hands the reviewer these values to copy back). A missing, invalid,
                       unbound or stale review file is missing work.
  gen-run-claude-review
                       Claude's own visual review, review-image-claude.json (same schema and binding as the image
                       review, by claude), recorded as spec.claude_image_review. It never replaces the independent
                       image review and never grades PASS for it. run.md must equal the file (else FAIL: re-run
                       manifest); an invalid, unbound or stale file, or a reviewer other than claude, is a WARN; a
                       FAIL verdict is missing work (the agent regenerates or the run stays draft). A missing file is
                       a WARN only in the full review tier: review_tier computes the tier at check time from
                       scripts/assetgen/data/review-tiers.json (light purposes icon, ui-element, texture-tileable; any
                       other purpose is full; a run with selected style-lock anchors is always full) and never records
                       it. In the light tier a missing file grades PASS; a present file is graded as in the full tier.
  gen-run-qa           qa.json is the evidence: it hashed the recorded output bytes, run.md's qa equals its state and
                       results (else FAIL: re-run manifest), its state is PASS, and every recorded output has a PASS
                       row for each check the purpose requires (runfiles.required_checks of the run's spec.json
                       purpose, whose content hash must equal spec.purpose.sha256). NOT_AVAILABLE never grades PASS:
                       it is missing work (install Pillow, re-run qa). A report that claims PASS while a row is not
                       PASS or a required check is missing contradicts itself and always FAILS; rows for unrecorded
                       outputs FAIL. Style consistency rows (style-*, never required checks) are graded as qa.json says:
                       WARN stays WARN (a soft signal, never FAIL), NOT_AVAILABLE neither grades nor contradicts, and a
                       style-* FAIL row must agree with a FAIL qa state. With spec.style_lock qa.json must record the
                       style inputs it graded with (style_binding = runfiles.qa_style_binding of spec.json and the run's
                       anchor copies: style ref, effective style data hash, family, anchor copy hashes), else FAIL as
                       stale (re-run qa and manifest); a report without style_binding counts as stale.
  gen-run-outputs      outputs recorded, inside the run directory, on disk, sha256 equal; no unrecorded outputs/*.png
  gen-run-provenance   provenance {generated_by, tool comfyui, model} complete and equal to spec.generation;
                       the rendered workflow.json is present; run.md spec.params equal the rendered params
                       (runfiles.rendered_params of workflow.json over spec.json), else FAIL (re-run manifest)
  gen-run-style        the style lock (spec.style_lock, resolve with project.json, anchors and rejections): the style ref
                       is well formed, names the run's style and resolves (a newer version or another hash is a WARN:
                       anchors of the recorded version stay valid), run.md equals spec.json, an override carries a
                       reason (WARN, the approver weighs it). Every recorded reference names an anchor that exists, is
                       well formed and active (retired since the run: WARN), approved by a person (not an agent or
                       model name), whose image bytes equal image_sha256, the run's pick and the source output, and
                       whose source gen-run is approved in run.md and by its signed approval (ctx.approval). An active
                       anchor promoted from this run FAILS while this run is not approved. With the style lock the
                       image reviews also bind the style ref and the anchors shown (else stale). A run recorded before
                       the style lock with no anchor promoted from it gets no row.
  gen-run-refs         purpose, style and template resolve in the core + game layers (content drift = WARN, the
                       record keeps what was used), prompt_sha256 and prompt.md match the recorded prompt, and a
                       handoff contract assetgen-to-<handoff_domain> is registered
  gen-run-workflow-style
                       the quality plugin check workflow-style: the run's workflow.ui.json against the workflow style
                       guide (scripts/assetgen/graphstyle.py ui_violations, node types from
                       scripts/assetgen/data/known-nodes.json). A first phase: every violation and an unreadable file
                       are WARN, never FAIL, whatever the run status; no violation is PASS. A run directory without
                       workflow.ui.json gets no row.

Integrity violations (hash or prompt mismatch, path escape, unmarked same-model review, unresolved ref) always FAIL.
Missing work (a review, QA, an output file or the model not recorded yet) FAILS once the run claims completeness
(proposed and later) and is a WARN while the run is draft, rejected, blocked, superseded or deprecated.
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

from domains._api import Result

ROOT = Path(__file__).resolve().parents[3]
LENIENT = {"draft", "rejected", "blocked", "superseded", "deprecated"}
FALLBACK = "SAME_MODEL:"
REVIEW_FILES = {"prompt": "review-prompt.json", "image": "review-image.json"}
CLAUDE_REVIEW = "review-image-claude.json"
REVIEW_TIERS = ROOT / "scripts" / "assetgen" / "data" / "review-tiers.json"
KNOWN_NODES = ROOT / "scripts" / "assetgen" / "data" / "known-nodes.json"
_engine = {}
_review_tiers = []


def engine(name):
    """scripts/assetgen/<name>.py (layers: the resolver; runfiles: evidence rules; stylelock: anchors and style refs;
    graphstyle: the workflow style guide),
    loaded once under a private name. stylelock's `import layers` is bound to the private layers module for the load
    only, so sys.modules keeps no engine module under its plain name."""
    if name not in _engine:
        spec = importlib.util.spec_from_file_location("assetgen_" + name, ROOT / "scripts" / "assetgen" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        if name == "stylelock":
            saved = sys.modules.get("layers")
            sys.modules["layers"] = engine("layers")
            try:
                spec.loader.exec_module(module)
            finally:
                if saved is None:
                    del sys.modules["layers"]
                else:
                    sys.modules["layers"] = saved
        else:
            spec.loader.exec_module(module)
        _engine[name] = module
    return _engine[name]


def review_tiers():
    """data/review-tiers.json, loaded once; None when it is unreadable or not JSON (every run is then full)."""
    if not _review_tiers:
        try:
            _review_tiers.append(json.loads(REVIEW_TIERS.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            _review_tiers.append(None)
    return _review_tiers[0]


def review_tier(spec, table=None):
    """The review tier of a run, "light" or "full", computed at check time and never recorded: a run with selected
    style-lock anchors is full; else the tier table[purposes][spec.purpose.id] (table defaults to
    data/review-tiers.json). Anything other than "light" (unknown or missing purpose, malformed table) is full."""
    try:
        if not isinstance(spec, dict) or engine("runfiles").style_lock_references(spec):
            return "full"
        table = review_tiers() if table is None else table
        purpose = spec.get("purpose")
        pid = purpose.get("id") if isinstance(purpose, dict) else None
        tiers = table.get("purposes") if isinstance(table, dict) else None
        if isinstance(pid, str) and isinstance(tiers, dict) and tiers.get(pid) == "light":
            return "light"
    except Exception:
        pass
    return "full"


def layers():
    return engine("layers")


def family(name):
    return re.split(r"[-_/.:@ ]", str(name).strip().lower(), maxsplit=1)[0]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def check(artifact, ctx):
    if artifact.get("kind") != "gen-run":
        return [Result("assetgen-kind", "FAIL", ["unrecognized assetgen artifact kind"])]
    spec = artifact.get("spec") if isinstance(artifact.get("spec"), dict) else {}
    lenient = artifact.get("status") in LENIENT
    results = []

    def grade(name, fails, todo=(), warns=(), human=()):
        """fails: always FAIL; todo: FAIL unless the status is lenient (then WARN); human: HUMAN_REQUIRED (a person
        must act, nothing is wrong); warns: WARN."""
        fails, todo, warns, human = list(fails), list(todo), list(warns), list(human)
        if fails or (todo and not lenient):
            results.append(Result(name, "FAIL", fails + todo + human + warns))
        elif human:
            results.append(Result(name, "HUMAN_REQUIRED", human + todo + warns))
        elif todo or warns:
            results.append(Result(name, "WARN", todo + warns))
        else:
            results.append(Result(name, "PASS", []))

    run_id = spec.get("run_id") if isinstance(spec.get("run_id"), str) else ""
    rel = PurePosixPath(str(ctx.artifact_path).replace("\\", "/"))
    run_rel = str(rel.parent)
    expected = "assetgen/runs/%s/run.md" % run_id
    fails = [] if str(rel) == expected else ["run record must be %s, found at %s" % (expected, rel)]
    if artifact.get("id") != "AGEN-" + run_id:
        fails.append("id must be AGEN-%s, found %s" % (run_id, artifact.get("id")))
    grade("gen-run-location", fails)

    def resolve(name):
        """Absolute path of a run-relative file, or None when it escapes the repo."""
        roots = ctx.repo_roots or {}
        if "authoring" in roots:
            return ctx.resolve_repo_path("authoring", run_rel + "/" + name)
        base = Path(ctx.repo).resolve()
        p = (base / run_rel / name).resolve()
        return p if p == base or base in p.parents else None

    outputs = [o for o in spec.get("outputs") or [] if isinstance(o, dict)]
    recorded = {o.get("path"): o.get("sha256") for o in outputs}
    runfiles = engine("runfiles")
    sj = resolve("spec.json")
    try:
        spec_json = json.loads(sj.read_text(encoding="utf-8")) if sj is not None and sj.is_file() else None
        purpose = spec_json["purpose"] if spec_json is not None else None
    except (OSError, ValueError, KeyError, TypeError):
        spec_json, purpose = None, False
    wf = resolve("workflow.json")
    try:
        workflow = json.loads(wf.read_text(encoding="utf-8")) if wf is not None and wf.is_file() else None
    except (OSError, ValueError):
        workflow = None
    size = runfiles.requested_size(workflow, spec_json if isinstance(spec_json, dict) else spec)
    # a review is bound to the params it was shown: the rendered params (workflow.json read back over spec.json), what
    # review-cmd hands out and manifest records as run.md spec.params; never substituted from spec.json
    rendered = runfiles.rendered_params(workflow, spec_json)[0] if isinstance(spec_json, dict) else None
    bound = dict(spec, params=rendered) if rendered is not None else spec
    requirements = {"prompt": runfiles.requirements_sha256(bound, None), "image": runfiles.requirements_sha256(
        bound, runfiles.generation_inputs(workflow, spec_json if isinstance(spec_json, dict) else spec,
                                    lambda name: resolve("references/" + name)))}
    lock = spec.get("style_lock") if isinstance(spec.get("style_lock"), dict) else None

    def lock_stale(disk):
        """With spec.style_lock an image verdict names the style ref and the anchors it was shown (review-cmd binding)."""
        if lock is None:
            return False
        want = [{"anchor_id": r.get("anchor_id"), "sha256": r.get("sha256")} for r in runfiles.style_lock_references(spec)]
        return disk.get("style") != lock.get("style") or disk.get("anchors") != want

    author = spec.get("prompt_author") or ""
    for phase in ("prompt", "image"):
        rv = spec.get(phase + "_review") if isinstance(spec.get(phase + "_review"), dict) else {}
        by, state, fails, todo, warns = rv.get("by") or "", rv.get("state"), [], [], []
        name = REVIEW_FILES[phase]
        rf = resolve(name)
        if rf is None or not rf.is_file():
            todo.append("%s is missing from the run directory (run the review, then assetgen.py manifest)" % name)
        else:
            disk = runfiles.read_verdict(str(rf), phase)
            if disk != rv:
                fails.append("run.md %s_review differs from %s (file: %s by %s); re-run assetgen.py manifest"
                             % (phase, name, disk["state"], disk["by"] or "-"))
            if disk["state"] == "INVALID":
                todo.append("%s holds no JSON verdict with state PASS or FAIL" % name)
            elif disk["prompt_sha256"] != spec.get("prompt_sha256"):
                todo.append("%s is bound to prompt %s, not the recorded prompt %s: re-run the review (review-cmd)"
                            % (name, str(disk["prompt_sha256"])[:12], str(spec.get("prompt_sha256"))[:12]))
            elif phase == "image" and {o["path"]: o["sha256"] for o in disk["outputs"]} != recorded:
                todo.append("%s is bound to other outputs than the recorded ones: re-run the image review" % name)
            elif disk["requirements_sha256"] != requirements[phase]:
                todo.append("%s is bound to other requirements (purpose, style, template or params changed since the "
                            "review%s): re-run the review" % (name, ", or the generation inputs" if phase == "image" else ""))
            elif phase == "image" and lock_stale(disk):
                todo.append("%s is not bound to the style lock (its style ref and anchors differ from spec.style_lock: "
                            "%s with %d anchor(s)): re-run the image review with review-cmd" % (
                                name, (lock.get("style") or {}).get("style_id"), len(runfiles.style_lock_references(spec))))
        if state != "PASS":
            todo.append("%s review is %s%s (evidence review-%s.json)" % (
                phase, state or "missing", ", %s finding(s)" % rv.get("findings") if rv.get("findings") else "", phase))
        if not author:
            fails.append("prompt_author is not recorded")
        if by:
            marked = by.startswith(FALLBACK)
            model = by[len(FALLBACK):] if marked else by
            same = bool(author) and family(model) == family(author)
            if marked and same:
                warns.append("%s review is a same-model fallback by %s (prompt author %s): the independent reviewer "
                             "was not available; the human approver weighs it" % (phase, model, author))
            elif marked:
                fails.append("%s review is marked %s but %s is not the prompt author %s; drop the marker"
                             % (phase, FALLBACK.rstrip(":"), model, author))
            elif same:
                fails.append("%s review by %s, the prompt author's model %s: an independent model must review, or "
                             "an unavailable reviewer is recorded explicitly as by \"%s%s\"" % (phase, by, author, FALLBACK, model))
        elif state == "PASS":
            fails.append("%s review PASS without a reviewer (by)" % phase)
        grade("gen-run-%s-review" % phase, fails, todo, warns)

    fails, todo, warns = [], [], []
    rv = spec.get("claude_image_review") if isinstance(spec.get("claude_image_review"), dict) else None
    rf = resolve(CLAUDE_REVIEW)
    if rf is None or not rf.is_file():
        if review_tier(spec) != "light":  # light tier: Claude's own review is optional, a present file is still graded
            warns.append("%s is missing: record Claude's own visual review (review schema, by claude, the binding of "
                         "review-cmd --phase image --json), then assetgen.py manifest" % CLAUDE_REVIEW)
        if rv is not None and rv.get("state") not in (None, "NOT_RUN"):
            fails.append("run.md claude_image_review is %s but %s is missing; re-run assetgen.py manifest"
                         % (rv.get("state"), CLAUDE_REVIEW))
    else:
        disk = runfiles.read_verdict(str(rf), "image")
        if disk != rv:
            fails.append("run.md claude_image_review differs from %s (file: %s by %s); re-run assetgen.py manifest"
                         % (CLAUDE_REVIEW, disk["state"], disk["by"] or "-"))
        if disk["state"] == "INVALID":
            warns.append("%s holds no JSON verdict with state PASS or FAIL" % CLAUDE_REVIEW)
        elif disk["prompt_sha256"] != spec.get("prompt_sha256") or disk["requirements_sha256"] != requirements["image"]                 or {o["path"]: o["sha256"] for o in disk["outputs"]} != recorded or lock_stale(disk):
            warns.append("%s is not bound to the current prompt, requirements, outputs and style lock: review the images again "
                         "with the binding of review-cmd --phase image --json" % CLAUDE_REVIEW)
        elif disk["state"] == "FAIL":
            todo.append("Claude's visual review is FAIL (%d finding(s)): regenerate, or keep the run draft"
                        % disk["findings"])
        if disk["state"] != "INVALID" and family(disk["by"] or "") != "claude":
            warns.append("%s is by %s, not claude; the independent review belongs in %s"
                         % (CLAUDE_REVIEW, disk["by"] or "-", REVIEW_FILES["image"]))
    grade("gen-run-claude-review", fails, todo, warns)

    fails, todo = [], []
    if not outputs:
        todo.append("no outputs recorded (fetch_outputs into outputs/, then assetgen.py manifest)")
    for path, digest in recorded.items():
        full = resolve(path) if isinstance(path, str) else None
        if full is None:
            fails.append("output %r is not a path inside the run directory" % path)
        elif not full.is_file():
            todo.append("output %s is missing on disk" % path)
        elif sha256_file(full) != digest:
            fails.append("output %s: sha256 on disk differs from the record; re-run qa and manifest" % path)
    out_dir = resolve("outputs")
    if out_dir is not None and out_dir.is_dir():
        for name in sorted(os.listdir(out_dir)):
            if name.lower().endswith(".png") and "outputs/" + name not in recorded:
                fails.append("outputs/%s is not recorded; re-run qa and manifest" % name)
    grade("gen-run-outputs", fails, todo)

    fails, todo = [], []
    qa = spec.get("qa") if isinstance(spec.get("qa"), dict) else {}
    disk = None
    qa_file = resolve("qa.json")
    if qa_file is not None and qa_file.is_file():
        try:
            disk = json.loads(qa_file.read_text(encoding="utf-8"))
            hashed = {o.get("path"): o.get("sha256") for o in disk.get("outputs") or [] if isinstance(o, dict)}
        except (OSError, ValueError, AttributeError):
            disk = None
            fails.append("qa.json is not readable JSON")
        else:
            if hashed != recorded:
                fails.append("qa.json checked other bytes than the recorded outputs; re-run qa and manifest")
            if [disk.get("state"), disk.get("results", [])] != [qa.get("state"), qa.get("results")]:
                fails.append("run.md qa (%s) differs from qa.json (%s); re-run assetgen.py manifest"
                             % (qa.get("state"), disk.get("state")))
    else:
        todo.append("qa.json is missing from the run directory (assetgen.py qa)")
    state = disk.get("state") if disk is not None else None
    all_rows = [r for r in (disk or {}).get("results") or [] if isinstance(r, dict)]
    rows = [r for r in all_rows if not (str(r.get("check", "")).startswith("style-") and r.get("state") in ("WARN", "NOT_AVAILABLE"))]
    required, problems = None, []
    rec_purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
    if purpose is None:
        todo.append("spec.json is missing from the run directory; the purpose's required QA checks are unknown")
    elif not isinstance(purpose, dict) or not isinstance(purpose.get("data"), dict) \
            or layers().content_hash(purpose["data"]) != rec_purpose.get("sha256"):
        fails.append("spec.json purpose is not the purpose the run recorded (unreadable, or its content hash "
                     "differs from spec.purpose.sha256)")
    else:
        purpose_qa = purpose["data"].get("qa", {})
        malformed = runfiles.qa_errors(purpose_qa)
        if malformed:
            fails.append("spec.json purpose qa block is malformed (%s); fix the purpose, resolve, re-run qa and manifest"
                         % "; ".join(malformed))
        required = runfiles.required_checks(purpose_qa)
    if disk is not None:
        if disk.get("purpose_sha256") != rec_purpose.get("sha256"):
            fails.append("qa.json was graded with another purpose qa block (purpose_sha256 %s, run records %s); "
                         "re-run qa and manifest" % (disk.get("purpose_sha256"), rec_purpose.get("sha256")))
        if disk.get("requested_size") != size:
            fails.append("qa.json was graded for requested size %r, the run now requests %r; re-run qa and manifest"
                         % (disk.get("requested_size"), size))
        if isinstance(spec_json, dict):
            now = runfiles.qa_style_binding(spec_json, lambda rel: resolve(rel))
            was = disk.get("style_binding")
            if now is not None and not isinstance(was, dict):
                fails.append("qa.json does not record the style inputs it graded with (style_binding: a report from "
                             "before the binding); re-run qa and manifest")
            elif was != now:
                what = [k for k in ("style", "style_sha256", "family", "anchors")
                        if (was or {}).get(k) != (now or {}).get(k)] or ["style_lock"]
                fails.append("qa.json was graded with other style inputs (%s differ from spec.json and the run's "
                             "anchor copies); re-run qa and manifest" % ", ".join(what))
        if state != "PASS":
            todo.append("QA is %s; run assetgen.py qa until it reports PASS, then manifest" % (state or "missing"))
        for path in recorded:
            mine = [r for r in rows if r.get("output") == path]
            bad = ["%s %s" % (r.get("check"), r.get("state")) for r in mine if r.get("state") != "PASS"]
            if any(r.get("state") == "NOT_AVAILABLE" for r in mine):
                bad.append("NOT_AVAILABLE does not grade PASS (install Pillow, re-run qa)")
            missing = [c for c in required or [] if c not in {r.get("check") for r in mine}]
            if not mine:
                problems.append("QA results do not cover %s" % path)
            elif bad:
                problems.append("QA of %s: %s" % (path, ", ".join(bad)))
            if mine and missing:
                problems.append("QA of %s lacks the required check(s) %s" % (path, ", ".join(missing)))
        stale = sorted({str(r.get("output")) for r in all_rows} - set(recorded) - {"outputs/"})
        if stale:
            fails.append("QA results name outputs that are not recorded: " + ", ".join(stale))
        if state == "PASS" and (problems or any(r.get("state") != "PASS" for r in rows)):
            fails.append("qa.json claims PASS but contradicts its own rows: " + ("; ".join(problems) or "a row is not PASS"))
        else:
            todo += problems
    style_warns = ["style consistency %s: %s %s%s" % (r.get("output"), r.get("check"), r.get("state"),
                                                       " (%s)" % "; ".join(map(str, r.get("reasons") or [])) if r.get("reasons") else "")
                   for r in all_rows if str(r.get("check", "")).startswith("style-") and r.get("state") == "WARN"]
    grade("gen-run-qa", fails, todo, style_warns)

    prov = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    gen = spec.get("generation") if isinstance(spec.get("generation"), dict) else {}
    fails, todo = [], []
    if prov.get("tool") != "comfyui":
        fails.append("provenance.tool must be comfyui, found %r" % prov.get("tool"))
    for key in ("generated_by", "model"):
        if not prov.get(key):
            todo.append("provenance.%s is not recorded" % key)
        elif gen.get(key) != prov.get(key):
            fails.append("provenance.%s %r differs from spec.generation.%s %r" % (key, prov.get(key), key, gen.get(key)))
    if gen.get("tool") != prov.get("tool"):
        fails.append("spec.generation.tool %r differs from provenance.tool %r" % (gen.get("tool"), prov.get("tool")))
    wf = resolve("workflow.json")
    if gen.get("workflow") != "workflow.json" or wf is None or not wf.is_file():
        todo.append("the rendered workflow.json is not recorded in the run directory (assetgen.py render --run)")
    sent = runfiles.workflow_prompts(workflow)
    if workflow is not None and sent and any(p != spec.get("prompt") for p in sent):
        todo.append("workflow.json sends another prompt than the recorded one (prompt.md); re-render the workflow "
                    "and generate again")
    for name in runfiles.reference_names(workflow):
        ref = resolve("references/" + os.path.basename(name))
        if ref is None or not ref.is_file():
            todo.append("reference image %s is not kept as references/%s in the run directory (copy the original "
                        "there before upload_file; the image review binds its sha256)" % (name, os.path.basename(name)))
    recorded_params = spec.get("params") if isinstance(spec.get("params"), dict) else None
    if rendered is not None and recorded_params != rendered:
        diff = sorted(k for k in set(rendered) | set(recorded_params or {})
                      if (recorded_params or {}).get(k, "<absent>") != rendered.get(k, "<absent>"))
        fails.append("run.md spec.params differ from the rendered params (workflow.json over spec.json) in %s; re-run "
                     "assetgen.py manifest" % (", ".join(diff) or "type"))
    grade("gen-run-provenance", fails, todo)

    fails, todo, warns = [], [], []
    lay = layers()
    for kind, key in (("purpose", "purpose"), ("style", "style"), ("template", "template")):
        ref = spec.get(key) if isinstance(spec.get(key), dict) else {}
        try:
            entry = lay.load(kind, ref.get("id"), ctx.repo)
        except (lay.SpecError, TypeError) as exc:
            fails.append("%s %r does not resolve in the core or game layer: %s" % (kind, ref.get("id"), exc))
            continue
        now = lay.content_hash(entry["data"])
        if now != ref.get("sha256") or entry["layer"] != ref.get("layer"):
            warns.append("%s %s changed since the run (recorded %s %s, now %s %s); the record keeps what was used"
                         % (kind, ref.get("id"), ref.get("layer"), str(ref.get("sha256"))[:12], entry["layer"], now[:12]))
    prompt = spec.get("prompt") if isinstance(spec.get("prompt"), str) else ""
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != spec.get("prompt_sha256"):
        fails.append("prompt_sha256 does not match the recorded prompt")
    pf = resolve("prompt.md")
    if pf is None or not pf.is_file():
        todo.append("prompt.md is missing from the run directory")
    elif pf.read_text(encoding="utf-8").strip() != prompt:
        fails.append("prompt.md differs from the recorded prompt; re-run assetgen.py manifest")
    target = spec.get("handoff_domain")
    if not any(c.get("id") == "assetgen-to-%s" % target and c.get("kind") == "handoff" for c in ctx.registry.get("contracts", [])):
        fails.append("no handoff contract assetgen-to-%s is registered for handoff_domain %r" % (target, target))
    grade("gen-run-refs", fails, todo, warns)
    style_check(artifact, spec, spec_json, lock, recorded, run_id, ctx, grade)
    ui_file = resolve("workflow.ui.json")
    if ui_file is not None and ui_file.is_file():
        grade("gen-run-workflow-style", [], warns=workflow_style_warnings(ui_file))
    return results


def workflow_style_warnings(ui_file):
    """The quality plugin check workflow-style: graphstyle.ui_violations of the run's workflow.ui.json, each a WARN
    (never FAIL in this first phase, whatever the run status)."""
    try:
        ui = json.loads(ui_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["workflow.ui.json is not readable JSON"]
    try:
        known = json.loads(KNOWN_NODES.read_text(encoding="utf-8"))["nodes"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["scripts/assetgen/data/known-nodes.json is not readable; the workflow style is not checked"]
    try:
        return list(engine("graphstyle").ui_violations(ui, known))
    except Exception as exc:  # a quality check never crashes the run: a graphstyle bug is a WARN naming it
        return ["the workflow style check failed (%s: %s)" % (type(exc).__name__, exc)]


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, encoding="utf-8")
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def pending_approval(authoring, run_id):
    """(path, committed) of the gen-run approval record on disk for run.md as it is now (or as committed), or None.
    committed: run.md and the record are both in HEAD as they are on disk (the signature is ctx.approval's)."""
    rel_md = "assetgen/runs/%s/run.md" % run_id
    md = Path(authoring) / rel_md
    if not md.is_file():
        return None
    disk = _git(authoring, "hash-object", "--", rel_md)
    if not disk:
        data = md.read_bytes()
        disk = hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()
    head = _git(authoring, "rev-parse", "HEAD:" + rel_md)
    for rev in dict.fromkeys(r for r in (disk, head) if r):
        rel = "approvals/AGEN-%s/assetgen-approval-%s.json" % (run_id, rev)
        if (Path(authoring) / rel).is_file():
            added = _git(authoring, "log", "--no-renames", "--diff-filter=A", "--format=%H", "--", rel)
            dirty = _git(authoring, "status", "--porcelain", "--", rel, rel_md)
            return rel, bool(added) and dirty == "" and head == disk
    return None


def anchor_problems(rec, stylelock, ctx, authoring):
    """(fails, warns, human) of one anchor record: well formed, a person approved it, image bytes, source gen-run
    approved in the engine view (run.md status) and by its signed approval. A retired anchor only warns. An approval
    record that is on disk but not committed or not signed is HUMAN_REQUIRED (the person commits and signs it), the
    grade the trace check gives."""
    data, fails, warns, human = rec["data"], [], [], []
    aid = rec["id"]
    if rec["errors"]:
        return ["anchor %s is malformed: %s" % (aid, "; ".join(rec["errors"]))], [], []
    if data["status"] == "retired":
        warns.append("anchor %s is retired since the run; the record keeps what was used" % aid)
    elif data["status"] != "active":
        fails.append("anchor %s is %s, not active: only a person activates an anchor (status active, approved_by, "
                     "approved_on)" % (aid, data["status"]))
    image = os.path.join(os.path.dirname(rec["path"]), data["image"])
    if not os.path.isfile(image):
        fails.append("anchor %s image %s is missing" % (aid, data["image"]))
    elif sha256_file(image) != data["image_sha256"]:
        fails.append("anchor %s image %s: sha256 on disk differs from image_sha256" % (aid, data["image"]))
    if data["image_sha256"] != data["source_run"]["sha256"]:
        fails.append("anchor %s image_sha256 is not the sha256 of its source output %s"
                     % (aid, data["source_run"]["output"]))
    source = data["source_run"]["run_id"]
    status = stylelock.run_status(authoring, source)
    if status != "approved":
        fails.append("anchor %s: source gen-run %s is %s, not approved" % (aid, source, status or "missing (no run.md)"))
    else:
        verdict = ctx.approval("AGEN-" + source)
        state = (verdict or {}).get("state", "missing") if isinstance(verdict, dict) else "missing"
        if state != "verified":
            pending = pending_approval(authoring, source)
            if pending and (not pending[1] or state in ("missing", "untrusted")):
                human.append("anchor %s: the approval of source gen-run AGEN-%s is present but not committed/signed (%s): "
                             "the person commits run.md and the record in one signed commit" % (aid, source, pending[0]))
            else:
                fails.append("anchor %s: the approval of source gen-run AGEN-%s is %s (%s)" % (
                    aid, source, state, "; ".join((verdict or {}).get("reasons") or [] if isinstance(verdict, dict) else [])))
    return fails, warns, human


def style_check(artifact, spec, spec_json, lock, recorded, run_id, ctx, grade):
    """gen-run-style: the style lock of the run (style ref, recorded anchors, override) and the anchors promoted from
    this run's outputs. A run recorded before the style lock with no anchor promoted from it gets no row."""
    stylelock = engine("stylelock")
    authoring = (ctx.repo_roots or {}).get("authoring") or ctx.repo
    sourced = []
    for _, kind, path in stylelock.anchor_files(authoring):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        src = data.get("source_run") if kind == "anchor" and isinstance(data, dict) else None
        if isinstance(src, dict) and src.get("run_id") == run_id:
            sourced.append((path, data))
    if lock is None and not sourced:
        return
    fails, warns, human = [], [], []
    if lock is not None:
        ref = lock.get("style")
        errs = stylelock.ref_errors(ref, "spec.style_lock.style")
        fails += errs
        st = spec.get("style") if isinstance(spec.get("style"), dict) else {}
        if not errs:
            if ref["style_id"] != st.get("id") or ref["sha256"] != st.get("sha256"):
                fails.append("spec.style_lock.style (%s %s) is not the run's style (%s %s)" % (
                    ref["style_id"], ref["sha256"][:12], st.get("id"), str(st.get("sha256"))[:12]))
            lay = layers()
            try:
                now = stylelock.style_ref(lay.load("style", ref["style_id"], authoring))
            except lay.SpecError as exc:
                fails.append("style %s of the style lock does not resolve: %s" % (ref["style_id"], exc))
            else:
                if now != ref:
                    warns.append("style %s changed since the run (recorded v%s %s, now v%s %s); anchors of the recorded "
                                 "version stay valid, the record keeps what was used" % (
                                     ref["style_id"], ref.get("version"), ref["sha256"][:12], now["version"], now["sha256"][:12]))
        if isinstance(spec_json, dict) and spec_json.get("style_lock") != lock:
            fails.append("run.md spec.style_lock differs from spec.json; re-run assetgen.py manifest")
        override = lock.get("override")
        if override is not None:
            if isinstance(override, str) and override.strip():
                warns.append("style override recorded: %s (the human approver weighs it)" % override.strip())
            else:
                fails.append("spec.style_lock.override must be null or a non-empty reason")
        refs = lock.get("references")
        picks = [r for r in refs if isinstance(r, dict)] if isinstance(refs, list) else []
        if refs is not None and (not isinstance(refs, list) or len(picks) != len(refs)):
            fails.append("spec.style_lock.references must be a list of anchor picks")
        cap = lock.get("max_references")
        if isinstance(cap, int) and len(picks) > cap:
            fails.append("spec.style_lock.references holds %d anchors, more than max_references %d" % (len(picks), cap))
        sid = ref.get("style_id") if isinstance(ref, dict) else None
        records = {r["id"]: r for r in stylelock.load_anchors(authoring, sid)} if not errs else {}
        for pick in picks:
            aid = pick.get("anchor_id")
            rec = records.get(aid) if isinstance(aid, str) else None
            if rec is None:
                fails.append("anchor %s is not in assetgen/styles/%s/anchors/" % (aid, sid))
                continue
            f, w, h = anchor_problems(rec, stylelock, ctx, authoring)
            if not rec["errors"] and pick.get("sha256") != rec["data"]["image_sha256"]:
                f.append("anchor %s: the run used image sha256 %s, the anchor now holds %s" % (
                    aid, str(pick.get("sha256"))[:12], rec["data"]["image_sha256"][:12]))
            fails += f
            warns += w
            human += h
    for path, data in sourced:
        aid = data.get("id") or os.path.basename(path)[:-5]
        if data.get("status") != "active":
            continue
        if artifact.get("status") != "approved":
            fails.append("anchor %s is active but its source gen-run AGEN-%s is %s, not approved: retire the anchor or "
                         "have a person approve the run" % (aid, run_id, artifact.get("status")))
        by = data.get("approved_by")
        if not isinstance(by, str) or not by.strip() or stylelock.is_agent_name(by):
            fails.append("anchor %s is active without a person's approval (approved_by %r): only a person activates an "
                         "anchor" % (aid, by))
        src = data.get("source_run")
        if not isinstance(src, dict) or recorded.get(src.get("output")) != src.get("sha256"):
            src = src if isinstance(src, dict) else {}
            fails.append("anchor %s names output %s sha256 %s, which this run does not record" % (
                aid, src.get("output"), str(src.get("sha256"))[:12]))
    grade("gen-run-style", fails, (), warns, human)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
