"""Bounded scheduler primitives; execution is supplied by a governed caller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    objective: str
    run_at: datetime
    interval_seconds: Optional[int] = None
    enabled: bool = True
    requires_approval: bool = True


class TaskScheduler:
    """In-process scheduler that emits due work but never runs it itself."""

    def __init__(self, max_tasks: int = 100):
        self.max_tasks = max_tasks
        self._tasks: Dict[str, ScheduledTask] = {}

    def add(self, task: ScheduledTask) -> None:
        if len(self._tasks) >= self.max_tasks and task.task_id not in self._tasks:
            raise ValueError("scheduler task limit reached")
        if task.interval_seconds is not None and not 60 <= task.interval_seconds <= 31_536_000:
            raise ValueError("recurring interval must be between 60 seconds and one year")
        self._tasks[task.task_id] = task

    def remove(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def due(self, now: Optional[datetime] = None) -> list[ScheduledTask]:
        current = now or datetime.now(timezone.utc)
        return [task for task in self._tasks.values() if task.enabled and task.run_at <= current]

    def acknowledge(self, task_id: str, now: Optional[datetime] = None) -> None:
        task = self._tasks.get(task_id)
        if task is None or task.interval_seconds is None:
            self._tasks.pop(task_id, None)
            return
        current = now or datetime.now(timezone.utc)
        self._tasks[task_id] = ScheduledTask(
            task_id=task.task_id,
            objective=task.objective,
            run_at=current + timedelta(seconds=task.interval_seconds),
            interval_seconds=task.interval_seconds,
            enabled=task.enabled,
            requires_approval=task.requires_approval,
        )

    def list(self) -> list[ScheduledTask]:
        return list(self._tasks.values())
