#!/usr/bin/env python3
"""CI plan: which run-all suites a change must run in CI, and on which OS.

  ci-plan.py [--base REF] [--event KIND] [--full] [--changed-file FILE] [--summary FILE] [--github-output FILE]

  --base REF           the commit the change is measured from (a PR base sha, a push 'before')
  --event KIND         the GitHub event name, echoed into the plan; 'schedule' always plans every suite
  --full               plan every suite
  --changed-file FILE  the changed paths, one per line (stand-in for `tests/affected.py changed BASE`; tests use it)
  --summary FILE       append a markdown table of run versus skipped suites (the job summary)
  --github-output FILE append matrix=<compact JSON>, count=, full=, changed= (the GITHUB_OUTPUT file)

Prints one JSON object on stdout: full, reason, event, base, changed_files, matrix {include: [{suite, cases, os}]},
suites [{suite, cases, os: [...]}] and skipped [{suite, reason}]. Every runnable suite is in exactly one of
suites / skipped. Exit 0 on a plan (a full plan included), 2 when no plan can be made (cannot list the suites, a
tests/ci-windows-suites.txt line is not a runnable suite).

The runnable suites are the lines of `tests/run-all.sh --list-suites --no-workspace --no-claude`. The selection is
`tests/affected.py cases`, called once; this file never selects by itself. Anything unsure plans every suite (cases ALL):
--full, a schedule event, no base and no --changed-file, a base that is all zeros or not a commit, an affected.py error, a
changed CI-plumbing file (.github/workflows/**, .github/actions/**, tests/run-all.sh, tests/affected.py, this file,
tests/ci-windows-suites.txt) and an affected.py answer that already selects every suite with ALL.

A suite runs on ubuntu-24.04, plus windows-2025 when tests/ci-windows-suites.txt names it (one suite path per line,
'#' comments). Read-only: it writes only the files named by --summary and --github-output.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from shells import find_bash  # noqa: E402  (a bare "bash" resolves to the WSL launcher on Windows)

LINUX = "ubuntu-24.04"
WINDOWS = "windows-2025"
WINDOWS_LIST = "tests/ci-windows-suites.txt"
FULL_PREFIXES = (".github/workflows/", ".github/actions/")
FULL_FILES = ("tests/run-all.sh", "tests/affected.py", "scripts/ci-plan.py", WINDOWS_LIST)
ZERO_SHA = re.compile(r"^0+$")


def fail(message):
    print("ci-plan: " + message, file=sys.stderr)
    sys.exit(2)


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def text(raw):
    return raw.decode("utf-8", errors="replace")


def runnable_suites():
    bash = find_bash()
    if not bash:
        fail("no bash found to list the suites")
    result = run([bash, "tests/run-all.sh", "--list-suites", "--no-workspace", "--no-claude"])
    if result.returncode != 0:
        fail("tests/run-all.sh --list-suites failed (exit %d): %s" % (result.returncode, text(result.stderr).strip()[:300]))
    suites = [line.strip() for line in text(result.stdout).splitlines() if line.strip()]
    if not suites:
        fail("tests/run-all.sh --list-suites printed no suite")
    return list(dict.fromkeys(suites))


def windows_suites(suites):
    path = os.path.join(ROOT, WINDOWS_LIST)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as error:
        fail("cannot read %s: %s" % (WINDOWS_LIST, error))
    named = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if line:
            named.append(line)
    unknown = [name for name in named if name not in suites]
    if unknown:
        fail("%s names no runnable suite: %s" % (WINDOWS_LIST, ", ".join(unknown)))
    return set(named)


def usable_base(base):
    if ZERO_SHA.match(base):
        return False
    return run(["git", "rev-parse", "--verify", "--quiet", base + "^{commit}"]).returncode == 0


def read_changed(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [line.strip() for line in fh if line.strip()]
    except OSError as error:
        fail("cannot read --changed-file %s: %s" % (path, error))


def git_changed(base):
    result = run([sys.executable, "-B", "tests/affected.py", "changed", base])
    if result.returncode != 0:
        return None
    return [line.strip() for line in text(result.stdout).splitlines() if line.strip()]


def normal(path):
    path = path.replace("\\", "/")
    return path[2:] if path.startswith("./") else path


def forces_full(files):
    for path in map(normal, files):
        if path.startswith(FULL_PREFIXES) or path in FULL_FILES:
            return path
    return None


def affected_cases(files, suites):
    """{suite: cases} from one `tests/affected.py cases` call, or None when affected.py fails."""
    handle, tmp = tempfile.mkstemp(prefix="ci-plan-", suffix=".txt")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(path + "\n" for path in files))
        result = run([sys.executable, "-B", "tests/affected.py", "cases", tmp] + suites)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if result.returncode != 0:
        return None
    picked = {}
    for line in text(result.stdout).splitlines():
        suite, _, cases = line.partition("\t")
        if suite in suites:
            picked[suite] = cases.strip() or "ALL"
    return picked


def plan(args):
    suites = runnable_suites()
    on_windows = windows_suites(suites)
    base = args["base"]
    full, reason = False, ""
    files = []

    if args["full"]:
        full, reason = True, "--full"
    elif args["event"] == "schedule":
        full, reason = True, "schedule event"
    elif base is None and args["changed_file"] is None:
        full, reason = True, "no base"
    elif base is not None and not usable_base(base):
        full, reason = True, "unusable base %s" % base

    if args["changed_file"] is not None:
        files = read_changed(args["changed_file"])
    elif base is not None and usable_base(base):
        found = git_changed(base)
        if found is None:
            if not full:
                full, reason = True, "affected.py changed failed"
        else:
            files = found

    picked = {}
    if not full:
        trigger = forces_full(files)
        if trigger:
            full, reason = True, "changed " + trigger
    if not full:
        found = affected_cases(files, suites)
        if found is None:
            full, reason = True, "affected.py cases failed"
        elif len(found) == len(suites) and all(cases == "ALL" for cases in found.values()):
            full, reason = True, "affected.py selected every suite"
        else:
            picked = found
    if full:
        picked = {suite: "ALL" for suite in suites}

    run_rows = [{"suite": s, "cases": picked[s], "os": [LINUX] + ([WINDOWS] if s in on_windows else [])}
                for s in suites if s in picked]
    skipped = [{"suite": s, "reason": "not affected"} for s in suites if s not in picked]
    include = [{"suite": row["suite"], "cases": row["cases"], "os": os_name} for row in run_rows for os_name in row["os"]]
    return {"full": full, "reason": reason, "event": args["event"], "base": base, "changed_files": len(files),
            "matrix": {"include": include}, "suites": run_rows, "skipped": skipped}


def summary(result):
    mode = "every suite (%s)" % result["reason"] if result["full"] else "selected suites"
    lines = ["## CI plan: %d changed file(s)" % result["changed_files"], "",
             "- Plan: %s; %d run, %d skipped" % (mode, len(result["suites"]), len(result["skipped"])),
             "- Event: %s; base: %s" % (result["event"], result["base"] or "none"), "",
             "| Suite | Run | Cases | OS / reason |", "| --- | --- | --- | --- |"]
    lines += ["| %s | yes | %s | %s |" % (row["suite"], row["cases"], ", ".join(row["os"])) for row in result["suites"]]
    lines += ["| %s | no | - | %s |" % (row["suite"], row["reason"]) for row in result["skipped"]]
    return "\n".join(lines) + "\n"


def parse(argv):
    args = {"base": None, "event": "unspecified", "full": False, "changed_file": None, "summary": None, "github_output": None}
    options = {"--base": "base", "--event": "event", "--changed-file": "changed_file", "--summary": "summary",
               "--github-output": "github_output"}
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--full":
            args["full"] = True
        elif flag in options and i + 1 < len(argv):
            i += 1
            args[options[flag]] = argv[i]
        else:
            print(__doc__, file=sys.stderr)
            sys.exit(2)
        i += 1
    if args["base"] == "":
        args["base"] = None   # an empty $BASE variable in a workflow is "no base"
    return args


def main(argv):
    args = parse(argv)
    result = plan(args)
    if args["summary"]:
        with open(args["summary"], "a", encoding="utf-8", newline="\n") as fh:
            fh.write(summary(result))
    if args["github_output"]:
        with open(args["github_output"], "a", encoding="utf-8", newline="\n") as fh:
            fh.write("matrix=%s\ncount=%d\nfull=%s\nchanged=%d\n" % (
                json.dumps(result["matrix"], separators=(",", ":")), len(result["matrix"]["include"]),
                "true" if result["full"] else "false", result["changed_files"]))
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
