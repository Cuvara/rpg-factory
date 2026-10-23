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

if runner.os.name == "nt":
    with patch.object(runner.shutil, "which", return_value="bash.exe"), \
         patch.object(runner.subprocess, "Popen", return_value=FakeProcess()), \
         patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "denied")):
        code, output, timed_out, cleanup = runner.run_check("sleep", ".", {}, 1)
else:
    with patch.object(runner.shutil, "which", return_value="bash"), \
         patch.object(runner.subprocess, "Popen", return_value=FakeProcess()), \
         patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")), \
         patch.object(runner.os, "killpg", side_effect=PermissionError("denied")):
        code, output, timed_out, cleanup = runner.run_check("sleep", ".", {}, 1)

assert code == 124 and timed_out
assert "failed" in cleanup and "cleanup=failed" in output

# Exercise Windows path selection and tree-cleanup branches even when this fixture runs on POSIX.
import ntpath
with patch.object(runner.os, "name", "nt"), \
     patch.object(runner.os, "path", ntpath), \
     patch.object(runner.shutil, "which", side_effect=lambda name: None if name == "cygpath" else "bash.exe"):
    assert runner.bash_env_path(r"C:\Work Space\Unity", r"C:\Git\bin\bash.exe") == "C:/Work Space/Unity"

with patch.object(runner.os, "name", "nt"), \
     patch.object(runner.os.path, "realpath", return_value=r"c:\windows\system32\bash.exe"), \
     patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "/mnt/c/Work Space/Unity", "")) as convert:
    assert runner.bash_env_path(r"C:\Work Space\Unity", "bash.exe") == "/mnt/c/Work Space/Unity"
    assert convert.call_args.args[0][0] == "bash.exe"

with patch.object(runner.os, "name", "nt"), \
     patch.object(runner.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True), \
     patch.object(runner.shutil, "which", return_value="bash.exe"), \
     patch.object(runner.subprocess, "Popen", return_value=FakeProcess()) as spawn, \
     patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "terminated", "")) as kill:
    code, output, timed_out, cleanup = runner.run_check("sleep", ".", {}, 1)
    assert spawn.call_args.kwargs["creationflags"] == 512
    assert kill.call_args.args[0] == ["taskkill", "/T", "/F", "/PID", "4242"]
    assert code == 124 and timed_out and cleanup == "success"
