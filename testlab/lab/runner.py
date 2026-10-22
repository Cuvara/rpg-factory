"""One scenario run, end to end: preflight, isolated stack, players, shared start, server probe,
disruptions, bots, collection, analysis, report, cleanup. Every run gets a fresh directory named
by its run id, so no artifact of an earlier run can be read as this run's evidence.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import threading
import time
import traceback
from pathlib import Path

from . import analyze, clients, provenance, report, scenarios, stack, util
from .config import LabConfig
from .probe import ServerProbe


def _git(repo: Path, *args) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _host_load() -> dict | None:
    """Host CPU load and free memory when the run starts (Windows), so environment noise is on record."""
    if not util.IS_WINDOWS:
        return None
    cmd = ["powershell", "-NoProfile", "-Command",
           "$c=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
           "$m=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory; Write-Output \"$c $m\""]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.split()
        return {"cpu_load_pct": float(out[0]), "free_mem_mb": round(float(out[1]) / 1024)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _player_fingerprint(cfg: LabConfig) -> dict:
    exe = cfg.player_exe
    managed = exe.parent / (exe.stem + "_Data") / "Managed"
    testlab = managed / "NDC.TestLab.dll"
    di = managed / "NDC.Scripts.DI.dll"
    info = {"exe": str(exe), "exists": exe.exists(), "testlab_assembly": testlab.exists()}
    for name, p in (("testlab_dll", testlab), ("di_dll", di)):
        if p.exists():
            info[name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16], "mtime": p.stat().st_mtime}
    build_info = exe.parent.parent / "testlab-build.json"
    info["build"] = util.read_json(build_info, default=None)
    return info


def run(cfg: LabConfig, scenario_name: str, *, overrides: dict | None = None, build_server: bool = False,
        keep_clients: bool = False, run_id: str | None = None, quiet: bool = False) -> dict:
    sc = scenarios.load(scenario_name, overrides)
    run_id = run_id or util.new_run_id(sc["id"])
    run_dir = cfg.runs_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    log_lines: list[str] = []

    def log(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        log_lines.append(line)
        if not quiet:
            print(line, flush=True)
        (run_dir / "orchestrator.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    meta = {
        "schema": "rpg.testlab.run.v1",
        "run_id": run_id,
        "scenario": {"id": sc["id"], "version": sc["version"], "path": sc["_path"]},
        "host": {"platform": platform.platform(), "python": platform.python_version(), "node": platform.node()},
        "repos": {
            "factory": {"path": str(Path(__file__).resolve().parents[2]), "head": _git(Path(__file__).resolve().parents[2], "rev-parse", "HEAD"),
                        "dirty": bool(_git(Path(__file__).resolve().parents[2], "status", "--porcelain"))},
            "server": {"path": str(cfg.server_repo), "head": _git(cfg.server_repo, "rev-parse", "HEAD"),
                       "branch": _git(cfg.server_repo, "rev-parse", "--abbrev-ref", "HEAD"),
                       "dirty": bool(_git(cfg.server_repo, "status", "--porcelain"))},
            "client": {"path": str(cfg.client_project), "head": _git(cfg.client_project, "rev-parse", "HEAD"),
                       "branch": _git(cfg.client_project, "rev-parse", "--abbrev-ref", "HEAD"),
                       "dirty": bool(_git(cfg.client_project, "status", "--porcelain"))},
        },
        "player": _player_fingerprint(cfg),
        "host_load_at_start": _host_load(),
        # What the player under test was BUILT from (testlab-build.json written by build-client);
        # repos.client above is only the configured project checkout, which may have moved on.
        "config": cfg.as_dict(),
        "started_utc": util.utc_stamp(),
        "clients": {},
        "timeline": [],
        "harness_error": None,
    }
    util.write_json(run_dir / "scenario.json", sc)
    players: list[clients.Player] = []
    probe: ServerProbe | None = None
    bots_proc = None
    harness_error = None
    interrupted = False
    server_image = None

    def mark(event: str, **kw) -> None:
        meta["timeline"].append({"event": event, "mono": util.mono(), **kw})

    try:
        log(f"run {run_id}: scenario {sc['id']} v{sc['version']} - {sc['title']}")
        if not meta["player"]["testlab_assembly"]:
            raise RuntimeError(f"{cfg.player_exe} has no NDC.TestLab.dll: build with testlab.py build-client "
                               "(PlayerBuilder -extraDefines CUVARA_TESTLAB)")
        for note in clients.clean_orphans(cfg):
            log(note)
        pre = stack.preflight(cfg)
        meta["preflight"] = pre
        if pre["conflicts"]:
            raise RuntimeError("port conflict: " + "; ".join(pre["conflicts"]))

        env = stack.env_for(sc, cfg)
        if sc.get("snapshot_trace") and not stack.compose_forwards(cfg, "GAMESERVER_SNAPSHOT_TRACE"):
            raise stack.StackError(f"{cfg.deploy_dir / 'docker-compose.yml'} does not forward GAMESERVER_SNAPSHOT_TRACE "
                                   "to the game server; the snapshot trace (snapshot_trace: true) cannot be recorded")
        log(f"stack: ensuring scratch stack ({len(env)} settings, build={build_server})")
        # A trace must start with this run: a reused server would hold earlier runs' rows.
        meta["stack"] = stack.ensure(cfg, env, build=build_server, log_path=run_dir / "stack-up.log",
                                     force_restart_gameserver=bool(sc["fresh_server"] or sc.get("snapshot_trace")))
        for action in meta["stack"]["actions"]:
            log("stack: " + action)
        server_image = provenance.docker_image_id(cfg, cfg.gameserver_container)
        mark("stack_ready")

        probe = ServerProbe(cfg, run_dir / "server", entity_hz=float(sc["server_sample_hz"]))
        probe.scrape_metrics("start")
        probe.start()

        control_path = run_dir / "control.json"
        clients.write_control(control_path, 0, [])
        for i in range(int(sc["clients"])):
            p = clients.Player(i, run_dir, run_id, device=f"testlab-{run_id}-{i}")
            plan = scenarios.client_plan(sc, i, run_id)
            p.dir.mkdir(parents=True, exist_ok=True)
            util.write_json(p.dir / "plan.json", plan)
            clients.launch(cfg, sc, p, p.dir / "plan.json", control_path)
            players.append(p)
            log(f"client {i}: launched pid {p.pid} device {p.device}")
            time.sleep(float(sc.get("launch_stagger_s", 1.0)))
        clients.register_active(cfg, run_id, [p.pid for p in players], cfg.player_exe)
        mark("clients_launched")

        t0 = util.mono()
        clients.wait_phase(players, {"in_world"}, float(sc["join_timeout_s"]), label="all clients in world")
        user_ids = [p.status().get("user_id") for p in players]
        for p, uid in zip(players, user_ids):
            meta["clients"][str(p.index)] = {"device": p.device, "first_user_id": uid}
        log(f"all {len(players)} clients in world after {util.mono() - t0:.1f}s: {user_ids}")
        mark("all_in_world", seconds=util.mono() - t0)

        start_ms = util.unix_ms() + int(float(sc["start_delay_s"]) * 1000)
        probe.start_mono = util.mono() + (start_ms - util.unix_ms()) / 1000.0
        clients.write_control(control_path, start_ms, user_ids)
        log(f"scenario clock starts in {sc['start_delay_s']}s; duration {sc['duration_s']}s")
        mark("start_scheduled", start_mono=probe.start_mono)

        if sc.get("bots") and int(sc["bots"].get("players", 0)) > 0:
            bots_proc = _start_bots(cfg, sc, run_dir, log)

        redis_taken = False
        end_scraped = False
        disruptions = sorted(sc["disruptions"], key=lambda d: d["at_s"])
        pending_relaunch: list[tuple[float, clients.Player]] = []
        end_at = probe.start_mono + float(sc["duration_s"])
        while util.mono() < end_at + float(sc.get("finish_grace_s", 20)):
            now_st = util.mono() - probe.start_mono
            if not redis_taken and now_st >= float(sc.get("redis_at_s", min(5.0, float(sc["duration_s"]) / 2))):
                redis_taken = True
                _take_redis(cfg, sc, run_dir)
                log(f"redis: {util.read_json(run_dir / 'redis.json')}")
            if not end_scraped and now_st >= float(sc["duration_s"]) - 1.0:
                # Counters for the scenario window: scraped while every client is still in the
                # world. Clients quitting afterwards close their sessions, which is teardown,
                # not a failure of the run (that delta is in metrics-after.txt).
                end_scraped = True
                probe.scrape_metrics("end")
                mark("metrics_end")
            while disruptions and now_st >= float(disruptions[0]["at_s"]):
                d = disruptions.pop(0)
                _disrupt(cfg, sc, d, players, pending_relaunch, probe, log, run_dir)
                mark("disruption", **d)
            for item in list(pending_relaunch):
                if util.mono() >= item[0]:
                    pending_relaunch.remove(item)
                    p = item[1]
                    clients.launch(cfg, sc, p, p.dir / "plan.json", control_path)
                    clients.register_active(cfg, run_id, [q.pid for q in players], cfg.player_exe)
                    log(f"client {p.index}: relaunched pid {p.pid} (same device {p.device})")
                    mark("relaunch", client=p.index, pid=p.pid)
            if util.mono() >= end_at and all((p.proc and p.proc.poll() is not None) for p in players) and not pending_relaunch:
                break
            time.sleep(0.2)

        codes = clients.wait_exit(players, timeout=5)
        log(f"client exit codes: {codes}")
        if not redis_taken:
            _take_redis(cfg, sc, run_dir)
    except KeyboardInterrupt:
        # Ctrl-C: the cleanup below still stops the players; the run is recorded as interrupted
        # and the interrupt is raised again once the record is written.
        interrupted = True
        harness_error = "KeyboardInterrupt: run interrupted (Ctrl-C)"
        log("HARNESS ERROR: " + harness_error)
        (run_dir / "harness-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    except Exception as exc:
        harness_error = f"{type(exc).__name__}: {exc}"
        log("HARNESS ERROR: " + harness_error)
        (run_dir / "harness-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        if bots_proc is not None:
            try:
                bots_proc.wait(timeout=40)  # loadtest writes its JSON when its window closes
            except subprocess.TimeoutExpired:
                pass
        if bots_proc is not None and bots_proc.poll() is None:
            util.kill_tree(bots_proc.pid)
            log("bots: killed loadtest (still running at end)")
        if probe is not None:
            if not (probe.out / "metrics-end.txt").exists():
                probe.scrape_metrics("end")
            probe.scrape_metrics("after")
            probe.stop()
            meta["probe_counts"] = probe.counts
        if players and not keep_clients:
            control = run_dir / "control.json"
            if control.exists():
                c = util.read_json(control, default={}) or {}
                clients.write_control(control, c.get("start_at_unix_ms", 0), c.get("client_user_ids", []), abort=True)
            time.sleep(1.0 if harness_error else 0)
            for note in clients.stop(players):
                log(note)
        if not keep_clients:
            clients.unregister_active(cfg, run_id)
        for p in players:
            meta["clients"].setdefault(str(p.index), {})["history"] = p.history
        if sc.get("snapshot_trace") and meta.get("stack"):
            try:
                meta["snapshot_trace"] = stack.fetch_snapshot_trace(cfg, run_dir / "server" / "snapshot-trace.csv")
                log(f"snapshot trace: {meta['snapshot_trace']}")
            except Exception as exc:  # the record must still be written
                meta["snapshot_trace"] = {"copied": False, "error": f"{type(exc).__name__}: {exc}"}
        meta["harness_error"] = harness_error
        meta["ended_utc"] = util.utc_stamp()
        try:
            meta["provenance"] = _provenance(cfg, meta, run_dir, server_image)
        except Exception as exc:  # an incomplete record grades INCONCLUSIVE; never lose run.json
            meta["provenance"] = {"run_id": run_id, "error": f"{type(exc).__name__}: {exc}"}
        util.write_json(run_dir / "run.json", meta)

    ev = analyze.load_evidence(run_dir)
    results = analyze.evaluate(ev)
    outcome = analyze.overall(results, harness_error)
    result = report.write(run_dir, ev, results, outcome, harness_error)
    log(f"RESULT {outcome}: {sum(r['status'] == 'PASS' for r in results)} pass, "
        f"{sum(r['status'] == 'FAIL' for r in results)} fail, "
        f"{sum(r['status'] == 'INCONCLUSIVE' for r in results)} inconclusive, "
        f"{sum(r['status'] == 'INFO' for r in results)} info -> {run_dir / 'report.md'}")
    if interrupted:
        raise KeyboardInterrupt
    return result


def _provenance(cfg: LabConfig, meta: dict, run_dir: Path, server_image: str | None) -> dict:
    """The run record's provenance block (lab/provenance.py); verified by every analysis."""
    repos = meta.get("repos") or {}
    player = provenance.player_record(cfg.player_exe)
    return {
        "schema": provenance.SCHEMA,
        "run_id": meta["run_id"],
        "factory": {"sha": (repos.get("factory") or {}).get("head"), "dirty": (repos.get("factory") or {}).get("dirty")},
        "server": {"sha": (repos.get("server") or {}).get("head"), "dirty": (repos.get("server") or {}).get("dirty"),
                   "image_id": server_image, "container": cfg.gameserver_container},
        # The commit the player was BUILT from (testlab-build.json), not the configured checkout.
        "client": {"sha": player.get("built_from_client"), "dirty": player.get("built_dirty"),
                   "configured_head": (repos.get("client") or {}).get("head")},
        "netcode": player.pop("netcode"),
        "player": player,
        "scenario": {**(meta.get("scenario") or {}),
                     "sha256": provenance.sha256_file(run_dir / "scenario.json")},
        "host_quiet": {"load_start": meta.get("host_load_at_start"), "load_end": _host_load(),
                       "note": "host-wide stalls are graded per run by the host_quiet assertion"},
        "started_utc": meta.get("started_utc"),
        "ended_utc": meta.get("ended_utc"),
        "manifest": provenance.manifest(run_dir),
    }


