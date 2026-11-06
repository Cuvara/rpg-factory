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
                       params; for the image review also the generation inputs of workflow.json) and, for the
                       image review, outputs = the recorded outputs (review-cmd hands the reviewer these values to copy back). A missing, invalid,
                       unbound or stale review file is missing work.
  gen-run-qa           qa.json is the evidence: it hashed the recorded output bytes, run.md's qa equals its state and
                       results (else FAIL: re-run manifest), its state is PASS, and every recorded output has a PASS
                       row for each check the purpose requires (runfiles.required_checks of the run's spec.json
                       purpose, whose content hash must equal spec.purpose.sha256). NOT_AVAILABLE never grades PASS:
                       it is missing work (install Pillow, re-run qa). A report that claims PASS while a row is not
                       PASS or a required check is missing contradicts itself and always FAILS; rows for unrecorded
                       outputs FAIL.
  gen-run-outputs      outputs recorded, inside the run directory, on disk, sha256 equal; no unrecorded outputs/*.png
  gen-run-provenance   provenance {generated_by, tool comfyui, model} complete and equal to spec.generation;
                       the rendered workflow.json is present
  gen-run-refs         purpose, style and template resolve in the core + game layers (content drift = WARN, the
                       record keeps what was used), prompt_sha256 and prompt.md match the recorded prompt, and a
                       handoff contract assetgen-to-<handoff_domain> is registered

Integrity violations (hash or prompt mismatch, path escape, unmarked same-model review, unresolved ref) always FAIL.
Missing work (a review, QA, an output file or the model not recorded yet) FAILS once the run claims completeness
(proposed and later) and is a WARN while the run is draft, rejected, blocked, superseded or deprecated.
"""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path, PurePosixPath

from domains._api import Result

ROOT = Path(__file__).resolve().parents[3]
LENIENT = {"draft", "rejected", "blocked", "superseded", "deprecated"}
FALLBACK = "SAME_MODEL:"
REVIEW_FILES = {"prompt": "review-prompt.json", "image": "review-image.json"}
_engine = {}


def engine(name):
    """scripts/assetgen/<name>.py (layers: the resolver; runfiles: evidence rules), loaded once under a private name."""
    if name not in _engine:
        spec = importlib.util.spec_from_file_location("assetgen_" + name, ROOT / "scripts" / "assetgen" / (name + ".py"))
        _engine[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_engine[name])
    return _engine[name]


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

    def grade(name, fails, todo=(), warns=()):
        """fails: always FAIL; todo: FAIL unless the status is lenient (then WARN); warns: WARN."""
        fails, todo, warns = list(fails), list(todo), list(warns)
        if fails or (todo and not lenient):
            results.append(Result(name, "FAIL", fails + todo + warns))
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
    requirements = {"prompt": runfiles.requirements_sha256(spec, None), "image": runfiles.requirements_sha256(
        spec, runfiles.generation_inputs(workflow, spec_json if isinstance(spec_json, dict) else spec,
                                    lambda name: resolve("references/" + name)))}
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
    rows = [r for r in (disk or {}).get("results") or [] if isinstance(r, dict)]
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
        stale = sorted({str(r.get("output")) for r in rows} - set(recorded) - {"outputs/"})
        if stale:
            fails.append("QA results name outputs that are not recorded: " + ", ".join(stale))
        if state == "PASS" and (problems or any(r.get("state") != "PASS" for r in rows)):
            fails.append("qa.json claims PASS but contradicts its own rows: " + ("; ".join(problems) or "a row is not PASS"))
        else:
            todo += problems
    grade("gen-run-qa", fails, todo)

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
    for name in runfiles.reference_names(workflow):
        ref = resolve("references/" + os.path.basename(name))
        if ref is None or not ref.is_file():
            todo.append("reference image %s is not kept as references/%s in the run directory (copy the original "
                        "there before upload_file; the image review binds its sha256)" % (name, os.path.basename(name)))
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
    return results


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
