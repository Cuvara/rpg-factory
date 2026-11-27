#!/usr/bin/env python3
"""Batch drivers of the per-purpose loops of tests/assetgen.test.sh.

Each loop used to start about ten processes per purpose or variant (resolve, render, jq, a converter) and a process start
costs 0.5-1.5 s on a Windows host. Here one interpreter does the same work in-process, with the same files written and the
same checks made, and writes one result line per assertion for the suite to report with its own ok/no:
  OK<TAB>label
  NO<TAB>label<TAB>detail file (its text is the failure detail)
Usage: loops.py golden ROOT RUNS GOLD UPDATE(0|1) RESULTS   render every core purpose and variant against golden/
       loops.py ui ROOT RUNS RESULTS                        re-render them and convert each workflow.ui.json back
RUNS is the run directory the suite resolves into (<authoring>/assetgen/runs).
"""
import contextlib
import difflib
import io
import json
import os
import shutil
import sys
import traceback

STYLE = "stylized-painterly"


class Loop:
    def __init__(self, root, runs, results):
        self.root, self.runs, self.results = root, runs, results
        self.core = os.path.join(root, "templates", "assetgen")
        self.cases = os.path.join(root, "tests", "fixtures", "assetgen", "cases")
        self.lines, self.details = [], 0
        sys.path.insert(0, os.path.join(root, "scripts", "assetgen"))
        import assetgen
        self.assetgen = assetgen
        self.purposes = sorted(os.path.splitext(n)[0] for n in os.listdir(os.path.join(self.core, "purposes")) if n.endswith(".json"))

    # -- what the suite's helpers case_params / case_variants / mkrun / AG do ------------------------------------------
    def ag(self, argv):
        """assetgen.py ARGV in-process: (exit code, stdout + stderr)."""
        buf = io.StringIO()
        rc = 0
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                rc = self.assetgen.main(argv)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
                if isinstance(exc.code, str):
                    print(exc.code)
            except Exception:
                traceback.print_exc()
                rc = 1
        return rc or 0, buf.getvalue()

    @staticmethod
    def load(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def case_params(self, purpose, template=""):
        """The --param arguments: the render_params of cases/<purpose>.json (variants.<template> for a variant) or of
        cases/<purpose>--<template>.json, each value as jq's tostring prints it."""
        variant_file = os.path.join(self.cases, "%s--%s.json" % (purpose, template))
        plain = os.path.join(self.cases, purpose + ".json")
        if template and os.path.isfile(variant_file):
            params = self.load(variant_file).get("render_params")
        elif os.path.isfile(plain):
            data = self.load(plain)
            params = (data.get("variants") or {}).get(template, {}).get("render_params") if template else data.get("render_params")
        else:
            return []
        out = []
        for key, value in (params or {}).items():
            out += ["--param", "%s=%s" % (key, value if isinstance(value, str) else json.dumps(value, separators=(",", ":"), ensure_ascii=False))]
        return out

    def case_variants(self, purpose):
        found = set()
        plain = os.path.join(self.cases, purpose + ".json")
        if os.path.isfile(plain):
            found.update((self.load(plain).get("variants") or {}).keys())
        prefix = purpose + "--"
        for name in os.listdir(self.cases):
            if name.startswith(prefix) and name.endswith(".json"):
                found.add(name[len(prefix):-len(".json")])
        return sorted(found)

    def mkrun(self, name, purpose, extra):
        run = os.path.join(self.runs, name)
        os.makedirs(os.path.join(run, "outputs"), exist_ok=True)
        rc, _ = self.ag(["resolve", "--purpose", purpose] + extra + ["--out", os.path.join(run, "spec.json")])
        if rc != 0:
            return False
        with open(os.path.join(run, "prompt.md"), "wb") as f:
            f.write(("Test prompt for %s: one subject, centered.\n" % purpose).encode("utf-8"))
        return True

    # -- results --------------------------------------------------------------------------------------------------------
    def ok(self, label):
        self.lines.append("OK\t%s" % label)

    def no(self, label, detail=""):
        self.details += 1
        path = "%s.%d" % (self.results, self.details)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(detail)
        self.lines.append("NO\t%s\t%s" % (label, path))

    def finish(self):
        with open(self.results, "w", encoding="utf-8", newline="") as f:
            f.write("".join(line + "\n" for line in self.lines))

    def each_case(self):
        for p in self.purposes:
            yield p, ""
            for t in self.case_variants(p):
                yield p, t


def canonical(path):
    with open(path, encoding="utf-8") as f:
        return json.dumps(json.load(f), sort_keys=True, indent=1).splitlines()


def golden(loop, gold, update):
    # a variant is declared once: either in cases/<purpose>.json variants or as cases/<purpose>--<template>.json
    for p in loop.purposes:
        plain = os.path.join(loop.cases, p + ".json")
        for t in loop.case_variants(p):
            if os.path.isfile(os.path.join(loop.cases, "%s--%s.json" % (p, t))) and os.path.isfile(plain) \
                    and t in (loop.load(plain).get("variants") or {}):
                loop.no("cases: variant %s--%s is declared twice (cases/%s.json variants and cases/%s--%s.json)" % (p, t, p, p, t))
    for name in sorted(os.listdir(loop.cases)):
        if not name.endswith(".json") or "--" not in name:
            continue
        purpose, template = name[:-len(".json")].split("--", 1)
        if not (os.path.isfile(os.path.join(loop.core, "purposes", purpose + ".json"))
                and os.path.isfile(os.path.join(loop.core, "workflows", template + ".json"))):
            loop.no("cases: %s names no core purpose and core template (cases/<purpose>--<template>.json)" % name[:-len(".json")])
    for p, t in loop.each_case():
        g = "%s--%s" % (p, t) if t else p
        run = "golden-%s-001" % g
        extra = ["--style", STYLE] + (["--template", t] if t else [])
        if not loop.mkrun(run, p, extra):
            loop.no("resolve %s" % g)
            continue
        rc, out = loop.ag(["render", "--run", os.path.join(loop.runs, run)] + loop.case_params(p, t))
        wf = os.path.join(loop.runs, run, "workflow.json")
        golden_path = os.path.join(gold, g + ".json")
        if update and rc == 0:
            shutil.copyfile(wf, golden_path)
        same = False
        try:
            same = rc == 0 and os.path.isfile(golden_path) and canonical(wf) == canonical(golden_path)
            if same:
                with open(wf, encoding="utf-8") as f:
                    same = "{{" not in f.read()
        except (OSError, ValueError):
            same = False
        if same:
            loop.ok("render %s = golden (no placeholder left)" % g)
        else:
            try:
                diff = "\n".join(difflib.unified_diff(canonical(wf), canonical(golden_path), lineterm="", n=1))
            except (OSError, ValueError):
                diff = ""
            loop.no("render %s rc=%d" % (g, rc), out + "\n" + diff)


def ui(loop):
    import ui2api
    known = os.path.join(loop.root, "scripts", "assetgen", "data", "known-nodes.json")
    for p, t in loop.each_case():
        g = "%s--%s" % (p, t) if t else p
        run = "golden-%s-001" % g
        d = os.path.join(loop.runs, run)
        # re-render with the cases params only: earlier tests re-rendered some runs with other params
        loop.ag(["render", "--run", d] + loop.case_params(p, t))
        try:
            out = ui2api.convert(known, os.path.join(d, "workflow.ui.json"), os.path.join(d, "workflow.json"))
        except Exception:
            out = traceback.format_exc()
        try:
            doc = loop.load(os.path.join(d, "workflow.ui.json"))
            tag = "%s|%s" % (((doc.get("extra") or {}).get("assetgen") or {}).get("run_id"), json.dumps(doc.get("version")))
        except (OSError, ValueError, AttributeError):
            tag = ""
        label = "%s: converts back to workflow.json; run id in extra" % g
        if out == "ok" and tag == "%s|0.4" % run:
            loop.ok("workflow.ui.json " + label)
        else:
            loop.no("ui workflow %s" % g, out)


def main(argv):
    command, root = argv[0], argv[1]
    sys.path.insert(0, os.path.join(root, "tests", "fixtures", "assetgen"))
    if command == "golden":
        runs, gold, update, results = argv[2:6]
        loop = Loop(root, runs, results)
        golden(loop, gold, update == "1")
    elif command == "ui":
        runs, results = argv[2:4]
        loop = Loop(root, runs, results)
        ui(loop)
    else:
        sys.exit("loops.py: unknown command %s" % command)
    loop.finish()


if __name__ == "__main__":
    main(sys.argv[1:])
