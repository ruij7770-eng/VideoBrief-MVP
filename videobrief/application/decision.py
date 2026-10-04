"""Build the single conclusion-first decision projection."""
from __future__ import annotations

import re

_SENT_END = re.compile(r"[。！？!?\n]")
_DECISION_QUESTIONS = {
    "tutorial": "完成这项操作最重要的方法是什么？",
    "interview": "这场访谈最重要的观点和分歧是什么？",
    "review": "这项评测的结论和适用对象是什么？",
    "lecture": "这个视频解释的核心问题是什么？",
    "commentary": "作者基于哪些事实提出了什么观点？",
}
_DECISION_ANSWER_ROLES = {
    "tutorial": ("result", "goal"),
    "interview": ("speaker_position", "topic"),
    "review": ("verdict", "tradeoff", "subject"),
    "lecture": ("conclusion", "relationship", "concept", "central_question"),
    "commentary": ("opinion", "fact", "topic"),
}
_DECISION_TAKEAWAY_ROLES = {
    "tutorial": ("step", "pitfall", "parameter", "prerequisite"),
    "interview": ("speaker_position", "disagreement", "argument", "key_quote", "open_question"),
    "review": ("pro", "con", "tradeoff", "criterion", "verdict"),
    "lecture": ("concept", "relationship", "boundary", "example", "conclusion"),
    "commentary": ("fact", "opinion", "uncertainty", "controversy", "inference"),
}


def _text_key(value: object) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).lower()


def build_decision_brief(brief: dict) -> dict:
    content_type = brief.get("content_type") if brief.get("content_type") in _DECISION_QUESTIONS else "lecture"
    quick = brief.get("quick_brief") if isinstance(brief.get("quick_brief"), dict) else {}
    model = brief.get("content_model") if isinstance(brief.get("content_model"), dict) else {}
    model_items = [item for item in model.get("items", []) if isinstance(item, dict)]

    answer = str(quick.get("direct_answer") or "").strip()
    if not answer:
        by_role = {role: [item for item in model_items if item.get("role") == role] for role in _DECISION_ANSWER_ROLES[content_type]}
        for role in _DECISION_ANSWER_ROLES[content_type]:
            if by_role[role]:
                answer = str(by_role[role][-1].get("detail") or by_role[role][-1].get("title") or "").strip()
                break
    answer = answer or str(brief.get("summary") or brief.get("title") or "").strip()

    if quick and brief.get("key_insights"):
        candidates = [item for item in brief["key_insights"] if isinstance(item, dict)]
    else:
        candidates, remaining = [], []
        for role in _DECISION_TAKEAWAY_ROLES[content_type]:
            role_items = [item for item in model_items if item.get("role") == role]
            if role_items:
                candidates.append(role_items[0])
                remaining.extend(role_items[1:])
        candidates.extend(remaining)

    takeaways = []
    seen = {_text_key(answer)}
    for item in candidates:
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if _text_key(title) in {"处理流程", "操作步骤", "内容要点", "回顾", "总结"}:
            concrete = [part.strip() for part in _SENT_END.split(detail) if len(part.strip()) >= 6 and _text_key(part) != _text_key(title)]
            if concrete:
                title = concrete[0][:28] + ("…" if len(concrete[0]) > 28 else "")
        evidence_ids = item.get("evidence_ids")
        keys = {_text_key(title), _text_key(detail), _text_key(f"{title}{detail}")}
        keys.discard("")
        if not title or not detail or not isinstance(evidence_ids, list) or not evidence_ids or seen.intersection(keys):
            continue
        seen.update(keys)
        takeaways.append({
            "title": title,
            "detail": detail,
            "time": item.get("time", "00:00"),
            "seconds": item.get("seconds", 0),
            "evidence_ids": evidence_ids,
            "evidence": item.get("evidence", []),
            "audit_status": item.get("audit_status", "deterministic"),
        })
        if len(takeaways) == 3:
            break

    segments = brief.get("must_watch_segments") or []
    watch_seconds = sum(max(0, int(item.get("end_seconds", 0)) - int(item.get("start_seconds", 0))) for item in segments)
    duration = int((brief.get("metrics") or {}).get("duration_seconds", 0) or 0)
    watch_ratio = watch_seconds / duration if duration else 0
    if not segments:
        watch_verdict, watch_reason = "直接阅读即可", "没有检测到必须依赖画面的内容。"
    elif watch_ratio <= 0.35:
        watch_verdict = "只需回看关键片段"
        watch_reason = f"大部分内容可直接阅读，仅有 {len(segments)} 个片段依赖画面或操作。"
    else:
        watch_verdict, watch_reason = "建议观看原视频", "较多关键内容依赖画面或实际操作。"

    return {
        "question": str(quick.get("central_question") or _DECISION_QUESTIONS[content_type]).strip(),
        "answer": answer[:320],
        "takeaways": takeaways,
        "watch_verdict": watch_verdict,
        "watch_reason": watch_reason,
        "watch_seconds": watch_seconds,
        "why_it_matters": str(quick.get("why_it_matters") or "").strip()[:200],
        "boundary": str(quick.get("limitation") or "").strip()[:200],
    }
