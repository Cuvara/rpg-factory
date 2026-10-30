#!/usr/bin/env bash
# End-to-end authoring to engineering handoff, lifecycle and invalidation fixture.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
T=$(mktemp_win) || exit 1
trap 'rm -rf "$T"' EXIT
export TMPDIR="$T" RPG_FACTORY_STATE_DIR="$T/state"
A="$T/authoring"; S="$T/server"; mkdir -p "$A/design/features" "$S/backend"
for r in "$A" "$S"; do git -C "$r" init -q -b main; git -C "$r" config user.name Fixture; git -C "$r" config user.email fixture@example.test; done
ssh-keygen -q -t ed25519 -N '' -f "$T/approver" -C p6-approver
KEY=$(cat "$T/approver.pub")
cat > "$T/registry.json" <<EOF
{"repos":{"authoring":{},"server":{}},"domains":{"design":{"artifact_kinds":["feature-spec"],"human_gates":["design-review"],"approvers":[{"principal":"Maintainer","ssh_public_key":"$KEY"}]},"engineering":{"repos":["server"]}},"contracts":[{"id":"feature-spec-to-impl","kind":"handoff","domain":"design","source":{"repo":"authoring","path":"design/features/"},"copies":[{"repo":"server","path":"backend/"}],"driver":"game-design","gate":null,"evidence":"artifact-trace"}],"skills":{"game-design":{"domain":"design"}},"artifact_lifecycles":{"default":{"states":["draft","review","approved","in-implementation","verified","released"],"transitions":{"draft":["review"],"review":["approved"],"approved":["in-implementation"],"in-implementation":["verified"],"verified":["released"],"released":[]},"requirements":{"approved":{"needs_approval":["design-review"]},"in-implementation":{"needs_approval":["design-review"],"needs_trace":["impl"]},"verified":{"needs_approval":["design-review"],"needs_trace_for_test":["impl","test"]},"released":{"needs_approval":["design-review"],"needs_trace":["release"],"needs_trace_for_test":["impl","test"]}}}}}
EOF
F="$A/design/features/crafting.md"
write_artifact() { python3 - "$F" "$1" "$2" <<'PY'
import json,sys
p,status,trace=sys.argv[1:]
o={"id":"FS-P6-001","kind":"feature-spec","domain":"design","status":status,"title":"Crafting","upstream":[],"acceptance":[{"id":"AC1","text":"Crafting works","verify":"test"}],"trace":json.loads(trace)}
open(p,"w",encoding="utf-8").write("---json\n"+json.dumps(o,sort_keys=True)+"\n---\n")
PY
}
approve_current() {
  local rev
  rev=$(git -C "$A" hash-object -w "$F")
  mkdir -p "$A/approvals/FS-P6-001"
  python3 - "$A/approvals/FS-P6-001/design-review-$rev.json" "$rev" <<'PY'
import json,sys
json.dump({"artifact":"FS-P6-001","gate":"design-review","scope":"design","rev":sys.argv[2],"by":"Maintainer","date":"2026-10-30T00:00:00Z"},open(sys.argv[1],"w"),sort_keys=True)
PY
  git -C "$A" add design/features/crafting.md "approvals/FS-P6-001/design-review-$rev.json"
  git -C "$A" -c gpg.format=ssh -c user.signingkey="$T/approver" commit -q -S -m "Approve feature revision"
}
trace() { python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$A" --registry "$T/registry.json" --repos server="$S"; }
pass=0; fail=0
expect() { local label="$1" expected="$2" actual="$3"; if [[ "$actual" == "$expected" ]]; then pass=$((pass+1)); echo "PASS $label: $actual"; else fail=$((fail+1)); echo "FAIL $label: expected [$expected], got [$actual]"; fi; }
write_artifact draft '[]'; git -C "$A" add design; git -C "$A" commit -q -m draft
expect draft 'PASS FS-P6-001 trace and approvals verified' "$(trace | head -1)"
write_artifact review '[]'; git -C "$A" add design; git -C "$A" commit -q -m review
expect review 'PASS FS-P6-001 trace and approvals verified' "$(trace | head -1)"
write_artifact approved '[]'; git -C "$A" add design; git -C "$A" commit -q -m approved
expect approval-required 'HUMAN_REQUIRED FS-P6-001 missing approval' "$(trace | head -1)"
approve_current
expect signed-approval 'PASS FS-P6-001 trace and approvals verified' "$(trace | head -1)"
write_artifact in-implementation '[]'; git -C "$A" add design; git -C "$A" commit -q -m implementation
approve_current
git -C "$S" -c user.name=Fixture -c user.email=fixture@example.test commit --allow-empty -q -m implementation
IMPL=$(git -C "$S" rev-parse HEAD)
git -C "$S" -c user.name=Fixture -c user.email=fixture@example.test commit --allow-empty -q -m tests
TEST=$(git -C "$S" rev-parse HEAD)
SPEC_REV=$(git -C "$A" rev-parse "HEAD:design/features/crafting.md")
TR="[{\"repo\":\"server\",\"ref\":\"$IMPL\",\"kind\":\"impl\",\"ac\":[\"AC1\"],\"spec_rev\":\"$SPEC_REV\"},{\"repo\":\"server\",\"ref\":\"$TEST\",\"kind\":\"test\",\"ac\":[\"AC1\"]}]"
write_artifact verified "$TR"; git -C "$A" add design; git -C "$A" commit -q -m verified
approve_current
expect verified 'PASS FS-P6-001 trace and approvals verified' "$(trace | head -1)"
git -C "$S" tag v-fixture
REL=$(git -C "$S" rev-parse HEAD)
TR="[{\"repo\":\"server\",\"ref\":\"$IMPL\",\"kind\":\"impl\",\"ac\":[\"AC1\"],\"spec_rev\":\"$SPEC_REV\"},{\"repo\":\"server\",\"ref\":\"$TEST\",\"kind\":\"test\",\"ac\":[\"AC1\"]},{\"repo\":\"server\",\"ref\":\"$REL\",\"kind\":\"release\",\"ac\":[\"AC1\"]}]"
write_artifact released "$TR"; git -C "$A" add design; git -C "$A" commit -q -m released
approve_current
expect released 'PASS FS-P6-001 trace and approvals verified' "$(trace | head -1)"
write_artifact released "$TR"; python3 - "$F" <<'PY'
import sys
p=sys.argv[1];s=open(p,encoding="utf-8").read().replace('"title": "Crafting"','"title": "Crafting Reworked"');open(p,"w",encoding="utf-8").write(s)
PY
git -C "$A" add design; git -C "$A" commit -q -m "Edit spec after implementation"
out=$(trace)
expect stale-approval 'HUMAN_REQUIRED FS-P6-001 missing approval' "$(grep '^HUMAN_REQUIRED' <<<"$out" | head -1)"
expect stale-downstream "FAIL downstream-stale FS-P6-001 impl server@$IMPL" "$(grep '^FAIL downstream-stale' <<<"$out" | head -1)"
graph=$(python3 - "$T/registry.json" "$ROOT/scripts/lib/context.py" <<'PY'
import importlib.util,json,sys
spec=importlib.util.spec_from_file_location("context",sys.argv[2]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
order,cycle=m.handoff_graph(json.load(open(sys.argv[1],encoding="utf-8")),"design")
print("CYCLE: "+" -> ".join(cycle) if cycle else "Dependency graph: "+" -> ".join(order))
PY
); rc=$?
expect graph-order 'Dependency graph: design -> engineering' "$graph"
echo "handoff-e2e: $((pass+fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
