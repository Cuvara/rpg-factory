"""Self-test of the asset-gen style engine: approval records (approval.py), the manifest status rule, the uncommitted
approval grade of gen-run-style, cross-family anchor selection, style-id drift and the structured-style lint WARN.

Every case runs on a throwaway authoring git repo under a temp dir (never the plugin checkout). The quality plugin is
called as tests/assetgen.test.sh calls it (domains._api.Context), with the real ctx.approval (artifact-trace rules).
Prints 'ok N - <name>' or 'not ok N - <name>' per case and exits 1 when any case fails.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "assetgen"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "checks"))

import approval  # noqa: E402
import layers  # noqa: E402
import lint  # noqa: E402
import stylelock  # noqa: E402
from domains._api import Context  # noqa: E402

_spec = importlib.util.spec_from_file_location("assetgen_plugin_selftest", os.path.join(ROOT, "scripts", "checks", "domains", "assetgen.py"))
plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plugin)
REG = json.load(open(os.path.join(ROOT, "registry.json"), encoding="utf-8"))
TMP = tempfile.mkdtemp(prefix="style-selftest-")
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="Self Test", GIT_AUTHOR_EMAIL="selftest@example.invalid",
               GIT_COMMITTER_NAME="Self Test", GIT_COMMITTER_EMAIL="selftest@example.invalid",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=GIT_ENV)
    assert r.returncode == 0, "git %s: %s" % (" ".join(args), r.stderr)
    return r.stdout.strip()


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, indent=2))
    return path


def repo(name):
    """A fresh authoring git repo with one style rpg-base v1 (structured fields) in the game layer."""
    a = os.path.join(TMP, name)
    os.makedirs(a)
    git(a, "init", "-q")
    write(os.path.join(a, "assetgen", "styles", "rpg-base.json"), {
        "schema": "rpg-factory.assetgen-style/1", "title": "RPG base", "version": 1, "status": "active",
        "prefix": "RPG base art,", "palette": {"text": "warm", "colors": [{"hex": "#aa5533", "role": "primary"}]}})
    return a


def run_md(a, rid, status="proposed", spec=None, extra=None):
    front = {"id": "AGEN-" + rid, "kind": "gen-run", "domain": "assetgen", "schema_version": 2, "status": status,
             "title": rid, "authors": [{"kind": "agent", "id": "claude"}],
             "provenance": {"generated_by": "claude", "tool": "comfyui", "model": "m"},
             "spec": dict({"run_id": rid, "prompt_author": "claude", "prompt_review": {"by": "gemini-2", "state": "PASS"},
                           "outputs": [{"path": "outputs/a.png", "sha256": "1" * 64}]}, **(spec or {}))}
    front.update(extra or {})
    body = "# %s\n\n- QA: PASS\n- Status: %s (approval is human-only)\n\n## Prompt\n\np\n" % (rid, status)
    write(os.path.join(a, "assetgen", "runs", rid, "run.md"), "---json\n%s\n---\n%s" % (json.dumps(front, indent=2), body))
    return os.path.join(a, "assetgen", "runs", rid)


def refused(fn, text):
    try:
        fn()
    except layers.SpecError as exc:
        assert text in str(exc), "refusal %r lacks %r" % (str(exc), text)
        return
    raise AssertionError("not refused (expected %r)" % text)


# -- approve_record --------------------------------------------------------------------------------------------

@case("approve_record refuses an empty or missing --by")
def _():
    a = repo("refuse-by")
    rd = run_md(a, "r-001")
    refused(lambda: approval.approve_record(rd, ""), "needs --by")
    refused(lambda: approval.approve_record(rd, "   "), "needs --by")
    refused(lambda: approval.approve_record(rd, None), "needs --by")
    assert not os.path.isdir(os.path.join(a, "approvals")), "a refused call wrote an approval"


@case("approve_record refuses agent and model names and the run's own agents and reviewers")
def _():
    a = repo("refuse-agent")
    rd = run_md(a, "r-001")
    before = open(os.path.join(rd, "run.md"), encoding="utf-8").read()
    for name in ("claude", "Claude-Opus", "codex", "gpt-5", "SAME_MODEL:claude"):
        refused(lambda: approval.approve_record(rd, name), "agent or model")
    refused(lambda: approval.approve_record(rd, "gemini-2"), "recorded in this run")
    assert open(os.path.join(rd, "run.md"), encoding="utf-8").read() == before, "run.md changed on a refusal"
    assert not os.path.isdir(os.path.join(a, "approvals"))


@case("approve_record refuses a draft run and a run directory outside assetgen/runs")
def _():
    a = repo("refuse-status")
    refused(lambda: approval.approve_record(run_md(a, "d-001", status="draft"), "Dana"), "is draft")
    other = os.path.join(a, "elsewhere", "x-001")
    os.makedirs(other)
    refused(lambda: approval.approve_record(other, "Dana"), "must be <authoring>/assetgen/runs/")


@case("approve_record: run.md status approved (body kept), record shape and rev = git blob of run.md")
def _():
    a = repo("record")
    rd = run_md(a, "r-001")
    out = approval.approve_record(rd, "Dana", note="approved in chat", today="2026-11-08")
    text = open(os.path.join(rd, "run.md"), encoding="utf-8").read()
    front, body = approval.split_front(text)
    assert front["status"] == "approved" and "- Status: approved (approval is human-only)" in body and "## Prompt" in body, text
    rel_md = "assetgen/runs/r-001/run.md"
    rev = git(a, "hash-object", "--", rel_md)
    assert out["rev"] == rev, (out["rev"], rev)
    rel = "approvals/AGEN-r-001/assetgen-approval-%s.json" % rev
    assert os.path.normcase(out["approval"]) == os.path.normcase(os.path.join(a, rel)), out["approval"]
    rec = json.load(open(out["approval"], encoding="utf-8"))
    assert rec == {"artifact": "AGEN-r-001", "gate": "assetgen-approval", "scope": "assetgen", "rev": rev,
                   "date": "2026-11-08", "by": "Dana", "note": "approved in chat"}, rec
    assert "assetgen-approval" in REG["domains"]["assetgen"]["human_gates"]
    # artifact-trace reads it once committed: past path, content, rev and date to the signature (unsigned here)
    git(a, "add", "-A")
    git(a, "commit", "-qm", "approve")
    trace = importlib.util.spec_from_file_location("artifact_trace_selftest", os.path.join(ROOT, "scripts", "checks", "artifact-trace.py"))
    mod = importlib.util.module_from_spec(trace)
    trace.loader.exec_module(mod)
    reason = mod.approval(a, rel_md, front, "assetgen-approval", REG)
    assert reason in ("no trusted approver keys", "approval signature untrusted or invalid"), reason
    again = approval.approve_record(rd, "Dana", note="approved in chat", today="2026-11-08")
    assert again["rev"] == rev, "approving an approved run again changed run.md"


@case("approve_record never overwrites a record: same approval is a no-op, another one for the rev is refused")
def _():
    a = repo("immutable")
    rd = run_md(a, "r-001")
    md = os.path.join(rd, "run.md")
    first = approval.approve_record(rd, "Dana", note="ok", today="2026-11-08")
    record = open(first["approval"], "rb").read()
    approved = open(md, "rb").read()
    same = approval.approve_record(rd, "Dana", note="ok", today="2026-11-08")
    assert same["approval"] == first["approval"] and same["rev"] == first["rev"], same
    for kw in ({"by": "Robin", "note": "ok", "today": "2026-11-08"}, {"by": "Dana", "note": "other", "today": "2026-11-08"},
               {"by": "Dana", "note": "ok", "today": "2026-11-09"}, {"by": "Dana", "note": None, "today": "2026-11-08"}):
        refused(lambda: approval.approve_record(rd, kw["by"], note=kw["note"], today=kw["today"]), "never overwritten")
        assert open(first["approval"], "rb").read() == record, "a refused re-approval changed the record (%r)" % kw
        assert open(md, "rb").read() == approved, "a refused re-approval changed run.md (%r)" % kw
    # a changed run.md is another revision: a new record next to the old one, which stays as it was
    with open(md, "wb") as f:
        f.write(approved.replace(b'"title": "r-001"', b'"title": "r-001 v2"'))
    second = approval.approve_record(rd, "Robin", today="2026-11-09")
    assert second["rev"] != first["rev"] and os.path.isfile(second["approval"]), second
    assert open(first["approval"], "rb").read() == record, "a new revision touched the old record"


@case("approve_record parses a CRLF run.md, keeps CRLF, and rev = git hash-object with the repo's line-ending filter")
def _():
    for autocrlf in ("input", "false"):
        a = repo("crlf-" + autocrlf)
        git(a, "config", "core.autocrlf", autocrlf)
        rd = run_md(a, "r-001")
        md = os.path.join(rd, "run.md")
        lf = open(md, "rb").read()
        with open(md, "wb") as f:
            f.write(lf.replace(b"\n", b"\r\n"))
        out = approval.approve_record(rd, "Dana", today="2026-11-08")
        data = open(md, "rb").read()
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b""), "line endings not kept: %r" % data[:80]
        front, body = approval.split_front(data.decode("utf-8"))
        assert front["status"] == "approved" and "- Status: approved (approval is human-only)\r\n" in body, body
        rel_md = "assetgen/runs/r-001/run.md"
        rev = subprocess.run(["git", "-C", a, "hash-object", "--", rel_md], stdout=subprocess.PIPE, text=True).stdout.strip()
        assert out["rev"] == rev, (autocrlf, out["rev"], rev)
        assert (rev == approval.git_blob(data)) == (autocrlf == "false"), (autocrlf, rev)
        if autocrlf == "input":
            # committed, the blob is the LF text: the record's rev is that blob (what artifact-trace binds)
            git(a, "-c", "core.autocrlf=input", "add", "-A")
            git(a, "-c", "core.autocrlf=input", "commit", "-qm", "approve")
            assert git(a, "rev-parse", "HEAD:" + rel_md) == out["rev"]


# -- keep_status -----------------------------------------------------------------------------------------------

def front(status, **spec):
    base = {"outputs": [{"path": "outputs/a.png", "sha256": "1" * 64}], "prompt_sha256": "2" * 64,
            "purpose": {"id": "p", "sha256": "3" * 64}, "style": {"id": "s", "sha256": "4" * 64},
            "template": {"id": "t", "sha256": "5" * 64}, "params": {"size": "1024x1024"},
            "qa": {"state": "PASS", "results": []}, "image_review": {"by": "codex", "state": "PASS"}}
    base.update(spec)
    return {"status": status, "title": "t", "spec": base}


@case("keep_status: approved stays approved when nothing bound changed (title only)")
def _():
    old = front("approved")
    new = dict(front("proposed"), title="another title")
    assert approval.bound_changes(old, new) == [], approval.bound_changes(old, new)
    assert approval.keep_status(old, new) == "approved"


@case("keep_status: approved becomes proposed when outputs, params or a review changed, and says what")
def _():
    old = front("approved")
    for new, want in ((front("proposed", outputs=[{"path": "outputs/a.png", "sha256": "9" * 64}]), "outputs"),
                      (front("proposed", params={"size": "512x512"}), "requirements (purpose, style, template or params)"),
                      (front("proposed", image_review={"by": "codex", "state": "FAIL"}), "image review")):
        assert approval.keep_status(old, new) == "proposed", new
        assert want in approval.bound_changes(old, new), approval.bound_changes(old, new)


@case("keep_status: other statuses stay while the outputs are the same; no earlier run.md is proposed")
def _():
    assert approval.keep_status(front("reviewed"), front("proposed", qa={"state": "FAIL"})) == "reviewed"
    assert approval.keep_status(front("reviewed"), front("proposed", outputs=[])) == "proposed"
    assert approval.keep_status(None, front("proposed")) == "proposed"
    assert approval.keep_status({}, front("proposed")) == "proposed"


# -- gen-run-style: an approval on disk that is not committed or signed --------------------------------------

def anchor(a, aid, src, family="props", status="active", n=0):
    d = os.path.join(a, "assetgen", "styles", "rpg-base", "anchors")
    os.makedirs(d, exist_ok=True)
    data = b"\x89PNG anchor " + bytes([n])
    open(os.path.join(d, aid + ".png"), "wb").write(data)
    sha = hashlib.sha256(data).hexdigest()
    ref = stylelock.style_ref(layers.load("style", "rpg-base", a))
    write(os.path.join(d, aid + ".json"), {
        "schema": stylelock.ANCHOR_SCHEMA, "id": aid, "status": status, "style": ref, "family": family,
        "dimensions": ["palette"], "strength": "canonical", "image": aid + ".png", "image_sha256": sha,
        "source_run": {"run_id": src, "output": "outputs/a.png", "sha256": sha},
        "approved_by": "Dana" if status == "active" else None, "approved_on": "2026-11-08" if status == "active" else None})
    return ref, sha


def style_row(a, rid, ref, aid, sha):
    spec = {"run_id": rid, "style": {"id": ref["style_id"], "layer": "game", "sha256": ref["sha256"]}, "outputs": [],
            "style_lock": {"project": None, "family": "props", "family_source": "purpose", "style": ref, "override": None,
                           "max_references": 3, "rejections": [], "references": [{"anchor_id": aid, "sha256": sha}]}}
    obj = {"id": "AGEN-" + rid, "kind": "gen-run", "status": "proposed", "spec": spec}
    artifacts = {}
    src = "src-001"
    md = os.path.join(a, "assetgen", "runs", src, "run.md")
    if os.path.isfile(md):
        artifacts["AGEN-" + src] = ("assetgen/runs/%s/run.md" % src, approval.split_front(open(md, encoding="utf-8").read())[0])
    ctx = Context(a, REG, "assetgen/runs/%s/run.md" % rid, artifacts, None, {"authoring": a})
    rows = [r for r in plugin.check(obj, ctx) if r.check == "gen-run-style"]
    assert len(rows) == 1, rows
    return rows[0]


def approval_repo(name):
    a = repo(name)
    run_md(a, "src-001")
    ref, sha = anchor(a, "a-src", "src-001")
    git(a, "add", "-A")
    git(a, "commit", "-qm", "seed")
    return a, ref, sha


@case("gen-run-style: approval written, nothing committed -> HUMAN_REQUIRED 'present but not committed/signed'")
def _():
    a, ref, sha = approval_repo("pending-all")
    approval.approve_record(os.path.join(a, "assetgen", "runs", "src-001"), "Dana", today="2026-11-08")
    row = style_row(a, "use-001", ref, "a-src", sha)
    text = "; ".join(row.reasons)
    assert row.state == "HUMAN_REQUIRED" and "present but not committed/signed" in text and "AGEN-src-001" in text, (row.state, text)


@case("gen-run-style: run.md committed approved, approval record uncommitted -> HUMAN_REQUIRED")
def _():
    a, ref, sha = approval_repo("pending-record")
    out = approval.approve_record(os.path.join(a, "assetgen", "runs", "src-001"), "Dana", today="2026-11-08")
    git(a, "add", "assetgen")
    git(a, "commit", "-qm", "run approved")
    assert os.path.isfile(out["approval"])
    row = style_row(a, "use-001", ref, "a-src", sha)
    assert row.state == "HUMAN_REQUIRED" and "present but not committed/signed" in "; ".join(row.reasons), (row.state, row.reasons)


@case("gen-run-style: approval committed but unsigned (no trusted key) -> HUMAN_REQUIRED, not FAIL")
def _():
    a, ref, sha = approval_repo("unsigned")
    approval.approve_record(os.path.join(a, "assetgen", "runs", "src-001"), "Dana", today="2026-11-08")
    git(a, "add", "-A")
    git(a, "commit", "-qm", "approve")
    row = style_row(a, "use-001", ref, "a-src", sha)
    assert row.state == "HUMAN_REQUIRED" and "present but not committed/signed" in "; ".join(row.reasons), (row.state, row.reasons)


@case("gen-run-style: approved in run.md with no approval file stays FAIL 'missing'")
def _():
    a, ref, sha = approval_repo("no-record")
    md = os.path.join(a, "assetgen", "runs", "src-001", "run.md")
    text = open(md, encoding="utf-8").read().replace('"status": "proposed"', '"status": "approved"', 1)
    write(md, text)
    git(a, "commit", "-qam", "approved by hand")
    row = style_row(a, "use-001", ref, "a-src", sha)
    text = "; ".join(row.reasons)
    assert row.state == "FAIL" and "approval of source gen-run AGEN-src-001 is missing" in text \
        and "present but not committed" not in text, (row.state, text)


@case("gen-run-style: a real FAIL next to a pending approval still FAILS")
def _():
    a, ref, sha = approval_repo("pending-and-fail")
    approval.approve_record(os.path.join(a, "assetgen", "runs", "src-001"), "Dana", today="2026-11-08")
    row = style_row(a, "use-001", ref, "a-gone", "0" * 64)
    assert row.state == "FAIL", (row.state, row.reasons)


# -- cross-family selection ------------------------------------------------------------------------------------

def records(*specs):
    out = []
    for aid, fam, strength in specs:
        out.append({"id": aid, "errors": [], "data": {"id": aid, "family": fam, "strength": strength, "dimensions": ["palette"],
                                                      "style": {"style_id": "rpg-base", "version": 1}, "image_sha256": "a" * 64}})
    return out


STYLE = {"style_id": "rpg-base", "version": 1, "sha256": "b" * 64}


@case("selection warns when a picked anchor is of another family (fallback allowed by default)")
def _():
    anchors = records(("c-hero", "characters", "canonical"), ("p-barrel", "props", "strong"))
    picks, warns = stylelock.select_with_warnings(anchors, STYLE, "props", ["palette"], 3)
    assert [p["anchor_id"] for p in picks] == ["p-barrel", "c-hero"], picks
    assert len(warns) == 1 and "c-hero is a characters anchor" in warns[0] and "props" in warns[0], warns
    picks, warns = stylelock.select_with_warnings(anchors, STYLE, "props", ["palette"], 1)
    assert [p["anchor_id"] for p in picks] == ["p-barrel"] and warns == [], (picks, warns)
    assert stylelock.select_with_warnings(anchors, STYLE, None, [], 3)[1] == [], "a run without a family warns"


@case("anchor_family_fallback false selects only same-family anchors (none when there are none)")
def _():
    anchors = records(("c-hero", "characters", "canonical"), ("p-barrel", "props", "strong"))
    picks, warns = stylelock.select_with_warnings(anchors, STYLE, "props", [], 3, fallback=False)
    assert [p["anchor_id"] for p in picks] == ["p-barrel"] and len(warns) == 1 and "1 anchor(s)" in warns[0], (picks, warns)
    picks, warns = stylelock.select_with_warnings(records(("c-hero", "characters", "canonical")), STYLE, "props", [], 3, fallback=False)
    assert picks == [] and "were not selected" in warns[0], (picks, warns)
    assert stylelock.select_references(anchors, STYLE, "props", [], 3) == stylelock.select_references(anchors, STYLE, "props", [], 3, True)


@case("anchor_family_fallback: purpose wins over project.json, default true; non-bool values are errors")
def _():
    a = repo("fallback")
    assert stylelock.family_fallback({}, a) is True
    proj = {"schema": stylelock.PROJECT_SCHEMA, "style": {"id": "rpg-base", "version": 1}, "anchor_family_fallback": False}
    write(stylelock.project_path(a), proj)
    assert stylelock.project_errors(proj, a) == [], stylelock.project_errors(proj, a)
    assert stylelock.family_fallback({}, a) is False
    assert stylelock.family_fallback({"anchor_family_fallback": True}, a) is True
    assert stylelock.purpose_errors({"anchor_family_fallback": False}) == []
    assert "anchor_family_fallback must be true or false" in stylelock.purpose_errors({"anchor_family_fallback": "no"})
    assert "anchor_family_fallback must be true or false" in stylelock.project_errors(dict(proj, anchor_family_fallback=0))
    schema = json.load(open(os.path.join(ROOT, "docs", "schemas", "assetgen-project.schema.json"), encoding="utf-8"))
    assert schema["properties"]["anchor_family_fallback"]["type"] == "boolean"


# -- drift: style id mismatch ----------------------------------------------------------------------------------

@case("drift reports anchors and runs whose style id is not the project's (style-id-mismatch), not family styles")
def _():
    a = repo("drift")
    g = os.path.join(a, "assetgen")
    write(os.path.join(g, "styles", "explore.json"), {"schema": "rpg-factory.assetgen-style/1", "title": "Explore", "version": 1})
    write(os.path.join(g, "styles", "rpg-chars.json"), {"extends": "rpg-base", "title": "Chars"})
    write(stylelock.project_path(a), {"schema": stylelock.PROJECT_SCHEMA, "style": {"id": "rpg-base", "version": 1},
                                      "allowed_styles": ["explore"], "families": {"characters": "rpg-chars"}})
    explore = stylelock.style_ref(layers.load("style", "explore", a))
    base = stylelock.style_ref(layers.load("style", "rpg-base", a))
    chars = stylelock.style_ref(layers.load("style", "rpg-chars", a))
    for rid, ref in (("ex-001", explore), ("base-001", base), ("chars-001", chars)):
        run_md(a, rid, spec={"style_lock": {"style": ref}})
    d = os.path.join(g, "styles", "explore", "anchors")
    write(os.path.join(d, "e-1.json"), {"id": "e-1", "style": explore})
    write(os.path.join(g, "styles", "rpg-base", "anchors", "b-1.json"), {"id": "b-1", "style": base})
    items = stylelock.drift(a)["items"]
    got = sorted((i["kind"], i["id"], i["state"]) for i in items)
    assert got == [("anchor", "e-1", "style-id-mismatch"), ("gen-run", "AGEN-ex-001", "style-id-mismatch")], got
    assert all(i["project_style"] == "rpg-base" and i["version_state"] is None for i in items), items
    os.remove(stylelock.project_path(a))
    assert stylelock.drift(a)["items"] == [], "without project.json there is no project style to mismatch"


@case("drift: a mismatched style that is also behind keeps its version state apart")
def _():
    a = repo("drift-version")
    g = os.path.join(a, "assetgen")
    write(os.path.join(g, "styles", "explore.json"), {"schema": "rpg-factory.assetgen-style/1", "title": "Explore", "version": 2})
    write(stylelock.project_path(a), {"schema": stylelock.PROJECT_SCHEMA, "style": {"id": "rpg-base", "version": 1}})
    write(os.path.join(g, "styles", "explore", "anchors", "e-1.json"), {"id": "e-1", "style": {"style_id": "explore", "version": 1, "sha256": "1" * 64}})
    run_md(a, "gone-001", spec={"style_lock": {"style": {"style_id": "gone", "version": 1, "sha256": "2" * 64}}})
    got = sorted((i["id"], i["state"], i.get("version_state")) for i in stylelock.drift(a)["items"])
    assert got == [("AGEN-gone-001", "style-missing", None), ("e-1", "style-id-mismatch", "older-version")], got


# -- lint: an active game style without structured fields ------------------------------------------------------

@case("lint WARNs an active game style without structured fields; no WARN with them, when deprecated, or for core")
def _():
    a = repo("lint")
    g = os.path.join(a, "assetgen", "styles")
    bare = write(os.path.join(g, "bare.json"), {"schema": "rpg-factory.assetgen-style/1", "title": "Bare", "version": 1,
                                               "status": "active", "palette": "warm earth tones", "prefix": "art,"})
    res = lint.lint_file(bare, a)
    assert res["state"] == "WARN" and any("every style-* QA row would be NOT_AVAILABLE" in r for r in res["reasons"]), res
    res = lint.lint_file(os.path.join(g, "rpg-base.json"), a)
    assert res["state"] == "PASS", res
    for name, extra in (("toned", {"tone": {"tolerance": 0.1}}), ("canvased", {"canvas": {"props": {"aspect": "1:1"}}}),
                        ("old", {"status": "deprecated"}), ("drafty", {"status": "draft"})):
        data = dict(json.load(open(bare, encoding="utf-8")), **extra)
        res = lint.lint_file(write(os.path.join(g, name + ".json"), data), a)
        assert res["state"] == "PASS", (name, res)
    ext = write(os.path.join(g, "rpg-kid.json"), {"extends": "rpg-base", "title": "Kid"})
    assert lint.lint_file(ext, a)["state"] == "PASS", "a game style extending a structured style WARNs"
    for path in lint.default_paths(None):
        if os.sep + "styles" + os.sep in path or "/styles/" in path:
            res = lint.lint_file(path, None)
            assert not any("structured style fields" in r for r in res["reasons"]), (path, res)


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
    shutil.rmtree(TMP, ignore_errors=True)
    print("%d case(s), %d failed" % (len(CASES), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
