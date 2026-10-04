"""Job creation, polling and compatibility analyse routes."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile

from videobrief.application.commands import AnalyseCommand
from videobrief.domain.errors import InputValidationError, JobCapacityError, JobNotFoundError, UploadTooLargeError

from ..schemas import AnalyseRequest

router = APIRouter(prefix="/api")
_ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
_CHUNK_SIZE = 1024 * 1024


@router.post("/jobs")
def create_text_job(payload: AnalyseRequest, background: BackgroundTasks, request: Request) -> dict:
    if len(payload.transcript.encode("utf-8")) > 2_000_000:
        raise UploadTooLargeError("字幕文本超过 2 MB 限制。")
    command = AnalyseCommand(
        url=payload.url, transcript=payload.transcript,
        analysis_mode=payload.analysis_mode, language=payload.language,
    )
    container = request.app.state.container
    if container.jobs.active_count() >= container.settings.max_concurrent_jobs:
        raise JobCapacityError("当前处理任务已达上限，请稍后再试。", stage="queued", retryable=True)
    job = container.jobs.create("任务已创建")
    background.add_task(container.runner.run, job["id"], command)
    return job


@router.post("/jobs/upload")
async def create_upload_job(
    background: BackgroundTasks,
    request: Request,
    media: UploadFile = File(...),
    model_size: str = "tiny",
    analysis_mode: str = "auto",
    language: str = "zh",
) -> dict:
    suffix = Path(media.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise InputValidationError("不支持该文件格式。")
    if analysis_mode not in {"auto", "fast", "smart"}:
        raise InputValidationError("??????? auto?fast ? smart?")
    if model_size not in {"tiny", "small", "medium"}:
        raise InputValidationError("??????? tiny?small ? medium?")
    container = request.app.state.container
    if container.jobs.active_count() >= container.settings.max_concurrent_jobs:
        raise JobCapacityError("?????????????????", stage="queued", retryable=True)
    container.settings.upload_dir.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(
        prefix="videobrief-", suffix=suffix, dir=container.settings.upload_dir, delete=False,
    )
    temp_path = Path(temp.name)
    total = 0
    try:
        while chunk := await media.read(_CHUNK_SIZE):
            total += len(chunk)
            if total > container.settings.max_upload_bytes:
                raise UploadTooLargeError("文件大小超过上传限制。")
            temp.write(chunk)
        temp.close()
        if total == 0:
            raise InputValidationError("上传文件为空。")
        command = AnalyseCommand(
            upload_path=temp_path, original_filename=media.filename or f"media{suffix}",
            analysis_mode=analysis_mode, whisper_model=model_size, language=language,
        )
        job = container.jobs.create("文件已上传")
        background.add_task(container.runner.run, job["id"], command, temp_path)
        return job
    except Exception:
        temp.close()
        temp_path.unlink(missing_ok=True)
        raise


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = request.app.state.container.jobs.get(job_id)
    if not job:
        raise JobNotFoundError("任务不存在或服务已重启。")
    return job


@router.post("/analyse")
def analyse(payload: AnalyseRequest, request: Request) -> dict:
    command = AnalyseCommand(
        url=payload.url, transcript=payload.transcript,
        analysis_mode=payload.analysis_mode, language=payload.language,
    )
    container = request.app.state.container
    result = container.pipeline.run(command)
    result["brief_id"] = container.briefs.save(result)
    return result
