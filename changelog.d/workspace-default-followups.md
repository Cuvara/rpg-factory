### Fixed

- **Workspace default.** With `RPG_FACTORY_WORKSPACE` unset, `factory-context.sh` and `fstate.workspace` convert the registry workspace default to the platform path form, allowing Git Bash for Windows to find the workspace instead of reporting "markers not found". `default_workspace` also uses the registry default when one is supplied. `check-registry.sh`, `netcode-headless.sh` and the remaining shell and Python readers (`pin-plan.py`, `pin-status.py`, `skill-citations.py`, `factory-cmd.py`) also use the platform form, and a test detects scripts that hard-code the WSL-form default.
