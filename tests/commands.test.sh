#!/usr/bin/env bash
# Slash commands: every commands/*.md is well-formed and calls factory-cmd.py with its own verb; the
# dispatcher validates arguments (exit 2 + usage) and really invokes the scripts (fixture workspace).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMD="$ROOT/scripts/factory-cmd.py"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
# -- command files
for f in "$ROOT"/commands/*.md; do
  n=$(basename "$f" .md)
  head -1 "$f" | grep -q '^---$' && grep -q '^description: ' "$f" && grep -q '^disable-model-invocation: true$' "$f" \
    && ok "commands/$n.md frontmatter (description, user-only)" || no "commands/$n.md frontmatter"
  grep -qE '^!`python3 \$\{CLAUDE_PLUGIN_ROOT\}/scripts/factory-cmd.py '"$n"'( |`)' "$f" && ok "commands/$n.md runs factory-cmd.py $n" || no "commands/$n.md dispatch line"
  # the ! line must match the command's own allowed-tools pattern, or Claude Code refuses to run it
  pat=$(sed -n 's/^allowed-tools: Bash(\(.*\):\*)$/\1/p' "$f"); line=$(sed -n 's/^!`\(.*\)`$/\1/p' "$f")
  [ -n "$pat" ] && [ "${line#"$pat"}" != "$line" ] && ok "commands/$n.md ! line matches its allowed-tools prefix" || no "commands/$n.md: '$line' does not start with allowed '$pat'"
done
[ "$(ls "$ROOT"/commands/*.md | wc -l)" -eq 4 ] && ok "exactly 4 commands (status, route, check, doctor)" || no "command count"
# -- argument validation (exit 2, no script run)
for a in "" "bogus" "route" "route nosuchrepo x.go" "route server" "check" "check nosuchrepo" "status extra" "doctor extra" "route server x.go --lead"; do
  python3 -B "$CMD" $a >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && grep -q "status \[--remote\]" "$TMP/err" && ok "usage error -> exit 2: '$a'" || no "expected usage error for '$a' (rc=$rc)"
done
# -- real invocations on a fixture workspace
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$S/backend/gateway/server" "$C/ProjectSettings"; touch "$S/backend/TEAM.md" "$S/backend/gateway/server/server.go" "$C/ProjectSettings/ProjectVersion.txt"
for r in "$S" "$C"; do git -C "$r" init -q -b develop; git -C "$r" -c user.email=t@t -c user.name=t add -A; git -C "$r" -c user.email=t@t -c user.name=t commit -qm init; done
export RPG_FACTORY_WORKSPACE="$WS"
out=$(cd "$WS" && python3 -B "$CMD" route server backend/gateway/server/server.go)
grep -q 'Routing\*\* lead `rpg-factory:server-services`' <<<"$out" && grep -q "^Explain:" <<<"$out" && ok "route: lead + explanation" || no "route output: $(head -c 300 <<<"$out")"
out=$(cd "$WS" && python3 -B "$CMD" route "server backend/gateway/server/server.go")   # one quoted $ARGUMENTS string
grep -q 'lead `rpg-factory:server-services`' <<<"$out" && ok "route: single quoted argument string is split" || no "route quoted"
out=$(cd "$WS" && python3 -B "$CMD" route server backend/gateway/server/server.go --lead measure 2>&1); rc=$?
[ $rc -ne 0 ] && ok "route --lead with a non-candidate is rejected (rc=$rc)" || no "route --lead accepted a non-candidate"
out=$(cd "$WS" && python3 -B "$CMD" check server backend/gateway/server/server.go --status); rc=$?
grep -q "against the CURRENT tree (nothing was run)" <<<"$out" && grep -q "NOT_RUN" <<<"$out" && [ $rc -eq 1 ] && ok "check --status: NOT_RUN, nothing run, exit 1" || no "check --status: rc=$rc $(head -c 300 <<<"$out")"
out=$(cd "$WS" && python3 -B "$CMD" status); rc=$?
grep -q "# Factory status" <<<"$out" && grep -q "## Freshness" <<<"$out" && [ $rc -eq 0 ] && ok "status runs factory-status (exit 0)" || no "status rc=$rc"
out=$(cd "$WS" && python3 -B "$CMD" doctor 2>&1)
grep -q "## Install" <<<"$out" && grep -q "## Tripwire latches" <<<"$out" && grep -q "persistent state: $TMP/state" <<<"$out" && ok "doctor: install, latches, state paths" || no "doctor: $(tail -c 300 <<<"$out")"
[ -z "$(git -C "$S" status --porcelain)" ] && ok "read-only commands left the fixture repo untouched" || no "fixture repo changed"
total=$((pass + fail)); echo "commands tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
