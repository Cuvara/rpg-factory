"""Read only Codex configuration and installed cache names; never expose values."""
import functools
import os
import re
try:
    from .pluginroot import is_codex
except ImportError:
    from pluginroot import is_codex


def home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def config():
    try:
        import tomllib
        with open(os.path.join(home(), "config.toml"), "rb") as fh:
            data = tomllib.load(fh)
            return data if isinstance(data, dict) else {}
    except (ImportError, OSError, ValueError):
        return {}


def enabled_plugins():
    if not is_codex():
        return set()
    plugins = config().get("plugins", {})
    if not isinstance(plugins, dict):
        return set()
    return {k.split("@", 1)[0] for k, v in plugins.items()
            if isinstance(v, dict) and v.get("enabled", False)}


def mcp_servers():
    if not is_codex():
        return set()
    servers = config().get("mcp_servers", {})
    return set(servers) if isinstance(servers, dict) else set()


def active_root():
    """Match Codex 0.164 core-plugin-common/installed.rs version selection."""
    base = os.path.join(home(), "plugins", "cache", "rpg-factory", "rpg-factory")
    try:
        versions = [v for v in os.listdir(base) if re.fullmatch(r"[A-Za-z0-9.+_-]+", v)
                    and v not in {".", ".."} and os.path.isdir(os.path.join(base, v))]
    except OSError:
        return None

    def key(v):
        m = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?", v)
        if not m:
            return None
        pre = m[4]
        ids = pre.split(".") if pre else []
        if any(not x or (x.isdigit() and len(x) > 1 and x[0] == "0") for x in ids):
            return None
        return (tuple(map(int, m.group(1, 2, 3))), not pre,
                tuple((0, int(x)) if x.isdigit() else (1, x) for x in ids), m[5] or "")

    def compare(a, b):
        ka, kb = key(a), key(b)
        a, b = (ka, kb) if ka is not None and kb is not None else (a, b)
        return (a > b) - (a < b)

    version = "local" if "local" in versions else max(versions, key=functools.cmp_to_key(compare), default=None)
    return os.path.join(base, version) if version else None
