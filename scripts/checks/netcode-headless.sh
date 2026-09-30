#!/usr/bin/env bash
# netcode-headless.sh — run Netcode's headless (non-Unity) test project WITHOUT writing into
# the Netcode repo. Netcode has no .gitignore, so `dotnet test` in place would leave bin/ and
# obj/ as untracked files in the user's tree. This copies Runtime/, Tests/ and Tests~/ into a
# temp dir (on /mnt/c when only Windows dotnet.exe exists), runs the same command CI's
# `headless` job runs, and reports the .trx counters the way CI asserts them.
#
# Usage: netcode-headless.sh [--netcode DIR] [--keep]
# Exit 0 = executed > 0 and failed == 0; 1 = failures or nothing executed; 2 = setup error.
set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
src="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/Netcode"
keep=false
while [ $# -gt 0 ]; do
  case "$1" in --netcode) src="$2"; shift 2 ;; --keep) keep=true; shift ;; *) echo "unknown arg $1"; exit 2 ;; esac
done
[ -f "$src/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj" ] || { echo "ERROR: no headless project under $src"; exit 2; }

if command -v dotnet >/dev/null 2>&1; then dotnet=dotnet; base="${TMPDIR:-/tmp}"
elif command -v dotnet.exe >/dev/null 2>&1; then dotnet=dotnet.exe; base="$PLUGIN_ROOT"   # Windows dotnet needs a /mnt/c path
else echo "NOT-RUN(tool-missing): neither dotnet nor dotnet.exe on PATH"; exit 2; fi

work=$(mktemp -d "$base/.tmp-netcode-headless-XXXXXX")
$keep || trap 'rm -rf "$work"' EXIT
for d in Runtime Tests "Tests~"; do cp -r "$src/$d" "$work/" || { echo "ERROR: copy $d failed"; exit 2; }; done

echo "source: $src @ $(git -C "$src" rev-parse --short HEAD 2>/dev/null) ($(git -C "$src" status --porcelain 2>/dev/null | wc -l) uncommitted paths included as-is)"
echo "run:    (cd <copy>/Tests~/Headless && $dotnet test --logger 'trx;LogFileName=results.trx' --results-directory results)"
(cd "$work/Tests~/Headless" && timeout 900 "$dotnet" test --logger 'trx;LogFileName=results.trx' --results-directory results 2>&1 | tail -15)

python3 - "$work/Tests~/Headless/results" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
files = sorted(glob.glob(sys.argv[1] + "/**/*.trx", recursive=True))
if not files:
    print("FAIL: no .trx produced - nothing was verified"); sys.exit(1)
ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
tot = {"total": 0, "executed": 0, "passed": 0, "failed": 0, "notExecuted": 0}
for f in files:
    c = ET.parse(f).getroot().find(".//t:ResultSummary/t:Counters", ns)
    for k in tot:
        tot[k] += int(c.get(k, 0))
print("headless tests: discovered={total} executed={executed} passed={passed} failed={failed} skipped/notExecuted={notExecuted}".format(**tot))
sys.exit(0 if tot["executed"] > 0 and tot["failed"] == 0 else 1)
PY
