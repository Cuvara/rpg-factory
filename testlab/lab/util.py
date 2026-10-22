"""Small helpers: clocks, JSON files, HTTP, WSL commands, path conversion, process control.

Everything here runs on the Windows host Python (the players are Windows processes). WSL is
reached only through `wsl.exe -d <distro> -- bash -lc <cmd>`, with MSYS path conversion
disabled, so the same code works from Git Bash, PowerShell or cmd.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path, PureWindowsPath

IS_WINDOWS = os.name == "nt"


def mono() -> float:
    """Monotonic seconds. Every duration the lab measures uses this, never wall-clock deltas:
    this host's wall clock runs 10-17% fast (rpg-mmo-server#153)."""
    return time.monotonic()


def unix_ms() -> int:
    """Wall-clock epoch milliseconds; used ONLY to hand clients a shared start instant."""
    return int(time.time() * 1000)


def utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def new_run_id(scenario_id: str) -> str:
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"{utc_stamp()}-{scenario_id}-{suffix}"


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        # PermissionError: on Windows a file being replaced by its writer at this instant.
        return default


def write_json(path: Path, data) -> None:
    """Atomic write (temp + replace), so a reader polling the file never sees half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, sort_keys=False)
        fh.write("\n")
    # On Windows a replace fails with "Access is denied" while another process (a player
    # polling control.json) has the target open; that is momentary, so retry briefly
    # instead of failing the run (seen in S03 run 20261022T095452Z-S03-1rw4).
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.02)


def iter_ndjson(path: Path):
    """Rows of an ndjson file, one at a time. A cut-short last line (a killed writer) is skipped."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # The last line of a file a killed client was writing may be cut short.
                    continue
    except FileNotFoundError:
        return


def read_ndjson(path: Path) -> list:
    return list(iter_ndjson(path))


class LazyNdjson:
    """The rows of an ndjson file, read again on every iteration and never held in memory: a 1 h soak's
    samples.ndjson is gigabytes as Python objects (T41). Behaves like a read-only sequence for
    iteration, truthiness, len() and reversed()."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def __iter__(self):
        return iter_ndjson(self.path)

    def __bool__(self) -> bool:
        return next(iter(self), None) is not None

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __reversed__(self):
        return reversed(list(self))

    def __repr__(self) -> str:
        return f"LazyNdjson({self.path})"


class Distribution:
    """Values for percentile/max/len without keeping all of them: exact (every value, as util.percentile
    on a list) up to `exact_cap` values, then a histogram of `resolution` bins. A histogram percentile
    is the bin's lower edge, within `resolution` of the exact value; max stays exact."""

    def __init__(self, exact_cap: int = 1_000_000, resolution: float = 1e-6):
        from array import array
        self._exact = array("d")
        self._bins: dict | None = None
        self._cap, self._res = exact_cap, resolution
        self._n, self._max = 0, None

    def add(self, v: float) -> None:
        self._n += 1
        if self._max is None or v > self._max:
            self._max = v
        if self._bins is None:
            self._exact.append(v)
            if len(self._exact) > self._cap:
                self._bins = {}
                for x in self._exact:
                    self._bin(x)
                from array import array
                self._exact = array("d")
        else:
            self._bin(v)

    def _bin(self, v: float) -> None:
        k = math.floor(v / self._res)
        self._bins[k] = self._bins.get(k, 0) + 1

    def __len__(self) -> int:
        return self._n

    def __bool__(self) -> bool:
        return self._n > 0

    def max(self):
        return self._max

    def percentile(self, p: float):
        if self._n == 0:
            return None
        if self._bins is None:
            return percentile(self._exact, p)
        rank = max(1, min(self._n, int(-(-p / 100.0 * self._n // 1))))
        seen = 0
        for k in sorted(self._bins):
            seen += self._bins[k]
            if seen >= rank:
                return min(k * self._res, self._max)
        return self._max


def http_get(url: str, timeout: float = 3.0) -> tuple[int, bytes]:
    """(status, body); status 0 when nothing answered."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b""
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, b""


def http_post_json(url: str, payload: dict, timeout: float = 5.0) -> tuple[int, dict | None]:
    """POST a JSON body; (status, parsed JSON body or None). Status 0 when nothing answered."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, (exc.read() if exc.fp else b"")
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, None
    try:
        return status, json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return status, None


def http_json(url: str, timeout: float = 3.0):
    status, body = http_get(url, timeout)
    if status != 200:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def to_wsl_path(path: Path | str) -> str:
    """C:\\a\\b -> /mnt/c/a/b. Paths already in POSIX form are returned unchanged."""
    s = str(path)
    if s.startswith("/"):
        return s
    p = PureWindowsPath(s)
    drive = p.drive.rstrip(":").lower()
    rest = "/".join(p.parts[1:])
    return f"/mnt/{drive}/{rest}"


def to_windows_path(path: Path | str) -> str:
    """/c/a/b or /mnt/c/a/b -> C:\\a\\b (Git Bash and WSL spellings); Windows paths unchanged."""
    s = str(path)
    m = re.match(r"^/(?:mnt/)?([a-zA-Z])/(.*)$", s)
    if m:
        return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")
    return str(PureWindowsPath(s))


def wsl(distro: str, command: str, timeout: float = 600, check: bool = False) -> subprocess.CompletedProcess:
    """Run a bash command inside WSL. MSYS_NO_PATHCONV stops Git Bash rewriting /mnt/... args."""
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    proc = subprocess.run(
        # --exec: no default-shell pass over the arguments. With `--` wsl.exe joins them into a
        # command line for the login shell, which expands $VAR before bash -c ever sees it.
        ["wsl.exe", "-d", distro, "--exec", "bash", "-c", command],
        capture_output=True, timeout=timeout, env=env,
    )
    out = proc.stdout.decode("utf-8", "replace").replace("\r", "")
    err = proc.stderr.decode("utf-8", "replace").replace("\r", "")
    result = subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    if check and proc.returncode != 0:
        raise RuntimeError(f"wsl command failed ({proc.returncode}): {command}\n{out}\n{err}")
    return result


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def process_image(pid: int) -> str | None:
    """Executable path of a live process, or None. Used to refuse killing a reused PID."""
    if not IS_WINDOWS:
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None
    cmd = ["powershell", "-NoProfile", "-Command",
           f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Path"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    return out or None


def kill_tree(pid: int) -> bool:
    if not process_alive(pid):
        return False
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    return True


def percentile(values, p: float):
    """Nearest-rank percentile; None for no values."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    rank = max(1, min(len(vals), int(-(-p / 100.0 * len(vals) // 1))))
    return vals[rank - 1]


def eprint(*args) -> None:
    print(*args, file=sys.stderr, flush=True)
