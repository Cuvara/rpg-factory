# Hardware guide for asset-gen's local and hybrid branch

Target machine: Windows 11, NVIDIA RTX 5060 8 GB VRAM, 32 GB RAM. This is another machine than the one the plugin is
developed on (see "Development machine"). Domain description and routing: `docs/architecture/domains/assetgen.md`.

## Status

**UNTESTED on RTX 5060.** The local and hybrid branch (the four `local-8gb` templates and the `--profile` routing)
has never run on the target machine. The user tests it there after the merge. This guide claims no measured VRAM
number, no passing generation, no timing and no quality result for the local branch.

Every figure below carries a status:

- **verified**: with its source, either a file in this repo (path given) or a measurement with date and command.
- **unverified**: a planning estimate, a template declaration, or a vendor figure not checked on the target.

Estimates stay **unverified** until the user has run `docs/plans/assetgen-hybrid/e2e-local.md` on the RTX 5060
machine. That runbook is the only way an estimate becomes verified. A figure that merely sits in a template
(`requires.peak_vram_gb`, `requires.ram_gb`, `requires.models[].size_gb`) is a declaration, not a measurement.

## Target machine

| Requirement | Value | Status |
|---|---|---|
| GPU | NVIDIA RTX 5060, 8 GB VRAM (Blackwell, compute capability 12.0) | unverified (planned target; not seen by this repo) |
| NVIDIA driver | supports CUDA 12.8 or newer: `nvidia-smi` header shows "CUDA Version: 12.8" or higher | unverified (rule is in `scripts/assetgen/data/hardware.json`; the target's driver was not checked) |
| Minimum Windows driver for CUDA 12.8 | about 570.x | unverified (vendor figure from <https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/>, not checked on the target) |
| ComfyUI env torch | a CUDA build of 12.8 or newer; Blackwell has `sm_120` kernels only in those builds | verified as a rule (`torch_arch` in `scripts/assetgen/data/hardware.json`); the target's torch is unverified |
| RAM | 32 GB (reports about 31.8 GiB); `local-8gb` needs at least 30 GiB | threshold verified (`hardware.json`); the target's RAM unverified |
| Free SSD | about 60 GB recommended; the check enforces 40 GiB | 40 GiB threshold verified (`hardware.json`); 60 GB is an unverified planning estimate (models, ComfyUI env with a CUDA torch, packs, cut-out weight, outputs) |

Check the torch build with the ComfyUI instance's own Python (the Comfy Desktop instance env, not the system Python):

    python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_capability(), torch.cuda.get_arch_list())"

Expect `torch.version.cuda` 12.8 or newer, capability `(12, 0)` and `sm_120` in the arch list. A `+cpu` build
or a CUDA build older than 12.8 does not meet `local-8gb`; `scripts/comfy-desktop-setup.py --check` reads
`torch/version.py` in the instance env (it never imports torch) and reports the same.

## Profiles

Thresholds come from `scripts/assetgen/data/hardware.json` (schema `rpg-factory.assetgen-hardware/1`) in GiB: VRAM is
`nvidia-smi` memory.total in MiB divided by 1024, RAM and free disk are bytes divided by 1024^3. They are planning
values set a little under the nominal size, not measurements.

| Profile | Rank | GPU | Min VRAM GiB | Min RAM GiB | Min free disk GiB | torch | Status |
|---|---|---|---|---|---|---|---|
| `api-only` | 0 | no | 0 | 0 | 1 | none | thresholds verified (`hardware.json`); no local model, images come from the ChatGPT image API through the 9router node |
| `local-4gb` | 1 | yes | 3.5 | 15 | 20 | CUDA build, any version | thresholds verified (`hardware.json`); never run on any 4 GB card, SD1.5-class plan only |
| `local-8gb` | 2 | yes | 7.5 | 30 | 40 | CUDA build 12.8 or newer | thresholds verified (`hardware.json`); UNTESTED on RTX 5060 |

`comfy-desktop-setup.py --check` prints the best profile the machine meets. It never applies the profile, never
downloads models and never installs packs.

Which template needs which profile (`requires.profile` in `templates/assetgen/workflows/`, routes in
`scripts/assetgen/data/template-profiles.json`):

