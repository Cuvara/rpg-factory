"""Registry human gates and registered skill file advisories."""
import os
import re
import sys

from .common import SCRIPTS, find_workspace, native_path
from .git import gh_normalise
from .process import _process_argvs
from .shell import expand, prog, segments, tokenize

def human_gate_hits(payload, registry):
    """Registry human_gates with a `match` regex, applied to every expanded command inside the workspace."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    tool = payload.get("tool_name") or "Bash"
    cwd = payload.get("cwd") or os.getcwd()
    if not find_workspace(cwd, registry) and not any(find_workspace(native_path(os.path.expanduser(t)), registry)
                                                     for t in re.findall(r"((?:\b[A-Za-z]:[/\\]|/)[^\s'\"]+)", command)):
        return []
    shell = "powershell" if tool == "PowerShell" else "bash"
    texts = {" ".join(seg) for seg in segments(tokenize(command))}
    for argv in expand(command, shell=shell):
        texts.add(" ".join(argv))
        if prog(argv[0]) in {"gh", "gh.exe"}:  # `gh --repo o/r pr merge 1` is seen as `gh pr merge 1`
            texts.add(" ".join(["gh"] + gh_normalise(argv)[1:]))
    hits = []
    read_only = []  # computed once, only when a read_only_exempt gate matched
    for text in texts:
        for g in registry.get("human_gates", []):
            m = g.get("match")
            if not m or tool not in g.get("tools", ["Bash", "PowerShell"]):
                continue
            try:
                matched = re.search(m, text)
            except re.error:  # one bad registry regex must not disable the rest of the guard
                continue
            if matched and g.get("read_only_exempt"):
                if not read_only:
                    try:
                        sys.path.append(SCRIPTS)  # appended: stdlib first
                        import factory_session as session  # noqa: E402
                        session._REGISTRY = session._REGISTRY or registry
                        read_only.append(session.is_read_only(payload))
                    except Exception:
                        read_only.append(False)  # cannot tell: the gate applies
                if read_only[0]:
                    continue  # `sed -n 1,40p run-clients.sh`: inspecting the script does not run it
            if matched:
                hits.append((g.get("decision", "ask"), f"human gate '{g['id']}': {g['rule']}"))
    return hits


def skill_read_hits(payload, registry):
    """A registered skill's SKILL.md read through the shell (`cat`, `sed -n`, `Get-Content`, ...) is not a loaded
    skill: point the session at the Skill tool. Parsed argv only; a command that cannot be parsed gets no opinion."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "skill.md" not in command.lower():
        return []
    import factory_session as session  # noqa: E402
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    names = []
    for argv in _process_argvs(command, shell):
        if argv and prog(argv[0]) in session.SKILL_READERS:
            for a in argv[1:]:
                m = session.SKILL_FILE.search(a)
                if m and a.replace("\\", "/").rstrip("'\"").endswith("/SKILL.md"):
                    names.append(m.group(1))
    hint = session.skill_read_hint(names, registry)
    return [hint] if hint else []
