#!/usr/bin/env bash
# netcode-headless.sh — run Netcode's headless (non-Unity) test project WITHOUT writing into
# the Netcode repo. Netcode has no .gitignore, so `dotnet test` in place would leave bin/ and
# obj/ as untracked files in the user's tree. This copies Runtime/, Tests/ and Tests~/ into a
# temp dir (on /mnt/c when only Windows dotnet.exe exists), runs the same command CI's
# `headless` job runs, and reports the .trx counters the way CI asserts them.
#
# Usage: netcode-headless.sh [--netcode DIR] [--server DIR] [--keep] [--resolve-server]
# The Shared.GameLogic tag is read from rpg-mmo-server: --server DIR, else the first of
# <dirname of the Netcode dir>/rpg-mmo-server and $RPG_FACTORY_WORKSPACE/rpg-mmo-server that has the
# tag (a Netcode worktree outside the workspace has no sibling server repo). --resolve-server prints
# the server repo it would use and exits.
# Exit 0 = executed > 0 and failed == 0; 1 = failures or nothing executed; 2 = setup error.
set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
. "$(dirname "${BASH_SOURCE[0]}")/../lib/compat.sh"
src=""
if [ "${RPG_FACTORY_REPO_KEY:-}" = netcode ] || [ -z "${RPG_FACTORY_REPO_KEY:-}" ]; then
  src="${RPG_FACTORY_REPO_DIR:-}"
fi
if [ -z "$src" ]; then
  cwd_top="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$cwd_top" ] && [ -f "$cwd_top/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj" ]; then src="$cwd_top"; fi
fi
if [ -z "$src" ] && [ -n "${RPG_FACTORY_WORKSPACE:-}" ]; then src="$RPG_FACTORY_WORKSPACE/Netcode"; fi
keep=false
server_arg=""; resolve_only=false
while [ $# -gt 0 ]; do
  case "$1" in
    --netcode) src="$2"; shift 2 ;; --server) server_arg="$2"; shift 2 ;; --keep) keep=true; shift ;;
    --resolve-server) resolve_only=true; shift ;; *) echo "unknown arg $1"; exit 2 ;;
  esac
done
is_worktree_root() {
  local dir="$1"
  [ -n "$dir" ] && [ "$(git -C "$dir" rev-parse --is-inside-work-tree 2>/dev/null)" = true ] && [ -z "$(git -C "$dir" rev-parse --show-prefix 2>/dev/null)" ]
}
is_worktree_root "$src" || { echo "ERROR: Netcode target is not a git work-tree root: ${src:-<unresolved>}"; exit 2; }
[ -z "$server_arg" ] || is_worktree_root "$server_arg" || { echo "ERROR: server target is not a git work-tree root: $server_arg"; exit 2; }
[ -f "$src/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj" ] || { echo "ERROR: no headless project under $src"; exit 2; }

sgl_tag=$(python3 -B -c "import json,sys; u=json.load(open(sys.argv[1], encoding='utf-8')).get('x-manualDependencies', {}).get('com.rpgmmo.shared-gamelogic', ''); print(u.rsplit('#', 1)[1] if '#' in u else '')" "$src/package.json")

# The server repo that holds the pinned Shared.GameLogic tag. An explicit --server is used as given
# (no silent fallback); otherwise the sibling of the Netcode dir, then the workspace's.
resolve_server() {
  if [ -n "$server_arg" ]; then
    git -C "$server_arg" rev-parse -q --verify "refs/tags/$1" >/dev/null 2>&1 && { echo "$server_arg"; return 0; }
    return 1
  fi
  local c
  for c in "$(dirname "$src")/rpg-mmo-server" "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/rpg-mmo-server"; do
    is_worktree_root "$c" || continue
    git -C "$c" rev-parse -q --verify "refs/tags/$1" >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  return 1
}
srv=""
if [ -n "$sgl_tag" ]; then
  srv=$(resolve_server "$sgl_tag") || { echo "NOT-RUN(blocked): Shared.GameLogic tag $sgl_tag not found in ${server_arg:-$(dirname "$src")/rpg-mmo-server or ${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/rpg-mmo-server} (pass --server, or fetch its tags)"; exit 2; }
fi
if $resolve_only; then echo "server: ${srv:-<none needed: no Shared.GameLogic pin>} tag: ${sgl_tag:-<none>}"; exit 0; fi

