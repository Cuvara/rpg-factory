#!/usr/bin/env bash
# scripts/ui/figma_env.py: read-only Figma connector environment check on fixture Unity projects (git-pinned,
# file:-pinned, embedded, old pin, missing connector, missing package, port file with a planted evalToken).
# States, JSON fields, exit codes; the token is never printed; no socket without --probe-pipeline, and the
# probe against a closed localhost port reports unreachable without crashing.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
ENV="$ROOT/scripts/ui/figma_env.py"
TOKEN="evaltok-PLANTED-SECRET-9f3c"

# -- fixtures
pkg() { # pkg DIR VERSION [with-tools]: a com.cuvara.uitoolkit package folder
  mkdir -p "$1"
  printf '{"name": "com.cuvara.uitoolkit", "version": "%s", "unity": "6000.3"}\n' "$2" > "$1/package.json"
  if [ "${3:-}" = with-tools ]; then
    mkdir -p "$1/Tools~/FigmaImport" "$1/Tools~/UxmlCodegenCli"
    echo 'print("helper")' > "$1/Tools~/FigmaImport/figma-import.py"
    echo '<Project Sdk="Microsoft.NET.Sdk"/>' > "$1/Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj"
  fi
}
project() { # project DIR UNITY MANIFEST-DEPS-JSON LOCK-DEPS-JSON
  mkdir -p "$1/ProjectSettings" "$1/Packages" "$1/Assets"
  printf 'm_EditorVersion: %s\nm_EditorVersionWithRevision: %s (abc)\n' "$2" "$2" > "$1/ProjectSettings/ProjectVersion.txt"
  printf '{"dependencies": %s}\n' "$3" > "$1/Packages/manifest.json"
  printf '{"dependencies": %s}\n' "$4" > "$1/Packages/packages-lock.json"
}
port_file() { # port_file PROJECT PORT HEARTBEAT
  mkdir -p "$1/Library/Pipeline"
  printf '{"port": %s, "evalToken": "%s", "lastHeartbeat": "%s", "endpoints": [{"type": "http", "port": "%s"}]}\n' \
    "$2" "$TOKEN" "$3" "$2" > "$1/Library/Pipeline/.unity-pipeline-port"
}
now_utc() { python3 -B -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "1Z")'; }
CONN='"com.unity.ui.figma": "0.3.0-exp.1"'
CONN_LOCK='"com.unity.ui.figma": {"version": "0.3.0-exp.1", "source": "registry"}, "com.unity.pipeline": {"version": "0.9.1-exp.1", "source": "registry"}'
HASH=0123456789abcdef0123456789abcdef01234567

# git-pinned v0.8.0, resolved into Library/PackageCache, connector installed, Editor running (fresh heartbeat)
GIT="$TMP/git-pinned"
project "$GIT" 6000.3.9f1 "{\"com.cuvara.uitoolkit\": \"https://github.com/Cuvara/UIToolkit.git#v0.8.0\", $CONN}" \
  "{\"com.cuvara.uitoolkit\": {\"version\": \"https://github.com/Cuvara/UIToolkit.git#v0.8.0\", \"source\": \"git\", \"hash\": \"$HASH\"}, $CONN_LOCK}"
pkg "$GIT/Library/PackageCache/com.cuvara.uitoolkit@0123456789ab" 0.8.0 with-tools
pkg "$GIT/Library/PackageCache/com.cuvara.uitoolkit@ffffffffffff" 0.7.2
port_file "$GIT" 54321 "$(now_utc)"
mkdir -p "$GIT/ProjectSettings/Packages/com.unity.pipeline"
echo '{"m_AllowBrowserClients": true}' > "$GIT/ProjectSettings/Packages/com.unity.pipeline/EditorPipelineConfig.json"

# file:-pinned (relative to Packages/) to a checkout with the tools, connector installed, Editor closed
FILE="$TMP/file-pinned"; pkg "$TMP/checkout" 0.8.0 with-tools
project "$FILE" 6000.3.9f1 "{\"com.cuvara.uitoolkit\": \"file:../../checkout\", $CONN}" "{$CONN_LOCK}"

