### Added

- **VFX production architecture doc.** `docs/architecture/vfx-production.md` describes the chain from the vfx-style
  profile through textures, recipe, capture and vfx-lint to the human review and the `vfx-asset` record: which repo
  owns each leg and what stays `HUMAN_REQUIRED`. `docs/architecture/README.md` links it.
- **vfx-graph touchpoints.** `rpg-factory:vfx-graph` is named in the factory-core skill table, the skill-contract
  diagram, the README diagram, tables and counts, and `docs/architecture/overview.md`.
- **vfx-graph routing and dogfood coverage.** `tests/routing.test.sh` has scenarios for a UnityVFX recipe and `.vfx`
  build (unity-package leads, tech vfx-graph), an editor verb, runtime-only code (no vfx-graph) and an authoring
  `vfx/assets` path; `tests/fixtures/routing-golden.json` carries the new cases; `tests/dogfood.sh` gains the
  `tech-vfx` effect scenario; `evals/vfx-graph-effect/` adds a prompt and five graders.
- **Operating lesson.** `skills/factory-core/references/parallel-work.md`: a `terminal_handle_stale` answer from
  `orca terminal read` does not prove a task lead ended; check `orca orchestration worker-list --run <its run>` and
  the lead's own Run messages before dispatching a replacement lead.
- **Backlog.** `docs/plans/backlog.md` topic `vfx-graph-production-followups` lists ten follow-ups from the
  vfx-graph-production plan.

### Changed

- **unity-mcp used_by.** Registry dev tools `unity-mcp-cli` and `unity-mcp` list `vfx-graph` in `used_by`
  (`registry/core.json`, rebuilt `registry.json`);
  the `vfx-graph` Tools section names `unity-mcp`.
- **vfx-plan steps.** The recipe and capture steps name the `rpg-factory:unity-package` leg for a change to the
  `com.cuvara.vfx` package itself and `rpg-factory:vfx-graph` for authoring (`scripts/vfx/data/plan.json`).
- **Docs wording.** `docs/architecture/domains/vfx.md` names the input handoff `gameplay-event-to-vfx`;
  `commands/vfx-lint.md` examples use `vfx/style/`; `skills/vfx-graph/references/vfxgraph-review.md` names the
  `recipe_sha256` of `stats.json` correctly.

### Fixed

- **vfx-plan gameplay wording.** A request such as "shadow strike cooldown" or "increase the fire bolt damage" plans
  as `NOT_VFX`: the effect-noun pattern ignores a noun followed by a gameplay stat word. A positive control ("make a
  shadow strike") still plans as VFX (`tests/vfx-production.test.sh`).
- **pipeline.test.sh NOKILL.** The cleanup check matches only the word `kill` (word boundaries), so a checkout path
  such as `feat-skills-vfx-graph-touchpoints` no longer trips it.
