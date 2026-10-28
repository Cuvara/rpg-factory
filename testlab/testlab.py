#!/usr/bin/env python3
"""rpg-factory testlab - autonomous multiplayer gameplay runs with real rendered Unity clients.

    python testlab/testlab.py list
    python testlab/testlab.py run S01 [S02 ...] [--server-repo PATH] [--player PATH] [--build-server]
    python testlab/testlab.py suite smoke|crowding|load|soak|full
    python testlab/testlab.py sweep S07 --levels 0,25,50,100 [--stop-on-fail]
    python testlab/testlab.py analyze <run_dir> [--out DIR]      # re-evaluate stored evidence
    python testlab/testlab.py analyze --delivery <run_dir> [--out DIR]   # snapshot delivery path (#473)
    python testlab/testlab.py replay-trace <run_dir> [--client N] [--out DIR]  # predictor call trace check
    python testlab/testlab.py leak-check <player> [--expect-testlab]     # TestLab code in a build?
    python testlab/testlab.py build-client [--project PATH] [--out PATH]
    python testlab/testlab.py build-loadtest [--server-repo PATH]
    python testlab/testlab.py stack up|down|status
    python testlab/testlab.py clean                      # kill orphaned players of interrupted runs
    python testlab/testlab.py preflight-soak [--window-min 90] [--window-announced "18:30Z 90min"] [--json]

run, suite and sweep stop the scratch stack when they finish (also on failure and Ctrl-C) unless
--keep-stack is given.

Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE or INVALID (the host guard fired: not a verdict on the
candidate), 3 harness/usage error, 4 PASS_WITH_WARNINGS (an informational assertion would have failed). Docs: testlab/README.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import analyze, clients, config, delivery, hostguard, leakcheck, predtrace, report, runner, native, scenarios, soakinputs, stack, thresholds, util  # noqa: E402

SUITES_FILE = Path(__file__).resolve().parent / "suites.json"
THRESHOLDS_DOC = Path(__file__).resolve().parent / "docs" / "THRESHOLDS.md"


def _path(arg: str) -> Path:
    """A path argument as this Python sees it. Git Bash normally rewrites `/c/...` arguments for a
    Windows program, but not with MSYS_NO_PATHCONV=1 (which the WSL commands need) or inside
    `--opt=/c/...`; Windows Python would read `/c/x` as a folder `c` on the current drive, so
    convert here."""
    if util.IS_WINDOWS and arg.startswith("/"):
        return Path(util.to_windows_path(arg))
    return Path(arg)


def _cfg(args) -> config.LabConfig:
    overrides = {key: (_path(v) if v else None) for key, v in (
        ("server_repo", getattr(args, "server_repo", None)),
        ("player_exe", getattr(args, "player", None)),
        ("client_project", getattr(args, "project", None)),
        ("runs_root", getattr(args, "runs_root", None)))}
    for key in ("server_mode", "native_build"):
        overrides[key] = getattr(args, key, None)      # plain strings, not paths
    return config.load(_path(args.config) if getattr(args, "config", None) else None, overrides)


def _worst(outcomes: list[str]) -> int:
    """FAIL 1 > INCONCLUSIVE / INVALID 2 > PASS_WITH_WARNINGS 4 > PASS 0."""
    if "FAIL" in outcomes:
        return 1
    if "INCONCLUSIVE" in outcomes or "INVALID" in outcomes or not outcomes:
        return 2
    if "PASS_WITH_WARNINGS" in outcomes:
        return 4
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
    if getattr(args, "snapshot_trace", False):
        o["snapshot_trace"] = True
    return o


def _with_stack_teardown(cfg: config.LabConfig, args, body):
    """Run `body()` and stop the scratch stack afterwards - on success, failure, harness error and
    Ctrl-C - unless --keep-stack. Only the scratch project is stopped (stack.down). A teardown that fails
    (a native game server that cannot be stopped) never hides the run's own outcome, but a run that
    would exit 0 or 4 exits 3 instead and the failure is kept in <runs>/stack/teardown-failure.json."""
    failure = None
    # The WSL distro (dockerd and the scratch stack) stops when no wsl.exe session is open: hold one for the invocation.
    stack.KEEPALIVE = stack.WslKeepAlive(cfg.wsl_distro).start()
    try:
        code = body()
    finally:
        try:
            if not getattr(args, "keep_stack", False):
                try:
                    print(f"testlab: {stack.down(cfg)}", flush=True)
                except Exception as exc:  # never mask the run's own exception or interrupt
                    failure = f"{type(exc).__name__}: {exc}"
                    util.eprint(f"testlab: stopping the scratch stack failed: {failure}")
                    util.write_json(cfg.runs_root / "stack" / "teardown-failure.json", {"error": failure})
        finally:
            stack.KEEPALIVE.stop()
            stack.KEEPALIVE = None
    if failure and code in (0, 4):
        return 3
    return code


def _refuse_stale_soak_inputs(cfg, names, args) -> int | None:
    """H6: exit code 3 (nothing started, no stack touched) when a requires_clean_host scenario would run on a default
    player or server checkout, or on a build other than the expected one; None when every scenario may start."""
    for name in names:
        try:
            soakinputs.check(cfg, scenarios.load(name, _overrides(args)),
                             expect_player_sha=getattr(args, "expect_player_sha", None),
                             expect_server_sha=getattr(args, "expect_server_sha", None))
        except soakinputs.SoakInputsError as exc:
            util.eprint(f"testlab: {exc}")
            return 3
    return None


def cmd_run(args) -> int:
    cfg = _cfg(args)
    refused = _refuse_stale_soak_inputs(cfg, args.scenarios, args)
    if refused is not None:
        return refused

    def body():
        outcomes = []
        for name in args.scenarios:
            res = runner.run(cfg, name, overrides=_overrides(args), build_server=args.build_server,
                             keep_clients=args.keep_clients,
                             require_clean_host=getattr(args, "require_clean_host", False),
                             allow_agents=tuple(getattr(args, "allow_agent", None) or ()),
                             expect_player_sha=getattr(args, "expect_player_sha", None),
                             expect_server_sha=getattr(args, "expect_server_sha", None))
            outcomes.append(res["outcome"])
            args.build_server = False  # build once per invocation
        return _worst(outcomes)
    return _with_stack_teardown(cfg, args, body)


def cmd_preflight_soak(args) -> int:
    """Host preflight P1-P7 for a clean-host soak (lab/hostguard.py): a 2 min passive sample plus the
    AnyDesk, Orca and WSL state. Read-only; prints one PASS/FAIL row each and writes nothing unless
    --out is given. Exit 0 when every row passes, 2 otherwise."""
    result = hostguard.preflight(window_min=args.window_min, announced=args.window_announced,
                                 sample_s=args.sample_s, allow_agents=tuple(args.allow_agent or ()))
    if args.out:
        util.write_json(_path(args.out), result)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for row in result["rows"]:
            note = f" [{row['note']}]" if row.get("note") else ""
            print(f"{row['id']} {row['status']}: {row['detail']}{note}")
        print(f"preflight-soak: {'OK' if result['ok'] else 'FAILED ' + ', '.join(result['failed'])} "
              f"({result['samples']} samples over {result['sample_s']:.0f} s)")
    return 0 if result["ok"] else 2


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
    refused = _refuse_stale_soak_inputs(cfg, [args.scenario], args)
    if refused is not None:
        return refused
    return _with_stack_teardown(cfg, args, lambda: _sweep(cfg, args))


def _sweep(cfg, args) -> int:
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
    # The scenario id, not the argument: a scenario given as a file path would otherwise put
    # path separators into the file name and write the sweep into a nested directory.
    out = cfg.runs_root / "sweeps" / f"{util.utc_stamp()}-{base['id']}.json"
    util.write_json(out, {"scenario": args.scenario, "levels": rows, "first_failing_level": first_fail})
    print(f"sweep written: {out}; first failing level: {first_fail}")
    return _worst([r["outcome"] for r in rows])


def _sweep_key(res: dict) -> dict:
    key = {}
    for a in res["assertions"]:
        if a["check"] in ("server_tick", "kcp_health", "snapshot_cadence", "frame_time", "bots_joined", "snapshot_update_gap", "enemy_budget"):
            key[a["id"]] = {"status": a["status"], "measured": a.get("measured")}
    return key


def cmd_analyze(args) -> int:
    run_dir = _path(args.run_dir)
    if not (run_dir / "run.json").exists() and not (run_dir / "scenario.json").exists():
        util.eprint(f"testlab: {run_dir} is not a run directory (no run.json, no scenario.json)")
        return 3
    out_dir = _path(args.out) if args.out else run_dir
    if args.delivery:
        doc = delivery.analyze(run_dir, gap_ms=args.gap_ms, bucket_s=args.bucket_s)
        j, m = delivery.write(doc, out_dir)
        print(f"delivery {doc['completeness']}: {m}  classes {doc['classes']}  scopes {doc['scopes']}")
        for line in doc["missing"]:
            print(f"  missing: {line}")
        return 0 if doc["completeness"] == "COMPLETE" else 2
    ev = analyze.load_evidence(run_dir)
    results = analyze.evaluate(ev)
    harness_error = (ev["meta"] or {}).get("harness_error")
    outcome = analyze.overall(results, harness_error)
    report.write(run_dir, ev, results, outcome, harness_error, out_dir=out_dir)
    print(f"{outcome}: {out_dir / 'report.md'}")
    return report.EXIT_CODES.get(outcome, 2)


def cmd_replay_trace(args) -> int:
    """Validate the predictor call trace of a run's client(s) and summarise the corrections it recorded
    per scripted stall. Exit 0 every trace valid, 1 one is invalid, 2 no trace in the run, 3 usage.
    The exact replay itself is Netcode's PredictorTraceReplayer (README "Predictor call trace")."""
    run_dir = _path(args.run_dir)
    if not run_dir.is_dir():
        util.eprint(f"testlab: {run_dir} is not a directory")
        return 3
    indices = [args.client] if args.client is not None else predtrace.traced_clients(run_dir)
    if not indices:
        print(f"no predictor trace in {run_dir} (no client plan with predictor_trace, no trace.ndjson)")
        return 2
    docs = []
    for i in indices:
        doc = predtrace.summarise(run_dir / f"client-{i}", min_correction=args.min_correction,
                                  local_window_s=args.window_s)
        doc["client"] = i
        docs.append(doc)
        print(predtrace.render(doc))
    if args.out:
        out = _path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        util.write_json(out / "trace-summary.json", {"run_dir": str(run_dir), "clients": docs})
        print(f"written: {out / 'trace-summary.json'}")
    return 0 if all(d["valid"] for d in docs) else 1


