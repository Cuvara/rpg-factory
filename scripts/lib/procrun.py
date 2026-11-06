"""Check process execution, timeout cleanup and checkout pollution fingerprints.

The caller selects the bash runtime; process cleanup is owned here on both
Windows (Job Objects, with a taskkill fallback) and POSIX (process groups).
"""
import os
import signal
import stat
import subprocess
import time

# Cleanup budgets: how long the runner may spend between noticing a timeout and
# verifying that the check's process tree is gone. A timeout record reports the
# measured latency against this grace (POLL_SLACK_S covers the last probe and
# poll sleep past a deadline), so tests bound the runner's own work, not the
# machine's load.
POSIX_LIST_S, POSIX_REAP_S, VERIFY_S, TASKKILL_S, POLL_SLACK_S = 3, 1, 3, 5, .5
POSIX_GRACE_S = POSIX_LIST_S + POSIX_REAP_S + VERIFY_S + POLL_SLACK_S
WINDOWS_JOB_GRACE_S = VERIFY_S + POLL_SLACK_S
WINDOWS_FALLBACK_GRACE_S = TASKKILL_S + VERIFY_S + POLL_SLACK_S


def _timing_start(timing, limit):
    if timing is not None:
        timing.clear()
        timing.update(limit_s=limit, started=time.monotonic())


def _timing_timeout(timing, grace):
    if timing is not None:
        timing.update(timed_out_after_s=round(time.monotonic() - timing["started"], 3), cleanup_grace_s=grace,
                      killed_after_s=None, verified=False)


def _timing_killed(timing):
    if timing is not None:
        timing.update(killed_after_s=round(time.monotonic() - timing["started"], 3), verified=True)


def timeout_record(timing):
    """JSON shape of a timeout: the limit, when it fired, when the tree was verified gone, the runner's grace."""
    return {k: timing.get(k) for k in ("limit_s", "timed_out_after_s", "killed_after_s", "cleanup_grace_s", "verified")}


def git(d, *args):
    try:
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def worktree_state(d):
    """Fingerprint changed/untracked paths, including edits to already-dirty files."""
    entries = git(d, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=all").split("\0")
    paths = set()
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) >= 4:
            status, path = entry[:2], entry[3:]
            paths.add(path)
            if "R" in status or "C" in status:
                if i < len(entries) and entries[i]:
                    paths.add(entries[i])  # the source path follows the destination in porcelain -z output
                i += 1
    state = {}
    for path in paths:
        full = os.path.join(d, path)
        try:
            st = os.stat(full, follow_symlinks=False)
            target = ""
            if stat.S_ISLNK(st.st_mode):
                target = ":target=" + os.readlink(full)
            state[path] = f"size={st.st_size}:mtime_ns={st.st_mtime_ns}:mode={st.st_mode}{target}"
        except OSError as e:
            state[path] = f"unreadable:{e}"
    return state


