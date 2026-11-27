"""Fake claude/codex MCP commands with environment-bearing registration state."""
import json
import os
import sys

cli, args = sys.argv[1], sys.argv[2:]
state = os.environ["FAKE_CLI_STATE_" + cli.upper()]
with open(os.environ["FAKE_CLI_LOG"], "a") as f:
    f.write(cli + " " + " ".join(args) + "\n")
cur = json.load(open(state)) if os.path.exists(state) else None
if args[:2] == ["mcp", "get"]:
    if not cur:
        sys.exit(1)
    env = cur.get("env", {"COMFY_LOCAL_URL": cur.get("url", "")})
    if "--json" in args:
        print(json.dumps({"name": "comfy-mcp", "transport": {"type": "stdio", "command": cur["exe"], "env": env}}))
    else:
        print("comfy-mcp:\n  Status: Connected\n  Environment:")
        for key, value in env.items():
            print("    %s=%s" % (key, value))
elif args[:2] == ["mcp", "add"]:
    env = {}
    i = 0
    while i < len(args):
        if args[i] in ("-e", "--env"):
            i += 1
            while i < len(args) and not args[i].startswith("-") and "=" in args[i]:
                key, value = args[i].split("=", 1)
                env[key] = value
                i += 1
        else:
            i += 1
    json.dump({"env": env, "exe": args[-1]}, open(state, "w"))
elif args[:2] == ["mcp", "remove"]:
    if os.path.exists(state):
        os.remove(state)
