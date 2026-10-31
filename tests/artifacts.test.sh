#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
pass=0; fail=0; skip=0
ok() { pass=$((pass+1)); echo "PASS $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
skp() { skip=$((skip+1)); echo "SKIP $1"; }
T=$(mktemp_win) || exit 1; trap 'rm -rf "$T"' EXIT
R="$T/author"; P="$T/product"; D="$T/design-author"; mkdir -p "$R" "$P" "$D"
git -C "$R" init -q -b main; git -C "$P" init -q -b main; git -C "$D" init -q -b main
for repo in "$R" "$P" "$D"; do git -C "$repo" config user.name Fixture; git -C "$repo" config user.email fixture@example.test; done
cat > "$T/reg.json" <<'EOF'
{"domains":{"fixture":{"artifact_kinds":["spec","feature-spec"],"human_gates":["review","gameplay-rules"],"approvers":[]}},"artifact_lifecycles":{"default":{"states":["draft","review","approved","in-implementation","verified","released","deprecated"],"transitions":{"draft":["review"],"review":["approved"],"approved":["in-implementation"],"in-implementation":["verified"],"verified":["released"],"released":["deprecated"],"deprecated":["draft"]},"requirements":{"approved":{"needs_approval":["review"],"approval_when_binding":true},"in-implementation":{"needs_trace":["impl"],"approval_when_binding":true},"verified":{"needs_trace_for_test":["impl","test"],"approval_when_binding":true},"released":{"needs_trace":["release"],"needs_trace_for_test":["impl","test"],"approval_when_binding":true}}},"feature-spec":{"states":["draft","approved"],"transitions":{"draft":["approved"],"approved":[]},"requirements":{"approved":{"approval_when_binding":["gameplay-rules"]}}}}}
EOF
cat > "$T/make.py" <<'PY'
import json,sys
base=sys.argv[1]; status=sys.argv[2]; verify=sys.argv[3] if len(sys.argv)>3 else "review"; binding=len(sys.argv)>4 and sys.argv[4]=="binding"
o={"id":"FX-test-001","kind":"spec","domain":"fixture","status":status,"title":"Fixture","upstream":[],"acceptance":[{"id":"AC1","text":"Works","verify":verify}],"trace":[]}
if binding: o["binding_values"]=True
open(base+"/spec.md","w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
git -C "$P" -c user.name=Fixture -c user.email=fixture@example.test commit --allow-empty -qm product
export TMPDIR="$T" RPG_FACTORY_STATE_DIR="$T/state"
python3 "$T/make.py" "$R" draft test
git -C "$R" add spec.md; git -C "$R" commit -qm init
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'PASS FX-test-001 trace and approvals verified' ]] && ok 'draft test criterion needs no trace' || bad "draft coverage: $got"
python3 "$T/make.py" "$R" draft review binding
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'PASS FX-test-001 trace and approvals verified' ]] && ok 'draft binding values need no approval' || bad "draft binding: $got"
write_design() {
  python3 - "$D/feature.md" "$1" "${2:-false}" <<'PY'
import json,sys
obj={"id":"ZZ-test-001","kind":"feature-spec","domain":"fixture","status":sys.argv[2],"title":"Value-free feature","upstream":[],"acceptance":[],"trace":[]}
if sys.argv[3] == "true": obj["binding_values"]=True
open(sys.argv[1],"w",encoding="utf-8").write("---json\n"+json.dumps(obj)+"\n---\n")
PY
}
write_design draft false; git -C "$D" add feature.md; git -C "$D" commit -qm 'Draft value-free feature spec'
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$D" --registry "$T/reg.json" --repos product="$P" | grep '^PASS ZZ-test-001'); [[ "$got" == 'PASS ZZ-test-001 trace and approvals verified' ]] && ok 'value-free draft feature spec needs no approval' || bad "value-free draft: $got"
write_design approved true; git -C "$D" add feature.md; git -C "$D" commit -qm 'Approve binding feature spec'
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$D" --registry "$T/reg.json" --repos product="$P" | grep '^HUMAN_REQUIRED ZZ-test-001'); [[ "$got" == 'HUMAN_REQUIRED ZZ-test-001 missing approval' ]] && ok 'approved binding feature spec requires gameplay-rules approval' || bad "binding feature: $got"
write_design approved false; git -C "$D" add feature.md; git -C "$D" commit -qm 'Approve value-free feature spec'
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$D" --registry "$T/reg.json" --repos product="$P" | grep '^PASS ZZ-test-001'); [[ "$got" == 'PASS ZZ-test-001 trace and approvals verified' ]] && ok 'approved value-free feature spec needs no approval' || bad "value-free approved: $got"
rm "$D/feature.md"
python3 "$T/make.py" "$R" draft
line() { python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$R" --registry "$T/reg.json" | head -1; }
got=$(line); [[ "$got" == 'PASS FX-test-001' ]] && ok 'valid artifact' || bad "valid artifact: $got"
python3 - "$R/spec.md" <<'PY'
import json,sys
p=sys.argv[1]; s=open(p).read(); o=json.loads(s.split("\n",1)[1].split("\n---",1)[0]);o["title"]="";open(p,"w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
got=$(line); [[ "$got" == 'FAIL FX-test-001 $.title is too short; bad title' ]] && ok 'bad schema rejected' || bad "bad schema: $got"
python3 "$T/make.py" "$R" draft
git -C "$R" add spec.md; git -C "$R" commit --allow-empty -qm restore
python3 "$T/make.py" "$R" review
git -C "$R" add spec.md; git -C "$R" commit -qm review
got=$(line); [[ "$got" == 'WARN deprecated-state review -> proposed FX-test-001' ]] && ok 'legacy review alias warns' || bad "legal transition: $got"
python3 "$T/make.py" "$R" verified
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$R" --registry "$T/reg.json" | head -1); [[ "$got" == 'FAIL FX-test-001 illegal transition'* ]] && ok 'illegal transition rejected' || bad "illegal transition: $got"
python3 "$T/make.py" "$R" approved
git -C "$R" add spec.md; git -C "$R" commit -qm approved
cp "$R/spec.md" "$R/duplicate.md"
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$R" --registry "$T/reg.json" | grep '^FAIL' | head -1); [[ "$got" == 'FAIL FX-test-001 duplicate id' ]] && ok 'duplicate id rejected' || bad "duplicate id: $got"
rm "$R/duplicate.md"
python3 "$T/make.py" "$R" verified test
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'FAIL FX-test-001 missing AC coverage' ]] && ok 'verified AC coverage enforced' || bad "verified AC coverage: $got"
python3 "$T/make.py" "$R" verified review
git -C "$R" add spec.md; git -C "$R" commit -qm 'Verified review criterion'
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'PASS FX-test-001 trace and approvals verified' ]] && ok 'verified review criterion needs no impl/test trace' || bad "verified review coverage: $got"
python3 "$T/make.py" "$R" approved review binding
git -C "$R" add spec.md; git -C "$R" commit -qm 'Approved binding values'
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-test-001 missing approval' ]] && ok 'approved binding values require approval' || bad "approved binding: $got"
python3 - "$R/spec.md" <<'PY'
import json,sys
p=sys.argv[1]; s=open(p).read();o=json.loads(s.split("\n",1)[1].split("\n---",1)[0]);o["status"]="draft";o["trace"]=[{"repo":"product","ref":"0123456789abcdef0123456789abcdef01234567","kind":"impl","ac":[]}];open(p,"w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'FAIL FX-test-001 unknown trace SHA' ]] && ok 'unknown trace SHA rejected' || bad "unknown trace: $got"
python3 "$T/make.py" "$R" approved
python3 - "$R/spec.md" <<'PY'
import json,sys
p=sys.argv[1];s=open(p).read();o=json.loads(s.split("\n",1)[1].split("\n---",1)[0]);o["upstream"]=[{"id":"FX-parent-001","rev":"0000000000000000000000000000000000000000"}];open(p,"w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'FAIL FX-test-001 upstream-changed FX-parent-001' ]] && ok 'stale upstream rejected' || bad "stale upstream: $got"
python3 "$T/make.py" "$R" approved
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-test-001 missing approval' ]] && ok 'missing approval is human required' || bad "approval state: $got"
# Exercise the JSON path against committed history and the published schema.
J="$T/json"; mkdir -p "$J"
cat > "$J/spec.artifact.json" <<'EOF'
{"id":"FX-json-001","kind":"spec","domain":"fixture","status":"draft","title":"JSON fixture","upstream":[],"acceptance":[],"trace":[]}
EOF
git -C "$J" init -q -b main; git -C "$J" config user.name Fixture; git -C "$J" config user.email fixture@example.test
git -C "$J" add .; git -C "$J" commit -qm initial
python3 - "$J/spec.artifact.json" <<'PY'
import json,sys
p=sys.argv[1]; o=json.load(open(p)); o['status']='review'; json.dump(o,open(p,'w'))
PY
git -C "$J" add .; git -C "$J" commit -qm transition
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$J" --registry "$T/reg.json" | head -1)
[[ "$got" == 'WARN deprecated-state review -> proposed FX-json-001' ]] && ok 'JSON legacy review alias across commits' || bad "JSON legal transition: $got"
python3 - "$J/spec.artifact.json" <<'PY'
import json,sys
p=sys.argv[1]; o=json.load(open(p)); o.update(id='FX-renamed-001',status='approved'); json.dump(o,open(p,'w'))
PY
git -C "$J" add .; git -C "$J" commit -qm identity
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$J" --registry "$T/reg.json" | head -1)
[[ "$got" == 'FAIL FX-renamed-001 id changed FX-json-001 -> FX-renamed-001'* ]] && ok 'JSON artifact id change rejected' || bad "JSON id change: $got"
schema_case() {
  case_repo="$T/schema-$1"; mkdir -p "$case_repo"
  python3 - "$case_repo/spec.artifact.json" <<'PY'
import json,sys
json.dump({'id':'FX-case-001','kind':'spec','domain':'fixture','status':'draft','title':'Fixture','upstream':[],'acceptance':[],'trace':[]},open(sys.argv[1],'w'))
PY
  git -C "$case_repo" init -q -b main; git -C "$case_repo" config user.name Fixture; git -C "$case_repo" config user.email fixture@example.test
  git -C "$case_repo" add .; git -C "$case_repo" commit -qm initial
  python3 - "$case_repo/spec.artifact.json" "$1" <<'PY'
import json,sys
p,case=sys.argv[1:]; o=json.load(open(p))
if case=='top': o['mystery']=1
elif case=='nested': o['acceptance']=[{'id':'AC1','text':'Works','verify':'review','extra':1}]
elif case=='type': o['upstream']='wrong'
elif case=='enum': o['acceptance']=[{'id':'AC1','text':'Works','verify':'other'}]
elif case=='pattern': o['trace']=[{'repo':'fixture','ref':'bad','kind':'impl','ac':[]}]
json.dump(o,open(p,'w'))
PY
  git -C "$case_repo" add .; git -C "$case_repo" commit -qm "schema $1"
  python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$case_repo" --registry "$T/reg.json" | head -1
}
got=$(schema_case top); [[ "$got" == 'FAIL FX-case-001 $ unknown field mystery'* ]] && ok 'unknown JSON top-level field rejected' || bad "unknown top-level: $got"
got=$(schema_case nested); [[ "$got" == 'FAIL FX-case-001 $.acceptance[0] unknown field extra'* ]] && ok 'unknown nested JSON field rejected' || bad "unknown nested: $got"
got=$(schema_case type); [[ "$got" == 'FAIL FX-case-001 $.upstream must be array'* ]] && ok 'JSON schema type enforced' || bad "schema type: $got"
got=$(schema_case enum); [[ "$got" == 'FAIL FX-case-001 $.acceptance[0].verify must be one of'* ]] && ok 'JSON schema enum enforced' || bad "schema enum: $got"
got=$(schema_case pattern); [[ "$got" == 'FAIL FX-case-001 $.trace[0].ref does not match pattern'* ]] && ok 'JSON schema pattern enforced' || bad "schema pattern: $got"
if command -v ssh-keygen >/dev/null; then
  ssh-keygen -q -t ed25519 -N '' -f "$T/approver" -C fixture-approver
  jq --arg key "$(cat "$T/approver.pub")" '.domains.fixture.approvers=[{"principal":"fixture-approver","ssh_public_key":$key}]' "$T/reg.json" > "$T/with-key.json"
  rev=$(git -C "$R" rev-parse HEAD:spec.md); mkdir -p "$R/approvals/FX-test-001"
  python3 - "$R/approvals/FX-test-001/review-$rev.json" "$rev" <<'PY'
import json,sys
json.dump({"artifact":"FX-test-001","gate":"review","scope":"fixture","rev":sys.argv[2],"by":"fixture-approver","date":"2026-10-29T10:00:00Z"},open(sys.argv[1],"w"))
PY
  for variant in unsigned principal; do
    git clone -q "$R" "$T/$variant"
    mkdir -p "$T/$variant/approvals/FX-test-001"
    by=fixture-approver; [ "$variant" = principal ] && by=other-principal
    python3 - "$T/$variant/approvals/FX-test-001/review-$rev.json" "$rev" "$by" <<'PY'
import json,sys
json.dump({"artifact":"FX-test-001","gate":"review","scope":"fixture","rev":sys.argv[2],"by":sys.argv[3],"date":"2026-10-29T10:00:00Z"},open(sys.argv[1],"w"))
PY
    git -C "$T/$variant" add approvals
    if [ "$variant" = principal ]; then git -C "$T/$variant" -c gpg.format=ssh -c user.signingkey="$T/approver" commit -S -m 'Mismatched principal' >/dev/null 2>&1
    else git -C "$T/$variant" commit -qm 'Unsigned approval'; fi
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$T/$variant" --registry "$T/with-key.json" --repos product="$P" | head -1)
    if [ "$variant" = principal ]; then [[ "$got" == 'HUMAN_REQUIRED FX-test-001 approval principal mismatch' ]] && ok 'principal mismatch requires human' || bad "principal mismatch: $got"
    else [[ "$got" == 'HUMAN_REQUIRED FX-test-001 approval signature untrusted or invalid' ]] && ok 'unsigned approval requires human' || bad "unsigned approval: $got"; fi
  done
  git -C "$R" add approvals
  if git -C "$R" -c gpg.format=ssh -c user.signingkey="$T/approver" commit -S -m 'Add approval' >/dev/null 2>&1; then
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/with-key.json" --repos product="$P" | head -1)
    [[ "$got" == 'PASS FX-test-001 trace and approvals verified' ]] && ok 'signed approval verified' || bad "signed approval: $got"
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1)
    [[ "$got" == 'HUMAN_REQUIRED FX-test-001 no trusted approver keys' ]] && ok 'empty trusted approver list requires human' || bad "empty approvers: $got"
    git clone -q --depth 1 "file://$R" "$T/shallow"
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$T/shallow" --registry "$T/with-key.json" --repos product="$P" | head -1)
    [[ "$got" == 'HUMAN_REQUIRED FX-test-001 shallow clone' ]] && ok 'shallow clone requires human' || bad "shallow clone: $got"
    git clone -q "$R" "$T/replay"
    python3 - "$T/replay/spec.md" <<'PY'
import json,sys
p=sys.argv[1];s=open(p).read();o=json.loads(s.split("\n",1)[1].split("\n---",1)[0]);o["id"]="FX-other-001";open(p,"w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
    git -C "$T/replay" add spec.md; git -C "$T/replay" commit -qm 'Change artifact identity'
    replay_rev=$(git -C "$T/replay" rev-parse HEAD:spec.md); mkdir -p "$T/replay/approvals/FX-other-001"
    cp "$R/approvals/FX-test-001/review-$rev.json" "$T/replay/approvals/FX-other-001/review-$replay_rev.json"
    git -C "$T/replay" add approvals; git -C "$T/replay" commit -qm 'Replay approval'
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$T/replay" --registry "$T/with-key.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-other-001 approval path/content/rev mismatch' ]] && ok 'approval replay rejected' || bad "approval replay: $got"
    ssh-keygen -q -t ed25519 -N '' -f "$T/untrusted" -C untrusted
    jq --arg key "$(cat "$T/untrusted.pub")" '.domains.fixture.approvers[0].ssh_public_key=$key' "$T/with-key.json" > "$T/untrusted.json"
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/untrusted.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-test-001 approval signature untrusted or invalid' ]] && ok 'untrusted signer requires human' || bad "untrusted signer: $got"
    jq '.domains.fixture.approvers[0].revoked=true' "$T/with-key.json" > "$T/revoked.json"
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/revoked.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-test-001 no trusted approver keys' ]] && ok 'revoked signer requires human' || bad "revoked signer: $got"
    approval="$R/approvals/FX-test-001/review-$rev.json"
    printf ' ' >> "$approval"; git -C "$R" add approvals; git -C "$R" commit -qm tamper
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/with-key.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-test-001 approval is not immutable' ]] && ok 'tampered approval requires human' || bad "tampered approval: $got"
    git -C "$R" mv "$approval" "$R/approvals/FX-test-001/renamed-$rev.json" 2>/dev/null || { mkdir -p "$R/approvals/FX-test-001"; mv "$approval" "$R/approvals/FX-test-001/renamed-$rev.json"; git -C "$R" add -A approvals; }
    git -C "$R" commit -qm rename
    got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/with-key.json" --repos product="$P" | head -1); [[ "$got" == 'HUMAN_REQUIRED FX-test-001 missing approval' ]] && ok 'renamed approval requires human' || bad "renamed approval: $got"
  else skp 'git SSH signing unavailable'; fi
else skp 'ssh-keygen unavailable'; fi
python3 - <<PY
import importlib.util
s=importlib.util.spec_from_file_location("runner",r"$ROOT/scripts/run-checks.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
state,_,_=m.grade("artifact",0,"HUMAN_REQUIRED FX-test-001 missing approval\\n")
print("PASS run-checks grades HUMAN_REQUIRED" if state=="HUMAN_REQUIRED" else "FAIL run-checks parser: "+state)
if state!="HUMAN_REQUIRED": raise SystemExit(1)
PY
result=$?
if [ "$result" -eq 0 ]; then pass=$((pass+1)); else fail=$((fail+1)); fi
# asset manifest records: anyOf (source_rev or hash) must not short-circuit the other schema rules
A="$T/assets"; mkdir -p "$A"; git -C "$A" init -q -b main
asset() { # name json-patch
  python3 - "$A/item.asset.json" "$2" <<'PY2'
import json,sys
o={"id":"FX-asset-001","kind":"spec","domain":"fixture","status":"draft","source_uri":"figma://file/1","source_rev":"r1","license":"CC0","provenance":"authored","delivery":{"repo":"product","path":"Assets/Art/item.png"}}
o.update(json.loads(sys.argv[2])); [o.pop(k) for k in [k for k,v in list(o.items()) if v is None]]
open(sys.argv[1],"w").write(json.dumps(o))
PY2
  python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$A" --registry "$T/reg.json" | head -1
}
got=$(asset valid '{}'); [[ "$got" == 'PASS FX-asset-001' ]] && ok 'valid asset record' || bad "valid asset: $got"
got=$(asset structured-provenance '{"schema_version":2,"provenance":{"generated_by":"asset-import","tool":"fixture"},"authors":[{"kind":"human","id":"artist"}]}'); [[ "$got" == 'PASS FX-asset-001' ]] && ok 'version 2 asset metadata accepted' || bad "structured asset provenance: $got"
got=$(asset unknown '{"hash":"abc","mystery":true}'); [[ "$got" == 'FAIL FX-asset-001'* ]] && ok 'asset unknown key rejected (anyOf does not short-circuit)' || bad "asset unknown key: $got"
got=$(asset wrongtype '{"license":5}'); [[ "$got" == 'FAIL FX-asset-001'* ]] && ok 'asset wrong type rejected' || bad "asset wrong type: $got"
got=$(asset nosource '{"source_rev":null}'); [[ "$got" == 'FAIL FX-asset-001'* ]] && ok 'asset without source_rev or hash rejected' || bad "asset no source: $got"
# editing an artifact without changing its status is not a transition (a draft edited twice stays legal)
K="$T/same-status"; mkdir -p "$K"; git -C "$K" init -q -b main; git -C "$K" config user.email t@example.com; git -C "$K" config user.name t
python3 "$T/make.py" "$K" draft; git -C "$K" add spec.md; git -C "$K" commit -qm one
python3 - "$K/spec.md" <<'PY3'
import json, sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read(); o = json.loads(s.split("\n", 1)[1].split("\n---", 1)[0]); o["title"] = o["title"] + " revised"
open(p, "w", encoding="utf-8", newline="\n").write("---json\n" + json.dumps(o) + "\n---\n")
PY3
git -C "$K" add spec.md; git -C "$K" commit -qm two
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$K" --registry "$T/reg.json" | head -1); [[ "$got" == 'PASS FX-test-001' ]] && ok 'unchanged status across commits is not a transition' || bad "draft edited twice: $got"
echo "artifacts: $((pass+fail+skip)) run, $pass passed, $fail failed, $skip skipped"
[ "$fail" -eq 0 ]
