# Worker D integration notes - UI QA and skill evaluation

Branch `feat/ui/skills-d` (base 6db4cc7). Files owned by D: `tests/ui-skill-routing.test.sh`,
`tests/fixtures/ui-plan-cases.json`, `tests/fixtures/ui-select-cases.json`, `tests/fixtures/ui-select-repo/**`,
`evals/ui-settings-screen/**`, `evals/ui-figma-import/**`, `evals/ui-not-ui/**`, this file.

The test is a black box against the shared contracts in `briefs/common.md`. On D's branch alone it reports one
`FAIL engine missing: scripts/ui/ui_plan.py scripts/ui/ui_select.py` (plan and selection cases NOT_RUN) and passes
its registry and routing assertions. After B is merged it runs the full matrix (46 plan cases + 10 global plan
assertions + 16 selection assertions + 9 registry/routing assertions).

## Expectations to reconcile with B's classifier

The golden matrix follows the contract literally. These cases depend on a judgement call. If B's classifier
disagrees, decide once and change ONE side (prefer the fixture when the contract allows both answers):

| case id | request | D expects | alternative |
|---|---|---|---|
| mission-popup | "Build a reusable popup." | screen, screen=popup | components (a reusable package control would be unity-package) |
| mission-existing-components | "Use the existing UI Toolkit components to build this screen." | screen | components |
| mission-validate-imported | "Validate imported UXML and USS" | figma-validate [ui-figma-import, ui-validation] | review [ui-validation] |
| ui-login-button-colour | "Fix the login button colour." | troubleshoot [ui-toolkit-screen, ui-validation] | screen |
| verb-screen-imported | ui-screen "Implement this imported UXML in the current screen architecture" | integrate | screen |
| not-ui-inventory-migration | "Add a SQL migration for the player inventory table." | NOT_UI | (must stay NOT_UI: "inventory" alone is not a UI signal) |
| no-client-needs-project | figma import with URL, workspace without the client repo | NEEDS_CONTEXT, some missing item other than figma-frame-url | - |

Selection: `settings data` accepts reuse or configure (the briefs disagree: D.md says configure, common.md says
reuse). `graphics quality` accepts compose or configure. Selections are found as any JSON object with both `need`
and `status`, so the top-level shape of `ui_select.py --json` is free. `ui_select.py` is run with
`RPG_FACTORY_WORKSPACE` pointing at a fixture workspace (`UIToolkit` tagged v0.8.0, client manifest `#v0.8.0`);
it must find the repo through the workspace default, not only through `--uitoolkit`.

## tests/run-all.sh line

Add after the `slash commands` line (no workspace and no Claude needed, so it also runs in CI):

```bash
run "UI plan routing, golden matrix, component selection (fixture workspace)" env -u TMPDIR tests/ui-skill-routing.test.sh
```

