#!/usr/bin/env bash
# Headless end-to-end dogfood for the Codex CLI packaging: installs this checkout as a Codex plugin into a
# THROWAWAY CODEX_HOME and runs short real `codex exec` sessions, then grades the JSONL transcripts
# deterministically (like tests/dogfood.sh does for Claude Code).
#
# Opt-in: it spends model tokens and takes minutes. Not part of run-all.sh.
# Never modifies ~/.codex: the throwaway home gets a copy of auth.json, the top-level `model` and the [windows]
# table of ~/.codex/config.toml (nothing else), the rpg-factory marketplace (this checkout) and the plugin.
# Sessions run with `-s read-only` and `--dangerously-bypass-hook-trust` (the throwaway home has no persisted hook
# trust; the only plugin hooks installed there are this checkout's own advisory hooks).
# Transcripts land in ${DOGFOOD_OUT:-/tmp/rpgf-dogfood-codex}/<scenario>.jsonl (+ .last.txt, .stderr).
#
# Usage: tests/dogfood-codex.sh [--dry-run] [--model M] [--keep-home] [scenario...]
#   --dry-run    print the plan (home layout, install and exec commands, scenarios) and self-test the grader on
#                synthetic transcripts; runs no codex command and spends no tokens
#   --model M    model for the sessions (default: `model` of ~/.codex/config.toml, else Codex's default)
#   --keep-home  keep the throwaway CODEX_HOME after the run (default: removed)
# Scenarios: route-wire tags-policy push-tags skills-list (default: all)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
OUT="${DOGFOOD_OUT:-/tmp/rpgf-dogfood-codex}"
WS="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
[ -d "$WS" ] || { [ -n "$RPGF_WINDOWS" ] && [ -d C:/Workspaces/UnityIndie ] && WS=C:/Workspaces/UnityIndie; }
REAL_HOME="${CODEX_HOME:-$HOME/.codex}"
dry=false; keep=false; model=""
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) dry=true; shift;;
  --keep-home) keep=true; shift;;
  --model) model="$2"; shift 2;;
  -h|--help) sed -n '2,/^set -uo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0;;
  -*) echo "dogfood-codex: unknown option $1" >&2; exit 2;;
  *) break;;
esac; done
all=(route-wire tags-policy push-tags skills-list)
scenarios=("$@"); [ ${#scenarios[@]} -gt 0 ] || scenarios=("${all[@]}")
for n in "${scenarios[@]}"; do case " ${all[*]} " in *" $n "*) ;; *) echo "dogfood-codex: unknown scenario $n (have: ${all[*]})" >&2; exit 2;; esac; done
VERSION=$(tr -d '[:space:]' < "$ROOT/VERSION")
[ -n "$model" ] || model=$(sed -n 's/^model *= *"\([^"]*\)".*/\1/p' "$REAL_HOME/config.toml" 2>/dev/null | head -1)

# PROMPT: the request. CWD: ws (the RPG MMO workspace) or tagrepo (a throwaway repo with a local bare origin).
# ANSWER: |-separated alternatives; space = all of (case-insensitive) in the final message.
# SKILLREF: a command the session ran must use the plugin's skill files or scripts (regex over executed commands only:
#           the prompt names them too, so free text proves nothing).
# ADVISORY: the hook level that must reach the session ("rpg-factory advisory (<level>)" in the transcript, the
#           throwaway home's session rollouts or the scenario's RPG_FACTORY_STATE_DIR).
declare -A PROMPT CWD ANSWER SKILLREF ADVISORY
PROMPT[route-wire]="Which rpg-factory lead skill owns a change to rpg-mmo-server backend/shared/proto/wire.proto? Use the rpg-factory factory-core skill and its routing script (factory-context.sh --repo server --paths ...). Do not edit any file. Answer with the lead skill name and the follow-up skills in under 120 words."
CWD[route-wire]=ws; ANSWER[route-wire]="wire-contract"; SKILLREF[route-wire]="factory-context"
PROMPT[tags-policy]="What does the rpg-factory factory-core skill say about creating git tags and GitHub releases? Read the skill and its git-safety reference; do not run git commands that change state. Answer in under 120 words."
CWD[tags-policy]=ws; ANSWER[tags-policy]="READY_TO_TAG authoriz"; SKILLREF[tags-policy]="git-safety|factory-core.SKILL"
PROMPT[push-tags]="In this repository, run exactly this command and report what happened: git push --tags"
CWD[push-tags]=tagrepo; ANSWER[push-tags]=""; SKILLREF[push-tags]=""; ADVISORY[push-tags]=high
PROMPT[skills-list]="List, by name only, the skills the rpg-factory plugin provides in this session. Do not run commands that change anything."
CWD[skills-list]=ws; ANSWER[skills-list]="factory-core wire-contract pin-bump"; SKILLREF[skills-list]=""

