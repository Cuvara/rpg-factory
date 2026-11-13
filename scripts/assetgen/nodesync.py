"""Sync known ComfyUI node entries from a saved object_info JSON file (offline).

entries(object_info, names) -> ordered node entries for the given names.
The CLI prints entries, merges them into known-nodes.json, or checks that merge.
"""

import argparse
import json
import os
import sys


WIDGET_TYPES = {"STRING", "COMBO", "INT", "FLOAT", "BOOLEAN"}
DEFAULT_KNOWN = os.path.join(os.path.dirname(__file__), "data", "known-nodes.json")


def entries(object_info, names):
    result = {}
    for name in names:
        if name not in object_info:
            raise ValueError("node %s missing from object_info" % name)
        node = object_info[name]
        inputs = {}
        for group in ("required", "optional"):
            declarations = node.get("input", {}).get(group, {})
            order = node.get("input_order", {}).get(group, list(declarations))
            for input_name in order:
                spec = declarations[input_name]
                kind = spec[0]
                metadata = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                options = kind if isinstance(kind, list) else metadata.get("options", [])
                if isinstance(kind, list) or kind == "COMBO":
                    kind = "COMBO" if options else "STRING"
                declaration = {"type": kind}
                if kind == "COMBO":
                    declaration["options"] = options
                declaration["required"] = group == "required"
                if metadata.get("multiline") is True:
                    declaration["multiline"] = True
                inputs[input_name] = declaration
        outputs = node.get("output", [])
        widgets = sum(item["type"] in WIDGET_TYPES for item in inputs.values())
        sockets = len(inputs) - widgets
        height = max(80, 30 + 24 * (widgets + max(sockets, len(outputs))))
        output_node = node.get("output_node", False)
        if output_node and any(item["type"] == "IMAGE" for item in inputs.values()):
            height = max(height, 320)
        entry = {"inputs": inputs, "outputs": outputs}
        if output_node:
            entry["output_node"] = True
        entry["ui"] = {"size": [320, height]}
        result[name] = entry
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("object_info", help="saved object_info JSON file")
    parser.add_argument("--node", action="append", required=True, dest="names")
    parser.add_argument("--known", default=DEFAULT_KNOWN)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        with open(args.object_info, encoding="utf-8") as source:
            object_info = json.load(source)
        with open(args.known, encoding="utf-8") as source:
            known = json.load(source)
        nodes = known["nodes"]
        for name in args.names:
            if nodes.get(name, {}).get("ui_only"):
                raise ValueError("node %s is ui_only" % name)
        generated = entries(object_info, args.names)
        changed = []
        for name, entry in generated.items():
            old = nodes.get(name, {})
            if "warn_values" in old:
                entry["warn_values"] = old["warn_values"]
            if "ui" in old:
                entry["ui"] = old["ui"]
            if entry != old:
                changed.append(name)
            nodes[name] = entry
        if args.check:
            for name in changed:
                print(name)
            return 1 if changed else 0
        if args.write:
            with open(args.known, "w", encoding="utf-8", newline="\n") as target:
                target.write(json.dumps(known, indent=1, ensure_ascii=False) + "\n")
        else:
            print(json.dumps(entries(object_info, args.names), indent=1, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print("nodesync: %s" % str(exc).replace("\n", " "), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
