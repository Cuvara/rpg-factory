### Changed

- **comfy-desktop-setup.** The skill's ordered steps now end with an explicit step 6 that saves `hardware-profile.json`
  with the existing `comfy-desktop-setup.py --check --json` redirect (exit 3 is expected), and the skill states that no
  command in this repo writes the model-hash cache yet, so local model sha256 stay unverified until one exists.
  `tests/comfy-desktop-setup.test.sh` runs the documented save step into a temp state dir.
- **Docs.** `docs/architecture/multi-discipline-factory.md` states the current number of tech skills, counted from the
  registry.
