"""assetgen finalize: defringe (alpha purposes only), embed and qa in one fixed order, after fetch_outputs.

The three verbs keep their own contracts; this module only sequences them so embed can never be skipped before qa.
It never imports assetgen: assetgen.py passes its own module (`ag`), so there is no import cycle.

ag.fail() exits the process, so every condition a callee would fail() on is checked here first (precheck), before
anything is written; after that a step ends in a state, never in an exit. Steps stop at the first FAIL, naming it.

Exit codes follow qa: 0 PASS, 1 FAIL, 3 NOT_AVAILABLE.
"""
import glob
import json
import os

SCHEMA = "rpg-factory.assetgen-finalize/1"


def outputs_of(ag, run_dir):
    """{"outputs/<name>": sha256} of every outputs/*.png of the run: what a binding record names."""
    return {"outputs/" + os.path.basename(p): ag.qa.sha256(p)
            for p in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))}


def image_reviews(ag, run_dir):
    """The image review records (Codex's, Claude's) that bind the current outputs."""
    own = (ag.REVIEW_FILES["image"], ag.CLAUDE_REVIEW)
    return [n for n in ag.bound_records(run_dir, outputs_of(ag, run_dir)) if n in own]


def precheck(ag, run_dir):
    """Refuse, before any write, what a step would ag.fail() on. Returns (spec, defringe record or None)."""
    rel = run_dir.replace(os.sep, "/")
    if not os.path.isfile(os.path.join(run_dir, "spec.json")):
        ag.fail("finalize needs %s/spec.json (resolve --out first)" % rel)
    spec = ag.load_spec(os.path.join(run_dir, "spec.json"))
    if not glob.glob(os.path.join(run_dir, "outputs", "*.png")):
        ag.fail("no outputs/*.png in %s to finalize (fetch_outputs first)" % rel)
    front = ag.existing_front(os.path.join(run_dir, "run.md"))
    if isinstance(front, dict) and front.get("status") == "approved":
        ag.fail("run.md is approved: finalize would rewrite the approved outputs; start a new attempt <slug>-NNN+1 "
                "instead")
    ag.read_ui(run_dir)  # workflow.ui.json: embed fails without it
    ag.requested_size(run_dir, spec)  # workflow.json, when present, must parse: qa fails otherwise
    record = None
    path = os.path.join(run_dir, ag.DEFRINGE_FILE)
    if os.path.isfile(path):
        record = ag.read_json(path, "defringe record")
    return spec, record


def wants_alpha(spec):
    purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
    data = purpose.get("data") if isinstance(purpose.get("data"), dict) else {}
    qa = data.get("qa") if isinstance(data.get("qa"), dict) else {}
    return qa.get("alpha") == "required"


def needs_defringe(ag, path):
    """True unless defringe itself would skip the output (not 8-bit, or no transparent pixels). An unreadable output
    counts as needing it: defringe reports it as a FAIL row."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if ag.depth_refusal(data, "defringed"):
            return False
        img = ag.png.decode(path)
    except (ag.png.Invalid, ag.png.Unsupported, OSError):
        return True
    return bool(img.has_alpha) and min(img.rgba[3::4]) < 255


def defringe_step(ag, run_dir, spec, record, force):
    """The defringe step: {step, state: defringed|skipped|FAIL, reason, results}."""
    step = {"step": "defringe", "state": "skipped", "reason": "", "results": []}
    if not wants_alpha(spec):
        step["reason"] = "not an alpha purpose (qa.alpha is not required)"
        return step
    images = sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))
    todo = [p for p in images if needs_defringe(ag, p)]
    if not todo:
        step["reason"] = "no output needs it (no transparent pixels, or not 8-bit)"
        return step
    done = {}
    for o in (record.get("outputs") if isinstance(record, dict) else None) or []:
        if isinstance(o, dict) and o.get("after_pixels_sha256"):
            done[o.get("output")] = o["after_pixels_sha256"]
    if all(done.get("outputs/" + os.path.basename(p)) is not None
           and done["outputs/" + os.path.basename(p)] == ag.pixels_sha256(p) for p in todo):
        step["reason"] = "already defringed (defringe.json still matches the output pixels)"
        return step
    bound = ag.bound_records(run_dir, outputs_of(ag, run_dir))
    if bound and not force:
        step.update(state="FAIL", reason="%s already bind(s) the current outputs and defringe would change them; "
                    "pass --force to defringe anyway (then those records are stale: re-run them)" % ", ".join(bound))
        return step
    rows, _ = ag.defringe(run_dir, None, force)
    fails = [r for r in rows if r["state"] == "FAIL"]
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("defringed", "skipped", "FAIL")}
    step.update(state="FAIL" if fails else "defringed", results=rows,
                reason="%(defringed)d defringed, %(skipped)d skipped, %(FAIL)d FAIL" % counts)
    if fails:
        step["reason"] += ": " + "; ".join("%s: %s" % (r["output"], r["reason"]) for r in fails)
    return step


def embed_step(ag, run_dir):
    rows = ag.embed(run_dir)
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("embedded", "replaced", "kept", "FAIL")}
    reason = "%(embedded)d embedded, %(replaced)d replaced, %(kept)d kept, %(FAIL)d FAIL" % counts
    fails = [r for r in rows if r["state"] == "FAIL"]
    if fails:
        reason += ": " + "; ".join("%s: %s" % (r["output"], r["reason"]) for r in fails)
    return {"step": "embed", "state": "FAIL" if fails else "done", "reason": reason, "results": rows}


def qa_step(ag, run_dir):
    report, text, code = ag.qa_run(run_dir)
    return ({"step": "qa", "state": report["state"], "reason": "qa.json written", "results": report["results"],
             "summary": report["summary"]}, text, code)


def step_lines(step):
    lines = ["%s %s: %s" % (step["step"], step["state"], step["reason"])]
    lines += ["  %s %s: %s" % (r["state"], r["output"], r["reason"]) for r in step["results"] if step["step"] != "qa"]
    return lines


def run(ag, run_dir, force=False, as_json=False):
    """The finalize verb: returns the exit code (0 PASS, 1 FAIL, 3 NOT_AVAILABLE) after printing the result."""
    spec, record = precheck(ag, run_dir)
    before = image_reviews(ag, run_dir)
    steps, qa_text, code, failed = [], "", 0, None
    steps.append(defringe_step(ag, run_dir, spec, record, force))
    if steps[-1]["state"] == "FAIL":
        failed = "defringe"
    if not failed:
        steps.append(embed_step(ag, run_dir))
        if steps[-1]["state"] == "FAIL":
            failed = "embed"
    if not failed:
        step, qa_text, code = qa_step(ag, run_dir)
        steps.append(step)
        if step["state"] == "FAIL":
            failed = "qa"
    if failed:
        code = 1
    state = "FAIL" if failed else steps[-1]["state"]
    after = image_reviews(ag, run_dir)
    stale = [n for n in before if n not in after]
    summary = "assetgen finalize: %s" % state
    if failed:
        summary += " at %s: %s" % (failed, steps[-1]["reason"])
    obj = {"schema": SCHEMA, "run": os.path.basename(os.path.normpath(run_dir)), "steps": steps, "failed_at": failed,
           "stale": stale, "state": state, "exit": code}
    lines = []
    for step in steps:
        lines += step_lines(step)
        if step["step"] == "qa":
            lines.append(qa_text)
    if stale:
        lines.append("stale now (re-run them): " + ", ".join(stale))
    lines.append(summary)
    print(json.dumps(obj, indent=1, sort_keys=True) if as_json else "\n".join(lines))
    return code
