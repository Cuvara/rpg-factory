"""Check result grading for run-checks.py: which parser a registry check uses and how its output grades."""
import re


def parser_for(check):
    p = check.get("parser")
    if p:
        return p
    run = check["run"]
    if re.search(r"\bgo test\b", run):
        return "go-test"
    if re.search(r"\bdotnet(\.exe)? test\b|\{dotnet\} test", run) and "Regenerate" not in run:
        return "dotnet-test"
    if "netcode-headless.sh" in run:
        return r"regex:executed=[1-9]\d* passed=\d+ failed=0"
    return "exit"


def grade(parser, code, out):
    """(state, counts, reason)"""
    counts = {}
    if parser == "artifact":
        lines = [line for line in out.splitlines() if re.match(r"^(PASS|FAIL|HUMAN_REQUIRED|NOT_AVAILABLE) ", line)]
        counts = {"passed": sum(line.startswith("PASS ") for line in lines),
                  "failed": sum(line.startswith("FAIL ") for line in lines),
                  "human_required": sum(line.startswith("HUMAN_REQUIRED ") for line in lines),
                  "not_available": sum(line.startswith("NOT_AVAILABLE ") for line in lines),
                  "discovered": len(lines)}
        if code != 0 or counts["failed"]:
            return "FAIL", counts, f"exit {code}, {counts['failed']} artifact failures"
        if not lines:
            return "FAIL", counts, "no artifact result lines"
        if counts["human_required"] or counts["not_available"]:
            reasons = []
            if counts["human_required"]: reasons.append(f"{counts['human_required']} artifact(s) need human approval")
            reasons.extend(line[len("NOT_AVAILABLE "):] for line in lines if line.startswith("NOT_AVAILABLE "))
            return "HUMAN_REQUIRED", counts, "; ".join(reasons)
        if counts["passed"] == 0:
            return "FAIL", counts, "no artifact PASS result lines"
        return "PASS", counts, None
    if parser == "go-test":
        counts = {"passed": len(re.findall(r"^\s*--- PASS", out, re.M)), "failed": len(re.findall(r"^\s*--- FAIL", out, re.M)),
                  "skipped": len(re.findall(r"^\s*--- SKIP", out, re.M)),
                  "packages_ok": len(re.findall(r"^ok\s", out, re.M)), "packages_failed": len(re.findall(r"^FAIL\s", out, re.M)),
                  "no_test_files": len(re.findall(r"\[no test files\]", out))}
        counts["discovered"] = counts["passed"] + counts["failed"] + counts["skipped"]
        if code != 0 or counts["failed"]:
            return "FAIL", counts, f"exit {code}, {counts['failed']} failed"
        if counts["passed"] == 0:
            return "FAIL", counts, "exit 0 but no test PASSED - nothing was verified"
        return "PASS", counts, None
    if parser == "dotnet-test":
        tot = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        for m in re.finditer(r"(?:Passed|Failed)!\s+-\s+Failed:\s+(\d+),\s+Passed:\s+(\d+),\s+Skipped:\s+(\d+),\s+Total:\s+(\d+)", out):
            f, p, s, t = map(int, m.groups())
            tot["failed"] += f; tot["passed"] += p; tot["skipped"] += s; tot["total"] += t
        counts = {**tot, "discovered": tot["total"]}
        if code != 0 or tot["failed"]:
            return "FAIL", counts, f"exit {code}, {tot['failed']} failed"
        if tot["passed"] == 0:
            return "FAIL", counts, "no test passed (0 executed or all skipped) - dotnet test exits 0 on that"
        return "PASS", counts, None
    if parser.startswith("regex:"):
        pat = parser[6:]
        if code != 0:
            return "FAIL", counts, f"exit {code}"
        m = re.search(pat, out, re.M)
        if not m:
            return "FAIL", counts, f"exit 0 but expected evidence /{pat}/ not found"
        line = out[out.rfind("\n", 0, m.start()) + 1: out.find("\n", m.end()) if out.find("\n", m.end()) >= 0 else len(out)]
        counts = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
        counts["evidence"] = line.strip()[:120]
        return "PASS", counts, None
    return ("PASS", counts, None) if code == 0 else ("FAIL", counts, f"exit {code}")
