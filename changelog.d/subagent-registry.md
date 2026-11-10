### Added

- **Registry.** New `pipeline.subagents` policy: per role (run_lead, planner, lead, implement, review, qa) the subagent
  access (`none|read`), `max_parallel` and the one situation that justifies a subagent, plus the forbidden actions and
  the subagent model per agent. The default subagent model is Claude Sonnet 5.5 (`claude-sonnet-5-5`, alias `sonnet`,
  agent `rpg-factory:factory-explorer`); Codex uses `gpt-6.1-terra` at effort `medium`. `scripts/lib/subagent_policy.py`
  `rule(reg, role, agent)` turns one entry into the sentence a dispatch prompt carries.
- **Checks.** `scripts/check-registry.sh` fails when a subagent model or effort is outside `pipeline.models.scope`, or a
  Claude alias is not the `pipeline.models.agent_tool_alias` of its model. New suite `tests/subagent-policy.test.py`
  covers the rule text per role and agent, the missing block and the scope failures. The suite runs `check-registry.sh`
  through the Git Bash resolver (`scripts/lib/shells.py`), so it also runs on Windows.
