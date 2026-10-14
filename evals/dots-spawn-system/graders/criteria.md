---
type: llm
weight: 2
---

Uses an unmanaged ISystem with [BurstCompile] on the struct and methods (or explains why a managed touch point stays un-Bursted), installs it through a bootstrap with [DisableAutoCreation]/[UpdateInGroup] and UpdateAfter ordering, does structural changes through the package DotsEndSimulationCommandBufferSystem singleton (ParallelWriter with [ChunkIndexInQuery]) or reuses TimeToLive, spawns with the full component set (no per-frame Add/Remove), picks Schedule vs ScheduleParallel from ParallelScheduling, never uses Entities.ForEach, adds an EditMode world test asserting SystemOrderVerifier is empty, and stops at ready-to-tag. Claims no performance number.
