# Architecture documentation

This directory contains accepted architecture decisions and plans for rpg-factory.

## Documents

- [Multi-discipline factory](multi-discipline-factory.md): domain ownership, routing, shared artifacts, approvals, and rollout phases.
- [Routing, handoffs and ownership](routing.md): entry points, dependency graphs, conflict rules and downstream invalidation.
- [UI skills](ui-skills.md): UI request planning, progressive skill loading, the five UI tech skills and their boundaries.
- [ADR 0001: Domains](adr/0001-domains.md): the registry and shared artifact contract decision.

## Conventions

- Write architecture documentation in English.
- Mermaid diagrams are allowed only in `docs/architecture/`.
- Keep one canonical copy of each fact; link to it from other documents.
- Name architecture decision records `adr/NNNN-<title>.md`.
