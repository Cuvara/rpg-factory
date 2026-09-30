# Final report template

Every Factory task ends with this report. Keep the section order. Write "none" rather than
dropping a section. Every validation row needs a state from the result-state list, and
every `passed` needs evidence.

```markdown
## Summary
<1-3 sentences: what changed and why. Name the task.>

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
| Tier | Module | Check | Command (cwd) | Result | Evidence |
|---|---|---|---|---|---|
| fast | server.gateway | go-test | `go test ./... -v -race -timeout 60s` (backend/gateway) | passed | 42 discovered: 42 pass, 0 fail, 0 skip |
| fast | server.gameserver-dotnet | dotnet-test | `dotnet.exe test ...` | passed | Total 812: 790 pass, 0 fail, 22 skip (SkippableFact: no Redis) + verify-test-counters exit 0 |
| extended | server.integration-test | integration-e2e | `go test -tags integration ...` | not-run:needs-confirmation | trigger: redirect contract changed |
| external | server.* | ci | CI on PR | not-run:external | no PR opened (user did not ask) |

<!-- Cross-repo tasks (a driver skill ran): one Validation table PER REPO in leg order, plus: -->
## Contract evidence (cross-repo tasks only)
| Contract | End (repo:path) | State (changed / byte-identical / pending leg) | Evidence |
|---|---|---|---|

## Routing
- Lead skill: <skill> · legs run: <skills> · follow-ups left: <skill in repo> | none

## Verification notes
- Expected vs observed for any measured number.
- Zero readings proven able to be non-zero, or flagged.
- Anything that passed only because it selected nothing: none | <details>.

## Not done / risks
- <open items, extended/external checks still required, assumptions, questions>

## Git
- Commits: <sha subject | none - not requested>
- Push / PR: <url | none - not requested>
```

Rules:

- **Never** write "tests pass", "looks good", or "all green" without the counts in the table.
- If a fast check could not run, the task is not done. Say so in the Summary.
- Report pre-existing failures separately from failures your change introduced. Prove
  which is which by running the same check on the base commit in a separate worktree
  (server). Never stash the user's baseline to do it.
- Link CI runs by id or URL when you cite them.
