#!/usr/bin/env bash
# netcode-headless.sh: which rpg-mmo-server it reads the pinned Shared.GameLogic tag from.
# A Netcode worktree outside the workspace has no sibling server repo; --server and
# RPG_FACTORY_WORKSPACE must find it. Fixture repos only (--resolve-server builds nothing).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
chk() { if [ "$2" = "$3" ]; then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1: expected '$2' got '$3'"; fi; }

netcode() { # dir - a Netcode checkout pinning sgl-v9.9.9
  mkdir -p "$1/Tests~/Headless"; : > "$1/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"
  printf '{"name":"com.cuvara.netcode","x-manualDependencies":{"com.rpgmmo.shared-gamelogic":"https://x/rpg-mmo-server.git?path=p#sgl-v9.9.9"}}' > "$1/package.json"
  git -C "$1" init -q; git -C "$1" add package.json 'Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj'
  git -C "$1" -c user.email=t@t -c user.name=t commit -qm fixture
}
server() { # dir [tag]
  mkdir -p "$1"; git -C "$1" init -q; echo a > "$1/a"; git -C "$1" add a
  git -C "$1" -c user.email=t@t -c user.name=t commit -qm a; [ -n "${2:-}" ] && git -C "$1" tag "$2"; return 0
}
resolve() { bash "$ROOT/scripts/checks/netcode-headless.sh" --resolve-server "$@" 2>&1; }

WS="$TMP/ws"; server "$WS/rpg-mmo-server" sgl-v9.9.9; netcode "$WS/Netcode"
chk "sibling of the Netcode dir (workspace layout)" "server: $WS/rpg-mmo-server tag: sgl-v9.9.9" "$(resolve --netcode "$WS/Netcode")"

WT="$TMP/elsewhere/wt-netcode"; netcode "$WT"      # a worktree outside the workspace
chk "worktree outside the workspace -> RPG_FACTORY_WORKSPACE" "server: $WS/rpg-mmo-server tag: sgl-v9.9.9" \
    "$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT")"

server "$TMP/elsewhere/rpg-mmo-server"             # a sibling without the tag is skipped
chk "sibling without the tag falls through to the workspace" "server: $WS/rpg-mmo-server tag: sgl-v9.9.9" \
    "$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT")"

OTHER="$TMP/other-server"; server "$OTHER" sgl-v9.9.9
chk "--server wins" "server: $OTHER tag: sgl-v9.9.9" "$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT" --server "$OTHER")"

out=$(RPG_FACTORY_WORKSPACE="$WS" resolve --netcode "$WT" --server "$TMP/elsewhere/rpg-mmo-server"); rc=$?
chk "--server without the tag is an error, not a fallback" "2 blocked" "$rc $(grep -o 'blocked' <<<"$out")"

out=$(RPG_FACTORY_WORKSPACE="$TMP/none" resolve --netcode "$WT"); rc=$?
chk "no server anywhere -> NOT-RUN(blocked)" "2 blocked" "$rc $(grep -o 'blocked' <<<"$out")"

# ---- the dotnet test status decides together with the TRX counters (a failed or timed-out run can
# leave a zero-failure TRX behind). A fake `dotnet` first on PATH writes a TRX, then exits/sleeps.
FAKE="$TMP/fakebin"; mkdir -p "$FAKE"
cat > "$FAKE/dotnet" <<'SH'
#!/usr/bin/env bash
mkdir -p results
executed=3; [ "${FAKE_DOTNET_MODE:-ok}" = empty ] && executed=0
failed=0; [ "${FAKE_DOTNET_MODE:-ok}" = counters ] && failed=1
printf '<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010"><ResultSummary outcome="Completed"><Counters total="3" executed="%s" passed="%s" failed="%s" error="0" timeout="0" aborted="0" notExecuted="0"/></ResultSummary></TestRun>' "$executed" "$((executed - failed))" "$failed" > results/results.trx
echo "fake dotnet log mode=${FAKE_DOTNET_MODE:-ok}"
case "${FAKE_DOTNET_MODE:-ok}" in fail) exit 1 ;; sleep) sleep 10 ;; esac
exit 0
SH
chmod +x "$FAKE/dotnet"
NC="$TMP/nc-nosgl"; mkdir -p "$NC/Runtime" "$NC/Tests" "$NC/Tests~/Headless"; : > "$NC/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"
echo '{"name":"com.cuvara.netcode"}' > "$NC/package.json"
git -C "$NC" init -q; git -C "$NC" add package.json Runtime Tests 'Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj'
git -C "$NC" -c user.email=t@t -c user.name=t commit -qm fixture
run_fake() { FAKE_DOTNET_MODE="$1" NETCODE_HEADLESS_TIMEOUT=2 TMPDIR="$TMP" PATH="$(path_entry "$FAKE"):$PATH" \
  bash "$ROOT/scripts/checks/netcode-headless.sh" --netcode "$NC" >"$TMP/out.txt" 2>&1; echo $?; }
chk "dotnet test passes and the TRX has executed tests -> 0" 0 "$(run_fake ok)"
chk "dotnet test exits 1 with a zero-failure TRX -> 1" 1 "$(run_fake fail)"
grep -q "dotnet test exited 1" "$TMP/out.txt" && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  failure reason not printed"; cat "$TMP/out.txt"; }
chk "dotnet test times out with a zero-failure TRX -> 1" 1 "$(run_fake sleep)"
grep -q "timed out" "$TMP/out.txt" && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  timeout not reported"; cat "$TMP/out.txt"; }
chk "dotnet test passes but nothing executed -> 1" 1 "$(run_fake empty)"

