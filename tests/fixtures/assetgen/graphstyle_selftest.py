"""Self-test of scripts/assetgen/graphstyle.py: every graph style rule on the template form and on the frontend (UI) form.

The clean fixture tests/fixtures/assetgen/graph-style/clean.json passes every rule; for each rule a mutated copy fails
with a violation that starts with the rule id and names the node (`node <id> (<class_type>`) or the group
(`group "<title>"`). The UI form is the clean template laid out by uiworkflow.to_ui as render writes workflow.ui.json
(placeholders filled, filename_prefix assetgen/<run_id>-final, extra.assetgen.run_id), then mutated. Style-lock
anchor nodes obey the title and group rules like every node; the render cases add them with assetgen.wire_references
and lay them out through assetgen.ui_with_references (References group). No file is written, no network. Prints 'ok N - <name>' or 'not ok N - <name>' per case and exits 1 when any case fails.
"""
import copy
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
ENGINE = os.path.join(ROOT, "scripts", "assetgen")
sys.path.insert(0, ENGINE)

import graphstyle  # noqa: E402
import uiworkflow  # noqa: E402

with open(os.path.join(ENGINE, "data", "known-nodes.json"), encoding="utf-8") as _f:
    KNOWN = json.load(_f)["nodes"]
with open(os.path.join(ROOT, "tests", "fixtures", "assetgen", "graph-style", "clean.json"), encoding="utf-8") as _f:
    CLEAN = json.load(_f)
RUN_ID = "gs-selftest-001"
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def template(mutate=None):
    data = copy.deepcopy(CLEAN)
    if mutate:
        mutate(data)
    return data


def rule(violations, rule_id, *names):
    """The violations of rule_id; asserts one exists and that one of them names every given node/group substring."""
    hits = [v for v in violations if v.startswith(rule_id + ":")]
    assert hits, "no %s violation in %r" % (rule_id, violations)
    assert any(all(n in v for n in names) for v in hits), "no %s violation names %r: %r" % (rule_id, names, hits)
    return hits


def no_rule(violations, rule_id):
    hits = [v for v in violations if v.startswith(rule_id + ":")]
    assert not hits, "unexpected %s violation(s): %r" % (rule_id, hits)


def render_graph(data, run_id=RUN_ID):
    """The template's workflow with placeholders filled as render fills them (defaults, a prompt, a reference image,
    the run's filename_prefix)."""
    values = {name: decl.get("default") for name, decl in data["params"].items()}
    values.update(prompt="A test prompt: one subject, centered.", reference_image="ref.png",
                  filename_prefix="assetgen/" + run_id)
    graph = copy.deepcopy(data["workflow"])
    for node in graph.values():
        for name, value in node["inputs"].items():
            if isinstance(value, str):
                node["inputs"][name] = PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), value)
    return graph


def ui_form(data=None, run_id=RUN_ID, graph=None, extra=True):
    data = data or template()
    graph = graph if graph is not None else render_graph(data, run_id)
    meta = {"assetgen": {"run_id": run_id, "workflow": "workflow.json"}} if extra else None
    return uiworkflow.to_ui(graph, KNOWN, meta, data.get("ui"))


def node(ui, nid):
    return next(n for n in ui["nodes"] if n["id"] == nid)


def group(ui, title):
    return next(g for g in ui["groups"] if g["title"] == title)


def inside(n, g):
    x, y = n["pos"]
    w, h = n["size"]
    bx, by, bw, bh = g["bounding"]
    return x >= bx and y - 30 >= by and x + w <= bx + bw and y + h <= by + bh


# -- template form -------------------------------------------------------------------------------------------------

@case("clean template: no violation, template_row PASS without reasons")
def _():
    assert graphstyle.template_violations(template(), KNOWN) == []
    row = graphstyle.template_row(template(), KNOWN, "clean.json")
    assert row == {"path": "clean.json", "check": graphstyle.CHECK, "state": "PASS", "reasons": []}, row
    assert graphstyle.CHECK == "assetgen-graph-style"
    assert graphstyle.STAGES == ("Prompt", "References", "Generate", "Post-process", "Preview", "Output")
    assert graphstyle.NOTE_TYPES == ("Note", "MarkdownNote")


def drop_title(d):
    del d["workflow"]["4"]["_meta"]


def class_title(d):
    d["workflow"]["4"]["_meta"]["title"] = "ImageScale"


