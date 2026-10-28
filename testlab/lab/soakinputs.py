"""H6: a soak-class run (`requires_clean_host`) never starts on inputs it picked by itself.

The runner defaults to the player at `<runs_root>/builds/testlab` and to the server checkout `<workspace>/rpg-mmo-server`.
Both go stale without a sound: G-SOAK9 arm A ran a client built from 908950f and a server worktree at 11f0140 because
nothing refused them. For a scenario that needs a clean host (hours of lab time) the player and the server checkout must
be named on the command line (`--player`, `--server-repo`) or in the config file, and, when the caller says which build
it means (`--expect-player-sha`, `--expect-server-sha`), the build that would run must be that one. Other scenarios are
untouched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import util


class SoakInputsError(RuntimeError):
    """The run is refused before anything starts."""


def _git_head(repo: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def player_sha(player_exe: Path) -> str | None:
    """The client commit the player was BUILT from (`testlab-build.json` next to the build, written by build-client)."""
    for cand in (player_exe.parent.parent / "testlab-build.json", player_exe.parent / "testlab-build.json"):
        data = util.read_json(cand, default=None)
        if isinstance(data, dict) and data.get("client_head"):
            return str(data["client_head"])
    return None


def sha_matches(expected: str, actual: str | None) -> bool:
    """`expected` is a prefix (7 or more hex digits) of `actual`, or equal to it; case-insensitive."""
    e = (expected or "").strip().lower()
    return bool(actual) and len(e) >= 7 and actual.lower().startswith(e)


def check(cfg, scenario: dict, *, expect_player_sha: str | None = None, expect_server_sha: str | None = None,
          server_head=_git_head, player_head=player_sha) -> dict:
    """Raise SoakInputsError when a `requires_clean_host` scenario would run on a default or an unexpected build.
    Returns the record stored in run.json (`soak_inputs`)."""
    required = bool(scenario.get("requires_clean_host"))
    explicit = set(getattr(cfg, "explicit", ()) or ())
    rec = {"required": required, "explicit": sorted(explicit & {"player_exe", "server_repo"}),
           "expect_player_sha": expect_player_sha, "expect_server_sha": expect_server_sha}
    if not required:
        return rec
    problems = []
    if "player_exe" not in explicit:
        problems.append(f"no explicit --player: the default player {cfg.player_exe} is whatever was last built there")
    if "server_repo" not in explicit:
        problems.append(f"no explicit --server-repo: the default server checkout {cfg.server_repo} is whatever is checked out there")
    rec["player_sha"] = player_head(cfg.player_exe)
    rec["server_sha"] = server_head(cfg.server_repo)
    if expect_player_sha and not sha_matches(expect_player_sha, rec["player_sha"]):
        problems.append(f"player built from {rec['player_sha'] or 'an unknown commit (no testlab-build.json)'}, expected {expect_player_sha}")
    if expect_server_sha and not sha_matches(expect_server_sha, rec["server_sha"]):
        problems.append(f"server checkout at {rec['server_sha'] or 'an unknown commit'}, expected {expect_server_sha}")
    if problems:
        raise SoakInputsError(f"scenario {scenario.get('id')} requires a clean host and refuses to start: " + "; ".join(problems))
    return rec
