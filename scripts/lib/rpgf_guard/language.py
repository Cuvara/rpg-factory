"""English-only advisories for the text the git guard can see: commit messages, gh PR and issue text, orca session
messages and launch prompts, and the prompt of the Agent tool. Advisory only (level warn, rule `english-only`); the
detection is lib/english.py, shared with scripts/checks/english-only.py and scripts/file-guard.py.

Fast path: pure ASCII text returns before any parsing. A command that cannot be parsed, or that lies outside the
workspace, gets no opinion.
"""
import os
import re

from .common import PLUGIN_ROOT, find_workspace, native_path, outside_workspace, within
from .git import gh_normalise, parse_git
from .shell import expand, prog

import english  # noqa: E402  (scripts/lib is on sys.path: common.py appends it)

MAX_HITS = 3
EXCERPT = 80
GH_TEXT = {("pr", "create"), ("pr", "edit"), ("pr", "comment"), ("issue", "create"), ("issue", "edit"),
           ("issue", "comment")}
EXECUTABLE_SUFFIX = re.compile(r"\.(exe|cmd|bat|ps1)$")
AGENT_TOOLS = {"Agent", "Task"}


def option_values(args, long_names, short_letters):
    """Values of `--name VALUE`, `--name=VALUE`, `-x VALUE`, `-xVALUE` and a short-flag cluster that ends in the
    letter (`-am VALUE`). Stops at `--`. Anything else is skipped."""
    out, i = [], 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--":
            break
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in long_names:
                if eq:
                    out.append(value)
                elif i < len(args):
                    out.append(args[i])
                    i += 1
        elif arg.startswith("-") and len(arg) > 1:
            body = arg[1:]
            for k, char in enumerate(body):
                if char in short_letters:
                    rest = body[k + 1:]
                    if rest:
                        out.append(rest)
                    elif i < len(args):
                        out.append(args[i])
                        i += 1
                    break
    return out


def targets(argv):
    """(label, text) of every message text this argv writes, for the commands the policy covers."""
    if not argv:
        return []
    name = EXECUTABLE_SUFFIX.sub("", prog(argv[0]))
    if name == "git":
        parsed = parse_git(argv)
        if parsed and parsed[1] == "commit":
            return [("git commit message", t) for t in option_values(parsed[2], {"--message"}, {"m"})]
    elif name == "gh":
        words = gh_normalise(argv)
        if len(words) > 2 and (words[1], words[2]) in GH_TEXT:
            label = f"gh {words[1]} {words[2]} text"
            return [(label, t) for t in option_values(words[3:], {"--title", "--body"}, {"t", "b"})]
    elif name == "orca":
        positional = [a for a in argv[1:] if not a.startswith("-")][:2]
        if positional == ["orchestration", "send"]:
            return [("orca orchestration send text", t) for t in option_values(argv[1:], {"--subject", "--body"}, set())]
        if positional == ["agent", "launch"]:
            return [("orca agent launch prompt", t) for t in option_values(argv[1:], {"--prompt"}, set())]
    return []


def finding(label, text):
    """The advisory reason for one text, or None when it is English."""
    found = english.first_offending_line(text)
    if not found:
        return None
    number, line = found
    line = " ".join(line.split())
    if len(line) > EXCERPT:
        line = line[:EXCERPT] + "..."
    return ("ask", f"english-only: the {label} is not English (line {number}: \"{line}\"); everything written is English, "
                   "only the report to the owner uses the report language")


def in_scope(cwd, registry, command=""):
    """The command runs in the workspace, in a worktree whose main checkout is in it, or in the plugin checkout."""
    cwd = cwd or os.getcwd()
    if find_workspace(cwd, registry) or within(cwd, PLUGIN_ROOT):
        return True
    if outside_workspace(os.path.abspath(cwd), registry, {}):
        return True
    return bool(command) and any(find_workspace(native_path(os.path.expanduser(t)), registry)
                                 for t in re.findall(r"((?:\b[A-Za-z]:[/\\]|/)[^\s'\"]+)", command))


def language_hits(payload, registry):
    """Bash and PowerShell commands: git commit, gh pr/issue, orca send/launch text that is not English."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if command.isascii() or not in_scope(payload.get("cwd"), registry, command):
        return []
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    hits, flagged = [], set()
    for argv in expand(command, shell=shell):
        for label, text in targets(argv):
            hit = finding(label, text) if label not in flagged else None  # one finding per kind of text
            if hit:
                flagged.add(label)
                hits.append(hit)
        if len(hits) >= MAX_HITS:
            break
    return hits[:MAX_HITS]


def agent_prompt_hits(payload, registry):
    """The Agent tool: a prompt for a subagent is a brief, so it is English."""
    prompt = (payload.get("tool_input") or {}).get("prompt")
    if not isinstance(prompt, str) or prompt.isascii() or not in_scope(payload.get("cwd"), registry):
        return []
    hit = finding("Agent tool prompt", prompt)
    return [hit] if hit else []
