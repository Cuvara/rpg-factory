"""The isolated backend: `stack.sh --scratch` in WSL, configured per scenario.

Isolation rules (each one a past or likely incident):
- Only the scratch compose project (`rpg-mmo-scratch`, containers `rpgs-*`, its own ports and
  image tags) is ever started, restarted or stopped. The default stack (`rpg-*`) a developer is
  playing on is never touched; a port held by anything that is not a `rpgs-*` container is a
  conflict the lab reports instead of fighting.
- Scenario server settings travel through `STACK_SCRATCH_EXTRA_ENV` (an env file appended last to
  `.env.scratch`), never through exported variables: a Windows docker shim would drop them.
- A healthy stack whose settings are unchanged is reused; a settings change recreates only the
  services compose decides changed. Every restart is recorded in the run's stack.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import time
from pathlib import Path

from . import util
from .config import LabConfig

ALWAYS_ENV = {
    # /debug/entities: the authoritative positions every movement/crowding check compares with.
    "GAMESERVER_DEBUG_ENTITIES": "on",
    # Every local player and bot reaches the gateway from one docker-bridge address; the
    # production default (10/min per IP) refuses the 11th join in a minute. 0 disables it on the
    # scratch stack only (needs the compose passthrough on rpg-mmo-server's testlab branch).
    "GATEWAY_CONN_RATE_PER_MIN": "0",
}


# Where the game server writes its per-snapshot delivery trace (contract C1) inside the scratch
# container when a scenario sets `snapshot_trace: true`. /tmp is writable for the runtime user.
SNAPSHOT_TRACE_PATH = "/tmp/testlab-snapshot-trace.csv"


class StackError(RuntimeError):
    pass


SCRATCH_PREFIX = "rpgs-"


def is_scratch_name(cfg: LabConfig, name: str) -> bool:
    """True only for a scratch-stack container name. The prefix itself must be a scratch prefix,
    so a misconfigured `container_prefix` ("rpg-", "") can never widen the filter to the
    developer's default stack (`rpg-*`)."""
    prefix = cfg.container_prefix or ""
    return prefix.startswith(SCRATCH_PREFIX) and name.startswith(prefix)


def assert_scratch_name(cfg: LabConfig, name: str) -> None:
    if not is_scratch_name(cfg, name):
        raise StackError(f"refusing to act on container '{name}': only {SCRATCH_PREFIX}* (the scratch stack) is ours")


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def scratch_containers(cfg: LabConfig) -> dict:
    """{name: status} of the scratch project's containers."""
    res = util.wsl(cfg.wsl_distro, "docker ps -a --format '{{.Names}}\t{{.Status}}'", timeout=60)
    if res.returncode != 0:
        raise StackError("docker is not reachable inside WSL: " + (res.stderr or res.stdout).strip()[:400])
    out = {}
    for line in res.stdout.splitlines():
        if "\t" in line:
            name, status = line.split("\t", 1)
            if is_scratch_name(cfg, name):
                out[name] = status
    return out


def preflight(cfg: LabConfig) -> dict:
    """Docker reachable; scratch ports either free or held by the scratch stack itself."""
    report = {"docker": False, "conflicts": [], "scratch_running": []}
    containers = scratch_containers(cfg)
    report["docker"] = True
    running = [n for n, s in containers.items() if s.startswith("Up")]
    report["scratch_running"] = running
    owned = bool(running)
    for port, what in ((cfg.gateway_port, "gateway"), (cfg.nakama_port, "nakama"), (cfg.status_port, "gameserver status")):
        if _port_open(port) and not owned:
            report["conflicts"].append(f"port {port} ({what}) is in use and no {cfg.container_prefix}* container is running")
    if not (cfg.deploy_dir / "stack.sh").exists():
        raise StackError(f"stack.sh not found under {cfg.deploy_dir} (set server_repo)")
    stack_sh = (cfg.deploy_dir / "stack.sh").read_text(encoding="utf-8", errors="replace")
    if "STACK_SCRATCH_EXTRA_ENV" not in stack_sh:
        raise StackError(
            f"{cfg.deploy_dir / 'stack.sh'} predates STACK_SCRATCH_EXTRA_ENV (rpg-mmo-server branch "
            "feat/testlab/autonomous-playtest); scenario server settings could not be applied")
    for name in (cfg.gameserver_container, cfg.redis_container):
        assert_scratch_name(cfg, name)
    if b"\r\n" in (cfg.deploy_dir / "stack.sh").read_bytes():
        raise StackError(f"{cfg.deploy_dir / 'stack.sh'} has CRLF line endings; bash in WSL cannot run it")
    return report


