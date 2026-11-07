#!/usr/bin/env bash
# factory-pipeline.py on a throwaway workspace (a server repo and a Unity client project): tiers, plan validation
# (ownership, cycles, cross-model review, the no-worktree rule for Unity projects, exclusive resources), dispatch
# commands for Orca and the Agent fallback, verdicts and the READY_FOR_PR gate. Never touches the real workspace.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
P="$ROOT/scripts/factory-pipeline.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export RPG_FACTORY_AGENTS=claude,codex
export RPG_FACTORY_STATE_DIR="$TMP/state" TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws"
# hermetic inside an Orca terminal: no ORCA_* variable, so the default runner is print and --runner agent is allowed
# (the Orca-first cases below set them on purpose)
for v in $(compgen -e | grep '^ORCA_'); do unset "$v"; done
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"; T="$TMP/tool"
pass=0; fail=0
# expect <name> <rc> <grep-regex|-> <args...>: exit code and (optionally) a line of the combined output
expect() {
  local name="$1" want="$2" pat="$3"; shift 3
  local out rc; out=$(python3 -B "$P" "$@" 2>&1); rc=$?
  if [ "$rc" = "$want" ] && { [ "$pat" = - ] || grep -qE -- "$pat" <<<"$out"; }; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, want $want, pattern '$pat')"; sed 's/^/      /' <<<"$out" | head -30; fi
}
# refute <name> <grep-regex> <args...>: the output must NOT contain the pattern (exit code ignored)
refute() {
  local name="$1" pat="$2"; shift 2
  local out; out=$(python3 -B "$P" "$@" 2>&1)
  if grep -qE -- "$pat" <<<"$out"; then fail=$((fail + 1)); echo "FAIL  $name (found '$pat')"; sed 's/^/      /' <<<"$out" | head -20
  else pass=$((pass + 1)); echo "PASS  $name"; fi
}
# Match a rule in the persisted Orca spec, rather than the one-line launch prompt.
expect_spec() {
  local name="$1" pat="$2"; shift 2
  local out rc spec
  out=$(python3 -B "$P" "$@" 2>&1); rc=$?
  spec=$(python3 -c 'import pathlib,shlex,sys
args=shlex.split(sys.argv[1]); flag="--prompt" if "--prompt" in args else "--spec"
prompt=args[args.index(flag)+1]
assert prompt.startswith("Read your task spec at ") and prompt.endswith(" and follow it.")
print(pathlib.Path(prompt[len("Read your task spec at "):-len(" and follow it.")]).read_text(encoding="utf-8"))' "$out" 2>&1)
  if [ "$rc" = 0 ] && grep -qE -- "$pat" <<<"$spec"; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, pattern '$pat')"; head -20 <<<"$spec"; fi
}
# refute_spec <name> <grep-regex> <args...>: the persisted Orca spec must NOT contain the pattern (exit 0, spec read)
refute_spec() {
  local name="$1" pat="$2"; shift 2
  local out rc spec src
  out=$(python3 -B "$P" "$@" 2>&1); rc=$?
  spec=$(python3 -c 'import pathlib,shlex,sys
args=shlex.split(sys.argv[1]); flag="--prompt" if "--prompt" in args else "--spec"
prompt=args[args.index(flag)+1]
assert prompt.startswith("Read your task spec at ") and prompt.endswith(" and follow it.")
print(pathlib.Path(prompt[len("Read your task spec at "):-len(" and follow it.")]).read_text(encoding="utf-8"))' "$out" 2>&1); src=$?
  if [ "$rc" = 0 ] && [ "$src" = 0 ] && [ -n "$spec" ] && ! grep -qE -- "$pat" <<<"$spec"; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, spec rc=$src, found or no spec '$pat')"; head -20 <<<"$spec"; fi
}
gi() { local d="$1"; shift; git -C "$d" -c user.email=t@t -c user.name=t "$@"; }
plan() { printf '%s\n' "$2" > "$TMP/$1.json"; echo "$TMP/$1.json"; }

for d in "$S" "$C" "$T"; do mkdir -p "$d"; git init -q -b develop "$d"; done
mkdir -p "$C/ProjectSettings" "$T/ProjectSettings"; echo "m_EditorVersion: 6000.0.0f1" > "$C/ProjectSettings/ProjectVersion.txt"
cp "$C/ProjectSettings/ProjectVersion.txt" "$T/ProjectSettings/"
for d in "$S" "$C"; do echo base > "$d/README.md"; gi "$d" add -A; gi "$d" commit -qm base; done
HEAD='"schema":"rpg-factory.pipeline-plan/1","id":"demo","title":"Demo change","topic":"feat/core/demo","deliver":"pr"'

echo "-- validate"
OK=$(plan ok "{$HEAD,\"tasks\":[
 {\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c1\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c2\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/B/\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"}]}")
expect "valid plan: OK, waves printed" 0 "^OK$" validate "$OK"
X=$(plan x "{$(sed 's/"id":"demo"/"id":"_planner"/' <<<"$HEAD"),\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]}]}")
expect "plan id _planner is reserved for the planner's specs" 1 "ERROR plan id ._planner. is reserved" validate "$X"
expect "two tasks of a Unity project never share a wave" 0 "^Wave 2: c2$" validate "$OK"
expect "the Unity project is named as no-worktree" 0 "No worktree .*: client" validate "$OK"
X=$(plan overlap "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/x.go\"],\"acceptance\":[\"a\"]}]}")
expect "overlapping owned paths are an error" 1 "ERROR tasks a and b own overlapping paths" validate "$X"
X=$(plan overlap-dep "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/x.go\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]}]}")
expect "overlap ordered by a dependency is fine" 0 "^Wave 2: b$" validate "$X"
X=$(plan cycle "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"deps\":[\"b\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"y/\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]}]}")
expect "dependency cycle is an error" 1 "ERROR dependency cycle among a, b" validate "$X"
X=$(plan same "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\",\"reviewer\":\"codex\"}]}")
expect "reviewer of the implementer's model is an error" 1 "cross-model review needs the pair \(claude\)" validate "$X"
X=$(plan wt "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/\"],\"acceptance\":[\"a\"],\"worktree\":true}]}")
expect "worktree: true in a Unity project is an error" 1 "takes no worktree" validate "$X"
X=$(plan res "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"n\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"resources\":[\"unity-test\"]}]}")
expect "two Unity test users in one wave: queue warning" 0 "WARN  wave 1: a, n share .unity-test." validate "$X"
X=$(plan unknown "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"nope\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "unknown repo is an error" 1 "neither a registry repo nor in plan.repos" validate "$X"
TOOL=$(plan tool "{$HEAD,\"repos\":{\"tool\":{\"path\":\"tool\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"tool\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "unregistered repo with ProjectVersion.txt is a no-worktree repo" 0 "No worktree .*: tool" validate "$TOOL"

echo "-- subplan validate"
# subplan <name> <task> <subtasks JSON>: a subplan of the plan $OK (named relative to the subplan file)
subplan() { printf '{"schema":"rpg-factory.pipeline-subplan/1","plan":"ok.json","task":"%s","subtasks":%s}\n' "$2" "$3" > "$TMP/sub-$1.json"; echo "$TMP/sub-$1.json"; }
SP=$(subplan ok gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","reviewer":"codex"},
 {"id":"s2","objective":"o","paths":["backend/gateway/b.go"],"implementer":"codex","acceptance":["a"],"checks":["c"]},
 {"id":"s3","objective":"o","paths":["backend/gateway/a/x.go"],"implementer":"claude","deps":["s1","s2"]}]')
expect "valid subplan: OK" 0 "^OK$" subplan validate "$SP"
expect "valid subplan: parallel subtasks share wave 1" 0 "^Wave 1: s1, s2$" subplan validate "$SP"
expect "valid subplan: overlap ordered by deps runs in wave 2" 0 "^Wave 2: s3$" subplan validate "$SP"
expect "valid subplan --json: waves and no errors" 0 '"errors": \[\]' subplan validate "$SP" --json
X=$(subplan overlap gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/"],"implementer":"claude"},
 {"id":"s2","objective":"o","paths":["backend/gateway/x.go"],"implementer":"codex"}]')
expect "overlapping subtask paths are an error" 1 "ERROR subtasks s1 and s2 own overlapping paths \(backend/gateway/ ~ backend/gateway/x.go\)" subplan validate "$X"
X=$(subplan outside gw '[{"id":"s1","objective":"o","paths":["backend/gatewayx/a.go"],"implementer":"claude"}]')
expect "subtask path outside the task's owned paths is an error" 1 "ERROR subtask s1: path backend/gatewayx/a.go is outside the owned paths of task gw" subplan validate "$X"
X=$(subplan wider gw '[{"id":"s1","objective":"o","paths":["backend/"],"implementer":"claude"}]')
expect "subtask path wider than the owned path is an error" 1 "path backend/ is outside the owned paths" subplan validate "$X"
X=$(subplan same gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"codex","reviewer":"codex"}]')
expect "same-model reviewer is an error" 1 "ERROR subtask s1: reviewer .codex. is the implementer's model; cross-model review needs the pair \(claude\)" subplan validate "$X"
X=$(subplan noimpl gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"gpt"}]')
expect "implementer that is no pipeline agent is an error" 1 "implementer .gpt. is not a pipeline agent" subplan validate "$X"
X=$(subplan cycle gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","deps":["s2"]},
 {"id":"s2","objective":"o","paths":["backend/gateway/b/"],"implementer":"claude","deps":["s1"]}]')
