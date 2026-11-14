# asset-gen hybrid and local live test runbook (RTX 5060 8 GB)

Status: UNTESTED

This is the whole status of the local and hybrid branch (the four `local-8gb` templates `hybrid-icon-ui`,
`hybrid-character`, `hybrid-environment` and `local-variation`, and the `--profile` routing). Nothing in this file was
run: no generation, no install, no download, no measurement. It holds no measured number and makes no pass claim. The
machine this file was written on resolves to `api-only` and cannot run it.

You (the owner) run it once on the Windows 11 machine with the NVIDIA RTX 5060 8 GB and 32 GB RAM, after the merge.
It is the document `docs/hardware.md` names as the only way an unverified figure there becomes verified. Fill the
results table (Results) and the evidence directory (Evidence) as you go; until a cell holds a real value it stays
`NOT_RUN`.

## Owner approval gates

An agent that helps you run this stops at each gate below and waits for your explicit yes in that step. Nothing here is
done by default:

| Gate | What it covers | Where |
| --- | --- | --- |
| G1 install | Installing a custom node pack (`install_node`, a manual `git clone` or `comfy node install`) | Prerequisites, step P6 |
| G2 download | Downloading or placing any model file (checkpoint, ControlNet, IPAdapter, CLIP vision, upscaler) | Prerequisites, step P7 |
| G3 update | Updating ComfyUI core or a pack (`update_comfyui`, `comfy update`, `comfy node update`), or restarting an instance for it | Never needed by this runbook; ask first if a step says it is |
| G4 cut-out weight | The first run of `InspyrenetRembg` downloads its InSPyReNet weight by itself (no download step in this repo, size unverified) in `hybrid-icon-ui` and `hybrid-character` | Template sections 1 and 2 |
| G5 generation | Every `run_workflow` call. A hybrid run spends one API image on the 9router gateway; `local-variation` spends none but still loads and runs the GPU model | Each template section, step 9 |

Never `confirm_spend` on your own: it is set only after your yes for that exact run, and only if `run_workflow` refuses
without it.

## Credentials

This runbook never prints, echoes, pastes or asks for a credential. The 9router image node reads its own base URL and
Authorization header at run time from the provider section the Codex config names; nothing here touches them.

- Do not run `env`, `printenv`, `set`, `cat ~/.codex/config.toml` or any dump of an MCP registration or node config.
- comfy-mcp `system_stats` returns `system.argv`, ComfyUI's full launch command line: read only the `devices` entries
  (`vram_total`, `vram_free`) and never paste the `system` block into a record.
- `fetch_outputs` with `url_only=true` returns URLs: if the result carries a host, a token or any credential-like
  string, do not paste it into the Evidence notes (the files themselves are credential-free).
- If a command prints something that looks like a secret, stop, do not copy it anywhere and rotate it.

## Placeholders

Same as `docs/plans/assetgen-workflows/e2e.md`:

- `assetgen.py` is `python3 -B scripts/assetgen/assetgen.py`, run from the plugin checkout in Git Bash (never WSL,
  never PowerShell 5.1 for anything that redirects output).
- `<A>` is an authoring directory: a game-authoring checkout with `assetgen/project.json` and an approved style lock, or
  a scratch directory when there is none (then `--style <id>` is required and no anchors exist, see section 4).
- `<run>` is `<A>/assetgen/runs/<slug>-001`. Slugs used below: `hy-icon`, `hy-char`, `hy-env`, `lv`.
- `<state dir>` is the Factory state dir (`scripts/lib/fstate.py`); `<evidence>` is
  `<state dir>/pipeline/assetgen-hybrid/e2e-local` (see Evidence).
- `$COMFY_URL` is the `url` that comfy-mcp `server_info` reports for the running local instance. Never assume a port.
- comfy-mcp rows give the tool and every argument passed; arguments not listed stay at their defaults.

## Prerequisites

Do these in order. Every step is read-only except P6 and P7, which are gated.

