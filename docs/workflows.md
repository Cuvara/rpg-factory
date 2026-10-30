# Dependency-aware workflows

Write a JSON workflow spec with an `id`, `title`, `goal`, `targets`, and `existing` artifact IDs. Each artifact target names a registered kind, sources by artifact ID, and acceptance criteria. Engineering targets use `kind: "implementation"`, a registered `repo`, and repo-relative `paths`.

```json
{"id":"crafting","title":"Crafting","goal":"Add crafting","targets":[{"id":"design","kind":"feature-spec","sources":[],"acceptance":["Recipe can be crafted"]},{"id":"server","kind":"implementation","repo":"server","paths":["backend/gameserver-dotnet/"],"sources":["design"],"acceptance":["Crafting is implemented"]}],"existing":[]}
```

Plan and inspect the resulting dependency waves:

```sh
python3 -B scripts/factory-workflow.py plan workflow.json --authoring /path/to/game-authoring
```

Dispatch nodes in wave order; independent nodes in a wave can run in parallel. Dispatch prints a worker contract by default, or use `--runner orca` / `--runner agent` to format it for a runner. Contracts identify artifacts by ID and current blob revision. Run status as artifacts land, then produce the integrated report:

```sh
python3 -B scripts/factory-workflow.py status workflow.json --authoring /path/to/game-authoring
python3 -B scripts/factory-workflow.py dispatch workflow.json --node design --authoring /path/to/game-authoring
python3 -B scripts/factory-workflow.py report workflow.json --authoring /path/to/game-authoring
```

Approvals remain human decisions. Missing dependencies, failed quality, stale inputs, and missing approval evidence stay visible as blockers.
