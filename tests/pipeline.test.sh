#!/usr/bin/env bash
# factory-pipeline.py on a throwaway workspace (a server repo and a Unity client project): tiers, plan validation
# (ownership, cycles, cross-model review, the no-worktree rule for Unity projects, exclusive resources), dispatch
# commands for Orca and the Agent fallback, verdicts and the READY_FOR_PR gate. Never touches the real workspace.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
P="$ROOT/scripts/factory-pipeline.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export RPG_FACTORY_STATE_DIR="$TMP/state" TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws"
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
expect "the task-lead spec names the subplan schema, plan and task" 0 "pipeline-subplan.schema.json; .plan. is .*ok.json, .task. is gw" dispatch "$OK" --task gw --phase lead

echo "-- dispatch"
expect "server task lead: Orca creates the task worktree from the base on the task branch" 0 "^orca worktree create --name feat/core/demo-gw --repo '?path:[^ ]*rpg-mmo-server'? --base-branch develop --branch feat/core/demo-gw --no-parent " dispatch "$OK" --task gw --phase lead --runner orca
refute "the task lead is no nested Orca worker (no worker-start)" "^orca orchestration worker-start" dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead runs the planned implementer" 0 "--no-parent --agent claude --prompt " dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead creates its own Orca Run" 0 "Create your OWN Run \(.orca orchestration run-create" dispatch "$OK" --task gw --phase lead
expect "task lead reports to the run lead's Orca run" 0 "orca orchestration send --to run:R42 --type status --subject .task done: gw" dispatch "$OK" --task gw --phase lead --report-to R42
expect "--report-to goes only with the lead" 2 "--report-to .* goes with --phase lead" dispatch "$OK" --task gw --phase implement --report-to R42
for pat in '"owned_paths": \[' '"backend/gateway/"' '"branch": "feat/core/demo-gw"' '"acceptance": \[' "subplan validate <subplan.json>" \
  "ONE fresh Claude or Codex session in this task worktree" "--phase implement --paths <subtask paths>" "do NOT commit \(one shared index\)" \
  "commit that subtask yourself with explicit paths" "Codex reviews Claude's work, Claude reviews Codex's" "here codex for claude" \
  "SAME_MODEL fallback" "--phase qa --sha <HEAD>" "FAIL goes to a fresh fix session" "worker-release" \
  "to the run lead: branch feat/core/demo-gw, HEAD SHA" "Never push, merge, tag or remove the worktree"; do
  expect "task-lead spec: $pat" 0 "$pat" dispatch "$OK" --task gw --phase lead
done
expect "Unity task lead: an agent launched in the main checkout" 0 "^orca agent launch --agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task c1 --phase lead --runner orca
refute "Unity task lead never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase lead --runner orca
refute "Unity task lead in the agent fallback never creates a worktree" "isolation|Create your own worktree" dispatch "$OK" --task c1 --phase lead --runner agent
expect "Unity task lead runs subtasks one after another" 0 "Subtasks run one after another" dispatch "$OK" --task c1 --phase lead
refute "Unity review never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c2 --phase review --sha abc1234 --runner orca
refute "Unity per-task qa never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase qa --sha abc1234 --runner orca
expect "Unity task lead works on the integration branch in the main checkout" 0 "No worktree: .*on branch feat/core/demo;" dispatch "$OK" --task c1 --phase lead
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
expect "registry worktrees=false: implement does not commit" 0 "Do NOT commit, stage or stash" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
refute "registry worktrees=false: implement never commits or creates a worktree" "commit explicit|new-top-level|--base-branch|worktree create" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
expect "Unity marker (unregistered repo): implement does not commit" 0 "Do NOT commit, stage or stash" dispatch "$TOOL" --task t --phase implement --runner orca
refute "Unity marker: implement never commits or creates a worktree" "commit explicit|new-top-level|--base-branch|worktree create" dispatch "$TOOL" --task t --phase implement --runner orca
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
expect "implement sub-session does not commit" 0 "Do NOT commit, stage or stash: the" dispatch "$OK" --task gw --phase implement
expect "implement sub-session reports changed paths and check counts to the task lead" 0 "report to the task lead: " dispatch "$OK" --task gw --phase implement
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
git -C "$S" worktree remove "$TMP/demo-gw"; git -C "$S" branch -q -D feat/core/demo-gw
# integration QA joins the checkout of plan.topic; without one it is an error and no worktree is created
before=$(git -C "$S" worktree list --porcelain); out=$(python3 -B "$P" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca 2>&1); rc=$?
if [ "$rc" = 1 ] && grep -q "no worktree of .* has the integration branch feat/core/demo checked out" <<<"$out" && grep -q "No worktree was created" <<<"$out" \
   && ! grep -q "new-top-level" <<<"$out" && [ "$before" = "$(git -C "$S" worktree list --porcelain)" ]; then pass=$((pass + 1)); echo "PASS  integration QA without the integration checkout: error, no worktree"