| Step | Command or tool | Expected, else stop |
| --- | --- | --- |
| P1 | `nvidia-smi` | Header shows driver and "CUDA Version: 12.8" or higher (a driver of about 570.x or newer); the GPU line names the RTX 5060 with 8 GB |
| P2 | `mkdir -p ~/.local/state/rpg-factory/assetgen` then `python3 -B scripts/comfy-desktop-setup.py --check --json > ~/.local/state/rpg-factory/assetgen/hardware-profile.json` | File written. Git Bash only: PowerShell 5.1 `>` writes UTF-16 or a BOM and the file becomes unreadable. Exit code 3 still writes a valid file; do not chain on it. Replace `~/.local/state/rpg-factory` when `RPG_FACTORY_STATE_DIR` or `XDG_STATE_HOME` is set (`docs/hardware.md`, "Saving the profile for --profile auto") |
| P3 | `python3 -B scripts/comfy-desktop-setup.py --check` (read-only) | The `gpu` row names the RTX 5060; the `torch` row shows a CUDA build 12.8 or newer with `sm_120`; the `profile` row says `local-8gb`. Anything lower (`local-4gb`, `api-only`) means stop: nothing below can run, see "When something fails" |
| P4 | With the Comfy Desktop instance's own Python (not the system Python; the `torch` row names the env it read): `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_capability(), torch.cuda.get_arch_list())"` | `torch.version.cuda` 12.8 or newer, capability `(12, 0)` and `sm_120` in the arch list; not a `+cpu` build |
| P5 | comfy-mcp `server_info` (no arguments); `nodes` `action="get"`, `name="NineRouterImage"` | ComfyUI running, `url` noted as `$COMFY_URL`, node present. Missing node or comfy-mcp: `rpg-factory:comfy-desktop-setup` |
| P6 | **G1.** `--check` rows `packs`: `comfyui_ipadapter_plus` (all four templates), `comfyui_controlnet_aux` (`hybrid-character`, `hybrid-environment`), InspyrenetRembg cut-out (`hybrid-icon-ui`, `hybrid-character`) | All present. A missing pack is listed with its id and you decide: install only with your yes, then restart the instance (Stop + Launch; custom nodes load only at start) and run P5 again |
| P7 | **G2.** `--check` rows `models`; compare with the Models and packs table of `docs/hardware.md` | All present under `<instance>/ComfyUI/models/<folder>/`: `sd_xl_base_1.0.safetensors` (checkpoints), `controlnet-canny-sdxl-1.0.safetensors` and `diffusers_xl_canny_mid.safetensors` (controlnet), `ip-adapter-plus_sdxl_vit-h.safetensors` (ipadapter), `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` (clip_vision), `4x-UltraSharp.pth` and `RealESRGAN_x4plus.pth` (upscale_models). A missing file is downloaded only with your yes; never substitute another file silently |
| P8 | `python3 -B scripts/assetgen/assetgen.py resolve --purpose icon --profile auto` | Prints `profile local-8gb [auto: ...]` and template `hybrid-icon-ui`. `api-only` means the saved file (P2) is missing or unreadable; fix it before going on. This command writes nothing (no `--out`) |

Also free: about 60 GB on the SSD (the check enforces 40 GiB) and no other GPU-heavy program running during a run, or the
VRAM figures you record are not the template's.

## Per-run procedure (the same for every template)

Each template section below fills in the placeholders of these ten steps with concrete commands. In every section,
`--profile local-8gb` is named wherever the tool accepts a profile.

1. `resolve` with `--profile local-8gb`, `--authoring <A>`, `--out <run>/spec.json`; read the summary (profile line,
   template, references = the selected anchors, warnings).
2. Write `<run>/prompt.md` (prompt text only; no text, logos or brands) from the purpose's guidance
   (`assetgen.py show --kind purpose <purpose> --authoring <A>`).
3. `render --run <run>`, then the prompt review (`review-cmd --phase prompt --run <run>`, run the printed command as
   printed; it contains no credential), then `render --run <run>` again so the prompt node shows the review state.
