"""Start twin-server (auto-reload) and the Vite dev server together. Ctrl+C stops both."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
IS_WINDOWS = os.name == "nt"
NPM = shutil.which("npm.cmd" if IS_WINDOWS else "npm") or "npm"


def kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        os.killpg(proc.pid, signal.SIGTERM)


def spawn(cmd: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    kwargs: dict[str, object] = {"cwd": cwd}
    if not IS_WINDOWS:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]


def main() -> int:
    if not (FRONTEND / "node_modules").is_dir():
        print("Installing frontend dependencies (first run)...")
        subprocess.run([NPM, "install"], cwd=FRONTEND, check=True)

    server = spawn([sys.executable, "-m", "twin_server", "serve", "--reload"], ROOT)
    web = spawn([NPM, "run", "dev"], FRONTEND)
    procs = {"twin-server": server, "frontend": web}
    print("\n  UI:  http://localhost:5173\n  API: http://localhost:8000/docs\n")

    exit_code = 0
    try:
        while True:
            for name, proc in procs.items():
                code = proc.poll()
                if code is not None:
                    print(f"\n{name} exited with code {code}; stopping the rest.")
                    exit_code = code or 1
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in procs.values():
            kill_tree(proc)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
