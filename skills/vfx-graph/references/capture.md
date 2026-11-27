# Sandbox run and deterministic capture

Source: UnityVFX `Documentation~/AUTHORING.md` sections "Sandbox" and "Agent interface: `Tools~/vfxcli.py`", and
`Documentation~/CAPTURE.md` (all sections); schema `Schemas~/vfx-capture.schema.json` (`cuvara.vfx-capture/1`).
Run everything from the UnityVFX repository root. Re-read CAPTURE.md when a value here looks off: it wins.

## The unity-mcp-cli sequence

```sh
python Tools~/setup-sandbox.py                        # links, local Unity-MCP config, NuGet state; prints JSON
OPEN="$(python Tools~/setup-sandbox.py --print-open-path)"
python Tools~/setup-sandbox.py --open                 # refuses a second editor of this clone; memory guard; waits for Unity-MCP
unity-mcp-cli status "$OPEN"                          # Unity is running (PID n), MCP server reachable
# prove the editor is the Sandbox: a script-execute that returns Application.dataPath and the process id
# must print <open path>/Assets and the PID status printed (write the input to a file, pass --input-file)
unity-mcp-cli run-tool rql-query "$OPEN" --input-file editor-state.json   # isCompiling, isUpdating false
python Tools~/vfxcli.py <verb> --json '<args>' [--out <file>]           # catalog, describe, build, ..., capture
python Tools~/setup-sandbox.py --close                # SaveAssets, normal quit of that PID, report exit code
```

- Never pass `Sandbox~` to `unity-mcp-cli`; `vfxcli.py --project Sandbox~` is fine (it resolves to the open path).
- `vfxcli.py` exit 3 means no usable editor: run what the message names (`setup-sandbox.py`), never another project.
- The user's game client editor also runs Unity-MCP on this machine: never open, drive or modify it.
- `SandboxSetup.Report()` through `script-execute` checks the project settings; `SandboxSetup.Apply()` repairs them.

## Capture inputs

| Argument | Default | Notes |
|---|---|---|
| `effect` | required | `.prefab` (one or more `VisualEffect`s) or `.vfx` |
| `seed` | 1234 | `startSeed` of every `VisualEffect`, `resetSeedOnPlay` off |
| `times` | 8 over `meta.duration_seconds` (1 s without a recipe) | at most 64 |
| `camera` | `gameplay` | `gameplay` (45 deg, 10 m), `close` (15 deg, 4 m), `side` (5 deg, 7 m from +X) |
| `lighting` | `dusk` | `day`, `dusk`, `night`; ACES, bloom, post exposure |
| `out` | `<project>/Captures/<effect>/seed-<seed>-<camera>-<lighting>` | gitignored; a folder Unity would import is refused |
| `delta_time`, `width`, `height`, `columns` | 1/60, 640, 360, 4 | |
| `probe_interval`, `settle_frames`, `max_seconds`, `timeout_seconds` | 0.05, 70 (min 62), 10, 900 | |
| `character`, `target_count`, `target_spacing`, `source_socket`, `target_socket` | none, 0, 3.5, `hand_r`, `chest` | a prefab path or `placeholder`; binds every `ChainLightningBinder` |

Use the camera, lighting and seed of the approved vfx-style profile's `capture` block: `vfx-lint`'s
`capture-conditions` row compares them with `stats.json` (`scripts/vfx/vfx_lint_rules.py` `rule_capture_conditions`).
A sample character is given by its Sandbox path (`Assets/Showcase/Characters/VfxTestCharacterMale.prefab`, or the
`Samples~/Showcase/...` path through `vfxcli.py`). For a lane use `gameplay` or `close`: `side` looks down the lane.

## How it runs

`VfxCli.Run("capture")` checks the arguments in edit mode, stores the job and enters play mode (a domain reload);
the job builds the stage (other loaded scenes' roots deactivated), sets `runInBackground` and `captureDeltaTime`,
holds the effect still for `settle_frames` at every sample and probe before reading counts, writes the files, leaves
play mode and only then writes the result. `vfxcli.py` waits for it (about 15 s for BurstQuads through the editor,
30 s in batch). The editor must be in edit mode, compiled, with no other capture; a script change during a capture
fails the job.

## Outputs and how to read them

- `frame-<t>.png` per sample (sRGB, after post), `contact-sheet.png` (sample order, left to right, top to bottom).
- `stats.json`: `effect` (project path), `recipe_sha256`, `seed`, `delta_time`, `camera`, `lighting`, `unity`,
  `vfx_graph`, `duration_seconds`, `alive` (`peak`, `samples[{t, count}]`), `bounds`, `systems[{name, capacity,
  peak}]`, `frames[{t, file, sha256, mean_luminance, max_luminance}]`, `contact_sheet`, `resolution`,
  `probe_interval`, `settle_frames`, and the optional `characters` (null without) and `binders` (empty without).

Reading order (CAPTURE.md "Reading the evidence"):

1. **Look at the contact sheet first:** does the effect read at gameplay distance, does colour change over life as
   intended, is it lost against the day backdrop or blown out at night?
2. `alive.peak` against `systems[].capacity`: a peak at capacity means dropped particles.
3. `alive.samples` against `meta.phases`, and `duration_seconds` against `meta.duration_seconds`; null duration means
   it did not end by `max_seconds` (looping) or never spawned.
4. `max_luminance` near 1: pixels at the top of the ACES curve (bright, bloomed). `mean_luminance` compares a frame
   with the empty stage (the last sample of a finished effect). HDR values of the graph are `inspect` `hdr_colors`.
5. `bounds` against the intended area (with `Manual` bounds it only repeats the box).
6. `recipe_sha256` must equal the current recipe's hash, or the evidence is of another recipe: rebuild and recapture.

## Determinism and limits

- Two captures with one seed must agree on the `alive` counts; equal PNG hashes are observed, not promised (GPU and
  driver; with characters the frames took one of two reproducible hash sets).
- Not measured: overdraw, draw calls, frame time - a human review item. The alive count of a system fed by GPU events
  is unreliable unless it stores `alive`. A peak shorter than `probe_interval` can be missed.
- A prefab plays with its own exposed values; scene references other than chain binders (meshes, skinned meshes,
  custom binders) are not set: the Showcase covers those for the person's Play-mode review.
