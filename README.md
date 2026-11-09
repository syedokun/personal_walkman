# personal_walkman

Automate the tedious bits of loading songs onto a Walkman:

1. Download the audio from a YouTube video (or a whole YouTube playlist / "album").
2. Convert it to MP3.
3. Parse the YouTube title into clean **artist** / **song** values.
4. Look up the real **album cover** via the iTunes Search API.
5. Embed the cover art and write ID3 tags into the MP3.

After it finishes, the tagged MP3s sit in `downloads/`, ready to be dragged onto your Walkman over USB. You can also point the script directly at the mounted device — see `OUTPUT_DIR` in `config.py`.

---

## Project layout

```
personal_walkman/
├── README.md                 <- you are here
├── Personal Walkman.command  <- double-click launcher (macOS)
├── Personal Walkman.bat      <- double-click launcher (Windows)
├── run.py                    <- creates .venv, installs deps, opens the UI
├── requirements.txt          <- Python deps
├── config.py                 <- knobs: output folder, bitrate, etc.
├── urls.txt                  <- optional CLI input file
├── main.py                   <- CLI entry point
├── ui/                       <- local web UI
└── walkman/
    ├── downloader.py         <- yt-dlp wrapper (YouTube -> MP3)
    ├── metadata.py           <- title parsing + ID3 tag writing
    ├── album_art.py          <- iTunes lookup + YouTube thumbnail fallback
    └── pipeline.py           <- shared download/tag orchestration
```

---

## Quick start (UI)

1. Install **Python 3.10+** and **ffmpeg** (see below).
2. Double-click **`Personal Walkman.command`** (macOS) or **`Personal Walkman.bat`** (Windows),  
   or run:

```bash
python3 run.py
```

On first launch the app creates a local `.venv`, installs dependencies, starts a tiny local server, and opens the UI in your browser. Paste any YouTube video or playlist URL and hit **Download**.

---

## One-time system setup

### 1. Install Python 3.10+

```bash
python3 --version
```

### 2. Install ffmpeg

ffmpeg does the actual MP3 transcoding. It's a system dependency, not a Python package.

On macOS:

```bash
brew install ffmpeg
```

On Linux (Debian/Ubuntu):

```bash
sudo apt install ffmpeg
```

On Windows: download a build from [ffmpeg.org](https://ffmpeg.org/download.html) and put it on your `PATH`.

Verify:

```bash
ffmpeg -version
```

Python packages are installed automatically by `run.py` — no manual `pip install` needed for the UI.

---

## CLI usage (optional)

The original workflow still works.

### 1. Add URLs to `urls.txt`

Paste YouTube links — **one per line**. Lines that start with `#` are comments. Both single videos and playlists work:

```
# Single song
https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Whole album as a playlist
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Run the CLI

```bash
.venv/bin/python main.py          # after you've run run.py once
# or, with an activated venv:
python main.py
```

You'll see something like:

```
╭──────────────────────────────────────────────────╮
│  personal_walkman                                │
│  1 URL(s)  →  /.../downloads                     │
╰──────────────────────────────────────────────────╯

▸ https://www.youtube.com/watch?v=...

[1/1] Rick Astley - Never Gonna Give You Up (Official Music Video)
  ✓ Downloaded
  Artist  Rick Astley
  Title   Never Gonna Give You Up
  ✓ Cover art  iTunes · Whenever You Need Somebody
  ✓ Saved  Rick Astley - Never Gonna Give You Up (Official Music Video).mp3

╭──────────────────────────────────────────────────╮
│  Done  —  1 tagged · 1 downloaded                │
╰──────────────────────────────────────────────────╯
```

### 3. Plug in your Walkman and copy the files

By default the MP3s land in `downloads/`. If you'd rather have the script write straight to the device, edit `config.py`:

```python
from pathlib import Path
OUTPUT_DIR = Path("/Volumes/WALKMAN/MUSIC")   # macOS example
```

---

## Tweaking behavior

All of the dials live in `config.py` and each one is documented inline. The most useful ones:

| Setting | What it does |
| --- | --- |
| `OUTPUT_DIR` | Where MP3s get written. Point this at your Walkman to skip the copy step. |
| `AUDIO_BITRATE_KBPS` | MP3 bitrate. 192 (default) is good; 320 for audiophiles. |
| `USE_ITUNES_LOOKUP` | Set to `False` to skip the iTunes album-art lookup entirely. |
| `FALLBACK_TO_YOUTUBE_THUMBNAIL` | If iTunes finds nothing, embed the YouTube thumbnail instead. |
| `OVERWRITE_EXISTING` | By default already-tagged MP3s are skipped on re-runs. Flip to `True` to retag everything. |
| `TITLE_CLEANUP_PATTERNS` | Regexes used to strip noise like "(Official Video)" from titles. Add your own if you keep seeing junk. |

---

## How the title parsing works

YouTube titles are messy. The script:

1. Strips known noise via the regexes in `TITLE_CLEANUP_PATTERNS` (case-insensitive). Out of the box it handles things like `(Official Video)`, `[HD]`, `(Lyrics)`, `(Remastered 2011)`, and anything after a `|`.
2. Looks for `Artist - Song` (with the hyphen, en-dash, or em-dash). If found, those become the **artist** and **title** tags.
3. If the title has no separator, it falls back to using the **channel name** (e.g. `RickAstleyVEVO`) as the artist and the cleaned title as the song name.

The album name comes from the iTunes lookup if that succeeds; otherwise it's left blank.

---

## Troubleshooting

**`ffmpeg not found` / "Postprocessing: ffmpeg or ffprobe not found"**
Install ffmpeg (see setup step 2) and make sure `ffmpeg -version` works in your terminal.

**`HTTP Error 403: Forbidden` from YouTube**
Update `yt-dlp`: `pip install -U yt-dlp`. YouTube changes their player code regularly and yt-dlp ships fixes within hours.

**Wrong artist / title got tagged**
Check the raw YouTube title — if it doesn't have an `Artist - Song` shape, the parser can only do so much. You can either:
* edit the YouTube title in a browser (you can't), so instead
* add a more aggressive pattern to `TITLE_CLEANUP_PATTERNS` in `config.py`, **or**
* open the MP3 in any tag editor (Mp3tag, Kid3, etc.) and fix it by hand.

**No cover art got embedded**
Either iTunes had no match (try less specific titles) or you're offline. Set `FALLBACK_TO_YOUTUBE_THUMBNAIL = True` in `config.py` so you at least get the thumbnail.

**The script re-downloads things every run**
By default, MP3s that already exist in `downloads/` are not re-downloaded, and already-tagged files are not re-tagged. Set `OVERWRITE_EXISTING = True` in `config.py` if you want to force a full re-download and re-tag.
