#!/usr/bin/env python3
"""VFX domain quality rules; intentionally independent of engine installations (never launches Unity).

Checks per kind (docs/architecture/domains/vfx.md "Quality rules"):

  vfx-direction        purpose and visual_language present
  vfx-style            vfx-style-profile: the profile resolves with scripts/vfx/vfx_style.py (the lint's own reader),
                       carries binding_values true, and is the only live vfx-style profile of the authoring repo
  vfx-spec             vfx-triggers, vfx-timing, vfx-curves, vfx-platform-budgets, vfx-sync-dependencies,
                       vfx-verification-evidence; vfx-spec-style when spec.style names a profile: the profile
                       resolves, each platform budget the profile also budgets stays within it (max_particles <=
                       max_alive_particles, particle systems <= max_systems; a platform the profile does not budget is
                       a WARN) and each anticipation/impact/dissipation phase share stays inside the profile's band
  vfx-asset            vfx-asset-budget; vfx-asset-capture (capture evidence well formed and, when its stats.json is
                       found under a Captures/ folder of a registered repo root, equal to it; a .vfx asset without
                       capture evidence is HUMAN_REQUIRED); vfx-asset-style-lint (the lint is bound to the profile's
                       current git blob revision and to the capture's stats hash: the lint report found next to the
                       capture is recomputed with vfx_style.py lint and must agree; a mismatch is FAIL, a report or
                       capture that cannot be found is NOT_AVAILABLE); vfx-asset-textures (every game texture names an
                       approved gen-run with a verified approval whose outputs hold its output hash; missing approval
                       is a WARN while the asset is draft, rejected, blocked, superseded or deprecated and a FAIL past
                       draft; an output hash the gen-run does not record always FAILS); the look, readability,
                       overdraw and frame time are always HUMAN_REQUIRED (gate vfx-visual-review: a person judges them
                       in Play mode, agents never record it)
"""
import hashlib
import importlib.util
import json
import math
import numbers
import os
import subprocess
from pathlib import Path

from domains._api import Result

ROOT = Path(__file__).resolve().parents[3]
LENIENT = {"draft", "rejected", "blocked", "superseded", "deprecated"}
CLOSED = {"rejected", "superseded", "deprecated"}
VISUAL_REVIEW = ("look, readability, overdraw and frame time are judged by a person in Play mode "
                 "(gate vfx-visual-review); agents never record this review")
_cache = {}


def _valid_number(value, *, integer=False):
    """Return whether a budget or measurement is finite and non-negative."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    if not math.isfinite(value) or value < 0:
        return False
    return not integer or isinstance(value, numbers.Integral)


def _vfx_style():
    """scripts/vfx/vfx_style.py, the reader and lint the profile and lint checks share with the CLI."""
    if "vfx_style" not in _cache:
        spec = importlib.util.spec_from_file_location("vfx_style_for_quality", ROOT / "scripts" / "vfx" / "vfx_style.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _cache["vfx_style"] = module
    return _cache["vfx_style"]


def _plan_rules():
    """scripts/vfx/data/plan.json: capture and lint file names, skipped folders, approved states."""
    if "plan" not in _cache:
        with open(ROOT / "scripts" / "vfx" / "data" / "plan.json", encoding="utf-8") as f:
            _cache["plan"] = json.load(f)
    return _cache["plan"]


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _artifact_file(ctx, artifact_id, fallback=None):
    """Absolute path of an artifact's file in the authoring repo, or None."""
    pair = ctx.artifacts.get(artifact_id)
    rel = pair[0] if isinstance(pair, tuple) and pair[0] else fallback
    return Path(ctx.repo) / rel if rel else None


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, encoding="utf-8")
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _blob_revisions(ctx, path):
    """The current git blob ids of a file: of its bytes on disk and as git would store it (line-ending filters)."""
    data = path.read_bytes()
    revisions = {hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()}
    try:
        rel = path.resolve().relative_to(Path(ctx.repo).resolve()).as_posix()
    except ValueError:
        rel = None
    stored = _git(ctx.repo, "hash-object", "--", rel) if rel else None
    if stored:
        revisions.add(stored)
    return revisions


