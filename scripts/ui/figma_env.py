#!/usr/bin/env python3
"""Read-only environment check for a Figma-to-Unity import through the official connector.

Usage: figma_env.py --project <unity project> [--json] [--probe-pipeline]

Reports, for one Unity project, what the ui-figma-import workflow needs (com.cuvara.uitoolkit
0.8 Documentation~/FIGMA-INTEGRATION.md "Requirements", FIGMA-VALIDATION.md "Headless import helper"):

  unity              ProjectSettings/ProjectVersion.txt (the package needs 6000.3 or later)
  uitoolkit          com.cuvara.uitoolkit in Packages/ (embedded), manifest.json and packages-lock.json
                     (git #vX.Y.Z, file: path, registry); the Figma integration starts at 0.8.0
  package-source     where the package files are (embedded folder, file: path, Library/PackageCache)
  figma-import       <package>/Tools~/FigmaImport/figma-import.py (the headless import helper)
  connector          com.unity.ui.figma (tested 0.3.0-exp.1; the Cuvara Figma assembly needs 0.3.0-exp.1 or later)
  pipeline-package   com.unity.pipeline (installed by the connector; tested 0.9.1-exp.1)
  pipeline-port      Library/Pipeline/.unity-pipeline-port: present, port, heartbeat age. The evalToken in
                     that file is never printed.
  allow-browser      ProjectSettings/Packages/com.unity.pipeline/EditorPipelineConfig.json m_AllowBrowserClients
  validator-cli      <package>/Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj (the `validate` verb)
  dotnet             dotnet on PATH (builds and runs the validator CLI)
  figma-plugin       the Figma plugin pairing: never visible from files, always HUMAN_REQUIRED
  pipeline-probe     only with --probe-pipeline: one HTTP GET to 127.0.0.1:<port> with a 2 s timeout,
                     no token sent. Without the flag the script opens no socket at all.

Each item has a state OK | NOT_AVAILABLE | HUMAN_REQUIRED, a reason and, when not OK, a fix.
Exit 0 when every required item is OK, 1 otherwise, 2 on a usage error. Writes nothing.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

SCHEMA = "rpg-factory.figma-env/1"
UITOOLKIT = "com.cuvara.uitoolkit"
CONNECTOR = "com.unity.ui.figma"
PIPELINE = "com.unity.pipeline"
MIN_UITOOLKIT = "0.8.0"            # first release with the Figma integration (MIGRATION-0.8.md)
TESTED_CONNECTOR = "0.3.0-exp.1"   # FIGMA-INTEGRATION.md "Requirements"; also the assembly's versionDefines floor
TESTED_PIPELINE = "0.9.1-exp.1"
MIN_UNITY = (6000, 3)              # package.json "unity": "6000.3"
TESTED_UNITY = "6000.3.9f1"
PORT_FILE = ("Library", "Pipeline", ".unity-pipeline-port")
PIPELINE_CONFIG = ("ProjectSettings", "Packages", "com.unity.pipeline", "EditorPipelineConfig.json")
HELPER = ("Tools~", "FigmaImport", "figma-import.py")
VALIDATOR = ("Tools~", "UxmlCodegenCli", "UxmlCodegenCli.csproj")
HEARTBEAT_STALE_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 2.0
OK, NA, HUMAN = "OK", "NOT_AVAILABLE", "HUMAN_REQUIRED"


def version_key(text):
    """'0.3.0-exp.1' -> ((0, 3, 0), 0, ('exp', 1)); a release sorts after its prereleases."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", text or "")
    if not m:
        return None
    core = tuple(int(m.group(i)) for i in (1, 2, 3))
    if not m.group(4):
        return (core, 1, ())
    pre = tuple(int(p) if p.isdigit() else p for p in m.group(4).split("."))
    return (core, 0, tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in pre))


def at_least(version, floor):
    a, b = version_key(version), version_key(floor)
    return a is not None and b is not None and a >= b