def lab_secrets(cfg: LabConfig) -> dict:
    """Secrets the LAB owns for its scratch stack, generated once and kept under runs_root.

    The scratch stack would otherwise inherit the developer's backend/deploy/.env, which the lab
    must not read (secrets gate). With its own JWT/join-token secrets the lab can hand them to the
    headless load generator (-join direct) without ever opening that file.
    """
    import secrets as _secrets
    path = cfg.runs_root / "stack" / "secrets.json"
    data = util.read_json(path, default=None)
    if not data:
        data = {"JWT_SECRET": "testlab-" + _secrets.token_hex(24),
                "JOIN_TOKEN_SECRET": "testlab-join-" + _secrets.token_hex(24)}
        util.write_json(path, data)
    return data


def advertised_game_addr(cfg: LabConfig, map_id: str = "map_01") -> str:
    """The UDP address the game server advertises (servers:id hash), reachable from Windows."""
    for line_no, line in enumerate(redis_cli(cfg, f"hget servers:id:gs-dotnet-{map_id} addr")):
        if ":" in line:
            return line.strip()
    raise StackError(f"servers:id:gs-dotnet-{map_id} has no addr")


def env_for(scenario: dict, cfg: LabConfig | None = None) -> dict:
    env = dict(ALWAYS_ENV)
    if cfg is not None:
        env.update(lab_secrets(cfg))
    if scenario.get("map"):
        env["GAMESERVER_MAP_ID"] = scenario["map"]
        # Pinned here because .env.scratch inherits the developer's .env, which may pin
        # GAMESERVER_ID to map_01's id whatever map the server actually runs.
        env["GAMESERVER_ID"] = f"gs-dotnet-{scenario['map']}"
    if scenario.get("seed") is not None:
        env["GAMESERVER_ENEMY_SEED"] = str(scenario["seed"])
    for k, v in (scenario.get("server_env") or {}).items():
        env[str(k)] = str(v)
    if scenario.get("snapshot_trace"):
        env["GAMESERVER_SNAPSHOT_TRACE"] = SNAPSHOT_TRACE_PATH
    return env


