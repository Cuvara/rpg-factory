#!/usr/bin/env python3
"""In-process runner for tests/assetgen.test.sh: one interpreter serves every `AG` call of a suite run.

On a Windows host a process start costs 0.5-1.5 s and the suite makes hundreds of `assetgen.py` calls, so the suite
starts this server once and its `AG` function hands each call over instead of spawning `python3 assetgen.py`. A call
keeps its contract: argv, working directory, the environment variables the cases set, stdout, stderr and the exit code;
`assetgen.main()` is the entry point `python3 assetgen.py` runs. The channel is plain files (a pipe or coprocess is not
visible to the subshells of `$(AG ...)` and `AG ... | jq`):
  DIR/c/ID.req   request, written first: NUL-terminated fields. 1: working directory; 2: the number N of environment
                 fields; then N fields "S<NAME>=<value>" (set) or "U<NAME>" (unset); then the argv, one field per argument
  DIR/go/ID      marker, created after the request is complete; the server consumes it
  DIR/c/ID.out, ID.err   the captured streams, then DIR/c/ID.rc (written last, atomically): the exit code
  DIR/ready      created once assetgen is imported; DIR/quit asks the server to stop (it also stops when DIR is gone
                 when the suite process OWNER is gone (a killed suite never runs its exit trap; DIR is removed then), or
                 when it has had no request for IDLE seconds)
Usage: agserver.py ASSETGEN-DIR DIR [OWNER-PID]
OWNER-PID is the suite shell's pid in the form this interpreter can look up: the POSIX pid on Linux, the Windows pid on
Windows (Git Bash passes /proc/$$/winpid). Without it, or when the lookup is not possible, the owner counts as alive.
"""
import contextlib
import io
import os
import shutil
import sys
import time
import traceback

IDLE = 1800
assetgen_dir, base = sys.argv[1:3]
owner = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 0
sys.dont_write_bytecode = True
sys.path.insert(0, assetgen_dir)
import assetgen  # noqa: E402

HOME = os.getcwd()  # the working directory between calls: never a directory the suite deletes
ENCODING = sys.stdout.encoding or "utf-8"
calls, goes = os.path.join(base, "c"), os.path.join(base, "go")


def owner_alive():
    """False only when the owner process is certainly gone. os.kill(pid, 0) is the POSIX existence probe; on Windows
    os.kill would terminate the process, so the handle is queried instead."""
    if owner <= 0:
        return True
    try:
        if os.name == "nt":
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = ctypes.c_void_p
            handle = kernel.OpenProcess(0x1000, False, owner)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return kernel.GetLastError() != 87  # ERROR_INVALID_PARAMETER: no such process
            code = ctypes.c_ulong()
            alive = not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)) or code.value == 259
            kernel.CloseHandle(ctypes.c_void_p(handle))
            return alive
        os.kill(owner, 0)
    except ProcessLookupError:
        return False
    except Exception:  # PermissionError (it exists) or a platform detail: no opinion means alive
        return True
    return True


def capture(errors="strict"):
    """A text stream with the newline translation and the encoding a Python stdout pipe has on this platform (stderr
    never fails on an unencodable character: it uses backslashreplace)."""
    return io.TextIOWrapper(io.BytesIO(), encoding=ENCODING, errors=errors)


def run(fields):
    cwd, count = fields[0], int(fields[1])
    for field in fields[2:2 + count]:
        if field[0] == "S":
            name, _, value = field[1:].partition("=")
            os.environ[name] = value
        else:
            os.environ.pop(field[1:], None)
    argv = fields[2 + count:]
    out, err = capture(), capture("backslashreplace")
    rc = 0
    try:
        os.chdir(cwd)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = assetgen.main(argv)
            except SystemExit as exc:
                code = exc.code
                if code is None:
                    rc = 0
                elif isinstance(code, int):
                    rc = code
                else:
                    print(code, file=sys.stderr)
                    rc = 1
            except Exception:  # an uncaught error of `python3 assetgen.py`: traceback on stderr, exit 1
                traceback.print_exc()
                rc = 1
    except OSError as exc:  # the working directory is gone
        print("agserver: %s" % exc, file=err)
        rc = 1
    finally:
        os.chdir(HOME)
    return rc, out, err


def serve(call_id):
    path = os.path.join(calls, call_id)
    try:
        with open(path + ".req", "rb") as f:
            fields = [x.decode("utf-8", "surrogateescape") for x in f.read().split(b"\0")[:-1]]
        rc, out, err = run(fields)
    except Exception:  # a malformed request: the caller sees a failed call, never a hang
        rc, out, err = 1, capture(), capture("backslashreplace")
        traceback.print_exc(file=err)
    for stream, ext in ((out, ".out"), (err, ".err")):
        stream.flush()
        with open(path + ext, "wb") as f:
            f.write(stream.buffer.getvalue())
    with open(path + ".rc.tmp", "w") as f:
        f.write("%d\n" % rc)
    os.replace(path + ".rc.tmp", path + ".rc")  # the marker the caller waits for: complete or absent


def main():
    open(os.path.join(base, "ready"), "w").close()
    last = checked = time.monotonic()
    while os.path.isdir(base) and not os.path.exists(os.path.join(base, "quit")):
        if time.monotonic() - checked > 2:
            checked = time.monotonic()
            if not owner_alive():
                shutil.rmtree(base, ignore_errors=True)
                break
        try:
            pending = sorted(os.listdir(goes))
        except OSError:
            break
        if not pending:
            if time.monotonic() - last > IDLE:
                break
            time.sleep(0.003)
            continue
        for call_id in pending:
            try:
                os.remove(os.path.join(goes, call_id))
            except OSError:
                continue
            serve(call_id)
        last = time.monotonic()


if __name__ == "__main__":
    main()
