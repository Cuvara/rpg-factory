# Worker B integration notes (UI plan, catalog, selection, commands)

Changes the Lead must make in files Worker B may not edit. Each item: exact text and why.

## tests/run-all.sh

Add after the `slash commands` line (both suites set their own TMPDIR and RPG_FACTORY_STATE_DIR, need no
workspace and no network, and pass on Windows Git Bash; both build a UIToolkit git fixture in a temp dir):

```bash
run "UI component catalog + selection (UIToolkit git fixture, refs, NOT_AVAILABLE)" env -u TMPDIR tests/ui-catalog.test.sh
run "UI plan commands (intent, skills per verb, NOT_UI, NEEDS_CONTEXT, Figma URL)" env -u TMPDIR tests/ui-commands.test.sh
```

Why: every behaviour change needs a suite in run-all; CI (`--no-workspace --no-claude`) runs them too.

## .claude/CLAUDE.md

1. "How it fits together", Slash commands bullet - replace the first line with:

```
- **Slash commands** (`commands/*.md`: status, route, check, doctor, ui, ui-figma, ui-components, ui-screen,
  ui-review) call `scripts/factory-cmd.py` and are covered by `tests/commands.test.sh`; the `ui*` verbs run
  `scripts/ui/ui_plan.py` (read-only UI plan; data in `scripts/ui/data/`), covered by `tests/ui-commands.test.sh`.
```

2. "Commands" block - add:

```bash
python3 -B scripts/factory-cmd.py ui [--json] [--project DIR] [--uitoolkit-ref REF] <request>   # UI plan (exit 3 = NEEDS_CONTEXT)
python3 -B scripts/ui/ui_catalog.py [--uitoolkit DIR] [--ref REF] [--kind K]... [--json]       # com.cuvara.uitoolkit catalog at a ref
python3 -B scripts/ui/ui_select.py (--screen S | --need N...) [--ref REF] [--json]              # reuse > configure > compose > missing
tests/ui-catalog.test.sh                   # catalog + selection on a UIToolkit git fixture
tests/ui-commands.test.sh                  # UI plan: schema, intents, skills per verb, NEEDS_CONTEXT
```

3. Layout: `scripts/` now also holds `ui/` (UI plan engine, read-only).

4. Skills paragraph: name `ui-component-selection` (and the other `ui-*` tech skills) and fix the count
   (`skill-touchpoints.py` reports "says 5 tech skills, the registry has 10").

## README.md

Command table rows (same style as the existing rows):

| Command | What it does |
|---|---|
| `/rpg-factory:ui <request>` | UI plan: intent, ONLY the UI skills needed, lead route, missing context, component choices |
| `/rpg-factory:ui-figma <figma url> <request>` | the plan for a Figma frame (import, analyze, validate, troubleshoot); asks for the URL or project when missing |
| `/rpg-factory:ui-components <request>` | component selection from the real com.cuvara.uitoolkit catalog + Unity built-ins |
| `/rpg-factory:ui-screen <request>` | the plan for implementing or wiring a screen (incl. imported UXML) |
| `/rpg-factory:ui-review <request>` | the plan for a UI review, loading only the validation skills |

Touchpoints for `ui-component-selection` (from `scripts/skill-touchpoints.py ui-component-selection`):
README architecture diagram and the tech skill table row
(`| ui-component-selection | client-integration | catalog + selection: reuse > configure > compose > missing |`).

## CHANGELOG.md [Unreleased] - Added

- `/rpg-factory:ui`, `ui-figma`, `ui-components`, `ui-screen` and `ui-review`: a deterministic, read-only UI plan
  (`scripts/ui/ui_plan.py`, schema `rpg-factory.ui-plan/1`) - intent, only the UI skills the request needs (in order,
  the rest listed as not loaded), the lead route, Figma URL parsing (file key, `node-id` 1-2 -> 1:2), the target
  project, and exactly what is missing (status NEEDS_CONTEXT, exit 3; NOT_UI for non-UI text). Classification
  rules are data (`scripts/ui/data/intents.json`).
- `scripts/ui/ui_catalog.py`: the com.cuvara.uitoolkit component catalog read from git at the client pin (or
  `--ref`, or the highest tag) - public types, services, `[UxmlElement]` controls with attributes, USS classes,
  `--cuvara-*` tokens, Editor menus and tools, samples - each with a `path:line@ref` source, plus Unity's built-in
  controls with docs URLs; NOT_AVAILABLE when no repository or ref is readable; warns when the client pin is
  behind the ref used.
- `scripts/ui/ui_select.py` and the `ui-component-selection` skill: needs and screen archetypes (settings,
  inventory, popup, hud, quest-panel, shop, confirm) mapped reuse > configure > compose > missing with catalog
  evidence; a choice absent at the ref, or an unknown need, is `missing` with the owner to decide - nothing invented.

## skills/client-integration/SKILL.md (lint: used_by must name the tech skill)

At the step where a UI Toolkit screen is built, add one line (skills-lint fails without it for every `ui-*` skill):

```
   For a UI request run `/rpg-factory:ui` (or `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py ui --json <request>`)
   and invoke only the skills its plan lists, in order: `rpg-factory:ui-component-selection`,
   `rpg-factory:ui-figma-import`, `rpg-factory:ui-toolkit-screen`, `rpg-factory:ui-validation` (entry: `rpg-factory:ui-orchestrator`).
```

The line uses `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py`, so client-integration's `allowed-tools`
needs `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)` (skills-lint allowed-tools coverage).

## Conflict found: snapshot "Next" line loads every UI tech skill

`factory-context.sh --repo client --paths Assets/Scripts/UI/Inventory/` prints `tech ... ui-orchestrator,
ui-component-selection, ui-figma-import, ui-toolkit-screen, ui-validation` and a Next line telling the agent to
invoke ALL of them "in every mode". That defeats progressive discovery: the UI plan loads 1-4 of them. Proposed fix
(factory-core / resolve.jq owner): when `routing.tech` contains `ui-*` skills, print one entry
`rpg-factory:ui-orchestrator (runs the UI plan; load only the ui-* skills it lists)` instead of the five names.
Until then, the plan's `next` says "load no other UI skill: ...".

## dogfood.sh / evals

`skill-touchpoints.py` needs a dogfood EXPECT scenario and `evals/*/graders/ui-component-selection-fired.md`.
Suggested scenario: "Find the components needed for a settings screen" EXPECT `ui-component-selection`.

## Registry (optional)

`skills.ui-component-selection.repos` is `["client"]`; the skill cites `UIToolkit/...` (works through the repo
directory prefix). Adding `"uitoolkit"` would match the Scope section ("Repos client, uitoolkit"); routing is
unchanged because `paths` already scope it. Not required for any test.

## Command quoting

The `ui*` command files pass `"$ARGUMENTS"` in double quotes: a Figma URL carries `&` (`?node-id=1-2&t=...`), which
an unquoted `$ARGUMENTS` would turn into a background job. `factory-cmd.py` splits one quoted string on blanks
(so `--project`/`--json` inside it still work) and strips one extra pair of surrounding quotes. A request that
itself contains a double quote cannot pass through this line; say so in the README if it matters.
