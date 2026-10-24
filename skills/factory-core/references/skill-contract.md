# Skill contract

Every rpg-factory skill **specialises** Factory Core's workflow. None of them replaces it. This
page is the contract that skill authors and skill runners follow.

## Layering

```
factory-core  - scope, baseline, branch, plan, implement, obligations, validate, verify, review, report
     │          (snapshot: modules, dependents, cross-repo dependents, contracts, suggested skills, gates)
     ├── cross-repo drivers  - wire-contract, pin-bump, measure
     │        own: ordering, contract evidence, hand-offs, human gates between legs, per-repo report
     └── repo skills         - server-realtime, server-services, server-ops, unity-package, client-integration
              own: implementation + validation inside one repo (one leg)
                   │
                   └── tech skills - dotnet-gameserver, go-backend, unity-client-tech, unity-dots, netcode-client
                            own: how a technology works in this workspace (never routed, loaded by
                            the skills in their used_by when the work needs it)
```

| Belongs in Core | Belongs in a specialised skill |
|---|---|
| snapshot, module resolution, dependents, contracts detection | domain architecture: where things live, how a feature is wired |
| workflow steps and result states | domain rules and review checklist |
| validation tiers, evidence rules, report template | the domain's validation delta: which extended/external checks matter and how to read their evidence |
| git safety and the guard | domain human gates (kubectl, toggling client packages, ...) |
| registry schema | registry *content* for its modules (`skills`, `rules`, `checks`) |

## What every skill must do

1. **Core first.** The first line of the body is:
   > **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.
   Skills never re-derive git state, modules, dependents or checks. They read the snapshot or run
   `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo <key> [--json] [--paths ...]`.
2. **Registry facts only.** Paths, commands, docs, changelogs and generated paths come from
   `registry.json`. The prose in SKILL.md explains *how to work*. It does not restate facts
   the registry holds. When you need a fact, query it with `jq`.
3. **Own only its domain.** Declare the repos and modules in scope. Anything outside that list
   is a hand-off to the owning skill (see `registry.skills`), not an edit.
4. **Declare the validation delta.** Say which extended and external checks the domain triggers
   and how to read their evidence. The fast tier is always Core's.
5. **Declare protected and generated paths.** Name each one and its generator.
6. **Declare human gates.** Use the registry `human_gates` plus any domain gates. Stop at each
   gate and ask the user.
7. **Produce domain evidence.** Examples: test counts, byte-identical diffs, pin agreement, a
   measurement with a control.
8. **No tag without release authorization.** Tags (`v*`, `sgl-v*`, `core-baseline-*`) are created by the
   lead; skills stop at **"ready to tag <repo> <version>"**. Only when the user explicitly authorizes the
   release in the current task does the agent tag and publish itself (`git-safety.md` rule 5).
   The guard flags `git tag <name>` and pushing tags (advisory `high`) either way.
9. **Never bypass Core.** This covers the baseline, the guard, and the report template.
10. **Never create another registry.** No feature lists, GDD state or task trackers. Feature and
    GDD lifecycle belongs to `game-ai-workflows`. Module knowledge belongs to `registry.json`.

## Tech skills

A repo skill says **where** a change goes and **which rules** apply. A tech skill says **how the
technology works here**: architecture that takes several files to understand, idioms the code
already uses, pitfalls with the file that proves them, how to run one test, and which dev tools help.

- Registry: `skills.<name>` = `{kind: "tech", repos, summary, order, used_by: [repo/cross-repo skills]}`.
  A tech skill owns no module or contract (`check-registry.sh` rejects it), so it is never lead, leg
  or follow-up. The snapshot lists it as `tech` in the routing line when a skill in `used_by` works on
  the change **and** the snapshot's repo is in the tech skill's `repos` (`routing.tech`): a measure run on
  the server lists `dotnet-gameserver`, not `unity-dots`.
- Every skill in `used_by` names `rpg-factory:<tech skill>` in its body (lint), at the step that needs it,
  as "invoke" (Skill tool) for implementing, debugging, reviewing and how-it-works/how-to-test questions.
