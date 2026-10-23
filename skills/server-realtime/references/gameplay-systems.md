# Gameplay systems map (server-authoritative)

Verified 2026-10-21 against rpg-mmo-server `origin/develop` @ e982a6d. Paths are relative to `backend/gameserver-dotnet/` unless
`backend/` is named. Every number in content is a placeholder pending design
(the `PLACEHOLDER` header, `backend/content/abilities.json:3`, and siblings): the global rule `phase-plumbing-only` applies to any
new value. This page says where gameplay lives and how authority is enforced, not what the game is.

## Where each mechanic lives

| Mechanic | Rules (shared, deterministic) | Server execution | Client |
|---|---|---|---|
| Movement | `Shared.GameLogic/Systems/MovementSystem.cs`, `CharacterMotor.cs` | `Input/InputHandler.cs` (`move_x`/`move_y` are a direction, x speed x dt integrated server-side, `:662-664`) | predicted with the same `TryMove` (`rpg-factory:netcode-client`) |
| Melee / abilities | `Systems/CombatLogic.cs` (`ValidateAttack :59`, `InRange :76`), `Systems/AbilityLogic.cs` (`ValidateCast :85`, `CooldownUntil :269`) | `Gameplay/CombatResolver.cs` (`ApplyEffects :84`: damage / heal / apply_status) | displayed from snapshots and events |
| Projectiles | `Systems/ProjectileLogic.cs` | server entities (ADR-29); first-step rewind only (`RewindTick`, `Gameplay/GameplaySystems.cs:155-158`) | `ProjectilePredictor`, hits never predicted |
| Lag compensation | `Systems/HitboxHistory.cs` (`MaxRewindMs = 200`, `:38`) | rewind at `render_tick` | sends `render_tick` |
| Status effects | `Systems/StatusLogic.cs` (permille fixed point; only the final speed scale is float, with `MovementSystem`'s casts, `:138-140`) | stepped in the critical scope | caption only |
| Inventory / equipment | opcodes `Inventory`..`InventoryChanged` `Shared.GameLogic/Gameplay/GameplayOpcodes.cs:18-33` | `Commands/CommandRouter.cs` (pipeline `OnRequest` to `ExecuteAsync` `:108-236`, slots `TryParseSlot` `:550-559`) | `InventoryService` (no optimistic state) |
| Loot | content `backend/content/loot.json` (server-only) | `CombatResolver.RollLoot :272`, SplitMix64 `LootRandom` per (seed, tick, victim, i) `CombatResolver.cs:286,343-351` | push 100 |
| Content | `Shared.GameLogic/Content/*Definition.cs`, `ContentValidation.Validate :46` | `GameServer/Content/ContentLoader.cs` (refuses to boot on invalid content, ADR-19) | `/content` fetch |
| Enemies / AI | - | `Scaffolding/EnemyAi*.cs`, `EnemyCombatSystems.cs` (scaffolding, `IEcsSystem`s) | snapshots |
| Persistence | - | `Persistence/AsyncSaver.cs` every 30 s (`SaveInterval`, `Server/GameServer.cs:322`); migrations `Persistence/Migrations/` (server-services owns) | - |

Not present: quests, XP grant, NPC dialogue, PvP, bosses (the unused `Pvp` / `Boss` / `Quest` importance factors, `Snapshot/ReplicationImportance.cs:114-119`).
Adding one is a design decision first (game-ai-workflows), then plumbing here.

## Authority checklist for a new input or command

1. The client sends **intent**, never an outcome: a direction not a displacement, a target id not a damage
   value, an item id not an inventory state.
2. Decode with `TryRead`, reject malformed payloads with a typed error (`GameplayErrors.InvalidPayload`, `CommandRouter.cs:187-190`); for input,
   add a value to `Input/InputRejection.cs` with its `RejectionWeight` (Benign / LatencyExplicable / Forged,
   `:237-260`).
3. Validate on server state in the tick: entity alive, range checked **after** this tick's movement,
   cooldown in **ticks** (`AttackCooldownTicks`, `InputHandler.cs:232,798-800`), never wall-clock.
4. Rate-limit at admission (`TryAdmit`, `CommandRouter.cs:134-138`) and keep per-connection queues bounded.
5. Any randomness is a deterministic function of server state (the loot pattern), never `System.Random`
   on the tick.
6. Anti-cheat today **observes only** (`InputAnomalyTracker` `Input/InputAnomalyTracker.cs:6-9,42`, `AttackRateAudit` `Input/AttackRateAudit.cs:49-55`;
   `LogWarning` "Observation only, no action taken", `Server/GameServer.cs:866-883`). A new check records into these;
   turning observation into kicks or bans is a gameplay decision with thresholds - stop and ask.
7. Tests: one rejection test per new reason, the happy path through `TickLoop.TickOnce()`, and
   `CoreV3/GameplayAllocationTests` still 0 B (a new branch must not allocate).

## Determinism (Shared.GameLogic, ADR-10)

- Allowed float ops: `+ - * /`, comparisons, `MathF.Min/Max/Abs/Sqrt`; transcendentals (`Sin`, `Atan2`, `Pow`) are banned
  because NativeAOT x64 and IL2CPP ARM64 may disagree (`backend/docs/ARCHITECTURE-DECISIONS.md:1105-1111`);
  round every intermediate to `float`, because `RyuJIT` and Unity's Mono JIT differ (`:1113-1117`). Server-only code may use them (`Net/FacingCodec.cs`).
- Fixed-point integers for stat math (64-bit permille; float only in the final speed scale, cast like `MovementSystem`, `StatusLogic.cs:138-140`).
- Enforced by the registry check `sgl-determinism` (fast tier), golden vectors on both sides, and review.

## Known structural debt (do not copy, do not "fix" in passing)

- Player input, movement, combat and statuses run inline in the tick body, not as declared `IEcsSystem`s
  (`Server/TickLoop.cs:525-532`): they get the critical-group timing but no per-system metric or
  `ComponentAccess`. Moving them is an architecture change (ADR-12/13 note) with a measure leg.
- Enemy targeting scans all players linearly per enemy (`TryNearest`, `Scaffolding/PlayerTargetBuffer.cs:108-135`),
  chosen deliberately because a grid query allocated per enemy per tick. At thousands of enemies it is a
  suspect for over-budget ticks - prove it with `TickBreakdownBench` before changing it.
