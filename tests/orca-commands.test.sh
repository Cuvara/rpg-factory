#!/usr/bin/env bash
# Every `orca ...` command cited in skills/factory-core/references/parallel-work.md exists in the installed Orca
# CLI: `orca <cmd> <sub>` in `orca --help`, `orca orchestration <sub>` in `orca orchestration --help`, and each
# `--flag` cited in the same code span in that command's own `--help`. A made-up command or flag must fail the
# same checker. Prints SKIP and exits 0 when orca is not on PATH (CI).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
if ! command -v orca >/dev/null 2>&1; then echo "SKIP  orca not on PATH"; exit 0; fi
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
orca --help > "$TMP/top.txt" 2>&1
orca orchestration --help > "$TMP/orch.txt" 2>&1
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -15 | sed 's/^/      /'; }

# check <doc>: prints "OK <cmd>" / "MISSING <cmd>" for each distinct orca command in the doc's code spans
check() {
  python3 -B - "$1" "$TMP/top.txt" "$TMP/orch.txt" <<'PY'
import re, subprocess, sys
doc, top, orch = (open(p, encoding="utf-8", errors="replace").read() for p in sys.argv[1:4])
spans = re.findall(r"`([^`]+)`", doc)
cmds = []
flags = {}  # command -> --flags cited after it in the same code span
for s in spans:
    for m in re.finditer(r"\borca\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?", s):
        c = (m.group(1), m.group(2))
        if c not in cmds:
            cmds.append(c)
        flags.setdefault(c, set()).update(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", s[m.end():]))
def listed(text, words):
    return re.search(r"^\s+" + r"\s+".join(map(re.escape, words)) + r"(\s|$)", text, re.M) is not None
for cmd, sub in cmds:
    if cmd == "orchestration":
        found = sub is not None and (listed(orch, [sub]) or listed(top, ["orchestration", sub]))
        words = [cmd, sub]
    elif sub and listed(top, [cmd, sub]):
        found, words = True, [cmd, sub]
    else:
        found, words = listed(top, [cmd]), [cmd]
    name = "orca " + " ".join(w for w in words if w)
    print(("OK " if found else "MISSING ") + name)
    if found and flags.get((cmd, sub)):
        res = subprocess.run(["orca", *words, "--help"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60)
        usage = res.stdout + res.stderr
        for f in sorted(flags[(cmd, sub)]):
            ok = re.search(re.escape(f) + r"(?![a-z-])", usage) is not None
            print(("OK " if ok else "MISSING ") + f"{name} {f}")
PY
}

out=$(check "$ROOT/skills/factory-core/references/parallel-work.md")
n=$(grep -c '^OK ' <<<"$out"); missing=$(grep '^MISSING ' <<<"$out")
[ -z "$missing" ] && [ "$n" -ge 10 ] && ok "parallel-work.md: $n cited orca commands exist in orca --help ($(orca --version 2>/dev/null | head -1))" \
  || no "parallel-work.md cites orca commands that do not exist (or too few found: $n)" "$missing"
grep -q '^OK orca orchestration worker-start$' <<<"$out" && grep -q '^OK orca skills get$' <<<"$out" && grep -q '^OK orca status$' <<<"$out" \
  && ok "the checker saw worker-start, skills get and status" || no "expected commands not extracted" "$out"
grep -q '^OK orca status --json$' <<<"$out" && grep -q '^OK orca orchestration worker-start --worktree$' <<<"$out" \
  && ok "the cited flags --json and --worktree exist in their commands' --help" || no "cited flags not checked" "$out"

# the checker bites: made-up commands and flags are reported MISSING
printf 'Use `orca orchestration made-up-cmd` and `orca nosuch thing`.\n' > "$TMP/bad.md"
out=$(check "$TMP/bad.md")
grep -q '^MISSING orca orchestration made-up-cmd$' <<<"$out" && grep -q '^MISSING orca nosuch$' <<<"$out" \
  && ok "made-up orca commands are reported missing" || no "checker accepted a made-up command" "$out"
printf 'Detect with `orca status --made-up-flag` and dispatch with `orca orchestration worker-start --no-such-flag`.\n' > "$TMP/badflag.md"
out=$(check "$TMP/badflag.md")
grep -q '^MISSING orca status --made-up-flag$' <<<"$out" && grep -q '^MISSING orca orchestration worker-start --no-such-flag$' <<<"$out" \
  && ok "made-up flags are reported missing" || no "checker accepted a made-up flag" "$out"

echo "orca-commands: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