def _profile(ctx, profile_id):
    """(path, resolved profile, errors) of the vfx-style artifact profile_id, resolved with vfx_style.py."""
    pair = ctx.artifacts.get(profile_id)
    obj = pair[1] if isinstance(pair, tuple) else pair
    if not isinstance(obj, dict):
        return None, None, ["style profile %s is not an artifact of the authoring repo" % profile_id]
    if obj.get("kind") != "vfx-style":
        return None, None, ["style profile %s is a %s artifact, not vfx-style" % (profile_id, obj.get("kind"))]
    path = _artifact_file(ctx, profile_id)
    if path is None or not path.is_file():
        return None, None, ["style profile %s: its file is not on disk" % profile_id]
    style = _vfx_style()
    try:
        profile, _ = style.resolve_profile(str(path))
    except style.InputError as e:
        return path, None, [str(e)]
    return path, profile, []


def _roots(ctx):
    """The registered repo roots of this validation (authoring first), each once."""
    seen, roots = set(), []
    for root in [ctx.repo] + [str(v) for v in (ctx.repo_roots or {}).values()]:
        if not root:
            continue
        p = Path(root).resolve()
        if p not in seen and p.is_dir():
            seen.add(p)
            roots.append(p)
    return roots


def _capture_dirs(ctx):
    """Captures/ folders at a repo root or one level below it (a project such as UnityVFX Sandbox~)."""
    dirs = []
    for root in _roots(ctx):
        for candidate in [root / "Captures"] + sorted(root.glob("*/Captures")):
            if candidate.is_dir() and candidate not in dirs:
                dirs.append(candidate)
    return dirs


def _find(ctx, names, sha256):
    """The first file named one of names under the capture folders whose SHA-256 is sha256, or None."""
    skip = set(_plan_rules().get("skip_dirs", []))
    for top in _capture_dirs(ctx):
        for base, subdirs, files in os.walk(top):
            subdirs[:] = sorted(d for d in subdirs if d not in skip)
            for name in sorted(files):
                if name in names:
                    path = Path(base) / name
                    try:
                        if _sha256_file(path) == sha256:
                            return path
                    except OSError:
                        continue
    return None


def _bases(ctx, *files):
    """Folders a lint report's relative input paths may be relative to: repo roots, the projects that hold the
    given files (the parent of their Captures/ folder) and the parents of both."""
    bases = []
    for f in files:
        for parent in Path(f).parents:
            if parent.name == "Captures":
                bases.append(parent.parent)
                break
    bases += _roots(ctx)
    out = []
    for b in bases + [b.parent for b in bases]:
        if b not in out:
            out.append(b)
    return out


def _resolve(path, bases, sha256=None):
    """A report input path resolved against bases (absolute paths as they are); with sha256 only a file of it."""
    if not isinstance(path, str) or not path:
        return None
    candidates = [Path(path)] if os.path.isabs(path) else [b / path for b in bases]
    for c in candidates:
        try:
            if c.is_file() and (sha256 is None or _sha256_file(c) == sha256):
                return c
        except OSError:
            continue
    return None


def _grade(name, fails, warns=(), unavailable=(), human=()):
    if fails:
        return Result(name, "FAIL", list(fails) + list(unavailable) + list(warns))
    if human:
        return Result(name, "HUMAN_REQUIRED", list(human) + list(warns))
    if unavailable:
        return Result(name, "NOT_AVAILABLE", list(unavailable) + list(warns))
    if warns:
        return Result(name, "WARN", list(warns))
    return Result(name, "PASS", [])


