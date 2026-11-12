#!/usr/bin/env python3
"""Set up Comfy Desktop + the 9router image node + comfy-mcp for Claude and Codex (asset-gen's ComfyUI side).

Read-only by default. `--check` (the default) inspects and prints what is missing and changes nothing;
`--apply` does the missing steps; `--generate-test` (only with --apply) runs one low-quality image through
the instance. Idempotent: a step that is already OK is skipped.

Usage: comfy-desktop-setup.py [--check | --apply] [--instance NAME|ID] [--targets claude,codex|none]
           [--port N] [--venv DIR] [--python EXE] [--desktop-dir DIR] [--codex-config FILE] [--provider NAME]
           [--generate-test] [--json]

Steps (each prints OK, MISSING, OUTDATED, ACTION or FAIL; `ACTION` is a human step):
  desktop    Comfy Desktop's data dir (installations.json)            override --desktop-dir / COMFY_DESKTOP_DIR
  instance   a local (non-cloud) instance, e.g. sourceId standalone    the Cloud instance cannot host nodes
  provider   [model_providers.<name>] in the Codex config has base_url and an Authorization header (names only)
  node       comfyui_9router in <instance>/ComfyUI/custom_nodes equals the plugin's vendored copy
  venv       comfy-mcp installed in its own venv (default ~/.comfy-mcp-venv)
  port       the instance's running port (comfy-procs/<id>.json, else port-locks/); ACTION when it is not running
  node-live  GET /object_info/NineRouterImage on that port: ACTION (Stop + Launch the instance) when absent
  mcp-claude / mcp-codex   comfy-mcp registered with COMFY_LOCAL_URL equal to the port (a changed port = remove + add)
  generate   --generate-test: PrimitiveStringMultiline -> NineRouterImage -> SaveImage through POST /prompt

Exit codes: 0 READY (every step OK); 1 FAIL (a step failed or a prerequisite cannot be fixed by this script);
2 usage; 3 ACTION_NEEDED (something is missing or a human step remains: --check with a gap, or --apply done
but the instance must be restarted / created first).

Never prints, logs or stores a credential: the provider config is only tested for the presence of the names
`base_url` and `http_headers.Authorization`; the key reaches the gateway only through the node at run time.
It never runs `comfy-mcp --help` (a stdio server: it hangs) and never edits the Codex config by hand (the
`codex mcp` CLI owns it). Writes (with --apply only): the instance's custom_nodes/comfyui_9router, the venv,
the two CLIs' MCP registrations, and with --generate-test an image in the instance's output folder. It writes no
Factory state and nothing into the plugin or any repository, so it lives under scripts/ (write-capable tools:
new-skill.py, changelog.py), not under scripts/checks/ or the read-only factory-context/status scripts.
Test hooks: COMFY_SETUP_CLAUDE_CMD / COMFY_SETUP_CODEX_CMD replace the CLI argv prefix (space-split, forward slashes).
Platforms: Windows is verified; the macOS and Linux paths are UNVERIFIED (reported as such in the output).
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_SRC = os.path.join(ROOT, "templates", "assetgen", "comfy-node", "comfyui_9router", "__init__.py")
TEMPLATE = os.path.join(ROOT, "templates", "assetgen", "workflows", "image-generate.json")
NODE_DIR = "comfyui_9router"
MCP_NAME = "comfy-mcp"
HOST = "127.0.0.1"
WIN = sys.platform == "win32"
UNVERIFIED = not WIN
SECRET = re.compile(r"(Bearer\s+\S+|\bsk-[A-Za-z0-9_-]{8,}|\"?Authorization\"?\s*[:=]\s*\S+)", re.I)
OK, MISSING, OUTDATED, ACTION, FAIL, SKIP = "OK", "MISSING", "OUTDATED", "ACTION", "FAIL", "SKIP"


def scrub(text, limit=300):
    return SECRET.sub("<redacted>", str(text))[:limit]


class Report:
    def __init__(self):
        self.rows = []

    def add(self, step, state, detail="", hint=""):
        self.rows.append({"step": step, "state": state, "detail": scrub(detail, 400), "hint": hint})
        return state

    def state(self, step):
        for r in self.rows:
            if r["step"] == step:
                return r["state"]
        return None

    def exit_code(self):
        states = [r["state"] for r in self.rows]
        if FAIL in states:
            return 1
        if any(s in (MISSING, OUTDATED, ACTION) for s in states):
            return 3
        return 0


# ---- paths -------------------------------------------------------------------------------------------------------

def desktop_dir(arg):
    if arg:
        return arg
    if os.environ.get("COMFY_DESKTOP_DIR"):
        return os.environ["COMFY_DESKTOP_DIR"]
    home = os.path.expanduser("~")
    if WIN:
        return os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "Comfy Desktop")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Comfy Desktop")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "Comfy Desktop")


def venv_exe(venv):
    return os.path.join(venv, "Scripts", "comfy-mcp.exe") if WIN else os.path.join(venv, "bin", "comfy-mcp")


def venv_python(venv):
    return os.path.join(venv, "Scripts", "python.exe") if WIN else os.path.join(venv, "bin", "python")


def codex_config(arg):
    return arg or os.environ.get("NINEROUTER_CODEX_CONFIG") or os.path.join(os.path.expanduser("~"), ".codex", "config.toml")


def norm_hash(path):
    """sha256 of the file with CRLF folded to LF (git autocrlf on Windows must not make the node look outdated)."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---- steps -------------------------------------------------------------------------------------------------------

