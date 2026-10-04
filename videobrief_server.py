"""VideoBrief compatibility entry point and modular FastAPI composition root."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import uvicorn

from videobrief.api.app import create_app
from videobrief.application.commands import AnalyseCommand
from videobrief.config import Settings
from videobrief.infrastructure.persistence.sqlite import SQLiteBriefRepository

settings = Settings.from_env()
DB_PATH = settings.db_path
MAX_UPLOAD = settings.max_upload_bytes
ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
PORT = settings.port

app = create_app()
_container = app.state.container
_jobs = _container.jobs.jobs
_jobs_lock = _container.jobs.lock

# Historical request DTO imports remain available.
from videobrief.api.schemas import AnalyseRequest, QuestionRequest


def _sync_repository_path() -> SQLiteBriefRepository:
    """Honor legacy tests/scripts that monkeypatch ``DB_PATH`` at runtime."""
    global _container
    path = Path(DB_PATH)
    if _container.briefs.path != path:
        repository = SQLiteBriefRepository(path)
        _container.briefs = repository
        _container.runner.briefs = repository
    return _container.briefs


@contextmanager
def _db():
    with _sync_repository_path().connection() as connection:
        yield connection


def _save_result(result: dict) -> str:
    return _sync_repository_path().save(result)


def _set_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            current = _jobs[job_id]
            if "progress" in values:
                values["progress"] = max(int(current.get("progress", 0)), int(values["progress"]))
            current.update(values)


def _new_job(message: str) -> dict:
    return _container.jobs.create(message)


def _command_from_payload(payload: dict) -> AnalyseCommand:
    return AnalyseCommand(
        url=str(payload.get("url", "")),
        transcript=str(payload.get("transcript", "")),
        analysis_mode=str(payload.get("analysis_mode", "auto")),
    )


def analyse_payload(payload: dict) -> dict:
    """Synchronous compatibility API; no persistence side effect."""
    return _container.pipeline.run(_command_from_payload(payload))


def analyse_file(filename: str, path: Path, model_size: str = "tiny", analysis_mode: str = "auto") -> dict:
    return _container.pipeline.run(AnalyseCommand(
        upload_path=Path(path), original_filename=filename,
        whisper_model=model_size, analysis_mode=analysis_mode,
    ))


def _run_with_live_progress(job_id: str, function, *, start: int, ceiling: int, message: str):
    """Compatibility heartbeat wrapper retained for long blocking work."""
    progress = start
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(function)
        while True:
            try:
                return future.result(timeout=2)
            except FutureTimeout:
                progress = min(ceiling, progress + 3)
                _set_job(job_id, progress=progress, message=message)


def _run_text_job(job_id: str, payload: dict) -> None:
    _container.runner.run(job_id, _command_from_payload(payload))


def _run_upload_job(job_id: str, filename: str, temp_path: str, model_size: str, analysis_mode: str) -> None:
    _container.runner.run(
        job_id,
        AnalyseCommand(
            upload_path=Path(temp_path), original_filename=filename,
            whisper_model=model_size, analysis_mode=analysis_mode,
        ),
        Path(temp_path),
    )


if __name__ == "__main__":
    _sync_repository_path().ensure_schema()
    print(f"VideoBrief V4 listening on http://127.0.0.1:{PORT}/")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
