# compat.sh - source from bash scripts (tests and check-registry.sh). Makes them run the same on Linux, WSL
# and Windows git-bash (MSYS/MINGW). Needs `set -o pipefail` in the caller so jq's exit status survives.

case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) RPGF_WINDOWS=1 ;;
  *) RPGF_WINDOWS= ;;
esac

# jq on Windows writes CRLF; `$(jq -r ...)` word splitting keeps the \r (`skills/foo\r/SKILL.md` does not exist).
if [ -n "$RPGF_WINDOWS" ]; then jq() { command jq "$@" | tr -d '\r'; }; fi

# mktemp_win: a temp dir in a form native Windows programs (python, git) resolve too (C:/Users/...), not MSYS /tmp.
mktemp_win() {
  local d; d="$(mktemp -d -p /tmp)" || return 1
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$d"; else printf '%s\n' "$d"; fi
}

# path_entry DIR: DIR as a $PATH entry. `C:/x` holds a colon and splits $PATH; git-bash needs `/c/x` there.
path_entry() { if [ -n "$RPGF_WINDOWS" ]; then cygpath -u "$1"; else printf '%s\n' "$1"; fi; }

# is_abs PATH: absolute on this platform (`/x`, or `C:/x` / `C:\x` on Windows).
is_abs() {
  case "$1" in /*) return 0 ;; esac
  [ -n "$RPGF_WINDOWS" ] && [[ "$1" =~ ^[A-Za-z]:[/\\] ]]
}

# fwd PATH: backslashes to forward slashes, to compare a path Python printed natively with a bash path.
fwd() { local bs='\'; printf '%s' "${1//"$bs"//}"; }

# dir_readonly DIR / dir_writable DIR: chmod has no effect on NTFS; deny create/delete with an ACL there.
dir_readonly() {
  if [ -n "$RPGF_WINDOWS" ]; then MSYS2_ARG_CONV_EXCL='*' icacls "$(cygpath -w "$1")" /deny "$USERNAME:(OI)(CI)(WD,AD,DC,DE)" >/dev/null
  else chmod 555 "$1"; fi
}
dir_writable() {
  if [ -n "$RPGF_WINDOWS" ]; then MSYS2_ARG_CONV_EXCL='*' icacls "$(cygpath -w "$1")" /remove:d "$USERNAME" /t >/dev/null
  else chmod 755 "$1"; fi
}
