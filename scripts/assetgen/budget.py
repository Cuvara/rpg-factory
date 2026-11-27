"""asset-gen spend guard: how many generations a run series used against spec.budget.max_outputs.

The limit is ADVISORY. The engine cannot stop comfy-mcp run_workflow (it never runs ComfyUI), so the asset-gen skill
runs `assetgen.py budget --run <run>` before each run_workflow and does not run when remaining is 0 or the state is
exceeded. resolve records spec.budget = {"max_outputs": N} (--max-outputs N, default DEFAULT_MAX_OUTPUTS).

used = the generations made + the failed attempts of its series (lower-numbered sibling run dirs without run.md).
The budget counts generations, so a discard never refunds one: the run's deliverable outputs/*.png (excluding previews)
plus its active discards (discards.json entries whose file is still in outputs-rejected/ with the recorded sha256, the
rule of discard.active; a file moved back to outputs/ counts once, as an output). A sliced sheet counts as one
generation whether its cells are present or discarded (a fully discarded sheet still counts 1): its cells never add to
the count. Output classification uses fetch.json evidence via runfiles.output_origins. --json: `outputs` is the counted
generations (failed attempts excluded), `discarded` how many of them are discarded (discarded non-sheet outputs plus
sheets whose every cell is discarded), `sheet_cells` the cells present in outputs/ and `sheet_cells_discarded` the
discarded cells of sheets (both only when sheet.json exists).
States: unlimited (spec.json has no budget: a run resolved before the spend guard, never a failure), ok (used <
allowed), at-limit (used == allowed), exceeded (used > allowed), invalid (spec.budget present but malformed). Only
exceeded and invalid exit 1. Stdlib only; never imports assetgen.
"""
import glob
import hashlib
import json
import os
import re

import runfiles

SCHEMA = "rpg-factory.assetgen-budget/1"
DEFAULT_MAX_OUTPUTS = 4
_DECIMAL = re.compile(r"[0-9]+")


def parse_max(text):
    """--max-outputs value -> int >= 1; ValueError with a message otherwise ("0", "-1", "x", "1.5", "")."""
    value = "" if text is None else str(text)
    if not _DECIMAL.fullmatch(value):
        raise ValueError("%r is not a whole number (a decimal integer >= 1, e.g. 4)" % text)
    n = int(value)
    if n < 1:
        raise ValueError("%r must be at least 1" % text)
    return n


def _output_counts(run_dir):
    try:
        with open(os.path.join(run_dir, "workflow.json"), encoding="utf-8") as f:
            workflow = json.load(f)
    except (OSError, ValueError, UnicodeError):
        workflow = None
    origins = runfiles.output_origins(run_dir, workflow)
    previews = sum(1 for origin in origins.values() if origin["kind"] == "preview")
    return len(origins) - previews, previews


def count_outputs(run_dir):
    """Number of deliverable outputs/*.png files of the run."""
    return _output_counts(run_dir)[0]


def _limit(spec):
    """(max_outputs or None, problem or None) of spec.budget; (None, None) when the spec has no budget."""
    if not isinstance(spec, dict) or "budget" not in spec:
        return None, None
    budget = spec["budget"]
    if not isinstance(budget, dict):
        return None, "spec.budget is not an object"
    if "max_outputs" not in budget:
        return None, "spec.budget has no max_outputs"
    n = budget["max_outputs"]
    if isinstance(n, bool) or not isinstance(n, int):
        return None, "spec.budget.max_outputs %r is not an integer" % (n,)
    if n < 1:
        return None, "spec.budget.max_outputs %d is below 1" % n
    return n, None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _output_path(value):
    """value when it is an outputs/<name>.png path, else None."""
    if (isinstance(value, str) and value.startswith("outputs/") and os.path.basename(value) == value[8:]
            and value.endswith(".png")):
        return value
    return None


