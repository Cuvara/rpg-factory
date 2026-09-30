#!/usr/bin/env python3
"""Entry point behind the rpg-factory slash commands. Validates arguments, then runs the real script.

  status [--remote]                       factory-status.py: pending cross-repo work, evidence, freshness
  route <repo> <path>... [--lead SKILL]   factory-context.sh --explain: lead / co-leads / legs / follow-ups,
                                          contracts, checks and gates for those files, and why
  check <repo> [<path>...] [--status]     run-checks.py (fast tier) - or --status: grade stored evidence
                                          against the current tree without running anything
  doctor                                  install state, tripwire latches, registry, state paths, tools

Read-only except `check` without --status, which runs the fast checks (builds/tests) exactly like
run-checks.py. Exit code = the underlying script's; 2 = usage error.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))


def usage(msg=None):
    if msg:
        print(f"factory-cmd: {msg}\n", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


def registry():
    return json.load(open(os.path.join(ROOT, "registry.json"), encoding="utf-8"))


def run(argv):
    sys.stdout.flush()
    return subprocess.run(argv, env={**os.environ, "CLAUDE_PLUGIN_ROOT": ROOT}).returncode


def split_args(args):
    """Accept `a b`, `a,b` and a single quoted "a b" argument (slash commands pass one string)."""
    out = []
    for a in args:
        for part in a.replace(",", " ").split():
            out.append(part)
    return out


def repo_and_paths(args, verb):
    reg = registry()
    if not args:
        raise ValueError(f"{verb} needs a repo: {' | '.join(reg['repos'])}")
    if args[0] not in reg["repos"]:
        raise ValueError(f"unknown repo '{args[0]}'; repos: {' | '.join(reg['repos'])}")
    return args[0], args[1:]


def cmd_status(args):
    extra = [a for a in args if a == "--remote"]
    if [a for a in args if a != "--remote"]:
        raise ValueError("status takes only --remote")
    return run([sys.executable, "-B", os.path.join(ROOT, "scripts", "factory-status.py"), *extra])


def cmd_route(args):
    lead = None
    if "--lead" in args:
        i = args.index("--lead")
        if i + 1 >= len(args):
            raise ValueError("--lead needs a skill name")
        lead, args = args[i + 1], args[:i] + args[i + 2:]
    repo, paths = repo_and_paths(args, "route")
    if not paths:
        raise ValueError("route needs at least one repo-relative path (the files the task will write)")
    argv = ["bash", os.path.join(ROOT, "scripts", "factory-context.sh"), "--repo", repo, "--explain"]
    if lead:
        argv += ["--lead", lead]
    return run(argv + ["--paths", *paths])


def cmd_check(args):
    status = "--status" in args
    args = [a for a in args if a != "--status"]
    repo, paths = repo_and_paths(args, "check")
    argv = [sys.executable, "-B", os.path.join(ROOT, "scripts", "run-checks.py"), "--repo", repo]
    if status:
        argv.append("--status")
    if paths:
        argv += ["--paths", *paths]
    return run(argv)


def cmd_doctor(args):
    if args:
        raise ValueError("doctor takes no arguments")
    import fstate
    reg = registry()
    rc = 0
    print("## Install")
    rc |= run([sys.executable, "-B", os.path.join(ROOT, "scripts", "install-status.py")])
    print("\n## Tripwire latches (clear only after reviewing the repos: `! python3 "
          + os.path.join(ROOT, "scripts", "tripwire.py") + " --ack`)")
    run([sys.executable, "-B", os.path.join(ROOT, "scripts", "tripwire.py"), "--status"])
    print("\n## Registry")
    rc |= run(["bash", os.path.join(ROOT, "scripts", "check-registry.sh"), "--structure-only"])
    print("\n## Workspace and state")
    ws = os.environ.get(reg["workspace"]["root_env"]) or reg["workspace"]["root_default"]
    ok_ws = all(os.path.exists(os.path.join(ws, m)) for m in reg["workspace"]["root_markers"])
    print(f"- workspace {ws}: {'OK' if ok_ws else 'MARKERS MISSING'}")
    for k, r in reg["repos"].items():
        p = os.path.join(ws, r["path"])
        print(f"- repo {k}: {'present' if os.path.isdir(os.path.join(p, '.git')) else 'absent'} ({p})")
    print(f"- scratch state: {fstate.scratch()}  (TMPDIR={os.environ.get('TMPDIR', '<unset>')!r})")
    print(f"- persistent state: {fstate.persistent()}")
    missing = [t for t in ("git", "jq", "python3", "bash") if not shutil.which(t)]
    print(f"- tools: {'all present' if not missing else 'MISSING ' + ', '.join(missing)}")
    hooks = json.load(open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8"))["hooks"]
    print("- hooks: " + "; ".join(f"{e} [{', '.join(h.get('matcher') or '*' for h in v)}]" for e, v in hooks.items()))
    if missing or not ok_ws:
        rc |= 1
    return rc


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        return usage()
    verb, args = argv[0], split_args(argv[1:])
    fn = {"status": cmd_status, "route": cmd_route, "check": cmd_check, "doctor": cmd_doctor}.get(verb)
    if not fn:
        return usage(f"unknown command '{verb}'")
    try:
        return fn(args)
    except ValueError as e:
        return usage(str(e))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
