"""
walkman.console
===============

Clean terminal output for personal_walkman.

Uses Rich for progress bars and status lines while suppressing noisy
third-party loggers (yt-dlp, urllib3, etc.).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.text import Text

console = Console(highlight=False)

_PROGRESS = Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(bar_width=32),
    TaskProgressColumn(),
    DownloadColumn(),
    TransferSpeedColumn(),
    TimeRemainingColumn(),
    console=console,
    transient=True,
)


@dataclass
class RunStats:
    """Counters shown in the final summary."""

    urls: int = 0
    tracks_total: int = 0
    downloaded: int = 0
    skipped_download: int = 0
    tagged: int = 0
    skipped_tag: int = 0
    failed: int = 0


@dataclass
class ConsoleState:
    """Mutable run state shared across pipeline stages."""

    stats: RunStats = field(default_factory=RunStats)
    progress: Progress = field(default_factory=lambda: _PROGRESS)


def setup_console() -> ConsoleState:
    """Silence warnings and route all user-facing output through Rich."""
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
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    return ConsoleState()


def print_banner(url_count: int, output_dir: str) -> None:
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold]personal_walkman[/bold]\n"
                f"{url_count} URL(s)  →  [cyan]{output_dir}[/cyan]"
            ),
            border_style="blue",
            padding=(0, 2),
        )
    )
    console.print()


def print_url_header(url: str, label: str | None = None) -> None:
    title = label or _short_url(url)
    console.print(f"[bold blue]▸[/bold blue] [bold]{title}[/bold]")
    if label:
        console.print(f"  [dim]{_short_url(url)}[/dim]")


def print_track_header(index: int, total: int, title: str) -> None:
    console.print()
    console.print(f"[bold][{index}/{total}] {title}[/bold]")


def print_step(message: str, style: str = "dim") -> None:
    console.print(f"  [{style}]{message}[/{style}]")


def print_success(message: str) -> None:
    console.print(f"  [green]✓[/green] {message}")


def print_skip(message: str) -> None:
    console.print(f"  [dim]○ {message}[/dim]")


def print_error(message: str) -> None:
    console.print(f"  [red]✗[/red] {message}")


def print_summary(stats: RunStats) -> None:
    parts: list[str] = []
    if stats.tagged:
        parts.append(f"[green]{stats.tagged} tagged[/green]")
    if stats.downloaded:
        parts.append(f"[cyan]{stats.downloaded} downloaded[/cyan]")
    if stats.skipped_download:
        parts.append(f"[dim]{stats.skipped_download} already on disk[/dim]")
    if stats.skipped_tag:
        parts.append(f"[dim]{stats.skipped_tag} already tagged[/dim]")
    if stats.failed:
        parts.append(f"[red]{stats.failed} failed[/red]")

    summary = " · ".join(parts) if parts else "[dim]nothing to do[/dim]"
    console.print()
    console.print(
        Panel(
            Text.from_markup(f"[bold]Done[/bold]  —  {summary}"),
            border_style="green" if stats.failed == 0 else "yellow",
            padding=(0, 2),
        )
    )
    console.print()


def progress_context(state: ConsoleState):
    """Enter the shared Rich progress display."""
    return state.progress


def start_fetch_spinner(state: ConsoleState, message: str = "Fetching info…") -> int:
    return state.progress.add_task(message, total=None)


def start_download_task(
    state: ConsoleState,
    title: str,
    total_bytes: int | None = None,
) -> int:
    short = _truncate(title, 40)
    return state.progress.add_task(
        f"Downloading {short}",
        total=total_bytes or None,
    )


def stop_task(state: ConsoleState, task_id: int) -> None:
    state.progress.remove_task(task_id)


def _short_url(url: str, max_len: int = 72) -> str:
    return url if len(url) <= max_len else url[: max_len - 1] + "…"


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
