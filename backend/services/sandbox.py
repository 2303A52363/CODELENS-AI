"""Isolated execution. User code NEVER runs inside the Flask process."""
import os, sys, subprocess, tempfile, shutil, time, signal
import config
try:
    import resource
except ImportError:  # Windows
    resource = None

RUNNER = r'''
import sys, os
CWD = os.path.realpath(os.getcwd())
READ_OK = {os.path.realpath(p) for p in (sys.prefix, sys.base_prefix, sys.exec_prefix)}
BLOCKED = {"socket.connect","socket.bind","socket.getaddrinfo","subprocess.Popen","os.system","os.fork",
           "os.forkpty","os.posix_spawn","os.spawn","os.remove","os.rmdir","os.rename","os.chmod","ctypes.dlopen"}
src = open("code.py", encoding="utf-8").read()
def hook(ev, args):
    if ev in BLOCKED or ev.startswith("os.exec"):
        raise PermissionError("Blocked for safety: " + ev)
    if ev == "open" and not isinstance(args[0], int):
        p = os.path.realpath(os.fsdecode(args[0])); write = any(c in str(args[1] or "r") for c in "wax+")
        if write and not p.startswith(CWD): raise PermissionError("Writing outside the sandbox is blocked")
        if not write and not (p.startswith(CWD) or any(p.startswith(r) for r in READ_OK)):
            raise PermissionError("Reading outside the sandbox is blocked")
sys.addaudithook(hook)
try:
    exec(compile(src, "<student>", "exec"), {"__name__": "__main__"})
except SystemExit:
    raise
except BaseException:
    import traceback
    t, v, tb = sys.exc_info()
    traceback.print_exception(t, v, tb.tb_next)
    sys.exit(1)
'''

def _limits(timeout, mem_mb):
    def apply():
        if not resource: return
        resource.setrlimit(resource.RLIMIT_CPU, (int(timeout) + 1, int(timeout) + 1))
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    return apply

def run_python(code, stdin="", timeout=None, mem_mb=None):
    timeout = timeout or config.EXEC_TIMEOUT
    mem_mb = mem_mb or config.EXEC_MEMORY_MB
    d = tempfile.mkdtemp(prefix="sbx_")
    start = time.perf_counter()
    try:
        open(os.path.join(d, "code.py"), "w", encoding="utf-8").write(code)
        open(os.path.join(d, "runner.py"), "w").write(RUNNER)
        if config.SANDBOX_MODE == "docker":
            cmd = ["docker", "run", "--rm", "-i", "--network", "none", "--memory", f"{mem_mb}m", "--cpus", "0.5",
                   "--pids-limit", "64", "--read-only", "--tmpfs", "/tmp", "-v", f"{d}:/work:ro", "-w", "/work",
                   "python:3.12-slim", "python", "-I", "-B", "runner.py"]
            kw = {}
        else:
            cmd = [sys.executable, "-I", "-B", "runner.py"]
            kw = {"cwd": d, "env": {"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"}}
            if os.name == "posix":
                kw.update(preexec_fn=_limits(timeout, mem_mb), start_new_session=True)
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)
        except FileNotFoundError:
            return {"stdout": "", "stderr": "Sandbox unavailable (is Docker installed?)", "exit_code": -1,
                    "timed_out": False, "duration_ms": 0, "truncated": False, "sandbox_error": True}
        timed_out = False
        try:
            out, err = p.communicate(stdin or "", timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(p.pid, signal.SIGKILL)
            except Exception: p.kill()
            out, err = p.communicate()
        trunc = len(out) > 20000 or len(err) > 20000
        return {"stdout": out[:20000], "stderr": err[:20000], "exit_code": p.returncode, "timed_out": timed_out,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1), "truncated": trunc}
    finally:
        shutil.rmtree(d, ignore_errors=True)

# Add new languages here: name -> runner(code, stdin) -> result dict
RUNNERS = {"python": run_python}

def run(code, stdin="", language="python"):
    if language not in RUNNERS:
        raise ValueError(f"Language '{language}' is not supported yet. Supported: {', '.join(RUNNERS)}")
    return RUNNERS[language](code, stdin)