def pick_instance(rep, ddir, want):
    inst_file = os.path.join(ddir, "installations.json")
    data = read_json(inst_file)
    if not isinstance(data, list):
        rep.add("desktop", MISSING, "no installations.json under the Comfy Desktop data dir (%s)" % ("unverified path on this OS" if UNVERIFIED else "Desktop never started?"),
                "install and start Comfy Desktop once; or pass --desktop-dir")
        return None
    rep.add("desktop", OK, "%d installation(s)%s" % (len(data), "; path UNVERIFIED on this OS" if UNVERIFIED else ""))
    local = [i for i in data if isinstance(i, dict) and i.get("sourceId") != "cloud" and i.get("installPath")]
    if want:
        local = [i for i in local if want in (i.get("id"), i.get("name"))]
    if not local:
        cloud = any(isinstance(i, dict) and i.get("sourceId") == "cloud" for i in data)
        rep.add("instance", ACTION, "no local instance%s" % (" named %r" % want if want else "") + (" (only Comfy Cloud: it cannot host custom nodes and comfy-mcp cannot reach it)" if cloud else ""),
                "Desktop > Dashboard > New Instance > Standalone / Local (CPU is enough: only API nodes run), then re-run")
        return None
    local.sort(key=lambda i: (i.get("sourceId") != "standalone", -(i.get("lastLaunchedAt") or 0)))
    chosen = local[0]
    extra = " (first of %d; pass --instance)" % len(local) if len(local) > 1 and not want else ""
    rep.add("instance", OK, "%s [%s, %s]%s" % (chosen.get("name"), chosen.get("id"), chosen.get("sourceId"), extra))
    return chosen


def check_provider(rep, cfg, name):
    if tomllib is None:
        rep.add("provider", FAIL, "Python 3.11+ is needed to read the Codex config (tomllib)")
        return False
    try:
        with open(cfg, "rb") as f:
            prov = tomllib.load(f).get("model_providers", {}).get(name)
    except OSError:
        prov = None
    except tomllib.TOMLDecodeError:
        rep.add("provider", FAIL, "the Codex config is not valid TOML")
        return False
    need = "[model_providers.%s] with base_url and http_headers.Authorization in the Codex config (~/.codex/config.toml; NINEROUTER_CODEX_CONFIG / NINEROUTER_PROVIDER override)" % name
    if not isinstance(prov, dict):
        rep.add("provider", FAIL, "no [model_providers.%s] section" % name, "add " + need + "; this script never writes it")
        return False
    miss = []
    if not prov.get("base_url"):
        miss.append("base_url")
    headers = prov.get("http_headers")
    if not (isinstance(headers, dict) and headers.get("Authorization")):
        miss.append("http_headers.Authorization")
    if miss:
        rep.add("provider", FAIL, "missing: " + ", ".join(miss), "add " + need)
        return False
    rep.add("provider", OK, "[model_providers.%s] has base_url and an Authorization header (values not read out)" % name)
    return True


