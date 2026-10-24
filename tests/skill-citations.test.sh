#!/usr/bin/env bash
# scripts/checks/skill-citations.py against a throwaway plugin (minimal registry + one skill) and
# throwaway repos: resolution (cite_roots, repo prefixes, bare basenames), continuations, anchors,
# drift with a suggestion, past-the-end lines, ref-based reading, --ref, --offline, missing repos.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
unset RPG_FACTORY_WORKSPACE
P="$TMP/plugin"; WS="$TMP/ws"; SRV="$WS/srv"; CLI="$WS/cli"
mkdir -p "$P/scripts/checks" "$P/skills/demo/references" "$SRV/backend/game" "$SRV/backend/other" "$CLI/Assets/UI"
cp "$ROOT/scripts/checks/skill-citations.py" "$P/scripts/checks/"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
cat > "$P/registry.json" <<EOF
{"workspace": {"root_default": "$WS", "root_env": "RPGF_TEST_WS"},
 "repos": {"server": {"path": "srv", "default_branch": "develop"}, "client": {"path": "cli", "default_branch": "develop"}},
 "skills": {"demo": {"kind": "tech", "repos": ["server", "client"],
                     "cite_roots": {"": "server:backend", "client:": "client:Assets"}}}}
EOF
# server: Tick.cs with RunAsync at 3 and TickOnce at 6; two Shared.cs (ambiguous basename); Unique.cs
printf 'class Tick {\n  // run\n  void RunAsync() {}\n  int a;\n  int b;\n  void TickOnce() {}\n}\n' > "$SRV/backend/game/Tick.cs"
printf 'class Shared {}\n' > "$SRV/backend/game/Shared.cs"; printf 'class Shared {}\n' > "$SRV/backend/other/Shared.cs"
printf 'x\nclass Unique { void Go() {} }\n' > "$SRV/backend/other/Unique.cs"
printf '# Changelog\n\n## [0.47.0]\n\nKcpTransport\n' > "$SRV/backend/game/CHANGELOG.md"
printf '# Guide\n\n## Heading\n\nStableSymbol\n' > "$SRV/backend/other/Guide.MD"
printf 'class Hud {\n  void Bind() {}\n}\n' > "$CLI/Assets/UI/Hud.cs"
for r in "$SRV" "$CLI"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done

pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/      /'; }
skill() { printf '%s\n' "---" "name: demo" "---" "$@" > "$P/skills/demo/SKILL.md"; }
run() { (cd "$P" && CLAUDE_PLUGIN_ROOT="$P" python3 -B scripts/checks/skill-citations.py "$@" 2>&1); }

skill '- `Tick.RunAsync` (`game/Tick.cs:3`), then `TickOnce` (`:6`).' \
      '- `Go` (`Unique.cs:2`) by basename; `Bind` (`client:UI/Hud.cs:2`); `Hud` (`cli/Assets/UI/Hud.cs:1-3`) by repo name.'
out=$(run); rc=$?
[ $rc -eq 0 ] && grep -q "^OK: 5 line citation(s) checked" <<<"$out" \
  && ok "anchored citations resolve: default root, continuation, basename, client: prefix, repo-name prefix" || no "good citations (rc=$rc)" "$out"

skill '- `KcpTransport` (`game/CHANGELOG.md:5`).'
out=$(run); [ $? -eq 1 ] && grep -q 'doc line citation: cite `game/CHANGELOG.md` by section, not line (skill-contract)' <<<"$out" \
  && ok "Markdown line citations fail even when the anchor matches" || no "Markdown line citation" "$out"
skill '- `StableSymbol` (`other/Guide.MD:5`).'
out=$(run); [ $? -eq 1 ] && grep -q 'doc line citation: cite `other/Guide.MD` by section, not line (skill-contract)' <<<"$out" \
  && ok "uppercase extension and nested path are rejected" || no "uppercase Markdown line citation" "$out"
skill '- See `game/CHANGELOG.md` section `[0.47.0]` for the transport change.'
out=$(run); [ $? -eq 0 ] && ok "a section citation without a line number passes" || no "section citation" "$out"

skill '- `RunAsync` (`game/Tick.cs:3`) and loop (`:6`).'
out=$(run); [ $? -eq 1 ] && grep -q 'Tick.cs:6` - unanchored' <<<"$out" && ok "a continuation needs its own anchor" || no "continuation without anchor" "$out"

skill '- `TickOnce` (`game/Tick.cs:9`).'
out=$(run); grep -q 'line past the end (server:backend/game/Tick.cs has 7 lines at develop)' <<<"$out" && ok "line past the end of the file fails" || no "past the end" "$out"

