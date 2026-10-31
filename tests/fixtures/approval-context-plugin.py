from domains._api import Result


def check(artifact, ctx):
    result = ctx.approval(artifact["id"])
    state = "PASS" if result["state"] == "verified" else "NOT_AVAILABLE"
    return [Result("approval-context", state, [result["state"]] + result["reasons"])]
