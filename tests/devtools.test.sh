#!/usr/bin/env bash
# Dev tools and services: lib/devtools.py probes (tcp, PATH, MCP server names, enabled plugins), the
# snapshot's "Services" / "Tools for this change" lines and the doctor "Dev tools" section. Secrets
# planted in the fixture MCP configs must never appear in any output.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_CONFIG_DIR="$TMP/cfg"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
SECRET1="sk-PLANTED-SECRET-111"; SECRET2="tok-PLANTED-SECRET-222"

# -- fixture workspace + config (names next to secret-looking values)
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$S/backend/gateway/server" "$C/ProjectSettings" "$C/Assets/Scripts/UI" "$TMP/cfg" "$TMP/bin"
touch "$S/backend/TEAM.md" "$S/backend/gateway/server/server.go" "$C/ProjectSettings/ProjectVersion.txt" "$C/Assets/Scripts/UI/A.cs"
for r in "$S" "$C"; do git -C "$r" init -q -b develop; git -C "$r" -c user.email=t@t -c user.name=t add -A; git -C "$r" -c user.email=t@t -c user.name=t commit -qm init; done
cat > "$WS/.mcp.json" <<EOF
{"mcpServers": {"lsp": {"command": "agent-lsp", "args": ["go:gopls"], "env": {"API_KEY": "$SECRET1"}}}}
EOF
cat > "$TMP/cfg/.claude.json" <<EOF
{"mcpServers": {"pg-aiguide": {"type": "http", "url": "https://example.invalid/mcp?token=$SECRET2"}},
 "projects": {"$C": {"mcpServers": {"ai-game-developer": {"headers": {"Authorization": "Bearer $SECRET1"}}}}}}
EOF
echo '{"enabledPlugins": {"context-mode@context-mode": true, "codex@openai-codex": false}}' > "$TMP/cfg/settings.json"
printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/gopls"; chmod +x "$TMP/bin/gopls"
export RPG_FACTORY_WORKSPACE="$WS" PATH="$TMP/bin:$PATH"

# -- unit: probes
out=$(cd "$ROOT/scripts/lib" && python3 -B - "$WS" "$ROOT/registry.json" <<'EOF'
import json, socket, sys
import devtools
ws, reg = sys.argv[1], json.load(open(sys.argv[2]))
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
print("tcp-open", devtools.tcp_reachable(f"tcp://127.0.0.1:{port}"))
srv.close()
print("tcp-closed", devtools.tcp_reachable(f"tcp://127.0.0.1:{port}"))
print("tcp-bad", devtools.tcp_reachable("tcp://nonsense"))
m = devtools.mcp_servers(ws, reg)
print("mcp", sorted(m), json.dumps(m))
print("plugins", sorted(devtools.enabled_plugins(ws)))
reg["services"] = {"svc": {"probe": f"tcp://127.0.0.1:{port}"}}
p = devtools.Prober(ws, reg)
for t in ({"id": "a", "probes": ["mcp:lsp", "bin:gopls"]},
          {"id": "b", "probes": ["mcp:ai-game-developer", "service:svc"]},
          {"id": "c", "probes": ["bin:no-such-binary-xyz|plugin:codex"]},
          {"id": "d", "probes": ["plugin:context-mode"]}):
    r = p.tool(t); print("state", t["id"], r["state"], "|", "; ".join(r["detail"]))
EOF
)
grep -q "^tcp-open True" <<<"$out" && grep -q "^tcp-closed False" <<<"$out" && grep -q "^tcp-bad False" <<<"$out" \
  && ok "tcp probe: listening port reachable, closed port and bad probe not" || no "tcp probe: $out"
grep -q "^mcp \['ai-game-developer', 'lsp', 'pg-aiguide'\]" <<<"$out" && ok "mcp servers found in workspace .mcp.json, user and project entries" || no "mcp names: $out"
grep -q "^plugins \['context-mode'\]" <<<"$out" && ok "plugins: enabled counted, disabled (codex=false) not" || no "plugins: $out"
grep -q "^state a OK" <<<"$out" && ok "tool state OK when every probe passes" || no "state a: $out"
grep -q "^state b DOWN .*svc not reachable" <<<"$out" && ok "tool state DOWN when only a service probe fails" || no "state b: $out"
grep -q "^state c MISSING .*plugin codex not enabled" <<<"$out" && ok "tool state MISSING when no alternative passes" || no "state c: $out"
grep -q "^state d OK" <<<"$out" && ok "plugin probe passes for an enabled plugin" || no "state d: $out"
grep -qE "$SECRET1|$SECRET2" <<<"$out" && no "probe output leaks a planted secret" || ok "probe output carries no config values"

