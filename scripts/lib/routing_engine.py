"""The routing engine call: scripts/lib/resolve.jq run through jq (used by the context engine).

Nothing path-sized goes through argv (Windows limit: 32767 characters): stdin binds the inputs, the registry
is a file and the program text is the only large argument.
"""
import functools
import json
import os
import subprocess

from pluginroot import plugin_root
from snapshot_render import die

RESOLVE = os.path.join(plugin_root(), "scripts", "lib", "resolve.jq")


@functools.lru_cache(maxsize=None)
def _resolve_program():
    with open(RESOLVE, encoding="utf-8") as fh:
        return ". as {files: $files, subst: $subst, tools: $tools} | $__reg[0] | " + fh.read()


def resolve(registry, key, files, subst, tools):
    """Route `files` of repo `key` against the registry file at path `registry`; die() when jq fails."""
    r = subprocess.run(["jq", "-c", "--arg", "repo", key, "--slurpfile", "__reg", registry, _resolve_program()],
                       input=json.dumps({"files": files, "subst": subst, "tools": tools}),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die(f"routing engine failed: {r.stderr.strip()}")
    return json.loads(r.stdout)