def bash_env_path(path, bash, flavor=None):
    """Convert native workspace paths to the selected bash's path syntax; fail closed."""
    if os.name != "nt":
        return os.path.realpath(path)
    if flavor == "wsl":
        conv = subprocess.run([bash, "-c", "wslpath -u \"$1\"", "runner", path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return conv.stdout.strip() if conv.returncode == 0 and conv.stdout.strip().startswith("/") else None
    if flavor != "gitbash":
        return None
    # Git Bash accepts the ENV CONTRACT's Windows drive form directly. This
    # avoids depending on cygpath being visible to Windows Python's PATH.
    absolute = os.path.abspath(path)
    drive, tail = os.path.splitdrive(absolute)
    if not drive or not tail.startswith(("\\", "/")):
        return None
    return drive.replace("\\", "/") + tail.replace("\\", "/")


def wsl_environment(env):
    """Bridge already-translated contract values into WSL without path conversion."""
    names = ("RPG_FACTORY_WORKSPACE", "RPG_FACTORY_REPO_DIR", "RPG_FACTORY_REPO_KEY", "RPG_FACTORY_HEAD", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")
    entries = [x for x in env.get("WSLENV", "").split(":") if x]
    env["WSLENV"] = ":".join(dict.fromkeys(entries + list(names)))
    return env


def _verify_windows_pids(pids, is_alive, grace=VERIFY_S):
    deadline = time.monotonic() + grace
    remaining = set(pids)
    while time.monotonic() < deadline:
        # The Windows probe is tri-state: only a positively verified gone PID
        # is clean. Preserve bool support for callers/tests using the old shape.
        remaining = set()
        for pid in pids:
            state = is_alive(pid)
            still_present = state != "gone" if isinstance(state, str) else bool(state)
            if still_present:
                remaining.add(pid)
        if not remaining:
            return True, set()
        time.sleep(.05)
    return False, remaining


def _windows_pid_state(kernel, pid, ctypes, wintypes):
    handle = kernel.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return "gone" if ctypes.get_last_error() == 87 else "unknown"
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "unknown"
        return "alive" if code.value == 259 else "gone"
    finally:
        kernel.CloseHandle(handle)


def _windows_fallback_cleanup(exit_code, pids, is_alive, fallback="", verify_pids=None):
    verified, remaining = (verify_pids or _verify_windows_pids)(pids, is_alive)
    status = "success" if exit_code == 0 and verified else f"failed (taskkill exit {exit_code}; remaining pids={sorted(remaining)})"
    return f"{status}; {fallback}" if fallback else status


def _run_windows_check(bash, command, kwargs, timeout, timing=None):
    """Own a suspended check in a kill-on-close job before it can spawn children."""
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
    class EXT_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
    class BASIC_ACCOUNT(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong), ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong), ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD), ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

    def alive(pid):
        return _windows_pid_state(kernel, pid, ctypes, wintypes)

    def descendants(root):
        # Toolhelp snapshot, then walk parent links without relying on wmic.
        class ENTRY(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]; k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]; k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
        snap = k32.CreateToolhelp32Snapshot(2, 0)
        if snap == wintypes.HANDLE(-1).value: return {int(root)}
        try:
            e = ENTRY(); e.dwSize = ctypes.sizeof(e); rows = []
            ok = k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                rows.append((int(e.th32ProcessID), int(e.th32ParentProcessID)))
                e.dwSize = ctypes.sizeof(e); ok = k32.Process32NextW(snap, ctypes.byref(e))
            found = {int(root)}
            changed = True
            while changed:
                before = len(found); found.update(pid for pid, parent in rows if parent in found); changed = len(found) != before
            return found
        finally: kernel.CloseHandle(snap)
    job = kernel.CreateJobObjectW(None, None)
    p = None
    fallback = None
    if job:
        info = EXT_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
            p = subprocess.Popen([bash, "-c", command], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004, **kwargs)  # CREATE_SUSPENDED
            if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(p._handle))):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
            status = ctypes.WinDLL("ntdll").NtResumeProcess(wintypes.HANDLE(int(p._handle)))
            if status != 0:
                raise OSError(f"NtResumeProcess status {status}")
        except Exception as e:
            fallback = f"job creation/assignment failed ({e}); taskkill fallback"
            if p and p.poll() is None:
                if job:
                    kernel.TerminateJobObject(job, 1)
                else:
                    p.kill()
                try: p.wait(timeout=2)
                except subprocess.SubprocessError: pass
            if p:
                # The assigned process may still be suspended: terminate it, then reap/close it.
                if p.poll() is None:
                    try: p.kill(); p.wait(timeout=2)
                    except (OSError, subprocess.SubprocessError): pass
                try: p._handle.Close()
                except Exception: pass
            kernel.CloseHandle(job)
            job = None
            p = None
    else:
        fallback = f"job creation failed ({ctypes.get_last_error()}); taskkill fallback"
    if p is None:
        p = subprocess.Popen([bash, "-c", command], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, **kwargs)
    _timing_start(timing, timeout)
    try:
        out, _ = p.communicate(timeout=timeout)
        if job:
            kernel.CloseHandle(job)
        try: p._handle.Close()
        except Exception: pass
        return p.returncode, out or "", False, "not needed"
    except subprocess.TimeoutExpired:
        cleanup = "failed"
        _timing_timeout(timing, WINDOWS_JOB_GRACE_S if job else WINDOWS_FALLBACK_GRACE_S)
        if job:
            kernel.TerminateJobObject(job, 1)
            account = BASIC_ACCOUNT()
            deadline = time.monotonic() + VERIFY_S
            verified = False
            while time.monotonic() < deadline:
                if kernel.QueryInformationJobObject(job, 1, ctypes.byref(account), ctypes.sizeof(account), None) and account.ActiveProcesses == 0:
                    verified = True
                    _timing_killed(timing)
                    break
                time.sleep(.05)
            cleanup = "success (job ActiveProcesses=0)" if verified else f"failed (job ActiveProcesses={account.ActiveProcesses})"
        else:
            try:
                tree = descendants(p.pid)
                killer = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TASKKILL_S)
                cleanup = _windows_fallback_cleanup(killer.returncode, tree, alive, fallback)
                if cleanup.startswith("success"):
                    _timing_killed(timing)
            except (OSError, subprocess.SubprocessError) as e:
                cleanup = f"failed ({e}); {fallback}"
        try:
            out, _ = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            out = ""
            cleanup += "; process pipes did not close within 3 s"
        if job:
            kernel.CloseHandle(job)
        try: p._handle.Close()
        except Exception: pass
        return 124, f"TIMEOUT after {timeout} s; pids={[p.pid]}; cleanup={cleanup}\n{out or ''}", True, cleanup