def ungroup(d):
    d["ui"]["groups"][3]["nodes"].remove("4")


def rename_group(d):
    d["ui"]["groups"][3]["title"] = "Postprocess"
    for note in d["ui"]["notes"]:
        if note["group"] == "Post-process":
            note["group"] = "Postprocess"


def swap_groups(d):
    g = d["ui"]["groups"]
    g[1], g[2] = g[2], g[1]


def drop_note(d):
    d["ui"]["notes"] = [n for n in d["ui"]["notes"] if n["group"] != "Output"]


def literal_prompt(d):
    d["workflow"]["3"]["inputs"]["user_prompt"] = "{{prompt}}"


def other_prompt_source(d):
    d["workflow"]["1"]["class_type"] = "PrimitiveString"


def literal_prompt_source(d):
    d["workflow"]["1"]["inputs"]["value"] = "A fixed prompt that bypasses the review."


def other_placeholder_source(d):
    d["workflow"]["1"]["inputs"]["value"] = "{{model}}"


def prompt_plus_text_source(d):
    d["workflow"]["1"]["inputs"]["value"] = "{{prompt}}, highly detailed"


def two_image_nodes(d):
    d["workflow"]["7"] = {"class_type": "NineRouterImage", "_meta": {"title": "Second image"},
                          "inputs": {"user_prompt": ["1", 0], "model": "{{model}}", "size": "{{size}}",
                                     "quality": "{{quality}}", "background": "{{background}}"}}
    d["ui"]["groups"][2]["nodes"].append("7")


def bare_prefix(d):
    d["workflow"]["6"]["inputs"]["filename_prefix"] = "{{filename_prefix}}"


def placeholder_suffix(d):
    d["workflow"]["6"]["inputs"]["filename_prefix"] = "{{filename_prefix}}-{{size}}"


def static_prefix(d):
    d["workflow"]["6"]["inputs"]["filename_prefix"] = "assetgen/icon"


def intermediate_save(d):
    d["workflow"]["7"] = {"class_type": "SaveImage", "_meta": {"title": "Save raw image"},
                          "inputs": {"filename_prefix": "{{filename_prefix}}-raw", "images": ["3", 0]}}
    d["ui"]["groups"][3]["nodes"].append("7")


def static_load(d):
    d["workflow"]["2"]["inputs"]["image"] = "ref.png"


def partial_load(d):
    d["workflow"]["2"]["inputs"]["image"] = "{{reference_image}}.png"


TEMPLATE_FAILS = [
    ("title", "a node without _meta.title", drop_title, ("node 4 (ImageScale",)),
    ("title", "a node titled with its class name", class_title, ("node 4 (ImageScale",)),
    ("group", "a node in no ui group", ungroup, ("node 4 (ImageScale",)),
    ("vocabulary", "a group title outside the stage vocabulary", rename_group, ('group "Postprocess"',)),
    ("order", "groups listed (laid out) Generate before References", swap_groups, ('group "References"',)),
    ("note", "a group without a Note", drop_note, ('group "Output"',)),
    ("prompt", "user_prompt as a literal value", literal_prompt, ("node 3 (NineRouterImage",)),
    ("prompt", "user_prompt linked from a PrimitiveString", other_prompt_source, ("node 3 (NineRouterImage", "node 1 (PrimitiveString")),
    ("prompt", "the prompt node holding literal text", literal_prompt_source,
     ("node 3 (NineRouterImage", "node 1 (PrimitiveStringMultiline", "{{prompt}}")),
    ("prompt", "the prompt node holding another placeholder ({{model}})", other_placeholder_source,
     ("node 3 (NineRouterImage", "node 1 (PrimitiveStringMultiline", '"{{model}}"')),
    ("prompt", "the prompt node holding {{prompt}} plus extra text", prompt_plus_text_source,
     ("node 3 (NineRouterImage", "node 1 (PrimitiveStringMultiline")),
    ("one-image-node", "two NineRouterImage nodes", two_image_nodes, ("2", "3", "7")),
    ("save-suffix", "filename_prefix without a suffix", bare_prefix, ("node 6 (SaveImage",)),
    ("save-suffix", "a suffix holding another placeholder", placeholder_suffix, ("node 6 (SaveImage",)),
    ("save-suffix", "a static filename_prefix", static_prefix, ("node 6 (SaveImage",)),
    ("save-output", "an intermediate SaveImage in Post-process", intermediate_save, ("node 7 (SaveImage",)),
    ("load-image", "a static LoadImage file name", static_load, ("node 2 (LoadImage",)),
    ("load-image", "a placeholder plus a static extension", partial_load, ("node 2 (LoadImage",)),
]


