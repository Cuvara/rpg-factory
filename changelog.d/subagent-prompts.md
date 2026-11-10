### Added

- **Pipeline.** Every session prompt `scripts/factory-pipeline.py` prints now carries one line with its role's subagent
  rule, read from the registry `pipeline.subagents` through `scripts/lib/subagent_policy.py` `rule(reg, role, agent)`:
  the planner, the task lead (a new rule 7; the push rule is now rule 8), implementation sessions (shared and child),
  review (the reviewer's own model, the verdict stays the reviewer's) and task and integration QA (no subagents). The
  rule names the agent that actually runs the session: with `--runner agent` that is Claude, so a Codex review turned
  into a Claude SAME_MODEL review names Claude's Sonnet alias. A registry without `pipeline.subagents` exits 1 with
  nothing dispatched.
