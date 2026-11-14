"""assetgen.py style report: how a game style performs over its approved runs, with suggested thresholds (hooked up by assetgen.py).

  style report --authoring DIR [--style ID] [--json]

Read-only and deterministic: it writes nothing (no file, no directory), starts no process and reads no clock, so the same
data prints byte-identical output. Per style and per family (a run's spec.style_lock.family, a rejection's family; none
is the family "(none)") plus the style-wide "total" it reports:
  runs         assetgen/runs/*/run.md (front matter, as stylelock.run_status reads it) whose style ref
               (stylelock._run_style) names the style, counted by status
  tone         over the approved runs' outputs/*.png (sorted; a missing or unreadable PNG, or one with no opaque pixel,
               is listed as skipped, never a crash): min, max and mean of the mean luminance and mean saturation
               (consistency.tone_stats)
  palette      when the merged style has a usable palette (consistency.palette_config): per output the share of opaque
               samples within the current max_distance and d_needed, the smallest integer distance (capped at 441) at
               which that share reaches min_share; min, median and max of both
  qa           for every run of the style with a readable qa.json, each style-* row (qa.is_style_row) counted by state
               PASS, WARN, FAIL and NOT_AVAILABLE per check, with warn_rate and fail_rate = count / rows of that check
               (3 decimals; null without rows)
  rejections   stylelock.load_rejections counted by reason (a malformed record under "malformed"), per family and total
  suggestions  palette.max_distance = the largest d_needed over the approved outputs; tone.tolerance = the smallest
               tolerance, rounded up to 2 decimals, that keeps every approved output's mean luminance and saturation
               inside the range of the valid active anchors of the style's current version (the anchors of the family
               when it has any, else all of the style's; an anchor whose PNG is missing, does not match its image_sha256
               or has no opaque pixel is skipped). A suggestion is only ever printed with its supporting numbers and
               is never applied: nothing here edits a style. It is null with a reason when it cannot be computed.
Styles: --style ID, else every style with a game file assetgen/styles/<id>.json, named by a run's style ref or holding
anchor or rejection records, sorted. --json prints schema rpg-factory.assetgen-style-report/1 (indent 1, sorted keys).
Exit codes: 0 report printed (also when there is nothing to report), 1 refusal (a --style no data knows), 2 usage (a
malformed --style).
"""
import bisect
import json
import math
import os
import re
import sys

import consistency
import layers
import png
import qa
import style_cmd
import style_derive
import stylelock

REPORT_SCHEMA = "rpg-factory.assetgen-style-report/1"
NO_FAMILY = "(none)"
STATES = ("PASS", "WARN", "FAIL", "NOT_AVAILABLE")
DEFAULT_TONE_TOLERANCE = 0.05
MAX_DISTANCE_CAP = 441
NOT_APPLIED = "suggestion only, not applied"
Refusal = style_cmd.Refusal


def add_parser(subs):
    """Registers `report` on the nested `style` subparsers (assetgen.py passes the style parser's subparsers action)."""
    c = subs.add_parser("report", allow_abbrev=False,
                        help="read-only: tone, palette, QA and rejection statistics per style and family, with suggested thresholds")
    c.add_argument("--authoring", required=True, metavar="DIR", help="the authoring repo")
    c.add_argument("--style", metavar="ID", help="only this game style id (default: every style with data)")
    c.add_argument("--json", action="store_true")


# -- small helpers ---------------------------------------------------------------------------------------------

def _r(x):
    return None if x is None else round(x, 3)


def _median(values):
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _spread(values):
    """{min, median, max} rounded to 3 decimals, or None without values."""
    if not values:
        return None
    return {"min": _r(min(values)), "median": _r(_median(values)), "max": _r(max(values))}


def _stats(values):
    if not values:
        return None
    return {"min": _r(min(values)), "max": _r(max(values)), "mean": _r(sum(values) / len(values))}


def _rate(count, rows):
    return round(count / rows, 3) if rows else None


def _family(value):
    return value if isinstance(value, str) and value else NO_FAMILY


def _round_up_2(x):
    return round(math.ceil(round(x * 100, 9)) / 100, 2)


