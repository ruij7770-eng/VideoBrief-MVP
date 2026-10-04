"""Transcription infrastructure."""

from .whisper import WhisperTranscriber, get_whisper_model

__all__ = ["WhisperTranscriber", "get_whisper_model"]
