"""Plugin root lookup and registry.json loading shared by the pin checks. Stdlib only.

Unlike pluginroot.py this honours only CLAUDE_PLUGIN_ROOT (not PLUGIN_ROOT).
"""
import json
import os


def plugin_root():
    """CLAUDE_PLUGIN_ROOT when set and non-empty, else the plugin checkout root (three directories up)."""
    return os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_registry(root=None):
    """Parsed registry.json under root (default plugin_root()); OSError and JSON errors propagate."""
    with open(os.path.join(root or plugin_root(), "registry.json"), encoding="utf-8") as f:
        return json.load(f)
