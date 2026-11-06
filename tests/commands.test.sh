#!/usr/bin/env bash
# Slash commands: every commands/*.md is well-formed and calls factory-cmd.py with its own verb; the
# dispatcher validates arguments (exit 2 + usage) and really invokes the scripts (fixture workspace).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
CMD="$ROOT/scripts/factory-cmd.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
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
[ "$(ls "$ROOT"/commands/*.md | wc -l)" -eq 13 ] && ok "exactly 13 commands (status, route, check, doctor, domain, workflow, pipeline, ui, ui-figma, ui-components, ui-screen, ui-review, assetgen)" || no "command count"
# the usage text documents every command's verb
python3 -B "$CMD" --help 2>"$TMP/usage"
for f in "$ROOT"/commands/*.md; do
  n=$(basename "$f" .md)
  grep -qE "^  ([a-z-]+ [|] )*$n( |$)" "$TMP/usage" && ok "usage text documents '$n'" || no "usage text lacks '$n'"
done
# -- argument validation (exit 2, no script run)
for a in "" "bogus" "route" "route nosuchrepo x.go" "route server" "check" "check nosuchrepo" "status extra" "doctor extra" "route server x.go --lead" \
         "doctor --remote" "domain a b" "domain --bogus" "help extra" \
         "ui" "ui-figma" "ui-components" "ui-screen" "ui-review" "ui --project" "workflow" "workflow bogus spec.json" "pipeline" "pipeline bogus"          "assetgen" "assetgen bogus" "assetgen render --run x" "assetgen qa --run x" "assetgen manifest --run x" "assetgen resolve --purpose icon --out x.json"; do
  python3 -B "$CMD" $a >/dev/null 2>"$TMP/err"; rc=$?
  [ $rc -eq 2 ] && grep -q "status \[--remote\]" "$TMP/err" && ok "usage error -> exit 2: '$a'" || no "expected usage error for '$a' (rc=$rc)"
done
python3 -B "$CMD" domain nosuchdomain >/dev/null 2>"$TMP/err"; rc=$?
[ $rc -eq 2 ] && grep -q "unknown domain 'nosuchdomain'; domains: engineering | .*design" "$TMP/err" && ok "unknown domain -> exit 2 listing the registry domains" || no "unknown domain rc=$rc: $(head -1 "$TMP/err")"
# -- help: the discovery surface for agents and Codex (every verb, both forms)
out=$(python3 -B "$CMD" help); rc=$?
[ $rc -eq 0 ] && grep -q '^- domain \[<id>\] \[--json\]' <<<"$out" && grep -q 'e.g. /rpg-factory:domain design  |  python3 -B .*/scripts/factory-cmd.py domain design' <<<"$out" \
  && ok "help: text lists verbs with Claude and Codex forms (exit 0)" || no "help text rc=$rc: $(head -c 300 <<<"$out")"
python3 -B "$CMD" help --json >"$TMP/help.json"; rc=$?
[ $rc -eq 0 ] && jq -e '.schema == "rpg-factory.commands/1" and (.commands | length) == 14
  and all(.commands[]; .verb as $v | (.args | type) == "string" and (.read_only | type) == "boolean" and (.example | startswith($v))
          and (.codex | test("^python3 -B .*/scripts/factory-cmd.py " + $v + "$")))
  and ([.commands[] | select(.read_only | not) | .verb] == ["check", "pipeline"])
  and ([.commands[] | select(.claude == null) | .verb] == ["help"])' "$TMP/help.json" >/dev/null \
  && ok "help --json: rpg-factory.commands/1, every verb with args, read-only flag, example, both forms" || no "help --json: $(head -c 300 "$TMP/help.json")"
