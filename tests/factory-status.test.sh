#!/usr/bin/env bash
# factory-status: derived cross-repo state through a full wire rollout, in throwaway repos.
# Walks: consistent -> server changes wire -> Netcode copies -> Netcode bumps -> (lead tags) ->
# client pins -> consistent; plus in-flight topic branches, migration drift and resume/idempotency.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; N="$WS/Netcode"; C="$WS/IndieRPGMMOAdventure"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
mkdir -p "$S/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1" "$S/backend/shared/proto/gen" "$S/backend/shared/messages" \
         "$S/backend/gameserver-dotnet/GameServer/Persistence/Migrations" "$S/backend/deploy/db/migrations/gamestate" \
         "$S/backend/gameserver-dotnet/Shared.GameLogic" "$N/Runtime/Protocol/Generated" "$C/Packages" "$C/ProjectSettings"
touch "$S/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt"
echo "// wire v1" > "$S/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"
echo "message A {}" > "$S/backend/shared/proto/wire.proto"; echo "// go v1" > "$S/backend/shared/proto/gen/wire.pb.go"
echo "public const uint ProtocolVersion = 2;" > "$S/backend/gameserver-dotnet/GameServer/Net/WireProtocol.cs"
echo "const WireProtocolVersion uint32 = 2" > "$S/backend/shared/messages/messages.go"
printf -- "-- init\nCREATE TABLE a (id int);\n" > "$S/backend/gameserver-dotnet/GameServer/Persistence/Migrations/001_init.sql"
printf "CREATE TABLE a (id int);\n" > "$S/backend/deploy/db/migrations/gamestate/001_init.sql"
echo '{"version":"0.6.0"}' > "$S/backend/gameserver-dotnet/Shared.GameLogic/package.json"
cp "$S/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs" "$N/Runtime/Protocol/Generated/Wire.cs"
echo "public const uint Current = 2;" > "$N/Runtime/Protocol/WireProtocolVersion.cs"
echo '{"name":"com.cuvara.netcode","version":"1.0.0"}' > "$N/package.json"; printf "# Changelog\n## [1.0.0] - 2026-01-01\n" > "$N/CHANGELOG.md"
lock() { printf '{"dependencies":{"com.cuvara.netcode":{"version":"https://github.com/Cuvara/Netcode.git#%s"},"com.rpgmmo.shared-gamelogic":{"version":"https://x.git?path=/y#sgl-v0.6.0"}}}\n' "$1" > "$C/Packages/packages-lock.json"; }
lock v1.0.0
for r in "$S" "$N" "$C"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done
gc "$N" tag v1.0.0; gc "$S" tag sgl-v0.6.0
pass=0; fail=0
status() { python3 -B "$ROOT/scripts/factory-status.py" --json; }
expect() { if jq -e "$2" <<<"$3" >/dev/null 2>&1; then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; jq -c '{rollout: [.wire_rollout[] | "\(.stage)=\(.ok)"], pending: [.pending[] | "\(.skill): \(.what)"]}' <<<"$3"; fi; }
stage() { jq -r '[.wire_rollout[] | select(.ok == false) | .stage][0] // "complete"' <<<"$1"; }

s=$(status)
expect "S0 consistent: rollout complete, no wire pending" '([.wire_rollout[] | .ok] | all) and ([.pending[] | select(.what | test("wire"))] | length == 0)' "$s"
expect "S0 contracts ok (wire, version, migrations normalised)" '[.contracts[] | .ok] | all' "$s"

# S1: server regenerates bindings with a new field (server leg done)
echo "message A { string region = 1; }" > "$S/backend/shared/proto/wire.proto"; echo "// go v2" > "$S/backend/shared/proto/gen/wire.pb.go"
echo "// wire v2 (region)" > "$S/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"; gc "$S" commit -qam "feat(wire): region"
s=$(status)
expect "S1 server done -> pending at 'Netcode copy' owned by unity-package" '([.wire_rollout[] | select(.ok == false) | .stage][0] == "Netcode copy (develop)") and any(.pending[]; .skill == "unity-package" and (.what | test("Netcode copy")))' "$s"
expect "S1 contract wire-generated reported inconsistent" 'any(.contracts[]; .id == "wire-generated" and .ok == false)' "$s"

