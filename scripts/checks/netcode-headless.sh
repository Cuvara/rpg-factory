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
src="${RPG_FACTORY_REPO_DIR:-}"
if [ -z "$src" ]; then src="$(git rev-parse --show-toplevel 2>/dev/null)"; fi
src="${src:-}"
keep=false
while [ $# -gt 0 ]; do
  case "$1" in --netcode) src="$2"; shift 2 ;; --keep) keep=true; shift ;; *) echo "unknown arg $1"; exit 2 ;; esac
done
[ -n "$src" ] && git -C "$src" rev-parse --show-toplevel >/dev/null 2>&1 || { echo "ERROR: Netcode target is not a git work tree: ${src:-<unresolved>}"; exit 2; }
[ -f "$src/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj" ] || { echo "ERROR: no headless project under $src"; exit 2; }

if command -v dotnet >/dev/null 2>&1; then dotnet=dotnet; base="${TMPDIR:-/tmp}"
  case "$base" in /*) [ -d "$base" ] && [ -w "$base" ] || base=/tmp ;; *) base=/tmp ;; esac   # never a relative/invalid TMPDIR
elif command -v dotnet.exe >/dev/null 2>&1; then dotnet=dotnet.exe; base="$PLUGIN_ROOT"   # Windows dotnet needs a /mnt/c path
else echo "NOT-RUN(tool-missing): neither dotnet nor dotnet.exe on PATH"; exit 2; fi

work=$(mktemp -d "$base/.tmp-netcode-headless-XXXXXX")
$keep || trap 'rm -rf "$work"' EXIT
for d in Runtime Tests "Tests~"; do cp -r "$src/$d" "$work/" || { echo "ERROR: copy $d failed"; exit 2; }; done

# The prediction tests compile against Shared.GameLogic at the tag package.json pins
# (x-manualDependencies). CI checks that tag out and passes -p:SglDir; do the same from the workspace
# server repo with `git archive` (read-only; nothing is built inside rpg-mmo-server).
sgl_args=()
sgl_tag=$(python3 -B -c "import json,sys; u=json.load(open(sys.argv[1], encoding='utf-8')).get('x-manualDependencies', {}).get('com.rpgmmo.shared-gamelogic', ''); print(u.rsplit('#', 1)[1] if '#' in u else '')" "$src/package.json")
if [ -n "$sgl_tag" ]; then
  srv="${RPG_FACTORY_WORKSPACE:-$(dirname "$src")}/rpg-mmo-server"; sgl_path=backend/gameserver-dotnet/Shared.GameLogic
  mkdir -p "$work/sgl"
  git -C "$srv" archive "$sgl_tag" "$sgl_path" | tar -x -C "$work/sgl" \
    || { echo "NOT-RUN(blocked): Shared.GameLogic tag $sgl_tag not readable in $srv (fetch its tags)"; exit 2; }
  sgl_dir="$work/sgl/$sgl_path"
  # Windows dotnet needs C:/... - git-bash: cygpath; WSL running dotnet.exe: wslpath (/mnt/c/... is not a path to it)
  if command -v cygpath >/dev/null 2>&1; then sgl_dir=$(cygpath -m "$sgl_dir")
  elif [ "$dotnet" = dotnet.exe ] && command -v wslpath >/dev/null 2>&1; then sgl_dir=$(wslpath -m "$sgl_dir"); fi
  sgl_args=(-p:SglDir="$sgl_dir")
  echo "sgl:    $sgl_tag from $srv (git archive, as CI checks out the pinned tag)"
fi

echo "source: $src @ $(git -C "$src" rev-parse HEAD) ($(git -C "$src" status --porcelain 2>/dev/null | wc -l) uncommitted paths included as-is)"
echo "run:    (cd <copy>/Tests~/Headless && $dotnet test ${sgl_args[*]:-} --logger 'trx;LogFileName=results.trx' --results-directory results)"
run_log="$work/dotnet.log"
set +e
(cd "$work/Tests~/Headless" && timeout 900 "$dotnet" test "${sgl_args[@]}" --logger 'trx;LogFileName=results.trx' --results-directory results) >"$run_log" 2>&1
dotnet_rc=$?
set -e
tail -15 "$run_log"
[ "$dotnet_rc" -eq 0 ] || { echo "FAIL: dotnet test exited $dotnet_rc"; exit 1; }

python3 - "$work/Tests~/Headless/results" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
files = sorted(glob.glob(sys.argv[1] + "/**/*.trx", recursive=True))
if not files:
    print("FAIL: no .trx produced - nothing was verified"); sys.exit(1)
ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
tot = {"total": 0, "executed": 0, "passed": 0, "failed": 0, "notExecuted": 0}
for f in files:
    summary = ET.parse(f).getroot().find(".//t:ResultSummary", ns)
    if summary is None or summary.get("outcome", "Passed").lower() != "passed":
        print(f"FAIL: trx outcome is not Passed: {f}"); sys.exit(1)
    c = summary.find("t:Counters", ns)
    if c is None:
        print(f"FAIL: trx has no counters: {f}"); sys.exit(1)
    for k in tot:
        tot[k] += int(c.get(k, 0))
print("headless tests: discovered={total} executed={executed} passed={passed} failed={failed} skipped/notExecuted={notExecuted}".format(**tot))
sys.exit(0 if tot["executed"] > 0 and tot["failed"] == 0 else 1)
PY
