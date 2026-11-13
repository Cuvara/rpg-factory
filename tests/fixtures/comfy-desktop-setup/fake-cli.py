"""Fake `claude` / `codex` for tests/comfy-desktop-setup.test.sh. Usage: fake-cli.py claude|codex mcp get|add|remove ...
State (the registered COMFY_LOCAL_URL) in $FAKE_CLI_STATE_<NAME>, every call appended to $FAKE_CLI_LOG."""
import json, os, sys
cli, args = sys.argv[1], sys.argv[2:]
state = os.environ["FAKE_CLI_STATE_" + cli.upper()]
with open(os.environ["FAKE_CLI_LOG"], "a") as f:
    f.write(cli + " " + " ".join(args) + "\n")
cur = json.load(open(state)) if os.path.exists(state) else None
if args[:2] == ["mcp", "get"]:
    if not cur:
        sys.exit(1)
    if "--json" in args:
        print(json.dumps({"name": "comfy-mcp", "transport": {"type": "stdio", "command": cur["exe"], "env": {"COMFY_LOCAL_URL": cur["url"]}}}))
    else:
        print("comfy-mcp:\n  Status: Connected\n  Environment:\n    COMFY_LOCAL_URL=%s" % cur["url"])
elif args[:2] == ["mcp", "add"]:
    url = [a.split("=", 1)[1] for a in args if a.startswith("COMFY_LOCAL_URL=")][0]
    json.dump({"url": url, "exe": args[-1]}, open(state, "w"))
elif args[:2] == ["mcp", "remove"]:
    if os.path.exists(state):
        os.remove(state)
