# Shared artifact contract

Artifacts are domain-owned records whose metadata can be checked without embedding discipline rules in Factory Core.
The JSON Schema is [artifact.schema.json](../artifact.schema.json). Markdown artifact files use strict JSON front matter:

```text
---json
{"id":"FS-crafting-001","kind":"feature-spec","domain":"design","status":"draft","title":"Crafting","upstream":[],"acceptance":[{"id":"AC1","text":"Crafting succeeds","verify":"test"}],"trace":[]}
---
```

The `---json` delimiter selects a small, unambiguous standard-library parser; YAML features, aliases and implicit scalar
conversions are not accepted. Asset manifest JSON uses the schema's asset definition and records a source URI and
revision or hash, license, provenance, and delivery repository path.

`registry.json` defines `artifact_lifecycles.default`, optionally overridden by an entry named for a kind. Each lifecycle
lists legal states, outgoing transitions, and per-state `needs_approval` gate ids and `needs_trace` kinds. A domain
registers its artifact kinds and human gate ids in `domains.<id>`. Quality gates remain ordinary registered checks;
the lifecycle refers to human approval gates only. New artifacts may start in any lifecycle state, while updates must
follow the transition table.

`artifact-lint.py <repo-dir> [--registry R]` validates metadata and transitions against `HEAD~1`. It reports each
artifact and a final tally. `artifact-trace.py <repo-dir> --registry R [--repos key=dir ...]` verifies upstream blob
revisions, trace commit existence, and status coverage. Every `test` acceptance criterion requires both `impl` and
`test` trace; a released artifact also requires `release` coverage. A handoff implementation trace records `spec_rev`,
the source spec blob revision. A later specification-content edit reports `downstream-stale` until implementation is
traced again; lifecycle status and trace bookkeeping changes preserve the implemented payload. Registry quality gates
can add checks for domain specific evidence without changing these shared checks.

Approvals are immutable JSON records at
`approvals/<artifact-id>/<gate>-<artifact-blob-sha>.json`, with `{artifact, gate, scope, rev, by, date}`. `scope` must
equal the artifact domain and the gate must appear in that domain's `human_gates`. The introducing commit must be signed
with an SSH key registered in `domains.<id>.approvers`; Git authorship is not identity proof. The verifier rejects
untrusted or revoked keys, signature or principal mismatches, stale revisions, changes/deletions/renames, shallow
clones, and AI agent co-author trailers. Any approval uncertainty prints `HUMAN_REQUIRED`; trace or schema failures
print `FAIL`. The initial production approver list is empty until the maintainer registers a key from an authorized
source.
