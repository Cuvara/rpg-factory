# Dependency-aware workflows

Write a JSON workflow spec with an `id`, `title`, `goal`, `targets`, and `existing` artifact IDs. Each artifact target names a registered kind, sources by artifact ID, and acceptance criteria. Engineering targets use `kind: "implementation"`, a registered `repo`, and repo-relative `paths`.

```json
{"id":"crafting","title":"Crafting","goal":"Add crafting","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["Recipe can be crafted"]},{"id":"server","kind":"implementation","repo":"server","paths":["backend/gameserver-dotnet/"],"sources":["design"],"acceptance":["Crafting is implemented"]}],"existing":[]}
```

Plan and inspect the resulting dependency waves:

```sh
python3 -B scripts/factory-workflow.py plan workflow.json --authoring /path/to/game-authoring
```

Dispatch nodes in wave order; independent nodes in a wave can run in parallel. Dispatch refuses a node with exit 2 until its dependencies are usable. The `print`, `orca`, and `agent` runners all include only artifact IDs and current blob revisions, output paths, allowed paths, checks, and acceptance criteria; they never paste artifact contents. Add `--json` to emit the dispatch contract as JSON. Contracts identify artifacts by ID and current working-tree blob revision. Run status as artifacts land, then produce the integrated report:

When artifacts already exist, their `upstream` and `sources` artifact IDs determine the wave order. Ordered domain handoff contracts provide fallback ordering for planned nodes without artifact references; they do not override the order recorded by written artifacts. A cycle in artifact references, or among contract-ordered planned nodes, is reported as `CYCLE`. Contracts with `ordering: "none"` remain synchronization links and never order waves.

```sh
python3 -B scripts/factory-workflow.py status workflow.json --authoring /path/to/game-authoring
python3 -B scripts/factory-workflow.py dispatch workflow.json --node design --authoring /path/to/game-authoring
python3 -B scripts/factory-workflow.py report workflow.json --authoring /path/to/game-authoring
```

Status reports each node's lifecycle (`missing`, `draft`, `proposed`, `reviewed`, `approved`, `in-implementation`, `verified`, `released`, `rejected`, `blocked`, `stale`, or `human-required`), ready nodes, stale upstream references, and downstream nodes to revalidate in wave order. A rejected artifact is recoverable by authoring a new draft revision, then proposing it again. An absent dependency blocks dispatch. Approval is verified from signed approval results returned by artifact quality; a missing trusted signature is `human-required` and cannot produce a complete report.

Reports include artifact revisions, quality checks, reviews, approval results, and engineering implementation trace entries checked against `--repos key=path` repositories. A report is complete only when every workflow node is `verified` or `released` and none is stale, blocked, or human-required. Output contracts are documented in `docs/schemas/workflow-{plan,status,dispatch,report}.schema.json`.
