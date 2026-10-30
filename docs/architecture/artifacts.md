# Shared artifact contract

## Lifecycle v2 and quality results

The common metadata supports `schema_version` 1 (legacy) and 2 (current), `authors`, `sources`,
`provenance`, `blocked_by`, `rejection`, and kind-specific `spec`. Register each kind schema under
`kind_schemas`; schemas live in `docs/schemas/kinds/`. Lifecycle requirements are data in
`artifact_lifecycles`. Canonical states are draft, proposed, reviewed, approved,
in-implementation, verified, released, rejected and blocked; deprecated and superseded are
terminal states where appropriate. Legacy `review` means proposed and emits a deprecation warning.

| State | Required evidence |
|---|---|
| proposed | Complete schema and acceptance criteria |
| reviewed | Independent record under `reviews/<id>/<blob-sha>-<reviewer-id>.json` |
| approved | Existing immutable signed approval gates, including `approval_when_binding` |
| in-implementation | Implementation trace |
| verified | Per criterion: tests need implementation and test trace; review needs a review record; measure needs an existing evidence reference |
| released | Release trace, reached through approved and verified |
| rejected | `rejection.reason`; recovery only to draft |
| blocked | Non-empty `blocked_by` and reason |

Review JSON identifies artifact and blob revision, reviewer `{kind,id}`, verdict, findings and date.
Review identity is derived from git: artifact authors are the commit author emails of every commit that touched the artifact (following renames), union the declared `authors[].id` values. A review counts only when the single commit that added its file has a different author email and `reviewer.id` exactly matches that email; later edits, renames or deletions invalidate it. The default `process` assurance relies on commit identities and the factory's dispatch discipline. An actor who controls git identities can bypass it. Binding decisions always need signed approvals; reviews never substitute for those approvals.

Lifecycle requirements default to `review_assurance: process`. Set `requirements.<state>.review_assurance` to `signed` for a state or kind that needs cryptographic reviewer identity. Signed reviews must verify with a key in that artifact domain's `reviewers` registry list; an empty list or untrusted signature yields `HUMAN_REQUIRED`, never `PASS`. Review assurance is reported as `process` or `signed`.
`artifact-quality.py` reports schema, lifecycle, dependencies, staleness, review/approval, and plugin
results as `rpg-factory.validation/1` JSON (`docs/schemas/validation-result.schema.json`). Domain
plugins are registered by `domains.<domain>.quality_plugin`, live under `scripts/checks/domains/`,
and expose `check(artifact, ctx) -> list[Result]`; `_api.py` defines the result and context contract.
To add a kind, add it to the domain `artifact_kinds`, declare its schema in `kind_schemas`, add a
lifecycle entry if needed, then add a domain plugin rule only when domain-owned quality logic exists.

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
