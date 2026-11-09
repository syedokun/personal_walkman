#!/usr/bin/env python3
"""
run.py
======

One-click launcher for personal_walkman.

On a fresh machine this script will:

1. Locate a usable Python 3 interpreter
2. Create a local virtualenv in ``.venv`` (if missing)
3. Install / refresh dependencies from ``requirements.txt``
4. Warn if ffmpeg is missing
5. Start the UI and open it in your browser

Usage::

    python3 run.py

Or double-click ``Personal Walkman.command`` on macOS /
``Personal Walkman.bat`` on Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MARKER = VENV_DIR / ".deps_installed"
HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}/"
MIN_VERSION = (3, 10)


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _venv_pip() -> list[str]:
    return [str(_venv_python()), "-m", "pip"]


def _print(msg: str) -> None:
    print(msg, flush=True)


def _version_of(python_bin: str) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [python_bin, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        major_s, minor_s = out.split(".", 1)
        return int(major_s), int(minor_s)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def _candidate_pythons() -> list[str]:
    names = [
        "python3.13",
        "python3.12",
        "python3.11",
        "python3.10",
        "python3",
        "python",
    ]
    found: list[str] = []
    seen: set[str] = set()

    def add(path: str | None) -> None:
        if not path:
            return
        resolved = str(Path(path).resolve()) if Path(path).exists() else path
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(path)

    add(sys.executable)
    for name in names:
        add(shutil.which(name))

    # Common install locations when PATH is minimal (double-click launchers).
    extras = [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/opt/anaconda3/bin/python3",
        "/opt/anaconda3/bin/python3.10",
        str(Path.home() / "anaconda3/bin/python3"),
        str(Path.home() / "miniconda3/bin/python3"),
    ]
    if os.name == "nt":
        extras.extend(
            [
                r"C:\Python313\python.exe",
                r"C:\Python312\python.exe",
                r"C:\Python311\python.exe",
                r"C:\Python310\python.exe",
            ]
        )
    for path in extras:
        if Path(path).exists():
            add(path)
    return found


def _resolve_bootstrap_python() -> str:
    """Return a Python 3.10+ binary to create the project venv with."""
    if sys.version_info >= MIN_VERSION:
        return sys.executable

    for candidate in _candidate_pythons():
        version = _version_of(candidate)
        if version and version >= MIN_VERSION:
            _print(
                f"Current interpreter is {sys.version.split()[0]}; "
                f"using {candidate} ({version[0]}.{version[1]}) instead."
            )
            return candidate

    _print(
        "Python 3.10+ is required.\n"
        "Install it from https://www.python.org/downloads/ then run this again."
    )
    sys.exit(1)


def _create_venv(bootstrap_python: str) -> None:
    if _venv_python().exists():
        version = _version_of(str(_venv_python()))
        if version and version >= MIN_VERSION:
            return
        _print("Existing .venv is too old; recreating it…")
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    _print("Creating local virtual environment (.venv)…")
    subprocess.check_call([bootstrap_python, "-m", "venv", str(VENV_DIR)])


def _deps_are_current() -> bool:
    if not MARKER.exists() or not REQUIREMENTS.exists():
        return False
    try:
        return MARKER.stat().st_mtime >= REQUIREMENTS.stat().st_mtime
    except OSError:
        return False


def _install_deps() -> None:
    if _deps_are_current():
        return

    _print("Installing dependencies (first run or requirements changed)…")
    pip = _venv_pip()
    subprocess.check_call(
        pip + ["install", "--upgrade", "pip"],
        cwd=str(ROOT),
    )
    subprocess.check_call(
        pip + ["install", "-r", str(REQUIREMENTS)],
        cwd=str(ROOT),
    )
    MARKER.write_text("ok\n", encoding="utf-8")
    _print("Dependencies ready.\n")


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg"):
        return
    _print(
        "Warning: ffmpeg was not found on PATH.\n"
        "  Audio conversion will fail until you install it.\n"
        "  macOS:  brew install ffmpeg\n"
        "  Linux:  sudo apt install ffmpeg\n"
        "  Windows: https://ffmpeg.org/download.html\n"
    )


def _wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=1) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.25)
    return False


def _launch_ui() -> int:
    python = _venv_python()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    _print(f"Starting personal_walkman UI on {URL}")
    proc = subprocess.Popen(
        [
            str(python),
            "-c",
            (
                "from ui.app import main; "
                f"main(host={HOST!r}, port={PORT})"
            ),
        ],
        cwd=str(ROOT),
        env=env,
    )

    if _wait_for_server():
        _print("Opening browser…")
        webbrowser.open(URL)
    else:
        _print(
            "Server did not become ready in time. "
            f"Try opening {URL} manually."
        )

    _print("Leave this window open while you use the app. Ctrl+C to quit.\n")
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        _print("\nStopped.")
        return 0


def main() -> int:
    os.chdir(ROOT)
    bootstrap = _resolve_bootstrap_python()
    _create_venv(bootstrap)
    _install_deps()
    _check_ffmpeg()
    return _launch_ui()


if __name__ == "__main__":
    sys.exit(main())
