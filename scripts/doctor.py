"""Check the local environment: tools, ports and data directory."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = {8000: "twin-server", 8100: "mock-saas", 5173: "frontend"}
TOOLS = {
    "git": ["git", "--version"],
    "uv": ["uv", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm.cmd" if os.name == "nt" else "npm", "--version"],
}


def tool_version(cmd: list[str]) -> str | None:
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    result = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, check=False)
    return result.stdout.strip() or None


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    ok = True
    print(f"python  {sys.version.split()[0]}")
    for name, cmd in TOOLS.items():
        version = tool_version(cmd)
        ok &= version is not None
        print(f"{name:<7} {version or 'MISSING'}")

    node = tool_version(TOOLS["node"])
    if node and int(node.lstrip("v").split(".")[0]) < 24:
        print("        node 24 LTS or newer is expected")
        ok = False

    for port, owner in PORTS.items():
        state = "free" if port_free(port) else "IN USE"
        print(f"port {port} ({owner}): {state}")

    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    probe = data / ".write-test"
    try:
        probe.write_text("ok")
        probe.unlink()
        print(f"data dir {data}: writable")
    except OSError as exc:
        print(f"data dir {data}: NOT WRITABLE ({exc})")
        ok = False

    print("\nAll good." if ok else "\nSome checks failed.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
