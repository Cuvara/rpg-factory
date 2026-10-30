# Worker C - integration notes for the Lead

Changes Worker C needs in files it does not own. Each item: the exact text and why.

## 1. tests/run-all.sh - run the new suite

Add next to the other `env -u TMPDIR` suites (it sets its own TMPDIR / RPG_FACTORY_STATE_DIR and needs no workspace,
no network and no Unity, so it also belongs in the CI `--no-workspace --no-claude` run):

```bash
run "Figma connector environment check (fixture Unity projects, no network)" env -u TMPDIR tests/ui-figma-env.test.sh
```

Place it with the other unconditional suites (for example after the `devtools.test.sh` line), not inside a
workspace-only block.

## 2. registry.json - dev tools

Why: `skills/ui-figma-import/SKILL.md` `## Tools` currently says no registry dev tool lists it. skills-lint requires a
`## Tools` bullet that leads with a backticked id to be a registered id whose `used_by` lists the skill, so once these
land, change the two `## Tools` bullets to lead with `` `figma-mcp` `` and `` `unity-mcp` ``.

```json
{
  "id": "figma-mcp",
  "kind": "mcp",
  "probes": ["mcp:figma|mcp:claude_ai_Figma|plugin:figma"],
  "provides": "Figma file access for UI work: get_metadata (frame tree and node ids), get_screenshot (reference image), get_variable_defs (variable collections and modes). Read-only use in ui-figma-import step 1.",
  "used_by": ["ui-figma-import", "ui-orchestrator"],
  "required": false,
  "fallback": "ask the user for the frame link (Copy link to selection, with node-id=) and a PNG export of the frame; the preflight is then HUMAN_REQUIRED for anything the screenshot cannot show (variable bindings)"
}
```

Caveat to verify before merging: claude.ai connector servers (this machine shows `claude_ai_Figma`) are configured
on the account, not in `.mcp.json` or `~/.claude.json`, so `lib/devtools.py` `mcp:` probes may report the tool missing
while it is usable. If so, keep `required: false` and say it in the provides text, or add a probe kind later.

Add `"ui-figma-import"` to `unity-mcp.used_by` (Console and Play-mode screenshots in the import lab), then the second
`## Tools` bullet can lead with `` `unity-mcp` ``.

`unity-figma-connector` is NOT a dev tool: it is a Unity package inside a project, which no probe kind
(`bin`, `tool`, `service`, `mcp`, `plugin`) can see. `scripts/ui/figma_env.py --project <p>` is its probe. If the
doctor should mention it, add a one-line note to the doctor output instead of a `dev_tools` entry.

## 3. registry.json - facts

Why: the skill names version floors as facts (skill contract: version-like values are `facts[]` with a probe). Probes
read the integration branch, not the working tree (verified on this machine: prints `0.3.0-exp.1`):

```json
{
  "id": "uitoolkit-figma-connector-floor",
  "value": "0.3.0-exp.1",
  "repo": "uitoolkit",
  "probe": "git show origin/main:Editor/Figma/Cuvara.UIToolkit.Editor.Figma.asmdef | sed -n 's/.*\"expression\": \"\\(.*\\)\".*/\\1/p'",
  "why": "com.unity.ui.figma version that opens the gated Cuvara.UIToolkit.Editor.Figma assembly; also the tested connector version (FIGMA-INTEGRATION.md Requirements)"
}
```

`scripts/ui/figma_env.py` keeps its own constants (`TESTED_CONNECTOR`, `MIN_UITOOLKIT`, `TESTED_UNITY`); if the Lead
prefers, it can read them from the registry facts later (then `tests/ui-figma-env.test.sh` needs a registry fixture).

## 4. Skill touchpoints for ui-figma-import (skill-touchpoints.py)

Remaining after this branch, all in Lead-owned files:

- `skills/factory-core/SKILL.md` "Skills" section: name `ui-figma-import`.
- `skills/factory-core/references/skill-contract.md` layering diagram: add it to the tech skills line.
- `README.md` architecture diagram and tech skill table: one row, e.g.
  `| ui-figma-import | client | Figma frame to UI Toolkit through the official connector and com.cuvara.uitoolkit 0.8: preflight, env check, headless import, validator, diagnostics, profile/bridge/preset |`.
- `.claude/CLAUDE.md` "Skills:" paragraph (also the "5 tech skills" count; the registry now has 10).
- `tests/dogfood.sh`: a scenario that EXPECTs it, e.g.
  `PROMPT[ui-figma]="/rpg-factory:ui-figma import https://www.figma.com/design/AbC123/Game?node-id=1-2 into the client"`,
  `EXPECT[ui-figma]="client-integration ui-figma-import"`.
- `evals/*/graders/ui-figma-import-fired.md`: grader file (no owner assigned in the briefs).
- `skills/client-integration/SKILL.md` must name `rpg-factory:ui-figma-import` (used_by lint), at the UI step:
  "Figma frame to import or an imported screen that breaks: invoke `rpg-factory:ui-figma-import`."

## 5. docs/architecture/README.md

Add under Documents:

```markdown
- [Real Figma-to-Unity integration test](ui-figma-real-test.md): the "Game Settings" procedure and its evidence table (NOT YET RUN until filled).
```

## 6. CHANGELOG.md [Unreleased]

```markdown
### Added
- `ui-figma-import` skill: Figma to Unity through the official UI Toolkit Connector for Figma and the com.cuvara.uitoolkit 0.8
  tools - scope, designer preflight (FIG023), environment check, headless import, validator triage, profile, token bridge,
  mapping preset, mode sheets, ScreenCreator "Existing UXML" hand-off. Every tool and menu it names is cited at UIToolkit v0.8.0.
- `scripts/ui/figma_env.py --project <p> [--json] [--probe-pipeline]`: read-only environment check (Unity, package
  source and version, helper, connector, Pipeline port without the token, Allow Browser Clients, validator CLI, dotnet);
  no network unless `--probe-pipeline`. Tested by `tests/ui-figma-env.test.sh`.
- `docs/architecture/ui-figma-real-test.md`: the real Figma-to-Unity "Game Settings" test procedure and evidence table.
```

## 7. Brief discrepancy (for the real test)

The brief's lab command `create-lab-project.py --package https://github.com/Cuvara/UIToolkit.git#v0.8.0` does not work
at v0.8.0: `--package` must be a local checkout (`read_package` opens `<checkout>/package.json`, `build_manifest`
writes `file:<abspath>`). The procedure exports the tag with `git archive` into a scratch folder instead and tells how
to switch the lab manifest to the git pin afterwards.

## 8. For Worker B (ui_plan.py)

`scripts/ui/figma_env.py` is importable: `figma_env.inspect(project, probe=False)` returns the report dict
(`schema: rpg-factory.figma-env/1`, `status`, `items[]` with `id/state/required/value/reason/fix`, `paths.package`,
`paths.figma_import`, `paths.validator_csproj`). It opens no socket unless `probe=True`.
