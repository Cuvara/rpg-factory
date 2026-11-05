"""registry.json is generated from fragments under registry/ (scripts/build-registry.py).

Parallel branches that add a domain's modules, contracts or skills then edit different files, instead of the same
arrays at the end of one 9000-line JSON file (registry.json conflicted in every parallel domain merge of 1.3.0).

Layout (place() is the single rule; check-registry and build-registry --check enforce it):
  registry/core.json                    every top-level key in output order; shared sections (workspace, repos,
                                         tiers, gates, facts, dev tools, ...), domains.engineering, `default` kinds
  registry/engineering/<repo>.json      modules without a domain, by repo
  registry/engineering/skills.json      skills without a domain
  registry/engineering/contracts.json   contracts without a domain
  registry/domains/<id>.json            one domain: domains.<id>, its modules, contracts, skills, kind_schemas and
                                         artifact_lifecycles for its artifact kinds

Build order: core.json, then engineering/*.json, then domains/*.json, each in file-name order. Objects merge by key
(a key defined twice is an error), arrays concatenate, a scalar may only come from core.json, and core.json names
every top-level key, so the output key order is core.json's.
"""
import json
import os

FRAGMENT_DIR = "registry"


def fragment_paths(root):
    base = os.path.join(root, FRAGMENT_DIR)
    out = [os.path.join(base, "core.json")] if os.path.isfile(os.path.join(base, "core.json")) else []
    for sub in ("engineering", "domains"):
        d = os.path.join(base, sub)
        if os.path.isdir(d):
            out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]
    return out


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build(root):
    """(merged registry dict, [problems]) from the fragments under <root>/registry/."""
    paths = fragment_paths(root)
    problems = []
    if not paths or not paths[0].endswith("core.json"):
        return None, [f"{FRAGMENT_DIR}/core.json missing"]
    merged, origin = {}, {}
    for path in paths:
        name = rel(root, path)
        try:
            frag = load(path)
        except (OSError, ValueError) as e:
            problems.append(f"{name}: not readable JSON ({e})")
            continue
        if not isinstance(frag, dict):
            problems.append(f"{name}: not a JSON object")
            continue
        for key, value in frag.items():
            if name.endswith("core.json") and path == paths[0]:
                merged[key] = value if not isinstance(value, (dict, list)) else type(value)(value)
                if isinstance(value, dict):
                    origin.update({(key, k): name for k in value})
                continue
            if key not in merged:
                problems.append(f"{name}: top-level key '{key}' is not declared in {FRAGMENT_DIR}/core.json")
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                for k, v in value.items():
                    if k in merged[key]:
                        problems.append(f"{name}: {key}.{k} is already defined in {origin.get((key, k), '?')}")
                    else:
                        merged[key][k] = v
                        origin[(key, k)] = name
            elif isinstance(merged[key], list) and isinstance(value, list):
                merged[key].extend(value)
            else:
                problems.append(f"{name}: '{key}' must be an object or array here (scalars live in core.json only)")
    return merged, problems


def render(reg):
    return json.dumps(reg, indent=2, ensure_ascii=False) + "\n"


def kind_owner(reg):
    return {k: d for d, v in (reg.get("domains") or {}).items() for k in v.get("artifact_kinds", [])}


def place(section, key, item, reg):
    """Fragment (relative to registry/) that holds one entry: section is the top-level key, key the dict key or
    the item's id. Entries that are not domain or repo specific stay in core.json."""
    owner = kind_owner(reg)
    if section == "domains":
        return "core.json" if key == "engineering" else f"domains/{key}.json"
    if section in ("kind_schemas", "artifact_lifecycles"):
        d = owner.get(key)
        return f"domains/{d}.json" if d and d != "engineering" else "core.json"
    if section in ("modules", "contracts", "skills"):
        d = (item or {}).get("domain")
        if d and d != "engineering":
            return f"domains/{d}.json"
        if section == "modules":
            return f"engineering/{item['repo']}.json"
        return f"engineering/{section}.json"
    return "core.json"


def split(reg):
    """{fragment relative path: fragment dict} for a full registry; build() of the result gives `reg` back up to
    the order of entries that moved between fragments."""
    out = {"core.json": {}}
    for key, value in reg.items():
        out["core.json"][key] = {} if isinstance(value, dict) else [] if isinstance(value, list) else value
    for section, value in reg.items():
        if isinstance(value, dict):
            for k, v in value.items():
                frag = place(section, k, v, reg)
                if frag == "core.json":
                    out["core.json"][section][k] = v
                else:
                    out.setdefault(frag, {}).setdefault(section, {})[k] = v
        elif isinstance(value, list):
            for item in value:
                frag = place(section, item.get("id") if isinstance(item, dict) else None, item, reg) \
                    if section in ("modules", "contracts") else "core.json"
                if frag == "core.json":
                    out["core.json"][section].append(item)
                else:
                    out.setdefault(frag, {}).setdefault(section, []).append(item)
    return out


def misplaced(root, reg):
    """Entries whose fragment is not the one place() names (hand edits in the wrong file)."""
    problems = []
    for path in fragment_paths(root)[1:]:
        name = rel(root, path)[len(FRAGMENT_DIR) + 1:]
        try:
            frag = load(path)
        except (OSError, ValueError):
            continue
        for section, value in frag.items():
            entries = value.items() if isinstance(value, dict) else \
                ((i.get("id") if isinstance(i, dict) else None, i) for i in value) if isinstance(value, list) else ()
            for k, v in entries:
                want = place(section, k, v, reg)
                if want != name:
                    problems.append(f"{FRAGMENT_DIR}/{name}: {section} '{k}' belongs in {FRAGMENT_DIR}/{want}")
    core = os.path.join(root, FRAGMENT_DIR, "core.json")
    try:
        frag = load(core)
    except (OSError, ValueError):
        frag = {}
    for section, value in frag.items():
        if isinstance(value, dict):
            entries = value.items()
        elif isinstance(value, list) and section in ("modules", "contracts"):
            entries = ((i.get("id"), i) for i in value if isinstance(i, dict))
        else:
            continue
        for k, v in entries:
            want = place(section, k, v, reg)
            if want != "core.json":
                problems.append(f"{FRAGMENT_DIR}/core.json: {section} '{k}' belongs in {FRAGMENT_DIR}/{want}")
    return problems


def write_fragments(root, frags):
    """Replace registry/ with `frags` (stale fragment files removed); returns the written relative paths."""
    base = os.path.join(root, FRAGMENT_DIR)
    keep = set()
    for name, data in sorted(frags.items()):
        path = os.path.join(base, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render(data))
        keep.add(os.path.normpath(path))
    for path in fragment_paths(root):
        if os.path.normpath(path) not in keep:
            os.remove(path)
    return sorted(frags)


def same(a, b):
    """Equal registries up to the order of modules and contracts (split() groups them by fragment)."""
    def norm(r):
        r = dict(r)
        for k in ("modules", "contracts"):
            if isinstance(r.get(k), list):
                r[k] = sorted(r[k], key=lambda i: json.dumps(i, sort_keys=True))
        return r
    return norm(a) == norm(b)
