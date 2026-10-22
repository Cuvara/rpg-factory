"""Run provenance: what exactly was tested, recorded when the run happens and verified whenever the
run is analysed.

A run record (run.json `provenance`) names every input that decides what the evidence means:
- the factory, server and client commits, the server image the scratch container ran, the
  Netcode commit embedded in the player (from the build's VERIFY-PROVENANCE.txt) and the player's
  executable and managed-assembly hashes;
- the scenario id, version and the hash of the scenario file as run;
- host load at start and end, and the start and end instants;
- a manifest of the evidence files (relative path -> sha256) taken when the run ended.

`verify()` re-reads the run directory and returns every problem it finds: a missing field, a run id
that does not match its directory, a scenario or evidence file that changed after the run, a client
summary written by another run. Any problem makes the `provenance` assertion INCONCLUSIVE, so a
stale, copied or incomplete run can never grade PASS.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from . import util

SCHEMA = "rpg.testlab.provenance.v1"

# Evidence the checks read: every file under client-*/, server/ and bots/, and these root files.
# Outputs of an analysis (results.json, report.md, delivery.*) and files the orchestrator keeps
# writing after the manifest (orchestrator.log, run.json, control.json, logs) are not evidence.
MANIFEST_DIRS = ("server", "bots")
MANIFEST_FILES = ("scenario.json", "redis.json", "disruptions.ndjson")
MANIFEST_EXCLUDE = re.compile(r"(^|/)(results\.json|report\.md|delivery\.(json|md)|.*\.tmp)$")

# Files every complete run must have recorded (expected_inventory adds the conditional ones).
SERVER_INVENTORY = ("server/entities.ndjson", "server/status.ndjson", "server/container.ndjson",
                    "server/metrics-start.txt", "server/metrics-end.txt")
CLIENT_INVENTORY = ("plan.json", "status.json", "summary.json", "events.ndjson", "snapshots.ndjson",
                    "samples.ndjson", "frames.csv")


def expected_inventory(scenario: dict) -> list[str]:
    """The evidence files a finished run of `scenario` must have, as relative posix paths: the
    scenario as run, redis, the server probe, each client's recorder outputs, and the files only some
    scenarios produce (disruptions.ndjson with disruptions, bots/loadtest.json with bots,
    server/snapshot-trace.csv with snapshot_trace)."""
    inv = ["scenario.json", "redis.json", *SERVER_INVENTORY]
    for i in range(int(scenario.get("clients", 0))):
        inv += [f"client-{i}/{n}" for n in CLIENT_INVENTORY]
    if scenario.get("disruptions"):
        inv.append("disruptions.ndjson")
    if int((scenario.get("bots") or {}).get("players", 0) or 0) > 0:
        inv.append("bots/loadtest.json")
    if scenario.get("snapshot_trace"):
        inv.append("server/snapshot-trace.csv")
    return inv


def sha256_file(path: Path, chunk: int = 1 << 20) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def managed_dir(exe: Path) -> Path:
    return exe.parent / (exe.stem + "_Data") / "Managed"


def managed_sha256(exe: Path) -> str | None:
    """One hash over every managed assembly of the player (name + content, sorted): the code that
    ran. The Unity exe itself is a launcher stub identical across builds of one Unity version."""
    d = managed_dir(exe)
    if not d.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(d.glob("*.dll")):
        h.update(p.name.encode())
        h.update((sha256_file(p) or "").encode())
    return h.hexdigest()


def read_verify_provenance(build_root: Path) -> dict | None:
    """VERIFY-PROVENANCE.txt written by the verification build script: `netcode <sha> client <sha>`."""
    path = build_root / "VERIFY-PROVENANCE.txt"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out = {"path": str(path)}
    for key in ("netcode", "client"):
        m = re.search(rf"\b{key}\s+([0-9a-f]{{7,40}})\b", text)
        if m:
            out[key] = m.group(1)
    return out


def netcode_record(build: dict | None, verify: dict | None) -> dict:
    """Which Netcode the player compiled. A build that embeds com.cuvara.netcode under Packages/ (an
    unreleased commit) must name that commit; a build without an embedded copy used the manifest
    pin. The commit comes from VERIFY-PROVENANCE.txt (verification builds) or from the `netcode`
    block build-client writes into testlab-build.json (embedded git HEAD or packages-lock hash)."""
    embedded = [p for p in ((build or {}).get("embedded_packages") or []) if p.get("name") == "com.cuvara.netcode"]
    written = (build or {}).get("netcode") or {}
    sha, source = (verify or {}).get("netcode"), (verify or {}).get("path") if (verify or {}).get("netcode") else None
    if not sha and written.get("sha"):
        sha, source = written["sha"], f"testlab-build.json netcode ({written.get('source')})"
    rec = {"embedded": bool(embedded), "sha": sha,
           "version": embedded[0].get("version") if embedded else written.get("version"),
           "cs_sha256": embedded[0].get("cs_sha256") if embedded else None,
           "dirty": written.get("dirty"), "source": source}
    if build is None:
        rec["embedded"] = None  # unknown: no testlab-build.json
    return rec


def player_record(exe: Path) -> dict:
    build_root = exe.parent.parent
    build = util.read_json(build_root / "testlab-build.json", default=None)
    verify = read_verify_provenance(build_root)
    return {
        "exe": str(exe),
        "exe_sha256": sha256_file(exe) if exe.exists() else None,
        "managed_sha256": managed_sha256(exe),
        "built_from_client": (build or {}).get("client_head"),
        "built_dirty": (build or {}).get("client_dirty"),
        "verify_provenance": verify,
        "netcode": netcode_record(build, verify),
    }


def docker_image_id(cfg, container: str) -> str | None:
    """Image id the scratch container runs (`docker inspect`). Only `rpgs-*` names are asked for."""
    from . import stack
    stack.assert_scratch_name(cfg, container)
    res = util.wsl(cfg.wsl_distro, f"docker inspect --format '{{{{.Image}}}}' {container}", timeout=60)
    out = res.stdout.strip()
    return out if res.returncode == 0 and out.startswith("sha256:") else None


def git(repo: Path, *args) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def evidence_files(run_dir: Path) -> list[Path]:
    """Every evidence file now in the run directory (the set the manifest records)."""
    run_dir = Path(run_dir)
    paths = [run_dir / f for f in MANIFEST_FILES]
    paths += sorted(p for p in run_dir.glob("client-*/**/*") if p.is_file())
    for d in MANIFEST_DIRS:
        paths += sorted(p for p in (run_dir / d).glob("**/*") if p.is_file())
    return [p for p in paths if p.is_file() and not MANIFEST_EXCLUDE.search(p.relative_to(run_dir).as_posix())]


def manifest(run_dir: Path) -> dict:
    """{relative posix path: sha256} of the evidence files in a run directory."""
    return {p.relative_to(run_dir).as_posix(): sha256_file(p) for p in evidence_files(run_dir)}


# Fields a complete record must carry: (dotted path, why it matters).
REQUIRED = (
    ("run_id", "binds the record to its run directory"),
    ("factory.sha", "the harness and checks that produced the evidence"),
    ("server.sha", "the server source"),
    ("server.image_id", "the image the scratch container actually ran"),
    ("client.sha", "the client commit the player was built from"),
    ("player.exe_sha256", "the player executable"),
    ("player.managed_sha256", "the player's managed code"),
    ("scenario.id", "what was run"),
    ("scenario.version", "which version of it"),
    ("scenario.sha256", "the scenario file as run"),
    ("host_quiet.load_start", "host load when the run started"),
    ("host_quiet.load_end", "host load when the run ended"),
    ("started_utc", "start instant"),
    ("ended_utc", "end instant"),
    ("manifest", "evidence files and their hashes"),
)


def _get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def verify(run_dir: Path, meta: dict, scenario: dict, clients: list[dict]) -> list[str]:
    """Every reason the run directory does not match its provenance record; [] when it does."""
    prov = (meta or {}).get("provenance")
    if not prov:
        return ["run.json has no provenance record (run predates provenance, or the harness failed before writing it)"]
    problems = []
    for path, why in REQUIRED:
        if _get(prov, path) in (None, "", {}):
            problems.append(f"provenance.{path} missing ({why})")
    nc = prov.get("netcode") or (prov.get("player") or {}).get("netcode") or {}
    if nc.get("embedded") is None:
        problems.append("provenance.netcode: unknown whether the player embedded Netcode (no testlab-build.json)")
    elif nc.get("embedded") and not nc.get("sha"):
        problems.append("provenance.netcode.sha missing: the player embeds com.cuvara.netcode but its build has no "
                        "VERIFY-PROVENANCE.txt naming the commit")
    srv = prov.get("server") or {}
    if srv.get("label_supported"):
        rev, sha = srv.get("image_revision"), srv.get("sha")
        if not rev:
            problems.append("server image has no revision label although stack.sh supports STACK_GIT_REVISION "
                            "(image built without it: rebuild with --build-server)")
        elif not sha or not sha.startswith(rev) and not rev.startswith(sha):
            problems.append(f"server image revision {rev[:12]} != recorded server sha {str(sha)[:12]}: the container "
                            "does not run the recorded source (rebuild with --build-server)")
    name = Path(run_dir).name
    for label, rid in (("provenance.run_id", prov.get("run_id")), ("run.json run_id", meta.get("run_id"))):
        if rid and rid != name:
            problems.append(f"{label} '{rid}' does not match the run directory '{name}'")
    ps = prov.get("scenario") or {}
    if scenario.get("id") != ps.get("id") or scenario.get("version") != ps.get("version"):
        problems.append(f"scenario.json is {scenario.get('id')} v{scenario.get('version')}, the record says "
                        f"{ps.get('id')} v{ps.get('version')}")
    if ps.get("sha256") and sha256_file(Path(run_dir) / "scenario.json") != ps["sha256"]:
        problems.append("scenario.json changed after the run (hash mismatch)")
    for c in clients:
        s = c.get("summary") or {}
        if s.get("run_id") and s["run_id"] != prov.get("run_id"):
            problems.append(f"client-{c['index']}/summary.json belongs to run {s['run_id']}")
    recorded = prov.get("manifest") or {}
    if recorded:
        # Every file the scenario must produce is in the record (a truncated manifest proves nothing
        # about what it left out), and no evidence file appeared after the run.
        for rel in expected_inventory(scenario):
            if rel not in recorded:
                problems.append(f"evidence file {rel} is not in the manifest (omitted, or never written)")
        for p in evidence_files(Path(run_dir)):
            rel = p.relative_to(run_dir).as_posix()
            if rel not in recorded:
                problems.append(f"evidence file {rel} is not in the manifest (added after the run)")
        for rel, digest in sorted(recorded.items()):
            now = sha256_file(Path(run_dir) / rel)
            if now is None:
                problems.append(f"evidence file {rel} is missing")
            elif now != digest:
                problems.append(f"evidence file {rel} changed after the run (hash mismatch)")
            if len(problems) > 40:
                problems.append("... (more)")
                break
    return problems