- Below the prerequisite line a tech skill carries the guard `> **Supporting skill, never the owner:**
  invoke the lead ... first` (lint). Real sessions showed a model jumping straight to the tech skill,
  which holds the "how" answers, and skipping the lead, which holds the rules, gates and validation.
- It does not restate rules, checks or gates; those stay in the repo skill and the registry.
- Layout: the same frontmatter and prerequisite line; sections `Applies when / Not when`, `Scope`,
  `Architecture`, `Idioms`, `Pitfalls`, `Testing`, `Tools`. Same size limits as below.
- Facts: every architectural claim cites the repo file that shows it. Version-like values (language
  version, default rates, settings, package versions) are registry `facts[]` with a probe; API advice that
  depends on a package version names the fact (e.g. `entities-version`), never a remembered version.
- Every `## Pitfalls` bullet cites a file (`path:line` or a backticked path) or an issue (`#123`) that
  proves it (lint). A pitfall nobody can point at is an opinion.
- **Line citations are checked against the code** (`scripts/checks/skill-citations.py`). Form: a
  backticked `path:N`, `:N-M` or `:N,M-K`; a bare `` `:N` `` continues the last file named earlier in the same
  section (a heading resets it). Each one has an **anchor**: the symbol it shows, backticked, after the previous citation
  and before this one - `` `TickOnce` (`GameServer/Server/TickLoop.cs:510`) ``; the anchor's last segment
  must occur within the cited lines +/- 3 at the repo's integration branch. Paths resolve through
  registry `skills.<s>.cite_roots` (prefix -> `repo:subpath`; repo directory names are prefixes too).
  No anchor, a moved symbol or a line past the end fails `tests/run-all.sh`; `--suggest` prints the fix.
  Documentation files ending in `.md` (case-insensitive) must be cited by section name, not line; the checker rejects every `.md` line citation.
- Optional review file: `references/<area>-review.md`, a checklist factory-core step 11 applies when the
  skill is in `routing.tech` (e.g. `unity-dots` `references/ecs-review.md`).

## Learning loop

Knowledge enters the plugin only from a verified failure: reproduced, root-caused, fixed. The report's
**Lessons** section names where it went (`references/report.md`): a regression test in the product repo
(preferred - it cannot rot), a cited Pitfall in the owning tech skill, a registry `known_issues` entry, or
a `facts[]` entry with a probe. One place, never several. A later plugin task promotes proposed skill or
registry lines; `tests/facts.test.sh` and the citation lint keep them honest afterwards.

## Dev tools

Registry `dev_tools[]` lists the MCP servers, plugins and binaries a skill relies on, with probes,
`used_by`, `required` and a `fallback`. Every skill except `factory-core` (repo, cross-repo and tech) has
a `## Tools` section that names
the ids in whose `used_by` it appears and says for which step it uses each one; lint checks both
directions. The snapshot prints "Tools for this change" with each tool's state; when a tool is not OK,
use its fallback and say so in the report. `/rpg-factory:doctor` shows them all.

## SKILL.md layout (at most about 150 lines)

```markdown
---
name: <skill>
description: <semantic: the developer situation it applies to, and what it is NOT for>
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# <Skill title>
> **Prerequisite:** follow `rpg-factory:factory-core` ...
## Applies when / Not when
## Scope            (repos, registry module ids; hand-offs)
## Workflow delta   (only the steps that differ from or add to Core, numbered)
## Rules            (domain rules not already in registry module rules; cite the source doc)
## Generated & protected paths
## Validation delta (extended/external checks and their evidence)
## Human gates
## Review checklist
## Report additions (what the Core report must also contain)
```

`references/` is optional and holds at most 3 files, only for real domain content such as
architecture maps or procedures. Every fact in them must be checked against the repository
when it is written, and cite the file it came from.

**Descriptions must be semantic.** A good example: "Use when changing a network message,
protocol field, ...". A description that is only a list of keywords ("protobuf, redis") is not
allowed.

## Routing

`factory-context.sh --paths ...` prints the **routing** (lead, co-leads, legs, follow-ups) with a role per skill:

