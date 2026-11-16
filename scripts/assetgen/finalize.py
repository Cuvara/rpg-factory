"""assetgen finalize: filter, slice, fit, defringe, pixel-grid, embed and qa in order, after fetch_outputs.

filter comes first: fetch_outputs also downloads PreviewImage files into outputs/, so every outputs/*.png that
runfiles.output_origins classifies as a preview (not written by a SaveImage node of the rendered workflow.json) is moved
to <run>/previews/ (never overwritten, never deleted); a file with no SaveImage or preview evidence stays and is reported.
The primary source evidence is fetch.json; the comfy-cli job state is the fallback.
filter FAILs, moving nothing, when every output is a preview. Runs whose outputs are all SaveImage files are untouched.

fit pads orientation mismatches for opted-in alpha purposes, preserving originals under raw/ without overwriting or
deleting them. The other verbs keep their own contracts; embed can never be skipped before qa.
It never imports assetgen: assetgen.py passes its own module (`ag`), so there is no import cycle.

ag.fail() exits the process, so every condition a callee would fail() on is checked here first (precheck), before
anything is written; after that a step ends in a state, never in an exit. Steps stop at the first FAIL, naming it.

Exit codes follow qa: 0 PASS, 1 FAIL, 3 NOT_AVAILABLE.
With --discard-qa-fail, move failing outputs to outputs-rejected/ and grade the remaining outputs again.
"""
import glob
import hashlib
import json
import os
import shutil

import consistency
import pixelgrid
import slicer

SCHEMA = "rpg-factory.assetgen-finalize/1"
RAW_DIR = "raw"


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
    pixel_record = None
    path = os.path.join(run_dir, "pixelgrid.json")
    if os.path.isfile(path):
        pixel_record = ag.read_json(path, "pixel grid record")
    sheet_path = os.path.join(run_dir, "sheet.json")
    if os.path.isfile(sheet_path):
        ag.read_json(sheet_path, "sheet record")
    return spec, record, pixel_record


def free_target(directory, name):
    """<directory>/<name>, or <stem>.<n><ext> with the first free n >= 1 when that exists: a move never overwrites."""
    target = os.path.join(directory, name)
    stem, ext = os.path.splitext(name)
    n = 0
    while os.path.lexists(target):
        n += 1
        target = os.path.join(directory, "%s.%d%s" % (stem, n, ext))
    return target


def filter_step(ag, run_dir):
    """The filter step: {step, state: moved|skipped|FAIL, reason, results}. Moves every preview file of outputs/ to
    previews/; save files get no row, unknown files a kept row. Nothing is deleted or overwritten."""
    step = {"step": "filter", "state": "skipped", "reason": "", "results": []}
    workflow = None
    path = os.path.join(run_dir, "workflow.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                workflow = json.load(f)
        except (OSError, ValueError, UnicodeError):
            workflow = None
    origins = ag.runfiles.output_origins(run_dir, workflow)
    pngs = ["outputs/" + os.path.basename(p) for p in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))]
    sheet_path = os.path.join(run_dir, "sheet.json")
    record = ag.read_json(sheet_path, "sheet record") if os.path.isfile(sheet_path) else {}
    recorded = {cell.get("output") for sheet in record.get("sheets", []) if isinstance(sheet, dict)
                for cell in sheet.get("cells", []) if isinstance(cell, dict)} if isinstance(record, dict) else set()
    previews = [o for o in pngs if o not in recorded and origins.get(o, {}).get("kind") == "preview"]
    unknown = [o for o in pngs if o not in recorded and origins.get(o, {}).get("kind", "unknown") not in ("save", "preview")]
    if not previews:
        step["reason"] = "no preview file in outputs/"
    elif len(previews) == len(pngs):
        step.update(state="FAIL", reason="every outputs/*.png is a preview file (no SaveImage output): nothing to "
                    "finalize")
        return step
    else:
        target_dir = os.path.join(run_dir, ag.runfiles.PREVIEW_DIR)
        os.makedirs(target_dir, exist_ok=True)
        for output in previews:
            target = free_target(target_dir, output.split("/", 1)[1])
            os.rename(os.path.join(run_dir, *output.split("/")), target)
            step["results"].append({"state": "moved", "output": output, "reason": "-> %s/%s: %s" % (
                ag.runfiles.PREVIEW_DIR, os.path.basename(target), origins[output].get("reason", ""))})
        step.update(state="moved", reason="%d moved to %s/, %d kept" % (len(previews), ag.runfiles.PREVIEW_DIR,
                                                                         len(pngs) - len(previews)))
    for output in unknown:
        step["results"].append({"state": "kept", "output": output,
                                "reason": "no SaveImage or preview evidence, left in outputs/: %s"
                                % origins.get(output, {}).get("reason", "not classified")})
    return step