else fail=$((fail + 1)); echo "FAIL  integration QA without the integration checkout (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
git -C "$S" worktree add -q "$TMP/demo-int" -b feat/core/demo develop 2>/dev/null
expect "integration QA joins the integration checkout of plan.topic" 0 "--agent codex --worktree '?path:[^' ]*demo-int'?" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
refute "integration QA never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
expect "integration QA checks HEAD is the candidate in the shared checkout" 0 "You share the integration checkout .*demo-int with the run lead" dispatch "$OK" --task integration:server --phase qa --sha abc1234
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
expect "Unity tasks need their own QA, one after another" 1 "BLOCKER c1: no qa verdict" gate "$G"
v --task c1 --phase qa --sha "$C1" --by codex --state PASS
v --task c2 --phase qa --sha "$C1" --by codex --state PASS
expect "per-task QA on a commit without the reviewed one blocks" 1 "BLOCKER c2: QA ran on .* does not contain the reviewed commit" gate "$G"
v --task c2 --phase qa --sha "$C2" --by codex --state PASS
expect "all verdicts PASS on the integrated tree: READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$G"
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
git -C "$S" worktree add -q "$TMP/st-int" -b feat/core/st develop 2>/dev/null
st_phase "review PASS: next merges the task branch into the integration worktree" a reviewed "merge --no-ff feat/core/st-a"
gi "$TMP/st-int" merge -q --no-ff feat/core/st-a -m "merge a"
st_phase "merged after review PASS: integrated" a integrated '^$'
expect "QA waits for the other tasks of the repo" 0 "QA runs once all tasks of the repo are integrated: waits for b" status "$ST"
st_phase "the dependency is integrated: b is ready, next starts its task lead" b pending "--task b --phase lead"
expect "ready tasks span waves: b (wave 3) next to c1 (wave 1)" 0 "^Ready wave: 1  \(dispatch: b, c1\)$" status "$ST"
git -C "$S" worktree remove "$TMP/st-a"; git -C "$S" branch -q -D feat/core/st-a
st_phase "a removed task branch stays integrated (verdict + integration branch)" a integrated
git -C "$S" worktree add -q "$TMP/st-b" -b feat/core/st-b feat/core/st 2>/dev/null
st_phase "a task branch cut from the integration branch, no own commits yet: implementing" b implementing
mkdir -p "$TMP/st-b/sb"; echo b > "$TMP/st-b/sb/b.go"; gi "$TMP/st-b" add sb; gi "$TMP/st-b" commit -qm "feat: b"; SB=$(git -C "$S" rev-parse feat/core/st-b)
sv --task b --phase review --sha "$SB" --by codex --state PASS
gi "$TMP/st-int" merge -q --no-ff feat/core/st-b -m "merge b"; SI=$(git -C "$S" rev-parse feat/core/st)
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
expect "Unity fix session after the FAIL does not commit" 0 "Do NOT commit, stage or stash" dispatch "$ST" --task c1 --phase implement --runner orca
refute "Unity fix session after the FAIL has no committing prompt and no worktree" "commit explicit|new-top-level|--base-branch|worktree create" dispatch "$ST" --task c1 --phase implement --runner orca
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

total=$((pass + fail)); echo "pipeline tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
