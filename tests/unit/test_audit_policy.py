import os
import unittest
from unittest.mock import patch

from videobrief.domain.errors import AnalysisUnavailableError
from videobrief.infrastructure.analysis.audit import _merge_agent_output


BASE = {
    "title": "本地标题",
    "summary": "本地摘要",
    "content_type": "tutorial",
    "chapters": [],
    "evidence_store": [
        {"evidence_id": "E0001", "time": "00:00", "seconds": 0, "quote": "原文"}
    ],
    "key_insights": [],
    "content_model": {"template": "tutorial", "items": []},
}
CONFIG = {"provider": "deepseek", "model": "deepseek-chat"}


class FailClosedAuditPolicyTests(unittest.TestCase):
    def test_missing_summary_status_keeps_local_summary(self):
        result = _merge_agent_output(
            BASE,
            {"summary": "未经审计的远端摘要", "content_type": "tutorial", "key_insights": []},
            {"insight_audit": [], "quick_brief_status": "rejected"},
            CONFIG,
        )
        self.assertEqual(result["summary"], "本地摘要")

    def test_partial_quick_brief_without_correction_is_not_accepted(self):
        result = _merge_agent_output(
            BASE,
            {"content_type": "tutorial", "key_insights": [], "quick_brief": {
                "central_question": "问题", "direct_answer": "表述过强", "why_it_matters": "重要",
                "evidence_ids": ["E0001"],
            }},
            {"summary_status": "rejected", "quick_brief_status": "partial", "insight_audit": []},
            CONFIG,
        )
        self.assertNotIn("quick_brief", result)

    def test_smart_adapter_maps_missing_key_to_application_error(self):
        from videobrief.infrastructure.analysis.deepseek import DeepSeekAnalyzer

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AnalysisUnavailableError) as raised:
                DeepSeekAnalyzer().enhance([], BASE, "smart")
        self.assertEqual(raised.exception.stage, "enhancing")
        self.assertNotIn("api_key", raised.exception.to_dict())


if __name__ == "__main__":
    unittest.main()
