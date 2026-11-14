### Added

- **Asset generation.** UNTESTED on RTX 5060: local and hybrid provenance binds the full graph for KSampler workflows and checks linked CLIP prompts. The run records models, LoRAs, seed, sampler settings and the requires hash; model sha256 comes from the comfy-desktop-setup hash cache when available, otherwise it is unverified and warns. The seed must be a rendered parameter. Runs without local nodes are unchanged. No generation was run or measured; comfy-desktop-setup does not write the hash cache yet.