def cmd_thresholds(args) -> int:
    """Print (or --write) testlab/docs/THRESHOLDS.md, generated from lab/thresholds.py and the scenarios."""
    text = thresholds.render()
    if args.write:
        with open(THRESHOLDS_DOC, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"written: {THRESHOLDS_DOC}")
    else:
        print(text)
    return 0


def cmd_leak_check(args) -> int:
    """Exit 0 when the build matches the expectation (no TestLab code, or with --expect-testlab
    TestLab code present), 1 when it does not, 3 when no player was found."""
    res = leakcheck.inspect(_path(args.player))
    print(json.dumps(res, indent=2))
    if res["verdict"] == "ERROR":
        return 3
    present = res["verdict"] == "TESTLAB_PRESENT"
    return 0 if present == bool(args.expect_testlab) else 1


def cmd_build_client(args) -> int:
    cfg = _cfg(args)
    out_root = Path(args.out) if args.out else cfg.player_exe.parent.parent
    log = cfg.runs_root / "logs" / f"build-client-{util.utc_stamp()}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    project = cfg.client_project
    steps = []
    if args.rebuild_scene:
        # Regeneration is not byte-deterministic (Unity assigns new fileIDs), so it is opt-in:
        # by default the COMMITTED scene is validated and built, and the build stays clean.
        steps.append(("scene", ["-quit", "-executeMethod", "TestLab.Editor.TestLabSceneBuilder.Build"] +
                      (["-testlabMap", str(cfg.server_repo / "backend" / "content" / "maps" / "dev_arena.json")]
                       if (cfg.server_repo / "backend" / "content" / "maps" / "dev_arena.json").exists() else [])))
    steps += [
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
                                                      "embedded_packages": _embedded_packages(project),
                                                      "netcode": netcode_provenance(project)})
    print(f"build-client: OK -> {out_root}")
    return 0


