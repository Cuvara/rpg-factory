### Fixed

- **Guard: path-only `git reset` (#155).** A reset that only updates the index (`git reset -q <file>`,
  `git reset -- <paths>`, `git reset HEAD -- <file>`, `git reset -p <file>`) no longer gets the "moves protected
  branch" advisory. Words after `--` are paths; a word before it counts as a revision only when it looks like one (a ref,
  a hex SHA, or anything with `~ ^ @ :`) and is not an existing path. `git reset HEAD~1`, `git reset origin/main`,
  `git reset --soft HEAD~2` and `git reset --mixed <sha>` are still flagged.
- **Guard: quoted heredoc data (#158).** Kill commands named inside a quoted heredoc (`<<'EOF'`, `<<"EOF"`) fed to a
  reader that does not run it (`cat > f`, `tee f`, `gh ... --body-file -`) no longer get the process-termination
  advisory: the shell never expands that body. An unquoted heredoc's `$(...)` and backticks, and a heredoc fed to a
  shell, are still checked.
- **Guard: own-PID exemption (#158).** `export`, `declare`, `local`, `typeset` and `readonly` rebinding the PID variable
  to a non-own value now void the exemption; `foreach Kill` (the `ForEach-Object` alias) is flagged like
  `ForEach-Object Kill`; `kill -- $pid` and `$p.Kill()` on a `Start-Process -PassThru` result count as own-PID kills.
  A rebinding inside a nested `bash -c` is not tracked.
