# UI skills: discovery, routing and boundaries

This page describes how rpg-factory handles UI requests for the Unity client: a settings screen, a Figma frame
import, a component search, a screen review. It covers the five UI tech skills, how an agent finds and loads
only the ones a request needs, and where each kind of work belongs.

The integration contract is `com.cuvara.uitoolkit` **v0.8.0** (repo `UIToolkit`) plus the Unity 6 built-in UI
Toolkit controls. Skills cite the package at its tag; nothing here restates package facts that the skills cite.

## Status of the pieces

| Piece | Where | Status |
|---|---|---|
| Five UI tech skills, registry entries with `domain: ui` and `paths` | `skills/ui-*/`, `registry.json` | implemented |
| `routing.tech` scoping by `paths` | `scripts/lib/resolve.jq` | implemented |
| Snapshot Next line loads UI skills through `ui-orchestrator` | `scripts/lib/context.py` | implemented |
| UI plan engine and the `ui*` verbs and commands | `scripts/ui/ui_plan.py`, `scripts/factory-cmd.py`, `commands/ui*.md` | implemented |
| Component catalog and selection | `scripts/ui/ui_catalog.py`, `scripts/ui/ui_select.py`, `scripts/ui/data/*.json` | implemented |
| Figma connector environment check | `scripts/ui/figma_env.py` | implemented |
| Dev tools `figma-mcp`, `unity-mcp`, `dotnet` for the UI skills | `registry.json` `dev_tools[]` | implemented |
| Real Figma import test | `docs/architecture/ui-figma-real-test.md` | import and validator run ("Game Settings": import succeeded, validator 0 errors); Unity runtime rows **not yet run** |

## Discovery and routing

```
user request (plain language or /rpg-factory:ui*)
   -> UI plan: python3 scripts/factory-cmd.py <verb> --json <request>
        status NOT_UI        -> no UI skill; factory-core alone
        status NEEDS_CONTEXT -> ask for the listed missing items (exit 3); nothing is guessed
        status PLAN          -> intent, ordered skills, not_loaded, lead + route, components, next
   -> factory-core Route with the plan's lead.route (factory-context.sh --repo client --paths ... | --domain ui)
   -> invoke the lead (client-integration, unity-package or ui-ux)
   -> invoke ONLY the plan's skills, in order; never the not_loaded ones (re-plan when the task changes)
```

- **Entry point.** `ui-orchestrator` is the model-invoked entry for plain-language requests. The slash commands
  call the same engine, so a command and a conversation give the same plan.
- **Deterministic.** The same request text and verb produce the same JSON (`schema: rpg-factory.ui-plan/1`).
  Exit codes: 0 PLAN or NOT_UI, 3 NEEDS_CONTEXT, 2 usage error.
- **Tech skills stay behind their lead.** All five are `kind: tech` with `used_by: [client-integration]`. The
  Skill hook loads factory-core first when one is requested too early and flags a call made before the lead
  (advisory only). `client-integration` names each of them at its UI step.
- **`paths` scoping.** A tech skill with a `paths` list appears in the snapshot's `routing.tech` only when a
  changed file matches it. For the UI skills the list is `**/*.uxml`, `**/*.uss`, `**/*.tss`,
  `Assets/UI Toolkit/`, `Assets/Scripts/UI/` and `Assets/Figma/`. A client change outside those paths lists no
  UI skill; a change inside lists all five in the routing line.
- **Next line.** For such a change the snapshot's **Next** line does not tell the agent to invoke all five. It
  names the other tech skills as usual and adds one clause: `UI skills (...): invoke rpg-factory:ui-orchestrator
  first; its UI plan names the subset to load - invoke only those, never all of them.` A change without a UI file
  prints no `UI skills (` clause.

## Commands

| Command | Verb | Forces intent family |
|---|---|---|
| `/rpg-factory:ui` | `ui` | none: intent is detected from the text |
| `/rpg-factory:ui-figma` | `ui-figma` | Figma import, analysis or validation |
| `/rpg-factory:ui-components` | `ui-components` | component search and selection |
| `/rpg-factory:ui-screen` | `ui-screen` | screen or popup implementation |
| `/rpg-factory:ui-review` | `ui-review` | review (the `ui-validation` checklist) |

Options: `--json`, `--project <Unity project path>`, `--uitoolkit-ref <ref>`.

