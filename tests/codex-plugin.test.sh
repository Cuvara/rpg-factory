#!/usr/bin/env bash
# Codex CLI packaging of the plugin: .codex-plugin/plugin.json, the repo-local Codex marketplace
# (.agents/plugins/marketplace.json), the Codex hook config and the hook adapter scripts/codex_hook.py.
# Each part is checked strictly once its file exists; while a file is absent its checks SKIP with the reason
# (never FAIL). The adapter must stay advisory: exit 0 always, stdout empty or exactly one JSON object, never a
# deny/block decision, no traceback, the advisory level each fixture's README row names, with or without CLAUDE_* env.
#
# Usage: tests/codex-plugin.test.sh     (standalone; own temp TMPDIR / RPG_FACTORY_STATE_DIR; no network, no codex CLI)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
# isolated replay environment (tests/fixtures/codex-hooks/README.md): a stand-in workspace with the registry's root
# markers and git repos, a fresh empty CODEX_HOME and HOME (no install anywhere), no guard switch, no root override
WS="$TMP/ws"
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state" RPG_FACTORY_WORKSPACE="$WS" CODEX_HOME="$TMP/codex-home" HOME="$TMP/home" USERPROFILE="$TMP/home"
unset RPG_FACTORY_GUARD RPG_FACTORY_REGISTRY PLUGIN_ROOT PLUGIN_DATA CLAUDE_PLUGIN_ROOT
mkdir -p "$RPG_FACTORY_STATE_DIR" "$WS" "$TMP/elsewhere" "$CODEX_HOME" "$HOME"
while IFS= read -r m; do mkdir -p "$WS/$(dirname "$m")"; touch "$WS/$m"; done < <(jq -r '.workspace.root_markers[]' "$ROOT/registry.json")
for r in "$WS"/*/; do git init -q "$r" && git -C "$r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init; done
CM="$ROOT/.codex-plugin/plugin.json"; MK="$ROOT/.agents/plugins/marketplace.json"
AD="$ROOT/scripts/codex_hook.py"; FX="$ROOT/tests/fixtures/codex-hooks"
VERSION=$(tr -d '[:space:]' < "$ROOT/VERSION")
pass=0; fail=0; skip=0
ok()  { pass=$((pass + 1)); echo "PASS  $1"; }
no()  { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/      /'; return 0; }
skp() { skip=$((skip + 1)); echo "SKIP  $1 ($2)"; }

# hookout.py <stdout-file> <stderr-file>: grades one adapter run. Prints "<level> <problems>" where level is
# none|warn|high and problems is empty or a ;-joined list (not one JSON object, a deny/block decision, a traceback).
cat > "$TMP/hookout.py" <<'PY'
import json, os, sys
sys.stdout.reconfigure(newline="\n")  # no CR on Windows: bash `read` would keep it
out = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
err = open(sys.argv[2], "rb").read().decode("utf-8", "replace")
problems, strings = [], []
if "Traceback (most recent call last)" in err or "Traceback (most recent call last)" in out:
    problems.append("traceback")
obj = None
if out.strip():
    try:
        obj = json.loads(out)
    except ValueError as e:
        problems.append("stdout is not exactly one JSON value (%s)" % str(e)[:80])
    else:
        if not isinstance(obj, dict):
            problems.append("stdout JSON is a %s, not an object" % type(obj).__name__)
def walk(v):
    if isinstance(v, dict):
        for k, x in v.items():
            if k == "permissionDecision":
                problems.append("permissionDecision=%r" % (x,))
            if k == "decision" and str(x).lower() in ("block", "deny"):
                problems.append("decision=%r" % (x,))
            if k == "continue" and x is False:
                problems.append("continue=false")
            walk(x)
    elif isinstance(v, list):
        for x in v:
            walk(x)
    elif isinstance(v, str):
        strings.append(v)
walk(obj)
if os.environ.get("SHAPE") == "1" and isinstance(obj, dict):
    inner = obj.get("hookSpecificOutput")
    if set(obj) != {"hookSpecificOutput"} or not isinstance(inner, dict) or not set(inner) <= {"hookEventName", "additionalContext"}:
        problems.append("shape: expected only hookSpecificOutput.{hookEventName,additionalContext}, got %s" % json.dumps(obj)[:160])
text = "\n".join(strings)
level = "high" if "rpg-factory advisory (high)" in text else "warn" if "rpg-factory advisory (warn)" in text else "none"
if os.environ.get("SHAPE") == "1" and level == "none" and out.strip():
    problems.append("shape: no advisory but stdout is not empty")
print(level, ";".join(problems))
PY

# run_adapter <event> <stdin-file> [env-prefix...]: runs the adapter from an unrelated cwd; sets RC, LEVEL, PROBS
run_adapter() {
  local ev="$1" in="$2"; shift 2
  (cd "$TMP/elsewhere" && "$@" python3 -B "$AD" "$ev" < "$in" > "$TMP/o" 2> "$TMP/e"); RC=$?
  read -r LEVEL PROBS < <(python3 -B "$TMP/hookout.py" "$TMP/o" "$TMP/e")
}

echo "-- Codex manifest (.codex-plugin/plugin.json)"
if [ ! -f "$CM" ]; then
  skp "Codex manifest: valid JSON, name, version, skills" ".codex-plugin/plugin.json absent"
  skp "Codex manifest exposes the same skill set as the Claude manifest" ".codex-plugin/plugin.json absent"
else
  if jq -e . "$CM" >/dev/null 2>&1; then ok "Codex manifest is valid JSON"; else no "Codex manifest is valid JSON" "$(jq . "$CM" 2>&1 | tail -2)"; fi
  n=$(jq -r '.name // empty' "$CM" 2>/dev/null); v=$(jq -r '.version // empty' "$CM" 2>/dev/null); s=$(jq -r '.skills // empty' "$CM" 2>/dev/null)
  [ "$n" = rpg-factory ] && ok "Codex manifest name rpg-factory" || no "Codex manifest name" "name=$n"
  [ "$v" = "$VERSION" ] && ok "Codex manifest version == VERSION ($VERSION)" || no "Codex manifest version == VERSION" "codex=$v VERSION=$VERSION"
  [ "$s" = "./skills/" ] && ok "Codex manifest skills ./skills/" || no "Codex manifest skills ./skills/" "skills=$s"
  # same skill set: every directory with a SKILL.md under each manifest's skills path
  skillset() { local d="$ROOT/${1#./}"; [ -d "$d" ] && for f in "$d"/*/SKILL.md; do [ -f "$f" ] && basename "$(dirname "$f")"; done | sort; }
  cs=$(skillset "$(jq -r .skills "$ROOT/.claude-plugin/plugin.json")"); xs=$(skillset "${s:-./missing/}")
  if [ -n "$cs" ] && [ "$cs" = "$xs" ]; then ok "Codex manifest exposes the same skill set as the Claude manifest ($(wc -l <<<"$cs") skills)"
  else no "Codex manifest skill set == Claude manifest skill set" "$(diff <(echo "$cs") <(echo "$xs"))"; fi
