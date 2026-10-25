"""The game server as a native Windows process (`--server-mode native`).

Why: inside WSL2 the game server's monotonic clock steps in rate against the Windows clock the players
render with (F23, F24B; soak 3ng5). A server built with the Windows dotnet reads the same QueryPerformanceCounter
as the players, so a clock-rate step of the WSL VM can no longer move the server's tick against the
harness second. Redis, Postgres, Nakama and the gateway stay in the scratch compose project: they are not
tick-time critical.

What the lab does here (and nothing else):
- builds GameServer from the configured server checkout with the Windows dotnet into the runs root
  (`--artifacts-path`, so the checkout gets no bin/obj), and records the source sha, the SDK and the hashes
  of the binary it will run;
- reads the environment the scratch compose service WOULD get (`docker compose config` on the generated
  `.env.scratch`: scenario settings, lab secrets and every GAMESERVER_* default), so the settings are the
  compose service's and not a copy, and rewrites only what is container-network specific: the listen and
  advertised address, the metrics address, and the Redis, Postgres and Nakama endpoints (their published
  host ports);
- starts the compose project WITHOUT its `gameserver-dotnet` service, removes a leftover scratch game server
  container and its registry entry, and runs the server as a child process of the host;
- exposes the same /status, /metrics, /debug/* endpoints on the same port, a process CPU/memory sampler
  in place of `docker stats`, and the snapshot trace as a file.

Only the scratch project (`rpg-mmo-scratch`, containers `rpgs-*`) and processes this module started (pid
recorded in `<runs_root>/native/server.json`, killed only while the pid still runs that executable) are ever
touched. Windows only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import util
from .config import LabConfig

RUNTIME = "windows-native"
RID = "win-x64"
SERVICE = "gameserver-dotnet"
SCRATCH_PROJECT = "rpg-mmo-scratch"
CSPROJ = Path("backend") / "gameserver-dotnet" / "GameServer" / "GameServer.csproj"

# Variables that describe the server's own process environment; a stale one inherited from the lab's shell
# must not leak into the child (the compose service starts with exactly its `environment:` list).
_INHERIT_DROP = re.compile(r"^(GAMESERVER_|SIM_|JWT_|JOIN_TOKEN|REDIS_|NAKAMA_|GAME_DB|METRICS_|TRANSPORT_|"
                           r"CONTENT_DIR|AGONES|LOADTEST_|DOTNET_|COMPlus_)")
_SECRET = re.compile(r"(SECRET|PASSWORD|_KEY$|DB_URL|TOKEN)", re.I)

# The last environment this process started a server with, for `restart` (disruption restart_gameserver).
_LAST: dict = {}


class NativeError(RuntimeError):
    pass


def _paths(cfg: LabConfig) -> dict:
    root = cfg.runs_root / "native"
    return {"root": root, "state": root / "server.json", "log": root / "server.log",
            "trace": root / "snapshot-trace.csv", "artifacts": root / "artifacts", "build": root / "build"}


def _git(repo: Path, *args) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              timeout=60).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------------------------- build

def dotnet_version() -> str | None:
    try:
        out = subprocess.run(["dotnet", "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def linker_available() -> bool:
    """NativeAOT on Windows needs the MSVC linker (Visual Studio 'Desktop development with C++'). Looked up
    with vswhere only: a `link.exe` on PATH may be Git for Windows' coreutils `link`, not the linker."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / \
        "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return False
    try:
        out = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                              "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                             capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out)


def build_kind(cfg: LabConfig) -> str:
    """`aot` (what the image runs: NativeAOT) or `r2r` (self-contained ReadyToRun JIT: no linker needed, the code
    is precompiled but tiered JIT still recompiles hot methods). `auto` picks AOT only when the linker exists."""
    if cfg.native_build == "auto":
        return "aot" if linker_available() else "r2r"
    return cfg.native_build


def publish_command(cfg: LabConfig, kind: str, out_dir: Path, artifacts: Path) -> list[str]:
    cmd = ["dotnet", "publish", str(cfg.server_repo / CSPROJ), "-c", "Release", "-r", RID,
           "--self-contained", "true", "--artifacts-path", str(artifacts), "-o", str(out_dir),
           "-nologo", "-nodeReuse:false", "-p:UseSharedCompilation=false"]
    if kind == "r2r":
        cmd += ["-p:PublishAot=false", "-p:PublishReadyToRun=true"]
    elif kind != "aot":
        raise NativeError(f"unknown native build kind '{kind}'")
    return cmd


