# Worker A - integration notes for the Lead

Branch `feat/ui/skills-a` (base 6db4cc7). Files owned and changed by A:
`skills/ui-orchestrator/SKILL.md`, `skills/ui-toolkit-screen/SKILL.md`, `skills/ui-validation/SKILL.md`,
`skills/ui-validation/references/ui-review.md` (new), `skills/client-integration/SKILL.md` (4 lines in
Workflow delta step 4), `docs/architecture/ui-skills.md` (new), `docs/architecture/README.md` (one index line),
`tests/ui-skills.test.sh` (new, 100755), this file.

## 1. tests/run-all.sh (Lead-owned): add the new suite

`tests/ui-skills.test.sh` needs no workspace, no Claude and no TMPDIR (it makes its own). Add it next to the
other content suites, e.g. after `skills-lint.sh`:

```bash
run "ui skills" tests/ui-skills.test.sh
```

(use whatever helper run-all.sh uses for the neighbouring suites; it prints `ui skills tests: N run, N passed, 0 failed`).

## 2. registry.json (Lead-owned): dev tools for the UI skills (proposal)

skills-lint only lets a `## Tools` bullet lead with a backticked dev tool id when the tool's `used_by`
lists the skill. The three skills therefore name `unity-mcp` and `dotnet` inside the bullet text, "through the
lead". If you want them as first-class tools, add to `dev_tools[]`:

- `unity-mcp.used_by` += `ui-toolkit-screen`, `ui-validation` (ScreenCreator in the Editor; tests-run,
  console-get-logs, screenshot-game-view)
- `dotnet.used_by` += `ui-validation` (UxmlCodegenCli drift check and `validate` verb)

After that, rewrite the two `## Tools` bullets to lead with the backticked id (lint then requires it).
No `cite_roots` change is needed: citations use the `UIToolkit/` repo-directory prefix, which resolves to the
`uitoolkit` repo at `origin/main` (== `v0.8.0`, 99daab9).

## 3. Snapshot "Next" line vs progressive loading (factory-context / resolve.jq, Lead-owned)

For any UI file the snapshot routing prints `tech ... ui-orchestrator, ui-component-selection, ui-figma-import,
ui-toolkit-screen, ui-validation` and its **Next** line says "invoke the tech skill(s) ... all five". That
contradicts the plan's "only the listed skills". The skills handle it in text (ui-orchestrator idiom 3: the
plan's `skills` is the subset to load). Suggested code change: when `routing.tech` contains domain-`ui` tech
skills, print them in the Next line as "UI skills: run `rpg-factory:ui-orchestrator` (UI plan) and invoke only
the skills it lists" instead of the full list. Verified routing today (workspace, origin/develop):
`--repo client --paths Assets/Scripts/UI/Settings/Settings.uxml` -> tech lists all five ui-*;
`--paths Assets/Scripts/DI/GameLifetimeScope.cs` -> no ui-*.

## 4. Touchpoints still missing for A's skills (all Lead-owned files)

`python3 -B scripts/skill-touchpoints.py ui-orchestrator ui-toolkit-screen ui-validation`, per skill:
factory-core SKILL.md "Skills" line, skill-contract.md layering diagram, README architecture diagram and
tech-skill table, `.claude/CLAUDE.md` "Skills:" paragraph (and its count: "5 tech skills" -> 10), a
`tests/dogfood.sh` EXPECT scenario, and an eval grader `evals/*/graders/<skill>-fired.md`. A's own
touchpoints (no SCAFFOLD marker, client-integration names all five) are clear.

Suggested text:

- factory-core SKILL.md "Skills" line: `supporting Engineering skills: dotnet-gameserver, go-backend,
  unity-client-tech, unity-dots, netcode-client; UI (client, via client-integration): ui-orchestrator,
  ui-component-selection, ui-figma-import, ui-toolkit-screen, ui-validation`.
- skill-contract.md diagram, tech skills line: append
  `; UI: ui-orchestrator, ui-component-selection, ui-figma-import, ui-toolkit-screen, ui-validation`.
- `.claude/CLAUDE.md` Skills paragraph: "10 tech skills (`kind: tech`: dotnet-gameserver, go-backend,
  unity-client-tech, unity-dots, netcode-client, and the UI skills ui-orchestrator, ui-component-selection,
  ui-figma-import, ui-toolkit-screen, ui-validation, scoped by registry `paths`)".
- README tech table rows:
  - `ui-orchestrator` | entry for plain-language UI requests: UI plan, missing context, loads only the listed UI skills
  - `ui-toolkit-screen` | screens and popups on com.cuvara.uitoolkit 0.8: ScreenCreator, presenters, navigator, theme
  - `ui-validation` | UI review and evidence: references, bindings, lifecycle, theme, responsive, runtime, tests
- Dogfood scenarios (EXPECT): "create a settings screen in the client" -> ui-orchestrator then
  ui-component-selection, ui-toolkit-screen; "review the HUD screen UXML" -> ui-validation.

## 5. CHANGELOG.md [Unreleased] bullets (Lead-owned)

- `feat(skills)`: `ui-orchestrator` is the entry point for plain-language UI requests: runs the UI plan,
  asks for missing context, routes through factory-core and loads only the listed UI skills.
- `feat(skills)`: `ui-toolkit-screen` documents screens and popups on com.cuvara.uitoolkit 0.8 (ScreenCreator
  new/existing UXML, presenters, registration, navigator, codegen, settings, dialogs, theme service), cited at v0.8.0.
- `feat(skills)`: `ui-validation` grades UI work by artifact across seven areas and ships the
  `/rpg-factory:ui-review` checklist (`references/ui-review.md`).
- `feat(skills)`: `client-integration` names the five UI skills at its UI step.
- `docs`: `docs/architecture/ui-skills.md` describes UI discovery, routing, commands, intents and boundaries.
- `test`: `tests/ui-skills.test.sh` pins the UI skills' contract (164 assertions).

## 6. Cross-worker dependencies

- The skills and the doc reference `factory-cmd.py ui|ui-figma|ui-components|ui-screen|ui-review`,
  `scripts/ui/ui_plan.py`, `ui_catalog.py`, `ui_select.py`, `scripts/ui/data/*.json` (Worker B) and
  `docs/architecture/ui-figma-real-test.md` (Worker C) by name only. After merging, delete the "parallel
  branch" rows of the status table in `docs/architecture/ui-skills.md` (or change them to "implemented").
- The command table assumes command files `commands/ui.md`, `ui-figma.md`, `ui-components.md`, `ui-screen.md`,
  `ui-review.md`. If B names them differently, update the table; `tests/ui-skills.test.sh` asserts the
  `/rpg-factory:<verb>` names.
- `tests/commands.test.sh` asserts "exactly 4 commands"; B's new commands must update it (not A's file).

## 7. Out of scope, noticed

- `python3 -B scripts/checks/skill-citations.py` (live) reports 3 pre-existing drifts in
  `skills/dotnet-gameserver/SKILL.md` and `skills/server-realtime/references/gameserver.md` (GameServer.cs
  lines moved on server origin/develop). Not touched by A.
- The client pins `com.cuvara.uitoolkit` v0.7.2 (pin-status.py); 0.8.0 APIs used by the UI skills need a
  pin-bump. The skills say so without stating the version (no point-in-time value in prose).