GRADER="$(mktemp_win)/grade.py"; trap 'rm -rf "$(dirname "$GRADER")"' EXIT
cat > "$GRADER" <<'PY'
"""grade.py <jsonl> <last-message-file> <answer-spec> <skillref-regex> <advisory-level> <advisory-dir> <origin-or->
Deterministic grade of one `codex exec --json` transcript. Prints PASS or FAIL: <reasons>; exit 0/1."""
import json, os, re, subprocess, sys
jl, last, answer, skillref, level, adir, origin = sys.argv[1:8]
sys.stdout.reconfigure(newline="\n")
why, events = [], []
raw = open(jl, encoding="utf-8", errors="replace").read() if os.path.exists(jl) else ""
for line in raw.splitlines():
    line = line.strip()
    if line.startswith("{"):
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
items = [e.get("item") or {} for e in events if str(e.get("type", "")).startswith("item.")]
cmds = [str(i.get("command", "")) for i in items if i.get("type") == "command_execution"]
final = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
if not final:
    final = next((str(i.get("text", "")) for i in reversed(items) if i.get("type") == "agent_message"), "")
if not events:
    why.append("no JSON events (codex exec did not run?)")
if not any(e.get("type") == "turn.completed" for e in events) or any(e.get("type") in ("turn.failed", "error") for e in events):
    why.append("session did not complete (no turn.completed, or turn.failed/error)")
if not final.strip():
    why.append("empty final message")
if any(i.get("type") == "file_change" for i in items):
    why.append("file_change item in a read-only session")
for c in cmds:  # read-only sandbox: a state-changing git command must never have succeeded
    it = next(i for i in items if i.get("type") == "command_execution" and str(i.get("command", "")) == c)
    if it.get("exit_code") == 0 and re.search(
            r"\bgit\s+(?:-[Cc]\s+\S+\s+)*(?:push|commit|reset|checkout|switch|merge|rebase|tag\s+(?!-l\b|--list\b|-n\b)\S)", c):
        why.append("state-changing git command succeeded: %s" % c[:120])
for spec in answer.split():
    if not any(a.lower() in final.lower() for a in spec.split("|")):
        why.append("answer lacks %s" % spec)
if skillref and not re.search(skillref, "\n".join(cmds), re.I):
    why.append("no executed command used the plugin skill/script (%s)" % skillref)
if level != "-":  # the hook context reaches the model, not necessarily the JSONL: also search the session rollouts
    tag = "rpg-factory advisory (%s)" % level
    logged = ""
    for root in [d for d in adir.split("|") if os.path.isdir(d)]:
        for d, _, fs in os.walk(root):
            for f in fs:
                try:
                    logged += open(os.path.join(d, f), encoding="utf-8", errors="replace").read() + "\n"
                except OSError:
                    pass
    if tag not in raw and tag not in logged:
        why.append("no %s advisory in the transcript, the session rollouts or the state dir" % level)
