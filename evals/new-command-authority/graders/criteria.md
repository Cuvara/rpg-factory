---
type: llm
weight: 2
---

Places it in CommandRouter with an opcode in Shared.GameLogic GameplayOpcodes, TryRead + typed rejection, validation on server state (item owned, entity alive), admission rate limit, no client-supplied outcome, deterministic server-side effects, rejection and happy-path tests and the 0 B GameplayAllocationTests; names wire/SGL impact (opcode is shared -> SGL release + pin-bump follow-up); stops and asks for any gameplay number (despawn time, pickup range) instead of inventing it.
