"""Fake NVIDIA query output for hardware profile tests."""
import os
import sys

args = sys.argv[1:]
if os.environ.get("FAKE_SMI_LOG"):
    with open(os.environ["FAKE_SMI_LOG"], "a") as log:
        log.write(" ".join(args) + "\n")
gpu = os.environ.get("FAKE_GPU", "none")
if gpu == "none":
    print("No devices were found")
    sys.exit(6)
if gpu == "oldsmi5060" and any("compute_cap" in arg for arg in args):
    print('Field "compute_cap" is not a valid field to query.')
    sys.exit(2)
print({
    "gtx1650": "NVIDIA GeForce GTX 1650, 4096, 7.5, 610.88",
    "rtx5060": "NVIDIA GeForce RTX 5060, 8151, 12.0, 576.02",
    "oldsmi5060": "NVIDIA GeForce RTX 5060, 8151, 576.02",
}[gpu])
