import os
import sys

sys.path.insert(0, sys.argv[1])
import evidence

workspace = sys.argv[2]
record = {"module": "server.gateway", "check": "t-prune", "state": "PASS", "timestamp": "20260101T000000",
          "identity": {"tree": "t"}}
logs = [evidence.store(workspace, "server", record, f"run {i}") for i in range(25)]
directory = os.path.dirname(logs[-1])
mine = [f for f in os.listdir(directory) if f.startswith("server.gateway__t-prune-")]
other = [f for f in os.listdir(directory) if f.startswith("server.gateway__t-pass-")]
latest = evidence.latest(workspace, "server", "server.gateway", "t-prune")
ok = (len(set(logs)) == 25 and len(mine) == 20 and os.path.exists(latest["log"])
      and latest["log"] == logs[-1] and other)
sys.exit(0 if ok else 1)
