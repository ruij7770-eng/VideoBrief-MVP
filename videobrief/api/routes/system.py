"""System and provider status routes."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict:
    container = request.app.state.container
    return {"status": "ok", "version": "4.0", "schema_version": 4, "port": container.settings.port}


@router.get("/agent/status")
def get_agent_status(request: Request) -> dict:
    return request.app.state.container.settings.agent_status()