def netcode_provenance(project: Path) -> dict:
    """Which com.cuvara.netcode a build compiles, written into testlab-build.json so the run's
    provenance names a commit (lab/provenance.py):
    - an embedded package under Packages/ that is a git clone: its HEAD (and whether it is dirty);
    - an embedded copy without .git: version and source hash only; its commit is unknown unless the
      build also writes VERIFY-PROVENANCE.txt (the verification build script does);
    - otherwise the manifest pin: packages-lock.json `hash` (the commit Unity resolved) and `version`
      (the git URL with its tag)."""
    packages = project / "Packages"
    for d in sorted(packages.iterdir()) if packages.is_dir() else []:
        meta = util.read_json(d / "package.json", {}) or {} if d.is_dir() else {}
        if meta.get("name") != "com.cuvara.netcode":
            continue
        rec = {"embedded": True, "version": meta.get("version"), "path": str(d), "sha": None, "dirty": None,
               "source": "embedded copy without .git (commit unknown)"}
        if (d / ".git").exists():
            head = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            status = subprocess.run(["git", "-C", str(d), "status", "--porcelain"], capture_output=True, text=True).stdout
            rec.update({"sha": head or None, "dirty": bool(status.strip()), "source": "embedded git clone HEAD"})
        return rec
    lock = (util.read_json(packages / "packages-lock.json", {}) or {}).get("dependencies", {}).get("com.cuvara.netcode") or {}
    return {"embedded": False, "version": lock.get("version"), "sha": lock.get("hash"), "dirty": False,
            "source": "Packages/packages-lock.json (manifest pin)" if lock else "not found in packages-lock.json"}


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