def _active_discards(run_dir):
    """The outputs/ names of the active discards (see discard.active), one per rejected file; [] when discards.json
    is missing or unreadable. Reads discards.json itself: budget never imports assetgen or discard."""
    try:
        with open(os.path.join(run_dir, "discards.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return []
    rows = data.get("discards") if isinstance(data, dict) else None
    seen, result = set(), []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        output, path = row.get("output"), row.get("path")
        if (not isinstance(output, str) or not isinstance(path, str) or not path.startswith("outputs-rejected/")
                or os.path.basename(path) != path[len("outputs-rejected/"):]
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            continue
        target = os.path.join(run_dir, *path.split("/"))
        try:
            ok = os.path.isfile(target) and _sha256(target) == row.get("sha256")
        except OSError:
            ok = False
        if ok and path not in seen:
            seen.add(path)
            result.append(output)
    return result


def _sheets(run_dir):
    """The sheets of sheet.json as lists of their outputs/ cell paths, or None when there is no readable record."""
    try:
        with open(os.path.join(run_dir, "sheet.json"), encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(record, dict):
        return None
    sheets = record.get("sheets")
    result = []
    for sheet in sheets if isinstance(sheets, list) else []:
        if not isinstance(sheet, dict):
            continue
        cells = sheet.get("cells")
        paths = [_output_path(cell.get("output")) for cell in cells if isinstance(cell, dict)] if isinstance(cells, list) else []
        result.append([p for p in paths if p])
    return result


def _generations(run_dir, outputs):
    """(generations, discarded, extra): the generations made, the counted ones that are discarded, and the sheet keys
    (sheet_cells, sheet_cells_discarded) when sheet.json exists, else {}. `outputs` is the number of deliverable
    outputs/*.png files; sheet cells never add to the count, a sheet counts once, a discard never refunds."""
    active = _active_discards(run_dir)
    sheets = _sheets(run_dir)
    cells = {path for cell_paths in sheets or [] for path in cell_paths}
    present = {path for path in cells if os.path.isfile(os.path.join(run_dir, *path.split("/")))}
    discarded_cells = [o for o in active if o in cells and o not in present]
    discarded_plain = [o for o in active if o not in cells]
    generations = outputs - len(present) + len(sheets or []) + len(discarded_plain)
    fully = sum(1 for cell_paths in sheets or [] if cell_paths and all(
        p not in present and p in discarded_cells for p in cell_paths))
    extra = {} if sheets is None else {"sheet_cells": len(present), "sheet_cells_discarded": len(discarded_cells)}
    return generations, len(discarded_plain) + fully, extra


def state(run_dir, spec, failed_attempts):
    """The budget state of a run (see the module docstring); failed_attempts are the run ids of its series' failed
    attempts (assetgen.failed_attempts)."""
    failed = list(failed_attempts or [])
    outputs, previews = _output_counts(run_dir)
    preview_pattern = os.path.join(glob.escape(run_dir), runfiles.PREVIEW_DIR, "*")
    previews += sum(1 for path in glob.glob(preview_pattern) if os.path.isfile(path))
    outputs, discarded, extra = _generations(run_dir, outputs)
    used = outputs + len(failed)
    allowed, problem = _limit(spec)
    remaining = None
    if problem:
        st, exit_code = "invalid", 1
        reason = "spec.json has a malformed budget: %s (resolve --out again with --max-outputs N)" % problem
    elif allowed is None:
        st, exit_code = "unlimited", 0
        reason = "spec.json has no budget (resolved before the spend guard)"
    else:
        remaining = max(0, allowed - used)
        if used < allowed:
            st, exit_code = "ok", 0
            reason = "%d of %d generations left in this run series" % (remaining, allowed)
        elif used == allowed:
            st, exit_code = "at-limit", 0
            reason = "the run series used all %d allowed generations: do not run run_workflow again" % allowed
        else:
            st, exit_code = "exceeded", 1
            reason = "the run series used %d generations, more than the %d allowed" % (used, allowed)
    result = {"schema": SCHEMA, "run": os.path.basename(os.path.normpath(run_dir)), "outputs": outputs,
              "discarded": discarded, "previews": previews, "failed_attempts": failed, "used": used, "allowed": allowed,
              "remaining": remaining, "state": st, "reason": reason, "exit": exit_code}
    result.update(extra)
    return result


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def line(st):
    """One text line: "budget <state>: ..."."""
    discarded = st.get("discarded", 0)
    used = "%d used (%s%s + %s)" % (st["used"], _plural(st["outputs"], "output"),
                                     ", %d discarded" % discarded if discarded else "",
                                     _plural(len(st["failed_attempts"]), "failed attempt"))
    preview_note = " (%s not counted)" % _plural(st.get("previews", 0), "preview file") if st.get("previews", 0) else ""
    if st["state"] == "unlimited":
        return "budget unlimited: %s; spec.json has no budget (resolved before the spend guard)%s" % (used, preview_note)
    if st["state"] == "invalid":
        return "budget invalid: %s; %s%s" % (used, st["reason"], preview_note)
    return "budget %s: %s of %d allowed, %d remaining%s (advisory)" % (st["state"], used, st["allowed"], st["remaining"], preview_note)