# restart / resume: recomputed twice, identical
s2=$(status)
[ "$(jq -S .pending <<<"$s")" = "$(jq -S .pending <<<"$s2")" ] && { pass=$((pass + 1)); echo "PASS  resume: status is idempotent (same pending list after restart)"; } || { fail=$((fail + 1)); echo "FAIL  status not idempotent"; }

# S2: Netcode copies Wire.cs on develop (no release yet)
cp "$S/backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs" "$N/Runtime/Protocol/Generated/Wire.cs"; gc "$N" commit -qam "chore(wire): resync"
s=$(status)
expect "S2 copied -> pending at 'Netcode release'" '([.wire_rollout[] | select(.ok == false) | .stage][0] == "Netcode release (tag)")' "$s"
expect "S2 package state: unreleased changes" 'any(.packages[]; .repo == "netcode" and .state == "unreleased changes")' "$s"

# S3: Netcode bumps version + dated section -> READY_TO_TAG (agents stop here)
echo '{"name":"com.cuvara.netcode","version":"1.1.0"}' > "$N/package.json"; printf "# Changelog\n## [1.1.0] - 2026-02-01\n## [1.0.0] - 2026-01-01\n" > "$N/CHANGELOG.md"; gc "$N" commit -qam "chore(release): 1.1.0"
s=$(status)
expect "S3 READY_TO_TAG netcode v1.1.0" 'any(.packages[]; .repo == "netcode" and .state == "READY_TO_TAG") and any(.pending[]; .what | test("READY_TO_TAG netcode v1.1.0"))' "$s"

# S4: (the lead tags) -> released, not propagated -> pin-bump
gc "$N" tag v1.1.0
s=$(status)
expect "S4 released, client pin old -> pin-bump pending, rollout stops at client pin" '([.wire_rollout[] | select(.ok == false) | .stage][0] == "client pin") and any(.pending[]; .skill == "pin-bump" and (.what | test("v1.1.0")))' "$s"

# S5: client pins v1.1.0 -> complete
lock v1.1.0; gc "$C" commit -qam "chore(packages): netcode v1.1.0"
s=$(status)
expect "S5 rollout complete, nothing pending for the wire" '([.wire_rollout[] | .ok] | all) and ([.pending[] | select(.skill == "pin-bump" or (.what | test("wire rollout")))] | length == 0)' "$s"

# S6: in-flight cross-repo topic: server branch changes the wire, Netcode/client have no branch
gc "$S" switch -q -c feat/wire/party
echo "message A { string region = 1; string party = 2; }" > "$S/backend/shared/proto/wire.proto"; gc "$S" commit -qam "feat(wire): party"
gc "$S" switch -q develop
s=$(status)
expect "S6 topic 'party' in flight on server, pending legs in netcode+client" 'any(.in_flight[]; .topic == "party") and any(.pending[]; .skill == "wire-contract" and (.what | test("party")) and (.repo | test("netcode")))' "$s"

# S7: migration copy drift on the integration branch
printf "CREATE TABLE b (id int);\n" > "$S/backend/deploy/db/migrations/gamestate/002_b.sql"; gc "$S" add -A; gc "$S" commit -qm "deploy copy only"
s=$(status)
expect "S7 migration drift -> server-services pending" 'any(.contracts[]; .id == "gamestate-migrations" and .ok == false) and any(.pending[]; .skill == "server-services")' "$s"

# S8: client workflows call the build toolkit at mixed majors -> pin-bump pending
mkdir -p "$C/.github/workflows"
printf 'jobs:\n  a:\n    uses: Cuvara/unity-build-workflows/.github/workflows/unity-pipeline.yml@v6\n' > "$C/.github/workflows/01-ci.yml"
printf 'jobs:\n  a:\n    uses: Cuvara/unity-build-workflows/.github/workflows/pipeline-android-release.yml@v5\n' > "$C/.github/workflows/20-release-android.yml"
gc "$C" add .github; gc "$C" commit -qm "ci: half-moved toolkit"
s=$(status)
expect "S8 workflow refs listed; mixed majors v5/v6 -> pin-bump pending" 'any(.pins[]; .package | test("workflow refs")) and any(.pending[]; .skill == "pin-bump" and (.what | test("mixed majors")))' "$s"

