"""Pasted transcript source adapter."""
from __future__ import annotations

from videobrief.application.commands import AnalyseCommand
from videobrief.application.ports import AcquisitionResult, ProgressCallback
from videobrief.application.transcript import parse_timestamped_transcript
from videobrief.domain.errors import InputValidationError


class PastedTranscriptSource:
    kind = "pasted_transcript"

    def acquire(self, command: AnalyseCommand, progress: ProgressCallback | None = None) -> AcquisitionResult:
        if progress:
            progress("acquiring", 20, "正在解析字幕文本")
        rows = parse_timestamped_transcript(command.transcript)
        if not rows and command.transcript:
            rows = [{"time": "00:00", "body": command.transcript}]
        if not rows:
            raise InputValidationError("字幕文本为空。")
        return AcquisitionResult(rows=rows, source=self.kind)
