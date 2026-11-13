### Fixed

- **Workspace default.** When `RPG_FACTORY_WORKSPACE` is unset, the workspace defaults to `/c/Workspaces/UnityIndie` on Git Bash, MSYS and Cygwin and `/mnt/c/Workspaces/UnityIndie` elsewhere, using shared helpers `scripts/lib/workspace.sh` (`rpgf_default_workspace`) and `scripts/lib/workspace.py` (`default_workspace`), including in `routing.test.sh` and `run-all.sh`. Previously run-all's live checks defaulted to the WSL form, which fails on Git Bash for Windows.
