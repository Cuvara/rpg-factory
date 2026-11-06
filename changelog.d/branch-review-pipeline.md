### Fixed

- **Pipeline: Unity aliases.** `status` and `dispatch` serialize no-worktree tasks by checkout, as `validate` does: two
  plan repo keys that name one Unity checkout are never both ready, the second task waits for the first one's QA, and
  per-task QA counts every alias of the checkout (also in the gate). `status` offers a no-worktree checkout's
  integration QA only after every task of the checkout, under any alias, passed per-task QA, and runs the aliases'
  integration QAs one at a time, so no QA session runs beside a task lead in one Unity checkout. The gate counts
  every alias's owned paths on the shared integration branch, so their changes are not stray.
- **Pipeline: dependent tasks with shared paths.** `status` counts only a task's own commits: a task branch cut from the
  integration branch starts at its fork point (no own commits while it is still on the topic's first-parent chain),
  and a no-worktree task starts after its serial predecessor's last verdict (before that verdict it has not started).
  A dependent task that owns an earlier task's paths is no longer a review candidate before its first commit, in a
  worktree repo and in a no-worktree (Unity) repo.
- **Pipeline: child names.** Review and QA children are named `<parent>--[<subtask>--]<phase>-<sha7>`, so the review
  and the QA of one candidate, or a subtask whose implement child still exists, never collide in Orca. A child
  command also says on stderr to run it from the parent worktree (integration QA included).
- **Pipeline: one id rule.** Task and subtask ids follow the schemas' pattern `^[A-Za-z0-9][A-Za-z0-9_.-]*$` in
  `validate`, `subplan validate`, `dispatch` and `verdict`; `subplan validate` rejects unknown subplan and subtask keys,
  and `validate` rejects a task id `integration_<repo>` (it would share the integration QA's verdict file).
- **Pipeline: case on Windows.** The gate's and `status`'s git pathspecs for owned paths are case-insensitive on
  Windows, matching the owned-path check, so a plan path in another case no longer hides a stale review.
- **Pipeline: Agent fallback for a child.** `--runner agent` with child placement uses the Agent tool's
  `isolation: worktree` and never tells the session to run `git worktree add`.