## Intents and the skills they load

| Intent | Skills, in order | Lead |
|---|---|---|
| design | none (add `ui-component-selection` when components are asked) | `ui-ux` (`--domain ui`) |
| figma-import | `ui-figma-import`, `ui-component-selection`, `ui-toolkit-screen`, `ui-validation` | `client-integration` |
| figma-analyze | `ui-figma-import`, `ui-component-selection` | `client-integration` |
| figma-validate | `ui-figma-import`, `ui-validation` | `client-integration` |
| components | `ui-component-selection` | `client-integration` |
| screen | `ui-component-selection`, `ui-toolkit-screen`, `ui-validation` | `client-integration` |
| integrate | `ui-toolkit-screen`, `ui-validation` | `client-integration` |
| review | `ui-validation` (`ui-figma-import` first with Figma context) | `client-integration` |
| troubleshoot | `ui-figma-import` for connector or `FIG0xx` terms, else `ui-toolkit-screen`, `ui-validation` | `client-integration` |
| analyze | `ui-toolkit-screen` | `client-integration` |

`NEEDS_CONTEXT` is returned for figma-import and figma-analyze without a Figma frame URL, and for
figma-import without a target project when no client repo is in the workspace and none is given.

**When the plan does less than asked.** The real Figma run showed it: "import ... integrate ... run the package
validator" was planned as `figma-validate`, so `ui-toolkit-screen` never loaded and the screen was not integrated.
`ui-orchestrator` therefore checks the plan's intent and skills against everything the user asked for; when they
fall short it re-plans with the explicit verb (`ui-figma` for an import, `ui-screen` for implementing or wiring) or
stops and says which part is left out. It never silently does less than asked. The engine fix for this request
(an import verb with a Figma URL wins over validate wording) is tracked with the golden cases of
`tests/fixtures/ui-plan-cases.json`.

## The five skills

| Skill | Owns the "how" of | Never |
|---|---|---|
| `ui-orchestrator` | running the plan, asking for missing context, loading only the listed skills, the execution plan, the UI report additions | does the work itself |
| `ui-component-selection` | finding components in the real package catalog and Unity built-ins; grading each need reuse, configure, compose or missing | invents a component or API |
| `ui-figma-import` | the official UI Toolkit Connector for Figma (`com.unity.ui.figma`) through the package's profiles, token bridge, mapping preset, headless helper, validator and diagnostics | builds an importer, exporter or UXML/USS generator |
| `ui-toolkit-screen` | ScreenCreator, presenters, `ScreenSubscriptions`, registration, `IScreenNavigator`, `Require<T>` and codegen, settings, dialogs, toasts, theme service; analyze mode maps an existing UI read-only | edits package source |
| `ui-validation` | the seven review areas (references, bindings, lifecycle, theme, responsive, runtime, tests) and which artifact backs each result state; the `/rpg-factory:ui-review` checklist | grades PASS without an artifact |

## Boundaries with the neighbouring skills

- **`ui-ux`** (lead, domain `ui`, authoring repo) owns the design artifacts (ux-requirements, ia-map,
  design-tokens, component-spec, screen-spec, ui-handoff). A `ui-handoff` or screen spec is the design input for
  the engine-side work the UI skills plan; `ui-ux` names `rpg-factory:ui-orchestrator` for that part.
  A request for a spec, not code, routes there with `--domain ui`.
- **`client-integration`** (lead, client repo) owns where client changes go, its rules, validation, gates and
  report. Every UI code change in `IndieRPGMMOAdventure` runs inside its workflow.
- **`unity-package`** (lead, package repos) owns changes to `com.cuvara.uitoolkit` itself. A component graded
  `missing` with owner `unity-package` is a hand-off there, released by tag and moved in by `pin-bump`.
- **`unity-client-tech`** (tech) owns how Unity client code works in general: async, VContainer lifetimes,
  asmdefs, tests. The UI skills add only what is specific to UI Toolkit screens and the package.

## Selecting components

Selection runs before any file is created (`ui-component-selection`). The catalog is built from the UIToolkit
git repo at a ref, never from the working tree: the `--uitoolkit-ref` argument, else the client's pin, else the
newest `v*` tag. Each need gets one grade: **reuse** (use as is), **configure** (set attributes or options),
**compose** (build from built-in controls and tokens), **missing** (named owner, never invented). When the
client pin is older than the ref used, the plan says so and names the `pin-bump` follow-up. Without a
UIToolkit repo the catalog is NOT_AVAILABLE.

