### Fixed

- **asset-gen.** comfy-mcp `fetch_outputs` also downloads the PreviewImage temp files into `<run>/outputs/` (the live
  end-to-end run on `staged-icon` fetched a 64 px preview next to the SaveImage output), so `finalize` defringed,
  embedded and graded the preview as a second deliverable and failed its size. `finalize` now runs a filter step first:
  every output that is not a SaveImage file of the rendered workflow moves to `<run>/previews/` (never overwritten,
  nothing deleted) and the step reports what it moved; a file without evidence stays and is named, and outputs that are
  all previews fail at filter. Runs whose outputs are all SaveImage files are unchanged.
- **asset-gen.** The fetched files are all renamed `<p8>_NNN.png` and the comfy-cli job state can stay `queued` with no
  outputs, so the free read-only `fetch_outputs` `url_only=true` result, saved as `<run>/fetch.json`, is the primary
  evidence of each file's source (output or temp); the job state is the fallback.
- **asset-gen.** `budget` counts deliverables only: a preview, in `outputs/` or `previews/`, never counts (a run with one
  SaveImage output and one preview uses 1, not 2), and `--json` reports the previews separately.
- **asset-gen.** The `gen-run-outputs` check fails a recorded output outside `outputs/`; `previews/` is never listed.

### Changed

- **asset-gen.** The `asset-gen` (step 6) and `comfyui` run sequences call `fetch_outputs` again with `url_only=true`
  right after the fetch and save its result verbatim as `<run>/fetch.json`; the domain doc states the observed
  PreviewImage behaviour and the `previews/` rule instead of calling it unverified.