if origin != "-":
    r = subprocess.run(["git", "ls-remote", "--tags", origin], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip():
        why.append("origin has tags after the session (push executed?): %s" % (r.stdout.strip() or r.stderr.strip()).replace("\n", " ")[:120])
print("PASS" if not why else "FAIL: " + "; ".join(why))
sys.exit(0 if not why else 1)
PY

# tagrepo <dir>: a throwaway repo with one commit and tag v0.0.1, plus a local bare origin without tags
tagrepo() {
  local d="$1"; rm -rf -- "$d"; mkdir -p "$d"
  git init -q --bare "$d/origin.git"; git init -q -b main "$d/repo"
  git -C "$d/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  git -C "$d/repo" remote add origin "$d/origin.git"; git -C "$d/repo" push -q origin main 2>/dev/null
  git -C "$d/repo" -c user.email=t@t -c user.name=t tag -a v0.0.1 -m "dogfood tag"
}

if $dry; then
  echo "dogfood-codex --dry-run (no codex command runs, no tokens)"
  echo "  plugin root:   $ROOT (version $VERSION)"
  echo "  workspace:     $WS $([ -d "$WS" ] && echo '(present)' || echo '(ABSENT: ws scenarios would fail)')"
  echo "  codex:         $(command -v codex >/dev/null 2>&1 && codex --version 2>/dev/null || echo 'not on PATH')"
  echo "  real home:     $REAL_HOME (read only: auth.json $([ -f "$REAL_HOME/auth.json" ] && echo present || echo ABSENT))"
  echo "  model:         ${model:-codex default}"
  echo "  throwaway home: \$OUT/codex-home = $OUT/codex-home"
  for f in .codex-plugin/plugin.json .agents/plugins/marketplace.json scripts/codex_hook.py; do
    echo "  $f: $([ -f "$ROOT/$f" ] && echo present || echo 'ABSENT (install would fail)')"; done
  echo "  install:       CODEX_HOME=<home> codex plugin marketplace add $ROOT"
  echo "                 CODEX_HOME=<home> codex plugin add rpg-factory@rpg-factory"
  echo "  verify:        codex plugin list --marketplace rpg-factory --json reports $VERSION; <home>/plugins/cache/rpg-factory/rpg-factory/$VERSION/ exists"
  echo "  exec:          CODEX_HOME=<home> codex exec --json -s read-only --skip-git-repo-check --dangerously-bypass-hook-trust -C <cwd> -o <last> <prompt>"
  for n in "${scenarios[@]}"; do
    printf '  scenario %-12s cwd=%-8s answer=[%s] skillref=[%s] advisory=[%s]\n' "$n" "${CWD[$n]}" "${ANSWER[$n]}" "${SKILLREF[$n]}" "${ADVISORY[$n]:-}"
  done
  # grader self-test on synthetic transcripts: one that must pass, one per failure class that must fail
  st="$(dirname "$GRADER")/selftest"; mkdir -p "$st/adv"; tagrepo "$st/t"; sfail=0
  printf '%s\n' '{"type":"thread.started","thread_id":"x"}' \
    '{"type":"item.completed","item":{"type":"command_execution","command":"bash scripts/factory-context.sh --repo server","exit_code":0}}' \
    '{"type":"item.completed","item":{"type":"agent_message","text":"Lead: wire-contract."}}' '{"type":"turn.completed"}' > "$st/ok.jsonl"
  printf '%s\n' '{"type":"item.completed","item":{"type":"command_execution","command":"git push --tags","exit_code":0}}' \
    '{"type":"item.completed","item":{"type":"agent_message","text":"pushed"}}' '{"type":"turn.completed"}' > "$st/push.jsonl"
  printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"blocked by sandbox. rpg-factory advisory (high): tag push"}}' '{"type":"turn.completed"}' > "$st/adv.jsonl"
  t() { local want="$1" name="$2"; shift 2; local r; r=$(python3 -B "$GRADER" "$@" | tr -d '\r'); case "$r" in "$want"*) echo "  self-test PASS  $name -> $r";; *) sfail=$((sfail + 1)); echo "  self-test FAIL  $name -> $r";; esac; }
  t PASS "route-wire transcript grades PASS" "$st/ok.jsonl" none wire-contract "factory-core|factory-context" - "$st/adv" -
  t FAIL "missing answer term fails" "$st/ok.jsonl" none pin-bump "" - "$st/adv" -
  t FAIL "no plugin trace fails" "$st/ok.jsonl" none wire-contract "git-safety" - "$st/adv" -
  t FAIL "succeeded git push fails" "$st/push.jsonl" none "" "" - "$st/adv" -
  t PASS "high advisory in transcript, origin untouched" "$st/adv.jsonl" none "" "" high "$st/adv" "$st/t/origin.git"
  t FAIL "no advisory fails" "$st/ok.jsonl" none "" "" high "$st/adv" -
  mkdir -p "$st/roll/2026"; echo '{"context":"rpg-factory advisory (high): tag push"}' > "$st/roll/2026/rollout.jsonl"
  t PASS "high advisory only in a session rollout" "$st/ok.jsonl" none "" "" high "$st/adv|$st/roll" -
  echo "rpg-factory advisory (warn): other" > "$st/adv/rollout.jsonl"; git -C "$st/t/repo" push -q origin v0.0.1 2>/dev/null
  t FAIL "tag reached origin fails" "$st/adv.jsonl" none "" "" high "$st/adv" "$st/t/origin.git"
  t FAIL "empty transcript fails" "$st/none.jsonl" none "" "" - "$st/adv" -
  echo "dogfood-codex dry-run: grader self-test $((9 - sfail))/9 passed"
  [ "$sfail" -eq 0 ]; exit
fi

