"""DeepSeek analysis and independent evidence-audit prompts."""
import json
from videobrief.domain.taxonomy import CONTENT_MODEL_ROLE_ORDER

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
            "title": "最多3条高价值观点；删掉任一条都会影响用户对视频的正确理解",
            "detail": "说明这条信息为什么重要，不得重复直接答案或其他观点",
            "evidence_ids": ["一个或多个真实证据 ID"],
            "claim_type": "video_explicit/context_summary/system_inference",
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
                "核心观点最多3条，必须高价值且互不重复；不得为了填满结构重复同一事实。"
                "如果视频信息量低，宁可只输出1到2条，也不要制造看似完整但没有增量的内容。"
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
