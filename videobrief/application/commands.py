"""Application commands validated before external work begins."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from videobrief.domain.errors import InputValidationError

AnalysisMode = Literal["auto", "fast", "smart"]
WhisperModel = Literal["tiny", "small", "medium"]


@dataclass(frozen=True)
class AnalyseCommand:
    url: str = ""
    transcript: str = ""
    upload_path: Path | None = None
    original_filename: str = ""
    analysis_mode: AnalysisMode = "auto"
    whisper_model: WhisperModel = "tiny"
    language: str = "zh"

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", self.url.strip())
        object.__setattr__(self, "transcript", self.transcript.strip())
        active = sum(bool(value) for value in (self.url, self.transcript, self.upload_path))
        if active != 1:
            raise InputValidationError("请且仅提供一种输入：视频链接、字幕文本或本地文件。")
        if self.analysis_mode not in {"auto", "fast", "smart"}:
            raise InputValidationError("分析模式仅支持 auto、fast 或 smart。")
        if self.whisper_model not in {"tiny", "small", "medium"}:
            raise InputValidationError("转写模型仅支持 tiny、small 或 medium。")
        if not self.language or len(self.language) > 10:
            raise InputValidationError("转写语言无效。")