def slice_step(ag, run_dir, rows, cols, force):
    """Slice all sheets only after every sheet has been decoded and validated."""
    step = {"step": "slice", "state": "skipped", "reason": "", "results": []}
    record_path = os.path.join(run_dir, "sheet.json")
    if os.path.isfile(record_path):
        record = ag.read_json(record_path, "sheet record")
        if not isinstance(record, dict) or (record.get("rows"), record.get("cols")) != (rows, cols):
            step.update(state="FAIL", reason="sheet.json records %sx%s; start a new attempt" % (
                record.get("rows") if isinstance(record, dict) else "?", record.get("cols") if isinstance(record, dict) else "?"))
            return step
        sheets = [s for s in record.get("sheets", []) if isinstance(s, dict)]
        # cells may since be discarded or rewritten by later steps; the recorded sheets themselves must still be there
        if sheets and all(isinstance(s.get("sheet"), str) and s["sheet"].startswith("sheets/")
                          and os.path.basename(s["sheet"]) == s["sheet"][7:]
                          and os.path.isfile(os.path.join(run_dir, *s["sheet"].split("/"))) for s in sheets):
            step["reason"] = "already sliced (sheet.json)"
            return step
        step.update(state="FAIL", reason="sheet.json names a sheet missing from sheets/; start a new attempt")
        return step
    bound = ag.bound_records(run_dir, outputs_of(ag, run_dir))
    if bound and not force:
        step.update(state="FAIL", reason="%s already bind(s) the current outputs and slice would change them; "
                    "pass --force to slice anyway (then those records are stale: re-run them)" % ", ".join(bound))
        return step
    todo = []
    for path in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png"))):
        row = {"output": "outputs/" + os.path.basename(path), "state": "skipped"}
        step["results"].append(row)
        try:
            with open(path, "rb") as f:
                source = f.read()
            refusal = ag.depth_refusal(source, "sliced")
            if refusal:
                raise slicer.SliceError(refusal)
            img = ag.png.decode(path)
            cells, info = slicer.slice_image(img, rows, cols)
            encoded = []
            for cell in cells:
                width, height, rgba = slicer.crop(img, cell["box"])
                encoded.append(ag.rebuild(ag.png.encode(width, height, rgba), lambda t, b: True, ag.text_chunks(source)))
            todo.append((path, source, cells, info, encoded, row))
            row["reason"] = "sheet validated"
        except (ag.png.Invalid, ag.png.Unsupported, OSError, slicer.SliceError) as exc:
            row.update(state="FAIL", reason=str(exc))
    if any(row["state"] == "FAIL" for row in step["results"]):
        step.update(state="FAIL", reason="sheet validation failed; nothing sliced")
        return step
    sheets_dir = os.path.join(run_dir, "sheets")
    records = []
    written, moved, pending = [], [], None
    try:
        os.makedirs(sheets_dir, exist_ok=True)
        for path, source, cells, info, encoded, row in todo:
            entries = []
            for cell, data in zip(cells, encoded):
                name = "%s-r%sc%s.png" % (os.path.splitext(os.path.basename(path))[0], cell["row"], cell["col"])
                out = free_target(os.path.join(run_dir, "outputs"), name)
                pending = out + ".slice.tmp"
                ag.write_atomic(out, data, ".slice.tmp")
                written.append(out)
                pending = None
                entries.append(dict(cell, output="outputs/" + os.path.basename(out), sha256=hashlib.sha256(data).hexdigest()))
            records.append({"source": row["output"], "sha256": hashlib.sha256(source).hexdigest(),
                            "size": info["size"], "background": info["background"], "cells": entries})
        for (path, _, _, _, _, row), record in zip(todo, records):
            target = free_target(sheets_dir, os.path.basename(path))
            os.rename(path, target)
            moved.append((path, target))
            record["sheet"] = "sheets/" + os.path.basename(target)
        data = (json.dumps({"schema": "rpg-factory.assetgen-sheet/1", "run": os.path.basename(os.path.normpath(run_dir)),
                            "rows": rows, "cols": cols, "sheets": records}, indent=1, sort_keys=True) + "\n").encode("utf-8")
        pending = record_path + ".slice.tmp"
        ag.write_atomic(record_path, data, ".slice.tmp")
        pending = None
    except OSError as exc:
        for original, target in reversed(moved):
            os.rename(target, original)
        for path in written + ([pending] if pending else []):
            if os.path.exists(path):
                os.remove(path)
        step.update(state="FAIL", reason="sheet write failed: %s" % exc)
        step["results"].append({"state": "FAIL", "reason": str(exc)})
        return step
    for (_, _, _, _, _, row), record in zip(todo, records):
        row.update(state="sliced", reason="-> %s, %d outputs" % (record["sheet"], len(record["cells"])))
    step.update(state="sliced", reason="%d sheet(s) sliced" % len(records))
    return step


