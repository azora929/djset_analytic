from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Callable


TaskTarget = Callable[..., dict]


@dataclass
class TaskRecord:
    task_id: str
    state: str = "PENDING"
    meta: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LocalTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, TaskRecord] = {}

    def submit(self, task_id: str, target: TaskTarget, kwargs: dict[str, Any]) -> None:
        with self._lock:
            self._tasks[task_id] = TaskRecord(task_id=task_id)

        def _runner() -> None:
            self._set_state(task_id, "STARTED", {})

            def progress_callback(update: dict[str, Any]) -> None:
                self._set_state(task_id, "PROGRESS", dict(update))

            try:
                result = target(task_id=task_id, progress_callback=progress_callback, **kwargs)
                self._set_result(task_id, result if isinstance(result, dict) else {})
            except Exception as exc:
                self._set_error(task_id, str(exc))

        threading.Thread(target=_runner, daemon=True).start()

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _set_state(self, task_id: str, state: str, meta: dict[str, Any]) -> None:
        with self._lock:
            rec = self._tasks.get(task_id)
            if not rec:
                rec = TaskRecord(task_id=task_id)
                self._tasks[task_id] = rec
            rec.state = state
            rec.meta = meta
            rec.updated_at = datetime.now(timezone.utc).isoformat()

    def _set_result(self, task_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            rec = self._tasks.get(task_id)
            if not rec:
                rec = TaskRecord(task_id=task_id)
                self._tasks[task_id] = rec
            rec.state = "SUCCESS"
            rec.result = result
            rec.error = None
            rec.updated_at = datetime.now(timezone.utc).isoformat()

    def _set_error(self, task_id: str, error: str) -> None:
        with self._lock:
            rec = self._tasks.get(task_id)
            if not rec:
                rec = TaskRecord(task_id=task_id)
                self._tasks[task_id] = rec
            rec.state = "FAILURE"
            rec.error = error
            rec.updated_at = datetime.now(timezone.utc).isoformat()


local_task_queue = LocalTaskQueue()