def _template_fail(rule_id, mutate, names):
    def fn():
        assert graphstyle.template_violations(template(), KNOWN) == [], "the clean template must pass %s" % rule_id
        data = template(mutate)
        violations = graphstyle.template_violations(data, KNOWN)
        rule(violations, rule_id, *names)
        row = graphstyle.template_row(data, KNOWN, "t.json")
        assert row["state"] == "FAIL" and row["reasons"] == violations and row["check"] == graphstyle.CHECK, row
    return fn


for _rule, _label, _mutate, _names in TEMPLATE_FAILS:
    case("template %s: %s FAILS, naming %s" % (_rule, _label, " ".join(_names)))(_template_fail(_rule, _mutate, _names))


@case("template prompt: the prompt node holding {{prompt}} (also with spaces inside the braces, as render reads it) passes")
def _():
    assert template()["workflow"]["1"]["inputs"]["value"] == "{{prompt}}"
    assert graphstyle.template_violations(template(), KNOWN) == []
    spaced = template(lambda d: d["workflow"]["1"]["inputs"].__setitem__("value", "{{ prompt }}"))
    assert graphstyle.template_violations(spaced, KNOWN) == []


@case("template prompt: a source of the wrong class gets one prompt violation (the value is not judged twice)")
def _():
    data = template(other_prompt_source)
    data["workflow"]["1"]["inputs"]["value"] = "literal"
    hits = rule(graphstyle.template_violations(data, KNOWN), "prompt", "node 1 (PrimitiveString")
    assert len(hits) == 1, hits


@case("template one-image-node: no NineRouterImage FAILS with the count")
def _():
    def mutate(d):
        d["workflow"]["3"] = {"class_type": "ImageBatch", "_meta": {"title": "Batch references"},
                              "inputs": {"image1": ["2", 0], "image2": ["2", 0]}}
    hits = rule(graphstyle.template_violations(template(mutate), KNOWN), "one-image-node")
    assert any("0" in h for h in hits), hits


@case("template passing variants: '/final' suffix, a Preview group between Post-process and Output, an omitted stage")
def _():
    def slash(d):
        d["workflow"]["6"]["inputs"]["filename_prefix"] = "{{filename_prefix}}/final"

    def preview_group(d):
        d["ui"]["groups"][3]["nodes"].remove("5")
        d["ui"]["groups"].insert(4, {"title": "Preview", "nodes": ["5"]})
        d["ui"]["notes"].append({"text": "Look at the raw image.", "group": "Preview"})

    def no_references(d):  # any subsequence of STAGES: References dropped, its LoadImage gone
        del d["workflow"]["2"]
        del d["workflow"]["3"]["inputs"]["reference_images"]
        del d["params"]["reference_image"]
        del d["ui"]["groups"][1]
        d["ui"]["notes"] = [n for n in d["ui"]["notes"] if n["group"] != "References"]
    for mutate in (slash, preview_group, no_references):
        assert graphstyle.template_violations(template(mutate), KNOWN) == [], mutate.__name__


@case("template: a stage title twice is a layout violation (uiworkflow rejects it), never a pass")
def _():
    def dup(d):
        d["ui"]["groups"][3]["nodes"].remove("5")
        d["ui"]["groups"].insert(4, {"title": "Post-process", "nodes": ["5"]})
    violations = graphstyle.template_violations(template(dup), KNOWN)
    rule(violations, "layout", "Post-process")


@case("UI order: a stage title twice FAILS, naming the group")
def _():
    ui = ui_form()
    group(ui, "Preview" if any(g["title"] == "Preview" for g in ui["groups"]) else "Output")["title"] = "Post-process"
    rule(graphstyle.ui_violations(ui, KNOWN), "order", 'group "Post-process"')


