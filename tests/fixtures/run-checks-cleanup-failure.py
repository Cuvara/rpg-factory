import importlib.util
import subprocess
import sys
import ctypes
from ctypes import wintypes
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("runner", sys.argv[1])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class FakeProcess:
    pid = 4242

    def __init__(self):
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if self.calls == 1:
            raise subprocess.TimeoutExpired("bash", timeout)
        return "", None

    def wait(self, timeout=None):
        return 0

with patch.object(runner.os, "name", "posix"), \
     patch.object(runner.shutil, "which", return_value="bash"), \
     patch.object(runner.subprocess, "Popen", return_value=FakeProcess()), \
     patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")), \
     patch.object(runner.signal, "SIGKILL", 9, create=True), \
     patch.object(runner.os, "killpg", side_effect=PermissionError("denied"), create=True):
    code, output, timed_out, cleanup = runner.run_check("sleep", ".", {}, 1)

assert code == 124 and timed_out, (code, timed_out, cleanup, output)
assert "failed" in cleanup and "cleanup=failed" in output, (cleanup, output)

# A successful killpg call is not proof that every group member exited.
def group_member(pgid, sig):
    if sig == 0:
        raise PermissionError("member remains")
with patch.object(runner.os, "name", "posix"), \
     patch.object(runner.shutil, "which", return_value="bash"), \
     patch.object(runner.subprocess, "Popen", return_value=FakeProcess()), \
     patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")), \
     patch.object(runner.signal, "SIGKILL", 9, create=True), \
     patch.object(runner.os, "killpg", side_effect=group_member, create=True):
    code, output, timed_out, cleanup = runner.run_check("sleep", ".", {}, 1)
assert code == 124 and timed_out and "failed" in cleanup and "cleanup=failed" in output

# Even taskkill exit 0 cannot verify a still-live Windows child.
with patch.object(runner, "_verify_windows_pids", return_value=(False, {4242})):
    cleanup = runner._windows_fallback_cleanup(0, {4242}, lambda pid: True, "simulated fallback")
assert cleanup.startswith("failed") and "remaining pids=[4242]" in cleanup

# Access denied is unknown, not proof that a captured child has exited.
class AccessDeniedKernel:
    def OpenProcess(self, access, inherit, pid):
        return 0

with patch.object(ctypes, "get_last_error", return_value=5):
    state = runner._windows_pid_state(AccessDeniedKernel(), 4242, ctypes, wintypes)
assert state == "unknown", state
cleanup = runner._windows_fallback_cleanup(0, {4242}, lambda pid: state, "simulated fallback")
assert cleanup.startswith("failed") and "remaining pids=[4242]" in cleanup, cleanup

class ExitedKernel:
    def OpenProcess(self, access, inherit, pid):
        return 1
    def GetExitCodeProcess(self, handle, code):
        ctypes.cast(code, ctypes.POINTER(wintypes.DWORD)).contents.value = 0
        return 1
    def CloseHandle(self, handle):
        return 1
assert runner._windows_pid_state(ExitedKernel(), 4242, ctypes, wintypes) == "gone"

class ActiveKernel(ExitedKernel):
    def GetExitCodeProcess(self, handle, code):
        ctypes.cast(code, ctypes.POINTER(wintypes.DWORD)).contents.value = 259
        return 1
assert runner._windows_pid_state(ActiveKernel(), 4242, ctypes, wintypes) == "alive"

class QueryFailureKernel(ExitedKernel):
    def GetExitCodeProcess(self, handle, code):
        return 0
assert runner._windows_pid_state(QueryFailureKernel(), 4242, ctypes, wintypes) == "unknown"

with patch.object(ctypes, "get_last_error", return_value=87):
    assert runner._windows_pid_state(AccessDeniedKernel(), 4242, ctypes, wintypes) == "gone"

# Exercise Windows path selection and tree-cleanup branches even when this fixture runs on POSIX.
import ntpath
with patch.object(runner.os, "name", "nt"), \
     patch.object(runner.os, "path", ntpath), \
     patch.object(runner.shutil, "which", side_effect=lambda name: None if name == "cygpath" else "bash.exe"):
    assert runner.bash_env_path(r"C:\Work Space\Unity", r"C:\Git\bin\bash.exe", "gitbash") == "C:/Work Space/Unity"

with patch.object(runner.os, "name", "nt"), \
     patch.object(runner.os.path, "realpath", return_value=r"c:\windows\system32\bash.exe"), \
     patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "/mnt/c/Work Space/Unity", "")) as convert:
    assert runner.bash_env_path(r"C:\Work Space\Unity", "bash.exe", "wsl") == "/mnt/c/Work Space/Unity"
    assert convert.call_args.args[0][0] == "bash.exe"
