#!/usr/bin/env python3
"""scripts/lib/subagent_policy.py over the shipped registry.json and scripts/check-registry.sh on temp copies of it:
rule text per role and agent (every value read from the registry), the policy check, the refusals (missing block,
unknown role or agent) and the model scope enforced by check-registry (codex model and effort, Claude model and alias).

Usage: tests/subagent-policy.test.py   (standalone; own temp TMPDIR and RPG_FACTORY_STATE_DIR; no network)
Exit 1 on any failure.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="subagent-policy-")
os.environ["TMPDIR"] = TMP
os.environ["RPG_FACTORY_STATE_DIR"] = os.path.join(TMP, "state")
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.dont_write_bytecode = True
import subagent_policy as sp  # noqa: E402
from shells import find_bash  # noqa: E402

with open(os.path.join(ROOT, "registry.json"), encoding="utf-8") as fh:
    REG = json.load(fh)
BLOCK = REG["pipeline"]["subagents"]
ROLES = ("run_lead", "planner", "lead", "implement", "review", "qa")
AGENTS = ("claude", "codex")

passed = failed = 0


def ok(label):
    global passed
    passed += 1
    print("PASS  " + label)


def no(label, detail=""):
    global failed
    failed += 1
    print("FAIL  " + label)
    if detail:
        print("".join("      " + line + "\n" for line in str(detail).splitlines()), end="")


def expect(label, cond, detail=""):
    ok(label) if cond else no(label, detail)


def mutated(fn):
    reg = copy.deepcopy(REG)
    fn(reg["pipeline"]["subagents"])
    return reg


def raises(fn):
    try:
        fn()
    except sp.SubagentPolicyError as exc:
        return str(exc)
    return None


print("-- rule text per role and agent (shipped registry)")
claude, codex = BLOCK["models"]["claude"], BLOCK["models"]["codex"]
expect("shipped default Claude subagent model is claude-sonnet-5-5 (alias sonnet)",
       claude["model"] == "claude-sonnet-5-5" and claude["alias"] == "sonnet", claude)
for role in ROLES:
    spec = BLOCK["roles"][role]
    for agent in AGENTS:
        text = sp.rule(REG, role, agent)
        label = f"rule {role}/{agent}"
        expect(label + ": one non-empty sentence", bool(text.strip()) and "\n" not in text and text.endswith("."), text)
        if spec["access"] == "none":
            expect(label + ": says none and gives the registry reason",
                   "none" in text and spec["when"] in text and "at most" not in text, text)
            continue
        expect(label + ": names max_parallel and when from the registry",
               f"at most {spec['max_parallel']} in parallel" in text and spec["when"] in text, text)
        expect(label + ": states read-only and every forbidden action",
               "read-only" in text and all(f in text for f in BLOCK["forbidden"]), text)
        if agent == "claude":
            expect(label + ": names the agent type, alias and model",
                   claude["agent"] in text and claude["alias"] in text and claude["model"] in text, text)
            expect(label + ": does not name the codex model", codex["model"] not in text, text)
        else:
            expect(label + ": names the codex model and effort",
                   codex["model"] in text and codex["effort"] in text, text)
            expect(label + ": does not name the Claude agent type", claude["agent"] not in text, text)
        if spec.get("own_model"):
            expect(label + ": own agent named, verdict stays the reviewer's, no own-model claim",
                   f"your own agent, {agent} (" in text and "never the other agent" in text
                   and "verdict stays yours" in text and "your own model" not in text, text)
            subagent_model = claude["model"] if agent == "claude" else codex["model"]
            expect(label + ": own-agent clause names the subagent model",
                   f"your own agent, {agent} (" in text and subagent_model in text.split("your own agent,")[1], text)
        else:
            expect(label + ": no own-model clause", "own model" not in text and "verdict" not in text.replace(
                "dispatch or verdict", ""), text)
expect("only review keeps its own model", [r for r in ROLES if BLOCK["roles"][r].get("own_model")] == ["review"])
expect("limits: run_lead and planner 3, lead 2, implement 2, review 3, qa none",
       [(BLOCK["roles"][r]["access"], BLOCK["roles"][r]["max_parallel"]) for r in ROLES]
       == [("read", 3), ("read", 3), ("read", 2), ("read", 2), ("read", 3), ("none", 0)],
       {r: BLOCK["roles"][r] for r in ROLES})
expect("qa rule says none for both agents",
       all(sp.rule(REG, "qa", a).startswith("Subagents: none") for a in AGENTS))

print("-- the rule follows the registry (no hard-coded values)")


def changed(label, fn, role, agent, needle):
    text = sp.rule(mutated(fn), role, agent)
    expect(label, needle in text, text)


changed("max_parallel change shows", lambda b: b["roles"]["lead"].update(max_parallel=7), "lead", "claude",
        "at most 7 in parallel")
changed("when change shows", lambda b: b["roles"]["planner"].update(when="the sky is green"), "planner", "codex",
        "only when the sky is green")
changed("forbidden change shows", lambda b: b.update(forbidden=["foo", "bar"]), "implement", "claude",
        "never foo or bar")
changed("claude agent type change shows", lambda b: b["models"]["claude"].update(agent="x:other-scout"),
        "run_lead", "claude", "x:other-scout")
changed("claude model and alias change shows",
        lambda b: b["models"]["claude"].update(model="claude-opus-5-5", alias="opus"), "run_lead", "claude",
        "model opus (claude-opus-5-5)")
changed("codex model and effort change shows",
        lambda b: b["models"]["codex"].update(model="gpt-6.1-sol", effort="high"), "lead", "codex",
        "gpt-6.1-sol with effort high")
changed("own_model on another role shows", lambda b: b["roles"]["lead"].update(own_model=True), "lead", "claude",
        "your own agent, claude (")
changed("access none on a role shows", lambda b: b["roles"]["implement"].update(access="none", max_parallel=0,
                                                                              when="not here"),
        "implement", "claude", "Subagents: none in this session (not here)")

print("-- refusals and check()")
expect("missing block raises SubagentPolicyError", raises(lambda: sp.rule({"pipeline": {}}, "lead", "claude")) is not None)
expect("no pipeline at all raises SubagentPolicyError", raises(lambda: sp.rule({}, "lead", "claude")) is not None)
msg = raises(lambda: sp.rule(REG, "janitor", "claude"))
expect("unknown role raises and names the role", msg is not None and "janitor" in msg, msg)
msg = raises(lambda: sp.rule(REG, "lead", "gemini"))
expect("unknown agent raises and names the agent", msg is not None and "gemini" in msg, msg)
expect("check() is empty on the shipped registry", sp.check(REG) == [], sp.check(REG))
expect("check() reports a missing block", sp.check({"pipeline": {}}) == ["registry pipeline.subagents is missing"])
expect("check() reports a missing role", any("missing role qa" in e for e in sp.check(mutated(lambda b: b["roles"].pop("qa")))))
expect("check() reports max_parallel against access",
       any("max_parallel must be 0 exactly when access is none" in e
           for e in sp.check(mutated(lambda b: b["roles"]["qa"].update(max_parallel=1)))))
expect("check() reports an empty forbidden list",
       any("forbidden" in e for e in sp.check(mutated(lambda b: b.update(forbidden=[])))))

print("-- check-registry.sh enforces the model scope (temp registry copies)")


def check_registry(reg):
    path = os.path.join(TMP, "registry-copy.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh)
    # run the real script in a bash subprocess on the temp copy, passed unchanged through --registry
    proc = subprocess.run([find_bash() or "bash", os.path.join(ROOT, "scripts", "check-registry.sh"), "--structure-only",
                           "--registry", path], capture_output=True, text=True, env=dict(os.environ))
    return proc.returncode, proc.stdout + proc.stderr


rc, out = check_registry(REG)
expect("shipped data passes", rc == 0 and "pipeline.subagents" not in out, f"rc={rc}\n{out}")

for label, fn, needle in (
    ("out-of-scope codex model", lambda b: b["models"]["codex"].update(model="gpt-9-unknown"), "models/codex"),
    ("out-of-scope codex effort", lambda b: b["models"]["codex"].update(effort="ultra"), "models/codex"),
    ("unknown claude model", lambda b: b["models"]["claude"].update(model="claude-unknown-9"), "models/claude"),
    ("wrong claude alias", lambda b: b["models"]["claude"].update(alias="opus"), "alias"),
    ("missing subagents block", lambda b: None, "pipeline.subagents: registry pipeline.subagents is missing"),
):
    reg = mutated(fn)
    if label == "missing subagents block":
        del reg["pipeline"]["subagents"]
    rc, out = check_registry(reg)
    lines = [ln for ln in out.splitlines() if ln.startswith("pipeline.subagents: ")]
    expect(f"fails on {label}", rc != 0 and any(needle in ln for ln in lines), f"rc={rc}\n{out}")

print(f"subagent policy tests: {passed + failed} run, {passed} passed, {failed} failed")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if failed else 0)
