"""Subagent policy of the delivery pipeline: what an in-session subagent may do, per role, and which model it runs on.

Source of truth: registry `pipeline.subagents` (description, forbidden, roles, models). Policy text:
skills/delivery/references/delivery.md section 8 "In-session subagents". Nothing here runs an agent or writes a file.

  forbidden  what no subagent does (edits, git writes, Orca, dispatch or verdict, nested subagents).
  roles      role -> {access: none|read, max_parallel, when, own_model?}: whether a session in that role may start
             subagents, how many at once, and the one situation that justifies one (`when` follows "only when").
  models     agent -> what a subagent runs on: claude {model, alias, agent type}, codex {model, effort}. Every entry is
             inside pipeline.models.scope (check()), so the default subagent model cannot leave the model policy.

rule() turns one role and agent into the sentence a dispatch prompt carries; every value is read from the registry.
"""
import copy

import model_policy

ROLES = ("run_lead", "planner", "lead", "implement", "review", "qa")
ACCESS = ("none", "read")


class SubagentPolicyError(Exception):
    """The registry has no subagent policy, or a request names an unknown role or agent."""


def subagents_of(reg):
    """A copy of the registry's pipeline.subagents, unchecked (check() lists what is wrong)."""
    block = ((reg or {}).get("pipeline") or {}).get("subagents")
    if not isinstance(block, dict):
        raise SubagentPolicyError("registry pipeline.subagents is missing")
    return copy.deepcopy(block)


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _check_roles(roles):
    errors = []
    if not isinstance(roles, dict):
        return ["roles must be an object"]
    for role in ROLES:
        if role not in roles:
            errors.append(f"roles: missing role {role}")
    for role, spec in roles.items():
        if role not in ROLES:
            errors.append(f"roles/{role}: unknown role (use {', '.join(ROLES)})")
            continue
        if not isinstance(spec, dict):
            errors.append(f"roles/{role}: must be an object")
            continue
        access = spec.get("access")
        count = spec.get("max_parallel")
        if access not in ACCESS:
            errors.append(f"roles/{role}: access must be one of {', '.join(ACCESS)}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"roles/{role}: max_parallel must be an integer >= 0")
        elif access in ACCESS and (count == 0) != (access == "none"):
            errors.append(f"roles/{role}: max_parallel must be 0 exactly when access is none")
        if not _is_text(spec.get("when")):
            errors.append(f"roles/{role}: when must be a non-empty string")
        if "own_model" in spec and not isinstance(spec["own_model"], bool):
            errors.append(f"roles/{role}: own_model must be a boolean")
    return errors


def _check_models(models, scope_policy):
    errors = []
    scope = scope_policy.get("scope") or {}
    aliases = scope_policy.get("agent_tool_alias") or {}
    if not isinstance(models, dict):
        return ["models must be an object"]
    for agent in scope:
        if agent not in models:
            errors.append(f"models: missing agent {agent} (it is in pipeline.models.scope)")
    for agent, entry in models.items():
        if agent not in scope:
            errors.append(f"models/{agent}: agent is not in pipeline.models.scope")
        elif not isinstance(entry, dict):
            errors.append(f"models/{agent}: must be an object")
        elif agent == "claude":
            model = entry.get("model")
            if "effort" in entry:
                errors.append("models/claude: effort is not set for a Claude subagent (the Agent tool takes an alias)")
            if model not in scope["claude"]:
                errors.append(f"models/claude: model {model!r} is outside pipeline.models.scope")
            elif entry.get("alias") != aliases.get(model):
                errors.append(f"models/claude: alias {entry.get('alias')!r} is not pipeline.models.agent_tool_alias "
                              f"of {model} ({aliases.get(model)!r})")
            if not _is_text(entry.get("agent")):
                errors.append("models/claude: agent must be a non-empty string (the Agent subagent_type)")
        else:
            if not model_policy.in_scope(scope_policy, agent, entry.get("model"), entry.get("effort")):
                errors.append(f"models/{agent}: {entry.get('model')} / {entry.get('effort')} is outside "
                              f"pipeline.models.scope")
    return errors


def check(reg):
    """Every problem of the registry's subagent policy as a string: a missing block, roles, access, parallel limits,
    forbidden list, and subagent models outside pipeline.models.scope or the alias map."""
    try:
        block = subagents_of(reg)
    except SubagentPolicyError as exc:
        return [str(exc)]
    errors = _check_roles(block.get("roles"))
    forbidden = block.get("forbidden")
    if not isinstance(forbidden, list) or not forbidden or not all(_is_text(f) for f in forbidden):
        errors.append("forbidden must be a non-empty list of strings")
    try:
        scope_policy = model_policy.policy_of(reg)
    except model_policy.PolicyError as exc:
        return errors + [str(exc)]
    return errors + _check_models(block.get("models"), scope_policy)


def _join(items):
    """'a', 'a or b', 'a, b, or c' (the serial comma keeps an item like 'dispatch or verdict' readable)."""
    items = [str(i) for i in items]
    if len(items) <= 2:
        return " or ".join(items)
    return ", ".join(items[:-1]) + ", or " + items[-1]


def _model_clause(models, agent):
    entry = models[agent]
    if agent == "claude":
        return f"use Agent subagent_type {entry['agent']} with model {entry['alias']} ({entry['model']})"
    return f"run them on {entry['model']} with effort {entry['effort']}"


def rule(reg, role, agent):
    """ONE short sentence for a dispatch prompt: what subagents a session in `role` may start when it runs on `agent`.
    SubagentPolicyError for a missing block, an unknown role or agent, or an entry too malformed to phrase."""
    block = subagents_of(reg)
    if role not in ROLES:
        raise SubagentPolicyError(f"unknown role {role!r} (use {', '.join(ROLES)})")
    spec = (block.get("roles") or {}).get(role)
    if not isinstance(spec, dict) or spec.get("access") not in ACCESS or not _is_text(spec.get("when")):
        raise SubagentPolicyError(f"no usable subagent policy for role {role!r}")
    models = block.get("models") or {}
    if agent not in models:
        raise SubagentPolicyError(f"unknown agent {agent!r} (use {', '.join(sorted(models)) or 'none'})")
    if spec["access"] == "none":
        return f"Subagents: none in this session ({spec['when']})."
    forbidden = block.get("forbidden")
    if not isinstance(forbidden, list) or not forbidden:
        raise SubagentPolicyError("registry pipeline.subagents.forbidden is missing")
    try:
        clause = _model_clause(models, agent)
    except (KeyError, TypeError) as exc:
        raise SubagentPolicyError(f"registry pipeline.subagents.models.{agent} is incomplete ({exc})")
    if spec.get("own_model"):
        clause = f"they run on your own model ({clause}), never the other one, and the verdict stays yours"
    return (f"Subagents: read-only scouts only, at most {spec['max_parallel']} in parallel, only when {spec['when']}; "
            f"never {_join(forbidden)}; {clause}.")
