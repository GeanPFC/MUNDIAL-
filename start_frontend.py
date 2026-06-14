from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
PID_FILE = ROOT / "server.pid"
OUT_LOG = ROOT / "server.out.log"
ERR_LOG = ROOT / "server.err.log"


def is_listening(host: str = HOST, port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> None:
    if is_listening():
        print(f"Frontend already running: http://{HOST}:{PORT}")
        return

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )

    with OUT_LOG.open("ab") as stdout, ERR_LOG.open("ab") as stderr:
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "web_app.py",
                "--host",
                HOST,
                "--port",
                str(PORT),
            ],
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(3)
    if is_listening():
        print(f"Frontend ready: http://{HOST}:{PORT}")
        print(f"PID: {process.pid}")
        return

    print("Frontend failed to listen on port 8765.")
    if OUT_LOG.exists():
        print("STDOUT:")
        print(OUT_LOG.read_text(encoding="utf-8", errors="replace")[-2000:])
    if ERR_LOG.exists():
        print("STDERR:")
        print(ERR_LOG.read_text(encoding="utf-8", errors="replace")[-2000:])
    raise SystemExit(1)


if __name__ == "__main__":
    main()
