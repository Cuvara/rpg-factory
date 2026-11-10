"""Model policy of the delivery pipeline: which model and effort each agent role and task grade runs with.

Source of truth: registry `pipeline.models` (scope, agent_tool_alias, profiles, default_grade, rubric). Policy text:
skills/delivery/references/delivery.md section 10 "Model choice". Nothing here runs an agent or writes a file.

  scope     agent -> model id -> allowed efforts: what may run at all.
  profiles  agent -> role or grade -> {model, effort}: what each role (planner, lead, review, qa) and each grade
            (light, standard, heavy) runs with. Every profile is inside scope (check()).

A personal override file (not committed) may narrow scope and replace profiles; it is merged over the registry and
re-checked, so a profile left outside the narrowed scope is an error, never silently dispatched:

  $RPG_FACTORY_MODEL_POLICY, else <persistent state dir>/model-policy.json (lib/fstate.py)
  {"scope": {"claude": {"claude-sonnet-5-5": ["high"]}},
   "profiles": {"claude": {"lead": {"model": "claude-sonnet-5-5", "effort": "high"}, ...}}}

`scope` replaces the scope of each agent it names (models and efforts must already be in the registry scope);
`profiles` replaces the profile of each agent/role it names. A missing file is no override.
"""
import copy
import json
import os

import fstate

GRADES = ("light", "standard", "heavy")
ROLES = ("planner", "lead", "review", "qa") + GRADES
OVERRIDE_KEYS = ("scope", "profiles", "description")


class PolicyError(Exception):
    """The policy (registry plus override) is missing, malformed, outside its scope, or cannot resolve a request."""


def override_path():
    """$RPG_FACTORY_MODEL_POLICY when set, else <persistent state dir>/model-policy.json."""
    env = os.environ.get("RPG_FACTORY_MODEL_POLICY", "")
    return env if env else os.path.join(fstate.persistent(), "model-policy.json")


def policy_of(reg):
    """A copy of the registry's pipeline.models, unchecked (check() lists what is wrong)."""
    models = ((reg or {}).get("pipeline") or {}).get("models")
    if not isinstance(models, dict):
        raise PolicyError("registry pipeline.models is missing")
    return copy.deepcopy(models)


