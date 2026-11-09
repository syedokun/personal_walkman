"""
config.py
=========

User-tweakable settings for personal_walkman.

This is the only file you should normally edit (besides ``urls.txt``).
Everything here is a plain Python value, so changing a setting is just a
matter of editing the value to the right of the ``=`` sign.
"""

from pathlib import Path

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
# Project root - resolved relative to this file so the script works no matter
# where you run it from.
PROJECT_ROOT: Path = Path(__file__).resolve().parent

# File that contains the list of YouTube URLs to process (one per line).
URLS_FILE: Path = PROJECT_ROOT / "urls.txt"

# Folder that finished MP3s get written to. The folder is created
# automatically if it doesn't already exist.
#
# Tip: if you want the script to drop files straight onto your Walkman, you
# can point this at the mounted device path, e.g.:
#     OUTPUT_DIR = Path("/Volumes/WALKMAN/MUSIC")
OUTPUT_DIR: Path = PROJECT_ROOT / "downloads"


# -----------------------------------------------------------------------------
# Audio quality
# -----------------------------------------------------------------------------
# MP3 bitrate in kbps. 192 is a good balance of size vs. quality for most
# listening; bump to 256 or 320 if you want higher fidelity.
AUDIO_BITRATE_KBPS: int = 192


# -----------------------------------------------------------------------------
# Album art
# -----------------------------------------------------------------------------
# Whether to look up real album art via the iTunes Search API.
# If False, the script will skip the lookup and only use the YouTube
# thumbnail (if FALLBACK_TO_YOUTUBE_THUMBNAIL is True).
USE_ITUNES_LOOKUP: bool = True

# If iTunes has no result for the song, fall back to the YouTube video
# thumbnail so the MP3 still has *some* cover image embedded.
FALLBACK_TO_YOUTUBE_THUMBNAIL: bool = True

# Resolution requested from iTunes for the artwork. iTunes returns a 100x100
# URL by default; we rewrite the URL to fetch a larger version. 600 is a
# good size for a Walkman screen without blowing up the file size.
ITUNES_ARTWORK_SIZE_PX: int = 600


# -----------------------------------------------------------------------------
# Title cleanup
# -----------------------------------------------------------------------------
# YouTube titles tend to be cluttered with things like "(Official Video)",
# "[HD]", "| Lyrics", etc. These regex patterns get stripped from the title
# *before* we try to split it into "Artist - Song". Patterns are
# case-insensitive.
#
# Add your own patterns here if you keep seeing junk in your tags.
TITLE_CLEANUP_PATTERNS: list[str] = [
    r"\(official\s*music\s*video\)",
    r"\(official\s*video\)",
    r"\(official\s*audio\)",
    r"\(official\s*lyric\s*video\)",
    r"\(lyrics?\)",
    r"\(lyric\s*video\)",
    r"\(visualizer\)",
    r"\(audio\)",
    r"\(hd\)",
    r"\(4k\)",
    r"\(remastered.*?\)",
    r"\[official\s*music\s*video\]",
    r"\[official\s*video\]",
    r"\[official\s*audio\]",
    r"\[lyrics?\]",
    r"\[lyric\s*video\]",
    r"\[visualizer\]",
    r"\[audio\]",
    r"\[hd\]",
    r"\[4k\]",
    r"\[remastered.*?\]",
    # Anything after a vertical bar is usually channel/branding noise:
    r"\|.*$",
]


# -----------------------------------------------------------------------------
# Behavior
# -----------------------------------------------------------------------------
# If True, re-download and re-tag MP3s even when a matching file already
# exists in OUTPUT_DIR. If False (default), skip both steps so re-running
# the script is cheap.
OVERWRITE_EXISTING: bool = False

# If True, the script keeps going when a single URL fails (logging the error)
# rather than aborting the whole run. Recommended.
CONTINUE_ON_ERROR: bool = True
