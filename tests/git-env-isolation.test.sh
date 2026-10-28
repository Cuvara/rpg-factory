#!/usr/bin/env bash
# M4/P0: a test run must never write the SHARED git config of the repository it runs in.
# Root cause (reproduced): a git process that runs a command (`git rebase --exec tests/run-all.sh`, `git bisect run`, a
# hook) exports GIT_DIR (sometimes GIT_WORK_TREE). The fixtures then ran `git init <tmpdir>`, which with GIT_DIR set
# re-initialises the CALLER's repository, and from a linked worktree that rewrites the main checkout's shared config
# (core.worktree = the worktree path, or core.bare = true). Here: (1) with GIT_DIR/GIT_WORK_TREE exported by a caller,
# sourcing compat.sh gives fixtures a clean git environment; (2) the run-all self-check (gitcfg-guard.sh) detects a
# changed shared config. Throwaway repos only.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/scripts/lib/compat.sh"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -10 | sed 's/^/      /'; }
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
hash_of() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi; }

M="$TMP/main"; W="$TMP/wt"
git init -q -b main "$M"; gc "$M" commit -q --allow-empty -m init; gc "$M" worktree add -q "$W" -b feat/x
CFG="$M/.git/config"; before=$(hash_of "$CFG")

# (1) the caller exports the worktree's git dir and work tree; a fresh shell that sources compat.sh runs a fixture `git init`
GD=$(git -C "$W" rev-parse --path-format=absolute --git-dir)
out=$(cd "$W" && env GIT_DIR="$GD" GIT_WORK_TREE="$W" bash -c '. "$1/scripts/lib/compat.sh"; git init -q "$2/fixture" && git -C "$2/fixture" rev-parse --git-dir' _ "$ROOT" "$TMP" 2>&1); rc=$?
after=$(hash_of "$CFG")
[ "$before" = "$after" ] && ok "fixture git init under inherited GIT_DIR/GIT_WORK_TREE leaves the shared config untouched" \
  || no "shared config rewritten by a fixture git init (core.worktree / core.bare)" "$(git config -f "$CFG" --list | grep -E 'worktree|bare')"
[ $rc -eq 0 ] && [ -d "$TMP/fixture/.git" ] && ok "the fixture repository is created where it was asked for" || no "fixture repository missing (rc=$rc)" "$out"
[ -z "$(git config -f "$CFG" --get core.worktree)" ] && [ "$(git config -f "$CFG" --get core.bare)" = false ] \
  && ok "main checkout config has no core.worktree and core.bare=false" || no "main checkout config damaged"

# (2) the run-all self-check
. "$ROOT/scripts/lib/gitcfg-guard.sh"
gitcfg_snapshot "$W"
gitcfg_verify >/dev/null && ok "guard: unchanged shared config passes" || no "guard: unchanged shared config reported as changed"
git config -f "$CFG" core.worktree "/mnt/c/somewhere/else"
msg=$(gitcfg_verify); rc=$?
[ $rc -ne 0 ] && grep -q "changed during the run" <<<"$msg" && ok "guard: a rewritten shared config (core.worktree) fails with a message" || no "guard missed a changed shared config (rc=$rc)" "$msg"
gitcfg_snapshot "$W"; git config -f "$CFG" --unset core.worktree; gitcfg_verify >/dev/null; rc=$?
[ $rc -ne 0 ] && ok "guard: a second change is caught against the new snapshot" || no "guard: second change not caught"
gitcfg_snapshot "$TMP"       # not a repository: nothing recorded, nothing to fail
gitcfg_verify >/dev/null && ok "guard: outside a repository it records nothing and passes" || no "guard: outside a repository it failed"

echo "git-env-isolation: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