4. `graph-lint` on the template file and on the run, both with `--profile local-8gb`. Exit 1 means no `run_workflow`.
5. comfy-mcp `upload_file` for every file in `<run>/references/` (anchors and a base image), `overwrite=false`;
   the anchor `LoadImage` nodes name `anchor-<id>.png`, and a base image is passed by the name the upload returned.
6. comfy-mcp `validate_workflow`. Read `valid` and `spends_credits` and the `partner_nodes` list and write them down.
7. `budget --run <run>`. Exit 1 or `remaining 0`: stop and ask.
8. Start the VRAM log in a second Git Bash window (Recording, "Peak VRAM"), then ask for the gate.
9. **G5, owner's yes first.** `run_workflow` with `wait=false`, then `job` `action="wait"`.
10. `fetch_outputs`, `finalize`, `qa`, then record.

The 9router node is not a partner-API node: in the earlier live run of a staged template `validate_workflow` reported
`spends_credits: false` and `run_workflow` was not gated, although the gateway image costs credits. So a `false` for a
hybrid template does not mean free; the cost is one API image each and it still needs your yes. The only template that
must show `spends_credits: false` and no `NineRouterImage` node in the graph is `local-variation`.

## 1. hybrid-icon-ui

Purpose `icon` (also routed: `ui-element`). Run id `hy-icon-001`. Cost: one API image. G4 applies (cut-out weight on
first run).

| Step | Command or tool |
| --- | --- |
| 1 | `python3 -B scripts/assetgen/assetgen.py resolve --purpose icon --profile local-8gb --authoring <A> --out <run>/spec.json` (add `--style <style id>` when `<A>` has no `project.json`; run `mkdir -p <run>` first) |
| 2 | `<run>/prompt.md`: one game item icon, centered, transparent background, readable at 64 px |
| 3 | `python3 -B scripts/assetgen/assetgen.py render --run <run> --authoring <A> --param quality=low`; `python3 -B scripts/assetgen/assetgen.py review-cmd --phase prompt --run <run> --authoring <A>`, then the printed command as printed; `render` again with the same `--param` (quality `low` keeps the API image cheap; the template default is `auto`) |
| 4 | `python3 -B scripts/assetgen/assetgen.py graph-lint templates/assetgen/workflows/hybrid-icon-ui.json --profile local-8gb`; `python3 -B scripts/assetgen/assetgen.py graph-lint --run <run> --authoring <A> --profile local-8gb` |
| 5 | comfy-mcp `upload_file` `paths=[<run>/references/anchor-<id>.png, ...]` (absolute paths; one per selected anchor, none when `resolve` printed "references: none"), `overwrite=false` |
| 6 | comfy-mcp `validate_workflow` `workflow_path="<run>/workflow.json"` |
| 7 | `python3 -B scripts/assetgen/assetgen.py budget --run <run> --authoring <A>` |
| 8 | second window: VRAM log (Recording) |
| 9a | **G5 and G4: ask the owner.** comfy-mcp `run_workflow` `workflow_path="<run>/workflow.json"`, `wait=false` (`confirm_spend` only if it refuses without it and the owner said yes) |
| 9b | comfy-mcp `job` `action="wait"`, `prompt_id="<id from 9a>"`, `timeout_seconds=900` |
| 10a | comfy-mcp `fetch_outputs` `prompt_id="<id from 9a>"`, `out_dir="<run>/outputs"`; then again with `url_only=true` and save the result as `<run>/fetch.json` (see Credentials: no host or token in your notes) |
| 10b | `python3 -B scripts/assetgen/assetgen.py finalize --run <run> --authoring <A>` |
| 10c | `python3 -B scripts/assetgen/assetgen.py qa --run <run> --authoring <A>` |

The template saves one image (node 20, "Save final image") and shows previews of the base ("Preview API base"), the
refined image and a 64 px view; finalize moves the previews to `<run>/previews/`.

## 2. hybrid-character

