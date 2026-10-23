import subprocess
import sys

sys.path.insert(0, sys.argv[1])
import evidence

workspace = sys.argv[2]
record = {"module": "server.gateway", "check": "t-race", "state": "PASS", "timestamp": "20260101T000000",
          "identity": {"tree": "t", "head": "h"}}
evidence.store(workspace, "server", record, "x" * 20000)
code = ("import sys; sys.path.insert(0, %r); import evidence\nrecord = %r\n"
        "for i in range(40): evidence.store(%r, 'server', record, 'y' * 200000)\n") % (sys.argv[1], record, workspace)
writer = subprocess.Popen([sys.executable, "-B", "-c", code])
misses = 0
while writer.poll() is None:
    if evidence.latest(workspace, "server", "server.gateway", "t-race") is None:
        misses += 1
writer.wait()
sys.exit(1 if misses or writer.returncode else 0)
