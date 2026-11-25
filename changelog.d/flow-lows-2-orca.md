### Fixed

- `factory-pipeline.py dispatch --phase lead` no longer prints an `orca worktree set` that runs before Orca knows the new
  task worktree (it then set nothing): the set is chained after the new read-only verb
  `factory-pipeline.py orca-wait --worktree <path>`, which polls `orca worktree list --json` until the worktree is listed
  (`--timeout`, default 60 s; `--interval`, default 2 s). When it never appears, orca-wait exits 1 and says the worktree
  stays hidden in Orca: retry, or run `orca worktree set` by hand once `orca worktree list` shows the path.
- `factory-pipeline.py cleanup` no longer deletes a branch before its worktree record is gone: `orca worktree rm`
  removes asynchronously, so a `git branch -d` right after it failed with 'used by worktree'. Before a repo's first
  `git branch -d` it now prints one `orca-wait --gone --worktree <path>` per path it removes through `orca worktree rm`
  (merged children and leftover directories or records), and the child and leftover notes say the branch is deleted
  only once the worktree record is gone.
- `factory-pipeline.py status` and `cleanup` count a concise `worker-list` row (Orca without `--full`) whose
  `terminalState` is `released` as released even without a `state`, instead of naming it in the "settledness not
  checked" note.
