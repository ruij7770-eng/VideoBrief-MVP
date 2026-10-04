"""Deterministic local semantic analyzer.

This module owns transcript-to-Brief structure. It has no network, database,
FastAPI, Whisper, or LLM dependencies.
"""
from __future__ import annotations

import re

from videobrief import SCHEMA_VERSION
from videobrief.application.decision import build_decision_brief
from videobrief.application.transcript import time_to_seconds, to_simplified

_SENT_END = re.compile(r"[。！？!?\n]")
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
            "audit_status": "local",
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
    result = {
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
            "claim_type": "context_summary",
            "audit_status": "local",
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
    result["schema_version"] = SCHEMA_VERSION
    result["decision_brief"] = build_decision_brief(result)
    return result
