from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / "server.pid"


def main() -> None:
    if not PID_FILE.exists():
        print("No server.pid found.")
        return
    pid_text = PID_FILE.read_text(encoding="utf-8").strip()
    if not pid_text:
        PID_FILE.unlink(missing_ok=True)
        print("No PID found.")
        return
    pid = int(pid_text)
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
    else:
        os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print("Frontend stopped.")


if __name__ == "__main__":
    main()
