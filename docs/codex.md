# rpg-factory on Codex CLI

rpg-factory ships one checkout for two agent runtimes. Claude Code reads `.claude-plugin/`; Codex CLI reads
`.codex-plugin/plugin.json` and the repo-local Codex marketplace `.agents/plugins/marketplace.json`. Both manifests
point at the same `./skills/` directory, so the skill set is identical (`tests/codex-plugin.test.sh` checks it).

## Files

| File | Runtime | Purpose |
|---|---|---|
| `.codex-plugin/plugin.json` | Codex | name `rpg-factory`, version == `VERSION`, `"skills": "./skills/"`, `"hooks": "./hooks/codex-hooks.json"`; no `commands` (Codex skips the Factory command templates) |
| `hooks/codex-hooks.json` | Codex | SessionStart and PreToolUse (`Bash`, `apply_patch`) commands running `scripts/codex_hook.py`, each ending with `; exit 0` |
| `.agents/plugins/marketplace.json` | Codex | marketplace `rpg-factory` with one plugin `rpg-factory`, local source (this checkout) |
| `scripts/codex_hook.py` | Codex | hook adapter: `session-start` and `pre-tool-use`; reads Codex hook JSON on stdin |
| `tests/fixtures/codex-hooks/` | tests | `<event>-<case>.json` hook inputs; `README.md` lists the expected advisory level (none, warn, high) |

## Commands

Codex skips the Factory command templates, so it reaches every command through the script behind them, run from the
installed plugin root (the directory that holds `skills/`). `python3 -B <plugin root>/scripts/factory-cmd.py help --json`
(schema `rpg-factory.commands/1`) lists each verb with its arguments, read-only flag, an example and both forms;
`--json` makes the output machine-readable (`domain`: `rpg-factory.domain/1`). Exit 2 is a usage error.

| Verb | Claude Code | Codex / shell (`python3 -B <plugin root>/scripts/factory-cmd.py ...`) | Read-only |
|---|---|---|---|
| status | `/rpg-factory:status [--remote] [--json]` | `status [--remote] [--json]` | yes |
| route | `/rpg-factory:route ...` | `route (--domain <id> \| --kind <kind>) \| <repo> <path>... [--lead <skill>] [--json]` | yes |
| check | `/rpg-factory:check ...` | `check <repo> [<path>...] [--status] [--json]` | only with `--status` |
| doctor | `/rpg-factory:doctor [--json]` | `doctor [--json]` | yes |
| domain | `/rpg-factory:domain [<id>] [--json]` | `domain [<id>] [--json]` | yes |
| workflow | `/rpg-factory:workflow ...` | `workflow plan\|status\|dispatch\|report <spec> [--json]` | yes |
| pipeline | `/rpg-factory:pipeline ...` | `pipeline tier\|validate\|planner\|dispatch\|verdict\|gate\|cleanup [args]` | no (`verdict`, `cleanup` record state) |
| ui, ui-figma, ui-components, ui-screen, ui-review | `/rpg-factory:ui <request>` ... | `ui [--json] [--project <dir>] [--uitoolkit-ref <ref>] <request>` | yes |
| assetgen | `/rpg-factory:assetgen ...` | `assetgen list\|show\|resolve\|lint\|review-cmd\|drift [args]` | yes (`render`, `qa`, `manifest`, `promote-anchor`, `reject` are refused: the asset-gen skill runs them) |
| help | none | `help [--json]` | yes |

## Delivery in any project

The `delivery` skill (`skills/delivery/SKILL.md`) is the generic multi-step flow: two levels, agent routing, cross-model
review, QA tiers and the plan, verdict and gate pipeline. Codex loads it like every other skill: it reads
`skills/delivery/SKILL.md` from the installed plugin root (the directory that holds `skills/`) and runs
`python3 -B <plugin root>/scripts/factory-pipeline.py <verb> --registry none` where no RPG registry applies. Inside the
workspace, factory-core calls it. To make Codex load it in any repository, put one line in `~/.codex/AGENTS.md`
(the line is in the README, "Delivery in any project"). The hook adapter and its advisories stay RPG-only: they
never act on a repository outside the workspace.

