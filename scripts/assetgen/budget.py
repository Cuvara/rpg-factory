"""asset-gen spend guard: how many generations a run series used against spec.budget.max_outputs.

The limit is ADVISORY. The engine cannot stop comfy-mcp run_workflow (it never runs ComfyUI), so the asset-gen skill
runs `assetgen.py budget --run <run>` before each run_workflow and does not run when remaining is 0 or the state is
exceeded. resolve records spec.budget = {"max_outputs": N} (--max-outputs N, default DEFAULT_MAX_OUTPUTS).

used = the run's deliverable outputs/*.png (excluding previews) + the failed attempts of its series (lower-numbered
sibling run dirs without run.md). Output classification uses fetch.json evidence via runfiles.output_origins.
States: unlimited (spec.json has no budget: a run resolved before the spend guard, never a failure), ok (used <
allowed), at-limit (used == allowed), exceeded (used > allowed), invalid (spec.budget present but malformed). Only
exceeded and invalid exit 1. Stdlib only; never imports assetgen.
"""
import glob
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


def state(run_dir, spec, failed_attempts):
    """The budget state of a run (see the module docstring); failed_attempts are the run ids of its series' failed
    attempts (assetgen.failed_attempts)."""
    failed = list(failed_attempts or [])
    outputs, previews = _output_counts(run_dir)
    preview_pattern = os.path.join(glob.escape(run_dir), runfiles.PREVIEW_DIR, "*")
    previews += sum(1 for path in glob.glob(preview_pattern) if os.path.isfile(path))
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
    return {"schema": SCHEMA, "run": os.path.basename(os.path.normpath(run_dir)), "outputs": outputs, "previews": previews,
            "failed_attempts": failed, "used": used, "allowed": allowed, "remaining": remaining, "state": st,
            "reason": reason, "exit": exit_code}


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def line(st):
    """One text line: "budget <state>: ..."."""
    used = "%d used (%s + %s)" % (st["used"], _plural(st["outputs"], "output"),
                                   _plural(len(st["failed_attempts"]), "failed attempt"))
    preview_note = " (%s not counted)" % _plural(st.get("previews", 0), "preview file") if st.get("previews", 0) else ""
    if st["state"] == "unlimited":
        return "budget unlimited: %s; spec.json has no budget (resolved before the spend guard)%s" % (used, preview_note)
    if st["state"] == "invalid":
        return "budget invalid: %s; %s%s" % (used, st["reason"], preview_note)
    return "budget %s: %s of %d allowed, %d remaining%s (advisory)" % (st["state"], used, st["allowed"], st["remaining"], preview_note)