## Figma import overview

The official connector imports; the package validates and scaffolds. The import folder (`Assets/Figma/<file>/`)
belongs to the connector; ScreenCreator refuses to write there and generates the screen code in a game-owned
folder from the "Existing UXML" source. The validator (`UxmlCodegenCli validate` or the Editor API) grades the
folder with stable `FIG0xx` codes. Procedure: `ui-figma-import`; real-import test and its evidence:
`docs/architecture/ui-figma-real-test.md`.

Integrating the output (`ui-toolkit-screen`, `references/imported-uxml.md`): the connector UXML carries **no
`name` attributes**, so a game-owned view binds by type and document order or by the component class
(`toggle`, `button-close`, ...), once, and throws when a count changes; nothing is added to the connector file.
Controls arrive without a value range or choices. Settings map only to members `SettingsModel` has (volumes,
graphics quality, fullscreen, VSync, language); a music or sound on/off toggle is game-owned state. The UXML links
`light.uss` itself, so light and dark need `RegisterModeSheets` plus `AttachScreen` on the open screen.
`ui-validation` accepts such a binding only with a PlayMode test on the real imported file.

## UIToolkit v0.8.0 compatibility and known limitations

- The Figma integration is optional: its Editor assembly compiles only with `com.unity.ui.figma` installed.
- Unity 6000.3.9f1 cannot clone UXML with `var()` in an inline style (validator `FIG023`). Designer rule:
  bind variables only on component roots and `<Role>/Label` single-text components.
- Typed node-id bindings (audit gap G4) are deferred.
- SafeArea emission, shadows and gradients are not verified in a real import; never report them as working.
- The theme service, mode sheets and ScreenCreator's "Existing UXML" source are new in 0.8.0. A client pinned
  to an older tag cannot use them until `pin-bump` moves the pin.
- The client has no screen host registered yet; standing up `RegisterUIToolkit` and `RegisterScreenFlow` is a
  client wiring change planned by `client-integration`.

## Troubleshooting

| Symptom | Look at |
|---|---|
| plan says `NOT_UI` for a UI request | add a UI term (screen, popup, UXML, Figma, HUD) or use a `ui-*` verb |
| plan says `NEEDS_CONTEXT` | give exactly the `missing` items: Figma frame URL with `node-id`, `--project` |
| snapshot lists all five UI skills | expected for UI files; the Next line says to start with `ui-orchestrator` and load only the plan's `skills` |
| a UI skill runs with a `high` advisory | the lead was not invoked first; route and invoke it |
| catalog NOT_AVAILABLE | no UIToolkit repo in the workspace; pass `--uitoolkit-ref` with a reachable repo |
| `FIG0xx` findings, connector problems | `ui-figma-import` and the package's `TROUBLESHOOTING-FIGMA.md` |
| plan intent covers less than the request (e.g. `figma-validate` for an import) | re-run with `ui-figma` or `ui-screen`; otherwise say what is left out |
| `Require<T>` finds nothing in an imported screen | connector output has no names: bind by type, order or class (`ui-toolkit-screen`) |
| imported screen stays light after a mode switch | register both mode sheets and `AttachScreen` the open screen |

## Adding a UI skill

1. Scaffold: `python3 -B scripts/new-skill.py --name ui-<name> --kind tech --repos client --used-by client-integration --domain ui --summary "<text>"`.
2. Add `paths` to its registry entry by hand (the scaffolder has no flag for it); reuse the UI list above
   unless the skill needs a narrower one.
3. Add the intent mapping to the UI plan engine's data, and a scenario to its tests.
4. Fill the skill (`skill-contract.md`), name it in `client-integration` at the step that needs it, and run
   `python3 -B scripts/skill-touchpoints.py ui-<name>` until it is OK.

## Adding component metadata or recipes

Component facts that the package cannot express (Unity built-in controls, screen recipes) live in
`scripts/ui/data/*.json`: `unity-builtins.json` (built-in controls, each with a docs URL) and
`screen-recipes.json` (needs per screen archetype). Package components come from the UIToolkit repo itself;
do not copy them into data files. Every new entry needs a source and a test in the catalog's test suite.
