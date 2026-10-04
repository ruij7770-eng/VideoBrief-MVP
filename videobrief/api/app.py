"""VideoBrief FastAPI application factory."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from videobrief.domain.errors import (
    AnalysisUnavailableError,
    JobCapacityError,
    BriefNotFoundError,
    InputValidationError,
    JobNotFoundError,
    SourceUnavailableError,
    TranscriptionError,
    UnsupportedSourceError,
    UploadTooLargeError,
    VideoBriefError,
)

from .dependencies import ApplicationContainer
from .routes import briefs, jobs, system

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
WEB_ROOT = PACKAGE_ROOT / "web"


def _cleanup_stale_uploads(upload_dir: Path, max_age_seconds: int = 24 * 3600) -> int:
    """Remove uploads left behind by a previous process; never follows links."""
    if not upload_dir.is_dir():
        return 0
    deadline = time.time() - max_age_seconds
    removed = 0
    for path in upload_dir.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < deadline:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _status_for(error: VideoBriefError) -> int:
    if isinstance(error, UploadTooLargeError):
        return 413
    if isinstance(error, (BriefNotFoundError, JobNotFoundError)):
        return 404
    if isinstance(error, JobCapacityError):
        return 429
    if isinstance(error, (InputValidationError, UnsupportedSourceError)):
        return 400
    if isinstance(error, (SourceUnavailableError, TranscriptionError, AnalysisUnavailableError)):
        return 502
    return 500


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    app = FastAPI(title="VideoBrief API", version="4.0")
    app.state.container = container or ApplicationContainer.default()
    _cleanup_stale_uploads(app.state.container.settings.upload_dir)
    app.include_router(system.router)
    app.include_router(jobs.router)
    app.include_router(briefs.router)

    @app.exception_handler(VideoBriefError)
    async def application_error(_request: Request, error: VideoBriefError) -> JSONResponse:
        payload = {
            "detail": error.message,
            "error": error.to_dict(),
        }
        return JSONResponse(payload, status_code=_status_for(error))

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        message = "请求参数格式不正确。"
        return JSONResponse(
            {"detail": message, "error": {"code": "INVALID_REQUEST", "message": message, "retryable": False, "stage": "request"}},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _error: Exception) -> JSONResponse:
        message = "服务处理请求时发生内部错误。"
        return JSONResponse(
            {"detail": message, "error": {"code": "INTERNAL_ERROR", "message": message, "retryable": False, "stage": "failed"}},
            status_code=500,
        )

    assets = WEB_ROOT / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        target = WEB_ROOT / "index.html"
        return FileResponse(target if target.exists() else PROJECT_ROOT / "videobrief-app.html")

    @app.get("/videobrief-app.html")
    def compatibility_page() -> FileResponse:
        target = WEB_ROOT / "index.html"
        return FileResponse(target if target.exists() else PROJECT_ROOT / "videobrief-app.html")

    return app
