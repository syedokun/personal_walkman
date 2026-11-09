"""
ui.app
======

Local web UI for personal_walkman.

Serves a minimal single-page interface and streams pipeline events so the
user can paste YouTube video / playlist URLs and watch progress without
touching the CLI.
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import subprocess
import sys
import threading
import warnings
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

import config
from walkman.pipeline import parse_url_text, run_pipeline
from walkman.ui_progress import QueueReporter, UIState

ROOT = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)

_run_lock = threading.Lock()
_browse_lock = threading.Lock()
_active_run: threading.Thread | None = None
_ui_output_dir = config.OUTPUT_DIR.resolve()


def _silence_noise() -> None:
    warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.CRITICAL, force=True)
    for name in (
        "walkman",
        "walkman.downloader",
        "walkman.album_art",
        "yt_dlp",
        "urllib3",
        "requests",
        "mutagen",
        "werkzeug",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def _validate_urls(urls: list[str]) -> str | None:
    if not urls:
        return "Paste at least one YouTube video or playlist URL."
    for url in urls:
        lowered = url.lower()
        if "youtube.com" not in lowered and "youtu.be" not in lowered:
            return f"Not a YouTube URL: {url}"
    return None


def _resolve_output_dir(raw: object) -> tuple[Path | None, str | None]:
    """Validate a user-supplied folder path."""
    if raw is None or raw == "":
        return _ui_output_dir, None
    if not isinstance(raw, str):
        return None, "Invalid save folder."
    text = raw.strip()
    if not text:
        return None, "Choose a save folder."
    path = Path(text).expanduser()
    try:
        path = path.resolve()
    except OSError as exc:
        return None, f"Invalid save folder — {exc}"

    if path.exists() and not path.is_dir():
        return None, "Save folder must be a directory."

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"Could not create save folder — {exc}"

    if not path.is_dir():
        return None, "Save folder must be a directory."

    return path, None


@app.get("/")
def index():
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    return render_template(
        "index.html",
        output_dir=str(_ui_output_dir),
        ffmpeg_ok=ffmpeg_ok,
    )


@app.get("/api/status")
def status():
    busy = _run_lock.locked() or (
        _active_run is not None and _active_run.is_alive()
    )
    return jsonify(
        {
            "busy": busy,
            "output_dir": str(_ui_output_dir),
            "ffmpeg_ok": shutil.which("ffmpeg") is not None,
        }
    )


@app.post("/api/output-dir")
def set_output_dir():
    global _ui_output_dir
    payload = request.get_json(silent=True) or {}
    path, error = _resolve_output_dir(payload.get("output_dir"))
    if error or path is None:
        return jsonify({"ok": False, "error": error or "Invalid save folder."}), 400
    _ui_output_dir = path
    return jsonify({"ok": True, "output_dir": str(_ui_output_dir)})


@app.post("/api/browse-folder")
def browse_folder():
    """Open a native folder picker (local app only)."""
    global _ui_output_dir

    if not _browse_lock.acquire(blocking=False):
        return jsonify(
            {"ok": False, "error": "A folder picker is already open."}
        ), 409

    # Run tkinter in a short-lived subprocess so macOS/Windows GUI
    # toolkits aren't invoked from a Flask worker thread.
    picker_script = r"""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

initial = sys.argv[1] if len(sys.argv) > 1 else str(Path.home())
root = tk.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)
except tk.TclError:
    pass
chosen = filedialog.askdirectory(
    title="Choose save folder",
    initialdir=initial,
    mustexist=False,
)
root.destroy()
sys.stdout.write(chosen or "")
"""

    try:
        result = subprocess.run(
            [sys.executable, "-c", picker_script, str(_ui_output_dir)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Folder picker timed out."}), 504
    except Exception as exc:  # noqa: BLE001
        return jsonify(
            {"ok": False, "error": f"Could not open folder picker — {exc}"}
        ), 500
    finally:
        _browse_lock.release()

    if result.returncode != 0:
        detail = (result.stderr or "").strip() or "unknown error"
        return jsonify(
            {"ok": False, "error": f"Could not open folder picker — {detail}"}
        ), 500

    chosen = (result.stdout or "").strip()
    if not chosen:
        return jsonify(
            {
                "ok": True,
                "cancelled": True,
                "output_dir": str(_ui_output_dir),
            }
        )

    path, error = _resolve_output_dir(chosen)
    if error or path is None:
        return jsonify({"ok": False, "error": error or "Invalid save folder."}), 400

    _ui_output_dir = path
    return jsonify(
        {"ok": True, "cancelled": False, "output_dir": str(_ui_output_dir)}
    )


@app.post("/api/run")
def start_run():
    global _active_run, _ui_output_dir

    payload = request.get_json(silent=True) or {}
    raw = payload.get("urls", "")
    if not isinstance(raw, str):
        return jsonify({"ok": False, "error": "Invalid request body."}), 400

    urls = parse_url_text(raw)
    error = _validate_urls(urls)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    output_dir, dir_error = _resolve_output_dir(payload.get("output_dir"))
    if dir_error or output_dir is None:
        return jsonify({"ok": False, "error": dir_error or "Invalid save folder."}), 400
    _ui_output_dir = output_dir

    if not shutil.which("ffmpeg"):
        return jsonify(
            {
                "ok": False,
                "error": (
                    "ffmpeg is not installed (or not on PATH). "
                    "Install it, then try again — MP3 conversion needs it."
                ),
            }
        ), 400

    if not _run_lock.acquire(blocking=False):
        return jsonify(
            {"ok": False, "error": "A download is already in progress."}
        ), 409

    event_queue: queue.Queue[dict | None] = queue.Queue()
    reporter = QueueReporter(event_queue)

    def emit(event: dict) -> None:
        event_queue.put(event)

    state = UIState(emit=emit)
    dest = output_dir

    def worker() -> None:
        try:
            run_pipeline(urls, state, reporter, output_dir=dest)
        except Exception as exc:  # noqa: BLE001
            event_queue.put({"type": "error", "message": f"Run crashed — {exc}"})
            event_queue.put(
                {
                    "type": "summary",
                    "message": "stopped with an unexpected error",
                    "failed": 1,
                }
            )
        finally:
            event_queue.put(None)
            _run_lock.release()

    _active_run = threading.Thread(target=worker, daemon=True)
    _active_run.start()

    def event_stream():
        while True:
            item = event_queue.get()
            if item is None:
                yield "event: done\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def create_app() -> Flask:
    global _ui_output_dir
    _silence_noise()
    _ui_output_dir = config.OUTPUT_DIR.resolve()
    _ui_output_dir.mkdir(parents=True, exist_ok=True)
    return app


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    create_app()
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
