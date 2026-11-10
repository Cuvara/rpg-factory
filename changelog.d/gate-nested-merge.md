### Fixed

- **Pipeline: gate after a topic sync into a task branch.** A task branch that merged the topic (after the topic took a
  default-branch merge through another task) no longer makes earlier tasks' reviews STALE. Only that sync merge's own
  conflict resolutions count; the merging task's current review covers them when it owns the path and depends on the
  earlier task. A real post-review edit on the topic or in a task branch stays STALE.