# S9 (v0.4): a package CI installs another package at an old tag -> unity-package pending (watchers)
D="$WS/UnityDots"; mkdir -p "$D/.github/workflows"
printf '{"dependencies":{"com.cuvara.netcode":"https://github.com/Cuvara/Netcode.git#v1.0.0"}}\n' > "$D/.github/workflows/ci.yml"
echo '{"name":"com.cuvara.dots","version":"0.1.0"}' > "$D/package.json"
git -C "$D" init -q -b main; gc "$D" add -A; gc "$D" commit -qm init
s=$(status)
expect "S9 CI pin drift: unitydots CI on netcode v1.0.0 while the client pins v1.1.0" 'any(.ci_pins[]; .watcher == "unitydots:.github/workflows/ci.yml" and .ref == "v1.0.0" and .client_pin == "v1.1.0") and any(.pending[]; .skill == "unity-package" and (.what | test("netcode#v1.0.0")))' "$s"

# S10 (v0.4): remote knowledge freshness - an origin/* integration ref with an old (or no) fetch is reported, never fetched
git init -q --bare "$TMP/n-remote.git"; gc "$N" remote add origin "$TMP/n-remote.git"; gc "$N" push -q origin develop 2>/dev/null
gc "$N" fetch -q origin; touch -d "3 days ago" "$N/.git/FETCH_HEAD"
s=$(status)
expect "S10 stale fetch (72h) flagged with the fetch command" '.freshness.netcode.stale == true and (.freshness.netcode.last_fetch_h > 48) and any(.pending[]; .skill == "factory-core" and (.what | test("fetch origin")))' "$s"
touch "$N/.git/FETCH_HEAD"; s=$(status)
expect "S10 fresh fetch -> not stale" '.freshness.netcode.stale == false' "$s"

# S11 (v0.4): embedded clones are listed as user state, not as the canonical repo
mkdir -p "$C/Packages"; git init -q -b main "$C/Packages/com.cuvara.dots"; echo x > "$C/Packages/com.cuvara.dots/a.cs"; gc "$C/Packages/com.cuvara.dots" add -A; gc "$C/Packages/com.cuvara.dots" commit -qm c
s=$(status)
expect "S11 embedded clone listed with its canonical repo" 'any(.clones[]; .path == "Packages/com.cuvara.dots" and .of == "unitydots" and (.canonical_head | length > 0))' "$s"

# S12 (v0.4): uncommitted work is visible (interrupted implementation)
echo "wip" >> "$S/backend/shared/messages/messages.go"; s=$(status)
expect "S12 uncommitted tracked change in server is reported" '.worktrees.server.tracked_changes == 1' "$s"
gc "$S" checkout -q -- backend/shared/messages/messages.go

# S13 (v0.4): stored validation evidence is graded against the current tree (PASS -> STALE after an edit)
# (records are made the way run-checks.py makes them: the registry definition and its scopes_for())
store_ev() { python3 -B - "$ROOT" "$WS" "$S" "$1" <<'PY'
import json, sys, time; sys.path.insert(0, sys.argv[1] + "/scripts/lib")
import evidence
reg = json.load(open(sys.argv[1] + "/registry.json", encoding="utf-8"))
chk = dict(next(c for m in reg["modules"] if m["id"] == "server.shared" for c in m["checks"]["fast"] if c["id"] == "go-test"))
if sys.argv[4] == "old-run":  # evidence produced before the registry changed the command
    chk["run"] = "go test ./... -old-flag"
scopes = evidence.scopes_for(reg, "server.shared", chk["cwd"])
res = {"module": "server.shared", "check": "go-test", "tier": "fast", "command": chk["run"], "cwd": chk["cwd"], "state": "PASS",
       "timestamp": time.strftime("%Y%m%dT%H%M%S"), "identity": evidence.identity(sys.argv[3], scopes, chk), "scopes": scopes,
       "definition": {k: chk.get(k) for k in ("run", "cwd", "parser", "evidence")}}
evidence.store(sys.argv[2], "server", res, "--- PASS: TestX\nok x\n")
PY
}
store_ev old-run; s=$(status)
expect "S13 evidence made under an older check command -> STALE (definition changed), like run-checks --status" \
  'any(.evidence.server[]; .check == "server.shared/go-test" and .state == "STALE" and (.detail | test("definition changed")))' "$s"