`git ls-files -s tests/ui-skill-routing.test.sh` must show mode 100755 (set on D's branch).

## tests/dogfood.sh scenarios

Add next to the other PROMPT/EXPECT lines and append `ui-settings ui-figma ui-not-ui` to the default `scenarios=(...)` list:

```bash
PROMPT[ui-settings]="Create a settings screen (music and sound toggles, master volume, graphics quality, a confirm popup on reset) for the Unity client IndieRPGMMOAdventure using the existing com.cuvara.uitoolkit components."
EXPECT[ui-settings]="factory-core client-integration ui-orchestrator ui-component-selection ui-toolkit-screen ui-validation"; HANDOFF[ui-settings]=""; SHOWS[ui-settings]="ConfirmDialog|SettingsModel"; NOTEXPECT[ui-settings]="ui-figma-import"
PROMPT[ui-figma]="Import this Figma screen into the Unity client IndieRPGMMOAdventure and fit it into our existing UI architecture: https://www.figma.com/design/AbC123xyz/Game-UI?node-id=12-34"
EXPECT[ui-figma]="factory-core client-integration ui-orchestrator ui-figma-import ui-component-selection ui-toolkit-screen ui-validation"; HANDOFF[ui-figma]=""; SHOWS[ui-figma]="FIG023|HUMAN_REQUIRED|NOT_RUN"
PROMPT[ui-not-ui]="Change the Go gateway in rpg-mmo-server so its TLS listener accepts TLS 1.3 only."
EXPECT[ui-not-ui]="factory-core server-services"; HANDOFF[ui-not-ui]=""; NOTEXPECT[ui-not-ui]="ui-orchestrator ui-component-selection ui-figma-import ui-toolkit-screen ui-validation"
```

dogfood.sh has no "must not invoke" field today. Exact diff to add one (`NOTEXPECT`, space = none of):

```diff
-declare -A PROMPT EXPECT HANDOFF MODE TOOLRUN SHOWS RAW CORRECTS
+# NOTEXPECT: skills that must NOT be invoked (space = none of), if set.
+declare -A PROMPT EXPECT HANDOFF MODE TOOLRUN SHOWS RAW CORRECTS NOTEXPECT
@@
   for e in ${EXPECT[$n]}; do
     ...
   done
+  for x in ${NOTEXPECT[$n]:-}; do grep -qw -- "$x" <<<"$used" && why+="$x invoked but must not be; "; done
```

The `ui-settings` and `ui-figma` scenarios also satisfy the dogfood `tests/dogfood.sh has no scenario that EXPECTs it`
touchpoint for all five UI skills. `ui-orchestrator` is `kind: tech`; the tech-first rule in dogfood.sh
requires `client-integration` to load before it (or an advisory plus the lead afterwards), which the
expected flow (factory-core, then client-integration, then the UI skills) meets.

## CHANGELOG.md bullets ([Unreleased] / Added)

```markdown
- `tests/ui-skill-routing.test.sh`: black-box tests of the UI plan against a golden matrix
  (`tests/fixtures/ui-plan-cases.json`, 46 cases covering every `ui*` verb, every intent, the mission requests,
  10 non-UI requests, Figma URL variants and troubleshooting), exact skill order, `not_loaded`, missing items and
  exit codes 0/3/2; component selection on a UIToolkit v0.8.0 fixture repo (`tests/fixtures/ui-select-cases.json`:
  reuse ConfirmDialog/SettingsModel/ToastService, compose ui:Toggle/Slider/DropdownField/TabView, missing with
  an owner, never `missing` for an existing component, NOT_AVAILABLE without a repo); the five `domain: ui` tech
  skills in the registry and their path-scoped `routing.tech`.
- Evals `ui-settings-screen`, `ui-figma-import` and `ui-not-ui`, with a `<skill>-fired.md` grader for every UI
  skill and "must not invoke" graders (`min: 0, max: 0`) for Figma on a plain screen and for any UI skill on a
  non-UI request.
- `tests/dogfood.sh`: scenarios `ui-settings`, `ui-figma`, `ui-not-ui` and a `NOTEXPECT` field (skills that
  must not be invoked).
```

## Integration test matrix

| area | case | test file | CI or local | real-tool requirement |
|---|---|---|---|---|
| skill discovery | five `kind: tech`, `domain: ui` skills registered, used_by client-integration, path-scoped, SKILL.md present | tests/ui-skill-routing.test.sh | CI | none |
| skill discovery | skill contract, `## Tools`, scaffold markers gone | tests/skills-lint.sh | CI | none |
| skill discovery | every touchpoint per UI skill (evals, dogfood, README, CLAUDE.md) | scripts/skill-touchpoints.py --all | CI (via run-all) | none |
| routing | `.uxml`, `.uss` under `Assets/UI Toolkit/`, `Assets/Scripts/UI/**` list the five UI skills in routing.tech; `MainSessionFlow.cs` and a server path list none | tests/ui-skill-routing.test.sh | CI | none |
| routing | `--domain ui` lead ui-ux; server gateway lead server-services; golden engineering routing unchanged | tests/ui-skill-routing.test.sh, tests/routing-golden.test.sh, tests/routing.test.sh --no-history | CI | none |
| commands | UI plan golden matrix: status, intent, exact skill order, not_loaded, missing items, exit 0/3, NOT_UI loads nothing, ui-orchestrator never listed | tests/ui-skill-routing.test.sh | CI | none |
| commands | Markdown output, usage errors exit 2, determinism | tests/ui-skill-routing.test.sh | CI | none |
| commands | 9 command files, dispatch lines, usage loop | tests/commands.test.sh (B), tests/ui-commands.test.sh (B) | CI | none |
| component selection | reuse / configure / compose / missing, never duplicate, evidence cites `path@v0.8.0`, NOT_AVAILABLE without repo | tests/ui-skill-routing.test.sh, tests/ui-catalog.test.sh (B) | CI | none |
| component selection | catalog on the real UIToolkit at v0.8.0 and at the client pin | B report (manual run) | local | UIToolkit repo on disk |
| Figma workflow | URL parsing (design/file, `12-34`, `12%3A34`, extra query), NEEDS_CONTEXT without URL or project | tests/ui-skill-routing.test.sh | CI | none |
| Figma workflow | environment probe (`figma_env.py`) | C's test | CI | none |
| Figma workflow | real import through the official connector, validator `FIG023`, screen opens light/dark | Lead-run, manual | local | Unity 6000.3.9f1 Editor, com.unity.ui.figma, Figma login (HUMAN_REQUIRED) |
| skill behaviour | settings screen, Figma import, non-UI request: skills fired, skills not fired, criteria | evals/ui-settings-screen, evals/ui-figma-import, evals/ui-not-ui (`claude plugin eval`) | local | Claude (tokens) |
| skill behaviour | real headless sessions invoke the expected skills and not the others | tests/dogfood.sh ui-settings ui-figma ui-not-ui | local | Claude (tokens), workspace |
| regression | whole local suite | tests/run-all.sh (`--no-workspace --no-claude` in CI) | both | none in CI |