| Role | Comes from | Meaning |
|---|---|---|
| **lead** | the driver of a touched contract (cross-repo drivers always; repo-kind drivers when the contract **source** changed), otherwise the skills of touched modules | invoke it first; it owns ordering |
| **leg** | owners of a touched contract's other ends in this repo, owners of first-hop dependents when a cross-repo driver leads, owners of touched modules when a driver leads | runs inside the lead's workflow |
| **follow-up** | skills of cross-repo dependents and other-repo contract ends | later work in another repo; name it in the report |

Among several lead candidates exactly one becomes the **primary lead** (deterministic, from
`routing.precedence` in the JSON output):

| Class | Rule |
|---|---|
| 0 | a cross-repo contract driver (`wire-contract`, `pin-bump`) |
| 1 | a repo-kind contract driver whose contract **source** was touched |
| 2 | the primary owner of a touched module (first skill in its `skills` list) |
| 3 | a secondary owner |
| tie | lower `skills.<name>.order` (wire-contract 10 … measure 80) |

The other lead candidates become **co-leads**, run after the lead in that order (code before
deploy before measurement). **AMBIGUOUS** is printed only when the registry cannot order the
candidates; ask the user or pass `--lead <skill>` (rejected with exit 2 unless it is a candidate).
`--explain` prints why each registered skill was or was not selected. Files that match no module
map to the repo fallback `<repo>.root` (repo-level files); `X.meta` routes like `X`. The user can
always name a skill explicitly (`/rpg-factory:<skill>`). `tests/routing.test.sh` and
`tests/routing-properties.test.py` (real history: one lead, order-independent, no lead that is
also a follow-up) pin this behaviour.

## Composition (driver → legs)

- The driver plans the legs in contract order, for example server → netcode → client.
- For each leg, the driver invokes the leg's skill (Skill tool) with the leg's scope. The leg
  skill implements and validates in its repo, using `factory-context.sh --repo <key> --paths ...`,
  and returns its validation table.
- Between legs the driver checks **contract evidence**, for example that `Wire.cs` is
  byte-identical to the server copy, and stops at human gates such as tags.
- File ownership: every file maps to one module, and so to that module's skill. The driver
  itself edits only files that no leg owns. **Exception - contract co-edits:** a contract may
  carry a `co_edit` clause that names the exact lines another skill may touch in the same commit
  (e.g. `server-knobs`: `server-realtime` adds only the `env:` passthrough lines in compose/fleet
  manifests owned by `server-ops`). Nothing outside that clause.
- Conflicting rules: **the stricter rule wins**. Precedence when rules are equally strict:
  `global_rules` > `human_gates` > Core git safety > driver skill > leg skill > module rules.
- The final report is Core's template with **one validation table per repo** plus a
  **contract evidence** table.

## Extending the registry

- New module: add a `modules[]` entry with `skills`. Run `scripts/check-registry.sh`.
- New contract: add a `contracts[]` entry `{id, summary, source, copies, driver, gate, evidence}` and
  optionally `upstream` (where released versions come from), `watchers` (independent consumers) and
  `co_edit` (exact lines another skill may touch); only `source`/`copies` route.
  Every `path` must exist in its repo.
- New skill: add `skills.<name>` = `{kind, repos, summary, order}` (a free `order`; tech skills also
  `used_by`, and `cite_roots` when citations are not relative to the first repo's root) and
  `skills/<name>/SKILL.md`. The checker fails when either one exists without the other.
- New human gate: add `human_gates[]` `{id, rule, match?, decision?}`. When `match` (a Python
  regex) is present, the git guard returns a `warn` advisory (`high` when `decision` is `deny`) for Bash
  commands that match it inside the workspace. Hooks never ask or block (1.0.3).

After any change run `tests/run-all.sh`. It must report 0 failed.

## Coexistence

- **Product repos:** their own `.claude` assets stay where they are: the client's Unity-MCP
  tool skills (including the `profiler-*` point samples measure uses) and `verify-a-result`. Skills call
  them. They do not copy them. Netcode client knowledge lives in `netcode-client`; the client's old
  `unity-netcode` agent is retired.
- **`game-ai-workflows`:** independent. Factory never reads or writes `.ai/`, `docs/registry/`
  or `docs/features/`.
- **Review:** the built-in `/code-review` is the review step.
