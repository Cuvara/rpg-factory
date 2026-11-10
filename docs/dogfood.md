# Dogfood: real-session runs and how to read their failures

`tests/dogfood.sh` (Claude Code) and `tests/dogfood-codex.sh` (Codex CLI) run real headless sessions and grade
their transcripts. They spend tokens, are not part of `tests/run-all.sh`, and a release runs
`tests/dogfood.sh --installed` on the release commit (`docs/releasing.md`).

## Nondeterministic failures are normal; report them honestly

A `tests/dogfood.sh --all` run (read-only and write scenarios) usually has 1-3 failures that pass on retry. Seen
in 1.3-1.5:

- a session skipped loading a lead skill;
- an answer did not quote the expected command output;
- an empty transcript: the session never started.

The same runs also found real defects: grader false positives, `--all` masking a failed scenario's exit code, and
sessions reading `SKILL.md` instead of invoking the skill (now a guard advisory). So a failure is never waved off
unread.

For every failing scenario:

1. Read its transcript (`$DOGFOOD_OUT/<scenario>.jsonl`; default `/tmp/rpgf-dogfood`, Codex
   `/tmp/rpgf-dogfood-codex`).
2. Classify the cause: **grader** (the session did the right thing, the check misread it), **plugin** (a skill,
   hook or script led the session wrong) or **model** (correct inputs, the model varied).
3. Fix grader and plugin causes in the same task, with a test (synthetic transcripts: `--grade-two-level`,
   `tests/dogfood-codex.sh --dry-run`).
4. Re-run model-only failures. Before calling a failure that repeats "model", check the grader against the
   transcript again.
5. Report the first-run failures, their classification and the retry results. A retry PASS does not erase the
   first-run failure from the report.

## Known traps

- **Claude Code resets the shell cwd.** After a `cd` outside the project directory, Claude Code prints "Shell cwd
  was reset" and the next command runs in the project again. A write grader that assumed the session stayed in
  the scratch workspace reported a repeatable false positive (fixed in PR #70). Graders check absolute paths, not
  the session's cwd.
- **Custom Codex model provider.** `~/.codex/config.toml` may route `model` through a custom `model_provider`.
  That provider is not copied into the throwaway `CODEX_HOME`, so the session fails to start;
  `tests/dogfood-codex.sh` therefore skips copying such a model and uses Codex's default unless `--model` is given.
- **Load.** Do not run dogfood next to more than one full `tests/run-all.sh` (`.claude/CLAUDE.md` "Operating
  lessons"): slow sessions hit timeouts that look like model failures.
