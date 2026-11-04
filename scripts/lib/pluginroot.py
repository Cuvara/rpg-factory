"""Plugin paths shared by Claude and Codex; no runtime environment is required."""
import os


def plugin_root():
    return (os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("PLUGIN_ROOT")
            or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def is_codex():
    return bool(os.environ.get("CODEX_HOME") or os.environ.get("PLUGIN_ROOT")
                or (os.environ.get("CODEX_THREAD_ID") and not os.environ.get("CLAUDE_PLUGIN_ROOT")))
