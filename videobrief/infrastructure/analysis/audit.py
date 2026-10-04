"""Fail-closed evidence merge policy for smart analysis output."""
from copy import deepcopy
from videobrief.domain.taxonomy import CONTENT_MODEL_ROLE_ORDER, CONTENT_MODEL_ROLES, CONTENT_TYPE_LABELS

def _content_template(value: object) -> str:
    template = str(value or "").strip().lower()
    if template == "explainer":
        return "lecture"
    return template if template in CONTENT_MODEL_ROLES else ""


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
    summary_status = audit.get("summary_status", "rejected")
    if summary_status == "partial":
        corrected = audit.get("corrected_summary")
        summary = corrected if isinstance(corrected, str) and corrected.strip() else None
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
        if claim_type not in {"video_explicit", "context_summary", "system_inference"}:
            claim_type = "context_summary"
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
    result["key_insights"] = insights[:3]

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
            if quick_status == "partial":
                corrected = audit.get("corrected_direct_answer")
                if not isinstance(corrected, str) or not corrected.strip():
                    direct_answer = ""
                else:
                    direct_answer = corrected
            quick_evidence = [evidence_by_id[item] for item in valid_ids]
            if not direct_answer.strip():
                direct_answer = ""
            if direct_answer:
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
