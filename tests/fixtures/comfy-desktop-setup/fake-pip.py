"""Fake the comfy-cli pip installation without network access."""
import os
from pathlib import Path
import shutil
import sys

venv = Path(sys.argv[1])
with open(os.environ["FAKE_CLI_LOG"], "a") as log:
    log.write("pip " + " ".join(sys.argv[2:]) + "\n")
if os.environ.get("FAKE_PIP_FAIL") == "1":
    print("ERROR: network unreachable")
    sys.exit(1)
for site in (venv / "Lib/site-packages", venv / "lib/python3.12/site-packages"):
    site.mkdir(parents=True, exist_ok=True)
    for old in site.glob("comfy_cli-*.dist-info"):
        shutil.rmtree(old)
    (site / "comfy_cli-1.26.0.dist-info").mkdir()
for binary in (venv / "Scripts/comfy.exe", venv / "bin/comfy"):
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch()