def compose_forwards(cfg: LabConfig, var: str) -> bool:
    """The compose file passes `var` into the containers (the game server's environment is an
    explicit list, so a setting compose does not forward never reaches the server)."""
    try:
        text = (cfg.deploy_dir / "docker-compose.yml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return re.search(rf"^\s*-?\s*{re.escape(var)}\s*[:=]", text, re.M) is not None


def fetch_snapshot_trace(cfg: LabConfig, dest: Path) -> dict:
    """Copy the server's snapshot trace out of the scratch game server container into the run dir."""
    assert_scratch_name(cfg, cfg.gameserver_container)
    dest.parent.mkdir(parents=True, exist_ok=True)
    res = util.wsl(cfg.wsl_distro, f"docker cp {cfg.gameserver_container}:{SNAPSHOT_TRACE_PATH} "
                                   f"'{util.to_wsl_path(dest)}'", timeout=300)
    ok = res.returncode == 0 and dest.exists()
    return {"container_path": SNAPSHOT_TRACE_PATH, "copied": ok, "path": str(dest) if ok else None,
            "bytes": dest.stat().st_size if ok else None,
            "error": None if ok else (res.stderr or res.stdout).strip()[:300]}


def _env_hash(env: dict) -> str:
    return hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()[:16]


def ensure(cfg: LabConfig, env: dict, *, build: bool, log_path: Path, force_restart_gameserver: bool) -> dict:
    """Bring the scratch stack to `env`. Returns a record of what was done (for stack.json)."""
    state_dir = cfg.runs_root / "stack"
    state_dir.mkdir(parents=True, exist_ok=True)
    env_file = state_dir / "extra.env"
    state_path = state_dir / "state.json"
    wanted = _env_hash(env)
    state = util.read_json(state_path, default={}) or {}
    shown = {k: ("<lab secret>" if "SECRET" in k else v) for k, v in env.items()}
    record = {"env": shown, "env_hash": wanted, "actions": [], "server_repo": str(cfg.server_repo)}

    healthy = health(cfg)["ok"]
    same = state.get("env_hash") == wanted and state.get("server_repo") == str(cfg.server_repo)
    if healthy and same and not build:
        record["actions"].append("reused healthy scratch stack (settings unchanged)")
    else:
        with open(env_file, "w", encoding="utf-8", newline="\n") as fh:
            for k, v in sorted(env.items()):
                fh.write(f"{k}={v}\n")
        flags = "" if build else " --no-build"
        revision = ""
        if build and supports_git_revision(cfg):
            # Stamp the image with the source it is built from (org.opencontainers.image.revision),
            # so provenance can prove the running container is that commit.
            sha = server_head(cfg)
            if sha:
                revision = f"STACK_GIT_REVISION='{sha}' "
                record["stamped_revision"] = sha
        cmd = (f"cd '{util.to_wsl_path(cfg.deploy_dir)}' && "
               f"{revision}STACK_SCRATCH_EXTRA_ENV='{util.to_wsl_path(env_file)}' ./stack.sh --scratch up{flags}")
        started = util.mono()
        res = util.wsl(cfg.wsl_distro, cmd, timeout=3600)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(res.stdout + "\n--- stderr ---\n" + res.stderr, encoding="utf-8")
        record["actions"].append(f"stack.sh --scratch up{flags} exit={res.returncode} in {util.mono() - started:.1f}s"
                                 f" ({'settings changed' if not same else 'stack unhealthy' if not healthy else 'build requested'})")
        if res.returncode != 0:
            raise StackError(f"stack.sh --scratch up failed (exit {res.returncode}); log: {log_path}")
        util.write_json(state_path, {"env_hash": wanted, "server_repo": str(cfg.server_repo), "env": shown})
        force_restart_gameserver = False  # just (re)created

    if force_restart_gameserver:
        restart_gameserver(cfg)
        record["actions"].append(f"docker restart {cfg.gameserver_container} (fresh world for this scenario)")

    wait_ready(cfg, env.get("GAMESERVER_MAP_ID", "map_01"), timeout=120)
    record["health"] = health(cfg)
    return record


NAKAMA_MODULE = "modules/nakama.so"


def check_nakama_module(cfg: LabConfig, build: bool) -> None:
    """The Nakama Go plugin (backend/deploy/modules/nakama.so) is built only by `stack.sh up` with
    builds on. A worktree without it, run without --build-server, starts a Nakama with no
    gateway_token RPC and every join times out after join_timeout_s (T06 lost run
    20261022T174703Z-S09-ierj to this). Fail fast instead."""
    if build:
        return
    if not (cfg.deploy_dir / NAKAMA_MODULE).is_file():
        raise StackError(f"{cfg.deploy_dir / NAKAMA_MODULE} is missing: this server worktree has never been built "
                         "with the stack, so Nakama would start without the gateway_token RPC and every join would "
                         "time out. Run once with --build-server (it builds the plugin and the images).")


REVISION_LABEL = "org.opencontainers.image.revision"


def supports_git_revision(cfg: LabConfig) -> bool:
    """stack.sh stamps STACK_GIT_REVISION into the images (rpg-mmo-server 1dc89ed and later)."""
    try:
        return "STACK_GIT_REVISION" in (cfg.deploy_dir / "stack.sh").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def server_head(cfg: LabConfig) -> str | None:
    """The server checkout's HEAD (Windows git: the worktree is a Windows path), 40-hex or None."""
    import subprocess
    try:
        out = subprocess.run(["git", "-C", str(cfg.server_repo), "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if re.fullmatch(r"[0-9a-f]{40}", out) else None


def image_revision(cfg: LabConfig) -> str | None:
    """The org.opencontainers.image.revision label of the image the scratch game server runs."""
    assert_scratch_name(cfg, cfg.gameserver_container)
    res = util.wsl(cfg.wsl_distro, "docker inspect --format '{{ index .Config.Labels \"" + REVISION_LABEL + "\" }}' "
                   + cfg.gameserver_container, timeout=60)
    out = res.stdout.strip()
    return out if res.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", out) else None


def restart_gameserver(cfg: LabConfig) -> None:
    assert_scratch_name(cfg, cfg.gameserver_container)
    res = util.wsl(cfg.wsl_distro, f"docker restart {cfg.gameserver_container}", timeout=120)
    if res.returncode != 0:
        raise StackError(f"docker restart {cfg.gameserver_container} failed: {res.stderr.strip()[:300]}")


def health(cfg: LabConfig) -> dict:
    status = util.http_json(cfg.status_url, timeout=2)
    nakama_code, _ = util.http_get(f"http://127.0.0.1:{cfg.nakama_port}/healthcheck", timeout=2)
    ok = bool(status and status.get("ok")) and nakama_code == 200 and _port_open(cfg.gateway_port)
    return {"ok": ok, "status_ok": bool(status and status.get("ok")), "nakama": nakama_code,
            "gateway_port_open": _port_open(cfg.gateway_port)}


def wait_ready(cfg: LabConfig, map_id: str, timeout: float) -> None:
    """Healthy endpoints, a registered server for the map, and the initial spawn settled."""
    deadline = util.mono() + timeout
    while util.mono() < deadline:
        if health(cfg)["ok"] and redis_map_members(cfg, map_id):
            return
        time.sleep(1)
    raise StackError(f"scratch stack not ready within {timeout:.0f}s: {health(cfg)}; "
                     f"servers:map:{map_id}={redis_map_members(cfg, map_id)}")


def redis_cli(cfg: LabConfig, args: str) -> list[str]:
    assert_scratch_name(cfg, cfg.redis_container)
    res = util.wsl(cfg.wsl_distro,
                   f"docker exec {cfg.redis_container} sh -c 'redis-cli ${{REDIS_PASSWORD:+-a \"$REDIS_PASSWORD\"}} "
                   f"--no-auth-warning {args}'", timeout=30)
    if res.returncode != 0:
        return []
    return [l for l in res.stdout.splitlines() if l.strip()]


def redis_map_members(cfg: LabConfig, map_id: str) -> list[str]:
    return redis_cli(cfg, f"smembers servers:map:{map_id}")


def redis_session_keys(cfg: LabConfig) -> list[str]:
    return redis_cli(cfg, '--scan --pattern "session:*"')


def docker_stats(cfg: LabConfig) -> dict | None:
    """CPU% and memory of the scratch game server container."""
    assert_scratch_name(cfg, cfg.gameserver_container)
    res = util.wsl(cfg.wsl_distro,
                   f"docker stats --no-stream --format '{{{{.CPUPerc}}}}\t{{{{.MemUsage}}}}' {cfg.gameserver_container}",
                   timeout=30)
    if res.returncode != 0 or "\t" not in res.stdout:
        return None
    cpu, mem = res.stdout.strip().split("\t", 1)
    return {"cpu_pct": _num(cpu.rstrip("%")), "mem": mem.strip(), "mem_bytes": _bytes(mem.split("/")[0])}


def _num(s: str):
    try:
        return float(s)
    except ValueError:
        return None


def _bytes(s: str):
    s = s.strip()
    units = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "kB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}
    for unit in sorted(units, key=len, reverse=True):
        if s.endswith(unit):
            v = _num(s[: -len(unit)])
            return None if v is None else int(v * units[unit])
    return None


def down(cfg: LabConfig) -> str:
    """Stop the scratch stack (`stack.sh --scratch down`: compose project rpg-mmo-scratch only)."""
    for name in (cfg.gameserver_container, cfg.redis_container):
        assert_scratch_name(cfg, name)
    res = util.wsl(cfg.wsl_distro, f"cd '{util.to_wsl_path(cfg.deploy_dir)}' && ./stack.sh --scratch down", timeout=600)
    # The state file says which settings the running stack has; a stopped stack has none.
    state = cfg.runs_root / "stack" / "state.json"
    if res.returncode == 0 and state.exists():
        state.unlink()
    return f"stack.sh --scratch down exit={res.returncode}"
