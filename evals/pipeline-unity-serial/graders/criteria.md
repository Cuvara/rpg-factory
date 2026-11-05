---
type: llm
weight: 2
---

A successful response:
- Splits the work into tasks with disjoint owned paths (the server RPC, the party list panel, the invite popup).
- Creates no worktree of IndieRPGMMOAdventure (a Unity project): its two tasks run one after another in the main
  checkout, each with review and QA before the next starts. The server task may get its own worktree and run in
  parallel with the client tasks.
- Has each task's code reviewed by the other model (Claude's code by Codex, Codex's by Claude) on a fixed commit.
- Runs Unity tests one at a time.
- Opens the PR only after the gate is READY_FOR_PR (all reviews and QA PASS, checks PASS), and leaves the merge to
  the user.