## Hook adapter contract

The adapter follows the same rules as the Claude hooks (`.claude/CLAUDE.md`, "Rules for changing this repo"):

- `python3 -B scripts/codex_hook.py <session-start|pre-tool-use>` exits 0 on every input: empty, malformed, huge or
  binary stdin, an unknown event, no event argument.
- stdout is empty or exactly one JSON object; advisories are `rpg-factory advisory (high|warn): ...` context.
- Never a `permissionDecision`, never `"decision": "block"` or `"deny"`, never `"continue": false`, never a traceback.
- It does not depend on any `CLAUDE_*` variable and resolves the plugin root itself (any cwd).
- Every Codex hook command runs an existing script and ends with `; exit 0`.

`tests/codex-plugin.test.sh` checks all of this (run-all runs it), plus the hook wiring (SessionStart and PreToolUse
for both `Bash` and `apply_patch` reach the adapter). A missing Codex file fails.

Codex reports every shell as `Bash`, but on Windows it runs the command with PowerShell (`powershell.exe -Command`).
The adapter therefore parses it as PowerShell there (Bash elsewhere), so native `C:\` paths and backtick escapes
reach the guard and a backtick-escaped `;` is not taken for a separator. Runtime
detection (`scripts/lib/pluginroot.py` `is_codex()`) uses `CODEX_THREAD_ID` or `PLUGIN_ROOT` and is always false
under Claude Code (`CLAUDECODE`): a Claude session that inherits `CODEX_HOME` keeps the Claude install check.

## Versions

A release bumps `.codex-plugin/plugin.json` together with `VERSION`, `.claude-plugin/plugin.json`, the Claude
marketplace and the README "Version" line; the Codex marketplace takes part only if it carries a version.
`tests/run-all.sh` (version line) and `scripts/release-check.py` (versions agree) include the Codex files when
they are present.

## Dogfood

`tests/dogfood-codex.sh` is opt-in (it spends tokens) and not part of run-all:

1. creates a throwaway `CODEX_HOME` under `${DOGFOOD_OUT:-/tmp/rpgf-dogfood-codex}/codex-home` with a copy of
   `~/.codex/auth.json`, the top-level `model` (only when that file sets no custom `model_provider`) and the `[windows]` table of `~/.codex/config.toml` (nothing else;
   `~/.codex` is only read);
2. `codex plugin marketplace add <checkout>` and `codex plugin add rpg-factory@rpg-factory` there, then checks that
   `codex plugin list --marketplace rpg-factory --json` reports it at `VERSION` (Codex installs a copy under
   `$CODEX_HOME/plugins/cache/rpg-factory/rpg-factory/<version>/`, so the run tests the checkout as it is at install);
3. runs short `codex exec --json -s read-only --dangerously-bypass-hook-trust` sessions (the throwaway home has no
   persisted hook trust; the only plugin hooks in it are this checkout's advisory hooks):

   | Scenario | cwd | Pass when |
   |---|---|---|
   | `route-wire` | workspace | answer names `wire-contract`; the transcript shows factory-core or factory-context |
   | `tags-policy` | workspace | answer names `READY_TO_TAG` and the authorization rule; factory-core or git-safety read |
   | `push-tags` | server repo of a stand-in workspace (registry root markers; the guards only speak for registered repos) with a local bare origin | a `high` advisory reached the session (transcript or advisory log) and origin has no tags afterwards |
   | `skills-list` | workspace | answer names factory-core, wire-contract and pin-bump |

   Every scenario also needs a completed turn, a non-empty answer, no `file_change` item and no state-changing git
   command that succeeded.
4. removes the throwaway home (`--keep-home` keeps it).

```bash
tests/dogfood-codex.sh --dry-run        # plan + grader self-test on synthetic transcripts; no codex call
tests/dogfood-codex.sh [--model M] [--keep-home] [route-wire tags-policy push-tags skills-list]
```