# -- data ------------------------------------------------------------------------------------------------------

def _runs(authoring):
    """[{id, dir, status, style_id, family}] of every readable gen-run, sorted by directory name; unreadable run names."""
    root = os.path.join(layers.game_dir(authoring), "runs")
    runs, unreadable = [], []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        path = os.path.join(root, name, "run.md")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                m = re.match(r"\A---json\s*\n(.*?)\n---", f.read(), re.S)
            front = json.loads(m.group(1)) if m else None
        except (OSError, ValueError):
            front = None
        if not isinstance(front, dict):
            unreadable.append(name)
            continue
        ref = stylelock._run_style(front)
        spec = front.get("spec") if isinstance(front.get("spec"), dict) else {}
        lock = spec.get("style_lock") if isinstance(spec.get("style_lock"), dict) else {}
        sid = ref.get("style_id") if isinstance(ref, dict) else None
        status = front.get("status")
        runs.append({"id": name, "dir": os.path.join(root, name), "status": status if isinstance(status, str) else "unknown",
                     "style_id": sid if isinstance(sid, str) and stylelock.ID.match(sid) else None,
                     "family": _family(lock.get("family"))})
    return runs, unreadable


def _style_ids(authoring, runs):
    ids = set(layers.layer_files("style", authoring)["game"])
    ids |= {r["style_id"] for r in runs if r["style_id"]}
    ids |= {sid for sid, _, _ in stylelock.anchor_files(authoring)}
    return sorted(i for i in ids if stylelock.ID.match(i))


