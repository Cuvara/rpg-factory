# Gameplay systems map (server-authoritative)

Verified 2026-10-14 against rpg-mmo-server. Paths are relative to `backend/gameserver-dotnet/` unless
`backend/` is named. Every number in content is a placeholder pending design
(`backend/content/abilities.json:3` and siblings): the global rule `phase-plumbing-only` applies to any
new value. This page says where gameplay lives and how authority is enforced, not what the game is.

## Where each mechanic lives

| Mechanic | Rules (shared, deterministic) | Server execution | Client |
|---|---|---|---|
| Movement | `Shared.GameLogic/Systems/MovementSystem.cs`, `CharacterMotor.cs` | `Input/InputHandler.cs` (direction x speed x dt integrated server-side, `:662-664`) | predicted with the same `TryMove` (`rpg-factory:netcode-client`) |
| Melee / abilities | `Systems/CombatLogic.cs` (`ValidateAttack :59`, `InRange :76`), `Systems/AbilityLogic.cs` (`ValidateCast :85`, `CooldownUntil :269`) | `Gameplay/CombatResolver.cs` (`ApplyEffects :84`: damage / heal / apply_status) | displayed from snapshots and events |
| Projectiles | `Systems/ProjectileLogic.cs` | server entities (ADR-29); first-step rewind only (`Gameplay/GameplaySystems.cs:156-159`) | `ProjectilePredictor`, hits never predicted |
| Lag compensation | `Systems/HitboxHistory.cs` (`MaxRewindMs = 200`, `:38`) | rewind at `render_tick` | sends `render_tick` |
| Status effects | `Systems/StatusLogic.cs` (permille fixed point, `:138-140`) | stepped in the critical scope | caption only |
| Inventory / equipment | opcodes `Shared.GameLogic/Gameplay/GameplayOpcodes.cs:18-33` | `Commands/CommandRouter.cs` (pipeline `:121-233`, slots `:550-558`) | `InventoryService` (no optimistic state) |
| Loot | content `backend/content/loot.json` (server-only) | `CombatResolver.RollLoot :272`, SplitMix64 per (seed, tick, victim, i) `:286,343-351` | push 100 |
| Content | `Shared.GameLogic/Content/*Definition.cs`, `ContentValidation.Validate :46` | `GameServer/Content/ContentLoader.cs` (refuses to boot on invalid content, ADR-19) | `/content` fetch |
| Enemies / AI | - | `Scaffolding/EnemyAi*.cs`, `EnemyCombatSystems.cs` (scaffolding, `IEcsSystem`s) | snapshots |
| Persistence | - | `Persistence/AsyncSaver.cs` every 30 s (`Server/GameServer.cs:311`); migrations `Persistence/Migrations/` (server-services owns) | - |

Not present: quests, XP grant, NPC dialogue, PvP, bosses (`Snapshot/ReplicationImportance.cs:118`).
Adding one is a design decision first (game-ai-workflows), then plumbing here.

## Authority checklist for a new input or command

1. The client sends **intent**, never an outcome: a direction not a displacement, a target id not a damage
   value, an item id not an inventory state.
2. Decode with `TryRead`, reject malformed payloads with a typed error (`CommandRouter.cs:121`); for input,
   add a value to `Input/InputRejection.cs` with its `RejectionWeight` (Benign / LatencyExplicable / Forged,
   `:197-220`).
3. Validate on server state in the tick: entity alive, range checked **after** this tick's movement,
   cooldown in **ticks** (`InputHandler.cs:232,798-800`), never wall-clock.
4. Rate-limit at admission (`CommandRouter.cs:134-136` `TryAdmit`) and keep per-connection queues bounded.
5. Any randomness is a deterministic function of server state (the loot pattern), never `System.Random`
   on the tick.
6. Anti-cheat today **observes only** (`Input/InputAnomalyTracker.cs:6-9`, `Input/AttackRateAudit.cs:49-52`;
   "Observation only, no action taken", `Server/GameServer.cs:911-926`). A new check records into these;
   turning observation into kicks or bans is a gameplay decision with thresholds - stop and ask.
7. Tests: one rejection test per new reason, the happy path through `TickLoop.TickOnce()`, and
   `CoreV3/GameplayAllocationTests` still 0 B (a new branch must not allocate).

## Determinism (Shared.GameLogic, ADR-10)

- Allowed float ops: `+ - * /`, comparisons, `MathF.Min/Max/Abs/Sqrt`; transcendentals are banned
  because NativeAOT x64 and IL2CPP ARM64 may disagree (`backend/docs/ARCHITECTURE-DECISIONS.md:1105-1111`);
  round every intermediate to `float` (`:1113-1114`). Server-only code may use them (`Net/FacingCodec.cs`).
- Fixed-point integers for stat math (`StatusLogic.cs:138-140`).
- Enforced by the registry check `sgl-determinism` (fast tier), golden vectors on both sides, and review.

## Known structural debt (do not copy, do not "fix" in passing)

- Player input, movement, combat and statuses run inline in the tick body, not as declared `IEcsSystem`s
  (`Server/TickLoop.cs:525-532`): they get the critical-group timing but no per-system metric or
  `ComponentAccess`. Moving them is an architecture change (ADR-12/13 note) with a measure leg.
- Enemy targeting scans all players linearly per enemy (`Scaffolding/PlayerTargetBuffer.cs:108-130`),
  chosen deliberately because a grid query allocated per enemy per tick. At thousands of enemies it is a
  suspect for over-budget ticks - prove it with `TickBreakdownBench` before changing it.