def style_profile_check(artifact, ctx):
    """vfx-style-profile: the profile resolves with vfx_style.py, is binding and is the project's only live one."""
    fails = []
    path = _artifact_file(ctx, artifact.get("id"), ctx.artifact_path or None)
    if path is None or not path.is_file():
        fails.append("the profile's file is not on disk: vfx_style.py reads the artifact file")
    else:
        style = _vfx_style()
        try:
            style.resolve_profile(str(path))
        except style.InputError as e:
            fails.append(str(e))
    if artifact.get("binding_values") is not True:
        fails.append("a vfx-style profile is binding: binding_values must be true (its approval covers every effect)")
    if artifact.get("status") not in CLOSED:
        others = sorted(aid for aid, (_, obj) in ctx.artifacts.items() if obj.get("kind") == "vfx-style"
                        and aid != artifact.get("id") and obj.get("status") not in CLOSED)
        if others:
            fails.append("one vfx-style profile per project: also live " + ", ".join(others)
                         + " (supersede or deprecate the old one)")
    return _grade("vfx-style-profile", fails)


def spec_style_check(spec, ctx, maximum):
    """vfx-spec-style: the spec's budgets and phase shares within the bands of the profile it names."""
    profile_id = spec.get("style")
    _, profile, fails = _profile(ctx, str(profile_id))
    warns = []
    if profile is None:
        return _grade("vfx-spec-style", fails)
    systems = len([s for s in spec.get("particle_systems", []) if isinstance(s, dict)])
    for platform, data in sorted((spec.get("platforms") or {}).items()):
        limits = profile["budgets"].get(platform)
        if not isinstance(limits, dict):
            warns.append("%s: profile %s has no budget for this platform, the spec budget is not bounded by it" % (platform, profile_id))
            continue
        budget = data.get("budget") if isinstance(data, dict) else None
        budget = budget if isinstance(budget, dict) else {}
        alive = limits.get("max_alive_particles")
        if _valid_number(budget.get("max_particles"), integer=True) and _valid_number(alive) and budget["max_particles"] > alive:
            fails.append("%s max_particles %s exceeds profile %s max_alive_particles %s" % (platform, budget["max_particles"], profile_id, alive))
        if _valid_number(alive) and maximum > alive:
            fails.append("%s particle-system maxima %s exceed profile %s max_alive_particles %s" % (platform, maximum, profile_id, alive))
        if _valid_number(limits.get("max_systems")) and systems > limits["max_systems"]:
            fails.append("%s %d particle systems exceed profile %s max_systems %s" % (platform, systems, profile_id, limits["max_systems"]))
    try:
        declared = float(spec["duration_seconds"])
        phases = [(p["name"], float(p["duration_seconds"])) for p in spec.get("phases", [])]
    except (TypeError, ValueError, KeyError):
        declared, phases = 0.0, []
    if declared > 0 and math.isfinite(declared):
        for name in ("anticipation", "impact", "dissipation"):
            seconds = sum(d for n, d in phases if n == name)
            if not any(n == name for n, _ in phases):
                continue
            band, share = profile["timing"][name], seconds / declared
            if not band["min"] - 1e-9 <= share <= band["max"] + 1e-9:
                fails.append("phase %s share %.4g of %.4g s is outside profile %s band %s..%s" % (name, share, declared, profile_id, band["min"], band["max"]))
    return _grade("vfx-spec-style", fails, warns)