# missing connector (embedded package copy, older Unity patch)
NOCONN="$TMP/no-connector"
project "$NOCONN" 6000.3.2f1 '{"com.cuvara.uitoolkit": "https://github.com/Cuvara/UIToolkit.git#v0.8.0"}' '{}'
pkg "$NOCONN/Packages/com.cuvara.uitoolkit" 0.8.0 with-tools

# missing package
NOPKG="$TMP/no-package"; project "$NOPKG" 6000.3.9f1 "{$CONN}" "{$CONN_LOCK}"

# old pin (0.7.2 embedded, like the client before the pin bump) and a stale port file
OLD="$TMP/old-pin"
project "$OLD" 6000.3.9f1 "{\"com.cuvara.uitoolkit\": \"https://github.com/Cuvara/UIToolkit.git#v0.7.2\", $CONN}" "{$CONN_LOCK}"
pkg "$OLD/Packages/com.cuvara.uitoolkit" 0.7.2
port_file "$OLD" 50000 "2020-01-01T00:00:00.1234567Z"

# git-pinned but never opened (no PackageCache): package source is HUMAN_REQUIRED
UNRES="$TMP/unresolved"
project "$UNRES" 6000.3.9f1 "{\"com.cuvara.uitoolkit\": \"https://github.com/Cuvara/UIToolkit.git#v0.8.0\", $CONN}" '{}'

# not a Unity project
NOTU="$TMP/not-unity"; mkdir -p "$NOTU"

run() { (cd "$ROOT" && python3 -B "$ENV" "$@" 2>&1); }
state() { # state JSON-TEXT ITEM-ID
  python3 -B -c 'import json,sys; r=json.loads(sys.argv[1]); print(next((i["state"] for i in r["items"] if i["id"]==sys.argv[2]), "ABSENT"))' "$1" "$2"
}
field() { python3 -B -c 'import json,sys; r=json.loads(sys.argv[1]); print(eval(sys.argv[2], {}, {"r": r}))' "$1" "$2"; }

# -- usage
run >/dev/null; rc=$?; [ $rc -eq 2 ] && ok "no --project: exit 2" || no "no --project: exit $rc"
run --project "$TMP/does-not-exist" >/dev/null; rc=$?; [ $rc -eq 2 ] && ok "missing directory: exit 2" || no "missing directory: exit $rc"
run --project "$GIT" --bogus >/dev/null; rc=$?; [ $rc -eq 2 ] && ok "unknown flag: exit 2" || no "unknown flag: exit $rc"

# -- git-pinned, everything required present
out=$(run --project "$GIT" --json); rc=$?
[ $rc -eq 0 ] && ok "git-pinned: exit 0" || no "git-pinned: exit $rc ($out)"
[ "$(field "$out" 'r["schema"]')" = "rpg-factory.figma-env/1" ] && ok "schema rpg-factory.figma-env/1" || no "schema: $(field "$out" 'r.get("schema")')"
[ "$(field "$out" 'r["status"]')" = OK ] && ok "git-pinned: status OK" || no "git-pinned: status $(field "$out" 'r["status"]')"
[ "$(field "$out" 'sorted(r)')" = "['items', 'paths', 'probe_pipeline', 'project', 'schema', 'status']" ] && ok "top-level fields" || no "top-level fields: $(field "$out" 'sorted(r)')"
[ "$(field "$out" 'all({"id","state","required","value","reason"} <= set(i) and i["state"] in ("OK","NOT_AVAILABLE","HUMAN_REQUIRED") for i in r["items"])')" = True ] \
  && ok "every item has id/state/required/value/reason and a valid state" || no "item shape"
[ "$(field "$out" 'all(("fix" in i) == (i["state"] != "OK") for i in r["items"])')" = True ] && ok "fix present exactly when not OK" || no "fix presence"
for id in unity uitoolkit package-source figma-import connector pipeline-package pipeline-port allow-browser validator-cli; do
  s=$(state "$out" "$id"); [ "$s" = OK ] && ok "git-pinned: $id OK" || no "git-pinned: $id $s"
