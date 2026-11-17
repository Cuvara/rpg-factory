### Fixed

- **Netcode headless check.** `scripts/checks/netcode-headless.sh` keeps the `.trx` files and the dotnet log of a failed
  run under the Factory state dir (`evidence/netcode-headless/...`) and prints the path, so the cause of a one-off
  failure is no longer lost with the work copy; a pass still cleans up.
- **Plan repo paths.** Only a leading `/mnt/<letter>/` (or its Git Bash rewrite under the Git install root) is read as
  a WSL drive mount; a native path that merely contains a `/mnt/<letter>/` segment is kept.