if command -v dotnet >/dev/null 2>&1; then dotnet=dotnet; base="${TMPDIR:-/tmp}"
  is_abs "$base" && [ -d "$base" ] && [ -w "$base" ] || base=/tmp   # never a relative/invalid TMPDIR
elif command -v dotnet.exe >/dev/null 2>&1; then dotnet=dotnet.exe; base="$PLUGIN_ROOT"   # WSL: Windows dotnet needs a /mnt/c path
  # Git Bash: a usable Windows TMPDIR is reachable by dotnet.exe; under WSL a Linux TMPDIR (/tmp) is not
  if [ -n "$RPGF_WINDOWS" ] && [ -n "${TMPDIR:-}" ] && is_abs "$TMPDIR" && [ -d "$TMPDIR" ] && [ -w "$TMPDIR" ]; then base="$TMPDIR"; fi
else echo "NOT-RUN(tool-missing): neither dotnet nor dotnet.exe on PATH"; exit 2; fi
if [ -n "$RPGF_WINDOWS" ] && command -v cygpath >/dev/null 2>&1; then base=$(cygpath -u "$base"); fi

work=$(mktemp -d "$base/.tmp-netcode-headless-XXXXXX")
$keep || trap 'rm -rf "$work"' EXIT
for d in Runtime Tests "Tests~"; do cp -r "$src/$d" "$work/" || { echo "ERROR: copy $d failed"; exit 2; }; done

# The prediction tests compile against Shared.GameLogic at the tag package.json pins
# (x-manualDependencies). CI checks that tag out and passes -p:SglDir; do the same from the workspace
# server repo with `git archive` (read-only; nothing is built inside rpg-mmo-server).
sgl_args=()
if [ -n "$sgl_tag" ]; then
  sgl_path=backend/gameserver-dotnet/Shared.GameLogic
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
(cd "$work/Tests~/Headless" && timeout "${NETCODE_HEADLESS_TIMEOUT:-900}" "$dotnet" test "${sgl_args[@]}" --logger 'trx;LogFileName=results.trx' --results-directory results) >"$run_log" 2>&1
dotnet_rc=$?
tail -15 "$run_log"

python3 - "$work/Tests~/Headless/results" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
files = sorted(glob.glob(sys.argv[1] + "/**/*.trx", recursive=True))
if not files:
    print("FAIL: no .trx produced - nothing was verified"); sys.exit(1)
ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
tot = {k: 0 for k in ("total", "executed", "passed", "failed", "error", "timeout", "aborted")}
for f in files:
    try:
        summary = ET.parse(f).getroot().find(".//t:ResultSummary", ns)
    except (ET.ParseError, OSError) as e:
        print(f"FAIL: cannot parse trx {f}: {e}"); sys.exit(1)
    outcome = summary.get("outcome") if summary is not None else None
    if outcome is None:
        print(f"FAIL: trx ResultSummary has no outcome: {f}"); sys.exit(1)
    if outcome.lower() not in ("completed", "passed"):
        print(f"FAIL: trx outcome is {outcome}: {f}"); sys.exit(1)
    c = summary.find("t:Counters", ns)
    if c is None:
        print(f"FAIL: trx has no counters: {f}"); sys.exit(1)
    try:
        counts = {k: int(c.attrib[k]) for k in tot}
    except (KeyError, ValueError) as e:
        print(f"FAIL: trx has missing or invalid counter {e}: {f}"); sys.exit(1)
    for k, value in counts.items():
        tot[k] += value
print("headless tests: total={total} executed={executed} passed={passed} failed={failed} error={error} timeout={timeout} aborted={aborted}".format(**tot))
bad = [k for k in ("failed", "error", "timeout", "aborted") if tot[k] != 0]
if tot["executed"] <= 0:
    print("FAIL: no tests executed")
    sys.exit(1)
if bad:
    print("FAIL: nonzero TRX counters: " + ", ".join(f"{k}={tot[k]}" for k in bad))
    sys.exit(1)
sys.exit(0)
PY
counters_rc=$?
if [ "$dotnet_rc" -eq 124 ]; then echo "FAIL: dotnet test timed out after ${NETCODE_HEADLESS_TIMEOUT:-900} s"; exit 1; fi
if [ "$dotnet_rc" -ne 0 ]; then echo "FAIL: dotnet test exited $dotnet_rc"; exit 1; fi
exit "$counters_rc"
