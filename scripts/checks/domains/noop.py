"""No-op sample plugin, used by core contract tests."""


def check(artifact, ctx):
    # The explicit result makes the plugin contract visible in machine output.
    return [{"check": "plugin-example", "state": "PASS", "reasons": []}]