def run_check(command, cwd, env, timeout, bash_selection, timing=None):
    """Run bash in an isolated process group and clean up its entire child tree on timeout.

    A `timing` dict, when given, is filled with the runner's own measurements
    (see timeout_record). They exclude interpreter start-up and other work
    outside the check, which a caller's wall clock includes."""
    bash, flavor = bash_selection
    if not bash:
        return 127, "could not start: bash not found", False, "not started"
    if flavor == "wsl":
        required = ("RPG_FACTORY_WORKSPACE", "RPG_FACTORY_REPO_DIR", "RPG_FACTORY_REPO_KEY", "RPG_FACTORY_HEAD", "PYTHONDONTWRITEBYTECODE")
        checks = " ".join(f'test -n "${{{name}}}" || {{ echo "BLOCKED: WSL environment missing {name}"; exit 97; }};' for name in required)
        command = checks + " " + command
    kwargs = dict(cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                  encoding="utf-8", errors="replace", env=env)
    if os.name == "nt":
        return _run_windows_check(bash, command, kwargs, timeout, timing)
    else:
        p = subprocess.Popen([bash, "-c", command], start_new_session=True, **kwargs)
    _timing_start(timing, timeout)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or "", False, "not needed"
    except subprocess.TimeoutExpired:
        pids = [p.pid]
        cleanup = "success"
        _timing_timeout(timing, POSIX_GRACE_S)
        try:
            if os.name == "nt":
                killer = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                cleanup = "success" if killer.returncode == 0 else f"failed (taskkill exit {killer.returncode}: {killer.stderr.strip() or killer.stdout.strip()})"
            else:
                try:  # diagnostic listing only: a missing or slow ps must never skip the kill below
                    listing = subprocess.run(["ps", "-eo", "pid=,pgid="], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=POSIX_LIST_S)
                    if listing.returncode == 0:
                        pids = sorted({int(pid) for pid, pgid in (line.split() for line in listing.stdout.splitlines()) if int(pgid) == p.pid})
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # group already gone; the probe below records it as killed
                try:
                    p.wait(timeout=POSIX_REAP_S)  # reap the direct child before probing group membership
                except subprocess.TimeoutExpired:
                    pass
                deadline = time.monotonic() + VERIFY_S
                while time.monotonic() < deadline:
                    try:
                        os.killpg(p.pid, 0)
                    except ProcessLookupError:
                        cleanup = "success"
                        _timing_killed(timing)
                        break
                    except PermissionError:
                        cleanup = f"failed (pgid {p.pid} still has members)"
                        break
                    time.sleep(.05)
                else:
                    cleanup = f"failed (pgid {p.pid} still has members)"
        except (OSError, subprocess.SubprocessError) as e:
            cleanup = f"failed ({e})"
        try:
            out, _ = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            out = ""
            cleanup += "; pipes/process did not close within 3 s"
        return 124, f"TIMEOUT after {timeout} s; pids={pids}; cleanup={cleanup}\n{out or ''}", True, cleanup
