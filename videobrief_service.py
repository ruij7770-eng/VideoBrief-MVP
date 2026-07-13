"""VideoBrief 关键词分割、语义分组与结构化生成工具。

将转写片段拆分成语义密集、时间合理的章节，并提取标题、要点与结论，
供前端直接渲染为理解页。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from videobrief_agent import enhance_brief

# ── URL 识别 ──────────────────────────────────────────────

_converter = None
_whisper_models: dict[str, object] = {}
_whisper_lock = threading.Lock()


def to_simplified(text: str) -> str:
    """将转写输出统一转换为简体中文（Whisper 常返回繁体）。"""
    global _converter
    if not text:
        return text
    if _converter is None:
        from opencc import OpenCC
        _converter = OpenCC("t2s")
    return _converter.convert(text)


def extract_youtube_id(url: str) -> str | None:
    """从标准/短链/嵌入链接中提取 YouTube 视频 ID。"""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        match = re.match(r"^/(?:embed|shorts)/([^/?]+)", parsed.path)
        if match:
            return match.group(1)
    return None


def source_kind(value: str) -> str:
    """根据输入值判断来源类型（不发起网络请求）。"""
    parsed = urlparse(value)
    host = parsed.netloc.lower().removeprefix("www.")
    if host.endswith("bilibili.com") or host == "b23.tv":
        return "bilibili"
    if extract_youtube_id(value):
        return "youtube"
    return "local"

# ── 字幕解析 ──────────────────────────────────────────────

def _time_label(h: str, m: str, s: str) -> str:
    hours, minutes, seconds = int(h or 0), int(m), int(s)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def parse_timestamped_transcript(source: str) -> list[dict[str, str]]:
    """解析 WebVTT / SRT / [HH:]MM:SS 正文格式，返回带时间戳的条目列表。"""
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
    return "\n".join(f"[{r['time']}] {r['body']}" for r in rows)


def time_to_seconds(value: str) -> int:
    """将 MM:SS 或 HH:MM:SS 转换为秒。"""
    try:
        parts = [int(part) for part in value.split(":")]
    except (TypeError, ValueError):
        return 0
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def get_whisper_model(size: str = "tiny"):
    """进程内复用 Whisper 模型，避免每个任务重复加载。"""
    with _whisper_lock:
        if size not in _whisper_models:
            from faster_whisper import WhisperModel
            _whisper_models[size] = WhisperModel(size, device="cpu", compute_type="int8")
        return _whisper_models[size]


def yt_dlp_command() -> str:
    return shutil.which("yt-dlp") or str(Path.home() / ".local" / "bin" / "yt-dlp")

# ── 来源获取 ──────────────────────────────────────────────

def fetch_youtube_transcript(url: str) -> list[dict[str, str]]:
    """yt-dlp 优先提取字幕，失败时回退到 youtube-transcript-api。"""
    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("目前自动提取仅支持 YouTube 链接。")
    yt_dlp_error = "未找到可用字幕。"
    with tempfile.TemporaryDirectory(prefix="videobrief-") as folder:
        template = str(Path(folder) / "subtitle.%(ext)s")
        command = [yt_dlp_command(), "--skip-download", "--write-subs", "--write-auto-subs",
                   "--sub-langs", "zh.*,en.*", "--sub-format", "vtt", "-o", template, url]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        vtts = list(Path(folder).glob("*.vtt"))
        if completed.returncode == 0 and vtts:
            rows = parse_timestamped_transcript(vtts[0].read_text(encoding="utf-8", errors="replace"))
            if rows:
                return rows
        yt_dlp_error = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else yt_dlp_error
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["zh-Hans", "zh-CN", "zh", "en"])
        rows = []
        for item in transcript:
            seconds = int(item.start)
            time = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60:02d}:{seconds % 60:02d}"
            rows.append({"time": time, "body": item.text})
        if rows:
            return rows
    except Exception as api_error:
        raise RuntimeError(f"无法自动提取字幕。yt-dlp: {yt_dlp_error}; transcript API: {api_error}") from api_error
    raise RuntimeError(f"无法自动提取字幕：{yt_dlp_error}")


def fetch_bilibili_transcript(url: str) -> list[dict[str, str]]:
    """通过 Bilibili API 获取音频并本地转写。"""
    from videobrief_bilibili import bilibili_transcribe
    rows = bilibili_transcribe(url)
    if rows:
        return rows
    raise RuntimeError("Bilibili 自动提取失败。该视频可能不提供公开字幕；你可以下载后在此页面直接上传，系统会做本地语音识别。")


def transcribe_local_video(path: Path, model_size: str = "tiny") -> list[dict[str, str]]:
    """使用缓存的本机 faster-whisper 模型对音视频做语音识别。"""
    model = get_whisper_model(model_size)
    segments, _ = model.transcribe(str(path), vad_filter=True, language="zh")
    rows = []
    for segment in segments:
        seconds = int(segment.start)
        time = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60:02d}:{seconds % 60:02d}"
        text = segment.text.strip()
        if text:
            rows.append({"time": time, "body": text})
    if not rows:
        raise RuntimeError("未能从该视频识别出语音内容。")
    return rows


# ── 关键词提取 & 语义分组 ─────────────────────────────────

# 中文句子结束标记（包括英文句号借用）
_SENT_END = re.compile(r"[。！？!?\n]")
# 可用于提取标题的关键词：包含"是/定义/概念/核心/关键/第一步/第二步/总结/如何"等内容
_TOPIC_MARKER = re.compile(r"^(?:如何|什么|为什么|怎么|第[一二三四五六七八九十\d]+[步章节部]|核心|关键|重点|总结|最后|首先|接下来|然后是|再来看)")

_NUM_CLEAN = re.compile(r"^(?:第[一二三四五六七八九十\d]+(?:部分|步|章|节|门)?(?:是)?)[：:，,]*")
_PREFIX_CLEAN = re.compile(r"^(?:接下来|最后|今天|我们|那[么么]|然后|再来看|首先|总结|就是|而|但|和|与|更是)[：:，,]*")
_FILLER_CLEAN = re.compile(r"^(?:呃|啊|嗯|哦|这个|那个|就是|就是说|对吧|对不对|其实是|其实是说)+")
_LEADING_VERB = re.compile(r"^(?:是|就是|其实是)[：:，,]*")

_HAN_PAT = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")

def _clean_sentence(s: str) -> str:
    s = s.strip()
    s = _NUM_CLEAN.sub("", s)
    s = _PREFIX_CLEAN.sub("", s)
    s = _FILLER_CLEAN.sub("", s)
    s = _LEADING_VERB.sub("", s)
    # 去掉开头和结尾的标点、空白
    s = re.sub(r"^[\W_]+", "", s)
    s = re.sub(r"[\W_]+$", "", s)
    return s.strip()

def _extract_title(text: str, length: int = 24) -> str:
    """从一段中文文本中提取一个紧凑的章节标题。"""
    # 按主要标点拆分
    clauses = [c.strip() for c in _SENT_END.split(text) if c.strip()]
    if not clauses:
        clauses = [text]
    # 优先选包含"是"、"核心"、"关键"、"如何"等词的第一句
    for clause in clauses:
        clean = _clean_sentence(clause)
        if not clean:
            continue
        if len(clean) <= length + 4:
            return clean[:length] + ("…" if len(clean) > length else "")
    # 选最短且包含汉字的句子
    short = sorted([c for c in clauses if _HAN_PAT.search(c)], key=len)
    if short:
        clean = _clean_sentence(short[0])
        return clean[:length] + ("…" if len(clean) > length else "")
    clean = _clean_sentence(clauses[0])
    return clean[:length] + ("…" if len(clean) > length else "")


def _extract_summary(text: str, length: int = 120) -> str:
    """提取一句结论。优先取带'总结'的句子、或最后一个实质句。"""
    # 把某段文本按句号拆开
    parts = [p.strip() for p in _SENT_END.split(text) if p.strip()]
    if not parts:
        return _clean_sentence(text)[:length]
    # 找"总结"、"核心"、"一句话" — 取它之后的一句
    for i, p in enumerate(parts):
        if re.search(r"总结|核心结论|一句话概括|综上|最终", p):
            # 如果"总结"后面有内容，取后面；否则取它本身去掉"总结"前缀
            remain = re.sub(r"^总结[：:，,]*", "", p).strip()
            if remain:
                c = _clean_sentence(remain)
                return c[:length] + ("…" if len(c) > length else "")
    # fallback: 取最后一个带汉字的句子
    for p in reversed(parts):
        if _HAN_PAT.search(p):
            c = _clean_sentence(p)
            return c[:length] + ("…" if len(c) > length else "")
    c = _clean_sentence(parts[-1])
    return c[:length] + ("…" if len(c) > length else "")


def _smart_chunks(rows: list[dict[str, str]], target_chapters: int = 7, max_chapters: int = 20) -> list[list[dict[str, str]]]:
    """将转写条目按语义和时间距离分组合并。

    策略：首先按句号/换行等自然边界聚合临近片段，再按每段内容量（字数）合并，
    使每章覆盖约 60-150 个汉字，目标控制在 target_chapters 章附近。
    """
    if not rows:
        return []
    if len(rows) <= target_chapters:
        return [[r] for r in rows]

    # 第一阶段：合并时间相邻且属于同一句的片段
    merged: list[dict[str, str]] = []
    buffer_parts: list[str] = []
    buffer_sources: list[dict] = []
    buf_time = rows[0]["time"]
    for row in rows:
        if not buffer_sources:
            buf_time = row["time"]
        body = row["body"]
        buffer_parts.append(body)
        buffer_sources.append(row)
        buffer = "".join(buffer_parts)
        # 遇到句子结束标记就 flush，同时保留构成该语义句的原始证据。
        if _SENT_END.search(body) and len(buffer) >= 15:
            merged.append({"time": buf_time, "body": buffer.strip(), "source_rows": list(buffer_sources)})
            buffer_parts = []
            buffer_sources = []
    if buffer_sources:
        merged.append({"time": buf_time, "body": "".join(buffer_parts).strip(), "source_rows": list(buffer_sources)})

    if len(merged) <= target_chapters:
        return [[m] for m in merged]

    # 第二阶段：按字数分组，每章 80-160 字
    target = max(target_chapters, min(max_chapters, len(merged) // 2))
    total_chars = sum(len(m["body"]) for m in merged)
    chars_per_chapter = max(60, min(160, total_chars // target))
    chunks: list[list[dict[str, str]]] = []
    current_chunk: list[dict[str, str]] = []
    current_chars = 0
    for m in merged:
        mlen = len(m["body"])
        if current_chunk and current_chars + mlen > chars_per_chapter * 1.8:
            chunks.append(current_chunk)
            current_chunk = [m]
            current_chars = mlen
        else:
            current_chunk.append(m)
            current_chars += mlen
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _content_type(text: str) -> str:
    scores = {
        "tutorial": len(re.findall(r"步骤|第一步|第二步|然后|点击|打开|设置|安装|配置|运行|操作|教程|演示", text)),
        "interview": len(re.findall(r"采访|嘉宾|主持人|您觉得|怎么看|对话", text)),
        "lecture": len(re.findall(r"概念|定义|原理|课程|这一章|知识点|理论", text)),
        "review": len(re.findall(r"优点|缺点|测评|对比|价格|推荐|体验|评测", text)),
        "commentary": len(re.findall(r"评论|事实|观点|我认为|争议|推测|不确定|尚未|可能", text)),
    }
    kind, score = max(scores.items(), key=lambda item: item[1])
    return kind if score else "general"


def _fingerprint(text: str, duration_seconds: int, chapters: list[dict], content_type: str) -> dict:
    minutes = max(duration_seconds / 60, 1)
    chars_per_minute = len(text) / minutes
    density = "高" if chars_per_minute >= 180 else "中" if chars_per_minute >= 90 else "低"
    labels = {"tutorial": "操作教程", "interview": "访谈对话", "lecture": "知识讲解", "review": "评测对比", "commentary": "观点评论", "general": "综合内容"}
    focus = [chapter["title"] for chapter in chapters[:3]]
    return {
        "type_label": labels[content_type],
        "information_density": density,
        "recommended_path": "先读核心观点，再按需查看章节证据" if chapters else "阅读核心结论",
        "focus": focus,
    }


def _local_content_model(content_type: str, chapters: list[dict]) -> dict:
    template = content_type if content_type in {"tutorial", "interview", "review", "lecture", "commentary"} else "lecture"
    items = []
    for index, chapter in enumerate(chapters[:12]):
        text = f"{chapter.get('title', '')} {chapter.get('body', '')}"
        if template == "tutorial":
            role = "goal" if index == 0 else "result" if index == len(chapters) - 1 and re.search(r"总结|完成|结果", text) else "pitfall" if re.search(r"不要|避免|错误|注意|阻力|失败", text) else "parameter" if re.search(r"参数|字段|设置|配置", text) else "step"
        elif template == "interview":
            role = "topic" if index == 0 else "disagreement" if re.search(r"分歧|不同意|但是|争议", text) else "speaker_position" if re.search(r"认为|表示|观点|主张", text) else "argument"
        elif template == "review":
            role = "subject" if index == 0 else "pro" if re.search(r"优点|优势|值得", text) else "con" if re.search(r"缺点|不足|问题", text) else "verdict" if re.search(r"结论|推荐|适合", text) else "criterion"
        elif template == "commentary":
            role = "topic" if index == 0 else "uncertainty" if re.search(r"可能|尚未|不确定|未知", text) else "controversy" if re.search(r"争议|分歧|反对", text) else "opinion" if re.search(r"认为|观点|应该|主张", text) else "fact"
        else:
            role = "central_question" if index == 0 else "example" if re.search(r"例如|比如|案例", text) else "relationship" if re.search(r"因此|导致|关系|因为|所以", text) else "conclusion" if index == len(chapters) - 1 and re.search(r"结论|总结", text) else "concept"
        evidence = chapter.get("evidence", [])[:2]
        if not evidence:
            continue
        items.append({
            "role": role,
            "title": chapter.get("title", "内容要点"),
            "detail": (chapter.get("points") or [chapter.get("body", "")])[0],
            "time": evidence[0]["time"],
            "seconds": evidence[0]["seconds"],
            "evidence_ids": [item["evidence_id"] for item in evidence],
            "evidence": evidence,
            "audit_status": "deterministic",
        })
    return {"template": template, "items": items}


def _content_map(rows: list[dict[str, str]], chapters: list[dict], summary: str) -> list[dict]:
    text = " ".join(row["body"] for row in rows)
    if re.search(r"问题|失败|困难|为什么|如何", text):
        first_kind = "问题"
    else:
        first_kind = "主题"
    nodes = [{"kind": first_kind, "title": chapters[0]["title"], "time": chapters[0]["time"]}]
    for chapter in chapters[1:4]:
        nodes.append({"kind": "要点", "title": chapter["title"], "time": chapter["time"]})
    if summary and (not nodes or summary not in {node["title"] for node in nodes}):
        nodes.append({"kind": "结论", "title": summary, "time": chapters[-1]["time"]})
    return nodes


def _must_watch_segments(rows: list[dict[str, str]]) -> list[dict]:
    visual_pattern = re.compile(r"看屏幕|画面|点击|界面|图表|这里可以看到|操作如下|代码运行|效果对比")
    segments = []
    for index, row in enumerate(rows):
        if not visual_pattern.search(row["body"]):
            continue
        start = time_to_seconds(row["time"])
        next_start = time_to_seconds(rows[index + 1]["time"]) if index + 1 < len(rows) else start + 60
        segments.append({
            "time": row["time"],
            "start_seconds": start,
            "end_seconds": max(start + 15, next_start - 1),
            "reason": "这部分依赖画面或实际操作，建议查看原片段",
            "preview": _clean_sentence(row["body"])[:80],
        })
        if len(segments) >= 5:
            break
    return segments


def make_brief(rows: list[dict[str, str]]) -> dict:
    """生成带证据、时间范围、行动项和阅读指标的结构化理解页数据。"""
    normalized_rows = [{"time": row["time"], "body": to_simplified(row["body"])} for row in rows]
    rows = []
    for index, row in enumerate(normalized_rows):
        start = time_to_seconds(row["time"])
        next_start = time_to_seconds(normalized_rows[index + 1]["time"]) if index + 1 < len(normalized_rows) else start
        rows.append({
            **row,
            "evidence_id": f"E{index + 1:04d}",
            "seconds": start,
            "end_seconds": max(start, next_start - 1),
        })
    if not rows:
        raise ValueError("没有可用于分析的转写内容。")

    chunks = _smart_chunks(rows)
    chapters = []
    for index, group in enumerate(chunks):
        full = " ".join(row["body"] for row in group)
        title = _extract_title(full)
        points: list[str] = []
        seen = set()
        for row in group[:5]:
            point = _clean_sentence(row["body"])
            if point and point not in seen and len(point) >= 4:
                points.append(point[:60] + ("…" if len(point) > 60 else ""))
                seen.add(point)
            if len(points) >= 3:
                break
        start_seconds = time_to_seconds(group[0]["time"])
        next_group = chunks[index + 1] if index + 1 < len(chunks) else None
        end_seconds = time_to_seconds(next_group[0]["time"]) - 1 if next_group else time_to_seconds(group[-1]["time"])
        source_evidence_rows = []
        for row in group:
            source_evidence_rows.extend(row.get("source_rows", [row]))
        evidence = [{
            "evidence_id": row["evidence_id"],
            "time": row["time"],
            "seconds": row["seconds"],
            "end_seconds": row["end_seconds"],
            "quote": row["body"][:180],
        } for row in source_evidence_rows]
        chapters.append({
            "time": group[0]["time"],
            "start_seconds": start_seconds,
            "end_seconds": max(start_seconds, end_seconds),
            "title": title,
            "body": full,
            "points": points,
            "evidence": evidence,
        })

    all_text = " ".join(row["body"] for row in rows)
    summary = _extract_summary("。".join(row["body"] for row in rows[-3:]), 120)
    title = _extract_title(rows[0]["body"], 28)
    if len(title) < 4 or not _HAN_PAT.search(title):
        title = _extract_title(all_text, 28)

    actions = []
    for chapter in chapters:
        for point in chapter["points"]:
            if re.search(r"应该|需要|可以|先|创建|建立|检查|执行|使用|设置|保持|完成", point):
                actions.append({"text": point, "time": chapter["time"], "seconds": chapter["start_seconds"]})
                break
        if len(actions) >= 5:
            break

    duration_seconds = max((time_to_seconds(row["time"]) for row in rows), default=0)
    content_type = _content_type(all_text)
    return {
        "title": title,
        "summary": summary,
        "content_type": content_type,
        "fingerprint": _fingerprint(all_text, duration_seconds, chapters, content_type),
        "content_model": _local_content_model(content_type, chapters),
        "content_map": _content_map(rows, chapters, summary),
        "must_watch_segments": _must_watch_segments(rows),
        "key_insights": [{
            "title": chapter["title"],
            "detail": chapter["points"][0] if chapter["points"] else chapter["body"][:80],
            "time": chapter["evidence"][0]["time"] if chapter["evidence"] else chapter["time"],
            "seconds": chapter["evidence"][0]["seconds"] if chapter["evidence"] else chapter["start_seconds"],
            "evidence_ids": [chapter["evidence"][0]["evidence_id"]] if chapter["evidence"] else [],
            "evidence": chapter["evidence"][:1],
            "claim_type": "contextual_summary",
            "audit_status": "deterministic",
        } for chapter in chapters[:5]],
        "chapters": chapters,
        "evidence_store": [{
            "evidence_id": row["evidence_id"],
            "time": row["time"],
            "seconds": row["seconds"],
            "end_seconds": row["end_seconds"],
            "quote": row["body"],
            "source": "transcript",
        } for row in rows],
        "actions": actions,
        "metrics": {
            "duration_seconds": duration_seconds,
            "estimated_read_minutes": max(1, round(len(all_text) / 450)),
            "chapter_count": len(chapters),
            "evidence_count": sum(len(chapter["evidence"]) for chapter in chapters),
        },
        "source_rows": len(rows),
        "engine": "semantic-chunking",
        "language": "zh-CN",
    }


def answer_from_brief(brief: dict, question: str) -> dict:
    """仅依据知识页内容回答问题；找不到证据时明确说明。"""
    cleaned = to_simplified(question)
    for phrase in ("为什么", "作者", "推荐", "什么", "怎么", "是否", "视频", "里面", "讲了", "提到", "请问"):
        cleaned = cleaned.replace(phrase, "")
    han = "".join(_HAN_PAT.findall(cleaned))
    terms = {han[index:index + 2] for index in range(max(0, len(han) - 1))}
    if len(han) == 1:
        terms.add(han)

    ranked = []
    for chapter in brief.get("chapters", []):
        haystack = f"{chapter.get('title', '')} {chapter.get('body', '')}"
        score = sum(1 for term in terms if term and term in haystack)
        if han and han in haystack:
            score += 3
        ranked.append((score, chapter))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not terms or not ranked or ranked[0][0] == 0:
        return {"found": False, "answer": "视频中未明确提及这个问题。", "evidence": []}

    chapter = ranked[0][1]
    chapter_evidence = chapter.get("evidence", [])
    evidence_ranked = []
    for item in chapter_evidence:
        quote = item.get("quote", "")
        score = sum(1 for term in terms if term and term in quote)
        if han and han in quote:
            score += 3
        evidence_ranked.append((score, item))
    evidence_ranked.sort(key=lambda item: item[0], reverse=True)
    matched_evidence = [item for score, item in evidence_ranked if score > 0]
    evidence = matched_evidence[:3] or chapter_evidence[:3]
    anchor = evidence[0] if evidence else {
        "time": chapter.get("time", "00:00"),
        "seconds": chapter.get("start_seconds", 0),
    }
    answer = chapter.get("points", [None])[0] or chapter.get("body", "")
    return {
        "found": True,
        "answer": answer,
        "chapter": chapter.get("title", ""),
        "time": anchor.get("time", chapter.get("time", "00:00")),
        "seconds": anchor.get("seconds", chapter.get("start_seconds", 0)),
        "evidence": evidence,
    }


def request_brief(payload: dict) -> dict:
    transcript = str(payload.get("transcript", "")).strip()
    url = str(payload.get("url", "")).strip()
    if transcript:
        raw_rows = parse_timestamped_transcript(transcript)
        rows = raw_rows or [{"time": "00:00", "body": transcript}]
        source = "pasted_transcript"
    elif url:
        kind = source_kind(url)
        if kind == "bilibili":
            rows = fetch_bilibili_transcript(url)
            source = "bilibili_audio"
        else:
            rows = fetch_youtube_transcript(url)
            source = "youtube_subtitles"
    else:
        raise ValueError("请提供视频链接或字幕/转写文本。")
    result = make_brief(rows)
    result = enhance_brief(rows, result, mode=str(payload.get("analysis_mode", "auto")))
    result.update({"source": source, "url": url})
    return result


if __name__ == "__main__":
    print(json.dumps(make_brief(parse_timestamped_transcript("[00:00] 示例内容，用于测试结构化生成。")), ensure_ascii=False, indent=2))
