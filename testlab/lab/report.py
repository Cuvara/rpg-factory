"""results.json (machine-readable) and report.md (for a reviewer) for one run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import SCHEMA_RESULT, analyze, failsum, util

# INVALID (contaminated host) is not clean: it exits with the INCONCLUSIVE code, never 0.
EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "INVALID": 2, "PASS_WITH_WARNINGS": 4}


def write(run_dir: Path, ev: dict, results: list[dict], outcome: str, harness_error: str | None,
          out_dir: Path | None = None) -> dict:
    meta = ev["meta"]
    sc = ev["scenario"]
    out_dir = Path(out_dir) if out_dir is not None else Path(run_dir)
    prov = next((r for r in results if r.get("check") == "provenance"), None)
    doc = {
        "schema": SCHEMA_RESULT,
        "run_id": meta.get("run_id"),
        # Which run this analysis is of, and by which harness: a results.json copied next to other
        # evidence still names its own run.
        "analysis": {"run_id": meta.get("run_id"), "run_dir": str(run_dir), "run_dir_name": Path(run_dir).name,
                     "analyzed_utc": util.utc_stamp(), "factory_sha": _factory_sha(),
                     "provenance": None if prov is None else prov["status"]},
        "scenario": {"id": sc.get("id"), "version": sc.get("version"), "title": sc.get("title")},
        "outcome": outcome,
        # Shown next to the verdict: informational breaches and host load (analyze.qualifications).
        "qualifications": analyze.qualifications(results, meta),
        "exit_code": EXIT_CODES.get(outcome, 2),
        "harness_error": harness_error,
        "repos": meta.get("repos"),
        "player": meta.get("player"),
        "stack": meta.get("stack"),
        # Where the game server ran: "docker" (scratch container) or "windows-native" (lab/native.py), with the
        # binary it ran. The runtime decides how its clock reads against the players' (F23, F24B).
        "server_runtime": _server_runtime(meta),
        "probe_counts": meta.get("probe_counts"),
        "counts": {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "INCONCLUSIVE", "INVALID", "INFO")},
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
    out_dir.mkdir(parents=True, exist_ok=True)
    util.write_json(out_dir / "results.json", doc)
    with open(out_dir / "report.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_markdown(doc, ev))
    # Derived triage of a run that is not a clean PASS; written last, reads results, never changes them.
    failsum.write(run_dir, ev, results, outcome, harness_error, out_dir)
    return doc


def _server_runtime(meta: dict) -> dict:
    srv = ((meta.get("provenance") or {}).get("server")) or {}
    nat = srv.get("native") or meta.get("server_runtime") or {}
    return {"runtime": srv.get("runtime") or nat.get("runtime") or "docker",
            "build_kind": nat.get("kind"), "dotnet_sdk": nat.get("dotnet_sdk"),
            "dotnet_runtime": nat.get("dotnet_runtime"), "exe_sha256": nat.get("exe_sha256"),
            "source_sha": nat.get("source_sha"), "image_id": srv.get("image_id")}


def _factory_sha() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


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
    if doc["outcome"] == "INVALID":
        fired = [q["id"] for q in doc["qualifications"] if q.get("kind") == "invalid" and str(q.get("id", "")).startswith("G")]
        lines += [f"> **INVALID: the host was not clean while this run was measured** (guards {', '.join(fired) or 'see host_guard'}). "
                  "This is not a verdict on the candidate: no timing result below can be read as PASS, and a FAIL in the table is kept as evidence.", ""]
    rt = doc.get("server_runtime") or {}
    if rt.get("runtime") == "windows-native":
        lines += [f"**Server runtime: windows-native** - the game server ran as a Windows process "
                  f"({rt.get('build_kind')} build, {rt.get('dotnet_runtime')}, binary `{str(rt.get('exe_sha256'))[:12]}`), "
                  "so its Stopwatch is the Windows QPC the players use; Redis, Postgres, Nakama and the gateway ran in the "
                  "scratch stack. A native JIT/ReadyToRun build is not the NativeAOT image: compare with docker-mode "
                  "runs per runtime, not across them.", ""]
    else:
        lines += ["Server runtime: docker (scratch container; its clock is the WSL VM's).", ""]
    if doc["qualifications"]:
        lines += ["**Qualified by:**", ""] + [f"- {q['kind']}: {q['text']}" for q in doc["qualifications"]] + [""]
    lines += [
        f"Analysis of run `{doc['analysis']['run_dir_name']}` at {doc['analysis']['analyzed_utc']} by factory "
        f"`{(doc['analysis']['factory_sha'] or 'unknown')[:10]}`; provenance **{doc['analysis']['provenance']}**.",
        "",
    ]
    if doc["harness_error"]:
        lines += [f"> Harness error: `{doc['harness_error']}` - see harness-error.txt. The result cannot be PASS.", ""]
    repos = doc.get("repos") or {}
    lines += ["## Build and environment", "", "| Item | Value |", "|---|---|"]
    lines.append(f"| server runtime | {rt.get('runtime') or 'docker'}" + (
        f" ({rt.get('build_kind')} build, {rt.get('dotnet_sdk')}, binary `{str(rt.get('exe_sha256'))[:12]}`)"
        if rt.get("runtime") == "windows-native" else "") + " |")
    for key in ("server", "client", "factory"):
        r = repos.get(key) or {}
        lines.append(f"| {key} | `{r.get('branch') or ''}` @ `{(r.get('head') or '')[:10]}`{' (dirty)' if r.get('dirty') else ''} - {r.get('path')} |")
    p = doc.get("player") or {}
    lines.append(f"| player | {p.get('exe')} (NDC.TestLab.dll {((p.get('testlab_dll') or {}).get('sha256')) or 'MISSING'}) |")
    b = p.get("build") or {}
    configured = ((doc.get("repos") or {}).get("client") or {}).get("head")
    if b.get("client_head") and configured and b["client_head"] != configured:
        lines.append(f"| **provenance** | player built from client `{b['client_head'][:10]}` but the configured project is at "
                     f"`{configured[:10]}`: the evidence describes the BUILT commit |")
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
        if r["status"] in ("FAIL", "INCONCLUSIVE", "INVALID", "INFO") or r.get("detail", {}).get("layer"):
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