def read_json(path):
    """The parsed JSON object, or None. Never echoes the file content."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def find_project(start):
    """The nearest folder at or above start that holds ProjectSettings/ProjectVersion.txt."""
    here = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(here, "ProjectSettings", "ProjectVersion.txt")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def item(ident, state, required, reason, value=None, fix=None, **extra):
    out = {"id": ident, "state": state, "required": required, "value": value, "reason": reason}
    if fix and state != OK:
        out["fix"] = fix
    out.update(extra)
    return out


def check_unity(project):
    path = os.path.join(project, "ProjectSettings", "ProjectVersion.txt")
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError:
        return item("unity", NA, True, "no ProjectSettings/ProjectVersion.txt: not a Unity project",
                    fix="pass --project <Unity project root>")
    m = re.search(r"^m_EditorVersion:\s*(\S+)", text, re.M)
    if not m:
        return item("unity", NA, True, "ProjectVersion.txt has no m_EditorVersion", fix=f"open the project in Unity {TESTED_UNITY}")
    version = m.group(1)
    parts = re.match(r"^(\d+)\.(\d+)", version)
    if not parts or (int(parts.group(1)), int(parts.group(2))) < MIN_UNITY:
        return item("unity", NA, True, f"Unity {version} is older than 6000.3 (com.cuvara.uitoolkit 0.8 needs 6000.3 or later)",
                    value=version, fix=f"upgrade the project to Unity {TESTED_UNITY} (the tested version)")
    note = "the tested version" if version == TESTED_UNITY else f"tested on {TESTED_UNITY}"
    return item("unity", OK, True, f"Unity {version} ({note})", value=version)


def lock_entry(lock, name):
    entry = ((lock or {}).get("dependencies") or {}).get(name)
    return entry if isinstance(entry, dict) else None


def package_json_version(folder):
    data = read_json(os.path.join(folder, "package.json")) if folder else None
    return data.get("version") if data else None


def locate_uitoolkit(project, manifest, lock):
    """(source kind, declared spec, folder or None, version or None, notes)."""
    deps = (manifest or {}).get("dependencies") or {}
    spec = deps.get(UITOOLKIT)
    entry = lock_entry(lock, UITOOLKIT)
    notes = []
    embedded = os.path.join(project, "Packages", UITOOLKIT)
    if os.path.isfile(os.path.join(embedded, "package.json")):
        if spec and not str(spec).startswith("file:"):
            notes.append(f"Packages/{UITOOLKIT} is an embedded copy and wins over the manifest entry {spec}")
        return "embedded", spec, embedded, package_json_version(embedded), notes
    if not spec and not entry:
        return None, None, None, None, notes
    spec = str(spec or entry.get("version") or "")
    if spec.startswith("file:"):
        raw = spec[len("file:"):]
        folder = raw if os.path.isabs(raw) or re.match(r"^[A-Za-z]:[/\\]", raw) else os.path.join(project, "Packages", raw)
        folder = os.path.normpath(folder)
        if not os.path.isfile(os.path.join(folder, "package.json")):
            return "file", spec, None, None, notes + [f"file: path {folder} has no package.json"]
        return "file", spec, folder, package_json_version(folder), notes
    cached = sorted(glob.glob(os.path.join(project, "Library", "PackageCache", UITOOLKIT + "@*")))
    folder = None
    if entry and entry.get("hash"):
        folder = next((c for c in cached if entry["hash"].startswith(c.rsplit("@", 1)[1]) or
                       c.rsplit("@", 1)[1].startswith(entry["hash"])), None)
    if folder is None and len(cached) == 1:
        folder = cached[0]
    if folder is None and cached:
        notes.append(f"{len(cached)} Library/PackageCache entries, none matches packages-lock.json")
    if re.match(r"^(https?|git|ssh)[:+]|\.git(#|$)|^git@", spec):
        m = re.search(r"#v?(\d+\.\d+\.\d+[0-9A-Za-z.-]*)$", spec)
        version = package_json_version(folder) or (m.group(1) if m else None)
        if not m:
            notes.append("git dependency without a #vX.Y.Z tag: the version is whatever the branch head was")
        return "git", spec, folder, version, notes
    return "registry", spec, folder, package_json_version(folder) or spec, notes


def check_uitoolkit(project, manifest, lock):
    kind, spec, folder, version, notes = locate_uitoolkit(project, manifest, lock)
    if kind is None:
        return [item("uitoolkit", NA, True, f"{UITOOLKIT} is not in Packages/manifest.json",
                     fix=f"add {UITOOLKIT} at v{MIN_UITOOLKIT} or later (client: the pin-bump skill)"),
                item("package-source", NA, True, "no package to locate")], None
    out = []
    shown = f"{version or '?'} ({kind}: {spec})" if spec and kind != "embedded" else f"{version or '?'} ({kind})"
    if version and at_least(version, MIN_UITOOLKIT):
        out.append(item("uitoolkit", OK, True, f"{UITOOLKIT} {shown}", value=version, source=kind, spec=spec, notes=notes))
    elif version:
        out.append(item("uitoolkit", NA, True, f"{UITOOLKIT} {shown} predates the Figma integration (0.8.0)",
                        value=version, source=kind, spec=spec, notes=notes,
                        fix=f"move the pin to v{MIN_UITOOLKIT} or later (client: the pin-bump skill)"))
    else:
        out.append(item("uitoolkit", HUMAN, True, f"{UITOOLKIT} version unknown ({kind}: {spec})", source=kind, spec=spec,
                        notes=notes, fix="open the project in Unity so the package manager resolves it, then run this again"))
    if folder:
        out.append(item("package-source", OK, True, f"package files at {folder}", value=folder))
    elif kind == "file":
        out.append(item("package-source", NA, True, f"the file: path does not hold {UITOOLKIT}",
                        fix="point the file: dependency at a com.cuvara.uitoolkit checkout"))
    else:
        out.append(item("package-source", HUMAN, True, f"no Library/PackageCache/{UITOOLKIT}@* entry yet",
                        fix="open the project in Unity once so the package manager downloads the package"))
    return out, folder


def check_dependency(ident, name, manifest, lock, floor, tested, required, fix):
    deps = (manifest or {}).get("dependencies") or {}
    entry = lock_entry(lock, name)
    version = (entry or {}).get("version") or deps.get(name)
    if not version:
        return item(ident, HUMAN if required else NA, required, f"{name} is not installed", fix=fix)
    if not at_least(version, floor):
        return item(ident, HUMAN if required else NA, required, f"{name} {version} is older than {floor}", value=version, fix=fix)
    note = "the tested version" if version == tested else f"tested with {tested}"
    if entry is None:
        note += "; not in packages-lock.json yet (open the project to resolve it)"
    return item(ident, OK, required, f"{name} {version} ({note})", value=version)


def parse_heartbeat(text):
    if not isinstance(text, str):
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$", text.strip())
    if not m:
        return None
    zone = m.group(3) or "Z"
    stamp = m.group(1) + "." + (m.group(2) or "0")[:6].ljust(6, "0") + ("+00:00" if zone == "Z" else zone)
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def check_port(project, unity_version):
    path = os.path.join(project, *PORT_FILE)
    open_fix = f"open the project in Unity {unity_version or TESTED_UNITY} with {CONNECTOR} installed; Pipeline writes the port file while the Editor runs"
    if not os.path.isfile(path):
        return item("pipeline-port", HUMAN, True, "no Library/Pipeline/.unity-pipeline-port: the Editor is not running on this project",
                    fix=open_fix), None
    data = read_json(path)
    if data is None:
        return item("pipeline-port", HUMAN, True, "the port file is not a JSON object", fix=open_fix), None
    port = data.get("port") or 0
    if not port:
        for endpoint in data.get("endpoints") or []:
            if isinstance(endpoint, dict) and endpoint.get("type") == "http" and endpoint.get("port"):
                port = endpoint["port"]
                break
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    has_token = bool(data.get("evalToken"))
    if not port or not has_token:
        return item("pipeline-port", HUMAN, True, "the port file has no port or no evalToken: the Pipeline server is not running",
                    fix="Edit > Project Settings > Pipeline > Editor: start the Pipeline server"), None
    seen = parse_heartbeat(data.get("lastHeartbeat"))
    age = int((datetime.now(timezone.utc) - seen).total_seconds()) if seen else None
    if age is not None and age > HEARTBEAT_STALE_SECONDS:
        return item("pipeline-port", HUMAN, True, f"port {port}, heartbeat {age} s old: the Editor is probably closed",
                    value=port, heartbeat_age_seconds=age, fix=open_fix), port
    when = f", heartbeat {age} s old" if age is not None else ", no readable heartbeat"
    return item("pipeline-port", OK, True, f"port {port}{when} (evalToken present, not shown)", value=port,
                heartbeat_age_seconds=age), port


def check_allow_browser(project):
    data = read_json(os.path.join(project, *PIPELINE_CONFIG))
    fix = "Edit > Project Settings > Pipeline > Editor: enable Allow Browser Clients, then restart the Pipeline server"
    if data is None or "m_AllowBrowserClients" not in data:
        return item("allow-browser", HUMAN, False, "Allow Browser Clients is not set (the Figma plugin cannot connect without it)", fix=fix)
    if data.get("m_AllowBrowserClients") is True:
        return item("allow-browser", OK, False, "Allow Browser Clients is on", value=True)
    return item("allow-browser", HUMAN, False, "Allow Browser Clients is off", value=False, fix=fix)


def check_file(ident, folder, parts, required, what):
    if not folder:
        return item(ident, NA, required, f"no package source, so no {what}"), None
    path = os.path.join(folder, *parts)
    if os.path.isfile(path):
        return item(ident, OK, required, f"{what} at {path}", value=path), path
    return item(ident, NA, required, f"{what} missing at {path}",
                fix=f"use {UITOOLKIT} v{MIN_UITOOLKIT} or later (the file ships under Tools~)"), None


def check_dotnet():
    found = shutil.which("dotnet")
    if found:
        return item("dotnet", OK, False, f"dotnet at {found} (the validator CLI targets net10.0)", value=found)
    return item("dotnet", NA, False, "dotnet is not on PATH: the validator CLI cannot run here",
                fix="install the .NET 10 SDK, or validate in Unity (Window > Cuvara > Figma Diagnostics)")


def probe_pipeline(port):
    """One GET to 127.0.0.1:<port>/ with a 2 s timeout and no credentials. Any HTTP reply is reachable."""
    import http.client
    import socket
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=PROBE_TIMEOUT_SECONDS)
    try:
        connection.request("GET", "/")
        status = connection.getresponse().status
    except (OSError, socket.timeout, http.client.HTTPException) as error:
        return item("pipeline-probe", HUMAN, False, f"127.0.0.1:{port} unreachable ({type(error).__name__})", value="unreachable",
                    fix="open the project in Unity and start the Pipeline server (Edit > Project Settings > Pipeline > Editor)")
    finally:
        connection.close()
    return item("pipeline-probe", OK, False, f"127.0.0.1:{port} reachable (HTTP {status})", value="reachable")


def inspect(project, probe=False):
    """The report as a dict (importable: other Factory scripts may call this)."""
    root = find_project(project) or os.path.abspath(project)
    manifest = read_json(os.path.join(root, "Packages", "manifest.json"))
    lock = read_json(os.path.join(root, "Packages", "packages-lock.json"))
    items = [check_unity(root)]
    unity_version = items[0].get("value")
    if manifest is None:
        items.append(item("manifest", NA, True, "no readable Packages/manifest.json", fix="pass --project <Unity project root>"))
    package_items, folder = check_uitoolkit(root, manifest, lock)
    items += package_items
    helper, helper_path = check_file("figma-import", folder, HELPER, True, "headless import helper")
    items.append(helper)
    connector_fix = (f"Window > Package Manager > + > Add package by name: {CONNECTOR} version {TESTED_CONNECTOR} "
                     "(a change to the project's Packages/manifest.json: ask the user first)")
    items.append(check_dependency("connector", CONNECTOR, manifest, lock, TESTED_CONNECTOR, TESTED_CONNECTOR, True, connector_fix))
    items.append(check_dependency("pipeline-package", PIPELINE, manifest, lock, "0.0.0", TESTED_PIPELINE, True,
                                  f"install {CONNECTOR}; it brings {PIPELINE}"))
    port_item, port = check_port(root, unity_version)
    items.append(port_item)
    items.append(check_allow_browser(root))
    validator, validator_path = check_file("validator-cli", folder, VALIDATOR, False, "validator CLI project")
    items.append(validator)
    items.append(check_dotnet())
    items.append(item("figma-plugin", HUMAN, False, "the Figma plugin pairing is not visible from files",
                      fix="in Figma run the Unity UI Toolkit Connector plugin on the file; in Unity open Window > UI Toolkit > "
                          "Connector for Figma design, select Copy token and paste it within 60 s into the plugin's Settings tab "
                          "(Pipeline token), then Connect to Unity"))
    if probe:
        items.append(probe_pipeline(port) if port else
                     item("pipeline-probe", HUMAN, False, "no port to probe (see pipeline-port)", value="unreachable",
                          fix="open the project in Unity first"))
    required = [i for i in items if i["required"]]
    if any(i["state"] == NA for i in required):
        status = NA
    elif any(i["state"] == HUMAN for i in required):
        status = HUMAN
    else:
        status = OK
    return {
        "schema": SCHEMA,
        "project": root,
        "status": status,
        "probe_pipeline": bool(probe),
        "paths": {"package": folder, "figma_import": helper_path, "validator_csproj": validator_path},
        "items": items,
    }


def render(report):
    lines = [f"figma env: {report['status']}  project {report['project']}"]
    for i in report["items"]:
        need = "required" if i["required"] else "optional"
        lines.append(f"  {i['state']:<14} {i['id']:<16} {need:<8} {i['reason']}")
        for note in i.get("notes") or []:
            lines.append(f"  {'':<14} {'':<16} {'':<8} note: {note}")
        if i.get("fix"):
            lines.append(f"  {'':<14} {'':<16} {'':<8} fix: {i['fix']}")
    if not report["probe_pipeline"]:
        lines.append("  (no network: pass --probe-pipeline to probe the Pipeline port)")
    return "\n".join(lines)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"figma_env.py: error: {message}", file=sys.stderr)
        sys.exit(2)


def main(argv):
    parser = Parser(prog="figma_env.py", description="Read-only Figma connector environment check for a Unity project.")
    parser.add_argument("--project", required=True, help="Unity project root, or a folder inside it")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--probe-pipeline", action="store_true",
                        help="probe the Pipeline port once (127.0.0.1, 2 s timeout); without it no socket is opened")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.project):
        print(f"figma_env.py: error: --project {args.project} is not a directory", file=sys.stderr)
        return 2
    report = inspect(args.project, args.probe_pipeline)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["status"] == OK else 1


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
