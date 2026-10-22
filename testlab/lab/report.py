"""results.json (machine-readable) and report.md (for a reviewer) for one run."""

from __future__ import annotations

import json
from pathlib import Path

from . import SCHEMA_RESULT, util

EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}


def write(run_dir: Path, ev: dict, results: list[dict], outcome: str, harness_error: str | None) -> dict:
    meta = ev["meta"]
    sc = ev["scenario"]
    doc = {
        "schema": SCHEMA_RESULT,
        "run_id": meta.get("run_id"),
        "scenario": {"id": sc.get("id"), "version": sc.get("version"), "title": sc.get("title")},
        "outcome": outcome,
        "exit_code": EXIT_CODES.get(outcome, 2),
        "harness_error": harness_error,
        "repos": meta.get("repos"),
        "player": meta.get("player"),
        "stack": meta.get("stack"),
        "probe_counts": meta.get("probe_counts"),
        "counts": {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "INCONCLUSIVE", "INFO")},
        "assertions": results,
        "clients": [
            {"index": c["index"], "user_id": (c["summary"] or {}).get("user_id"), "outcome": (c["summary"] or {}).get("outcome"),
             "frames": (c["summary"] or {}).get("frames"), "net": (c["summary"] or {}).get("net"),
             "render": (c["summary"] or {}).get("render"), "prediction": (c["summary"] or {}).get("prediction"),
             "input": (c["summary"] or {}).get("input"),
             "screenshots": sorted(str(p.relative_to(run_dir)) for p in (c["dir"] / "shots").glob("*.png"))}
            for c in ev["clients"]
        ],
    }
    util.write_json(run_dir / "results.json", doc)
    (run_dir / "report.md").write_text(_markdown(doc, ev), encoding="utf-8")
    return doc


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, (dict, list)):
        return "`" + json.dumps(v, separators=(", ", ": "))[:300] + "`"
    return str(v)


def _markdown(doc: dict, ev: dict) -> str:
    sc = ev["scenario"]
    lines = [
        f"# Testlab run {doc['run_id']}",
        "",
        f"**Outcome: {doc['outcome']}** (exit {doc['exit_code']}) - scenario `{sc.get('id')}` v{sc.get('version')}: {sc.get('title')}",
        "",
    ]
    if doc["harness_error"]:
        lines += [f"> Harness error: `{doc['harness_error']}` - see harness-error.txt. The result cannot be PASS.", ""]
    repos = doc.get("repos") or {}
    lines += ["## Build and environment", "", "| Item | Value |", "|---|---|"]
    for key in ("server", "client", "factory"):
        r = repos.get(key) or {}
        lines.append(f"| {key} | `{r.get('branch') or ''}` @ `{(r.get('head') or '')[:10]}`{' (dirty)' if r.get('dirty') else ''} - {r.get('path')} |")
    p = doc.get("player") or {}
    lines.append(f"| player | {p.get('exe')} (NDC.TestLab.dll {((p.get('testlab_dll') or {}).get('sha256')) or 'MISSING'}) |")
    b = p.get("build") or {}
    lines.append(f"| player built from | `{(b.get('client_head') or 'unknown')[:10]}`{' + uncommitted changes' if b.get('client_dirty') else ''}"
                 f" in {b.get('project')} at {b.get('built_utc')} defines {b.get('defines')} |")
    for pkg in b.get("embedded_packages") or []:
        if str(pkg.get("name", "")).startswith("com.cuvara."):
            lines.append(f"| embedded package | {pkg.get('name')} {pkg.get('version')} (sources {pkg.get('cs_sha256')}) - overrides the manifest pin |")
    for action in (doc.get("stack") or {}).get("actions", []):
        lines.append(f"| stack | {action} |")
    lines.append(f"| probe | {_fmt(doc.get('probe_counts'))} |")
    lines += ["", "## Assertions", "", "| # | Assertion | Status | Measured | Threshold | Source / sampling |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(doc["assertions"], 1):
        lines.append(f"| {i} | `{r['id']}` {r.get('title', '')} | **{r['status']}** | {_fmt(r.get('measured'))} | "
                     f"{_fmt(r.get('threshold'))} | {r.get('source')} ({r.get('sampling')}) |")
    lines += ["", "## Details", ""]
    for r in doc["assertions"]:
        if r["status"] in ("FAIL", "INCONCLUSIVE", "INFO") or r.get("detail", {}).get("layer"):
            lines += [f"### {r['id']} - {r['status']}", "", f"Rationale: {r.get('rationale', '')}", "",
                      "```json", json.dumps(r.get("detail"), indent=2)[:6000], "```", ""]
            if r.get("artifacts"):
                lines += ["Artifacts: " + ", ".join(f"`{a}`" for a in r["artifacts"][:8]), ""]
    lines += ["## Clients", "", "| # | user | outcome | frame p50/p95/p99 ms | snapshots | max gap ms | render jumps | predict snaps | screenshots |",
              "|---|---|---|---|---|---|---|---|---|"]
    for c in doc["clients"]:
        f = c.get("frames") or {}
        n = c.get("net") or {}
        rd = c.get("render") or {}
        pr = c.get("prediction") or {}
        lines.append(f"| {c['index']} | `{c.get('user_id')}` | {c.get('outcome')} | {_r(f.get('p50_ms'))}/{_r(f.get('p95_ms'))}/{_r(f.get('p99_ms'))} | "
                     f"{n.get('snapshots')} | {_r(n.get('max_snapshot_gap_ms'))} | {rd.get('jumps')} (local {rd.get('local_jumps')}) | "
                     f"{pr.get('snaps')} | {len(c.get('screenshots') or [])} |")
    lines += ["", "Raw evidence: `client-*/` (status, summary, events, inputs, snapshots, samples, frames.csv, shots/), "
              "`server/` (entities, status, container, metrics-start/end), `redis.json`, `run.json`, `orchestrator.log`.", ""]
    return "\n".join(lines)


def _r(v):
    return "-" if v is None else f"{v:.1f}" if isinstance(v, float) else str(v)
