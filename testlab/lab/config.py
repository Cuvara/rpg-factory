"""Lab configuration: where the repos, the player and the run artifacts are, and which ports the
isolated (scratch) stack uses.

Defaults come from the workspace layout; every value can be overridden by an optional JSON file
(`--config`, default `<runs_root>/testlab.config.json` when present) and then by CLI flags. Nothing
here is a secret: the scratch stack uses the dev defaults of `backend/deploy/.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import util


def _default_workspace() -> Path:
    env = os.environ.get("RPG_FACTORY_WORKSPACE")
    if env:
        return Path(util.to_windows_path(env)) if util.IS_WINDOWS else Path(env)
    # testlab/lab/config.py -> <factory>/testlab/lab ; the factory checkout lives in the workspace.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "rpg-mmo-server").is_dir() and (parent / "IndieRPGMMOAdventure").is_dir():
            return parent
    return Path("C:/Workspaces/UnityIndie")


@dataclass
class LabConfig:
    workspace: Path = field(default_factory=_default_workspace)
    # The server checkout whose backend/deploy/stack.sh runs the scratch stack. A worktree is fine.
    server_repo: Path | None = None
    # The Unity client project (for builds) and the player under test.
    client_project: Path | None = None
    player_exe: Path | None = None
    unity_exe: Path = Path("C:/Program Files/Unity/Hub/Editor/6000.3.9f1/Editor/Unity.exe")
    runs_root: Path | None = None
    wsl_distro: str = "Ubuntu"

    # Scratch stack (stack.sh --scratch). Ports are fixed by stack.sh; listed so the lab never
    # guesses them and so a conflict check can name what it found.
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 9000
    nakama_host: str = "127.0.0.1"
    nakama_port: int = 8350
    nakama_key: str = "defaultkey"
    status_port: int = 9501
    gateway_metrics_port: int = 9502
    redis_container: str = "rpgs-redis"
    gameserver_container: str = "rpgs-gameserver"
    container_prefix: str = "rpgs-"

    window_width: int = 800
    window_height: int = 600
    loadtest_exe: Path | None = None

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace)
        if self.server_repo is None:
            self.server_repo = self.workspace / "rpg-mmo-server"
        if self.client_project is None:
            self.client_project = self.workspace / "IndieRPGMMOAdventure"
        if self.runs_root is None:
            self.runs_root = self.workspace / ".testlab-runs"
        if self.player_exe is None:
            self.player_exe = self.runs_root / "builds" / "testlab" / "StandaloneWindows64" / "IndieRPGMMOAdventure.exe"
        if self.loadtest_exe is None:
            self.loadtest_exe = self.runs_root / "bin" / ("loadtest.exe" if util.IS_WINDOWS else "loadtest")
        for f in ("server_repo", "client_project", "player_exe", "runs_root", "unity_exe", "loadtest_exe"):
            setattr(self, f, Path(getattr(self, f)))
        # A build directory is accepted for --player: the exe inside it, or inside its
        # StandaloneWindows64 folder (what build-client --out writes).
        if self.player_exe.is_dir():
            for cand in (self.player_exe / "IndieRPGMMOAdventure.exe",
                         self.player_exe / "StandaloneWindows64" / "IndieRPGMMOAdventure.exe"):
                if cand.is_file():
                    self.player_exe = cand
                    break

    @property
    def deploy_dir(self) -> Path:
        return self.server_repo / "backend" / "deploy"

    @property
    def status_url(self) -> str:
        return f"http://127.0.0.1:{self.status_port}/status"

    @property
    def metrics_url(self) -> str:
        return f"http://127.0.0.1:{self.status_port}/metrics"

    @property
    def debug_kill_url(self) -> str:
        return f"http://127.0.0.1:{self.status_port}/debug/kill"

    @property
    def debug_entities_url(self) -> str:
        return f"http://127.0.0.1:{self.status_port}/debug/entities"

    def apply(self, overrides: dict) -> "LabConfig":
        names = {f.name for f in fields(self)}
        for key, value in (overrides or {}).items():
            if key not in names:
                raise ValueError(f"unknown config key '{key}' (known: {', '.join(sorted(names))})")
            setattr(self, key, value)
        self.__post_init__()
        return self

    def as_dict(self) -> dict:
        return {f.name: str(getattr(self, f.name)) if isinstance(getattr(self, f.name), Path) else getattr(self, f.name)
                for f in fields(self)}


def load(config_path: Path | None = None, overrides: dict | None = None) -> LabConfig:
    cfg = LabConfig()
    path = config_path or (cfg.runs_root / "testlab.config.json")
    data = util.read_json(path, default=None) if path and Path(path).exists() else None
    if data:
        cfg.apply(data)
    if overrides:
        cfg.apply({k: v for k, v in overrides.items() if v is not None})
    return cfg
