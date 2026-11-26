### Fixed

- **Delivery pipeline: `nudge` judges an implement spec by its own subtask's progress (#152).** A terminal whose start
  prompt names an implement spec (`<task>-implement-<digest>.md`) is no longer cleared by task-level progress (a commit
  on the task branch, the lead report, task or sibling verdicts): only a verdict or a subtask-branch commit of the
  subtask whose implementer record names that spec counts, so an idle implementer is reported STUCK although a sibling
  subtask was committed after its spec was written. Lead and verify specs keep the task-level rule.
