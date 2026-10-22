#!/usr/bin/env python3
"""rpg-factory testlab - autonomous multiplayer gameplay runs with real rendered Unity clients.

    python testlab/testlab.py list
    python testlab/testlab.py run S01 [S02 ...] [--server-repo PATH] [--player PATH] [--build-server]
    python testlab/testlab.py suite smoke|crowding|load|soak|full
    python testlab/testlab.py sweep S07 --levels 0,25,50,100 [--stop-on-fail]
    python testlab/testlab.py analyze <run_dir>          # re-evaluate stored evidence
    python testlab/testlab.py build-client [--project PATH] [--out PATH]
    python testlab/testlab.py build-loadtest [--server-repo PATH]
    python testlab/testlab.py stack up|down|status
    python testlab/testlab.py clean                      # kill orphaned players of interrupted runs

Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 harness/usage error. Docs: testlab/README.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import analyze, clients, config, report, runner, scenarios, stack, util  # noqa: E402

SUITES_FILE = Path(__file__).resolve().parent / "suites.json"


def _cfg(args) -> config.LabConfig:
    overrides = {
        "server_repo": getattr(args, "server_repo", None),
        "player_exe": getattr(args, "player", None),
        "client_project": getattr(args, "project", None),
        "runs_root": getattr(args, "runs_root", None),
    }
    return config.load(Path(args.config) if getattr(args, "config", None) else None, overrides)


def _worst(outcomes: list[str]) -> int:
    if "FAIL" in outcomes:
        return 1
    if "INCONCLUSIVE" in outcomes or not outcomes:
        return 2
    return 0


def cmd_list(args) -> int:
    for path in sorted(scenarios.SCENARIO_DIR.glob("*.json")):
        sc = util.read_json(path, {}) or {}
        print(f"{sc.get('id', path.stem):5} v{sc.get('version')}  {sc.get('title')}")
    suites = util.read_json(SUITES_FILE, {}) or {}
    for name, ids in suites.items():
        print(f"suite {name}: {' '.join(ids)}")
    return 0


def _overrides(args) -> dict:
    o = {}
    if getattr(args, "duration", None):
        o["duration_s"] = args.duration
    if getattr(args, "clients", None):
        o["clients"] = args.clients
    return o


def cmd_run(args) -> int:
    cfg = _cfg(args)
    outcomes = []
    for name in args.scenarios:
        res = runner.run(cfg, name, overrides=_overrides(args), build_server=args.build_server,
                         keep_clients=args.keep_clients)
        outcomes.append(res["outcome"])
        args.build_server = False  # build once per invocation
    return _worst(outcomes)


def cmd_suite(args) -> int:
    suites = util.read_json(SUITES_FILE, {}) or {}
    if args.name not in suites:
        util.eprint(f"unknown suite {args.name}; known: {', '.join(suites)}")
        return 3
    args.scenarios = suites[args.name]
    return cmd_run(args)


def cmd_sweep(args) -> int:
    """Increasing bot levels on one scenario; stops at the first FAIL when asked."""
    cfg = _cfg(args)
    levels = [int(x) for x in args.levels.split(",")]
    rows, first_fail = [], None
    for level in levels:
        base = scenarios.load(args.scenario)
        bots = dict(base.get("bots") or {"movement": "cluster"})
        bots["players"] = level
        overrides = {**_overrides(args), "bots": bots if level > 0 else None}
        res = runner.run(cfg, args.scenario, overrides=overrides, build_server=args.build_server)
        args.build_server = False
        failing = [a["id"] for a in res["assertions"] if a["status"] == "FAIL"]
        rows.append({"bots": level, "outcome": res["outcome"], "run_id": res["run_id"], "failing": failing,
                     "key": _sweep_key(res)})
        print(json.dumps(rows[-1]), flush=True)
        if res["outcome"] == "FAIL" and first_fail is None:
            first_fail = level
            if args.stop_on_fail:
                break
    out = cfg.runs_root / "sweeps" / f"{util.utc_stamp()}-{args.scenario}.json"
    util.write_json(out, {"scenario": args.scenario, "levels": rows, "first_failing_level": first_fail})
    print(f"sweep written: {out}; first failing level: {first_fail}")
    return _worst([r["outcome"] for r in rows])


def _sweep_key(res: dict) -> dict:
    key = {}
    for a in res["assertions"]:
        if a["check"] in ("server_tick", "kcp_health", "snapshot_cadence", "frame_time", "bots_joined", "snapshot_update_gap"):
            key[a["id"]] = {"status": a["status"], "measured": a.get("measured")}
    return key


def cmd_analyze(args) -> int:
    run_dir = Path(args.run_dir)
    ev = analyze.load_evidence(run_dir)
    results = analyze.evaluate(ev)
    harness_error = (ev["meta"] or {}).get("harness_error")
    outcome = analyze.overall(results, harness_error)
    report.write(run_dir, ev, results, outcome, harness_error)
    print(f"{outcome}: {run_dir / 'report.md'}")
    return report.EXIT_CODES.get(outcome, 2)


def cmd_build_client(args) -> int:
    cfg = _cfg(args)
    out_root = Path(args.out) if args.out else cfg.player_exe.parent.parent
    log = cfg.runs_root / "logs" / f"build-client-{util.utc_stamp()}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    project = cfg.client_project
    steps = [
        ("scene", ["-quit", "-executeMethod", "TestLab.Editor.TestLabSceneBuilder.Build"] +
         (["-testlabMap", str(cfg.server_repo / "backend" / "content" / "maps" / "dev_arena.json")]
          if (cfg.server_repo / "backend" / "content" / "maps" / "dev_arena.json").exists() else [])),
        ("validate", ["-executeMethod", "TestLab.Editor.TestLabSceneBuilder.Validate"]),
        ("player", ["-quit", "-buildTarget", "Win64", "-executeMethod", "PlayerBuilder.Build", "-buildOutput", str(out_root),
                    "-bootScene", "Assets/Scenes/Tests/MultiplayerCombatTest.unity", "-extraDefines", "CUVARA_TESTLAB"]),
    ]
    for name, extra in steps:
        step_log = log.with_name(log.stem + f"-{name}.log")
        cmd = [str(cfg.unity_exe), "-batchmode", "-nographics", "-projectPath", str(project), "-logFile", str(step_log)] + extra
        print(f"build-client: {name} ...", flush=True)
        code = subprocess.run(cmd, timeout=3600).returncode
        if code != 0:
            util.eprint(f"build-client: step {name} failed (exit {code}); log {step_log}")
            return 3
    head = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(project), "status", "--porcelain"], capture_output=True, text=True).stdout.strip())
    util.write_json(out_root / "testlab-build.json", {"client_head": head, "client_dirty": dirty, "project": str(project),
                                                      "built_utc": util.utc_stamp(), "defines": ["CUVARA_TESTLAB"],
                                                      "embedded_packages": _embedded_packages(project)})
    print(f"build-client: OK -> {out_root}")
    return 0


def _embedded_packages(project: Path) -> list[dict]:
    """Packages/<name>/ directories override the manifest's git pins in Unity. Record each one
    (version and a content hash) so a build tested against a local package change says so."""
    import hashlib
    out = []
    for d in sorted((project / "Packages").iterdir()):
        pj = d / "package.json"
        if not d.is_dir() or not pj.exists():
            continue
        h = hashlib.sha256()
        for f in sorted(d.rglob("*.cs")):
            h.update(f.read_bytes())
        meta = util.read_json(pj, {}) or {}
        out.append({"name": meta.get("name", d.name), "version": meta.get("version"),
                    "cs_sha256": h.hexdigest()[:16], "git": (d / ".git").exists()})
    return out


def cmd_build_loadtest(args) -> int:
    cfg = _cfg(args)
    out = cfg.loadtest_exe
    out.parent.mkdir(parents=True, exist_ok=True)
    code = subprocess.run(["go", "build", "-o", str(out), "./cmd/loadtest"],
                          cwd=str(cfg.server_repo / "backend" / "loadtest")).returncode
    print(f"build-loadtest: exit {code} -> {out}")
    return 0 if code == 0 else 3


def cmd_stack(args) -> int:
    cfg = _cfg(args)
    if args.action == "status":
        print(json.dumps({"preflight": stack.preflight(cfg), "health": stack.health(cfg)}, indent=2))
        return 0
    if args.action == "down":
        print(stack.down(cfg))
        return 0
    sc = {"map": "map_01", "seed": 1}
    rec = stack.ensure(cfg, stack.env_for(sc, cfg), build=args.build_server,
                       log_path=cfg.runs_root / "logs" / "stack-up.log", force_restart_gameserver=False)
    print(json.dumps(rec, indent=2))
    return 0


def cmd_clean(args) -> int:
    cfg = _cfg(args)
    for line in clients.clean_orphans(cfg) or ["nothing to clean"]:
        print(line)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config")
    p.add_argument("--server-repo")
    p.add_argument("--player")
    p.add_argument("--project")
    p.add_argument("--runs-root")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    r = sub.add_parser("run")
    r.add_argument("scenarios", nargs="+")
    for sp in (r,):
        sp.add_argument("--build-server", action="store_true")
        sp.add_argument("--keep-clients", action="store_true")
        sp.add_argument("--duration", type=float)
        sp.add_argument("--clients", type=int)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("suite")
    s.add_argument("name")
    s.add_argument("--build-server", action="store_true")
    s.add_argument("--keep-clients", action="store_true")
    s.add_argument("--duration", type=float)
    s.add_argument("--clients", type=int)
    s.set_defaults(fn=cmd_suite)
    w = sub.add_parser("sweep")
    w.add_argument("scenario")
    w.add_argument("--levels", required=True)
    w.add_argument("--stop-on-fail", action="store_true")
    w.add_argument("--build-server", action="store_true")
    w.add_argument("--duration", type=float)
    w.add_argument("--clients", type=int)
    w.set_defaults(fn=cmd_sweep)
    a = sub.add_parser("analyze")
    a.add_argument("run_dir")
    a.set_defaults(fn=cmd_analyze)
    b = sub.add_parser("build-client")
    b.add_argument("--out")
    b.set_defaults(fn=cmd_build_client)
    sub.add_parser("build-loadtest").set_defaults(fn=cmd_build_loadtest)
    st = sub.add_parser("stack")
    st.add_argument("action", choices=["up", "down", "status"])
    st.add_argument("--build-server", action="store_true")
    st.set_defaults(fn=cmd_stack)
    sub.add_parser("clean").set_defaults(fn=cmd_clean)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (scenarios.ScenarioError, stack.StackError, clients.ClientError, ValueError) as exc:
        util.eprint(f"testlab: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