Purpose `ref-3d-character` (also routed: `ref-3d-turnaround`, `sprite-2d`). Run id `hy-char-001`. Cost: one API image.
G4 applies. One Canny ControlNet is loaded (the template names `controlnet-canny-sdxl-1.0.safetensors`).

| Step | Command or tool |
| --- | --- |
| 1 | `python3 -B scripts/assetgen/assetgen.py resolve --purpose ref-3d-character --profile local-8gb --authoring <A> --out <run>/spec.json` |
| 2 | `<run>/prompt.md`: one game character, full body, neutral pose, plain background, no text |
| 3 | `python3 -B scripts/assetgen/assetgen.py render --run <run> --authoring <A> --param quality=low`; `python3 -B scripts/assetgen/assetgen.py review-cmd --phase prompt --run <run> --authoring <A>`, then the printed command as printed; `render` again with the same `--param` |
| 4 | `python3 -B scripts/assetgen/assetgen.py graph-lint templates/assetgen/workflows/hybrid-character.json --profile local-8gb`; `python3 -B scripts/assetgen/assetgen.py graph-lint --run <run> --authoring <A> --profile local-8gb` |
| 5 | comfy-mcp `upload_file` `paths=[<run>/references/anchor-<id>.png, ...]`, `overwrite=false` |
| 6 | comfy-mcp `validate_workflow` `workflow_path="<run>/workflow.json"` |
| 7 | `python3 -B scripts/assetgen/assetgen.py budget --run <run> --authoring <A>` |
| 8 | second window: VRAM log |
| 9a | **G5 and G4: ask the owner.** comfy-mcp `run_workflow` `workflow_path="<run>/workflow.json"`, `wait=false` |
| 9b | comfy-mcp `job` `action="wait"`, `prompt_id="<id from 9a>"`, `timeout_seconds=900` |
| 10a | comfy-mcp `fetch_outputs` `prompt_id="<id from 9a>"`, `out_dir="<run>/outputs"`; then again with `url_only=true` saved as `<run>/fetch.json` |
| 10b | `python3 -B scripts/assetgen/assetgen.py finalize --run <run> --authoring <A>` |
| 10c | `python3 -B scripts/assetgen/assetgen.py qa --run <run> --authoring <A>` |

## 3. hybrid-environment

Purpose `scene-2d` (also routed: `concept-2d`, `texture-tileable`). Run id `hy-env-001`. Cost: one API image. No cut-out
in this template, so no G4. One Canny ControlNet (`diffusers_xl_canny_mid.safetensors`), a 1536x1024 API base by default
(the gateway may return another size) scaled to 1024 px wide for the local stage.

| Step | Command or tool |
| --- | --- |
| 1 | `python3 -B scripts/assetgen/assetgen.py resolve --purpose scene-2d --profile local-8gb --authoring <A> --out <run>/spec.json` |
| 2 | `<run>/prompt.md`: one game environment scene, clear layout, no characters, no text |
| 3 | `python3 -B scripts/assetgen/assetgen.py render --run <run> --authoring <A> --param quality=low`; `python3 -B scripts/assetgen/assetgen.py review-cmd --phase prompt --run <run> --authoring <A>`, then the printed command as printed; `render` again with the same `--param` (the template default quality is `high`) |
| 4 | `python3 -B scripts/assetgen/assetgen.py graph-lint templates/assetgen/workflows/hybrid-environment.json --profile local-8gb`; `python3 -B scripts/assetgen/assetgen.py graph-lint --run <run> --authoring <A> --profile local-8gb` |
| 5 | comfy-mcp `upload_file` `paths=[<run>/references/anchor-<id>.png, ...]`, `overwrite=false` |
| 6 | comfy-mcp `validate_workflow` `workflow_path="<run>/workflow.json"` |
| 7 | `python3 -B scripts/assetgen/assetgen.py budget --run <run> --authoring <A>` |
| 8 | second window: VRAM log |
| 9a | **G5: ask the owner.** comfy-mcp `run_workflow` `workflow_path="<run>/workflow.json"`, `wait=false` |
| 9b | comfy-mcp `job` `action="wait"`, `prompt_id="<id from 9a>"`, `timeout_seconds=900` |
| 10a | comfy-mcp `fetch_outputs` `prompt_id="<id from 9a>"`, `out_dir="<run>/outputs"`; then again with `url_only=true` saved as `<run>/fetch.json` |
| 10b | `python3 -B scripts/assetgen/assetgen.py finalize --run <run> --authoring <A>` |
| 10c | `python3 -B scripts/assetgen/assetgen.py qa --run <run> --authoring <A>` |

