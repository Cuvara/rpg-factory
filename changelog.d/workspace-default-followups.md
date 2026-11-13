### Fixed

- **Workspace default.** With `RPG_FACTORY_WORKSPACE` unset, `factory-context.sh` and `fstate.workspace` convert the registry workspace default to the platform path form, allowing Git Bash for Windows to find the workspace instead of reporting "markers not found". `default_workspace` also uses the registry default when one is supplied.
