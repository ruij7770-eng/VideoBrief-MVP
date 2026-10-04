"""Ports at replaceable application boundaries."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .commands import AnalyseCommand

ProgressCallback = Callable[[str, int, str], None]


@dataclass
class AcquisitionResult:
    rows: list[dict[str, Any]]
    source: str
    url: str = ""
    filename: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    kind: str

    def acquire(self, command: AnalyseCommand, progress: ProgressCallback | None = None) -> AcquisitionResult: ...


class SourceResolver(Protocol):
    def resolve(self, command: AnalyseCommand) -> SourceAdapter: ...


class Transcriber(Protocol):
    def transcribe(self, path: Path, model_size: str = "tiny") -> list[dict[str, Any]]: ...


class SmartAnalyzer(Protocol):
    def enhance(self, rows: list[dict[str, Any]], brief: dict[str, Any], mode: str) -> dict[str, Any]: ...


class BriefRepository(Protocol):
    def save(self, brief: dict[str, Any]) -> str: ...
    def get(self, brief_id: str) -> dict[str, Any]: ...
    def list_recent(self, limit: int = 30) -> list[dict[str, Any]]: ...


class JobRepository(Protocol):
    def create(self, message: str) -> dict[str, Any]: ...
    def update(self, job_id: str, **values: Any) -> dict[str, Any]: ...
    def get(self, job_id: str) -> dict[str, Any] | None: ...
