# Run report: plugin-asset-gen-routing

Tier XS plan (one prose task, edited by the run lead). Fixes the only failing check left after the 1.9.1 release gate:
the dogfood scenario `asset-gen` failed with "expected comfyui not invoked". `tests/run-all.sh --release` had passed
530 of 530 on the 1.9.1 merge commit; `tests/dogfood.sh --installed` passed 25 of 28, and two of the three failures
(`art2d-foundation`, `package-propagation`) passed 3 of 3 on rerun (model variation).

## Outcome

- `skills/asset-gen/SKILL.md`: the instruction to invoke `rpg-factory:comfyui` lived only in step 1 of the workflow, so
  a `plan` or `analyze` task answered without it. The Prerequisite block (same line, the skill is at its 160-line cap)
  now asks for it first, in every mode. Fragment `changelog.d/asset-gen-comfyui.md` (### Fixed).
- Baseline: the same scenario failed on exports of v1.8.0 (3 of 3 runs) and v1.7.0 (2 of 3), so it is not a
  regression of the 1.9 line. On the fixed tree it passed 5 of 5.

## Sessions and verdicts

| Task | Review | QA |
|---|---|---|
| asset-gen-comfyui | codex: FAIL (candidate HEAD mismatch, rerun), FAIL (the run-lead plan file seen as scope), PASS 80be304 | tier XS, run lead: skills-lint 674/674, routing 122/122, changelog check OK, dogfood asset-gen 5/5 |

## Limitations

- The dogfood scenarios call a live model, so a scenario can vary between runs.
- Cost: NOT_AVAILABLE (no usage reported through Orca).

## Cleanup

No task worktree or task branch (tier XS). The integration branch `plugin-asset-gen-routing` is removed after merge.