def capture_check(spec, ctx, is_graph):
    """vfx-asset-capture: the capture evidence is well formed and equal to its stats.json when that is found."""
    capture = spec.get("capture")
    if capture is None:
        if is_graph:
            return Result("vfx-asset-capture", "HUMAN_REQUIRED", [
                "a .vfx asset without capture evidence: capture it (com.cuvara.vfx Tools~/vfxcli.py capture) and record "
                "spec.capture, until then a person judges it in Play mode"])
        return None
    if not isinstance(capture, dict):
        return Result("vfx-asset-capture", "FAIL", ["spec.capture must be an object"])
    fails = []
    if not _is_sha256(capture.get("stats_hash")):
        fails.append("capture.stats_hash must be the lowercase SHA-256 of the capture's stats.json")
    seed = capture.get("seed")
    if not _valid_number(seed, integer=True) or seed > 4294967295:
        fails.append("capture.seed must be an integer in 0..4294967295 (VisualEffect.startSeed)")
    if not _valid_number(capture.get("alive_peak"), integer=True):
        fails.append("capture.alive_peak must be a non-negative integer (alive.peak)")
    if "contact_sheet_hash" in capture and not _is_sha256(capture.get("contact_sheet_hash")):
        fails.append("capture.contact_sheet_hash must be a lowercase SHA-256")
    if fails:
        return _grade("vfx-asset-capture", fails)
    stats_path = _find(ctx, {_plan_rules()["capture_file"]}, capture["stats_hash"])
    if stats_path is None:
        return Result("vfx-asset-capture", "PASS", ["capture evidence well formed; no stats.json with stats_hash under "
                                                    "a Captures/ folder of the registered repo roots to compare with"])
    try:
        stats = json.loads(stats_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return Result("vfx-asset-capture", "FAIL", ["%s is not JSON: %s" % (stats_path, e)])
    stats = stats if isinstance(stats, dict) else {}
    alive = stats.get("alive") if isinstance(stats.get("alive"), dict) else {}
    sheet = stats.get("contact_sheet") if isinstance(stats.get("contact_sheet"), dict) else {}
    if stats.get("seed") != seed:
        fails.append("capture.seed %s differs from stats.json seed %s" % (seed, stats.get("seed")))
    if alive.get("peak") != capture["alive_peak"]:
        fails.append("capture.alive_peak %s differs from stats.json alive.peak %s" % (capture["alive_peak"], alive.get("peak")))
    if "contact_sheet_hash" in capture and sheet.get("sha256") != capture["contact_sheet_hash"]:
        fails.append("capture.contact_sheet_hash differs from stats.json contact_sheet.sha256 %s" % sheet.get("sha256"))
    if fails:
        return _grade("vfx-asset-capture", fails)
    return Result("vfx-asset-capture", "PASS", ["capture evidence equals " + stats_path.as_posix()])


def style_lint_check(artifact, spec, ctx, specs):
    """vfx-asset-style-lint: the lint is bound to the profile's current blob revision and to the capture's stats hash,
    and vfx_style.py lint computes the same result on them now."""
    style_ev, lint, capture = spec.get("style"), spec.get("lint"), spec.get("capture")
    named = sorted({s.get("spec", {}).get("style") for _, s in specs if isinstance(s.get("spec", {}).get("style"), str)})
    if style_ev is None and lint is None and not named:
        return None
    lenient = artifact.get("status") in LENIENT
    fails, warns, unavailable = [], [], []
    if style_ev is None or lint is None:
        missing = [k for k, v in (("style", style_ev), ("lint", lint)) if v is None]
        reason = ("no %s evidence: lint the effect with scripts/vfx/vfx_style.py lint against %s and record spec.style "
                  "and spec.lint" % (" and ".join(missing), ", ".join(named) or "the project's vfx-style profile"))
        return _grade("vfx-asset-style-lint", [] if lenient else [reason], [reason] if lenient else [])
    if not isinstance(style_ev, dict) or not isinstance(lint, dict):
        return _grade("vfx-asset-style-lint", ["spec.style and spec.lint must be objects"])
    profile_id, blob = style_ev.get("profile_id"), style_ev.get("blob_revision")
    if not isinstance(profile_id, str) or not profile_id:
        fails.append("style.profile_id must name the vfx-style artifact")
    if not (isinstance(blob, str) and len(blob) == 40 and all(c in "0123456789abcdef" for c in blob)):
        fails.append("style.blob_revision must be a 40-hex git blob id")
    if lint.get("state") not in ("PASS", "WARN", "FAIL"):
        fails.append("lint.state must be PASS, WARN or FAIL")
    if not _is_sha256(lint.get("report_hash")):
        fails.append("lint.report_hash must be the lowercase SHA-256 of the lint result JSON")
    if fails:
        return _grade("vfx-asset-style-lint", fails)
    for other in named:
        if other != profile_id:
            fails.append("the vfx-spec names style %s, the lint graded %s" % (other, profile_id))
    profile_path, profile, errors = _profile(ctx, profile_id)
    fails += errors
    if profile_path is not None and profile_path.is_file() and blob not in _blob_revisions(ctx, profile_path):
        fails.append("style.blob_revision %s is not the current revision of %s: the lint graded another revision of "
                     "the profile, lint again" % (blob, profile_id))
    if lint["state"] == "FAIL":
        fails.append("the recorded lint state is FAIL")
    elif lint["state"] == "WARN":
        warns.append("the recorded lint state is WARN")
    if not isinstance(capture, dict) or not _is_sha256(capture.get("stats_hash")):
        fails.append("a lint is bound to its capture: record spec.capture with stats_hash")
    if fails or profile is None:
        return _grade("vfx-asset-style-lint", fails, warns)
    rules = _plan_rules()
    stats_path = _find(ctx, {rules["capture_file"]}, capture["stats_hash"])
    if stats_path is None:
        unavailable.append("no stats.json with stats_hash %s under a Captures/ folder of the registered repo roots "
                           "(pass the effect's repo with --repos <repo>=<path>)" % capture["stats_hash"][:12])
        return _grade("vfx-asset-style-lint", fails, warns, unavailable)
    report_path = None
    for name in rules["lint_files"]:
        candidate = stats_path.parent / name
        if candidate.is_file() and _sha256_file(candidate) == lint["report_hash"]:
            report_path = candidate
            break
    report_path = report_path or _find(ctx, set(rules["lint_files"]), lint["report_hash"])
    if report_path is None:
        unavailable.append("no lint result (%s) with report_hash %s under a Captures/ folder" % (" or ".join(rules["lint_files"]), lint["report_hash"][:12]))
        return _grade("vfx-asset-style-lint", fails, warns, unavailable)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        stats = json.loads(stats_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return _grade("vfx-asset-style-lint", ["%s or %s is not JSON: %s" % (report_path, stats_path, e)])
    report = report if isinstance(report, dict) else {}
    stats = stats if isinstance(stats, dict) else {}
    inputs = report.get("inputs") if isinstance(report.get("inputs"), dict) else {}
    recipe_in = inputs.get("recipe") if isinstance(inputs.get("recipe"), dict) else {}
    graded = ((report.get("style") or {}).get("artifact") or {}) if isinstance(report.get("style"), dict) else {}
    if report.get("schema") != rules["schemas"]["lint"]:
        fails.append("%s schema is %r, expected %s" % (report_path.name, report.get("schema"), rules["schemas"]["lint"]))
    if report.get("status") != lint["state"]:
        fails.append("lint.state %s differs from the report status %s" % (lint["state"], report.get("status")))
    if isinstance(graded, dict) and graded.get("id") not in (None, profile_id):
        fails.append("the report graded style %s, not %s" % (graded.get("id"), profile_id))
    if not inputs.get("stats"):
        fails.append("the lint report graded no capture (inputs.stats is null): lint with --stats <stats.json>")
    if recipe_in.get("sha256") != stats.get("recipe_sha256"):
        fails.append("the report's recipe sha256 %s is not the capture's recipe_sha256 %s" % (recipe_in.get("sha256"), stats.get("recipe_sha256")))
    bases = _bases(ctx, stats_path, report_path)
    if inputs.get("stats"):
        resolved = _resolve(inputs["stats"], bases)
        if resolved is not None and _sha256_file(resolved) != capture["stats_hash"]:
            fails.append("the report's inputs.stats %s is not the capture with stats_hash" % inputs["stats"])
    if fails:
        return _grade("vfx-asset-style-lint", fails, warns)
    recomputed, why = _relint(ctx, inputs, recipe_in, profile_path, stats_path, specs, bases)
    if recomputed is None:
        unavailable.append("cannot recompute the lint: " + why)
        return _grade("vfx-asset-style-lint", fails, warns, unavailable)
    if recomputed["status"] != lint["state"]:
        fails.append("vfx_style.py lint now computes %s on the bound profile and capture, the record says %s"
                     % (recomputed["status"], lint["state"]))
    want = {r.get("id"): r.get("state") for r in report.get("rows", []) if isinstance(r, dict)}
    have = {r["id"]: r["state"] for r in recomputed["rows"]}
    differ = sorted(k for k in set(want) | set(have) if want.get(k) != have.get(k))
    if differ:
        fails.append("the report rows differ from what vfx_style.py lint computes now: " + ", ".join(
            "%s %s -> %s" % (k, want.get(k), have.get(k)) for k in differ))
    return _grade("vfx-asset-style-lint", fails, warns)


def _relint(ctx, inputs, recipe_in, profile_path, stats_path, specs, bases):
    """(vfx_style.py lint result, None) on the bound profile and capture with the report's other inputs, or
    (None, why) when one of them is not found."""
    recipe = _resolve(recipe_in.get("path"), bases, recipe_in.get("sha256"))
    if recipe is None:
        return None, "recipe %s with sha256 %s not found" % (recipe_in.get("path"), str(recipe_in.get("sha256"))[:12])
    opts = {"--style": str(profile_path), "--recipe": str(recipe), "--stats": str(stats_path)}
    if inputs.get("inspect"):
        inspect = _resolve(inputs["inspect"], bases)
        if inspect is None:
            return None, "inspect result %s not found" % inputs["inspect"]
        opts["--inspect"] = str(inspect)
    if inputs.get("spec"):
        spec_path = next((p for p in (_artifact_file(ctx, aid) for aid, _ in specs) if p is not None and p.is_file()), None)
        spec_path = spec_path or _resolve(inputs["spec"], bases)
        if spec_path is None:
            return None, "vfx-spec %s not found" % inputs["spec"]
        opts["--spec"] = str(spec_path)
    style = _vfx_style()
    try:
        return style.lint(opts), None
    except style.InputError as e:
        return None, str(e)


def textures_check(artifact, spec, ctx):
    """vfx-asset-textures: every game texture traces to an approved gen-run that recorded its output hash."""
    textures = spec.get("textures")
    if textures is None:
        return None
    if not isinstance(textures, list):
        return Result("vfx-asset-textures", "FAIL", ["spec.textures must be a list"])
    lenient = artifact.get("status") in LENIENT
    approved = set(_plan_rules().get("approved_states", []))
    style_ev = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    profile = _profile(ctx, style_ev["profile_id"])[1] if isinstance(style_ev.get("profile_id"), str) else None
    fails, todo = [], []
    for i, tex in enumerate(textures):
        if not isinstance(tex, dict):
            fails.append("textures[%d] must be an object" % i)
            continue
        run_id, output = tex.get("gen_run_id"), tex.get("output_hash")
        label = "textures[%d] (%s)" % (i, tex.get("transform") or "no transform")
        if not _is_sha256(output) or not _is_sha256(tex.get("game_texture_hash")):
            fails.append(label + ": output_hash and game_texture_hash must be lowercase SHA-256 values")
            continue
        if not isinstance(tex.get("transform"), str) or not tex["transform"]:
            fails.append(label + ": transform must name the import-texture transform applied")
        pair = ctx.artifacts.get(run_id) if isinstance(run_id, str) else None
        run = pair[1] if isinstance(pair, tuple) else None
        if not isinstance(run, dict) or run.get("kind") != "gen-run":
            todo.append("%s: gen-run %s is not an artifact of the authoring repo" % (label, run_id))
            continue
        if run.get("status") not in approved:
            todo.append("%s: gen-run %s is %s, not approved" % (label, run_id, run.get("status")))
            continue
        verdict = ctx.approval(run_id)
        state = verdict.get("state") if isinstance(verdict, dict) else "missing"
        if state != "verified":
            todo.append("%s: the approval of gen-run %s is %s (%s)" % (label, run_id, state, "; ".join(
                (verdict or {}).get("reasons") or [] if isinstance(verdict, dict) else [])))
            continue
        outputs = (run.get("spec") or {}).get("outputs") or []
        if output not in {o.get("sha256") for o in outputs if isinstance(o, dict)}:
            fails.append("%s: output_hash %s is not an output of gen-run %s" % (label, output[:12], run_id))
        run_style = ((run.get("spec") or {}).get("style") or {}).get("id")
        if profile is not None and run_style != profile.get("assetgen_style"):
            fails.append("%s: gen-run %s used asset-gen style %s, the profile's is %s" % (label, run_id, run_style, profile.get("assetgen_style")))
    if lenient:
        return _grade("vfx-asset-textures", fails, todo)
    return _grade("vfx-asset-textures", fails + todo)


def check(artifact, ctx):
    kind = artifact.get("kind")
    spec = artifact.get("spec") if isinstance(artifact.get("spec"), dict) else {}
    results = []

    def add(name, errors):
        results.append(Result(name, "FAIL" if errors else "PASS", errors))

    if kind == "vfx-direction":
        add("vfx-direction", [] if spec.get("purpose") and spec.get("visual_language") else ["purpose and visual_language are required for a usable direction"])
        return results
    if kind == "vfx-style":
        return [style_profile_check(artifact, ctx)]
    known = {aid for aid, (_, obj) in ctx.artifacts.items() if obj.get("domain") == "design"}
    domain = ctx.registry.get("domains", {}).get("vfx", {})
    known.update(str(x) for x in domain.get("engineering_event_ids", []))
    existing_ids = set(ctx.artifacts)
    if kind == "vfx-spec":
        errors = ["trigger does not reference an existing design artifact or registered engineering event id: " + str(event)
                  for event in spec.get("triggers", []) if event not in known]
        add("vfx-triggers", errors)
        phase_errors = []
        try:
            durations = [float(p["duration_seconds"]) for p in spec.get("phases", [])]
            declared = float(spec["duration_seconds"])
            if not math.isfinite(declared) or any(not math.isfinite(x) for x in durations): phase_errors.append("phase durations and total duration must be finite numbers")
            if any(x < 0 for x in durations) or declared < 0: phase_errors.append("phase durations and total duration must be non-negative")
            if abs(sum(durations) - declared) > max(0.001, declared * 0.001): phase_errors.append("lifecycle phases must sum to declared total duration")
        except (TypeError, ValueError, KeyError): phase_errors.append("phase durations and total duration must be numeric")
        add("vfx-timing", phase_errors)
        curve_errors = []
        for curve in spec.get("curves", []):
            times = []
            for point in curve.get("keyframes", []):
                try:
                    t = float(point["time"]); value = float(point["value"])
                    if not math.isfinite(t) or not math.isfinite(value): curve_errors.append("curve keyframe time and value must be finite numbers")
                    if not 0 <= t <= 1: curve_errors.append("curve keyframe time must be in [0,1]")
                    times.append(t)
                except (TypeError, ValueError, KeyError): curve_errors.append("curve keyframes need numeric time and value")
            if times != sorted(times): curve_errors.append("curve keyframes must be sorted by time")
        add("vfx-curves", curve_errors)
        budget_errors = []
        platforms = spec.get("platforms", {})
        if not platforms: budget_errors.append("every target platform needs a budget")
        maximum = 0
        for system in spec.get("particle_systems", []):
            value = system.get("max_particles") if isinstance(system, dict) else None
            if not _valid_number(value, integer=True):
                budget_errors.append("particle-system max_particles must be a finite non-negative integer")
            else:
                maximum += value
        for platform, data in platforms.items():
            budget = data.get("budget") if isinstance(data, dict) else None
            if not isinstance(budget, dict) or not all(k in budget for k in ("max_particles", "max_overdraw", "max_draw_calls", "max_ms")):
                budget_errors.append(platform + " platform needs complete particle, overdraw, draw-call and ms budget")
            else:
                for key in ("max_particles", "max_overdraw", "max_draw_calls", "max_ms"):
                    if not _valid_number(budget[key], integer=key in ("max_particles", "max_draw_calls")):
                        budget_errors.append(platform + " " + key + " budget must be a finite non-negative" + (" integer" if key in ("max_particles", "max_draw_calls") else " number"))
                if _valid_number(budget["max_particles"], integer=True) and maximum > budget["max_particles"]:
                    budget_errors.append(platform + " particle maxima exceed platform budget")
        add("vfx-platform-budgets", budget_errors)
        if spec.get("style") is not None:
            results.append(spec_style_check(spec, ctx, maximum))
        dependency_errors = []
        for dep in spec.get("dependencies", []):
            if dep.get("status") != "tbd" and dep.get("id") not in existing_ids:
                dependency_errors.append("UI/audio dependency must resolve to an existing id or be marked TBD: " + str(dep.get("id")))
        add("vfx-sync-dependencies", dependency_errors)
        if artifact.get("status") == "verified":
            linked = [obj for _, obj in ctx.artifacts.values() if obj.get("kind") == "vfx-asset" and artifact.get("id") in obj.get("sources", []) + [x.get("id") for x in obj.get("upstream", []) if isinstance(x, dict)]]
            add("vfx-verification-evidence", [] if any(x.get("status") in ("verified", "released") and x.get("spec", {}).get("checks") for x in linked) else ["verified effect requires a verified vfx-asset record with checks"])
        return results
    if kind == "vfx-asset":
        errors = []
        linked = [obj for _, obj in ctx.artifacts.values() if obj.get("kind") == "vfx-spec" and obj.get("id") in artifact.get("sources", []) + [x.get("id") for x in artifact.get("upstream", []) if isinstance(x, dict)]]
        if not linked: errors.append("asset record must reference its vfx-spec")
        stats = spec.get("stats")
        if not isinstance(stats, dict) or not stats:
            errors.append("production-complete asset requires measured or declared stats")
        for source in linked:
            expected_platforms = source.get("spec", {}).get("platforms", {})
            if not isinstance(stats, dict): stats = {}
            for platform in expected_platforms:
                if platform not in stats:
                    errors.append("missing measured or declared stats for platform " + platform)
            for platform, measured in stats.items():
                budget = source.get("spec", {}).get("platforms", {}).get(platform, {}).get("budget")
                if not isinstance(budget, dict) or not budget: errors.append("no declared budget for measured platform " + platform); continue
                if not isinstance(measured, dict):
                    errors.append(platform + " stats must be an object"); continue
                for stat, bkey in (("particles", "max_particles"), ("overdraw", "max_overdraw"), ("draw_calls", "max_draw_calls"), ("ms", "max_ms")):
                    integer = stat in ("particles", "draw_calls")
                    if stat not in measured or not _valid_number(measured[stat], integer=integer):
                        errors.append(platform + " " + stat + " must be a finite non-negative" + (" integer" if integer else " number"))
                    elif not _valid_number(budget.get(bkey), integer=integer):
                        errors.append(platform + " " + bkey + " budget must be a finite non-negative" + (" integer" if integer else " number"))
                    elif measured[stat] > budget[bkey]:
                        errors.append(platform + " " + stat + " exceeds declared budget")
        add("vfx-asset-budget", errors)
        path = str(spec.get("asset_path", ""))
        is_graph = path.lower().endswith(".vfx")
        specs = [(obj.get("id"), obj) for obj in linked]
        for extra in (capture_check(spec, ctx, is_graph), style_lint_check(artifact, spec, ctx, specs),
                      textures_check(artifact, spec, ctx)):
            if extra is not None:
                results.append(extra)
        if is_graph:
            results.append(Result("vfx-graph-visual-verification", "HUMAN_REQUIRED", ["VFX Graph asset: " + VISUAL_REVIEW]))
        else:
            results.append(Result("vfx-visual-review", "HUMAN_REQUIRED", [VISUAL_REVIEW]))
        unity = ctx.tools("unity") if callable(ctx.tools) else None
        if not unity:
            results.append(Result("unity-editor-availability", "NOT_AVAILABLE", ["Unity Editor was not detected; the core artifact workflow does not require it"]))
        else:
            results.append(Result("unity-editor-availability", "WARN", ["Unity Editor detected for reporting only; it is never launched by the workflow"]))
        return results
    return [Result("vfx-kind", "FAIL", ["unrecognized VFX artifact kind"])]


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