def _output_record(img, palette):
    """{luminance, saturation, share, d_needed} of one decoded output, or None without an opaque sampled pixel.
    palette: the consistency.palette_config tuple (cfg, rgb, max_distance, min_share) or None."""
    tone = consistency.tone_stats(img)
    if tone is None:
        return None
    rec = {"luminance": tone[0], "saturation": tone[1], "share": None, "d_needed": None}
    if palette is not None:
        _, rgb, max_distance, min_share = palette
        sq = sorted(min((r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2 for pr, pg, pb in rgb)
                    for r, g, b, _ in consistency.opaque_samples(img))
        n = len(sq)
        rec["share"] = bisect.bisect_right(sq, max_distance * max_distance) / n
        k = min(n, max(1, math.ceil(round(min_share * n, 9))))
        d = math.isqrt(sq[k - 1])
        rec["d_needed"] = min(MAX_DISTANCE_CAP, d + (1 if d * d < sq[k - 1] else 0))
    return rec


def _approved_outputs(style_runs, palette):
    """([{run, output, family, ...record}], [{run, output, reason}]) over the approved runs' outputs/*.png."""
    used, skipped = [], []
    for run in style_runs:
        if run["status"] != "approved":
            continue
        out_dir = os.path.join(run["dir"], "outputs")
        for name in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
            if not name.lower().endswith(".png"):
                continue
            rel = "outputs/" + name
            try:
                rec = _output_record(png.decode(os.path.join(out_dir, name)), palette)
            except Exception as exc:  # an unreadable PNG is reported, never a crash
                skipped.append({"run": run["id"], "output": rel, "reason": "not readable (%s)" % exc})
                continue
            if rec is None:
                skipped.append({"run": run["id"], "output": rel, "reason": "no opaque pixels"})
                continue
            used.append(dict(rec, run=run["id"], output=rel, family=run["family"]))
    return used, skipped


def _qa_rows(style_runs):
    """([(family, check, state)] of every style-* row of the runs' qa.json, [unreadable run ids], runs with qa)."""
    rows, unreadable, with_qa = [], [], set()
    for run in style_runs:
        path = os.path.join(run["dir"], "qa.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                results = json.load(f)["results"]
            if not isinstance(results, list):
                raise ValueError("results is not a list")
        except (OSError, ValueError, KeyError, TypeError):
            unreadable.append(run["id"])
            continue
        with_qa.add(run["id"])
        for row in results:
            if isinstance(row, dict) and qa.is_style_row(row) and row.get("state") in STATES:
                rows.append((run["family"], str(row["check"]), row["state"], run["id"]))
    return rows, unreadable, with_qa


def _rejections(authoring, style_id):
    """[(family, reason)] of every rejection record of the style; a malformed record's reason is "malformed"."""
    out = []
    for rec in stylelock.load_rejections(authoring, style_id):
        reason = "malformed" if rec["errors"] else rec["data"].get("reason")
        out.append((_family(rec["data"].get("family")), reason if isinstance(reason, str) else "malformed"))
    return out


# -- groups ----------------------------------------------------------------------------------------------------

def _qa_summary(rows):
    out = {}
    for check in sorted({r[1] for r in rows}):
        states = [r[2] for r in rows if r[1] == check]
        counts = {s: states.count(s) for s in STATES}
        out[check] = dict(counts, rows=len(states), warn_rate=_rate(counts["WARN"], len(states)),
                          fail_rate=_rate(counts["FAIL"], len(states)))
    return out


def _suggest_palette(outs, palette, reason):
    if palette is None:
        return {"value": None, "reason": reason, "data": {"current": None}, "applied": False}
    _, _, max_distance, min_share = palette
    data = {"current": _r(max_distance), "min_share": _r(min_share), "outputs": len(outs)}
    if not outs:
        return {"value": None, "reason": "no approved output with opaque pixels", "data": data, "applied": False}
    needed = [o["d_needed"] for o in outs]
    data["d_needed"] = _spread(needed)
    data["pass_at_current"] = sum(1 for o in outs if o["share"] >= min_share)
    return {"value": max(needed), "reason": None, "data": data, "applied": False}


def _suggest_tone(outs, anchors, current):
    data = {"current": _r(current), "anchors": len(anchors), "outputs": len(outs)}
    if not anchors or not outs:
        return {"value": None, "applied": False, "data": data,
                "reason": "no valid active anchor of the current style version" if not anchors
                else "no approved output with opaque pixels"}
    need, anchor_range, output_range = 0.0, {}, {}
    for key in ("luminance", "saturation"):
        lo, hi = min(a[key] for a in anchors), max(a[key] for a in anchors)
        vals = [o[key] for o in outs]
        anchor_range[key] = [_r(lo), _r(hi)]
        output_range[key] = [_r(min(vals)), _r(max(vals))]
        need = max(need, max(max(0.0, lo - v, v - hi) for v in vals))
    inside = sum(1 for o in outs if all(
        min(a[k] for a in anchors) - current <= o[k] <= max(a[k] for a in anchors) + current
        for k in ("luminance", "saturation")))
    data.update(anchor_range=anchor_range, output_range=output_range, inside_at_current=inside)
    return {"value": min(1.0, _round_up_2(need)), "reason": None, "data": data, "applied": False}


def _group(fam, style_runs, outs, qa_rows, rejections, palette, palette_reason, anchors, tone_current):
    """The statistics of one family (fam) or of the whole style (fam None)."""
    pick = (lambda f: True) if fam is None else (lambda f: f == fam)
    runs = [r for r in style_runs if pick(r["family"])]
    outs = [o for o in outs if pick(o["family"])]
    rej = [r for f, r in rejections if pick(f)]
    scope = [a for a in anchors if fam is not None and a["family"] == fam] or anchors
    if palette is None:
        pal = {"state": palette_reason[0], "reason": palette_reason[1]}
    else:
        pal = {"state": "ok", "max_distance": _r(palette[2]), "min_share": _r(palette[3]), "outputs": len(outs),
               "share_at_current": _spread([o["share"] for o in outs]), "d_needed": _spread([o["d_needed"] for o in outs])}
    return {"runs": {"total": len(runs), "by_status": {s: sum(1 for r in runs if r["status"] == s)
                                                        for s in sorted({r["status"] for r in runs})}},
            "approved_outputs": len(outs),
            "tone": {"luminance": _stats([o["luminance"] for o in outs]), "saturation": _stats([o["saturation"] for o in outs])},
            "palette": pal,
            "qa": _qa_summary([r for r in qa_rows if pick(r[0])]),
            "rejections": {"total": len(rej), "by_reason": {x: rej.count(x) for x in sorted(set(rej))}},
            "suggestions": {"palette.max_distance": _suggest_palette(outs, palette, palette_reason[1]),
                            "tone.tolerance": _suggest_tone(outs, scope, tone_current)}}


def _style_report(authoring, style_id, runs):
    style_runs = [r for r in runs if r["style_id"] == style_id]
    game = style_id in layers.layer_files("style", authoring)["game"]
    out = {"style_id": style_id, "game_file": game, "version": None, "status": None, "error": None}
    merged = None
    try:
        merged = layers.load("style", style_id, authoring)["data"]
        out["version"], out["status"] = stylelock.style_version(merged), stylelock.style_status(merged)
    except layers.SpecError as exc:
        out["error"] = str(exc)
    state, got = consistency.palette_config(merged)
    palette = got if state == "ok" else None
    palette_reason = (state, got if state != "ok" else "")
    if merged is None:
        palette_reason = ("absent", out["error"])
    tone_state, tone_got = consistency.tone_config(merged)
    tone_current = tone_got[1] if tone_state == "ok" else DEFAULT_TONE_TOLERANCE
    outs, skipped_outputs = _approved_outputs(style_runs, palette)
    used, skipped_anchors = style_derive._load_anchors(authoring, style_id, out["version"], None)
    anchors, anchor_rows = [], []
    for data, img in used:
        tone = consistency.tone_stats(img)
        if tone is None:
            skipped_anchors.append({"id": data["id"], "reason": "no opaque pixels"})
            continue
        anchors.append({"id": data["id"], "family": data["family"], "luminance": tone[0], "saturation": tone[1]})
        anchor_rows.append({"id": data["id"], "family": data["family"], "luminance": _r(tone[0]), "saturation": _r(tone[1])})
    qa_rows, qa_unreadable, with_qa = _qa_rows(style_runs)
    rejections = _rejections(authoring, style_id)
    families = sorted({r["family"] for r in style_runs} | {f for f, _ in rejections})
    args = (style_runs, outs, qa_rows, rejections, palette, palette_reason, anchors, tone_current)
    out.update(anchors=anchor_rows, qa_runs=len(with_qa), qa_unreadable=qa_unreadable,
               skipped={"anchors": sorted(skipped_anchors, key=lambda s: s["id"]), "outputs": skipped_outputs},
               families={f: _group(f, *args) for f in families}, total=_group(None, *args))
    return out


# -- output ----------------------------------------------------------------------------------------------------

def _fmt(x):
    return "-" if x is None else ("%g" % x)


def _spread_text(s):
    return "none" if s is None else "min %s median %s max %s" % (_fmt(s["min"]), _fmt(s["median"]), _fmt(s["max"]))


def _suggestion_text(name, s):
    d = s["data"]
    if name == "palette.max_distance":
        facts = ["current %s" % _fmt(d["current"])]
        if "outputs" in d:
            facts += ["min_share %s" % _fmt(d["min_share"]), "%d approved output(s)" % d["outputs"]]
        if "d_needed" in d:
            facts += ["d_needed %s" % _spread_text(d["d_needed"]), "%d pass at current" % d["pass_at_current"]]
    else:
        facts = ["current %s" % _fmt(d["current"]), "%d anchor(s)" % d["anchors"], "%d approved output(s)" % d["outputs"]]
        if "anchor_range" in d:
            for key in ("luminance", "saturation"):
                facts.append("%s anchors [%s, %s] outputs [%s, %s]" % (
                    key, _fmt(d["anchor_range"][key][0]), _fmt(d["anchor_range"][key][1]),
                    _fmt(d["output_range"][key][0]), _fmt(d["output_range"][key][1])))
            facts.append("%d inside at current" % d["inside_at_current"])
    head = "%s = %s" % (name, _fmt(s["value"])) if s["value"] is not None else "%s: no suggestion (%s)" % (name, s["reason"])
    return "%s (%s): %s" % (head, NOT_APPLIED, "; ".join(facts))


def _group_text(g, pad):
    lines = ["%sruns: %d%s" % (pad, g["runs"]["total"], " (%s)" % ", ".join(
        "%s %d" % kv for kv in g["runs"]["by_status"].items()) if g["runs"]["by_status"] else "")]
    lines.append("%sapproved outputs: %d" % (pad, g["approved_outputs"]))
    for key in ("luminance", "saturation"):
        s = g["tone"][key]
        lines.append("%stone %s: %s" % (pad, key, "none" if s is None else "min %s max %s mean %s" % (
            _fmt(s["min"]), _fmt(s["max"]), _fmt(s["mean"]))))
    p = g["palette"]
    lines.append("%spalette: %s" % (pad, "not graded (%s: %s)" % (p["state"], p["reason"]) if p["state"] != "ok" else
                                    "share within max_distance %s: %s; d_needed (min_share %s): %s" % (
                                        _fmt(p["max_distance"]), _spread_text(p["share_at_current"]), _fmt(p["min_share"]),
                                        _spread_text(p["d_needed"]))))
    for check, c in g["qa"].items():
        lines.append("%sqa %s: %d row(s), PASS %d, WARN %d, FAIL %d, NOT_AVAILABLE %d, warn_rate %s, fail_rate %s" % (
            pad, check, c["rows"], c["PASS"], c["WARN"], c["FAIL"], c["NOT_AVAILABLE"], _fmt(c["warn_rate"]), _fmt(c["fail_rate"])))
    rej = g["rejections"]
    lines.append("%srejections: %d%s" % (pad, rej["total"], " (%s)" % ", ".join(
        "%s %d" % kv for kv in rej["by_reason"].items()) if rej["by_reason"] else ""))
    lines += ["%s%s" % (pad, _suggestion_text(name, s)) for name, s in g["suggestions"].items()]
    return lines


def _text(report):
    if not report["styles"]:
        return "no style data to report"
    lines = []
    for st in report["styles"]:
        lines.append("style %s version %s status %s%s" % (st["style_id"], _fmt(st["version"]), st["status"] or "unknown",
                                                         "" if st["game_file"] else " (no game style file)"))
        if st["error"]:
            lines.append("  style not loadable: " + st["error"])
        lines.append("  anchors used: %s" % (", ".join("%s (%s)" % (a["id"], a["family"]) for a in st["anchors"]) or "none"))
        lines += ["  anchor skipped: %s: %s" % (s["id"], s["reason"]) for s in st["skipped"]["anchors"]]
        lines += ["  output skipped: %s %s: %s" % (s["run"], s["output"], s["reason"]) for s in st["skipped"]["outputs"]]
        lines.append("  qa.json read from %d run(s)%s" % (st["qa_runs"], "; unreadable: " + ", ".join(st["qa_unreadable"])
                                                         if st["qa_unreadable"] else ""))
        for fam, g in st["families"].items():
            lines.append("  family %s:" % fam)
            lines += _group_text(g, "    ")
        lines.append("  all families:")
        lines += _group_text(st["total"], "    ")
    if report["runs_unreadable"]:
        lines.append("runs with unreadable run.md: " + ", ".join(report["runs_unreadable"]))
    lines.append("read-only report: nothing was written; every suggestion is for a person to apply")
    return "\n".join(lines)


def run(a):
    """Exit code of `style report`; a refusal prints `assetgen: <message>` to stderr."""
    try:
        return _run(a)
    except Refusal as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return exc.code
    except layers.SpecError as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return 1


def _run(a):
    authoring = os.path.abspath(a.authoring)
    if a.style is not None and not stylelock.ID.match(a.style):
        raise Refusal("--style %r must be a lowercase id (a-z, 0-9 and '-')" % a.style, 2)
    runs, unreadable = _runs(authoring)
    ids = _style_ids(authoring, runs)
    if a.style is not None:
        known = a.style in ids or a.style in layers.layer_files("style", authoring)["core"]
        if not known:
            raise Refusal("style %s has no game style file, no layer style and no run, anchor or rejection record in %s"
                          % (a.style, authoring.replace(os.sep, "/")))
        ids = [a.style]
    report = {"schema": REPORT_SCHEMA, "style_filter": a.style, "runs_unreadable": unreadable,
              "styles": [_style_report(authoring, sid, runs) for sid in ids]}
    if a.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print(_text(report))
    return 0
