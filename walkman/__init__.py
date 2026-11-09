"""
walkman
=======

Internal package for personal_walkman.

The package is split into three modules, each handling one stage of the
pipeline:

* :mod:`walkman.downloader` - pulls audio off YouTube and converts it to MP3.
* :mod:`walkman.metadata`   - parses video titles and writes ID3 tags.
* :mod:`walkman.album_art`  - finds and downloads album cover images.

The top-level ``main.py`` orchestrates these three modules.
"""
