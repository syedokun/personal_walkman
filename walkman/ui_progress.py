"""
walkman.ui_progress
===================

Progress + reporter adapters that drive the web UI instead of Rich.
Mirrors the surface that :mod:`walkman.downloader` expects from
``ConsoleState.progress`` so downloads keep working unchanged.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from walkman.console import RunStats


EmitFn = Callable[[dict[str, Any]], None]


@dataclass
class _Task:
    description: str
    total: float | None = None
    completed: float = 0.0


class UIProgress:
    """Drop-in stand-in for Rich ``Progress`` used by the downloader."""

    def __init__(self, emit: EmitFn) -> None:
        self._emit = emit
        self._tasks: dict[int, _Task] = {}
        self._next_id = 1
        self._lock = threading.Lock()
        self._active = False

    def __enter__(self) -> UIProgress:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False
        with self._lock:
            self._tasks.clear()

    def add_task(self, description: str, total: float | None = None) -> int:
        with self._lock:
            task_id = self._next_id
            self._next_id += 1
            self._tasks[task_id] = _Task(description=description, total=total)
        self._emit(
            {
                "type": "progress",
                "task_id": task_id,
                "message": description,
                "completed": 0,
                "total": total,
                "phase": "start",
            }
        )
        return task_id

    def update(
        self,
        task_id: int,
        *,
        completed: float | None = None,
        total: float | None = None,
        description: str | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if completed is not None:
                task.completed = completed
            if total is not None:
                task.total = total
            if description is not None:
                task.description = description
            snapshot = _Task(task.description, task.total, task.completed)
        self._emit(
            {
                "type": "progress",
                "task_id": task_id,
                "message": snapshot.description,
                "completed": snapshot.completed,
                "total": snapshot.total,
                "phase": "update",
            }
        )

    def remove_task(self, task_id: int) -> None:
        with self._lock:
            task = self._tasks.pop(task_id, None)
        if task is None:
            return
        self._emit(
            {
                "type": "progress",
                "task_id": task_id,
                "message": task.description,
                "completed": task.completed,
                "total": task.total,
                "phase": "done",
            }
        )


@dataclass
class UIState:
    """ConsoleState-compatible object for UI-driven runs."""

    emit: EmitFn
    stats: RunStats = field(default_factory=RunStats)
    progress: UIProgress = field(init=False)

    def __post_init__(self) -> None:
        self.progress = UIProgress(self.emit)


class QueueReporter:
    """Reporter that pushes structured events onto a thread-safe queue."""

    def __init__(self, event_queue: queue.Queue[dict[str, Any] | None]) -> None:
        self._queue = event_queue

    def _put(self, event: dict[str, Any]) -> None:
        self._queue.put(event)

    def banner(self, url_count: int, output_dir: str) -> None:
        self._put(
            {
                "type": "banner",
                "message": f"{url_count} URL(s) → {output_dir}",
                "url_count": url_count,
                "output_dir": output_dir,
            }
        )

    def url_header(self, url: str) -> None:
        self._put({"type": "url", "message": url})

    def track_header(self, index: int, total: int, title: str) -> None:
        self._put(
            {
                "type": "track",
                "message": title,
                "index": index,
                "total": total,
            }
        )

    def step(self, message: str) -> None:
        self._put({"type": "step", "message": message})

    def success(self, message: str) -> None:
        self._put({"type": "success", "message": message})

    def skip(self, message: str) -> None:
        self._put({"type": "skip", "message": message})

    def error(self, message: str) -> None:
        self._put({"type": "error", "message": message})

    def summary(self, stats: RunStats) -> None:
        parts: list[str] = []
        if stats.tagged:
            parts.append(f"{stats.tagged} tagged")
        if stats.downloaded:
            parts.append(f"{stats.downloaded} downloaded")
        if stats.skipped_download:
            parts.append(f"{stats.skipped_download} already on disk")
        if stats.skipped_tag:
            parts.append(f"{stats.skipped_tag} already tagged")
        if stats.failed:
            parts.append(f"{stats.failed} failed")
        self._put(
            {
                "type": "summary",
                "message": " · ".join(parts) if parts else "nothing to do",
                "failed": stats.failed,
                "tagged": stats.tagged,
                "downloaded": stats.downloaded,
            }
        )
