---
name: netcode-client
description: How the client networking in com.cuvara.netcode (Netcode repo) and its DOTS adapter actually work - the TCP gateway hop and KCP-only gameplay transport and their PlayerLoop pump, KcpCrypto versus the sealed session, codecs and the encoding sniffer, snapshot interning and merge, the interpolation clock, local movement prediction and reconciliation with clock steering, projectile prediction, reconnect policy, per-packet allocations, and the headless test project. Use when you write, debug, review or optimise netcode client code, prediction or interpolation, or answer how the client side of the wire behaves. Not for deciding scope, rules, checks or gates (unity-package, wire-contract, client-integration own those), not for wire.proto changes (wire-contract), and not for the server's transport (dotnet-gameserver).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Netcode client - transport, snapshots, interpolation, prediction

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `unity-package`, `wire-contract`, `client-integration` or `measure`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths are relative to the `Netcode/` repo unless prefixed `dots:` (`UnityDots/`) or `client:`
(`IndieRPGMMOAdventure/Assets/Scripts/`). This skill replaces the client's `unity-netcode` agent, which
predates the package and the KCP-only decision.

## Applies when / Not when

Applies: code under `Netcode/Runtime/**`, `Netcode/Tests*`, `dots:Runtime.Netcode*`, or the client's
input-send / session code, when you need to know what runs where and when. Not when: the question is
which module, contract, check or gate applies (lead skill), a `wire.proto` field (`wire-contract`), ECS
mechanics in general (`rpg-factory:unity-dots`), or server networking (`rpg-factory:dotnet-gameserver`).

## Scope

Repos `netcode`, `unitydots`, `client`. Owns no module, contract or check.

## Architecture

- **Two hops.** Gateway: `TcpTransport`, optional TLS with an exact-bytes certificate pin
  (`Runtime/Transport/TcpTransport.cs:30-37,286,322-337`). Gameplay: **KCP/UDP only** since 0.47.0; a
  join reply naming `tcp` or empty is refused (`CHANGELOG.md:7-10,28-30`). No WebGL gameplay
  (`Runtime/Transport/KcpTransport.cs:43-44`).
- **Pump.** `KcpTransport` reads with `UniTask.Delay(1, Realtime, PlayerLoopTiming.Update)` (`:221`) and
  runs the KCP update timer on the PlayerLoop too (`:313`): frame rate bounds receive latency and ARQ
  timing. `KcpClientSession` is Unity-free and takes one lock per public member (`KcpClientSession.cs:15-27`);
  its tuning must equal the server's (`:31-37`). `Kcp.cs` is a byte-compatible port of kcp-go (`:6-20`).
- **Crypto.** `KcpCrypto` is kcp-go AES-CFB with a CRC32 - confidentiality, **no integrity**
  (`Runtime/Transport/KcpCrypto.cs:8-22`). Authenticated encryption is the sealed session
  (`Runtime/Crypto/`: X25519 + HKDF + ChaCha20-Poly1305, Ed25519 server identity; BouncyCastle because
  IL2CPP lacks the primitives, `SealedCrypto.cs:15-28`).
- **Codec.** Protobuf default, JSON legacy; `EncodingSniffer` decides by the first byte (`{` JSON, `0x08`
  Protobuf, `Runtime/Codec/EncodingSniffer.cs:24-41`). Protocol range: `WireProtocolVersion.Current` and
  `MinimumServerVersion` (`Runtime/Protocol/WireProtocolVersion.cs:65,75`). `Generated/Wire.cs` is a byte
  copy of the server's (wire-contract).
- **Snapshots.** `SnapshotResolver` interns handles (`EntityHandleTable`) and aborts the whole snapshot on
  an unknown handle - the caller resyncs (`Runtime/Snapshot/SnapshotResolver.cs:13-29`). The field merge is
  `Shared.GameLogic`'s `SnapshotMerger`, behind `WorldState`, which is not thread-safe
  (`Runtime/World/WorldState.cs:9-37`). Into ECS: `dots:Runtime.Netcode/DotsEntityView.cs` only enqueues
  (`:20`; producer thread latched, `:59-68`); `NetworkViewCommandSystem` drains in `SnapshotApplyGroup` and
  drops commands from an older session generation (`dots:Runtime.Netcode/NetworkViewCommandSystem.cs:100,151,182`).
- **Interpolation.** One `InterpolationClock` per connection, in ticks, never snapped - only dilated
  within `MaxClockRateAdjust`, so `RenderTick` strictly increases (`Runtime/Interpolation/InterpolationClock.cs:26-33,164-182`).
  Defaults: `InterpolationConfig.Default` (`Runtime/Interpolation/InterpolationConfig.cs:142-157`). One
  evaluator for GameObject and ECS paths (`Documentation~/INTERPOLATION.md:13-15`); the ECS job is
  `dots:Runtime.Netcode/RemoteInterpolationJob.cs:49-66` (excludes the predicted entity).
