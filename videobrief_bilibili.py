"""Bilibili 字幕 / 音频提取模块。

策略：
1. 先查官方字幕接口（最快）
2. 没有字幕则下载音频，用 Whisper 本地转写
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import requests

_BILI_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _BILI_UA})


def _bvid_from(url: str) -> str | None:
    m = re.search(r"(?:BV[a-zA-Z0-9]{10}|av\d+)", url)
    return m.group(0) if m else None


def _api(path: str, referer: str = "") -> dict:
    headers = {"Referer": referer or "https://www.bilibili.com/"}
    r = _SESSION.get(path, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def bilibili_transcribe(url: str) -> list[dict[str, str]]:
    """从 Bilibili 视频获取带时间戳的字幕/转写条目。"""
    identifier = _bvid_from(url)
    if not identifier:
        raise ValueError("无法从链接中识别 Bilibili 视频 ID。")

    # 1. 获取 aid / cid
    info = _api(f"https://api.bilibili.com/x/web-interface/view?bvid={identifier}", referer=url)
    if info.get("code") != 0:
        raise RuntimeError(f"Bilibili API 返回错误：{info.get('message', '未知')}")
    data = info["data"]
    aid, cid = data["aid"], data["cid"]

    # 2. 尝试官方字幕
    player = _api(f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}", referer=url)
    subtitles = player.get("data", {}).get("subtitle", {}).get("subtitles", [])

    for sub in subtitles:
        sub_url = sub.get("subtitle_url", "")
        if not sub_url:
            continue
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        elif sub_url.startswith("/"):
            sub_url = "https:" + sub_url
        try:
            content = _api(sub_url, referer=url)
        except Exception:
            continue
        body_raw = content.get("body", [])
        if not body_raw:
            continue
        rows = []
        for item in body_raw:
            seconds = int(item.get("from", 0))
            time = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60:02d}:{seconds % 60:02d}"
            text = re.sub(r"<[^>]+>", "", item.get("content", "")).strip()
            if text:
                rows.append({"time": time, "body": text})
        if rows:
            return rows

    # 3. 无字幕 → 下载音频流并 Whisper 转写
    play = _api(
        f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=16&type=&platform=web&fnver=0&fnval=4048&fourk=1",
        referer=url)
    dash = play.get("data", {}).get("dash", {})
    audio_list = dash.get("audio", [{}])
    if not audio_list:
        raise RuntimeError("无法获取 Bilibili 音频流。")

    audio_url = audio_list[0].get("baseUrl") or audio_list[0].get("backupUrl", [None])[0]
    if not audio_url:
        raise RuntimeError("Bilibili 音频 URL 不可用。")

    with tempfile.TemporaryDirectory(prefix="videobrief-bili-") as folder:
        audio_path = Path(folder) / "audio.mp4"
        # 下载音频
        resp = _SESSION.get(audio_url, headers={"Referer": "https://www.bilibili.com/"}, timeout=300, stream=True)
        resp.raise_for_status()
        with open(audio_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        if audio_path.stat().st_size == 0:
            raise RuntimeError("Bilibili 音频下载失败。")

        # Whisper 转写（复用已加载模型）
        from videobrief_service import get_whisper_model
        model = get_whisper_model("tiny")
        segments, _ = model.transcribe(str(audio_path), vad_filter=True, language="zh")
        rows = []
        for segment in segments:
            seconds = int(segment.start)
            time = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60:02d}:{seconds % 60:02d}"
            text = segment.text.strip()
            if text:
                rows.append({"time": time, "body": text})
        if rows:
            return rows
        raise RuntimeError("Bilibili 音频转写未产出内容。")
