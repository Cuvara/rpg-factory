#!/usr/bin/env python3
"""Validate artifact files. Markdown metadata uses strict JSON between ---json delimiters."""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

ID = re.compile(r"^[A-Z]{2,5}-[a-z0-9-]+-\d{3}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def resolve_ref(schema, ref):
    if not ref.startswith("#/"):
        raise ValueError("unsupported schema reference " + ref)
    value = schema
    for part in ref[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def schema_errors(value, rule, schema, path="$", seen=None):
    seen = set() if seen is None else seen
    if "$ref" in rule:
        key = (rule["$ref"], path)
        if key in seen:
            return []
        return schema_errors(value, resolve_ref(schema, rule["$ref"]), schema, path, seen | {key})
    errors = []
    # oneOf/anyOf constrain the value in addition to the sibling keywords (type, properties,
    # additionalProperties, ...), which are always evaluated below
    for keyword in ("oneOf", "anyOf"):
        if keyword not in rule:
            continue
        matches = [schema_errors(value, branch, schema, path, seen) for branch in rule[keyword]]
        valid = sum(not errors_ for errors_ in matches)
        accepted = valid == 1 if keyword == "oneOf" else valid > 0
        if not accepted:
            errors.extend(min(matches, key=len) if valid == 0 and matches else [f"{path} must match {keyword}"])
    expected = rule.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}
    if expected and (expected not in types or not isinstance(value, types[expected]) or expected in ("integer", "number") and isinstance(value, bool)):
        return [f"{path} must be {expected}"]
    if "const" in rule and value != rule["const"]:
        errors.append(f"{path} must equal {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{path} must be one of {rule['enum']!r}")
    if isinstance(value, str):
        if "pattern" in rule and not re.search(rule["pattern"], value):
            errors.append(f"{path} does not match pattern")
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{path} is too short")
        if rule.get("format") == "date-time":
            try:
                datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{path} must be date-time")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            errors.append(f"{path} has too few items")
        if "items" in rule:
            for i, item in enumerate(value):
                errors.extend(schema_errors(item, rule["items"], schema, f"{path}[{i}]", seen))
    if isinstance(value, dict):
        for key in rule.get("required", []):
            if key not in value:
                errors.append(f"{path} missing {key}")
        props = rule.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors.extend(schema_errors(item, props[key], schema, f"{path}.{key}", seen))
            elif rule.get("additionalProperties") is False:
                errors.append(f"{path} unknown field {key}")
    return errors


def git(root, *args):
    return subprocess.run(
        ["git", "-C", root, *args],
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def load_file(path):
    raw = open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        return json.loads(raw)
    m = re.match(r"\A---json\s*\n(.*?)\n---(?:\s*\n|\Z)", raw, re.S)
    if not m:
        raise ValueError("expected ---json front matter (strict JSON subset)")
    return json.loads(m.group(1))


def lifecycle(reg, kind):
    all_l = reg.get("artifact_lifecycles", {})
    return all_l.get(kind, all_l.get("default", {}))


def validate(obj, reg, schema):
    errors = []
    errors.extend(schema_errors(obj, schema, schema))
    if not isinstance(obj, dict):
        return ["document must be an object"]
    if "acceptance" not in obj and "trace" not in obj:
        for k in (
            "id",
            "kind",
            "domain",
            "status",
            "source_uri",
            "license",
            "provenance",
            "delivery",
        ):
            if k not in obj:
                errors.append("missing " + k)
        if not isinstance(obj.get("id"), str) or not ID.fullmatch(obj.get("id", "")):
            errors.append("bad id")
        if obj.get("provenance") not in ("authored", "library", "generated"):
            errors.append("bad provenance")
        if not (
            isinstance(obj.get("source_rev"), str)
            and obj["source_rev"]
            or isinstance(obj.get("hash"), str)
            and obj["hash"]
        ):
            errors.append("missing source_rev or hash")
        delivery = obj.get("delivery")
        if (
            not isinstance(delivery, dict)
            or set(delivery) != {"repo", "path"}
            or not all(
                isinstance(delivery.get(k), str) and delivery[k]
                for k in ("repo", "path")
            )
        ):
            errors.append("bad delivery")
        dom = reg.get("domains", {}).get(obj.get("domain"), {})
        life = lifecycle(reg, obj.get("kind"))
        if obj.get("kind") not in dom.get("artifact_kinds", []):
            errors.append("unregistered kind/domain")
        if not life or (obj.get("status") not in life.get("states", []) and not (obj.get("status") == "review" and "proposed" in life.get("states", []))):
            errors.append("illegal status")
        return errors
    required = (
        "id",
        "kind",
        "domain",
        "status",
        "title",
        "upstream",
        "acceptance",
        "trace",
    )
    for k in required:
        if k not in obj:
            errors.append("missing " + k)
    if "id" in obj and (not isinstance(obj["id"], str) or not ID.fullmatch(obj["id"])):
        errors.append("bad id")
    for k in ("kind", "domain", "status", "title"):
        if k in obj and (not isinstance(obj[k], str) or not obj[k]):
            errors.append("bad " + k)
    dom = reg.get("domains", {}).get(obj.get("domain"), {})
    life = lifecycle(reg, obj.get("kind"))
    if obj.get("kind") not in dom.get("artifact_kinds", []):
        errors.append("unregistered kind/domain")
    if not life or (obj.get("status") not in life.get("states", []) and not (obj.get("status") == "review" and "proposed" in life.get("states", []))):
        errors.append("illegal status")
    for item in obj.get("upstream", []):
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "rev"}
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("rev"), str)
            or not SHA.fullmatch(item.get("rev", ""))
        ):
            errors.append("bad upstream")
    acids = set()
    if not isinstance(obj.get("acceptance"), list):
        errors.append("bad acceptance")
    else:
        for item in obj["acceptance"]:
            if (
                not isinstance(item, dict)
                or not {"id", "text", "verify"}.issubset(item)
                or set(item) - {"id", "text", "verify", "evidence"}
                or not all(
                    isinstance(item.get(k), str) and item[k] for k in ("id", "text")
                )
                or item.get("verify") not in ("test", "review", "measure")
            ):
                errors.append("bad acceptance item")
                continue
            if item["id"] in acids:
                errors.append("duplicate acceptance id")
            acids.add(item["id"])
    if not isinstance(obj.get("trace"), list):
        errors.append("bad trace")
    else:
        for item in obj["trace"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"repo", "ref", "kind", "ac"}
                or not isinstance(item.get("repo"), str)
                or not SHA.fullmatch(item.get("ref", ""))
                or item.get("kind") not in ("impl", "test", "release")
                or not isinstance(item.get("ac"), list)
            ):
                errors.append("bad trace item")
            elif not all(isinstance(x, str) for x in item["ac"]):
                errors.append("bad trace AC")
    if "binding_values" in obj and obj["binding_values"] is not True:
        errors.append("binding_values must be true when present")
    if obj.get("schema_version", 1) not in (1, 2):
        errors.append("unsupported schema_version")
    if "spec" in obj:
        schema_path = reg.get("kind_schemas", {}).get(obj.get("kind"))
        if schema_path:
            try:
                kind_schema = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", schema_path), encoding="utf-8"))
                errors.extend(schema_errors(obj["spec"], kind_schema, kind_schema, "$.spec"))
            except Exception as exc:
                errors.append("invalid kind schema: " + str(exc))
    return errors


