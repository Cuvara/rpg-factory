# Routing, handoffs and ownership

Factory Core accepts three routing entry points:

- `--domain <id>` starts from an active domain's lead and registered artifact kinds.
- `--kind <artifact-kind>` resolves an artifact kind to its owning domain. Use `--lead` when a kind has more than one owner.
- `--repo <key> --paths <path...>` resolves registered module ownership and contract ends. Paths in an authoring repo show downstream handoff follow-ups from the source contract.

## Dependency graph

Handoff contracts are entries in `registry.json` with `kind: "handoff"`. Their source belongs to the upstream domain lead; `copies` lists the downstream repository/module or authoring path ends. The owning domain lists the contract id in `domains.<id>.handoffs`. Run `scripts/factory-context.sh --domain <id> --graph` to print a stable topological order. Cycles are reported as a path and exit with status 3.

For example, `feature-spec-to-impl` connects `authoring:design/features/` to the server and client repositories. Routing a feature spec reports those downstream ends as follow-ups, while routing a downstream path reports the source lead and the upstream end.

## Ownership conflicts

Non-fallback modules in different domains may not claim the same path or an ancestor/descendant path in the same repository. The declared fallback module is excluded because it intentionally catches otherwise unmapped paths. Artifact kinds must be unique across domains so `--kind` has a single owner. `check-registry.sh` checks these rules and verifies that a handoff source resolves to a module in the driver's domain.

If one `--paths` set selects leads from multiple domains, context reports `AMBIGUOUS` with each lead and its routing reasons and exits 3. Pass `--lead <skill>` to select the responsible lead explicitly.

## Invalidation and traceability

An engineering `impl` trace for a handoff records `repo`, `ref`, `kind: "impl"`, and `spec_rev`, the source feature specification's blob revision used for implementation. Trace bookkeeping and lifecycle status changes do not alter the implemented specification payload; edits to its content do. `artifact-trace.py` reports `FAIL downstream-stale <artifact> impl <repo>@<ref>` when the recorded revision no longer matches that payload. A fresh implementation trace must point at the current spec revision. Approval checks remain bound to the exact artifact blob revision, so changing the artifact also makes the previous approval `HUMAN_REQUIRED`.

Release completion requires current approvals, implementation and test coverage for each test acceptance criterion, and a release trace to a commit in the downstream repository. The artifact lifecycle checks those states together with the ordinary run-checks results.
