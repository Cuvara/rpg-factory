# ECS review checklist

Used by the review step (factory-core step 11) when `routing.tech` lists `unity-dots`. Each item names
the file that shows the expected shape. A finding cites the diff line and the item.

## Design
- [ ] The feature belongs in ECS: many homogeneous entities updated from data each frame. A
      request/response or one-off flow (inventory, login, menus) stays a VContainer service
      (SKILL.md "ECS or not").
- [ ] Authority unchanged: the client predicts only movement and projectiles
      (`Netcode/Documentation~/PREDICTION.md:29-31`); everything else is applied from snapshots.
- [ ] Hybrid traffic uses an existing seam (enqueue-only `DotsEntityView`, bridge system + presenter,
      view groups), not a new static or a `FindObjectOfType` from a system.

## Systems and order
- [ ] `[DisableAutoCreation]` + `[UpdateInGroup]` + installed by a bootstrap; the install test asserts
      `SystemOrderVerifier.Verify(world)` is empty (`UnityDots/Tests/Editor/DotsSimulationBootstrapTests.cs:43`).
- [ ] Ordering by `UpdateAfter`/`UpdateBefore` against siblings, not OrderFirst/OrderLast.
- [ ] `RequireForUpdate` for every singleton the system reads.

## Burst and jobs
- [ ] Unmanaged `ISystem`: `[BurstCompile]` on the struct and on `OnCreate`/`OnUpdate`; job structs too.
      A managed touch point is un-Bursted with the reason in the doc comment.
- [ ] No `Entities.ForEach`; `IJobEntity` unless per-chunk optional components justify `IJobChunk`.
- [ ] Schedule vs ScheduleParallel chosen from `ParallelScheduling`, or `Schedule` with a note.
- [ ] No new `Dependency.Complete()` / `CompleteDependency()` in `OnUpdate` without a reason in a
      comment and a ProfilerMarker around the managed part.

## Structural changes and memory
- [ ] Structural changes from jobs go through the package ECB singleton with `[ChunkIndexInQuery]`.
- [ ] No per-frame or per-snapshot `AddComponent`/`RemoveComponent` on the same entity; components that
      will be needed are added at spawn, toggles are enableable components (or the churn is measured).
- [ ] Allocator matches lifetime: Temp (one update), `WorldUpdateAllocator` (one frame), Persistent
      disposed in `OnDestroy` after `CompleteDependency()`.
- [ ] No managed allocation per frame in a system: no LINQ, closures, method groups as delegates,
      string formatting, `new` collections.

## Data
- [ ] Singleton writes compare before writing (change filters fire on any write).
- [ ] Components hold data only (no references to services); managed singletons only for managed bridges.

## Tests and evidence
- [ ] EditMode world test through the production bootstrap for a new system; behaviour asserted, not
      just "installs".
- [ ] A performance claim in the PR has a `measure` record (control + run id); otherwise it is removed.
