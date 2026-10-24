---
name: netcode-client
description: How the client networking in com.cuvara.netcode (Netcode repo) and its DOTS adapter actually work - the TCP gateway hop and KCP-only gameplay transport and their PlayerLoop pump, KcpCrypto versus the sealed session, codecs and the encoding sniffer, snapshot interning and merge, the interpolation clock, local movement prediction and reconciliation with clock steering, projectile prediction, reconnect policy, per-packet allocations, and the headless test project. Use when you write, debug, review or optimise netcode client code, prediction or interpolation, or answer how the client side of the wire behaves. Not for deciding scope, rules, checks or gates (unity-package, wire-contract, client-integration own those), not for wire.proto changes (wire-contract), and not for the server's transport (dotnet-gameserver).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/netcode-headless.sh:*)
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
  (`PinValidator`, `Runtime/Transport/TcpTransport.cs:30-37,286,322-349`). Gameplay: **KCP/UDP only** since
  0.47.0 (`KcpTransport`, `CHANGELOG.md:375-380`). A join reply naming `tcp` or empty is refused (`TransportKinds.ParseGameplay`, `Runtime/Transport/TransportKinds.cs:29-52`); only KCP passes (`TransportKinds.RequireGameplay`, `Runtime/Transport/TransportKinds.cs:62-70`). No WebGL gameplay: the constructor throws `NotSupportedException`
  (`Runtime/Transport/KcpTransport.cs:43-44`).
- **Pump.** `KcpTransport` reads with `UniTask.Delay(1, Realtime, PlayerLoopTiming.Update)`
  (`Runtime/Transport/KcpTransport.cs:248`) and runs the KCP update timer on the PlayerLoop too
  (`KcpClientSession.TuningInterval`, `:388`): frame rate bounds receive latency and ARQ timing.
  `KcpClientSession` is Unity-free and takes one lock per public member (`KcpClientSession.cs:16-32`);
  its tuning must equal the server's `KcpTuning` (`:34-42`). `Kcp` is a byte-compatible port of kcp-go
  (`Runtime/Transport/Kcp.cs:6-22`).
- **Crypto.** `KcpCrypto` is kcp-go AES-CFB with a CRC32 - confidentiality, **no integrity**
  (`Runtime/Transport/KcpCrypto.cs:8-22`). Authenticated encryption is the sealed session
  (`Runtime/Crypto/`: X25519 + HKDF + ChaCha20-Poly1305, Ed25519 server identity; BouncyCastle because
  IL2CPP lacks the primitives - no `ChaCha20Poly1305`, `SealedCrypto.cs:15-32`).
- **Codec.** Protobuf default, JSON legacy; `EncodingSniffer` decides by the first byte (`{` JSON, `0x08`
  Protobuf, `Runtime/Codec/EncodingSniffer.cs:24-41`). Protocol range: `WireProtocolVersion.Current` and
  `MinimumServerVersion` (`Runtime/Protocol/WireProtocolVersion.cs:65,75`). `Generated/Wire.cs` is a byte
  copy of the server's (wire-contract).
- **Snapshots.** `SnapshotResolver` interns handles (`EntityHandleTable`) and aborts the whole snapshot on
  an unknown handle - the caller resyncs (`Runtime/Snapshot/SnapshotResolver.cs:13-29`). The field merge is
  `Shared.GameLogic`'s `SnapshotMerger`, behind `WorldState`, which is not thread-safe
  (`Runtime/World/WorldState.cs:9-37`). Into ECS: `dots:Runtime.Netcode/DotsEntityView.cs` only enqueues for
  `NetworkViewCommandSystem` (`:20-21`); the first caller thread is latched as the producer and any
  other thread gets `InvalidOperationException` (`:59-68`). `NetworkViewCommandSystem` drains in `SnapshotApplyGroup` and
  drops commands from an older session generation (`dots:Runtime.Netcode/NetworkViewCommandSystem.cs:100,151,182`).
- **Interpolation.** One `InterpolationClock` per connection, in ticks, never snapped - only dilated
  within `MaxClockRateAdjust`, so `RenderTick` strictly increases (`Runtime/Interpolation/InterpolationClock.cs:26-33,164-182`).
  Defaults: `InterpolationConfig.Default` (`Runtime/Interpolation/InterpolationConfig.cs:142-157`). One
  evaluator, `SnapshotInterpolation.Evaluate`, for GameObject and ECS paths (`Documentation~/INTERPOLATION.md`
  "How it works"); the ECS job excludes the predicted entity (`PredictedTransform`,
  `dots:Runtime.Netcode/RemoteInterpolationJob.cs:49-66`).
- **Prediction.** `LocalMovePredictor` replays inputs through the shared `MovementSystem.TryMove` - the
  server's exact entry point, never a re-implementation (`Runtime/Prediction/LocalMovePredictor.cs:36-40`,
  `Documentation~/PREDICTION.md` "Replay through Shared.GameLogic"). Movement only, on purpose
  (`PREDICTION.md` "LocalMovePredictor"); projectiles via `ProjectilePredictor` (hits never predicted, they
  arrive as `GAME_EVENT_TYPE_PROJECTILE_HIT`, `Runtime/Prediction/ProjectilePredictor.cs:81-82`). In ECS,
  `dots:Runtime.Netcode.Prediction/LocalPredictionSystem.cs` reconciles once per new `WorldState.Tick`
  (`:183-239`): `SetServerSpeed`, `PredictionClockSteering.SampleTickRate`/`OnSnapshot`, and
  `Reconcile` (3D or 2D motor, `:208-242`), then `Advance` every frame (`:269`).
