"""Select exactly one source adapter for an AnalyseCommand."""
from __future__ import annotations

from urllib.parse import urlparse

from videobrief.application.commands import AnalyseCommand
from videobrief.application.ports import SourceAdapter
from videobrief.domain.errors import UnsupportedSourceError
from videobrief.infrastructure.transcription import WhisperTranscriber

from .bilibili import BilibiliSource
from .pasted import PastedTranscriptSource
from .upload import UploadSource
from .youtube import YouTubeSource, extract_youtube_id

_BILIBILI_HOSTS = {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"}


def classify_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in _BILIBILI_HOSTS:
        return "bilibili"
    if extract_youtube_id(url):
        return "youtube"
    return "unsupported"


class SourceRegistry:
    def __init__(self, pasted: SourceAdapter, upload: SourceAdapter, bilibili: SourceAdapter, youtube: SourceAdapter) -> None:
        self._pasted = pasted
        self._upload = upload
        self._bilibili = bilibili
        self._youtube = youtube

    @classmethod
    def default(cls) -> "SourceRegistry":
        transcriber = WhisperTranscriber()
        return cls(PastedTranscriptSource(), UploadSource(transcriber), BilibiliSource(transcriber), YouTubeSource())

    def resolve(self, command: AnalyseCommand) -> SourceAdapter:
        if command.transcript:
            return self._pasted
        if command.upload_path:
            return self._upload
        kind = classify_url(command.url)
        if kind == "bilibili":
            return self._bilibili
        if kind == "youtube":
            return self._youtube
        raise UnsupportedSourceError("目前仅支持 Bilibili 或 YouTube 视频链接。")
