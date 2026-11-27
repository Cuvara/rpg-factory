### Fixed

- **comfy-desktop-setup.** `scripts/comfy-desktop-setup.py` reconfigures stdout and stderr to UTF-8 at start and reads
  subprocess output as UTF-8 (`errors="replace"`), like the other scripts, so the Windows cp1252 pipe default no longer
  garbles or breaks its output.