expect "subtask dependency cycle is an error" 1 "ERROR dependency cycle among s1, s2" subplan validate "$X"
X=$(subplan unkdep gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","deps":["zz"]}]')
expect "unknown subtask dependency is an error" 1 "ERROR subtask s1: unknown dependency zz" subplan validate "$X"
X=$(subplan unktask nope '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]')
expect "unknown task is an error" 1 "ERROR unknown task nope: plan demo has gw, c1, c2" subplan validate "$X"
X=$(subplan other gw '[{"id":"s1","task":"c1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]')
expect "a subtask of another task is an error" 1 "ERROR subtask s1: belongs to task c1, not gw" subplan validate "$X"
EX=$(plan ex "{$HEAD,\"tasks\":[{\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/\"],\"exclusions\":[\"backend/shared/proto/\"],\"acceptance\":[\"a\"]}]}")
X=$(subplan excl gw '[{"id":"s1","objective":"o","paths":["backend/shared/proto/wire.proto"],"implementer":"claude"}]')
expect "--plan overrides the subplan's plan: a path inside a task exclusion is an error" 1 "path backend/shared/proto/wire.proto overlaps an exclusion of task gw" subplan validate "$X" --plan "$EX"
expect "without --plan the subplan's own plan applies: that path is outside gw" 1 "path backend/shared/proto/wire.proto is outside the owned paths" subplan validate "$X"
printf '{"schema":"rpg-factory.pipeline-subplan/1","task":"gw","subtasks":[]}\n' > "$TMP/sub-noplan.json"
expect "a subplan without plan and --plan is a usage error" 2 "names no .plan. and no --plan" subplan validate "$TMP/sub-noplan.json"
expect "a missing subplan file is a usage error" 2 "cannot read subplan" subplan validate "$TMP/sub-missing.json"
if python3 - "$ROOT" "$TMP" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-subplan.schema.json", encoding="utf-8"))
assert schema["properties"]["schema"]["const"] == "rpg-factory.pipeline-subplan/1"
for name in ("ok", "same", "cycle", "excl"):
    value = json.load(open(f"{sys.argv[2]}/sub-{name}.json", encoding="utf-8"))
    errors = m.schema_errors(value, schema, schema)
    assert not errors, (name, errors)
bad = json.load(open(f"{sys.argv[2]}/sub-ok.json", encoding="utf-8"))
bad["subtasks"][0]["owner"] = "x"
del bad["subtasks"][1]["implementer"]
assert m.schema_errors(bad, schema, schema), "an unknown field and a missing implementer must fail the schema"
PY
then pass=$((pass + 1)); echo "PASS  pipeline-subplan.schema.json is valid JSON and matches the test subplans"
else fail=$((fail + 1)); echo "FAIL  pipeline-subplan.schema.json"; fi
# path safety: owned paths are compared by spelling, so absolute and `..` paths never reach containment or overlap
X=$(subplan escape gw '[{"id":"s1","objective":"o","paths":["backend/gateway/../../outside.cs"],"implementer":"claude"}]')
expect "a subtask path leaving the task with .. is an error" 1 "ERROR subtask s1: path backend/gateway/../../outside.cs has a .\.\.. segment" subplan validate "$X"
X=$(subplan abs gw '[{"id":"s1","objective":"o","paths":["/etc/passwd"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["C:/x/backend/gateway/a.go"],"implementer":"codex"}]')
expect "an absolute subtask path is an error" 1 "ERROR subtask s1: path /etc/passwd is absolute" subplan validate "$X"
expect "a drive-letter subtask path is an error" 1 "ERROR subtask s2: path C:/x/backend/gateway/a.go is absolute" subplan validate "$X"
X=$(subplan exbypass gw '[{"id":"s1","objective":"o","paths":["backend/x/../shared/proto/wire.proto"],"implementer":"claude"}]')
expect "a .. path cannot bypass a task exclusion" 1 "ERROR subtask s1: path backend/x/../shared/proto/wire.proto has a" subplan validate "$X" --plan "$EX"
refute "a .. path is not reported OK" "^OK$" subplan validate "$X" --plan "$EX"
X=$(subplan ovbypass gw '[{"id":"s1","objective":"o","paths":["backend/gateway/b.go"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["backend/gateway/a/../b.go"],"implementer":"codex"}]')
expect "a .. path cannot hide an overlap" 1 "ERROR subtask s2: path backend/gateway/a/../b.go has a" subplan validate "$X"
X=$(subplan dot gw '[{"id":"s1","objective":"o","paths":["backend/gateway/b.go"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["backend//gateway/./b.go"],"implementer":"codex"}]')
expect "./ and // segments are normalized before the overlap check" 1 "ERROR subtasks s1 and s2 own overlapping paths" subplan validate "$X"
X=$(plan dotdot "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/../x/\"],\"exclusions\":[\"/abs/\"],\"acceptance\":[\"a\"]}]}")
expect "plan validate rejects a .. owned path" 1 "ERROR task a: path backend/../x/ has a" validate "$X"
expect "plan validate rejects an absolute exclusion" 1 "ERROR task a: exclusion /abs/ is absolute" validate "$X"
expect "dispatch --paths rejects a .. path" 2 "--paths backend/gateway/../../outside.cs has a" dispatch "$OK" --task gw --phase implement --paths backend/gateway/../../outside.cs
expect "dispatch --paths rejects an absolute path" 2 "--paths C:/etc/x is absolute" dispatch "$OK" --task gw --phase implement --paths C:/etc/x
# malformed subtasks are errors, never silently dropped
X=$(subplan null gw '[null]')
expect "a null subtask is an error" 1 "ERROR subtask #1: must be an object, got null" subplan validate "$X"
refute "a null subtask is not OK" "^OK$" subplan validate "$X"
X=$(subplan mixed gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"},"s2",3]')
expect "a string subtask is an error" 1 'ERROR subtask #2: must be an object, got "s2"' subplan validate "$X"
expect "a number subtask is an error" 1 "ERROR subtask #3: must be an object, got 3" subplan validate "$X"
X=$(subplan types gw '[{"id":"s1","objective":"o","paths":"backend/gateway/a/","implementer":"claude","deps":"s2"},{"id":["s2"],"objective":"o","paths":[1],"implementer":"codex"}]')
expect "paths that are not a list is an error" 1 'ERROR subtask s1: .paths. must be a list of strings, got "backend/gateway/a/"' subplan validate "$X"
expect "deps that are not a list is an error" 1 "ERROR subtask s1: .deps. must be a list of strings" subplan validate "$X"
expect "a non-string id is an error" 1 "ERROR subtask #2: .id. must be a string" subplan validate "$X"
expect "a non-string path is an error" 1 "ERROR subtask #2: .paths. must be a list of strings, got \[1\]" subplan validate "$X"
printf '{"schema":"rpg-factory.pipeline-subplan/1","plan":"ok.json","task":"gw","subtasks":{"id":"s1"}}\n' > "$TMP/sub-obj.json"
expect "subtasks that are not a list is an error" 1 "ERROR .subtasks. must be a non-empty list of objects" subplan validate "$TMP/sub-obj.json"
# one id rule (the schemas' pattern) for subplan validate, dispatch and verdict; unknown keys are errors (additionalProperties)
X=$(subplan badid gw '[{"id":"ui/settings","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"},{"id":"fix ui","objective":"o","paths":["backend/gateway/b/"],"implementer":"claude"}]')
expect "a subtask id with / is an error" 1 'ERROR subtask "ui/settings": id is not an id' subplan validate "$X"
expect "a subtask id with a space is an error" 1 'ERROR subtask "fix ui": id is not an id' subplan validate "$X"
refute "a malformed subtask id is never OK" "^OK$" subplan validate "$X"
expect "dispatch refuses the subplan with a malformed id" 1 "subplan is invalid.*id is not an id" dispatch "$OK" --task gw --phase implement --subplan "$X" --subtask ui/settings
expect "verdict refuses the same id (one rule)" 2 "--subtask is the id of a subtask of a plan task \(letters, digits" verdict "$OK" --task gw --phase review --sha abc1234 --by codex --state PASS --subtask ui/settings
X=$(subplan keys gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","owner":"me"}]')
expect "an unknown subtask key is an error" 1 "ERROR subtask s1: unknown key .owner." subplan validate "$X"
printf '{"schema":"rpg-factory.pipeline-subplan/1","plan":"ok.json","task":"gw","extra":1,"subtasks":[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]}\n' > "$TMP/sub-top.json"
expect "an unknown subplan key is an error" 1 "ERROR unknown key .extra." subplan validate "$TMP/sub-top.json"
X=$(plan badtid "{$HEAD,\"tasks\":[{\"id\":\"a/b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "plan validate: a task id with / is an error (same rule)" 1 'ERROR task id "a/b" is not an id' validate "$X"
X=$(plan intclash "{$HEAD,\"tasks\":[{\"id\":\"integration_server\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "plan validate: task integration_<repo> would share the integration QA's verdict file" 1 "ERROR task id .integration_server. is reserved: the integration QA of repo server" validate "$X"
# a no-worktree repo runs its subtasks one after another: the registry flag and the Unity marker
X=$(subplan par gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["backend/gateway/b/"],"implementer":"codex"}]')
expect "disjoint subtasks of a worktree repo share a wave" 0 "^Wave 1: s1, s2$" subplan validate "$X"
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["repos"]["server"]["worktrees"]=False; r["repos"]["server"]["worktrees_reason"]="test flag"; json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$ROOT/registry.json" "$TMP/reg-nowt.json"
expect "registry worktrees=false: disjoint subtasks run one per wave" 0 "^Wave 2: s2$" --registry "$TMP/reg-nowt.json" subplan validate "$X"
expect "registry worktrees=false: the reason is printed" 0 "One subtask at a time \(no worktree: test flag\)" --registry "$TMP/reg-nowt.json" subplan validate "$X"
refute "registry worktrees=false: never two subtasks in one wave" "^Wave 1: s1, s2$" --registry "$TMP/reg-nowt.json" subplan validate "$X"
X=$(subplan marker t '[{"id":"s1","objective":"o","paths":["x/a/"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["x/b/"],"implementer":"codex"}]')
expect "Unity marker (unregistered repo): disjoint subtasks run one per wave" 0 "^Wave 2: s2$" subplan validate "$X" --plan "$TOOL"
expect "Unity marker: the marker is named" 0 "One subtask at a time \(no worktree: ProjectSettings/ProjectVersion.txt present" subplan validate "$X" --plan "$TOOL"
expect "Unity marker --json: the serial reason is reported" 0 '"serial": "ProjectSettings' subplan validate "$X" --plan "$TOOL" --json
# placement: shared (default) or child (an Orca child of the task worktree, with a reason); never child without worktrees
SPC=$(subplan child gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","placement":"shared"},
 {"id":"s2","objective":"o","paths":["backend/gateway/b.go"],"implementer":"codex","placement":"child","reason":"runs the full suite","checks":["c"]}]')
expect "placement shared and child (with a reason): OK" 0 "^OK$" subplan validate "$SPC"
X=$(subplan child-noreason gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","placement":"child"}]')
expect "placement child without a reason is an error" 1 "ERROR subtask s1: placement child needs a .reason." subplan validate "$X"
X=$(subplan child-bad gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","placement":"top"}]')
expect "an unknown placement is an error" 1 "ERROR subtask s1: placement .top. is not one of shared, child" subplan validate "$X"
X=$(subplan child-unity t '[{"id":"s1","objective":"o","paths":["x/a/"],"implementer":"claude","placement":"child","reason":"r"}]')
expect "placement child in a Unity project is an error" 1 "ERROR subtask s1: placement child in repo .tool., which takes no worktree" subplan validate "$X" --plan "$TOOL"
expect "placement child with registry worktrees=false is an error" 1 "placement child in repo .server., which takes no worktree \(test flag\)" --registry "$TMP/reg-nowt.json" subplan validate "$SPC"
if python3 - "$ROOT" "$SPC" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-subplan.schema.json", encoding="utf-8"))
value = json.load(open(sys.argv[2], encoding="utf-8"))
assert not m.schema_errors(value, schema, schema)
value["subtasks"][0]["placement"] = "top"
assert m.schema_errors(value, schema, schema), "an unknown placement must fail the schema"
PY
then pass=$((pass + 1)); echo "PASS  pipeline-subplan.schema.json knows placement and reason"
else fail=$((fail + 1)); echo "FAIL  pipeline-subplan.schema.json placement"; fi
# a UTF-8 BOM (PowerShell's Out-File / Set-Content) is no read error, for plans and subplans
printf '\xef\xbb\xbf' > "$TMP/bom.json"; cat "$OK" >> "$TMP/bom.json"
printf '\xef\xbb\xbf{"schema":"rpg-factory.pipeline-subplan/1","plan":"bom.json","task":"gw","subtasks":[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]}\n' > "$TMP/sub-bom.json"
expect "a plan with a UTF-8 BOM validates" 0 "^OK$" validate "$TMP/bom.json"
expect "a subplan (and its plan) with a UTF-8 BOM validates" 0 "^OK$" subplan validate "$TMP/sub-bom.json"
expect "dispatch reads a plan with a UTF-8 BOM" 0 "^Task lead for task gw" dispatch "$TMP/bom.json" --task gw --phase lead
expect "the task-lead spec names the subplan schema, plan and task" 0 "pipeline-subplan.schema.json; .plan. is .*ok.json, .task. is gw" dispatch "$OK" --task gw --phase lead

echo "-- dispatch"
expect "server task lead: Orca creates the task worktree from the base on the task branch" 0 "^orca worktree create --name feat/core/demo-gw --repo '?path:[^ ]*rpg-mmo-server'? --base-branch develop --branch feat/core/demo-gw --no-parent " dispatch "$OK" --task gw --phase lead --runner orca
refute "the task lead is no nested Orca worker (no worker-start)" "^orca orchestration worker-start" dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead of a claude-implementer task is claude" 0 "--no-parent --agent claude --prompt " dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead of a codex-implementer task is still claude (pipeline.lead_agent)" 0 "^orca agent launch --agent claude " dispatch "$OK" --task c2 --phase lead --runner orca
refute "task lead of a codex-implementer task is never codex" "^orca .*--agent codex" dispatch "$OK" --task c2 --phase lead --runner orca
expect "--agent codex on --phase lead warns" 0 "the task lead is claude \(lead_agent\); --agent codex is ignored" dispatch "$OK" --task gw --phase lead --runner orca --agent codex
expect "--agent codex on --phase lead still prints --agent claude" 0 "--no-parent --agent claude --prompt " dispatch "$OK" --task gw --phase lead --runner orca --agent codex
refute "--agent codex on --phase lead never launches codex" "^orca .*--agent codex" dispatch "$OK" --task gw --phase lead --runner orca --agent codex
expect "the codex task's implement session keeps its implementer" 0 "^orca orchestration worker-start .*--agent codex" dispatch "$OK" --task c2 --phase implement --runner orca
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["pipeline"].pop("lead_agent",None); json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$ROOT/registry.json" "$TMP/reg-nolead.json"
expect "registry without pipeline.lead_agent: the task lead defaults to claude" 0 "^orca agent launch --agent claude " --registry "$TMP/reg-nolead.json" dispatch "$OK" --task c2 --phase lead --runner orca
expect "task lead creates its own Orca Run" 0 "create your OWN Run \(.orca orchestration run-create" dispatch "$OK" --task gw --phase lead
expect "task lead reports to the run lead's Orca run" 0 "orca orchestration send --to run:R42 --type status --subject .task done: gw" dispatch "$OK" --task gw --phase lead --report-to R42
expect "--report-to accepts Orca's run:<id> form" 0 "orca orchestration send --to run:R42 --type status" dispatch "$OK" --task gw --phase lead --report-to run:R42
refute "--report-to run:<id> never doubles the prefix" "run:run:" dispatch "$OK" --task gw --phase lead --report-to run:R42
expect "--report-to goes only with the lead" 2 "--report-to .* goes with --phase lead" dispatch "$OK" --task gw --phase implement --report-to R42
for pat in '"owned_paths": \[' '"backend/gateway/"' '"branch": "feat/core/demo-gw"' '"acceptance": \[' "subplan validate <subplan.json>" \
  "ONE fresh session in this task worktree" "--phase implement --subplan <subplan.json> --subtask <id>" "does NOT commit \(one shared index\)" \
  "you commit it with explicit paths" "Cross-model review .<dispatch> --phase review" "\(codex for claude" \
  "SAME_MODEL fallback" "--phase qa --sha <HEAD>" "FAIL goes to a fresh fix session" "worker-release" \
  "<dispatch> = .<pipeline> dispatch <plan> --task gw." "placement child .*merge that branch into feat/core/demo-gw and remove the child at once" \
  "never create or remove a child worktree while a full tests/run-all.sh runs" "verdict --subtask <id>" \
  "branch feat/core/demo-gw, HEAD SHA, your Orca Run id" "the moment it reports, its candidate is superseded or it stops - not at task end" "status <plan> --orca-run <your run id>" \
  "Never push, tag, merge into the integration branch or remove the task worktree"; do
  expect "task-lead spec: $pat" 0 "$pat" dispatch "$OK" --task gw --phase lead
done
expect "Unity task lead: an agent launched in the main checkout" 0 "^orca agent launch --agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task c1 --phase lead --runner orca
refute "Unity task lead never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase lead --runner orca
refute "Unity task lead in the agent fallback never creates a worktree" '"isolation"|Create your own worktree' dispatch "$OK" --task c1 --phase lead --runner agent
expect "Unity task lead runs subtasks one after another" 0 "Subtasks, review and QA run one after another" dispatch "$OK" --task c1 --phase lead
refute "Unity review never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c2 --phase review --sha abc1234 --runner orca
refute "Unity per-task qa never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase qa --sha abc1234 --runner orca
expect "Unity task lead works on the integration branch in the main checkout" 0 "No worktree: .*on branch feat/core/demo;" dispatch "$OK" --task c1 --phase lead
refute "Unity task lead rule 7 never mentions removing a worktree" "^7\..*remove(s)? the (task )?worktree" dispatch "$OK" --task c1 --phase lead
expect "Unity task lead rule 7: the main checkout is never removed" 0 "^7\. Never push, merge or tag: .*the main checkout is never removed" dispatch "$OK" --task c1 --phase lead
refute "Unity task lead prompt has no double period after the reason" "\.\. " dispatch "$OK" --task c1 --phase lead
# no_new_worktree <name> <args...>: exit 1, names the branch and `--phase lead`, and `git worktree list` is unchanged
no_new_worktree() {
  local name="$1"; shift; local before after out rc
  before=$(git -C "$S" worktree list --porcelain); out=$(python3 -B "$P" "$@" 2>&1); rc=$?; after=$(git -C "$S" worktree list --porcelain)
  if [ "$rc" = 1 ] && grep -q "has the task branch feat/core/demo-gw checked out" <<<"$out" && grep -q -- "--phase lead" <<<"$out" \
     && ! grep -q "new-top-level" <<<"$out" && [ "$before" = "$after" ]; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
}
no_new_worktree "implement without the task worktree: error, no worktree" dispatch "$OK" --task gw --phase implement --runner orca
no_new_worktree "review without the task worktree: error, no worktree" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
no_new_worktree "per-task qa without the task worktree: error, no worktree" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
no_new_worktree "agent fallback without the task worktree: error too" dispatch "$OK" --task gw --phase implement --runner agent
expect "client implement: main checkout, no new worktree" 0 "--agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task c1 --phase implement --runner orca
refute "client implement has no creation flags" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase implement --runner orca
expect "Unity implement without --paths is a sub-session that does not commit" 0 "Do NOT commit, stage or stash" dispatch "$OK" --task c1 --phase implement
refute "Unity implement never prints a committing worker" "commit explicit|Implementation worker \(" dispatch "$OK" --task c1 --phase implement
refute "Unity implement in the agent fallback never commits or creates a worktree" "commit explicit|isolation|Create your own worktree" dispatch "$OK" --task c1 --phase implement --runner agent
expect_spec "registry worktrees=false: implement does not commit" "Do NOT commit, stage or stash" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
refute "registry worktrees=false: implement never creates a worktree" "new-top-level|--base-branch|worktree create" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
refute_spec "registry worktrees=false: the implement spec never commits" "commit explicit" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
expect_spec "Unity marker (unregistered repo): implement does not commit" "Do NOT commit, stage or stash" dispatch "$TOOL" --task t --phase implement --runner orca
refute "Unity marker: implement never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$TOOL" --task t --phase implement --runner orca
refute_spec "Unity marker: the implement spec never commits" "commit explicit" dispatch "$TOOL" --task t --phase implement --runner orca
expect "next Unity task warns until the previous task has QA PASS" 0 "task c1 has no QA PASS yet" dispatch "$OK" --task c2 --phase implement
expect "review of codex's code goes to claude, read-only in the main checkout" 0 "--agent claude --worktree '?path:" dispatch "$OK" --task c2 --phase review --sha abc1234 --runner orca
expect "review needs a candidate SHA" 2 "review needs --sha" dispatch "$OK" --task gw --phase review
expect "per-task qa in the Unity project" 0 "task c1" dispatch "$OK" --task c1 --phase qa --sha abc1234
expect "agent fallback task lead for another repo: creates the task worktree from the base" 0 "Create your own worktree first: .*-b feat/core/demo-gw develop" dispatch "$OK" --task gw --phase lead --runner agent
refute "agent fallback for the Unity project has no isolation" '"isolation"' dispatch "$OK" --task c1 --phase implement --runner agent
# the task lead's worktree exists: every session of the task joins it
git -C "$S" worktree add -q "$TMP/demo-gw" -b feat/core/demo-gw develop 2>/dev/null
WT="--worktree '?path:[^' ]*demo-gw'?"
expect "implement joins the task worktree" 0 "--agent claude $WT" dispatch "$OK" --task gw --phase implement --runner orca
refute "implement never creates a worktree" "new-top-level|--base-branch" dispatch "$OK" --task gw --phase implement --runner orca
expect "implement sub-session does not commit" 0 "Do NOT commit, stage or stash: one shared index" dispatch "$OK" --task gw --phase implement
expect "implement sub-session reports changed paths and check counts to the task lead" 0 "Report to the task lead: changed paths" dispatch "$OK" --task gw --phase implement
expect "subtask paths narrow the sub-session" 0 '"subtask_paths": \[' dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go
expect "a subtask session may name its own model" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go --agent codex --runner orca
expect "subtask paths inside a task exclusion are refused" 2 "--paths backend/shared/proto/wire.proto overlap the exclusions of task gw: backend/shared/proto/" dispatch "$EX" --task gw --phase implement --paths backend/shared/proto/wire.proto
expect "subtask paths containing a task exclusion are refused" 2 "--paths backend/shared/ overlap the exclusions of task gw" dispatch "$EX" --task gw --phase implement --paths backend/gateway/x.go backend/shared/
refute "an excluded subtask path never reaches a worker" "subtask_paths|orca orchestration" dispatch "$EX" --task gw --phase implement --paths backend/shared/proto/wire.proto --runner orca
expect "subtask paths outside the owned paths are refused" 2 "--paths backend/other outside the owned paths of task gw" dispatch "$OK" --task gw --phase implement --paths backend/other
expect "--paths goes only with implement" 2 "--paths .* goes with --phase implement" dispatch "$OK" --task gw --phase review --sha abc1234 --paths backend/gateway/x.go
expect "review of claude's code goes to codex, in the task worktree" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
refute "review never creates a worktree" "new-top-level|--base-branch" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
expect "review checks HEAD is the candidate in the shared worktree" 0 "who keeps HEAD at the candidate: first check .git rev-parse HEAD. equals it" dispatch "$OK" --task gw --phase review --sha abc1234
expect "per-task qa in a worktree repo runs in the task worktree" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
refute "per-task qa never creates a worktree" "new-top-level|--base-branch" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
expect "per-task qa names the task" 0 "QA worker .*branch feat/core/demo-gw, task gw" dispatch "$OK" --task gw --phase qa --sha abc1234
expect "a second task lead resumes in the existing task worktree" 0 "^orca agent launch --agent claude $WT" dispatch "$OK" --task gw --phase lead --runner orca
expect "agent fallback for a codex reviewer starts a fresh Claude session" 0 '"subagent_type": "general-purpose"' dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
expect "agent fallback for a codex reviewer says SAME_MODEL in the prompt" 0 'SAME_MODEL: this session was planned for codex; the Agent-tool fallback runs Claude only' dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
expect "agent fallback for a codex reviewer says SAME_MODEL on stderr" 0 "starts a fresh Claude session for this codex session: SAME_MODEL" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
refute "agent fallback never uses the codex subagent" "codex:codex-rescue" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
refute "agent fallback for a claude session is not SAME_MODEL" "SAME_MODEL: this session" dispatch "$OK" --task gw --phase implement --runner agent
expect "agent fallback for a codex subtask session: Claude, SAME_MODEL" 0 'SAME_MODEL: this session was planned for codex' dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go --agent codex --runner agent
expect "agent fallback names the existing task worktree" 0 "Placement: work in the existing checkout .*demo-gw" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
# Every Orca phase emits one physical command line, with the exact full spec in persistent state. Include
# both new and resumed leads, narrowed subtasks, integration QA and planner requests containing newlines.
if python3 -B - "$P" "$OK" "$TMP" <<'PY'
import json, os, pathlib, shlex, subprocess, sys
p, plan, tmp = sys.argv[1:]
root = pathlib.Path(os.environ["RPG_FACTORY_STATE_DIR"])
def same(a, b):  # TEMP may be an 8.3 short path (windows CI: RUNNER~1); compare real, case-folded paths
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
saved = {}
def check(args, key="demo", note=""):
    def run(runner):
        r = subprocess.run([sys.executable, "-B", p, *args, "--runner", runner], capture_output=True, text=True)
        assert r.returncode == 0, (args, r.stderr)
        return r.stdout
    command = run("orca")
    assert len(command.splitlines()) == 1, repr(command)
    argv = shlex.split(command)
    assert all("\n" not in arg and "\r" not in arg for arg in argv), argv
    flag = "--prompt" if "--prompt" in argv else "--spec"
    prompt = argv[argv.index(flag) + 1]
    prefix, suffix = "Read your task spec at ", " and follow it." + note
    assert prompt.startswith(prefix) and prompt.endswith(suffix), prompt
    path = pathlib.Path(prompt[len(prefix):-len(suffix)])
    assert path.is_absolute() and same(path.parent, root / "pipeline" / key / "specs"), path
    full = path.read_text(encoding="utf-8")
    assert "\n" in full and full == run("print").split("\n", 1)[1][:-1], full  # remove only print()'s newline
    saved[str(path)] = full
    assert prompt == prefix + str(path) + suffix, prompt
    return path
for task in ("gw", "c1"):
    for phase in ("lead", "implement", "review", "qa"):
        args = ["dispatch", plan, "--task", task, "--phase", phase]
        check(args + (["--sha", "abc1234"] if phase in ("review", "qa") else []))
first = check(["dispatch", plan, "--task", "gw", "--phase", "implement", "--paths", "backend/gateway/a.go"])
second = check(["dispatch", plan, "--task", "gw", "--phase", "implement", "--paths", "backend/gateway/b.go"])
assert first != second, "subtasks must not overwrite each other's specs"
check(["dispatch", plan, "--task", "integration:client", "--phase", "qa", "--sha", "abc1234"])
fresh = pathlib.Path(tmp) / "fresh.json"
value = json.loads(pathlib.Path(plan).read_text(encoding="utf-8"))
value["topic"] += "-gw"  # the existing task worktree also serves as this fixture's integration checkout
value["tasks"] = [value["tasks"][0]]
fresh.write_text(json.dumps(value), encoding="utf-8")
check(["dispatch", str(fresh), "--task", "gw", "--phase", "lead"])  # no task branch/worktree yet
check(["dispatch", str(fresh), "--task", "integration:server", "--phase", "qa", "--sha", "abc1234"])
# the planner's one line also names the request, whitespace runs collapsed; the spec keeps it verbatim
request = "add a thing\n  with a\tsecond requirement\n"
spec = check(["planner", "--request", request], "_planner", " Request: add a thing with a second requirement")
assert f"Request: {request}" in spec.read_text(encoding="utf-8")
# A second prompt must never alter a spec an already-launched session has yet to read.
assert all(pathlib.Path(path).read_text(encoding="utf-8") == full for path, full in saved.items())
PY
then pass=$((pass + 1)); echo "PASS  Orca phases use one-line prompts and complete, immutable persistent specs"
else fail=$((fail + 1)); echo "FAIL  Orca one-line prompts and persistent specs"; fi
echo "-- dispatch: subplan subtasks and Orca child worktrees"
CH="^orca orchestration worker-start .*--worktree new-child --name feat/core/demo-gw--"
expect "subplan placement child: worker-start --worktree new-child from the task branch" 0 "${CH}s2 --base-branch feat/core/demo-gw .*--json$" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect "the child subtask runs its implementer (codex)" 0 "worker-start .*--agent codex --worktree new-child" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect "a child command says the run-all rule (stderr)" 0 "never create or remove a child worktree while a full tests/run-all.sh runs \(shared .git/config\)" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec commits on the child branch" "Commit on your child branch with explicit paths" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec: the task lead merges and removes the child at once" "the task lead merges it into feat/core/demo-gw and removes the child at once" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec says the run-all rule" "never create or remove a child worktree while a full tests/run-all.sh runs" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the subtask's paths are in the spec" '"subtask_paths": \["backend/gateway/b.go"\]' dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child's reason is in the spec" '"placement_reason": "runs the full suite"' dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect "subplan placement shared: the task worktree" 0 "--agent claude $WT" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s1 --runner orca
expect_spec "a shared subtask does not commit" "Do NOT commit, stage or stash" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s1 --runner orca
expect "--placement shared overrides the subtask's child" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --placement shared --runner orca
expect "a subtask review goes to its implementer's pair (claude for codex)" 0 "worker-start .*--agent claude --worktree new-child --name feat/core/demo-gw--s2--review-abc1234 --base-branch abc1234 " dispatch "$OK" --task gw --phase review --sha abc1234 --subplan "$SPC" --subtask s2 --runner orca
expect_spec "a child review checks HEAD is the candidate in its child" "Orca child worktree of .*demo-gw created at it" dispatch "$OK" --task gw --phase review --sha abc1234 --subplan "$SPC" --subtask s2 --runner orca
expect_spec "a subtask review records with verdict --subtask" "record with .verdict --subtask s2." dispatch "$OK" --task gw --phase review --sha abc1234 --subplan "$SPC" --subtask s2 --runner orca
expect "--placement child on qa: a frozen child at the SHA" 0 "${CH}qa-abc1234 --base-branch abc1234 " dispatch "$OK" --task gw --phase qa --sha abc1234 --placement child --runner orca
# review, QA and implement of one child subtask get distinct Orca names (they run at once on one candidate)
names=$(for ph in "implement" "review --sha abc1234" "qa --sha abc1234"; do
  # shellcheck disable=SC2086
  python3 -B "$P" dispatch "$OK" --task gw --phase $ph --subplan "$SPC" --subtask s2 --runner orca 2>/dev/null | grep -oE -- "--name [^ ]+"; done)
if [ "$(sort -u <<<"$names" | wc -l)" = 3 ] && grep -qx -- "--name feat/core/demo-gw--s2--qa-abc1234" <<<"$names"; then
  pass=$((pass + 1)); echo "PASS  implement, review and QA children of one subtask have distinct names"
else fail=$((fail + 1)); echo "FAIL  child names collide: $names"; fi
out=$(python3 -B "$P" dispatch "$OK" --task gw --phase qa --sha abc1234 --placement child --runner agent 2>/dev/null)
if jq -e '.isolation == "worktree" and (.prompt | test("never create or remove a worktree yourself")) and (.prompt | test("git worktree add") | not)' <<<"$out" >/dev/null
then pass=$((pass + 1)); echo "PASS  --runner agent child placement: the Agent tool isolates, the session never runs git worktree add"
else fail=$((fail + 1)); echo "FAIL  --runner agent child placement"; head -c 600 <<<"$out"; fi
expect "a child command says where to run it (stderr)" 0 "run the command from .*demo-gw \(Orca makes the child of the worktree it runs in\)" dispatch "$OK" --task gw --phase qa --sha abc1234 --placement child --runner orca
expect "--subtask without --subplan is a usage error" 2 "--subplan and --subtask go together" dispatch "$OK" --task gw --phase implement --subtask s2
expect "an unknown subtask is a usage error" 2 "unknown subtask zz: subplan has s1, s2" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask zz
expect "a subplan of another task is a usage error" 2 "splits task gw, not c1" dispatch "$OK" --task c1 --phase implement --subplan "$SPC" --subtask s1
# child in a no-worktree repo: usage error, nothing on stdout
for args in "--task c1 --phase implement" "--task c1 --phase qa --sha abc1234" "--task c1 --phase lead" "--task integration:client --phase qa --sha abc1234"; do
  # shellcheck disable=SC2086
  out=$(python3 -B "$P" dispatch "$OK" $args --placement child --runner orca 2>/dev/null); rc=$?
  err=$(python3 -B "$P" dispatch "$OK" $args --placement child --runner orca 2>&1 >/dev/null)
  if [ "$rc" = 2 ] && [ -z "$out" ] && grep -q "takes no worktree" <<<"$err"; then pass=$((pass + 1)); echo "PASS  child in the Unity project ($args): usage error, nothing printed"
  else fail=$((fail + 1)); echo "FAIL  child in the Unity project ($args) (rc=$rc)"; head -5 <<<"$out$err"; fi
done
git -C "$S" worktree remove "$TMP/demo-gw"; git -C "$S" branch -q -D feat/core/demo-gw
expect "new task worktree without an integration checkout: --no-parent fallback" 0 "^orca worktree create --name feat/core/demo-gw .*--branch feat/core/demo-gw --no-parent --agent claude " dispatch "$OK" --task gw --phase lead --runner orca
refute "new task worktree without an integration checkout: no --parent-worktree" "--parent-worktree" dispatch "$OK" --task gw --phase lead --runner orca
expect "new task worktree without an integration checkout: stderr note" 0 "has the integration branch feat/core/demo checked out: the task worktree is created with --no-parent" dispatch "$OK" --task gw --phase lead --runner orca
expect "lead --placement child without the integration checkout: same --no-parent fallback" 0 "--branch feat/core/demo-gw --no-parent --agent claude " dispatch "$OK" --task gw --phase lead --placement child --runner orca
# integration QA joins the checkout of plan.topic; without one it is an error and no worktree is created
before=$(git -C "$S" worktree list --porcelain); out=$(python3 -B "$P" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca 2>&1); rc=$?
if [ "$rc" = 1 ] && grep -q "no worktree of .* has the integration branch feat/core/demo checked out" <<<"$out" && grep -q "No worktree was created" <<<"$out" \
   && ! grep -q "new-top-level" <<<"$out" && [ "$before" = "$(git -C "$S" worktree list --porcelain)" ]; then pass=$((pass + 1)); echo "PASS  integration QA without the integration checkout: error, no worktree"
else fail=$((fail + 1)); echo "FAIL  integration QA without the integration checkout (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
git -C "$S" worktree add -q "$TMP/demo-int" -b feat/core/demo develop 2>/dev/null
expect "integration QA joins the integration checkout of plan.topic" 0 "--agent codex --worktree '?path:[^' ]*demo-int'?" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
refute "integration QA never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
expect "integration QA checks HEAD is the candidate in the shared checkout" 0 "You share the integration checkout .*demo-int with the run lead" dispatch "$OK" --task integration:server --phase qa --sha abc1234
expect "new task worktree: an Orca child of the integration checkout by default" 0 "^orca worktree create --name feat/core/demo-gw .*--branch feat/core/demo-gw --parent-worktree '?path:[^' ]*demo-int'? --agent claude " dispatch "$OK" --task gw --phase lead --runner orca
refute "new task worktree with an integration checkout has no --no-parent" "--no-parent" dispatch "$OK" --task gw --phase lead --runner orca
expect "lead --placement shared: the task worktree stays top-level (--no-parent)" 0 "--branch feat/core/demo-gw --no-parent --agent claude " dispatch "$OK" --task gw --phase lead --placement shared --runner orca
refute "lead --placement shared has no --parent-worktree" "--parent-worktree" dispatch "$OK" --task gw --phase lead --placement shared --runner orca
expect "lead --placement child (redundant): the same Orca child of the integration checkout" 0 "^orca worktree create --name feat/core/demo-gw .*--branch feat/core/demo-gw --parent-worktree '?path:[^' ]*demo-int'? --agent claude " dispatch "$OK" --task gw --phase lead --placement child --runner orca
refute "lead --placement child has no --no-parent" "--no-parent" dispatch "$OK" --task gw --phase lead --placement child --runner orca
expect "lead --placement child says the run-all rule (stderr)" 0 "never create or remove a child worktree while a full tests/run-all.sh runs" dispatch "$OK" --task gw --phase lead --placement child --runner orca
expect "integration QA --placement child: a child of the integration checkout at the SHA" 0 "^orca orchestration worker-start .*--worktree new-child --name feat/core/demo--qa-abc1234 --base-branch abc1234 " dispatch "$OK" --task integration:server --phase qa --sha abc1234 --placement child --runner orca
expect "integration QA in a child: the command runs from the integration checkout (stderr)" 0 "run the command from .*demo-int " dispatch "$OK" --task integration:server --phase qa --sha abc1234 --placement child --runner orca
expect_spec "integration QA in a child checks HEAD in its child" "Orca child worktree of .*demo-int created at it" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --placement child --runner orca
git -C "$S" worktree remove "$TMP/demo-int"; git -C "$S" branch -q -D feat/core/demo
expect "integration QA in the Unity project: main checkout" 0 "--worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner orca
expect "planner runs in the lead's checkout (no worktree)" 0 "--worktree current" planner --request "add a thing" --runner orca

echo "-- tier"
ctx() { printf '%s\n' "$2" > "$TMP/ctx-$1.json"; echo "$TMP/ctx-$1.json"; }
X=$(ctx s '{"repos":[{"repo":"server","touched":["server.gateway"],"files":[{"path":"a","source":"given"}],"contracts":[],"generated_hits":[]}]}')
expect "one module, one file: S" 0 '"tier": "S"' tier --json --context-json "$X"
X=$(ctx m '{"repos":[{"repo":"server","touched":["server.gateway","server.shared"],"files":[{"path":"a","source":"given"}],"contracts":[],"generated_hits":[]}]}')
expect "two modules: M" 0 "^Tier: M" tier --context-json "$X"
X=$(ctx l '{"repos":[{"repo":"server","touched":["server.proto"],"files":[{"path":"a","source":"given"}],"contracts":[{"id":"wire-generated"}],"generated_hits":[]}]}')
expect "a contract: L" 0 "above M: contract wire-generated" tier --context-json "$X"
X=$(ctx l2 '{"repos":[{"repo":"server","touched":["server.a"],"files":[{"path":"a","source":"given"}],"contracts":[],"generated_hits":[]},{"repo":"client","touched":["client.a"],"files":[{"path":"b","source":"given"}],"contracts":[],"generated_hits":[]}]}')
expect "two repos: L" 0 "^Tier: L" tier --context-json "$X"

echo "-- verdict and gate"
# srv/cli: plan.repos aliases of the fixture checkouts (unregistered: no run-checks); cli is a Unity project by its marker
G=$(plan gate "{$HEAD,\"repos\":{\"srv\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"},\"cli\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"gw\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c1\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c2\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"./Assets/B\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"}]}")
expect "no integration branch: NOT_READY" 1 "BLOCKER srv: integration branch feat/core/demo does not exist" gate "$G"
gi "$S" checkout -qb feat/core/demo; mkdir -p "$S/backend/gateway"; echo x > "$S/backend/gateway/a.go"; gi "$S" add -A; gi "$S" commit -qm "feat(gateway): a"
SG=$(git -C "$S" rev-parse HEAD)
gi "$C" checkout -qb feat/core/demo; mkdir -p "$C/Assets/A" "$C/Assets/B"; echo a > "$C/Assets/A/a.cs"; gi "$C" add -A; gi "$C" commit -qm "feat(ui): a"
C1=$(git -C "$C" rev-parse HEAD); echo b > "$C/Assets/B/b.cs"; gi "$C" add -A; gi "$C" commit -qm "feat(ui): b"; C2=$(git -C "$C" rev-parse HEAD)
v() { python3 -B "$P" verdict "$G" "$@" >/dev/null || echo "verdict failed: $*"; }
expect "no verdicts yet: blockers name review and QA" 1 "BLOCKER gw: no review verdict" gate "$G"
expect "verdict rejects an unknown state" 2 "--state must be one of" verdict "$G" --task gw --phase review --sha "$SG" --by codex --state GREEN
expect "verdict rejects a SHA that is not a commit of the repo" 2 "is not a commit of repo srv" verdict "$G" --task gw --phase review --sha deadbeef1 --by codex --state PASS
expect "review verdicts are per task" 2 "review verdicts are per task" verdict "$G" --task integration:srv --phase review --sha "$SG" --by codex --state PASS
expect "per-task qa verdict of a worktree repo is recorded (the task lead's QA)" 0 "recorded qa PASS for gw" verdict "$G" --task gw --phase qa --sha "$SG" --by codex --state PASS
expect "a per-task qa verdict does not replace the integration QA" 1 "BLOCKER integration:srv: no qa verdict" gate "$G"
v --task gw --phase review --sha "$SG" --by claude --state PASS
expect "same-model review blocks" 1 "BLOCKER gw: reviewed by claude, cross-model review needs codex" gate "$G"
expect "same-model review accepted only with --allow-same-model" 1 "NOTE    gw: review SAME_MODEL \(claude\) accepted" gate "$G" --allow-same-model
v --task gw --phase review --sha "$SG" --by codex --state PASS
v --task c1 --phase review --sha "$C1" --by codex --state PASS
v --task c2 --phase review --sha "$C2" --by claude --state PASS
v --task integration:srv --phase qa --sha "$SG" --by codex --state PASS
v --task integration:cli --phase qa --sha "$C2" --by codex --state PASS
# subtask reviews and per-candidate records never replace the task review the gate reads
VD="$RPG_FACTORY_STATE_DIR/pipeline/demo"
expect "verdict --subtask records the subtask's own review" 0 "recorded review FAIL for gw subtask s2 at .*gw@s2__review.json" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state FAIL --subtask s2
expect "a non-pair task review at the reviewed SHA keeps the pair's record" 0 "kept the codex review of gw .*kept per candidate only" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state FAIL
if jq -e '.by == "codex" and .state == "PASS"' "$VD/gw__review.json" >/dev/null && jq -e '.subtask == "s2" and .state == "FAIL"' "$VD/gw@s2__review.json" >/dev/null \
   && [ -f "$VD/gw__review__${SG:0:12}__codex.json" ] && [ -f "$VD/gw__review__${SG:0:12}__claude.json" ] && [ -f "$VD/gw@s2__review__${SG:0:12}__claude.json" ]
then pass=$((pass + 1)); echo "PASS  verdict --subtask never overwrites the task review; every verdict is kept per candidate"
else fail=$((fail + 1)); echo "FAIL  verdict records"; ls "$VD" | sed 's/^/      /'; fi
expect "--subtask goes with a plan task" 2 "--subtask is the id of a subtask" verdict "$G" --task integration:srv --phase qa --sha "$SG" --by codex --state PASS --subtask s2
expect "Unity tasks need their own QA, one after another" 1 "BLOCKER c1: no qa verdict" gate "$G"
v --task c1 --phase qa --sha "$C1" --by codex --state PASS
v --task c2 --phase qa --sha "$C1" --by codex --state PASS
expect "per-task QA on a commit without the reviewed one blocks" 1 "BLOCKER c2: QA ran on .* does not contain the reviewed commit" gate "$G"
v --task c2 --phase qa --sha "$C2" --by codex --state PASS
# every task and integration verdict PASS, but the current subtask s2 review FAIL still blocks gate and status
expect "a current subtask review FAIL blocks the gate: NOT_READY" 1 "BLOCKER gw: subtask s2 review FAIL at .* by claude" gate "$G"
expect "status names the subtask FAIL and starts the task lead" 0 "note: subtask s2 review FAIL" status "$G"
refute "status offers no gate while a subtask FAIL is open" "^Next: .* gate " status "$G"
python3 -B "$P" verdict "$G" --task gw --phase qa --sha "$SG" --by codex --state FAIL --subtask s3 >/dev/null
expect "a subtask QA FAIL blocks the gate" 1 "BLOCKER gw: subtask s3 qa FAIL" gate "$G"
# verdict file names: task "a__sub-b" and subtask b of task a never share a file (the old <task>__sub-<id> did)
X=$(plan coll "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"coll\",\"title\":\"Coll\",\"topic\":\"feat/core/coll\",
 \"repos\":{\"srv\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"ca/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"a__sub-b\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"cb/\"],\"acceptance\":[\"a\"]}]}")
CVD="$RPG_FACTORY_STATE_DIR/pipeline/coll"
git -C "$S" branch -q feat/core/coll "$SG"
python3 -B "$P" verdict "$X" --task a --phase review --sha "$SG" --by claude --state FAIL --subtask b >/dev/null
python3 -B "$P" verdict "$X" --task a__sub-b --phase review --sha "$SG" --by codex --state PASS >/dev/null
if jq -e '.task == "a" and .subtask == "b" and .state == "FAIL"' "$CVD/a@b__review.json" >/dev/null    && jq -e '.task == "a__sub-b" and .state == "PASS" and (has("subtask") | not)' "$CVD/a__sub-b__review.json" >/dev/null    && [ -f "$CVD/a@b__review__${SG:0:12}__claude.json" ] && [ -f "$CVD/a__sub-b__review__${SG:0:12}__codex.json" ]
then pass=$((pass + 1)); echo "PASS  task a__sub-b and subtask b of task a keep their own verdict files"
else fail=$((fail + 1)); echo "FAIL  verdict file collision"; ls "$CVD" | sed 's/^/      /'; fi
expect "the subtask FAIL blocks its own task a" 1 "BLOCKER a: subtask b review FAIL" gate "$X" --no-run-checks
refute "task a__sub-b is not blocked by subtask b of task a" "BLOCKER a__sub-b: subtask|a__sub-b: no review verdict" gate "$X" --no-run-checks
# an older <task>__sub-<id> record still counts for its own task and subtask
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r.update(subtask="c",state="FAIL"); json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$CVD/a@b__review.json" "$CVD/a__sub-c__review.json"
expect "a legacy subtask record of task a still blocks it" 1 "BLOCKER a: subtask c review FAIL" gate "$X" --no-run-checks
python3 -B "$P" verdict "$X" --task a --phase review --sha "$SG" --by codex --state PASS --subtask c >/dev/null
refute "a new-style subtask PASS supersedes the legacy FAIL for that phase" "subtask c review FAIL" gate "$X" --no-run-checks
# Other phases retain their legacy evidence until that phase has a new-style record too.
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["phase"]="qa"; json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$CVD/a__sub-c__review.json" "$CVD/a__sub-c__qa.json"
expect "a new-style review does not supersede a legacy QA FAIL" 1 "BLOCKER a: subtask c qa FAIL" gate "$X" --no-run-checks
v --task gw --phase review --sha "$SG" --by claude --state PASS --subtask s2
v --task gw --phase qa --sha "$SG" --by codex --state PASS --subtask s3
# late results: a PASS on an older candidate (SG~1) never resolves a FAIL on the newer SG; a PASS on SG resolves it, and
# a late FAIL on the older candidate then changes nothing
SA=$(git -C "$S" rev-parse "$SG~1")
v --task gw --phase review --sha "$SG" --by claude --state FAIL --subtask s4
v --task gw --phase review --sha "$SA" --by claude --state PASS --subtask s4
expect "a late subtask PASS on an older candidate keeps the newer FAIL: NOT_READY" 1 "BLOCKER gw: subtask s4 review FAIL at ${SG:0:10} by claude" gate "$G"
expect "status keeps the newer subtask FAIL after a late older PASS" 0 "note: subtask s4 review FAIL at ${SG:0:10}" status "$G"
v --task gw --phase review --sha "$SG" --by claude --state PASS --subtask s4
v --task gw --phase review --sha "$SA" --by claude --state FAIL --subtask s4
refute "a late subtask FAIL on an older candidate does not reopen the newer PASS" "subtask s4" gate "$G"
# a fix left on an unmerged child branch: its PASS on a descendant of the integration HEAD resolves nothing
SC=$(git -C "$S" commit-tree "$SG^{tree}" -p "$SG" -m "fix(gateway): child"); git -C "$S" branch -q gw-child-fix "$SC"
v --task gw --phase review --sha "$SG" --by claude --state FAIL --subtask s5
v --task gw --phase review --sha "$SC" --by claude --state PASS --subtask s5
expect "a subtask PASS on an unmerged child commit keeps the FAIL on the integration HEAD: NOT_READY" 1 "BLOCKER gw: subtask s5 review FAIL at ${SG:0:10} by claude" gate "$G"
expect "status keeps the subtask FAIL while its fix is on an unmerged child" 0 "note: subtask s5 review FAIL at ${SG:0:10}" status "$G"
git -C "$S" branch -q -D gw-child-fix
v --task gw --phase review --sha "$SG" --by claude --state PASS --subtask s5
expect "all verdicts PASS on the integrated tree: READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "manual fallback for an available model is refused" 2 "fallback codex is available now" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state PASS --fallback codex
expect "refused fallback leaves paired evidence intact" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "mark codex down after its implementation was reviewed" 0 "MODEL_UNAVAILABLE" agents "$G" --down codex --reason 401
expect "cross-model review survives implementer becoming unavailable" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "clear codex runtime failure" 0 "codex: available" agents "$G" --up codex
# a fallback is stamped only from the review dispatch of that candidate, never from availability at verdict time
RPG_FACTORY_AGENTS=claude v --task c1 --phase review --sha "$C1" --by claude --state PASS
if ! grep -q '"fallback"' "$VD/c1__review__${C1:0:12}__claude.json"; then pass=$((pass + 1)); echo "PASS  single claude verdict without a fallback review dispatch stamps no fallback"
else fail=$((fail + 1)); echo "FAIL  single claude verdict without a fallback review dispatch stamps no fallback"; fi
# dr <task> <sha>: dispatch the review (records the reviewer and any fallback); gw joins a temporary task worktree
dr() {
  if [ "$1" = gw ]; then gi "$S" worktree add -q -b feat/core/demo-gw "$TMP/gate-gw" "$2"; fi
  python3 -B "$P" dispatch "$G" --task "$1" --phase review --sha "$2" --runner orca >/dev/null 2>&1 || echo "dispatch failed: $*"
  if [ "$1" = gw ]; then gi "$S" worktree remove --force "$TMP/gate-gw"; gi "$S" branch -q -D feat/core/demo-gw; fi
}
RPG_FACTORY_AGENTS=claude dr gw "$SG"; RPG_FACTORY_AGENTS=claude dr c1 "$C1"; RPG_FACTORY_AGENTS=claude dr c2 "$C2"
RPG_FACTORY_AGENTS=claude expect "single claude records the dispatched fallback" 0 "recorded review PASS" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state PASS
RPG_FACTORY_AGENTS=claude v --task c1 --phase review --sha "$C1" --by claude --state PASS
RPG_FACTORY_AGENTS=claude v --task c2 --phase review --sha "$C2" --by claude --state PASS
RPG_FACTORY_AGENTS=claude expect "single claude fallback gate accepted" 0 "SAME_MODEL \(fallback: codex unavailable\)" gate "$G"
expect "fallback evidence stays SAME_MODEL when both models return" 0 "SAME_MODEL \(fallback: codex unavailable\)" gate "$G"
RPG_FACTORY_AGENTS=codex dr gw "$SG"; RPG_FACTORY_AGENTS=codex dr c1 "$C1"; RPG_FACTORY_AGENTS=codex dr c2 "$C2"
RPG_FACTORY_AGENTS=codex expect "single codex records the dispatched fallback" 0 "recorded review PASS" verdict "$G" --task gw --phase review --sha "$SG" --by codex --state PASS
RPG_FACTORY_AGENTS=codex v --task c1 --phase review --sha "$C1" --by codex --state PASS
RPG_FACTORY_AGENTS=codex v --task c2 --phase review --sha "$C2" --by codex --state PASS
RPG_FACTORY_AGENTS=codex expect "single codex fallback gate accepted" 0 "SAME_MODEL \(fallback: claude unavailable\)" gate "$G"
v --task c1 --phase review --sha "$C1" --by codex --state PASS
v --task c2 --phase review --sha "$C2" --by claude --state PASS
expect "restore paired review" 0 "recorded review PASS" verdict "$G" --task gw --phase review --sha "$SG" --by codex --state PASS
expect "mark model down" 0 "MODEL_UNAVAILABLE: revoked" agents "$G" --down codex --reason revoked
expect "restore model availability" 0 "codex: available" agents "$G" --up codex

expect "READY prints the PR command against the base branch" 0 "gh pr create --base develop --head feat/core/demo" gate "$G"
cp "$G" "$TMP/gate.bak"; sed -i 's/"objective":"o","paths":\["backend/"objective":"changed","paths":["backend/' "$G"
expect "a changed task in the plan makes its verdicts STALE" 1 "gw: review verdict is STALE - the plan" gate "$G"
cp "$TMP/gate.bak" "$G"
git -C "$C" worktree add -q "$TMP/client-wt" -b feat/core/demo-c1 2>/dev/null
expect "a pipeline worktree of the Unity project blocks" 1 "no-worktree repo has pipeline worktrees" gate "$G"
git -C "$C" worktree remove "$TMP/client-wt"; git -C "$C" branch -q -D feat/core/demo-c1
echo s > "$S/stray.txt"; gi "$S" add stray.txt; gi "$S" commit -qm "chore: stray"
expect "a change outside every owned path blocks" 1 "BLOCKER srv: changes outside every task's owned paths: stray.txt" gate "$G"
gi "$S" rm -q stray.txt; gi "$S" commit -qm "chore: drop stray"
echo y >> "$S/backend/gateway/a.go"; gi "$S" commit -qam "fix(gateway): after review"
expect "a change to owned paths after review makes it STALE" 1 "BLOCKER gw: review is STALE" gate "$G"
expect "and the QA on the old HEAD is STALE" 1 "BLOCKER srv: QA is STALE" gate "$G"
echo dirty > "$S/untracked.txt"
expect "an unclean integration tree blocks" 1 "integration tree .* has uncommitted changes" gate "$G"
rm "$S/untracked.txt"
SG2=$(git -C "$S" rev-parse HEAD)
v --task gw --phase review --sha "$SG2" --by codex --state PASS
v --task gw --phase review --sha "$SG2" --by claude --state PASS --subtask s2
v --task integration:srv --phase qa --sha "$SG2" --by codex --state PASS
N=$(plan none "$(sed 's/"deliver":"pr"/"deliver":"none"/' "$G")")
expect "deliver none: READY but no push or PR command" 0 "deliver is not .pr.: stop here" gate "$N"
refute "deliver none prints no gh pr create" "gh pr create" gate "$N"
R=$(plan reg "{$(sed 's/"id":"demo"/"id":"reg"/' <<<"$HEAD"),\"tasks\":[{\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]}]}")
python3 -B "$P" verdict "$R" --task gw --phase review --sha "$SG2" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$R" --task integration:server --phase qa --sha "$SG2" --by codex --state PASS >/dev/null
expect "--no-run-checks never delivers: UNVERIFIED" 1 "^Gate: UNVERIFIED" gate "$R" --no-run-checks
refute "UNVERIFIED prints no gh pr create" "gh pr create" gate "$R" --no-run-checks

echo "-- cleanup"
expect "no worktree or task branch left: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
expect "an integrated task worktree is LEFTOVER with its remove command" 1 "git -C .* worktree remove .*srv-gw" cleanup "$G"
expect "and its merged branch is deleted with -d" 1 "branch -d feat/core/demo-gw" cleanup "$G"
expect "every run reminds to release worker sessions" 1 "orca orchestration worker-release --dispatch" cleanup "$G"
echo dirty > "$TMP/srv-gw/wip.txt"
expect "a worktree with uncommitted work is kept and named" 1 "KEPT  srv: worktree .* has uncommitted changes" cleanup "$G"
rm "$TMP/srv-gw/wip.txt"; git -C "$S" worktree remove "$TMP/srv-gw"; git -C "$S" branch -q -d feat/core/demo-gw
gi "$S" branch feat/core/demo-x develop; gi "$S" checkout -q feat/core/demo-x; echo z > "$S/z.txt"; gi "$S" add z.txt; gi "$S" commit -qm z; gi "$S" checkout -q feat/core/demo
expect "an unintegrated task branch is kept, not deleted" 1 "KEPT  srv: branch feat/core/demo-x is not in feat/core/demo" cleanup "$G"
refute "an unintegrated task branch gets no branch -d" "branch -d feat/core/demo-x" cleanup "$G"
gi "$S" branch -q -D feat/core/demo-x
expect "after removal: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
# a leftover Orca child of the task worktree (branch and directory <task branch>--<subtask>): status and cleanup name it
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/feat-core-demo-gw--s2" -b feat/core/demo-gw--s2 feat/core/demo-gw 2>/dev/null
echo c > "$TMP/feat-core-demo-gw--s2/backend/gateway/c.go"; gi "$TMP/feat-core-demo-gw--s2" add backend/gateway/c.go; gi "$TMP/feat-core-demo-gw--s2" commit -qm "feat(gateway): c"
expect "cleanup lists a leftover child as a child of its task" 1 "KEPT  srv: child of gw: leftover child worktree .*feat-core-demo-gw--s2 \(feat/core/demo-gw--s2\): merge it into feat/core/demo-gw" cleanup "$G"
refute "an unmerged child gets no remove command" "^  orca worktree rm .*--s2" cleanup "$G"
python3 -B "$P" status --json "$G" > "$TMP/status-child.json" 2>&1
if jq -e '(.tasks[] | select(.id == "gw") | .children) as $c | ($c | length) == 1 and ($c[0].branch == "feat/core/demo-gw--s2") and ($c[0].merged == false)' "$TMP/status-child.json" >/dev/null \
   && jq -e '.tasks[] | select(.id == "gw") | any(.notes[]; test("leftover child worktree .*--s2.*orca worktree rm --worktree"))' "$TMP/status-child.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  status lists the leftover child with a note"
else fail=$((fail + 1)); echo "FAIL  status children"; head -c 1500 "$TMP/status-child.json"; fi
if python3 - "$ROOT" "$TMP/status-child.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status --json with children matches the status schema"
else fail=$((fail + 1)); echo "FAIL  status --json children schema"; fi
gi "$TMP/srv-gw" merge -q --no-ff feat/core/demo-gw--s2 -m "merge s2"
expect "a merged child gets its orca worktree rm command" 1 "^  orca worktree rm --worktree '?path:[^ ]*feat-core-demo-gw--s2'?$" cleanup "$G"
echo wip > "$TMP/feat-core-demo-gw--s2/wip.txt"
expect "a merged child with uncommitted work is kept and named" 1 "KEPT  srv: child of gw: .*feat-core-demo-gw--s2 has uncommitted changes - not removed" cleanup "$G"
refute "a dirty child gets no remove command" "orca worktree rm .*--s2" cleanup "$G"
rm "$TMP/feat-core-demo-gw--s2/wip.txt"
cp "$TMP/feat-core-demo-gw--s2/.git" "$TMP/s2-gitfile"; echo "gitdir: $TMP/nowhere" > "$TMP/feat-core-demo-gw--s2/.git"
expect "a child whose git status fails is kept and named" 1 "KEPT  srv: child of gw: .git status. failed in .*feat-core-demo-gw--s2 - not removed" cleanup "$G"
refute "a child whose git status fails gets no remove command" "orca worktree rm .*--s2" cleanup "$G"
cp "$TMP/s2-gitfile" "$TMP/feat-core-demo-gw--s2/.git"
git -C "$S" worktree remove "$TMP/feat-core-demo-gw--s2"; git -C "$S" worktree remove "$TMP/srv-gw"
git -C "$S" branch -q -D feat/core/demo-gw--s2 feat/core/demo-gw
expect "child and task worktree removed: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
specs="$RPG_FACTORY_STATE_DIR/pipeline/demo/specs"; n=$(ls "$specs"/*.md 2>/dev/null | wc -l)
expect "cleanup names the plan's dispatch specs as kept state, still CLEAN" 0 "STATE $n spec file\(s\) in .*demo.specs .*delete by hand" cleanup "$G"
if [ "$n" -gt 0 ] && [ "$(ls "$specs"/*.md | wc -l)" = "$n" ]; then pass=$((pass + 1)); echo "PASS  cleanup never deletes the spec files"
else fail=$((fail + 1)); echo "FAIL  cleanup spec files ($n before)"; fi

echo "-- cleanup and status: settled Orca workers that are not released"
# a fake `orca` first on PATH: worker-list prints $FAKE_ORCA_JSON (page 2 when --cursor is given), worktree list
# prints $FAKE_ORCA_WT (when set), `error` exits 1,
# `garbage` prints no JSON; every call is logged so the tests can prove only worker-list ran
FB="$TMP/fakebin"; mkdir -p "$FB"
cat > "$FB/fake_orca.py" <<'PY'
import json, os, sys
with open(os.environ["FAKE_ORCA_LOG"], "a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
mode = os.environ.get("FAKE_ORCA_MODE", "list")
if sys.argv[1:3] == ["status", "--json"]:
    reachable = os.environ.get("FAKE_ORCA_REACHABLE", "true") == "true"
    print(json.dumps({"ok": True, "result": {"runtime": {"reachable": reachable}}})); sys.exit(0)
if sys.argv[1:3] == ["worktree", "list"] and mode != "error" and os.environ.get("FAKE_ORCA_WT"):
    print(open(os.environ["FAKE_ORCA_WT"], encoding="utf-8").read()); sys.exit(0)
if sys.argv[1:3] != ["orchestration", "worker-list"] or mode == "error":
    print("error: run not found", file=sys.stderr); sys.exit(1)
if mode == "garbage":
    print("not json"); sys.exit(0)
src = os.environ["FAKE_ORCA_JSON"] + (".page2" if "--cursor" in sys.argv else "")
print(json.dumps(json.load(open(src, encoding="utf-8"))))
PY
PYEXE=$(python3 -c 'import sys; print(sys.executable)')
if [ -n "$RPGF_WINDOWS" ]; then printf '@"%s" "%%~dp0fake_orca.py" %%*\r\n' "$PYEXE" > "$FB/orca.cmd"
else printf '#!/bin/sh\nexec "%s" "$(dirname "$0")/fake_orca.py" "$@"\n' "$PYEXE" > "$FB/orca"; chmod +x "$FB/orca"; fi
export FAKE_ORCA_LOG="$TMP/orca.log" FAKE_ORCA_JSON="$TMP/workers.json"
# w <dispatch> <workerState> <terminalState> <stage detail> [releaseRequestedAt]: one worker-list row
w() { jq -nc --arg d "$1" --arg ws "$2" --arg t "$3" --arg st "$4" --arg rq "${5:-}" '{dispatchId:$d,runId:"run_T",workerState:$ws,
  dispatchStatus:(if $ws=="running" then "dispatched" else "completed" end),terminalState:$t,
  resource:{releaseState:$t,releaseRequestedAt:(if $rq=="" then null else $rq end),
  retainedReason:(if $t=="retained" then "user_takeover" else null end)},projection:{stage:{detail:$st}}}'; }
jq -n --argjson a "$(w ctx_rel succeeded released settled 2026-11-05)" --argjson b "$(w ctx_ret succeeded retained settled)" \
  --argjson c "$(w ctx_run running active running)" --argjson d "$(w ctx_live succeeded active settled)" \
  '{ok:true,result:{workers:[$a,$b,$c,$d],page:{hasMore:true,nextCursor:"c2"},scope:{run:"run_T"}}}' > "$FAKE_ORCA_JSON"
jq -n --argjson e "$(w ctx_pend failed release_pending settled 2026-11-06)" --argjson f "$(w ctx_recl failed reclaimable settled)" \
  '{ok:true,result:{workers:[$e,$f],page:{hasMore:false,nextCursor:null}}}' > "$FAKE_ORCA_JSON.page2"
GO=$(plan gate-orca "$(sed 's/"id":"gw","repo":"srv"/"id":"gw","repo":"srv","orca_run":"run:run_T"/' "$G")")
fpath="$(path_entry "$FB"):$PATH"
# opath <name> <rc> <pattern> <args...> / oref <name> <pattern> <args...>: expect / refute with the fake orca first on PATH
opath() { local n="$1" rc="$2" pat="$3"; shift 3; PATH="$fpath" expect "$n" "$rc" "$pat" "$@"; }
oref() { local n="$1" pat="$2"; shift 2; PATH="$fpath" refute "$n" "$pat" "$@"; }
expect "a plan task's orca_run is valid" 0 "^OK" validate "$GO"
X=$(plan orca-bad "$(sed 's/"id":"gw","repo":"srv"/"id":"gw","repo":"srv","orca_run":""/' "$G")")
expect "an empty orca_run is an error" 1 "task gw: .orca_run. must be the task lead's Orca Run id" validate "$X"
if [ "$(python3 -B "$P" status --json "$G" | jq -c .tasks)" = "$(PATH="$fpath" python3 -B "$P" status --json "$GO" 2>/dev/null | jq -c .tasks)" ]
then pass=$((pass + 1)); echo "PASS  orca_run is not part of the verdict fingerprint (same task phases)"
else fail=$((fail + 1)); echo "FAIL  orca_run changed the task status"; fi
: > "$FAKE_ORCA_LOG"
opath "settled unreleased workers make cleanup LEFTOVER" 1 "^Cleanup: LEFTOVER" cleanup "$GO"
opath "a settled retained worker gets its release command" 1 "^  orca orchestration worker-release --dispatch ctx_ret$" cleanup "$GO"
opath "a settled worker with a live terminal is unreleased" 1 "worker-release --dispatch ctx_live$" cleanup "$GO"
opath "the next page is read: a reclaimable failed worker" 1 "UNRELEASED ctx_recl \(failed, terminal reclaimable\)" cleanup "$GO"
opath "a pending release is named with its request time" 1 "UNRELEASED ctx_pend .*release requested at 2026-11-06" cleanup "$GO"
opath "the run line counts unreleased, released and running" 1 "WORKERS UNRELEASED  run run_T: 4 settled worker\(s\) not released, 1 released, 1 running" cleanup "$GO"
oref "a released worker is no finding" "dispatch ctx_rel( |$)" cleanup "$GO"
oref "a running worker is no finding" "dispatch ctx_run( |$)" cleanup "$GO"
opath "--orca-run names a Run for a plan without orca_run" 1 "worker-release --dispatch ctx_ret" cleanup "$G" --orca-run run_T
if grep -q -- "--run run_T " "$FAKE_ORCA_LOG" && ! grep -qvE "^orchestration worker-list --run run_T --limit 100 --json( --cursor c2)?$" "$FAKE_ORCA_LOG"
then pass=$((pass + 1)); echo "PASS  only read-only worker-list calls, run:<id> normalised"
else fail=$((fail + 1)); echo "FAIL  orca calls"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
PATH="$fpath" python3 -B "$P" cleanup --json "$GO" > "$TMP/cleanup-orca.json" 2>&1
if jq -e '.state == "LEFTOVER" and (.workers[0].unreleased | length) == 4 and any(.left[]; . == "orca:ctx_ret")' "$TMP/cleanup-orca.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  cleanup --json carries the workers"
else fail=$((fail + 1)); echo "FAIL  cleanup --json workers"; head -c 1500 "$TMP/cleanup-orca.json"; fi
opath "status lists unreleased workers" 0 "^Workers:   UNRELEASED ctx_ret" status "$GO"
if PATH="$fpath" python3 -B "$P" status --json "$GO" 2>/dev/null | jq -e '.next[0] | test("worker-release --dispatch ctx_ret$")' >/dev/null
then pass=$((pass + 1)); echo "PASS  status --json puts the release commands first in next"
else fail=$((fail + 1)); echo "FAIL  status --json next"; fi
PATH="$fpath" python3 -B "$P" status --json "$GO" > "$TMP/so.json" 2> "$TMP/se.txt"; rc=$?
if [ $rc = 0 ] && jq -e '.next[0] | test("worker-release --dispatch ctx_ret$")' "$TMP/so.json" >/dev/null && grep -q "^Workers:   UNRELEASED ctx_ret" "$TMP/se.txt"
then pass=$((pass + 1)); echo "PASS  status --json: unreleased workers on stderr, release command in next, exit 0"
else fail=$((fail + 1)); echo "FAIL  status --json unreleased (rc $rc)"; head -5 "$TMP/se.txt"; fi
PATH="$fpath" python3 -B "$P" status --json "$GO" > "$TMP/status-orca.json" 2>/dev/null
if python3 - "$ROOT" "$TMP/status-orca.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status --json with workers still matches the status schema"
else fail=$((fail + 1)); echo "FAIL  status --json with workers schema"; fi
jq -n --argjson a "$(w ctx_rel succeeded released settled 2026-11-05)" --argjson c "$(w ctx_run running active running)" \
  '{ok:true,result:{workers:[$a,$c],page:{hasMore:false}}}' > "$FAKE_ORCA_JSON"
opath "every settled worker released: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$GO"
opath "and the run line is OK" 0 "WORKERS OK  run run_T: 0 settled" cleanup "$GO"
for mode in error garbage; do
  FAKE_ORCA_MODE=$mode opath "orca $mode: NOT_AVAILABLE, never a failure" 0 "WORKERS NOT_AVAILABLE  run run_T: orca worker-list exited" cleanup "$GO"
  FAKE_ORCA_MODE=$mode oref "orca $mode: no traceback" "Traceback" status "$GO"
done
# status_json_na <name> [env...]: status --json exits 0, stdout is valid JSON, stderr has the NOT_AVAILABLE Run line
status_json_na() { local n="$1" rc; shift
  env "$@" python3 -B "$P" status --json "$GO" > "$TMP/so.json" 2> "$TMP/se.txt"; rc=$?
  if [ $rc = 0 ] && jq -e '.valid' "$TMP/so.json" >/dev/null && grep -q "^Workers: NOT_AVAILABLE  run run_T" "$TMP/se.txt"
  then pass=$((pass + 1)); echo "PASS  $n"
  else fail=$((fail + 1)); echo "FAIL  $n (rc $rc)"; head -5 "$TMP/se.txt"; fi; }
status_json_na "orca erroring: status --json prints NOT_AVAILABLE on stderr, valid JSON, exit 0" PATH="$fpath" FAKE_ORCA_MODE=error
noorca=""; IFS=: read -ra parts <<<"$PATH"
for d in "${parts[@]}"; do [ -e "$d/orca" ] || [ -e "$d/orca.exe" ] || [ -e "$d/orca.cmd" ] || noorca="$noorca${noorca:+:}$d"; done
PATH="$noorca" expect "orca missing: NOT_AVAILABLE, cleanup stays CLEAN" 0 "WORKERS NOT_AVAILABLE  run run_T: orca is not on PATH" cleanup "$GO"
PATH="$noorca" expect "orca missing: status still exits 0" 0 "^Workers: NOT_AVAILABLE  run run_T" status "$GO"
status_json_na "orca missing: status --json prints NOT_AVAILABLE on stderr, valid JSON, exit 0" PATH="$noorca"
refute "no Run named: no worker line" "WORKERS " cleanup "$G"
# a child with any name (orca worktree create --parent-worktree path:<task worktree> --name isolated-qa): Orca's
# lineage (parentWorktreeId, or the parent's childWorktreeIds) names it; orca unavailable means the naming rule only
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/isolated-qa" -b isolated-qa feat/core/demo-gw 2>/dev/null
wtp() { git -C "$1" rev-parse --show-toplevel; }
export FAKE_ORCA_WT="$TMP/orca-wt.json"
jq -n --arg p "$(wtp "$TMP/srv-gw")" --arg c "$(wtp "$TMP/isolated-qa")" --arg o "$TMP/other-child"   '{ok:true,result:{worktrees:[{id:"r::gw",path:$p,parentWorktreeId:null,childWorktreeIds:[]},
   {id:"r::qa",path:$c,parentWorktreeId:"r::gw",childWorktreeIds:[]},{id:"r::o",path:$o,parentWorktreeId:"r::gw"}]}}' > "$FAKE_ORCA_WT"
: > "$FAKE_ORCA_LOG"
opath "Orca lineage: a child named isolated-qa is a child of its task" 1 "KEPT  srv: child of gw: leftover child worktree .*isolated-qa \(isolated-qa\): merged, then remove it" cleanup "$G"
opath "Orca lineage: the merged child gets its orca worktree rm command" 1 "^  orca worktree rm --worktree '?path:[^ ]*isolated-qa'?$" cleanup "$G"
if PATH="$fpath" python3 -B "$P" status --json "$G" 2>/dev/null | jq -e '.tasks[] | select(.id == "gw") | (.children | length) == 1 and .children[0].branch == "isolated-qa"' >/dev/null
then pass=$((pass + 1)); echo "PASS  Orca lineage: status lists the isolated-qa child"
else fail=$((fail + 1)); echo "FAIL  Orca lineage: status children"; fi
if grep -q "^worktree list --limit 10000 --json$" "$FAKE_ORCA_LOG" && ! grep -qvE "^(worktree list --limit 10000 --json|orchestration worker-list .*)$" "$FAKE_ORCA_LOG"
then pass=$((pass + 1)); echo "PASS  Orca lineage is read with the read-only worktree list only"
else fail=$((fail + 1)); echo "FAIL  Orca lineage calls"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
jq '.result.worktrees |= map(if .id == "r::qa" then .parentWorktreeId = null elif .id == "r::gw" then .childWorktreeIds = ["r::qa"] else . end)' "$FAKE_ORCA_WT" > "$FAKE_ORCA_WT.2"; mv "$FAKE_ORCA_WT.2" "$FAKE_ORCA_WT"
opath "Orca lineage: the parent's childWorktreeIds also name the child" 1 "KEPT  srv: child of gw: leftover child worktree .*isolated-qa" cleanup "$G"
FAKE_ORCA_MODE=error oref "orca failing: the naming rule only, the isolated-qa child is not named" "child of gw" cleanup "$G"
FAKE_ORCA_MODE=error oref "orca failing: no traceback" "Traceback" cleanup "$G"
PATH="$noorca" refute "orca missing: the naming rule only, never an error" "child of gw|Traceback" cleanup "$G"
PATH="$noorca" expect "orca missing: status still exits 0 with a child by lineage only" 0 "^Pipeline demo" status "$G"
unset FAKE_ORCA_WT
git -C "$S" worktree remove "$TMP/isolated-qa"; git -C "$S" worktree remove "$TMP/srv-gw"
git -C "$S" branch -q -D isolated-qa feat/core/demo-gw
expect "lineage children removed: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
# a new task worktree is an Orca child of the integration checkout ($S on feat/core/demo); dispatch only prints it
: > "$FAKE_ORCA_LOG"
opath "fake orca: a new task worktree carries --parent-worktree path:<integration checkout>" 0 "^orca worktree create --name feat/core/demo-gw .*--parent-worktree '?path:$(wtp "$S")'? --agent claude " dispatch "$G" --task gw --phase lead --runner orca
oref "fake orca: a new task worktree under the integration checkout has no --no-parent" "--no-parent" dispatch "$G" --task gw --phase lead --runner orca
opath "fake orca: --placement shared keeps --no-parent" 0 "--branch feat/core/demo-gw --no-parent --agent claude " dispatch "$G" --task gw --phase lead --placement shared --runner orca
if ! grep -q "worktree create" "$FAKE_ORCA_LOG"; then pass=$((pass + 1)); echo "PASS  fake orca: dispatch --phase lead only prints the worktree create"
else fail=$((fail + 1)); echo "FAIL  fake orca: dispatch ran orca worktree create"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
# children of the integration checkout ($S on feat/core/demo): the integration QA child dispatch names
# (<topic>--qa) and a helper with any name whose Orca lineage parent is the integration checkout; status lists them
# once per repo in integration_children with cleanup guidance, cleanup names them "child of integration:srv"
opath "integration QA --placement child (orca on PATH): worker-start --worktree new-child at the SHA" 0 "^orca orchestration worker-start .*--worktree new-child --name feat/core/demo--qa-${SG:0:7} --base-branch $SG " dispatch "$G" --task integration:srv --phase qa --sha "$SG" --placement child --runner orca
git -C "$S" worktree add -q "$TMP/feat-core-demo--qa" -b feat/core/demo--qa "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/int-helper" -b int-helper "$SG" 2>/dev/null
export FAKE_ORCA_WT="$TMP/orca-wt.json"
jq -n --arg p "$(wtp "$S")" --arg h "$(wtp "$TMP/int-helper")" \
  '{ok:true,result:{worktrees:[{id:"r::int",path:$p,parentWorktreeId:null},{id:"r::h",path:$h,parentWorktreeId:"r::int"}]}}' > "$FAKE_ORCA_WT"
PATH="$fpath" python3 -B "$P" status --json "$G" > "$TMP/status-int.json" 2>/dev/null
if jq -e '(.integration_children | length) == 2 and all(.integration_children[]; .repo == "srv" and .merged
     and (.note | test("leftover child worktree .*merged, then remove it at once: orca worktree rm --worktree")))
   and ([.integration_children[].branch] | sort) == ["feat/core/demo--qa", "int-helper"]
   and all(.tasks[]; (.children | length) == 0)' "$TMP/status-int.json" >/dev/null && python3 - "$ROOT" "$TMP/status-int.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status lists integration-checkout children once per repo (name and lineage), schema-valid"
else fail=$((fail + 1)); echo "FAIL  status integration_children"; head -c 1500 "$TMP/status-int.json"; fi
opath "status text names the integration child with its rm command" 0 "^  \[integration:srv\] child: leftover child worktree .*feat-core-demo--qa .*orca worktree rm" status "$G"
opath "cleanup names the integration QA child" 1 "KEPT  srv: child of integration:srv: leftover child worktree .*feat-core-demo--qa" cleanup "$G"
opath "cleanup names the lineage helper of the integration checkout" 1 "KEPT  srv: child of integration:srv: leftover child worktree .*int-helper" cleanup "$G"
unset FAKE_ORCA_WT

echo "-- Orca first: --runner agent inside a reachable Orca session needs --orca-unavailable"
# the fake orca's `status --json` answers reachable unless FAKE_ORCA_REACHABLE=false
inorca() { PATH="$fpath" ORCA_WORKTREE_ID=x "$@"; }
inorca expect "inside Orca: dispatch --runner agent exits 2 naming --runner orca" 2 "ORCA_WORKTREE_ID is set.*use --runner orca" dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner agent
inorca expect "inside Orca: the refusal names --orca-unavailable REASON" 2 "needs --orca-unavailable REASON" dispatch "$OK" --task c1 --phase lead --runner agent
inorca refute "inside Orca: the refusal prints no agent call" '"subagent_type"' dispatch "$OK" --task c1 --phase lead --runner agent
inorca expect "inside Orca: planner --runner agent exits 2 too" 2 "use --runner orca" planner --request "add a thing" --runner agent
PATH="$fpath" ORCA_AGENT_HOOK_ENDPOINT=e expect "inside Orca (ORCA_AGENT_HOOK_ENDPOINT only): refused" 2 "ORCA_AGENT_HOOK_ENDPOINT is set" planner --request "add a thing" --runner agent
inorca expect "inside Orca with --orca-unavailable: the planner prompt opens with the reason" 0 '"prompt": "Orca unavailable: quota hit\. This session runs through' planner --request "add a thing" --runner agent --orca-unavailable "quota hit"
inorca expect "inside Orca with --orca-unavailable: the agent call's prompt names the reason (whitespace collapsed)" 0 '\\nOrca unavailable: quota hit\. This session runs through the Claude Code Agent-tool fallback' dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner agent --orca-unavailable 'quota   hit'
inorca expect "inside Orca with --orca-unavailable: stderr note" 0 "Orca unavailable \(quota hit\)" planner --request "add a thing" --runner agent --orca-unavailable "quota hit"
inorca expect "inside Orca with --orca-unavailable: the lead prompt passes the flag on" 0 "pass --orca-unavailable with it to every factory-pipeline.py planner or dispatch" dispatch "$OK" --task c1 --phase lead --runner agent --orca-unavailable "quota hit"
expect "outside Orca with --orca-unavailable: the reason is named too" 0 "Orca unavailable: quota hit\." planner --request "add a thing" --runner agent --orca-unavailable "quota hit"
inorca expect "inside Orca: the default runner is orca" 0 "^orca orchestration worker-start " planner --request "add a thing"
inorca refute "inside Orca: the default runner is not print" "^# agent:" planner --request "add a thing"
expect "outside Orca: the default runner is print" 0 "^# agent: " planner --request "add a thing"
PATH="$fpath" expect "orca reachable but no ORCA_* variable: the default runner is print" 0 "^# agent: " planner --request "add a thing"
PATH="$fpath" expect "orca reachable but no ORCA_* variable: --runner agent as before" 0 '"subagent_type": "general-purpose"' planner --request "add a thing" --runner agent
FAKE_ORCA_REACHABLE=false inorca expect "Orca env set, runtime unreachable: --runner agent as before" 0 '"subagent_type": "general-purpose"' planner --request "add a thing" --runner agent
FAKE_ORCA_REACHABLE=false inorca expect "Orca env set, runtime unreachable: the default runner is print" 0 "^# agent: " planner --request "add a thing"
noorca=$(IFS=:; for d in $PATH; do [ -e "$d/orca" ] || [ -e "$d/orca.cmd" ] || [ -e "$d/orca.exe" ] || printf '%s:' "$d"; done)
PATH="${noorca%:}" ORCA_WORKTREE_ID=x expect "Orca env set, orca not on PATH: --runner agent as before" 0 '"subagent_type": "general-purpose"' dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner agent
inorca expect "--orca-unavailable with --runner orca is a usage error" 2 "--orca-unavailable REASON goes with --runner agent only" planner --request "add a thing" --runner orca --orca-unavailable x
expect "--orca-unavailable without --runner is a usage error" 2 "goes with --runner agent only" planner --request "add a thing" --orca-unavailable x
expect "--orca-unavailable with a blank reason is a usage error" 2 "--orca-unavailable needs a REASON" planner --request "add a thing" --runner agent --orca-unavailable "  "
git -C "$S" worktree remove "$TMP/feat-core-demo--qa"; git -C "$S" worktree remove "$TMP/int-helper"
git -C "$S" branch -q -D feat/core/demo--qa int-helper
if python3 -B "$P" status --json "$G" 2>/dev/null | jq -e '.integration_children == []' >/dev/null
then pass=$((pass + 1)); echo "PASS  integration children removed: status lists none"
else fail=$((fail + 1)); echo "FAIL  integration_children after removal"; fi

echo "-- review findings"
expect "--agent cannot swap the planned implementer" 2 "is planned for claude; set .implementer: codex." dispatch "$OK" --task gw --phase implement --agent codex
X=$(plan alias "{$HEAD,\"repos\":{\"cli2\":{\"path\":\"ws/IndieRPGMMOAdventure\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"cli2\",\"objective\":\"o\",\"paths\":[\"Assets/A/x.cs\"],\"acceptance\":[\"a\"]}]}")
expect "two keys for one Unity checkout: overlap still found" 1 "ERROR tasks a and b own overlapping paths" validate "$X"
X=$(plan alias2 "{$HEAD,\"repos\":{\"cli2\":{\"path\":\"ws/IndieRPGMMOAdventure\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"cli2\",\"objective\":\"o\",\"paths\":[\"Assets/B/\"],\"acceptance\":[\"a\"]}]}")
expect "two keys for one Unity checkout: still one task per wave" 0 "^Wave 2: b$" validate "$X"
# status and dispatch serialize by checkout too: two plan aliases of one Unity checkout are never both ready
X=$(plan alias3 "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"alias3\",\"title\":\"Alias\",\"topic\":\"feat/core/alias3\",
 \"repos\":{\"u1\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"},\"u2\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"u1\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"u2\",\"objective\":\"o\",\"paths\":[\"Assets/B/\"],\"acceptance\":[\"a\"]}]}")
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert o["ready"]==["a"], o["ready"]
assert r["b"]["next"] is None and any(n=="waits for a" for n in r["b"]["notes"]), r["b"]'
then pass=$((pass + 1)); echo "PASS  status: two aliases of one Unity checkout are never both ready (b waits for a)"
else fail=$((fail + 1)); echo "FAIL  status alias serialization"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
expect "dispatch warns the second alias task that the first has no QA PASS" 0 "takes one task at a time: task a has no QA PASS yet" dispatch "$X" --task b --phase lead --runner print
# after task a's review and per-task QA PASS (task b not started), the checkout is b's: no integration QA of either
# alias runs beside b's task lead, and the aliases' integration QAs run one at a time once b passed its QA too
gi "$C" checkout -qb feat/core/alias3 develop; mkdir -p "$C/Assets/A" "$C/Assets/B"
echo a > "$C/Assets/A/al.cs"; gi "$C" add Assets/A; gi "$C" commit -qm "feat: alias a"; UA=$(git -C "$C" rev-parse HEAD)
python3 -B "$P" verdict "$X" --task a --phase review --sha "$UA" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$X" --task a --phase qa --sha "$UA" --by codex --state PASS >/dev/null
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert o["ready"]==["b"] and o["ready_wave"]==2, (o["ready"], o["ready_wave"])
assert r["a"]["phase"]=="qa" and r["a"]["next"] is None, r["a"]
assert "--task b --phase lead" in r["b"]["next"] and "integration:" not in json.dumps(o), r["b"]'
then pass=$((pass + 1)); echo "PASS  status: after the first alias task's QA only the next task lead is offered (no integration QA)"
else fail=$((fail + 1)); echo "FAIL  status alias integration QA beside a task lead"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
expect "dispatch warns an alias's integration QA while a task of the checkout has no QA PASS" 0 "u1 takes one task at a time: task b has no QA PASS yet" dispatch "$X" --task integration:u1 --phase qa --sha "$UA" --runner print
echo b > "$C/Assets/B/al.cs"; gi "$C" add Assets/B; gi "$C" commit -qm "feat: alias b"; UB=$(git -C "$C" rev-parse HEAD)
python3 -B "$P" verdict "$X" --task b --phase review --sha "$UB" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$X" --task b --phase qa --sha "$UB" --by codex --state PASS >/dev/null
# dispatch reads the per-task QA like status: a PASS recorded for an older version of task a is STALE, not PASS
python3 -c 'import json,sys; p=json.load(open(sys.argv[1],encoding="utf-8")); p["tasks"][0]["objective"]="changed"; json.dump(p,open(sys.argv[2],"w",encoding="utf-8"))' "$X" "$TMP/alias3-stale.json"
expect "dispatch: a STALE per-task QA PASS leaves the alias's integration QA open" 0 "u1 takes one task at a time: task a has no QA PASS yet" dispatch "$TMP/alias3-stale.json" --task integration:u1 --phase qa --sha "$UB" --runner print
expect "dispatch: a STALE QA PASS of the serial predecessor still warns the next task lead" 0 "takes one task at a time: task a has no QA PASS yet" dispatch "$TMP/alias3-stale.json" --task b --phase lead --runner print
refute "dispatch: a current QA PASS of every alias task: no warning" "takes one task at a time" dispatch "$X" --task integration:u1 --phase qa --sha "$UB" --runner print
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert "--task integration:u1 --phase qa" in r["a"]["next"], r["a"]
assert r["b"]["next"] is None and any("integration QA of u1 runs first" in n for n in r["b"]["notes"]), r["b"]'
then pass=$((pass + 1)); echo "PASS  status: integration QAs of two aliases of one Unity checkout run one at a time"
else fail=$((fail + 1)); echo "FAIL  status alias integration QA order"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
python3 -B "$P" verdict "$X" --task integration:u1 --phase qa --sha "$UB" --by codex --state PASS >/dev/null
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["a"]["phase"]=="qa" and r["a"]["next"] is None, r["a"]
assert "--task integration:u2 --phase qa" in r["b"]["next"], r["b"]'
then pass=$((pass + 1)); echo "PASS  status: the second alias's integration QA follows the first one's PASS"
else fail=$((fail + 1)); echo "FAIL  status alias second integration QA"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
python3 -B "$P" verdict "$X" --task integration:u2 --phase qa --sha "$UB" --by codex --state PASS >/dev/null
refute "gate: the aliases' tasks share the integration branch, so neither alias's changes are stray" "changes outside every task's owned paths" gate "$X" --no-run-checks
expect "gate: two aliases of one Unity checkout with every verdict are READY_FOR_PR" 0 "READY_FOR_PR" gate "$X" --no-run-checks
# a dependent no-worktree task owning its predecessor's path: the predecessor's commits on the shared integration
# branch are not its own, so it is no review candidate before the predecessor's verdict and its own commit
X=$(plan uov "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"uov\",\"title\":\"Uov\",\"topic\":\"feat/core/uov\",
 \"repos\":{\"u1\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"u1\",\"objective\":\"o\",\"paths\":[\"Assets/U/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"u1\",\"objective\":\"o\",\"paths\":[\"Assets/U/\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]}]}")
gi "$C" checkout -qb feat/core/uov develop; mkdir -p "$C/Assets/U"
echo a > "$C/Assets/U/u.cs"; gi "$C" add Assets/U; gi "$C" commit -qm "feat: uov a"; VA=$(git -C "$C" rev-parse HEAD)
echo wip > "$C/Assets/U/wip.cs"  # the predecessor's uncommitted work in the shared path is not b's
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["a"]["phase"]=="candidate" and "--task a --phase review --sha "+sys.argv[1] in r["a"]["next"], r["a"]
assert r["b"]["phase"]=="pending" and r["b"]["next"] is None and any(n=="waits for a" for n in r["b"]["notes"]), r["b"]
assert "--task b --phase review" not in json.dumps(o), o' "$VA"
then pass=$((pass + 1)); echo "PASS  status: a dependent no-worktree task with the same path is pending before its predecessor's QA (no review at a's commit)"
else fail=$((fail + 1)); echo "FAIL  status no-worktree dependent before QA"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
rm -f "$C/Assets/U/wip.cs"
for failed_phase in review qa; do
  python3 -B "$P" verdict "$X" --task a --phase review --sha "$VA" --by codex --state PASS >/dev/null
  python3 -B "$P" verdict "$X" --task a --phase "$failed_phase" --sha "$VA" --by codex --state FAIL >/dev/null
  echo "fix after $failed_phase FAIL" >> "$C/Assets/U/u.cs"
  gi "$C" add Assets/U; gi "$C" commit -qm "fix: uov a after $failed_phase FAIL"; VA=$(git -C "$C" rev-parse HEAD)
  if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["a"]["phase"]=="candidate" and "--task a --phase review --sha "+sys.argv[1] in r["a"]["next"], r["a"]
assert r["b"]["phase"]=="pending" and r["b"]["next"] is None and "waits for a" in r["b"]["notes"], r["b"]
assert "--task b --phase review" not in json.dumps(o), o' "$VA"
  then pass=$((pass + 1)); echo "PASS  status: predecessor fixes after $failed_phase FAIL keep the dependent pending without a review command"
  else fail=$((fail + 1)); echo "FAIL  status dependent after predecessor $failed_phase FAIL"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
done
python3 -B "$P" verdict "$X" --task a --phase review --sha "$VA" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$X" --task a --phase qa --sha "$VA" --by codex --state PASS >/dev/null
echo b >> "$C/Assets/U/u.cs"; gi "$C" add Assets/U; gi "$C" commit -qm "feat: uov b"; VB=$(git -C "$C" rev-parse HEAD)
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["b"]["phase"]=="candidate" and r["b"]["sha"]==sys.argv[1] and "--task b --phase review --sha "+sys.argv[1] in r["b"]["next"], r["b"]' "$VB"
then pass=$((pass + 1)); echo "PASS  status: after the predecessor's QA PASS, the dependent task's own commit makes it a candidate at that SHA"
else fail=$((fail + 1)); echo "FAIL  status no-worktree dependent after QA"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
gi "$C" checkout -q feat/core/demo
X=$(plan norm "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"./backend/gateway\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend\\\\gateway\\\\x.go\"],\"acceptance\":[\"a\"]}]}")
expect "./ and backslash spellings of one path overlap" 1 "ERROR tasks a and b own overlapping paths" validate "$X"
X=$(ctx br '{"repos":[{"repo":"server","touched":["server.gateway"],"files":[{"path":"a","source":"branch"},{"path":"b","source":"branch"},{"path":"c","source":"branch"},{"path":"d","source":"branch"},{"path":"e","source":"branch"},{"path":"f","source":"branch"},{"path":"g","source":"branch"}],"contracts":[],"generated_hits":[]}]}')
expect "files committed on the branch count for the tier" 0 "7 files > 6" tier --context-json "$X"
TP=$(plan tp "{$HEAD,\"repos\":{\"other\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"o\",\"repo\":\"other\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
out=$(cd "$TMP" && python3 -B "$P" dispatch "$TP" --task o --phase lead --runner agent 2>&1)
if grep -q "Create your own worktree first" <<<"$out" && ! grep -q '"isolation"' <<<"$out"; then pass=$((pass + 1)); echo "PASS  agent fallback for another repo names repo and base, no isolation"
else fail=$((fail + 1)); echo "FAIL  agent fallback placement"; head -c 400 <<<"$out"; fi

echo "-- tier for a repo the registry does not know (the plugin repo)"
PL=$(plan plug "{$HEAD,\"repos\":{\"plugin\":{\"path\":\"tool\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"plugin\",\"objective\":\"o\",\"paths\":[\"scripts/\"],\"acceptance\":[\"a\"]}]}")
expect "one file of a plan repo: S from the paths alone" 0 '"tier": "S"' tier --json --plan "$PL" --repo plugin --paths scripts/factory-pipeline.py
expect "plan repo tier names its basis" 0 "basis: paths \(repo not in the registry\)" tier --plan "$PL" --repo plugin --paths scripts/a.py
out=$(python3 -B "$P" tier --json --plan "$PL" --repo plugin --paths skills/factory-core/SKILL.md skills/ui-ux/SKILL.md scripts/lib/x.py scripts/y.py tests/z.sh README.md 2>&1)
if python3 -c 'import json,sys; o=json.loads(sys.argv[1]); f=o["facts"]
assert o["tier"]=="M", o["tier"]
assert f["modules"]==["other","scripts","scripts/lib","skills/factory-core","skills/ui-ux","tests"], f["modules"]
assert f["files"]==6 and f["repos"]==["plugin"] and f["contracts"]==[] and f["generated"]==[]' "$out"; then
  pass=$((pass + 1)); echo "PASS  plan repo tier: skills/<name>, scripts/lib, listed dirs and other are modules; M"
else fail=$((fail + 1)); echo "FAIL  plan repo tier facts"; head -c 600 <<<"$out"; fi
out=$(python3 -B "$P" tier --json --plan "$PL" --repo plugin --paths .claude/CLAUDE.md evals/e.json changelog.d/x.md README.md skills/README.md hooks/hooks.json registry/core.json docs/d.md commands/c.md 2>&1)
if python3 -c 'import json,sys; f=json.loads(sys.argv[1])["facts"]
assert f["modules"]==["commands","docs","hooks","other","registry"], f["modules"]' "$out"; then
  pass=$((pass + 1)); echo "PASS  plan repo tier: .claude, evals, changelog.d and root files are one other module"
else fail=$((fail + 1)); echo "FAIL  plan repo tier other module"; head -c 600 <<<"$out"; fi
expect "seven files of a plan repo: above S" 0 "7 files > 6" tier --plan "$PL" --repo plugin --paths scripts/a scripts/b scripts/c scripts/d scripts/e scripts/f scripts/g
expect "tier --plan needs --paths" 2 "needs --repo <plan repo key> and --paths" tier --plan "$PL" --repo plugin
expect "tier --plan with an unknown repo key fails cleanly" 2 "neither a registry repo nor in plan.repos" tier --plan "$PL" --repo nope --paths x
expect "--repo without --plan is a usage error" 2 "go with --plan" tier --repo plugin --paths x

echo "-- status (resume a run from git and the verdicts)"
# srv: a worktree repo (a, then b); cli: a Unity project (c1, then c2 in the main checkout); topic feat/core/st
ST=$(plan st "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"st\",\"title\":\"Status\",\"topic\":\"feat/core/st\",
 \"repos\":{\"srv\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"},\"cli\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"sa/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"sb/\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]},
 {\"id\":\"c1\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"Assets/C/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c2\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"Assets/D/\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"}]}")
sv() { python3 -B "$P" verdict "$ST" "$@" >/dev/null || echo "verdict failed: $*"; }
# review_diff_lists <name> <files>: run the `git diff X...Y` printed in b's review spec in the fixture; it lists exactly <files>
review_diff_lists() {
  local name="$1" want="$2" out spec range got
  out=$(python3 -B "$P" dispatch "$ST" --task b --phase review --sha "$SB" --runner orca 2>&1)
  spec=$(python3 -c 'import pathlib,shlex,sys
args=shlex.split(sys.argv[1]); flag="--prompt" if "--prompt" in args else "--spec"; prompt=args[args.index(flag)+1]
print(pathlib.Path(prompt[len("Read your task spec at "):-len(" and follow it.")]).read_text(encoding="utf-8"))' "$out" 2>&1)
  range=$(grep -oE 'git diff [^ `]+\.\.\.[0-9a-f]+' <<<"$spec" | head -1 | cut -d' ' -f3)
  got=$([ -n "$range" ] && git -C "$S" diff --name-only "$range" | tr '\n' ' ' | sed 's/ $//')
  if [ -n "$range" ] && [ "$got" = "$want" ]; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (range '$range' lists '$got', want '$want')"; fi
}
# st_phase <name> <task> <phase> [<next-regex>]: the task's phase in status --json (and its next command)
st_phase() {
  local name="$1" id="$2" want="$3" nx="${4:-}" out
  out=$(python3 -B "$P" status --json "$ST" 2>&1)
  if python3 -c 'import json,re,sys; o=json.loads(sys.argv[1]); r={t["id"]:t for t in o["tasks"]}[sys.argv[2]]
assert r["phase"]==sys.argv[3], r
assert not sys.argv[4] or re.search(sys.argv[4], r["next"] or ""), r' "$out" "$id" "$want" "$nx"; then
    pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name"; head -c 1500 <<<"$out"; echo; fi
}
st_phase "nothing started in a worktree repo: pending, next starts the task lead" a pending "dispatch .* --task a --phase lead --runner orca"
st_phase "nothing started in the Unity project: next starts its task lead in the main checkout" c1 pending "dispatch .* --task c1 --phase lead --runner orca"
st_phase "a dependent task waits (no next command)" b pending '^$'
refute "no integration commits in owned paths: no \"integrated earlier\" note" "no review record: integrated earlier" status "$ST"
expect "the first Unity task is ready, the second waits for its QA" 0 "note: waits for c1" status "$ST"
expect "status prints the ready wave and its tasks" 0 "^Ready wave: 1  \(dispatch: a, c1\)" status "$ST"
git -C "$S" worktree add -q "$TMP/st-a" -b feat/core/st-a develop 2>/dev/null
st_phase "task branch and worktree without commits: implementing" a implementing '^$'
expect "implementing names the worker's worktree" 0 "implementation worker on feat/core/st-a in .*st-a" status "$ST"
mkdir -p "$TMP/st-a/sa"; echo a > "$TMP/st-a/sa/a.go"; gi "$TMP/st-a" add sa; gi "$TMP/st-a" commit -qm "feat: a"; SA=$(git -C "$S" rev-parse feat/core/st-a)
st_phase "commits ahead of the base: candidate, next is the review at that SHA" a candidate "--task a --phase review --sha $SA --runner orca"
sv --task a --phase review --sha "$SA" --by codex --state FAIL
st_phase "review FAIL: reviewed, next resumes the task lead (only it commits the fix)" a reviewed "--task a --phase lead --runner orca"
expect "review FAIL is named with its SHA" 0 "review FAIL@${SA:0:10}" status "$ST"
echo a2 >> "$TMP/st-a/sa/a.go"; gi "$TMP/st-a" commit -qam "fix: a"; SA=$(git -C "$S" rev-parse feat/core/st-a)
st_phase "a fix after the FAIL is a new candidate" a candidate "--phase review --sha $SA"
expect "and the old review is named STALE" 0 "review at .* is STALE: owned paths changed since" status "$ST"
sv --task a --phase review --sha "$SA" --by codex --state PASS
st_phase "review PASS without an integration branch: create it from the base" a reviewed "branch feat/core/st develop"
expect "no integration branch yet: a later-wave task lead starts from the base" 0 "--base-branch develop --branch feat/core/st-b " dispatch "$ST" --task b --phase lead --runner orca
git -C "$S" worktree add -q "$TMP/st-int" -b feat/core/st develop 2>/dev/null
st_phase "review PASS: next merges the task branch into the integration worktree" a reviewed "merge --no-ff feat/core/st-a"
gi "$TMP/st-int" merge -q --no-ff feat/core/st-a -m "merge a"
st_phase "merged after review PASS: integrated" a integrated '^$'
# Prior tasks can touch paths a later task also owns. That integration history is not evidence the later
# task started: without a local task branch/worktree or prior review record it must stay pending, with no SHA.
if python3 -B - "$P" "$ST" "$TMP/st-unstarted.json" <<'PY'
import json, pathlib, subprocess, sys
p, source, target = sys.argv[1:]
plan = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
plan["tasks"].append({"id": "unstarted", "repo": "srv", "objective": "follow-up in existing paths",
                      "paths": ["sa/"], "acceptance": ["a"], "deps": ["a"]})
pathlib.Path(target).write_text(json.dumps(plan), encoding="utf-8")
r = subprocess.run([sys.executable, "-B", p, "status", target, "--json"], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
row = next(t for t in json.loads(r.stdout)["tasks"] if t["id"] == "unstarted")
assert row["phase"] == "pending" and row["sha"] is None and row["worktree"] is None, row
assert "--task unstarted --phase lead --runner orca" in row["next"], row
assert any("commits in owned paths on feat/core/st but no review record: integrated earlier?" in n for n in row["notes"]), row
PY
then pass=$((pass + 1)); echo "PASS  task without branch/worktree stays pending despite earlier integration commits in its paths"
else fail=$((fail + 1)); echo "FAIL  unstarted task inherits an integration candidate"; fi
# A dependent task that owns the same paths, cut from the integration branch after a was merged: a's commits are
# not its own. Without own commits it is implementing, never a review candidate; its first commit makes it one.
python3 -c 'import json,sys; p=json.load(open(sys.argv[1],encoding="utf-8")); p["tasks"].append({"id":"ov","repo":"srv","objective":"o","paths":["sa/"],"acceptance":["a"],"deps":["a"]}); json.dump(p,open(sys.argv[2],"w",encoding="utf-8"))' "$ST" "$TMP/st-ov.json"
git -C "$S" worktree add -q "$TMP/st-ov" -b feat/core/st-ov feat/core/st 2>/dev/null
ov_phase() {  # ov_phase <name> <phase> [<sha>]
  local out; out=$(python3 -B "$P" status --json "$TMP/st-ov.json" 2>&1)
  if python3 -c 'import json,sys; r={t["id"]:t for t in json.loads(sys.argv[1])["tasks"]}["ov"]
assert r["phase"]==sys.argv[2], r
assert not sys.argv[3] or (r["next"] or "").find("--phase review --sha "+sys.argv[3])>=0, r' "$out" "$2" "${3:-}"
  then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; head -c 1200 <<<"$out"; echo; fi
}
ov_phase "dependent task with a's paths, cut after a's merge, no own commits: implementing (not a candidate)" implementing
echo ov > "$TMP/st-ov/sa/ov.go"; gi "$TMP/st-ov" add sa; gi "$TMP/st-ov" commit -qm "feat: ov"; SOV=$(git -C "$S" rev-parse feat/core/st-ov)
ov_phase "its own first commit makes it a review candidate at that SHA" candidate "$SOV"
git -C "$S" worktree remove --force "$TMP/st-ov"; git -C "$S" branch -q -D feat/core/st-ov
expect "QA waits for the other tasks of the repo" 0 "QA runs once all tasks of the repo are integrated: waits for b" status "$ST"
st_phase "the dependency is integrated: b is ready, next starts its task lead" b pending "--task b --phase lead"
expect "wave 2: the task lead's worktree starts from the integration branch (it carries wave 1)" 0 "--base-branch feat/core/st --branch feat/core/st-b " dispatch "$ST" --task b --phase lead --runner orca
expect_spec "wave 2: the task spec names the integration branch as its base" '"base": "feat/core/st"' dispatch "$ST" --task b --phase lead --runner orca
st_phase "status is unchanged by the wave-2 dispatch: b still pending" b pending "--task b --phase lead"
expect "ready tasks span waves: b (wave 3) next to c1 (wave 1)" 0 "^Ready wave: 1  \(dispatch: b, c1\)$" status "$ST"
git -C "$S" worktree remove "$TMP/st-a"; git -C "$S" branch -q -D feat/core/st-a
st_phase "a removed task branch stays integrated (verdict + integration branch)" a integrated
expect "wave 1 starts from the base even when the integration branch exists" 0 "--base-branch develop --branch feat/core/st-a " dispatch "$ST" --task a --phase lead --runner orca
git -C "$S" worktree add -q "$TMP/st-b" -b feat/core/st-b feat/core/st 2>/dev/null
st_phase "a task branch cut from the integration branch, no own commits yet: implementing" b implementing
mkdir -p "$TMP/st-b/sb"; echo b > "$TMP/st-b/sb/b.go"; gi "$TMP/st-b" add sb; gi "$TMP/st-b" commit -qm "feat: b"; SB=$(git -C "$S" rev-parse feat/core/st-b)
expect_spec "wave-2 review diffs against the integration branch, not the base" "git diff feat/core/st\.\.\.$SB" dispatch "$ST" --task b --phase review --sha "$SB" --runner orca
review_diff_lists "wave-2 review before the merge: the printed diff lists only b's files" sb/b.go
st_phase "status still compares b against the base: candidate at its SHA" b candidate "--task b --phase review --sha $SB"
sv --task b --phase review --sha "$SB" --by codex --state PASS
gi "$TMP/st-int" merge -q --no-ff feat/core/st-b -m "merge b"; SI=$(git -C "$S" rev-parse feat/core/st)
review_diff_lists "wave-2 re-review after the merge: the printed diff still lists only b's files (its fork point)" sb/b.go
refute_spec "wave-2 re-review after the merge never diffs against the integration branch (empty)" "git diff feat/core/st\.\.\." dispatch "$ST" --task b --phase review --sha "$SB" --runner orca
refute_spec "wave-2 re-review after the merge needs no fallback note" "without a merge commit" dispatch "$ST" --task b --phase review --sha "$SB" --runner orca
st_phase "every task of the repo integrated: next is the integration QA at its HEAD" a integrated "--task integration:srv --phase qa --sha $SI"
sv --task integration:srv --phase qa --sha "$SI" --by codex --state PASS
st_phase "QA PASS on a commit containing the review: qa" a qa
st_phase "and for the second task" b qa
# the Unity project: tasks run on the integration branch in the main checkout
gi "$C" checkout -qb feat/core/st develop
mkdir -p "$C/Assets/C"; echo c > "$C/Assets/C/c.cs"
st_phase "uncommitted work in the Unity task's paths: implementing" c1 implementing
gi "$C" add Assets/C; gi "$C" commit -qm "feat: c1"; SC=$(git -C "$C" rev-parse HEAD)
st_phase "a commit on the integration branch touching the task: candidate" c1 candidate "--task c1 --phase review --sha $SC"
st_phase "the next Unity task still waits" c2 pending '^$'
sv --task c1 --phase review --sha "$SC" --by codex --state FAIL
st_phase "Unity review FAIL: next resumes the task lead in the main checkout, not an implement worker" c1 reviewed "--task c1 --phase lead --runner orca$"
# follow status.next: the resumed task lead is launched in the main checkout, never a worktree or a committing worker
NX=$(python3 -B "$P" status --json "$ST" | python3 -c 'import json,sys; print({t["id"]:t for t in json.load(sys.stdin)["tasks"]}["c1"]["next"])')
out=$(eval "$NX" 2>&1)
if grep -qE "^orca agent launch --agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure" <<<"$out" \
   && ! grep -qE "new-top-level|--base-branch|worktree create|commit explicit" <<<"$out"; then
  pass=$((pass + 1)); echo "PASS  Unity review FAIL: status.next launches the task lead in the main checkout"
else fail=$((fail + 1)); echo "FAIL  Unity review FAIL: status.next"; sed 's/^/      /' <<<"$out" | head -10; fi
expect_spec "Unity fix session after the FAIL does not commit" "Do NOT commit, stage or stash" dispatch "$ST" --task c1 --phase implement --runner orca
refute "Unity fix session after the FAIL creates no worktree" "new-top-level|--base-branch|worktree create" dispatch "$ST" --task c1 --phase implement --runner orca
refute_spec "Unity fix session after the FAIL: the spec never commits" "commit explicit" dispatch "$ST" --task c1 --phase implement --runner orca
sv --task c1 --phase review --sha "$SC" --by codex --state PASS
st_phase "Unity review PASS is integrated at once; next is the per-task QA" c1 integrated "--task c1 --phase qa --sha $SC"
sv --task c1 --phase qa --sha "$SC" --by codex --state PASS
st_phase "per-task QA PASS: qa" c1 qa
st_phase "and the next Unity task is ready: its task lead" c2 pending "--task c2 --phase lead --runner orca"
refute "no gate command while c2 is pending" "^Next: .* gate " status "$ST"
mkdir -p "$C/Assets/D"; echo d > "$C/Assets/D/d.cs"; gi "$C" add Assets/D; gi "$C" commit -qm "feat: c2"; SD=$(git -C "$C" rev-parse HEAD)
sv --task c2 --phase review --sha "$SD" --by claude --state PASS
sv --task c2 --phase qa --sha "$SD" --by claude --state PASS
# agree <name>: status names the gate as next exactly when the gate (no registry checks here) is READY_FOR_PR
agree() {
  local out g rc
  out=$(python3 -B "$P" status --json "$ST" 2>&1); g=$(python3 -B "$P" gate "$ST" 2>&1); rc=$?
  if python3 -c 'import json,sys; o=json.loads(sys.argv[1]); said=any(" gate " in c for c in o["next"])
assert said == (sys.argv[2] == "0"), (o["next"], sys.argv[2])' "$out" "$rc"; then pass=$((pass + 1)); echo "PASS  $1"
  else fail=$((fail + 1)); echo "FAIL  $1 (gate rc=$rc)"; head -c 800 <<<"$out"; echo; sed 's/^/      /' <<<"$g" | head -10; fi
}
st_phase "per-task QA of every Unity task: integration QA at the HEAD is still due" c2 integrated "--task integration:cli --phase qa --sha $SD"
expect "and the missing integration QA is named" 0 "no integration QA for cli: the gate needs it" status "$ST"
refute "no gate command before the Unity integration QA" "^Next: .* gate " status "$ST"
expect "the gate agrees: integration QA missing" 1 "BLOCKER integration:cli: no qa verdict" gate "$ST"
agree "status and gate agree before the Unity integration QA"
sv --task integration:cli --phase qa --sha "$SC" --by codex --state PASS
st_phase "an integration QA on an older HEAD is STALE" c1 integrated "--task integration:cli --phase qa --sha $SD"
agree "status and gate agree on a stale integration QA"
sv --task integration:cli --phase qa --sha "$SD" --by codex --state PASS
expect "every task has QA: the plan-level next is the gate" 0 "^Next: .* gate .*st.json" status "$ST"
expect "and the gate is READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$ST"
agree "status and gate agree once every QA is at the HEAD"
expect "every wave integrated" 0 "^Every wave is integrated" status "$ST"
python3 -B "$P" status --json "$ST" > "$TMP/status.json" 2>&1
if python3 - "$ROOT" "$TMP/status.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
value = json.load(open(sys.argv[2], encoding="utf-8"))
assert value["schema"] == "rpg-factory.pipeline-status/1"
errors = m.schema_errors(value, schema, schema)
assert not errors, errors
PY
then pass=$((pass + 1)); echo "PASS  status --json matches docs/schemas/pipeline-status.schema.json"
else fail=$((fail + 1)); echo "FAIL  status --json schema"; head -c 800 "$TMP/status.json"; fi
sed -i 's/"objective":"o","paths":\["sa\/"\]/"objective":"changed","paths":["sa\/"]/' "$ST"
st_phase "a changed task in the plan: its review is no longer counted; review the integration HEAD" a candidate "--task a --phase review --sha $SI"
expect "and the stale verdict is named" 0 "review verdict is STALE: the plan's task changed" status "$ST"
X=$(plan stbad "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"nope\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "status of an invalid plan: exit 1, next is validate" 1 "^Next: .* validate " status "$X"
gi "$C" checkout -q feat/core/demo
git -C "$S" worktree remove "$TMP/st-b"; git -C "$S" worktree remove "$TMP/st-int"

echo "-- owned paths in another case (Windows: case-insensitive pathspecs)"
# The plan owns SRC/ while the commits touch src/a.txt. On Windows (os.name nt, as specs() checks) the owned-path check
# and the git pathspecs agree case-insensitively: status counts the commit and a later change makes the review STALE.
# Elsewhere git is case-sensitive: the commit is not the task's own, so the task is still implementing.
I="$WS/icase"; mkdir -p "$I"; git init -q -b develop "$I"; echo base > "$I/README.md"; gi "$I" add -A; gi "$I" commit -qm base
IC=$(plan icase '{"schema":"rpg-factory.pipeline-plan/1","id":"icase","title":"Case","topic":"feat/core/ic","deliver":"pr",
 "repos":{"ic":{"path":"ws/icase","base":"develop"}},"tasks":[{"id":"t","repo":"ic","objective":"o","paths":["SRC/"],"acceptance":["a"]}]}')
gi "$I" checkout -qb feat/core/ic-t; mkdir -p "$I/src"; echo a > "$I/src/a.txt"; gi "$I" add -A; gi "$I" commit -qm "feat: a"; IT=$(git -C "$I" rev-parse HEAD)
ic_phase() {  # ic_phase <name> <phase>: task t's phase in status --json
  local out; out=$(python3 -B "$P" status --json "$IC" 2>&1)
  if python3 -c 'import json,sys; r={t["id"]:t for t in json.loads(sys.argv[1])["tasks"]}["t"]; assert r["phase"]==sys.argv[2], r' "$out" "$2"
  then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; head -c 1200 <<<"$out"; echo; fi
}
if [ "$(python3 -c 'import os; print(os.name)')" = nt ]; then
  ic_phase "Windows: status counts a commit in src/ for the owned path SRC/ (candidate)" candidate
  python3 -B "$P" verdict "$IC" --task t --phase review --sha "$IT" --by codex --state PASS >/dev/null || echo "verdict failed: icase review"
  gi "$I" checkout -qb feat/core/ic develop; gi "$I" merge -q --no-ff feat/core/ic-t -m "merge t"; II=$(git -C "$I" rev-parse HEAD)
  python3 -B "$P" verdict "$IC" --task integration:ic --phase qa --sha "$II" --by codex --state PASS >/dev/null || echo "verdict failed: icase qa"
  expect "Windows: review and QA PASS on the owned path in another case: READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$IC"
  echo b >> "$I/src/a.txt"; gi "$I" commit -qam "fix: a after review"
  expect "Windows: a change to src/ after review makes the review of SRC/ STALE" 1 "BLOCKER t: review is STALE" gate "$IC"
  expect "Windows: and the QA on the old HEAD is STALE" 1 "BLOCKER ic: QA is STALE" gate "$IC"
else
  ic_phase "case-sensitive host: a commit in src/ is not the task's own for SRC/ (implementing)" implementing
fi

echo "-- dogfood two-level grader (offline, synthetic transcripts)"
# tl_transcript <file> <bash command> <its result text> [extra tool_use json]: a stream-json run lead transcript that
# loads factory-core, runs one Bash command (is_error false, as a pipe reports) and finishes with success
tl_transcript() {
  local f="$1" cmd="$2" res="$3" extra="${4:-}"
  {
    jq -nc '{type:"assistant",message:{content:[{type:"tool_use",id:"s1",name:"Skill",input:{skill:"rpg-factory:factory-core"}}]}}'
    jq -nc '{type:"user",message:{content:[{type:"tool_result",tool_use_id:"s1",content:"Launching skill: rpg-factory:factory-core"}]}}'
    jq -nc --arg c "$cmd" '{type:"assistant",message:{content:[{type:"tool_use",id:"b1",name:"Bash",input:{command:$c}}]}}'
    jq -nc --arg r "$res" '{type:"user",message:{content:[{type:"tool_result",tool_use_id:"b1",content:$r,is_error:false}]}}'
    [ -z "$extra" ] || jq -nc --argjson u "$extra" '{type:"assistant",message:{content:[$u]}}'
    jq -nc '{type:"result",subtype:"success",is_error:false}'
  } > "$f"
}
# grade <name> <rc> <grep-regex> <transcript>: tests/dogfood.sh --grade-two-level exit code and result line
grade() {
  local name="$1" want="$2" pat="$3" out rc; out=$(bash "$ROOT/tests/dogfood.sh" --grade-two-level "$4" 2>&1); rc=$?
  if [ "$rc" = "$want" ] && grep -qE -- "$pat" <<<"$out"; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, want $want, pattern '$pat')"; sed 's/^/      /' <<<"$out" | head -10; fi
}
LEAD_CMD='python3 -B scripts/factory-pipeline.py dispatch plan.json --task t --phase lead --runner print 2>&1 | head -60'
LEAD_OUT=$'# agent: claude   worktree: new-top-level   base: main\nTask lead for task t of plan p (Demo), references/parallel-work.md. You own this task and this task worktree.\n{\n  "plan": "p"\n}'
tl_transcript "$TMP/tl-pass.jsonl" "$LEAD_CMD" "$LEAD_OUT"
grade "grader: factory-core + successful print-runner lead dispatch: PASS" 0 "dispatch tool_use: b1 \| PASS$" "$TMP/tl-pass.jsonl"
tl_transcript "$TMP/tl-warn.jsonl" "$LEAD_CMD" "$LEAD_OUT"$'\nfactory-pipeline: `codex` is not on PATH here: the codex task lead may be unavailable'
grade "grader: a not-on-PATH warning next to the printed spec still passes" 0 "\| PASS$" "$TMP/tl-warn.jsonl"
tl_transcript "$TMP/tl-masked.jsonl" "$LEAD_CMD" "factory-pipeline: cannot read plan plan.json: [Errno 2] No such file or directory"
grade "grader: failed dispatch masked by a pipe (is_error false): FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch --phase lead" "$TMP/tl-masked.jsonl"
tl_transcript "$TMP/tl-trace.jsonl" "$LEAD_CMD" "$LEAD_OUT"$'\nTraceback (most recent call last):\n  File "x", line 1'
grade "grader: a traceback in the dispatch output: FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch" "$TMP/tl-trace.jsonl"
tl_transcript "$TMP/tl-tier.jsonl" "python3 -B scripts/factory-pipeline.py tier -- --repo plugin --paths scripts/factory-cmd.py" "Tier M"
grade "grader: tier only: FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch --phase lead" "$TMP/tl-tier.jsonl"
tl_transcript "$TMP/tl-edit.jsonl" "$LEAD_CMD" "$LEAD_OUT" '{"type":"tool_use","id":"e1","name":"Edit","input":{"file_path":"C:\\w\\rpg-factory\\skills\\factory-core\\SKILL.md","old_string":"a","new_string":"b"}}'
grade "grader: run lead edits skills/factory-core/SKILL.md: FAIL" 1 "FAIL: run lead edited task files with file tools: .*skills/factory-core/SKILL\.md" "$TMP/tl-edit.jsonl"
tl_transcript "$TMP/tl-orca.jsonl" "python3 -B scripts/factory-pipeline.py dispatch plan.json --task t --phase lead --runner orca" "orca worktree create --name feat/x --prompt 'Read your task spec at /s/t.md and follow it.' --json"
grade "grader: --runner orca dispatch: FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch --phase lead" "$TMP/tl-orca.jsonl"
grade "grader: missing transcript: FAIL" 1 "FAIL: no transcript" "$TMP/tl-none.jsonl"
if tail -n 1 "$ROOT/tests/dogfood.sh" | grep -qF '"${tl_fail:-0}" -eq 0'; then pass=$((pass + 1)); echo "PASS  dogfood --all exit status includes the two-level result"
else fail=$((fail + 1)); echo "FAIL  dogfood --all exit status includes the two-level result (last line of tests/dogfood.sh)"; fi

echo "-- recorded implementer"
# a fallback implementation is recorded: after the model returns, review pairs against the recorded implementer
R="$TMP/rec"; mkdir -p "$R/ProjectSettings" "$R/code" "$R/docs"; echo 'm_EditorVersion: 6000.0.0f1' > "$R/ProjectSettings/ProjectVersion.txt"
git init -q -b develop "$R"; echo a > "$R/code/a.cs"; echo a > "$R/docs/a.md"; gi "$R" add -A; gi "$R" commit -qm init
gi "$R" checkout -qb feat/core/rec; echo b > "$R/code/a.cs"; echo b > "$R/docs/a.md"; gi "$R" commit -qam "feat: b"; RS=$(git -C "$R" rev-parse HEAD)
RP=$(plan rec '{"schema":"rpg-factory.pipeline-plan/1","id":"rec","title":"Recorded","topic":"feat/core/rec","repos":{"rec":{"path":"rec","base":"develop"}},"tasks":[
 {"id":"k","repo":"rec","kind":"code","objective":"o","paths":["code/"],"acceptance":["a"]},
 {"id":"d","repo":"rec","kind":"docs","objective":"o","paths":["docs/"],"acceptance":["a"]},
 {"id":"q","repo":"rec","kind":"code","objective":"o","paths":["ProjectSettings/"],"acceptance":["a"]}]}')
RVD="$RPG_FACTORY_STATE_DIR/pipeline/rec"
RPG_FACTORY_AGENTS=claude expect "claude-only: the code task is implemented by claude (fallback)" 0 "implement -> claude" dispatch "$RP" --task k --phase implement --runner orca
expect "codex back: the review pairs against the recorded claude implementer" 0 "implement -> claude \(recorded implementer: fallback: codex unavailable\)" dispatch "$RP" --task k --phase review --sha "$RS" --runner print
expect "codex back: the review of the recorded claude implementation goes to codex" 0 "^# agent: codex" dispatch "$RP" --task k --phase review --sha "$RS" --runner print
expect "verdict records the recorded implementer" 0 "recorded review PASS for k" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS
expect "a claude review of the recorded claude implementation is not cross-model" 1 "BLOCKER k: reviewed by claude, cross-model review needs codex" gate "$RP" --no-run-checks
RPG_FACTORY_AGENTS=codex expect "codex-only: the docs task is implemented by codex (fallback)" 0 "implement -> codex" dispatch "$RP" --task d --phase implement --runner orca
expect "claude back: the review of the recorded codex implementation goes to claude" 0 "^# agent: claude" dispatch "$RP" --task d --phase review --sha "$RS" --runner print
python3 -B "$P" verdict "$RP" --task d --phase review --sha "$RS" --by codex --state PASS >/dev/null
expect "a codex review of the recorded codex implementation is not cross-model" 1 "BLOCKER d: reviewed by codex, cross-model review needs claude" gate "$RP" --no-run-checks
expect "per-task QA pairs against the recorded implementer too" 0 "qa -> codex" dispatch "$RP" --task k --phase qa --sha "$RS" --runner print
RPG_FACTORY_AGENTS=claude expect "no record: review pairs against the planned implementer, not availability" 0 "implement -> codex \(planned implementer: kind: code\)" dispatch "$RP" --task q --phase review --sha "$RS" --runner print
# verdict stamps a fallback only from this candidate's review dispatch and only for its reviewer
RPG_FACTORY_AGENTS=claude python3 -B "$P" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS >/dev/null
expect "claude-only verdict with no fallback review dispatch: still NOT_READY" 1 "BLOCKER k: reviewed by claude, cross-model review needs codex" gate "$RP" --no-run-checks
RPG_FACTORY_AGENTS=claude expect "claude-only review dispatch of the claude implementation is a SAME_MODEL fallback" 0 "review -> claude \(SAME_MODEL \(fallback: codex unavailable\)\)" dispatch "$RP" --task k --phase review --sha "$RS" --runner orca
python3 -B "$P" verdict "$RP" --task k --phase review --sha "$RS" --by codex --state FAIL >/dev/null
if ! grep -q '"fallback": "' "$RVD/k__review.json"; then pass=$((pass + 1)); echo "PASS  a verdict by another model than the dispatched fallback reviewer stamps no fallback"
else fail=$((fail + 1)); echo "FAIL  a verdict by another model than the dispatched fallback reviewer stamps no fallback"; fi
expect "the dispatched fallback reviewer's verdict is stamped (both models back)" 0 "recorded review PASS for k" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS
expect "gate accepts the dispatched fallback" 1 "NOTE    k: SAME_MODEL \(fallback: codex unavailable\)" gate "$RP" --no-run-checks
gi "$R" commit -q --allow-empty -m "chore: next"; RS2=$(git -C "$R" rev-parse HEAD)
RPG_FACTORY_AGENTS=claude python3 -B "$P" verdict "$RP" --task k --phase review --sha "$RS2" --by claude --state PASS >/dev/null
if ! grep -q '"fallback": "' "$RVD/k__review__${RS2:0:12}__claude.json"; then pass=$((pass + 1)); echo "PASS  a fallback dispatch of another candidate stamps no fallback"
else fail=$((fail + 1)); echo "FAIL  a fallback dispatch of another candidate stamps no fallback"; fi
# a subtask fallback is never laundered by the task review: subtask s by claude (codex down), codex back, task review by
# claude paired against the planned codex implementer
RSP=$(plan recsub '{"schema":"rpg-factory.pipeline-plan/1","id":"recsub","title":"Recorded subtasks","topic":"feat/core/rec","repos":{"rec":{"path":"rec","base":"develop"}},"tasks":[
 {"id":"k","repo":"rec","kind":"code","objective":"o","paths":["code/","docs/"],"acceptance":["a"]}]}')
RSS="$TMP/sub-recsub.json"
printf '%s\n' '{"schema":"rpg-factory.pipeline-subplan/1","plan":"recsub.json","task":"k","subtasks":[
 {"id":"s","objective":"o","kind":"code","paths":["code/"]},{"id":"s2","objective":"o","kind":"code","paths":["docs/a.md"]},
 {"id":"s3","objective":"o","kind":"docs","paths":["docs/b/"]}]}' > "$RSS"
RSVD="$RPG_FACTORY_STATE_DIR/pipeline/recsub"
rs() { python3 -B "$P" "$@" --runner orca >/dev/null 2>&1 || echo "dispatch failed: $*"; }
rv() { python3 -B "$P" verdict "$RSP" "$@" >/dev/null || echo "verdict failed: $*"; }
RPG_FACTORY_AGENTS=claude rs dispatch "$RSP" --task k --phase implement --subplan "$RSS" --subtask s
RPG_FACTORY_AGENTS=claude rs dispatch "$RSP" --task k --phase implement --subplan "$RSS" --subtask s2
rs dispatch "$RSP" --task k --phase review --sha "$RS2"
rv --task k --phase review --sha "$RS2" --by claude --state PASS
rv --task integration:rec --phase qa --sha "$RS2" --by codex --state PASS
expect "a claude fallback subtask is not laundered by the claude task review once codex is back" 1 "BLOCKER k: subtask s recorded implementer claude, but the task review by claude pairs against codex: record .verdict --subtask s. PASS by codex" gate "$RSP" --no-run-checks
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s
refute "a subtask review by its implementer's pair covers that subtask" "BLOCKER k: subtask s recorded" gate "$RSP" --no-run-checks
RPG_FACTORY_AGENTS=claude rs dispatch "$RSP" --task k --phase review --sha "$RS2" --subplan "$RSS" --subtask s2
rv --task k --phase review --sha "$RS2" --by claude --state PASS --subtask s2
expect "a dispatch-recorded SAME_MODEL fallback subtask review passes the gate" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
expect "and the gate notes the subtask fallback" 0 "NOTE    k: subtask s2 SAME_MODEL \(fallback: codex unavailable\)" gate "$RSP" --no-run-checks
# An ancestral PASS covers only unchanged reviewed paths; old records conservatively cover the whole task.
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s --subplan "$RSS"
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s2 --subplan "$RSS"
echo c > "$R/code/a.cs"; gi "$R" commit -qam "fix: later subtask edit"; RS3=$(git -C "$R" rev-parse HEAD)
rv --task k --phase review --sha "$RS3" --by claude --state PASS
rv --task integration:rec --phase qa --sha "$RS3" --by codex --state PASS
expect "a stale subtask PASS cannot cover the task reviewer's later edit: NOT_READY" 1 "BLOCKER k: subtask s .*changed paths code/a.cs; needs codex review" gate "$RSP" --no-run-checks
rv --task k --phase review --sha "$RS3" --by codex --state PASS --subtask s --subplan "$RSS"
expect "a fresh paired subtask review covers the later edit" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
echo c > "$R/docs/a.md"; gi "$R" commit -qam "docs: outside code subtask"; RS4=$(git -C "$R" rev-parse HEAD)
rv --task k --phase review --sha "$RS4" --by claude --state PASS
rv --task integration:rec --phase qa --sha "$RS4" --by codex --state PASS
rv --task k --phase review --sha "$RS4" --by codex --state PASS --subtask s2 --subplan "$RSS"
expect "an edit outside subtask paths keeps its ancestral review valid" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
# Restore the fixture candidate used by subsequent verdict routing checks.
RS2=$RS4
# verdict --subtask pairs against the subtask's routing: --subplan (docs subtask s3: claude), else its review dispatch
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s3 --subplan "$RSS"
if jq -e '.implementer == "claude"' "$RSVD/k@s3__review.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  verdict --subtask --subplan routes the implementer over the subtask's kind"
else fail=$((fail + 1)); echo "FAIL  verdict --subtask --subplan routes the implementer over the subtask's kind"; fi
rs dispatch "$RSP" --task k --phase review --sha "$RS" --subplan "$RSS" --subtask s3
rv --task k --phase review --sha "$RS" --by codex --state PASS --subtask s3
if jq -e '.implementer == "claude"' "$RSVD/k@s3__review__${RS:0:12}__codex.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  verdict --subtask takes the implementer its review dispatch routed"
else fail=$((fail + 1)); echo "FAIL  verdict --subtask takes the implementer its review dispatch routed"; fi
expect "verdict --fallback refuses an unknown agent" 2 "--fallback must be one of claude, codex" verdict "$RSP" --task k --phase review --sha "$RS2" --by claude --state PASS --fallback gemini
expect "verdict --fallback goes with review only" 2 "--fallback .* goes with --phase review" verdict "$RSP" --task k --phase qa --sha "$RS2" --by claude --state PASS --fallback codex
NOID=$(plan noid '{"schema":"rpg-factory.pipeline-plan/1","id":"noid","title":"t","topic":"feat/core/noid","repos":{"rec":{"path":"rec","base":"develop"}},"tasks":[{"repo":"rec","objective":"o","paths":["x/"],"acceptance":["a"]}]}')
expect "status of a task without id: INVALID" 1 "INVALID" status "$NOID"
refute "status of a task without id: no traceback" "Traceback" status "$NOID"
jq 'del(.pipeline.qa_prefer)' "$ROOT/registry.json" > "$TMP/reg-noqa.json"
out=$("$ROOT/scripts/check-registry.sh" --structure-only --registry "$TMP/reg-noqa.json" 2>&1)
if ! grep -qE "jq: error|qa_prefer" <<<"$out"; then pass=$((pass + 1)); echo "PASS  check-registry without pipeline.qa_prefer: no jq error"
else fail=$((fail + 1)); echo "FAIL  check-registry without pipeline.qa_prefer: no jq error"; echo "$out" | head -5; fi
# check_reg <name> <jq mutation> <problem regex>: check-registry.sh fails on the mutated registry and names the problem
check_reg() {
  local out rc; jq "$2" "$ROOT/registry.json" > "$TMP/reg-bad.json"
  out=$("$ROOT/scripts/check-registry.sh" --structure-only --registry "$TMP/reg-bad.json" 2>&1); rc=$?
  if [ "$rc" != 0 ] && grep -qE -- "$3" <<<"$out"; then pass=$((pass + 1)); echo "PASS  $1"
  else fail=$((fail + 1)); echo "FAIL  $1 (rc=$rc)"; echo "$out" | head -5; fi
}
check_reg "check-registry: unknown agent in agent_routing fails" '.pipeline.agent_routing.code = "gpt"' "pipeline.agent_routing: invalid kind or agent code"
check_reg "check-registry: unknown kind in agent_routing fails" '.pipeline.agent_routing.bogus = "claude"' "pipeline.agent_routing: invalid kind or agent bogus"
check_reg "check-registry: unknown agent in qa_prefer fails" '.pipeline.qa_prefer = "gpt"' "pipeline.qa_prefer: unknown agent"
check_reg "check-registry: unknown agent in available_agents fails" '.pipeline.available_agents = ["gpt"]' "pipeline.available_agents: unknown agent gpt"

echo "-- model routing"
cat > "$TMP/routing-cases.py" <<'ROUTING'
import importlib.util, json, os, pathlib, sys
from unittest.mock import patch
root, tmp, case = sys.argv[1:]
sys.path.insert(0, root + '/scripts/lib')
import pipeline_route as r
pipe = json.loads(pathlib.Path(root + '/registry.json').read_text())['pipeline']
both = {a: {'available': True} for a in pipe['agents']}
if case.startswith('kind-'):
    kind = case[len('kind-'):]
    assert kind in r.KINDS
    assert r.route(pipe, {'kind': kind}, both)[0] == pipe['agent_routing'][kind]
if case == 'overrides-and-qa':
    assert r.route(pipe, {'kind': 'code', 'implementer': 'claude'}, both)[0] == 'claude'
    assert r.warnings(pipe, [{'kind': 'code', 'implementer': 'claude'}])
    assert not r.warnings(pipe, [{'kind': 'code', 'implementer': 'claude', 'reason': 'special expertise'}])
    assert r.warnings(pipe, [{'kind': 'code'}] * 3)
    assert r.roles(pipe, {'kind': 'code'}, both)['qa'][0] == 'claude'
    assert r.roles(pipe, {'kind': 'docs'}, both)['qa'][0] == 'codex'
plan = {'id': 'routing-unit'}
for sole in ('claude', 'codex'):
    if case != 'availability-' + sole:
        continue
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': sole}):
        avail = r.available(pipe, plan)
        for kind in r.KINDS:
            roles = r.roles(pipe, {'kind': kind}, avail)
            assert all(agent == sole for agent, why in roles.values()), roles
            assert 'SAME_MODEL (fallback:' in roles['review'][1]
    bindir = pathlib.Path(tmp) / ('only-' + sole)
    bindir.mkdir(exist_ok=True)
    binary = bindir / (pipe['agents'][sole]['bin'] + ('.exe' if os.name == 'nt' else ''))
    binary.write_text('fixture')
    binary.chmod(0o755)
    with patch.dict(os.environ, {'PATH': str(bindir), 'PATHEXT': '.EXE;.CMD'}, clear=True):
        avail = r.available(pipe, plan)
        assert all(a == sole for a, why in r.roles(pipe, {'kind': 'code'}, avail).values())
if case == 'marks-and-empty':
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': 'claude,codex'}):
        r.mark(plan, 'codex', '401 revoked token')
        assert r.route(pipe, {'kind': 'code'}, r.available(pipe, plan)) == ('claude', 'fallback: codex unavailable')
        r.mark(plan, 'codex')
        assert r.available(pipe, plan)['codex']['available']
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': ''}):
        assert 'WARNING' in r.route(pipe, {'kind': 'code'}, r.available(pipe, plan))[1]
import subprocess
for label, payload, down in (
    ('no-auth', json.dumps({'result': {'codex': {'accounts': [], 'systemDefault': {'hasAuth': False}}}}), True),
    ('system-auth', json.dumps({'result': {'codex': {'accounts': [], 'systemDefault': {'hasAuth': True}}}}), False),
    ('account-auth', json.dumps({'result': {'codex': {'accounts': [{}], 'systemDefault': {'hasAuth': False}}}}), False),
    ('malformed', '{"result":null}', False),
):
    if case != 'orca-' + label:
        continue
    with patch.dict(os.environ, {'ORCA_WORKTREE_ID': 'fixture', 'PATH': 'orca-' + label,
                                'RPG_FACTORY_STATE_DIR': tmp + '/account-state'}, clear=True), \
         patch('pipeline_route.shutil.which', return_value='/fake'), \
         patch('pipeline_route.subprocess.run', return_value=subprocess.CompletedProcess([], 0, payload)):
        avail = r.available(pipe, {'id': 'account-' + label})
        assert avail['claude']['available']
        assert avail['codex']['available'] != down
if case == 'orca-offline':
    with patch.dict(os.environ, {'ORCA_WORKTREE_ID': 'fixture', 'PATH': 'orca-offline',
                                'RPG_FACTORY_STATE_DIR': tmp + '/account-state'}, clear=True), \
         patch('pipeline_route.shutil.which', return_value='/fake'), \
         patch('pipeline_route.subprocess.run', side_effect=OSError('offline')):
        assert all(a['available'] for a in r.available(pipe, {'id': 'account-offline'}).values())
spec = importlib.util.spec_from_file_location('routing_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
reg = json.loads(pathlib.Path(root + '/registry.json').read_text())
plan = {'schema': m.SCHEMA, 'id': 'route-validation', 'title': 'test', 'topic': 'test',
        'repos': {'plugin': {'path': root}},
        'tasks': [{'id': 't', 'repo': 'plugin', 'kind': 'code', 'implementer': 'claude',
                   'objective': 'x', 'paths': ['scripts/'], 'acceptance': ['x']}]}
if case == 'followup-validation':
    plan['tasks'][0].pop('kind')
    plan['tasks'][0]['implementer'] = 'claude' if r.route(pipe, {}, both)[0] == 'codex' else 'codex'
    assert any('default routing without reason' in w for w in m.validate(plan, reg)['warnings'])
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x'], 'implementer': plan['tasks'][0]['implementer']}]}
    assert any('default routing without reason' in w for w in m.validate_subplan(sub, plan, reg)['warnings'])
    custom = dict(pipe, agent_routing={})
    other = next(agent for agent in pipe['agents'] if agent != pipe['default_implementer'])
    assert r.warnings(custom, [{'implementer': other}])
    assert r.warnings(custom, [{'kind': 'code', 'implementer': other}]) == [
        '?: implementer overrides default routing without reason']
    assert not r.warnings(custom, [{'implementer': other, 'reason': 'expertise'}])
    plan['tasks'][0]['kind'] = 'outside-schema'
    assert m.validate(plan, reg)['errors']
if case == 'followup-legacy':
    with patch.object(m, 'verdict_dir', return_value=tmp + '/legacy-followup'), \
         patch.object(m, 'scope_fingerprint', return_value='current'), \
         patch.object(m, 'repo_info', return_value={'path': root}):
        directory = pathlib.Path(m.verdict_dir(plan))
        directory.mkdir(exist_ok=True)
        legacy = {'task': 't', 'subtask': 'a', 'phase': 'review', 'sha': 'abc',
                  'state': 'FAIL', 'by': 'codex', 'fingerprint': 'current'}
        (directory / 't__sub-a__review.json').write_text(json.dumps(legacy))
        (directory / 't@a__review__b__review.json').write_text(json.dumps(dict(legacy, subtask='a__review__b', state='PASS')))
        assert m.subtask_failures(plan, reg, 't', 'abc')
        current = directory / 't@a__review.json'
        current.write_text(json.dumps(dict(legacy, state='PASS', fingerprint='stale')))
        assert m.subtask_failures(plan, reg, 't', 'abc')
        current.write_text(json.dumps(dict(legacy, state='PASS')))
        assert not m.subtask_failures(plan, reg, 't', 'abc')
        current.rename(directory / 't@a__review__0123456789ab__codex.json')
        assert not m.subtask_failures(plan, reg, 't', 'abc')
if case == 'validation':
    assert any('without reason' in w for w in m.validate(plan, reg)['warnings'])
    plan['tasks'][0]['reason'] = 'expertise'
    assert not m.validate(plan, reg)['warnings']
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x'], 'implementer': 'gpt'}]}
    assert any('implementer `gpt` is not' in e for e in m.validate_subplan(sub, plan, reg)['errors'])
    sub['subtasks'][0].update(implementer='claude', kind='code')
    assert any('without reason' in w for w in m.validate_subplan(sub, plan, reg)['warnings'])
    sub['subtasks'][0]['reason'] = 'expertise'
    assert not m.validate_subplan(sub, plan, reg)['warnings']
import subprocess
project = pathlib.Path(tmp) / 'routing-project'
(project / 'ProjectSettings').mkdir(parents=True, exist_ok=True)
(project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.0f1')
plan['repos']['plugin']['path'] = str(project)
plan['repos']['plugin']['base'] = 'main'
planfile = pathlib.Path(tmp) / 'routing-command-plan.json'
plan['tasks'][0].pop('implementer', None)
planfile.write_text(json.dumps(plan))
if case == 'followup-preview':
    state = tmp + '/preview-state'
    env = dict(os.environ, RPG_FACTORY_AGENTS='claude,codex', RPG_FACTORY_STATE_DIR=state)
    for runner in ('print', 'orca', 'agent'):
        for phase in ('implement', 'review'):
            args = [sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'dispatch', str(planfile),
                    '--task', 't', '--phase', phase, '--runner', runner]
            if phase == 'review':
                args += ['--sha', 'abc1234']
            if runner == 'agent':
                args += ['--orca-unavailable', 'fixture']
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            assert result.returncode == 0, result.stderr
            records = list(pathlib.Path(state).rglob('*.model.json'))
            assert bool(records) == (runner != 'print'), records
            if runner != 'print':
                role = 'implementer' if phase == 'implement' else 'reviewer'
                assert any('__' + role in record.name for record in records), records
                for record in records:
                    record.unlink()
    for reason in (None, 'revoked'):
        args = [sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'agents', str(planfile), '--down', 'codex']
        if reason:
            args += ['--reason', reason]
        result = subprocess.run(args, capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stdout.count('MODEL_UNAVAILABLE') == 1, result.stdout
        assert ('MODEL_UNAVAILABLE: revoked' if reason else 'MODEL_UNAVAILABLE') in result.stdout
for sole in ('claude', 'codex'):
    if case != 'dispatch-' + sole and case != 'status-' + sole:
        continue
    # own state per case: an implement dispatch records its model, which later review/QA dispatches pair against
    env = dict(os.environ, RPG_FACTORY_AGENTS=sole, RPG_FACTORY_STATE_DIR=tmp + '/state-' + case)
    if case == 'status-' + sole:
        result = subprocess.run([sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'status', str(planfile), '--json'], capture_output=True, text=True, encoding='utf-8', env=env)
        models = json.loads(result.stdout)['models']['t']
        assert all(x['agent'] == sole and x['why'] for x in models.values()), models
        assert 'SAME_MODEL (fallback:' in models['review']['why']
        continue
    for phase in ('lead', 'implement', 'review', 'qa'):
        args = [sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'dispatch', str(planfile),
                '--task', 't', '--phase', phase, '--runner', 'print']
        if phase == 'lead':
            args += ['--agent', 'codex' if sole == 'claude' else 'claude']
        if phase in ('review', 'qa'):
            args += ['--sha', 'abc1234']
        result = subprocess.run(args, capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert '# agent: ' + sole in result.stdout, result.stdout
        assert 'model: ' + phase + ' -> ' + sole in result.stderr, result.stderr
        if phase == 'lead':
            assert 'the task lead is ' + sole in result.stderr and 'always' not in result.stderr
            if sole == 'codex':
                assert 'fallback: claude unavailable' in result.stderr
if case == 'registry-defaults':
    custom = dict(pipe, available_agents=['claude'], agent_routing=dict(pipe['agent_routing'], default='codex'))
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': 'claude,codex'}):
        avail = r.available(custom, {'id': 'candidate-set'})
        assert not avail['codex']['available']
        assert avail['codex']['why'] == 'not in pipeline.available_agents'
    assert r.route(custom, {}, both) == ('codex', 'agent_routing.default')
if case == 'planned-warning':
    assert not r.warnings(pipe, [{'kind': k} for k in ('code', 'docs', 'test')])
if case == 'subtask-kind':
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x']}]}
    assert 'subtask s: missing implementer (or kind)' in m.validate_subplan(sub, plan, reg)['errors']
    sub['subtasks'][0]['kind'] = 'code'
    assert not m.validate_subplan(sub, plan, reg)['errors']
if case == 'no-probe':
    import shutil
    orig_run, orig_which, started = subprocess.run, shutil.which, []
    def spy(args, *k, **kw):
        if isinstance(args, (list, tuple)) and list(args[:1]) == ['orca']:
            started.append(args)
            return subprocess.CompletedProcess(args, 0, '{}')
        return orig_run(args, *k, **kw)
    env = {k: v for k, v in os.environ.items() if k != 'RPG_FACTORY_AGENTS'}
    env['ORCA_WORKTREE_ID'] = 'fixture'
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x'], 'kind': 'code'}]}
    with patch.dict(os.environ, env, clear=True), patch('subprocess.run', spy), \
         patch('shutil.which', lambda n, *a, **k: '/fake' if n == 'orca' else orig_which(n, *a, **k)):
        m.validate(plan, reg)
        m.validate_subplan(sub, plan, reg)
        assert not started, started
        r.available(pipe, {'id': 'probe-control'})
        assert started, 'control: available() starts the orca account probe'
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': 'claude,codex'}), \
         patch('pipeline_route.fstate.read_json', side_effect=AssertionError('marks read')):
        r.available(pipe, None)  # the planner: no per-run marks
        try:
            r.available(pipe, {'id': 'marks-control'})
            raise RuntimeError('control: a plan reads its marks')
        except AssertionError as e:
            assert 'marks read' in str(e)
if case == 'kinds-single-list':
    import re
    kinds = list(r.KINDS)
    assert set(kinds) == set(pipe['agent_routing']) - {'default'}, pipe['agent_routing']
    def find(node, key, out):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    out.append(v)
                find(v, key, out)
        elif isinstance(node, list):
            for v in node:
                find(v, key, out)
        return out
    for name in ('pipeline-plan', 'pipeline-subplan'):
        schema = json.loads(pathlib.Path(root + '/docs/schemas/' + name + '.schema.json').read_text(encoding='utf-8'))
        found = [v['enum'] for v in find(schema, 'kind', []) if isinstance(v, dict) and 'enum' in v]
        assert found and all(e == kinds for e in found), (name, found)
    schema = json.loads(pathlib.Path(root + '/docs/registry.schema.json').read_text(encoding='utf-8'))
    found = [v['propertyNames']['enum'] for v in find(schema, 'agent_routing', []) if isinstance(v, dict) and 'propertyNames' in v]
    assert found and all(e == kinds + ['default'] for e in found), found
    text = pathlib.Path(root + '/scripts/check-registry.sh').read_text(encoding='utf-8')
    listed = re.search(r'agent_routing // \{\}\) \| to_entries\[\]\s*\|\s*select\(\(\.key \| IN\(([^)]*)\)', text)
    assert listed and [x.strip().strip('"') for x in listed.group(1).split(',')] == kinds + ['default'], listed
print('routing assertions passed')
ROUTING
expect_route() {
  local name="$1" out rc
  out=$(python3 -B "$TMP/routing-cases.py" "$ROOT" "$TMP" "$name" 2>&1); rc=$?
  if [ "$rc" = 0 ]; then pass=$((pass + 1)); echo "PASS  routing $name"
  else fail=$((fail + 1)); echo "FAIL  routing $name"; echo "$out"; fi
}
expect_route kind-lead
expect_route kind-plan
expect_route kind-docs
expect_route kind-policy
expect_route kind-design
expect_route kind-code
expect_route kind-test
expect_route kind-fix
expect_route kind-refactor
expect_route kind-generated
expect_route overrides-and-qa
expect_route availability-claude
expect_route availability-codex
expect_route marks-and-empty
expect_route orca-no-auth
expect_route orca-system-auth
expect_route orca-account-auth
expect_route orca-malformed
expect_route orca-offline
expect_route validation
expect_route followup-validation
expect_route followup-legacy
expect_route followup-preview
expect_route dispatch-claude
expect_route dispatch-codex
expect_route status-claude
expect_route status-codex
expect_route registry-defaults
expect_route planned-warning
expect_route subtask-kind
expect_route no-probe
expect_route kinds-single-list

total=$((pass + fail)); echo "pipeline tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
