"""VideoBrief V3：FastAPI、后台任务、进度查询和本地历史记录。"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from videobrief_agent import agent_status, enhance_brief
from videobrief_service import answer_from_brief, make_brief, request_brief, transcribe_local_video

DB_PATH = ROOT / "videobrief.db"
MAX_UPLOAD = 500 * 1024 * 1024
ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
PORT = int(os.getenv("VIDEOBRIEF_PORT", "12000"))

app = FastAPI(title="VideoBrief API", version="3.0")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class AnalyseRequest(BaseModel):
    url: str = ""
    transcript: str = ""
    analysis_mode: str = "auto"


class QuestionRequest(BaseModel):
    question: str


@contextmanager
def _db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS briefs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            url TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
    """)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _save_result(result: dict) -> str:
    brief_id = str(uuid.uuid4())
    with _db() as connection:
        connection.execute(
            "INSERT INTO briefs VALUES (?, ?, ?, ?, ?, ?)",
            (brief_id, datetime.now(timezone.utc).isoformat(), result.get("title", "未命名"),
             result.get("source", "unknown"), result.get("url", ""), json.dumps(result, ensure_ascii=False)),
        )
    return brief_id


def _set_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)


def _new_job(message: str) -> dict:
    job_id = str(uuid.uuid4())
    job = {"id": job_id, "status": "queued", "stage": "queued", "progress": 0,
           "message": message, "result": None, "error": None}
    with _jobs_lock:
        _jobs[job_id] = job
    return job


def analyse_payload(payload: dict) -> dict:
    """保留供自动化测试与兼容接口调用的同步入口。"""
    return request_brief(payload)


def analyse_file(filename: str, path: Path, model_size: str = "tiny", analysis_mode: str = "auto") -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("仅支持 MP4、MOV、MKV、WebM、MP3、WAV 或 M4A。")
    rows = transcribe_local_video(path, model_size=model_size)
    result = enhance_brief(rows, make_brief(rows), mode=analysis_mode)
    result.update({"source": "local_whisper", "url": "", "filename": filename})
    return result


def _run_with_live_progress(job_id: str, function, *, start: int, ceiling: int, message: str):
    """运行阻塞任务时持续发出心跳进度，避免页面长期停在单一百分比。"""
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
    try:
        transcript = str(payload.get("transcript", "")).strip()
        if transcript:
            _set_job(job_id, status="running", stage="reading", progress=35, message="正在解析字幕文本")
            result = request_brief(payload)
        else:
            _set_job(job_id, status="running", stage="acquiring", progress=15, message="正在连接视频平台并获取字幕")
            result = _run_with_live_progress(
                job_id, lambda: request_brief(payload), start=15, ceiling=76,
                message="正在获取字幕或转写音频，请保持页面打开",
            )
        _set_job(job_id, stage="structuring", progress=85, message="正在生成结构化知识页")
        brief_id = _save_result(result)
        result["brief_id"] = brief_id
        _set_job(job_id, status="completed", stage="completed", progress=100, message="知识页已生成", result=result)
    except Exception as error:
        _set_job(job_id, status="failed", stage="failed", message="处理失败", error=str(error))


def _run_upload_job(job_id: str, filename: str, temp_path: str, model_size: str, analysis_mode: str) -> None:
    path = Path(temp_path)
    try:
        _set_job(job_id, status="running", stage="transcribing", progress=20, message="正在加载语音识别模型")
        result = _run_with_live_progress(
            job_id, lambda: analyse_file(filename, path, model_size, analysis_mode), start=20, ceiling=80,
            message="正在识别视频语音，请保持页面打开",
        )
        _set_job(job_id, stage="structuring", progress=85, message="正在生成结构化知识页")
        brief_id = _save_result(result)
        result["brief_id"] = brief_id
        _set_job(job_id, status="completed", stage="completed", progress=100, message="知识页已生成", result=result)
    except Exception as error:
        _set_job(job_id, status="failed", stage="failed", message="处理失败", error=str(error))
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/agent/status")
def get_agent_status() -> dict:
    return agent_status()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "3.0", "port": PORT}


@app.post("/api/jobs")
def create_text_job(payload: AnalyseRequest, background: BackgroundTasks) -> dict:
    if not payload.url.strip() and not payload.transcript.strip():
        raise HTTPException(400, "请提供视频链接或字幕文本。")
    if payload.analysis_mode not in {"auto", "fast", "smart"}:
        raise HTTPException(400, "分析模式仅支持 auto、fast 或 smart。")
    if len(payload.transcript.encode("utf-8")) > 2_000_000:
        raise HTTPException(413, "字幕文本超过 2 MB 限制。")
    job = _new_job("任务已创建")
    background.add_task(_run_text_job, job["id"], payload.model_dump())
    return job


@app.post("/api/jobs/upload")
async def create_upload_job(background: BackgroundTasks, media: UploadFile = File(...), model_size: str = "tiny", analysis_mode: str = "auto") -> dict:
    suffix = Path(media.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "不支持该文件格式。")
    if model_size not in {"tiny", "small", "medium"}:
        raise HTTPException(400, "转写模型仅支持 tiny、small 或 medium。")
    if analysis_mode not in {"auto", "fast", "smart"}:
        raise HTTPException(400, "分析模式仅支持 auto、fast 或 smart。")
    content = await media.read(MAX_UPLOAD + 1)
    if not content or len(content) > MAX_UPLOAD:
        raise HTTPException(413, "文件大小必须在 1 B 到 500 MB 之间。")
    temp = tempfile.NamedTemporaryFile(prefix="videobrief-", suffix=suffix, delete=False)
    temp.write(content)
    temp.close()
    job = _new_job("文件已上传")
    background.add_task(_run_upload_job, job["id"], media.filename or f"media{suffix}", temp.name, model_size, analysis_mode)
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在或服务已重启。")
        return dict(job)


@app.get("/api/history")
def history() -> list[dict]:
    with _db() as connection:
        rows = connection.execute(
            "SELECT id, created_at, title, source, url FROM briefs ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/history/{brief_id}")
def history_item(brief_id: str) -> dict:
    with _db() as connection:
        row = connection.execute("SELECT result_json FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    if not row:
        raise HTTPException(404, "历史记录不存在。")
    result = json.loads(row["result_json"])
    result["brief_id"] = brief_id
    return result


@app.post("/api/briefs/{brief_id}/ask")
def ask_brief(brief_id: str, payload: QuestionRequest) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, "请输入想查找的问题。")
    with _db() as connection:
        row = connection.execute("SELECT result_json FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    if not row:
        raise HTTPException(404, "知识页不存在。")
    return answer_from_brief(json.loads(row["result_json"]), question)


# 兼容旧前端/API，内部仍使用同步处理。
@app.post("/api/analyse")
def analyse(payload: AnalyseRequest) -> dict:
    try:
        result = request_brief(payload.model_dump())
        result["brief_id"] = _save_result(result)
        return result
    except (ValueError, RuntimeError) as error:
        raise HTTPException(400, str(error)) from error


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "videobrief-app.html")


@app.get("/videobrief-app.html")
def app_page() -> FileResponse:
    return FileResponse(ROOT / "videobrief-app.html")


if __name__ == "__main__":
    with _db():
        pass
    print(f"VideoBrief V3 listening on http://127.0.0.1:{PORT}/")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