| Template | Purposes it is routed for | `requires.profile` | Status |
|---|---|---|---|
| `hybrid-icon-ui` | `icon`, `ui-element` | `local-8gb` | UNTESTED on RTX 5060 |
| `hybrid-character` | `ref-3d-character`, `ref-3d-turnaround`, `sprite-2d` | `local-8gb` | UNTESTED on RTX 5060 |
| `hybrid-environment` | `scene-2d`, `concept-2d`, `texture-tileable` | `local-8gb` | UNTESTED on RTX 5060 |
| `local-variation` | none (`prop-2d`, `image-edit` only with `--template local-variation`; no API call, no credit) | `local-8gb` | UNTESTED on RTX 5060 |

Routes exist only for `local-8gb`. Under `local-4gb` and `api-only` every purpose falls back to its API default
template, so **`local-4gb` routes nothing local today**: it is a threshold row without a template. `resolve --profile
api-only|local-4gb|local-8gb|auto` refuses (exit 1) a template whose `requires.profile` is above the chosen profile;
`--template` still overrides the route. All four templates declare `requires.peak_vram_gb` 7.0 and `requires.ram_gb`
24: both are **unverified** planning declarations, never measured.

## What runs and what does not

Planned for `local-8gb` (all **unverified** on the RTX 5060 until `docs/plans/assetgen-hybrid/e2e-local.md` is run):

- SDXL checkpoint (pruned fp16 or fp8) at 1024 px, batch 1.
- One SDXL ControlNet at a time (Canny, in `hybrid-character` and `hybrid-environment`).
- IPAdapter (SDXL), conditioned by the style-lock anchors.
- Tiled VAE decode.
- A 4x upscaler (4x-UltraSharp or RealESRGAN_x4plus).
- Cut-out (InSPyReNet in the templates; BiRefNet or rembg are the pack family).

Hybrid flow: the API image node (9router, ChatGPT image API) makes the base image, then a local SDXL stage refines it.
Only the local stage uses the GPU.

What the 8 GB profile **cannot** do (rules in `hardware.json` `excludes` and the graph-lint profile rules in
`scripts/assetgen/graphstyle.py`):

- Flux fp16 (the weights alone exceed 8 GB). Flux GGUF (quantized) is an optional later step, not part of the plan.
- Two checkpoints loaded at once, unless the template declares `requires.offload` true (graph-lint refuses it).
- Two or more ControlNets at once; chain them one at a time instead.
- 3D mesh generation. The branch makes 2D images and 3D reference turnarounds only.
- A batch size above 1.
- A non-tiled VAE decode above 1024 px.
- A template whose `requires.peak_vram_gb` is above the profile's VRAM.

These exclusions are rules in this repo (verified as rules). Whether the planned workload fits in 8 GB is the open
question the runbook answers.

## Models and packs

Put each file under `<instance>/ComfyUI/models/<folder>/` of the Comfy Desktop instance. Sizes are the template
declarations (`requires.models[].size_gb`), not checked against the downloaded files, so every size is **unverified**.
Links are the expected sources, **unverified** (not downloaded or checked by this repo); they live in docs only,
never in templates or scripts.

| Name | Kind | Folder | Size GB | Template(s) | Source | Status |
|---|---|---|---|---|---|---|
| `sd_xl_base_1.0.safetensors` | checkpoint | `checkpoints` | 6.9 | all four | <https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0> | unverified |
| `controlnet-canny-sdxl-1.0.safetensors` | ControlNet | `controlnet` | 2.5 | `hybrid-character` | <https://huggingface.co/diffusers/controlnet-canny-sdxl-1.0> (fp16 weight, renamed to the template's file name) | unverified |
| `diffusers_xl_canny_mid.safetensors` | ControlNet | `controlnet` | 0.5 | `hybrid-environment` | <https://huggingface.co/lllyasviel/sd_control_collection> | unverified |
| `ip-adapter-plus_sdxl_vit-h.safetensors` | IPAdapter | `ipadapter` | 0.8 | all four | <https://huggingface.co/h94/IP-Adapter> (`sdxl_models/`) | unverified |
| `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` | CLIP vision | `clip_vision` | 2.5 | all four | <https://huggingface.co/h94/IP-Adapter> (`models/image_encoder/model.safetensors`, renamed, as the ComfyUI_IPAdapter_plus README says) | unverified |
| `4x-UltraSharp.pth` | upscaler | `upscale_models` | 0.07 | `hybrid-icon-ui`, `hybrid-environment` | <https://huggingface.co/Kim2091/UltraSharp> | unverified |
| `RealESRGAN_x4plus.pth` | upscaler | `upscale_models` | 0.07 | `hybrid-character` | <https://github.com/xinntao/Real-ESRGAN/releases> | unverified |

