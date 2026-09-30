#!/usr/bin/env bash
# factory-status: derived cross-repo state through a full wire rollout, in throwaway repos.
# Walks: consistent -> server changes wire -> Netcode copies -> Netcode bumps -> (lead tags) ->
# client pins -> consistent; plus in-flight topic branches, migration drift and resume/idempotency.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
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
python3 -B - "$ROOT" "$WS" "$S" <<'PY'
import sys, time; sys.path.insert(0, sys.argv[1] + "/scripts/lib")
import evidence
chk = {"run": "go test ./...", "cwd": "backend/shared", "parser": "go-test", "evidence": "e"}
res = {"module": "server.shared", "check": "go-test", "tier": "fast", "command": chk["run"], "cwd": chk["cwd"], "state": "PASS",
       "timestamp": time.strftime("%Y%m%dT%H%M%S"), "identity": evidence.identity(sys.argv[3], chk["cwd"], chk), "definition": chk}
evidence.store(sys.argv[2], "server", res, "--- PASS: TestX\nok x\n")
PY
s=$(status)
expect "S13 fresh evidence -> PASS on the current tree" 'any(.evidence.server[]; .check == "server.shared/go-test" and .state == "PASS")' "$s"
echo "// edit" >> "$S/backend/shared/messages/messages.go"; s=$(status)
expect "S13 edit after the run -> STALE" 'any(.evidence.server[]; .check == "server.shared/go-test" and .state == "STALE")' "$s"
gc "$S" checkout -q -- backend/shared/messages/messages.go

# exit codes
python3 -B "$ROOT/scripts/factory-status.py" >/dev/null; rc=$?
[ $rc -eq 0 ] && { pass=$((pass + 1)); echo "PASS  default exit 0 (informational)"; } || { fail=$((fail + 1)); echo "FAIL  exit $rc"; }
python3 -B "$ROOT/scripts/factory-status.py" --strict >/dev/null; rc=$?
[ $rc -eq 1 ] && { pass=$((pass + 1)); echo "PASS  --strict exits 1 when work is pending"; } || { fail=$((fail + 1)); echo "FAIL  --strict exit $rc"; }
total=$((pass + fail)); echo "factory-status tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