@case("legacy core templates image-generate and image-edit: template_row WARN (never FAIL), first reason names the legacy template")
def _():
    paths = {os.path.basename(p)[:-5]: p for p in glob.glob(os.path.join(ROOT, "templates", "assetgen", "workflows", "*.json"))}
    for tid in ("image-generate", "image-edit"):
        with open(paths[tid], encoding="utf-8") as f:
            data = json.load(f)
        assert "ui" not in data, "%s gained a ui block: update this case" % tid
        row = graphstyle.template_row(data, KNOWN, tid)
        assert row["state"] == "WARN" and row["check"] == graphstyle.CHECK, row
        assert row["reasons"][0].startswith("legacy template without a ui block"), row


@case("template_row: a ui block without groups is legacy WARN, also with violations")
def _():
    for ui in ({}, {"groups": []}):
        data = template(lambda d: d.__setitem__("ui", ui))
        row = graphstyle.template_row(data, KNOWN, "t.json")
        assert row["state"] == "WARN" and row["reasons"][0].startswith("legacy template without a ui block"), (ui, row)
    data = template(static_load)
    del data["ui"]
    row = graphstyle.template_row(data, KNOWN, "t.json")
    assert row["state"] == "WARN", row
    rule(row["reasons"], "load-image", "node 2 (LoadImage")


@case("template malformed shapes: one layout violation, never an exception")
def _():
    bad = [
        lambda d: d.__setitem__("workflow", []),
        lambda d: d.__setitem__("workflow", {}),
        lambda d: d["workflow"]["4"].pop("class_type"),
        lambda d: d["ui"]["groups"][0]["nodes"].append("99"),
        lambda d: d["ui"]["groups"][1]["nodes"].append("1"),
        lambda d: d["ui"].__setitem__("groups", "Prompt"),
        lambda d: d["workflow"]["4"].__setitem__("class_type", "NoSuchNode"),
    ]
    for i, mutate in enumerate(bad):
        violations = graphstyle.template_violations(template(mutate), KNOWN)
        assert violations and all(v.startswith("layout:") for v in violations), (i, violations)
        assert len(violations) == 1, (i, violations)


@case("graphstyle imports stdlib only (loaded as the quality plugin loads it, scripts/assetgen not on sys.path)")
def _():
    code = ("import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location('graphstyle_private', sys.argv[1])\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "assert 'uiworkflow' not in sys.modules\n"
            "print(m.CHECK)\n")
    r = subprocess.run([sys.executable, "-B", "-I", "-c", code, os.path.join(ENGINE, "graphstyle.py")],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=os.path.dirname(ROOT))
    assert r.returncode == 0 and r.stdout.strip() == "assetgen-graph-style", r.stderr


# -- UI form (a run's workflow.ui.json) ----------------------------------------------------------------------------

@case("UI form: the clean template rendered for a run (prefix assetgen/<run_id>-final) has no violation, ui_row PASS")
def _():
    ui = ui_form()
    assert node(ui, 6)["widgets_values"] == ["assetgen/%s-final" % RUN_ID], node(ui, 6)
    assert graphstyle.ui_violations(ui, KNOWN) == []
    assert graphstyle.ui_violations(ui, KNOWN, prefix="assetgen/" + RUN_ID) == []
    row = graphstyle.ui_row(ui, KNOWN, "workflow.ui.json")
    assert row == {"path": "workflow.ui.json", "check": graphstyle.CHECK, "state": "PASS", "reasons": []}, row


def _ui_fail(rule_id, mutate, names, prefix=None):
    def fn():
        ui = ui_form()
        assert graphstyle.ui_violations(ui, KNOWN, prefix=None) == [], "the clean UI form must pass"
        mutate(ui)
        violations = graphstyle.ui_violations(ui, KNOWN, prefix=prefix)
        rule(violations, rule_id, *names)
        row = graphstyle.ui_row(ui, KNOWN, "workflow.ui.json", prefix)
        assert row["state"] == "FAIL" and row["reasons"] == violations, row
    return fn


def ui_outside(ui):
    node(ui, 4)["pos"] = [5000, 5000]


def ui_drop_note(ui):
    out = group(ui, "Output")
    notes = [n for n in ui["nodes"] if n["type"] == "Note" and inside(n, out)]
    assert len(notes) == 1, notes
    ui["nodes"].remove(notes[0])


def ui_retitle(ui):
    group(ui, "Post-process")["title"] = "Final"


