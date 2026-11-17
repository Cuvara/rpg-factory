### Changed

- **Guards.** The english-only advisory now covers every rpg-factory checkout and each of its linked worktrees,
  wherever they lie on disk: the git guard (commit, gh, orca text and the Agent tool prompt, also `git -C <checkout>`
  from an unrelated directory) and the file guard share one checkout detector (`workspace.plugin_checkout`, no git
  call). The file guard no longer treats another plugin's checkout as governed; unrelated directories still get no
  opinion.
