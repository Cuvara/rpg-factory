# Client profiling (frame time, GC, ECS)

Verified 2026-10-14 against IndieRPGMMOAdventure and the com.cuvara.* repos. Client measurement has
almost no instrumentation yet: one `ProfilerMarker` in all repos
(`UnityDots/Runtime.Netcode/NetworkViewCommandSystem.cs:115`), no `Unity.PerformanceTesting` use, and the
package's own rule is "profiler markers, allocation and queue metrics, then targeted optimisation against
a recorded baseline. No capacity claim before this" (`UnityDots/ROADMAP.md:88-89`). So most client
claims start with *adding the instrument*, then a record, then the run.

## What to measure

| Question | Metric | Instrument |
|---|---|---|
| Is a frame over budget? | CPU main-thread ms p50/p95/p99, GPU ms (Frame Timing Stats on) | `BenchmarkRecorder` (`Assets/Scripts/Benchmark/BenchmarkRecorder.cs`, `FrameSample.cs`) |
| Who pays inside the frame? | per-marker ms | `ProfilerMarker` around the suspect code + Profiler capture / `ProfilerRecorder` |
| GC pressure | GC alloc bytes per frame, GC count per minute | `ProfilerRecorder` on `GC Allocated In Frame`; `MemorySample.cs` |
| ECS cost | entity count, per-system ms, sync points (`Complete`) | markers in systems; Entities Systems window (Editor, human) |
| Network cost on the client | bytes/s in, snapshots/s, alloc per packet | `NetworkMetrics` (`Netcode/Runtime/Diagnostics/`), GC alloc per frame at fixed entity count |

Budgets: there is no recorded client frame budget yet. Do not invent one (no "must be < 16.6 ms" gate)
until a baseline run exists for the device class; then the budget is "no worse than baseline + stated
tolerance", with the tolerance taken from repeat variance.

## Marker conventions

- Name `Cuvara.<Area>.<Type>.<Op>` like the existing one (`Cuvara.DOTS.NetworkViewCommandSystem.Drain`).
- `static readonly ProfilerMarker`; `using (Marker.Auto())` around managed code; in Burst code use
  `ProfilerMarker` too (it is Burst-compatible) and keep it outside inner loops.
- Markers are cheap but not free: add them around a phase, never per entity.
- A marker added to measure is a package or client change routed through its owning skill; it may stay.

## Legs

1. **Point sample (cheap, never a baseline).** Unity MCP `profiler-get-script-stats`,
   `profiler-get-memory-stats`, `profiler-capture-frame` return single-frame snapshots
   (`IndieRPGMMOAdventure/.claude/skills/profiler-*/SKILL.md`). Use them to find a suspect, not to quote.
2. **Device benchmark (the client's recorded number).** `BenchmarkRecorder` in
   `Assets/Scenes/DeviceBenchmark.unity` - see `legs.md` "Client: device benchmark" for phases, overrides
   and validity rules. Stress population: `Assets/Scripts/Benchmark/Dots/DotsStressBenchmark.cs` (uses a
   prebuilt `EntityArchetype`, `:175`).
3. **Performance test (repeatable in CI later).** `com.unity.test-framework.performance` is resolved
   transitively (registry fact `perf-testing-version`); a test asmdef referencing `Unity.PerformanceTesting`
   can use `[Test, Performance]` + `Measure.Method(...).WarmupCount().MeasurementCount().Run()` or
   `Measure.Frames()`. Shape to copy: `UnityDots/Tests/Runtime/ParallelSchedulingBenchmark.cs` (warm-up,
   interleaved pairs, no timing asserts, bit-identical check). Report-only until 3 baseline runs show the
   spread; then a regression threshold may be proposed, never before.
4. **Multi-client** (`legs.md`): correctness of "A sees B", not frame time.

## Validity

- Editor numbers are not player numbers; Development builds are relative only (`docs/DEVICE-BENCHMARK.md`).
- Windows/Mono proves nothing about IL2CPP (client `CLAUDE.md` "Scripting backend"): a mobile claim needs
  an IL2CPP device run.
- Control = same build with the change behind a runtime flag, or the parent commit's build, same device,
  same session, interleaved. Thermal throttling: >10% p95 disagreement between repeats invalidates the pair.
- GC alloc per frame must be read at a steady entity count; spawning frames are a separate phase.
- Network-bound client effects (frame-rate-bound KCP pump, `rpg-factory:netcode-client`) need the server
  side held constant: same server build, same bot load.