done
[ "$(state "$out" figma-plugin)" = HUMAN_REQUIRED ] && ok "figma-plugin always HUMAN_REQUIRED (not visible from files)" || no "figma-plugin $(state "$out" figma-plugin)"
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="uitoolkit")["source"]')" = git ] && ok "git-pinned: source git" || no "git-pinned: source"
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="uitoolkit")["value"]')" = 0.8.0 ] && ok "git-pinned: version 0.8.0" || no "git-pinned: version"
case "$(fwd "$(field "$out" 'r["paths"]["package"]')")" in *PackageCache/com.cuvara.uitoolkit@0123456789ab) ok "git-pinned: PackageCache entry matched by lock hash";;
  *) no "git-pinned: package path $(field "$out" 'r["paths"]["package"]')";; esac
case "$(fwd "$(field "$out" 'r["paths"]["figma_import"]')")" in *"Tools~/FigmaImport/figma-import.py") ok "paths.figma_import";; *) no "paths.figma_import";; esac
case "$(fwd "$(field "$out" 'r["paths"]["validator_csproj"]')")" in *"Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj") ok "paths.validator_csproj";; *) no "paths.validator_csproj";; esac
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="pipeline-port")["value"]')" = 54321 ] && ok "port value printed" || no "port value"
[ "$(field "$out" 'r["probe_pipeline"]')" = False ] && ok "probe_pipeline false by default" || no "probe_pipeline"
txt=$(run --project "$GIT"); rc=$?
[ $rc -eq 0 ] && ok "text mode exit 0" || no "text mode exit $rc"
grep -q '^figma env: OK' <<<"$txt" && ok "text mode headline" || no "text headline: $(head -1 <<<"$txt")"
grep -q 'no network' <<<"$txt" && ok "text mode says no network without --probe-pipeline" || no "text mode network note"
sub=$(run --project "$GIT/Assets" --json); [ "$(field "$sub" 'r["status"]')" = OK ] && ok "a folder inside the project resolves to the project" || no "subfolder: $(field "$sub" 'r["status"]')"

# -- the evalToken is never printed (json, text, probe; every fixture with a port file)
all=$(run --project "$GIT" --json; run --project "$GIT"; run --project "$GIT" --probe-pipeline --json; run --project "$OLD" --json; run --project "$OLD")
grep -qF "$TOKEN" <<<"$all" && no "evalToken leaked" || ok "evalToken never printed"
grep -qi 'evalToken present, not shown' <<<"$all" && ok "token presence reported without the value" || no "token presence note"

# -- file:-pinned
out=$(run --project "$FILE" --json); rc=$?
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="uitoolkit")["source"]')" = file ] && ok "file-pinned: source file" || no "file-pinned: source"
[ "$(state "$out" figma-import)" = OK ] && ok "file-pinned: helper found through the file: path" || no "file-pinned: helper $(state "$out" figma-import)"
[ "$(state "$out" pipeline-port)" = HUMAN_REQUIRED ] && ok "file-pinned: no port file is HUMAN_REQUIRED" || no "file-pinned: port $(state "$out" pipeline-port)"
grep -q 'open the project in Unity 6000.3.9f1' <<<"$out" && ok "file-pinned: fix names the project's Unity version" || no "file-pinned: port fix"
[ $rc -eq 1 ] && [ "$(field "$out" 'r["status"]')" = HUMAN_REQUIRED ] && ok "file-pinned: exit 1, HUMAN_REQUIRED" || no "file-pinned: exit $rc status $(field "$out" 'r["status"]')"
bad=$(python3 -B - "$ROOT/scripts/ui" "$FILE" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import figma_env
manifest = {"dependencies": {"com.cuvara.uitoolkit": "file:../../nowhere"}}
items, folder = figma_env.check_uitoolkit(sys.argv[2], manifest, None)
print(folder, [i["state"] for i in items])
EOF
)
[ "$bad" = "None ['HUMAN_REQUIRED', 'NOT_AVAILABLE']" ] && ok "file: path without package.json: package-source NOT_AVAILABLE" || no "dangling file: path: $bad"

