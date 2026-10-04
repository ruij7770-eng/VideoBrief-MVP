"""Uploaded local media source adapter."""
from __future__ import annotations

from videobrief.application.commands import AnalyseCommand
from videobrief.application.ports import AcquisitionResult, ProgressCallback, Transcriber
from videobrief.domain.errors import InputValidationError


class UploadSource:
    kind = "local_whisper"

    def __init__(self, transcriber: Transcriber) -> None:
        self._transcriber = transcriber

    def acquire(self, command: AnalyseCommand, progress: ProgressCallback | None = None) -> AcquisitionResult:
        if not command.upload_path:
            raise InputValidationError("未提供本地音视频文件。")
        if progress:
            progress("transcribing", 20, "正在识别视频语音")
        rows = self._transcriber.transcribe(command.upload_path, command.whisper_model)
        return AcquisitionResult(rows=rows, source=self.kind, filename=command.original_filename)
