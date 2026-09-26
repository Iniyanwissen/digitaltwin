"""Start twin-server and the Vite dev server together, restarting the server on changes.

Reload is done here instead of `uvicorn --reload`, whose reloader on Windows can fail to stop
the old process (it keeps serving and the new code never loads). On any .py/.yaml change under
the watched folders the server process tree is stopped hard and started again. If the server
crashes (e.g. a syntax error while editing) it is restarted on the next change. Ctrl+C stops all.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from watchfiles import watch

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
IS_WINDOWS = os.name == "nt"
NPM = shutil.which("npm.cmd" if IS_WINDOWS else "npm") or "npm"
WATCH_DIRS = [
    ROOT / "services" / "twin-server" / "twin_server",
    ROOT / "packages" / "domain" / "workplace_domain",
    ROOT / "config",
]
WATCH_SUFFIXES = {".py", ".yaml", ".yml", ".mako"}
SERVER_CMD = [sys.executable, "-m", "twin_server", "serve"]


def kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    proc.wait()


def spawn(cmd: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    kwargs: dict[str, object] = {"cwd": cwd}
    if not IS_WINDOWS:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]


def relevant(changes: set[tuple[object, str]]) -> list[str]:
    paths = [p for _, p in changes if "__pycache__" not in p]
    return [p for p in paths if Path(p).suffix in WATCH_SUFFIXES]


def main() -> int:
    if not (FRONTEND / "node_modules").is_dir():
        print("Installing frontend dependencies (first run)...")
        subprocess.run([NPM, "install"], cwd=FRONTEND, check=True)

    server = spawn(SERVER_CMD, ROOT)
    web = spawn([NPM, "run", "dev"], FRONTEND)
    print("\n  UI:  http://localhost:5173\n  API: http://localhost:8000/docs\n")

    exit_code = 0
    server_down_reported = False
    try:
        # Yields changed files, or an empty set every 0.5 s so we can check the processes.
        for changes in watch(*WATCH_DIRS, rust_timeout=500, yield_on_timeout=True):
            if web.poll() is not None:
                print(f"\nfrontend exited with code {web.returncode}; stopping.")
                exit_code = web.returncode or 1
                break
            if server.poll() is not None and not server_down_reported:
                print(f"\ntwin-server exited with code {server.returncode}; "
                      "fix the error and save a file to restart it.")  # fmt: skip
                server_down_reported = True
            changed = relevant(changes)
            if changed:
                print(f"\nChange detected ({Path(changed[0]).name}); restarting twin-server...")
                kill_tree(server)
                server = spawn(SERVER_CMD, ROOT)
                server_down_reported = False
    except KeyboardInterrupt:
        pass
    finally:
        kill_tree(server)
        kill_tree(web)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
