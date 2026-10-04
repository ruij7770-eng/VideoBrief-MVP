"""Compatibility facade for the modular Bilibili source adapter."""
from videobrief.application.commands import AnalyseCommand
from videobrief.infrastructure.sources.bilibili import BilibiliSource
from videobrief.infrastructure.transcription import WhisperTranscriber


def bilibili_transcribe(url: str, model_size: str = "tiny") -> list[dict]:
    adapter = BilibiliSource(WhisperTranscriber())
    return adapter.acquire(AnalyseCommand(url=url, whisper_model=model_size)).rows


__all__ = ["bilibili_transcribe"]