def main():
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("repo_dir")
    p.add_argument(
        "--registry",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "registry.json"),
    )
    a = p.parse_args()
    root = os.path.abspath(a.repo_dir)
    reg = json.load(open(a.registry, encoding="utf-8"))
    schema = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "artifact.schema.json"), encoding="utf-8"))
    files = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git" and d != "approvals"]
        for n in names:
            full = os.path.join(base, n)
            if n.endswith((".artifact.json", ".asset.json")) or (
                n.endswith(".md") and open(full, encoding="utf-8").read(7) == "---json"
            ):
                files.append(full)
    seen = {}
    failures = []
    for f in sorted(files):
        rel = os.path.relpath(f, root).replace(os.sep, "/")
        reasons = []
        try:
            obj = load_file(f)
            reasons.extend(validate(obj, reg, schema))
            ident = obj.get("id")
            if ident in seen:
                reasons.append("duplicate id")
            elif ident:
                seen[ident] = rel
            prev = git(root, "show", f"HEAD~1:{rel}")
            if prev.returncode == 0:
                try:
                    old = (
                        json.loads(prev.stdout)
                        if rel.endswith((".artifact.json", ".asset.json"))
                        else json.loads(
                            re.search(
                                r"\A---json\s*\n(.*?)\n---", prev.stdout, re.S
                            ).group(1)
                        )
                    )
                    if old.get("id") != ident:
                        reasons.append(f"id changed {old.get('id')} -> {ident}")
                    if obj.get("status") not in lifecycle(
                        reg, obj.get("kind")
                    ).get("transitions", {}).get(old.get("status"), []):
                        reasons.append("illegal transition")
                except Exception:
                    reasons.append("invalid prior artifact")
        except Exception as e:
            reasons.append("bad document: " + str(e))
        line = (
            ("FAIL" if reasons else ("WARN deprecated-state review -> proposed" if isinstance(obj, dict) and obj.get("status") == "review" else "PASS"))
            + " "
            + (
                str(obj.get("id", "unknown"))
                if "obj" in locals() and isinstance(obj, dict)
                else rel
            )
        )
        print(line + (" " + "; ".join(dict.fromkeys(reasons)) if reasons else ""))
        obj = None
        if reasons:
            failures.append(rel)
    print(
        f"Artifacts: {len(files)} total, {len(files)-len(failures)} passed, {len(failures)} failed"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
