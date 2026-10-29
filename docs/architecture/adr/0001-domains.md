# ADR 0001: Domains in the factory registry

## Context

rpg-factory routes engineering work through a flat registry of skills, modules, repositories, and contracts. The factory needs to support additional disciplines, authored artifacts, and cross-domain handoffs while preserving existing routing and engineering ownership.

## Decision

Keep the registry flat and add domain metadata. Domains describe their leads, artifact kinds, repositories, allowed authoring paths, quality gates, handoffs, and feature-state ownership. Use one shared artifact contract for identity, lifecycle, upstream revisions, trace links, and approvals across domains.

## Consequences

- Existing skill, module, and contract lookups remain flat; domain metadata extends the existing model.
- The core routes and coordinates domains from registry data instead of embedding discipline-specific rules.
- Shared artifact checks can validate design documents, UI specifications, and asset manifests through the same lifecycle and trace model.
- Domain-specific quality gates and authoring paths remain declared in registry data.
