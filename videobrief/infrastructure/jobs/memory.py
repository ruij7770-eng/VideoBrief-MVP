"""Thread-safe bounded in-memory job repository."""
from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any


class InMemoryJobRepository:
    TERMINAL = {"completed", "failed"}

    def __init__(self, *, max_terminal: int = 100, ttl_seconds: int = 24 * 3600) -> None:
        self.max_terminal = max(1, max_terminal)
        self.ttl_seconds = max(1, ttl_seconds)
        self._jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    @property
    def jobs(self) -> dict[str, dict[str, Any]]:
        """Compatibility-only direct store; new code uses snapshot methods."""
        return self._jobs

    def create(self, message: str) -> dict[str, Any]:
        now = time.time()
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "message": message,
            "result": None,
            "error": None,
            "error_info": None,
            "created_at": now,
            "updated_at": now,
        }
        with self.lock:
            self._jobs[job_id] = job
            self._prune_locked(now)
            return copy.deepcopy(job)

    def update(self, job_id: str, **values: Any) -> dict[str, Any]:
        with self.lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            current = self._jobs[job_id]
            if "progress" in values:
                values["progress"] = max(int(current.get("progress", 0)), min(100, int(values["progress"])))
            current.update(values)
            current["updated_at"] = time.time()
            self._prune_locked(current["updated_at"])
            return copy.deepcopy(current)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            value = self._jobs.get(job_id)
            return copy.deepcopy(value) if value else None

    def count(self) -> int:
        with self.lock:
            return len(self._jobs)

    def active_count(self) -> int:
        with self.lock:
            return sum(1 for job in self._jobs.values() if job.get("status") not in self.TERMINAL)

    def _prune_locked(self, now: float) -> None:
        expired = [
            job_id for job_id, job in self._jobs.items()
            if job.get("status") in self.TERMINAL and now - float(job.get("updated_at", now)) > self.ttl_seconds
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        terminal = sorted(
            ((job_id, job) for job_id, job in self._jobs.items() if job.get("status") in self.TERMINAL),
            key=lambda pair: float(pair[1].get("updated_at", 0)),
        )
        for job_id, _ in terminal[:-self.max_terminal]:
            self._jobs.pop(job_id, None)
