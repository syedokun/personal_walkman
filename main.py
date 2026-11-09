"""
main.py
=======

Entry point for personal_walkman (CLI).

Run it with:

    python main.py

What it does
------------
1. Reads YouTube URLs from ``urls.txt``.
2. For each URL:

   a. Downloads the audio (single video *or* whole playlist) as MP3 via
      :mod:`walkman.downloader`.
   b. Parses the YouTube title into ``(artist, song)`` and looks up the
      album cover via :mod:`walkman.album_art`.
   c. Writes ID3 tags (title/artist/album + embedded cover art) onto
      the MP3 via :mod:`walkman.metadata`.

3. Prints a per-track status line so you can see what worked.

The script is "best effort": one bad URL will not stop the others (as
long as ``CONTINUE_ON_ERROR`` is True in ``config.py``).

After the script finishes, the tagged MP3s live in ``OUTPUT_DIR`` (also
configurable). You can then drag-and-drop them onto your Walkman, or
point ``OUTPUT_DIR`` directly at the mounted device.

Prefer the polished UI instead? Double-click ``Personal Walkman.command``
(macOS) or run ``python run.py``.
"""

from __future__ import annotations

import sys

import config
from walkman.console import (
    RunStats,
    print_banner,
    print_error,
    print_skip,
    print_step,
    print_success,
    print_summary,
    print_track_header,
    print_url_header,
    setup_console,
)
from walkman.pipeline import read_urls, run_pipeline


class ConsoleReporter:
    """Adapter that routes pipeline events to the Rich terminal UI."""

    def banner(self, url_count: int, output_dir: str) -> None:
        print_banner(url_count, output_dir)

    def url_header(self, url: str) -> None:
        print_url_header(url)

    def track_header(self, index: int, total: int, title: str) -> None:
        print_track_header(index, total, title)

    def step(self, message: str) -> None:
        print_step(message)

    def success(self, message: str) -> None:
        print_success(message)

    def skip(self, message: str) -> None:
        print_skip(message)

    def error(self, message: str) -> None:
        print_error(message)

    def summary(self, stats: RunStats) -> None:
        print_summary(stats)


def main() -> int:
    """Read ``urls.txt`` and process every URL in it."""
    state = setup_console()
    urls = read_urls(config.URLS_FILE)
    if not urls:
        print_error(
            f"No URLs to process. Add YouTube links to {config.URLS_FILE}."
        )
        return 1
    return run_pipeline(urls, state, ConsoleReporter())


if __name__ == "__main__":
    sys.exit(main())
