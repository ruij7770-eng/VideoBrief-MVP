"""Legacy function signatures backed by modular source adapters."""
from __future__ import annotations

from pathlib import Path

from videobrief.application.commands import AnalyseCommand
from videobrief.infrastructure.transcription import WhisperTranscriber, get_whisper_model

from .bilibili import BilibiliSource
from .registry import classify_url
from .youtube import YouTubeSource, extract_youtube_id, yt_dlp_command


def source_kind(value: str) -> str:
    kind = classify_url(value)
    return kind if kind != "unsupported" else "local"


def fetch_youtube_transcript(url: str) -> list[dict]:
    return YouTubeSource().acquire(AnalyseCommand(url=url)).rows


def fetch_bilibili_transcript(url: str, model_size: str = "tiny") -> list[dict]:
    transcriber = WhisperTranscriber()
    return BilibiliSource(transcriber).acquire(AnalyseCommand(url=url, whisper_model=model_size)).rows


def transcribe_local_video(path: Path, model_size: str = "tiny") -> list[dict]:
    return WhisperTranscriber().transcribe(Path(path), model_size)


__all__ = [
    "extract_youtube_id", "fetch_bilibili_transcript", "fetch_youtube_transcript",
    "get_whisper_model", "source_kind", "transcribe_local_video", "yt_dlp_command",
]
