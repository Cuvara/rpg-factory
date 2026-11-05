#!/usr/bin/env python3
"""Build registry.json from its fragments under registry/ (layout and merge rules: scripts/lib/registry_src.py).

Edit the fragments, then run this script; registry.json is generated and committed so every reader (scripts, hooks,
tests, the authoring repo's CI) keeps reading one file. On a merge conflict in registry.json, run it again: the
fragments merge cleanly and registry.json is rebuilt from them.

Usage: build-registry.py            write registry.json from registry/
       build-registry.py --check    read-only: registry.json == build(registry/), and every entry sits in the
                                    fragment its domain or repo names (exit 0/1)
       build-registry.py --split    write registry/ from registry.json, then rebuild registry.json from it
                                    (migration, scripts/new-skill.py)
       [--root DIR]                 plugin checkout (default: this script's)
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import registry_src  # noqa: E402


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mode = "build"
    it = iter(argv)
    for a in it:
        if a == "--root":
            root = next(it, None)
            if not root:
                print("build-registry: --root needs a directory", file=sys.stderr)
                return 2
        elif a in ("--check", "--split"):
            mode = a[2:]
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(__doc__, file=sys.stderr)
            return 2
    target = os.path.join(root, "registry.json")
    if mode == "split":
        reg = registry_src.load(target)
        names = registry_src.write_fragments(root, registry_src.split(reg))
        merged, problems = registry_src.build(root)
        if problems or not registry_src.same(merged, reg):
            for p in problems:
                print(f"FAIL  {p}", file=sys.stderr)
            print("FAIL  build(split(registry.json)) differs from registry.json", file=sys.stderr)
            return 1
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(registry_src.render(merged))  # canonical order: entries grouped by fragment
        print(f"build-registry: wrote {len(names)} fragment(s) under registry/ and rebuilt registry.json from them")
        return 0
    merged, problems = registry_src.build(root)
    if merged is not None and not problems:
        problems += registry_src.misplaced(root, merged)
    if problems:
        for p in problems:
            print(f"FAIL  {p}")
        return 1
    text = registry_src.render(merged)
    if mode == "check":
        try:
            current = open(target, encoding="utf-8").read()
        except OSError:
            current = None
        if current != text:
            print("FAIL  registry.json is not the build of registry/: run python3 -B scripts/build-registry.py")
            return 1
        print(f"OK    registry.json == build of {len(registry_src.fragment_paths(root))} fragment(s) under registry/")
        return 0
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"build-registry: wrote registry.json from {len(registry_src.fragment_paths(root))} fragment(s)")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    sys.exit(main(sys.argv[1:]))
