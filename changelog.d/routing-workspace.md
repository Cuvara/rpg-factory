### Fixed

- **Routing suite on Git Bash.** `tests/routing.test.sh` defaults the workspace by platform when
  `RPG_FACTORY_WORKSPACE` is unset or empty (`/c/Workspaces/UnityIndie` on Git Bash, MSYS and Cygwin,
  `/mnt/c/Workspaces/UnityIndie` elsewhere) and exports it for its `factory-context.sh` calls, so the history scenarios
  and context calls no longer fail on Windows without the variable; an explicit `RPG_FACTORY_WORKSPACE` still wins, and
  the `cli-selftest` case covers the default with a stubbed `uname`.
