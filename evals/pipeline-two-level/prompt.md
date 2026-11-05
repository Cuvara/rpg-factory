---
runs: 1
max_turns: 30
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
tags: [pipeline, parallel-work, plugin]
---

In the current rpg-factory plugin checkout, add a `help --verb <name>` filter to
`scripts/factory-cmd.py` that prints only the named verb and rejects unknown names. Document
the option in the Commands section of `skills/factory-core/SKILL.md`, and cover both cases
in `tests/commands.test.sh`. Include the required changelog fragment. Implement this through
the repository's normal development workflow; do not commit, merge, push, or publish anything
from this session.

This is a disposable plugin checkout with the rpg-factory plugin loaded. Shell commands and
file editing are available. Start the work and report the stage you reached with the commands
you actually ran; do not claim implementation, review, or QA that did not happen.