def wants_alpha(spec):
    purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
    data = purpose.get("data") if isinstance(purpose.get("data"), dict) else {}
    qa = data.get("qa") if isinstance(data.get("qa"), dict) else {}
    return qa.get("alpha") == "required"


def fit_step(ag, run_dir, spec, force):
    """Pad mismatched outputs, preserving their originals and respecting bound records."""
    step = {"step": "fit", "state": "skipped", "reason": "", "results": []}
    purpose = spec.get("purpose") if isinstance(spec.get("purpose"), dict) else {}
    data = purpose.get("data") if isinstance(purpose.get("data"), dict) else {}
    qa = data.get("qa") if isinstance(data.get("qa"), dict) else {}
    size = qa.get("size") if isinstance(qa.get("size"), dict) else {}
    if size.get("fit") != "pad":
        step["reason"] = "qa.size.fit is none"
        return step
    if qa.get("alpha") != "required":
        step["reason"] = "qa.size.fit pad needs qa.alpha required: not padded"
        return step
    expected = size.get("expect")
    if expected is None or expected == "auto":
        expected = ag.requested_size(run_dir, spec)
    expect = ag.qa.parse_size(expected)
    if expect is None:
        step["reason"] = "no expected size to fit to"
        return step
    ew, eh = expect
    tol = size.get("square_tolerance", 0.05)
    want = ag.qa.orientation_of(ew, eh, tol)
    todo = []
    for path in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png"))):
        row = {"output": "outputs/" + os.path.basename(path), "state": "skipped"}
        step["results"].append(row)
        try:
            with open(path, "rb") as f:
                source = f.read()
            refusal = ag.depth_refusal(source, "padded")
            if refusal:
                row["reason"] = refusal + ": not fitted (later steps grade it)"
                continue
            img = ag.png.decode(path)
        except (ag.png.Invalid, ag.png.Unsupported, OSError) as exc:
            row["reason"] = str(exc) + ": not fitted (later steps grade it)"
            continue
        if not img.has_alpha:
            row["reason"] = "no alpha channel: not padded (qa grades alpha)"
            continue
        have = ag.qa.orientation_of(img.width, img.height, tol)
        if have == want:
            row["reason"] = "%dx%d is %s, as expected: untouched" % (img.width, img.height, have)
            continue
        floor_ok, detail = ag.qa.floor_detail(img, size)
        if not floor_ok:
            row["reason"] = "%dx%d fails the size floors (%s): not padded (qa grades it)" % (
                img.width, img.height, ", ".join(detail))
            continue
        legacy = "outputs-raw/" + os.path.basename(path)
        if os.path.exists(os.path.join(run_dir, *legacy.split("/"))):
            row["reason"] = "already defringed before fit (%s): not padded; start a new attempt" % legacy
            continue
        row["reason"] = "%dx%d is %s, expected %s: not yet padded" % (img.width, img.height, have, want)
        todo.append((path, source, img, have, row))
    if not todo:
        step["reason"] = "%d skipped: no output to pad" % len(step["results"])
        return step
    bound = ag.bound_records(run_dir, outputs_of(ag, run_dir))
    if bound and not force:
        step.update(state="FAIL", reason="%s already bind(s) the current outputs and fit would change them; "
                    "pass --force to fit anyway (then those records are stale: re-run them)" % ", ".join(bound))
        return step
    for path, source, img, have, row in todo:
        width, height = ag.imaging.fit_box(img.width, img.height, ew, eh)
        rgba, left, top = ag.imaging.pad(img, width, height)
        if ag.png.gray_type(ag.png.header(source)[3]) and ag.png.is_gray(rgba):
            new = ag.png.encode_gray(width, height, rgba)
        else:
            new = ag.png.encode(width, height, rgba)
        new = ag.rebuild(ag.after_ihdr(new, ag.colour_chunks(source, ag.png.header(new)[3])),
                         lambda t, b: True, ag.text_chunks(source))
        raw_dir = os.path.join(run_dir, RAW_DIR)
        os.makedirs(raw_dir, exist_ok=True)
        raw = free_target(raw_dir, os.path.basename(path))
        shutil.copyfile(path, raw)
        ag.write_atomic(path, new, ".fit.tmp")
        raw_rel = RAW_DIR + "/" + os.path.basename(raw)
        original_size = "%dx%d" % (img.width, img.height)
        fitted_size = "%dx%d" % (width, height)
        fitted_orientation = ag.qa.orientation_of(width, height, tol)
        row.update(state="padded", raw=raw_rel, original_size=original_size, fitted_size=fitted_size,
                   offset=[left, top], before_sha256=hashlib.sha256(source).hexdigest(),
                   after_sha256=hashlib.sha256(new).hexdigest(),
                   reason="%s %s -> %s %s: centered on transparent bands, original in %s" % (
                       original_size, have, fitted_size, fitted_orientation, raw_rel))
    step.update(state="fitted", reason="%d padded, %d skipped" % (len(todo), len(step["results"]) - len(todo)))
    return step


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