fi

echo "-- Codex marketplace (.agents/plugins/marketplace.json)"
if [ ! -f "$MK" ]; then
  skp "Codex marketplace: valid JSON, name, plugin entry, local source, version" ".agents/plugins/marketplace.json absent"
else
  if jq -e . "$MK" >/dev/null 2>&1; then ok "Codex marketplace is valid JSON"; else no "Codex marketplace is valid JSON" "$(jq . "$MK" 2>&1 | tail -2)"; fi
  [ "$(jq -r '.name // empty' "$MK")" = rpg-factory ] && ok "Codex marketplace name rpg-factory" || no "Codex marketplace name" "$(jq -c .name "$MK")"
  [ "$(jq -r '.plugins[0].name // empty' "$MK")" = rpg-factory ] && ok "Codex marketplace plugins[0].name rpg-factory" \
    || no "Codex marketplace plugins[0].name" "$(jq -c '.plugins[0]' "$MK")"
  # a local source: {"source":"local","path":"./..."} (Codex) or a relative path string; it must resolve to this checkout
  src=$(jq -r '.plugins[0].source | if type == "object" then (if .source == "local" then (.path // "") else "" end) else (. // "") end' "$MK")
  sdir=""; case "$src" in ./*|.) sdir="$ROOT/${src#./}" ;; esac
  # Codex resolves a local path against the marketplace root: the directory that holds .agents/plugins/
  if [ -n "$sdir" ] && [ -f "$sdir/.codex-plugin/plugin.json" ] && [ "$(cd "$sdir" && pwd)" = "$(cd "$ROOT" && pwd)" ]; then
    ok "Codex marketplace plugins[0] has a local source resolving to this checkout ($src)"
  else no "Codex marketplace local source" "source=$(jq -c '.plugins[0].source' "$MK")"; fi
  mv=$(jq -r '[.version?, (.plugins[] | select(.name == "rpg-factory") | .version?)] | map(select(. != null))[]' "$MK" | sort -u)
  if [ -z "$mv" ]; then ok "Codex marketplace carries no version (nothing to agree)"
  elif [ "$mv" = "$VERSION" ]; then ok "Codex marketplace version == VERSION ($VERSION)"
  else no "Codex marketplace version == VERSION" "marketplace=$(tr '\n' ' ' <<<"$mv") VERSION=$VERSION"; fi
fi

echo "-- Codex hook config"
# The manifest's "hooks" is either an inline object or a path (or list of paths) relative to the plugin root.
hook_cfgs=()
if [ -f "$CM" ]; then
  while IFS= read -r p; do [ -n "$p" ] && hook_cfgs+=("$ROOT/${p#./}"); done < <(jq -r '.hooks | if type == "string" then . elif type == "array" then .[] else empty end' "$CM" 2>/dev/null)
  if jq -e '.hooks | type == "object"' "$CM" >/dev/null 2>&1; then jq '{hooks: .hooks}' "$CM" > "$TMP/inline-hooks.json"; hook_cfgs+=("$TMP/inline-hooks.json"); fi
fi
if [ ! -f "$CM" ]; then skp "Codex hook commands: existing script, fail-safe '; exit 0'" ".codex-plugin/plugin.json absent"
elif [ ${#hook_cfgs[@]} -eq 0 ]; then skp "Codex hook commands: existing script, fail-safe '; exit 0'" "the Codex manifest declares no hooks"
else
  hbad=""; hn=0
  for cfg in "${hook_cfgs[@]}"; do
    if ! jq -e . "$cfg" >/dev/null 2>&1; then hbad+="unreadable hook config: $cfg"$'\n'; continue; fi
    while IFS= read -r c; do
      hn=$((hn + 1))
      [[ "$c" =~ \;[[:space:]]*exit[[:space:]]+0[[:space:]]*$ ]] || hbad+="does not end with '; exit 0': $c"$'\n'
      scripts=$(grep -oE 'scripts/[A-Za-z0-9_./-]+\.(py|sh)' <<<"$c" | sort -u)
      [ -n "$scripts" ] || hbad+="names no scripts/*.py|sh: $c"$'\n'
      for s in $scripts; do [ -f "$ROOT/$s" ] || hbad+="script missing ($s): $c"$'\n'; done
    done < <(jq -r '[.. | objects | select(has("command")) | .command | strings] | .[]' "$cfg")
  done
  [ "$hn" -gt 0 ] || hbad+="no command hooks found in: ${hook_cfgs[*]}"$'\n'
  [ -z "$hbad" ] && ok "Codex hook commands ($hn): each runs an existing script and ends with '; exit 0'" || no "Codex hook commands" "$hbad"
  # advisory only: no hook config may carry a blocking decision of its own
  if jq -se '[.[] | .. | objects | select(has("permissionDecision") or ((.decision? // "") | tostring | test("^(block|deny)$"; "i")))] | length == 0' "${hook_cfgs[@]}" >/dev/null 2>&1; then
    ok "Codex hook config carries no permissionDecision / block / deny"
  else no "Codex hook config carries a blocking decision"; fi
fi

echo "-- hook adapter (scripts/codex_hook.py): robustness"
if [ ! -f "$AD" ]; then
  skp "adapter: exit 0, one JSON object or nothing, never deny/block, no traceback (empty/malformed/huge/binary stdin)" "scripts/codex_hook.py absent"
else
  : > "$TMP/in-empty"
  printf '{"hook_event_name": "PreToolUse", "tool_input": {' > "$TMP/in-malformed"
  printf '[1, 2, 3]' > "$TMP/in-array"; printf 'null' > "$TMP/in-null"
  printf '{"hook_event_name": 5, "tool_name": ["x"], "tool_input": "git push --tags", "cwd": 7}' > "$TMP/in-wrongtypes"
  python3 -B -c "import json,sys; sys.stdout.write(json.dumps({'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':'echo ' + 'a' * (4 << 20)},'cwd':'.'}))" > "$TMP/in-huge"
  python3 -B -c "import sys; sys.stdout.buffer.write(b'{' * 200000)" > "$TMP/in-deep"
  python3 -B -c "import os,sys; sys.stdout.buffer.write(b'\xff\xfe\x00' + os.urandom(65536))" > "$TMP/in-binary"
  for ev in session-start pre-tool-use; do
    for c in empty malformed array null wrongtypes huge deep binary; do
      run_adapter "$ev" "$TMP/in-$c"
      if [ "$RC" -eq 0 ] && [ -z "$PROBS" ]; then ok "adapter $ev: $c stdin -> exit 0, valid output, no deny/block, no traceback"
      else no "adapter $ev: $c stdin" "rc=$RC problems=${PROBS:-none} stderr: $(head -c 400 "$TMP/e")"; fi
    done
  done
  run_adapter no-such-event "$TMP/in-empty"
  [ "$RC" -eq 0 ] && [ -z "$PROBS" ] && ok "adapter: unknown event argument -> exit 0, no traceback" || no "adapter: unknown event" "rc=$RC ${PROBS}"
  (cd "$TMP/elsewhere" && python3 -B "$AD" < "$TMP/in-empty" > "$TMP/o" 2> "$TMP/e"); RC=$?
  read -r LEVEL PROBS < <(python3 -B "$TMP/hookout.py" "$TMP/o" "$TMP/e")
  [ "$RC" -eq 0 ] && [ -z "$PROBS" ] && ok "adapter: no event argument -> exit 0, no traceback" || no "adapter: no event argument" "rc=$RC ${PROBS}"
fi

echo "-- hook adapter: fixtures (tests/fixtures/codex-hooks, levels from its README.md)"
if [ ! -f "$AD" ] || [ ! -d "$FX" ]; then
  why=$({ [ -f "$AD" ] || echo "scripts/codex_hook.py absent"; [ -d "$FX" ] || echo "tests/fixtures/codex-hooks absent"; } | paste -sd, - | sed 's/,/, /g')
  skp "adapter fixtures: advisory level per README row" "$why"
  skp "adapter fixtures with every CLAUDE_* variable unset" "fixtures or adapter absent"
elif [ ! -f "$FX/README.md" ]; then
  no "adapter fixtures: README.md lists the expected level per fixture" "tests/fixtures/codex-hooks/README.md missing"
else
  # README rows: a line naming <event>-<case>.json and the level none|warn|high (first level word after the name)
  python3 -B - "$FX/README.md" > "$TMP/levels" <<'PY'
import re, sys
sys.stdout.reconfigure(newline="\n")
for line in open(sys.argv[1], encoding="utf-8"):
    m = re.search(r"((?:session-start|pre-tool-use)-[A-Za-z0-9_.-]+?\.json)(.*)", line)
    if m:
        lv = re.search(r"\b(none|warn|high)\b", m.group(2))
        print(m.group(1), lv.group(1) if lv else "?")
PY
  fxs=$(cd "$FX" && ls -1 *.json 2>/dev/null | sort)
  listed=$(cut -d' ' -f1 "$TMP/levels" | sort -u)
  [ -n "$fxs" ] && ok "fixtures present: $(wc -l <<<"$fxs")" || no "fixtures present" "no *.json in $FX"
  [ "$fxs" = "$listed" ] && ok "README.md lists exactly the fixture files" || no "README.md lists exactly the fixture files" "$(diff <(echo "$fxs") <(echo "$listed"))"
  # names are <event>-<case>.json, the event being the adapter's argument
  bad_names=$(grep -vE '^(session-start|pre-tool-use)-[A-Za-z0-9_.-]+\.json$' <<<"$fxs")
  [ -z "$bad_names" ] && ok "fixture names are <session-start|pre-tool-use>-<case>.json" || no "fixture names" "$bad_names"
  # fixtures carry the placeholder cwd /codex-fixture/workspace/<repo>: point it at the stand-in workspace
  mkdir -p "$TMP/fx"
  python3 -B - "$FX" "$TMP/fx" "$WS" <<'PY'
import json, os, sys
src, dst, ws = sys.argv[1:4]
for f in os.listdir(src):
    if not f.endswith(".json"):
        continue
    raw = open(os.path.join(src, f), "rb").read()
    try:
        d = json.loads(raw)
    except ValueError:
        d = None
    if isinstance(d, dict) and isinstance(d.get("cwd"), str) and d["cwd"].startswith("/codex-fixture/workspace/"):
        d["cwd"] = os.path.join(ws, d["cwd"][len("/codex-fixture/workspace/"):])
        raw = json.dumps(d).encode("utf-8")
    open(os.path.join(dst, f), "wb").write(raw)
PY
  # pass 1 as Codex runs an installed plugin hook (PLUGIN_ROOT, PLUGIN_DATA, compat CLAUDE_PLUGIN_ROOT); pass 2 with
  # every CLAUDE_* variable of this environment (plus the ones Claude Code sets) and PLUGIN_ROOT unset: the adapter
  # must resolve the plugin root itself
  unset_claude=(env -u PLUGIN_ROOT -u PLUGIN_DATA)
  for v in $(env | sed -n 's/^\(CLAUDE[A-Za-z0-9_]*\)=.*/\1/p') CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR CLAUDE_SESSION_ID CLAUDECODE; do unset_claude+=(-u "$v"); done
  export SHAPE=1  # fixture README: advisory output is only hookSpecificOutput.{hookEventName,additionalContext}
  for pass_kind in codex-env no-claude; do
    while read -r f want; do
      [ -f "$TMP/fx/$f" ] || continue
      ev=$(sed -nE 's/^(session-start|pre-tool-use)-.*/\1/p' <<<"$f")
      if [ "$pass_kind" = codex-env ]; then
        run_adapter "$ev" "$TMP/fx/$f" env PLUGIN_ROOT="$ROOT" PLUGIN_DATA="$TMP/plugin-data" CLAUDE_PLUGIN_ROOT="$ROOT"
      else run_adapter "$ev" "$TMP/fx/$f" "${unset_claude[@]}"; fi
      label="fixture $f ($pass_kind): exit 0, no deny/block, level $want"
      if [ "$RC" -eq 0 ] && [ -z "$PROBS" ] && [ "$LEVEL" = "$want" ]; then ok "$label"
      else no "$label" "got level $LEVEL rc=$RC ${PROBS:+problems=$PROBS} stderr: $(head -c 300 "$TMP/e")"; fi
    done < "$TMP/levels"
  done
  # the fixture set must exercise the adapter's advisories, not only the silent path
  grep -qw high "$TMP/levels" && ok "fixture set includes a high advisory case" || no "fixture set has no high case (e.g. git push --tags)"
  grep -qw none "$TMP/levels" && ok "fixture set includes a silent (none) case" || no "fixture set has no none case"
fi

total=$((pass + fail + skip))
echo "codex-plugin tests: $total run, $pass passed, $fail failed, $skip skipped"
[ "$fail" -eq 0 ]
