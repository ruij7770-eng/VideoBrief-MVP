"""VideoBrief 智能分析层：DeepSeek/OpenAI-compatible 调用与证据约束合并。"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Callable

import requests

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
CONTENT_MODEL_ROLE_ORDER = {
    "tutorial": ("goal", "prerequisite", "step", "parameter", "pitfall", "result"),
    "interview": ("topic", "speaker_position", "argument", "disagreement", "key_quote", "open_question"),
    "review": ("subject", "criterion", "pro", "con", "tradeoff", "verdict"),
    "lecture": ("central_question", "concept", "relationship", "example", "conclusion", "boundary"),
    "commentary": ("topic", "fact", "opinion", "inference", "controversy", "uncertainty"),
}
CONTENT_MODEL_ROLES = {name: set(roles) for name, roles in CONTENT_MODEL_ROLE_ORDER.items()}
CONTENT_TYPES = set(CONTENT_MODEL_ROLES)
CONTENT_TYPE_LABELS = {
    "tutorial": "操作教程",
    "interview": "访谈对话",
    "review": "产品评测",
    "lecture": "知识讲解",
    "commentary": "观点评论",
}


def _content_template(value: object) -> str:
    template = str(value or "").strip().lower()
    if template == "explainer":
        return "lecture"
    return template if template in CONTENT_MODEL_ROLES else ""


def _config() -> dict:
    return {
        "provider": os.getenv("VIDEOBRIEF_LLM_PROVIDER", "deepseek"),
        "base_url": os.getenv("VIDEOBRIEF_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.getenv("VIDEOBRIEF_LLM_MODEL", DEFAULT_MODEL),
        "api_key": os.getenv("VIDEOBRIEF_LLM_API_KEY", ""),
    }


def agent_status() -> dict:
    config = _config()
    return {
        "configured": bool(config["api_key"]),
        "provider": config["provider"],
        "model": config["model"],
        "base_url": config["base_url"],
    }


def _http_transport(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _parse_content(response: dict) -> dict:
    try:
        content = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise RuntimeError("智能分析服务返回结构异常。") from error
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("智能分析没有返回有效 JSON。") from error
    if not isinstance(result, dict):
        raise RuntimeError("智能分析结果必须是 JSON 对象。")
    return result


def _prompt(rows: list[dict], brief: dict) -> list[dict]:
    schema = {
        "title": "准确、简洁的视频标题",
        "summary": "不超过120字的一句话核心结论",
        "content_type": "tutorial/interview/review/lecture/commentary",
        "content_model": {
            "template": "必须与 content_type 相同",
            "items": [{
                "role": "使用对应类型允许的角色",
                "title": "简短标题",
                "detail": "只依据证据的内容",
                "evidence_ids": ["一个或多个真实证据 ID"],
            }],
            "allowed_roles": {name: list(roles) for name, roles in CONTENT_MODEL_ROLE_ORDER.items()},
        },
        "quick_brief": {
            "central_question": "视频试图回答的核心问题",
            "direct_answer": "用户最先应该知道的直接答案",
            "why_it_matters": "为什么这件事值得知道",
            "limitation": "视频未覆盖的边界；没有则写未明确说明",
            "evidence_ids": ["支撑以上判断的真实证据 ID，例如 E0007"],
        },
        "key_insights": [{
            "title": "观点", "detail": "解释", "evidence_ids": ["一个或多个真实证据 ID"],
            "claim_type": "video_explicit/contextual_summary/system_inference",
        }],
        "content_map": [{"kind": "问题/要点/方法/结论", "title": "节点", "time": "字幕中的时间"}],
        "chapter_rewrites": [{"time": "现有章节开始时间", "title": "章节标题", "summary": "章节结论"}],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是 VideoBrief 视频理解智能体。目标是让用户不必完整观看，也能快速、准确理解视频。"
                "只能依据提供的证据库，不得补充证据中没有的信息。每个核心观点必须引用一个或多个真实 evidence_id。"
                "不要生成测验、掌握度、复习计划或额外任务。只输出严格 JSON，不输出 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "task": "先判断视频类型，再按该类型允许的角色重构内容模型，同时生成核心结论、观点、内容地图和章节标题",
                "required_schema": schema,
                "existing_brief": {
                    "title": brief.get("title"),
                    "summary": brief.get("summary"),
                    "chapters": [{"time": c.get("time"), "title": c.get("title")} for c in brief.get("chapters", [])],
                },
                "evidence_store": brief.get("evidence_store", [])[:500],
            }, ensure_ascii=False),
        },
    ]


def _audit_prompt(output: dict, brief: dict) -> list[dict]:
    referenced_ids = set()
    quick = output.get("quick_brief")
    if isinstance(quick, dict) and isinstance(quick.get("evidence_ids"), list):
        referenced_ids.update(quick["evidence_ids"])
    for insight in output.get("key_insights", []):
        if isinstance(insight, dict) and isinstance(insight.get("evidence_ids"), list):
            referenced_ids.update(insight["evidence_ids"])
    content_model = output.get("content_model")
    if isinstance(content_model, dict):
        for item in content_model.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("evidence_ids"), list):
                referenced_ids.update(item["evidence_ids"])
    evidence = {
        item.get("evidence_id"): {
            "time": item.get("time"),
            "quote": item.get("quote", ""),
        }
        for item in brief.get("evidence_store", [])
        if item.get("evidence_id") in referenced_ids
    }
    return [
        {
            "role": "system",
            "content": (
                "你是独立的视频证据审计员，不负责润色，只负责找错。"
                "逐条比较候选结论与字幕原文。supported 表示原文直接支持；partial 表示方向正确但表述过强，必须给出收窄后的 detail；"
                "rejected 表示原文不支持。不得因为 evidence_id 存在就判定观点成立。只输出严格 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "candidate_summary": output.get("summary"),
                "candidate_quick_brief": output.get("quick_brief"),
                "candidate_insights": [
                    {"index": index, **insight}
                    for index, insight in enumerate(output.get("key_insights", []))
                    if isinstance(insight, dict)
                ],
                "candidate_content_model": output.get("content_model"),
                "evidence_by_id": evidence,
                "required_schema": {
                    "summary_status": "supported/partial/rejected",
                    "corrected_summary": "仅在 partial 时填写",
                    "quick_brief_status": "supported/partial/rejected",
                    "corrected_direct_answer": "仅在 partial 时填写",
                    "insight_audit": [{"index": 0, "status": "supported/partial/rejected", "detail": "partial 时给出收窄表述"}],
                    "structure_audit": [{"index": 0, "status": "supported/partial/rejected", "detail": "partial 时给出收窄表述"}],
                    "overall_confidence": "high/medium/low",
                },
            }, ensure_ascii=False),
        },
    ]


def _merge_agent_output(brief: dict, output: dict, audit: dict, config: dict) -> dict:
    result = deepcopy(brief)
    local_content_model = deepcopy(result.get("content_model"))
    chapters = result.get("chapters", [])
    chapters_by_time = {chapter.get("time"): chapter for chapter in chapters}
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in result.get("evidence_store", [])
        if item.get("evidence_id")
    }

    title = output.get("title")
    if isinstance(title, str) and 4 <= len(title.strip()) <= 80:
        result["title"] = title.strip()
    summary = output.get("summary")
    summary_status = audit.get("summary_status", "supported")
    if summary_status == "partial" and isinstance(audit.get("corrected_summary"), str):
        summary = audit["corrected_summary"]
    if summary_status != "rejected" and isinstance(summary, str) and 4 <= len(summary.strip()) <= 240:
        result["summary"] = summary.strip()
    content_type = _content_template(output.get("content_type"))
    if content_type:
        result["content_type"] = content_type
        fingerprint = result.setdefault("fingerprint", {})
        fingerprint["type_label"] = CONTENT_TYPE_LABELS[content_type]
        if result.get("content_model", {}).get("template") != content_type:
            result.pop("content_model", None)

    for rewrite in output.get("chapter_rewrites", [])[:30]:
        if not isinstance(rewrite, dict):
            continue
        chapter = chapters_by_time.get(rewrite.get("time"))
        if not chapter:
            continue
        new_title = rewrite.get("title")
        new_summary = rewrite.get("summary")
        if isinstance(new_title, str) and 2 <= len(new_title.strip()) <= 60:
            chapter["title"] = new_title.strip()
        if isinstance(new_summary, str) and 4 <= len(new_summary.strip()) <= 180:
            points = chapter.setdefault("points", [])
            if points:
                points[0] = new_summary.strip()
            else:
                points.append(new_summary.strip())

    audit_by_index = {
        item.get("index"): item for item in audit.get("insight_audit", [])
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    }
    insights = []
    candidate_insights = output.get("key_insights", [])[:8]
    for index, insight in enumerate(candidate_insights):
        if not isinstance(insight, dict):
            continue
        verdict = audit_by_index.get(index, {})
        status = verdict.get("status")
        if status not in {"supported", "partial"}:
            continue
        requested_ids = insight.get("evidence_ids")
        if not isinstance(requested_ids, list) or not requested_ids or any(item not in evidence_by_id for item in requested_ids):
            continue
        linked_evidence = [evidence_by_id[item] for item in requested_ids]
        first_evidence = linked_evidence[0]
        title = insight.get("title")
        detail = verdict.get("detail") if status == "partial" else insight.get("detail")
        if not isinstance(title, str) or not isinstance(detail, str):
            continue
        if not title.strip() or not detail.strip():
            continue
        claim_type = insight.get("claim_type")
        if claim_type not in {"video_explicit", "contextual_summary", "system_inference"}:
            claim_type = "contextual_summary"
        insights.append({
            "title": title.strip()[:80],
            "detail": detail.strip()[:240],
            "time": first_evidence["time"],
            "seconds": first_evidence.get("seconds", 0),
            "evidence_ids": requested_ids,
            "evidence": linked_evidence,
            "claim_type": claim_type,
            "audit_status": status,
        })
    result["key_insights"] = insights[:5]

    candidate_model = output.get("content_model")
    candidate_structure_items = candidate_model.get("items", [])[:16] if isinstance(candidate_model, dict) else []
    structure_audit = {
        item.get("index"): item for item in audit.get("structure_audit", [])
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    }
    structure_items = []
    candidate_template = _content_template(candidate_model.get("template")) if isinstance(candidate_model, dict) else ""
    if candidate_template and candidate_template == content_type:
        allowed_roles = CONTENT_MODEL_ROLES[candidate_template]
        for index, item in enumerate(candidate_structure_items):
            if not isinstance(item, dict) or item.get("role") not in allowed_roles:
                continue
            verdict = structure_audit.get(index, {})
            status = verdict.get("status")
            if status not in {"supported", "partial"}:
                continue
            requested_ids = item.get("evidence_ids")
            if not isinstance(requested_ids, list) or not requested_ids or any(evidence_id not in evidence_by_id for evidence_id in requested_ids):
                continue
            title = item.get("title")
            detail = verdict.get("detail") if status == "partial" else item.get("detail")
            if not isinstance(title, str) or not title.strip() or not isinstance(detail, str) or not detail.strip():
                continue
            linked_evidence = [evidence_by_id[evidence_id] for evidence_id in requested_ids]
            structure_items.append({
                "role": item["role"],
                "title": title.strip()[:80],
                "detail": detail.strip()[:240],
                "time": linked_evidence[0]["time"],
                "seconds": linked_evidence[0].get("seconds", 0),
                "evidence_ids": requested_ids,
                "evidence": linked_evidence,
                "audit_status": status,
            })
    structure_fallback = False
    if structure_items:
        role_order = {role: index for index, role in enumerate(CONTENT_MODEL_ROLE_ORDER[candidate_template])}
        structure_items.sort(key=lambda item: (role_order[item["role"]], item["seconds"]))
    compatible_local = (
        isinstance(local_content_model, dict)
        and local_content_model.get("template") == candidate_template
        and bool(local_content_model.get("items"))
    )
    minimum_smart_items = min(len(candidate_structure_items), max(2, (len(candidate_structure_items) + 1) // 2)) if candidate_structure_items else 0
    if compatible_local and len(structure_items) < minimum_smart_items:
        result["content_model"] = local_content_model
        structure_fallback = True
    elif structure_items:
        result["content_model"] = {"template": candidate_template, "items": structure_items}

    quick = output.get("quick_brief")
    quick_status = audit.get("quick_brief_status")
    if isinstance(quick, dict) and quick_status in {"supported", "partial"}:
        requested_ids = quick.get("evidence_ids")
        valid_ids = requested_ids if isinstance(requested_ids, list) and requested_ids and all(item in evidence_by_id for item in requested_ids) else []
        required_fields = [quick.get("central_question"), quick.get("direct_answer"), quick.get("why_it_matters")]
        if valid_ids and all(isinstance(value, str) and value.strip() for value in required_fields):
            direct_answer = quick["direct_answer"]
            if quick_status == "partial" and isinstance(audit.get("corrected_direct_answer"), str):
                direct_answer = audit["corrected_direct_answer"]
            quick_evidence = [evidence_by_id[item] for item in valid_ids]
            result["quick_brief"] = {
                "central_question": quick["central_question"].strip()[:160],
                "direct_answer": direct_answer.strip()[:240],
                "why_it_matters": quick["why_it_matters"].strip()[:200],
                "limitation": str(quick.get("limitation") or "视频未明确说明边界。").strip()[:200],
                "evidence_ids": valid_ids,
                "evidence": quick_evidence[:6],
                "audit_status": quick_status,
            }

    content_map = []
    for node in output.get("content_map", [])[:10]:
        if not isinstance(node, dict) or node.get("time") not in chapters_by_time:
            continue
        title = node.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        content_map.append({
            "kind": node.get("kind") if node.get("kind") in {"问题", "要点", "方法", "结论"} else "要点",
            "title": title.strip()[:100],
            "time": node["time"],
        })
    if content_map:
        result["content_map"] = content_map

    result["agent"] = {
        "mode": "smart",
        "provider": config["provider"],
        "model": config["model"],
        "model_calls": 2,
        "validated_insights": len(result["key_insights"]),
        "validated_candidates": len(insights),
        "rejected_insights": max(0, len(candidate_insights) - len(insights)),
        "validated_structure_items": len(structure_items),
        "rejected_structure_items": max(0, len(candidate_structure_items) - len(structure_items)),
        "structure_fallback": structure_fallback,
        "audit_confidence": audit.get("overall_confidence") if audit.get("overall_confidence") in {"high", "medium", "low"} else "low",
    }
    result["engine"] = "agent-evidence-first"
    return result


def enhance_brief(rows: list[dict], brief: dict, mode: str = "auto", transport: Callable | None = None) -> dict:
    result = deepcopy(brief)
    config = _config()
    if mode not in {"auto", "fast", "smart"}:
        raise ValueError("分析模式仅支持 auto、fast 或 smart。")
    if mode == "fast":
        result["agent"] = {"mode": "fast", "reason": "user_selected"}
        return result
    if not config["api_key"]:
        if mode == "smart":
            raise ValueError("智能分析尚未配置 DeepSeek API Key。")
        result["agent"] = {"mode": "fast", "reason": "missing_api_key"}
        return result

    payload = {
        "model": config["model"],
        "messages": _prompt(rows, brief),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    call = transport or _http_transport
    try:
        analysis_response = call(
            f"{config['base_url']}/chat/completions",
            {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
            payload,
            120,
        )
        analysis = _parse_content(analysis_response)
        audit_payload = {
            "model": config["model"],
            "messages": _audit_prompt(analysis, brief),
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        audit_response = call(
            f"{config['base_url']}/chat/completions",
            {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
            audit_payload,
            120,
        )
        audit = _parse_content(audit_response)
        return _merge_agent_output(brief, analysis, audit, config)
    except Exception as error:
        if mode == "smart":
            if isinstance(error, (ValueError, RuntimeError)):
                raise
            raise RuntimeError(f"DeepSeek 智能分析失败：{type(error).__name__}") from error
        result["agent"] = {"mode": "fast", "reason": "agent_error", "error_type": type(error).__name__}
        return result
