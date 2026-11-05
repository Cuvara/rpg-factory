### Fixed

- **Pipeline test on Linux.** `tests/pipeline.test.sh` expected the Orca `--worktree path:...` argument quoted; `shlex.quote`
  leaves a POSIX path unquoted, so main CI failed on ubuntu after PR #75. The two dispatch cases accept both forms.