- **Prediction.** `LocalMovePredictor` replays inputs through the shared `MovementSystem.TryMove` - the
  server's exact entry point, never a re-implementation (`Runtime/Prediction/LocalMovePredictor.cs:36-40`,
  `Documentation~/PREDICTION.md:48-49`). Movement only, on purpose (`PREDICTION.md:29-31`); projectiles via
  `ProjectilePredictor` (hits never predicted, `Runtime/Prediction/ProjectilePredictor.cs:81-82`). In ECS,
  `dots:Runtime.Netcode.Prediction/LocalPredictionSystem.cs` reconciles once per merged snapshot
  (`:183-239`): `SetServerSpeed`, then `PredictionClockSteering.SampleTickRate`/`OnSnapshot` (`:201-214`),
  then `Reconcile` (3D or 2D motor), then `Advance` every frame (`:262`).
- **Input.** One component owns input per scene: it samples, sends, and records the same tick on the
  predictor (`client:DI/Dots/DotsWorldBridge.cs:63-67,233-260`).
- **Reconnect.** `ReconnectPolicy` decides Never / Reconnect / ReconnectAfterDelay from the close reason
  (`Runtime/Client/ReconnectPolicy.cs:9-60`); a reconnect is a new session generation everywhere downstream.

## Idioms

- Anything order-dependent on the predictor (`RecordInput`, `Reconcile`, `Advance`) runs on the main
  thread, one predicted entity (`dots:Runtime.Netcode.Prediction/LocalPredictionSystem.cs:60-66`).
- Model selection is by protocol, not configuration (`PREDICTION.md:83`); a missing optional field means the
  old behaviour, not zero (`PREDICTION.md:181`).
- Interpolate by server tick, never by arrival time; out-of-order and duplicate ticks are rejected
  (`INTERPOLATION.md:19,39-40`).
- Unity-free code (`KcpClientSession`, `Kcp`, codecs, predictor) stays Unity-free so the headless suite
  can compile it (`KcpClientSession.cs:15-19`).

## Pitfalls

- **Per-packet allocations, no pooling anywhere** (no `ArrayPool` in `Runtime/`):
  `KcpCrypto.Seal` creates an RNG and a nonce array per datagram (`KcpCrypto.cs:84-85`);
  `KcpClientSession.cs:301,344,370`; `Kcp.cs:248-249,405-407,482,488,639`; `FrameBuffer.cs:107`;
  `SnapshotResolver.cs:85,240,250,267-269`; `client:DI/Dots/DotsWorldBridge.cs:241` (`new InputMessage` per send).
  Fixing them is a package change measured before and after (`measure`, GC alloc per frame).
- **Frame-rate-bound receive** (`KcpTransport.cs:221,313`): a client at 20 fps adds up to 50 ms before a
  snapshot is even read. Do not "fix" lag in interpolation/prediction tuning before ruling this out.
- **Hidden hard dependency:** the Runtime asmdef references `Shared.GameLogic` unconditionally
  (`Runtime/Cuvara.Netcode.Runtime.asmdef:6`) while `package.json` lists it only under
  `x-manualDependencies` (`package.json:29-30`). The consumer must install the SGL pin.
- **Dev auth fallback:** `NetworkBootstrap` mints an HS256 dev JWT when no `IAuthProvider` is registered and
  defaults to the JSON codec (`Runtime/Bootstrap/NetworkBootstrap.cs:125,136-162`). Never ship a scene relying on it.
- **Doc drift:** `PREDICTION.md:37-43` names `PredictAndSend`/`RenderPosition` (not in code);
  `INTERPOLATION.md:50-51,67` show old config names and an old `Advance` signature; `JsonWireCodec.cs:15`
  says JSON is the only encoding. Trust the code.

## Testing

- **Headless (no Unity):** `Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj` compiles the Unity-free
  Runtime sources and `Tests/Editor` files directly, with `SglDir` pointing at the server's
  `Shared.GameLogic` (`:20-29,37-129,86-90`). Factory runs it from a temp copy:
  `bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/netcode-headless.sh` (no in-place build: the repo has no `.gitignore`).
- **EditMode in Unity:** `Tests/Editor` (prediction: `LocalMovePredictorTests`, `PredictionHarness`,
  `Reconcile*Tests`; transport: `KcpCoreTests`, `KcpCryptoTests`, `SealedTransportTests`; `GoldenVectors.cs`
  compares SGL vectors bit for bit). Runs only inside the client project (gate `client-package-toggle`) or CI.
- **PlayMode** `Tests/Runtime` needs a live backend (`LiveBackend.cs:17-31`, `CUVARA_*` env) - external.
  `PredictionLatencyMeasurement.cs` is a `measure` harness.

## Tools

- `dotnet`: the headless suite (`netcode-headless.sh`); missing = NOT_AVAILABLE, CI `ci.yml` is the evidence.
- `unity-mcp`: Unity EditMode run of one fixture when the client Editor has the package; DOWN = CI.
- `lsp-csharp`: callers of a public netcode API across the package, `UnityDots/Runtime.Netcode*`, the client
  and the DOTS Sample copy (MISSING here: grep all four, then the headless build).
- `context-mode`: headless `.trx` / Editor logs - only counters and failures enter context (fallback: grep).
