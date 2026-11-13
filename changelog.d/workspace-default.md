### Fixed

- **Workspace default.** Added shared shell and Python workspace default helpers, and used the shell helper in `tests/routing.test.sh` and the live checks in `tests/run-all.sh`. When `RPG_FACTORY_WORKSPACE` is unset, the shell helper uses `/c/Workspaces/UnityIndie` on Git Bash, MSYS and Cygwin and `/mnt/c/Workspaces/UnityIndie` elsewhere; the Python helper uses the native path form. Previously run-all's live checks used the WSL form, which fails on Git Bash for Windows.
