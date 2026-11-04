"""Plugin paths shared by Claude and Codex; no runtime environment is required."""
import os


def plugin_root():
    return (os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("PLUGIN_ROOT")
            or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def is_codex():
    """Inside a Codex session (hook or shell command), never inside Claude Code. CODEX_HOME is configuration, not a
    runtime marker: a Claude session may inherit it. Codex hooks also export a compatibility CLAUDE_PLUGIN_ROOT, so
    that variable does not mean Claude either; CLAUDECODE (set by Claude Code for its tools and hooks) does."""
    if os.environ.get("CLAUDECODE"):
        return False
    return bool(os.environ.get("CODEX_THREAD_ID") or os.environ.get("PLUGIN_ROOT"))
