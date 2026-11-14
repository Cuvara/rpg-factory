### Fixed

- **`tests/workspace-default.test.sh` with a drive-form `TMPDIR`.** The suite normalises its temp root to the POSIX form of the shell, so the stub directories it prepends to `PATH` no longer contain a drive-letter colon that split `PATH` (five cases failed with `TMPDIR=C:/...`).