def build(cfg: LabConfig, log_path: Path) -> dict:
    """Publish the game server for Windows and return the build record (also saved as build.json next to it)."""
    if not util.IS_WINDOWS:
        raise NativeError("--server-mode native runs the game server with the Windows dotnet: Windows only")
    csproj = cfg.server_repo / CSPROJ
    if not csproj.is_file():
        raise NativeError(f"{csproj} not found (set server_repo)")
    sdk = dotnet_version()
    if not sdk:
        raise NativeError("dotnet is not on PATH: the native server needs the Windows .NET SDK")
    kind = build_kind(cfg)
    sha = _git(cfg.server_repo, "rev-parse", "HEAD")
    dirty = bool(_git(cfg.server_repo, "status", "--porcelain", "--", "backend/gameserver-dotnet", "backend/content"))
    p = _paths(cfg)
    out_dir = p["build"] / f"{(sha or 'unknown')[:12]}{'-dirty' if dirty else ''}-{kind}"
    cmd = publish_command(cfg, kind, out_dir, p["artifacts"] / kind)
    started = util.mono()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(res.stdout + "\n--- stderr ---\n" + res.stderr, encoding="utf-8")
    exe = out_dir / "GameServer.exe"
    if res.returncode != 0 or not exe.is_file():
        tail = [l for l in (res.stdout + res.stderr).splitlines() if "error" in l.lower()][:3]
        raise NativeError(f"dotnet publish ({kind}) failed (exit {res.returncode}); log: {log_path}"
                          + (f"; {' | '.join(t.strip()[:300] for t in tail)}" if tail else ""))
    runtime = None
    rc = util.read_json(out_dir / "GameServer.runtimeconfig.json", default=None) or {}
    for fw in (rc.get("runtimeOptions") or {}).get("includedFrameworks") or []:
        runtime = f"{fw.get('name')} {fw.get('version')}"
    rec = {"runtime": RUNTIME, "kind": kind, "rid": RID, "dotnet_sdk": sdk, "dotnet_runtime": runtime,
           "source_sha": sha, "source_dirty": dirty, "exe": str(exe), "out_dir": str(out_dir),
           "exe_sha256": sha256_file(exe), "dll_sha256": sha256_file(out_dir / "GameServer.dll"),
           "built_utc": util.utc_stamp(), "build_seconds": round(util.mono() - started, 1),
           "command": [c if not c.startswith(str(cfg.runs_root)) else "<runs_root>" + c[len(str(cfg.runs_root)):]
                       for c in cmd]}
    util.write_json(out_dir / "build.json", rec)
    return rec


# ---------------------------------------------------------------------------------------- environment

def compose_cmd(cfg: LabConfig, tail: str) -> str:
    """A compose command against the scratch project only, from the deploy directory (relative paths: the
    docker.exe shim cannot resolve absolute WSL paths)."""
    return (f"cd '{util.to_wsl_path(cfg.deploy_dir)}' && docker compose -p {SCRATCH_PROJECT} -f docker-compose.yml "
            f"--env-file .env.scratch --profile realtime {tail}")


def compose_config(cfg: LabConfig) -> dict:
    res = util.wsl(cfg.wsl_distro, compose_cmd(cfg, "config --format json"), timeout=120)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        raise NativeError("docker compose config did not return JSON (is docker reachable in WSL, and "
                          f".env.scratch generated?): {(res.stderr or res.stdout).strip()[:300]}")