def check_node(rep, inst, apply):
    dest_dir = os.path.join(inst["installPath"], "ComfyUI", "custom_nodes", NODE_DIR)
    dest = os.path.join(dest_dir, "__init__.py")
    want = norm_hash(NODE_SRC)
    if want is None:
        return rep.add("node", FAIL, "the plugin's vendored node is missing: " + NODE_SRC)
    have = norm_hash(dest)
    if have == want:
        return rep.add("node", OK, dest)
    state = MISSING if have is None else OUTDATED
    if not os.path.isdir(os.path.dirname(dest_dir)):
        return rep.add("node", FAIL, "no custom_nodes dir at " + os.path.dirname(dest_dir), "start the instance once so ComfyUI creates it")
    if not apply:
        return rep.add("node", state, "copy to " + dest, "run with --apply")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with open(NODE_SRC, "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")
        with open(dest, "wb") as f:
            f.write(data)
    except OSError as e:
        return rep.add("node", FAIL, "copy failed: %s" % e)
    return rep.add("node", OK, "copied to %s (loads at the next instance start)" % dest)


def run(cmd, timeout=600, env=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def check_venv(rep, venv, py, apply):
    exe = venv_exe(venv)
    if os.path.isfile(exe):
        return rep.add("venv", OK, exe)
    if not apply:
        return rep.add("venv", MISSING, "no %s" % exe, "run with --apply (python -m venv, pip install comfy-mcp)")
    if not os.path.isfile(venv_python(venv)):
        rc, out = run([py, "-m", "venv", venv], 300)
        if rc != 0:
            return rep.add("venv", FAIL, "python -m venv failed: " + out[-300:])
    rc, out = run([venv_python(venv), "-m", "pip", "install", "--disable-pip-version-check", "comfy-mcp"], 900)
    if rc != 0 or not os.path.isfile(exe):
        return rep.add("venv", FAIL, "pip install comfy-mcp failed: " + out[-300:])
    return rep.add("venv", OK, exe)


def alive(port, timeout=3):
    try:
        with urllib.request.urlopen("http://%s:%d/system_stats" % (HOST, port), timeout=timeout) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def find_port(rep, ddir, inst, forced):
    """The port is not fixed (Desktop picks a free one): comfy-procs/<id>.json, else port-locks/port-*.json."""
    cands = []
    if forced:
        cands.append(forced)
    proc = read_json(os.path.join(ddir, "comfy-procs", "%s.json" % inst.get("id"))) or {}
    if isinstance(proc.get("port"), int):
        cands.append(proc["port"])
    locks = os.path.join(ddir, "port-locks")
    if os.path.isdir(locks):
        for fn in sorted(os.listdir(locks)):
            m = re.fullmatch(r"port-(\d+)\.json", fn)
            lk = read_json(os.path.join(locks, fn)) or {}
            if m and lk.get("installationName") == inst.get("name"):
                cands.append(int(m.group(1)))
    for p in dict.fromkeys(cands):
        if alive(p):
            rep.add("port", OK, "%d (instance answers)" % p)
            return p
    rep.add("port", ACTION, "instance %r is not running%s" % (inst.get("name"), " on the given port" if forced else ""),
            "Comfy Desktop > Launch the instance (an agent cannot click the app), then re-run")
    return None


def node_live(rep, port, restart_needed):
    try:
        with urllib.request.urlopen("http://%s:%d/object_info/NineRouterImage" % (HOST, port), timeout=10) as r:
            body = json.loads(r.read() or b"{}")
        if "NineRouterImage" in body:
            return rep.add("node-live", OK, "NineRouterImage is loaded on port %d" % port)
    except (OSError, ValueError):
        pass
    return rep.add("node-live", ACTION, "NineRouterImage is not loaded on port %d" % port,
                   "custom nodes load only at instance start: Desktop > Stop, then Launch the instance, then re-run" + (" (the node was just copied)" if restart_needed else ""))


def cli_cmd(cli):
    """The argv prefix of a CLI: COMFY_SETUP_<CLI>_CMD (tests; split on spaces, use forward slashes), else the PATH entry."""
    over = os.environ.get("COMFY_SETUP_%s_CMD" % cli.upper())
    if over:
        return shlex.split(over)
    found = shutil.which(cli)
    return [found] if found else None


def registered(cli):
    """(exists, url) of the comfy-mcp registration of one CLI; the output is parsed, never echoed."""
    base = cli_cmd(cli)
    if cli == "codex":
        rc, out = run(base + ["mcp", "get", MCP_NAME, "--json"], 60)
        if rc != 0:
            return False, None
        try:
            return True, ((json.loads(out).get("transport") or {}).get("env") or {}).get("COMFY_LOCAL_URL")
        except ValueError:
            return True, None
    rc, out = run(base + ["mcp", "get", MCP_NAME], 90)
    if rc != 0:
        return False, None
    m = re.search(r"COMFY_LOCAL_URL=(\S+)", out)
    return True, (m.group(1) if m else None)


def check_mcp(rep, cli, exe, url, apply):
    step = "mcp-" + cli
    base = cli_cmd(cli)
    if not base:
        return rep.add(step, SKIP, "%s CLI not on PATH" % cli)
    exists, have = registered(cli)
    if exists and have == url:
        return rep.add(step, OK, "%s -> %s (new MCP servers load only in a new session)" % (MCP_NAME, url))
    state = OUTDATED if exists else MISSING
    detail = "registered with COMFY_LOCAL_URL %s, running port needs %s" % (have, url) if exists else "%s is not registered" % MCP_NAME
    if not apply:
        return rep.add(step, state, detail, "run with --apply")
    if exists:  # a changed port = remove + add
        rc, out = run(base + ["mcp", "remove", MCP_NAME] + (["--scope", "user"] if cli == "claude" else []), 60)
        if rc != 0:
            return rep.add(step, FAIL, "remove failed: " + out[-200:])
    if cli == "claude":
        cmd = base + ["mcp", "add", MCP_NAME, "--scope", "user", "-e", "COMFY_LOCAL_URL=" + url, "--", exe]
    else:
        cmd = base + ["mcp", "add", MCP_NAME, "--env", "COMFY_LOCAL_URL=" + url, "--", exe]
    rc, out = run(cmd, 90)
    if rc != 0:
        return rep.add(step, FAIL, "%s mcp add failed: %s" % (cli, out[-200:]))
    return rep.add(step, OK, "registered %s -> %s; start a new %s session to load it" % (MCP_NAME, url, cli))


def default_model():
    d = read_json(TEMPLATE) or {}
    return ((d.get("params") or {}).get("model") or {}).get("default")


def generate(rep, port):
    model = default_model()
    if not model:
        return rep.add("generate", FAIL, "no default model in the image-generate template")
    graph = {
        "1": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "A small flat-color red apple icon on a plain light background."}},
        "2": {"class_type": "NineRouterImage", "inputs": {"user_prompt": ["1", 0], "model": model, "size": "1024x1024", "quality": "low", "background": "auto"}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "assetgen/setup-test"}},
    }
    base = "http://%s:%d" % (HOST, port)
    try:
        req = urllib.request.Request(base + "/prompt", data=json.dumps({"prompt": graph}).encode(), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            pid = json.loads(r.read())["prompt_id"]
    except urllib.error.HTTPError as e:
        return rep.add("generate", FAIL, "POST /prompt HTTP %d: %s" % (e.code, e.read()[:300].decode("utf-8", "replace")))
    except (OSError, ValueError, KeyError) as e:
        return rep.add("generate", FAIL, "POST /prompt failed: %s" % e)
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("%s/history/%s" % (base, pid), timeout=15) as r:
                hist = json.loads(r.read()).get(pid)
        except (OSError, ValueError):
            hist = None
        if hist and (hist.get("status") or {}).get("completed") is not None:
            st = hist["status"]
            if st.get("status_str") != "success":
                msgs = [m for m in st.get("messages", []) if m and m[0] == "execution_error"]
                return rep.add("generate", FAIL, "run failed: %s" % (msgs[-1][1].get("exception_message", "") if msgs else st.get("status_str")))
            imgs = [i for o in hist.get("outputs", {}).values() for i in o.get("images", [])]
            if not imgs:
                return rep.add("generate", FAIL, "run succeeded but produced no image")
            i = imgs[0]
            size = ""
            try:
                q = "filename=%s&subfolder=%s&type=%s" % (urllib.request.quote(i["filename"]), urllib.request.quote(i.get("subfolder", "")), i.get("type", "output"))
                with urllib.request.urlopen("%s/view?%s" % (base, q), timeout=30) as r:
                    head = r.read(24)
                if head[:8] == b"\x89PNG\r\n\x1a\n":
                    size = " %dx%d" % (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))
            except (OSError, ValueError, KeyError):
                pass
            return rep.add("generate", OK, "image generated%s (returned size can differ from the request); saved in the instance output folder under %s/%s" % (size, i.get("subfolder", ""), i["filename"]))
        time.sleep(2)
    return rep.add("generate", FAIL, "no result after 300 s (prompt %s)" % pid)