- **Input.** One component owns input per scene: it samples, sends, and records the same tick on the
  predictor (`RecordInput`, `client:DI/Dots/DotsWorldBridge.cs:63-67,233-260`).
- **Reconnect.** `ReconnectPolicy` decides Never / Reconnect / ReconnectAfterDelay from the close reason
  (`Runtime/Client/ReconnectPolicy.cs:9-60`); a reconnect is a new session generation everywhere downstream.

## Idioms

- Anything order-dependent on the predictor (`RecordInput`, `Reconcile`, `Advance`) runs on the main
  thread, one predicted entity (`dots:Runtime.Netcode.Prediction/LocalPredictionSystem.cs:60-66`).
- Model selection is by protocol, not configuration (`UseServerProtocol`, `PREDICTION.md` "3D movement:
  the character motor"); a missing optional field means the old behaviour, not zero (`PREDICTION.md`
  "Which history entry a snapshot describes: `ack_applied_tick`", "No field, no change").
- Interpolate by server tick, never by arrival time; out-of-order and duplicate ticks are rejected by
  `InterpolationRing.Accepts` (`INTERPOLATION.md` "Tick-based bracketing", "Buffer").
- Unity-free code (`KcpClientSession`, `Kcp`, codecs, predictor) stays Unity-free - no `UnityEngine` - so
  the headless suite can compile it (`KcpClientSession.cs:16-20`).

## Pitfalls

- **Per-packet allocations, no pooling anywhere** (no `ArrayPool` in `Runtime/`):
  `KcpCrypto.Seal` creates an RNG and a nonce array per datagram (`KcpCrypto.cs:89-90`);
  fresh arrays filled by `Buffer.BlockCopy` (`KcpClientSession.cs:422-424,465-466,491-492`); `Segment` data and
  datagrams (`Kcp.cs:248-249,405-407,482,488,639`); frame bodies (`Buffer.BlockCopy`, `FrameBuffer.cs:107`);
  lists, stat arrays and `ToArray` (`SnapshotResolver.cs:85,240,250,267-269`); a new `InputMessage` per
  send (`client:DI/Dots/DotsWorldBridge.cs:246`).
  Fixing them is a package change measured before and after (`measure`, GC alloc per frame).
- **Frame-rate-bound receive** (`UniTask.Delay`, `KcpTransport.cs:248,378`): a client at 20 fps adds up to 50 ms before a
  snapshot is even read. Do not "fix" lag in interpolation/prediction tuning before ruling this out.
- **Hidden hard dependency:** the Runtime asmdef references `Shared.GameLogic` unconditionally
  (`Runtime/Cuvara.Netcode.Runtime.asmdef:6`) while `package.json` lists it only under
  `x-manualDependencies` (`Shared.GameLogic`, `package.json:29-30`). The consumer must install the SGL pin.
- **Dev auth fallback:** `NetworkBootstrap` mints an HS256 dev JWT when no `IAuthProvider` is registered and
  defaults to the JSON codec (`Runtime/Bootstrap/NetworkBootstrap.cs:125,136-162`). Never ship a scene relying on it.
- **Doc drift:** `PREDICTION.md` "Key methods" names `PredictAndSend` and a predictor `RenderPosition`
  (neither exists on `LocalMovePredictor`); `INTERPOLATION.md` "InterpolationConfig" lists `MaxSamples` /
  `ExtrapolationLimit` 0.0 (code: `RingCapacity`, `MaxExtrapolation` 0.050) and "InterpolationClock"
  shows an old `Advance(deltaTime, newestReceivedTick, secondsPerTick)` (code:
  `Advance(deltaSeconds, config)`); the `JsonWireCodec` remarks say JSON is the only encoding (`JsonWireCodec.cs:13-25`), but
  `ProtobufWireCodec` exists. Trust the code.

## Testing

- **Headless (no Unity):** `Tests~/Headless/Cuvara.Netcode.Tests.Headless.csproj` compiles the Unity-free
  Runtime sources and `Tests/Editor` files directly, with `SglDir` pointing at the server's
  `Shared.GameLogic` (`:20-29,37-129,86-90`). Factory runs it from a temp copy:
  `bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/netcode-headless.sh` (no in-place build: the repo has no `.gitignore`).
- **EditMode in Unity:** `Tests/Editor` (prediction: `LocalMovePredictorTests`, `PredictionHarness`,
  `Reconcile*Tests`; transport: `KcpCoreTests`, `KcpCryptoTests`, `SealedTransportTests`; `GoldenVectors.cs`
  compares SGL vectors bit for bit). Runs only inside the client project (gate `client-package-toggle`) or CI.
- **PlayMode** `Tests/Runtime` needs a live backend (`CUVARA_*` env, `LiveBackendConfig`, `LiveBackend.cs:17-31`) - external.
  `PredictionLatencyMeasurement.cs` is a `measure` harness.

## Tools

- `dotnet`: the headless suite (`netcode-headless.sh`); missing = NOT_AVAILABLE, CI `ci.yml` is the evidence.
- `unity-mcp`: Unity EditMode run of one fixture when the client Editor has the package; DOWN = CI.
- `lsp-csharp`: callers of a public netcode API across the package, `UnityDots/Runtime.Netcode*`, the client
  and the DOTS Sample copy (MISSING here: grep all four, then the headless build).
- `context-mode`: headless `.trx` / Editor logs - only counters and failures enter context (fallback: grep).
