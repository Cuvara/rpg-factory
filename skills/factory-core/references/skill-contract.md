# Skill contract - building on Factory Core

Future rpg-factory skills (feature, fix, refactor, test, review, build, release, and
domain workflows like "bump netcode") **specialise** the Factory workflow. They do not
replace it.

## What every skill gets for free

| Need | Source | Do not |
|---|---|---|
| Repo, branch, dirty state, baseline | `factory-context.sh` snapshot | run your own ad-hoc git survey |
| Affected modules and dependents | `factory-context.sh --repo R --paths ...` | hand-map paths to modules |
| Module rules, docs, changelog, generated paths | `registry.json` | hard-code module knowledge in SKILL.md |
| Checks by tier + evidence format | `registry.json` via the snapshot | invent validation commands |
| Git safety | `references/git-safety.md` + hook | re-implement guards |
| Report format | `references/report.md` | invent a new report shape |

## How a skill depends on Core

1. **Skill** (`skills/<name>/SKILL.md` in this plugin). Begin the body with:

   > Follow `rpg-factory:factory-core` (invoke it first if it is not already loaded this
   > task). This skill owns steps <n..m>; all other steps are Core's.

   Add a live snapshot line if the skill needs it immediately:
   `` !`bash "${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh" --repo server 2>&1` ``
2. **Agent** (`agents/<name>.md`). Preload Core with `skills: [factory-core]` in the
   frontmatter and scope the agent to one repo in its description (see the rpg-team
   convention: one teammate per repo).

## What a skill must declare (at the top of its SKILL.md)

- **Task types** it handles (feature, fix, release, ...).
- **Scope**: repos/modules it may change. Anything else is out of scope and needs asking.
- **Owned steps**: which workflow steps it specialises (for example "Implement" and
  "Validate: extended"), and what it adds (extra checks, extra obligations).
- **Human gates** it adds beyond Core's.

## Extending knowledge without touching Core logic

- **New module or new path** -> add an entry to `registry.json` `modules`. The schema is
  open: unknown keys are ignored by Core, so a skill may add its own keys
  (`"release": {...}`) and read them with `jq`.
- **New check** -> add it to the module's `checks.<tier>`. Placeholders: `{dotnet}`,
  `{plugin_root}`. Put helper scripts in `scripts/checks/`.
- **New repo** (for example Netcode/UIToolkit/UnityDots) -> add `repos.<key>` plus modules.
  The context script and hook pick it up automatically.
- Run `scripts/check-registry.sh` and `tests/run-all.sh` after every registry change.

Change `factory-context.sh`, `resolve.jq`, the hook, or this contract only when a need is
common to several skills. Record the reason in `CHANGELOG.md`.

## Coexistence

- Unity MCP tool skills and the `verify-a-result` skill live in the client repo's
  `.claude/skills/` and remain there. Factory skills call them instead of duplicating them.
- The client `.claude/agents/unity-netcode.md` owns the client networking layer. Factory
  skills hand networking work to it.
- `game-ai-workflows` (user-level plugin: GDD, feature registry) is independent. Factory
  Core neither reads nor writes its state.
- Built-in `/code-review` is the review step. Do not add a parallel reviewer to Core.