# ---- main --------------------------------------------------------------------------------------------------------

def main(argv):
    ap = argparse.ArgumentParser(prog="comfy-desktop-setup.py", description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="inspect only (default)")
    mode.add_argument("--apply", action="store_true", help="do the missing steps")
    ap.add_argument("--instance", help="instance name or id (default: the most recently launched standalone one)")
    ap.add_argument("--targets", default="claude,codex", help="comma list of claude, codex, or none (default both)")
    ap.add_argument("--port", type=int, help="use this port instead of reading it from Desktop's files")
    ap.add_argument("--venv", default=os.path.join(os.path.expanduser("~"), ".comfy-mcp-venv"))
    ap.add_argument("--python", default=sys.executable, help="python used to create the venv (3.10+)")
    ap.add_argument("--desktop-dir", help="Comfy Desktop data dir (default per OS; COMFY_DESKTOP_DIR)")
    ap.add_argument("--codex-config", help="Codex config with the provider (default ~/.codex/config.toml; NINEROUTER_CODEX_CONFIG)")
    ap.add_argument("--provider", default=os.environ.get("NINEROUTER_PROVIDER", "9router"))
    ap.add_argument("--generate-test", action="store_true", help="with --apply: one low-quality image through the gateway (spends a little)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    targets = [] if a.targets == "none" else [t.strip() for t in a.targets.split(",") if t.strip()]
    if any(t not in ("claude", "codex") for t in targets):
        print("comfy-desktop-setup: --targets takes claude, codex or none", file=sys.stderr)
        return 2
    if a.generate_test and not a.apply:
        print("comfy-desktop-setup: --generate-test needs --apply (it writes an image and calls the gateway)", file=sys.stderr)
        return 2
    apply = a.apply
    rep = Report()
    inst = pick_instance(rep, desktop_dir(a.desktop_dir), a.instance)
    check_provider(rep, codex_config(a.codex_config), a.provider)
    node_changed = False
    if inst:
        before = norm_hash(os.path.join(inst["installPath"], "ComfyUI", "custom_nodes", NODE_DIR, "__init__.py"))
        check_node(rep, inst, apply)
        node_changed = apply and rep.state("node") == OK and before != norm_hash(NODE_SRC)
    check_venv(rep, a.venv, a.python, apply)
    port = find_port(rep, desktop_dir(a.desktop_dir), inst, a.port) if inst else None
    if port:
        node_live(rep, port, node_changed)
        url = "http://%s:%d" % (HOST, port)
        exe = venv_exe(a.venv)
        for cli in targets:
            if os.path.isfile(exe) or not apply:
                check_mcp(rep, cli, exe, url, apply and os.path.isfile(exe))
            else:
                rep.add("mcp-" + cli, FAIL, "no comfy-mcp executable to register")
        if a.generate_test:
            if rep.state("node-live") == OK and rep.state("provider") == OK:
                generate(rep, port)
            else:
                rep.add("generate", SKIP, "needs the node loaded and the provider config")
    else:
        for cli in targets:
            rep.add("mcp-" + cli, SKIP, "needs the running port (registration carries COMFY_LOCAL_URL)")
    code = rep.exit_code()
    if a.json:
        print(json.dumps({"mode": "apply" if apply else "check", "os": sys.platform, "unverified_os": UNVERIFIED, "exit": code, "steps": rep.rows}, indent=1))
    else:
        for r in rep.rows:
            print("%-10s %-9s %s" % (r["step"], r["state"], r["detail"]))
            if r["hint"] and r["state"] not in (OK, SKIP):
                print("%-10s %-9s -> %s" % ("", "", r["hint"]))
        if UNVERIFIED:
            print("note: macOS/Linux paths are UNVERIFIED (only Windows was exercised); override with --desktop-dir")
        print({0: "READY", 1: "FAIL", 3: "ACTION_NEEDED"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