def _take_redis(cfg, sc, run_dir):
    util.write_json(run_dir / "redis.json", {
        "session_keys": len(stack.redis_session_keys(cfg)),
        "map_members": stack.redis_map_members(cfg, sc["map"]),
        "taken_mono": util.mono(),
    })


def _disrupt(cfg, sc, d, players, pending, probe, log, run_dir=None):
    """Apply one disruption and append what happened to disruptions.ndjson (the evidence the
    checks read: a debug_kill that did not answer 200 makes its dependent assertions INCONCLUSIVE)."""
    kind = d["kind"]
    record = {"kind": kind, "at_s": d.get("at_s"), "client": d.get("client"), "mono": util.mono(),
              "st": probe.scenario_time(util.mono()) if probe is not None else None}
    if kind == "kill_client":
        p = players[int(d["client"])]
        if p.proc and p.proc.poll() is None:
            util.kill_tree(p.proc.pid)
            p.history.append({"event": "killed", "pid": p.proc.pid, "mono": util.mono()})
            log(f"disruption: killed client {p.index} pid {p.proc.pid}")
        if d.get("relaunch_after_s") is not None:
            pending.append((util.mono() + float(d["relaunch_after_s"]), p))
    elif kind == "restart_gameserver":
        log("disruption: restarting scratch game server")
        stack.restart_gameserver(cfg)
    elif kind == "debug_kill":
        record.update(debug_kill(cfg, players[int(d["client"])]))
        log(f"disruption: debug_kill client {d['client']} -> HTTP {record.get('http_status')} {record.get('response')}")
    if run_dir is not None:
        with open(run_dir / "disruptions.ndjson", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record) + "\n")