# -- scenarios over the REAL registry in a controlled environment (fake PATH, config, Editor port)
SC="$TMP/scen"; mkdir -p "$SC/bin" "$SC/cfg" "$SC/ws"
for b in gopls csharp-ls dotnet go protoc protoc-gen-go docker codex; do printf '#!/bin/sh\nexit 0\n' > "$SC/bin/$b"; chmod +x "$SC/bin/$b"; done
echo '{"mcpServers": {"ai-game-developer": {}, "lsp": {}, "pg-aiguide": {}}}' > "$SC/ws/.mcp.json"
echo '{"enabledPlugins": {"context-mode@context-mode": true, "codex@openai-codex": true}}' > "$SC/cfg/settings.json"
scen=$(cd "$ROOT/scripts/lib" && CLAUDE_CONFIG_DIR="$SC/cfg" python3 -B - "$SC" "$ROOT/registry.json" <<'EOF'
import json, os, socket, sys
import devtools
sc, reg = sys.argv[1], json.load(open(sys.argv[2]))
os.environ["PATH"] = f"{sc}/bin"
editor = socket.socket(); editor.bind(("127.0.0.1", 0)); editor.listen(1)
reg["services"]["unity-mcp"]["probe"] = f"tcp://127.0.0.1:{editor.getsockname()[1]}"
def states(tag):
    for t in reg["dev_tools"]:
        r = devtools.Prober(f"{sc}/ws", reg).tool(t)
        print(tag, t["id"], r["state"], "fallback=" + str(bool(t.get("fallback"))))
states("all")
editor.close()                                   # Editor closed
states("editor-closed")
os.remove(f"{sc}/bin/csharp-ls")                 # no C# language server
states("no-csharp")
EOF
)
n=$(jq '.dev_tools | length' "$ROOT/registry.json")
[ "$(grep -c '^all .* OK ' <<<"$scen")" -eq "$n" ] && ok "scenario all tools available: all $n OK" || no "scenario all: $(grep '^all' <<<"$scen" | grep -v ' OK ')"
grep -q '^editor-closed unity-mcp DOWN fallback=True' <<<"$scen" && [ "$(grep -c '^editor-closed .* OK ' <<<"$scen")" -eq $((n - 1)) ] \
  && ok "scenario Unity Editor closed: unity-mcp DOWN (not MISSING, not OK), fallback set, rest OK" || no "scenario editor-closed: $(grep '^editor-closed' <<<"$scen" | grep -v ' OK ')"
grep -q '^no-csharp lsp-csharp MISSING fallback=True' <<<"$scen" && grep -q '^no-csharp unity-mcp DOWN' <<<"$scen" \
  && ok "scenario no C# LSP: lsp-csharp MISSING with fallback, other states unchanged" || no "scenario no-csharp: $(grep '^no-csharp' <<<"$scen" | grep -v ' OK ')"
jq -e '[.dev_tools[] | select(.id == "unity-mcp" or .id == "lsp-csharp") | .required] == [false, false]' "$ROOT/registry.json" >/dev/null \
  && ok "unity-mcp and lsp-csharp are optional: their absence never fails doctor or a check" || no "unity-mcp/lsp-csharp marked required"
# doctor's exit code also reflects install state, so compare: an optional tool's absence must not change it
printf '#!/bin/sh\nexit 0\n' > "$SC/bin/csharp-ls"; chmod +x "$SC/bin/csharp-ls"
rc_with=$(cd "$WS" && PATH="$SC/bin:$PATH" python3 -B "$ROOT/scripts/factory-cmd.py" doctor >/dev/null 2>&1; echo $?)
rm -f "$SC/bin/csharp-ls"
out_without=$(cd "$WS" && PATH="$SC/bin:$PATH" python3 -B "$ROOT/scripts/factory-cmd.py" doctor 2>&1); rc_without=$?
grep -q '^- lsp-csharp (binary, optional): \*\*MISSING\*\*' <<<"$out_without" && [ "$rc_with" = "$rc_without" ] \
  && ok "doctor exit code is the same with and without a C# LSP (optional tool; rc=$rc_without)" \
  || no "doctor rc with C# LSP=$rc_with, without=$rc_without"

# -- snapshot: Services line + Tools for this change (routed skills only)
out=$(cd "$WS" && bash "$ROOT/scripts/factory-context.sh" --repo server --paths backend/gateway/server/server.go 2>&1)
grep -q '^\*\*Services:\*\* `unity-mcp` \(reachable\|not reachable\)' <<<"$out" && ok "snapshot: Services line probes registry services" || no "snapshot services: $(head -c 400 <<<"$out")"
grep -q '^Tools for this change: .*lsp-go OK' <<<"$out" && grep -q 'pg-aiguide OK' <<<"$out" && ! grep -q 'unity-mcp [A-Z]' <<<"$(grep '^Tools for' <<<"$out")" \
  && ok "snapshot: gateway change lists server-services tools, not Unity tools" || no "snapshot tools: $(grep '^Tools' <<<"$out")"
