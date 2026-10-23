import importlib.util
import subprocess
import sys
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

with patch.object(runner.os, "name", "posix"), \
     patch.object(runner.shutil, "which", return_value="bash"), \
     patch.object(runner.subprocess, "Popen", return_value=FakeProcess()), \
     patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")), \
     patch.object(runner.signal, "SIGKILL", 9, create=True), \
     patch.object(runner.os, "killpg", side_effect=PermissionError("denied"), create=True):
    code, output, timed_out, cleanup = runner.run_check("sleep", ".", {}, 1)

assert code == 124 and timed_out
assert "failed" in cleanup and "cleanup=failed" in output

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