def debug_kill(cfg: LabConfig, player) -> dict:
    """POST /debug/kill (rpg-mmo-server hook S1, needs GAMESERVER_DEBUG_ENTITIES=on) for a player's
    user id. Returns the HTTP status, the server's answer (outcome, tick, hp_before) and ok =
    HTTP 200 with outcome killed. Anything else is recorded, never retried."""
    uid = (player.status() or {}).get("user_id")
    if not uid:
        return {"user_id": None, "http_status": None, "response": None, "ok": False, "error": "client user id unknown"}
    status, body = util.http_post_json(cfg.debug_kill_url, {"id": uid}, timeout=5)
    ok = status == 200 and (body or {}).get("outcome") == "killed"
    return {"user_id": uid, "http_status": status, "response": body, "ok": ok,
            "server_tick": (body or {}).get("tick")}


def _start_bots(cfg: LabConfig, sc: dict, run_dir: Path, log):
    b = sc["bots"]
    exe = cfg.loadtest_exe
    if not exe.exists():
        raise RuntimeError(f"loadtest binary missing: {exe} (testlab.py build-loadtest)")
    secrets = stack.lab_secrets(cfg)
    addr = stack.advertised_game_addr(cfg, sc["map"])
    out = run_dir / "bots"
    out.mkdir(exist_ok=True)
    args = [str(exe), "-join", "direct", "-gameserver-addr", addr,
            "-server-id", f"gs-dotnet-{sc['map']}", "-players", str(b["players"]),
            # -ramp is players started per second; -duration is the measured window AFTER the
            # ramp and the 5 s warmup, so it is shortened to end inside the scenario.
            "-ramp", str(float(b.get("ramp_per_s", 20))),
            # Measured window ends ~4 s AFTER the scenario window, so every bot is still connected
            # when the end-of-scenario metrics are scraped (bots leaving inside the window would be
            # counted as closed sessions).
            "-duration", str(max(5, int(sc["duration_s"]) - int(b["players"] / max(1.0, float(b.get("ramp_per_s", 20)))) - 5 + 4)) + "s",
            "-movement", b.get("movement", "cluster"), "-gameserver-metrics", cfg.metrics_url,
            "-gateway-metrics", "", "-label", sc["id"], "-json", str(out / "loadtest.json"),
            "-join-token-secret", secrets["JOIN_TOKEN_SECRET"], "-jwt-secret", secrets["JWT_SECRET"],
            "-map-id", sc["map"]]
    log(f"bots: loadtest {b['players']} players movement={b.get('movement', 'cluster')} -> {addr}")
    fh = open(out / "loadtest.log", "w", encoding="utf-8")
    return subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT)
