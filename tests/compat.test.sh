#!/usr/bin/env bash
# Cross-platform behaviour (Linux, WSL, Windows git-bash): scripts/lib/compat.sh helpers, and every
# Python entry point writing UTF-8 whatever the console or pipe encoding is (Windows defaults to cp1252).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

# jq -r output carries no \r, so `for x in $(jq -r ...)` yields usable names and paths
printf '{"a":["x","y"]}' > "$TMP/j.json"
got=$(jq -r '.a[]' "$TMP/j.json" | od -An -c | tr -d ' \n')
[ "$got" = 'x\ny\n' ] && ok "jq -r lines end in LF only" || no "jq -r output bytes: $got"
names=""; for n in $(jq -r '.a[]' "$TMP/j.json"); do names="$names[$n]"; done
[ "$names" = "[x][y]" ] && ok "jq -r word splitting gives clean names" || no "jq -r names: $names"
jq -e '.missing' "$TMP/j.json" >/dev/null 2>&1; [ $? -ne 0 ] && ok "jq -e failure status survives the wrapper" || no "jq -e exit status lost"

# temp dirs are absolute and usable by bash and by native Python alike
is_abs "$TMP" && ok "mktemp_win is absolute ($TMP)" || no "mktemp_win not absolute: $TMP"
py=$(python3 -B -c "import os,sys; print(os.path.isdir(sys.argv[1]))" "$TMP")
[ "$py" = "True" ] && ok "native python resolves the mktemp_win path" || no "python cannot see $TMP"
is_abs "relative/x" && no "is_abs accepted a relative path" || ok "is_abs rejects a relative path"
is_abs "/x" && ok "is_abs accepts /x" || no "is_abs rejected /x"
if [ -n "$RPGF_WINDOWS" ]; then
  is_abs 'C:\x' && is_abs 'C:/x' && ok "is_abs accepts C:\\x and C:/x on Windows" || no "is_abs rejects a drive path"
else
  is_abs 'C:/x' && no "is_abs accepted C:/x off Windows" || ok "is_abs rejects C:/x off Windows"
fi
[ "$(fwd 'a\b\c')" = "a/b/c" ] && ok "fwd turns backslashes into slashes" || no "fwd: $(fwd 'a\b\c')"

# a directory under a C:/ path still works as a $PATH entry
mkdir -p "$TMP/bin"; printf '#!/bin/sh\necho hi\n' > "$TMP/bin/rpgf-probe-tool"; chmod +x "$TMP/bin/rpgf-probe-tool"
[ "$(PATH="$(path_entry "$TMP/bin"):$PATH" rpgf-probe-tool 2>/dev/null)" = "hi" ] && ok "path_entry dir is found on PATH" || no "path_entry dir not on PATH"

# tool lookup finds what bash finds (Windows: python3 is python3.exe, reached through PATHEXT)
for t in python3 git jq; do
  command -v "$t" >/dev/null 2>&1 || continue
  r=$(cd "$ROOT/scripts/lib" && python3 -B -c "import sys, context, devtools; print(bool(context.which([sys.argv[1]])), bool(devtools.which(sys.argv[1])))" "$t")
  [ "$r" = "True True" ] && ok "context.which / devtools.which find $t" || no "which($t): $r"
done

# scripts launched from native Python run under a real bash, never the System32 WSL launcher (bash.exe in System32
# wins over PATH for a bare "bash" in CreateProcess)
b=$(cd "$ROOT/scripts/lib" && python3 -B -c "import shells; print(shells.find_bash() or '')")
case "$(printf '%s' "$b" | tr 'A-Z\\' 'a-z/')" in
  "") no "shells.find_bash found no bash";;
  */windows/system32/*) no "shells.find_bash picked the WSL launcher: $b";;
  *) ok "shells.find_bash resolves a real bash ($b)";;
esac
grep -q 'run(\["bash"' "$ROOT/scripts/factory-cmd.py" "$ROOT/scripts/run-checks.py" \
  && no "factory-cmd/run-checks still launch a bare \"bash\"" || ok "factory-cmd and run-checks launch the resolved bash"

# Python entry points write UTF-8 even when the inherited stdout encoding is cp1252
# (a stand-in workspace: empty repos + root markers, so this also runs where no RPG MMO workspace exists, e.g. CI)
SW="$TMP/sw"
while IFS= read -r p; do
  git init -q "$SW/$p" && git -C "$SW/$p" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
done < <(jq -r '.repos[].path' "$ROOT/registry.json")
while IFS= read -r m; do mkdir -p "$SW/$(dirname "$m")"; touch "$SW/$m"; done < <(jq -r '.workspace.root_markers[]' "$ROOT/registry.json")
out=$(cd "$ROOT" && RPG_FACTORY_WORKSPACE="$SW" PYTHONIOENCODING=cp1252 python3 -B scripts/factory-cmd.py route client Assets/Scripts/X.cs 2>&1 | od -An -tx1 | tr -d ' \n')
case "$out" in *c2b7*) ok "factory-cmd route prints U+00B7 as UTF-8 under cp1252";;
  *) no "route output not UTF-8 (no c2b7 bytes)";; esac
for f in "$ROOT"/scripts/*.py "$ROOT"/scripts/checks/*.py "$ROOT"/scripts/lib/context.py; do
  grep -q '__main__' "$f" || continue
  grep -q '_stream.reconfigure(encoding="utf-8"' "$f" && ok "utf-8 stdio: ${f#$ROOT/}" || no "utf-8 stdio missing: ${f#$ROOT/}"
done
# subprocess output is decoded as UTF-8 (cp1252 cannot decode some UTF-8 bytes, e.g. 0x90 in U+0410)
bad=$(python3 -B - "$ROOT/scripts" <<'EOF'
import ast, glob, sys
for f in sorted(glob.glob(sys.argv[1] + "/**/*.py", recursive=True)):
    for n in ast.walk(ast.parse(open(f, encoding="utf-8").read(), f)):
        if isinstance(n, ast.Call):
            kw = {k.arg: k.value for k in n.keywords if k.arg}
            text = isinstance(kw.get("text"), ast.Constant) and kw["text"].value is True
            enc = isinstance(kw.get("encoding"), ast.Constant) and kw["encoding"].value == "utf-8"
            if text and not enc:
                print(f"{f}:{n.lineno}")
EOF
)
[ -z "$bad" ] && ok "every text=True subprocess call names encoding=utf-8" || no "subprocess without encoding: $bad"

echo "compat tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
