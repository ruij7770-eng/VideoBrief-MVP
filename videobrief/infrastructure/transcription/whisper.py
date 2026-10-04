"""Whisper transcription adapter with one process-wide model cache."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from videobrief.application.transcript import seconds_to_time, to_simplified
from videobrief.domain.errors import TranscriptionError

_models: dict[str, object] = {}
_model_lock = threading.Lock()


def get_whisper_model(size: str = "tiny"):
    if size not in {"tiny", "small", "medium"}:
        raise TranscriptionError("不支持该语音识别模型。", stage="transcribing")
    with _model_lock:
        if size not in _models:
            from faster_whisper import WhisperModel
            _models[size] = WhisperModel(size, device="cpu", compute_type="int8")
        return _models[size]


class WhisperTranscriber:
    def __init__(self, model_loader: Callable[[str], object] = get_whisper_model) -> None:
        self._model_loader = model_loader

    def transcribe(self, path: Path, model_size: str = "tiny", language: str = "zh") -> list[dict[str, Any]]:
        try:
            model = self._model_loader(model_size)
            selected_language = None if language.lower() in {"", "auto"} else language
            segments, _ = model.transcribe(str(path), vad_filter=True, language=selected_language)
            rows = []
            for segment in segments:
                text = to_simplified(str(segment.text).strip())
                if not text:
                    continue
                start, end = int(segment.start), int(segment.end)
                rows.append({"time": seconds_to_time(start), "body": text, "seconds": start, "end_seconds": max(start, end)})
        except TranscriptionError:
            raise
        except Exception as error:
            raise TranscriptionError("语音识别失败，请确认文件可播放或更换模型。", stage="transcribing") from error
        if not rows:
            raise TranscriptionError("未能从该视频识别出语音内容。", stage="transcribing")
        return rows
