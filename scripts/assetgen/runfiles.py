"""Run-directory evidence rules shared by the asset-gen engine and the gen-run quality plugin (stdlib only; imports
nothing from the engine, so scripts/checks/domains/assetgen.py can load it by file path).

read_verdict(path, phase) -> {by, state, findings, prompt_sha256, outputs}
  A review file (review-prompt.json, review-image.json) holds one JSON verdict object, possibly inside other text
  (codex exec -o writes the last message). state NOT_RUN when the file is absent, INVALID when no object with state
  PASS or FAIL is found. The binding fields are what review-cmd told the reviewer to copy back unchanged: the
  sha256 of the prompt it reviewed (both phases) and, for the image phase, [{path, sha256}] of the images it saw.
  A verdict without them, or with other values than the run's current prompt and outputs, is unbound or stale.
required_checks(purpose_qa) -> the QA check names every output must carry for that purpose qa block (qa.py runs
  exactly these; the plugin requires a PASS row for each).
requested_size(workflow, spec) -> the size the run asked for: the NineRouterImage size input of workflow.json, else
  the resolved spec's size param, else "auto". qa.json records it next to the purpose content hash it graded with
  (purpose_sha256), so a QA report made before the size or the purpose qa block changed is stale.
"""
import json
import os
import re

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def required_checks(purpose_qa):
    checks = ["png-valid", "png-size", "png-alpha"]
    if purpose_qa.get("transparent_corners"):
        checks.append("png-corners")
    if purpose_qa.get("tileable"):
        checks.append("png-tileable")
    if purpose_qa.get("not_blank") is not None:
        checks.append("png-not-blank")
    return checks


def requested_size(workflow, spec):
    if isinstance(workflow, dict):
        for node in workflow.values():
            if isinstance(node, dict) and node.get("class_type") == "NineRouterImage":
                return (node.get("inputs") or {}).get("size", "auto")
    params = spec.get("params") if isinstance(spec, dict) else None
    return (params or {}).get("size", "auto") if isinstance(params, dict) else "auto"


def _outputs(value):
    if not isinstance(value, list):
        return []
    rows = [{"path": o.get("path"), "sha256": o.get("sha256")} for o in value if isinstance(o, dict)]
    return sorted((o for o in rows if isinstance(o["path"], str) and isinstance(o["sha256"], str)), key=lambda o: o["path"])


def read_verdict(path, phase):
    if not os.path.isfile(path):
        return {"by": None, "state": "NOT_RUN", "findings": 0, "prompt_sha256": None, "outputs": []}
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    obj = None
    for candidate in [text] + re.findall(r"\{.*\}", text, re.S):
        try:
            obj = json.loads(candidate)
            break
        except ValueError:
            continue
    if not isinstance(obj, dict) or obj.get("state") not in ("PASS", "FAIL"):
        return {"by": None, "state": "INVALID", "findings": 0, "prompt_sha256": None, "outputs": []}
    digest = obj.get("prompt_sha256")
    findings = obj.get("findings")
    return {"by": obj.get("by") if isinstance(obj.get("by"), str) and obj.get("by") else None, "state": obj["state"],
            "findings": len(findings) if isinstance(findings, list) else 0,
            "prompt_sha256": digest if isinstance(digest, str) and SHA256.match(digest) else None,
            "outputs": _outputs(obj.get("outputs")) if phase == "image" else []}
