"""Evidence-only question answering for an existing Brief."""
from __future__ import annotations

import re

from .transcript import to_simplified

_HAN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def answer_from_brief(brief: dict, question: str) -> dict:
    cleaned = to_simplified(question)
    for phrase in ("为什么", "作者", "推荐", "什么", "怎么", "是否", "视频", "里面", "讲了", "提到", "请问"):
        cleaned = cleaned.replace(phrase, "")
    han = "".join(_HAN.findall(cleaned))
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
    chapter_evidence = chapter.get("evidence") or []
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
    anchor = evidence[0] if evidence else {"time": chapter.get("time", "00:00"), "seconds": chapter.get("start_seconds", 0)}
    points = chapter.get("points") or []
    answer = (points[0] if points else "") or chapter.get("body", "")
    return {
        "found": True,
        "answer": answer,
        "chapter": chapter.get("title", ""),
        "time": anchor.get("time", chapter.get("time", "00:00")),
        "seconds": anchor.get("seconds", chapter.get("start_seconds", 0)),
        "evidence_id": anchor.get("evidence_id", ""),
        "evidence": evidence,
    }
