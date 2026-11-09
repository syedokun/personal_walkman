"""
walkman.metadata
================

Two responsibilities:

1. **Parse a YouTube video title** into ``(artist, song)`` so we can fill
   ID3 tags sensibly. YouTube titles are messy ("Artist - Song (Official
   Video) [HD] | TopicChannel") so this module strips the noise first.

2. **Write ID3 tags** (title, artist, album, embedded cover art) onto the
   downloaded MP3 using `mutagen <https://mutagen.readthedocs.io/>`_.

Title parsing is best-effort: if we can't confidently split the title
into artist + song, we fall back to using the channel name as the artist
and the entire (cleaned) title as the song.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TIT2, TPE1
from mutagen.mp3 import MP3


# -----------------------------------------------------------------------------
# Public data shape
# -----------------------------------------------------------------------------
@dataclass
class TrackMetadata:
    """Metadata we plan to write to an MP3.

    ``album`` is optional - if we don't know it (we usually don't from a
    YouTube title alone), we leave it out and the album-art lookup may
    fill it in later.
    """

    title: str
    artist: str
    album: str | None = None


# -----------------------------------------------------------------------------
# Title cleanup
# -----------------------------------------------------------------------------
def clean_title(raw_title: str, cleanup_patterns: Iterable[str]) -> str:
    """Strip noisy suffixes/parentheticals from a YouTube title.

    Each pattern is a regex (case-insensitive). After all patterns are
    removed, leftover whitespace is collapsed.

    Examples
    --------
    >>> clean_title(
    ...     "Daft Punk - Get Lucky (Official Video) [HD]",
    ...     [r"\\(official\\s*video\\)", r"\\[hd\\]"],
    ... )
    'Daft Punk - Get Lucky'
    """
    cleaned = raw_title
    for pattern in cleanup_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    # Collapse any double spaces left behind, and trim.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Strip stray dashes/pipes left dangling at the ends after removals.
    cleaned = cleaned.strip(" -|\u2013\u2014")
    return cleaned


# Characters used to separate "Artist" and "Song" in YouTube titles.
# Includes the regular hyphen plus the en-dash and em-dash often used
# by music channels.
_ARTIST_SONG_SEPARATORS = (" - ", " \u2013 ", " \u2014 ")


def parse_artist_and_song(
    cleaned_title: str,
    fallback_artist: str,
) -> tuple[str, str]:
    """Try to split a cleaned title into (artist, song).

    Strategy
    --------
    Most music videos on YouTube are titled ``Artist - Song`` (with a
    hyphen surrounded by spaces). We split on the first such separator.

    If no separator is found, we assume the whole title is the song name
    and use ``fallback_artist`` (typically the channel/uploader name) as
    the artist.

    Parameters
    ----------
    cleaned_title:
        Title after passing through :func:`clean_title`.
    fallback_artist:
        Used as the artist if the title can't be split. Usually the
        YouTube channel name.
    """
    for sep in _ARTIST_SONG_SEPARATORS:
        if sep in cleaned_title:
            artist, song = cleaned_title.split(sep, 1)
            return artist.strip(), song.strip()
    return fallback_artist.strip(), cleaned_title.strip()


def build_metadata(
    raw_title: str,
    uploader: str,
    cleanup_patterns: Iterable[str],
) -> TrackMetadata:
    """Convenience wrapper: clean + parse in one call.

    This is what the main pipeline actually uses.
    """
    cleaned = clean_title(raw_title, cleanup_patterns)
    artist, song = parse_artist_and_song(cleaned, fallback_artist=uploader)
    return TrackMetadata(title=song, artist=artist, album=None)


# -----------------------------------------------------------------------------
# ID3 writing
# -----------------------------------------------------------------------------
def write_tags(
    mp3_path: Path,
    metadata: TrackMetadata,
    cover_art_jpeg_bytes: bytes | None,
) -> None:
    """Write title/artist/album tags + (optionally) embed cover art.

    Parameters
    ----------
    mp3_path:
        Path to the MP3 file to tag.
    metadata:
        The parsed metadata to write.
    cover_art_jpeg_bytes:
        Raw JPEG bytes of the cover art, or ``None`` to skip the
        embedded image.

    Notes
    -----
    Mutagen's ID3 frames use single-letter codes:
        * ``TIT2`` - track title
        * ``TPE1`` - lead performer / artist
        * ``TALB`` - album
        * ``APIC`` - attached picture (cover art)
    Encoding ``3`` means UTF-8.
    """
    # Some MP3s come out of yt-dlp with no ID3 header at all; mutagen
    # raises ID3NoHeaderError in that case and we have to add one.
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
    except ID3NoHeaderError:
        audio = MP3(mp3_path)
        audio.add_tags()

    tags = audio.tags
    assert tags is not None  # Just appeased the type checker.

    # Wipe any pre-existing values for the frames we're about to set so
    # we don't end up with duplicates if the file was tagged before.
    for frame_id in ("TIT2", "TPE1", "TALB", "APIC"):
        tags.delall(frame_id)

    tags.add(TIT2(encoding=3, text=metadata.title))
    tags.add(TPE1(encoding=3, text=metadata.artist))
    if metadata.album:
        tags.add(TALB(encoding=3, text=metadata.album))

    if cover_art_jpeg_bytes is not None:
        tags.add(
            APIC(
                encoding=3,           # UTF-8 description
                mime="image/jpeg",
                type=3,               # 3 = "Cover (front)"
                desc="Cover",
                data=cover_art_jpeg_bytes,
            )
        )

    # ``v2_version=3`` writes ID3v2.3, which is the version with the
    # widest support across portable players (older Walkmans included).
    audio.save(v2_version=3)
