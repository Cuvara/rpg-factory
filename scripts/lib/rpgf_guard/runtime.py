"""Fail-open hook input, independently isolated checks and advisory output."""
import io
import json
import os
import sys

from .common import MAX_COMMAND, load_registry
from .gates import human_gate_hits, skill_read_hits
from .git import evaluate
from .mode import _needs_mode, mode_hits
from .process import process_kill_hits

def main():
    if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"}:
        return 0
    try:  # UTF-8 whatever the console code page (Windows pipes default to cp1252: a non-ASCII cwd broke the match)
        stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace") if hasattr(sys.stdin, "buffer") else sys.stdin
        payload = json.load(stream)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") not in (None, "Bash", "PowerShell"):
        return 0  # `[]`, `null`, `42`: not a hook payload
    if not isinstance(payload.get("tool_input") or {}, dict) or not isinstance((payload.get("tool_input") or {}).get("command") or "", str):
        return 0
    registry = load_registry()
    if not registry:
        return 0
    reasons = collect(payload, registry)
    if reasons:
        json.dump(advisory("rpg-factory guard", reasons), sys.stdout)
    return 0


def collect(payload, registry, skill_tool=True):
    """Every reason for one Bash/PowerShell payload (dialect from tool_name). skill_tool=False is for runtimes
    without a Skill tool (Codex reads SKILL.md to load a skill): it drops the skill-read advisory. An argument,
    not a payload field, so no hook input can switch it off."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if len(command) > MAX_COMMAND:  # analysing it would take minutes: say so instead of guessing
        return [("ask", f"command too large to check ({len(command) // 1024} KB); review it")]
    reasons = []
    try:
        need_mode = _needs_mode(payload)
    except Exception:
        need_mode = True  # cannot tell cheaply: do the full checks
    parts = (mode_hits, evaluate, human_gate_hits, process_kill_hits) if need_mode else (evaluate, human_gate_hits, process_kill_hits)
    if skill_tool:
        parts += (skill_read_hits,)
    for part in parts:  # isolated: a failure in one never drops the others
        try:
            reasons += part(payload, registry)
        except Exception:  # a guard bug must never break the session
            pass
    return reasons


def advisory(who, reasons):
    """Advisory only (1.0.3): never a permissionDecision, so the hook neither asks the user nor blocks the agent.
    The former deny class is level `high`, the former ask class `warn`; the text reaches the agent as context."""
    level = "high" if any(d == "deny" for d, _ in reasons) else "warn"
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": f"rpg-factory advisory ({level}): {who}: " + "; ".join(dict.fromkeys(t for _, t in reasons)),
    }}


def run():
    """The hook entry (scripts/git-guard.py, which sets UTF-8 output): any guard bug is no opinion (exit 0)."""
    try:
        return main()
    except Exception:  # a guard bug must never break the session: no opinion
        return 0
