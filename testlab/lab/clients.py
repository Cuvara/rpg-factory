"""Real Unity players: launch, readiness, the shared start instant, and cleanup of exactly the
processes this run started.

Each player gets its own device id (so its own Nakama user), its own log file, plan and output
directory. Processes are started directly from Python (no shell, no launcher script), so the PID
recorded is the player's own and Windows paths are passed verbatim - no MSYS or wslpath
conversion is involved anywhere.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from . import util
from .config import LabConfig

ACTIVE_FILE = "active-pids.json"


class ClientError(RuntimeError):
    pass


class Player:
    def __init__(self, index: int, run_dir: Path, run_id: str, device: str):
        self.index = index
        self.dir = run_dir / f"client-{index}"
        self.device = device
        self.run_id = run_id
        self.proc: subprocess.Popen | None = None
        self.pid: int | None = None
        self.launches = 0
        self.history: list[dict] = []

    @property
    def status_path(self) -> Path:
        return self.dir / "status.json"

    def status(self) -> dict:
        return util.read_json(self.status_path, default={}) or {}


def register_active(cfg: LabConfig, run_id: str, pids: list[int], exe: Path) -> None:
    path = cfg.runs_root / ACTIVE_FILE
    data = util.read_json(path, default={}) or {}
    data[run_id] = {"pids": pids, "exe": str(exe)}
    util.write_json(path, data)


def unregister_active(cfg: LabConfig, run_id: str) -> None:
    path = cfg.runs_root / ACTIVE_FILE
    data = util.read_json(path, default={}) or {}
    data.pop(run_id, None)
    util.write_json(path, data)


def clean_orphans(cfg: LabConfig) -> list[str]:
    """Kill players left by an interrupted run - only PIDs this lab recorded, and only while the
    process behind the PID is still that player executable (a reused PID is never killed)."""
    path = cfg.runs_root / ACTIVE_FILE
    data = util.read_json(path, default={}) or {}
    done = []
    for run_id, entry in list(data.items()):
        exe = os.path.normcase(os.path.abspath(entry.get("exe", "")))
        for pid in entry.get("pids", []):
            image = util.process_image(pid)
            if image and os.path.normcase(os.path.abspath(image)) == exe:
                util.kill_tree(pid)
                done.append(f"killed orphan pid {pid} from run {run_id}")
        data.pop(run_id, None)
    util.write_json(path, data)
    return done


def launch(cfg: LabConfig, sc: dict, player: Player, plan_path: Path, control_path: Path) -> None:
    exe = cfg.player_exe
    if not exe.exists():
        raise ClientError(f"player not found: {exe} (build it: testlab.py build-client)")
    player.dir.mkdir(parents=True, exist_ok=True)
    player.launches += 1
    log = player.dir / ("player.log" if player.launches == 1 else f"player-{player.launches}.log")
    args = [
        str(exe),
        "-logFile", str(log),
        "-screen-fullscreen", "0",
        "-screen-width", str(cfg.window_width),
        "-screen-height", str(cfg.window_height),
        "-cuvara-gateway-host", cfg.gateway_host,
        "-cuvara-gateway-port", str(cfg.gateway_port),
        "-cuvara-nakama-host", cfg.nakama_host,
        "-cuvara-nakama-port", str(cfg.nakama_port),
        "-cuvara-nakama-key", cfg.nakama_key,
        "-cuvara-map", sc["map"],
        "-cuvara-device", player.device,
        "-cuvara-instance", str(player.index),
        "-cuvara-status-url", cfg.status_url,
        "-testlab-plan", str(plan_path),
        "-testlab-out", str(player.dir),
        "-testlab-control", str(control_path),
    ]
    # A relaunch must not read the previous process's terminal status as its own.
    if player.status_path.exists():
        player.status_path.unlink()
    flags = 0
    if util.IS_WINDOWS:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    player.proc = subprocess.Popen(args, cwd=str(exe.parent), creationflags=flags,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    player.pid = player.proc.pid
    player.history.append({"event": "launch", "pid": player.pid, "mono": util.mono(), "log": str(log)})


def wait_phase(players: list[Player], phases: set[str], timeout: float, *, label: str) -> dict[int, str]:
    """Wait until every player's status phase is in `phases`; raise on an error phase or exit."""
    deadline = util.mono() + timeout
    while True:
        states = {}
        for p in players:
            st = p.status()
            phase = st.get("phase", "starting")
            if phase == "error":
                raise ClientError(f"client {p.index} reported error while waiting for {label}: {st.get('error')}")
            if p.proc is not None and p.proc.poll() is not None and phase not in phases:
                raise ClientError(f"client {p.index} exited (code {p.proc.returncode}) while waiting for {label}; "
                                  f"last phase {phase}; log {p.dir}")
            states[p.index] = phase
        if all(s in phases for s in states.values()):
            return states
        if util.mono() > deadline:
            raise ClientError(f"timeout after {timeout:.0f}s waiting for {label}: {states}")
        time.sleep(0.5)


def write_control(path: Path, start_at_unix_ms: int, user_ids: list[str], abort: bool = False) -> None:
    util.write_json(path, {"start_at_unix_ms": start_at_unix_ms, "client_user_ids": user_ids, "abort": abort})


def wait_exit(players: list[Player], timeout: float) -> dict[int, int | None]:
    deadline = util.mono() + timeout
    codes = {}
    while util.mono() < deadline:
        codes = {p.index: (p.proc.poll() if p.proc else None) for p in players}
        if all(c is not None for c in codes.values()):
            return codes
        time.sleep(0.5)
    return codes


def stop(players: list[Player]) -> list[str]:
    """Kill the players this run started that are still alive (and only those)."""
    notes = []
    for p in players:
        if p.proc is not None and p.proc.poll() is None:
            util.kill_tree(p.proc.pid)
            notes.append(f"killed client {p.index} pid {p.proc.pid}")
    return notes
