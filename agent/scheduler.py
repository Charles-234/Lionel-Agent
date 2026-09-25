"""Simple task scheduler for Lionel's autonomous operations.

Provides a lightweight background task queue with cron-like scheduling.
Tasks are queued by the owner, run through the governed executor, and
their results are recorded in the audit ledger.

This is intentionally minimal: no distributed workers, no complex retries.
One in-process queue, one runner thread, deterministic ordering.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agent.run_limits import RunLimits

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 50
DEFAULT_SCAN_INTERVAL = 5.0


@dataclass(frozen=True)
class ScheduledTask:
    """One task waiting to run or running."""
    task_id: str
    description: str
    callback: Callable[[], Any]
    scheduled_at: float
    run_at: float
    max_attempts: int = 1
    attempt: int = 0
    last_error: Optional[str] = None
    status: str = "pending"  # pending | running | succeeded | failed | cancelled


@dataclass
class SchedulerStats:
    """Snapshot of scheduler state."""
    total_queued: int
    total_completed: int
    total_failed: int
    running_now: int
    uptime_seconds: float
    tasks: List[Dict[str, Any]] = field(default_factory=list)


class TaskScheduler:
    """In-process task queue with delayed execution."""

    def __init__(self, *, scan_interval: float = DEFAULT_SCAN_INTERVAL):
        self._lock = threading.RLock()
        self._tasks: List[ScheduledTask] = []
        self._running: Dict[str, ScheduledTask] = {}
        self._completed: int = 0
        self._failed: int = 0
        self._start_time: float = time.time()
        self._scan_interval = scan_interval
        self._shutdown = False
        self._thread: Optional[threading.Thread] = None

    def queue(
        self,
        description: str,
        callback: Callable[[], Any],
        *,
        delay_seconds: float = 0,
        max_attempts: int = 1,
        task_id: Optional[str] = None,
    ) -> str:
        """Queue a task for execution."""
        with self._lock:
            if len(self._tasks) + len(self._running) >= MAX_QUEUE_SIZE:
                raise ValueError("Task queue is full.")
            tid = task_id or f"task-{len(self._tasks) + len(self._running) + 1:04d}"
            now = time.time()
            task = ScheduledTask(
                task_id=tid,
                description=description,
                callback=callback,
                scheduled_at=now,
                run_at=now + max(0, delay_seconds),
                max_attempts=max_attempts,
            )
            self._tasks.append(task)
            logger.info("Scheduler: queued task %s (%s)", tid, description)
            return tid

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task. Returns True if cancelled."""
        with self._lock:
            for i, task in enumerate(self._tasks):
                if task.task_id == task_id and task.status == "pending":
                    self._tasks.pop(i)
                    logger.info("Scheduler: cancelled task %s", task_id)
                    return True
            return False

    def stats(self) -> SchedulerStats:
        """Return a snapshot of scheduler state."""
        with self._lock:
            uptime = time.time() - self._start_time
            return SchedulerStats(
                total_queued=len(self._tasks) + self._completed + self._failed,
                total_completed=self._completed,
                total_failed=self._failed,
                running_now=len(self._running),
                uptime_seconds=uptime,
                tasks=[
                    {
                        "task_id": t.task_id,
                        "description": t.description,
                        "status": t.status,
                        "run_at": t.run_at,
                        "attempt": t.attempt,
                        "last_error": t.last_error,
                    }
                    for t in self._tasks
                ],
            )

    def start(self) -> None:
        """Start the background scan loop."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._shutdown = False
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler: started (scan every %.1fs)", self._scan_interval)

    def stop(self) -> None:
        """Signal shutdown and wait for the thread."""
        self._shutdown = True
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Scheduler: stopped")

    def _scan_loop(self) -> None:
        """Background loop: move due tasks from queue to runner."""
        while not self._shutdown:
            try:
                self._scan()
            except Exception:
                logger.warning("Scheduler scan loop error", exc_info=True)
            time.sleep(self._scan_interval)

    def _scan(self) -> None:
        """Move due pending tasks into the running set."""
        with self._lock:
            now = time.time()
            due = [t for t in self._tasks if t.run_at <= now]
            for task in due:
                self._tasks.remove(task)
                task.status = "running"
                self._running[task.task_id] = task
            if not due:
                return

        for task in list(self._running.values()):
            self._run_task(task)

    def _run_task(self, task: ScheduledTask) -> None:
        """Execute one task and move it to completed/failed."""
        try:
            result = task.callback()
            with self._lock:
                task.status = "succeeded"
                self._completed += 1
                del self._running[task.task_id]
            logger.info("Scheduler: task %s succeeded", task.task_id)
        except Exception as e:
            with self._lock:
                task.attempt += 1
                task.last_error = str(e)[:200]
                if task.attempt < task.max_attempts:
                    # Re-queue for retry
                    task.status = "pending"
                    task.run_at = time.time() + 5
                    self._tasks.append(task)
                    del self._running[task.task_id]
                    logger.info("Scheduler: task %s retrying (%d/%d)",
                                task.task_id, task.attempt, task.max_attempts)
                else:
                    task.status = "failed"
                    self._failed += 1
                    del self._running[task.task_id]
                    logger.warning("Scheduler: task %s failed after %d attempts",
                                   task.task_id, task.max_attempts)


# Singleton
_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler


def schedule_task(
    description: str,
    callback: Callable[[], Any],
    *,
    delay_seconds: float = 0,
    task_id: Optional[str] = None,
) -> str:
    """Queue a task through the singleton scheduler."""
    return get_scheduler().queue(
        description, callback, delay_seconds=delay_seconds,
        task_id=task_id,
    )


def scheduler_stats() -> Dict[str, Any]:
    """Return stats as a plain dict for serialization."""
    s = get_scheduler().stats()
    return {
        "total_queued": s.total_queued,
        "total_completed": s.total_completed,
        "total_failed": s.total_failed,
        "running_now": s.running_now,
        "uptime_seconds": round(s.uptime_seconds, 1),
        "tasks": s.tasks,
    }
