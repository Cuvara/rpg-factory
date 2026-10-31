"""Locate the bash that runs the plugin's shell scripts.

On Windows a bare "bash" passed to CreateProcess resolves to C:\\Windows\\System32\\bash.exe (the WSL launcher)
before PATH is searched, so scripts would run inside WSL (or fail when no distribution is installed). Prefer the
Git for Windows bash next to the git on PATH, then the default install, then bash on PATH.
"""
import os
import shutil
import subprocess


def bash_candidates():
    if os.name != "nt":
        return [shutil.which("bash")]
    candidates = [r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")]
    git = shutil.which("git")
    if git:
        try:
            ep = subprocess.run([git, "--exec-path"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
            if ep.returncode == 0:
                candidates.insert(0, os.path.abspath(os.path.join(ep.stdout.strip(), "..", "..", "bin", "bash.exe")))
        except (OSError, subprocess.SubprocessError):
            pass
    return candidates


def find_bash():
    """Absolute path of the bash to use, or None."""
    return next((os.path.abspath(x) for x in bash_candidates() if x and os.path.isfile(x)), None)
