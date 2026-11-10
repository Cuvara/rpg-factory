# Run report: workflow-slim

Slim the plugin task workflow and close its gaps, from the 2026-11-10 audit of the core workflow (redundant text
loaded by every session, missing review checklist, base health, cost ledger, learning loop, tier XS).
Plan: `docs/plans/workflow-slim.json`. Integration branch `workflow-slim`, integrated HEAD `077b3c4`; main
(PR #93, plan plugin-qa-lean, 5e2c5da) merged in through task main-sync.

## Outcome

Sizes (bytes, base 8c8b3c9 -> integrated HEAD):

| File | Before | After |
|---|---|---|
| `.claude/CLAUDE.md` (auto-loaded by every session) | 23008 | 9110 |
| `skills/delivery/references/delivery.md` | 56018 (57813 on main 5e2c5da) | 32420 |
| `skills/factory-core/references/parallel-work.md` | 8666 | 4735 |
| `skills/delivery/SKILL.md` | 6312 | 5120 |
| `skills/factory-core/SKILL.md` | 13399 | 12745 |

Detail moved, not dropped: `docs/architecture/overview.md`, `docs/releasing.md`, `scripts/README.md` "Commands",
`docs/pipeline-cli.md`, `tests/README.md`.

- Worker prompts (implement, review, QA, verify) say the spec is complete; delivery.md only when blocked.
- `skills/factory-core/references/plugin-review.md`: the review checklist for this repo, named in plugin review prompts.
- Plan field `known_failing` (FAIL_AT_BASE in QA and verify) and a base CI hint on `dispatch --phase lead`.
- Run report: Cost table (NOT_AVAILABLE when unmeasured) and the learning-loop step (follow-ups to the backlog).
- Tier XS: a prose-only change within `pipeline.tiers.XS` is edited by the run lead, with one cross-model review
  and lead-run QA; `tier`, `validate`, `dispatch`, `status` and `gate` support it.
- Follow-ups: stale pointers to moved CLAUDE.md sections and to parallel-work.md for delivery policy; affected
  selection for `docs/architecture/overview.md` and `delivery.md`; release policy check reads `docs/releasing.md`.

## Sessions and verdicts

Codex was MODEL_UNAVAILABLE for the run (gateway 429 usage limit and 503 model_not_found for gpt-6.1-terra,
recorded with `agents --down codex`): implementers, reviewers and QA ran on Claude, and every review except the
prompts subtask pipeline-prompts is `SAME_MODEL (fallback: codex unavailable)`, recorded by dispatch.
Task leads: Claude Opus 5.5 medium.

| Task | Orca Run | Review | QA |
|---|---|---|---|
| slim-claude-md | run_f43fe1d3764a | PASS 3783a70 | PASS 3783a70 (519 passed, 0 failed) |
| dedupe-delivery | run_1f92695f3b58 | FAIL f3d9258, FAIL a84c47f, PASS bd67be4, FAIL 4a42681, PASS e353ade | FAIL bd67be4, PASS e353ade |
| prompts | run_ebc37f7ef1e6 | PASS 49ee21f (pipeline-prompts cross-model: Codex implemented) | PASS 49ee21f (343 passed, 0 failed) |
| base-health | run_dc09a9cc27f4 | PASS 865e421 | PASS 865e421 (342 passed, 0 failed) |
| report-loop | run_65ffdc95c701 | PASS 3937121 | PASS 3937121 (315 passed, 0 failed) |
| main-sync | run_4d1d007f3b39 | PASS dafa581 | PASS dafa581 (376 passed, 0 failed) |
| tier-xs | run_6f580f5e0b40 | FAIL c2fb5df, PASS 476d27d | PASS 476d27d (520 passed, 0 failed) |
| slim-followups | run_e920e028857f | PASS dfc65bb | PASS dfc65bb (520 passed, 0 failed) |
| final-pointers | run_211da4e2dded | FAIL 69501f8, PASS 732fba5 | PASS 732fba5 (520 passed, 0 failed) |

## Checks (integrated HEAD 077b3c4)

- final-pointers verify at 732fba5 (tree equal to the integrated HEAD except plan, backlog and this report): its
  change to `tests/affected.py` selects every suite: `tests/run-all.sh --affected`: 522 checks, 520 passed,
  0 failed, 2 skipped (release-only), live-workspace checks included.
- Run lead on 077b3c4: `tests/delivery-generic.test.sh` 47/47, `build-registry.py --check` OK, `changelog.py check`
  19 fragments, 0 problems.
- Not run: a separate integration QA session (`tests/run-all.sh --workspace-only`) on 077b3c4. The user asked to
  merge at once; the verify run above covered the same suites on the same tree content. CI on the PR is the full gate.

## Limitations

- No cross-model review in practice (Codex down), except one subtask.
- Report-loop's task QA missed the `delivery.md` size cap (affected selection did not map delivery.md to
  `delivery-generic`); the run lead caught it after integration, tier-xs fixed it and final-pointers fixed the map.
- The run lead committed an invalid plan for about a minute (exit code of grep, not validate); fixed in c088056.
- A worker ran `pkill -f skills-lint` and may have killed other sessions' runs; lesson added to CLAUDE.md.
- The run lead's waiter was stopped twice by Claude Code under memory pressure.

### Cost

| Task | Session role | Model | Effort | Tokens / cost | Source |
|---|---|---|---|---|---|
| all tasks | task lead, implementer, reviewer, QA | see Sessions | see Sessions | NOT_AVAILABLE | no usage reported through Orca |
| run lead (total) | run lead | claude-opus-5-5 | - | NOT_AVAILABLE | n/a |

## Cleanup

Task worktrees and branches of eight tasks removed after integration; final-pointers removed at merge. Every task
lead's workers released. Follow-ups: `docs/plans/backlog.md` topics workflow-slim-followups,
run-lead-waiter-reaped and plan-edit-commit-guard.
