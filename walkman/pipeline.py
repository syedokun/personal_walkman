"""
walkman.pipeline
================

Shared download → tag orchestration used by both the CLI (``main.py``)
and the desktop UI. Callers supply a :class:`Reporter` for user-facing
output; the core behavior stays identical either way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import config
from walkman.album_art import find_album_art
from walkman.console import RunStats
from walkman.downloader import DownloadedTrack, download_audio
from walkman.metadata import build_metadata, write_tags


class Reporter(Protocol):
    """Receives human-readable progress from the pipeline."""

    def banner(self, url_count: int, output_dir: str) -> None: ...

    def url_header(self, url: str) -> None: ...

    def track_header(self, index: int, total: int, title: str) -> None: ...

    def step(self, message: str) -> None: ...

    def success(self, message: str) -> None: ...

    def skip(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def summary(self, stats: RunStats) -> None: ...


class PipelineState(Protocol):
    """Minimal state surface shared by the CLI and UI runners."""

    stats: RunStats
    progress: Any


def read_urls(urls_file: Path) -> list[str]:
    """Read URLs from a text file, one per line.

    Blank lines and lines that start with ``#`` (comments) are ignored.
    Inline comments (``url  # note``) are also stripped.
    """
    if not urls_file.exists():
        return []

    urls: list[str] = []
    for raw_line in urls_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            urls.append(line)
    return urls


def parse_url_text(text: str) -> list[str]:
    """Parse pasted URL text the same way ``urls.txt`` is parsed."""
    urls: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            urls.append(line)
    return urls


def already_tagged(mp3_path: Path) -> bool:
    """Return True if the MP3 already has at least a title tag set."""
    try:
        from mutagen.mp3 import MP3

        audio = MP3(mp3_path)
        return audio.tags is not None and audio.tags.get("TIT2") is not None
    except Exception:
        return False


def process_track(track: DownloadedTrack, reporter: Reporter) -> None:
    """Tag a single downloaded MP3 in place."""
    raw_title = track.info.get("title") or track.mp3_path.stem
    uploader = track.info.get("uploader") or "Unknown Artist"
    youtube_thumb = track.info.get("thumbnail")

    metadata = build_metadata(
        raw_title=raw_title,
        uploader=uploader,
        cleanup_patterns=config.TITLE_CLEANUP_PATTERNS,
    )

    reporter.step(f"Artist  {metadata.artist}")
    reporter.step(f"Title   {metadata.title}")

    art = find_album_art(
        artist=metadata.artist,
        song=metadata.title,
        youtube_thumbnail_url=youtube_thumb,
        use_itunes=config.USE_ITUNES_LOOKUP,
        fallback_to_youtube=config.FALLBACK_TO_YOUTUBE_THUMBNAIL,
        artwork_size_px=config.ITUNES_ARTWORK_SIZE_PX,
    )
    if art is not None:
        if art.album_name:
            metadata.album = art.album_name
        if art.source == "itunes" and art.album_name:
            reporter.success(f"Cover art  iTunes · {art.album_name}")
        elif art.source == "itunes":
            reporter.success("Cover art  iTunes")
        else:
            reporter.success("Cover art  YouTube thumbnail")
    else:
        reporter.skip("No cover art found")

    write_tags(
        mp3_path=track.mp3_path,
        metadata=metadata,
        cover_art_jpeg_bytes=art.jpeg_bytes if art else None,
    )
    reporter.success(f"Saved  {track.mp3_path.name}")


def process_url(
    url: str,
    state: PipelineState,
    reporter: Reporter,
    output_dir: Path | None = None,
) -> int:
    """Download and tag everything that comes out of one URL.

    Returns the number of tracks successfully handled.
    """
    dest = output_dir or config.OUTPUT_DIR
    reporter.url_header(url)
    tracks, source_label = download_audio(
        url=url,
        output_dir=dest,
        bitrate_kbps=config.AUDIO_BITRATE_KBPS,
        overwrite_existing=config.OVERWRITE_EXISTING,
        state=state,
    )
    if source_label:
        reporter.step(source_label)

    if not tracks:
        reporter.error("No tracks found for this URL")
        state.stats.failed += 1
        return 0

    success_count = 0
    for idx, track in enumerate(tracks, start=1):
        title = track.info.get("title") or track.mp3_path.stem
        reporter.track_header(idx, len(tracks), title)

        if track.skipped_download:
            reporter.skip("Already on disk")

        if not config.OVERWRITE_EXISTING and already_tagged(track.mp3_path):
            reporter.skip("Already tagged")
            state.stats.skipped_tag += 1
            success_count += 1
            continue

        try:
            if not track.skipped_download:
                reporter.success("Downloaded")
            process_track(track, reporter)
            state.stats.tagged += 1
            success_count += 1
        except Exception as exc:  # noqa: BLE001 - intentional broad catch
            reporter.error(f"Failed — {exc}")
            state.stats.failed += 1
            if not config.CONTINUE_ON_ERROR:
                raise
    return success_count


def run_pipeline(
    urls: list[str],
    state: PipelineState,
    reporter: Reporter,
    output_dir: Path | None = None,
) -> int:
    """Process every URL. Returns a process-style exit code (0 = success)."""
    if not urls:
        reporter.error(
            f"No URLs to process. Add YouTube links to {config.URLS_FILE}."
        )
        return 1

    dest = output_dir or config.OUTPUT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    state.stats.urls = len(urls)
    reporter.banner(len(urls), str(dest))

    with state.progress:
        state.progress.start()
        try:
            for url in urls:
                try:
                    process_url(url, state, reporter, output_dir=dest)
                except Exception as exc:  # noqa: BLE001 - intentional broad catch
                    reporter.error(f"URL failed — {exc}")
                    state.stats.failed += 1
                    if not config.CONTINUE_ON_ERROR:
                        return 1
        finally:
            state.progress.stop()

    reporter.summary(state.stats)
    return 0 if state.stats.failed == 0 else 1