js=$(cd "$WS" && bash "$ROOT/scripts/factory-context.sh" --repo server --json --paths backend/gateway/server/server.go 2>&1)
jq -e '(.services | has("unity-mcp")) and any(.repos[0].dev_tools[]; .id == "lsp-go" and .ok)' <<<"$js" >/dev/null \
  && ok "snapshot --json: services + per-repo dev_tools" || no "snapshot json: $(head -c 300 <<<"$js")"
grep -qE "$SECRET1|$SECRET2" <<<"$out$js" && no "snapshot leaks a planted secret" || ok "snapshot carries no config values"

# -- doctor
out=$(cd "$WS" && python3 -B "$ROOT/scripts/factory-cmd.py" doctor 2>&1)
sec=$(sed -n '/^## Dev tools/,$p' <<<"$out")
n=$(jq '.dev_tools | length' "$ROOT/registry.json")
[ "$(grep -cE '^- [a-z0-9-]+ \((mcp|plugin|binary|service), (required|optional)\): \*\*(OK|DOWN|MISSING)\*\*' <<<"$sec")" -eq "$n" ] \
  && ok "doctor: one Dev tools line per registry entry ($n)" || no "doctor dev tools: $sec"
grep -q '^- codex (plugin, optional): \*\*MISSING\*\*.*plugin codex not enabled' <<<"$sec" && ok "doctor: disabled plugin reported MISSING" || no "doctor codex: $sec"
grep -qE "$SECRET1|$SECRET2|example.invalid|Bearer" <<<"$out" && no "doctor leaks config values" || ok "doctor carries no config values"

# -- a malformed config holding a secret: no parse error, traceback or partial content may surface
printf '{"mcpServers": {"broken": {"env": {"K": "%s"}}' "$SECRET1" > "$C/.mcp.json"     # truncated JSON
out=$(cd "$WS" && { bash "$ROOT/scripts/factory-context.sh" --repo client --paths Assets/Scripts/UI/A.cs; \
                    python3 -B "$ROOT/scripts/factory-cmd.py" doctor; } 2>&1)
grep -qE "$SECRET1|Traceback|JSONDecodeError" <<<"$out" && no "malformed config leaks content or a traceback" \
  || ok "malformed config: no secret, no traceback in snapshot/doctor (stdout+stderr)"
rm -f "$C/.mcp.json"
grep -rqE "$SECRET1|$SECRET2" "$RPG_FACTORY_STATE_DIR" "$TMP/state" 2>/dev/null && no "Factory state files contain a planted secret" \
  || ok "Factory state/evidence files carry no planted secret"

# -- check-registry rejects malformed dev_tools and tech skills (mutated copies, --structure-only)
PR="$TMP/pr"; mkdir -p "$PR/docs"; ln -s "$ROOT/skills" "$PR/skills"; cp "$ROOT/docs/registry.schema.json" "$PR/docs/"
reject() { # name expected-message jq-mutation
  jq "$3" "$ROOT/registry.json" > "$PR/registry.json"
  local o; o=$(CLAUDE_PLUGIN_ROOT="$PR" bash "$ROOT/scripts/check-registry.sh" --structure-only 2>&1)
  if [ $? -ne 0 ] && grep -qF "$2" <<<"$o"; then ok "check-registry rejects: $1"; else no "check-registry accepted $1: $(head -c 300 <<<"$o")"; fi
}
reject "dev tool used by an unknown skill" "used_by unknown skill nosuch" '.dev_tools[0].used_by += ["nosuch"]'
reject "dev tool probe of an unknown kind" "bad probe file:x" '.dev_tools[0].probes += ["file:x"]'
reject "dev tool probe naming an unknown registry tool" "names an unknown tool" '.dev_tools[0].probes += ["tool:nosuch"]'
reject "dev tool probe naming an unknown service" "names an unknown service" '.dev_tools[0].probes += ["service:nosuch"]'
reject "optional dev tool without fallback" "every tool needs a fallback" '(.dev_tools[] | select(.required == false)) |= del(.fallback)'
reject "required dev tool without fallback" "dev_tools dotnet: every tool needs a fallback" '(.dev_tools[] | select(.id == "dotnet")) |= del(.fallback)'
reject "dev tool without a purpose" "dev_tools go: missing field provides" '(.dev_tools[] | select(.id == "go")) |= del(.provides)'
reject "duplicate dev tool id" "duplicate dev_tools id" '.dev_tools += [.dev_tools[0]]'
reject "tech skill without used_by" "used_by (repo/cross-repo skills) missing" '.skills["x-tech"] = {kind: "tech", repos: ["server"], summary: "s", order: 999}'
reject "tech skill used_by a core skill" "used_by factory-core is not a repo/cross-repo skill" '.skills["x-tech"] = {kind: "tech", repos: ["server"], summary: "s", order: 999, used_by: ["factory-core"]}'
reject "tech skill owning a module" "must not own a module" '.skills["x-tech"] = {kind: "tech", repos: ["server"], summary: "s", order: 999, used_by: ["server-realtime"]} | .modules[0].skills += ["x-tech"]'

echo "devtools: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
