"""VideoBrief application services and ports."""

from .compatibility import detect_brief_generation, normalize_brief_for_read

__all__ = ["detect_brief_generation", "normalize_brief_for_read"]