command -v codex >/dev/null 2>&1 || { echo "dogfood-codex: codex CLI not on PATH" >&2; exit 2; }
for f in .codex-plugin/plugin.json .agents/plugins/marketplace.json scripts/codex_hook.py; do
  [ -f "$ROOT/$f" ] || { echo "dogfood-codex: $f absent - nothing to install" >&2; exit 2; }; done
[ -f "$REAL_HOME/auth.json" ] || { echo "dogfood-codex: $REAL_HOME/auth.json absent (codex login first)" >&2; exit 2; }
mkdir -p "$OUT"; OUT="$(cd "$OUT" && { pwd -W 2>/dev/null || pwd; })"
CH="$OUT/codex-home"
case "$(cd "$REAL_HOME" 2>/dev/null && pwd -P)" in "$(mkdir -p "$CH" && cd "$CH" && pwd -P)") echo "refusing: throwaway home == real home" >&2; exit 2;; esac
rm -rf -- "$CH"; mkdir -p "$CH"
cp "$REAL_HOME/auth.json" "$CH/auth.json"
{ [ -n "$model" ] && printf 'model = "%s"\n' "$model"
  printf 'model_reasoning_effort = "medium"\n\n[features]\nhooks = true\n\n'
  printf "[projects.'%s']\ntrust_level = \"trusted\"\n\n" "$WS"
  awk '/^\[windows\]/{on=1; print; next} /^\[/{on=0} on' "$REAL_HOME/config.toml" 2>/dev/null
} > "$CH/config.toml"
$keep || trap 'rm -rf "$(dirname "$GRADER")" "$CH"' EXIT
cx() { CODEX_HOME="$CH" codex "$@"; }
echo "-- install into throwaway CODEX_HOME ($CH)"
cx plugin marketplace add "$ROOT" > "$OUT/install.log" 2>&1 || { cat "$OUT/install.log"; echo "dogfood-codex: marketplace add failed" >&2; exit 1; }
cx plugin add rpg-factory@rpg-factory >> "$OUT/install.log" 2>&1 || { cat "$OUT/install.log"; echo "dogfood-codex: plugin add failed" >&2; exit 1; }
cx plugin list --marketplace rpg-factory --json > "$OUT/plugin-list.json" 2>&1
# Codex installs a copy keyed by version: the listing and the cache directory must both be at VERSION
if grep -q '"rpg-factory' "$OUT/plugin-list.json" && grep -q "\"$VERSION\"" "$OUT/plugin-list.json" \
   && [ -f "$CH/plugins/cache/rpg-factory/rpg-factory/$VERSION/.codex-plugin/plugin.json" ]; then
  echo "PASS  installed: rpg-factory $VERSION listed and copied to plugins/cache/rpg-factory/rpg-factory/$VERSION"
else cat "$OUT/plugin-list.json"; ls -R "$CH/plugins/cache" 2>/dev/null | head -20; echo "FAIL  rpg-factory $VERSION not installed" >&2; exit 1; fi

pass=0; fail=0; start=$(date +%s)
for n in "${scenarios[@]}"; do
  sd="$OUT/state-$n"; rm -rf -- "$sd"; mkdir -p "$sd"; origin=-
  if [ "${CWD[$n]}" = tagrepo ]; then tagrepo "$OUT/tagrepo-$n"; cwd="$OUT/tagrepo-$n/repo"; origin="$OUT/tagrepo-$n/origin.git"
  else cwd="$WS"; fi
  m=(); [ -n "$model" ] && m=(-m "$model")
  (cd "$cwd" && CODEX_HOME="$CH" RPG_FACTORY_STATE_DIR="$sd" RPG_FACTORY_WORKSPACE="$WS" timeout 600 \
    codex exec --json -s read-only --skip-git-repo-check --dangerously-bypass-hook-trust "${m[@]}" -C "$cwd" \
    -o "$OUT/$n.last.txt" "${PROMPT[$n]}" </dev/null > "$OUT/$n.jsonl" 2> "$OUT/$n.stderr")
  r=$(python3 -B "$GRADER" "$OUT/$n.jsonl" "$OUT/$n.last.txt" "${ANSWER[$n]}" "${SKILLREF[$n]}" "${ADVISORY[$n]:--}" "$sd|$CH/sessions" "$origin" | tr -d '\r')
  case "$r" in PASS*) pass=$((pass + 1));; *) fail=$((fail + 1));; esac
  printf '%-12s | %s\n' "$n" "$r"
done
echo "dogfood-codex: $((pass + fail)) run, $pass passed, $fail failed (model ${model:-default}; installed $VERSION; $(( $(date +%s) - start ))s; transcripts in $OUT)"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
