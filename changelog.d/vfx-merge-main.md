### Fixed

- `tests/assetgen.test.sh` runs on Windows again: the `AG` client strips the carriage return from the exit code that
  `tests/fixtures/assetgen/agserver.py` writes in text mode, so `return "$rc"` no longer fails with "numeric argument
  required" and every server-served case gets its real exit code.
