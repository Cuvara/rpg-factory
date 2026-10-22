---
name: skill-author
description: Add, split or rename a Factory skill in this plugin repo (rpg-factory) - a lead (repo/cross-repo) or a tech skill - from the learning-loop gate through scaffold, cited content, touchpoints, routing and dogfood scenarios to a green run-all. Use when the task is "add a skill for X", "split skill Y", "rename skill Z" or "teach Factory about technology T". Not for changing what an existing skill says about the product repos (edit it and run the citation check), not for product code (factory-core), and not for registry module or contract work without a new skill.
---

# Skill author (rpg-factory repo)

Repo-local workflow for this plugin's own skills. The rules are in `.claude/CLAUDE.md` and
`skills/factory-core/references/skill-contract.md`; this skill is the order of work and the tools.

## 1. Gate: does this deserve a skill?

- Knowledge enters only from a verified failure or a real recurring task (skill-contract "Learning loop").
  One place: a product-repo test, a cited Pitfall in an existing skill, a `known_issues` entry or a
  `facts[]` probe. A new skill only when no existing skill can own it without breaking its size limit
  (SKILL.md <= 160 lines, <= 3 references).
- Lead or tech: a lead owns modules/contracts and decides scope, rules, checks, gates; a tech skill owns
  nothing and explains how a technology behaves for the leads in its `used_by`.
- Ask the user before inventing ownership: which modules or contracts move to a new lead is their call.

## 2. Scaffold

```bash
python3 -B scripts/new-skill.py --name <name> --kind tech|repo|cross-repo --repos <keys> \
  --summary "<one line>" [--used-by <leads>] [--owns-modules <ids>] [--drives-contract <ids>] \
  [--tools <dev_tools ids>] [--cite-root "<prefix>=<repo>:<subpath>"] [--dry-run]
```

It writes `skills/<name>/SKILL.md` (every section skills-lint requires, `SCAFFOLD:` markers) and the
registry entry (next free `order`, ownership, `dev_tools.used_by`); it refuses on anything it cannot
validate and never reformats `registry.json`.

## 3. Write the content

- Replace every `SCAFFOLD:` (skills-lint fails while one is left). The description is semantic: the
  developer situation it applies to and what it is not for, with "Use when" and "Not".
- Every claim about the product repos cites the file that shows it. Line citations name their symbol:
  `` `TickOnce` (`GameServer/Server/TickLoop.cs:510`) ``; docs are cited by section. Check them against
  the integration branches:
  `python3 -B scripts/checks/skill-citations.py --skill <name> --suggest`.
- Version-like values go to registry `facts[]` with a probe, never into prose (`tests/facts.test.sh`).
- Tech skill: each lead in `used_by` names `rpg-factory:<name>` at the step that needs it.

## 4. Touchpoints

`python3 -B scripts/skill-touchpoints.py <name>` lists every other place to update: factory-core
"Skills" (table row or tech list), the skill-contract diagram, README diagram and tables, `.claude/CLAUDE.md`
"Skills:" (names and counts), `plugin.json`/`marketplace.json` lead count, a routing scenario
(`$(lead <name>)` / `$(tech <name>)` in `tests/routing.test.sh`), a dogfood scenario (`tests/dogfood.sh`
`EXPECT`), and an eval with `graders/<name>-fired.md` (`evals/`). Repeat until it prints OK.

## 5. Validate and report

- `tests/skills-lint.sh`, `scripts/check-registry.sh`, `tests/routing.test.sh`, then `tests/run-all.sh`
  (0 failed, report the count); `tests/dogfood.sh --installed <scenario>` for the new scenario (spends
  tokens - say so).
- CHANGELOG `[Unreleased]` entry; branch `feat/skills/<name>`; commit, push and PR only on request.
