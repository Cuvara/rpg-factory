"""Unit tests for `--server-mode native` (lab/native.py): the compose-derived environment and its network
rewrite, the build command, the stack bring-up without the container game server (fake shell, never a
real docker), the process sampler, and the provenance and report fields. No stack, no Unity, no network.

    python3 -B testlab/tests/test_native.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_lab import _run_dir, _write  # noqa: E402

from lab import analyze, config, native, probe, provenance, report, stack, util  # noqa: E402

# What `docker compose config --format json` reports for the scratch gameserver-dotnet service.
COMPOSE = {"services": {
    "redis": {}, "postgres": {}, "postgres-game": {}, "nakama": {}, "gateway": {},
    "gameserver-dotnet": {"environment": {
        "JWT_SECRET": "testlab-jwt", "JOIN_TOKEN_SECRET": "testlab-join", "GAMESERVER_ADDR": ":9000",
        "GAMESERVER_MAP_ID": "map_01", "GAMESERVER_ID": "gs-dotnet-map_01", "GAMESERVER_ENEMY_SEED": "9",
        "GAMESERVER_DEBUG_ENTITIES": "on", "GAMESERVER_KEYFRAME_INTERVAL": "30", "GAMESERVER_BOTS": "",
        "SIM_CRITICAL_HZ": "60", "METRICS_ADDR": ":9101", "REDIS_ADDR": "redis:6379", "REDIS_PASSWORD": "",
        "GAMESERVER_PUBLIC_ADDR": ":9300", "NAKAMA_URL": "http://nakama:7350", "NAKAMA_HTTP_KEY": "defaulthttpkey",
        "GAME_DB_URL": "postgres://game:localdev@postgres-game:5432/gamestate?sslmode=disable"}}}}


def _cfg(d, **kw):
    return config.LabConfig(workspace=Path(d), runs_root=Path(d) / "runs", server_repo=Path(d) / "server",
                            server_mode="native", **kw)


class ConfigTests(unittest.TestCase):
    def test_docker_is_the_default_and_unknown_modes_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.LabConfig(workspace=Path(d))
            self.assertEqual((cfg.server_mode, cfg.native, cfg.status_host), ("docker", False, "127.0.0.1"))
            self.assertEqual(cfg.status_url, f"http://127.0.0.1:{cfg.status_port}/status")
            with self.assertRaises(ValueError):
                config.LabConfig(workspace=Path(d), server_mode="wsl")
            with self.assertRaises(ValueError):
                config.LabConfig(workspace=Path(d), native_build="jit")

    def test_native_endpoints_use_localhost(self):
        # HttpListener without an URL ACL answers 400 to Host: 127.0.0.1 (measured), so every endpoint the
        # analyzers read must be addressed as localhost in native mode.
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            for url in (cfg.status_url, cfg.metrics_url, cfg.debug_kill_url, cfg.debug_entities_url):
                self.assertTrue(url.startswith(f"http://localhost:{cfg.status_port}/"), url)

    def test_the_mode_travels_through_config_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load(Path(d) / "none.json", {"server_mode": "native", "runs_root": Path(d)})
            self.assertTrue(cfg.native)


class EnvironmentTests(unittest.TestCase):
    def test_the_compose_service_environment_is_pointed_at_the_published_ports(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            env = native.native_env(cfg, COMPOSE, {})
            self.assertEqual(env["GAMESERVER_ADDR"], "127.0.0.1:9300")
            self.assertEqual(env["GAMESERVER_PUBLIC_ADDR"], "127.0.0.1:9300")     # what the gateway hands the players
            self.assertEqual(env["METRICS_ADDR"], f":{cfg.status_port}")
            self.assertEqual(env["REDIS_ADDR"], f"127.0.0.1:{cfg.redis_port}")
            self.assertEqual(env["NAKAMA_URL"], f"http://127.0.0.1:{cfg.nakama_port}")
            self.assertEqual(env["GAME_DB_URL"],
                             f"postgres://game:localdev@127.0.0.1:{cfg.postgres_game_port}/gamestate?sslmode=disable")
            self.assertEqual(env["CONTENT_DIR"], str(cfg.server_repo / "backend" / "content"))
            # Everything else is the compose service's, unchanged; empty values are dropped (unset).
            for k in ("GAMESERVER_MAP_ID", "GAMESERVER_ID", "GAMESERVER_ENEMY_SEED", "GAMESERVER_DEBUG_ENTITIES",
                      "SIM_CRITICAL_HZ", "JWT_SECRET", "JOIN_TOKEN_SECRET"):
                self.assertEqual(env[k], COMPOSE["services"]["gameserver-dotnet"]["environment"][k], k)
            self.assertNotIn("GAMESERVER_BOTS", env)
            self.assertNotIn("REDIS_PASSWORD", env)

    def test_the_snapshot_trace_is_a_host_file_only_when_the_scenario_asks(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            self.assertNotIn("GAMESERVER_SNAPSHOT_TRACE", native.native_env(cfg, COMPOSE, {}))
            env = native.native_env(cfg, COMPOSE, {"GAMESERVER_SNAPSHOT_TRACE": stack.SNAPSHOT_TRACE_PATH})
            self.assertEqual(env["GAMESERVER_SNAPSHOT_TRACE"], str(cfg.runs_root / "native" / "snapshot-trace.csv"))

    def test_a_tls_nakama_hop_or_a_missing_service_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            tls = json.loads(json.dumps(COMPOSE))
            tls["services"]["gameserver-dotnet"]["environment"]["NAKAMA_URL"] = "https://nakama:7350"
            with self.assertRaises(native.NativeError):
                native.native_env(cfg, tls, {})
            with self.assertRaises(native.NativeError):
                native.native_env(cfg, {"services": {"redis": {}}}, {})

    def test_secrets_are_redacted_but_tuning_values_are_not(self):
        red = native.redact({"JWT_SECRET": "a", "JOIN_TOKEN_SECRET": "b", "GAME_DB_URL": "c", "REDIS_PASSWORD": "d",
                             "NAKAMA_HTTP_KEY": "e", "TRANSPORT_KEY": "f", "GAMESERVER_KEYFRAME_INTERVAL": "30",
                             "SIM_CRITICAL_HZ": "60"})
        for k in ("JWT_SECRET", "JOIN_TOKEN_SECRET", "GAME_DB_URL", "REDIS_PASSWORD", "NAKAMA_HTTP_KEY", "TRANSPORT_KEY"):
            self.assertEqual(red[k], "<redacted>", k)
        self.assertEqual((red["GAMESERVER_KEYFRAME_INTERVAL"], red["SIM_CRITICAL_HZ"]), ("30", "60"))

    def test_the_child_does_not_inherit_stale_server_settings_from_the_lab_shell(self):
        with mock.patch.dict(os.environ, {"GAMESERVER_ENEMIES": "false", "SIM_WORLD_HZ": "1", "JWT_SECRET": "stale",
                                          "DOTNET_gcServer": "0", "PATH": "x"}):
            env = native.child_environment({"GAMESERVER_MAP_ID": "map_01"})
        self.assertEqual(env["GAMESERVER_MAP_ID"], "map_01")
        self.assertEqual(env["PATH"], "x")
        for k in ("GAMESERVER_ENEMIES", "SIM_WORLD_HZ", "JWT_SECRET", "DOTNET_gcServer"):
            self.assertNotIn(k, env, k)


class BuildTests(unittest.TestCase):
    def test_r2r_turns_aot_off_and_aot_is_the_project_default(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            r2r = native.publish_command(cfg, "r2r", Path(d) / "out", Path(d) / "art")
            self.assertIn("-p:PublishAot=false", r2r)
            self.assertIn("-p:PublishReadyToRun=true", r2r)
            aot = native.publish_command(cfg, "aot", Path(d) / "out", Path(d) / "art")
            self.assertFalse(any("PublishAot" in a for a in aot))
            for cmd in (r2r, aot):
                self.assertEqual(cmd[:2], ["dotnet", "publish"])
                self.assertIn("win-x64", cmd)
                self.assertIn("--artifacts-path", cmd)       # no bin/obj inside the server checkout
                self.assertIn("-nodeReuse:false", cmd)        # no build node outliving the build (G4 counts dotnet)
            with self.assertRaises(native.NativeError):
                native.publish_command(cfg, "jit", Path(d), Path(d))

    def test_auto_picks_aot_only_with_the_msvc_linker(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            with mock.patch.object(native, "linker_available", return_value=False):
                self.assertEqual(native.build_kind(cfg), "r2r")
            with mock.patch.object(native, "linker_available", return_value=True):
                self.assertEqual(native.build_kind(cfg), "aot")
            cfg.native_build = "r2r"
            with mock.patch.object(native, "linker_available", return_value=True):
                self.assertEqual(native.build_kind(cfg), "r2r")

    def test_a_failed_publish_is_reported_with_the_compiler_error(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            csproj = cfg.server_repo / native.CSPROJ
            _write(csproj, "<Project/>")
            failed = subprocess.CompletedProcess([], 1, "x.cs(1,1): error CS1002: ; expected\n", "")
            with mock.patch.object(native, "dotnet_version", return_value="10.0.400"), \
                    mock.patch.object(native.util, "IS_WINDOWS", True), \
                    mock.patch.object(native.subprocess, "run", side_effect=[
                        subprocess.CompletedProcess([], 0, "", ""),      # git rev-parse
                        subprocess.CompletedProcess([], 0, "", ""),      # git status
                        failed]):
                with self.assertRaises(native.NativeError) as ctx:
                    native.build(cfg, Path(d) / "build.log")
            self.assertIn("CS1002", str(ctx.exception))


class FakeShell:
    """Stands in for util.wsl: records every command, answers the few the bring-up reads."""

    def __init__(self, containers="rpgs-redis\tUp 1 minute\nrpgs-gameserver\tUp 1 minute\n", compose=COMPOSE):
        self.cmds = []
        self.containers = containers
        self.compose = compose

    def __call__(self, distro, command, timeout=600, check=False):
        self.cmds.append(command)
        out = ""
        if "docker ps -a" in command:
            out = self.containers
        elif "config --format json" in command:
            out = json.dumps(self.compose)
        return subprocess.CompletedProcess([], 0, out, "")

    def matching(self, text):
        return [c for c in self.cmds if text in c]


class BringUpTests(unittest.TestCase):
    BUILD = {"kind": "r2r", "dotnet_sdk": "10.0.400", "dotnet_runtime": "Microsoft.NETCore.App 10.0.11",
             "source_sha": "a" * 40, "source_dirty": False, "exe": "C:/b/GameServer.exe", "out_dir": "C:/b",
             "exe_sha256": "e" * 64, "dll_sha256": "d" * 64, "build_seconds": 1.0, "built_utc": "20260101T000000Z"}

    def _ensure(self, d, shell, *, build=False, force=False, backing_ok=False, alive=False, state=None):
        cfg = _cfg(d)
        started = []
        patches = [
            mock.patch.object(stack.util, "wsl", shell),
            mock.patch.object(stack, "health_backing", return_value=backing_ok),
            mock.patch.object(stack, "wait_ready"),
            mock.patch.object(stack, "wait_port_free"),
            mock.patch.object(stack, "advertised_game_addr", return_value="127.0.0.1:9300"),
            mock.patch.object(stack, "health", return_value={"ok": True}),
            mock.patch.object(stack, "supports_git_revision", return_value=False),
            mock.patch.object(native, "build", return_value=dict(self.BUILD)),
            mock.patch.object(native, "running", return_value=4242 if alive else None),
            mock.patch.object(native, "read_state", return_value=state or {}),
            mock.patch.object(native, "stop", return_value=None),
            mock.patch.object(native, "start", side_effect=lambda c, e, b: started.append(e) or 4242),
            mock.patch.object(native, "provenance", return_value={"runtime": "windows-native"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        rec = stack.ensure(cfg, {"GAMESERVER_MAP_ID": "map_01", "JWT_SECRET": "s"}, build=build,
                           log_path=Path(d) / "logs" / "stack-up.log", force_restart_gameserver=force)
        return rec, started

    def test_the_backing_services_start_without_the_container_game_server(self):
        with tempfile.TemporaryDirectory() as d:
            shell = FakeShell()
            rec, started = self._ensure(d, shell)
            up = shell.matching(" up -d ")
            self.assertEqual(len(up), 1, shell.cmds)
            self.assertIn("-p rpg-mmo-scratch", up[0])
            for service in ("redis", "postgres", "postgres-game", "nakama", "gateway"):
                self.assertRegex(up[0], rf"\b{service}\b")
            self.assertNotIn("gameserver-dotnet", up[0].split(" up -d ")[1])
            # stack.sh is used only to write .env.scratch (ps), never `up` without --build-server
            self.assertEqual(shell.matching("stack.sh --scratch up"), [])
            self.assertTrue(shell.matching("--no-build ps"))
            self.assertEqual(rec["server_runtime"], "windows-native")
            self.assertEqual(len(started), 1)
            self.assertEqual(started[0]["GAMESERVER_PUBLIC_ADDR"], "127.0.0.1:9300")

    def test_a_leftover_container_game_server_and_its_registry_entry_are_removed_before_the_start(self):
        with tempfile.TemporaryDirectory() as d:
            shell = FakeShell()
            order = []
            with mock.patch.object(stack, "redis_cli", side_effect=lambda c, a: order.append("redis " + a) or []):
                orig_call = shell.__call__

                def tracing(distro, command, timeout=600, check=False):
                    if "docker rm -f" in command:
                        order.append(command)
                    return orig_call(distro, command, timeout, check)
                self._ensure_with(d, tracing, order)
            rm = [o for o in order if "docker rm -f rpgs-gameserver" in o]
            self.assertEqual(len(rm), 1, order)
            self.assertIn("redis del servers:id:gs-dotnet-map_01", order)
            self.assertIn("redis srem servers:map:map_01 gs-dotnet-map_01", order)
            self.assertLess(order.index(rm[0]), order.index("redis del servers:id:gs-dotnet-map_01"))
            self.assertEqual(order[-1], "start")

    def _ensure_with(self, d, shell, order, free=None):
        cfg = _cfg(d)
        with mock.patch.object(stack.util, "wsl", shell), mock.patch.object(stack, "health_backing", return_value=False), \
                mock.patch.object(stack, "wait_ready"), mock.patch.object(stack, "health", return_value={}), \
                mock.patch.object(stack, "wait_port_free", side_effect=free), \
                mock.patch.object(stack, "advertised_game_addr", return_value="127.0.0.1:9300"), \
                mock.patch.object(stack, "supports_git_revision", return_value=False), \
                mock.patch.object(native, "build", return_value=dict(self.BUILD)), \
                mock.patch.object(native, "running", return_value=None), \
                mock.patch.object(native, "read_state", return_value={}), mock.patch.object(native, "stop", return_value=None), \
                mock.patch.object(native, "start", side_effect=lambda c, e, b: order.append("start") or 1), \
                mock.patch.object(native, "provenance", return_value={}):
            return stack.ensure(cfg, {"GAMESERVER_MAP_ID": "map_01"}, build=False, log_path=Path(d) / "l.log",
                                force_restart_gameserver=True)

    def test_a_healthy_unchanged_stack_and_server_are_reused(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            env = {"GAMESERVER_MAP_ID": "map_01", "JWT_SECRET": "s"}
            native_env = native.native_env(cfg, COMPOSE, env)
            state = {"env": native.redact(native_env), "build": dict(self.BUILD)}
            shell = FakeShell()
            # first call writes the stack state the second one compares with
            self._ensure(d, shell)
            shell2 = FakeShell()
            rec, started = self._ensure(d, shell2, backing_ok=True, alive=True, state=state)
            self.assertEqual(started, [])
            self.assertEqual(shell2.matching(" up -d "), [])
            self.assertTrue(any("reused native game server" in a for a in rec["actions"]), rec["actions"])

    def test_a_scenario_that_needs_a_fresh_world_restarts_the_server(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            env = {"GAMESERVER_MAP_ID": "map_01", "JWT_SECRET": "s"}
            state = {"env": native.redact(native.native_env(cfg, COMPOSE, env)), "build": dict(self.BUILD)}
            self._ensure(d, FakeShell())
            rec, started = self._ensure(d, FakeShell(), backing_ok=True, alive=True, state=state, force=True)
            self.assertEqual(len(started), 1)

    def test_the_status_port_is_awaited_after_the_container_is_removed(self):
        with tempfile.TemporaryDirectory() as d:
            order = []
            shell = FakeShell()
            orig = shell.__call__

            def tracing(distro, command, timeout=600, check=False):
                if "docker rm -f" in command:
                    order.append("rm")
                return orig(distro, command, timeout, check)
            self._ensure_with(d, tracing, order, free=lambda p, timeout: order.append("free"))
            self.assertEqual([o for o in order if o in ("rm", "free", "start")], ["rm", "free", "start"])

    def test_wait_port_free_gives_up_with_the_port_named(self):
        with mock.patch.object(stack, "_port_open", return_value=True), mock.patch.object(stack.time, "sleep"), \
                mock.patch.object(stack.util, "mono", side_effect=[0, 1, 100]):
            with self.assertRaises(stack.StackError) as ctx:
                stack.wait_port_free(9501, timeout=10)
        self.assertIn("9501", str(ctx.exception))
        with mock.patch.object(stack, "_port_open", return_value=False):
            stack.wait_port_free(9501, timeout=10)

    def test_a_server_whose_metrics_endpoint_could_not_bind_is_an_error_not_a_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            log = cfg.runs_root / "native" / "server.log"
            failed = "fail: Program[0]\n      Failed to start metrics endpoint on http://localhost:9501/\n"
            _write(log, "old run\n" + failed)
            util.write_json(cfg.runs_root / "native" / "server.json",
                            {"pid": 1, "exe": "x", "log_offset": log.stat().st_size})
            self.assertIsNone(native.startup_failure(cfg))          # an earlier run's failure is not this server's
            with open(log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(failed)
            self.assertIn("9501", native.startup_failure(cfg))
            with mock.patch.object(stack, "health", return_value={"ok": False}), \
                    mock.patch.object(stack, "redis_map_members", return_value=[]), \
                    mock.patch.object(native, "running", return_value=1):
                with self.assertRaises(stack.StackError) as ctx:
                    stack.wait_ready(cfg, "map_01", timeout=5)
            self.assertIn("without its status endpoint", str(ctx.exception))

    def test_a_scenario_with_netem_is_refused_in_native_mode(self):
        with tempfile.TemporaryDirectory() as d:
            sc = {"disruptions": [{"kind": "netem", "at_s": 5}]}
            with self.assertRaises(stack.StackError):
                stack.check_scenario_supported(_cfg(d), sc)
            stack.check_scenario_supported(_cfg(d), {"disruptions": [{"kind": "debug_kill", "at_s": 5}]})
            docker = config.LabConfig(workspace=Path(d))
            stack.check_scenario_supported(docker, sc)


class DispatchTests(unittest.TestCase):
    def test_restart_stats_and_trace_go_to_the_native_process(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            with mock.patch.object(native, "restart") as restart, mock.patch.object(stack.util, "wsl") as wsl:
                stack.restart_gameserver(cfg)
                restart.assert_called_once()
                wsl.assert_not_called()
            with mock.patch.object(native, "running", return_value=77), \
                    mock.patch.object(native, "process_stats", return_value={"mem_bytes": 1}) as ps:
                self.assertEqual(stack.server_stats(cfg), {"mem_bytes": 1})
                ps.assert_called_once_with(77)
            src = cfg.runs_root / "native" / "snapshot-trace.csv"
            _write(src, "tick,t\n1,2\n")
            out = stack.fetch_snapshot_trace(cfg, Path(d) / "run" / "server" / "snapshot-trace.csv")
            self.assertTrue(out["copied"], out)
            self.assertEqual((Path(d) / "run" / "server" / "snapshot-trace.csv").read_text(), "tick,t\n1,2\n")

    def test_docker_mode_still_uses_docker_stats(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.LabConfig(workspace=Path(d), runs_root=Path(d))
            with mock.patch.object(stack, "docker_stats", return_value={"cpu_pct": 1.0}) as ds:
                self.assertEqual(stack.server_stats(cfg), {"cpu_pct": 1.0})
                ds.assert_called_once()

    def test_the_probe_samples_through_server_stats(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("server_stats", Path(probe.__file__).read_text(encoding="utf-8"))

    def test_down_stops_the_native_server_and_a_docker_bring_up_stops_it_first(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            done = subprocess.CompletedProcess([], 0, "", "")
            with mock.patch.object(native, "stop", return_value="stopped native game server pid 9") as stop, \
                    mock.patch.object(stack.util, "wsl", return_value=done):
                self.assertIn("stopped native game server pid 9", stack.down(cfg))
                stop.assert_called_once()
            docker = config.LabConfig(workspace=Path(d), runs_root=Path(d))
            with mock.patch.object(native, "stop", return_value=None) as stop, \
                    mock.patch.object(stack, "health", return_value={"ok": True}), \
                    mock.patch.object(stack, "wait_ready"), mock.patch.object(stack.util, "wsl", return_value=done):
                stack.ensure(docker, {"GAMESERVER_MAP_ID": "map_01"}, build=False, log_path=Path(d) / "l.log",
                             force_restart_gameserver=False)
                stop.assert_called_once()


class NativeNeverRunsTheFullStackUpTests(unittest.TestCase):
    """RV-P1B-1: `stack.sh up` ends in `dc up -d` for the whole project, which starts gameserver-dotnet."""

    BUILD = BringUpTests.BUILD
    _ensure = BringUpTests._ensure

    def _run(self, build):
        with tempfile.TemporaryDirectory() as d:
            shell = FakeShell()
            self._ensure(d, shell, build=build)
            return shell.cmds

    def test_no_native_path_runs_the_full_stack_up(self):
        for build in (True, False):
            with self.subTest(build=build):
                cmds = self._run(build)
                self.assertEqual([c for c in cmds if re.search(r"stack\.sh.*\bup\b", c)], [], cmds)
                ups = [c for c in cmds if " up -d" in c]
                self.assertEqual(len(ups), 1, cmds)
                self.assertTrue(ups[0].rstrip().split(" up -d")[1].strip(), "up -d must name its services")
                self.assertNotIn("gameserver-dotnet", ups[0].split(" up -d")[1])

    def test_build_makes_the_plugin_and_gateway_image_and_not_the_game_server_image(self):
        cmds = self._run(True)
        self.assertEqual(len([c for c in cmds if "nakama-plugin.Dockerfile" in c]), 1, cmds)
        self.assertEqual(len([c for c in cmds if "docker/Dockerfile.gateway" in c]), 1, cmds)
        self.assertEqual([c for c in cmds if "Dockerfile.gameserver" in c], [])
        first_up = next(i for i, c in enumerate(cmds) if " up -d" in c)
        self.assertTrue(all(i < first_up for i, c in enumerate(cmds) if "Dockerfile" in c))

    def test_without_build_nothing_is_built(self):
        self.assertEqual([c for c in self._run(False) if "docker build" in c], [])

    def test_a_failed_image_build_stops_before_any_service_starts(self):
        shell = FakeShell()

        def failing(distro, command, timeout=600, check=False):
            res = shell(distro, command, timeout, check)
            return subprocess.CompletedProcess([], 1, "", "boom") if "Dockerfile.gateway" in command else res
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(stack.StackError):
                self._ensure(d, failing, build=True)
        self.assertEqual([c for c in shell.cmds if " up -d" in c], [])


class StopTests(unittest.TestCase):
    def _state(self, d):
        cfg = _cfg(d)
        state_path = native._paths(cfg)["state"]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{}", encoding="utf-8")
        return cfg, state_path

    def test_a_server_that_survives_the_kill_keeps_its_state_and_fails_the_stop(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, state_path = self._state(d)
            clock = iter(range(0, 1000, 5))
            with mock.patch.object(native, "running", return_value=77), \
                    mock.patch.object(native.util, "kill_tree", return_value=True), \
                    mock.patch.object(native.util, "process_alive", return_value=True), \
                    mock.patch.object(native.util, "mono", side_effect=lambda: next(clock)), \
                    mock.patch.object(native.time, "sleep"):
                with self.assertRaises(native.NativeError) as ctx:
                    native.stop(cfg)
            self.assertIn("pid 77", str(ctx.exception))
            self.assertTrue(state_path.exists())

    def test_a_server_that_exits_after_the_kill_clears_its_state(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, state_path = self._state(d)
            with mock.patch.object(native, "running", return_value=77), \
                    mock.patch.object(native.util, "kill_tree", return_value=True), \
                    mock.patch.object(native.util, "process_alive", return_value=False):
                self.assertIn("stopped native game server pid 77", native.stop(cfg))
            self.assertFalse(state_path.exists())


class ProcessTests(unittest.TestCase):
    @unittest.skipUnless(util.IS_WINDOWS, "Windows process counters")
    def test_the_sampler_reads_memory_and_a_cpu_rate_from_a_live_process(self):
        pid = os.getpid()
        native._PREV.pop(pid, None)
        first = native.process_stats(pid)
        self.assertGreater(first["mem_bytes"], 1_000_000)
        self.assertIsNone(first["cpu_pct"])                  # a rate needs two samples
        sum(i * i for i in range(2_000_000))
        second = native.process_stats(pid)
        self.assertGreater(second["cpu_pct"], 0.0)

    def test_a_missing_process_has_no_stats(self):
        self.assertIsNone(native.process_stats(None))
        self.assertIsNone(native.process_stats(0))

    def test_running_is_the_recorded_pid_only_while_it_runs_the_recorded_exe(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            self.assertIsNone(native.running(cfg))
            exe = str(Path(d) / "b" / "GameServer.exe")
            util.write_json(cfg.runs_root / "native" / "server.json", {"pid": 4242, "exe": exe})
            with mock.patch.object(native.util, "process_image", return_value=exe):
                self.assertEqual(native.running(cfg), 4242)
            with mock.patch.object(native.util, "process_image", return_value=str(Path(d) / "other" / "notepad.exe")):
                self.assertIsNone(native.running(cfg))          # a reused pid is never ours
                with mock.patch.object(native.util, "kill_tree") as kill:
                    native.stop(cfg)
                    kill.assert_not_called()
            self.assertFalse((cfg.runs_root / "native" / "server.json").exists())

    def test_a_server_that_exits_at_once_is_an_error_with_its_log(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            build = {"exe": sys.executable, "out_dir": d}
            with mock.patch.object(native.subprocess, "Popen") as popen, mock.patch.object(native.time, "sleep"):
                popen.return_value.poll.return_value = 3
                popen.return_value.returncode = 3
                popen.return_value.pid = 5
                with self.assertRaises(native.NativeError) as ctx:
                    native.start(cfg, {"GAMESERVER_MAP_ID": "map_01"}, build)
            self.assertIn("exited at once", str(ctx.exception))
            self.assertIsNone(native.running(cfg))

    def test_the_log_since_the_run_start_is_copied(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d)
            log = cfg.runs_root / "native" / "server.log"
            _write(log, "old run\n")
            offset = native.log_offset(cfg)
            with open(log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write("this run\n")
            res = native.copy_log(cfg, offset, Path(d) / "run" / "server" / "gameserver.log")
            self.assertTrue(res["copied"])
            self.assertEqual((Path(d) / "run" / "server" / "gameserver.log").read_text(), "this run\n")


NATIVE_PROV = {"runtime": "windows-native", "kind": "r2r", "dotnet_sdk": "10.0.400", "source_sha": "s" * 40,
               "exe_sha256": "e" * 64, "dotnet_runtime": "Microsoft.NETCore.App 10.0.11"}


def _native_run(root: Path, **edit):
    """A finished run directory whose provenance says the server ran natively."""
    run = _run_dir(root)
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    srv = meta["provenance"]["server"]
    srv.update(runtime="windows-native", native=dict(NATIVE_PROV), image_id="native:" + "e" * 64,
               label_supported=True, image_revision="s" * 40)
    srv.update(edit)
    _write(run / "run.json", json.dumps(meta))
    return run


class ProvenanceAndReportTests(unittest.TestCase):
    def _problems(self, run):
        return analyze.check_provenance(analyze.load_evidence(run), {})["detail"]["problems"]

    def test_a_complete_native_record_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            run = _native_run(Path(d))
            res = analyze.check_provenance(analyze.load_evidence(run), {})
            self.assertEqual(res["status"], analyze.PASS, res["detail"])

    def test_a_docker_record_reports_the_docker_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            self.assertEqual(report._server_runtime(analyze.load_evidence(run)["meta"])["runtime"], "docker")

    def test_the_binary_hash_is_required_and_must_match_the_image_id(self):
        with tempfile.TemporaryDirectory() as d:
            run = _native_run(Path(d), native={**NATIVE_PROV, "exe_sha256": None})
            self.assertTrue(any("server.native.exe_sha256 missing" in p for p in self._problems(run)))
        with tempfile.TemporaryDirectory() as d:
            run = _native_run(Path(d), image_id="native:" + "0" * 64)
            self.assertTrue(any("not the hash of the native binary" in p for p in self._problems(run)))

    def test_a_binary_built_from_another_commit_than_the_recorded_server_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            run = _native_run(Path(d), native={**NATIVE_PROV, "source_sha": "b" * 40})
            self.assertTrue(any("built from bbbbbbbbbbbb" in p for p in self._problems(run)), self._problems(run))

    def test_the_report_states_the_server_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            run = _native_run(Path(d))
            ev = analyze.load_evidence(run)
            results = analyze.evaluate(ev)
            doc = report.write(run, ev, results, "INCONCLUSIVE", None)
            self.assertEqual(doc["server_runtime"]["runtime"], "windows-native")
            self.assertEqual(doc["server_runtime"]["exe_sha256"], "e" * 64)
            md = (run / "report.md").read_text(encoding="utf-8")
            self.assertIn("**Server runtime: windows-native**", md)
            self.assertIn("| server runtime | windows-native (r2r build", md)
        with tempfile.TemporaryDirectory() as d:
            run = _run_dir(Path(d))
            ev = analyze.load_evidence(run)
            report.write(run, ev, analyze.evaluate(ev), "INCONCLUSIVE", None)
            md = (run / "report.md").read_text(encoding="utf-8")
            self.assertIn("Server runtime: docker", md)
            self.assertIn("| server runtime | docker |", md)


if __name__ == "__main__":
    unittest.main()
