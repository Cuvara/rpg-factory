# workspace.sh - source from bash scripts for the platform's default workspace path.
# The environment override wins; uname is resolved when the function is called.

rpgf_default_workspace() {
  if [ -n "${RPG_FACTORY_WORKSPACE:-}" ]; then printf '%s\n' "$RPG_FACTORY_WORKSPACE"; return; fi
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) printf '%s\n' /c/Workspaces/UnityIndie ;;
    *) printf '%s\n' /mnt/c/Workspaces/UnityIndie ;;
  esac
}
