# gitcfg-guard.sh - source from a test runner. Detects a run that rewrote the SHARED git config of the repository it
# runs in (the common dir's `config`, which a linked worktree shares with the main checkout).
#   gitcfg_snapshot [DIR]   record the hash of DIR's shared config (default: the current directory); sets GITCFG_FILE/GITCFG_HASH
#   gitcfg_verify           0 when the hash is unchanged (or nothing was recorded), 1 when the config changed or vanished;
#                           prints what changed to stdout
# It only reads; it never repairs the config.

_gitcfg_hash() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi; }

gitcfg_snapshot() {
  local d="${1:-.}" common
  GITCFG_FILE=""; GITCFG_HASH=""
  common=$(git -C "$d" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 0
  [ -f "$common/config" ] || return 0
  GITCFG_FILE="$common/config"
  GITCFG_HASH=$(_gitcfg_hash "$GITCFG_FILE")
  GITCFG_COPY=$(mktemp 2>/dev/null) && cp "$GITCFG_FILE" "$GITCFG_COPY" 2>/dev/null || GITCFG_COPY=""
}

gitcfg_verify() {
  [ -n "${GITCFG_FILE:-}" ] || return 0
  if [ ! -f "$GITCFG_FILE" ]; then echo "shared git config $GITCFG_FILE is gone"; return 1; fi
  local now; now=$(_gitcfg_hash "$GITCFG_FILE")
  [ "$now" = "$GITCFG_HASH" ] && { [ -n "${GITCFG_COPY:-}" ] && rm -f "$GITCFG_COPY"; return 0; }
  echo "shared git config $GITCFG_FILE changed during the run (sha256 $GITCFG_HASH -> $now)"
  [ -n "${GITCFG_COPY:-}" ] && diff "$GITCFG_COPY" "$GITCFG_FILE" 2>/dev/null | head -10 | sed 's/^/  /' && echo "  (copy from before the run: $GITCFG_COPY)"
  return 1
}
