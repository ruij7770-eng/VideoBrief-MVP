"""Central runtime settings and public provider status."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    db_path: Path = PROJECT_ROOT / "videobrief.db"
    port: int = 12000
    max_upload_bytes: int = 500 * 1024 * 1024
    max_concurrent_jobs: int = 2
    upload_dir: Path = PROJECT_ROOT / "uploads"
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            db_path=Path(os.getenv("VIDEOBRIEF_DB_PATH", str(PROJECT_ROOT / "videobrief.db"))),
            port=int(os.getenv("VIDEOBRIEF_PORT", "12000")),
            max_upload_bytes=int(os.getenv("VIDEOBRIEF_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024))),
            max_concurrent_jobs=int(os.getenv("VIDEOBRIEF_MAX_CONCURRENT_JOBS", "2")),
            upload_dir=Path(os.getenv("VIDEOBRIEF_UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))),
            llm_provider=os.getenv("VIDEOBRIEF_LLM_PROVIDER", "deepseek"),
            llm_base_url=os.getenv("VIDEOBRIEF_LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            llm_model=os.getenv("VIDEOBRIEF_LLM_MODEL", "deepseek-chat"),
            llm_api_key=os.getenv("VIDEOBRIEF_LLM_API_KEY", "").strip(),
        )

    def agent_status(self) -> dict[str, object]:
        return {
            "configured": bool(self.llm_api_key),
            "provider": self.llm_provider,
            "model": self.llm_model,
            "base_url": self.llm_base_url,
        }