## 4. local-variation

Purpose `prop-2d`, template chosen with `--template local-variation` (no purpose is routed to it, so routing needs
the flag; `image-edit` works the same way). Run ids `lv-001` and, for the comparisons, `lv-002` and `lv-003`.
Cost: none. No API call, no `NineRouterImage` node, no credit.

It needs an approved base image. Use the "Preview API base" file from section 1: after `hy-icon-001`'s finalize it sits in
`<run of hy-icon-001>/previews/` (find which file it is with comfy-mcp `job` `action="status"`,
`prompt_id="<id of hy-icon-001>"`: node 16 is "Preview API base"). Copy it to `<run>/references/base.png` and use `base.png`
as the name. Any other base PNG you have the right to use works too.

| Step | Command or tool |
| --- | --- |
| 1 | `python3 -B scripts/assetgen/assetgen.py resolve --purpose prop-2d --template local-variation --profile local-8gb --authoring <A> --out <run>/spec.json` |
| 2 | `<run>/prompt.md`: the base's subject, same item, new variation, no text |
| 3a | comfy-mcp `upload_file` `paths=[<run>/references/base.png]`, `overwrite=false`; note the name it returns (`<base name>`) |
| 3b | `python3 -B scripts/assetgen/assetgen.py render --run <run> --authoring <A> --param reference_image=<base name> --param seed=1`; `python3 -B scripts/assetgen/assetgen.py review-cmd --phase prompt --run <run> --authoring <A>`, then the printed command as printed; `render` again with the same `--param` flags |
| 4 | `python3 -B scripts/assetgen/assetgen.py graph-lint templates/assetgen/workflows/local-variation.json --profile local-8gb`; `python3 -B scripts/assetgen/assetgen.py graph-lint --run <run> --authoring <A> --profile local-8gb` |
| 5 | comfy-mcp `upload_file` `paths=[<run>/references/anchor-<id>.png, ...]`, `overwrite=false` (none when there are no anchors) |
| 6 | comfy-mcp `validate_workflow` `workflow_path="<run>/workflow.json"`: `spends_credits` must read false and `partner_nodes` must be empty. Anything else: do not run, see "When something fails", row "local-variation shows spends_credits true" |
| 7 | `python3 -B scripts/assetgen/assetgen.py budget --run <run> --authoring <A>` |
| 8 | second window: VRAM log |
| 9a | **G5: ask the owner** (no credit, but the GPU model runs). comfy-mcp `run_workflow` `workflow_path="<run>/workflow.json"`, `wait=false` |
| 9b | comfy-mcp `job` `action="wait"`, `prompt_id="<id from 9a>"`, `timeout_seconds=900` |
| 10a | comfy-mcp `fetch_outputs` `prompt_id="<id from 9a>"`, `out_dir="<run>/outputs"`. Before finalize copy the fetched files to `<evidence>/lv-001-raw/` and run `sha256sum` on them (fixed-seed repeat, below) |
| 10b | `python3 -B scripts/assetgen/assetgen.py finalize --run <run> --authoring <A>` |
| 10c | `python3 -B scripts/assetgen/assetgen.py qa --run <run> --authoring <A>` |

Because it costs nothing, `local-variation` is where the repeat and anchor comparisons run (Recording).

## Recording

For each template record the items below in the results table. Write the value and the command or file it came from;
leave `NOT_RUN` where you did not do it.

