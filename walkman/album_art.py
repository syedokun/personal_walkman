"""
walkman.album_art
=================

Find and download a cover image for a song.

Strategy (in order):

1. **iTunes Search API** - free, no API key required, returns clean
   square artwork in standard resolutions. Good metadata too: it can
   even tell us the album name, which we use to fill the ``TALB`` tag.

2. **YouTube thumbnail fallback** - if iTunes has nothing for this
   artist/song (very rare for real songs, common for live recordings,
   covers, etc.), we fall back to the highest-resolution thumbnail
   yt-dlp gave us. It's not square but at least it's *something*.

The module returns a small dataclass containing both the image bytes
(ready to embed via mutagen) and the album name iTunes told us about
(or ``None`` if we used the fallback).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests


# -----------------------------------------------------------------------------
# Public data shape
# -----------------------------------------------------------------------------
@dataclass
class AlbumArtResult:
    """Result of an album-art lookup.

    Attributes
    ----------
    jpeg_bytes:
        Raw JPEG image bytes ready to embed in an ID3 APIC frame.
    album_name:
        Album the iTunes API associated with the song. ``None`` if we
        used the YouTube-thumbnail fallback (we don't know the album in
        that case).
    source:
        Either ``"itunes"`` or ``"youtube"`` - useful for logging.
    """

    jpeg_bytes: bytes
    album_name: str | None
    source: str


# -----------------------------------------------------------------------------
# iTunes Search API
# -----------------------------------------------------------------------------
_ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

# iTunes returns artwork URLs that look like
#   https://.../source/100x100bb.jpg
# We swap "100x100" for the size we want to get a higher-res image.
_ITUNES_SIZE_RE = re.compile(r"/\d+x\d+bb\.jpg$")


def _fetch_itunes(
    artist: str,
    song: str,
    artwork_size_px: int,
    timeout_s: float = 10.0,
) -> AlbumArtResult | None:
    """Query iTunes for ``artist`` + ``song`` and return artwork if found.

    Returns ``None`` if iTunes has no results or the network call fails.
    """
    query = f"{artist} {song}".strip()
    if not query:
        return None

    try:
        response = requests.get(
            _ITUNES_SEARCH_URL,
            params={
                "term": query,
                "media": "music",
                "entity": "song",
                "limit": 1,
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    results = payload.get("results") or []
    if not results:
        return None

    top = results[0]
    artwork_url_small = top.get("artworkUrl100")
    album_name = top.get("collectionName")
    if not artwork_url_small:
        return None

    # Rewrite the size component of the URL to fetch a larger image.
    artwork_url = _ITUNES_SIZE_RE.sub(
        f"/{artwork_size_px}x{artwork_size_px}bb.jpg", artwork_url_small
    )

    image_bytes = _download_bytes(artwork_url, timeout_s=timeout_s)
    if image_bytes is None:
        return None

    return AlbumArtResult(
        jpeg_bytes=image_bytes,
        album_name=album_name,
        source="itunes",
    )


# -----------------------------------------------------------------------------
# YouTube thumbnail fallback
# -----------------------------------------------------------------------------
def _fetch_youtube_thumbnail(
    thumbnail_url: str | None,
    timeout_s: float = 10.0,
) -> AlbumArtResult | None:
    """Download the YouTube video thumbnail as a fallback cover image."""
    if not thumbnail_url:
        return None
    image_bytes = _download_bytes(thumbnail_url, timeout_s=timeout_s)
    if image_bytes is None:
        return None
    return AlbumArtResult(
        jpeg_bytes=image_bytes,
        album_name=None,
        source="youtube",
    )


# -----------------------------------------------------------------------------
# Shared helper
# -----------------------------------------------------------------------------
def _download_bytes(url: str, timeout_s: float) -> bytes | None:
    """Download a URL and return its raw bytes, or ``None`` on failure.

    We don't try to convert the image format here - APIC frames support
    both JPEG and PNG, and most YouTube/iTunes thumbnails are JPEG
    anyway. We declare the MIME type as ``image/jpeg`` when embedding,
    which is what virtually all players actually look at.
    """
    try:
        response = requests.get(url, timeout=timeout_s)
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        return None


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def find_album_art(
    artist: str,
    song: str,
    youtube_thumbnail_url: str | None,
    *,
    use_itunes: bool,
    fallback_to_youtube: bool,
    artwork_size_px: int,
) -> AlbumArtResult | None:
    """Find a cover image for the song.

    Parameters
    ----------
    artist, song:
        The metadata we'll search iTunes with.
    youtube_thumbnail_url:
        Used only if iTunes fails (or is disabled) and ``fallback_to_youtube``
        is True. Pass ``None`` if you don't have one.
    use_itunes:
        Toggle for the iTunes lookup (see ``config.USE_ITUNES_LOOKUP``).
    fallback_to_youtube:
        Toggle for the YouTube-thumbnail fallback.
    artwork_size_px:
        Resolution to request from iTunes (e.g. 600 -> 600x600 JPEG).

    Returns
    -------
    AlbumArtResult | None
        An :class:`AlbumArtResult` if any source produced an image, else
        ``None``. The caller can decide whether ``None`` is fatal or
        should just produce an MP3 with no embedded art.
    """
    if use_itunes:
        result = _fetch_itunes(artist, song, artwork_size_px)
        if result is not None:
            return result

    if fallback_to_youtube:
        result = _fetch_youtube_thumbnail(youtube_thumbnail_url)
        if result is not None:
            return result

    return None
