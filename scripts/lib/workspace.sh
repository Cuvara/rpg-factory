# workspace.sh - source from bash scripts for the platform's default workspace path.
# The environment override wins; uname is resolved when the function is called.

rpgf_platform_path() {
  local path="$1"
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*)
      if [[ "$path" =~ ^/mnt/([a-zA-Z])(/.*)?$ ]]; then
        path="/${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
      fi ;;
  esac
  printf '%s\n' "$path"
}

rpgf_default_workspace() {
  if [ -n "${RPG_FACTORY_WORKSPACE:-}" ]; then printf '%s\n' "$RPG_FACTORY_WORKSPACE"; return; fi
  rpgf_platform_path /mnt/c/Workspaces/UnityIndie
}
