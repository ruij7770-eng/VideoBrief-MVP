import os
import unittest
from unittest.mock import patch

from videobrief_agent import agent_status, enhance_brief


ROWS = [
    {"time": "00:00", "body": "今天介绍数据库设计。"},
    {"time": "01:20", "body": "字段太多会增加录入阻力，所以只保留必要字段。"},
]
BASE = {
    "title": "数据库设计",
    "summary": "只保留必要字段",
    "chapters": [
        {
            "time": "00:00", "title": "数据库设计", "body": ROWS[0]["body"],
            "points": [ROWS[0]["body"]], "evidence": [{"time": "00:00", "quote": ROWS[0]["body"]},
            ],
        },
        {
            "time": "01:20", "title": "减少字段", "body": ROWS[1]["body"],
            "points": [ROWS[1]["body"]], "evidence": [{"time": "01:20", "quote": ROWS[1]["body"]}],
        },
    ],
    "evidence_store": [
        {"evidence_id": "E0001", "time": "00:00", "seconds": 0, "end_seconds": 79, "quote": ROWS[0]["body"], "source": "transcript"},
        {"evidence_id": "E0002", "time": "01:20", "seconds": 80, "end_seconds": 80, "quote": ROWS[1]["body"], "source": "transcript"},
    ],
    "key_insights": [],
    "content_map": [],
}