skill '- `Shared` (`Shared.cs:1`).'
out=$(run); grep -q 'ambiguous file: server:backend/game/Shared.cs, server:backend/other/Shared.cs' <<<"$out" && ok "ambiguous basename fails with candidates" || no "ambiguous" "$out"

skill '- `Gone` (`game/Missing.cs:1`).'
out=$(run); grep -q 'no such file at server develop' <<<"$out" && ok "missing file fails" || no "missing file" "$out"

skill '- `TickOnce` (`:6`) with no file before it.' '- `RunAsync` (`game/Tick.cs:3`).'
out=$(run --offline); grep -q '`:6` - orphan continuation: it continues no file named earlier in its section' <<<"$out" \
  && ok "a bare :N with no file named earlier fails (not skipped)" || no "orphan continuation" "$out"
skill '## Tick (`game/Tick.cs`)' '' '- `RunAsync` (`:3`) in the first item.' '- `TickOnce` (`:6`) in a later item.'
out=$(run); [ $? -eq 0 ] && ok "a :N continues the file named in its section heading or an earlier list item" || no "section continuation" "$out"
skill '- `RunAsync` (`game/Tick.cs:3`).' '' '## Next section' '' '- `TickOnce` (`:6`).'
out=$(run --offline); grep -q '`:6` - orphan continuation' <<<"$out" && ok "a heading resets the continued file" || no "heading reset" "$out"

skill '- see game/Tick.cs:3 for the loop.'
out=$(run); grep -q 'line citation outside backticks' <<<"$out" && ok "a line citation outside backticks fails" || no "loose citation" "$out"

# drift: commit 20 lines before RunAsync on develop -> the citation drifts; --suggest names the new line
skill '- `RunAsync` (`game/Tick.cs:3`).'
{ printf 'class Tick {\n'; for i in $(seq 1 20); do printf '  // pad %s\n' "$i"; done; sed -n '2,$p' "$SRV/backend/game/Tick.cs"; } > "$TMP/t.cs"
cp "$TMP/t.cs" "$SRV/backend/game/Tick.cs"; gc "$SRV" commit -qam "move RunAsync"
out=$(run --suggest); [ $? -eq 1 ] && grep -q 'drift: `RunAsync` is not at the cited lines' <<<"$out" && grep -q 'suggest `game/Tick.cs:23`' <<<"$out" \
  && ok "moved symbol is drift, with the corrected citation" || no "drift" "$out"
skill '- `RunAsync` (`game/Tick.cs:23`).'
out=$(run); [ $? -eq 0 ] && ok "the suggested citation passes" || no "suggested citation" "$out"

# ref-based: an uncommitted change in the working tree is not read; --ref picks another ref
printf 'class Tick {}\n' > "$SRV/backend/game/Tick.cs"
out=$(run); [ $? -eq 0 ] && ok "uncommitted working-tree change is ignored (reads develop)" || no "worktree read" "$out"
gc "$SRV" checkout -q -- backend/game/Tick.cs
gc "$SRV" checkout -q -b feat/x; printf 'class Tick {\n  void RunAsync() {}\n}\n' > "$SRV/backend/game/Tick.cs"; gc "$SRV" commit -qam feat
out=$(run); [ $? -eq 0 ] && ok "a feature branch checked out does not change the default ref" || no "default ref" "$out"
out=$(run --ref server=HEAD); grep -q 'line past the end' <<<"$out" && ok "--ref server=HEAD reads the checked-out branch" || no "--ref" "$out"
gc "$SRV" checkout -q develop

# missing repo: SKIP, not FAIL; --offline needs no repos at all
skill '- `Bind` (`client:UI/Hud.cs:2`).'
mv "$CLI" "$TMP/cli-away"
out=$(run); [ $? -eq 0 ] && grep -q '^SKIP  repo client not present' <<<"$out" && ok "a missing repo is SKIP" || no "missing repo" "$out"
mv "$TMP/cli-away" "$CLI"
skill '- `RunAsync` (`game/Tick.cs:999`), loop (`:5`).'
out=$(RPGF_TEST_WS="$TMP/nowhere" run --offline); [ $? -eq 1 ] && grep -q 'Tick.cs:5` - unanchored' <<<"$out" && ! grep -q 'past the end' <<<"$out" \
  && grep -q 'checked offline' <<<"$out" && ok "--offline checks anchors only, without repos" || no "--offline" "$out"

out=$(run --skill nope); [ $? -eq 2 ] && ok "unknown skill is a usage error" || no "unknown skill" "$out"
echo "skill-citations tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
