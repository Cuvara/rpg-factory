### Fixed

- **Pipeline start base.** A task whose dependencies are all merged into the topic (a dependency branch already on the
  topic counts as settled even when its phase still reads candidate or reviewed) starts from the topic, not from that
  dependency's old branch tip, and `dispatch --phase lead` writes no `<task>__stack.json`. A task branch cut from the
  topic ahead of the plan base now uses the topic as its review base and own start, so the tier command and the review
  select only the task's own delta instead of every suite. A stack record whose dependency was integrated before the
  task branch was cut is ignored by `status`, verify/review/qa dispatch and the gate (no `stacked on` note, no
  `integrated before its dependency` blocker). Stacking on one in-flight dependency is unchanged.
