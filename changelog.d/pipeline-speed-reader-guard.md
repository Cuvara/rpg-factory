### Changed

- **QA.** The workspace reader guard (jq readers map the registry default workspace on the same line, Python readers use the shared helper) is now the read-only check `scripts/checks/workspace-readers.sh [ROOT]`, a run-all guard line that `--within` task QA also runs when the change reaches it. The `tests/workspace-default.test.sh` self-test calls the script and asserts its exit codes.
