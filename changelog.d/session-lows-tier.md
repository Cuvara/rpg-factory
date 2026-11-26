### Changed

- **Pipeline.** The plain `tier -- <factory-context.sh args>` and `--context-json` forms measure changed lines too,
  against the same `pipeline.tiers.XS` `max_changed_lines` as `tier --plan` and the gate (they used to count files
  only). With a checkout they count `git diff --numstat` over the snapshot's files plus the lines of untracked ones,
  against the merge-base with `HEAD` of the repo's `branch_diff_base` (the branch scan), else of the `--base` of the
  args (so `tier -- --repo <key> --paths <files> --base <b>` counts the committed lines since `<b>`), else against
  `HEAD`. The output names what was measured: `changed lines: <n> (<basis>)` or
  `changed lines: not measured (no checkout)`; `--json` carries `lines_basis`, and `changed_lines` only when something
  was measured (`tier --plan` without a checkout no longer reports 0).
- **Pipeline.** The base health hint of `dispatch --phase lead` (`gh run list --branch <base> --limit 1`, print only)
  is also written into the lead spec as a `Base health:` line, so the task lead sees it, not only the run lead; the
  stderr line is unchanged.

### Fixed

- **Docs.** Correction to the released 1.8.0 entry "Pipeline known failures": besides the task-lead, task QA and
  integration QA specs, the verify spec that `dispatch --phase verify` writes also carries the plan's `known_failing`
  list with the `FAIL_AT_BASE` rule. `docs/pipeline-cli.md` now documents the `nudge` options `--stall SECONDS`
  (default 900) and `--orca-run RUN_ID` with the STALLED worker rows, and the `status` line
  `Slots: LEFT BY VERIFY ...` (a released worker counts by `releaseCompletedAt`, else `releaseRequestedAt`).
