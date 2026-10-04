"""Non-destructive, fail-safe projections for historical Brief payloads."""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from typing import Any

from videobrief import SCHEMA_VERSION


_DECISION_QUESTIONS = {
    "tutorial": "完成这项操作最重要的方法是什么？",
    "interview": "这场访谈最重要的观点和分歧是什么？",
    "review": "这项评测的结论和适用对象是什么？",
    "lecture": "这个视频解释的核心问题是什么？",
    "commentary": "作者对这件事的核心判断是什么？",
}
_CONTENT_TYPES = frozenset(_DECISION_QUESTIONS)
_KNOWN_GENERATIONS = frozenset({
    "legacy-no-store", "evidence-store-v1", "typed-v2", "decision-v3", "canonical-v4",
})
_CANONICAL_COMPATIBILITY = {
    "source_generation": "canonical-v4",
    "projected": True,
    "stored_payload_unchanged": True,
}


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and bool(item) for item in value)


def _is_evidence_item(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        isinstance(value.get("evidence_id"), str)
        and bool(value["evidence_id"])
        and isinstance(value.get("time"), str)
        and _is_non_negative_int(value.get("seconds"))
        and _is_non_negative_int(value.get("end_seconds"))
        and isinstance(value.get("quote"), str)
        and bool(value["quote"])
        and isinstance(value.get("source"), str)
    )


def _is_evidence_store(value: Any, *, require_items: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not require_items)
        and all(_is_evidence_item(item) for item in value)
    )


def _is_insight(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        isinstance(value.get("title"), str)
        and bool(value["title"])
        and isinstance(value.get("detail"), str)
        and bool(value["detail"])
        and _is_string_list(value.get("evidence_ids"))
    )


def _is_content_item(value: Any) -> bool:
    return (
        _is_insight(value)
        and isinstance(value.get("role"), str)
        and bool(value["role"])
    )