store_ev current
s=$(status)
expect "S13 fresh evidence -> PASS on the current tree" 'any(.evidence.server[]; .check == "server.shared/go-test" and .state == "PASS")' "$s"
echo "// edit" >> "$S/backend/shared/messages/messages.go"; s=$(status)
expect "S13 edit after the run -> STALE" 'any(.evidence.server[]; .check == "server.shared/go-test" and .state == "STALE")' "$s"
gc "$S" checkout -q -- backend/shared/messages/messages.go
# valid JSON of the wrong shape next to real evidence is skipped or graded, never a crash (1.0.5)
EV=$(python3 -B -c "import sys; sys.path.insert(0, sys.argv[1] + '/scripts/lib'); import evidence; print(evidence.repo_dir_for(sys.argv[2], 'server'))" "$ROOT" "$WS")
printf '{"identity":"x"}' > "$EV/bad__a.json"; printf '[1]' > "$EV/bad__b.json"; printf '{"identity":{"tree":"t"}}' > "$EV/bad__c.json"
printf '{"identity":{},"state":"PASS","definition":[1],"scopes":{"x":1}}' > "$EV/bad__d.json"
s=$(status); rc=$?
expect "S13 wrong-shape evidence files: status still runs, the real record still graded" \
  'any(.evidence.server[]; .check == "server.shared/go-test" and .state == "PASS") and ([.evidence.server[] | select(.state == "PASS")] | length) == 1' "$s"
[ $rc -eq 0 ] && { pass=$((pass + 1)); echo "PASS  wrong-shape evidence: exit 0"; } || { fail=$((fail + 1)); echo "FAIL  wrong-shape evidence: exit $rc"; }
rm -f "$EV"/bad__*.json
# evidence for a check the registry no longer declares proves nothing about the checks declared now
printf '{"module":"server.gone","check":"x","state":"PASS","identity":{"tree":"t"}}' > "$EV/server.gone__x.json"
s=$(status)
expect "S13 evidence of a check no longer in the registry -> STALE" \
  'any(.evidence.server[]; .check == "server.gone/x" and .state == "STALE" and (.detail | test("no longer declared")))' "$s"
rm -f "$EV/server.gone__x.json"

# exit codes
python3 -B "$ROOT/scripts/factory-status.py" >/dev/null; rc=$?
[ $rc -eq 0 ] && { pass=$((pass + 1)); echo "PASS  default exit 0 (informational)"; } || { fail=$((fail + 1)); echo "FAIL  exit $rc"; }
python3 -B "$ROOT/scripts/factory-status.py" --strict >/dev/null; rc=$?
[ $rc -eq 1 ] && { pass=$((pass + 1)); echo "PASS  --strict exits 1 when work is pending"; } || { fail=$((fail + 1)); echo "FAIL  --strict exit $rc"; }

