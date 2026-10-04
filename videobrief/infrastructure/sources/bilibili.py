"""Bilibili subtitles/audio adapter without reverse service imports."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from videobrief.application.commands import AnalyseCommand
from videobrief.application.ports import AcquisitionResult, ProgressCallback, Transcriber
from videobrief.application.transcript import seconds_to_time
from videobrief.domain.errors import SourceUnavailableError, UnsupportedSourceError

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"


def _identifier(url: str) -> tuple[str, str] | None:
    match = re.search(r"BV[a-zA-Z0-9]{10}", url)
    if match:
        return "bvid", match.group(0)
    match = re.search(r"av(\d+)", url, re.IGNORECASE)
    return ("aid", match.group(1)) if match else None


def _first_audio_url(item: dict) -> str:
    direct = item.get("baseUrl") or item.get("base_url")
    if isinstance(direct, str) and direct:
        return direct
    backups = item.get("backupUrl") or item.get("backup_url") or []
    if isinstance(backups, str):
        return backups
    if isinstance(backups, list) and backups and isinstance(backups[0], str):
        return backups[0]
    return ""


class BilibiliSource:
    kind = "bilibili"

    def __init__(self, transcriber: Transcriber, session: requests.Session | None = None) -> None:
        self._transcriber = transcriber
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})

    def _json(self, url: str, referer: str) -> dict:
        response = self._session.get(url, headers={"Referer": referer}, timeout=30)
        response.raise_for_status()
        return response.json()

    def _resolve_short_url(self, url: str) -> str:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host != "b23.tv":
            return url
        response = self._session.get(url, allow_redirects=True, timeout=30)
        response.raise_for_status()
        return response.url

    def acquire(self, command: AnalyseCommand, progress: ProgressCallback | None = None) -> AcquisitionResult:
        try:
            url = self._resolve_short_url(command.url)
            identity = _identifier(url)
            if not identity:
                raise UnsupportedSourceError("无法从链接中识别 Bilibili 视频 ID。")
            key, value = identity
            query = f"{key}={value}"
            if progress:
                progress("acquiring", 15, "正在获取 Bilibili 字幕")
            info = self._json(f"https://api.bilibili.com/x/web-interface/view?{query}", url)
            if info.get("code") != 0:
                raise SourceUnavailableError(f"Bilibili API 返回错误：{info.get('message', '未知')}", stage="acquiring")
            data = info["data"]
            aid, cid = data["aid"], data["cid"]
            player = self._json(f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}", url)
            for subtitle in player.get("data", {}).get("subtitle", {}).get("subtitles", []):
                subtitle_url = subtitle.get("subtitle_url", "")
                if not subtitle_url:
                    continue
                if subtitle_url.startswith("//"):
                    subtitle_url = "https:" + subtitle_url
                elif subtitle_url.startswith("/"):
                    subtitle_url = "https://api.bilibili.com" + subtitle_url
                try:
                    body = self._json(subtitle_url, url).get("body", [])
                except (requests.RequestException, ValueError):
                    continue
                rows = []
                for item in body:
                    text = re.sub(r"<[^>]+>", "", str(item.get("content", ""))).strip()
                    if text:
                        rows.append({"time": seconds_to_time(int(item.get("from", 0))), "body": text})
                if rows:
                    return AcquisitionResult(rows=rows, source="bilibili_subtitles", url=command.url)

            if progress:
                progress("transcribing", 25, "未找到官方字幕，正在转写音频")
            play = self._json(
                f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=16&type=&platform=web&fnver=0&fnval=4048&fourk=1",
                url,
            )
            audio_list = play.get("data", {}).get("dash", {}).get("audio", [])
            if not audio_list:
                raise SourceUnavailableError("无法获取 Bilibili 音频流。", stage="acquiring")
            audio_url = _first_audio_url(audio_list[0])
            if not audio_url:
                raise SourceUnavailableError("Bilibili 音频 URL 不可用。", stage="acquiring")
            with tempfile.TemporaryDirectory(prefix="videobrief-bili-") as folder:
                audio_path = Path(folder) / "audio.mp4"
                response = self._session.get(audio_url, headers={"Referer": "https://www.bilibili.com/"}, timeout=300, stream=True)
                response.raise_for_status()
                with audio_path.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            stream.write(chunk)
                if not audio_path.exists() or audio_path.stat().st_size == 0:
                    raise SourceUnavailableError("Bilibili 音频下载失败。", stage="acquiring")
                rows = self._transcriber.transcribe(audio_path, command.whisper_model)
            return AcquisitionResult(rows=rows, source="bilibili_audio", url=command.url)
        except (UnsupportedSourceError, SourceUnavailableError):
            raise
        except requests.RequestException as error:
            raise SourceUnavailableError(f"Bilibili 网络请求失败：{error}", stage="acquiring") from error
        except Exception as error:
            raise SourceUnavailableError(f"Bilibili 处理失败：{error}", stage="acquiring") from error
