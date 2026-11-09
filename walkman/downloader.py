"""
walkman.downloader
==================

Thin wrapper around `yt-dlp <https://github.com/yt-dlp/yt-dlp>`_ that:

1. Accepts either a single-video URL or a playlist URL.
2. Downloads the best available audio stream.
3. Uses ffmpeg (must be installed on the system) to transcode it to MP3.
4. Returns one :class:`DownloadedTrack` per produced MP3 file, along with
   the raw metadata yt-dlp pulled from YouTube (title, uploader, duration,
   thumbnail URL, etc.) so later stages can use it.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

import yt_dlp

if TYPE_CHECKING:
    from walkman.console import ConsoleState


# -----------------------------------------------------------------------------
# Public data shape
# -----------------------------------------------------------------------------
@dataclass
class DownloadedTrack:
    """One downloaded MP3 plus the raw YouTube info that produced it."""

    mp3_path: Path
    info: dict[str, Any]
    skipped_download: bool = False


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------
class _QuietLogger:
    """Swallow yt-dlp log output so the Rich UI stays clean."""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _build_ydl_options(
    output_dir: Path,
    bitrate_kbps: int,
    progress_hook: Callable[[dict[str, Any]], None] | None = None,
    *,
    noplaylist: bool = False,
) -> dict[str, Any]:
    """Build the options dict passed to :class:`yt_dlp.YoutubeDL`."""
    opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        "ignoreerrors": True,
        "noplaylist": noplaylist,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(bitrate_kbps),
            }
        ],
    }
    ffmpeg = _ffmpeg_path()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]
    return opts


def _expected_mp3_path(ydl: yt_dlp.YoutubeDL, entry: dict[str, Any]) -> Path:
    """Return the MP3 path yt-dlp will produce for ``entry``."""
    return Path(ydl.prepare_filename(entry)).with_suffix(".mp3")


def _video_url(entry: dict[str, Any]) -> str | None:
    """Return a canonical YouTube watch URL for a playlist/video entry."""
    webpage_url = entry.get("webpage_url")
    if webpage_url:
        return webpage_url
    video_id = entry.get("id")
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    url = entry.get("url")
    if url and "youtube.com/watch" in url:
        return url
    return None


def _cleanup_intermediate_files(mp3_path: Path) -> None:
    """Remove leftover audio files once the MP3 exists."""
    for ext in (".webm", ".m4a", ".opus", ".ogg", ".wav", ".part"):
        leftover = mp3_path.with_suffix(ext)
        if leftover.exists():
            leftover.unlink(missing_ok=True)


def _convert_to_mp3(source: Path, mp3_path: Path, bitrate_kbps: int) -> None:
    """Convert an audio file to MP3 with ffmpeg."""
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise FileNotFoundError(
            "ffmpeg is not installed. Install it and make sure `ffmpeg -version` works."
        )

    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(mp3_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to convert {source.name} to MP3: {result.stderr.strip()}"
        )
    source.unlink(missing_ok=True)


def _recover_mp3_from_intermediate(
    mp3_path: Path,
    bitrate_kbps: int,
) -> Path | None:
    """Convert a leftover download file to MP3 if the MP3 is missing."""
    if mp3_path.exists():
        _cleanup_intermediate_files(mp3_path)
        return mp3_path

    for ext in (".webm", ".m4a", ".opus", ".ogg", ".wav"):
        leftover = mp3_path.with_suffix(ext)
        if leftover.exists():
            _convert_to_mp3(leftover, mp3_path, bitrate_kbps)
            return mp3_path
    return None


def _resolve_mp3_path(
    ydl: yt_dlp.YoutubeDL,
    info: dict[str, Any],
    output_dir: Path,
    bitrate_kbps: int,
) -> Path:
    """Return the on-disk MP3 path for a downloaded video."""
    mp3_path = _expected_mp3_path(ydl, info)
    if mp3_path.exists():
        _cleanup_intermediate_files(mp3_path)
        return mp3_path

    stem = mp3_path.stem
    matches = sorted(output_dir.glob(f"{stem}.mp3"))
    if matches:
        _cleanup_intermediate_files(matches[0])
        return matches[0]

    for ext in (".webm", ".m4a", ".opus", ".ogg", ".wav"):
        leftover = mp3_path.with_suffix(ext)
        if leftover.exists():
            _convert_to_mp3(leftover, mp3_path, bitrate_kbps)
            return mp3_path

    raise FileNotFoundError(f"Expected MP3 not found for {info.get('title', stem)!r}")


def _flatten_info(info: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield one info-dict per actual video."""
    if info is None:
        return
    if "entries" in info and info["entries"] is not None:
        for entry in info["entries"]:
            if entry is not None:
                yield entry
    else:
        yield info