def ui_save_into_post(ui):
    box = group(ui, "Post-process")["bounding"]
    save = node(ui, 6)
    save["pos"] = [box[0] + 10, box[1] + 40]
    assert inside(save, group(ui, "Post-process")) and not inside(save, group(ui, "Output")), (save, box)


def ui_bare_prefix(ui):
    node(ui, 6)["widgets_values"] = ["assetgen/" + RUN_ID]


def ui_swap_order(ui):
    refs, gen = group(ui, "References"), group(ui, "Generate")
    refs["title"], gen["title"] = "Generate", "References"


def ui_two_groups(ui):
    gen, post = group(ui, "Generate"), group(ui, "Post-process")
    x, y, w, h = gen["bounding"]
    px, py, pw, ph = post["bounding"]
    gen["bounding"] = [x, y, px + pw - x, max(h, py + ph - y)]


def ui_class_title(ui):
    node(ui, 4)["title"] = "ImageScale"


def ui_literal_prompt(ui):
    image = node(ui, 3)
    socket = next(s for s in image["inputs"] if s["name"] == "user_prompt")
    ui["links"] = [l for l in ui["links"] if l[0] != socket["link"]]
    socket["link"] = None
    image["widgets_values"][0] = "A literal prompt typed into the node."


UI_FAILS = [
    ("group", "a node moved outside every group", ui_outside, ("node 4 (ImageScale",), None),
    ("group", "a node inside two group boundings", ui_two_groups, ("node 4 (ImageScale", 'group "Generate"', 'group "Post-process"'), None),
    ("note", "the Output group's Note removed", ui_drop_note, ('group "Output"',), None),
    ("vocabulary", "a group retitled outside the vocabulary", ui_retitle, ('group "Final"',), None),
    ("order", "References and Generate titles swapped", ui_swap_order, ('group "',), None),
    ("save-output", "the SaveImage moved into Post-process", ui_save_into_post, ("node 6 (SaveImage",), None),
    ("save-suffix", "filename_prefix equal to the run prefix (no suffix)", ui_bare_prefix, ("node 6 (SaveImage",), None),
    ("save-suffix", "an explicit prefix argument the value does not start with", lambda ui: None, ("node 6 (SaveImage",), "assetgen/other-run"),
    ("title", "a node titled with its class name", ui_class_title, ("node 4 (ImageScale",), None),
    ("prompt", "user_prompt as a literal widget value, the link removed", ui_literal_prompt, ("node 3 (NineRouterImage",), None),
]

for _rule, _label, _mutate, _names, _prefix in UI_FAILS:
    case("UI %s: %s FAILS, naming %s" % (_rule, _label, " ".join(_names)))(_ui_fail(_rule, _mutate, _names, _prefix))


@case("UI save-suffix: without a prefix argument and without extra.assetgen.run_id it FAILS (run prefix unknown), never skips")
def _():
    ui = ui_form(extra=False)
    assert "extra" not in ui or not (ui.get("extra") or {}).get("assetgen"), ui.get("extra")
    hits = rule(graphstyle.ui_violations(ui, KNOWN), "save-suffix", "node 6 (SaveImage", "run prefix is unknown")
    assert len(hits) == 1, hits
    row = graphstyle.ui_row(ui, KNOWN, "workflow.ui.json")
    assert row["state"] == "FAIL", row
    ui_bare_prefix(ui)
    rule(graphstyle.ui_violations(ui, KNOWN), "save-suffix", "node 6 (SaveImage", "run prefix is unknown")


@case("UI save-suffix: a prefix argument stands in for a missing extra.assetgen.run_id (suffixed PASS, unsuffixed FAIL)")
def _():
    ui = ui_form(extra=False)
    assert graphstyle.ui_violations(ui, KNOWN, prefix="assetgen/" + RUN_ID) == []
    assert graphstyle.ui_row(ui, KNOWN, "workflow.ui.json", "assetgen/" + RUN_ID)["state"] == "PASS"
    ui_bare_prefix(ui)
    hits = rule(graphstyle.ui_violations(ui, KNOWN, prefix="assetgen/" + RUN_ID), "save-suffix", "node 6 (SaveImage")
    assert not any("unknown" in h for h in hits), hits


@case("UI save-suffix: the prefix argument wins over extra.assetgen.run_id")
def _():
    ui = ui_form()
    rule(graphstyle.ui_violations(ui, KNOWN, prefix="assetgen/other-run-001"), "save-suffix", "node 6 (SaveImage",
         '"assetgen/other-run-001"')