for f in "$ROOT"/commands/*.md; do
  n=$(basename "$f" .md)
  jq -e --arg n "$n" 'any(.commands[]; .verb == $n and .claude == "/rpg-factory:" + $n)' "$TMP/help.json" >/dev/null \
    && ok "help --json lists '$n' with its slash command" || no "help --json lacks '$n'"
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
grep -q "## Install" <<<"$out" && ! grep -qE "## Tripwire|--ack" <<<"$out" && grep -q "persistent state: $TMP/state" <<<"$out" && ok "doctor: install, state paths, no tripwire section" || no "doctor: $(tail -c 300 <<<"$out")"
# -- --json for status, route, check --status and doctor
jsonok() { jq -e "$2" >/dev/null 2>&1 <<<"$3" && ok "$1" || no "$1: $(head -c 300 <<<"$3")"; }
jsonok "status --json is valid JSON" 'has("pending") and has("freshness")' "$(cd "$WS" && python3 -B "$CMD" status --json)"
jsonok "route <repo> <path> --json is valid JSON" '.repos[0].routing.lead == "server-services"' "$(cd "$WS" && python3 -B "$CMD" route server backend/gateway/server/server.go --json)"
jsonok "route --domain design --json is valid JSON" '.domain.lead == "game-design"' "$(cd "$WS" && python3 -B "$CMD" route --domain design --json)"
jsonok "check --status --json is valid JSON" 'type == "object"' "$(cd "$WS" && python3 -B "$CMD" check server backend/gateway/server/server.go --status --json)"
jsonok "doctor --json: install, registry, workspace, repos, tools, hooks, dev_tools" \
  '.schema == "rpg-factory.doctor/1" and ([keys[]] | contains(["install","registry","workspace","repos","tools","hooks","dev_tools"]))
   and .registry.ok and .repos.server.present and (.repos.authoring.present | not) and .hooks.PreToolUse and (.dev_tools | type) == "array"' \
  "$(cd "$WS" && python3 -B "$CMD" doctor --json 2>/dev/null)"
# -- domain: overview and detail, without and with the optional authoring repo
out=$(cd "$WS" && python3 -B "$CMD" domain --json); rc=$?
reg_domains=$(jq -c '[.domains | keys[]] | sort' "$ROOT/registry.json")
[ $rc -eq 0 ] && jq -e --argjson d "$reg_domains" '.schema == "rpg-factory.domain/1" and ([.domains[].id] | sort) == $d and (.authoring_present | not)
  and all(.domains[]; .artifacts == null)' >/dev/null <<<"$out" && ok "domain --json without authoring: every registry domain, no artifact counts" || no "domain list rc=$rc: $(head -c 300 <<<"$out")"
out=$(cd "$WS" && python3 -B "$CMD" domain); rc=$?
[ $rc -eq 0 ] && grep -q '^- design \[game-design\]: repos authoring absent; artifacts: authoring repo absent$' <<<"$out" \
  && grep -q '^- engineering \[module ownership\]: repos server present, client present' <<<"$out" && ok "domain text: one line per domain" || no "domain text: $out"
out=$(cd "$WS" && python3 -B "$CMD" domain design --json); rc=$?
[ $rc -eq 0 ] && jq -e '.schema == "rpg-factory.domain/1" and .domain.lead == "game-design" and .domain.authoring.present == false
  and .domain.artifacts == null and (.domain.artifact_kinds | index("feature-spec")) and (.domain.human_gates | index("design-review"))
  and any(.domain.handoffs[]; .id == "feature-spec-to-ui-spec" and .from == "design/features/")
  and any(.domain.next[]; test("authoring repo is absent")) and any(.domain.next[]; . == "invoke rpg-factory:factory-core, then the lead rpg-factory:game-design")' >/dev/null <<<"$out" \
  && ok "domain design --json without authoring: lead, kinds, gates, handoffs, absent authoring in next" || no "domain design (absent) rc=$rc: $(head -c 400 <<<"$out")"
out=$(cd "$WS" && python3 -B "$CMD" domain engineering); rc=$?
[ $rc -eq 0 ] && grep -q '^- lead: none - routes by --repo/--paths' <<<"$out" && grep -q '/rpg-factory:route <repo> <path>' <<<"$out" && ! grep -q '^## Artifacts' <<<"$out" \
  && ok "domain engineering: module-ownership routing, no artifact section" || no "domain engineering: $out"
[ -z "$(git -C "$S" status --porcelain)" ] && ok "read-only commands left the fixture repo untouched" || no "fixture repo changed"
A="$WS/game-authoring"; mkdir -p "$A"; cp -R "$ROOT/tests/fixtures/dogfood/game-authoring/." "$A/"
git -C "$A" init -q -b main; git -C "$A" -c user.email=t@t -c user.name=t add -A; git -C "$A" -c user.email=t@t -c user.name=t commit -qm seed
out=$(cd "$WS" && python3 -B "$CMD" domain --json)
jq -e '.authoring_present and (.domains[] | select(.id == "design") | .artifacts) == {"draft": 1}
  and (.domains[] | select(.id == "ui") | .artifacts) == {} and (.domains[] | select(.id == "engineering") | .artifacts) == null' >/dev/null <<<"$out" \
  && ok "domain --json with authoring: artifact counts per domain" || no "domain list with authoring: $(head -c 400 <<<"$out")"
out=$(cd "$WS" && python3 -B "$CMD" domain design --json); rc=$?
[ $rc -eq 0 ] && jq -e '.domain.authoring.present and .domain.artifacts == {"draft": 1} and .domain.stale == [] and .domain.failing == []
  and .domain.human_required == [] and (.domain.quality | has("FAIL")) and any(.domain.next[]; test("workflow plan <spec.json>"))' >/dev/null <<<"$out" \
  && ok "domain design --json with authoring: domain_summary counts, stale, FAIL/HUMAN_REQUIRED, workflow next" || no "domain design (present) rc=$rc: $(head -c 400 <<<"$out")"
out=$(cd "$WS" && python3 -B "$CMD" domain design); rc=$?
[ $rc -eq 0 ] && grep -q '^- by status: draft 1$' <<<"$out" && grep -q '^- FAIL/BLOCKED: none; HUMAN_REQUIRED: none$' <<<"$out" && grep -q '^## Next$' <<<"$out" \
  && ok "domain design text: artifacts by status, FAIL/HUMAN_REQUIRED, Next" || no "domain design text: $out"
[ -z "$(git -C "$A" status --porcelain)" ] && ok "domain left the authoring repo untouched" || no "authoring repo changed"
# a downstream artifact with an outdated upstream revision, and an approved binding concept missing its approval
python3 -B - "$A" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); src = root / "design/concepts/GD-game-concept-001.artifact.json"
obj = json.loads(src.read_text(encoding="utf-8"))
down = dict(obj, id="GD-downstream-001", upstream=[{"id": "GD-game-concept-001", "rev": "0" * 40}])
(root / "design/concepts/GD-downstream-001.artifact.json").write_text(json.dumps(down), encoding="utf-8")
bad = dict(obj, id="GD-approved-001", status="approved", binding_values=True, spec={k: v for k, v in obj["spec"].items() if k != "concept"},
           acceptance=[{"id": "AC1", "text": "Concept is understandable", "verify": "review"}])
(root / "design/concepts/GD-approved-001.artifact.json").write_text(json.dumps(bad), encoding="utf-8")
PY
git -C "$A" -c user.email=t@t -c user.name=t add -A; git -C "$A" -c user.email=t@t -c user.name=t commit -qm "fixture: stale and gated"
out=$(cd "$WS" && python3 -B "$CMD" domain design --json); rc=$?
[ $rc -eq 0 ] && jq -e '.domain.artifacts == {"draft": 2, "approved": 1} and .domain.stale == ["GD-downstream-001"]
  and .domain.failing == ["GD-approved-001", "GD-downstream-001"] and .domain.human_required == ["GD-approved-001"] and .domain.quality.FAIL > 0
  and any(.domain.next[]; test("/rpg-factory:status")) and any(.domain.next[]; test("HUMAN_REQUIRED: a person approves GD-approved-001"))' >/dev/null <<<"$out" \
  && ok "domain design --json: stale, FAIL and HUMAN_REQUIRED artifacts with next steps (exit 0, read-only)" || no "domain design (gated) rc=$rc: $(jq -c "[.domain.artifacts,.domain.stale,.domain.failing,.domain.human_required,.domain.quality,.domain.next]" <<<"$out")"
cat >"$TMP/workflow.json" <<'EOF'
{"id":"demo","title":"Demo","goal":"Demo","targets":[{"kind":"feature-spec","sources":[],"acceptance":["Works"]}],"existing":[]}
EOF
out=$(cd "$WS" && python3 -B "$CMD" workflow plan "$TMP/workflow.json" --json 2>&1); rc=$?
[ "$rc" -eq 0 ] && python3 -c 'import json,sys; assert json.load(sys.stdin)["nodes"]' <<<"$out" && ok "workflow entry point dispatches plan" || no "workflow entry point rc=$rc: $(head -c 300 <<<"$out")"
out=$(python3 -B "$CMD" pipeline "planner --request 'add a crafting screen, then wire it' --runner orca" 2>/dev/null); rc=$?
# the Orca --spec is one line naming the spec file (under the test state dir), which holds the request verbatim
spec=$(python3 -c 'import os,pathlib,shlex,sys
args=shlex.split(sys.argv[1], posix=True); prompt=args[args.index("--spec")+1]
assert not any(c in prompt for c in "\r\n"), "multi-line --spec"
head, tail = "Read your task spec at ", " and follow it."
assert prompt.startswith(head) and tail in prompt, prompt
path = pathlib.Path(prompt[len(head):prompt.index(tail)])
state = pathlib.Path(os.environ["RPG_FACTORY_STATE_DIR"]).resolve()
assert state in path.resolve().parents, f"spec outside state dir: {path}"
print(path.read_text(encoding="utf-8"))' "$out" 2>&1)
[ "$rc" -eq 0 ] && [ "$(grep -c -- "--spec" <<<"$out")" -eq 1 ] && grep -qF "add a crafting screen, then wire it" <<<"$spec" && grep -q -- "--worktree current" <<<"$out" \
  && ok "pipeline entry point keeps the request text (one-line --spec, request verbatim in the spec file)" || no "pipeline entry point rc=$rc: $(head -c 300 <<<"$out") | $(head -c 300 <<<"$spec")"
printf '%s
' '{"schema":"rpg-factory.pipeline-plan/1","id":"cmd","title":"T","topic":"feat/core/cmd","tasks":[{"id":"a","repo":"nope","objective":"o","paths":["x/"],"acceptance":["a"]}]}' > "$TMP/pipeline-plan.json"
out=$(python3 -B "$CMD" pipeline status "$TMP/pipeline-plan.json" 2>&1); rc=$?
[ "$rc" -eq 1 ] && ! grep -q "pipeline needs" <<<"$out" && grep -qE "^Next: .* validate " <<<"$out" && ok "pipeline status is a pipeline verb (an invalid plan: exit 1, next is validate)" || no "pipeline status rc=$rc: $(head -c 300 <<<"$out")"
# -- assetgen: read-only assetgen.py verbs; the game layer of the workspace authoring repo is picked up by default
out=$(python3 -B "$CMD" assetgen list --kind purpose --json); rc=$?
[ $rc -eq 0 ] && jq -e '.schema == "rpg-factory.assetgen-list/1" and any(.entries[]; .id == "icon" and .layer == "core")' <<<"$out" >/dev/null   && ok "assetgen list: core purposes through factory-cmd (exit 0)" || no "assetgen list rc=$rc: $(head -c 300 <<<"$out")"
mkdir -p "$WS/game-authoring/assetgen/styles"
printf '%s
' '{"schema": "rpg-factory.assetgen-style/1", "title": "Game house style", "prefix": "p", "suffix": "s", "avoid": []}' > "$WS/game-authoring/assetgen/styles/house.json"
out=$(python3 -B "$CMD" assetgen "resolve --purpose icon --style house --json"); rc=$?
[ $rc -eq 0 ] && jq -e '.style.id == "house" and .style.layer == "game" and .purpose.id == "icon"' <<<"$out" >/dev/null   && ok "assetgen resolve (one quoted string): --authoring defaults to the workspace authoring repo's game layer" || no "assetgen resolve rc=$rc: $(head -c 300 <<<"$out")"
out=$(python3 -B "$CMD" assetgen lint 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "house.json" <<<"$out" && grep -qE "^assetgen lint: [0-9]+ PASS, [0-9]+ WARN, 0 FAIL" <<<"$out"   && ok "assetgen lint: core and game-layer data, 0 FAIL" || no "assetgen lint rc=$rc: $(tail -3 <<<"$out")"
python3 -B "$CMD" assetgen resolve --purpose icon --out "$TMP/spec.json" >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] && [ ! -e "$TMP/spec.json" ] && ok "assetgen resolve --out refused (exit 2, nothing written)" || no "assetgen resolve --out rc=$rc"
total=$((pass + fail)); echo "commands tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