# ---- a FAIL keeps its .trx files and the run log under the Factory state dir (persistent, never $TMPDIR or the
# Netcode repo) and prints the path; a PASS cleans up and writes no evidence. The state dir is a test dir.
STATE="$TMP/state"; EVROOT="$STATE/evidence/netcode-headless"
run_ev() { rm -rf "$STATE"; mkdir -p "$STATE"; RPG_FACTORY_STATE_DIR="$STATE" run_fake "$1"; }
ev_dirs() { find "$EVROOT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' '; }
for mode in fail counters sleep; do
  chk "failing run ($mode) -> 1" 1 "$(run_ev "$mode")"
  chk "failing run ($mode) keeps one evidence dir" 1 "$(ev_dirs)"
  ev=$(sed -n 's/^evidence: //p' "$TMP/out.txt" | tr -d '\r')
  chk "failing run ($mode) prints the evidence path under the state dir" "$(fwd "$EVROOT")" "$(fwd "$(dirname "$ev")")"
  [ -f "$ev/results/results.trx" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  evidence ($mode) has no results.trx"; }
  grep -q "fake dotnet log mode=$mode" "$ev/dotnet.log" 2>/dev/null && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  evidence ($mode) has no dotnet.log"; }
done
chk "passing run -> 0" 0 "$(run_ev ok)"
chk "passing run writes no evidence" 0 "$(ev_dirs)"
grep -q "^evidence:" "$TMP/out.txt" && { fail=$((fail + 1)); echo "FAIL  passing run printed an evidence path"; } || pass=$((pass + 1))
[ -z "$(find "$TMP" -maxdepth 1 -name '.tmp-netcode-headless-*' 2>/dev/null)" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  work copy left behind"; }
# an unwritable state dir (a file where the directory must be) warns and keeps the verdict
rm -rf "$STATE"; : > "$STATE"
chk "failing run with an unusable state dir keeps exit 1" 1 "$(RPG_FACTORY_STATE_DIR="$STATE" run_fake fail)"
grep -q "WARNING: evidence not saved" "$TMP/out.txt" && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  no warning for an unusable state dir"; cat "$TMP/out.txt"; }
rm -f "$STATE"

# Candidate identity must follow a linked worktree's distinct commit for both selectors.
LINKED="$TMP/linked-netcode"; git -C "$NC" worktree add -qb linked-candidate "$LINKED"
mkdir -p "$LINKED/Runtime" "$LINKED/Tests"
echo linked > "$LINKED/Runtime/candidate-marker"
git -C "$LINKED" add Runtime/candidate-marker
git -C "$LINKED" -c user.email=t@t -c user.name=t commit -qm candidate
LINKED_SHA=$(git -C "$LINKED" rev-parse HEAD)
linked_explicit() { FAKE_DOTNET_MODE=ok NETCODE_HEADLESS_TIMEOUT=2 TMPDIR="$TMP" PATH="$(path_entry "$FAKE"):$PATH" bash "$ROOT/scripts/checks/netcode-headless.sh" --netcode "$LINKED" >"$TMP/linked-explicit.log" 2>&1; }
chk "explicit linked Netcode candidate passes -> 0" 0 "$(linked_explicit; echo $?)"
grep -Fq "source: $LINKED @ $LINKED_SHA" "$TMP/linked-explicit.log" && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  explicit linked Netcode source SHA"; }
grep -Fq "source: $LINKED @ $(git -C "$NC" rev-parse HEAD)" "$TMP/linked-explicit.log" && { fail=$((fail + 1)); echo "FAIL  explicit linked Netcode used main fixture SHA"; } || pass=$((pass + 1))
linked_env() { FAKE_DOTNET_MODE=ok NETCODE_HEADLESS_TIMEOUT=2 TMPDIR="$TMP" PATH="$(path_entry "$FAKE"):$PATH" RPG_FACTORY_REPO_KEY=netcode RPG_FACTORY_REPO_DIR="$LINKED" bash "$ROOT/scripts/checks/netcode-headless.sh" >"$TMP/linked-env.log" 2>&1; }
chk "environment linked Netcode candidate passes -> 0" 0 "$(linked_env; echo $?)"
grep -Fq "source: $LINKED @ $LINKED_SHA" "$TMP/linked-env.log" && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  environment linked Netcode source SHA"; }
grep -Fq "source: $LINKED @ $(git -C "$NC" rev-parse HEAD)" "$TMP/linked-env.log" && { fail=$((fail + 1)); echo "FAIL  environment linked Netcode used main fixture SHA"; } || pass=$((pass + 1))

NON_GIT="$TMP/non-git-netcode"; mkdir -p "$NON_GIT/Tests~/Headless"; : > "$NON_GIT/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"
echo '{"name":"com.cuvara.netcode"}' > "$NON_GIT/package.json"
out=$(resolve --netcode "$NON_GIT"); rc=$?
[[ "$rc" -ne 0 && "$out" != *"server:"* ]] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  non-git --netcode target must fail closed without a server resolution"; }
mkdir -p "$NC/plain nested/Tests~/Headless"; : > "$NC/plain nested/Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj"
out=$(resolve --netcode "$NC/plain nested"); rc=$?
[[ "$rc" -ne 0 && "$out" == *"ERROR: Netcode target is not a git work-tree root"* && "$out" != *"server:"* ]] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL  nested plain Netcode target rejected in --resolve-server"; }

echo "netcode-headless: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
