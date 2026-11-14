# workspace.sh - source from bash scripts for the platform's default workspace path.
# The environment override wins; uname and cygpath are resolved when the function is called.

rpgf_platform_path() {
  local path="$1" drive rest converted
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*)
      if [[ "$path" =~ ^/mnt/([a-zA-Z])(/.*)?$ ]]; then
        path="/${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
      fi ;;
    CYGWIN*)
      # Stock Cygwin mounts drives under /cygdrive: ask cygpath for the Windows form when it exists.
      if [[ "$path" =~ ^/mnt/([a-zA-Z])(/.*)?$ ]]; then
        drive="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[2]}"
        if command -v cygpath >/dev/null 2>&1 \
            && converted="$(cygpath -u "${drive}:${rest:-/}" 2>/dev/null)" && [ -n "$converted" ]; then
          path="$converted"
        else
          path="/cygdrive/${drive}${rest}"
        fi
      fi ;;
  esac
  printf '%s\n' "$path"
}

rpgf_default_workspace() {
  if [ -n "${RPG_FACTORY_WORKSPACE:-}" ]; then printf '%s\n' "$RPG_FACTORY_WORKSPACE"; return; fi
  rpgf_platform_path /mnt/c/Workspaces/UnityIndie
}