def _make_progress_hook(state: ConsoleState, task_id: int):
    """Build a yt-dlp progress hook that drives a Rich download bar."""

    def hook(status: dict[str, Any]) -> None:
        phase = status.get("status")
        if phase == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            downloaded = status.get("downloaded_bytes") or 0
            state.progress.update(task_id, completed=downloaded, total=total)
        elif phase == "finished":
            total = (
                status.get("total_bytes")
                or status.get("total_bytes_estimate")
                or status.get("downloaded_bytes")
                or 1
            )
            state.progress.update(task_id, completed=total, total=total)

    return hook


def _source_label(info: dict[str, Any]) -> str | None:
    """Return a human label for a URL's source (playlist title, etc.)."""
    if info.get("_type") == "playlist":
        title = info.get("title")
        count = info.get("playlist_count") or len(info.get("entries") or [])
        if title:
            return f"{title} ({count} tracks)"
    return None


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def download_audio(
    url: str,
    output_dir: Path,
    bitrate_kbps: int = 192,
    overwrite_existing: bool = False,
    state: ConsoleState | None = None,
) -> tuple[list[DownloadedTrack], str | None]:
    """Download audio from a YouTube URL and return the resulting MP3s."""
    from walkman.console import start_download_task, start_fetch_spinner, stop_task

    output_dir.mkdir(parents=True, exist_ok=True)

    fetch_task: int | None = None
    if state is not None:
        fetch_task = start_fetch_spinner(state)

    meta_opts = _build_ydl_options(output_dir, bitrate_kbps)
    with yt_dlp.YoutubeDL(meta_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if state is not None and fetch_task is not None:
        stop_task(state, fetch_task)

    source_label = _source_label(info) if info else None
    tracks: list[DownloadedTrack] = []

    with yt_dlp.YoutubeDL(meta_opts) as ydl:
        for entry in _flatten_info(info):
            mp3_path = _expected_mp3_path(ydl, entry)
            recovered = _recover_mp3_from_intermediate(mp3_path, bitrate_kbps)
            if recovered is not None and not overwrite_existing:
                tracks.append(
                    DownloadedTrack(
                        mp3_path=recovered,
                        info=entry,
                        skipped_download=True,
                    )
                )
                if state is not None:
                    state.stats.skipped_download += 1
                continue

            video_url = _video_url(entry)
            if not video_url:
                continue

            title = entry.get("title") or mp3_path.stem
            download_task: int | None = None
            progress_hook = None
            if state is not None:
                filesize = entry.get("filesize") or entry.get("filesize_approx")
                download_task = start_download_task(state, title, filesize)
                progress_hook = _make_progress_hook(state, download_task)

            download_opts = _build_ydl_options(
                output_dir,
                bitrate_kbps,
                progress_hook=progress_hook,
                noplaylist=True,
            )
            try:
                with yt_dlp.YoutubeDL(download_opts) as video_ydl:
                    dl_info = video_ydl.extract_info(video_url, download=True)
                    if dl_info is None:
                        continue
                    mp3_path = _resolve_mp3_path(
                        video_ydl, dl_info, output_dir, bitrate_kbps,
                    )
            finally:
                if state is not None and download_task is not None:
                    stop_task(state, download_task)

            if state is not None:
                state.stats.downloaded += 1

            tracks.append(
                DownloadedTrack(
                    mp3_path=mp3_path,
                    info=dl_info,
                    skipped_download=False,
                )
            )

    return tracks, source_label
