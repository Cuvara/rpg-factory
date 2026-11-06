#!/usr/bin/env python3
"""Asset generation (assetgen) domain quality rules for gen-run records; read-only, no network, no ComfyUI.

A gen-run is <authoring>/assetgen/runs/<run_id>/run.md, written by scripts/assetgen/assetgen.py manifest. Checks:

  gen-run-location     run.md sits at assetgen/runs/<run_id>/run.md and the id is AGEN-<run_id>
  gen-run-prompt-review / gen-run-image-review
                       state PASS, by a model other than the prompt author (model family: the part of the name
                       before the first - _ / . : @ or space, so claude-sonnet counts as claude). A same-model review
                       is allowed only as an explicit fallback: by = "SAME_MODEL:<model>" grades WARN (the human
                       approver weighs it); an unmarked same-model review FAILS, and a marker naming another model
                       than the author FAILS (it is not a fallback).
  gen-run-qa           qa.state PASS, every output covered by PASS rows only, no rows for unrecorded outputs, and
                       qa.json (when present) hashed the same bytes as the recorded outputs
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
_layers = None


def layers():
    """scripts/assetgen/layers.py (the engine's resolver), loaded once."""
    global _layers
    if _layers is None:
        spec = importlib.util.spec_from_file_location("assetgen_layers", ROOT / "scripts" / "assetgen" / "layers.py")
        _layers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_layers)
    return _layers


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

    author = spec.get("prompt_author") or ""
    for phase in ("prompt", "image"):
        rv = spec.get(phase + "_review") if isinstance(spec.get(phase + "_review"), dict) else {}
        by, state, fails, todo, warns = rv.get("by") or "", rv.get("state"), [], [], []
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

    outputs = [o for o in spec.get("outputs") or [] if isinstance(o, dict)]
    recorded = {o.get("path"): o.get("sha256") for o in outputs}
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

    qa = spec.get("qa") if isinstance(spec.get("qa"), dict) else {}
    rows = [r for r in qa.get("results") or [] if isinstance(r, dict)]
    fails, todo = [], []
    if qa.get("state") != "PASS":
        todo.append("QA is %s; run assetgen.py qa until it reports PASS, then manifest" % (qa.get("state") or "missing"))
    for path in recorded:
        mine = [r for r in rows if r.get("output") == path]
        if not mine:
            todo.append("QA results do not cover %s" % path)
        elif any(r.get("state") != "PASS" for r in mine):
            todo.append("QA of %s: %s" % (path, ", ".join("%s %s" % (r.get("check"), r.get("state")) for r in mine if r.get("state") != "PASS")))
    stale = sorted({r.get("output") for r in rows} - set(recorded) - {"outputs/"})
    if stale:
        fails.append("QA results name outputs that are not recorded: " + ", ".join(map(str, stale)))
    qa_file = resolve("qa.json")
    if qa_file is not None and qa_file.is_file():
        try:
            disk = json.loads(qa_file.read_text(encoding="utf-8"))
            hashed = {o.get("path"): o.get("sha256") for o in disk.get("outputs") or [] if isinstance(o, dict)}
            if hashed != recorded:
                fails.append("qa.json checked other bytes than the recorded outputs; re-run qa and manifest")
        except (OSError, ValueError, AttributeError):
            fails.append("qa.json is not readable JSON")
    elif recorded:
        todo.append("qa.json is missing from the run directory")
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