# -- missing connector
out=$(run --project "$NOCONN" --json); rc=$?
[ $rc -eq 1 ] && ok "no connector: exit 1" || no "no connector: exit $rc"
[ "$(state "$out" connector)" = HUMAN_REQUIRED ] && ok "no connector: HUMAN_REQUIRED" || no "no connector: $(state "$out" connector)"
grep -q 'Add package by name: com.unity.ui.figma version 0.3.0-exp.1' <<<"$out" && ok "no connector: exact install fix" || no "no connector: fix text"
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="uitoolkit")["source"]')" = embedded ] && ok "embedded copy wins over the manifest entry" || no "embedded source"
grep -q 'tested on 6000.3.9f1' <<<"$out" && ok "other 6000.3 patch: OK, says the tested version" || no "unity tested note"

# -- missing package
out=$(run --project "$NOPKG" --json); rc=$?
[ $rc -eq 1 ] && [ "$(field "$out" 'r["status"]')" = NOT_AVAILABLE ] && ok "no package: exit 1, NOT_AVAILABLE" || no "no package: exit $rc"
[ "$(state "$out" uitoolkit)" = NOT_AVAILABLE ] && ok "no package: uitoolkit NOT_AVAILABLE" || no "no package: $(state "$out" uitoolkit)"
[ "$(state "$out" figma-import)" = NOT_AVAILABLE ] && ok "no package: helper NOT_AVAILABLE" || no "no package: helper $(state "$out" figma-import)"

# -- old pin, stale heartbeat
out=$(run --project "$OLD" --json)
[ "$(state "$out" uitoolkit)" = NOT_AVAILABLE ] && ok "0.7.2: NOT_AVAILABLE (predates the Figma integration)" || no "0.7.2: $(state "$out" uitoolkit)"
grep -q 'pin-bump' <<<"$out" && ok "0.7.2: fix points at pin-bump" || no "0.7.2: fix"
[ "$(state "$out" pipeline-port)" = HUMAN_REQUIRED ] && grep -q 'probably closed' <<<"$out" && ok "stale heartbeat (7 fraction digits): HUMAN_REQUIRED, Editor probably closed" || no "stale heartbeat: $(state "$out" pipeline-port)"

# -- unresolved git package, not a Unity project
out=$(run --project "$UNRES" --json)
[ "$(state "$out" package-source)" = HUMAN_REQUIRED ] && ok "git pin never resolved: package-source HUMAN_REQUIRED" || no "unresolved: $(state "$out" package-source)"
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="uitoolkit")["value"]')" = 0.8.0 ] && ok "git pin never resolved: version from #v0.8.0" || no "unresolved version"
out=$(run --project "$NOTU" --json); rc=$?
[ $rc -eq 1 ] && [ "$(state "$out" unity)" = NOT_AVAILABLE ] && ok "not a Unity project: unity NOT_AVAILABLE, exit 1" || no "not unity: exit $rc $(state "$out" unity)"

# -- version ordering
v=$(python3 -B - "$ROOT/scripts/ui" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from figma_env import at_least
print([at_least("0.3.0-exp.1", "0.3.0-exp.1"), at_least("0.3.0-exp.2", "0.3.0-exp.1"), at_least("0.3.0", "0.3.0-exp.1"),
       at_least("0.2.9", "0.3.0-exp.1"), at_least("0.3.0-exp.1", "0.3.0"), at_least("v0.10.0", "0.8.0"), at_least("garbage", "0.8.0")])
EOF
)
[ "$v" = "[True, True, True, False, False, True, False]" ] && ok "version ordering (prereleases, v prefix, garbage)" || no "version ordering: $v"

