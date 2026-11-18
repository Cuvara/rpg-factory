### Fixed

- **Workspace path rewrite.** `native_abs` (`scripts/lib/workspace.py`) undoes git-bash's MSYS rewrite of a WSL mount
  (`<prefix>/mnt/<letter>/...`) only when the prefix is a Git for Windows install root, for every caller
  (`context.py`, `run-checks.py`, plan paths) instead of only plan paths. The install-root check needs
  `usr/bin/bash.exe` or `git-bash.exe`, so a user directory merely named `Git` is no longer taken for one.
- **Git timeout in the snapshot.** `factory-context.sh` reports a product repo whose `git` call timed out as
  `git timed out after <N> s` instead of "not a git work tree"; a real failure keeps the old message. `workspace.git_out`
  still returns `""` for existing callers, and the new `workspace.git_result` tells a timeout from a failure.