@case("UI load-image: skipped (render fills it; a static file name in workflow.ui.json is fine)")
def _():
    ui = ui_form()
    assert node(ui, 2)["widgets_values"][0] == "ref.png", node(ui, 2)
    no_rule(graphstyle.ui_violations(ui, KNOWN), "load-image")


def anchored_graph(image_name, titled=False):
    """The rendered clean graph plus style-lock reference nodes like render's wire_references adds: a LoadImage of
    image_name and two ImageBatch nodes feeding NineRouterImage.reference_images; titled or not, in no group."""
    graph = render_graph(template())
    graph["7"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    graph["8"] = {"class_type": "ImageBatch", "inputs": {"image1": ["2", 0], "image2": ["7", 0]}}
    graph["9"] = {"class_type": "ImageBatch", "inputs": {"image1": ["8", 0], "image2": ["7", 0]}}
    if titled:
        for nid, title in (("7", "Anchor a-canon (strong)"), ("8", "Reference batch 1"), ("9", "Reference batch 2")):
            graph[nid]["_meta"] = {"title": title}
    graph["3"]["inputs"]["reference_images"] = ["9", 0]
    return graph


ANCHOR_NODES = ((7, "LoadImage"), (8, "ImageBatch"), (9, "ImageBatch"))


def with_references(data, ids):
    """The template with ids added to its References group (as render's ui_with_references does)."""
    data = copy.deepcopy(data)
    group = next(g for g in data["ui"]["groups"] if g["title"] == "References")
    group["nodes"] = group["nodes"] + list(ids)
    return data


@case("UI: no exemption by file name: ungrouped, untitled anchor-<id>.png LoadImage/ImageBatch nodes FAIL title and group, naming each")
def _():
    ui = ui_form(graph=anchored_graph("anchor-a-canon.png"))
    assert not any(inside(node(ui, n), g) for n, _ in ANCHOR_NODES for g in ui["groups"]), "anchor nodes laid out in a group"
    violations = graphstyle.ui_violations(ui, KNOWN)
    for nid, ctype in ANCHOR_NODES:
        rule(violations, "group", "node %d (%s" % (nid, ctype))
        rule(violations, "title", "node %d (%s" % (nid, ctype))


@case("UI: titled anchor nodes outside every group FAIL group only, naming each")
def _():
    violations = graphstyle.ui_violations(ui_form(graph=anchored_graph("anchor-a-canon.png", titled=True)), KNOWN)
    for nid, ctype in ANCHOR_NODES:
        rule(violations, "group", "node %d (%s" % (nid, ctype))
    no_rule(violations, "title")


@case("UI: an untitled anchor-named LoadImage inside the References group FAILS title, naming it")
def _():
    graph = anchored_graph("anchor-a-canon.png", titled=True)
    del graph["7"]["_meta"]
    ui = ui_form(with_references(template(), ["7", "8", "9"]), graph=graph)
    assert all(inside(node(ui, n), group(ui, "References")) for n, _ in ANCHOR_NODES)
    violations = graphstyle.ui_violations(ui, KNOWN)
    hits = rule(violations, "title", "node 7 (LoadImage")
    assert len(hits) == 1, hits
    no_rule(violations, "group")


@case("UI: titled anchor nodes inside the References group PASS")
def _():
    ui = ui_form(with_references(template(), ["7", "8", "9"]), graph=anchored_graph("anchor-a-canon.png", titled=True))
    assert all(inside(node(ui, n), group(ui, "References")) for n, _ in ANCHOR_NODES)
    assert graphstyle.ui_violations(ui, KNOWN) == []


def rendered_anchors(data):
    """(graph, ui block) as render builds them: the filled template plus wire_references' anchor nodes, and the
    template ui through assetgen.ui_with_references."""
    import assetgen
    graph = render_graph(data)
    assert assetgen.wire_references(graph, [{"anchor_id": "a-canon", "strength": "strong"},
                                            {"anchor_id": "b-pose", "strength": "medium"}]) == []
    return graph, assetgen.ui_with_references(data.get("ui"), graph, data["workflow"])


@case("render ui_with_references: anchor nodes join the template's References group (copy, template unchanged) and PASS")
def _():
    data = template()
    before = copy.deepcopy(data)
    graph, ui_block = rendered_anchors(data)
    assert data == before, "ui_with_references changed the template data"
    added = sorted(set(graph) - set(data["workflow"]), key=int)
    assert added == ["7", "8", "9", "10"], added
    assert group({"groups": ui_block["groups"]}, "References")["nodes"] == ["2"] + added, ui_block["groups"]
    assert ui_block["notes"] == data["ui"]["notes"], "an existing References group gets no extra Note"
    ui = uiworkflow.to_ui(graph, KNOWN, {"assetgen": {"run_id": RUN_ID}}, ui_block)
    assert all(inside(node(ui, int(n)), group(ui, "References")) for n in added)
    assert graphstyle.ui_violations(ui, KNOWN) == []


@case("render ui_with_references: without a References group a new one (with a Note) goes after Prompt and PASSES")
def _():
    def no_refs(d):
        d["workflow"]["3"]["inputs"].pop("reference_images")
        del d["workflow"]["2"]
        del d["params"]["reference_image"]
        d["ui"]["groups"] = [g for g in d["ui"]["groups"] if g["title"] != "References"]
        d["ui"]["notes"] = [n for n in d["ui"]["notes"] if n["group"] != "References"]
    data = template(no_refs)
    assert graphstyle.template_violations(data, KNOWN) == []
    graph, ui_block = rendered_anchors(data)
    titles = [g["title"] for g in ui_block["groups"]]
    assert titles == ["Prompt", "References", "Generate", "Post-process", "Output"], titles
    refs = group({"groups": ui_block["groups"]}, "References")
    assert refs["nodes"] == sorted(set(graph) - set(data["workflow"]), key=int) and refs["color"] in uiworkflow.PALETTE, refs
    assert [n for n in ui_block["notes"] if n["group"] == "References"], ui_block["notes"]
    assert [g["title"] for g in data["ui"]["groups"]] == ["Prompt", "Generate", "Post-process", "Output"]
    ui = uiworkflow.to_ui(graph, KNOWN, {"assetgen": {"run_id": RUN_ID}}, ui_block)
    assert graphstyle.ui_violations(ui, KNOWN) == []


@case("render ui_with_references: a legacy ui (none, or no groups) and a graph without added nodes come back as is")
def _():
    import assetgen
    graph = render_graph(template())
    wf = template()["workflow"]
    assert assetgen.ui_with_references(None, graph, wf) is None
    legacy = {"notes": []}
    assert assetgen.ui_with_references(legacy, dict(graph, **{"99": {}}), wf) is legacy
    ui_block = template()["ui"]
    assert assetgen.ui_with_references(ui_block, graph, wf) is ui_block


@case("UI: a MarkdownNote counts as a group's note")
def _():
    ui = ui_form()
    out = group(ui, "Output")
    note = next(n for n in ui["nodes"] if n["type"] == "Note" and inside(n, out))
    note["type"] = "MarkdownNote"
    assert graphstyle.ui_violations(ui, KNOWN) == []


@case("UI malformed shapes and unknown node types: layout/unknown violations, never an exception")
def _():
    rule(graphstyle.ui_violations({"nodes": {}}, KNOWN), "layout")
    rule(graphstyle.ui_violations([], KNOWN), "layout")
    ui = ui_form()
    ui["links"][0] = ["x"]
    rule(graphstyle.ui_violations(ui, KNOWN), "layout")
    ui = ui_form()
    socket = next(s for s in node(ui, 3)["inputs"] if s["name"] == "user_prompt")
    socket["link"] = 999
    rule(graphstyle.ui_violations(ui, KNOWN), "layout", "999")
    ui = ui_form()
    node(ui, 4)["type"] = "NoSuchNode"
    rule(graphstyle.ui_violations(ui, KNOWN), "unknown", "node 4 (NoSuchNode")
    row = graphstyle.ui_row({"nodes": "x"}, KNOWN, "w.json")
    assert row["state"] == "FAIL" and row["reasons"][0].startswith("layout:"), row


def main():
    failed = 0
    for n, (name, fn) in enumerate(CASES, 1):
        try:
            fn()
            print("ok %d - %s" % (n, name))
        except Exception:
            failed += 1
            print("not ok %d - %s" % (n, name))
            print("  " + traceback.format_exc().strip().replace("\n", "\n  "))
    print("%d case(s), %d failed" % (len(CASES), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
