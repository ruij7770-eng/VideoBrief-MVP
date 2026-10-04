"""YouTube subtitle adapter with a tested API fallback."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from videobrief.application.commands import AnalyseCommand
from videobrief.application.ports import AcquisitionResult, ProgressCallback
from videobrief.application.transcript import parse_timestamped_transcript, seconds_to_time
from videobrief.config import PROJECT_ROOT
from videobrief.domain.errors import SourceUnavailableError, UnsupportedSourceError


def extract_youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        match = re.match(r"^/(?:embed|shorts)/([^/?]+)", parsed.path)
        return match.group(1) if match else None
    return None


def yt_dlp_command() -> str:
    discovered = shutil.which("yt-dlp")
    candidates = [
        Path(discovered) if discovered else None,
        PROJECT_ROOT / ".venv" / "Scripts" / "yt-dlp.exe",
        Path.home() / ".local" / "bin" / "yt-dlp",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
    raise SourceUnavailableError("未找到可执行的 yt-dlp，请先安装项目依赖。", stage="acquiring")


def _default_transcript_fetch(video_id: str):
    from youtube_transcript_api import YouTubeTranscriptApi
    return YouTubeTranscriptApi().fetch(video_id, languages=["zh-Hans", "zh-CN", "zh", "en"])


class YouTubeSource:
    kind = "youtube_subtitles"

    def __init__(self, runner: Callable = subprocess.run, transcript_fetcher: Callable = _default_transcript_fetch) -> None:
        self._runner = runner
        self._transcript_fetcher = transcript_fetcher

    def acquire(self, command: AnalyseCommand, progress: ProgressCallback | None = None) -> AcquisitionResult:
        video_id = extract_youtube_id(command.url)
        if not video_id:
            raise UnsupportedSourceError("无法识别该 YouTube 链接。")
        if progress:
            progress("acquiring", 15, "正在获取 YouTube 字幕")
        cli_error = "未找到可用字幕。"
        with tempfile.TemporaryDirectory(prefix="videobrief-") as folder:
            template = str(Path(folder) / "subtitle.%(ext)s")
            try:
                completed = self._runner(
                    [yt_dlp_command(), "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "zh.*,en.*", "--sub-format", "vtt", "-o", template, command.url],
                    capture_output=True, text=True, timeout=120,
                )
                files = list(Path(folder).glob("*.vtt"))
                if completed.returncode == 0 and files:
                    rows = parse_timestamped_transcript(files[0].read_text(encoding="utf-8", errors="replace"))
                    if rows:
                        return AcquisitionResult(rows=rows, source=self.kind, url=command.url)
                if completed.stderr.strip():
                    cli_error = completed.stderr.strip().splitlines()[-1]
            except (FileNotFoundError, OSError, subprocess.SubprocessError) as error:
                cli_error = str(error)
        try:
            transcript = self._transcript_fetcher(video_id)
            rows = [{"time": seconds_to_time(int(item.start)), "body": item.text} for item in transcript if str(item.text).strip()]
            if rows:
                return AcquisitionResult(rows=rows, source=self.kind, url=command.url)
        except Exception as error:
            raise SourceUnavailableError(f"无法自动提取字幕。yt-dlp: {cli_error}; transcript API: {error}", stage="acquiring") from error
        raise SourceUnavailableError(f"无法自动提取字幕：{cli_error}", stage="acquiring")
