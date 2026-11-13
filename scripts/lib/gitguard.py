"""rpg-factory git guard (v2) - PreToolUse hook for the Bash and PowerShell tools.

Reads the hook payload on stdin. For commands that run inside the RPG MMO workspace (or in a linked worktree
outside it whose main checkout is in the workspace, e.g. an Orca worktree: that checkout's rules apply) it
expands the command into the programs that will actually run, peeling wrappers and
recursing into nested shells, then classifies every git / gh invocation. Advisory only (1.0.3): the
hook never asks the user and never blocks; a match is returned as additionalContext
"rpg-factory advisory (<level>): ..." for the agent to weigh. Internally a finding is a
("deny", reason) or ("ask", reason) tuple; "deny" is reported as advisory level high and "ask" as
level warn - neither is a permission decision:

  - high    creating, deleting or pushing tags (git tag, push --tags / tag refs, update-ref
            on tags, gh api .../git/refs|tags, gh release create) - release actions, only with explicit release authorization in the current task
  - warn    destructive or high-impact git (reset --hard, clean -f, checkout -- / -B,
            restore, stash, branch -D/-f, update-ref, gc --prune, reflog expire, rebase,
            filter-branch, any push, add -A, commit -a/--amend, commit/merge/cherry-pick/
            revert/am/pull --rebase/reset <commit> on a protected branch, submodule update,
            git -c alias.*), commands whose git use cannot be seen (interpreters with inline
            code or a heredoc, $VAR / $(...) as the program, encoded PowerShell), registry
            human_gates[].match, and non-English message text (rule english-only, lib/rpgf_guard/language.py:
            git commit -m/--message, gh pr|issue create/edit/comment text, orca orchestration send, orca agent
            launch --prompt, and the prompt of the Agent tool)
Wrappers peeled: VAR=x, env, command, builtin, exec, sudo, doas, timeout, nohup, nice, time,
stdbuf, ionice, setsid, xargs, find -exec/-execdir, and leading shell reserved words ({ ! if then
else elif do while until, `name()` / `function name` headers; PowerShell script-block braces).
Nested: bash|sh|zsh|dash -c, a heredoc fed to a shell (`bash <<EOF`, `cat <<EOF | sh`), eval,
cmd(.exe) /c|/k, powershell|pwsh -c|-Command, PowerShell `&` call operator. On Windows, git-bash
paths (/c/..., /mnt/c/...) are mapped to drive paths before they are resolved.

Git run by a script file or a program is invisible to text analysis (documented limitation).
A declared Factory execution mode (scripts/factory_session.py) flags state changes in analyze/plan/review.

Never approves or denies: no output + exit 0 = "no opinion", advisory output = still no decision. Any
internal error = no opinion; each
part (git analysis, human gates, mode) fails independently. RPG_FACTORY_GUARD=off disables it.
"""
import io
import json
import os
import re
import shlex
import subprocess
import sys


def _load_guard_package():
    """Load scripts/lib/rpgf_guard/ as the package `rpgf_guard`, by path and once. The directory carries the package
    name, so nothing called `guard` is importable from scripts/lib (a generic name that shadows, or is shadowed by,
    any other module called `guard`). Its relative imports stay."""
    import importlib.util
    name = "rpgf_guard"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        spec = importlib.util.spec_from_file_location(name, os.path.join(path, "__init__.py"),
                                                      submodule_search_locations=[path])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


_load_guard_package()

# Compatibility facade: retain every name the original hook module exported.
from rpgf_guard.common import (
    DEFAULT_PROTECTED,
    TAG_REF,
    SEPARATORS,
    GLOBAL_OPTS_WITH_VALUE,
    SHELLS,
    POWERSHELLS,
    CMDS,
    INTERPRETERS,
    CD_WORDS,
    MUTATING_GIT_WORDS,
    GIT_BUILTINS,
    MAX_DEPTH,
    MAX_COMMAND,
    STATELESS_READ_GIT,
    RESERVED_LEAD,
    LIB,
    SCRIPTS,
    plugin_root,
    find_workspace,
    git_out,
    linked_worktree,
    main_checkout,
    native_path,
    PLUGIN_ROOT,
    load_registry,
    within,
    outside_workspace,
    protected_patterns,
    is_protected,
)
from rpgf_guard.shell import (
    HEREDOC,
    logical_lines,
    _stdin_reader,
    heredoc_reader,
    tokenize,
    segments,
    prog,
    peel,
    expand,
)
from rpgf_guard.git import (
    parse_git,
    has_short_flag,
    refspec_dsts,
    TAG_LIST_MODES,
    TAG_RO,
    SORT_KEY,
    tag_listing,
    classify,
    GH_READ,
    GH_READ_GROUPS,
    GH_FIELD_FLAGS,
    TAGGISH,
    gh_api_request,
    GH_GLOBAL_VALUE,
    gh_normalise,
    classify_gh,
    names_registry_repo,
    stateless,
    new_branch_from,
    evaluate,
)
from rpgf_guard.process import (
    PROCESS_TERMINATION_RULE,
    PROCESS_KILL_FALLBACK,
    PROCESS_PREFILTER,
    TERMINATORS,
    CIM_QUERIES,
    GREP_LIKE,
    START_PROCESS,
    IMAGE_SELECTOR,
    PS_NAME_PARAM,
    WMIC_PID_WHERE,
    _substitutions,
    _process_argvs,
    _clean,
    process_findings,
    process_kill_hits,
)
from rpgf_guard.language import (
    AGENT_TOOLS,
    GH_TEXT,
    option_values,
    targets,
    finding,
    in_scope,
    language_hits,
    agent_prompt_hits,
)
from rpgf_guard.gates import (
    human_gate_hits,
    skill_read_hits,
)
from rpgf_guard.mode import (
    _needs_mode,
    MODE_SCRIPTS,
    mode_runner,
    mode_hits,
)
from rpgf_guard.runtime import (
    main,
    agent_main,
    collect,
    advisory,
    run,
)
