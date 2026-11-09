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
  plugin-file:<p>  the file <p> (relative to this plugin's root) exists, e.g. a bundled tool's entry script
  codex:subagents  Codex in-session subagents (`codex` is the kind, `subagents` the name): `codex features list`
                   says multi_agent is on, and the subagent model keys of the Codex config are inside registry
                   pipeline.models.scope.codex. WARN (not DOWN) when not; see codex_subagents

The config files are parsed in memory (JSON has to be parsed whole), but only server and plugin NAMES
leave this module. Commands, args, env, headers and URLs are never returned, printed, logged or stored:
they can carry tokens. A file that does not parse is treated as absent, with no error text (an error
message could quote its content). The Codex config holds secrets: the codex:subagents probe reads only
agents.default_subagent_model and agents.subagent.model, and shows a value only when it looks like a model id.
"""
import json
import os
import re
import shutil
import socket
import subprocess

TCP_TIMEOUT = 0.3
CODEX_FEATURES_TIMEOUT = 15
MODEL_ID = re.compile(r"[A-Za-z0-9._:/-]{1,64}")
NOT_A_MODEL_ID = "a value that is not a model id (not shown)"
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def _path_key(p):
    """Comparable form of a directory path: separators and (on Windows) case normalised."""
    return os.path.normcase(os.path.normpath(p)) if isinstance(p, str) else p


def mcp_servers(ws, reg):
    """{server name: [where configured]} - names only."""
    found = {}
    import codexconfig
    for name in codexconfig.mcp_servers():
        found[name] = ["Codex config"]

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
    # Claude Code keys projects by path as it saw it (on Windows `C:/x/y`, while `d` here is `C:\x\y`)
    projects = {_path_key(k): v for k, v in projects.items()}
    for d in dirs:
        p = projects.get(_path_key(d)) or {}
        if isinstance(p.get("mcpServers"), dict):
            note(list(p["mcpServers"]), f"~/.claude.json project {os.path.relpath(d, ws)}")
    return found


def enabled_plugins(ws):
    """Set of enabled plugin names (without @marketplace)."""
    import codexconfig
    names = codexconfig.enabled_plugins()
    for path in (os.path.join(_config_dir(), "settings.json"),
                 os.path.join(ws, ".claude", "settings.json"),
                 os.path.join(ws, ".claude", "settings.local.json")):
        ep = (_load(path) or {}).get("enabledPlugins")
        if isinstance(ep, dict):
            for k, v in ep.items():
                (names.add if v else names.discard)(k.split("@", 1)[0])
    return names


def which(name):
    """Like shutil.which without its extra stats; on Windows also name + each PATHEXT extension."""
    names = [name]
    if os.name == "nt" and not os.path.splitext(name)[1]:
        names += [name + e.lower() for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for n in names:
            p = os.path.join(d, n)
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


def _codex_multi_agent():
    """'on' | 'off' | None (unknown) from `codex features list`; its output never leaves this function."""
    exe = shutil.which("codex")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "features", "list"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=CODEX_FEATURES_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        f = line.split()
        if len(f) >= 2 and f[0] == "multi_agent" and f[-1] in ("true", "false"):
            return "on" if f[-1] == "true" else "off"
    return None


def _codex_subagent_models():
    """[(key, value)] of the two subagent model keys that are set; nothing else of the Codex config is returned."""
    import codexconfig
    cfg = codexconfig.config()
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    if not isinstance(agents, dict):
        return []
    sub = agents.get("subagent")
    found = []
    if "default_subagent_model" in agents:
        found.append(("agents.default_subagent_model", agents["default_subagent_model"]))
    if isinstance(sub, dict) and "model" in sub:
        found.append(("agents.subagent.model", sub["model"]))
    return found


def codex_subagents(reg):
    """(ok, detail, warn) of the codex:subagents probe. Read-only; only the two model keys of the config are read."""
    if not shutil.which("codex"):
        return False, "codex not on PATH", False
    pipe = (reg or {}).get("pipeline") or {}
    scope = ((pipe.get("models") or {}).get("scope") or {}).get("codex") or {}
    wanted = (((pipe.get("subagents") or {}).get("models") or {}).get("codex") or {}).get("model")
    if not isinstance(wanted, str):
        wanted = "<the pipeline.subagents codex model>"
    cfg_path = ("CODEX_HOME" if os.environ.get("CODEX_HOME") else "~/.codex") + "/config.toml"
    fix = f'; fix: [agents] default_subagent_model = "{wanted}" in {cfg_path}'
    warns, good = [], []
    multi = _codex_multi_agent()
    if multi is None:
        warns.append("multi_agent unknown (codex features list failed)")
    elif multi == "off":
        warns.append("multi_agent off; fix: codex features enable multi_agent (or [features] multi_agent = true in the Codex config)")
    models = _codex_subagent_models()
    for key, value in models:
        shown = value if isinstance(value, str) and MODEL_ID.fullmatch(value) else NOT_A_MODEL_ID
        if shown in scope:
            good.append(f"{key} = {shown}")
        else:
            warns.append(f"{key} = {shown} is outside pipeline.models.scope.codex{fix}")
    if not models:
        warns.append(f"no Codex subagent model set (subagents inherit the session model){fix}")
    if warns:
        return True, " / ".join(warns), True
    return True, f"codex subagents: multi_agent on, {', '.join(good)}", False


def probe_services(reg):
    return {sid: {"probe": s["probe"], "reachable": tcp_reachable(s["probe"])}
            for sid, s in (reg.get("services") or {}).items()}


class Prober:
    def __init__(self, ws, reg, services=None):
        self.ws, self.reg = ws, reg
        self._mcp = self._plugins = None
        self.services = services

    def _one(self, p):
        """(ok, detail) for one probe alternative; (ok, detail, True) when it passed with a warning."""
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
        if kind == "plugin-file":
            return (True, name) if os.path.isfile(os.path.join(PLUGIN_ROOT, name)) else (False, f"{name} not in the plugin")
        if kind == "codex" and name == "subagents":
            return codex_subagents(self.reg)
        return False, f"unknown probe {p}"

    def tool(self, t):
        """{id, ok, state, detail[]}; state OK | WARN (no probe failed, one warned) | DOWN (only a service probe
        failed) | MISSING."""
        detail, failed_kinds, warned = [], set(), False
        for probe in t.get("probes", []):
            res = [self._one(a) for a in probe.split("|")]
            hit = next((r for r in res if r[0]), None)
            if hit:
                detail.append(hit[1])
                warned = warned or (len(hit) > 2 and bool(hit[2]))
            else:
                failed_kinds |= {a.partition(":")[0] for a in probe.split("|")}
                detail.append(" / ".join(r[1] for r in res))
        state = ("WARN" if warned else "OK") if not failed_kinds else ("DOWN" if failed_kinds == {"service"} else "MISSING")
        return {"id": t["id"], "ok": state == "OK", "state": state, "detail": detail}

    def for_skills(self, skills):
        skills = set(skills)
        return [dict(self.tool(t), required=bool(t.get("required")), fallback=t.get("fallback"))
                for t in self.reg.get("dev_tools", []) if skills & set(t.get("used_by", []))]