# -- no network without --probe-pipeline; with it, a closed port is unreachable (no crash)
net=$(python3 -B - "$ROOT/scripts/ui" "$GIT" <<'EOF'
import socket, sys
sys.path.insert(0, sys.argv[1])
calls = []
real_connect = socket.socket.connect
def spy(self, *a, **k):
    calls.append(a)
    return real_connect(self, *a, **k)
socket.socket.connect = spy
socket.create_connection = lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(OSError("blocked"))
import figma_env, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    figma_env.main(["--project", sys.argv[2], "--json"])
    figma_env.main(["--project", sys.argv[2]])
print(len(calls))
EOF
)
[ "$net" = 0 ] && ok "no socket opened without --probe-pipeline" || no "sockets opened without the flag: $net"
closed=$(python3 -B -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
port_file "$GIT" "$closed" "$(now_utc)"
out=$(run --project "$GIT" --json --probe-pipeline); rc=$?
[ "$(state "$out" pipeline-probe)" = HUMAN_REQUIRED ] && [ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="pipeline-probe")["value"]')" = unreachable ] \
  && ok "probe on a closed port: unreachable" || no "probe closed: $(state "$out" pipeline-probe) ($out)"
[ $rc -eq 0 ] && ok "probe is optional: a closed port does not fail the required items" || no "probe closed: exit $rc"
[ "$(field "$out" 'r["probe_pipeline"]')" = True ] && ok "probe_pipeline true with the flag" || no "probe_pipeline flag"
probe=$(python3 -B - "$ROOT/scripts/ui" <<'EOF'
import http.server, sys, threading
sys.path.insert(0, sys.argv[1])
import figma_env
class H(http.server.BaseHTTPRequestHandler):
    seen = []
    def do_GET(self):
        H.seen.append(self.headers.get("Authorization"))
        self.send_response(404); self.end_headers()
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.handle_request, daemon=True).start()
r = figma_env.probe_pipeline(srv.server_address[1])
srv.server_close()
print(r["state"], r["value"], H.seen)
EOF
)
[ "$probe" = "OK reachable [None]" ] && ok "probe on a listening port: reachable, no Authorization header sent" || no "probe listening: $probe"
out=$(run --project "$FILE" --json --probe-pipeline)
[ "$(state "$out" pipeline-probe)" = HUMAN_REQUIRED ] && ok "probe without a port file: HUMAN_REQUIRED, no crash" || no "probe no port: $(state "$out" pipeline-probe)"

# -- connector mapping asset (FigmaImportSettings, script GUID 0ced1937...): the real lab run hit
#    cuvara.mapping.no-asset (preset BLOCKED) and FIG010 x11 from an empty connector prefix
MGUID=0ced1937e6a344ac0a9f905cc9237a5b
mapping() { # mapping FILE PREFIX META-GUID
  mkdir -p "$(dirname "$1")"
  printf '%%YAML 1.1\n--- !u!114 &11400000\nMonoBehaviour:\n  m_Script: {fileID: 11500000, guid: %s, type: 3}\n  m_Name: %s\n  fontMap: []\n  classPrefix: %s\n  controlMap: []\n' \
    "$MGUID" "$(basename "$1" .asset)" "$2" > "$1"
  printf 'fileFormatVersion: 2\nguid: %s\n' "$3" > "$1.meta"
}
[ "$(state "$(run --project "$GIT" --json)" mapping-asset)" = HUMAN_REQUIRED ] && ok "no mapping asset: HUMAN_REQUIRED" || no "no mapping asset: state"
grep -q 'Create mapping' <<<"$(run --project "$GIT")" && ok "no mapping asset: fix names Create mapping" || no "no mapping asset: fix"
[ "$(field "$(run --project "$GIT" --json)" 'next(i for i in r["items"] if i["id"]=="mapping-asset")["required"]')" = False ] && ok "mapping-asset is optional (exit stays 0)" || no "mapping-asset required"
MAPP="$TMP/mapping"; cp -r "$GIT" "$MAPP"
mkdir -p "$MAPP/Assets/Other"; printf 'MonoBehaviour:\n  m_Script: {fileID: 11500000, guid: ffffffffffffffffffffffffffffffff, type: 3}\n' > "$MAPP/Assets/Other/NotMapping.asset"
mapping "$MAPP/Assets/A/FigmaMapping.asset" "" aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
mapping "$MAPP/Assets/B/FigmaMapping.asset" rpg bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
out=$(run --project "$MAPP" --json)
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="mapping-asset")["value"]')" = Assets/A/FigmaMapping.asset ] \
  && ok "no active selection: first mapping asset by path (as the connector)" || no "mapping first: $(field "$out" 'next(i for i in r["items"] if i["id"]=="mapping-asset")')"