`local-variation` needs only the checkpoint, the IPAdapter model and the CLIP vision model.

Custom node packs (named in `requires.packs`; ids in `hardware.json`):

| Pack | Needed by | Source | Status |
|---|---|---|---|
| `comfyui_ipadapter_plus` | all four templates | <https://github.com/cubiq/ComfyUI_IPAdapter_plus> | unverified link |
| `comfyui_controlnet_aux` | `hybrid-character`, `hybrid-environment` | <https://github.com/Fannovel16/comfyui_controlnet_aux> | unverified link |
| `cut-out (BiRefNet or rembg)` | `hybrid-icon-ui`, `hybrid-character` | the templates use InspyrenetRembg: <https://github.com/john-mnz/ComfyUI-Inspyrenet-Rembg> | unverified link |

InspyrenetRembg downloads its own InSPyReNet weight on its first run. Its size is **unverified** and the download
happens without a model-download step of this repo, so get the user's yes before the first run, or place the weight first.

Total of the unique model declarations: about 13.3 GB (6.9 + 2.5 + 0.5 + 0.8 + 2.5 + 0.07 + 0.07), **unverified**, plus
the InSPyReNet weight. The 60 GB free-SSD recommendation covers these, a ComfyUI env with a CUDA torch, the packs and
the outputs; it is an unverified estimate.

## Saving the profile for --profile auto

`resolve --profile auto` reads `<persistent state>/assetgen/hardware-profile.json`, the saved output of
`comfy-desktop-setup.py --check --json`. Nothing writes this file automatically: the user or the agent saves it.
From the plugin checkout, in Git Bash:

    mkdir -p ~/.local/state/rpg-factory/assetgen
    python3 -B scripts/comfy-desktop-setup.py --check --json > ~/.local/state/rpg-factory/assetgen/hardware-profile.json

- Path resolution (`persistent()` in `scripts/lib/fstate.py`): `$RPG_FACTORY_STATE_DIR` if it is an absolute path,
  else `$XDG_STATE_HOME/rpg-factory`, else `~/.local/state/rpg-factory`. Replace `~/.local/state/rpg-factory` in the
  command when one of the first two is set.
- The JSON has a top-level `profile` object; `auto` reads its `id`.
- Exit code 3 (ACTION_NEEDED) still writes a valid file. `--check` never applies the profile, never downloads models
  and never installs packs.
- Re-run it after a driver, torch, GPU or RAM change.
- Do not save it with Windows PowerShell 5.1 (`>` or `Out-File`): the file gets UTF-16 or a BOM and is unreadable
  JSON. Use Git Bash.
- Without the file, or with an unreadable one, `auto` uses `api-only` (with a warning when the file exists but is
  unusable). Without `--profile`, `resolve` changes nothing.

## Development machine

Verified measurement, 2026-11-14, `python3 -B scripts/comfy-desktop-setup.py --check --json --targets none`:

| Fact | Value | Status |
|---|---|---|
| GPU | NVIDIA GeForce GTX 1650, 4.0 GiB VRAM, compute capability 7.5 | verified (2026-11-14, command above) |
| Driver | 610.88 | verified (2026-11-14) |
| RAM | 31.9 GiB | verified (2026-11-14) |
| torch in the Comfy Desktop instance env | 2.12.1+cpu | verified (2026-11-14) |
| Resulting profile | `api-only` | verified (2026-11-14) |

It resolves to `api-only`, not `local-4gb`: `local-4gb` was refused with "torch 2.12.1+cpu is a CPU build", and
`local-8gb` with "VRAM 4.0 GiB < 7.5" plus the CPU build. The VRAM (4.0 >= 3.5) and RAM (31.9 >= 15) thresholds of
`local-4gb` pass, so with a CUDA torch build in the instance env this machine would meet `local-4gb`; that profile
still routes no local template today. Earlier planning notes said "local-4gb"; the measured result is `api-only`.
This machine is not the target and says nothing about the RTX 5060.