**Peak VRAM.** In a second Git Bash window, before step 9a (start it, let it log idle for a few seconds, then run):

    mkdir -p "<evidence>/<run id>"
    nvidia-smi --query-gpu=timestamp,memory.used,memory.total --format=csv -l 1 > "<evidence>/<run id>/vram.csv"

Stop it with Ctrl+C after `job` reports the run finished. Peak and idle baseline, in MiB:

    tail -n +2 "<evidence>/<run id>/vram.csv" | awk -F', ' '{gsub(/ MiB/,"",$2); if (NR==1||$2+0<lo) lo=$2+0; if ($2+0>hi) hi=$2+0} END{print "idle-min " lo " MiB, peak " hi " MiB"}'

Alternatively poll comfy-mcp `system_stats` during the run and read only `devices[].vram_total` and `devices[].vram_free`
(never `system`). Record the peak used, the baseline, and the template's declared `requires.peak_vram_gb` (7.0, a planning
declaration) next to it. A CUDA out-of-memory error counts as the first failure.

**Seconds per image.** The ComfyUI job history, `execution_start` to `execution_success`:

    curl -s "$COMFY_URL/history/<prompt_id>" | python3 -c "import json,sys; h=json.load(sys.stdin); m=list(h.values())[0]['status']['messages']; t={k:v['timestamp'] for k,v in m}; print((t['execution_success']-t['execution_start'])/1000, 'seconds')"

The first run of a template includes loading the models (and, in sections 1 and 2, the cut-out weight download), and a
hybrid run includes the API call. Note which run it was; if the template is run again later, record the second time as
well and say which is which.

**First failure.** The first step that failed, its exit code or tool error and the message, verbatim and credential-free.
If nothing failed, write `none` only after all ten steps ran.