grep -q 'class prefix empty' <<<"$out" && ok "empty class prefix reported (FIG010 hint)" || no "empty prefix note"
printf '%%YAML 1.1\n--- !u!114 &1\nMonoBehaviour:\n  m_ActiveMappingGuid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n' > "$MAPP/ProjectSettings/FigmaMappingState.asset"
out=$(run --project "$MAPP" --json)
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="mapping-asset")["value"]')" = Assets/B/FigmaMapping.asset ] && [ "$(state "$out" mapping-asset)" = OK ] \
  && ok "FigmaMappingState selects the active asset" || no "active mapping: $(field "$out" 'next(i for i in r["items"] if i["id"]=="mapping-asset")')"
[ "$(field "$out" 'next(i for i in r["items"] if i["id"]=="mapping-asset")["class_prefix"]')" = rpg ] && ok "class prefix read from the active asset" || no "class prefix value"
printf 'MonoBehaviour:\n  m_ActiveMappingGuid: -\n' > "$MAPP/ProjectSettings/FigmaMappingState.asset"
out=$(run --project "$MAPP" --json)
[ "$(state "$out" mapping-asset)" = HUMAN_REQUIRED ] && grep -q 'cleared on purpose' <<<"$out" && ok "cleared mapping ('-'): HUMAN_REQUIRED" || no "cleared mapping: $(state "$out" mapping-asset)"

# -- ui-figma-import carries the facts the real lab import verified (round 3)
SK="$ROOT/skills/ui-figma-import"
skill_text=$(cat "$SK/SKILL.md" "$SK"/references/*.md 2>/dev/null)
for fact in DiscardedLayers NearMissNames DroppedGap 'no `name` attributes' 'ui:TabView' 'edit access' '--output-folder' \
            '--cli dotnet' 'single-purpose' 'rpg-factory:ui-toolkit-screen' 'MeaningfulChildCount' 'mapping-asset'; do
  grep -qF -- "$fact" <<<"$skill_text" && ok "ui-figma-import names: $fact" || no "ui-figma-import misses: $fact"
done
REAL="$ROOT/docs/architecture/ui-figma-real-test.md"
for fact in 'r-e91f7030' '116 nodes' 'FIG020 x7' 'NearMissNames x14' 'DiscardedLayers x4' 'DroppedGap x11'; do
  grep -qF -- "$fact" "$REAL" && ok "real-test evidence records: $fact" || no "real-test evidence misses: $fact"
done
grep -qE '^\| 1[2-4] .*NOT_RUN' "$REAL" && ok "Unity Play-mode rows stay NOT_RUN" || no "Play-mode rows no longer NOT_RUN"

# -- read-only: no file written into any fixture project
before=$(cd "$TMP" && find git-pinned file-pinned no-connector no-package old-pin unresolved not-unity checkout -type f | sort | md5sum)
for p in "$GIT" "$FILE" "$NOCONN" "$NOPKG" "$OLD" "$UNRES" "$NOTU"; do run --project "$p" --json >/dev/null; done
after=$(cd "$TMP" && find git-pinned file-pinned no-connector no-package old-pin unresolved not-unity checkout -type f | sort | md5sum)
[ "$before" = "$after" ] && ok "writes nothing into the projects" || no "files changed in a fixture project"

echo "ui-figma-env tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