def _read_override(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise PolicyError(f"model policy override {path}: unreadable or not JSON ({exc})")
    if not isinstance(data, dict):
        raise PolicyError(f"model policy override {path}: expected a JSON object")
    return data


def _merge(policy, override, source):
    unknown = sorted(set(override) - set(OVERRIDE_KEYS))
    if unknown:
        raise PolicyError(f"model policy override {source}: unknown key(s) {', '.join(unknown)} "
                          f"(allowed: scope, profiles)")
    scope = override.get("scope", {})
    profiles = override.get("profiles", {})
    if not isinstance(scope, dict) or not isinstance(profiles, dict):
        raise PolicyError(f"model policy override {source}: scope and profiles must be objects")
    base = policy.get("scope") or {}
    for agent, models in scope.items():
        if agent not in base:
            raise PolicyError(f"model policy override {source}: scope agent {agent} is not in the registry scope")
        if not isinstance(models, dict) or not models:
            raise PolicyError(f"model policy override {source}: scope {agent} must name at least one model")
        for model, efforts in models.items():
            if model not in base[agent]:
                raise PolicyError(f"model policy override {source}: scope {agent}/{model} is outside the registry "
                                  f"scope (an override may only narrow it)")
            if not isinstance(efforts, list) or not efforts:
                raise PolicyError(f"model policy override {source}: scope {agent}/{model} must list efforts")
            extra = [e for e in efforts if e not in base[agent][model]]
            if extra:
                raise PolicyError(f"model policy override {source}: scope {agent}/{model} effort {', '.join(map(str, extra))} "
                                  f"is outside the registry scope (an override may only narrow it)")
        policy["scope"][agent] = copy.deepcopy(models)
    for agent, roles in profiles.items():
        if not isinstance(roles, dict):
            raise PolicyError(f"model policy override {source}: profiles {agent} must be an object")
        policy.setdefault("profiles", {}).setdefault(agent, {})
        for role, prof in roles.items():
            policy["profiles"][agent][role] = copy.deepcopy(prof)


def load(reg, override=None):
    """The checked policy: registry pipeline.models merged with the override.

    override: None = the file at override_path() (a missing file is fine); a path string = that file; a dict = that
    override already parsed; False = no override. Raises PolicyError when the registry has no policy, the override
    is malformed or widens the scope, or the merged policy fails check()."""
    policy = policy_of(reg)
    source = None
    if override is None:
        source = override_path()
        override = _read_override(source)
    elif isinstance(override, str):
        source = override
        override = _read_override(source)
        if override is None:
            raise PolicyError(f"model policy override {source}: file not found")
    elif override is False:
        override = None
    else:
        source = "(given)"
    if override is not None:
        _merge(policy, override, source)
    errors = check(policy)
    if errors:
        where = f" (registry plus override {source})" if override is not None else ""
        raise PolicyError(f"model policy{where}: " + "; ".join(errors))
    return policy


def in_scope(policy, agent, model, effort):
    """True when model and effort are allowed for agent by the policy's scope."""
    models = (policy.get("scope") or {}).get(agent)
    return isinstance(models, dict) and isinstance(models.get(model), list) and effort in models[model]


def check(policy):
    """Every problem of a policy as a string: profiles outside scope, missing role or grade profiles, bad grades."""
    errors = []
    scope = policy.get("scope")
    profiles = policy.get("profiles")
    if not isinstance(scope, dict) or not scope:
        errors.append("scope must name at least one agent")
        scope = {}
    if not isinstance(profiles, dict) or not profiles:
        errors.append("profiles must name at least one agent")
        profiles = {}
    for agent, models in scope.items():
        if not isinstance(models, dict) or not models:
            errors.append(f"scope {agent}: must name at least one model")
        else:
            for model, efforts in models.items():
                if not isinstance(efforts, list) or not efforts or not all(isinstance(e, str) and e for e in efforts):
                    errors.append(f"scope {agent}/{model}: efforts must be a non-empty list of strings")
        if agent not in profiles:
            errors.append(f"profiles: agent {agent} is in scope but has no profiles")
    for agent, roles in profiles.items():
        if agent not in scope:
            errors.append(f"profiles {agent}: agent is not in scope")
        if not isinstance(roles, dict):
            errors.append(f"profiles {agent}: must be an object")
            continue
        for role in ROLES:
            if role not in roles:
                errors.append(f"profiles {agent}: missing role/grade {role}")
        for role, prof in roles.items():
            if role not in ROLES:
                errors.append(f"profiles {agent}/{role}: unknown role or grade (use {', '.join(ROLES)})")
            elif not isinstance(prof, dict) or not isinstance(prof.get("model"), str) or not isinstance(prof.get("effort"), str):
                errors.append(f"profiles {agent}/{role}: needs string model and effort")
            elif not in_scope(policy, agent, prof["model"], prof["effort"]):
                errors.append(f"profiles {agent}/{role}: {prof['model']} / {prof['effort']} is outside the scope")
    if policy.get("default_grade") not in GRADES:
        errors.append(f"default_grade must be one of {', '.join(GRADES)}")
    rubric = policy.get("rubric")
    if not isinstance(rubric, dict) or any(not isinstance(rubric.get(g), str) or not rubric[g] for g in GRADES):
        errors.append("rubric must give one sentence per grade (light, standard, heavy)")
    alias_map = policy.get("agent_tool_alias")
    if not isinstance(alias_map, dict):
        errors.append("agent_tool_alias must be an object")
    else:
        for model, name in alias_map.items():
            if not isinstance(name, str) or not name.strip():
                errors.append(f"agent_tool_alias {model}: must be a non-empty string")
    return errors


def resolve(policy, agent, role):
    """{'model', 'effort'} of agent for a role or grade. PolicyError for an unknown agent or role, or a profile
    outside the scope."""
    if role not in ROLES:
        raise PolicyError(f"unknown role or grade {role!r} (use {', '.join(ROLES)})")
    roles = (policy.get("profiles") or {}).get(agent)
    if not isinstance(roles, dict):
        raise PolicyError(f"no model profiles for agent {agent!r}")
    prof = roles.get(role)
    if not isinstance(prof, dict) or "model" not in prof or "effort" not in prof:
        raise PolicyError(f"no {role} profile for agent {agent!r}")
    if not in_scope(policy, agent, prof["model"], prof["effort"]):
        raise PolicyError(f"{agent} {role}: {prof['model']} / {prof['effort']} is outside the model scope")
    return {"model": prof["model"], "effort": prof["effort"]}


def alias(policy, model):
    """The Claude Code Agent tool model alias of a model id (opus, sonnet, haiku), or None."""
    name = (policy.get("agent_tool_alias") or {}).get(model)
    return name if isinstance(name, str) and name.strip() else None


def rubric(policy):
    """grade -> one sentence on how a lead grades a task or subtask."""
    return dict(policy.get("rubric") or {})