def _is_content_model(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    items = value.get("items")
    return (
        value.get("template") in _CONTENT_TYPES
        and isinstance(items, list)
        and all(_is_content_item(item) for item in items)
    )


def _is_decision_brief(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    takeaways = value.get("takeaways")
    return (
        isinstance(value.get("question"), str)
        and isinstance(value.get("answer"), str)
        and isinstance(takeaways, list)
        and len(takeaways) <= 3
        and all(_is_insight(item) for item in takeaways)
        and isinstance(value.get("watch_verdict"), str)
        and isinstance(value.get("watch_reason"), str)
        and _is_non_negative_int(value.get("watch_seconds"))
    )


def detect_brief_generation(raw: Mapping[str, Any] | Any) -> str:
    """Detect an observed stored generation using validated structure only.

    An empty Evidence Store is intentionally classified as legacy: it provides
    no evidence-generation signal and may need reconstruction from chapters.
    """
    if not isinstance(raw, Mapping):
        return "legacy-no-store"
    if _is_decision_brief(raw.get("decision_brief")):
        return "decision-v3"
    if _is_content_model(raw.get("content_model")):
        return "typed-v2"
    if _is_evidence_store(raw.get("evidence_store"), require_items=True):
        return "evidence-store-v1"
    return "legacy-no-store"


def _legacy_evidence_id(chapter_index: int, evidence_index: int, item: Mapping[str, Any]) -> str:
    identity = f"{chapter_index}|{evidence_index}|{item.get('time', '')}|{item.get('seconds', '')}|{item.get('quote', '')}"
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8].upper()
    return f"L{chapter_index + 1:03d}{evidence_index + 1:03d}-{digest}"


def _sanitize_chapters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    chapters: list[dict[str, Any]] = []
    for source in value:
        if not isinstance(source, Mapping):
            continue
        chapter = copy.deepcopy(dict(source))
        evidence = chapter.get("evidence")
        chapter["evidence"] = (
            [copy.deepcopy(dict(item)) for item in evidence if isinstance(item, Mapping)]
            if isinstance(evidence, list)
            else []
        )
        if not isinstance(chapter.get("points"), list):
            chapter["points"] = []
        chapters.append(chapter)
    return chapters


def _project_legacy_evidence(result: dict[str, Any]) -> None:
    evidence_store: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(result["chapters"]):
        normalized: list[dict[str, Any]] = []
        for evidence_index, source in enumerate(chapter["evidence"]):
            item = copy.deepcopy(source)
            seconds = item.get("seconds")
            if not _is_non_negative_int(seconds):
                seconds = chapter.get("start_seconds")
            if not _is_non_negative_int(seconds):
                seconds = 0
            end_seconds = item.get("end_seconds")
            if not _is_non_negative_int(end_seconds):
                end_seconds = seconds
            time = item.get("time")
            if not isinstance(time, str):
                time = chapter.get("time") if isinstance(chapter.get("time"), str) else "00:00"
            quote = item.get("quote") if isinstance(item.get("quote"), str) else ""
            source_name = item.get("source") if isinstance(item.get("source"), str) else "legacy_chapter_projection"
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or not evidence_id:
                evidence_id = _legacy_evidence_id(chapter_index, evidence_index, item)
            normalized_item = {
                **item,
                "evidence_id": evidence_id,
                "time": time,
                "seconds": seconds,
                "end_seconds": end_seconds,
                "quote": quote,
                "source": source_name,
            }
            normalized.append(normalized_item)
            if quote:
                evidence_store.append(copy.deepcopy(normalized_item))
        chapter["evidence"] = normalized
    result["evidence_store"] = evidence_store


def _sanitize_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    segments: list[dict[str, Any]] = []
    for source in value:
        if not isinstance(source, Mapping):
            continue
        start = source.get("start_seconds", source.get("seconds", 0))
        end = source.get("end_seconds", start)
        if not _is_non_negative_int(start) or not _is_non_negative_int(end) or end < start:
            continue
        segments.append(copy.deepcopy(dict(source)))
    return segments


def _decision_projection(result: dict[str, Any]) -> dict[str, Any]:
    quick = result["quick_brief"]
    content_type = result["content_type"]
    answer = str(quick.get("direct_answer") or quick.get("answer") or result.get("summary") or "").strip()
    available = {item["evidence_id"] for item in result["evidence_store"]}
    takeaways = []
    for candidate in result["key_insights"]:
        evidence_ids = [value for value in candidate["evidence_ids"] if value in available]
        if not evidence_ids:
            continue
        item = copy.deepcopy(candidate)
        item["evidence_ids"] = evidence_ids
        takeaways.append(item)
        if len(takeaways) == 3:
            break
    segments = result["must_watch_segments"]
    watch_seconds = sum(
        max(0, item.get("end_seconds", 0) - item.get("start_seconds", item.get("seconds", 0)))
        for item in segments
    )
    return {
        "question": _DECISION_QUESTIONS[content_type],
        "answer": answer,
        "takeaways": takeaways,
        "value": str(quick.get("value") or ""),
        "watch_verdict": "只需回看关键片段" if segments else "直接阅读即可",
        "watch_reason": "建议只看依赖画面的片段。" if segments else "核心内容可以通过阅读理解。",
        "watch_seconds": watch_seconds,
        "limitation": str(quick.get("skip_condition") or "旧记录仅保留当时已提取的字幕信息。"),
        "evidence_ids": [value for item in takeaways for value in item["evidence_ids"]],
    }


def normalize_brief_for_read(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical V4 read model without mutating stored JSON."""
    if not isinstance(raw, Mapping):
        raise TypeError("Brief payload must be a mapping")
    result = copy.deepcopy(dict(raw))
    previous = result.get("compatibility")
    claimed = previous.get("detected_generation") if isinstance(previous, Mapping) else None
    detected_generation = claimed if claimed in _KNOWN_GENERATIONS else detect_brief_generation(raw)
    result["chapters"] = _sanitize_chapters(result.get("chapters"))

    if not _is_evidence_store(result.get("evidence_store"), require_items=True):
        _project_legacy_evidence(result)

    content_type = result.get("content_type")
    if content_type not in _CONTENT_TYPES:
        fingerprint = result.get("fingerprint")
        candidate = fingerprint.get("type_code") if isinstance(fingerprint, Mapping) else None
        content_type = candidate if candidate in _CONTENT_TYPES else "lecture"
    result["content_type"] = content_type

    key_insights = result.get("key_insights")
    result["key_insights"] = (
        [copy.deepcopy(dict(item)) for item in key_insights if _is_insight(item)]
        if isinstance(key_insights, list)
        else []
    )
    if not _is_content_model(result.get("content_model")):
        result["content_model"] = {"template": content_type, "items": []}
    result["must_watch_segments"] = _sanitize_segments(result.get("must_watch_segments"))
    if not isinstance(result.get("metrics"), Mapping):
        result["metrics"] = {}
    if not isinstance(result.get("agent"), Mapping):
        result["agent"] = {"mode": "legacy", "engine": "legacy-read-projection"}
    if not isinstance(result.get("quick_brief"), Mapping):
        result["quick_brief"] = {}
    if not isinstance(result.get("fingerprint"), Mapping):
        result["fingerprint"] = {}

    if not _is_decision_brief(result.get("decision_brief")):
        result["decision_brief"] = _decision_projection(result)

    result["schema_version"] = SCHEMA_VERSION
    result["compatibility"] = {
        **copy.deepcopy(_CANONICAL_COMPATIBILITY),
        "detected_generation": detected_generation,
    }
    return result
