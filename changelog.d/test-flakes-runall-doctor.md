### Fixed

- **run-all.** The test slot takeover message now goes to stderr instead of stdout, so it no longer mixes with run-all's progress output.
- **netcode-headless.** The evidence prune now orders directories created in the same second by the full timestamp and then numerically by pid, instead of lexicographically on the pid part.

### Added

- **doctor.** `doctor` names the two machine-setup faults that made task QA report NOT_RUN on Windows: `python3` in Git Bash resolving to the Microsoft Store stub (WindowsApps) and a missing `jq`, each with a fix hint (a PATH shim).
- **scripts/README.md.** Lists `tests/assetgen.test.sh` with its `--case` groups (`--list-cases`) and names the two conventions a new check must meet: the UTF-8 stdio block (`tests/compat.test.sh`) and the workspace reader guard (`tests/workspace-default.test.sh`).
