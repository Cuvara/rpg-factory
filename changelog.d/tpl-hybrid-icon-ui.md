### Added

- **Asset-gen template `hybrid-icon-ui`.** A core workflow template for the icon and ui-element purposes under the
  local-8gb profile: the API image node makes the base image, a local SDXL stage refines it at low denoise with
  IPAdapter conditioning from the approved style-lock anchors (`anchor_target` is the IPAdapter image input, no
  ControlNet), then a tiled 4x upscale, a downscale to 2048 px and a cut-out that gives the saved image its alpha.
  Previews show the API base, the refined image and a 64 px view; exactly one SaveImage writes the `-final` file. The
  one reviewed prompt node feeds the API node and the positive encoder, and the template declares its `requires`
  block (profile, packs and model files by name). UNTESTED on RTX 5060: the local branch is untested on the target
  hardware (RTX 5060 8 GB); nothing was generated or measured, `requires.peak_vram_gb` is a planning estimate, and the
  sampler values (IPAdapter weight, steps, cfg, sampler, scheduler, denoise) are starting points to tune in the live
  task. The user will test on the RTX 5060 8 GB machine after merge.