def defringe_step(ag, run_dir, spec, record, force, pixel_grid=False, pixel_record=None):
    """The defringe step: {step, state: defringed|skipped|FAIL, reason, results}."""
    step = {"step": "defringe", "state": "skipped", "reason": "", "results": []}
    if pixel_grid:
        step["reason"] = "pixel grid requested: alpha is binarized, nothing to defringe"
        return step
    recorded = pixel_record.get("outputs", []) if isinstance(pixel_record, dict) else []
    for row in recorded if isinstance(recorded, list) else []:
        if not isinstance(row, dict) or row.get("state") != "pixelated":
            continue
        output = row.get("output")
        if (isinstance(output, str) and output.startswith("outputs/")
                and os.path.basename(output) == output[8:] and row.get("after_pixels_sha256")
                and ag.pixels_sha256(os.path.join(run_dir, *output.split("/"))) == row["after_pixels_sha256"]):
            step["reason"] = "pixel-gridded outputs (pixelgrid.json): not defringed"
            return step
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


def pixelgrid_step(ag, run_dir, spec, record, force, max_colors):
    """Reduce outputs to their detected grid, preserving the source and recording every result."""
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    style_data = style.get("data") if isinstance(style.get("data"), dict) else {}
    state, config = consistency.palette_config(style_data)
    palette = config[1] if state == "ok" else None
    limit = 16 if max_colors is None else max_colors
    params = {"max_colors": limit, "palette": "style" if palette else "quantized",
              "palette_colors": ["#%02x%02x%02x" % color for color in palette] if palette else None}
    old_params = record.get("params") if isinstance(record, dict) else None
    old_rows = record.get("outputs", []) if isinstance(record, dict) else []
    old = {r.get("output"): r for r in old_rows if isinstance(r, dict)} if isinstance(old_rows, list) else {}
    step = {"step": "pixel-grid", "state": "skipped", "reason": "", "results": []}
    todo = []
    for path in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png"))):
        output = "outputs/" + os.path.basename(path)
        prev = old.get(output, {})
        row = {"output": output, "state": "skipped"}
        step["results"].append(row)
        try:
            with open(path, "rb") as f:
                current = f.read()
            refusal = ag.depth_refusal(current, "pixel-gridded")
            if refusal:
                row["reason"] = refusal
                continue
            img = ag.png.decode(path)
            if (prev.get("state") == "pixelated" and prev.get("after_pixels_sha256")
                    and ag.pixels_sha256(path) == prev["after_pixels_sha256"] and old_params == params):
                row.update(prev)
                row.update(state="skipped", reason="already pixel-gridded")
                continue
            raw_rel = prev.get("raw")
            raw = os.path.join(run_dir, *raw_rel.split("/")) if isinstance(raw_rel, str) and raw_rel.startswith("outputs-raw/pixelgrid/") and os.path.basename(raw_rel) == raw_rel[len("outputs-raw/pixelgrid/"):] else None
            source = current
            if raw and os.path.isfile(raw) and ag.qa.sha256(raw) == prev.get("before_sha256"):
                with open(raw, "rb") as f:
                    source = f.read()
                refusal = ag.depth_refusal(source, "pixel-gridded")
                if refusal:
                    row["reason"] = refusal
                    continue
                img = ag.png.decode(raw)
            else:
                raw = None
            width, height, rgba, info = pixelgrid.process(img, palette=palette, max_colors=limit)
        except (ag.png.Invalid, ag.png.Unsupported, OSError, pixelgrid.NoGrid) as exc:
            row["reason"] = str(exc)
            continue
        row["reason"] = "grid detected: not yet pixel-gridded"
        todo.append((path, source, raw, width, height, rgba, info, row))
    if todo:
        bound = ag.bound_records(run_dir, outputs_of(ag, run_dir))
        if bound and not force:
            step.update(state="FAIL", reason="%s already bind(s) the current outputs and pixel-grid would change them; "
                        "pass --force to pixel-grid anyway (then those records are stale: re-run them)" % ", ".join(bound))
            return step
    for path, source, raw, width, height, rgba, info, row in todo:
        if raw is None:
            raw_dir = os.path.join(run_dir, "outputs-raw", "pixelgrid")
            os.makedirs(raw_dir, exist_ok=True)
            raw = free_target(raw_dir, os.path.basename(path))
            with open(raw, "xb") as f:
                f.write(source)
        new = ag.rebuild(ag.png.encode(width, height, rgba), lambda t, b: True, ag.text_chunks(source))
        ag.write_atomic(path, new, ".pixelgrid.tmp")
        row.update(state="pixelated", raw="outputs-raw/pixelgrid/" + os.path.basename(raw),
                   source_size=info["source_size"], size=info["size"], scale=info["scale"], offset=info["offset"],
                   colors=info["colors"], before_sha256=hashlib.sha256(source).hexdigest(),
                   after_sha256=hashlib.sha256(new).hexdigest(), after_pixels_sha256=ag.pixels_sha256(path),
                   reason="%s -> %s, scale %s, %d colors%s" % (info["source_size"], info["size"], info["scale"],
                            info["colors"], "; max_colors ignored for style palette" if palette else ""))
    step.update(state="pixelated" if todo else "skipped", reason="%d pixelated, %d skipped" % (
        len(todo), len(step["results"]) - len(todo)))
    ag.write_json(os.path.join(run_dir, "pixelgrid.json"), {
        "schema": "rpg-factory.assetgen-pixelgrid/1", "run": os.path.basename(os.path.normpath(run_dir)),
        "params": params, "outputs": [
            dict(old[row["output"]], reason="already pixel-gridded")
            if row.get("reason") == "already pixel-gridded" else row for row in step["results"]]})
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


