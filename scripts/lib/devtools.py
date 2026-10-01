"""Probe the developer tools the registry declares (`services`, `dev_tools`). Read-only.

Used by the snapshot (lib/context.py) and `/rpg-factory:doctor` (factory-cmd.py).

A `dev_tools` entry lists `probes`; all must pass for the tool to be available. One probe may hold
alternatives separated by `|` (any one passes). Probe kinds:

  bin:<name>       executable on PATH
  tool:<key>       registry `tools.<key>` resolves (its candidates on PATH)
  service:<id>     registry `services.<id>` tcp probe connects (0.3 s timeout)
  mcp:<server>     an MCP server with that name is configured: workspace or repo `.mcp.json`,
                   `~/.claude.json` (top level or the workspace/repo project entry)
  plugin:<name>    a Claude Code plugin `<name>@<marketplace>` is enabled in a settings file

Only server and plugin NAMES are read from the config files. Commands, args, env, headers and URLs
are never returned or printed: they can carry tokens.
"""
import json
import os
import socket

TCP_TIMEOUT = 0.3


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def _user_json():
    d = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(d, ".claude.json") if d else os.path.join(os.path.expanduser("~"), ".claude.json")


def mcp_servers(ws, reg):
    """{server name: [where configured]} - names only."""
    found = {}

    def note(names, where):
        for n in names or []:
            found.setdefault(n, []).append(where)

    dirs = [ws] + [os.path.join(ws, r["path"]) for r in reg.get("repos", {}).values()]
    for d in dirs:
        data = _load(os.path.join(d, ".mcp.json")) or {}
        if isinstance(data.get("mcpServers"), dict):
            note(list(data["mcpServers"]), os.path.relpath(os.path.join(d, ".mcp.json"), ws))
    user = _load(_user_json()) or {}
    if isinstance(user.get("mcpServers"), dict):
        note(list(user["mcpServers"]), "~/.claude.json")
    projects = user.get("projects") if isinstance(user.get("projects"), dict) else {}
    for d in dirs:
        p = projects.get(d) or {}
        if isinstance(p.get("mcpServers"), dict):
            note(list(p["mcpServers"]), f"~/.claude.json project {os.path.relpath(d, ws)}")
    return found


def enabled_plugins(ws):
    """Set of enabled plugin names (without @marketplace)."""
    names = set()
    for path in (os.path.join(_config_dir(), "settings.json"),
                 os.path.join(ws, ".claude", "settings.json"),
                 os.path.join(ws, ".claude", "settings.local.json")):
        ep = (_load(path) or {}).get("enabledPlugins")
        if isinstance(ep, dict):
            for k, v in ep.items():
                (names.add if v else names.discard)(k.split("@", 1)[0])
    return names


def which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def tcp_reachable(probe):
    """probe = tcp://host:port"""
    try:
        host, port = probe[len("tcp://"):].rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=TCP_TIMEOUT):
            return True
    except (OSError, ValueError):
        return False


def probe_services(reg):
    return {sid: {"probe": s["probe"], "reachable": tcp_reachable(s["probe"])}
            for sid, s in (reg.get("services") or {}).items()}


class Prober:
    def __init__(self, ws, reg, services=None):
        self.ws, self.reg = ws, reg
        self._mcp = self._plugins = None
        self.services = services

    def _one(self, p):
        """(ok, detail) for one probe alternative."""
        kind, _, name = p.partition(":")
        if kind == "bin":
            return (True, name) if which(name) else (False, f"{name} not on PATH")
        if kind == "tool":
            t = (self.reg.get("tools") or {}).get(name) or {}
            return (True, name) if any(which(c) for c in t.get("candidates", [])) else (False, f"{name} not on PATH")
        if kind == "service":
            if self.services is None:
                self.services = probe_services(self.reg)
            up = bool((self.services.get(name) or {}).get("reachable"))
            return up, f"{name} {'reachable' if up else 'not reachable'}"
        if kind == "mcp":
            if self._mcp is None:
                self._mcp = mcp_servers(self.ws, self.reg)
            where = self._mcp.get(name)
            return (True, f"mcp {name} ({', '.join(where[:2])})") if where else (False, f"mcp {name} not configured")
        if kind == "plugin":
            if self._plugins is None:
                self._plugins = enabled_plugins(self.ws)
            return (True, f"plugin {name}") if name in self._plugins else (False, f"plugin {name} not enabled")
        return False, f"unknown probe {p}"

    def tool(self, t):
        """{id, ok, state, detail[]}; state OK | DOWN (only a service probe failed) | MISSING."""
        detail, failed_kinds = [], set()
        for probe in t.get("probes", []):
            res = [self._one(a) for a in probe.split("|")]
            hit = next((r for r in res if r[0]), None)
            if hit:
                detail.append(hit[1])
            else:
                failed_kinds |= {a.partition(":")[0] for a in probe.split("|")}
                detail.append(" / ".join(r[1] for r in res))
        state = "OK" if not failed_kinds else ("DOWN" if failed_kinds == {"service"} else "MISSING")
        return {"id": t["id"], "ok": state == "OK", "state": state, "detail": detail}

    def for_skills(self, skills):
        skills = set(skills)
        return [dict(self.tool(t), required=bool(t.get("required")), fallback=t.get("fallback"))
                for t in self.reg.get("dev_tools", []) if skills & set(t.get("used_by", []))]
