#!/usr/bin/env python3
"""VFX domain quality rules; intentionally independent of engine installations."""
import math
import numbers
from domains._api import Result


def _valid_number(value, *, integer=False):
    """Return whether a budget or measurement is finite and non-negative."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    if not math.isfinite(value) or value < 0:
        return False
    return not integer or isinstance(value, numbers.Integral)

def check(artifact, ctx):
    kind = artifact.get("kind")
    spec = artifact.get("spec") if isinstance(artifact.get("spec"), dict) else {}
    results = []

    def add(name, errors):
        results.append(Result(name, "FAIL" if errors else "PASS", errors))

    if kind == "vfx-direction":
        add("vfx-direction", [] if spec.get("purpose") and spec.get("visual_language") else ["purpose and visual_language are required for a usable direction"])
        return results
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
        if path.lower().endswith(".vfx"):
            results.append(Result("vfx-graph-visual-verification", "HUMAN_REQUIRED", ["VFX Graph visual and performance verification requires a human reviewer"]))
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