**Fixed-seed repeat.** Free, on `local-variation`: render a second run (`lv-002`) from the same base, the same prompt, the
same params and the same seed (`--param seed=1`), run it, fetch it, copy the fetched files to `<evidence>/lv-002-raw/`,
and compare `sha256sum` of the files in `lv-001-raw/` and `lv-002-raw/`. Record: identical bytes, visually the same
(open both), or different. A hybrid template cannot repeat for free (the API base changes on every call), so its row
stays `NOT_RUN` unless you approve a second API image for it (one more image of credit, the owner's yes for that run).

**Style anchors steer the result.** Needs approved, active anchors in `<A>` (a person activates them; an agent does not).
Free, on `local-variation`, same base, prompt, seed and params for all runs:

- `lv-001`: with the anchors `resolve` selected (the summary lists "reference <id>").
- `lv-002` is the repeat above and must be the same as `lv-001`; for the comparison make `lv-003` with a scratch
  authoring dir that has the same `project.json` and style but no active anchors for it (without anchors the base
  conditions itself).
- Optional: `--param ipadapter_weight=<lower>` and `<higher>` than the template default on further runs.

Record: do the anchors visibly change palette, lighting, line or detail towards the anchors (yes, no, unclear, with the
two files side by side in `<evidence>`)? Without `project.json` or active anchors the cell stays `NOT_RUN`, with the
reason. The same comparison on a hybrid template costs another API image each and needs the owner's yes.

**QA result.** The `qa --run <run>` and `finalize` outcome as printed: the check rows and their states (PASS, FAIL,
NOT_AVAILABLE), no summary of your own. A QA FAIL caused by the gateway returning another size is recorded as such; it is
not a local-stage failure.

**Graph screenshot.** Drag the finalized PNG of the run (the workflow is embedded) into the ComfyUI frontend, or run
`python3 -B scripts/assetgen/assetgen.py publish --run <run> --authoring <A> --comfy-url "$COMFY_URL"` and open it under
Workflows > assetgen. Fit the view to the whole graph (`.` key), hide side panels, and save the screenshot as
`<evidence>/<run id>/graph.png`. Check the groups, titled nodes, left-to-right flow and that no wire runs through an
unrelated node (`skills/comfyui/references/workflow-style.md`).

## Results

Every cell is `NOT_RUN` until you have run that item. Replace a cell with the recorded value and its source; never with a
claim that is not backed by a file in `<evidence>`.

| Template | Peak VRAM | Seconds per image | First failure | Fixed-seed repeat | Anchors steer the result | QA result | Graph screenshot |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hybrid-icon-ui` | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| `hybrid-character` | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| `hybrid-environment` | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| `local-variation` | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

## Credit cost

- `hybrid-icon-ui`, `hybrid-character`, `hybrid-environment`: one API image each, three in total, at the quality you
  pass (`low` in the commands above).
- `local-variation`: none. The comparison and repeat runs on it cost nothing either.
- Extra images only when you approve them: a hybrid fixed-seed repeat or a hybrid anchor comparison, one more each.
- The prompt reviews run Codex, not the image gateway. `budget` counts outputs and failed attempts of a series against
  the default of four; a failed attempt also counts.

## When something fails

Stop at the first failure, keep the message (credential-free), the step number, and do not retry in a loop. Do not edit a
template or a number to make a run work during this test: record the failure, then correct the document. Which row of
`docs/hardware.md` to correct:

| Where it failed | Correct in `docs/hardware.md` |
| --- | --- |
| P1, P3 or P4: driver older than CUDA 12.8, a `+cpu` or older-than-12.8 torch, no `sm_120` | "Target machine" table rows NVIDIA driver, Minimum Windows driver, ComfyUI env torch; the fix is on the machine (driver or the instance env torch), then run P2 to P4 again |
| P3: profile lower than `local-8gb` although the hardware is right | "Profiles" table, `local-8gb` row (VRAM, RAM or free-disk threshold) and `scripts/assetgen/data/hardware.json` |
| A file the template names is not found, has another name, size or source | "Models and packs" table row for that file: name, folder, size GB, source link; and the template's `requires.models` |
| A pack is missing or a different pack provides the node | "Models and packs", custom node packs table; and the template's `requires.packs` |
| CUDA out of memory, a system out of memory, or a run far above the declared peak | "What runs and what does not": the bullet (SDXL at 1024 px batch 1, one ControlNet, IPAdapter, tiled VAE, 4x upscaler, cut-out) that did not fit, moved to the cannot-do list; and the template's `requires.peak_vram_gb` and `requires.ram_gb` (all four declare 7.0 and 24 today) |
| `graph-lint --profile` refused a template or `resolve` routed to the wrong template | "Profiles" template table; `scripts/assetgen/data/template-profiles.json` |
| A gateway size that is not what was asked (QA size) | Not a hardware row: record it, see `skills/comfyui/SKILL.md` Pitfalls |
| `local-variation` shows `spends_credits: true` (the "local-variation shows spends_credits true" row) or a `NineRouterImage` node | Stop: this is a template defect, not a hardware row; record it and do not run |

To turn a row from unverified to verified: edit that row of `docs/hardware.md` and set its status to `verified` with only
three things, the date, the exact command (or tool call) and the measured value, for example a peak VRAM taken from
`vram.csv` and the date of the run. Do not mark a row verified from a template declaration or from a vendor figure. Update
the Status section of `docs/hardware.md` and the "UNTESTED on RTX 5060" lines of the templates and docs only for what a
row of the results table above now backs; whatever stays `NOT_RUN` stays UNTESTED.

## Evidence

- Directory: `<state dir>/pipeline/assetgen-hybrid/e2e-local/<run id>/` per run, holding `vram.csv`, `graph.png`, the
  `sha256sum` outputs, and a short `notes.txt` (step, command, message). Never keep a credential or a host URL in it.
- The run directories themselves stay in `<A>/assetgen/runs/` (`spec.json`, `workflow.json`, `outputs/`, `qa.json`,
  `fetch.json`). Nothing here is approved: an `approve-record` is a separate step by a person (`rpg-factory:asset-gen`).
- When done, copy the filled Results table over the one above in a commit of its own, and change the Status line at the
  top only to what the table shows: partly tested if some cells are filled, never tested-and-passing as a whole unless
  every cell holds a recorded value. Until then the status is `UNTESTED`.
