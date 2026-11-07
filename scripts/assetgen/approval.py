"""Approval record of a gen-run for a person (assetgen.py approve-record) and the status rule of a re-run manifest.

approve_record(run_dir, by, note=None, today=None) -> {"run_md", "approval", "rev", "status", "record"}
  For a person only: refuses an empty `by`, an agent or model name (stylelock.is_agent_name) and a name the run
  itself records as an agent (authors of kind agent, provenance.generated_by, spec.prompt_author, the reviewers).
  Sets the run.md front-matter status to approved (the JSON front matter is rewritten in the manifest's format,
  indent 2, ASCII; the body is kept and only its "- Status:" line follows the new status), then writes
  <authoring>/approvals/AGEN-<run id>/assetgen-approval-<rev>.json with rev = the git blob id of the updated run.md
  (what `git hash-object` prints for it), in the shape scripts/checks/artifact-trace.py approval() reads:
  {artifact, gate, scope, rev, date, by, note}. It never commits and never signs: the record binds only once the
  person commits run.md and the record in one signed commit (until then the checks say "approval present but not
  committed/signed"). A run whose status is not proposed, review, reviewed or approved is refused.
keep_status(old_front, new_front) -> the status a re-run manifest writes: approved stays approved while nothing the
  approval binds changed (bound_changes is empty); any other earlier status stays while the outputs are the same;
  else (and without an earlier run.md) proposed.
bound_changes(old_front, new_front) -> the names of the bound run.md fields that differ (outputs, prompt,
  requirements, qa, the reviews, generation, style_lock), [] when none did.
"""
import datetime
import hashlib
import json
import os
import re

import layers
import runfiles
import stylelock

GATE = "assetgen-approval"  # registry domains.assetgen.human_gates
APPROVABLE = ("proposed", "review", "reviewed", "approved")
FRONT = re.compile(r"\A---json\s*\n(.*?)\n---(?:[ \t]*\n|\Z)", re.S)
STATUS_LINE = re.compile(r"^- Status: \S+", re.M)
RUN_ID = re.compile(r"\A[a-z0-9][a-z0-9-]*-[0-9]{3}\Z")
# run.md spec fields an approval binds: a change in any of them makes the approved run another run
BOUND = (("outputs", "outputs"), ("prompt_sha256", "prompt"), ("qa", "qa"), ("prompt_review", "prompt review"),
         ("image_review", "image review"), ("claude_image_review", "Claude image review"), ("generation", "generation"),
         ("style_lock", "style lock"))


class ApprovalError(layers.SpecError):
    pass


def git_blob(data):
    """The git blob id of these bytes (sha1 of "blob <size>\\0" + data), as `git hash-object` prints it."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def split_front(text):
    """(front dict, body text) of a ---json front-matter document; raises ApprovalError."""
    m = FRONT.match(text)
    if not m:
        raise ApprovalError("run.md has no ---json front matter")
    try:
        front = json.loads(m.group(1))
    except ValueError as exc:
        raise ApprovalError("run.md front matter is not JSON (%s)" % exc)
    if not isinstance(front, dict):
        raise ApprovalError("run.md front matter is not an object")
    return front, text[m.end():]


def front_text(front, body):
    """run.md text: the front matter in the manifest's format, then the body with its status line updated."""
    body = STATUS_LINE.sub(lambda _: "- Status: %s" % front.get("status"), body, count=1)
    return "---json\n%s\n---\n%s" % (json.dumps(front, indent=2, ensure_ascii=True), body)


def run_agents(front):
    """Names the run records as agents or models (never a person who approves it)."""
    spec = front.get("spec") if isinstance(front.get("spec"), dict) else {}
    names = [a.get("id") for a in front.get("authors") or [] if isinstance(a, dict) and a.get("kind") == "agent"]
    names.append((front.get("provenance") or {}).get("generated_by") if isinstance(front.get("provenance"), dict) else None)
    names.append(spec.get("prompt_author"))
    for key in ("prompt_review", "image_review", "claude_image_review"):
        rv = spec.get(key)
        names.append(rv.get("by") if isinstance(rv, dict) else None)
    return {n.strip().lower() for n in names if isinstance(n, str) and n.strip()}


def approve_record(run_dir, by, note=None, today=None):
    by = by.strip() if isinstance(by, str) else ""
    if not by:
        raise ApprovalError("approve-record needs --by NAME: the person who approves the run")
    if stylelock.is_agent_name(by) or by.lower() in ("agent", "model"):
        raise ApprovalError("%r is an agent or model name; only a person approves a gen-run" % by)
    full = os.path.abspath(os.path.normpath(run_dir))
    run_id, runs = os.path.basename(full), os.path.dirname(full)
    if not RUN_ID.match(run_id) or os.path.basename(runs) != "runs" or os.path.basename(os.path.dirname(runs)) != "assetgen":
        raise ApprovalError("run %s must be <authoring>/assetgen/runs/<slug>-NNN" % run_dir.replace(os.sep, "/"))
    authoring = os.path.dirname(os.path.dirname(runs))
    path = os.path.join(full, "run.md")
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    except OSError as exc:
        raise ApprovalError("cannot read %s (run assetgen.py manifest first): %s" % (path.replace(os.sep, "/"), exc))
    front, body = split_front(text)
    aid = "AGEN-" + run_id
    if front.get("kind") != "gen-run" or front.get("id") != aid:
        raise ApprovalError("run.md is not the gen-run %s (kind %r, id %r)" % (aid, front.get("kind"), front.get("id")))
    if by.lower() in run_agents(front):
        raise ApprovalError("%r is recorded in this run as an agent or reviewer; only a person approves a gen-run" % by)
    if front.get("status") not in APPROVABLE:
        raise ApprovalError("run %s is %s: only a proposed, review, reviewed or approved run can be approved"
                            % (aid, front.get("status")))
    if today is None:
        today = datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(today)
    except (TypeError, ValueError):
        raise ApprovalError("date %r is not YYYY-MM-DD" % (today,))
    front["status"] = "approved"
    data = front_text(front, body).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    rev = git_blob(data)
    record = {"artifact": aid, "gate": GATE, "scope": front.get("domain") or "assetgen", "rev": rev, "date": today,
              "by": by, "note": note.strip() if isinstance(note, str) and note.strip() else None}
    target = os.path.join(authoring, "approvals", aid, "%s-%s.json" % (GATE, rev))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, indent=2, ensure_ascii=True) + "\n")
    return {"run_md": path, "approval": target, "rev": rev, "status": "approved", "record": record}


def bound_changes(old_front, new_front):
    old = (old_front or {}).get("spec") if isinstance((old_front or {}).get("spec"), dict) else {}
    new = (new_front or {}).get("spec") if isinstance((new_front or {}).get("spec"), dict) else {}
    out = [label for key, label in BOUND if old.get(key) != new.get(key)]
    if runfiles.requirements_sha256(old) != runfiles.requirements_sha256(new):
        out.insert(2, "requirements (purpose, style, template or params)")
    return out


def keep_status(old_front, new_front):
    status = (old_front or {}).get("status")
    if not status:
        return "proposed"
    if status == "approved":
        return status if not bound_changes(old_front, new_front) else "proposed"
    old = old_front.get("spec") if isinstance(old_front.get("spec"), dict) else {}
    new = (new_front or {}).get("spec") if isinstance((new_front or {}).get("spec"), dict) else {}
    return status if old.get("outputs") == new.get("outputs") else "proposed"
