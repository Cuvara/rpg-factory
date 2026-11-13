### Fixed

- **Pipeline.** `factory-pipeline.py dispatch --phase lead` took the Orca parent of a task worktree from the checkout
  that holds `plan.topic` and silently fell back to the main checkout when no checkout had it, so a task worktree could
  land under the main checkout instead of the run lead's worktree. It now prints a stderr hint in that case (the parent
  falls back to the main checkout; set `plan.topic` to the run lead's integration branch or check it out before
  dispatching). The printed commands are unchanged.
