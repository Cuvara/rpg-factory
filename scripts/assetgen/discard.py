"""Move rejected outputs aside and retain their history without importing assetgen."""
import glob
import json
import os

REJECT_DIR = "outputs-rejected"
RECORD = "discards.json"
SCHEMA = "rpg-factory.assetgen-discards/1"


def outputs(run_dir):
    return ["outputs/" + os.path.basename(p) for p in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.png")))]


def records(ag, run_dir):
    path = os.path.join(run_dir, RECORD)
    data = ag.read_json(path, "discard record") if os.path.isfile(path) else {"schema": SCHEMA, "discards": []}
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("discards"), list):
        ag.fail("invalid discard record %s" % path)
    return data


def stale_records(ag, run_dir, removed):
    names = []
    for name in ("qa.json", ag.REVIEW_FILES["image"], ag.CLAUDE_REVIEW):
        try:
            with open(os.path.join(run_dir, name), encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("outputs", []) if isinstance(data, dict) else []
            if isinstance(rows, list) and any(isinstance(row, dict) and row.get("path") in removed for row in rows):
                names.append(name)
        except (OSError, ValueError, UnicodeError):
            pass
    return names


def move(ag, run_dir, output, reason, by, data):
    directory = os.path.join(run_dir, REJECT_DIR)
    os.makedirs(directory, exist_ok=True)
    target = ag.finalize.free_target(directory, os.path.basename(output))
    source = os.path.join(run_dir, *output.split("/"))
    digest = ag.qa.sha256(source)
    os.rename(source, target)
    entry = {"output": output, "path": REJECT_DIR + "/" + os.path.basename(target),
             "sha256": digest, "reason": reason, "by": by}
    data["discards"].append(entry)
    ag.write_json(os.path.join(run_dir, RECORD), data)
    return entry


def active(ag, run_dir):
    """The discards.json entries for run.md spec.trace.discarded: only those whose file is still in outputs-rejected/
    with the recorded sha256 (a file moved back to outputs/ drops out). A later output that reuses the name is no
    conflict: the trace names the rejected bytes, not the name."""
    if not os.path.isfile(os.path.join(run_dir, RECORD)):
        return []
    result = []
    for row in records(ag, run_dir)["discards"]:
        if not isinstance(row, dict):
            continue
        output, path = row.get("output"), row.get("path")
        if (not isinstance(output, str) or not isinstance(path, str)
                or not path.startswith(REJECT_DIR + "/") or os.path.basename(path) != path[len(REJECT_DIR) + 1:]
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            continue
        target = os.path.join(run_dir, *path.split("/"))
        if os.path.isfile(target) and ag.qa.sha256(target) == row.get("sha256"):
            result.append({key: row[key] for key in ("output", "path", "sha256", "reason")})
    return result


def run(ag, run_dir, selection, reason, as_json=False):
    front = ag.existing_front(os.path.join(run_dir, "run.md"))
    if isinstance(front, dict) and front.get("status") == "approved":
        ag.fail("run.md is approved: discard would change the approved outputs; start a new attempt <slug>-NNN+1 instead")
    if not reason or not reason.strip():
        ag.fail("discard needs a non-empty --reason", 2)
    current = outputs(run_dir)
    output = None
    if selection.isdigit():
        index = int(selection)
        if 1 <= index <= len(current):
            output = current[index - 1]
    else:
        candidate = selection if selection.startswith("outputs/") else "outputs/" + selection
        if candidate in current:
            output = candidate
    if output is None:
        ag.fail("no such output %r; current outputs: %s" % (selection, ", ".join(current) or "none"))
    if len(current) == 1:
        ag.fail("nothing would be left to finalize: start a new attempt")
    data = records(ag, run_dir)
    stale = stale_records(ag, run_dir, {output})
    entry = move(ag, run_dir, output, reason.strip(), "discard", data)
    obj = {"schema": "rpg-factory.assetgen-discard/1", "run": os.path.basename(os.path.normpath(run_dir)),
           "discarded": [entry], "stale": stale, "exit": 0}
    lines = ["discarded %s -> %s: %s" % (output, entry["path"], entry["reason"])]
    if stale:
        lines.append("stale now (re-run them): " + ", ".join(stale))
    lines.append("next: re-run qa and the image reviews, then manifest")
    ag.emit(obj, as_json, "\n".join(lines))
    return 0
