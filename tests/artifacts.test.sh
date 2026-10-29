#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
pass=0; fail=0; skip=0
ok() { pass=$((pass+1)); echo "PASS $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
skp() { skip=$((skip+1)); echo "SKIP $1"; }
T=$(mktemp_win) || exit 1; trap 'rm -rf "$T"' EXIT
R="$T/author"; P="$T/product"; mkdir -p "$R" "$P"
git -C "$R" init -q -b main; git -C "$P" init -q -b main
for repo in "$R" "$P"; do git -C "$repo" config user.name Fixture; git -C "$repo" config user.email fixture@example.test; done
cat > "$T/reg.json" <<'EOF'
{"domains":{"fixture":{"artifact_kinds":["spec"],"human_gates":["review"],"approvers":[]}},"artifact_lifecycles":{"default":{"states":["draft","review","approved","in-implementation","verified","released","deprecated"],"transitions":{"draft":["review"],"review":["approved"],"approved":["in-implementation"],"in-implementation":["verified"],"verified":["released"],"released":["deprecated"],"deprecated":["draft"]},"requirements":{"approved":{"needs_approval":["review"]},"in-implementation":{"needs_trace":["impl"]},"verified":{"needs_trace":["impl","test"]},"released":{"needs_trace":["impl","test","release"]}}}}}
EOF
cat > "$T/make.py" <<'PY'
import json,sys
base=sys.argv[1]; status=sys.argv[2]
o={"id":"FX-test-001","kind":"spec","domain":"fixture","status":status,"title":"Fixture","upstream":[],"acceptance":[{"id":"AC1","text":"Works","verify":"review"}],"trace":[]}
open(base+"/spec.md","w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
git -C "$P" -c user.name=Fixture -c user.email=fixture@example.test commit --allow-empty -qm product
export TMPDIR="$T" RPG_FACTORY_STATE_DIR="$T/state"
python3 "$T/make.py" "$R" draft
git -C "$R" add spec.md; git -C "$R" commit -qm init
line() { python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$R" --registry "$T/reg.json" | head -1; }
got=$(line); [[ "$got" == 'PASS FX-test-001' ]] && ok 'valid artifact' || bad "valid artifact: $got"
python3 - "$R/spec.md" <<'PY'
import json,sys
p=sys.argv[1]; s=open(p).read(); o=json.loads(s.split("\n",1)[1].split("\n---",1)[0]);o["title"]="";open(p,"w").write("---json\n"+json.dumps(o)+"\n---\n")
PY
got=$(line); [[ "$got" == 'FAIL FX-test-001 bad title' ]] && ok 'bad schema rejected' || bad "bad schema: $got"
python3 "$T/make.py" "$R" draft
git -C "$R" add spec.md; git -C "$R" commit --allow-empty -qm restore
python3 "$T/make.py" "$R" review
git -C "$R" add spec.md; git -C "$R" commit -qm review
got=$(line); [[ "$got" == 'PASS FX-test-001' ]] && ok 'legal transition' || bad "legal transition: $got"
python3 "$T/make.py" "$R" verified
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$R" --registry "$T/reg.json" | head -1); [[ "$got" == 'FAIL FX-test-001 illegal transition'* ]] && ok 'illegal transition rejected' || bad "illegal transition: $got"
python3 "$T/make.py" "$R" approved
git -C "$R" add spec.md; git -C "$R" commit -qm approved
cp "$R/spec.md" "$R/duplicate.md"
got=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$R" --registry "$T/reg.json" | grep '^FAIL' | head -1); [[ "$got" == 'FAIL FX-test-001 duplicate id' ]] && ok 'duplicate id rejected' || bad "duplicate id: $got"
rm "$R/duplicate.md"
python3 "$T/make.py" "$R" verified
got=$(python3 -B "$ROOT/scripts/checks/artifact-trace.py" "$R" --registry "$T/reg.json" --repos product="$P" | head -1); [[ "$got" == 'FAIL FX-test-001 missing AC coverage' ]] && ok 'verified AC coverage enforced' || bad "verified AC coverage: $got"
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
PY
result=$?
if [ "$result" -eq 0 ]; then pass=$((pass+1)); else fail=$((fail+1)); fi
echo "artifacts: $((pass+fail+skip)) run, $pass passed, $fail failed, $skip skipped"
[ "$fail" -eq 0 ]