def _server_mode_args(sp) -> None:
    sp.add_argument("--server-mode", choices=config.SERVER_MODES, dest="server_mode",
                    help="where the game server runs: docker (the scratch container, default) or native (a Windows "
                         "process built with the Windows dotnet, so its clock is the players' QPC; lab/native.py)")
    sp.add_argument("--native-build", choices=("auto", "aot", "r2r"), dest="native_build",
                    help="native server build: auto (AOT if the MSVC linker exists, else ReadyToRun JIT), aot, r2r")


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
    s = sub.add_parser("suite")
    s.add_argument("name")
    w = sub.add_parser("sweep")
    w.add_argument("scenario")
    w.add_argument("--levels", required=True)
    w.add_argument("--stop-on-fail", action="store_true")
    for sp in (r, s, w):
        sp.add_argument("--build-server", action="store_true")
        sp.add_argument("--duration", type=float)
        sp.add_argument("--clients", type=int)
        sp.add_argument("--keep-stack", action="store_true", help="leave the scratch stack running afterwards")
        _server_mode_args(sp)
        sp.add_argument("--snapshot-trace", action="store_true",
                        help="record the server snapshot trace (GAMESERVER_SNAPSHOT_TRACE) into server/")
    for sp in (r, s):
        sp.add_argument("--keep-clients", action="store_true")
        sp.add_argument("--require-clean-host", action="store_true",
                        help="run the host preflight (P1-P6) and refuse to start on a FAIL; always on for scenarios "
                             "flagged requires_clean_host (S09)")
        sp.add_argument("--expect-player-sha", help="soak-class scenarios: refuse to start unless the player was built from this "
                                                    "client commit (7+ hex digits; testlab-build.json)")
        sp.add_argument("--expect-server-sha", help="soak-class scenarios: refuse to start unless --server-repo is at this commit")
        sp.add_argument("--allow-agent", action="append",
                        help="Orca worktree name or path whose working agent P3 may ignore (the soak runner, the Lead)")
    r.set_defaults(fn=cmd_run)
    s.set_defaults(fn=cmd_suite)
    w.set_defaults(fn=cmd_sweep)
    a = sub.add_parser("analyze")
    a.add_argument("run_dir")
    a.add_argument("--out", help="write results/report (or delivery.*) here instead of into the run directory")
    a.add_argument("--delivery", action="store_true", help="snapshot delivery-path analysis (server trace C1, client trace C2)")
    a.add_argument("--gap-ms", type=float, default=250.0)
    a.add_argument("--bucket-s", type=float, default=300.0)
    a.set_defaults(fn=cmd_analyze)
    rt = sub.add_parser("replay-trace", help="validate a client's predictor call trace, corrections per stall")
    rt.add_argument("run_dir")
    rt.add_argument("--client", type=int, help="client index (default: every client with a trace)")
    rt.add_argument("--out", help="also write trace-summary.json here (never into the run directory by default)")
    rt.add_argument("--min-correction", type=float, default=0.05, help="list corrections from this size (units)")
    rt.add_argument("--window-s", type=float, default=5.0, help="corrections this long after a stall start count for it")
    rt.set_defaults(fn=cmd_replay_trace)
    th = sub.add_parser("thresholds")
    th.add_argument("--write", action="store_true", help="write testlab/docs/THRESHOLDS.md")
    th.set_defaults(fn=cmd_thresholds)
    lc = sub.add_parser("leak-check")
    lc.add_argument("player", help="player exe, build directory, StandaloneWindows64, <Name>_Data or Managed folder")
    lc.add_argument("--expect-testlab", action="store_true", help="the build SHOULD contain TestLab (a testlab build)")
    lc.set_defaults(fn=cmd_leak_check)
    b = sub.add_parser("build-client")
    b.add_argument("--out")
    b.add_argument("--rebuild-scene", action="store_true",
                   help="regenerate MultiplayerCombatTest.unity from MainScene first (dirties the tree)")
    b.set_defaults(fn=cmd_build_client)
    sub.add_parser("build-loadtest").set_defaults(fn=cmd_build_loadtest)
    pf = sub.add_parser("preflight-soak", help="host preflight P1-P7 for a clean-host soak (read-only)")
    pf.add_argument("--window-min", type=float, default=90.0)
    pf.add_argument("--window-announced", help='the window the user named, e.g. "18:30Z 90min" (P7)')
    pf.add_argument("--sample-s", type=float, default=hostguard.PRE_SAMPLE_S, help="passive sample length (default 120)")
    pf.add_argument("--allow-agent", action="append", help="Orca worktree name or path P3 may ignore")
    pf.add_argument("--out", help="also write the result JSON here")
    pf.add_argument("--json", action="store_true")
    pf.set_defaults(fn=cmd_preflight_soak)
    st = sub.add_parser("stack")
    st.add_argument("action", choices=["up", "down", "status"])
    st.add_argument("--build-server", action="store_true")
    _server_mode_args(st)
    st.set_defaults(fn=cmd_stack)
    sub.add_parser("clean").set_defaults(fn=cmd_clean)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (scenarios.ScenarioError, stack.StackError, native.NativeError, clients.ClientError, ValueError) as exc:
        util.eprint(f"testlab: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