def _port(addr: str | None, default: int) -> int:
    try:
        return int(str(addr).rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return default


def native_env(cfg: LabConfig, compose: dict, scenario_env: dict) -> dict:
    """The child process environment: the compose service's resolved `environment`, with only the
    container-network values pointed at the host ports the scratch stack publishes."""
    svc = (compose.get("services") or {}).get(SERVICE)
    if not svc:
        raise NativeError(f"the compose project has no {SERVICE} service: nothing to take the settings from")
    env = {k: str(v) for k, v in (svc.get("environment") or {}).items() if v not in (None, "")}
    port = _port(env.get("GAMESERVER_PUBLIC_ADDR"), 9300)
    nakama = env.get("NAKAMA_URL", "")
    if nakama.startswith("https://"):
        raise NativeError("native mode supports the plaintext Nakama hop only (NAKAMA_URL is https://)")
    env["GAMESERVER_ADDR"] = f"127.0.0.1:{port}"          # loopback: no firewall prompt; players are on this host
    env["GAMESERVER_PUBLIC_ADDR"] = f"127.0.0.1:{port}"   # what the gateway hands the clients
    env["METRICS_ADDR"] = f":{cfg.status_port}"           # Windows binds this as the `localhost` prefix (no admin)
    env["REDIS_ADDR"] = f"127.0.0.1:{cfg.redis_port}"
    if nakama:
        env["NAKAMA_URL"] = f"http://127.0.0.1:{cfg.nakama_port}"
    if env.get("GAME_DB_URL"):
        env["GAME_DB_URL"] = re.sub(r"@postgres-game:\d+/", f"@127.0.0.1:{cfg.postgres_game_port}/", env["GAME_DB_URL"])
    env["CONTENT_DIR"] = str(cfg.server_repo / "backend" / "content")
    if "GAMESERVER_SNAPSHOT_TRACE" in scenario_env:
        env["GAMESERVER_SNAPSHOT_TRACE"] = str(_paths(cfg)["trace"])
    return env


def redact(env: dict) -> dict:
    return {k: ("<redacted>" if _SECRET.search(k) else v) for k, v in sorted(env.items())}


def child_environment(env: dict) -> dict:
    base = {k: v for k, v in os.environ.items() if not _INHERIT_DROP.match(k)}
    base.update(env)
    return base


# ------------------------------------------------------------------------------------------ process

def read_state(cfg: LabConfig) -> dict:
    return util.read_json(_paths(cfg)["state"], default={}) or {}


def running(cfg: LabConfig) -> int | None:
    """The pid of the native server this lab started, only while that pid still runs that executable."""
    st = read_state(cfg)
    pid, exe = st.get("pid"), st.get("exe")
    if not pid or not exe:
        return None
    image = util.process_image(int(pid))
    if image and os.path.normcase(os.path.abspath(image)) == os.path.normcase(os.path.abspath(exe)):
        return int(pid)
    return None


def stop(cfg: LabConfig) -> str | None:
    """Stop the server this lab started. Returns a note, or None when none was running."""
    pid = running(cfg)
    st = read_state(cfg)
    state_path = _paths(cfg)["state"]
    if pid is None:
        if state_path.exists():
            state_path.unlink()
        return None
    util.kill_tree(pid)
    deadline = util.mono() + 15
    while util.mono() < deadline and util.process_alive(pid):
        time.sleep(0.2)
    if state_path.exists():
        state_path.unlink()
    return f"stopped native game server pid {pid}"


def start(cfg: LabConfig, env: dict, build_rec: dict) -> int:
    """Start the server as a detached child with `env`; the pid is recorded. Raises if it exits at once."""
    p = _paths(cfg)
    p["root"].mkdir(parents=True, exist_ok=True)
    if running(cfg) is not None:
        raise NativeError("a native game server of this lab is already running; stop it first")
    trace = env.get("GAMESERVER_SNAPSHOT_TRACE")
    if trace and Path(trace).exists():
        Path(trace).unlink()             # a trace must start with this server: it appends otherwise
    start_offset = log_offset(cfg)
    with open(p["log"], "ab") as log:
        log.write(f"=== native game server start {util.utc_stamp()} ===\n".encode())
        flags = 0
        if util.IS_WINDOWS:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen([build_rec["exe"]], cwd=build_rec["out_dir"], env=child_environment(env),
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
    time.sleep(1.0)
    if proc.poll() is not None:
        raise NativeError(f"the native game server exited at once (code {proc.returncode}):\n{log_tail(cfg)}")
    util.write_json(p["state"], {"pid": proc.pid, "exe": build_rec["exe"], "started_utc": util.utc_stamp(),
                                 "build": build_rec, "env": redact(env), "log_offset": start_offset})
    _LAST.update(cfg=cfg, env=env, build=build_rec)
    return proc.pid


def restart(cfg: LabConfig) -> int:
    """Disruption restart_gameserver / a fresh world: stop and start with the environment of the last start."""
    if not _LAST:
        raise NativeError("no native game server was started by this process: nothing to restart")
    stop(cfg)
    return start(cfg, _LAST["env"], _LAST["build"])


METRICS_FAILED = "Failed to start metrics endpoint"


def startup_failure(cfg: LabConfig) -> str | None:
    """Why the running server will never answer /status, when its own log says so: the metrics endpoint could not
    bind (the server logs that and keeps running, registered, without /status; typically the port is still held
    by a container's published port that WSL has not released yet)."""
    offset = int(read_state(cfg).get("log_offset") or 0)
    try:
        with open(_paths(cfg)["log"], "rb") as fh:
            fh.seek(offset)
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    if METRICS_FAILED in text:
        line = next((l for l in text.splitlines() if METRICS_FAILED in l), METRICS_FAILED)
        return (f"{line.strip()}: the status port {cfg.status_port} is held by another process "
                "(netstat -ano shows which); /status, /metrics and /debug/* would never answer")
    return None


def log_tail(cfg: LabConfig, lines: int = 25) -> str:
    try:
        return "\n".join(_paths(cfg)["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no server log)"


def log_offset(cfg: LabConfig) -> int:
    try:
        return _paths(cfg)["log"].stat().st_size
    except OSError:
        return 0


def copy_log(cfg: LabConfig, offset: int, dest: Path) -> dict:
    """The server's console output since `offset` (the run's start) into the run directory."""
    src = _paths(cfg)["log"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(src, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except OSError as exc:
        return {"copied": False, "error": str(exc)}
    dest.write_bytes(data)
    return {"copied": True, "path": str(dest), "bytes": len(data)}


def fetch_snapshot_trace(cfg: LabConfig, dest: Path) -> dict:
    src = _paths(cfg)["trace"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    ok = src.is_file()
    if ok:
        shutil.copyfile(src, dest)
    return {"container_path": None, "native_path": str(src), "copied": ok, "path": str(dest) if ok else None,
            "bytes": dest.stat().st_size if ok else None,
            "error": None if ok else f"{src} does not exist (the server writes it once snapshots flow)"}


def provenance(cfg: LabConfig) -> dict:
    """The provenance fields of the running native server (empty when none runs)."""
    st = read_state(cfg)
    b = st.get("build") or {}
    return {"runtime": RUNTIME, "pid": st.get("pid"), "started_utc": st.get("started_utc"),
            "kind": b.get("kind"), "rid": b.get("rid"), "dotnet_sdk": b.get("dotnet_sdk"),
            "dotnet_runtime": b.get("dotnet_runtime"), "source_sha": b.get("source_sha"),
            "source_dirty": b.get("source_dirty"), "exe": b.get("exe"), "exe_sha256": b.get("exe_sha256"),
            "dll_sha256": b.get("dll_sha256"), "built_utc": b.get("built_utc")}


# ----------------------------------------------------------------------------------------- sampling

_PREV: dict = {}


def process_stats(pid: int | None) -> dict | None:
    """CPU% (of one core, as `docker stats` reports) and working set of the native server; None when it is
    not running. CPU needs two samples, so the first call after a (re)start has `cpu_pct` None."""
    if not pid or not util.IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    handle = k32.OpenProcess(0x1000 | 0x0400 | 0x0010, False, int(pid))   # QUERY_LIMITED | QUERY | VM_READ
    if not handle:
        return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]
    try:
        c = Counters()
        c.cb = ctypes.sizeof(c)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb):
            return None
        ft = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(handle, *[ctypes.byref(f) for f in ft]):
            return None
        cpu_100ns = sum((f.dwHighDateTime << 32) | f.dwLowDateTime for f in ft[2:])   # kernel + user
    finally:
        k32.CloseHandle(handle)
    now = util.mono()
    prev = _PREV.get(pid)
    _PREV[pid] = (now, cpu_100ns)
    cpu = None
    if prev and now > prev[0]:
        cpu = round((cpu_100ns - prev[1]) / 1e7 / (now - prev[0]) * 100.0, 2)
    mem = int(c.WorkingSetSize)
    return {"cpu_pct": cpu, "mem": f"{mem / (1024 * 1024):.1f}MiB (working set)", "mem_bytes": mem}
