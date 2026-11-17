# Run report: owner-policy

Tier M plan, two tasks in one wave, on branch `owner-policy` (base `main` `4f53918`). It implements the two owner
decisions of 2026-11-17 recorded in backlog topic `policy-followups-leftovers`; the other items of that topic and the
low findings of this run stay there.

## Summary

- A plan may widen the model scope for itself (task `scope-widen`). New optional plan field `model_scope_widen`: a
  list of entries with `agent`, `model`, `efforts`, `basis` (`owner-approved` or `necessary`) and `reason`.
  `validate` rejects a malformed entry, an unknown agent, an unknown basis or an empty reason, and notes an entry
  that is already in scope. `validate`, `status` and `gate` list every widening of the plan, `dispatch` prints one
  line when it uses a widened model, subplan validation uses the widened scope, and the lead report template lists
  the widenings. The widening applies after the registry and the personal override; the personal override file may
  still only narrow. The registry profiles do not change, and `verdict --model` is untouched (it has no scope check).
  Documented in `docs/pipeline-cli.md` ("Model flags and runners") and in two sentences of
  `skills/delivery/references/delivery.md` section 10 (32746 bytes, under the 32768-byte cap; wording trimmed in the
  same section).
- The english-only advisories cover every rpg-factory checkout and each of its linked worktrees, wherever they are on
  disk (task `english-everywhere`). All three gaps named in the plan were real: the git guard gave no advisory in a
  plugin clone outside the workspace or a worktree of it (commit, gh, orca text and the Agent tool prompt), nor for a
  `git -C <clone>` command from a directory outside every scope; the file guard accepted the manifest of any plugin
  (too wide). One shared helper `workspace.plugin_checkout()` in `scripts/lib/workspace.py` recognises a checkout by
  its plugin manifest name, without a git call or a repository scan; both guards use it. The pure-ASCII fast path, the
  allowlists and the advisory wording are unchanged; an unrelated directory outside the workspace still gets no
  advisory.

Mode: implement. Model rule: the registry profiles, cross-model. Codex gpt-6.1-terra implements, Claude Opus 5.5 leads
and reviews. No model scope widening was used by this plan.

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| scope-widen | codex gpt-6.1-terra high (core, tests), claude-sonnet-5-5 high (docs) | claude-opus-5-5 medium review PASS; QA PASS recorded by the task lead from the task's checks | f9e694c | NOT_RUN (stopped for low memory); the task's checks passed (below) |
| english-everywhere | codex gpt-6.1-terra high | claude-opus-5-5 medium review PASS and QA PASS | 7ea150e | NOT_RUN (the verifier's shell timed out before the summary); the task's checks passed (below) |
| integration:plugin | - | QA PASS by the run lead (claude-fable-5-2) | 349538a | `tests/run-all.sh --workspace-only`: 24 checks, 24 passed, 0 failed, 0 skipped (1812s, `-j 1`) |

Checks the leads ran directly, one at a time:

- scope-widen at f9e694c: `tests/pipeline.test.sh --case model-policy` (with its dependency cases) 401/401,
  `tests/line-budget.test.sh` 7/7, `tests/parallel-policy.test.sh` 140/140, `tests/skills-lint.sh` 726/726,
  `tests/delivery-generic.test.sh` 47/47.
- english-everywhere at 7ea150e: `tests/file-guard.test.sh` 89/89, `tests/git-guard.test.sh` 666/666,
  `tests/hook-perf.test.sh` 27/27, `tests/workspace-default.test.sh` 84/84.

## Limitations

- Neither task ran its full tier command: the machine was short on memory (the scope-widen verify run was stopped by
  the harness with fork failures) and one verifier shell timed out. The whole pipeline suite and the wider affected
  set (59 of 77 suites for the workspace helper) are covered by CI only.
- A test run left by the released scope-widen verify session stayed alive and held a test slot during integration
  QA; the run lead did not start it and did not stop it (reported to the owner).
- The run lead's waiter was stopped once by the harness for low memory and was not restarted.
- Only absolute path tokens of a command are inspected by the git guard: a relative `git -C ../clone` from an
  unrelated directory stays without opinion, as before.
- Open minor findings of the scope-widen review, moved to the backlog: a malformed widening entry is reported twice
  by `validate`; `"model_scope_widen": null` passes `validate` while the schema requires an array; `status --json`
  prints the widening lines on stderr; the lead prompt loads the policy twice.
- Cost: NOT_AVAILABLE.
