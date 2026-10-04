"""Pure transcript normalization helpers."""
from __future__ import annotations

import re

_converter = None


def to_simplified(text: str) -> str:
    global _converter
    if not text:
        return text
    if _converter is None:
        from opencc import OpenCC
        _converter = OpenCC("t2s")
    return _converter.convert(text)


def _time_label(h: str, m: str, s: str) -> str:
    hours, minutes, seconds = int(h or 0), int(m), int(s)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def parse_timestamped_transcript(source: str) -> list[dict[str, str]]:
    lines = source.replace("\ufeff", "").splitlines()
    rows: list[dict[str, str]] = []
    current_time: str | None = None
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_time, current_text
        body = re.sub(r"<[^>]+>", "", " ".join(current_text)).strip()
        body = re.sub(r"\s+", " ", body)
        if current_time and body and (not rows or rows[-1]["body"] != body):
            rows.append({"time": current_time, "body": body})
        current_time, current_text = None, []

    stamp = re.compile(r"(?:(\d{1,2}):)?(\d{2}):(\d{2})(?:[.,]\d+)?\s+-->")
    bracket_stamp = re.compile(r"^\[(?:(\d{1,2}):)?(\d{2}):(\d{2})\]\s*(.*)$")
    for raw in lines:
        line = raw.strip()
        bracket = bracket_stamp.match(line)
        if bracket:
            flush()
            current_time = _time_label(*bracket.groups()[:3])
            if bracket.group(4):
                current_text.append(bracket.group(4))
            continue
        match = stamp.search(line)
        if match:
            flush()
            current_time = _time_label(*match.groups())
        elif not line:
            flush()
        elif current_time and not line.isdigit() and line != "WEBVTT" and not line.startswith(("NOTE", "Kind:", "Language:")):
            current_text.append(line)
    flush()
    return rows


def rows_to_text(rows: list[dict[str, str]]) -> str:
    return "\n".join(f"[{row['time']}] {row['body']}" for row in rows)


def time_to_seconds(value: str) -> int:
    try:
        parts = [int(part) for part in value.split(":")]
    except (AttributeError, TypeError, ValueError):
        return 0
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def seconds_to_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
