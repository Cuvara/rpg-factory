"""Read-only artifact discovery, quality grouping and domain summaries shared by Factory CLIs."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from fstate import workspace

ROOT = Path(__file__).resolve().parents[2]


def scan(authoring_dir):
    authoring = authoring_dir
    found = {}
    if not authoring or not Path(authoring).is_dir():
        return found
    for path in Path(authoring).rglob("*"):
        if not path.is_file() or ".git" in path.parts or "approvals" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                obj = json.loads(raw)
            elif raw.startswith("---json"):
                m = re.match(r"\A---json\s*\n(.*?)\n---", raw, re.S)
                obj = json.loads(m.group(1)) if m else None
            else:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                rev = subprocess.run(["git", "-C", str(authoring), "hash-object", str(path)], capture_output=True, text=True, encoding="utf-8").stdout.strip()
                if not re.fullmatch(r"[0-9a-f]{40,64}", rev):
                    rev = hashlib.sha1(path.read_bytes()).hexdigest()
                found[obj["id"]] = {"id": obj["id"], "rev": rev, "status": obj.get("status", "draft"), "domain": obj.get("domain"), "kind": obj.get("kind"), "path": path.relative_to(authoring).as_posix(), "sources": obj.get("sources", []), "upstream": obj.get("upstream", []), "trace": obj.get("trace", [])}
        except (OSError, ValueError):
            continue
    return found


def quality(authoring, reg_path, repos, involved, domain=None):
    if not authoring or not Path(authoring).is_dir(): return {}
    def unavailable(aid, detail):
        if not detail.startswith("quality-check-unavailable:"):
            detail="quality-check-unavailable: " + detail
        return {"results":[{"artifact":aid,"check":"quality-check-unavailable","state":"BLOCKED","reasons":[detail]}]}
    checker=os.environ.get("RPG_FACTORY_ARTIFACT_QUALITY",str(ROOT/"scripts/checks/artifact-quality.py"))
    cmd=[sys.executable,"-B",checker,authoring,"--registry",reg_path,"--json"]
    if domain is not None: cmd += ["--domain", domain]
    for item in repos: cmd += ["--repos",item]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8")
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        detail=f"could not run artifact-quality: {exc}"
        return {aid:unavailable(aid,detail) for aid in involved}
    detail=None
    if p.returncode not in (0,1): detail=f"artifact-quality exited {p.returncode}: {(p.stderr or p.stdout).strip()}"
    try: data=json.loads(p.stdout)
    except (ValueError, TypeError):
        data=None
        detail=detail or f"artifact-quality returned invalid JSON: {(p.stderr or p.stdout).strip()}"
    if not isinstance(data,dict) or not isinstance(data.get("results"),list):
        detail=detail or "artifact-quality JSON has no results array"
    if detail:
        return {aid:unavailable(aid,detail) for aid in involved}
    grouped = {}
    for result in data.get("results", []):
        if isinstance(result,dict) and result.get("artifact") in involved:
            grouped.setdefault(result["artifact"], {"results": []})["results"].append(result)
    valid_states={"PASS","FAIL","WARN","HUMAN_REQUIRED","NOT_AVAILABLE","BLOCKED"}
    for aid in involved:
        rows=grouped.get(aid,{}).get("results",[])
        bad=[row for row in rows if row.get("state") not in valid_states]
        if bad:
            grouped[aid]=unavailable(aid,f"artifact-quality returned an invalid result for {aid}: {bad[0].get('check')!r} state {bad[0].get('state')!r}")
        elif not rows or not any(row.get("check")=="lifecycle" for row in rows):
            grouped[aid]=unavailable(aid,f"artifact-quality returned no lifecycle result for {aid}")
    return grouped


def upstream_changes(artifact, all_artifacts):
    recorded = {}
    for item in artifact.get("upstream", []):
        if isinstance(item, dict) and item.get("id"):
            recorded[item["id"]] = item.get("rev")
    for item in artifact.get("sources", []):
        if isinstance(item, dict) and item.get("id"):
            recorded.setdefault(item["id"], item.get("rev"))
    return [aid for aid, rev in recorded.items() if aid in all_artifacts and rev != all_artifacts[aid].get("rev")]


def domain_summary(registry: dict, registry_path: str, authoring_dir: str, domain: str) -> dict:
    """Summarize one domain; quality counts check rows, item lists contain unique artifact IDs.

    Stale IDs identify downstream artifacts whose recorded upstream revisions changed.
    An unavailable checker stays BLOCKED rather than being reported as a pass.
    """
    all_artifacts = scan(authoring_dir)
    selected = {aid: art for aid, art in all_artifacts.items() if art.get("domain") == domain}
    ws = workspace(registry)
    repos = [f"{key}={os.path.join(ws, repo['path'])}" for key, repo in registry.get("repos", {}).items()
             if os.path.isdir(os.path.join(ws, repo["path"])) and key != "authoring"]
    grouped = quality(authoring_dir, registry_path, repos, selected, domain=domain) if selected else {}
    statuses = {}
    counts = {state: 0 for state in ("PASS", "FAIL", "WARN", "HUMAN_REQUIRED", "NOT_AVAILABLE", "BLOCKED")}
    human_required, failing = [], []
    for aid, artifact in sorted(selected.items()):
        status = artifact["status"]
        statuses[status] = statuses.get(status, 0) + 1
        states = []
        for row in grouped.get(aid, {}).get("results", []):
            state = row["state"]
            counts[state] = counts.get(state, 0) + 1
            states.append(state)
        if "HUMAN_REQUIRED" in states:
            human_required.append(aid)
        if "FAIL" in states or "BLOCKED" in states:
            failing.append(aid)
    return {"domain": domain, "lead": registry.get("domains", {}).get(domain, {}).get("lead"),
            "artifacts": statuses,
            "stale": sorted(aid for aid, artifact in selected.items() if upstream_changes(artifact, all_artifacts)),
            "quality": counts, "human_required": human_required, "failing": failing}