# Optional authoring is discovered through the registry, with no engineering status changes.
expect "S14 absent authoring omits JSON domains" 'has("domains") | not' "$s"
text=$(python3 -B "$ROOT/scripts/factory-status.py")
if ! grep -q '^## Domains$' <<<"$text"; then pass=$((pass + 1)); echo "PASS  absent authoring omits Domains section"; else fail=$((fail + 1)); echo "FAIL  unexpected Domains section"; fi
export RPG_FACTORY_WORKSPACE="$TMP/domain-ws"
A="$RPG_FACTORY_WORKSPACE/game-authoring"
mkdir -p "$A/design"; git -C "$A" init -q -b main
text=$(python3 -B "$ROOT/scripts/factory-status.py")
if grep -A1 '^## Domains$' <<<"$text" | grep -q '^- no authoring artifacts yet$'; then pass=$((pass + 1)); echo "PASS  empty authoring repo: Domains says no artifacts yet"
else fail=$((fail + 1)); echo "FAIL  empty authoring Domains text: $(grep -A1 '^## Domains' <<<"$text")"; fi
rm -rf "$A"; mkdir -p "$A"
cp -R "$ROOT/tests/fixtures/dogfood/game-authoring/." "$A/"
git -C "$A" init -q -b main; gc "$A" add .; gc "$A" commit -qm "fixture: draft concept"
s=$(status)
expect "S14 draft lifecycle counted under its registered domain lead" '.domains.design.domain == "design" and .domains.design.lead == "game-design" and .domains.design.artifacts == {draft: 1}' "$s"
expect "S14 empty domains and engineering skipped" '(.domains | keys) == ["design"]' "$s"
expect "S14 draft quality passes with no domain pending" '.domains.design.quality.PASS > 0 and .domains.design.quality.FAIL == 0 and .domains.design.human_required == [] and .domains.design.failing == [] and .pending == []' "$s"
python3 -B "$ROOT/scripts/factory-status.py" --strict > /dev/null; rc=$?
[ $rc -eq 0 ] && { pass=$((pass + 1)); echo "PASS  --strict accepts clean draft authoring"; } || { fail=$((fail + 1)); echo "FAIL  clean draft --strict exit $rc"; }
text=$(python3 -B "$ROOT/scripts/factory-status.py")
if grep -q '^## Domains$' <<<"$text" && grep -q 'design \[game-design\]: draft 1; stale upstream: none; FAIL 0; HUMAN_REQUIRED 0' <<<"$text"; then pass=$((pass + 1)); echo "PASS  text Domains reports lifecycle and quality counts"; else fail=$((fail + 1)); echo "FAIL  draft Domains text: $text"; fi
# Record a downstream revision, then edit the upstream without committing it.
python3 -B - "$A" <<'PY'
import json, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]); source=root/'design/concepts/GD-game-concept-001.artifact.json'
obj=json.loads(source.read_text(encoding='utf-8'))
rev=subprocess.run(['git','-C',str(root),'hash-object',str(source)],capture_output=True,text=True,check=True).stdout.strip()
obj.update(id='GD-downstream-001',upstream=[{'id':'GD-game-concept-001','rev':rev}])
(root/'design/concepts/GD-downstream-001.artifact.json').write_text(json.dumps(obj),encoding='utf-8')
PY
gc "$A" add .; gc "$A" commit -qm "fixture: recorded upstream"
s=$(status)
expect "S14 unchanged upstream revision is fresh" '.domains.design.stale == [] and .domains.design.artifacts.draft == 2' "$s"
printf '\n' >> "$A/design/concepts/GD-game-concept-001.artifact.json"
s=$(status)
expect "S14 working-tree upstream change marks downstream stale" '.domains.design.stale == ["GD-downstream-001"] and any(.pending[]; .skill == "game-design" and .repo == "authoring" and .what == "GD-downstream-001 stale upstream revision")' "$s"
text=$(python3 -B "$ROOT/scripts/factory-status.py")
if grep -q '^\- \[game-design\] authoring: GD-downstream-001 stale upstream revision$' <<<"$text"; then pass=$((pass + 1)); echo "PASS  stale text Pending routes to the domain lead"; else fail=$((fail + 1)); echo "FAIL  stale Pending text"; fi
python3 -B "$ROOT/scripts/factory-status.py" --strict > /dev/null; rc=$?
[ $rc -eq 1 ] && { pass=$((pass + 1)); echo "PASS  --strict rejects stale authoring alone"; } || { fail=$((fail + 1)); echo "FAIL  stale --strict exit $rc"; }
gc "$A" checkout -q -- design/concepts/GD-game-concept-001.artifact.json
# Value-free approved artifacts pass; binding artifacts still need human approval.
python3 -B - "$A" <<'PY'
import json, pathlib, sys
root=pathlib.Path(sys.argv[1]); obj=json.loads((root/'design/concepts/GD-game-concept-001.artifact.json').read_text(encoding='utf-8'))
obj.update(id='GD-approved-001',status='approved',acceptance=[{'id':'AC1','text':'Concept is understandable','verify':'review'}])
(root/'design/concepts/GD-approved-001.artifact.json').write_text(json.dumps(obj),encoding='utf-8')
PY
gc "$A" add .; gc "$A" commit -qm "fixture: approval gate"
s=$(status)
expect "S14 approved lifecycle counted alongside drafts" '.domains.design.artifacts == {draft: 2, approved: 1}' "$s"
expect "S14 value-free approved concept needs no approval" '.domains.design.quality.FAIL == 0 and .domains.design.human_required == [] and .pending == []' "$s"
python3 -B - "$A" <<'PY'
import json, pathlib, sys
path=pathlib.Path(sys.argv[1])/'design/concepts/GD-approved-001.artifact.json'
obj=json.loads(path.read_text(encoding='utf-8')); obj['binding_values']=True; obj['spec'].pop('concept')
path.write_text(json.dumps(obj),encoding='utf-8')
PY
gc "$A" add .; gc "$A" commit -qm "fixture: binding values and incomplete concept"
s=$(status)
expect "S14 missing approval remains HUMAN_REQUIRED" '.domains.design.quality.HUMAN_REQUIRED > 0 and .domains.design.human_required == ["GD-approved-001"] and any(.pending[]; .skill == "game-design" and .repo == "authoring" and (.what | startswith("GD-approved-001 HUMAN_REQUIRED")))' "$s"
expect "S14 failed concept quality appears in quality and Pending" '.domains.design.quality.FAIL > 0 and .domains.design.failing == ["GD-approved-001"] and any(.pending[]; .skill == "game-design" and .repo == "authoring" and (.what | startswith("GD-approved-001 FAIL")))' "$s"
before=$(git -C "$A" status --porcelain=v1)
s2=$(status)
if [ "$before" = "$(git -C "$A" status --porcelain=v1)" ] && [ "$(jq -S .domains <<<"$s")" = "$(jq -S .domains <<<"$s2")" ]; then pass=$((pass + 1)); echo "PASS  domain status is read-only and repeatable"; else fail=$((fail + 1)); echo "FAIL  domain status changed repository or summary"; fi
# Public library contract, filtered quality, unique artifact IDs, and unavailable checker behavior.
if python3 -B - "$ROOT" "$A" <<'PY'
import json, os, pathlib, sys
root=pathlib.Path(sys.argv[1]); authoring=sys.argv[2]; sys.path.insert(0,str(root/'scripts/lib'))
from artifacts import scan, upstream_changes, domain_summary
regpath=str(root/'registry.json'); reg=json.loads(pathlib.Path(regpath).read_text(encoding='utf-8'))
arts=scan(authoring_dir=authoring); summary=domain_summary(reg,regpath,authoring,'design')
assert set(summary)=={'domain','lead','artifacts','stale','quality','human_required','failing'},summary
assert len(arts)==3 and upstream_changes(arts['GD-downstream-001'],arts)==[]
assert summary['human_required']==['GD-approved-001'] and summary['failing']==['GD-approved-001'],summary
empty=domain_summary(reg,regpath,authoring,'ui')
assert empty['artifacts']=={} and not any(empty['quality'].values()),empty
os.environ['RPG_FACTORY_ARTIFACT_QUALITY']=str(root/'does-not-exist.py')
unavailable=domain_summary(reg,regpath,authoring,'design')
assert unavailable['quality']['BLOCKED']==3 and unavailable['quality']['PASS']==0 and len(unavailable['failing'])==3,unavailable
PY
then pass=$((pass + 1)); echo "PASS  shared artifact API preserves summary contract and unavailable checks"; else fail=$((fail + 1)); echo "FAIL  shared artifact API"; fi

total=$((pass + fail)); echo "factory-status tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
