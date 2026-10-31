#!/usr/bin/env python3
"""Deterministically grade isolated write-session artifacts and transcript evidence."""
import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def norm(value):
    value = str(value).replace("\\", "/")
    msys = re.match(r"^/([a-zA-Z])/(.*)$", value)
    if msys:
        value = msys.group(1).upper() + ":/" + msys.group(2)
    return posixpath.normpath(value).lower().rstrip("/")


def normalized_path(value, root):
    value = str(value).replace("\\", "/")
    if not value.startswith("/") and not re.match(r"^[a-zA-Z]:/", value):
        value = root.rstrip("/") + "/" + value
    return norm(value)


def shell_output_paths(command):
    """Return explicit output paths from common shell redirection/write forms."""
    token = r'(?P<path>(?:/[^\s|;&<>"\']+|[A-Za-z]:[\\/][^\s|;&<>"\']+|\.\.?/[^\s|;&<>"\']+))'
    patterns = (
        r'(?:^|\s)>{1,2}\s*["\']?' + token,
        r'(?:^|[|]\s*)tee(?:\s+-a)?\s+["\']?' + token,
        r'(?:^|\s)-o\s+["\']?' + token,
    )
    return [match.group("path") for pattern in patterns for match in re.finditer(pattern, command)]


def records(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--transcript", required=True, type=Path)
    ap.add_argument("--expected-skills", required=True)
    ap.add_argument("--expected-kinds", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--plan", default="")
    ap.add_argument("--installed", action="store_true")
    ap.add_argument("--version", default="")
    ap.add_argument("--loads", default="")
    a = ap.parse_args()
    authoring = a.workspace / "game-authoring"
    events = records(a.transcript)
    failures = []
    used = set()
    writes = []
    bash_commands = []
    for event in events:
        if event.get("type") == "user":
            for block in (event.get("message", {}).get("content") or []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    txt = block.get("content", "")
                    if isinstance(txt, list):
                        txt = " ".join(x.get("text", "") for x in txt if isinstance(x, dict))
                    for skill in re.findall(r"Launching skill: rpg-factory:([\w-]+)", str(txt)):
                        used.add(skill)
        if a.installed and event.get("type") == "system" and event.get("subtype") == "init":
            plugin = next((p for p in event.get("plugins", []) if p.get("name") == "rpg-factory"), None)
            if not plugin or plugin.get("source") != "rpg-factory@rpg-factory":
                failures.append("installed plugin source mismatch")
            elif plugin.get("version") != a.version:
                failures.append("installed plugin version mismatch")
            if plugin and a.loads and norm(os.path.realpath(plugin.get("path", ""))) != norm(os.path.realpath(a.loads)):
                failures.append("installed plugin load path mismatch")
        if event.get("type") == "assistant":
            for block in (event.get("message", {}).get("content") or []):
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name, data = block.get("name"), block.get("input", {})
                if name in ("Write", "Edit", "MultiEdit"):
                    writes.append(str(data.get("file_path", data.get("path", ""))))
                if name in ("Bash", "PowerShell"):
                    bash_commands.append(str(data.get("command", "")))
    for skill in a.expected_skills.split():
        if skill not in used:
            failures.append("missing lead skill " + skill)
    reg = json.loads((a.root / "registry.json").read_text(encoding="utf-8"))
    artifacts = []
    for path in authoring.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "approvals" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                obj = json.loads(raw)
            else:
                match = re.match(r"\A---json\s*\n(.*?)\n---", raw, re.S)
                obj = json.loads(match.group(1)) if match else None
            if isinstance(obj, dict) and obj.get("kind") in a.expected_kinds.split():
                artifacts.append((path, obj))
        except (OSError, ValueError):
            continue
    found = {obj.get("kind") for _, obj in artifacts}
    def routed_to_domain(relative, domain):
        relative = relative.replace("\\", "/").strip("/")
        matches = []
        for module in reg.get("modules", []):
            if module.get("repo") != "authoring":
                continue
            for route in module.get("paths", []):
                route = route.replace("\\", "/").strip("/")
                if not route or relative == route or relative.startswith(route + "/"):
                    matches.append((len(route), module.get("domain", "")))
        if matches:
            depth = max(length for length, _ in matches)
            if any(owner == domain for length, owner in matches if length == depth):
                return True
        for contract in reg.get("contracts", []):
            for endpoint in [contract.get("source", {})] + contract.get("copies", []):
                if endpoint.get("repo") != "authoring" or endpoint.get("domain") != domain:
                    continue
                route = endpoint.get("path", "").replace("\\", "/").strip("/")
                if route and (relative == route or relative.startswith(route + "/")):
                    return True
        return False
    for kind in a.expected_kinds.split():
        if kind not in found:
            failures.append("missing artifact kind " + kind)
        else:
            for path, obj in artifacts:
                if obj.get("kind") == kind and not routed_to_domain(path.relative_to(authoring).as_posix(), obj.get("domain", "")):
                    failures.append("artifact is outside registry-routed path: " + str(path.relative_to(authoring)))
    needed = {"ui-write": ("FD-inventory-001", "feature-spec"), "vfx-write": ("GS-craft-complete-001", "gameplay-system"), "xdomain-art3d-vfx": ("ARTD-workstation-001", "asset-3d"), "xdomain-stale": ("GS-stale-001", "gameplay-system")}.get(a.scenario)
    if needed:
        upstream_id, upstream_kind = needed
        upstream_path = None
        for candidate in authoring.rglob("*.json"):
            if ".git" in candidate.parts:
                continue
            try:
                if json.loads(candidate.read_text(encoding="utf-8")).get("id") == upstream_id:
                    upstream_path = candidate
                    break
            except (OSError, ValueError):
                pass
        if not upstream_path:
            failures.append("missing seeded upstream artifact " + upstream_id)
        else:
            revision = subprocess.run(["git", "-C", str(authoring), "hash-object", str(upstream_path)], capture_output=True, text=True, encoding="utf-8").stdout.strip()
            consumers = [obj for _, obj in artifacts if obj.get("kind") in a.expected_kinds.split() and obj.get("kind") != upstream_kind]
            matching = [ref for obj in consumers for key in ("upstream", "sources") for ref in obj.get(key, []) if isinstance(ref, dict) and ref.get("id") == upstream_id]
            if a.scenario == "xdomain-stale":
                if not matching or all(ref.get("rev") == revision for ref in matching):
                    failures.append("downstream does not retain the stale upstream revision for " + upstream_id)
            elif not any(ref.get("rev") == revision for ref in matching):
                failures.append("missing current upstream id/revision reference to " + upstream_id)
    base = norm(a.workspace.resolve())
    for path in writes:
        if not path:
            failures.append("write tool path missing")
        elif not normalized_path(path, base).startswith(base + "/"):
            failures.append("write outside scratch workspace: " + path)
    # relative output paths resolve against the shell's current directory: the workspace root at the start,
    # then every `cd <dir>` (after `&&`, `;` or a newline), which persists across Bash calls as in Claude Code
    cwd = base
    cd_re = re.compile(r'^\s*cd\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s;&|]+))\s*$')
    for command in bash_commands:
        for segment in re.split(r'&&|;|\n', command):
            moved = cd_re.match(segment)
            if moved:
                cwd = normalized_path(next(g for g in moved.groups() if g), cwd)
                continue
            for path in shell_output_paths(segment):
                if norm(path) != "/dev/null" and not normalized_path(path, cwd).startswith(base + "/"):
                    failures.append("possible write outside scratch workspace: " + path)
    for event in events:
        if event.get("type") == "result" and event.get("subtype") not in (None, "success"):
            failures.append("session did not finish successfully: " + str(event.get("subtype")))
    status = subprocess.run(["git", "-C", str(authoring), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, encoding="utf-8")
    changed = set()
    initial = subprocess.run(["git", "-C", str(authoring), "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    if initial:
        committed = subprocess.run(["git", "-C", str(authoring), "diff", "--name-only", initial[0], "HEAD"], capture_output=True, text=True, encoding="utf-8")
        changed.update(item.replace("\\", "/") for item in committed.stdout.splitlines() if item)
    for line in status.stdout.splitlines():
        rel = line[3:].strip(' "')
        if rel:
            changed.add(rel.replace("\\", "/"))
        if rel and (rel.startswith("../") or ":" in rel or rel.startswith("/")):
            failures.append("unexpected git path " + rel)
    if any("approvals" in p.split("/") and p in changed for p in changed):
        failures.append("approval file created")
    written = [(p, obj) for p, obj in artifacts if p.relative_to(authoring).as_posix() in changed]
    if written:
        lint = subprocess.run([sys.executable, "-B", str(a.root / "scripts/checks/artifact-lint.py"), str(authoring), "--registry", str(a.root / "registry.json")], capture_output=True, text=True, encoding="utf-8")
        ids = {obj.get("id") for _, obj in written}
        for line in lint.stdout.splitlines():
            if line.startswith("FAIL") and any(aid and aid in line for aid in ids):
                failures.append("artifact lint FAIL: " + line)
        for domain in sorted({obj.get("domain") for _, obj in written if obj.get("domain")}):
            quality = subprocess.run([sys.executable, "-B", str(a.root / "scripts/checks/artifact-quality.py"), str(authoring), "--registry", str(a.root / "registry.json"), "--domain", domain, "--json"], capture_output=True, text=True, encoding="utf-8")
            domain_ids = {obj.get("id") for _, obj in written if obj.get("domain") == domain}
            try:
                rows = json.loads(quality.stdout).get("results", [])
                for row in rows:
                    if row.get("artifact") in domain_ids and row.get("state") == "FAIL":
                        failures.append("quality FAIL: " + row.get("artifact", "") + "/" + row.get("check", ""))
            except (ValueError, AttributeError):
                failures.append("artifact-quality returned invalid JSON for " + domain)
    if a.scenario == "xdomain-stale":
        downstream_id = "VFX-craft-complete-001"
        checker = os.environ.get("RPG_FACTORY_ARTIFACT_QUALITY", str(a.root / "scripts/checks/artifact-quality.py"))
        quality = subprocess.run([sys.executable, "-B", checker, str(authoring), "--registry", str(a.root / "registry.json"), "--domain", "vfx", "--json"], capture_output=True, text=True, encoding="utf-8")
        try:
            rows = json.loads(quality.stdout).get("results", [])
            stale_rows = [row for row in rows if row.get("artifact") == downstream_id and row.get("check") == "trace-approval"]
            if quality.returncode not in (0, 1) or not any(row.get("state") == "FAIL" and any("upstream-changed" in reason for reason in row.get("reasons", [])) for row in stale_rows):
                failures.append("stale downstream must have an expected FAIL upstream-changed quality row: " + downstream_id)
        except (ValueError, AttributeError):
            failures.append("artifact-quality returned invalid JSON for stale downstream")
    if a.plan:
        def workflow_targets():
            by_id = {obj.get("id"): obj for _, obj in artifacts if obj.get("id")}
            selected = {obj.get("id") for _, obj in artifacts if obj.get("kind") in a.expected_kinds.split()}
            for aid in list(selected):
                obj = by_id.get(aid, {})
                for ref in obj.get("upstream", []) + obj.get("sources", []):
                    if isinstance(ref, dict) and ref.get("id") in by_id:
                        selected.add(ref["id"])
            return [{"id": by_id[aid]["id"], "kind": by_id[aid]["kind"], "domain": by_id[aid]["domain"]} for aid in sorted(selected) if aid in by_id]
        if a.plan in ("design-ui-eng", "art3d-vfx"):
            joined = "\n".join(bash_commands)
            if "factory-workflow.py" not in joined or "plan" not in joined or "status" not in joined:
                failures.append("workflow plan/status not run")
            targets = workflow_targets()
            spec = {"id": "dogfood-" + a.scenario, "title": a.scenario, "goal": "Verify routed production order", "targets": targets, "existing": [obj["id"] for _, obj in artifacts]}
            with tempfile.TemporaryDirectory(prefix="rpgf-write-grade-") as temp:
                specfile = Path(temp) / "workflow.json"
                specfile.write_text(json.dumps(spec), encoding="utf-8")
                base_cmd = [sys.executable, "-B", str(a.root / "scripts/factory-workflow.py")]
                outputs = []
                for action in ("plan", "status"):
                    result = subprocess.run(base_cmd + [action, str(specfile), "--registry", str(a.root / "registry.json"), "--authoring", str(authoring), "--json"], capture_output=True, text=True, encoding="utf-8")
                    if result.returncode:
                        failures.append("workflow " + action + " failed: " + result.stderr.strip())
                        outputs.append({})
                    else:
                        try:
                            outputs.append(json.loads(result.stdout))
                        except ValueError:
                            failures.append("workflow " + action + " returned invalid JSON")
                            outputs.append({})
                plan_data, status_data = outputs
            waves = plan_data.get("waves", [])
            by_id = plan_data.get("nodes", {})
            flattened = [by_id[n].get("domain") for wave in waves for n in wave if n in by_id]
            if a.plan == "art3d-vfx":
                try:
                    if flattened.index("art3d") >= flattened.index("vfx"):
                        failures.append("workflow waves do not order art3d before vfx")
                except ValueError:
                    failures.append("workflow waves omit art3d or vfx")
            else:
                design_ids = [obj["id"] for _, obj in artifacts if obj.get("kind") == "feature-spec"]
                ui_ids = [obj["id"] for _, obj in artifacts if obj.get("kind") == "screen-spec"]
                engineering_ids = [obj["id"] for _, obj in artifacts if obj.get("kind") == "technical-handoff"]
                positions = {n: i for i, wave in enumerate(waves) for n in wave}
                if not design_ids or not ui_ids or not engineering_ids or positions.get(design_ids[0], 999) >= positions.get(ui_ids[0], -1) or positions.get(ui_ids[0], 999) >= positions.get(engineering_ids[0], -1):
                    failures.append("workflow waves do not order design before UI and engineering handoff")
        elif a.plan == "stale":
            answer = " ".join(str(e.get("result", "")) for e in events if e.get("type") == "result").lower()
            if not any(x in answer for x in ("stale", "revalid")):
                failures.append("session did not report downstream stale / needs revalidation")
            targets = workflow_targets()
            spec = {"id": "dogfood-stale", "title": "Stale handoff", "goal": "Check stale downstream", "targets": targets, "existing": [obj["id"] for _, obj in artifacts]}
            with tempfile.TemporaryDirectory(prefix="rpgf-write-grade-") as temp:
                specfile = Path(temp) / "workflow.json"
                specfile.write_text(json.dumps(spec), encoding="utf-8")
                result = subprocess.run([sys.executable, "-B", str(a.root / "scripts/factory-workflow.py"), "status", str(specfile), "--registry", str(a.root / "registry.json"), "--authoring", str(authoring), "--json"], capture_output=True, text=True, encoding="utf-8")
                try:
                    status = json.loads(result.stdout)
                    if result.returncode or status.get("states", {}).get("VFX-craft-complete-001") != "stale":
                        failures.append("workflow status does not mark downstream artifact stale / needs revalidation")
                except ValueError:
                    failures.append("workflow status returned invalid JSON")
    if failures:
        print("FAIL " + a.scenario + ": " + "; ".join(failures))
        return 1
    print("PASS " + a.scenario + ": " + str(len(artifacts)) + " expected artifacts; skills=" + ",".join(sorted(used)))
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
