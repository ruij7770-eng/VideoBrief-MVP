"""Video source adapters."""

from .bilibili import BilibiliSource
from .pasted import PastedTranscriptSource
from .registry import SourceRegistry, classify_url
from .upload import UploadSource
from .youtube import YouTubeSource, extract_youtube_id, yt_dlp_command

__all__ = [
    "BilibiliSource",
    "PastedTranscriptSource",
    "SourceRegistry",
    "UploadSource",
    "YouTubeSource",
    "classify_url",
    "extract_youtube_id",
    "yt_dlp_command",
]