class AgentConfigurationTests(unittest.TestCase):
    def test_missing_key_is_reported_without_exposing_secrets(self):
        with patch.dict(os.environ, {}, clear=True):
            status = agent_status()
        self.assertFalse(status["configured"])
        self.assertEqual(status["provider"], "deepseek")
        self.assertNotIn("api_key", status)

    def test_auto_mode_falls_back_to_local_engine_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = enhance_brief(ROWS, BASE.copy(), mode="auto")
        self.assertEqual(result["agent"]["mode"], "fast")
        self.assertEqual(result["agent"]["reason"], "missing_api_key")
        self.assertEqual(result["title"], BASE["title"])

    def test_smart_mode_uses_second_pass_audit_before_merging(self):
        calls = []

        def fake_transport(url, headers, payload, timeout):
            calls.append({"url": url, "headers": headers, "payload": payload})
            if len(calls) == 1:
                content = {
                    "title": "为什么数据库字段越少越容易坚持",
                    "summary": "减少字段可以降低录入阻力。",
                    "content_type": "tutorial",
                    "quick_brief": {
                        "central_question": "怎样降低数据库录入阻力？",
                        "direct_answer": "只保留必要字段。",
                        "why_it_matters": "更容易持续录入。",
                        "limitation": "视频没有给出统一字段数量。",
                        "evidence_ids": ["E0002"],
                    },
                    "key_insights": [
                        {"title": "减少字段", "detail": "字段太多会增加录入阻力。", "evidence_ids": ["E0002"], "claim_type": "video_explicit"},
                        {"title": "不存在的观点", "detail": "视频没有说过。", "evidence_ids": ["E9999"], "claim_type": "system_inference"},
                    ],
                    "content_map": [{"kind": "问题", "title": "录入阻力", "time": "01:20"}],
                    "chapter_rewrites": [{"time": "01:20", "title": "字段越少越容易录入", "summary": "只保留必要字段。"}],
                }
            else:
                content = {
                    "insight_audit": [
                        {"index": 0, "status": "supported", "detail": "字段太多会增加录入阻力。"},
                        {"index": 1, "status": "rejected", "detail": ""},
                    ],
                    "quick_brief_status": "supported",
                    "overall_confidence": "high",
                }
            return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

        env = {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}
        with patch.dict(os.environ, env, clear=True):
            result = enhance_brief(ROWS, BASE.copy(), mode="smart", transport=fake_transport)

        self.assertEqual(result["agent"]["mode"], "smart")
        self.assertEqual(result["agent"]["model_calls"], 2)
        self.assertEqual(result["agent"]["audit_confidence"], "high")
        self.assertEqual(result["title"], "为什么数据库字段越少越容易坚持")
        self.assertEqual(len(result["key_insights"]), 1)
        self.assertEqual(result["key_insights"][0]["evidence"][0]["evidence_id"], "E0002")
        self.assertEqual(result["key_insights"][0]["evidence"][0]["time"], "01:20")
        self.assertEqual(result["key_insights"][0]["seconds"], 80)
        self.assertEqual(result["key_insights"][0]["claim_type"], "video_explicit")
        self.assertEqual(result["quick_brief"]["direct_answer"], "只保留必要字段。")
        self.assertEqual(result["chapters"][1]["title"], "字段越少越容易录入")
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0]["url"].endswith("/chat/completions"))
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret-test-key")
        audit_input = __import__("json").loads(calls[1]["payload"]["messages"][1]["content"])
        self.assertEqual(set(audit_input["evidence_by_id"]), {"E0002"})

    def test_sparse_smart_structure_does_not_replace_complete_local_model(self):
        brief = __import__("copy").deepcopy(BASE)
        brief["content_model"] = {
            "template": "tutorial",
            "items": [
                {"role": "goal", "title": "本地目标", "detail": "建立数据库。", "time": "00:00", "seconds": 0, "evidence_ids": ["E0001"], "evidence": [BASE["evidence_store"][0]], "audit_status": "deterministic"},
                {"role": "step", "title": "本地步骤", "detail": "减少字段。", "time": "01:20", "seconds": 80, "evidence_ids": ["E0002"], "evidence": [BASE["evidence_store"][1]], "audit_status": "deterministic"},
                {"role": "result", "title": "本地结果", "detail": "降低阻力。", "time": "01:20", "seconds": 80, "evidence_ids": ["E0002"], "evidence": [BASE["evidence_store"][1]], "audit_status": "deterministic"},
            ],
        }
        candidates = [
            {"role": role, "title": role, "detail": "候选内容。", "evidence_ids": ["E0002"]}
            for role in ("goal", "step", "result")
        ]
        responses = iter([
            {"title": "数据库教程", "summary": "减少字段降低阻力。", "content_type": "tutorial", "key_insights": [], "content_map": [], "chapter_rewrites": [], "content_model": {"template": "tutorial", "items": candidates}},
            {"insight_audit": [], "structure_audit": [
                {"index": 0, "status": "supported", "detail": ""},
                {"index": 1, "status": "rejected", "detail": ""},
                {"index": 2, "status": "rejected", "detail": ""},
            ], "quick_brief_status": "rejected", "overall_confidence": "high"},
        ])

        def fake_transport(*_args):
            content = next(responses)
            return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

        with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}, clear=True):
            result = enhance_brief(ROWS, brief, mode="smart", transport=fake_transport)

        self.assertEqual([item["title"] for item in result["content_model"]["items"]], ["本地目标", "本地步骤", "本地结果"])
        self.assertTrue(result["agent"]["structure_fallback"])
        self.assertEqual(result["agent"]["validated_structure_items"], 1)

    def test_each_video_type_uses_its_own_role_order(self):
        role_pairs = {
            "tutorial": ("goal", "step"),
            "interview": ("topic", "speaker_position"),
            "review": ("subject", "criterion"),
            "lecture": ("central_question", "concept"),
            "commentary": ("topic", "fact"),
        }
        for template, expected_roles in role_pairs.items():
            with self.subTest(template=template):
                responses = iter([
                    {
                        "title": "类型化内容模型",
                        "summary": "类型化摘要内容。",
                        "content_type": template,
                        "key_insights": [],
                        "content_map": [],
                        "chapter_rewrites": [],
                        "content_model": {"template": template, "items": [
                            {"role": expected_roles[1], "title": "第二类", "detail": "字段太多会增加录入阻力。", "evidence_ids": ["E0002"]},
                            {"role": expected_roles[0], "title": "第一类", "detail": "今天介绍数据库设计。", "evidence_ids": ["E0001"]},
                        ]},
                    },
                    {
                        "insight_audit": [],
                        "structure_audit": [
                            {"index": 0, "status": "supported", "detail": ""},
                            {"index": 1, "status": "supported", "detail": ""},
                        ],
                        "quick_brief_status": "rejected",
                        "overall_confidence": "high",
                    },
                ])

                def fake_transport(*_args):
                    content = next(responses)
                    return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

                with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}, clear=True):
                    result = enhance_brief(ROWS, BASE.copy(), mode="smart", transport=fake_transport)
                self.assertEqual([item["role"] for item in result["content_model"]["items"]], list(expected_roles))

    def test_tutorial_content_model_keeps_only_audited_native_roles(self):
        responses = iter([
            {
                "title": "数据库教程",
                "summary": "减少字段降低录入阻力。",
                "content_type": "tutorial",
                "key_insights": [],
                "content_map": [],
                "chapter_rewrites": [],
                "content_model": {
                    "template": "tutorial",
                    "items": [
                        {"role": "goal", "title": "目标", "detail": "降低知识记录阻力。", "evidence_ids": ["E0001"]},
                        {"role": "step", "title": "减少字段", "detail": "所有数据库都只能有一个字段。", "evidence_ids": ["E0002"]},
                        {"role": "speaker_position", "title": "错误角色", "detail": "教程不允许访谈角色。", "evidence_ids": ["E0002"]},
                        {"role": "pitfall", "title": "伪造引用", "detail": "不存在的内容。", "evidence_ids": ["E9999"]},
                    ],
                },
            },
            {
                "insight_audit": [],
                "structure_audit": [
                    {"index": 0, "status": "supported", "detail": ""},
                    {"index": 1, "status": "partial", "detail": "只保留真正需要的字段。"},
                    {"index": 2, "status": "supported", "detail": ""},
                    {"index": 3, "status": "supported", "detail": ""},
                ],
                "quick_brief_status": "rejected",
                "overall_confidence": "high",
            },
        ])

        def fake_transport(*_args):
            content = next(responses)
            return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

        with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}, clear=True):
            result = enhance_brief(ROWS, BASE.copy(), mode="smart", transport=fake_transport)

        model = result["content_model"]
        self.assertEqual(model["template"], "tutorial")
        self.assertEqual([item["role"] for item in model["items"]], ["goal", "step"])
        self.assertEqual(model["items"][1]["detail"], "只保留真正需要的字段。")
        self.assertEqual(model["items"][1]["evidence"][0]["evidence_id"], "E0002")
        self.assertEqual(result["agent"]["validated_structure_items"], 2)
        self.assertEqual(result["agent"]["rejected_structure_items"], 2)

    def test_agent_counts_only_the_insights_returned_to_the_page(self):
        candidates = [
            {"title": f"观点{i}", "detail": "字段太多会增加录入阻力。", "evidence_ids": ["E0002"], "claim_type": "video_explicit"}
            for i in range(6)
        ]
        responses = iter([
            {"title": "数据库设计摘要", "summary": "减少字段降低录入阻力。", "content_type": "tutorial", "key_insights": candidates, "content_map": [], "chapter_rewrites": []},
            {"insight_audit": [{"index": i, "status": "supported", "detail": ""} for i in range(6)], "quick_brief_status": "rejected", "overall_confidence": "high"},
        ])

        def fake_transport(*_args):
            content = next(responses)
            return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

        with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}, clear=True):
            result = enhance_brief(ROWS, BASE.copy(), mode="smart", transport=fake_transport)

        self.assertEqual(len(result["key_insights"]), 5)
        self.assertEqual(result["agent"]["validated_insights"], 5)
        self.assertEqual(result["agent"]["validated_candidates"], 6)

    def test_claim_with_any_unknown_evidence_id_is_discarded(self):
        responses = iter([
            {
                "title": "数据库设计",
                "summary": "减少字段降低阻力。",
                "content_type": "tutorial",
                "key_insights": [{
                    "title": "混合引用",
                    "detail": "这条观点包含一个伪造引用。",
                    "evidence_ids": ["E0002", "E9999"],
                    "claim_type": "video_explicit",
                }],
                "content_map": [],
                "chapter_rewrites": [],
            },
            {
                "insight_audit": [{"index": 0, "status": "supported", "detail": ""}],
                "quick_brief_status": "rejected",
                "overall_confidence": "low",
            },
        ])

        def fake_transport(*_args):
            content = next(responses)
            return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

        with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}, clear=True):
            result = enhance_brief(ROWS, BASE.copy(), mode="smart", transport=fake_transport)

        self.assertEqual(result["key_insights"], [])
        self.assertEqual(result["agent"]["rejected_insights"], 1)

    def test_auditor_rejects_a_claim_even_when_its_timestamp_exists(self):
        responses = iter([
            {
                "title": "数据库设计",
                "summary": "数据库设计摘要",
                "content_type": "tutorial",
                "key_insights": [
                    {"title": "虚构结论", "detail": "作者建议购买付费软件。", "evidence_ids": ["E0002"], "claim_type": "video_explicit"}
                ],
                "content_map": [],
                "chapter_rewrites": [],
            },
            {
                "insight_audit": [{"index": 0, "status": "rejected", "detail": ""}],
                "quick_brief_status": "rejected",
                "overall_confidence": "low",
            },
        ])

        def fake_transport(*_args):
            content = next(responses)
            return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

        with patch.dict(os.environ, {"VIDEOBRIEF_LLM_API_KEY": "secret-test-key"}, clear=True):
            result = enhance_brief(ROWS, BASE.copy(), mode="smart", transport=fake_transport)

        self.assertEqual(result["key_insights"], [])
        self.assertEqual(result["agent"]["rejected_insights"], 1)


if __name__ == "__main__":
    unittest.main()
