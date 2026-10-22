---
type: llm
weight: 2
---

Routes to server-realtime first, then loads dotnet-gameserver; gives dotnet test GameServer.Tests --filter "FullyQualifiedName~...SnapshotAllocationTests" from backend/gameserver-dotnet (no [Trait] categories); says it guards the snapshot write path against allocations and does not cover input/combat (TickAllocationBench, BENCH_TICK=1); with the C# LSP missing, falls back to grep over GameServer/, GameServer.Tests/, Shared.GameLogic/ plus a build; claims nothing ran.
