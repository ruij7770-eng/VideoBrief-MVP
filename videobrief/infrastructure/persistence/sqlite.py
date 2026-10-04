"""SQLite Brief repository with non-destructive history projection."""
from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from videobrief.application.compatibility import normalize_brief_for_read
from videobrief.domain.errors import BriefNotFoundError


class SQLiteBriefRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self.connection() as connection:
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

    def save(self, brief: dict) -> str:
        brief_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO briefs (id, created_at, title, source, url, result_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    brief_id,
                    datetime.now(timezone.utc).isoformat(),
                    str(brief.get("title") or "未命名"),
                    str(brief.get("source") or "unknown"),
                    str(brief.get("url") or ""),
                    json.dumps(brief, ensure_ascii=False),
                ),
            )
        return brief_id

    def get_raw(self, brief_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute("SELECT result_json FROM briefs WHERE id = ?", (brief_id,)).fetchone()
        if not row:
            raise BriefNotFoundError("历史记录不存在。")
        return json.loads(row["result_json"])

    def get(self, brief_id: str) -> dict:
        result = normalize_brief_for_read(self.get_raw(brief_id))
        result["brief_id"] = brief_id
        return result

    def list_recent(self, limit: int = 30) -> list[dict]:
        safe_limit = max(1, min(int(limit), 100))
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id, created_at, title, source, url FROM briefs ORDER BY created_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def raw_snapshot(self) -> list[dict]:
        """Read-only rows used by migration audits; never rewrites payloads."""
        with self.connection() as connection:
            rows = connection.execute("SELECT id, result_json FROM briefs ORDER BY created_at").fetchall()
        return [{"id": row["id"], "result": json.loads(row["result_json"])} for row in rows]
