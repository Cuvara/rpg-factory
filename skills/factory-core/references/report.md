# Final report template

Every Factory task ends with this report. Keep the section order. Write "none" rather than
dropping a section. Validation rows come from `run-checks.py` output (copy its table; cite the evidence JSON path).
Every PASS needs the runner's evidence; states other than PASS stay as the runner reported them.
Before writing the table run `run-checks.py ... --status`: nothing you report as PASS may be STALE.

```markdown
## Summary
<1-3 sentences: what changed and why. Name the task.>
Mode: <analyze | plan | implement | validate | review | resume> (as declared with --mode)

## Scope
- Repo(s) / branch: <repo> on <branch> (created from <base> | existing)
- Modules touched: <ids>        Dependents validated: <ids | none>
- Files changed: <n> (<list or grouped list>)
- Baseline preserved: <yes - baseline paths untouched | no - explain>

## Obligations
- [x] CHANGELOG `<path>` [Unreleased] <Added|Changed|Fixed|...>
- [x] Docs `<path>` (or: not needed - <reason>)
- [ ] Generated artifacts / .meta / contract other side / version bump (state each or "n/a")

## Validation
Runner: `run-checks.py --repo <key> --paths ...` · `--status` at report time: <result of --status, e.g. all current or the STALE/NOT_RUN checks> · logs: `~/.local/state/rpg-factory/evidence/...`
| Tier | Check | Cwd | State | Evidence |
|---|---|---|---|---|
| fast | server.gateway:go-test | backend/gateway | PASS | <n> passed, <n> failed, <n> skipped |
| fast | server.gameserver-dotnet:dotnet-test | backend/gameserver-dotnet | PASS | Total <n>: <n> passed, <n> failed, <n> skipped (SkippableFact: no Redis) |
| extended | integration-e2e | backend/integration_test | HUMAN_REQUIRED | trigger: redirect contract changed; not approved |
| external | ci | - | HUMAN_REQUIRED | no PR opened (user did not ask) |

<!-- Cross-repo tasks (a driver skill ran): one Validation table PER REPO in leg order, plus: -->
## Contract evidence (cross-repo tasks only)
| Contract | End (repo:path) | State (changed / byte-identical / pending leg) | Evidence |
|---|---|---|---|

## Routing
- Lead: <skill> (basis: <lead_basis> | override `--lead`) · co-leads: <skills | none> · legs run: <skills>
- Follow-ups left: <skill in repo> | none · AMBIGUOUS resolved by: <user | --lead | n/a>

<!-- Only when work was delegated to workers (references/parallel-work.md); otherwise omit this section. -->
## Parallel work (when delegated)
| Task | Owner / agent | Worktree | Branch | Base | Candidate SHA | QA / review verdict | Integrated | Cleanup |
|---|---|---|---|---|---|---|---|---|

## Pending (cross-repo / release)
- `factory-status.py` pending items this task created or left: <item -> owning skill> | none
- Release state: <READY_TO_TAG repo vX.Y.Z (lead tags) | tagged vX.Y.Z + release URL (authorized in this task) | n/a>

## Verification notes
- Expected vs observed for any measured number.
- Zero readings proven able to be non-zero, or flagged.
- Anything that passed only because it selected nothing: none | <details>.

## Review
- `/code-review` and checklists applied: <lead checklist, tech review files | not run - trivial diff>
- Findings: <file:line - item - fixed | open> | none

## Lessons (only verified ones)
- <symptom -> root cause -> captured as: test <path> | Pitfall in <skill> | known_issue <id> | fact <id>> | none

## Not done / risks
- <open items, extended/external checks still required, assumptions, questions>

## Git
- Commits: <sha subject | none - not requested>
- Push / PR: <url | none - not requested>
```

Rules:

- **Never** write "tests pass", "looks good", or "all green" without the counts in the table.
- If a fast check is not PASS, the task is not done. Say so in the Summary.
- Report pre-existing failures separately from failures your change introduced. Prove
  which is which by running the same check on the base commit in a separate worktree
  (server). Never stash the user's baseline to do it.
- Link CI runs by id or URL when you cite them.
- A Lesson is a failure you reproduced and fixed, not a guess. Capture it in exactly one durable place:
  a regression test (preferred), a Pitfall line with its file in the owning tech skill, a registry
  `known_issues` entry (tooling or doc drift), or a `facts[]` entry with a probe (a value that moves).
  Propose skill or registry edits in the report; the plugin change is its own task.