def run(ag, run_dir, force=False, as_json=False, discard_qa_fail=False, pixel_grid=False, max_colors=None, rows=None, cols=None):
    """The finalize verb: returns the exit code (0 PASS, 1 FAIL, 3 NOT_AVAILABLE) after printing the result."""
    spec, record, pixel_record = precheck(ag, run_dir)
    if discard_qa_fail:
        ag.discard.records(ag, run_dir)  # an unreadable discards.json refuses here, before any write
    before = image_reviews(ag, run_dir)
    steps, qa_text, code, failed = [], [], 0, None
    discarded, discard_stale = [], []
    steps.append(filter_step(ag, run_dir))
    if steps[-1]["state"] == "FAIL":
        failed = "filter"
    if not failed and rows is not None:
        steps.append(slice_step(ag, run_dir, rows, cols, force))
        if steps[-1]["state"] == "FAIL":
            failed = "slice"
    if not failed:
        steps.append(fit_step(ag, run_dir, spec, force))
        if steps[-1]["state"] == "FAIL":
            failed = "fit"
    if not failed:
        steps.append(defringe_step(ag, run_dir, spec, record, force, pixel_grid, pixel_record))
        if steps[-1]["state"] == "FAIL":
            failed = "defringe"
    if not failed and pixel_grid:
        steps.append(pixelgrid_step(ag, run_dir, spec, pixel_record, force, max_colors))
        if steps[-1]["state"] == "FAIL":
            failed = "pixel-grid"
    if not failed:
        steps.append(embed_step(ag, run_dir))
        if steps[-1]["state"] == "FAIL":
            failed = "embed"
    if not failed:
        step, text, code = qa_step(ag, run_dir)
        qa_text.append(text)
        steps.append(step)
        if discard_qa_fail and step["state"] == "PASS":
            steps.append({"step": "discard", "state": "skipped", "reason": "qa PASS: nothing to discard", "results": []})
        elif discard_qa_fail and step["state"] == "FAIL":
            current = ag.discard.outputs(run_dir)
            checks = {}
            for row in step["results"]:
                if row.get("state") == "FAIL" and row.get("output") in current:
                    checks.setdefault(row["output"], [])
                    if row["check"] not in checks[row["output"]]:
                        checks[row["output"]].append(row["check"])
            if checks and len(checks) == len(current):
                step["reason"] += "; every output failed QA: nothing discarded"
            elif checks:
                data = ag.discard.records(ag, run_dir)
                discard_stale = ag.discard.stale_records(ag, run_dir, set(checks))
                rows = []
                for output in current:
                    if output not in checks:
                        continue
                    names = ", ".join(checks[output])
                    entry = ag.discard.move(ag, run_dir, output, "qa FAIL: " + names, "finalize", data)
                    discarded.append(entry)
                    rows.append({"state": "discarded", "output": output,
                                 "reason": "-> %s: qa FAIL %s" % (entry["path"], names)})
                steps.append({"step": "discard", "state": "discarded",
                              "reason": "%d discarded to outputs-rejected/" % len(rows), "results": rows})
                step, text, code = qa_step(ag, run_dir)
                discard_stale = [n for n in discard_stale if n != "qa.json"]
                qa_text.append(text)
                steps.append(step)
        if step["state"] == "FAIL":
            failed = "qa"
    if failed:
        code = 1
    state = "FAIL" if failed else step["state"] if steps[-1]["step"] == "discard" else steps[-1]["state"]
    after = image_reviews(ag, run_dir)
    stale = [n for n in ("qa.json", ag.REVIEW_FILES["image"], ag.CLAUDE_REVIEW)
             if n in discard_stale or (n in before and n not in after)]
    summary = "assetgen finalize: %s" % state
    if failed:
        summary += " at %s: %s" % (failed, steps[-1]["reason"])
    obj = {"schema": SCHEMA, "run": os.path.basename(os.path.normpath(run_dir)), "steps": steps, "failed_at": failed,
           "stale": stale, "state": state, "exit": code}
    if discard_qa_fail:
        obj["discarded"] = discarded
    fields = ("output", "raw", "original_size", "fitted_size", "offset", "before_sha256", "after_sha256")
    fitted = [{key: row[key] for key in fields} for step in steps if step["step"] == "fit"
              for row in step["results"] if row["state"] == "padded"]
    padded_outputs = {row["output"] for row in fitted}
    try:
        with open(os.path.join(run_dir, "finalize.json"), encoding="utf-8") as f:
            previous = json.load(f)
        previous = previous.get("fitted", []) if isinstance(previous, dict) else []
        if not isinstance(previous, list):
            previous = []
        for row in previous:
            if not isinstance(row, dict) or not all(key in row for key in fields):
                continue
            output, raw = row["output"], row["raw"]
            if (isinstance(output, str) and output not in padded_outputs and isinstance(raw, str)
                    and raw.startswith("raw/") and os.path.basename(raw) == raw[4:]
                    and os.path.isfile(os.path.join(run_dir, *raw.split("/")))):
                fitted.append({key: row[key] for key in fields})
    except (OSError, ValueError, UnicodeError):
        pass
    obj["fitted"] = fitted
    ag.write_json(os.path.join(run_dir, "finalize.json"), obj)
    lines = []
    qa_texts = iter(qa_text)
    for step in steps:
        lines += step_lines(step)
        if step["step"] == "qa":
            lines.append(next(qa_texts))
    if stale:
        lines.append("stale now (re-run them): " + ", ".join(stale))
    if fitted:
        lines.append("fitted (originals in raw/, finalize.json): " + ", ".join(
            "%s %s -> %s" % (row["output"], row["original_size"], row["fitted_size"]) for row in fitted))
    lines.append(summary)
    print(json.dumps(obj, indent=1, sort_keys=True) if as_json else "\n".join(lines))
    return code
