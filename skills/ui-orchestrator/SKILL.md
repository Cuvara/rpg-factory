---
name: ui-orchestrator
description: Entry point for natural-language UI requests in the Unity client - "create a settings screen", "import this Figma frame", "find components for an inventory UI", "review this screen". Runs the deterministic UI plan (intent, minimal ordered skill set, missing context, lead route), then routes through factory-core and loads only the listed UI skills. Use when a request is about UI Toolkit screens, popups, HUD panels, themes, Figma imports or UI review and you have not planned it yet. Not for the work itself (ui-component-selection, ui-figma-import, ui-toolkit-screen, ui-validation), design artifacts (ui-ux), package source (unity-package) or non-UI tasks (factory-core directly).
argument-hint: "[UI request]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---

# UI orchestrator (plan, route, load only what is needed)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package`, `ui-ux`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Plugin paths (`scripts/...`) are relative to `${CLAUDE_PLUGIN_ROOT}`; product paths starting `UIToolkit/` are the
package repo, others the client repo `IndieRPGMMOAdventure/`. Architecture and commands:
`docs/architecture/ui-skills.md` in the plugin.

## Applies when / Not when

- **Applies:** a UI request arrives in plain language, or a UI command (`ui`, `ui-figma`, `ui-components`,
  `ui-screen`, `ui-review`) printed a plan you now execute; or the task changed and the plan must be redone.
- **Not when:** the plan is already followed and a listed skill is running; the request has no UI signal
  (status `NOT_UI`); the question is which module, rule, check or gate applies (the lead owns that).

## Scope

Repos `client`, `uitoolkit` (read for the catalog). Owns no module, contract or check. It decides the order of
UI skills, never scope or validation.

## Architecture

- **One engine.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py ui --json <request>` and the slash
  commands call the same plan engine (`scripts/ui/ui_plan.py`). Output schema `rpg-factory.ui-plan/1`:
  `status` (`PLAN`, `NEEDS_CONTEXT`, `NOT_UI`), `intent`, ordered `skills` with a `why`, `not_loaded`,
  `lead` with its `route`, `context` (Figma URL, project, UIToolkit ref, screen archetype), `missing`,
  `components`, `next`. Exit 0 = PLAN or NOT_UI, 3 = NEEDS_CONTEXT, 2 = usage.
- **Intent decides the skills.** design: none, lead `ui-ux`; figma-import: figma-import, component-selection,
  toolkit-screen, validation; figma-analyze: figma-import, component-selection; figma-validate: figma-import,
  validation; components: component-selection; screen: component-selection, toolkit-screen, validation;
  integrate: toolkit-screen, validation; review: validation (figma-import first with Figma context);
  troubleshoot: figma-import for connector or `FIG0xx` terms, else toolkit-screen, validation; analyze:
  toolkit-screen. Each name is `rpg-factory:ui-<name>`.
- **Routing still decides scope.** The plan's `lead.route` is the input to factory-core step 4
  (`factory-context.sh --repo client --paths ...` or `--domain ui`); the registry's `paths` list on each `ui-*`
  skill keeps them out of `routing.tech` for client changes that touch no UI file.
- **Components come from the real package.** The catalog is read from the UIToolkit repo at a ref (argument,
  else the client pin, else the newest tag), never from memory; selection grades each need reuse, configure,
  compose or missing (`rpg-factory:ui-component-selection`).

## Idioms

1. **Plan.** Run the command above with the user's words. Read `status`:
   - `NOT_UI`: stop using UI skills; continue with factory-core alone.
   - `NEEDS_CONTEXT`: ask for exactly the `missing` items (each has `why` and `how`); never guess a Figma file
     key, node id or project path. Re-run the plan with the answer.
   - `PLAN`: check the plan against the request before continuing (below).
   **Intent check.** Compare `intent` and `skills` with every outcome the user asked for. When they do less (the
   user asked to import and integrate, the plan says `figma-validate`; the user asked for a working screen, the plan
   has no `ui-toolkit-screen`), re-run with the explicit verb (`factory-cmd.py ui-figma ...` for an import,
   `ui-screen` for implementing or wiring) and use that plan. If no verb gives a plan that covers the request, stop
   and tell the user which part the plan leaves out. Never silently do less than asked.
2. **Route.** Follow `next`: factory-core Route with the plan's `lead.route` and the declared mode, then invoke
   the lead (`rpg-factory:client-integration`, `rpg-factory:unity-package` or `rpg-factory:ui-ux`).
3. **Load only the listed skills, in order.** For any UI file the snapshot's `tech` list names all five `ui-*`
   skills; the plan's `skills` is the subset to invoke. Never invoke a `not_loaded` skill. Invoke them in
   every mode, `plan` and `analyze` included: they hold the facts the plan or analysis needs. If the task changes (new
   Figma link, "now implement it", a review becomes a fix), re-run the plan instead of loading more.
4. **Select before creating.** When `ui-component-selection` is listed it runs before any file is created;
   a component graded reuse or configure is used, never rebuilt. `missing` goes to its owner as a hand-off.
5. **Write a short execution plan before implementing:** intent, lead and route, skills in order, components
   by grade, files to create or change, checks and gates, open questions.
6. **Parallel work:** independent legs (for example two unrelated screens) may be delegated; follow
   factory-core's parallel-work reference there. One worker per screen; the main session integrates.

## Pitfalls

- **A plan can under-serve the request.** In the real Figma run, "import ... and integrate ... run the package
  validator" was planned as `figma-validate`, so `ui-toolkit-screen` was never loaded and the screen was not
  integrated (regression case in `tests/fixtures/ui-plan-cases.json`). Apply the intent check in step 1.
- **A tech skill requested first is redirected.** Before factory-core the Skill hook loads factory-core instead;
  before the lead it runs with a `high` advisory (PreToolUse Skill hook, `hooks/hooks.json`). Plan, then route, then load.
- **The client pin can lag the package.** 0.8.0-only APIs (theme service, ScreenCreator "Existing UXML") need a
  pin at 0.8.0 or later (`UIToolkit/Documentation~/MIGRATION-0.8.md`, "Summary"); the plan reports the ref it
  used and a pin-bump follow-up when the pin is older.
- **Duplicate components are the common failure.** The client contract says screens compose components, never
  re-implement them (`docs/UI-ARCHITECTURE.md`, "Reusable components").
- **Generated UXML is a starting point,** not shipped UI (`docs/UI-ARCHITECTURE.md`, "Design workflow").
- **Never claim unverified Figma features** (SafeArea mapping, shadows, gradients in a real import):
  `UIToolkit/Documentation~/FIGMA-REAL-IMPORT.md`, "Unsupported constructs".

## Testing

- The plan is deterministic: the same request and verb give the same JSON. Check a plan with
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py ui --json "<request>"` and compare `intent`, `skills`
  and `status` with the intent table above.
- Plugin tests own the engine (`tests/` in the plugin); product validation is the lead's and
  `rpg-factory:ui-validation`'s.

## Tools

- `figma-mcp`: only to read the frame link's metadata when the plan reports Figma context and a detail is
  missing; fallback: ask the user for the frame URL with `node-id`. The plan and routing are plugin scripts;
  the listed skills and the lead name their own tools.

## Report additions

- Intent and verb; UI skills loaded, in order, and skipped (`not_loaded`).
- Components by grade (reuse, configure, compose, missing) with their catalog ids and the UIToolkit ref.
- One evidence artifact per claim (test result, screenshot, Console log, validator JSON), else the open state.
